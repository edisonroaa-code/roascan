"""
roascan.desktop.clipboard: Native clipboard integration for RoaScan.

Provides 100% local, zero-third-party-dependency clipboard read and write on
Windows via Win32 ctypes (user32/kernel32) with a Tkinter fallback.
"""

import ctypes
from ctypes import wintypes
import sys
from typing import Optional

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _copy_win32(text: str) -> bool:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # Configure 64-bit safe prototypes
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE

    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h_mem:
            return False
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            return False
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h_mem)
        return bool(user32.SetClipboardData(CF_UNICODETEXT, h_mem))
    finally:
        user32.CloseClipboard()


def _get_win32() -> str:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE

    if not user32.OpenClipboard(None):
        return ""
    try:
        h_mem = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_mem:
            return ""
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            return ""
        val = ctypes.wstring_at(ptr)
        kernel32.GlobalUnlock(h_mem)
        return val
    finally:
        user32.CloseClipboard()


def _copy_tkinter(text: str) -> bool:
    try:
        import tkinter as tk

        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        return True
    except Exception:
        return False


def _get_tkinter() -> str:
    try:
        import tkinter as tk

        r = tk.Tk()
        r.withdraw()
        val = r.clipboard_get()
        r.destroy()
        return str(val)
    except Exception:
        return ""


def copy_to_clipboard(text: str) -> bool:
    """Copy text string to the system clipboard (Windows native with Tkinter fallback)."""
    if sys.platform == "win32":
        try:
            if _copy_win32(text):
                return True
        except Exception:
            pass
    return _copy_tkinter(text)


def get_clipboard_text() -> str:
    """Retrieve text string currently in the system clipboard."""
    if sys.platform == "win32":
        try:
            res = _get_win32()
            if res:
                return res
        except Exception:
            pass
    return _get_tkinter()
