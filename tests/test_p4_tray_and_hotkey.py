"""
tests/test_p4_tray_and_hotkey.py: Mocked unit tests for RoaScan P4 Desktop Tray & Hotkey Companion.

Tests:
  1. test_tray_menu_actions_call_capture (verifies run_region_ocr_action calls capture_region_and_ocr)
  2. test_hotkey_handler_invokes_same_action (verifies hotkey triggers region OCR)
  3. test_lock_prevents_reentrant_capture (verifies lock blocks concurrent captures)
  4. test_ocr_failure_does_not_crash_tray_loop (verifies exceptions are caught and logged gracefully)
  5. test_hotkey_normalization (verifies pynput shortcut string formatting)
  6. test_module_import_without_desktop_extra (verifies core roascan works without desktop extra)

All tests are 100% mocked; no physical display window or OS global hotkey is touched.
"""

import os
import sys
import threading
from unittest.mock import MagicMock, patch

current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(current_dir)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from roascan.api import RoaScanResult
from roascan.desktop.hotkey import DEFAULT_HOTKEY, GlobalHotkeyManager, normalize_hotkey
from roascan.desktop.tray_app import RoaScanTrayApp, create_default_tray_icon


def test_hotkey_normalization():
    assert normalize_hotkey("Ctrl+Shift+O") == "<ctrl>+<shift>+o"
    assert normalize_hotkey("ctrl + alt + o") == "<ctrl>+<alt>+o"
    assert normalize_hotkey("<ctrl>+<shift>+o") == "<ctrl>+<shift>+o"
    assert normalize_hotkey("Cmd+Shift+4") == "<cmd>+<shift>+4"
    assert normalize_hotkey("Control+Shift+O") == "<ctrl>+<shift>+o"


def test_tray_menu_actions_call_capture():
    mock_res = RoaScanResult(
        text="MOCKED TRAY OCR TEXT",
        words=[{"text": "MOCKED", "confidence": 0.99}],
        page_count=1,
    )

    app = RoaScanTrayApp(enable_hotkey=False, language="es", dpi=300)
    app.notify = MagicMock()

    with patch("roascan.desktop.tray_app.capture_region_and_ocr", return_value=mock_res) as mock_capture:
        result = app.run_region_ocr_action()

        assert mock_capture.called
        assert mock_capture.call_args[1]["interactive"] is True
        assert mock_capture.call_args[1]["copy_clipboard"] is True
        assert mock_capture.call_args[1]["language"] == "es"
        assert result is not None
        assert result.text == "MOCKED TRAY OCR TEXT"
        assert app.notify.called


def test_hotkey_handler_invokes_same_action():
    app = RoaScanTrayApp(enable_hotkey=False)
    app.run_region_ocr_action = MagicMock()

    # Trigger hotkey callback directly
    app._on_hotkey_triggered()
    # Wait briefly for worker thread spawned by _spawn_action_thread
    import time
    time.sleep(0.05)
    assert app.run_region_ocr_action.called


def test_lock_prevents_reentrant_capture():
    app = RoaScanTrayApp(enable_hotkey=False)

    # Acquire lock externally to simulate a capture already in progress
    acquired_external = app._capture_lock.acquire(blocking=False)
    assert acquired_external is True

    try:
        with patch("roascan.desktop.tray_app.capture_region_and_ocr") as mock_capture:
            # Second call must immediately return None without executing capture
            res = app.run_region_ocr_action()
            assert res is None
            assert not mock_capture.called
    finally:
        app._capture_lock.release()


def test_ocr_failure_does_not_crash_tray_loop():
    app = RoaScanTrayApp(enable_hotkey=False)
    app.notify = MagicMock()

    # Simulate an unexpected hardware or driver exception during capture
    with patch(
        "roascan.desktop.tray_app.capture_region_and_ocr",
        side_effect=RuntimeError("Simulated OCR engine failure"),
    ):
        # Must not raise an exception; should catch, log, and notify
        res = app.run_region_ocr_action()
        assert res is None
        assert app.notify.called
        assert "Fallo en captura OCR" in app.notify.call_args[0][0]


def test_tray_icon_generation():
    im = create_default_tray_icon()
    assert im.size == (64, 64)
    assert im.mode == "RGBA"


def test_module_import_without_desktop_extra():
    # Verify core RoaScan functions run even if pystray/pynput are mocked as unavailable
    import builtins
    orig_import = builtins.__import__

    def mock_missing_desktop_import(name, *args, **kwargs):
        if name in ("pystray", "pynput"):
            raise ImportError(f"No module named '{name}'")
        return orig_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_missing_desktop_import):
        import roascan
        from roascan import RoaScanEngine, RoaScanResult, run_ocr
        assert hasattr(roascan, "run_ocr")
        assert hasattr(RoaScanEngine, "run")

        # Hotkey manager should report False when pynput is missing
        mgr = GlobalHotkeyManager("Ctrl+Shift+O")
        assert mgr.start() is False


if __name__ == "__main__":
    test_hotkey_normalization()
    test_tray_menu_actions_call_capture()
    test_hotkey_handler_invokes_same_action()
    test_lock_prevents_reentrant_capture()
    test_ocr_failure_does_not_crash_tray_loop()
    test_tray_icon_generation()
    test_module_import_without_desktop_extra()
    print("[ALL P4 TRAY & HOTKEY TESTS PASSED]")
