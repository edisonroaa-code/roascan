"""
tests/test_functional_ocr.py: Comprehensive automated test suite for RoaScan (pytest & standalone).

Covers:
  1. End-to-end English OCR accuracy (INV-987654, USD 1,250.00, APPROVED).
  2. End-to-end Spanish OCR accuracy (RUC 80012345-6, factura 001-002-0000123, fecha 28/10/2026,
     importe 1.300.000, Peña, ELECTRÓNICA, and boxed 3-column Markdown table reconstruction).
  3. Multi-page TIFF orientation recovery across all 4 orthogonal rotations (0°, 90°, 180°, 270°).
  4. P0 & R1: Protection against overwriting the input document (direct canonical collision AND
     exclusive temporary file creation when input is named `target.tmp.<pid>`).
  5. R2: Strict format/extension contract (rejecting `.md` or `.png` on explicit PDF interfaces
     and `.pdf` on explicit Markdown interfaces, plus `%PDF-` header verification).
  6. P1: Error propagation when output directory does not exist (CLI & MCP).
  7. P1: Physical PDF page size preservation in PDF points (A4 595.28 x 841.89 pt) & metadata preservation.
  8. P1: Explicit error return (-3) when ONNX model session is unavailable.
  9. P1: Strict MCP JSON-RPC 2.0 protocol validation (non-object payloads, invalid params, unknown tools).
  10. P1: Raw buffer bounds checking and individually isolated brightness, contrast, and threshold controls.
  11. R4: Multi-page PDF disk-backed image spooling (0 bytes of raw bitmaps retained in `engine._pages`
      during Searchable PDF generation) and automatic spool directory cleanup on `close()`.
"""

import hashlib
import os
import sys
import tempfile
from PIL import Image, ImageDraw, ImageFont

current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(current_dir)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from roascan import (
    RoaScanEngine,
    RoaScanDocumentWriter,
    scan_to_markdown,
    scan_to_pdf,
)
from roascan.__main__ import main as cli_main
from roascan.mcp_server import handle_jsonrpc_message


def _load_fonts():
    # Render identical documents on every host; system fonts and Pillow's
    # fallback change glyph shapes and therefore the OCR input itself.
    font_path = os.path.join(current_dir, "assets", "DejaVuSans.ttf")
    return ImageFont.truetype(font_path, 46), ImageFont.truetype(font_path, 30)


def create_test_image(path: str, ink_gray: int = 0) -> str:
    width, height = 1200, 600
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)
    font_large, font_small = _load_fonts()

    draw.text((80, 80), "ROASCAN RECOGNITION SYSTEM 2026", fill=ink_gray, font=font_large)
    draw.text((80, 180), "INVOICE NUMBER: INV-987654", fill=ink_gray, font=font_small)
    draw.text((80, 260), "TOTAL AMOUNT: USD 1,250.00", fill=ink_gray, font=font_small)
    draw.text((80, 340), "STATUS: APPROVED AND VERIFIED", fill=ink_gray, font=font_small)

    img.save(path, format="PNG", dpi=(300, 300))
    return path


