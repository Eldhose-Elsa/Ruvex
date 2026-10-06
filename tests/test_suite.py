"""
Unit and Integration Tests for RAW to PNG, WEBP and JPEG converter.
"""
import os
import sys
import shutil
import tempfile
import unittest
import numpy as np
import cv2
import piexif
from PIL import Image

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.constants import (
    SUPPORTED_RAW_EXTENSIONS,
    SUPPORTED_FORMATS_BY_BRAND,
    OUTPUT_FORMATS,
    SCALE_OPTIONS,
    COLOR_SPACES,
    DEMOSAIC_ALGORITHMS,
    WHITE_BALANCE_MODES
)
from core.converter import (
    ConversionConfig,
    determine_output_path,
    scan_raw_files,
    scan_multiple_folders,
    apply_image_scaling,
    ConversionResult
)
from core.metadata import inject_png_metadata, build_exif_bytes, extract_raw_metadata


class TestConstants(unittest.TestCase):
    def test_supported_extensions(self):
        for ext in [".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".rw2", ".orf", ".pef", ".3fr", ".iiq"]:
            self.assertIn(ext, SUPPORTED_RAW_EXTENSIONS)

    def test_output_format_order(self):
        # Format order: PNG 1st, WEBP 2nd, JPEG 3rd
        self.assertEqual(OUTPUT_FORMATS[0], "PNG")
        self.assertEqual(OUTPUT_FORMATS[1], "WEBP")
        self.assertEqual(OUTPUT_FORMATS[2], "JPEG")


class TestSubfolderHierarchyPreservation(unittest.TestCase):
    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.out_dir = tempfile.mkdtemp()

        # Create subfolders
        self.sub1 = os.path.join(self.src_dir, "event1", "portraits")
        self.sub2 = os.path.join(self.src_dir, "event2")
        os.makedirs(self.sub1, exist_ok=True)
        os.makedirs(self.sub2, exist_ok=True)

        self.file1 = os.path.join(self.sub1, "photoA.CR2")
        self.file2 = os.path.join(self.sub2, "photoB.CR2")
        self.file3 = os.path.join(self.src_dir, "root.CR2")

        for f in [self.file1, self.file2, self.file3]:
            with open(f, "w") as fp:
                fp.write("dummy")

    def tearDown(self):
        shutil.rmtree(self.src_dir, ignore_errors=True)
        shutil.rmtree(self.out_dir, ignore_errors=True)

    def test_preserve_subfolders_true(self):
        cfg = ConversionConfig(
            output_dir=self.out_dir,
            keep_subfolder_structure=True,
            base_input_dir=self.src_dir,
            all_input_files=[self.file1, self.file2, self.file3]
        )

        out1 = determine_output_path(self.file1, cfg)
        out2 = determine_output_path(self.file2, cfg)
        out3 = determine_output_path(self.file3, cfg)

        # Check that event1/portraits is preserved
        expected1 = os.path.join(self.out_dir, "event1", "portraits", "photoA.png")
        expected2 = os.path.join(self.out_dir, "event2", "photoB.png")
        expected3 = os.path.join(self.out_dir, "root.png")

        self.assertEqual(os.path.normpath(out1), os.path.normpath(expected1))
        self.assertEqual(os.path.normpath(out2), os.path.normpath(expected2))
        self.assertEqual(os.path.normpath(out3), os.path.normpath(expected3))

    def test_preserve_subfolders_false_flattens(self):
        cfg = ConversionConfig(
            output_dir=self.out_dir,
            keep_subfolder_structure=False,
            base_input_dir=self.src_dir,
            all_input_files=[self.file1, self.file2, self.file3]
        )

        out1 = determine_output_path(self.file1, cfg)
        expected1 = os.path.join(self.out_dir, "photoA.png")
        self.assertEqual(os.path.normpath(out1), os.path.normpath(expected1))


class TestScaling(unittest.TestCase):
    def test_75_percent_scale(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        scaled = apply_image_scaling(img, "75% Scale (Optimal < RAW Size)")
        self.assertEqual(scaled.shape[:2], (75, 75))

    def test_50_percent_scale(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        scaled = apply_image_scaling(img, "50% Scale (Half Size)")
        self.assertEqual(scaled.shape[:2], (50, 50))

    def test_40_percent_scale(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        scaled = apply_image_scaling(img, "40% Scale (Crisp < 8MB)")
        self.assertEqual(scaled.shape[:2], (40, 40))

    def test_auto_fit_scale(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        scaled = apply_image_scaling(img, "Target < 10 MB (Auto-Fit)")
        self.assertEqual(scaled.shape[:2], (42, 42))


if __name__ == "__main__":
    unittest.main()
