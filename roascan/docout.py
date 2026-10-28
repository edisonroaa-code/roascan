"""
roascan.docout: Multi-Page Document & Markdown Output for RoaScan (clean-room).

Supports:
  1. Enhanced Multi-Page Searchable PDF (.pdf): Preserves exact physical page
     dimensions in PDF points (72 pt/inch), embeds the deskewed and C++
     background-whitened image for each page with a calibrated invisible
     selectable text layer (render_mode=3), and preserves document metadata.
     NOTE: Optical restoration rasterizes and reconstructs each page; native
     vector links, annotations, and form fields from digital-born PDFs are not preserved.
  2. Structured Semantic Markdown (.md): Reconstructs headings (# / ##),
     bold key-value pairs, multi-column blocks, and tables (|---|---|).
  3. Structured JSON (.json) and Plain Text (.txt) with unified schema.
"""

import io
import json
import os
import tempfile
from typing import Iterable, List, Optional, Tuple
from PIL import Image

SUPPORTED_AUTO_EXTENSIONS = (".pdf", ".md", ".markdown", ".json", ".txt")


def validate_output_format(output_path: Optional[str], expected_format: str = "auto") -> str:
    """Validate that an output path has a coherent extension for the requested format.

    Args:
        output_path: Path to validate.
        expected_format: One of 'pdf', 'md', 'json', 'txt', or 'auto'.

    Raises:
        ValueError: If the extension does not match the requested format contract.
    """
    if not output_path or not isinstance(output_path, str) or not output_path.strip():
        raise ValueError("Output path must be a non-empty string.")

    lower = output_path.strip().lower()
    fmt = (expected_format or "auto").lower()

    if fmt == "pdf":
        if not lower.endswith(".pdf"):
            raise ValueError(
                f"Explicit PDF output requires a '.pdf' extension, got: {output_path}"
            )
        return "pdf"

    if fmt in ("md", "markdown"):
        if not lower.endswith((".md", ".markdown")):
            raise ValueError(
                f"Explicit Markdown output requires a '.md' or '.markdown' extension, got: {output_path}"
            )
        return "md"

    if fmt == "json":
        if not lower.endswith(".json"):
            raise ValueError(
                f"Explicit JSON output requires a '.json' extension, got: {output_path}"
            )
        return "json"

    if fmt == "txt":
        if not lower.endswith(".txt"):
            raise ValueError(
                f"Explicit text output requires a '.txt' extension, got: {output_path}"
            )
        return "txt"

    if fmt == "auto":
        if not lower.endswith(SUPPORTED_AUTO_EXTENSIONS):
            raise ValueError(
                f"Unsupported output extension for '{output_path}'. "
                f"Supported extensions: {', '.join(SUPPORTED_AUTO_EXTENSIONS)}"
            )
        if lower.endswith(".pdf"):
            return "pdf"
        if lower.endswith((".md", ".markdown")):
            return "md"
        if lower.endswith(".json"):
            return "json"
        return "txt"

    raise ValueError(f"Unknown expected_format '{expected_format}'.")


