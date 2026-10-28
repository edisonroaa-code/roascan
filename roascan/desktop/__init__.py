"""
roascan.desktop: Desktop capture, clipboard, result panel, and tray companion for RoaScan.

Provides:
  - `capture_screen`: Screen capture via Pillow.
  - `select_region_interactive`: Crosshair rectangle overlay via Tkinter.
  - `capture_region_and_ocr`: Full pipeline (region -> local OCR -> clipboard).
  - `copy_to_clipboard`, `get_clipboard_text`: Native Win32/Tkinter clipboard helpers.
  - `GlobalHotkeyManager`, `DEFAULT_HOTKEY`: System-wide shortcut listener via pynput.
  - `RoaScanTrayApp`: System tray background companion via pystray.
  - `show_result_panel`, `close_active_panel`: Interactive OCR text viewer/editor.
  - `load_config`, `save_config`, `get_config_path`: Platform user preferences.
  - `t`, `set_ui_language`, `get_ui_language`: UI localization (EN/ES).

100% offline, zero cloud vendor telemetry, zero proprietary code.
"""

from .clipboard import copy_to_clipboard, get_clipboard_text
from .capture import capture_screen, capture_region_and_ocr, select_region_interactive
from .hotkey import GlobalHotkeyManager, DEFAULT_HOTKEY, normalize_hotkey
from .tray_app import RoaScanTrayApp, create_default_tray_icon
from .config import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
    get_config_path,
    set_config_value,
)
from .i18n import t, set_ui_language, get_ui_language
from .result_panel import (
    show_result_panel,
    close_active_panel,
    generate_default_filename,
    save_text_to_file,
)

__all__ = [
    "copy_to_clipboard",
    "get_clipboard_text",
    "capture_screen",
    "capture_region_and_ocr",
    "select_region_interactive",
    "GlobalHotkeyManager",
    "DEFAULT_HOTKEY",
    "normalize_hotkey",
    "RoaScanTrayApp",
    "create_default_tray_icon",
    "DEFAULT_CONFIG",
    "load_config",
    "save_config",
    "get_config_path",
    "set_config_value",
    "t",
    "set_ui_language",
    "get_ui_language",
    "show_result_panel",
    "close_active_panel",
    "generate_default_filename",
    "save_text_to_file",
]
