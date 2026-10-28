"""
Unit tests for RoaScan Desktop Configuration Management (P6).

Runs 100% headless in CI without physical display or external services.
"""

import os
from pathlib import Path
import tempfile
import pytest

from roascan.desktop.config import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
    get_config_path,
    set_config_value,
    validate_and_clean_config,
    apply_env_overrides,
    _coerce_bool,
)


def test_default_config_schema():
    assert "hotkey" in DEFAULT_CONFIG
    assert "ocr_lang" in DEFAULT_CONFIG
    assert "save_dir" in DEFAULT_CONFIG
    assert "ui_lang" in DEFAULT_CONFIG
    assert "copy_on_success" in DEFAULT_CONFIG
    assert "show_result_panel" in DEFAULT_CONFIG
    assert DEFAULT_CONFIG["ui_lang"] in ("es", "en")
    assert DEFAULT_CONFIG["copy_on_success"] is True
    assert DEFAULT_CONFIG["show_result_panel"] is True


def test_config_path_resolution(monkeypatch):
    custom_path = Path("/tmp/custom_roascan_cfg.json")
    assert get_config_path(custom_path) == custom_path

    monkeypatch.setenv("ROASCAN_CONFIG_PATH", str(custom_path))
    assert get_config_path() == custom_path


def test_config_roundtrip_save_and_load(tmp_path):
    cfg_file = tmp_path / "subdir" / "roascan_test.json"
    data = {
        "hotkey": "Ctrl+Alt+O",
        "ocr_lang": "en",
        "save_dir": str(tmp_path / "MyScans"),
        "ui_lang": "en",
        "copy_on_success": False,
        "show_result_panel": False,
    }
    saved_path = save_config(data, config_path=cfg_file)
    assert saved_path == cfg_file
    assert cfg_file.is_file()

    loaded = load_config(config_path=cfg_file, apply_env=False)
    assert loaded["hotkey"] == "Ctrl+Alt+O"
    assert loaded["ocr_lang"] == "en"
    assert loaded["save_dir"] == str(tmp_path / "MyScans")
    assert loaded["ui_lang"] == "en"
    assert loaded["copy_on_success"] is False
    assert loaded["show_result_panel"] is False


def test_config_validation_and_coercion():
    raw = {
        "hotkey": "   ",  # invalid, should fallback to default
        "ocr_lang": "INVALID_LANG",  # invalid, fallback
        "ui_lang": "fr",  # invalid, fallback
        "copy_on_success": "false",  # string coercion to False
        "show_result_panel": 1,  # int coercion to True
    }
    cleaned = validate_and_clean_config(raw)
    assert cleaned["hotkey"] == DEFAULT_CONFIG["hotkey"]
    assert cleaned["ocr_lang"] == DEFAULT_CONFIG["ocr_lang"]
    assert cleaned["ui_lang"] == DEFAULT_CONFIG["ui_lang"]
    assert cleaned["copy_on_success"] is False
    assert cleaned["show_result_panel"] is True


def test_set_config_value(tmp_path):
    cfg_file = tmp_path / "config.json"
    updated = set_config_value("hotkey", "Ctrl+F12", config_path=cfg_file)
    assert updated["hotkey"] == "Ctrl+F12"

    reloaded = load_config(config_path=cfg_file, apply_env=False)
    assert reloaded["hotkey"] == "Ctrl+F12"


def test_env_var_priority_overrides_config(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.json"
    save_config({"hotkey": "Ctrl+Shift+O", "ui_lang": "es"}, config_path=cfg_file)

    monkeypatch.setenv("ROASCAN_HOTKEY", "Ctrl+Shift+K")
    monkeypatch.setenv("ROASCAN_UI_LANG", "en")
    monkeypatch.setenv("ROASCAN_SHOW_PANEL", "0")

    loaded = load_config(config_path=cfg_file, apply_env=True)
    assert loaded["hotkey"] == "Ctrl+Shift+K"
    assert loaded["ui_lang"] == "en"
    assert loaded["show_result_panel"] is False
