"""
Constants and options for RAW to PNG/WEBP/JPEG converter.
"""
from typing import Dict, List
import rawpy

SUPPORTED_RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".crw",   # Canon
    ".nef", ".nrw",           # Nikon
    ".arw", ".srf", ".sr2",   # Sony
    ".dng",                   # Adobe DNG (Smartphones, Leica, DJI, Pentax)
    ".raf",                   # Fujifilm
    ".rw2", ".raw",           # Panasonic Lumix
    ".orf", ".ori",           # Olympus / OM System
    ".pef", ".ptx",           # Pentax
    ".3fr", ".fff",           # Hasselblad
    ".iiq",                   # Phase One
    ".erf",                   # Epson
    ".mef", ".mos",           # Mamiya
    ".rwl",                   # Leica
    ".srw",                   # Samsung
    ".x3f",                   # Sigma
}

# Grouped formats with camera brand information for clear UI display
SUPPORTED_FORMATS_BY_BRAND: Dict[str, List[str]] = {
    "Canon": [".CR2", ".CR3", ".CRW"],
    "Nikon": [".NEF", ".NRW"],
    "Sony": [".ARW", ".SRF", ".SR2"],
    "Adobe / DNG": [".DNG (Smartphones, Leica, DJI, Pentax)"],
    "Fujifilm": [".RAF (Bayer & X-Trans)"],
    "Panasonic Lumix": [".RW2", ".RAW"],
    "Olympus / OM System": [".ORF", ".ORI"],
    "Pentax": [".PEF", ".PTX"],
    "Hasselblad": [".3FR", ".FFF"],
    "Phase One": [".IIQ"],
    "Leica": [".RWL", ".DNG"],
    "Samsung": [".SRW"],
    "Sigma": [".X3F"],
    "Epson": [".ERF"],
    "Mamiya": [".MEF", ".MOS"]
}

# Format order: PNG 1st (default), WEBP 2nd, JPEG 3rd
OUTPUT_FORMATS = ["PNG", "WEBP", "JPEG"]

SCALE_OPTIONS = [
    "Target < 10 MB (Auto-Fit)",
    "40% Scale (Crisp < 8MB)",
    "35% Scale (Safe < 6MB)",
    "2K QHD (2560px max)",
    "Full HD (1920px max)",
    "50% Scale (Half Size)",
    "75% Scale (Optimal < RAW)",
    "Original (100%)"
]

COLOR_SPACES: Dict[str, rawpy.ColorSpace] = {
    "sRGB": rawpy.ColorSpace.sRGB,
    "Adobe RGB": rawpy.ColorSpace.Adobe,
    "ProPhoto RGB": rawpy.ColorSpace.ProPhoto,
    "Wide Gamut": rawpy.ColorSpace.Wide,
    "Raw": rawpy.ColorSpace.raw,
}

DEMOSAIC_ALGORITHMS: Dict[str, rawpy.DemosaicAlgorithm] = {
    "AHD": rawpy.DemosaicAlgorithm.AHD,
    "AMAZE": rawpy.DemosaicAlgorithm.AAHD if not hasattr(rawpy.DemosaicAlgorithm, 'AMAZE') else getattr(rawpy.DemosaicAlgorithm, 'AMAZE'),
    "DCB": rawpy.DemosaicAlgorithm.DCB,
    "VNG": rawpy.DemosaicAlgorithm.VNG,
    "LINEAR": rawpy.DemosaicAlgorithm.LINEAR,
}

WHITE_BALANCE_MODES = ["Camera", "Auto", "Daylight"]
BIT_DEPTH_OPTIONS = [8, 16]
JPEG_QUALITY_DEFAULT = 95
PNG_COMPRESSION_DEFAULT = 9
MAX_TARGET_BYTES = 9.8 * 1024 * 1024  # 9.8 MB strict ceiling for under 10MB