def validate_output_paths(
    input_path: Optional[str],
    output_paths: Iterable[Optional[str]],
    expected_formats: Optional[Iterable[str]] = None,
) -> List[str]:
    """Validate output paths against input overwrite, duplicate targets, missing parent dirs,
    and format/extension incoherence.

    Raises:
        ValueError: If an output path resolves to the input path, duplicates another output path,
            or violates its expected format extension.
        FileNotFoundError: If the parent directory of an output path does not exist.
    """
    in_abs = os.path.abspath(input_path) if input_path else None
    in_norm = os.path.normcase(os.path.realpath(in_abs)) if in_abs else None
    in_exists = bool(in_abs and os.path.exists(in_abs))

    out_list = list(output_paths)
    fmt_list = list(expected_formats) if expected_formats is not None else ["auto"] * len(out_list)

    seen = set()
    validated: List[str] = []
    for idx, out_p in enumerate(out_list):
        if not out_p:
            continue
        if not isinstance(out_p, str) or not out_p.strip():
            raise ValueError("Output path must be a non-empty string.")

        exp_fmt = fmt_list[idx] if idx < len(fmt_list) else "auto"
        validate_output_format(out_p, exp_fmt)

        abs_out = os.path.abspath(out_p)
        norm_out = os.path.normcase(os.path.realpath(abs_out))
        if in_norm and norm_out == in_norm:
            raise ValueError(f"Refusing to overwrite input document: {abs_out}")
        if in_exists and os.path.exists(abs_out):
            try:
                if os.path.samefile(in_abs, abs_out):
                    raise ValueError(f"Refusing to overwrite input document (samefile): {abs_out}")
            except OSError:
                pass
        if norm_out in seen:
            raise ValueError(f"Duplicate output destination specified: {abs_out}")
        parent = os.path.dirname(abs_out)
        if parent and not os.path.isdir(parent):
            raise FileNotFoundError(f"Output directory does not exist: {parent}")
        seen.add(norm_out)
        validated.append(abs_out)
    return validated


def _create_exclusive_temp(target_path: str, input_path: Optional[str] = None) -> Tuple[int, str]:
    """Create an exclusive, unique temporary file in the same directory as target_path.
    Uses OS-level O_CREAT | O_EXCL via tempfile.mkstemp so it can never alias or overwrite
    an existing input file or concurrent temporary file.
    """
    abs_target = os.path.abspath(target_path)
    out_dir = os.path.dirname(abs_target) or "."
    base_name = os.path.basename(abs_target)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{base_name}.",
        suffix=".roascan.tmp",
        dir=out_dir,
    )
    if input_path and os.path.exists(input_path):
        try:
            if os.path.samefile(input_path, tmp_path):
                os.close(fd)
                raise ValueError(f"Temporary path collided with input document: {tmp_path}")
        except OSError:
            pass
    return fd, tmp_path


