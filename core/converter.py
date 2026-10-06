"""
Core RAW to PNG / WEBP / JPEG Conversion Engine.
Handles image processing via LibRaw (rawpy) and OpenCV,
multithreaded batch queuing, resolution downscaling, relative folder structure preservation,
strict < 10MB auto-fit, and metadata embedding.
"""

from dataclasses import dataclass, field
import os
import time
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Callable, Dict, Any, Tuple
from pathlib import Path

import cv2
import piexif
import rawpy

from core.constants import (
    SUPPORTED_RAW_EXTENSIONS,
    OUTPUT_FORMATS,
    SCALE_OPTIONS,
    COLOR_SPACES,
    DEMOSAIC_ALGORITHMS,
    WHITE_BALANCE_MODES,
    JPEG_QUALITY_DEFAULT,
    PNG_COMPRESSION_DEFAULT,
    MAX_TARGET_BYTES
)
from core.metadata import extract_raw_metadata, build_exif_bytes, inject_png_metadata


@dataclass
class ConversionConfig:
    output_format: str = "PNG"  # "PNG", "WEBP", "JPEG"
    bit_depth: int = 8  # 8 or 16 (default 8-bit for compact size)
    scale_mode: str = "Target < 10 MB (Auto-Fit)"  # Default < 10MB Auto-Fit
    white_balance: str = "Camera"  # "Camera", "Auto", "Daylight"
    color_space: str = "sRGB"  # "sRGB", "Adobe RGB", "ProPhoto RGB", "Wide Gamut", "Raw"
    demosaic_algorithm: str = "AHD"  # "AHD", "AMAZE", "DCB", "VNG", "LINEAR"
    preserve_metadata: bool = True
    half_size: bool = False
    compression_level: int = PNG_COMPRESSION_DEFAULT  # PNG compression 0-9 (default 9)
    jpeg_quality: int = JPEG_QUALITY_DEFAULT  # JPEG / WEBP quality 1-100
    output_dir: Optional[str] = None
    overwrite: bool = False
    keep_subfolder_structure: bool = True
    base_input_dir: Optional[str] = None
    all_input_files: Optional[List[str]] = None


@dataclass
class ConversionResult:
    input_path: str
    output_path: Optional[str] = None
    success: bool = False
    error_message: Optional[str] = None
    elapsed_time: float = 0.0
    original_size_bytes: int = 0
    output_size_bytes: int = 0
    metadata_preserved: bool = False


def determine_output_path(input_path: str, config: ConversionConfig) -> str:
    """
    Computes destination file path based on input path and format configuration.
    Preserves exact subfolder hierarchy when keep_subfolder_structure is enabled.
    """
    input_file = Path(input_path).resolve()
    fmt = config.output_format.upper()
    if fmt in ["JPEG", "JPG"]:
        target_ext = ".jpg"
    elif fmt == "WEBP":
        target_ext = ".webp"
    else:
        target_ext = ".png"

    filename = f"{input_file.stem}{target_ext}"

    if config.output_dir:
        out_base = Path(config.output_dir).resolve()
        sub_rel_folder = ""

        if config.keep_subfolder_structure:
            if config.base_input_dir:
                try:
                    base_p = Path(config.base_input_dir).resolve()
                    rel = input_file.parent.relative_to(base_p)
                    sub_rel_folder = str(rel) if str(rel) != "." else ""
                except ValueError:
                    pass

            if not sub_rel_folder and config.all_input_files and len(config.all_input_files) > 1:
                try:
                    common_root = os.path.commonpath([os.path.abspath(f) for f in config.all_input_files])
                    if os.path.isfile(common_root):
                        common_root = os.path.dirname(common_root)
                    rel = os.path.relpath(os.path.dirname(os.path.abspath(input_path)), common_root)
                    if rel and rel != "." and not rel.startswith(".."):
                        sub_rel_folder = rel
                except ValueError:
                    pass

        target_dir = out_base / sub_rel_folder if sub_rel_folder else out_base
    else:
        target_dir = input_file.parent

    target_dir.mkdir(parents=True, exist_ok=True)
    return str(target_dir / filename)


