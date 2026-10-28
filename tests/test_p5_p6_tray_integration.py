"""
Unit tests for Tray companion integration with Result Panel & Preferences (P5 & P6).

Runs 100% headless in CI without physical display or external services.
"""

from unittest.mock import MagicMock, patch
import pytest

from roascan.desktop.tray_app import RoaScanTrayApp
from roascan.api import RoaScanResult


@pytest.fixture
def mock_ocr_result():
    return RoaScanResult(
        text="FACTURA COMERCIAL #12345\nTOTAL: $500.00 USD",
        words=[
            {"text": "FACTURA", "confidence": 0.98},
            {"text": "COMERCIAL", "confidence": 0.95},
            {"text": "#12345", "confidence": 0.99},
            {"text": "TOTAL:", "confidence": 0.97},
            {"text": "$500.00", "confidence": 0.99},
            {"text": "USD", "confidence": 0.96},
        ],
        pages=[{"page": 0, "text": "FACTURA COMERCIAL"}],
        ocr_elapsed_ms=120.5,
    )


def test_tray_initialization_with_config():
    with patch("roascan.desktop.tray_app.load_config") as mock_cfg:
        mock_cfg.return_value = {
            "hotkey": "Ctrl+Shift+U",
            "ocr_lang": "en",
            "save_dir": "/custom/scans",
            "ui_lang": "en",
            "copy_on_success": False,
            "show_result_panel": True,
        }

        app = RoaScanTrayApp(enable_hotkey=False)
        assert app.hotkey_str == "Ctrl+Shift+U"
        assert app.language == "en"
        assert app.save_dir == "/custom/scans"
        assert app.ui_lang == "en"
        assert app.copy_on_success is False
        assert app.show_result_panel_enabled is True


def test_ocr_success_spawns_result_panel(mock_ocr_result):
    app = RoaScanTrayApp(
        enable_hotkey=False,
        show_result_panel=True,
        copy_on_success=True,
    )

    with patch("roascan.desktop.tray_app.capture_region_and_ocr", return_value=mock_ocr_result), \
         patch("roascan.desktop.tray_app.show_result_panel") as mock_show_panel, \
         patch.object(app, "notify") as mock_notify:

        res = app.run_region_ocr_action()
        assert res == mock_ocr_result
        assert app.last_result_text == mock_ocr_result.text

        # Verify notification and panel call
        mock_notify.assert_called_once()
        mock_show_panel.assert_called_once_with(
            text=mock_ocr_result.text,
            save_dir=app.save_dir,
            ui_lang=app.ui_lang,
            blocking=False,
        )


def test_ocr_disabled_panel_does_not_spawn_panel(mock_ocr_result):
    app = RoaScanTrayApp(
        enable_hotkey=False,
        show_result_panel=False,
        copy_on_success=True,
    )

    with patch("roascan.desktop.tray_app.capture_region_and_ocr", return_value=mock_ocr_result), \
         patch("roascan.desktop.tray_app.show_result_panel") as mock_show_panel:

        res = app.run_region_ocr_action()
        assert res == mock_ocr_result
        mock_show_panel.assert_not_called()


def test_open_last_result_action(mock_ocr_result):
    app = RoaScanTrayApp(enable_hotkey=False)

    # When no result has occurred yet
    with patch.object(app, "notify") as mock_notify, \
         patch("roascan.desktop.tray_app.show_result_panel") as mock_show_panel:
        app.open_last_result()
        mock_notify.assert_called_once()
        mock_show_panel.assert_not_called()

    # After a result is registered
    app.last_result_text = mock_ocr_result.text
    with patch("roascan.desktop.tray_app.show_result_panel") as mock_show_panel:
        app.open_last_result()
        mock_show_panel.assert_called_once_with(
            text=mock_ocr_result.text,
            save_dir=app.save_dir,
            ui_lang=app.ui_lang,
            blocking=False,
        )


def test_tray_set_language_runtime_switch():
    app = RoaScanTrayApp(enable_hotkey=False, ui_lang="es")
    with patch("roascan.desktop.tray_app.set_config_value") as mock_set_cfg:
        app.set_language("en")
        assert app.ui_lang == "en"
        mock_set_cfg.assert_called_once_with("ui_lang", "en")
