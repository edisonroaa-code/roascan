"""
roascan.desktop.hotkey: Global hotkey manager for the RoaScan desktop companion.

Uses open-source `pynput` to listen for system-wide shortcut triggers in Windows.
100% offline, zero cloud telemetry, clean-room design.
"""

import logging
import os
import threading
from typing import Callable, Optional

logger = logging.getLogger("roascan.desktop.hotkey")

DEFAULT_HOTKEY = os.environ.get("ROASCAN_HOTKEY", "Ctrl+Shift+O")


def normalize_hotkey(hotkey_str: str) -> str:
    """Normalize a shortcut string like 'Ctrl+Shift+O' or '<ctrl>+<shift>+o'
    into the format expected by pynput.keyboard.GlobalHotKeys ('<ctrl>+<shift>+o').
    """
    cleaned = hotkey_str.replace(" ", "")
    parts = [p.strip().strip("<>").lower() for p in cleaned.split("+") if p.strip()]
    formatted = []
    for p in parts:
        if p in ("ctrl", "control", "shift", "alt", "cmd", "win", "super"):
            canonical = "ctrl" if p == "control" else ("cmd" if p == "super" else p)
            formatted.append(f"<{canonical}>")
        else:
            formatted.append(p)
    return "+".join(formatted)


class GlobalHotkeyManager:
    """Manages registering and listening for a global system shortcut via pynput."""

    def __init__(
        self,
        hotkey_str: str = DEFAULT_HOTKEY,
        on_trigger: Optional[Callable[[], None]] = None,
    ):
        self.raw_hotkey = hotkey_str
        self.normalized_hotkey = normalize_hotkey(hotkey_str)
        self.on_trigger = on_trigger
        self._listener = None
        self._is_running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> bool:
        """Start the global hotkey listener in a background thread."""
        with self._lock:
            if self._is_running:
                return True

            try:
                from pynput import keyboard
            except ImportError as exc:
                logger.warning(
                    f"Optional desktop dependency 'pynput' not installed: {exc}. "
                    "Global hotkey disabled. Install with: pip install \"roascan[desktop]\""
                )
                return False

            def _handler():
                logger.debug(f"Hotkey triggered: {self.raw_hotkey}")
                if self.on_trigger:
                    self.on_trigger()

            try:
                hotkey_map = {self.normalized_hotkey: _handler}
                self._listener = keyboard.GlobalHotKeys(hotkey_map)
                self._listener.daemon = True
                self._listener.start()
                self._is_running = True
                logger.info(f"Registered global hotkey: {self.raw_hotkey} ({self.normalized_hotkey})")
                return True
            except Exception as exc:
                logger.error(f"Failed to bind global hotkey {self.raw_hotkey}: {exc}")
                self._listener = None
                self._is_running = False
                return False

    def stop(self):
        """Stop the global hotkey listener cleanly."""
        with self._lock:
            if self._listener:
                try:
                    self._listener.stop()
                except Exception:
                    pass
                self._listener = None
            self._is_running = False
            logger.info("Global hotkey listener stopped.")
