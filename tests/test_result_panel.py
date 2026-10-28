"""
Unit tests for RoaScan Result Panel (P5).

Runs 100% headless in CI without physical display.
"""

import datetime
from pathlib import Path
from queue import Empty, Queue
import threading
from unittest.mock import MagicMock, patch
import pytest

from roascan.desktop.result_panel import (
    generate_default_filename,
    save_text_to_file,
    show_result_panel,
    close_active_panel,
    _active_panel_lock,
)
import roascan.desktop.result_panel as rp


def test_generate_default_filename():
    dt = datetime.datetime(2026, 10, 28, 14, 30, 15)
    fn = generate_default_filename(timestamp=dt, ext=".md")
    assert fn == "roascan-20261028-143015.md"

    fn_txt = generate_default_filename(timestamp=dt, ext="txt")
    assert fn_txt == "roascan-20261028-143015.txt"


def test_save_text_to_file(tmp_path):
    dest = tmp_path / "deep" / "dir" / "result.md"
    content = "# Factura OCR\nTotal: $1,250.00 USD\n"
    saved = save_text_to_file(content, dest)

    assert saved == dest
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == content


def test_result_panel_window_logic():
    """Test ResultPanelWindow logic using mock Tkinter widgets to run purely headless."""
    with patch("tkinter.Tk") as mock_tk, \
         patch("tkinter.StringVar") as mock_str_var, \
         patch("tkinter.scrolledtext.ScrolledText") as mock_st, \
         patch("roascan.desktop.result_panel.copy_to_clipboard") as mock_copy:

        mock_root = MagicMock()
        mock_tk.return_value = mock_root

        mock_status_var = MagicMock()
        mock_str_var.return_value = mock_status_var

        mock_text_widget = MagicMock()
        mock_st.return_value = mock_text_widget
        mock_text_widget.get.return_value = "Texto corregido manualmente"

        from roascan.desktop.result_panel import ResultPanelWindow
        panel = ResultPanelWindow(text="Texto original", ui_lang="es")

        # Test retrieving current edited text
        assert panel.get_current_text() == "Texto corregido manualmente"

        # Test Copy button logic
        panel.copy_current_text()
        mock_copy.assert_called_once_with("Texto corregido manualmente")
        mock_status_var.set.assert_called()

        # Test content update (re-use / single instance)
        panel.update_content("Nuevo texto de segundo OCR")

        # Test close
        panel.close()
        mock_root.destroy.assert_called_once()


def test_show_result_panel_single_instance_management():
    close_active_panel()

    with patch("roascan.desktop.result_panel.ResultPanelWindow") as MockWindow:
        mock_instance = MagicMock()
        callbacks = Queue()
        stopped = threading.Event()
        updated = threading.Event()

        def event_loop():
            while not stopped.is_set():
                try:
                    callbacks.get(timeout=.1)()
                except Empty:
                    pass

        mock_instance.root.after.side_effect = lambda delay, callback: callbacks.put(callback)
        mock_instance.run.side_effect = event_loop
        mock_instance.close.side_effect = stopped.set
        mock_instance.update_content.side_effect = lambda text: updated.set()
        MockWindow.return_value = mock_instance

        # First call creates a new instance
        panel1 = show_result_panel("Primer OCR", blocking=False)
        assert panel1 == mock_instance
        MockWindow.assert_called_once()

        # Second call re-uses existing active panel
        panel2 = show_result_panel("Segundo OCR", blocking=False)
        assert panel2 == mock_instance
        assert updated.wait(1)
        # Should not create a second window instance
        assert MockWindow.call_count == 1
        mock_instance.update_content.assert_called_once_with("Segundo OCR")

        # Close active panel releases singleton
        close_active_panel()
        with _active_panel_lock:
            assert rp._active_panel_instance is None


def test_result_panel_startup_failure_is_reported_and_releases_singleton():
    close_active_panel()
    with patch("roascan.desktop.result_panel.ResultPanelWindow", side_effect=RuntimeError("no display")):
        with pytest.raises(RuntimeError, match="no display"):
            show_result_panel("OCR", blocking=False)
    with _active_panel_lock:
        assert rp._active_panel_instance is None
