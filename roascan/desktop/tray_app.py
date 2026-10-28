"""
roascan.desktop.tray_app: System Tray companion application for RoaScan.

Provides a persistent background tray icon with a global shortcut that triggers:
  Region crop -> Local C++17/ONNX OCR -> Clipboard copy -> Result Panel

100% offline, zero cloud vendor telemetry, clean-room architecture.
"""

import argparse
import logging
import os
import sys
import threading
from typing import List, Optional
from PIL import Image, ImageDraw

from .capture import capture_region_and_ocr
from .config import load_config, set_config_value, DEFAULT_CONFIG
from .hotkey import DEFAULT_HOTKEY, GlobalHotkeyManager
from .i18n import t, set_ui_language, get_ui_language
from .result_panel import show_result_panel, close_active_panel

logger = logging.getLogger("roascan.desktop.tray")


def create_default_tray_icon() -> Image.Image:
    """Generate a clean 64x64 RGBA RoaScan tray icon in memory without external assets."""
    im = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    # Dark rounded badge background
    draw.rounded_rectangle([2, 2, 62, 62], radius=12, fill=(24, 28, 36, 255), outline=(0, 255, 204, 255), width=3)

    # Vibrant teal 'R' glyph
    # Vertical spine
    draw.rectangle([18, 14, 25, 50], fill=(0, 255, 204, 255))
    # Top loop
    draw.rounded_rectangle([22, 14, 46, 34], radius=6, outline=(0, 255, 204, 255), width=6)
    # Leg
    draw.line([(32, 32), (46, 50)], fill=(0, 255, 204, 255), width=6)

    return im


class RoaScanTrayApp:
    """System tray companion for RoaScan with global shortcut and result viewer integration."""

    def __init__(
        self,
        hotkey: Optional[str] = None,
        enable_hotkey: bool = True,
        language: Optional[str] = None,
        dpi: int = 300,
        save_dir: Optional[str] = None,
        ui_lang: Optional[str] = None,
        copy_on_success: Optional[bool] = None,
        show_result_panel: Optional[bool] = None,
    ):
        cfg = load_config()

        self.hotkey_str = hotkey if hotkey is not None else cfg.get("hotkey", DEFAULT_HOTKEY)
        self.enable_hotkey = enable_hotkey
        self.language = language if language is not None else cfg.get("ocr_lang", "es")
        self.dpi = dpi
        self.save_dir = save_dir if save_dir is not None else cfg.get("save_dir")
        self.ui_lang = ui_lang if ui_lang is not None else cfg.get("ui_lang", "es")
        self.copy_on_success = copy_on_success if copy_on_success is not None else cfg.get("copy_on_success", True)
        self.show_result_panel_enabled = show_result_panel if show_result_panel is not None else cfg.get("show_result_panel", True)

        set_ui_language(self.ui_lang)

        self._icon = None
        self._capture_lock = threading.Lock()
        self._hotkey_manager = None
        self.last_result_text: Optional[str] = None

        if self.enable_hotkey:
            self._hotkey_manager = GlobalHotkeyManager(
                hotkey_str=self.hotkey_str,
                on_trigger=self._on_hotkey_triggered,
            )

    def _on_hotkey_triggered(self):
        """Callback invoked from the hotkey thread when the shortcut is pressed."""
        logger.info(f"Hotkey '{self.hotkey_str}' triggered.")
        self._spawn_action_thread()

    def _spawn_action_thread(self):
        """Spawn OCR capture in a dedicated worker thread so the tray message loop never blocks."""
        t_worker = threading.Thread(target=self.run_region_ocr_action, name="RoaScanCaptureThread")
        t_worker.daemon = True
        t_worker.start()

    def notify(self, message: str, title: Optional[str] = None):
        """Send notification via system tray if supported."""
        if title is None:
            title = t("tray.notification_title", lang=self.ui_lang)
        if self._icon and hasattr(self._icon, "notify"):
            try:
                self._icon.notify(message, title)
            except Exception as exc:
                logger.debug(f"Tray notification error: {exc}")

    def set_language(self, lang: str):
        """Change UI language at runtime, update config file, and rebuild menu."""
        self.ui_lang = lang
        set_ui_language(lang)
        try:
            set_config_value("ui_lang", lang)
        except Exception as exc:
            logger.debug(f"Failed to persist ui_lang: {exc}")

        if self._icon is not None:
            try:
                self._icon.menu = self._build_menu()
            except Exception as exc:
                logger.debug(f"Failed to update tray menu on lang change: {exc}")

    def open_last_result(self):
        """Open or focus the result panel with the last recognized OCR text."""
        if self.last_result_text is not None:
            show_result_panel(
                text=self.last_result_text,
                save_dir=self.save_dir,
                ui_lang=self.ui_lang,
                blocking=False,
            )
        else:
            self.notify(t("tray.no_last_result", lang=self.ui_lang))

    def run_region_ocr_action(self):
        """Main region capture and OCR action. Protected by anti-reentrancy lock."""
        acquired = self._capture_lock.acquire(blocking=False)
        if not acquired:
            logger.warning("Capture already in progress. Ignoring concurrent trigger.")
            return None

        try:
            logger.info(f"Starting interactive region OCR (lang={self.language}, dpi={self.dpi})...")
            res = capture_region_and_ocr(
                interactive=True,
                copy_clipboard=self.copy_on_success,
                language=self.language,
                dpi=self.dpi,
            )

            if res and res.text:
                self.last_result_text = res.text
                n_words = len(res.words)
                logger.info(f"OCR completed: {n_words} words in {res.ocr_elapsed_ms} ms.")

                if self.copy_on_success:
                    self.notify(t("tray.copied_notification", count=n_words, lang=self.ui_lang))

                if self.show_result_panel_enabled:
                    show_result_panel(
                        text=res.text,
                        save_dir=self.save_dir,
                        ui_lang=self.ui_lang,
                        blocking=False,
                    )
                return res
            else:
                logger.debug("Region selection cancelled by user or empty result.")
                if res and self.show_result_panel_enabled:
                    show_result_panel(
                        text="",
                        save_dir=self.save_dir,
                        ui_lang=self.ui_lang,
                        blocking=False,
                    )
                return res
        except Exception as exc:
            logger.error(f"RoaScan capture action failed: {exc}", exc_info=True)
            self.notify(t("tray.error_notification", error=str(exc), lang=self.ui_lang))
            return None
        finally:
            self._capture_lock.release()

    def _build_menu(self):
        try:
            import pystray
        except ImportError as exc:
            raise RuntimeError(
                f"Required dependency 'pystray' not installed: {exc}. "
                "Install with: pip install \"roascan[desktop]\""
            )

        hotkey_label = f" ({self.hotkey_str})" if self.enable_hotkey else ""

        lang_menu = pystray.Menu(
            pystray.MenuItem(
                t("tray.lang_es", lang=self.ui_lang),
                lambda icon, item: self.set_language("es"),
                checked=lambda item: self.ui_lang == "es",
            ),
            pystray.MenuItem(
                t("tray.lang_en", lang=self.ui_lang),
                lambda icon, item: self.set_language("en"),
                checked=lambda item: self.ui_lang == "en",
            ),
        )

        return pystray.Menu(
            pystray.MenuItem(
                f"{t('tray.ocr_region', lang=self.ui_lang)}{hotkey_label}",
                lambda icon, item: self._spawn_action_thread(),
                default=True,
            ),
            pystray.MenuItem(
                t("tray.open_last_result", lang=self.ui_lang),
                lambda icon, item: self.open_last_result(),
            ),
            pystray.MenuItem(
                t("tray.language", lang=self.ui_lang),
                lang_menu,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                t("tray.exit", lang=self.ui_lang),
                lambda icon, item: self.stop(),
            ),
        )

    def run(self):
        """Start the system tray companion and block until exit."""
        try:
            import pystray
        except ImportError as exc:
            print(
                f"[ERROR] Optional desktop dependency 'pystray' is not installed: {exc}\n"
                "To enable the system tray companion, install with:\n"
                "    pip install \"roascan[desktop]\"",
                file=sys.stderr,
            )
            return 1

        if self._hotkey_manager and self.enable_hotkey:
            self._hotkey_manager.start()

        icon_img = create_default_tray_icon()
        menu = self._build_menu()

        self._icon = pystray.Icon(
            name="roascan",
            icon=icon_img,
            title=f"RoaScan OCR ({self.hotkey_str})",
            menu=menu,
        )

        logger.info(f"RoaScan tray companion ready (hotkey={self.hotkey_str}).")
        msg = t("tray.running_bg", lang=self.ui_lang, hotkey=self.hotkey_str)
        print(f"[RoaScan] {msg}")

        try:
            self._icon.run()
        finally:
            self.stop()
        return 0

    def stop(self):
        """Shut down the tray companion and release the global hotkey listener cleanly."""
        if self._hotkey_manager:
            self._hotkey_manager.stop()
            self._hotkey_manager = None
        close_active_panel()
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
        logger.info("RoaScan tray companion stopped cleanly.")


