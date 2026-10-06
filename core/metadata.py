"""
Metadata extraction from RAW files and injection into PNG files.
Supports EXIF tags, PNG tEXt chunks, and PNG eXIf chunks.
"""
import io
import os
import struct
import zlib
from typing import Dict, Any, Optional, Tuple
import exifread
import piexif
from PIL import Image


def extract_raw_metadata(raw_path: str) -> Dict[str, str]:
    """
    Extract human-readable metadata tags from a RAW file.
    """
    metadata: Dict[str, str] = {}
    if not os.path.isfile(raw_path):
        return metadata

    try:
        with open(raw_path, 'rb') as f:
            tags = exifread.process_file(f, details=False, stop_tag='UNDEF')

        # Map common tags to clean keys
        mapping = {
            'Image Make': 'Make',
            'Image Model': 'Model',
            'Image DateTime': 'DateTimeOriginal',
            'EXIF DateTimeOriginal': 'DateTimeOriginal',
            'EXIF ExposureTime': 'ExposureTime',
            'EXIF FNumber': 'FNumber',
            'EXIF ISOSpeedRatings': 'ISO',
            'EXIF FocalLength': 'FocalLength',
            'EXIF LensModel': 'LensModel',
            'Image Software': 'OriginalSoftware',
        }

        for tag_name, clean_name in mapping.items():
            if tag_name in tags and clean_name not in metadata:
                val = str(tags[tag_name]).strip()
                if val:
                    metadata[clean_name] = val

    except Exception:
        pass

    metadata['Converter'] = 'Ruvex RAW to Image Converter (LibRaw + OpenCV)'
    return metadata


def build_exif_bytes(raw_path: str, meta: Dict[str, str]) -> Optional[bytes]:
    """
    Build standard EXIF TIFF byte block suitable for PNG eXIf chunk.
    Attempts to read directly or assemble using piexif.
    """
    try:
        zeroth_ifd = {}
        exif_ifd = {}

        if 'Make' in meta:
            zeroth_ifd[piexif.ImageIFD.Make] = meta['Make'].encode('utf-8', errors='ignore')
        if 'Model' in meta:
            zeroth_ifd[piexif.ImageIFD.Model] = meta['Model'].encode('utf-8', errors='ignore')
        if 'OriginalSoftware' in meta:
            zeroth_ifd[piexif.ImageIFD.Software] = meta['OriginalSoftware'].encode('utf-8', errors='ignore')
        else:
            zeroth_ifd[piexif.ImageIFD.Software] = b'RAWtoPNG LibRaw'

        if 'DateTimeOriginal' in meta:
            dt_str = meta['DateTimeOriginal'].encode('utf-8', errors='ignore')
            exif_ifd[piexif.ExifIFD.DateTimeOriginal] = dt_str

        # Also attempt to parse ISO
        if 'ISO' in meta:
            try:
                iso_val = int(meta['ISO'])
                exif_ifd[piexif.ExifIFD.ISOSpeedRatings] = iso_val
            except Exception:
                pass

        exif_dict = {
            '0th': zeroth_ifd,
            'Exif': exif_ifd,
            'GPS': {},
            '1st': {},
            'interop': {}
        }
        return piexif.dump(exif_dict)
    except Exception:
        return None


def inject_png_metadata(png_path: str, metadata: Dict[str, str], exif_bytes: Optional[bytes] = None) -> bool:
    """
    Injects tEXt chunks and eXIf chunk into an existing PNG file on disk.
    Preserves image integrity while making metadata accessible to all PNG viewers.
    """
    if not os.path.isfile(png_path):
        return False

    try:
        with open(png_path, 'rb') as f:
            png_data = f.read()

        if not png_data.startswith(b'\x89PNG\r\n\x1a\n'):
            return False

        iend_pos = png_data.rfind(b'IEND')
        if iend_pos == -1:
            return False

        chunk_start = iend_pos - 4
        new_chunks = []

        # 1. Add tEXt chunks for metadata key-values
        for key, val in metadata.items():
            try:
                keyword_bytes = key.encode('latin-1', errors='ignore')[:79]
                text_bytes = str(val).encode('latin-1', errors='ignore')
                cdata = keyword_bytes + b'\x00' + text_bytes
                crc = zlib.crc32(b'tEXt' + cdata) & 0xffffffff
                chunk = struct.pack('>I', len(cdata)) + b'tEXt' + cdata + struct.pack('>I', crc)
                new_chunks.append(chunk)
            except Exception:
                continue

        # 2. Add eXIf chunk if available
        if exif_bytes:
            try:
                crc = zlib.crc32(b'eXIf' + exif_bytes) & 0xffffffff
                chunk = struct.pack('>I', len(exif_bytes)) + b'eXIf' + exif_bytes + struct.pack('>I', crc)
                new_chunks.append(chunk)
            except Exception:
                pass

        if not new_chunks:
            return True

        assembled = png_data[:chunk_start] + b''.join(new_chunks) + png_data[chunk_start:]
        with open(png_path, 'wb') as f:
            f.write(assembled)

        return True
    except Exception:
        return False


def extract_thumbnail_preview(raw_path: str) -> Optional[Image.Image]:
    """
    Quickly extract embedded JPEG/RAW thumbnail from a RAW file for GUI preview,
    falling back to half-size raw decoding if no thumbnail exists.
    """
    import rawpy
    try:
        with rawpy.imread(raw_path) as raw:
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    return Image.open(io.BytesIO(thumb.data))
                elif thumb.format == rawpy.ThumbFormat.BITMAP:
                    return Image.fromarray(thumb.data)
            except Exception:
                pass

            # Fallback: fast half-size decode
            rgb = raw.postprocess(half_size=True, use_camera_wb=True)
            return Image.fromarray(rgb)
    except Exception:
        return None
