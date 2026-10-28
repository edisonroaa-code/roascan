"""
roascan.desktop.result_panel: Interactive result inspection and export panel for RoaScan.

Provides a clean Tkinter window displaying recognized OCR text with:
- Editable text area (allows corrections before copying/saving).
- Copy button (copies current edited text to clipboard).
- Save button (exports text to .md or .txt in the configured save directory).
- Close button / Escape key shortcut.
- Non-blocking execution with single-instance management.

Clean-room OSS implementation; 100% offline, zero cloud vendor telemetry.
"""

import datetime
import gc
import logging
import os
from pathlib import Path
from queue import Empty, Queue
import threading
from typing import Optional, Union

from .clipboard import copy_to_clipboard
from .config import load_config
from .i18n import t

logger = logging.getLogger("roascan.desktop.result_panel")

_active_panel_lock = threading.RLock()
_active_panel_instance = None
_active_panel_session = None


class _PanelSession:
    """Own one Tk window and a queue consumed exclusively by its UI thread."""

    def __init__(self):
        self.commands = Queue()
        self.ready = threading.Event()
        self.closed = threading.Event()
        self.panel = None
        self.error = None
        self.thread = None


def generate_default_filename(timestamp: Optional[datetime.datetime] = None, ext: str = ".md") -> str:
    """Generate timestamped default filename: roascan-YYYYMMDD-HHMMSS.md."""
    if timestamp is None:
        timestamp = datetime.datetime.now()
    if not ext.startswith("."):
        ext = "." + ext
    return f"roascan-{timestamp.strftime('%Y%m%d-%H%M%S')}{ext}"


