"""
roascan.engine: Core Multi-Page OCR & Document Enhancement Engine for RoaScan (clean-room).

Pipeline:
  1. Multi-page ingestion: Scanned multi-page PDFs (lazy per-page streaming via PyMuPDF),
     multi-frame TIFFs, standard images (PNG/JPEG/BMP), or raw in-memory pixel buffers.
  2. C++ native core (roascan_core.dll): Brightness/contrast adjustment, Sauvola adaptive
     binarization (or explicit threshold), coarse-to-fine skew detection, orthogonal
     90/180/270 orientation recovery, bilinear deskew rotation, CCL despeckle,
     background-whitening document enhancement (roascan_native_enhance_document),
     table grid-line removal, and XY-Cut multi-column line & word segmentation.
  3. Neural Recognizer (roascan.recognizer): SVTR/CRNN ONNX Runtime inference with
     line-level CTC timestep-to-word-box spatial alignment and Hunspell accent restoration.
  4. Output exporters (roascan.docout): Enhanced Multi-Page Searchable PDF (.pdf)
     preserving physical page dimensions in PDF points, and Structured Semantic
     Markdown (.md) / JSON (.json) / Text (.txt).
"""

import ctypes
import hashlib
import os
import re
import shutil
import statistics
import tempfile
import weakref
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PIL import Image
from .native import get_native_driver, RoaScanRect
from .prepro import RoaScanPreprocessor
from .recognizer import RoaScanTextRecognizer