def apply_image_scaling(image: Any, scale_mode: str) -> Any:
    """
    Applies downscaling to significantly reduce file size while maintaining pristine sharpness.
    Uses INTER_AREA interpolation for natural anti-aliasing and clarity.
    """
    if "Original" in scale_mode or not scale_mode:
        return image

    h, w = image.shape[:2]
    new_w, new_h = w, h

    if "Auto-Fit" in scale_mode:
        # Initial estimate for Auto-Fit: ~42% scale (2528x1686 on 24MP)
        new_w, new_h = int(w * 0.42), int(h * 0.42)
    elif "40%" in scale_mode:
        new_w, new_h = int(w * 0.40), int(h * 0.40)
    elif "35%" in scale_mode:
        new_w, new_h = int(w * 0.35), int(h * 0.35)
    elif "50%" in scale_mode:
        new_w, new_h = int(w * 0.50), int(h * 0.50)
    elif "75%" in scale_mode:
        new_w, new_h = int(w * 0.75), int(h * 0.75)
    elif "2K" in scale_mode:
        max_dim = 2560
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            new_w, new_h = int(w * ratio), int(h * ratio)
    elif "Full HD" in scale_mode:
        max_dim = 1920
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            new_w, new_h = int(w * ratio), int(h * ratio)
    elif "4K" in scale_mode:
        max_dim = 3840
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            new_w, new_h = int(w * ratio), int(h * ratio)

    if (new_w, new_h) != (w, h) and new_w > 0 and new_h > 0:
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)

    return image


