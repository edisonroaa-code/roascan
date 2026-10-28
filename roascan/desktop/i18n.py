"""
roascan.desktop.i18n: Lightweight localization module for RoaScan Desktop UI.

Provides English (en) and Spanish (es) translations for Tray menus, Result Panel,
and system notifications. Clean-room OSS implementation without external dependencies.
"""

from typing import Dict, Optional

_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "es": {
        # Tray Menu
        "tray.ocr_region": "OCR región",
        "tray.open_last_result": "Abrir último resultado",
        "tray.preferences": "Preferencias...",
        "tray.language": "Idioma",
        "tray.lang_es": "Español",
        "tray.lang_en": "English",
        "tray.exit": "Salir",
        "tray.running_bg": "RoaScan activo en segundo plano (atajo: {hotkey}). Clic derecho para opciones.",
        "tray.notification_title": "RoaScan OCR",
        "tray.copied_notification": "Texto copiado al portapapeles ({count} palabras)",
        "tray.no_last_result": "Aún no se ha realizado ninguna captura OCR en esta sesión.",
        "tray.error_notification": "Fallo en captura OCR: {error}",
        "tray.capture_in_progress": "Ya hay una captura en progreso.",

        # Result Panel
        "panel.title": "RoaScan — Resultado OCR",
        "panel.copy_btn": "Copiar",
        "panel.save_btn": "Guardar...",
        "panel.close_btn": "Cerrar",
        "panel.empty_result": "(No se detectó texto en la región seleccionada)",
        "panel.status_ready": "Listo. Puede editar el texto antes de copiar o guardar.",
        "panel.status_copied": "Texto copiado al portapapeles con éxito.",
        "panel.status_saved": "Guardado en: {path}",
        "panel.save_dialog_title": "Guardar resultado OCR",
        "panel.file_filter_md": "Documentos Markdown (*.md)",
        "panel.file_filter_txt": "Archivos de texto (*.txt)",
        "panel.file_filter_all": "Todos los archivos (*.*)",

        # Errors & Warnings
        "error.ocr_failed": "Error durante el reconocimiento OCR.",
        "error.save_failed": "Error al guardar el archivo: {error}",
    },
    "en": {
        # Tray Menu
        "tray.ocr_region": "OCR region",
        "tray.open_last_result": "Open last result",
        "tray.preferences": "Preferences...",
        "tray.language": "Language",
        "tray.lang_es": "Español",
        "tray.lang_en": "English",
        "tray.exit": "Exit",
        "tray.running_bg": "RoaScan running in background (hotkey: {hotkey}). Right-click for options.",
        "tray.notification_title": "RoaScan OCR",
        "tray.copied_notification": "Text copied to clipboard ({count} words)",
        "tray.no_last_result": "No OCR capture has been performed yet in this session.",
        "tray.error_notification": "OCR capture failed: {error}",
        "tray.capture_in_progress": "A capture is already in progress.",

        # Result Panel
        "panel.title": "RoaScan — OCR Result",
        "panel.copy_btn": "Copy",
        "panel.save_btn": "Save...",
        "panel.close_btn": "Close",
        "panel.empty_result": "(No text detected in selected region)",
        "panel.status_ready": "Ready. You can edit the text before copying or saving.",
        "panel.status_copied": "Text copied to clipboard successfully.",
        "panel.status_saved": "Saved to: {path}",
        "panel.save_dialog_title": "Save OCR Result",
        "panel.file_filter_md": "Markdown Documents (*.md)",
        "panel.file_filter_txt": "Text Files (*.txt)",
        "panel.file_filter_all": "All Files (*.*)",

        # Errors & Warnings
        "error.ocr_failed": "Error during OCR recognition.",
        "error.save_failed": "Failed to save file: {error}",
    },
}

_current_ui_lang: str = "es"


def set_ui_language(lang: str):
    """Set the active UI language ('es' or 'en')."""
    global _current_ui_lang
    l = str(lang).strip().lower()
    if l in _TRANSLATIONS:
        _current_ui_lang = l
    else:
        _current_ui_lang = "es"


def get_ui_language() -> str:
    """Return the active UI language."""
    return _current_ui_lang


def t(key: str, lang: Optional[str] = None, **kwargs) -> str:
    """
    Translate a key into the target language with keyword interpolation.
    Falls back to English if key is missing in chosen language, or key itself.
    """
    target_lang = str(lang).strip().lower() if lang else _current_ui_lang
    if target_lang not in _TRANSLATIONS:
        target_lang = "en"

    # Try target language
    msg = _TRANSLATIONS.get(target_lang, {}).get(key)
    if msg is None and target_lang != "en":
        # Fallback to English
        msg = _TRANSLATIONS.get("en", {}).get(key)

    if msg is None:
        # Ultimate fallback
        msg = key

    if kwargs:
        try:
            return msg.format(**kwargs)
        except Exception:
            return msg
    return msg
