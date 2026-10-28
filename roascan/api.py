"""
roascan.api: Stable high-level Python API & Bridge Contract for RoaScan.

Implements the standard bridge contract:
  Input:  { image_path | image_bytes | PIL.Image | PDF, lang?, options? }
  Output: RoaScanResult { text, words, pages, markdown, confidences, markdown_path, pdf_path }

Designed for zero-vendor-lock, 100% offline local CPU OCR.
"""

import io
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple, Union
from PIL import Image

from .docout import RoaScanDocumentWriter, validate_output_paths
from .engine import RoaScanEngine


@dataclass
class RoaScanResult(Mapping[str, Any]):
    """Standardized result object produced by RoaScan OCR.

    Supports both object attribute access (`result.text`) and dictionary mapping
    access (`result["text"]`) to satisfy bridge contracts across desktop UIs,
    scripts, and AI agents.
    """

    text: str = ""
    markdown: str = ""
    words: List[Dict[str, Any]] = field(default_factory=list)
    pages: List[Dict[str, Any]] = field(default_factory=list)
    confidences: List[float] = field(default_factory=list)
    page_count: int = 1
    markdown_path: Optional[str] = None
    pdf_path: Optional[str] = None
    ocr_elapsed_ms: float = 0.0
    elapsed_ms: float = 0.0
    language: str = "es"

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        keys = [
            "text",
            "markdown",
            "words",
            "pages",
            "confidences",
            "page_count",
            "markdown_path",
            "pdf_path",
            "ocr_elapsed_ms",
            "elapsed_ms",
            "language",
        ]
        return iter(keys)

    def __len__(self) -> int:
        return 11

    def to_dict(self) -> Dict[str, Any]:
        """Convert result into a serializable JSON-friendly dictionary."""
        return {
            "text": self.text,
            "markdown": self.markdown,
            "words": self.words,
            "pages": self.pages,
            "confidences": self.confidences,
            "page_count": self.page_count,
            "markdown_path": self.markdown_path,
            "pdf_path": self.pdf_path,
            "ocr_elapsed_ms": self.ocr_elapsed_ms,
            "elapsed_ms": self.elapsed_ms,
            "language": self.language,
        }

    def copy_to_clipboard(self, use_markdown: bool = False) -> bool:
        """Copy recognized text or markdown directly to the system clipboard."""
        from .desktop.clipboard import copy_to_clipboard

        content = self.markdown if use_markdown else self.text
        return copy_to_clipboard(content)

    def save_markdown(self, output_path: Union[str, Path]) -> str:
        """Save extracted structured Markdown to file."""
        abs_p = os.path.abspath(str(output_path))
        with RoaScanDocumentWriter() as writer:
            writer.configure_markdown(abs_p)
            writer._atomic_write_text(abs_p, self.markdown)
        self.markdown_path = abs_p
        return abs_p


def run_ocr(
    target: Union[str, Path, bytes, Image.Image],
    language: str = "es",
    dpi: int = 300,
    enhance_quality: bool = True,
    output_md_path: Optional[Union[str, Path]] = None,
    output_pdf_path: Optional[Union[str, Path]] = None,
    options: Optional[Dict[str, Any]] = None,
) -> RoaScanResult:
    """Execute RoaScan OCR on an image file, PDF, raw bytes, or PIL Image.

    Args:
        target: File path (.png, .jpg, .bmp, .tiff, .pdf), raw image bytes, or PIL.Image.
        language: Language code ('es', 'en', 'latin').
        dpi: Target DPI rasterization for PDF or image scaling (default: 300).
        enhance_quality: Apply C++ Sauvola background whitening and deskew.
        output_md_path: Optional destination path to write structured Markdown (.md).
        output_pdf_path: Optional destination path to write Searchable PDF (.pdf).
        options: Optional dict of advanced tuning options (e.g. {'threads': 4, 'threshold': 0}).

    Returns:
        RoaScanResult conforming to the bridge contract.
    """
    t_start = time.perf_counter()
    opts = options or {}
    threads = int(opts.get("threads", 0))

    out_md = str(output_md_path) if output_md_path else None
    out_pdf = str(output_pdf_path) if output_pdf_path else None

    # Validate output paths if provided
    in_file = str(target) if (isinstance(target, (str, Path)) and os.path.isfile(str(target))) else None
    if out_md or out_pdf:
        validate_output_paths(
            in_file,
            [out_pdf, out_md],
            expected_formats=["pdf", "md"],
        )

    with RoaScanEngine(language=language) as engine:
        engine.set_resolution(dpi, dpi)
        engine.set_document_enhancement(enhance_quality)
        engine.set_retain_images(bool(out_pdf))
        if threads > 0:
            engine.set_thread_count(threads)

        if "brightness" in opts:
            engine.set_brightness(int(opts["brightness"]))
        if "contrast" in opts:
            engine.set_contrast(int(opts["contrast"]))
        if "threshold" in opts:
            engine.set_threshold(int(opts["threshold"]))

        # Ingestion dispatch
        if isinstance(target, (str, Path)):
            p = str(target)
            if not os.path.exists(p):
                raise FileNotFoundError(f"Input file not found: {p}")
            engine.set_image_file(p)
        elif isinstance(target, Image.Image):
            gray = target.convert("L")
            w, h = gray.size
            engine.set_raw_image(gray.tobytes(), w, h, bpp=8)
        elif isinstance(target, (bytes, bytearray)):
            # Try decoding bytes as standard image via PIL
            bio = io.BytesIO(target)
            try:
                with Image.open(bio) as im:
                    gray = im.convert("L")
                    w, h = gray.size
                    engine.set_raw_image(gray.tobytes(), w, h, bpp=8)
            except Exception as exc:
                raise ValueError(f"Could not decode image bytes: {exc}")
        else:
            raise TypeError(f"Unsupported target type: {type(target)}")

        t_ocr0 = time.perf_counter()
        rc = engine.recognize()
        ocr_ms = round((time.perf_counter() - t_ocr0) * 1000.0, 2)

        if rc != 0:
            raise RuntimeError(engine.last_error or f"RoaScan recognition failed with code {rc}")

        extracted_words = engine.extract_words()
        extracted_pages = engine.extract_pages()
        text = engine.get_text()
        markdown = engine.to_markdown()
        confs = [float(w.get("confidence", 0.0)) for w in extracted_words if "confidence" in w]

        written_md = None
        written_pdf = None

        with RoaScanDocumentWriter() as writer:
            if out_md:
                writer.configure_markdown(out_md)
                w_rc = writer.write(engine)
                if w_rc != 0:
                    raise RuntimeError(writer.last_error or f"Failed to write Markdown to {out_md}")
                written_md = os.path.abspath(out_md)

            if out_pdf:
                writer.configure_pdf(out_pdf, enhance_quality=enhance_quality)
                w_rc = writer.write(engine)
                if w_rc != 0:
                    raise RuntimeError(writer.last_error or f"Failed to write PDF to {out_pdf}")
                written_pdf = os.path.abspath(out_pdf)

        total_ms = round((time.perf_counter() - t_start) * 1000.0, 2)

        return RoaScanResult(
            text=text,
            markdown=markdown,
            words=extracted_words,
            pages=extracted_pages,
            confidences=confs,
            page_count=engine.page_count,
            markdown_path=written_md,
            pdf_path=written_pdf,
            ocr_elapsed_ms=ocr_ms,
            elapsed_ms=total_ms,
            language=language,
        )
