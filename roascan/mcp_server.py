"""
roascan.mcp_server: Built-in Model Context Protocol (MCP) Server for RoaScan.

Exposes RoaScan's C++17 + ONNX OCR and document restoration pipeline directly to
AI Agents (Antigravity, Claude Code, Claude Desktop, Cursor, Windsurf, Cline)
over standard MCP stdio JSON-RPC 2.0 transport with strict schema, path, format,
and protocol validation.

Launch via:
  roascan --mcp
  roascan-mcp
  python -m roascan --mcp
"""

import json
import os
import sys
import time
from typing import Any, Dict, Optional

from . import RoaScanEngine, RoaScanDocumentWriter, validate_output_paths, __version__

SUPPORTED_MCP_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")
VALID_LANGUAGES = ("es", "en", "latin")

MCP_TOOLS = [
    {
        "name": "roascan_to_markdown",
        "description": (
            "Convert a scanned single or multi-page document (PDF, TIFF, PNG, JPEG, BMP) "
            "into structured Markdown (.md) with headings (#/##), bold key-value fields, "
            "and GitHub-Flavored Markdown tables (|---|---|). Runs locally on CPU "
            "via C++17 + ONNX."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the input document (.pdf, .tif, .tiff, .png, .jpg, .bmp).",
                },
                "output_md_path": {
                    "type": "string",
                    "description": "Optional path to save the generated Markdown file (must end with .md or .markdown).",
                },
                "language": {
                    "type": "string",
                    "enum": ["es", "en", "latin"],
                    "default": "es",
                    "description": "Document language ('es' restores Spanish accents/tildes via Hunspell lexicon; 'en' for English).",
                },
                "dpi": {
                    "type": "integer",
                    "minimum": 36,
                    "maximum": 1200,
                    "default": 300,
                    "description": "Target rasterization DPI for PDF pages (default: 300).",
                },
            },
            "required": ["input_path"],
        },
    },
    {
        "name": "roascan_to_searchable_pdf",
        "description": (
            "Optical scan restoration: restore a noisy, shadowed, or skewed scanned multi-page "
            "PDF/TIFF/image (auto-deskew to 0.1 deg, 90/180/270 orientation recovery, C++ Sauvola "
            "background whitening, speckle removal) and generate a Searchable PDF (.pdf) preserving "
            "physical page dimensions in PDF points (72 pt/inch) and document metadata with an "
            "invisible selectable text layer. Note: Optical restoration rasterizes and reconstructs "
            "each page from the restored bitmap; native vector elements, interactive hyperlinks, "
            "annotations, and form fields from digital-born PDFs are not preserved."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {
                    "type": "string",
                    "description": "Path to the scanned input document (.pdf, .tif, .tiff, .png, .jpg, .bmp).",
                },
                "output_pdf_path": {
                    "type": "string",
                    "description": "Destination path for the restored Searchable PDF (must end with .pdf).",
                },
                "language": {
                    "type": "string",
                    "enum": ["es", "en", "latin"],
                    "default": "es",
                    "description": "Document language ('es', 'en', or 'latin').",
                },
                "dpi": {
                    "type": "integer",
                    "minimum": 36,
                    "maximum": 1200,
                    "default": 300,
                    "description": "Target DPI for PDF rendering (default: 300).",
                },
                "enhance_quality": {
                    "type": "boolean",
                    "default": True,
                    "description": "Apply C++ background whitening and ink contrast enhancement.",
                },
            },
            "required": ["input_path", "output_pdf_path"],
        },
    },
    {
        "name": "roascan_process_document",
        "description": (
            "Full pipeline: process a scanned multi-page document and simultaneously "
            "export an enhanced Searchable PDF (.pdf) and/or structured Markdown (.md), "
            "returning page count, word count, latency, and extracted Markdown. "
            "Note: Searchable PDF output performs optical raster restoration and does not "
            "preserve native digital PDF hyperlinks, annotations, or interactive forms."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {
                    "type": "string",
                    "description": "Path to the input document (.pdf, .tif, .tiff, .png, .jpg, .bmp).",
                },
                "output_pdf_path": {
                    "type": "string",
                    "description": "Optional output path for the restored Searchable PDF (must end with .pdf).",
                },
                "output_md_path": {
                    "type": "string",
                    "description": "Optional output path for the structured Markdown (must end with .md or .markdown).",
                },
                "language": {
                    "type": "string",
                    "enum": ["es", "en", "latin"],
                    "default": "es",
                },
                "dpi": {
                    "type": "integer",
                    "minimum": 36,
                    "maximum": 1200,
                    "default": 300,
                },
            },
            "required": ["input_path"],
        },
    },
    {
        "name": "roascan_inspect_pdf",
        "description": (
            "Inspect a PDF file to determine its page count, physical page dimensions, "
            "embedded images, and whether each page is a scanned image requiring RoaScan OCR."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {
                    "type": "string",
                    "description": "Path to the PDF file to inspect.",
                },
            },
            "required": ["input_path"],
        },
    },
]

