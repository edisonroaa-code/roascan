"""
roascan.desktop.config_cli: CLI tool to inspect and modify RoaScan user preferences.

Usage:
  roascan config show
  roascan config set <key> <value>
  roascan config path
"""

import argparse
import json
import sys
from typing import List, Optional

from .config import (
    load_config,
    save_config,
    get_config_path,
    set_config_value,
    DEFAULT_CONFIG,
    VALID_OCR_LANGS,
    VALID_UI_LANGS,
    _coerce_bool,
)


def run_config_cli(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="roascan config",
        description="Inspect and update RoaScan desktop preferences (JSON config file).",
    )
    subparsers = parser.add_subparsers(dest="action", help="Config action: show, set, path")

    # show
    subparsers.add_parser("show", help="Display current active configuration")

    # path
    subparsers.add_parser("path", help="Print path to the user configuration JSON file")

    # set
    set_parser = subparsers.add_parser("set", help="Set a configuration key and value")
    set_parser.add_argument("key", help=f"Key name (one of: {', '.join(DEFAULT_CONFIG.keys())})")
    set_parser.add_argument("value", help="New value for the configuration key")

    args = parser.parse_args(argv)

    if args.action == "show" or args.action is None:
        cfg = load_config(apply_env=True)
        print(json.dumps(cfg, indent=2, ensure_ascii=False))
        return 0

    elif args.action == "path":
        print(get_config_path())
        return 0

    elif args.action == "set":
        key = args.key.strip()
        val_str = args.value.strip()

        if key not in DEFAULT_CONFIG:
            print(f"[ERROR] Invalid configuration key '{key}'. Valid keys: {', '.join(DEFAULT_CONFIG.keys())}", file=sys.stderr)
            return 1

        # Type conversion
        if key in ("copy_on_success", "show_result_panel"):
            parsed_val = _coerce_bool(val_str, DEFAULT_CONFIG[key])
        elif key == "ocr_lang":
            if val_str.lower() not in VALID_OCR_LANGS:
                print(f"[ERROR] Invalid ocr_lang '{val_str}'. Valid: {', '.join(VALID_OCR_LANGS)}", file=sys.stderr)
                return 1
            parsed_val = val_str.lower()
        elif key == "ui_lang":
            if val_str.lower() not in VALID_UI_LANGS:
                print(f"[ERROR] Invalid ui_lang '{val_str}'. Valid: {', '.join(VALID_UI_LANGS)}", file=sys.stderr)
                return 1
            parsed_val = val_str.lower()
        else:
            parsed_val = val_str

        updated = set_config_value(key, parsed_val)
        print(f"[RoaScan] Configuration updated: {key} = {updated.get(key)}")
        return 0

    return 0


def main(argv: Optional[List[str]] = None) -> int:
    return run_config_cli(argv)


if __name__ == "__main__":
    sys.exit(main())