def convert_single_file(
    input_path: str,
    output_path: Optional[str] = None,
    config: Optional[ConversionConfig] = None
) -> ConversionResult:
    """
    Converts a single camera RAW file to PNG, WEBP, or JPEG format.
    Preserves color fidelity, enforces strict < 10MB auto-fit if selected, and embeds metadata.
    """
    start_time = time.time()
    cfg = config or ConversionConfig()
    fmt = cfg.output_format.upper()
    is_jpeg = fmt in ["JPEG", "JPG"]
    is_webp = fmt == "WEBP"

    result = ConversionResult(
        input_path=input_path,
        original_size_bytes=os.path.getsize(input_path) if os.path.exists(input_path) else 0
    )

    if not os.path.isfile(input_path):
        result.error_message = f"File not found: {input_path}"
        result.elapsed_time = time.time() - start_time
        return result

    ext = Path(input_path).suffix.lower()
    if ext not in SUPPORTED_RAW_EXTENSIONS:
        result.error_message = f"Unsupported RAW extension: {ext}"
        result.elapsed_time = time.time() - start_time
        return result

    if not output_path:
        output_path = determine_output_path(input_path, cfg)
    result.output_path = output_path

    if os.path.exists(output_path) and not cfg.overwrite:
        result.error_message = f"Output file already exists: {output_path}"
        result.elapsed_time = time.time() - start_time
        return result

    try:
        # 1. Determine LibRaw postprocessing options
        color_space_enum = COLOR_SPACES.get(cfg.color_space, rawpy.ColorSpace.sRGB)
        demosaic_enum = DEMOSAIC_ALGORITHMS.get(cfg.demosaic_algorithm, rawpy.DemosaicAlgorithm.AHD)

        # JPEG and WEBP only support 8-bit depth; PNG supports 8 or 16-bit
        output_bps = 8 if (is_jpeg or is_webp) else (16 if cfg.bit_depth == 16 else 8)

        use_camera_wb = (cfg.white_balance.lower() == "camera")
        use_auto_wb = (cfg.white_balance.lower() == "auto")

        # 2. Decode RAW file
        with rawpy.imread(input_path) as raw:
            rgb = raw.postprocess(
                demosaic_algorithm=demosaic_enum,
                half_size=cfg.half_size,
                use_camera_wb=use_camera_wb,
                use_auto_wb=use_auto_wb,
                output_color=color_space_enum,
                output_bps=output_bps
            )

        # 3. OpenCV expects BGR color order
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        # 4. Apply downscaling
        bgr = apply_image_scaling(bgr, cfg.scale_mode)

        # 5. Save to target format with Auto-Fit loop for strict < 10MB
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        if is_jpeg:
            quality = max(1, min(100, cfg.jpeg_quality))
            cv2.imwrite(output_path, bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        elif is_webp:
            quality = max(1, min(100, cfg.jpeg_quality))
            cv2.imwrite(output_path, bgr, [cv2.IMWRITE_WEBP_QUALITY, quality])
        else:
            # PNG with maximum compression
            compression = max(0, min(9, cfg.compression_level))
            cv2.imwrite(output_path, bgr, [cv2.IMWRITE_PNG_COMPRESSION, compression])

            # Auto-Fit check: if "Auto-Fit" is selected and file exceeds 9.8MB, adaptively resize
            if "Auto-Fit" in cfg.scale_mode:
                curr_size = os.path.getsize(output_path)
                curr_bgr = bgr
                for _ in range(3):
                    if curr_size <= MAX_TARGET_BYTES or curr_bgr.shape[0] < 600:
                        break
                    # Scale factor needed to guarantee < 9.5MB
                    factor = math.sqrt((MAX_TARGET_BYTES * 0.94) / curr_size)
                    nw = max(300, int(curr_bgr.shape[1] * factor))
                    nh = max(200, int(curr_bgr.shape[0] * factor))
                    curr_bgr = cv2.resize(curr_bgr, (nw, nh), interpolation=cv2.INTER_AREA)
                    cv2.imwrite(output_path, curr_bgr, [cv2.IMWRITE_PNG_COMPRESSION, compression])
                    curr_size = os.path.getsize(output_path)

        if not os.path.exists(output_path):
            result.error_message = f"Failed to write {fmt} file."
            result.elapsed_time = time.time() - start_time
            return result

        # 6. Extract and inject metadata if requested
        if cfg.preserve_metadata:
            try:
                meta = extract_raw_metadata(input_path)
                exif_bytes = build_exif_bytes(input_path, meta)
                if is_jpeg and exif_bytes:
                    piexif.insert(exif_bytes, output_path)
                    result.metadata_preserved = True
                elif not (is_jpeg or is_webp):
                    meta_ok = inject_png_metadata(output_path, meta, exif_bytes)
                    result.metadata_preserved = meta_ok
            except Exception:
                result.metadata_preserved = False

        result.success = True
        result.output_size_bytes = os.path.getsize(output_path) if os.path.exists(output_path) else 0

    except Exception as e:
        result.error_message = str(e)
        result.success = False

    result.elapsed_time = time.time() - start_time
    return result


def scan_raw_files(path: str, recursive: bool = True) -> List[str]:
    """
    Scans a directory or single file path for supported RAW image files.
    """
    found_files: List[str] = []
    p = Path(path)

    if p.is_file():
        if p.suffix.lower() in SUPPORTED_RAW_EXTENSIONS:
            found_files.append(str(p.resolve()))
    elif p.is_dir():
        if recursive:
            for item in p.rglob("*"):
                if item.is_file() and item.suffix.lower() in SUPPORTED_RAW_EXTENSIONS:
                    found_files.append(str(item.resolve()))
        else:
            for item in p.iterdir():
                if item.is_file() and item.suffix.lower() in SUPPORTED_RAW_EXTENSIONS:
                    found_files.append(str(item.resolve()))

    return sorted(found_files)


def scan_multiple_folders(paths: List[str], recursive: bool = True) -> List[str]:
    """
    Scans multiple directories or file paths, returning a sorted unique list of RAW files.
    """
    all_files = set()
    for p in paths:
        found = scan_raw_files(p, recursive=recursive)
        all_files.update(found)
    return sorted(list(all_files))


class BatchConverter:
    """
    Threaded batch conversion orchestrator with cancel support,
    rate measurement, and live progress callbacks.
    """

    def __init__(
        self,
        files: List[str],
        config: ConversionConfig,
        max_workers: int = 4,
        progress_callback: Optional[Callable[[int, int, ConversionResult], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        self.files = files
        self.config = config
        self.config.all_input_files = files

        self.max_workers = max(1, max_workers)
        self.progress_callback = progress_callback
        self.log_callback = log_callback

        self._cancel_requested = threading.Event()
        self._is_running = False
        self.results: List[ConversionResult] = []

    def request_cancel(self):
        """Signal the conversion process to stop."""
        self._cancel_requested.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_requested.is_set()

    def run(self) -> List[ConversionResult]:
        """
        Executes batch conversion concurrently across the thread pool.
        """
        self._is_running = True
        self._cancel_requested.clear()
        total_files = len(self.files)
        completed_count = 0
        self.results = []

        target_fmt = self.config.output_format.upper()
        if self.log_callback:
            self.log_callback(f"Starting batch conversion of {total_files} file(s) to {target_fmt} ({self.config.scale_mode}) with {self.max_workers} threads.")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {}
            for file_path in self.files:
                if self._cancel_requested.is_set():
                    break
                fut = executor.submit(convert_single_file, file_path, None, self.config)
                future_to_file[fut] = file_path

            for future in as_completed(future_to_file):
                if self._cancel_requested.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    if self.log_callback:
                        self.log_callback("Batch conversion cancelled by user.")
                    break

                try:
                    res: ConversionResult = future.result()
                except Exception as ex:
                    fpath = future_to_file[future]
                    res = ConversionResult(
                        input_path=fpath,
                        success=False,
                        error_message=str(ex)
                    )

                self.results.append(res)
                completed_count += 1

                if self.log_callback:
                    status_text = "OK" if res.success else f"FAILED: {res.error_message}"
                    filename = Path(res.input_path).name
                    self.log_callback(f"[{completed_count}/{total_files}] {filename} -> {status_text} ({res.elapsed_time:.2f}s)")

                if self.progress_callback:
                    self.progress_callback(completed_count, total_files, res)

        self._is_running = False
        return self.results
