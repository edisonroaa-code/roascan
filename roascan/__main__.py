"""
roascan.__main__: Agent-First CLI, MCP Server, and Desktop Capture for RoaScan.

Usage:
  # 1. Start Model Context Protocol (MCP) server (stdio JSON-RPC 2.0):
  roascan --mcp
  roascan-mcp

  # 2. Run environment & model diagnostics:
  roascan --doctor

  # 3. Standard file OCR (Markdown, PDF, or clipboard):
  roascan ocr archivo.png --out out.md
  roascan scan.pdf --md output.md --pdf clean.pdf --lang es --copy
  roascan factura.png --copy

  # 4. Desktop Screen / Region Capture OCR:
  roascan clip
  roascan clip --bbox 100,100,500,400 --out recorte.md
"""

import argparse
import json
import os
import sys
import time
from typing import List, Optional

from . import RoaScanEngine, RoaScanDocumentWriter, validate_output_paths, __version__
from .api import run_ocr
from .desktop.clipboard import copy_to_clipboard
from .desktop.capture import capture_region_and_ocr
from .mcp_server import run_mcp_server


def _emit_error(message: str, as_json: bool, code: int = 1) -> int:
    err = {"status": "error", "code": code, "message": message}
    if as_json:
        print(json.dumps(err, ensure_ascii=False))
    else:
        print(f"[ERROR] {message}", file=sys.stderr)
    return code


