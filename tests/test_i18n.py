"""
Unit tests for RoaScan Desktop UI Localization (i18n) (P6).

Runs 100% headless in CI without physical display.
"""

import pytest
from roascan.desktop.i18n import (
    t,
    set_ui_language,
    get_ui_language,
    _TRANSLATIONS,
)


def test_catalogs_have_identical_keys():
    """Ensure every translation key in 'es' exists in 'en' and vice versa."""
    es_keys = set(_TRANSLATIONS["es"].keys())
    en_keys = set(_TRANSLATIONS["en"].keys())

    missing_in_en = es_keys - en_keys
    missing_in_es = en_keys - es_keys

    assert not missing_in_en, f"Keys missing in EN catalog: {missing_in_en}"
    assert not missing_in_es, f"Keys missing in ES catalog: {missing_in_es}"


def test_translation_and_formatting():
    # Spanish
    set_ui_language("es")
    assert get_ui_language() == "es"
    msg_es = t("tray.copied_notification", count=42)
    assert "42 palabras" in msg_es

    # English
    set_ui_language("en")
    assert get_ui_language() == "en"
    msg_en = t("tray.copied_notification", count=42)
    assert "42 words" in msg_en


def test_missing_key_fallback():
    set_ui_language("es")
    # Non-existent key should return key itself
    assert t("non.existent.key") == "non.existent.key"


def test_explicit_lang_override():
    # When active language is ES, explicit lang="en" gives EN
    set_ui_language("es")
    res = t("panel.copy_btn", lang="en")
    assert res == "Copy"

    res_es = t("panel.copy_btn", lang="es")
    assert res_es == "Copiar"