def create_spanish_invoice_with_table(path: str) -> str:
    width, height = 1600, 1100
    img = Image.new("L", (width, height), color=255)
    draw = ImageDraw.Draw(img)
    font_large, font_small = _load_fonts()

    draw.text((80, 60), "FACTURA ELECTRONICA", fill=0, font=font_large)
    draw.text((80, 150), "RUC: 80012345-6", fill=0, font=font_small)
    draw.text((80, 210), "Factura: 001-002-0000123", fill=0, font=font_small)
    draw.text((80, 270), "Fecha: 28/10/2026", fill=0, font=font_small)
    draw.text((80, 330), "Cliente: Jose Maria Peña", fill=0, font=font_small)

    # Draw a boxed 3-column table with solid grid lines
    x_cols = [80, 360, 1050, 1480]
    y_rows = [430, 510, 590, 670]
    for y in y_rows:
        draw.line([(x_cols[0], y), (x_cols[-1], y)], fill=0, width=3)
    for x in x_cols:
        draw.line([(x, y_rows[0]), (x, y_rows[-1])], fill=0, width=3)

    rows_data = [
        ("Codigo", "Descripcion", "Importe"),
        ("A01", "Licencia Corporativa", "1.300.000"),
        ("A02", "Soporte Tecnico", "450.000"),
    ]
    for r_idx, (c1, c2, c3) in enumerate(rows_data):
        ty = y_rows[r_idx] + 22
        draw.text((x_cols[0] + 20, ty), c1, fill=0, font=font_small)
        draw.text((x_cols[1] + 20, ty), c2, fill=0, font=font_small)
        draw.text((x_cols[2] + 20, ty), c3, fill=0, font=font_small)

    img.save(path, format="PNG", dpi=(300, 300))
    return path


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def test_missing_system_fonts_keep_spanish_ocr_readable(monkeypatch):
    original_truetype = ImageFont.truetype

    def without_system_fonts(font, *args, **kwargs):
        if isinstance(font, str) and font in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
            raise OSError("Simulated host without system fonts")
        return original_truetype(font, *args, **kwargs)

    monkeypatch.setattr(ImageFont, "truetype", without_system_fonts)
    large, small = _load_fonts()
    assert large.getbbox("ROASCAN")[3] - large.getbbox("ROASCAN")[1] >= 30
    assert small.getbbox("Peña")[3] - small.getbbox("Peña")[1] >= 20
    # Glyph height alone missed the macOS regression: the fallback font made
    # the recognizer read the surname as Peßa despite a readable text size.
    test_spanish_invoice_diacritics_ruc_and_boxed_table()


# ---------------------------------------------------------------------------
# 1. English OCR Accuracy
# ---------------------------------------------------------------------------
def test_end_to_end_ocr_accuracy():
    img_path = os.path.join(current_dir, "test_document.png")
    create_test_image(img_path)

    with RoaScanEngine(language="en") as engine:
        engine.set_resolution(300, 300)
        engine.set_image_file(img_path)
        assert engine.recognize() == 0
        words = engine.extract_words()
        assert len(words) >= 12
        full_text = engine.get_text()
        assert "INV-987654" in full_text
        assert "1,250.00" in full_text
        assert "APPROVED" in full_text


# ---------------------------------------------------------------------------
# 2. Spanish OCR Accuracy (Diacritics, RUC, Peña, and Boxed Table)
# ---------------------------------------------------------------------------
def test_spanish_invoice_diacritics_ruc_and_boxed_table():
    with tempfile.TemporaryDirectory() as tmpdir:
        inv_path = os.path.join(tmpdir, "factura_es.png")
        create_spanish_invoice_with_table(inv_path)

        with RoaScanEngine(language="es") as engine:
            engine.set_resolution(300, 300)
            engine.set_image_file(inv_path)
            assert engine.recognize() == 0
            text = engine.get_text()
            md = engine.to_markdown()

            assert "80012345-6" in text, f"Missing RUC in: {text}"
            assert "001-002-0000123" in text, f"Missing Factura number in: {text}"
            assert "28/10/2026" in text, f"Missing date in: {text}"
            assert "1.300.000" in text, f"Missing amount in: {text}"
            assert "Peña" in text, f"Expected 'Peña' with ñ preserved in: {text}"
            assert "ELECTRÓNICA" in text, f"Expected Hunspell accent restoration 'ELECTRÓNICA' in: {text}"
            assert "| :--- | :--- | :--- |" in md, f"Expected 3-column Markdown table in:\n{md}"