def save_text_to_file(text: str, file_path: Union[str, Path]) -> Path:
    """Safely write text to file with UTF-8 encoding, creating directories as needed."""
    target = Path(file_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(text)
    logger.info(f"Result text successfully saved to {target} ({len(text)} characters).")
    return target


class ResultPanelWindow:
    """Tkinter-based result viewer and editor window."""

    def __init__(
        self,
        text: str,
        save_dir: Optional[str] = None,
        ui_lang: Optional[str] = None,
        on_close: Optional[callable] = None,
    ):
        self.text_content = text or ""
        self.save_dir = Path(save_dir).expanduser() if save_dir else Path.home() / "Documents" / "RoaScan"
        self.ui_lang = ui_lang
        self.on_close_cb = on_close

        import tkinter as tk
        from tkinter import ttk, scrolledtext, filedialog

        self.tk = tk
        self.ttk = ttk
        self.scrolledtext = scrolledtext
        self.filedialog = filedialog

        self.root = tk.Tk()
        self.root.title(t("panel.title", lang=self.ui_lang))
        self.root.geometry("640x480")
        self.root.minsize(400, 300)

        # Style configuration
        self.root.configure(bg="#F3F4F6")

        self._build_ui()
        self._set_text(self.text_content)

        # Bindings
        self.root.bind("<Escape>", lambda event: self.close())
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self):
        # Header / Status bar
        header_frame = self.tk.Frame(self.root, bg="#F3F4F6", padx=12, pady=8)
        header_frame.pack(side=self.tk.TOP, fill=self.tk.X)

        self.status_var = self.tk.StringVar(master=self.root, value=t("panel.status_ready", lang=self.ui_lang))
        self.status_label = self.tk.Label(
            header_frame,
            textvariable=self.status_var,
            font=("Segoe UI", 9),
            fg="#4B5563",
            bg="#F3F4F6",
            anchor="w",
        )
        self.status_label.pack(side=self.tk.LEFT, fill=self.tk.X, expand=True)

        # Main Text Area
        text_frame = self.tk.Frame(self.root, padx=12, pady=4, bg="#F3F4F6")
        text_frame.pack(side=self.tk.TOP, fill=self.tk.BOTH, expand=True)

        self.text_widget = self.scrolledtext.ScrolledText(
            text_frame,
            wrap=self.tk.WORD,
            font=("Consolas", 10),
            bg="#FFFFFF",
            fg="#111827",
            insertbackground="#00BFA5",
            relief=self.tk.SOLID,
            borderwidth=1,
            padx=8,
            pady=8,
        )
        self.text_widget.pack(fill=self.tk.BOTH, expand=True)

        # Bottom Button Bar
        button_bar = self.tk.Frame(self.root, bg="#F3F4F6", padx=12, pady=10)
        button_bar.pack(side=self.tk.BOTTOM, fill=self.tk.X)

        # Action buttons
        self.copy_btn = self.tk.Button(
            button_bar,
            text=t("panel.copy_btn", lang=self.ui_lang),
            command=self.copy_current_text,
            font=("Segoe UI", 9, "bold"),
            bg="#00BFA5",
            fg="#FFFFFF",
            activebackground="#008E7A",
            activeforeground="#FFFFFF",
            relief=self.tk.FLAT,
            padx=14,
            pady=4,
            cursor="hand2",
        )
        self.copy_btn.pack(side=self.tk.LEFT, padx=(0, 8))

        self.save_btn = self.tk.Button(
            button_bar,
            text=t("panel.save_btn", lang=self.ui_lang),
            command=self.save_text,
            font=("Segoe UI", 9),
            bg="#E5E7EB",
            fg="#1F2937",
            activebackground="#D1D5DB",
            relief=self.tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
        )
        self.save_btn.pack(side=self.tk.LEFT, padx=(0, 8))

        self.close_btn = self.tk.Button(
            button_bar,
            text=t("panel.close_btn", lang=self.ui_lang),
            command=self.close,
            font=("Segoe UI", 9),
            bg="#E5E7EB",
            fg="#4B5563",
            activebackground="#D1D5DB",
            relief=self.tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
        )
        self.close_btn.pack(side=self.tk.RIGHT)

    def _set_text(self, text: str):
        self.text_widget.delete("1.0", self.tk.END)
        if text.strip():
            self.text_widget.insert(self.tk.END, text)
        else:
            self.text_widget.insert(self.tk.END, t("panel.empty_result", lang=self.ui_lang))
            self.text_widget.tag_add("placeholder", "1.0", self.tk.END)
            self.text_widget.tag_config("placeholder", foreground="#9CA3AF")

    def update_content(self, text: str):
        """Update existing open window with fresh OCR text and bring to front."""
        session = _active_panel_session
        if session is not None and session.panel is self and threading.current_thread() is not session.thread:
            session.commands.put(("update", text))
            return
        self._set_text(text)
        self.status_var.set(t("panel.status_ready", lang=self.ui_lang))
        self.bring_to_front()

    def get_current_text(self) -> str:
        """Return the current content of the editable text widget."""
        return self.text_widget.get("1.0", f"{self.tk.END}-1c")

    def copy_current_text(self):
        """Copy the current edited text to the system clipboard."""
        text = self.get_current_text()
        copy_to_clipboard(text)
        self.status_var.set(t("panel.status_copied", lang=self.ui_lang))
        logger.info(f"Copied {len(text)} characters from result panel to clipboard.")

    def save_text(self):
        """Prompt user for file location and save the current edited text."""
        text = self.get_current_text()
        default_file = generate_default_filename(ext=".md")
        self.save_dir.mkdir(parents=True, exist_ok=True)

        file_path = self.filedialog.asksaveasfilename(
            parent=self.root,
            title=t("panel.save_dialog_title", lang=self.ui_lang),
            initialdir=str(self.save_dir),
            initialfile=default_file,
            filetypes=[
                (t("panel.file_filter_md", lang=self.ui_lang), "*.md"),
                (t("panel.file_filter_txt", lang=self.ui_lang), "*.txt"),
                (t("panel.file_filter_all", lang=self.ui_lang), "*.*"),
            ],
            defaultextension=".md",
        )

        if file_path:
            try:
                saved = save_text_to_file(text, file_path)
                self.status_var.set(t("panel.status_saved", lang=self.ui_lang, path=saved.name))
            except Exception as exc:
                self.status_var.set(t("error.save_failed", lang=self.ui_lang, error=str(exc)))

    def bring_to_front(self):
        """Bring window to foreground and set focus."""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after_idle(self.root.attributes, "-topmost", False)
            self.text_widget.focus_set()
        except Exception as exc:
            logger.debug(f"bring_to_front: {exc}")

    def close(self):
        """Destroy window and invoke close callback."""
        global _active_panel_instance
        session = _active_panel_session
        if session is not None and session.panel is self and threading.current_thread() is not session.thread:
            close_active_panel()
            return
        with _active_panel_lock:
            if _active_panel_instance is self:
                _active_panel_instance = None

        if self.on_close_cb:
            try:
                self.on_close_cb()
            except Exception:
                pass

        try:
            self.root.destroy()
        except Exception:
            pass
        finally:
            # Release Tcl objects on their owning thread, even when callers keep
            # the returned panel handle after the window has closed.
            for name in (
                "status_var", "status_label", "text_widget", "copy_btn",
                "save_btn", "close_btn", "root",
            ):
                setattr(self, name, None)

    def run(self):
        """Run the Tkinter event loop."""
        self.bring_to_front()
        self.root.mainloop()