VALID_TOOL_NAMES = {t["name"] for t in MCP_TOOLS}


def _tool_error(msg: str) -> Dict[str, Any]:
    return {
        "isError": True,
        "content": [{"type": "text", "text": f"Error: {msg}"}],
    }


def _execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.perf_counter()
    if name not in VALID_TOOL_NAMES:
        return _tool_error(f"Unknown tool '{name}'. Valid tools: {sorted(VALID_TOOL_NAMES)}")

    if not isinstance(args, dict):
        return _tool_error("Tool 'arguments' must be a JSON object.")

    input_path = args.get("input_path")
    if not isinstance(input_path, str) or not input_path.strip():
        return _tool_error("Missing or invalid required string parameter 'input_path'.")

    if not os.path.exists(input_path):
        return _tool_error(f"File not found: {input_path}")

    abs_in = os.path.abspath(input_path)

    if name == "roascan_inspect_pdf":
        import fitz

        pages_info = []
        needs_ocr_count = 0
        with fitz.open(abs_in) as doc:
            for idx, page in enumerate(doc):
                txt = page.get_text("text").strip()
                n_imgs = len(page.get_images())
                needs_ocr = len(txt) < 15 and n_imgs > 0
                if needs_ocr:
                    needs_ocr_count += 1
                pages_info.append({
                    "page": idx + 1,
                    "width_pt": round(page.rect.width, 2),
                    "height_pt": round(page.rect.height, 2),
                    "images_count": n_imgs,
                    "embedded_chars": len(txt),
                    "needs_ocr": needs_ocr,
                })
        result = {
            "file": abs_in,
            "total_pages": len(pages_info),
            "pages_needing_ocr": needs_ocr_count,
            "recommendation": (
                "Run roascan_to_markdown or roascan_to_searchable_pdf"
                if needs_ocr_count > 0
                else "PDF already contains embedded text"
            ),
            "pages": pages_info,
        }
        return {
            "isError": False,
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
        }

    # Validate required tool-specific parameters
    out_pdf = args.get("output_pdf_path")
    out_md = args.get("output_md_path")

    if name == "roascan_to_searchable_pdf":
        if not isinstance(out_pdf, str) or not out_pdf.strip():
            return _tool_error("Tool 'roascan_to_searchable_pdf' requires a non-empty 'output_pdf_path'.")

    # Validate language and DPI
    lang = args.get("language", "es")
    if not isinstance(lang, str) or lang.lower() not in VALID_LANGUAGES:
        return _tool_error(f"Invalid language '{lang}'. Supported: {VALID_LANGUAGES}")

    raw_dpi = args.get("dpi", 300)
    if isinstance(raw_dpi, bool) or not isinstance(raw_dpi, int) or raw_dpi < 36 or raw_dpi > 1200:
        return _tool_error(f"Invalid dpi '{raw_dpi}'. Must be an integer between 36 and 1200.")
    dpi = int(raw_dpi)

    enhance = bool(args.get("enhance_quality", True))

    # Validate output paths and strict format extensions upfront before running OCR
    try:
        validate_output_paths(
            abs_in,
            [out_pdf, out_md],
            expected_formats=["pdf", "md"],
        )
    except Exception as exc:
        return _tool_error(str(exc))

    with RoaScanEngine(language=lang.lower()) as engine:
        engine.set_resolution(dpi, dpi)
        engine.set_document_enhancement(enhance)
        engine.set_retain_images(bool(out_pdf))
        engine.set_image_file(abs_in)

        t_ocr0 = time.perf_counter()
        rc = engine.recognize()
        ocr_elapsed_ms = round((time.perf_counter() - t_ocr0) * 1000.0, 2)

        if rc != 0:
            return _tool_error(engine.last_error or f"RoaScan engine returned error code {rc}")

        md_text = engine.to_markdown()
        outputs = []

        with RoaScanDocumentWriter() as writer:
            if out_pdf:
                abs_pdf = os.path.abspath(out_pdf)
                writer.configure_pdf(abs_pdf, enhance_quality=enhance)
                w_rc = writer.write(engine)
                if w_rc != 0 or not os.path.exists(abs_pdf):
                    return _tool_error(writer.last_error or f"Failed to write PDF to {abs_pdf}")
                outputs.append(abs_pdf)
            if out_md:
                abs_md = os.path.abspath(out_md)
                writer.configure_markdown(abs_md)
                w_rc = writer.write(engine)
                if w_rc != 0 or not os.path.exists(abs_md):
                    return _tool_error(writer.last_error or f"Failed to write Markdown to {abs_md}")
                outputs.append(abs_md)

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        if name == "roascan_to_markdown":
            header_meta = (
                f"<!-- RoaScan v{__version__} | pages={engine.page_count} | "
                f"words={len(engine.extract_words())} | ocr_time={ocr_elapsed_ms}ms | total_time={elapsed_ms}ms -->\n\n"
            )
            return {
                "isError": False,
                "content": [{"type": "text", "text": header_meta + md_text}],
            }

        summary = {
            "status": "ok",
            "engine": f"RoaScan v{__version__} (C++17 + ONNX)",
            "input": abs_in,
            "pages_processed": engine.page_count,
            "words_recognized": len(engine.extract_words()),
            "outputs_written": outputs,
            "ocr_elapsed_ms": ocr_elapsed_ms,
            "elapsed_ms": elapsed_ms,
            "markdown": md_text,
        }
        return {
            "isError": False,
            "content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=False, indent=2)}],
        }