# ---------------------------------------------------------------------------
# 3. Multi-Page TIFF Orientation Recovery (0°, 90°, 180°, 270°)
# ---------------------------------------------------------------------------
def test_multipage_tiff_all_four_orientations_0_90_180_270():
    with tempfile.TemporaryDirectory() as tmpdir:
        base_png = os.path.join(tmpdir, "base.png")
        create_test_image(base_png)
        base_im = Image.open(base_png)

        # Create 4 frames rotated at 0, 90, 180, and 270 degrees
        frames = [
            base_im.copy(),
            base_im.rotate(90, expand=True),
            base_im.rotate(180, expand=True),
            base_im.rotate(270, expand=True),
        ]
        tiff_path = os.path.join(tmpdir, "four_orientations.tiff")
        frames[0].save(
            tiff_path,
            save_all=True,
            append_images=frames[1:],
            dpi=(300, 300),
        )
        base_im.close()

        with RoaScanEngine(language="en") as engine:
            engine.set_resolution(300, 300)
            engine.set_image_file(tiff_path)
            assert engine.recognize() == 0
            pages = engine.extract_pages()
            assert len(pages) == 4
            for idx, p in enumerate(pages):
                p_text = " ".join(w["text"] for w in p["words"])
                assert "INV-987654" in p_text or "APPROVED" in p_text, (
                    f"Page {idx + 1} failed orientation recovery, got: {p_text}"
                )


# ---------------------------------------------------------------------------
# 4. P0 & R1: Input Overwrite Protection + Temp-File Collision Protection
# ---------------------------------------------------------------------------
def test_p0_input_overwrite_and_r1_temp_collision_protection():
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "sample.png")
        create_test_image(img_path)
        orig_hash = _sha256(img_path)

        # 1. Direct canonical collision: CLI must refuse input == output
        rc_md = cli_main([img_path, "--md", img_path, "--json"])
        assert rc_md != 0
        assert _sha256(img_path) == orig_hash

        rc_pdf = cli_main([img_path, "--pdf", img_path, "--json"])
        assert rc_pdf != 0
        assert _sha256(img_path) == orig_hash

        # 2. Direct collision in SDK scan_to_markdown & scan_to_pdf
        for fn in (
            lambda: scan_to_markdown(img_path, output_md_path=img_path),
            lambda: scan_to_pdf(img_path, output_pdf_path=img_path),
        ):
            try:
                fn()
                assert False, "Expected ValueError when input == output"
            except ValueError:
                pass
            assert _sha256(img_path) == orig_hash

        # 3. Direct collision in MCP
        resp = handle_jsonrpc_message({
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "roascan_to_markdown",
                "arguments": {"input_path": img_path, "output_md_path": img_path},
            },
        })
        assert resp["result"]["isError"] is True
        assert _sha256(img_path) == orig_hash

        # 4. R1 Reproduction: Input named `restored.md.tmp.<pid>` with destination `restored.md`
        target_md = os.path.join(tmpdir, "restored.md")
        tricky_input_md = f"{target_md}.tmp.{os.getpid()}"
        create_test_image(tricky_input_md)
        tricky_hash = _sha256(tricky_input_md)

        md_out = scan_to_markdown(tricky_input_md, output_md_path=target_md, language="en")
        assert os.path.exists(tricky_input_md), "R1 regression: original input file was deleted by temp writer!"
        assert _sha256(tricky_input_md) == tricky_hash, "R1 regression: original input hash changed!"
        assert os.path.exists(target_md)
        assert "INV-987654" in md_out

        # 5. R1 Reproduction on PDF output: Input named `restored.pdf.tmp.<pid>` with destination `restored.pdf`
        target_pdf = os.path.join(tmpdir, "restored.pdf")
        tricky_input_pdf = f"{target_pdf}.tmp.{os.getpid()}"
        create_test_image(tricky_input_pdf)
        tricky_pdf_hash = _sha256(tricky_input_pdf)

        scan_to_pdf(tricky_input_pdf, output_pdf_path=target_pdf, language="en")
        assert os.path.exists(tricky_input_pdf), "R1 regression on PDF: original input file was deleted!"
        assert _sha256(tricky_input_pdf) == tricky_pdf_hash
        assert os.path.exists(target_pdf)