def _run_panel_session(session, text, save_dir, ui_lang):
    global _active_panel_instance, _active_panel_session
    try:
        panel = ResultPanelWindow(text=text, save_dir=save_dir, ui_lang=ui_lang)
        session.panel = panel
        with _active_panel_lock:
            _active_panel_instance = panel

        def process_commands():
            try:
                while True:
                    command, value = session.commands.get_nowait()
                    if command == "close":
                        panel.close()
                        return
                    panel.update_content(value)
            except Empty:
                pass
            if panel.root is not None:
                panel.root.after(25, process_commands)

        panel.root.after(0, process_commands)
        session.ready.set()
        panel.run()
    except Exception as exc:
        # Store text rather than a traceback retaining Tcl objects across threads.
        session.error = str(exc)
        logger.error("Result panel failed: %s", exc)
    finally:
        if session.panel is not None and session.panel.root is not None:
            session.panel.close()
        # Tk widgets can form Python reference cycles. Collect them before their
        # owning thread exits, so Tcl is never finalized later by another thread.
        gc.collect()
        with _active_panel_lock:
            if _active_panel_session is session:
                _active_panel_instance = None
                _active_panel_session = None
        session.ready.set()
        session.closed.set()


def show_result_panel(
    text: str,
    save_dir: Optional[str] = None,
    ui_lang: Optional[str] = None,
    blocking: bool = False,
) -> Optional[ResultPanelWindow]:
    """
    Display the OCR result panel.
    If a panel is already open, updates its content and focuses it (single-instance).
    If blocking=True, blocks until closed (useful for CLI/scripts).
    All Tk operations run on one dedicated UI thread. Other threads enqueue
    updates; blocking=True waits until the window has closed.
    """
    global _active_panel_session

    with _active_panel_lock:
        session = _active_panel_session
        if session is None or session.closed.is_set() or (
            session.panel is not None and session.panel.root is None
        ):
            session = _PanelSession()
            _active_panel_session = session
            session.thread = threading.Thread(
                target=_run_panel_session,
                args=(session, text, save_dir, ui_lang),
                name="RoaScanResultPanelThread",
                daemon=True,
            )
            session.thread.start()
        else:
            session.commands.put(("update", text))

    if not session.ready.wait(5):
        session.commands.put(("close", None))
        raise RuntimeError("Result panel did not initialize within 5 seconds.")
    if session.error:
        raise RuntimeError(f"Unable to open result panel: {session.error}")
    if blocking and threading.current_thread() is not session.thread:
        session.closed.wait()
    return session.panel


def close_active_panel():
    """Close any currently open result panel window."""
    with _active_panel_lock:
        session = _active_panel_session
        if session is not None:
            session.commands.put(("close", None))
    if session is not None and threading.current_thread() is not session.thread:
        if not session.closed.wait(5):
            raise RuntimeError("Result panel did not close within 5 seconds.")