class RoaScanDocumentWriter:
    """Interface for multi-page document generation (PyMuPDF & Markdown)."""

    FORMAT_AUTO = 0
    FORMAT_PDF_MRC = 1  # Mixed Raster Content (ISO 16497)
    FORMAT_PDF_STD = 2
    FORMAT_TXT = 5
    FORMAT_JSON = 8
    FORMAT_MARKDOWN = 9

    def __init__(self, dll_dir: Optional[str] = None):
        self._output_path: Optional[str] = None
        self._format_type: int = self.FORMAT_PDF_STD
        self._pdf_version: int = 15
        self._text_over_image: bool = True
        self._embed_fonts: bool = True
        self._enhance_quality: bool = True
        self.last_error: Optional[str] = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self._output_path = None

    def configure_pdf(
        self,
        output_path: str,
        format_type: int = FORMAT_PDF_STD,
        pdf_version: int = 15,
        text_over_image: bool = True,
        embed_fonts: bool = True,
        enhance_quality: bool = True,
    ):
        """Configure explicit Searchable PDF (.pdf) output settings."""
        validate_output_format(output_path, "pdf")
        self._output_path = os.path.abspath(output_path)
        self._format_type = format_type if format_type in (self.FORMAT_PDF_STD, self.FORMAT_PDF_MRC) else self.FORMAT_PDF_STD
        self._pdf_version = pdf_version
        self._text_over_image = text_over_image
        self._embed_fonts = embed_fonts
        self._enhance_quality = enhance_quality

    def configure_markdown(self, output_path: str):
        """Configure explicit structured Markdown (.md) output."""
        validate_output_format(output_path, "md")
        self._output_path = os.path.abspath(output_path)
        self._format_type = self.FORMAT_MARKDOWN

    def configure_auto(self, output_path: str, enhance_quality: bool = True):
        """Configure generic output whose format (.pdf, .md, .json, .txt) is inferred from extension."""
        validate_output_format(output_path, "auto")
        self._output_path = os.path.abspath(output_path)
        self._format_type = self.FORMAT_AUTO
        self._enhance_quality = enhance_quality

    def _atomic_write_text(self, target_path: str, content: str, input_path: Optional[str] = None):
        fd, tmp_path = _create_exclusive_temp(target_path, input_path=input_path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = -1
                f.write(content)
            os.replace(tmp_path, target_path)
        except Exception:
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise

    def _expected_format_tag(self) -> str:
        if self._format_type in (self.FORMAT_PDF_STD, self.FORMAT_PDF_MRC):
            return "pdf"
        if self._format_type == self.FORMAT_MARKDOWN:
            return "md"
        if self._format_type == self.FORMAT_JSON:
            return "json"
        if self._format_type == self.FORMAT_TXT:
            return "txt"
        return "auto"

    def write(self, engine=None) -> int:
        """Write the output document (.pdf, .md, .json, or .txt). Returns 0 on success, <0 on failure."""
        self.last_error = None
        if not self._output_path:
            self.last_error = "No output path configured."
            return -1

        in_file = getattr(engine, "_current_image_file", None) if engine else None
        exp_tag = self._expected_format_tag()

        try:
            validate_output_paths(in_file, [self._output_path], expected_formats=[exp_tag])
            resolved_fmt = validate_output_format(self._output_path, exp_tag)
        except Exception as exc:
            self.last_error = str(exc)
            return -2

        try:
            if resolved_fmt == "md":
                md_text = engine.to_markdown() if (engine and hasattr(engine, "to_markdown")) else ""
                self._atomic_write_text(self._output_path, md_text, input_path=in_file)
                return 0

            if resolved_fmt == "txt":
                text = engine.get_text() if engine else ""
                self._atomic_write_text(self._output_path, text + "\n", input_path=in_file)
                return 0

            if resolved_fmt == "json":
                payload = engine.to_dict() if (engine and hasattr(engine, "to_dict")) else {
                    "version": "2.0.1",
                    "page_count": getattr(engine, "page_count", 0) if engine else 0,
                    "text": engine.get_text() if engine else "",
                    "markdown": engine.to_markdown() if (engine and hasattr(engine, "to_markdown")) else "",
                    "words": engine.extract_words() if engine else [],
                }
                self._atomic_write_text(
                    self._output_path,
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    input_path=in_file,
                )
                return 0

            return self._write_searchable_pdf_fitz(engine, input_path=in_file)
        except Exception as exc:
            self.last_error = str(exc)
            return -1

    def _insert_words_layer(
        self,
        fitz_mod,
        page,
        words,
        render_mode: int,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
    ):
        for w_info in words:
            text = w_info.get("text", "")
            bx = w_info.get("bbox")
            if bx and text:
                x0 = float(bx[0]) * scale_x
                y0 = float(bx[1]) * scale_y
                x1 = float(bx[2]) * scale_x
                y1 = float(bx[3]) * scale_y
                box_w = max(1.0, x1 - x0)
                box_h = max(1.0, y1 - y0)
                font_size = max(4.0, box_h * 0.85)
                try:
                    natural_w = fitz_mod.get_text_length(text, fontname="helv", fontsize=font_size)
                    if natural_w > 0:
                        font_size = font_size * (box_w / natural_w)
                        font_size = max(3.5, min(box_h * 1.25, font_size))
                except Exception:
                    pass

                page.insert_text(
                    fitz_mod.Point(x0, y1 - box_h * 0.12),
                    text,
                    fontname="helv",
                    fontsize=font_size,
                    render_mode=render_mode,
                )

    def _write_searchable_pdf_fitz(self, engine=None, input_path: Optional[str] = None) -> int:
        """Generate a single or multi-page enhanced searchable PDF preserving physical size in points."""
        try:
            import fitz
        except ImportError as exc:
            self.last_error = f"PyMuPDF (fitz) not available: {exc}"
            return -1

        fd, tmp_path = _create_exclusive_temp(self._output_path, input_path=input_path)
        os.close(fd)
        try:
            doc = fitz.open()
            render_mode = 3 if self._text_over_image else 0
            pages = engine.extract_pages() if (engine and hasattr(engine, "extract_pages")) else []
            default_dpi_x = float(getattr(engine, "_dpi_x", 300) or 300)
            default_dpi_y = float(getattr(engine, "_dpi_y", 300) or 300)

            if pages:
                for p in pages:
                    pw = int(p.get("width", 0) or 0)
                    ph = int(p.get("height", 0) or 0)
                    dpi_x = float(p.get("dpi_x", default_dpi_x) or default_dpi_x)
                    dpi_y = float(p.get("dpi_y", default_dpi_y) or default_dpi_y)

                    # Preserve exact physical page dimensions in PDF points (1 pt = 1/72 inch)
                    w_pt = float(p.get("width_pt") or (pw * 72.0 / dpi_x if dpi_x > 0 else pw))
                    h_pt = float(p.get("height_pt") or (ph * 72.0 / dpi_y if dpi_y > 0 else ph))

                    scale_x = (w_pt / pw) if pw > 0 else 1.0
                    scale_y = (h_pt / ph) if ph > 0 else 1.0

                    page = doc.new_page(width=w_pt, height=h_pt)
                    if self._text_over_image and pw > 0 and ph > 0:
                        spool_path = (
                            p.get("enhanced_spool_path")
                            if self._enhance_quality
                            else p.get("gray_spool_path")
                        ) or p.get("gray_spool_path")

                        if spool_path and os.path.exists(spool_path):
                            page.insert_image(page.rect, filename=spool_path)
                        else:
                            img_bytes = p.get("enhanced_gray") if self._enhance_quality else p.get("gray")
                            if not img_bytes:
                                img_bytes = p.get("gray")
                            if img_bytes:
                                pil_im = Image.frombytes("L", (pw, ph), img_bytes)
                                bio = io.BytesIO()
                                pil_im.save(bio, format="PNG", optimize=True)
                                page.insert_image(page.rect, stream=bio.getvalue())

                    self._insert_words_layer(
                        fitz,
                        page,
                        p.get("words", []),
                        render_mode,
                        scale_x=scale_x,
                        scale_y=scale_y,
                    )
            else:
                pw = int(getattr(engine, "_width", 1200) or 1200)
                ph = int(getattr(engine, "_height", 800) or 800)
                w_pt = pw * 72.0 / default_dpi_x
                h_pt = ph * 72.0 / default_dpi_y
                page = doc.new_page(width=w_pt, height=h_pt)
                words = engine.extract_words() if engine else []
                self._insert_words_layer(
                    fitz,
                    page,
                    words,
                    render_mode,
                    scale_x=w_pt / pw,
                    scale_y=h_pt / ph,
                )

            # Preserve original PDF metadata if available
            meta = getattr(engine, "_pdf_metadata", None) if engine else None
            if isinstance(meta, dict) and meta:
                clean_meta = {k: v for k, v in meta.items() if isinstance(v, str) and v}
                if clean_meta:
                    try:
                        doc.set_metadata(clean_meta)
                    except Exception:
                        pass

            doc.save(tmp_path, garbage=4, deflate=True)
            doc.close()

            # Verify valid %PDF- magic header before replacing destination
            with open(tmp_path, "rb") as f_chk:
                magic = f_chk.read(5)
            if magic != b"%PDF-":
                raise RuntimeError(f"Generated file does not have a valid %PDF- header: {self._output_path}")

            os.replace(tmp_path, self._output_path)
            return 0
        except Exception as exc:
            self.last_error = str(exc)
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            return -1


# Compatibility alias
RoaScanDocOut = RoaScanDocumentWriter
