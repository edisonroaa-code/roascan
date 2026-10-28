"""
RoaScan (roascan): Ultra-Lightweight C++17 & ONNX Multi-Page OCR Engine.

Built for AI Agents and Enterprise Document Pipelines:
  - Converts multi-page scanned PDFs/TIFFs/images into:
      1. Restored, background-whitened, compressed Searchable PDFs (.pdf)
      2. Structured Semantic Markdown (.md) with headings, key-values, and tables
  - Runs 100% locally on CPU with native C++17 preprocessing and ONNX Runtime.

Standard Bridge Contract APIs:
  - `roascan.run_ocr(target, ...)`: Core entrypoint returning `RoaScanResult`.
  - `RoaScanEngine.run(target, ...)`: Documented staticmethod alias to `run_ocr`
    satisfying the bridge contract:
        Input:  { image_path | image_bytes | PIL.Image | PDF, lang?, options? }
        Output: RoaScanResult { text, words, pages, markdown, confidences, ... }
"""

from typing import Optional
from .engine import RoaScanEngine
from .prepro import RoaScanPreprocessor
from .docout import RoaScanDocumentWriter, validate_output_paths, validate_output_format
from .native import RoaScanNativeDriver, get_native_driver, RoaScanRect
from .recognizer import RoaScanTextRecognizer
from .api import RoaScanResult, run_ocr

# Bridge Contract API:
# RoaScanEngine.run is exposed as a staticmethod pointing to `run_ocr`.
# It provides a consistent, object-oriented entrypoint for callers and desktop hosts:
#     result = RoaScanEngine.run("factura.png", language="es")
# returning a typed RoaScanResult satisfying { text, words, pages, confidences, ... }.
RoaScanEngine.run = staticmethod(run_ocr)


def scan_to_markdown(
    input_path: str,
    output_md_path: Optional[str] = None,
    language: str = "es",
    dpi: int = 300,
) -> str:
    """One-call helper: convert any scanned PDF/TIFF/image into structured Markdown (.md)."""
    if output_md_path is not None:
        validate_output_paths(input_path, [output_md_path], expected_formats=["md"])

    res = run_ocr(input_path, language=language, dpi=dpi, output_md_path=output_md_path)
    return res.markdown


def scan_to_pdf(
    input_path: str,
    output_pdf_path: str,
    language: str = "es",
    dpi: int = 300,
    enhance_quality: bool = True,
) -> int:
    """One-call helper: convert a scanned PDF/TIFF/image into a restored Searchable PDF (.pdf)."""
    validate_output_paths(input_path, [output_pdf_path], expected_formats=["pdf"])
    with RoaScanEngine(language=language) as engine:
        rc = engine.process_document(
            input_path=input_path,
            output_path=output_pdf_path,
            dpi=dpi,
            enhance_quality=enhance_quality,
            expected_format="pdf",
        )
        if rc != 0:
            raise RuntimeError(engine.last_error or f"Failed to generate Searchable PDF (code {rc})")
        return rc


__version__ = "2.0.0"
__all__ = [
    "RoaScanEngine",
    "RoaScanPreprocessor",
    "RoaScanDocumentWriter",
    "RoaScanNativeDriver",
    "RoaScanRect",
    "RoaScanTextRecognizer",
    "RoaScanResult",
    "run_ocr",
    "get_native_driver",
    "scan_to_markdown",
    "scan_to_pdf",
    "validate_output_paths",
    "validate_output_format",
]