# ---------------------------------------------------------------------------
# 5. R2: Strict Format & Extension Contract
# ---------------------------------------------------------------------------
def test_r2_strict_output_format_and_extension_contract():
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "sample.png")
        create_test_image(img_path)

        bad_pdf_as_md = os.path.join(tmpdir, "explicit_pdf.md")
        bad_pdf_as_png = os.path.join(tmpdir, "explicit_pdf.png")
        bad_md_as_pdf = os.path.join(tmpdir, "explicit_md.pdf")

        # 1. MCP roascan_to_searchable_pdf must reject .md and .png extensions
        for bad_dest in (bad_pdf_as_md, bad_pdf_as_png):
            resp = handle_jsonrpc_message({
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {
                    "name": "roascan_to_searchable_pdf",
                    "arguments": {"input_path": img_path, "output_pdf_path": bad_dest},
                },
            })
            assert resp["result"]["isError"] is True, f"R2 regression: MCP accepted {bad_dest} for PDF!"
            assert not os.path.exists(bad_dest)

        # 2. MCP roascan_to_markdown must reject .pdf extension
        resp_md = handle_jsonrpc_message({
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {
                "name": "roascan_to_markdown",
                "arguments": {"input_path": img_path, "output_md_path": bad_md_as_pdf},
            },
        })
        assert resp_md["result"]["isError"] is True
        assert not os.path.exists(bad_md_as_pdf)

        # 3. CLI --pdf and --md and -o must reject mismatched/unsupported extensions
        assert cli_main([img_path, "--pdf", bad_pdf_as_md, "--json"]) != 0
        assert cli_main([img_path, "--pdf", bad_pdf_as_png, "--json"]) != 0
        assert cli_main([img_path, "--md", bad_md_as_pdf, "--json"]) != 0
        assert cli_main([img_path, "-o", bad_pdf_as_png, "--json"]) != 0

        # 4. Valid PDF output must start with %PDF- magic bytes
        good_pdf = os.path.join(tmpdir, "valid_output.pdf")
        scan_to_pdf(img_path, good_pdf, language="en")
        with open(good_pdf, "rb") as f:
            assert f.read(5) == b"%PDF-"


# ---------------------------------------------------------------------------
# 6. P1: Non-Existent Output Directory Propagation
# ---------------------------------------------------------------------------
def test_p1_nonexistent_output_dir_fails():
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "sample.png")
        create_test_image(img_path)
        bad_out = os.path.join(tmpdir, "nonexistent_subdir", "out.pdf")

        rc = cli_main([img_path, "--pdf", bad_out, "--json"])
        assert rc != 0
        assert not os.path.exists(bad_out)

        resp = handle_jsonrpc_message({
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "roascan_to_searchable_pdf",
                "arguments": {"input_path": img_path, "output_pdf_path": bad_out},
            },
        })
        assert resp["result"]["isError"] is True


# ---------------------------------------------------------------------------
# 7. P1: Physical PDF Page Geometry (A4 595.28 x 841.89 pt) & Metadata
# ---------------------------------------------------------------------------
def test_p1_pdf_physical_dimensions_a4():
    import fitz

    with tempfile.TemporaryDirectory() as tmpdir:
        in_pdf = os.path.join(tmpdir, "input_a4.pdf")
        out_pdf = os.path.join(tmpdir, "output_a4.pdf")
        img_path = os.path.join(tmpdir, "page.png")
        create_test_image(img_path)

        doc = fitz.open()
        page = doc.new_page(width=595.28, height=841.89)
        page.insert_image(fitz.Rect(36, 36, 559, 336), filename=img_path)
        doc.set_metadata({"title": "RoaScan Audit Test A4", "author": "Roa"})
        doc.save(in_pdf)
        doc.close()

        scan_to_pdf(in_pdf, out_pdf, language="en", dpi=300)
        assert os.path.exists(out_pdf)

        with fitz.open(out_pdf) as out_doc:
            assert len(out_doc) == 1
            out_rect = out_doc[0].rect
            assert abs(out_rect.width - 595.28) < 1.0, f"Expected ~595.28 pt width, got {out_rect.width}"
            assert abs(out_rect.height - 841.89) < 1.0, f"Expected ~841.89 pt height, got {out_rect.height}"
            extracted_txt = out_doc[0].get_text("text")
            assert "INV-987654" in extracted_txt
            assert out_doc.metadata.get("title") == "RoaScan Audit Test A4"