def main(argv: Optional[List[str]] = None) -> int:
    cfg = load_config()

    parser = argparse.ArgumentParser(
        prog="roascan-tray",
        description="RoaScan System Tray Companion: local offline OCR via system shortcut and result panel.",
    )
    parser.add_argument(
        "--hotkey",
        default=None,
        help=f"Global hotkey combination (default from config: '{cfg.get('hotkey', DEFAULT_HOTKEY)}')",
    )
    parser.add_argument(
        "--no-hotkey",
        action="store_true",
        help="Disable global shortcut (tray menu only)",
    )
    parser.add_argument(
        "-l",
        "--lang",
        default=None,
        choices=["es", "en", "latin"],
        help=f"Recognition language: es, en, latin (default from config: '{cfg.get('ocr_lang', 'es')}')",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Target DPI for PDF/image scaling (default: 300)",
    )
    parser.add_argument(
        "--ui-lang",
        choices=["es", "en"],
        default=None,
        help=f"UI localization language: es, en (default from config: '{cfg.get('ui_lang', 'es')}')",
    )
    parser.add_argument(
        "--save-dir",
        default=None,
        help=f"Default directory to save OCR exports (default from config: '{cfg.get('save_dir')}')",
    )
    parser.add_argument(
        "--panel",
        action="store_true",
        default=None,
        help="Always display result panel on OCR completion",
    )
    parser.add_argument(
        "--no-panel",
        action="store_true",
        default=None,
        help="Do not display result panel on OCR completion",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed debug logging to stderr",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    show_panel = None
    if args.no_panel:
        show_panel = False
    elif args.panel:
        show_panel = True

    app = RoaScanTrayApp(
        hotkey=args.hotkey,
        enable_hotkey=not args.no_hotkey,
        language=args.lang,
        dpi=args.dpi,
        save_dir=args.save_dir,
        ui_lang=args.ui_lang,
        show_result_panel=show_panel,
    )
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
