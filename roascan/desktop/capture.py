"""
roascan.desktop.capture: Region & Screen Capture Controller for RoaScan.

Provides:
  1. `capture_screen`: Screen capture using standard Pillow with fallback handling.
  2. `select_region_interactive`: Lightweight crosshair selection overlay via Tkinter.
  3. `capture_region_and_ocr`: End-to-end capture -> OCR -> clipboard pipeline.

100% offline, zero cloud vendor telemetry, zero proprietary dependencies.
"""

from typing import Any, Dict, Optional, Tuple
from PIL import Image, ImageGrab

from ..api import RoaScanResult, run_ocr
from .clipboard import copy_to_clipboard


def capture_screen(
    bbox: Optional[Tuple[int, int, int, int]] = None,
) -> Image.Image:
    """Capture full screen or specific bounding box (left, top, right, bottom).

    Args:
        bbox: Optional (left, top, right, bottom) pixel coordinates.

    Returns:
        PIL.Image in RGB or RGBA mode.
    """
    try:
        im = ImageGrab.grab(bbox=bbox, all_screens=True)
        if im is not None:
            return im
    except Exception as exc:
        raise RuntimeError(
            f"Screen capture failed: display cannot be captured ({exc}). "
            "Ensure desktop is unlocked and display server is active."
        ) from exc
    raise RuntimeError("Screen grab returned empty image.")


def select_region_interactive(
    prompt: str = "RoaScan — Arrastre para seleccionar región (Esc o clic derecho para cancelar)",
) -> Optional[Tuple[int, int, int, int]]:
    """Open a temporary fullscreen translucent overlay to let the user select a region
    with mouse drag. Returns (left, top, right, bottom) or None if cancelled.
    """
    try:
        import tkinter as tk
    except ImportError:
        raise RuntimeError("Tkinter is required for interactive region selection.")

    root = tk.Tk()
    root.title(prompt)
    root.attributes("-fullscreen", True)
    root.attributes("-alpha", 0.3)
    root.config(cursor="cross")

    selected_bbox: Optional[Tuple[int, int, int, int]] = None
    start_x = 0
    start_y = 0
    rect_id = None
    label_id = None

    canvas = tk.Canvas(root, cursor="cross", bg="#1e1e1e", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    def on_mouse_down(event):
        nonlocal start_x, start_y, rect_id, label_id
        start_x = event.x_root
        start_y = event.y_root
        if rect_id:
            canvas.delete(rect_id)
        if label_id:
            canvas.delete(label_id)
        rect_id = canvas.create_rectangle(
            start_x, start_y, start_x, start_y,
            outline="#00ffcc", width=2, fill="#00ffff"
        )
        label_id = canvas.create_text(
            start_x + 5, start_y - 12,
            text="0 x 0", fill="#ffffff", font=("Segoe UI", 10, "bold"), anchor="nw"
        )

    def on_mouse_drag(event):
        nonlocal rect_id, label_id
        cur_x = event.x_root
        cur_y = event.y_root
        w = abs(cur_x - start_x)
        h = abs(cur_y - start_y)
        canvas.coords(rect_id, start_x, start_y, cur_x, cur_y)
        x0 = min(start_x, cur_x)
        y0 = min(start_y, cur_y)
        canvas.coords(label_id, x0 + 5, y0 - 16 if y0 > 20 else y0 + 5)
        canvas.itemconfig(label_id, text=f"{w} x {h}")

    def on_mouse_up(event):
        nonlocal selected_bbox
        end_x = event.x_root
        end_y = event.y_root
        x1, x2 = sorted([start_x, end_x])
        y1, y2 = sorted([start_y, end_y])
        if (x2 - x1) >= 8 and (y2 - y1) >= 8:
            selected_bbox = (x1, y1, x2, y2)
        root.destroy()

    def on_cancel(event=None):
        nonlocal selected_bbox
        selected_bbox = None
        root.destroy()

    canvas.bind("<Button-1>", on_mouse_down)
    canvas.bind("<B1-Motion>", on_mouse_drag)
    canvas.bind("<ButtonRelease-1>", on_mouse_up)
    canvas.bind("<Button-3>", on_cancel)
    root.bind("<Escape>", on_cancel)

    # Bring overlay to top
    root.lift()
    root.attributes("-topmost", True)
    root.focus_force()
    root.mainloop()

    return selected_bbox


def capture_region_and_ocr(
    bbox: Optional[Tuple[int, int, int, int]] = None,
    interactive: bool = False,
    copy_clipboard: bool = True,
    language: str = "es",
    dpi: int = 300,
    options: Optional[Dict[str, Any]] = None,
) -> RoaScanResult:
    """End-to-end screen capture -> local OCR -> clipboard pipeline.

    Args:
        bbox: Optional (x1, y1, x2, y2) bounding box.
        interactive: If True and bbox is None, prompt the user with interactive overlay.
        copy_clipboard: Automatically copy recognized text to system clipboard.
        language: Language code ('es', 'en', 'latin').
        dpi: Target raster resolution (default: 300).
        options: Advanced engine options.

    Returns:
        RoaScanResult containing recognized text, markdown, words, and latency.
    """
    target_box = bbox
    if target_box is None and interactive:
        target_box = select_region_interactive()
        if target_box is None:
            # User cancelled region selection
            return RoaScanResult(
                text="",
                markdown="",
                language=language,
            )

    screenshot = capture_screen(bbox=target_box)
    res = run_ocr(screenshot, language=language, dpi=dpi, options=options)

    if copy_clipboard and res.text:
        copy_to_clipboard(res.text)

    return res