# ---------------------------------------------------------------------------
# 8. P1: Explicit Error Return (-3) on Missing ONNX Model
# ---------------------------------------------------------------------------
def test_p1_missing_onnx_model_fails_explicitly():
    img_path = os.path.join(current_dir, "test_document.png")
    if not os.path.exists(img_path):
        create_test_image(img_path)

    with RoaScanEngine(language="en") as engine:
        engine.set_image_file(img_path)
        engine.recognizer.session = None
        rc = engine.recognize()
        assert rc == -3, f"Expected error code -3 when ONNX session is missing, got {rc}"
        assert engine.last_error is not None


# ---------------------------------------------------------------------------
# 9. P1: Strict MCP JSON-RPC 2.0 Validation
# ---------------------------------------------------------------------------
def test_p1_mcp_protocol_and_negative_validation():
    r_arr = handle_jsonrpc_message([])
    assert r_arr["error"]["code"] == -32600

    r_params = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": 123})
    assert r_params["error"]["code"] == -32602

    r_init = handle_jsonrpc_message({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "initialize",
        "params": {"protocolVersion": "1999-01-01"},
    })
    assert r_init["result"]["protocolVersion"] in ("2024-11-05", "2025-03-26", "2025-06-18")

    r_bad_tool = handle_jsonrpc_message({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "non_existent_tool", "arguments": {"input_path": "x"}},
    })
    assert r_bad_tool["result"]["isError"] is True

    img_path = os.path.join(current_dir, "test_document.png")
    r_no_out = handle_jsonrpc_message({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "roascan_to_searchable_pdf", "arguments": {"input_path": img_path}},
    })
    assert r_no_out["result"]["isError"] is True


# ---------------------------------------------------------------------------
# 10. P1: Raw Buffer Bounds & Individually Isolated Controls
# ---------------------------------------------------------------------------
def test_p1_buffer_bounds_and_isolated_controls():
    with RoaScanEngine(language="en") as engine:
        # 1. Undersized buffer must raise ValueError before touching C++
        try:
            engine.set_raw_image(b"\x00", 100, 100, bpp=8)
            assert False, "Expected ValueError on 1-byte buffer for 100x100 image"
        except ValueError:
            pass

        gray_gradient = bytes([int((i % 200) * 255 / 200) for i in range(200 * 80)])

        # 2. Isolate Brightness only (contrast=128, threshold=0)
        engine.set_brightness(70)
        engine.set_contrast(128)
        engine.set_threshold(0)
        engine.set_raw_image(gray_gradient, 200, 80, bpp=8)
        assert engine.recognize() == 0
        bright_low = engine._processed_gray

        engine.set_brightness(200)
        engine.set_contrast(128)
        engine.set_threshold(0)
        engine.set_raw_image(gray_gradient, 200, 80, bpp=8)
        assert engine.recognize() == 0
        bright_high = engine._processed_gray
        assert bright_low != bright_high, "Isolated brightness control must modify processed grayscale"

        # 3. Isolate Contrast only (brightness=128, threshold=0)
        engine.set_brightness(128)
        engine.set_contrast(70)
        engine.set_threshold(0)
        engine.set_raw_image(gray_gradient, 200, 80, bpp=8)
        assert engine.recognize() == 0
        contrast_low = engine._processed_gray

        engine.set_brightness(128)
        engine.set_contrast(200)
        engine.set_threshold(0)
        engine.set_raw_image(gray_gradient, 200, 80, bpp=8)
        assert engine.recognize() == 0
        contrast_high = engine._processed_gray
        assert contrast_low != contrast_high, "Isolated contrast control must modify processed grayscale"

        # 4. Isolate Threshold only (brightness=128, contrast=128) on mid-gray ink (ink=140)
        with tempfile.TemporaryDirectory() as tmpdir:
            mid_img = os.path.join(tmpdir, "mid_gray_ink.png")
            create_test_image(mid_img, ink_gray=140)

            engine.set_brightness(128)
            engine.set_contrast(128)
            engine.set_threshold(50)  # threshold=50 treats gray=140 as white background -> 0 words
            engine.set_image_file(mid_img)
            assert engine.recognize() == 0
            words_low_thr = len(engine.extract_words())

            engine.set_threshold(220)  # threshold=220 treats gray=140 as dark ink -> words detected
            engine.set_image_file(mid_img)
            assert engine.recognize() == 0
            words_high_thr = len(engine.extract_words())
            assert words_low_thr == 0 and words_high_thr >= 10, (
                f"Isolated threshold control failed: thr=50 gave {words_low_thr} words, thr=220 gave {words_high_thr}"
            )

    assert engine._processed_gray is None
    assert len(engine._pages) == 0
    assert len(engine._words) == 0