def _parse_bbox(bbox_str: Optional[str]):
    if not bbox_str:
        return None
    parts = [int(p.strip()) for p in bbox_str.split(",")]
    if len(parts) != 4:
        raise ValueError("Bbox must be 4 comma-separated integers: left,top,right,bottom")
    return tuple(parts)


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    args_list = list(sys.argv[1:] if argv is None else argv)

    # Normalize subcommands 'ocr', 'clip' / 'capture', 'tray', and 'config'
    subcommand = None
    if args_list and args_list[0] in ("ocr", "clip", "capture", "tray", "config"):
        subcommand = args_list.pop(0)
        if subcommand == "capture":
            subcommand = "clip"

    if subcommand == "tray":
        from .desktop.tray_app import main as tray_main
        return tray_main(args_list)

    if subcommand == "config":
        from .desktop.config_cli import run_config_cli
        return run_config_cli(args_list)

    parser = argparse.ArgumentParser(
        prog=f"roascan {subcommand}" if subcommand else "roascan",
        description=(
            f"RoaScan v{__version__} — C++17 & ONNX local OCR: "
            "Scanned PDF/TIFF/Image/Screen -> Searchable PDF & Structured Markdown."
        ),
    )

    if subcommand == "clip":
        parser.add_argument(
            "--bbox",
            help="Coordinates left,top,right,bottom (e.g. 100,100,600,400). If omitted, interactive overlay opens.",
        )
        parser.add_argument(
            "-o",
            "--out",
            help="Optional output path (.md, .pdf, .json, .txt)",
        )
        parser.add_argument(
            "--no-copy",
            action="store_true",
            help="Do not copy recognized text to system clipboard",
        )
        parser.add_argument(
            "--panel",
            action="store_true",
            help="Display interactive result panel after recognition",
        )
    else:
        parser.add_argument(
            "input",
            nargs="?",
            help="Input document path (.pdf, .tif, .tiff, .png, .jpg, .bmp). Omit when using --mcp or --doctor.",
        )
        parser.add_argument(
            "-o",
            "--output",
            "--out",
            dest="output",
            help="Output path (.pdf, .md, .json, or .txt)",
        )
        parser.add_argument(
            "--md",
            help="Explicit output path for structured Markdown (.md)",
        )
        parser.add_argument(
            "--pdf",
            help="Explicit output path for restored Searchable PDF (.pdf)",
        )
        parser.add_argument(
            "--copy",
            action="store_true",
            help="Copy recognized plain text directly to the system clipboard",
        )

    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Launch the RoaScan Model Context Protocol (MCP) stdio server for AI agents.",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Inspect native C++ core, ONNX Runtime providers, and model/dictionary availability.",
    )
    parser.add_argument(
        "-l",
        "--lang",
        default="es",
        choices=["es", "en", "latin"],
        help="Language code: es, en, latin (default: es)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Rasterization DPI [36..1200] (default: 300)",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=0,
        help="Maximum worker threads (default: auto)",
    )
    parser.add_argument(
        "--no-enhance",
        action="store_true",
        help="Disable C++ background whitening and ink contrast enhancement",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON summary to stdout (ideal for AI agents)",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"RoaScan {__version__}",
    )

    args = parser.parse_args(args_list)

    if getattr(args, "mcp", False):
        run_mcp_server()
        return 0

    if getattr(args, "doctor", False):
        diag = RoaScanEngine.diagnose(language=args.lang)
        print(json.dumps(diag, ensure_ascii=False, indent=2))
        return 0 if diag["status"] == "ok" else 1

    # --- Subcommand: clip / capture ----------------------------------------
    if subcommand == "clip":
        try:
            target_bbox = _parse_bbox(args.bbox)
        except Exception as exc:
            return _emit_error(str(exc), args.json, code=2)

        interactive = (target_bbox is None)
        try:
            res = capture_region_and_ocr(
                bbox=target_bbox,
                interactive=interactive,
                copy_clipboard=not args.no_copy,
                language=args.lang,
                dpi=args.dpi,
            )
            if not res.text and interactive:
                if not args.json:
                    print("[RoaScan] Captura cancelada por el usuario.")
                return 0

            if args.out:
                if args.out.lower().endswith((".md", ".markdown")):
                    res.save_markdown(args.out)
                else:
                    with RoaScanDocumentWriter() as writer:
                        writer.configure_auto(args.out)
                        writer._atomic_write_text(args.out, res.text)

            if args.json:
                print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
            else:
                copied_badge = " [Copiado al portapapeles]" if not args.no_copy else ""
                print(f"[RoaScan OK]{copied_badge} {len(res.words)} palabras en {res.ocr_elapsed_ms} ms:\n")
                print(res.text)

            if getattr(args, "panel", False) and res.text:
                from .desktop.result_panel import show_result_panel
                show_result_panel(res.text, blocking=True)
            return 0
        except Exception as exc:
            return _emit_error(str(exc), args.json, code=1)

    # --- Standard file OCR -------------------------------------------------
    if not args.input:
        parser.print_help()
        return 1

    t0 = time.perf_counter()
    if not os.path.exists(args.input):
        return _emit_error(f"Input file not found: {args.input}", args.json, code=1)

    if args.dpi < 36 or args.dpi > 1200:
        return _emit_error(f"Invalid DPI {args.dpi}: must be between 36 and 1200.", args.json, code=2)

    # Validate output paths and format contracts upfront BEFORE running OCR
    try:
        validate_output_paths(
            args.input,
            [args.output, args.pdf, args.md],
            expected_formats=["auto", "pdf", "md"],
        )
    except Exception as exc:
        return _emit_error(str(exc), args.json, code=2)

    enhance = not args.no_enhance
    needs_pdf_images = bool(
        args.pdf or (args.output and args.output.lower().endswith(".pdf"))
    )

    try:
        with RoaScanEngine(language=args.lang) as engine:
            engine.set_resolution(args.dpi, args.dpi)
            engine.set_document_enhancement(enhance)
            engine.set_retain_images(needs_pdf_images)
            if args.threads > 0:
                engine.set_thread_count(args.threads)
            engine.set_image_file(args.input)

            t_ocr0 = time.perf_counter()
            rc = engine.recognize()
            ocr_elapsed_ms = round((time.perf_counter() - t_ocr0) * 1000.0, 2)

            if rc != 0:
                msg = engine.last_error or f"Recognition pipeline failed with code {rc}"
                return _emit_error(msg, args.json, code=abs(rc))

            outputs_written: List[str] = []
            with RoaScanDocumentWriter() as writer:
                if args.output:
                    writer.configure_auto(args.output, enhance_quality=enhance)
                    w_rc = writer.write(engine)
                    if w_rc != 0 or not os.path.exists(args.output):
                        return _emit_error(
                            writer.last_error or f"Failed to write output file: {args.output}",
                            args.json,
                            code=2,
                        )
                    outputs_written.append(os.path.abspath(args.output))

                if args.pdf:
                    writer.configure_pdf(args.pdf, enhance_quality=enhance)
                    w_rc = writer.write(engine)
                    if w_rc != 0 or not os.path.exists(args.pdf):
                        return _emit_error(
                            writer.last_error or f"Failed to write PDF file: {args.pdf}",
                            args.json,
                            code=2,
                        )
                    outputs_written.append(os.path.abspath(args.pdf))

                if args.md:
                    writer.configure_markdown(args.md)
                    w_rc = writer.write(engine)
                    if w_rc != 0 or not os.path.exists(args.md):
                        return _emit_error(
                            writer.last_error or f"Failed to write Markdown file: {args.md}",
                            args.json,
                            code=2,
                        )
                    outputs_written.append(os.path.abspath(args.md))

            if args.copy:
                copy_to_clipboard(engine.get_text())

            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            if args.json:
                summary = engine.to_dict()
                summary["status"] = "ok"
                summary["input"] = os.path.abspath(args.input)
                summary["outputs"] = outputs_written
                summary["ocr_elapsed_ms"] = ocr_elapsed_ms
                summary["elapsed_ms"] = elapsed_ms
                if args.copy:
                    summary["clipboard"] = "copied"
                print(json.dumps(summary, ensure_ascii=False))
            elif not outputs_written:
                print(engine.to_markdown())
            else:
                copied_txt = " [Copiado al portapapeles]" if args.copy else ""
                print(
                    f"[RoaScan OK]{copied_txt} Processed {engine.page_count} page(s) "
                    f"({len(engine.extract_words())} words) in {ocr_elapsed_ms} ms OCR "
                    f"({elapsed_ms} ms total) -> {', '.join(outputs_written)}"
                )
    except Exception as exc:
        return _emit_error(str(exc), args.json, code=1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