class RoaScanEngine:
    """High-level multi-page OCR and document enhancement engine."""

    def __init__(
        self,
        dll_dir: Optional[str] = None,
        resources_dir: Optional[str] = None,
        language: str = "en",
    ):
        self.driver = get_native_driver(dll_dir)
        if not self.driver.core:
            raise RuntimeError(
                "RoaScan native core (roascan_core.dll) could not be loaded. "
                "Build it first (see roascan-native/) or set ROASCAN_NATIVE_DIR."
            )

        self.language = language
        self.recognizer = RoaScanTextRecognizer(language=language)
        self._dpi_x: int = 300
        self._dpi_y: int = 300
        self._alphabet_id: int = 0
        self._auto_alphabet: bool = True
        self._auto_orientation: bool = True
        self._enhance_document: bool = True
        self._retain_images: bool = True
        self._num_threads: int = RoaScanPreprocessor._active_threads
        self._brightness: int = RoaScanPreprocessor._active_brightness
        self._contrast: int = RoaScanPreprocessor._active_contrast
        self._threshold: int = RoaScanPreprocessor._active_threshold
        self.last_error: Optional[str] = None

        # Single-page & backward-compatibility attributes
        self._gray: Optional[bytes] = None
        self._width: int = 0
        self._height: int = 0
        self._processed_gray: Optional[bytes] = None
        self._enhanced_gray: Optional[bytes] = None
        self._processed_width: int = 0
        self._processed_height: int = 0
        self._skew_angle: float = 0.0
        self._current_image_file: Optional[str] = None
        self._words: List[Dict[str, object]] = []

        # Multi-page storage: list of dicts or tuples (gray_bytes, width, height, [width_pt, height_pt, dpi_x, dpi_y])
        self._input_pages: List[Tuple] = []
        # Lazy PDF streaming descriptor: (pdf_path, render_dpi, total_pages)
        self._pdf_source: Optional[Tuple[str, Optional[int], int]] = None
        self._pdf_metadata: Dict[str, str] = {}
        # Processed multi-page results
        self._pages: List[Dict[str, object]] = []
        # Disk-backed spool directory for page bitmaps so multi-page PDF export does not accumulate RAM
        self._spool_dir: Optional[str] = None
        self._spool_finalizer = None

    def _ensure_spool_dir(self) -> str:
        if self._spool_dir is None or not os.path.isdir(self._spool_dir):
            self._spool_dir = tempfile.mkdtemp(prefix="roascan_spool_")
            self._spool_finalizer = weakref.finalize(
                self, shutil.rmtree, self._spool_dir, True
            )
        return self._spool_dir

    def _cleanup_spool(self):
        if self._spool_dir and os.path.isdir(self._spool_dir):
            shutil.rmtree(self._spool_dir, ignore_errors=True)
        self._spool_dir = None

    # --- context manager ---------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Release all in-memory page buffers, recognition results, crop caches, and temporary spool files."""
        self._gray = None
        self._processed_gray = None
        self._enhanced_gray = None
        self._input_pages.clear()
        self._pages.clear()
        self._words.clear()
        self._pdf_source = None
        self._pdf_metadata.clear()
        self._cleanup_spool()
        if hasattr(self, "recognizer") and hasattr(self.recognizer, "_crop_cache"):
            self.recognizer._crop_cache.clear()

    # --- settings ----------------------------------------------------------
    def set_resolution(self, dpi_x: int = 300, dpi_y: int = 300):
        dpi_x_val = int(dpi_x)
        dpi_y_val = int(dpi_y)
        if dpi_x_val < 36 or dpi_x_val > 1200 or dpi_y_val < 36 or dpi_y_val > 1200:
            raise ValueError(f"DPI out of supported range [36..1200]: ({dpi_x_val}, {dpi_y_val})")
        self._dpi_x = dpi_x_val
        self._dpi_y = dpi_y_val

    def set_alphabet(self, alphabet_id: int = 0):
        self._alphabet_id = int(alphabet_id)

    def set_auto_alphabet(self, enabled: bool = True):
        self._auto_alphabet = bool(enabled)

    def set_auto_orientation(self, enabled: bool = True):
        self._auto_orientation = bool(enabled)

    def set_document_enhancement(self, enabled: bool = True):
        """Enable or disable C++ background whitening and ink contrast enhancement."""
        self._enhance_document = bool(enabled)

    def set_retain_images(self, enabled: bool = True):
        """Control whether processed grayscale buffers are retained in memory after OCR."""
        self._retain_images = bool(enabled)

    def set_thread_count(self, num_threads: int = 4):
        self._num_threads = max(1, int(num_threads))
        self.recognizer.set_threads(self._num_threads)

    def set_threads(self, ocr_threads: int = 4, binarization_threads: int = 4):
        self.set_thread_count(ocr_threads)

    def set_brightness(self, value: int):
        self._brightness = max(0, min(255, int(value)))

    def set_contrast(self, value: int):
        self._contrast = max(0, min(255, int(value)))

    def set_threshold(self, threshold: int):
        val = int(threshold)
        self._threshold = -1 if val < 0 else max(0, min(255, val))

    # --- single & multi-page ingestion -------------------------------------
    def set_raw_image(self, image_data, width: int, height: int, bpp: int = 8, stride=None):
        """Feed an in-memory raw image buffer (converted to 8-bit grayscale)."""
        width = int(width)
        height = int(height)
        bpp = int(bpp)
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid image dimensions: {width}x{height}")
        if bpp not in (8, 24, 32):
            raise ValueError(f"Unsupported bpp: {bpp}. Expected 8, 24, or 32.")

        bytes_per_px = bpp // 8
        min_stride = width * bytes_per_px
        actual_stride = int(stride) if stride is not None else min_stride
        if actual_stride < min_stride:
            raise ValueError(f"Invalid stride {actual_stride}: must be >= {min_stride}")

        raw_bytes = bytes(image_data)
        required_bytes = (height - 1) * actual_stride + min_stride
        if len(raw_bytes) < required_bytes:
            raise ValueError(
                f"Raw image buffer too small: got {len(raw_bytes)} bytes, "
                f"expected at least {required_bytes} bytes for {width}x{height}@{bpp}bpp (stride={actual_stride})."
            )

        if bpp == 8:
            if actual_stride > width:
                rows = [raw_bytes[y * actual_stride : y * actual_stride + width] for y in range(height)]
                gray = b"".join(rows)
            else:
                gray = raw_bytes[: width * height]
        else:
            mode = "RGBA" if bpp == 32 else "RGB"
            im = Image.frombuffer(mode, (width, height), raw_bytes, "raw", mode, actual_stride, 1)
            gray = im.convert("L").tobytes()

        self._gray = gray
        self._width = width
        self._height = height
        self._processed_gray = gray
        self._enhanced_gray = gray
        self._processed_width = width
        self._processed_height = height
        self._skew_angle = 0.0
        self._current_image_file = None
        self._words = []
        self._pdf_source = None
        self._pdf_metadata = {}
        w_pt = width * 72.0 / self._dpi_x
        h_pt = height * 72.0 / self._dpi_y
        self._input_pages = [(gray, width, height, w_pt, h_pt, float(self._dpi_x), float(self._dpi_y))]
        self._pages = []

    @staticmethod
    def _rasterize_pdf_page(page, render_dpi: int, explicit_dpi: bool) -> Tuple[bytes, int, int, float, float, float, float]:
        pw_pt = float(page.rect.width)
        ph_pt = float(page.rect.height)
        max_dim_pt = max(pw_pt, ph_pt)
        base_zoom = render_dpi / 72.0
        if not explicit_dpi and max_dim_pt > 1000:
            zoom = 1.0
        else:
            zoom = base_zoom
            if max_dim_pt * zoom > 3600:
                zoom = 3600.0 / max_dim_pt
        mat = page._fitz_matrix(zoom) if hasattr(page, "_fitz_matrix") else None
        import fitz
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
        eff_dpi_x = (pix.width * 72.0 / pw_pt) if pw_pt > 0 else float(render_dpi)
        eff_dpi_y = (pix.height * 72.0 / ph_pt) if ph_pt > 0 else float(render_dpi)
        return (bytes(pix.samples), pix.width, pix.height, pw_pt, ph_pt, eff_dpi_x, eff_dpi_y)

    def set_pdf_file(self, pdf_path: str, dpi: Optional[int] = None):
        """Register a scanned PDF file for lazy page-by-page streaming rasterization."""
        try:
            import fitz
        except ImportError:
            raise ImportError("PyMuPDF (fitz) is required for PDF input: pip install pymupdf")

        abs_path = os.path.abspath(pdf_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"PDF file not found: {abs_path}")

        render_dpi = int(dpi) if dpi is not None else self._dpi_x
        with fitz.open(abs_path) as doc:
            total_pages = len(doc)
            if total_pages == 0:
                raise ValueError(f"PDF contains 0 pages: {abs_path}")
            self._pdf_metadata = dict(doc.metadata or {})
            first_tuple = self._rasterize_pdf_page(doc[0], render_dpi, dpi is not None)

        # Store lazy PDF source descriptor instead of rasterizing all pages into RAM upfront
        self._pdf_source = (abs_path, dpi, total_pages)
        self._input_pages = []
        self._gray, self._width, self._height = first_tuple[0], first_tuple[1], first_tuple[2]
        self._processed_gray = self._gray
        self._enhanced_gray = self._gray
        self._processed_width = self._width
        self._processed_height = self._height
        self._skew_angle = 0.0
        self._current_image_file = abs_path
        self._words = []
        self._pages = []

    def set_image_file(self, file_path: str):
        """Load an image or multi-page document file (PDF/TIFF/PNG/BMP/JPEG)."""
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Input file not found: {abs_path}")
        if abs_path.lower().endswith(".pdf"):
            self.set_pdf_file(abs_path)
            return

        pages: List[Tuple] = []
        with Image.open(abs_path) as im:
            info_dpi = im.info.get("dpi")
            img_dpi_x = float(info_dpi[0]) if (info_dpi and len(info_dpi) >= 2 and info_dpi[0] >= 36) else float(self._dpi_x)
            img_dpi_y = float(info_dpi[1]) if (info_dpi and len(info_dpi) >= 2 and info_dpi[1] >= 36) else float(self._dpi_y)
            n_frames = getattr(im, "n_frames", 1)
            for frame_idx in range(n_frames):
                if n_frames > 1:
                    im.seek(frame_idx)
                gray = im.convert("L")
                w, h = gray.size
                w_pt = w * 72.0 / img_dpi_x
                h_pt = h * 72.0 / img_dpi_y
                pages.append((gray.tobytes(), w, h, w_pt, h_pt, img_dpi_x, img_dpi_y))

        self._pdf_source = None
        self._pdf_metadata = {}
        self._input_pages = pages
        self._gray, self._width, self._height = pages[0][0], pages[0][1], pages[0][2]
        self._processed_gray = self._gray
        self._enhanced_gray = self._gray
        self._processed_width = self._width
        self._processed_height = self._height
        self._skew_angle = 0.0
        self._current_image_file = abs_path
        self._words = []
        self._pages = []

    # --- helper: probe ONNX confidence on top lines of an image ------------
    def _probe_orientation_score(self, img_handle, bin_handle) -> float:
        core = self.driver.core
        w = core.roascan_native_image_width(img_handle)
        h = core.roascan_native_image_height(img_handle)
        ptr = core.roascan_native_image_data(img_handle)
        if not ptr or w <= 0 or h <= 0:
            return 0.0
        g_bytes = ctypes.string_at(ptr, w * h)
        pil_im = Image.frombytes("L", (w, h), g_bytes)

        max_boxes = 128
        boxes = (RoaScanRect * max_boxes)()
        n = min(max_boxes, core.roascan_native_segment_lines(bin_handle, boxes, max_boxes))
        if n == 0:
            return 0.0

        scores = []
        for i in range(min(n, 2)):
            b = boxes[i]
            if (b.bottom - b.top) < 8 or (b.right - b.left) < 12:
                continue
            crop = pil_im.crop((b.left, b.top, b.right, b.bottom))
            txt, conf = self.recognizer.recognize_crop(crop)
            if txt and any(ch.isalnum() for ch in txt):
                scores.append(conf)
        return float(sum(scores) / len(scores)) if scores else 0.0

    # --- internal single-page pipeline -------------------------------------
    def _recognize_single_page(
        self,
        gray_bytes: bytes,
        width: int,
        height: int,
        page_number: int = 1,
        width_pt: Optional[float] = None,
        height_pt: Optional[float] = None,
        dpi_x: Optional[float] = None,
        dpi_y: Optional[float] = None,
    ) -> Dict[str, object]:
        core = self.driver.core
        img = core.roascan_native_image_create(width, height, gray_bytes)
        if not img:
            raise RuntimeError("Failed to allocate native image buffer.")

        eff_dpi_x = float(dpi_x) if dpi_x else float(self._dpi_x)
        eff_dpi_y = float(dpi_y) if dpi_y else float(self._dpi_y)
        orig_w_pt = float(width_pt) if width_pt else (width * 72.0 / eff_dpi_x)
        orig_h_pt = float(height_pt) if height_pt else (height * 72.0 / eff_dpi_y)

        page_words: List[Dict[str, object]] = []
        page_lines_data: List[Dict[str, object]] = []
        binary = None
        seg_binary = None
        enhanced_handle = None
        skew_angle = 0.0
        proc_gray = gray_bytes
        enh_gray = gray_bytes
        proc_w, proc_h = width, height

        try:
            # 0. Apply brightness/contrast adjustment if non-neutral (128 is neutral)
            if (self._brightness != 128 or self._contrast != 128) and hasattr(
                core, "roascan_native_adjust_brightness_contrast"
            ):
                adj = core.roascan_native_adjust_brightness_contrast(img, self._brightness, self._contrast)
                if adj:
                    core.roascan_native_image_destroy(img)
                    img = adj

            # 1. Binarize using explicit threshold (if > 0) or adaptive Sauvola (0 = auto)
            if self._threshold > 0 and hasattr(core, "roascan_native_binarize_threshold"):
                binary = core.roascan_native_binarize_threshold(img, self._threshold)
            else:
                window = max(11, ((int(eff_dpi_x) * 15) // 300) | 1)
                binary = core.roascan_native_binarize_sauvola(img, window, 0.34)
            if not binary:
                raise RuntimeError("Native binarization failed.")

            # 2. Orthogonal Orientation Recovery (90 / 270 sideways detection) & Fine Deskew
            if self._auto_orientation:
                if hasattr(core, "roascan_native_detect_sideways") and hasattr(core, "roascan_native_rotate_orthogonal"):
                    if core.roascan_native_detect_sideways(binary) == 90:
                        img_90 = core.roascan_native_rotate_orthogonal(img, 90)
                        bin_90 = core.roascan_native_rotate_orthogonal(binary, 90)
                        img_270 = core.roascan_native_rotate_orthogonal(img, 270)
                        bin_270 = core.roascan_native_rotate_orthogonal(binary, 270)
                        s90 = self._probe_orientation_score(img_90, bin_90)
                        s270 = self._probe_orientation_score(img_270, bin_270)
                        core.roascan_native_image_destroy(img)
                        core.roascan_native_image_destroy(binary)
                        if s90 >= s270:
                            img, binary = img_90, bin_90
                            core.roascan_native_image_destroy(img_270)
                            core.roascan_native_image_destroy(bin_270)
                        else:
                            img, binary = img_270, bin_270
                            core.roascan_native_image_destroy(img_90)
                            core.roascan_native_image_destroy(bin_90)
                        # Swap physical page dimensions when rotated 90/270 degrees
                        orig_w_pt, orig_h_pt = orig_h_pt, orig_w_pt
                        eff_dpi_x, eff_dpi_y = eff_dpi_y, eff_dpi_x

                angle = core.roascan_native_detect_skew(binary)
                skew_angle = float(angle)
                if abs(angle) > 0.15:
                    if hasattr(core, "roascan_native_rotate_ex"):
                        rot_bin = core.roascan_native_rotate_ex(binary, -angle, 0, 0)
                        rot_gray = core.roascan_native_rotate_ex(img, -angle, 255, 1)
                    else:
                        rot_bin = core.roascan_native_rotate(binary, -angle)
                        rot_gray = core.roascan_native_rotate(img, -angle)
                    core.roascan_native_image_destroy(binary)
                    core.roascan_native_image_destroy(img)
                    binary = rot_bin
                    img = rot_gray

                # Check for upside-down (180 deg) scan if initial probe confidence is low
                if hasattr(core, "roascan_native_rotate_orthogonal"):
                    s0 = self._probe_orientation_score(img, binary)
                    if 0.0 < s0 < 0.72:
                        img_180 = core.roascan_native_rotate_orthogonal(img, 180)
                        bin_180 = core.roascan_native_rotate_orthogonal(binary, 180)
                        s180 = self._probe_orientation_score(img_180, bin_180)
                        if s180 > s0 + 0.08:
                            core.roascan_native_image_destroy(img)
                            core.roascan_native_image_destroy(binary)
                            img, binary = img_180, bin_180
                        else:
                            core.roascan_native_image_destroy(img_180)
                            core.roascan_native_image_destroy(bin_180)

            # 3. Connected-component despeckle
            cleaned = core.roascan_native_despeckle(binary, 6)
            core.roascan_native_image_destroy(binary)
            binary = cleaned

            # 4. Extract deskewed grayscale buffer & C++ Enhanced Document buffer
            proc_w = core.roascan_native_image_width(img)
            proc_h = core.roascan_native_image_height(img)
            data_ptr = core.roascan_native_image_data(img)
            if data_ptr and proc_w > 0 and proc_h > 0:
                proc_gray = ctypes.string_at(data_ptr, proc_w * proc_h)

            if self._enhance_document and hasattr(core, "roascan_native_enhance_document"):
                enhanced_handle = core.roascan_native_enhance_document(img, binary)
                if enhanced_handle:
                    enh_ptr = core.roascan_native_image_data(enhanced_handle)
                    if enh_ptr:
                        enh_gray = ctypes.string_at(enh_ptr, proc_w * proc_h)
                    else:
                        enh_gray = proc_gray
                else:
                    enh_gray = proc_gray
            else:
                enh_gray = proc_gray

            # 5. Table Grid-Line Removal & Layout-aware XY-Cut word segmentation
            if hasattr(core, "roascan_native_remove_grid_lines"):
                seg_binary = core.roascan_native_remove_grid_lines(binary, 0, 0)
            else:
                seg_binary = binary

            max_boxes = 8192
            boxes = (RoaScanRect * max_boxes)()
            n = min(max_boxes, core.roascan_native_segment_words(seg_binary, boxes, max_boxes))

            # Build OCR grayscale image with table grid lines whitened so vertical
            # cell borders are never misread as 'I', 'l', or '1' by ONNX CTC
            ocr_gray = proc_gray
            if seg_binary is not binary and proc_gray:
                b_ptr = core.roascan_native_image_data(binary)
                sb_ptr = core.roascan_native_image_data(seg_binary)
                if b_ptr and sb_ptr:
                    b_arr = np.frombuffer(ctypes.string_at(b_ptr, proc_w * proc_h), dtype=np.uint8)
                    sb_arr = np.frombuffer(ctypes.string_at(sb_ptr, proc_w * proc_h), dtype=np.uint8)
                    grid_removed = (b_arr != 0) & (sb_arr == 0)
                    if np.any(grid_removed):
                        g_arr = np.frombuffer(proc_gray, dtype=np.uint8).copy()
                        g_arr[grid_removed] = 255
                        ocr_gray = g_arr.tobytes()

            pil_img = Image.frombytes("L", (proc_w, proc_h), ocr_gray) if ocr_gray else None

            valid_boxes: List[Tuple[int, int, int, int]] = []
            for i in range(n):
                b = boxes[i]
                bw = b.right - b.left
                bh = b.bottom - b.top
                if bh < 8 or bw < 2:
                    continue
                valid_boxes.append((b.left, b.top, b.right, b.bottom))

            lines: List[List[Tuple[int, int, int, int]]] = []
            for bbox in valid_boxes:
                if not lines:
                    lines.append([bbox])
                    continue
                prev = lines[-1][-1]
                overlap_y = min(prev[3], bbox[3]) - max(prev[1], bbox[1])
                min_h = min(prev[3] - prev[1], bbox[3] - bbox[1])
                if bbox[0] >= prev[2] - 6 and overlap_y >= min_h * 0.4:
                    lines[-1].append(bbox)
                else:
                    lines.append([bbox])

            # 6. Line-level ONNX recognition with CTC spatial alignment
            for line_boxes in lines:
                line_results = self.recognizer.recognize_line_words(pil_img, line_boxes)
                active_line_words = []
                for item in line_results:
                    if item.get("text"):
                        item["page"] = page_number
                        page_words.append(item)
                        active_line_words.append(item)
                if active_line_words:
                    lx0 = min(w["bbox"][0] for w in active_line_words)
                    ly0 = min(w["bbox"][1] for w in active_line_words)
                    lx1 = max(w["bbox"][2] for w in active_line_words)
                    ly1 = max(w["bbox"][3] for w in active_line_words)
                    line_text = " ".join(w["text"] for w in active_line_words)
                    page_lines_data.append({
                        "text": line_text,
                        "bbox": (lx0, ly0, lx1, ly1),
                        "height": ly1 - ly0,
                        "words": active_line_words,
                    })
        finally:
            if enhanced_handle:
                core.roascan_native_image_destroy(enhanced_handle)
            if seg_binary and seg_binary is not binary:
                core.roascan_native_image_destroy(seg_binary)
            if binary:
                core.roascan_native_image_destroy(binary)
            if img:
                core.roascan_native_image_destroy(img)

        gray_spool_path: Optional[str] = None
        enh_spool_path: Optional[str] = None
        if self._retain_images and proc_w > 0 and proc_h > 0:
            spool_dir = self._ensure_spool_dir()
            if proc_gray:
                gray_spool_path = os.path.join(spool_dir, f"page_{page_number:04d}_gray.png")
                Image.frombytes("L", (proc_w, proc_h), proc_gray).save(
                    gray_spool_path, format="PNG", compress_level=1
                )
            if enh_gray:
                if enh_gray == proc_gray and gray_spool_path:
                    enh_spool_path = gray_spool_path
                else:
                    enh_spool_path = os.path.join(spool_dir, f"page_{page_number:04d}_enh.png")
                    Image.frombytes("L", (proc_w, proc_h), enh_gray).save(
                        enh_spool_path, format="PNG", compress_level=1
                    )

        return {
            "page_number": page_number,
            "width": proc_w,
            "height": proc_h,
            "width_pt": round(orig_w_pt, 2),
            "height_pt": round(orig_h_pt, 2),
            "dpi_x": round(eff_dpi_x, 2),
            "dpi_y": round(eff_dpi_y, 2),
            "gray": None,
            "enhanced_gray": None,
            "gray_spool_path": gray_spool_path,
            "enhanced_spool_path": enh_spool_path,
            "skew_angle": skew_angle,
            "words": page_words,
            "lines": page_lines_data,
        }

    def _unpack_input_page(self, item: Tuple) -> Tuple[bytes, int, int, Optional[float], Optional[float], Optional[float], Optional[float]]:
        if len(item) >= 7:
            return item[0], item[1], item[2], item[3], item[4], item[5], item[6]
        return item[0], item[1], item[2], None, None, None, None

    # --- recognition execution (single or multi-page) ----------------------
    def recognize(self) -> int:
        """Run the full preprocessing, enhancement, segmentation, and OCR pipeline
        across all loaded pages. Returns 0 on success, < 0 on failure.
        """
        self.last_error = None
        if not self.driver.is_available:
            self.last_error = "Native C++ core library (roascan_core) is not available."
            return -4

        if not self.recognizer.is_available:
            self.last_error = (
                f"ONNX recognition model or session is not available "
                f"(model={self.recognizer.model_path}, dict={self.recognizer.dict_path})."
            )
            return -3

        all_words: List[Dict[str, object]] = []
        pages_out: List[Dict[str, object]] = []

        try:
            # Case A: Lazy PDF page streaming (avoids pre-loading all pages in RAM)
            if self._pdf_source is not None:
                import fitz
                pdf_path, explicit_dpi, total_pages = self._pdf_source
                render_dpi = int(explicit_dpi) if explicit_dpi is not None else self._dpi_x
                with fitz.open(pdf_path) as doc:
                    for idx in range(total_pages):
                        p_tuple = self._rasterize_pdf_page(doc[idx], render_dpi, explicit_dpi is not None)
                        g_bytes, w, h, w_pt, h_pt, dx, dy = p_tuple
                        page_res = self._recognize_single_page(
                            g_bytes, w, h, page_number=idx + 1,
                            width_pt=w_pt, height_pt=h_pt, dpi_x=dx, dpi_y=dy,
                        )
                        pages_out.append(page_res)
                        all_words.extend(page_res["words"])
            else:
                # Case B: In-memory or image/TIFF pages
                if not self._input_pages:
                    if self._gray is not None and self._width > 0 and self._height > 0:
                        self._input_pages = [(self._gray, self._width, self._height)]
                    else:
                        self.last_error = "No input image or document loaded."
                        return -1

                n_pages = len(self._input_pages)
                max_workers = min(n_pages, max(1, min(4, self._num_threads)))
                if n_pages == 1 or max_workers == 1:
                    for idx, item in enumerate(self._input_pages):
                        g_bytes, w, h, w_pt, h_pt, dx, dy = self._unpack_input_page(item)
                        page_res = self._recognize_single_page(
                            g_bytes, w, h, page_number=idx + 1,
                            width_pt=w_pt, height_pt=h_pt, dpi_x=dx, dpi_y=dy,
                        )
                        pages_out.append(page_res)
                        all_words.extend(page_res["words"])
                else:
                    with ThreadPoolExecutor(max_workers=max_workers) as pool:
                        futures = []
                        for idx, item in enumerate(self._input_pages):
                            g_bytes, w, h, w_pt, h_pt, dx, dy = self._unpack_input_page(item)
                            futures.append(
                                pool.submit(
                                    self._recognize_single_page,
                                    g_bytes, w, h, idx + 1, w_pt, h_pt, dx, dy,
                                )
                            )
                        for fut in futures:
                            page_res = fut.result()
                            pages_out.append(page_res)
                            all_words.extend(page_res["words"])
        except Exception as exc:
            self.last_error = str(exc)
            return -2

        self._pages = pages_out
        self._words = all_words
        if pages_out:
            first = pages_out[0]
            self._processed_width = first["width"]
            self._processed_height = first["height"]
            self._skew_angle = first["skew_angle"]
            if len(pages_out) == 1 and self._retain_images:
                g_sp = first.get("gray_spool_path")
                e_sp = first.get("enhanced_spool_path")
                if g_sp and os.path.exists(g_sp):
                    with Image.open(g_sp) as im_g:
                        self._processed_gray = im_g.tobytes()
                if e_sp and os.path.exists(e_sp):
                    with Image.open(e_sp) as im_e:
                        self._enhanced_gray = im_e.tobytes()
            else:
                self._gray = None
                self._processed_gray = None
                self._enhanced_gray = None

        return 0

    # --- result accessors & structured Markdown / JSON generators ----------
    @property
    def page_count(self) -> int:
        if self._pages:
            return len(self._pages)
        if self._pdf_source is not None:
            return self._pdf_source[2]
        return len(self._input_pages)

    def extract_pages(self) -> List[Dict[str, object]]:
        """Return list of per-page recognition and enhancement results."""
        return list(self._pages)

    def extract_words(self) -> List[Dict[str, object]]:
        """Detected word bounding boxes with recognized text and confidence."""
        return list(self._words)

    def get_text(self) -> str:
        """Reconstructed plain text from all detected words across all pages."""
        if len(self._pages) > 1:
            page_texts = [
                " ".join(w["text"] for w in p["words"] if w.get("text"))
                for p in self._pages
            ]
            return "\n\n".join(t for t in page_texts if t)
        return " ".join(w["text"] for w in self._words if w.get("text"))

    def to_dict(self) -> Dict[str, Any]:
        """Return unified, versioned JSON-serializable dictionary of the OCR result."""
        pages_summary = []
        for p in self._pages:
            pages_summary.append({
                "page_number": p["page_number"],
                "width_px": p["width"],
                "height_px": p["height"],
                "width_pt": p.get("width_pt"),
                "height_pt": p.get("height_pt"),
                "dpi_x": p.get("dpi_x", self._dpi_x),
                "dpi_y": p.get("dpi_y", self._dpi_y),
                "skew_angle": round(float(p.get("skew_angle", 0.0)), 2),
                "words": p.get("words", []),
            })
        return {
            "schema_version": "2.0",
            "engine": "RoaScan v2.0.1",
            "language": self.language,
            "page_count": len(self._pages),
            "word_count": len(self._words),
            "text": self.get_text(),
            "markdown": self.to_markdown(),
            "pages": pages_summary,
        }

    @classmethod
    def diagnose(cls, language: str = "es") -> Dict[str, Any]:
        """Return diagnostic health check of native C++ core, ONNX Runtime, and models."""
        drv = get_native_driver()
        rec = RoaScanTextRecognizer(language=language)
        try:
            import onnxruntime as ort
            ort_ver = ort.__version__
            providers = ort.get_available_providers()
        except Exception:
            ort_ver = None
            providers = []

        def _sha256_prefix(p: str) -> Optional[str]:
            if not p or not os.path.exists(p):
                return None
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()[:16]

        return {
            "status": "ok" if (drv.is_available and rec.is_available) else "error",
            "engine_version": "2.0.1",
            "native_core": {
                "available": drv.is_available,
                "version": drv.version(),
                "dll_dir": drv.dll_dir,
            },
            "onnx_runtime": {
                "installed": ort_ver is not None,
                "version": ort_ver,
                "available_providers": providers,
            },
            "recognizer": {
                "available": rec.is_available,
                "language": language,
                "model_path": rec.model_path,
                "model_exists": os.path.exists(rec.model_path),
                "model_sha256_16": _sha256_prefix(rec.model_path),
                "dict_path": rec.dict_path,
                "dict_exists": os.path.exists(rec.dict_path),
                "vocab_size": len(rec.char_list),
                "accent_restorer_loaded": bool(rec.accent_restorer and rec.accent_restorer.valid_words),
            },
        }

    @staticmethod
    def _build_page_markdown(p: Dict[str, object], p_num: int, total_pages: int, include_page_markers: bool) -> str:
        words = p.get("words", [])
        lines = p.get("lines", [])
        if not words:
            return ""

        if not lines:
            return " ".join(w["text"] for w in words if w.get("text"))

        heights = [ln["height"] for ln in lines if ln["height"] > 0]
        median_h = statistics.median(heights) if heights else 20.0

        sorted_words = sorted(words, key=lambda w: (w["bbox"][1], w["bbox"][0]))
        visual_rows: List[List[Dict[str, object]]] = []
        for w in sorted_words:
            if not w.get("text"):
                continue
            wb = w["bbox"]
            if not visual_rows:
                visual_rows.append([w])
                continue
            cur_row = visual_rows[-1]
            row_top = min(rw["bbox"][1] for rw in cur_row)
            row_bot = max(rw["bbox"][3] for rw in cur_row)
            overlap = min(row_bot, wb[3]) - max(row_top, wb[1])
            min_h = min(row_bot - row_top, wb[3] - wb[1])
            if overlap >= max(4, min_h * 0.45):
                visual_rows[-1].append(w)
            else:
                visual_rows.append([w])

        row_cells_list: List[Dict[str, object]] = []
        for r_words in visual_rows:
            r_words.sort(key=lambda w: w["bbox"][0])
            cells: List[Dict[str, object]] = []
            for w in r_words:
                wb = w["bbox"]
                if not cells or (wb[0] - cells[-1]["bbox"][2]) >= 45:
                    cells.append({
                        "text": w["text"],
                        "bbox": wb,
                    })
                else:
                    prev_c = cells[-1]
                    pb = prev_c["bbox"]
                    prev_c["text"] = f"{prev_c['text']} {w['text']}"
                    prev_c["bbox"] = (pb[0], min(pb[1], wb[1]), wb[2], max(pb[3], wb[3]))

            ry0 = min(c["bbox"][1] for c in cells)
            ry1 = max(c["bbox"][3] for c in cells)
            has_numeric_right = len(cells) >= 2 and bool(re.search(r"\d", cells[-1]["text"]))
            row_cells_list.append({
                "y0": ry0,
                "y1": ry1,
                "cells": cells,
                "n_cols": len(cells),
                "is_tabular_candidate": (len(cells) >= 3) or has_numeric_right,
            })

        table_y_ranges: List[Tuple[int, int, List[List[str]]]] = []
        i = 0
        while i < len(row_cells_list):
            if row_cells_list[i]["n_cols"] >= 2:
                j = i
                while j < len(row_cells_list) and row_cells_list[j]["n_cols"] >= 2:
                    j += 1
                band = row_cells_list[i:j]
                num_tabular = sum(1 for r in band if r["is_tabular_candidate"])
                max_cols = max(r["n_cols"] for r in band)
                has_kv_colons = all(":" in c["text"] for r in band for c in r["cells"])
                if len(band) >= 2 and num_tabular >= 1 and not has_kv_colons:
                    t_y0 = band[0]["y0"]
                    t_y1 = band[-1]["y1"]
                    table_rows: List[List[str]] = []
                    for r in band:
                        row_strs = [c["text"].strip() for c in r["cells"]]
                        while len(row_strs) < max_cols:
                            row_strs.append("")
                        table_rows.append(row_strs[:max_cols])
                    table_y_ranges.append((t_y0, t_y1, table_rows))
                i = j
            else:
                i += 1

        def find_table_at_y(y_top: int, y_bot: int) -> Optional[int]:
            for t_idx, (ty0, ty1, _) in enumerate(table_y_ranges):
                if y_bot > ty0 + 2 and y_top < ty1 - 2:
                    return t_idx
            return None

        p_blocks: List[str] = []
        if include_page_markers and total_pages > 1:
            p_blocks.append(f"<!-- Page {p_num} -->")

        emitted_tables = set()
        prev_bbox = None

        for idx_ln, ln in enumerate(lines):
            bbox = ln["bbox"]
            t_idx = find_table_at_y(bbox[1], bbox[3])
            if t_idx is not None:
                if t_idx not in emitted_tables:
                    emitted_tables.add(t_idx)
                    _, _, t_rows = table_y_ranges[t_idx]
                    if p_blocks and p_blocks[-1] != "":
                        p_blocks.append("")
                    header = t_rows[0]
                    p_blocks.append("| " + " | ".join(header) + " |")
                    p_blocks.append("| " + " | ".join(":---" for _ in header) + " |")
                    for r_vals in t_rows[1:]:
                        p_blocks.append("| " + " | ".join(r_vals) + " |")
                    p_blocks.append("")
                continue

            text = ln["text"].strip()
            if not text:
                continue
            h = ln["height"]

            if prev_bbox is not None:
                is_new_column = (bbox[1] < prev_bbox[1] - median_h)
                if is_new_column and p_blocks and p_blocks[-1] != "":
                    p_blocks.append("")

            if h >= median_h * 1.25 and len(lines) > 1 and ":" not in text:
                if idx_ln == 0 or h >= median_h * 1.45:
                    p_blocks.append(f"# {text}")
                else:
                    p_blocks.append(f"## {text}")
                p_blocks.append("")
            elif ":" in text:
                kv_match = re.match(r"^([A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\s\-/]{2,35}:)\s*(.+)$", text)
                if kv_match:
                    key_part, val_part = kv_match.group(1), kv_match.group(2)
                    p_blocks.append(f"- **{key_part}** {val_part}")
                else:
                    p_blocks.append(text)
            else:
                p_blocks.append(text)

            prev_bbox = bbox

        return "\n".join(p_blocks).strip()

    def to_markdown(self, include_page_markers: bool = True) -> str:
        """Convert recognized multi-page document into structured Markdown (.md)."""
        if not self._pages:
            return ""

        md_pages: List[str] = []
        total_pages = len(self._pages)

        for p in self._pages:
            page_md = self._build_page_markdown(p, p["page_number"], total_pages, include_page_markers)
            if page_md:
                md_pages.append(page_md)

        return "\n\n---\n\n".join(md_pages) + "\n"

    def process_document(
        self,
        input_path: str,
        output_path: str,
        dpi: int = 300,
        enhance_quality: bool = True,
        expected_format: str = "auto",
    ) -> int:
        """End-to-end helper: ingest a single/multi-page document (PDF/TIFF/Image)
        and export either an enhanced Searchable PDF (.pdf), Structured Markdown (.md),
        JSON (.json), or plain text (.txt).
        """
        from .docout import RoaScanDocumentWriter, validate_output_paths, validate_output_format

        validate_output_paths(input_path, [output_path], expected_formats=[expected_format])
        resolved_fmt = validate_output_format(output_path, expected_format)

        self.set_resolution(dpi, dpi)
        self.set_document_enhancement(enhance_quality)
        self.set_retain_images(resolved_fmt == "pdf")
        self.set_image_file(input_path)
        status = self.recognize()
        if status != 0:
            return status

        with RoaScanDocumentWriter() as writer:
            if resolved_fmt == "md":
                writer.configure_markdown(output_path)
            elif resolved_fmt == "pdf":
                writer.configure_pdf(
                    output_path,
                    text_over_image=True,
                    enhance_quality=enhance_quality,
                )
            else:
                writer.configure_auto(output_path, enhance_quality=enhance_quality)
            w_rc = writer.write(self)
            if w_rc != 0:
                self.last_error = writer.last_error
            return w_rc

    @property
    def recognition_available(self) -> bool:
        """Whether neural character recognition is active."""
        return self.recognizer.is_available

    # --- language catalog --------------------------------------------------
    @classmethod
    def list_supported_languages(cls, dll_dir: Optional[str] = None) -> Dict[int, str]:
        return {
            0: "English (en)",
            1: "Spanish (es)",
            2: "Latin / Multilingual Western (latin)",
        }

    def get_supported_languages(self) -> Dict[int, str]:
        return self.list_supported_languages()
