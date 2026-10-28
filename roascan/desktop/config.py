"""
roascan.desktop.config: User configuration management for RoaScan Desktop.

Manages persistent JSON configuration in the user's platform configuration directory.
Precedence: CLI Arguments > Environment Variables > config.json > Default Values.

Clean-room OSS implementation; no proprietary telemetry, cloud auth, or remote sync.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("roascan.desktop.config")

# Fallback default save directory: ~/Documents/RoaScan
_DEFAULT_DOCUMENTS_DIR = Path.home() / "Documents" / "RoaScan"

DEFAULT_CONFIG: Dict[str, Any] = {
    "hotkey": "Ctrl+Shift+O",
    "ocr_lang": "es",
    "save_dir": str(_DEFAULT_DOCUMENTS_DIR),
    "ui_lang": "es",
    "copy_on_success": True,
    "show_result_panel": True,
}

VALID_OCR_LANGS = {"es", "en", "latin"}
VALID_UI_LANGS = {"es", "en"}


def get_default_config_dir() -> Path:
    """Return user configuration directory for RoaScan using platformdirs or standard fallbacks."""
    try:
        import platformdirs
        base_dir = Path(platformdirs.user_config_dir("roascan", appauthor=False))
    except Exception:
        # Standard OS fallbacks
        if os.name == "nt":
            appdata = os.environ.get("APPDATA")
            if appdata:
                base_dir = Path(appdata) / "roascan"
            else:
                base_dir = Path.home() / ".config" / "roascan"
        else:
            base_dir = Path.home() / ".config" / "roascan"
    return base_dir


def get_config_path(override_path: Optional[Path] = None) -> Path:
    """Return the absolute path to config.json."""
    if override_path is not None:
        return Path(override_path)
    env_path = os.environ.get("ROASCAN_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    return get_default_config_dir() / "config.json"


def _coerce_bool(val: Any, default: bool) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("true", "1", "yes", "t", "on"):
            return True
        if v in ("false", "0", "no", "f", "off"):
            return False
    return default


def validate_and_clean_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and sanitize configuration dictionary against schema."""
    cleaned = dict(DEFAULT_CONFIG)

    if "hotkey" in raw and isinstance(raw["hotkey"], str) and raw["hotkey"].strip():
        cleaned["hotkey"] = raw["hotkey"].strip()

    if "ocr_lang" in raw:
        lang = str(raw["ocr_lang"]).strip().lower()
        if lang in VALID_OCR_LANGS:
            cleaned["ocr_lang"] = lang

    if "save_dir" in raw and isinstance(raw["save_dir"], str) and raw["save_dir"].strip():
        cleaned["save_dir"] = str(Path(raw["save_dir"]).expanduser())

    if "ui_lang" in raw:
        ui = str(raw["ui_lang"]).strip().lower()
        if ui in VALID_UI_LANGS:
            cleaned["ui_lang"] = ui

    if "copy_on_success" in raw:
        cleaned["copy_on_success"] = _coerce_bool(raw["copy_on_success"], True)

    if "show_result_panel" in raw:
        cleaned["show_result_panel"] = _coerce_bool(raw["show_result_panel"], True)

    return cleaned


def apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply environment variable overrides with highest priority after CLI args."""
    cfg = dict(config)

    if "ROASCAN_HOTKEY" in os.environ and os.environ["ROASCAN_HOTKEY"].strip():
        cfg["hotkey"] = os.environ["ROASCAN_HOTKEY"].strip()

    if "ROASCAN_OCR_LANG" in os.environ and os.environ["ROASCAN_OCR_LANG"].strip():
        lang = os.environ["ROASCAN_OCR_LANG"].strip().lower()
        if lang in VALID_OCR_LANGS:
            cfg["ocr_lang"] = lang

    if "ROASCAN_SAVE_DIR" in os.environ and os.environ["ROASCAN_SAVE_DIR"].strip():
        cfg["save_dir"] = str(Path(os.environ["ROASCAN_SAVE_DIR"].strip()).expanduser())

    if "ROASCAN_UI_LANG" in os.environ and os.environ["ROASCAN_UI_LANG"].strip():
        ui = os.environ["ROASCAN_UI_LANG"].strip().lower()
        if ui in VALID_UI_LANGS:
            cfg["ui_lang"] = ui

    if "ROASCAN_COPY_ON_SUCCESS" in os.environ:
        cfg["copy_on_success"] = _coerce_bool(os.environ["ROASCAN_COPY_ON_SUCCESS"], cfg["copy_on_success"])

    if "ROASCAN_SHOW_PANEL" in os.environ:
        cfg["show_result_panel"] = _coerce_bool(os.environ["ROASCAN_SHOW_PANEL"], cfg["show_result_panel"])

    return cfg


def load_config(config_path: Optional[Path] = None, apply_env: bool = True) -> Dict[str, Any]:
    """Load config.json, merging with defaults and validating values."""
    path = get_config_path(config_path)
    merged = dict(DEFAULT_CONFIG)

    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                merged.update(data)
        except Exception as exc:
            logger.warning(f"Failed to read config from {path}: {exc}. Using default configuration.")

    cleaned = validate_and_clean_config(merged)
    if apply_env:
        cleaned = apply_env_overrides(cleaned)
    return cleaned


def save_config(config_data: Dict[str, Any], config_path: Optional[Path] = None) -> Path:
    """Validate and write configuration dictionary to config.json."""
    path = get_config_path(config_path)
    cleaned = validate_and_clean_config(config_data)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2, ensure_ascii=False)
        logger.info(f"Configuration saved successfully to {path}.")
    except Exception as exc:
        logger.error(f"Failed to save configuration to {path}: {exc}")
        raise

    return path


def set_config_value(key: str, value: Any, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load existing config, update a single key, save to disk, and return new config."""
    cfg = load_config(config_path=config_path, apply_env=False)
    cfg[key] = value
    save_config(cfg, config_path=config_path)
    return load_config(config_path=config_path, apply_env=True)