# ---------------------------------------------------------------------------
# 11. R4: Multi-Page PDF Disk-Backed Spooling (0 Bytes Raw Bitmaps in RAM)
# ---------------------------------------------------------------------------
def test_r4_multipage_pdf_memory_spooling_and_cleanup():
    import fitz

    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "page.png")
        create_test_image(img_path)
        multi_pdf = os.path.join(tmpdir, "multi_6p.pdf")
        out_pdf = os.path.join(tmpdir, "restored_6p.pdf")

        doc = fitz.open()
        for _ in range(6):
            p = doc.new_page(width=595.28, height=841.89)
            p.insert_image(fitz.Rect(36, 36, 559, 336), filename=img_path)
        doc.save(multi_pdf)
        doc.close()

        spool_dir_ref = None
        with RoaScanEngine(language="en") as engine:
            engine.set_retain_images(True)
            engine.set_pdf_file(multi_pdf, dpi=300)
            assert engine.recognize() == 0

            pages = engine.extract_pages()
            assert len(pages) == 6
            # Verify 0 bytes of raw bitmaps retained in RAM across all page dicts
            retained_ram_bytes = sum(
                len(p.get("gray") or b"") + len(p.get("enhanced_gray") or b"")
                for p in pages
            )
            assert retained_ram_bytes == 0, f"Expected 0 raw bitmap bytes in RAM, got {retained_ram_bytes}"
            assert engine._gray is None
            assert engine._processed_gray is None
            assert engine._enhanced_gray is None

            spool_dir_ref = engine._spool_dir
            assert spool_dir_ref and os.path.isdir(spool_dir_ref)

            with RoaScanDocumentWriter() as writer:
                writer.configure_pdf(out_pdf)
                assert writer.write(engine) == 0

        # Verify spool directory was automatically deleted upon context exit / close()
        assert not os.path.exists(spool_dir_ref), "Spool directory was not cleaned up on engine.close()"
        assert os.path.exists(out_pdf)
        with fitz.open(out_pdf) as out_doc:
            assert len(out_doc) == 6
            assert "INV-987654" in out_doc[5].get_text("text")


if __name__ == "__main__":
    test_end_to_end_ocr_accuracy()
    test_spanish_invoice_diacritics_ruc_and_boxed_table()
    test_multipage_tiff_all_four_orientations_0_90_180_270()
    test_p0_input_overwrite_and_r1_temp_collision_protection()
    test_r2_strict_output_format_and_extension_contract()
    test_p1_nonexistent_output_dir_fails()
    test_p1_pdf_physical_dimensions_a4()
    test_p1_missing_onnx_model_fails_explicitly()
    test_p1_mcp_protocol_and_negative_validation()
    test_p1_buffer_bounds_and_isolated_controls()
    test_r4_multipage_pdf_memory_spooling_and_cleanup()
    print("[ALL 11 ROASCAN AUDIT & FUNCTIONAL TESTS PASSED]")
