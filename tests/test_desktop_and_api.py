"""
tests/test_desktop_and_api.py: Test suite for P1 (Bridge Contract & Python API),
P2 (CLI Subcommands), and P3 (Desktop Capture & Native Clipboard).
"""

import os
import sys
import tempfile
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont

current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(current_dir)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from roascan import RoaScanEngine, RoaScanResult, run_ocr
from roascan.desktop import (
    copy_to_clipboard,
    get_clipboard_text,
    capture_screen,
    capture_region_and_ocr,
)
from roascan.__main__ import main as cli_main


def _create_sample_image(path: str) -> str:
    im = Image.new("L", (800, 300), color=255)
    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        font = ImageFont.load_default()
    draw.text((50, 60), "ROASCAN DESKTOP BRIDGE 2026", fill=0, font=font)
    draw.text((50, 140), "ID: DESK-774411", fill=0, font=font)
    draw.text((50, 210), "STATUS: VERIFIED LOCAL OCR", fill=0, font=font)
    im.save(path, format="PNG", dpi=(300, 300))
    return path


def test_p1_run_ocr_bridge_contract_filepath():
    with tempfile.TemporaryDirectory() as tmpdir:
        img_p = os.path.join(tmpdir, "sample.png")
        _create_sample_image(img_p)

        res = run_ocr(img_p, language="en")
        assert isinstance(res, RoaScanResult)

        # Bridge contract field verifications
        assert "DESK-774411" in res.text
        assert "VERIFIED" in res.text
        assert len(res.words) >= 6
        assert len(res.pages) == 1
        assert res.page_count == 1
        assert len(res.confidences) == len(res.words)
        assert res.ocr_elapsed_ms > 0
        assert res.elapsed_ms >= res.ocr_elapsed_ms

        # Dictionary mapping access verification
        assert res["text"] == res.text
        assert res["words"] == res.words
        assert res["page_count"] == 1


def test_p1_run_ocr_with_pil_image_and_raw_bytes():
    with tempfile.TemporaryDirectory() as tmpdir:
        img_p = os.path.join(tmpdir, "sample.png")
        _create_sample_image(img_p)

        with Image.open(img_p) as pil_im:
            res_pil = run_ocr(pil_im, language="en")
            assert "DESK-774411" in res_pil.text

        with open(img_p, "rb") as f:
            raw_bytes = f.read()
        res_bytes = run_ocr(raw_bytes, language="en")
        assert "DESK-774411" in res_bytes.text

        # Test RoaScanEngine.run alias
        res_alias = RoaScanEngine.run(raw_bytes, language="en")
        assert "DESK-774411" in res_alias.text


def test_p1_result_save_markdown_and_clipboard():
    with tempfile.TemporaryDirectory() as tmpdir:
        img_p = os.path.join(tmpdir, "sample.png")
        out_md = os.path.join(tmpdir, "saved.md")
        _create_sample_image(img_p)

        res = run_ocr(img_p, language="en")
        saved_path = res.save_markdown(out_md)
        assert os.path.exists(saved_path)
        with open(saved_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "DESK-774411" in content

        # Clipboard copy from result
        ok = res.copy_to_clipboard()
        if ok:
            clip_val = get_clipboard_text()
            assert "DESK-774411" in clip_val


def test_p3_native_clipboard_read_write():
    test_msg = "RoaScan P3 Native Clipboard Verification 2026"
    copied = copy_to_clipboard(test_msg)
    assert copied is True
    read_back = get_clipboard_text()
    assert read_back == test_msg


def test_p3_capture_region_and_ocr_pipeline():
    with tempfile.TemporaryDirectory() as tmpdir:
        img_p = os.path.join(tmpdir, "sample.png")
        _create_sample_image(img_p)

        with Image.open(img_p) as sample_im:
            with patch("roascan.desktop.capture.ImageGrab.grab", return_value=sample_im):
                res = capture_region_and_ocr(
                    bbox=(0, 0, 800, 300),
                    language="en",
                    copy_clipboard=True,
                )
                assert "DESK-774411" in res.text
                clip_val = get_clipboard_text()
                assert "DESK-774411" in clip_val


def test_p2_cli_subcommands():
    with tempfile.TemporaryDirectory() as tmpdir:
        img_p = os.path.join(tmpdir, "sample.png")
        out_md = os.path.join(tmpdir, "cli_out.md")
        _create_sample_image(img_p)

        # 1. Test `roascan ocr <input> --out <out.md> --copy`
        rc = cli_main(["ocr", img_p, "--out", out_md, "--copy", "--lang", "en"])
        assert rc == 0
        assert os.path.exists(out_md)
        with open(out_md, "r", encoding="utf-8") as f:
            assert "DESK-774411" in f.read()
        assert "DESK-774411" in get_clipboard_text()


if __name__ == "__main__":
    test_p1_run_ocr_bridge_contract_filepath()
    test_p1_run_ocr_with_pil_image_and_raw_bytes()
    test_p1_result_save_markdown_and_clipboard()
    test_p3_native_clipboard_read_write()
    test_p3_capture_region_and_ocr_pipeline()
    test_p2_cli_subcommands()
    print("[ALL P1, P2, P3 TESTS PASSED]")