def handle_jsonrpc_message(msg: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(msg, dict):
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request: expected JSON object."},
        }

    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params")

    if not isinstance(method, str) or not method:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32600, "message": "Invalid Request: missing or non-string 'method'."},
        }

    if params is not None and not isinstance(params, dict):
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32602, "message": "Invalid params: expected JSON object."},
        }
    params = params or {}

    # Notifications (no id) do not expect a response
    if "id" not in msg or msg_id is None:
        return None

    if method == "initialize":
        client_proto = params.get("protocolVersion", "2024-11-05")
        negotiated_proto = client_proto if client_proto in SUPPORTED_MCP_VERSIONS else SUPPORTED_MCP_VERSIONS[-1]
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": negotiated_proto,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"listChanged": False},
                },
                "serverInfo": {
                    "name": "roascan-mcp",
                    "version": __version__,
                },
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": MCP_TOOLS},
        }

    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"resources": []},
        }

    if method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"prompts": []},
        }

    if method == "tools/call":
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": "Invalid params: missing tool 'name'."},
            }
        tool_args = params.get("arguments")
        if tool_args is None:
            tool_args = {}
        if not isinstance(tool_args, dict):
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": "Invalid params: 'arguments' must be an object."},
            }
        try:
            res = _execute_tool(tool_name, tool_args)
            return {"jsonrpc": "2.0", "id": msg_id, "result": res}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": _tool_error(f"RoaScan MCP exception: {exc}"),
            }

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def run_mcp_server():
    """Run the MCP stdio loop (supports both line-delimited JSON and Content-Length framing)."""
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    while True:
        line = sys.stdin.readline()
        if not line:
            break

        stripped = line.strip()
        if not stripped:
            continue

        use_content_length = False
        if stripped.lower().startswith("content-length:"):
            use_content_length = True
            try:
                length = int(stripped.split(":", 1)[1].strip())
            except ValueError:
                continue
            while True:
                hdr_line = sys.stdin.readline()
                if not hdr_line or hdr_line.strip() == "":
                    break
            body = sys.stdin.read(length)
        else:
            body = stripped

        try:
            msg = json.loads(body)
        except Exception:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error: invalid JSON."},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()
            continue

        resp = handle_jsonrpc_message(msg)
        if resp is not None:
            out_str = json.dumps(resp, ensure_ascii=False)
            if use_content_length:
                out_bytes = out_str.encode("utf-8")
                sys.stdout.write(f"Content-Length: {len(out_bytes)}\r\n\r\n{out_str}")
            else:
                sys.stdout.write(out_str + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_mcp_server()
