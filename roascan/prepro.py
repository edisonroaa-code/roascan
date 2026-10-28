"""
roascan.prepro: Image Preprocessing interface for RoaScan (clean-room).

Provides explicit control over brightness, contrast, binarization threshold,
and worker threads, backed by ``roascan_core.dll``. Settings configured inside an
``RoaScanPreprocessor`` context or passed to ``RoaScanEngine`` are applied by the
native preprocessing pipeline.
"""

from typing import Optional
from .native import get_native_driver


class RoaScanPreprocessor:
    """Clean-room image preprocessing interface backed by roascan_core.dll."""

    # Shared last-configured defaults so standalone RoaScanPreprocessor blocks
    # propagate naturally when followed by RoaScanEngine in classic scripts.
    _active_brightness: int = 128
    _active_contrast: int = 128
    _active_threshold: int = 0  # 0 = adaptive Sauvola
    _active_threads: int = 4

    def __init__(self, dll_dir: Optional[str] = None):
        self.driver = get_native_driver(dll_dir)
        self.brightness: int = 128
        self.contrast: int = 128
        self.threshold: int = 0  # 0 = adaptive Sauvola
        self.num_threads: int = 4

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        pass

    def get_version(self) -> str:
        if self.driver and self.driver.core and hasattr(self.driver.core, "roascan_native_version"):
            v = self.driver.core.roascan_native_version()
            if v:
                return v.decode("utf-8", errors="replace")
        return "2.0.0-roascan-native"

    def get_build_info(self) -> dict:
        return {
            "version": self.get_version(),
            "branch": "main",
            "engine": "clean-room-cxx17",
        }

    def set_brightness(self, value: int):
        self.brightness = max(0, min(255, int(value)))
        RoaScanPreprocessor._active_brightness = self.brightness

    def set_contrast(self, value: int):
        self.contrast = max(0, min(255, int(value)))
        RoaScanPreprocessor._active_contrast = self.contrast

    def set_threshold(self, threshold: int):
        self.threshold = max(0, min(255, int(threshold)))
        RoaScanPreprocessor._active_threshold = self.threshold

    def set_thread_count(self, num_threads: int = 4):
        self.num_threads = max(1, int(num_threads))
        RoaScanPreprocessor._active_threads = self.num_threads

    set_threads = set_thread_count

    @classmethod
    def reset_defaults(cls):
        cls._active_brightness = 128
        cls._active_contrast = 128
        cls._active_threshold = 0
        cls._active_threads = 4
