"""
Command Line Interface (CLI) for RAW to PNG / JPEG / WEBP converter.
"""
import argparse
import os
import sys
import time
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.constants import (
    SUPPORTED_RAW_EXTENSIONS,
    SUPPORTED_FORMATS_BY_BRAND,
    OUTPUT_FORMATS,
    SCALE_OPTIONS,
    COLOR_SPACES,
    DEMOSAIC_ALGORITHMS,
    WHITE_BALANCE_MODES,
    BIT_DEPTH_OPTIONS,
    JPEG_QUALITY_DEFAULT,
    PNG_COMPRESSION_DEFAULT
)
from core.converter import (
    ConversionConfig,
    convert_single_file,
    scan_raw_files,
    scan_multiple_folders,
    BatchConverter
)


def format_bytes(num_bytes: int) -> str:
    """Format bytes into readable MB/GB string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def print_supported_formats():
    print("\n" + "=" * 65)
    print("  ALL SUPPORTED CAMERA RAW FORMATS (25+ Extensions)")
    print("=" * 65)
    for brand, exts in SUPPORTED_FORMATS_BY_BRAND.items():
        exts_str = ", ".join(exts)
        print(f"   [{brand:<16}] : {exts_str}")
    print("=" * 65)
    print("  All raw extensions:")
    all_exts = sorted(list(SUPPORTED_RAW_EXTENSIONS))
    for i in range(0, len(all_exts), 6):
        print("    " + "  ".join(f"{ext:<7}" for ext in all_exts[i:i+6]))
    print("=" * 65 + "\n")


def main_cli(args=None):
    parser = argparse.ArgumentParser(
        description="Ruvex - High-speed batch converter for camera RAW images (CR2, CR3, NEF, ARW, DNG, RAF, etc.)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "inputs",
        nargs="*",
        help="One or more input RAW files or directories containing RAW images"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output directory or target image file"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["JPEG", "PNG", "WEBP", "JPG"],
        default="JPEG",
        help="Output image format (JPEG produces compact ~3-6MB files, PNG is lossless, WEBP is ~2-4MB)"
    )
    parser.add_argument(
        "-s", "--scale",
        choices=SCALE_OPTIONS,
        default="Original (100%)",
        help="Resolution downscaling (cuts pixel count to drastically reduce file sizes)"
    )
    parser.add_argument(
        "-q", "--jpeg-quality",
        type=int,
        default=JPEG_QUALITY_DEFAULT,
        help="JPEG / WEBP quality level (1 to 100)"
    )
    parser.add_argument(
        "-b", "--bit-depth",
        type=int,
        choices=BIT_DEPTH_OPTIONS,
        default=8,
        help="Output bit depth for PNG (8 for standard, 16 for HDR)"
    )
    parser.add_argument(
        "-w", "--wb",
        choices=["Camera", "Auto", "Daylight"],
        default="Camera",
        help="White balance method to apply"
    )
    parser.add_argument(
        "-c", "--color-space",
        choices=list(COLOR_SPACES.keys()),
        default="sRGB",
        help="Output RGB color space"
    )
    parser.add_argument(
        "-d", "--demosaic",
        choices=list(DEMOSAIC_ALGORITHMS.keys()),
        default="AHD",
        help="Demosaicing algorithm (AHD = quality, AMAZE = fine detail, LINEAR = fast)"
    )
    parser.add_argument(
        "-t", "--threads",
        type=int,
        default=min(4, os.cpu_count() or 4),
        help="Number of concurrent worker threads (2-4 recommended for 8GB RAM PCs)"
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recursively scan subfolders when input contains directories"
    )
    parser.add_argument(
        "--compression",
        type=int,
        default=PNG_COMPRESSION_DEFAULT,
        help="PNG compression level (0-9, default 9 for maximum lossless compression)"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output image files"
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help="Do not copy camera EXIF metadata into output image"
    )
    parser.add_argument(
        "--list-formats",
        action="store_true",
        help="List all supported camera RAW formats by brand and exit"
    )

    parsed = parser.parse_args(args)

    if parsed.list_formats:
        print_supported_formats()
        return 0

    if not parsed.inputs:
        parser.print_help()
        return 1

    # Check input paths
    valid_inputs = []
    for p in parsed.inputs:
        abs_p = os.path.abspath(p)
        if os.path.exists(abs_p):
            valid_inputs.append(abs_p)
        else:
            print(f"Warning: Input path '{p}' does not exist, skipping.", file=sys.stderr)

    if not valid_inputs:
        print("Error: No valid input files or directories found.", file=sys.stderr)
        return 1

    output_fmt = "JPEG" if parsed.format.upper() in ["JPEG", "JPG"] else ("WEBP" if parsed.format.upper() == "WEBP" else "PNG")

    config = ConversionConfig(
        output_format=output_fmt,
        scale_mode=parsed.scale,
        jpeg_quality=parsed.jpeg_quality,
        bit_depth=parsed.bit_depth,
        white_balance=parsed.wb,
        color_space=parsed.color_space,
        demosaic_algorithm=parsed.demosaic,
        preserve_metadata=not parsed.no_metadata,
        compression_level=parsed.compression,
        output_dir=os.path.abspath(parsed.output) if parsed.output else None,
        overwrite=parsed.overwrite,
        keep_subfolder_structure=parsed.recursive,
        base_input_dir=valid_inputs[0] if (len(valid_inputs) == 1 and os.path.isdir(valid_inputs[0])) else None
    )

    # Gather files across all input folders
    files_to_process = scan_multiple_folders(valid_inputs, recursive=parsed.recursive)
    if not files_to_process:
        print(f"No supported RAW files found in the provided inputs.")
        print_supported_formats()
        return 1

    print("\n" + "=" * 65)
    print(f"  RUVEX - RAW TO {output_fmt} CONVERTER")
    print("=" * 65)
    print(f"  Input Source(s): {len(valid_inputs)} location(s)")
    print(f"  Total Files:     {len(files_to_process)}")
    print(f"  Output Format:   {output_fmt}" + (f" (Quality: {config.jpeg_quality}%)" if output_fmt in ["JPEG", "WEBP"] else f" ({config.bit_depth}-bit, L{config.compression_level})"))
    print(f"  Resolution:      {config.scale_mode}")
    print(f"  White Balance:   {config.white_balance}")
    print(f"  Color Space:     {config.color_space}")
    print(f"  Metadata:        {'Preserved' if config.preserve_metadata else 'Skipped'}")
    print(f"  Worker Threads:  {parsed.threads}")
    print("=" * 65 + "\n")

    start_batch_time = time.time()

    def log_line(msg: str):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")

    converter = BatchConverter(
        files=files_to_process,
        config=config,
        max_workers=parsed.threads,
        log_callback=log_line
    )

    results = converter.run()
    elapsed_total = time.time() - start_batch_time

    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count
    total_out_bytes = sum(r.output_size_bytes for r in results if r.success)

    print("\n" + "-" * 65)
    print("  CONVERSION SUMMARY")
    print("-" * 65)
    print(f"  Total Processed: {len(results)}")
    print(f"  Successful:      {success_count}")
    print(f"  Failed / Skipped:{fail_count}")
    print(f"  Total Out Size:  {format_bytes(total_out_bytes)}")
    print(f"  Total Duration:  {elapsed_total:.2f} seconds")
    if len(results) > 0 and elapsed_total > 0:
        speed = len(results) / elapsed_total
        print(f"  Average Speed:   {speed:.2f} images/sec")
    print("-" * 65 + "\n")

    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main_cli())
