"""
roascan.native: Low-level C ABI Native Interop Driver for RoaScan (clean-room).

Loads the clean-room ``roascan_core.dll`` / ``libroascan_core.so`` (C-ABI) only.
No proprietary binary is referenced, loaded, or bound.
"""

import os
import ctypes
from ctypes import (
    c_int16, c_int32, c_uint8, c_float, c_double,
    c_char_p, c_void_p, POINTER, Structure
)


class RoaScanRect(Structure):
    """Bounding box coordinates for zones, lines, words, and characters."""
    _fields_ = [
        ("left", c_int32),
        ("top", c_int32),
        ("right", c_int32),
        ("bottom", c_int32),
    ]

    def to_tuple(self):
        return (self.left, self.top, self.right, self.bottom)

    def __repr__(self):
        return f"RoaScanRect(left={self.left}, top={self.top}, right={self.right}, bottom={self.bottom})"


class RoaScanNativeDriver:
    """Singleton C-ABI interop driver for the clean-room native core."""
    _instance = None

    def __init__(self, dll_dir=None):
        if dll_dir is None:
            dll_dir = os.environ.get("ROASCAN_NATIVE_DIR")
        if dll_dir is None:
            dll_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.dll_dir = os.path.abspath(dll_dir)
        if hasattr(os, "add_dll_directory") and os.path.isdir(self.dll_dir):
            try:
                os.add_dll_directory(self.dll_dir)
            except Exception:
                pass

        self.core = self._load_dll(["roascan_core.dll", "libroascan_core.so", "libroascan_core.dylib"])
        self._bind_core()

    @property
    def is_available(self) -> bool:
        return self.core is not None

    def version(self) -> str:
        if self.core and hasattr(self.core, "roascan_native_version"):
            v = self.core.roascan_native_version()
            if v:
                return v.decode("utf-8", errors="replace")
        return "2.0.0-roascan"

    def _load_dll(self, candidates):
        if isinstance(candidates, str):
            candidates = [candidates]

        search_dirs = []
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.isdir(pkg_dir):
            search_dirs.append(pkg_dir)

        env_dir = os.environ.get("ROASCAN_NATIVE_DIR")
        if env_dir and os.path.isdir(env_dir):
            search_dirs.append(os.path.abspath(env_dir))

        # Traverse up from self.dll_dir to locate roascan-native/build/Release first
        p = self.dll_dir
        for _ in range(4):
            for cand in [
                os.path.join(p, "roascan-native", "build", "Release"),
                os.path.join(p, "build", "Release"),
                os.path.join(p, "roascan-native", "build"),
                p,
            ]:
                if os.path.isdir(cand) and cand not in search_dirs:
                    search_dirs.append(cand)
            parent = os.path.dirname(p)
            if parent == p:
                break
            p = parent

        for name in candidates:
            for s_dir in search_dirs:
                path = os.path.join(s_dir, name)
                if os.path.exists(path):
                    try:
                        return ctypes.CDLL(path)
                    except Exception:
                        continue
        return None

    def _bind_core(self):
        if not self.core:
            return

        # Version
        if hasattr(self.core, "roascan_native_version"):
            self.core.roascan_native_version.restype = c_char_p

        # Image lifecycle
        if hasattr(self.core, "roascan_native_image_create"):
            self.core.roascan_native_image_create.argtypes = [c_int32, c_int32, c_char_p]
            self.core.roascan_native_image_create.restype = c_void_p
            self.core.roascan_native_image_destroy.argtypes = [c_void_p]
            self.core.roascan_native_image_width.argtypes = [c_void_p]
            self.core.roascan_native_image_width.restype = c_int32
            self.core.roascan_native_image_height.argtypes = [c_void_p]
            self.core.roascan_native_image_height.restype = c_int32
            self.core.roascan_native_image_data.argtypes = [c_void_p]
            self.core.roascan_native_image_data.restype = POINTER(c_uint8)

        # Preprocessing
        if hasattr(self.core, "roascan_native_adjust_brightness_contrast"):
            self.core.roascan_native_adjust_brightness_contrast.argtypes = [c_void_p, c_int32, c_int32]
            self.core.roascan_native_adjust_brightness_contrast.restype = c_void_p

        if hasattr(self.core, "roascan_native_binarize_sauvola"):
            self.core.roascan_native_binarize_sauvola.argtypes = [c_void_p, c_int32, c_double]
            self.core.roascan_native_binarize_sauvola.restype = c_void_p
            self.core.roascan_native_binarize_otsu.argtypes = [c_void_p]
            self.core.roascan_native_binarize_otsu.restype = c_void_p
            self.core.roascan_native_detect_skew.argtypes = [c_void_p]
            self.core.roascan_native_detect_skew.restype = c_double
            self.core.roascan_native_despeckle.argtypes = [c_void_p, c_int32]
            self.core.roascan_native_despeckle.restype = c_void_p
            self.core.roascan_native_rotate.argtypes = [c_void_p, c_double]
            self.core.roascan_native_rotate.restype = c_void_p

        if hasattr(self.core, "roascan_native_binarize_threshold"):
            self.core.roascan_native_binarize_threshold.argtypes = [c_void_p, c_int32]
            self.core.roascan_native_binarize_threshold.restype = c_void_p

        if hasattr(self.core, "roascan_native_rotate_ex"):
            self.core.roascan_native_rotate_ex.argtypes = [c_void_p, c_double, c_uint8, c_int32]
            self.core.roascan_native_rotate_ex.restype = c_void_p

        if hasattr(self.core, "roascan_native_enhance_document"):
            self.core.roascan_native_enhance_document.argtypes = [c_void_p, c_void_p]
            self.core.roascan_native_enhance_document.restype = c_void_p

        if hasattr(self.core, "roascan_native_remove_grid_lines"):
            self.core.roascan_native_remove_grid_lines.argtypes = [c_void_p, c_int32, c_int32]
            self.core.roascan_native_remove_grid_lines.restype = c_void_p

        if hasattr(self.core, "roascan_native_rotate_orthogonal"):
            self.core.roascan_native_rotate_orthogonal.argtypes = [c_void_p, c_int32]
            self.core.roascan_native_rotate_orthogonal.restype = c_void_p

        if hasattr(self.core, "roascan_native_detect_sideways"):
            self.core.roascan_native_detect_sideways.argtypes = [c_void_p]
            self.core.roascan_native_detect_sideways.restype = c_int32

        # Segmentation
        if hasattr(self.core, "roascan_native_segment_lines"):
            self.core.roascan_native_segment_lines.argtypes = [c_void_p, POINTER(RoaScanRect), c_int32]
            self.core.roascan_native_segment_lines.restype = c_int32

        if hasattr(self.core, "roascan_native_segment_words"):
            self.core.roascan_native_segment_words.argtypes = [c_void_p, POINTER(RoaScanRect), c_int32]
            self.core.roascan_native_segment_words.restype = c_int32

        # Lexicon
        if hasattr(self.core, "roascan_native_lexicon_create"):
            self.core.roascan_native_lexicon_create.restype = c_void_p
            self.core.roascan_native_lexicon_destroy.argtypes = [c_void_p]
            self.core.roascan_native_lexicon_insert.argtypes = [c_void_p, c_char_p]
            self.core.roascan_native_lexicon_contains.argtypes = [c_void_p, c_char_p]
            self.core.roascan_native_lexicon_contains.restype = c_int32
            self.core.roascan_native_lexicon_load_file.argtypes = [c_void_p, c_char_p]
            self.core.roascan_native_lexicon_load_file.restype = c_int32

        if hasattr(self.core, "roascan_native_lexicon_suggest_best"):
            self.core.roascan_native_lexicon_suggest_best.argtypes = [c_void_p, c_char_p, c_int32]
            self.core.roascan_native_lexicon_suggest_best.restype = c_char_p

        # Language catalog
        if hasattr(self.core, "roascan_get_language_name"):
            self.core.roascan_get_language_name.argtypes = [c_int32]
            self.core.roascan_get_language_name.restype = c_char_p


def get_native_driver(dll_dir=None) -> RoaScanNativeDriver:
    """Get singleton native driver instance."""
    if RoaScanNativeDriver._instance is None:
        RoaScanNativeDriver._instance = RoaScanNativeDriver(dll_dir)
    return RoaScanNativeDriver._instance
