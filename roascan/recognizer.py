"""
roascan.recognizer: Neural Text Recognition Backend for RoaScan (Clean-Room).

Uses standard open-source Apache-2.0 CRNN/SVTR ONNX models with CTC decoding,
line-level CTC timestep-to-word-box spatial alignment, session caching, and
multi-threaded execution.
"""

import os
from typing import Dict, List, Optional, Tuple
import numpy as np
from PIL import Image

from .accent import AccentRestorer

try:
    import onnxruntime as ort
except ImportError:
    ort = None

# language -> preferred list of (model filename, dict filename) inside models/
LANGUAGE_MODELS = {
    "en": [
        ("roascan_rec_latin_v5.onnx", "ppocrv5_latin_dict.txt"),
        ("roascan_rec_en.onnx", "en_dict.txt"),
    ],
    "es": [
        ("roascan_rec_latin_v5.onnx", "ppocrv5_latin_dict.txt"),
        ("roascan_rec_en.onnx", "en_dict.txt"),
    ],
    "latin": [
        ("roascan_rec_latin_v5.onnx", "ppocrv5_latin_dict.txt"),
        ("roascan_rec_en.onnx", "en_dict.txt"),
    ],
}


class RoaScanTextRecognizer:
    """High-throughput text recognition engine using ONNX Runtime and CTC alignment."""

    # Process-wide ONNX session cache: (model_path, dict_path, threads) -> (session, input_name, char_list)
    _SESSION_CACHE: Dict[Tuple[str, str, int], Tuple[object, str, List[str]]] = {}

    def __init__(
        self,
        model_path: Optional[str] = None,
        dict_path: Optional[str] = None,
        language: str = "en",
        num_threads: int = 0,
    ):
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(pkg_dir)
        pkg_models_dir = os.path.join(pkg_dir, "models")
        default_models_dir = pkg_models_dir if os.path.isdir(pkg_models_dir) else os.path.join(base_dir, "models")

        if model_path is None or dict_path is None:
            candidates = LANGUAGE_MODELS.get(language.lower(), LANGUAGE_MODELS["en"])
            chosen_model, chosen_dict = candidates[-1]
            for m_file, d_file in candidates:
                m_full = os.path.join(default_models_dir, m_file)
                d_full = os.path.join(default_models_dir, d_file)
                if os.path.exists(m_full) and os.path.exists(d_full):
                    chosen_model, chosen_dict = m_file, d_file
                    break
            if model_path is None:
                model_path = os.path.join(default_models_dir, chosen_model)
            if dict_path is None:
                dict_path = os.path.join(default_models_dir, chosen_dict)

        self.language = language.lower()
        self.model_path = os.path.abspath(model_path)
        self.dict_path = os.path.abspath(dict_path)
        self.num_threads = num_threads if num_threads > 0 else max(2, min(8, os.cpu_count() or 4))
        self.session = None
        self.input_name = None
        self.char_list: List[str] = []
        self.accent_restorer = AccentRestorer() if self.language in ("es", "latin", "spa") else None
        self._crop_cache: Dict[Tuple[int, int, bytes], Tuple[np.ndarray, int]] = {}

        if ort is not None and os.path.exists(self.model_path) and os.path.exists(self.dict_path):
            self._load()

    def _load(self):
        cache_key = (self.model_path, self.dict_path, self.num_threads)
        if cache_key in self._SESSION_CACHE:
            self.session, self.input_name, self.char_list = self._SESSION_CACHE[cache_key]
            return

        with open(self.dict_path, "r", encoding="utf-8") as f:
            chars = [line.strip("\r\n") for line in f if line.strip("\r\n") != ""]
        self.char_list = ["blank"] + chars + [" "]

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = self.num_threads
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        avail = ort.get_available_providers()
        providers = []
        for pref in ("CUDAExecutionProvider", "DmlExecutionProvider", "CPUExecutionProvider"):
            if pref in avail:
                providers.append(pref)
        if not providers:
            providers = ["CPUExecutionProvider"]

        self.session = ort.InferenceSession(
            self.model_path,
            sess_options=opts,
            providers=providers,
        )
        self.input_name = self.session.get_inputs()[0].name
        self._SESSION_CACHE[cache_key] = (self.session, self.input_name, self.char_list)

    def set_threads(self, num_threads: int):
        new_threads = max(1, int(num_threads))
        if new_threads != self.num_threads:
            self.num_threads = new_threads
            if ort is not None and os.path.exists(self.model_path) and os.path.exists(self.dict_path):
                self._load()

    @property
    def is_available(self) -> bool:
        return self.session is not None

    def _run_onnx_crop(self, crop: Image.Image, width_scale: float = 0.85) -> Tuple[np.ndarray, int]:
        """Resize a PIL crop to height 48, normalize, and run ONNX inference."""
        cw, ch = crop.size
        gray_bytes = crop.tobytes() if crop.mode == "L" else crop.convert("L").tobytes()
        cache_key = (cw, ch, gray_bytes)
        if cache_key in self._crop_cache:
            return self._crop_cache[cache_key]

        if crop.mode != "RGB":
            crop_rgb = crop.convert("RGB")
        else:
            crop_rgb = crop

        target_h = 48
        target_w = max(16, int(target_h * (cw / ch) * width_scale))
        crop_resized = crop_rgb.resize((target_w, target_h), Image.Resampling.BILINEAR)

        arr = np.array(crop_resized, dtype=np.float32) * (1.0 / 127.5) - 1.0
        arr = np.transpose(arr, (2, 0, 1))  # (3, 48, W)
        arr = np.expand_dims(arr, axis=0)    # (1, 3, 48, W)

        preds = self.session.run(None, {self.input_name: arr})[0]
        res = (preds[0], len(preds[0]))
        if len(self._crop_cache) < 512:
            self._crop_cache[cache_key] = res
        return res

    def _finalize_word(self, text: str) -> str:
        text = self.postprocess_text(text)
        if self.accent_restorer is not None:
            text = self.accent_restorer.restore(text)
        return text

    def recognize_crop(self, crop: Image.Image) -> Tuple[str, float]:
        """Recognize text in a single PIL image crop."""
        if not self.is_available:
            return "", 0.0

        cw, ch = crop.size
        if cw == 0 or ch == 0:
            return "", 0.0

        logits, _ = self._run_onnx_crop(crop, width_scale=0.90)
        pred_idx = np.argmax(logits, axis=-1)

        decoded = []
        confs = []
        last_idx = 0
        for step_i, idx in enumerate(pred_idx):
            if idx != 0 and idx != last_idx:
                if idx < len(self.char_list):
                    decoded.append(self.char_list[idx])
                    confs.append(float(logits[step_i, idx]))
            last_idx = idx

        text = "".join(decoded).strip()
        confidence = float(np.mean(confs)) if confs else 0.0
        text = self._finalize_word(text)
        return text, confidence

    def recognize_line_words(
        self,
        pil_img: Image.Image,
        word_boxes: List[Tuple[int, int, int, int]],
    ) -> List[Dict[str, object]]:
        """Recognize all word boxes in a horizontal text line in a single ONNX pass.

        Uses CTC timestep-to-word-box spatial alignment so an entire line of K
        words requires only 1 ONNX invocation instead of K separate calls, while
        preserving exact per-word bounding boxes and confidence scores.
        """
        if not word_boxes:
            return []
        if not self.is_available or pil_img is None:
            return [{"text": "", "bbox": b, "confidence": 0.0} for b in word_boxes]

        img_w, img_h = pil_img.size

        # Split into contiguous sub-line spans if there is a wide horizontal gap (> 90 px)
        # or more than 10 words per span.
        spans: List[List[Tuple[int, int, int, int]]] = [[word_boxes[0]]]
        for b in word_boxes[1:]:
            prev_b = spans[-1][-1]
            line_h = max(12, prev_b[3] - prev_b[1])
            max_span_gap = max(80, line_h * 3)
            if (b[0] - prev_b[2]) > max_span_gap or len(spans[-1]) >= 10:
                spans.append([b])
            else:
                spans[-1].append(b)

        results: List[Dict[str, object]] = []
        for span in spans:
            if len(span) == 1:
                b = span[0]
                pad_x = 4
                pad_y = max(3, (b[3] - b[1]) // 6)
                cx0 = max(0, b[0] - pad_x)
                cy0 = max(0, b[1] - pad_y)
                cx1 = min(img_w, b[2] + pad_x)
                cy1 = min(img_h, b[3] + pad_y)
                crop = pil_img.crop((cx0, cy0, cx1, cy1))
                text, conf = self.recognize_crop(crop)
                results.append({"text": text, "bbox": b, "confidence": conf})
                continue

            pad_x = 4
            min_top = min(b[1] for b in span)
            max_bot = max(b[3] for b in span)
            pad_y = max(3, (max_bot - min_top) // 6)

            lx0 = max(0, span[0][0] - pad_x)
            ly0 = max(0, min_top - pad_y)
            lx1 = min(img_w, span[-1][2] + pad_x)
            ly1 = min(img_h, max_bot + pad_y)

            line_crop = pil_img.crop((lx0, ly0, lx1, ly1))
            logits, num_steps = self._run_onnx_crop(line_crop, width_scale=0.80)
            pred_idx = np.argmax(logits, axis=-1)

            # Midpoints between consecutive word boxes define spatial Voronoi boundaries
            boundaries = [
                0.5 * (span[i][2] + span[i + 1][0])
                for i in range(len(span) - 1)
            ]
            word_chars: List[List[str]] = [[] for _ in span]
            word_confs: List[List[float]] = [[] for _ in span]
            box_had_space_before: List[bool] = [False for _ in span]

            span_w = float(max(1, lx1 - lx0))
            last_idx = 0
            pending_space = False
            last_box_idx = -1

            for step_i, idx in enumerate(pred_idx):
                if idx != 0 and idx != last_idx and idx < len(self.char_list):
                    ch_str = self.char_list[idx]
                    if ch_str == " ":
                        pending_space = True
                    else:
                        x_img = lx0 + ((step_i + 0.5) / num_steps) * span_w
                        b_idx = 0
                        while b_idx < len(boundaries) and x_img > boundaries[b_idx]:
                            b_idx += 1
                        if pending_space:
                            if b_idx == last_box_idx and word_chars[b_idx]:
                                word_chars[b_idx].append(" ")
                            elif b_idx > last_box_idx >= 0 and not word_chars[b_idx]:
                                box_had_space_before[b_idx] = True
                            pending_space = False
                        word_chars[b_idx].append(ch_str)
                        word_confs[b_idx].append(float(logits[step_i, idx]))
                        last_box_idx = b_idx
                last_idx = idx

            # Merge adjacent boxes where C++ split a tight kerning pair (e.g. "1" + ",250.00")
            # and the neural network confirmed there is NO space between them.
            merged_span: List[Tuple[int, int, int, int]] = []
            merged_chars: List[List[str]] = []
            merged_confs: List[List[float]] = []

            for i, (b, w_ch, w_cf) in enumerate(zip(span, word_chars, word_confs)):
                if not w_ch:
                    continue
                if (
                    merged_span
                    and not box_had_space_before[i]
                    and (b[0] - merged_span[-1][2]) <= max(11, (max_bot - min_top) // 2)
                ):
                    prev_b = merged_span[-1]
                    merged_span[-1] = (prev_b[0], min(prev_b[1], b[1]), b[2], max(prev_b[3], b[3]))
                    merged_chars[-1].extend(w_ch)
                    merged_confs[-1].extend(w_cf)
                else:
                    merged_span.append(b)
                    merged_chars.append(w_ch)
                    merged_confs.append(w_cf)

            for b, w_ch, w_cf in zip(merged_span, merged_chars, merged_confs):
                raw_word = "".join(w_ch).strip()
                conf = float(np.mean(w_cf)) if w_cf else 0.0
                final_word = self._finalize_word(raw_word)
                results.append({"text": final_word, "bbox": b, "confidence": conf})

        return results

    @staticmethod
    def postprocess_text(text: str) -> str:
        """Heuristic post-processing: harmonize casing for OCR artifacts.

        When a word of >= 3 letters is overwhelmingly uppercase with a single
        isolated lowercase glyph (typical of lightweight models on all-caps
        text), it is unified to uppercase. Mixed-case words are left untouched.
        """
        if not text:
            return ""
        letters = [c for c in text if c.isalpha()]
        if len(letters) >= 3:
            upper_count = sum(1 for c in letters if c.isupper())
            lower_count = len(letters) - upper_count
            if lower_count == 1 and upper_count >= 2:
                return text.upper()
        return text
