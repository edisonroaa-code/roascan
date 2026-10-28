# RoaScan (`roascan`) — C++17 & ONNX Multi-Page OCR + MCP Server for AI Agents

**RoaScan** (`roascan`) is a local, CPU-first multi-page OCR and optical document restoration engine powered by a clean-room **C++17 native core** (`roascan_core`) and **ONNX Runtime** (`PP-OCRv5 Latin` / `PP-OCRv4 English`).

Designed as an **Agent-First local OCR tool** (Antigravity, Claude Code, Claude Desktop, Cursor, Windsurf, OpenHands) and document restoration library that runs on CPU without requiring GPU hardware, Tesseract, or Ghostscript.

---

## Key Capabilities & Architectural Scope

1. **Multi-Page Scanned Input (Lazy Streaming & Disk-Spooling)**:
   - Native ingestion of multi-page `.pdf` (rasterized page-by-page on demand), `.tiff`/`.tif`, `.png`, `.jpg`, and `.bmp`.
   - In Markdown/text mode (`set_retain_images(False)`), page bitmaps are discarded immediately after recognition (`0 bytes` retained in `engine._pages`).
   - In Searchable PDF mode (`set_retain_images(True)`), restored page images are spooled as compressed PNGs to an exclusive temporary directory (`_spool_dir`) and automatically cleaned up on `engine.close()`, keeping **`0 bytes` of raw uncompressed bitmaps in `engine._pages` RAM**.
2. **Dual High-Value Output**:
   - **Restored Searchable PDF (`.pdf`)**: Preserves physical page dimensions in PDF points (`72 pt/inch`, e.g. `595.28 x 841.89 pt` for A4) and document-level metadata (`title`, `author`), applies C++17 Sauvola 64-bit integral background whitening, 1px anti-aliased ink preservation, coarse-to-fine deskew (`0.1°` precision), and orthogonal `90° / 180° / 270°` orientation recovery with an invisible selectable text overlay (`Ctrl+F`).
   - **Structured Semantic Markdown (`.md`)**: Automatic reconstruction of `#`/`##` titles via typographic font-height clustering, `**Key:** Value` pairs, multi-column reading order (`XY-Cut`), C++ morphological table grid-line removal, and GitHub-Flavored Markdown tables (`|---|---|`).
3. **Built-in Model Context Protocol (MCP) Server**: Ready-to-run stdio JSON-RPC 2.0 server (`roascan --mcp` or `roascan-mcp`) exposing 4 validated tools (`roascan_to_markdown`, `roascan_to_searchable_pdf`, `roascan_process_document`, `roascan_inspect_pdf`).
4. **Spanish & Latin Diacritic Restoration**: Built-in Hunspell lexicon with `/G` and `/S` affix expansion (`ELECTRONICA` -> `ELECTRÓNICA`, `REPUBLICA` -> `REPÚBLICA`, `Pena` -> `Peña`).

> [!IMPORTANT]
> **Scope of Optical PDF Restoration (`roascan_to_searchable_pdf` / `--pdf`):**
> The Searchable PDF pipeline is an **optical scan restorer**. It rasterizes each page, corrects orthogonal rotations (`90°/180°/270°`) and fine skew, whitens shadowed backgrounds, and reconstructs the page from the restored bitmap at exact physical dimensions (`72 pt/inch`) with an invisible selectable text layer (`render_mode=3`) and document metadata (`title`, `author`). Native vector objects, interactive hyperlinks, annotations, and AcroForm fields from digital-born PDFs are not preserved.

---

## Measured Footprint & Reproducible Performance

| Metric | Measured Value (Intel Core i7-7700 4C/8T, Windows x64, Python 3.12) |
| :--- | :--- |
| **RoaScan Wheel Artifact Size** | `~15.0 MiB` compressed (`~17.0 MiB` unpacked, including C++ DLL + ONNX weights + Hunspell lexicon) |
| **Full Runtime Environment** | `~223 MiB` on disk when including `onnxruntime`, `numpy`, `Pillow`, and `PyMuPDF` in a clean virtual environment |
| **C++17 Coarse-to-Fine Deskew Kernel** | `~0.90–1.96 ms` (median `~1.03 ms`) on synthetic 300 DPI A4 binary page (`-15°..+15°` at `0.1°` step with spatial subsampling) |
| **End-to-End Single-Page OCR** | `~230–720 ms` in-process (`ocr_elapsed_ms` after ONNX session init; `~1.1 s` total cold CLI invocation including interpreter & session startup) |
| **30-Page A4 PDF Memory Profile** | `0 bytes` of raw page bitmaps retained in `engine.extract_pages()` in both Markdown and Searchable PDF modes |

### Platform Verification Status
- **Windows x64 (`win_amd64`)**: Precompiled `roascan_core.dll` bundled in wheel (`py3-none-win_amd64`); verified end-to-end. Requires standard Microsoft Visual C++ Redistributable (`MSVCP140.dll` / `VCRUNTIME140.dll`).
- **Linux & macOS (Experimental Source Build; runtime not yet verified)**: `sdist` includes full C++17 sources and `CMakeLists.txt` (`roascan-native/`). Building a wheel from source (`pip install .` or `python -m build --wheel`) automatically invokes `cmake` via `setup.py` to compile `libroascan_core.so` / `libroascan_core.dylib` (requires `cmake >= 3.16` and a C++17 compiler).

---

## Repository Structure

```text
├── pyproject.toml             # PEP 621 package definition
├── setup.py                   # CMake native builder & platform-tagged wheel packager
├── MANIFEST.in                # Complete source distribution (sdist) manifest
├── LICENSE                    # Full Apache-2.0 License
├── NOTICE                     # Provenance, SHA-256 hashes, and licensing notices
├── THIRD_PARTY_LICENSES.txt   # Full license texts for bundled third-party resources (MPL-1.1 / Apache-2.0)
├── SKILL.md                   # AI Agent discovery & usage specification
├── mcp_config.json            # Ready-to-use Model Context Protocol (MCP) config
├── roascan/                   # Python SDK, CLI, MCP Server, bundled DLL & ONNX models
│   ├── api.py                 # Stable high-level API & Bridge Contract (`run_ocr`, `RoaScanResult`)
│   └── desktop/               # Desktop capture, interactive region crop & native clipboard
├── roascan-native/            # C++17 Native Core (`roascan_core`) & CMake build
├── dotnet/                    # Experimental C# / .NET P/Invoke preprocessing bridge (`RoaScan.cs`)
├── examples/                  # End-to-end Python usage examples
└── tests/                     # Automated pytest suite (`test_functional_ocr.py`, `test_desktop_and_api.py`)
```

---

## Installation (`pip install`)

```bash
# 1. Core library + CLI + MCP Server:
pip install .

# 2. With desktop tray companion & global shortcut extra:
pip install ".[desktop]"

# Verify installation, native C++ core, and ONNX models:
roascan --doctor
```

---

## 1. Python API (`roascan.run_ocr`)

Stable bridge contract supporting file paths, PIL images, or raw image bytes without network dependencies:

```python
import roascan

# Run local OCR with automatic language correction & Markdown reconstruction
result = roascan.run_ocr("factura.png", language="es")

# Standard bridge contract attributes:
print(result.text)          # Reconstructed plain text
print(result.markdown)      # Structured Markdown with tables & headings
print(len(result.words))    # Detected words with bboxes & confidences
print(result.confidences)   # List of word confidence scores

# Copy recognized text directly to the Windows clipboard:
result.copy_to_clipboard()

# Save structured Markdown:
result.save_markdown("factura.md")

# Access as dictionary mapping:
data = result.to_dict()
```

---

## 2. CLI Usage (`roascan`)

```bash
# 1. OCR a file and copy text directly to clipboard:
roascan ocr factura.png --out factura.md --copy

# 2. Interactive desktop region capture (Tkinter overlay -> OCR -> clipboard):
roascan clip

# 3. Capture specific coordinates without interactive prompt:
roascan clip --bbox 100,100,700,500 --out recorte.md

# 4. Convert a scanned multi-page PDF into both Searchable PDF and Markdown:
roascan scan.pdf --pdf limpio.pdf --md out.md --lang es

# 5. Output unified, versioned JSON (includes ocr_elapsed_ms and total elapsed_ms):
roascan factura.pdf --json

# 6. Run environment & model health check:
roascan --doctor
```

---

## 3. Desktop Screen Capture & Tray Companion (`roascan.desktop`)

RoaScan includes an offline desktop companion (clean-room design: zero cloud, zero accounts, zero telemetry):

### 3.1. System Tray Companion (`roascan tray` / `roascan-tray`)
Starts a lightweight background companion in the Windows notification area with a global shortcut:
- **Default Global Shortcut:** `Ctrl+Shift+O` (triggers interactive region crop -> OCR -> copies text to clipboard).
- **Tray Menu:** "OCR región" (triggers capture), "Salir" (clean shutdown).
- **Anti-Reentrancy Lock:** Prevents overlapping captures if the shortcut is pressed repeatedly.

```bash
# Launch background system tray companion (default hotkey Ctrl+Shift+O):
roascan tray
# or
roascan-tray
# or
python -m roascan.desktop

# Custom hotkey or tray-only mode:
roascan tray --hotkey "Ctrl+Alt+O"
roascan tray --no-hotkey  # tray menu only
roascan tray --ui-lang en # English interface
```

> **Windows Hotkey Note:** Global shortcuts registered via `pynput` run in normal user mode and do not require administrative privileges. However, when an elevated administrator window (UAC) has active focus, Windows restricts non-elevated global keyhooks. To change the shortcut permanently without CLI flags, use `roascan config set hotkey "Ctrl+Alt+O"` or set `ROASCAN_HOTKEY="Ctrl+Alt+O"`.

### 3.2. Result Inspection & Editing Panel (P5)

When a region or clip is recognized, RoaScan automatically opens a lightweight, non-blocking result window:
- **Editable Text Area**: Review, edit, or format the recognized text before saving or copying.
- **Copy**: Places the *currently edited* text onto the system clipboard.
- **Save**: Exports the text as structured Markdown (`.md`) or plain text (`.txt`) to the configured `save_dir` (default: `~/Documents/RoaScan`).
- **Close / Escape**: Dismisses the panel cleanly while keeping the background tray companion alive.
- **Single Instance**: Triggering another OCR updates the active panel and brings it to the front rather than stacking multiple windows.

```bash
# Open interactive result panel directly from CLI clip:
roascan clip --panel
```

### 3.3. User Preferences & Localization (P6)

RoaScan stores user preferences in standard platform directories (`%LOCALAPPDATA%/roascan/config.json` on Windows or `~/.config/roascan/config.json` on Linux/macOS via `platformdirs`).

#### CLI Configuration Management:
```bash
# View active configuration and defaults:
roascan config show

# Get the path to config.json:
roascan config path

# Change preferences:
roascan config set hotkey "Ctrl+Shift+O"
roascan config set ui_lang "en"         # "es" or "en"
roascan config set ocr_lang "es"        # "es", "en", "latin"
roascan config set show_result_panel true
roascan config set copy_on_success true
roascan config set save_dir "D:/MisDocumentos/OCR"
```

#### Precedence Order:
`CLI Flags > Environment Variables (e.g. ROASCAN_HOTKEY, ROASCAN_UI_LANG) > config.json > Default Values`.

### 3.4. Programmatic Desktop Capture, Panel & Clipboard API

```python
from roascan.desktop import (
    capture_region_and_ocr,
    show_result_panel,
    copy_to_clipboard,
    get_clipboard_text,
    load_config,
)

# 1. Capture screen region -> local OCR -> show result editor:
result = capture_region_and_ocr(interactive=True, copy_clipboard=True, language="es")
if result and result.text:
    show_result_panel(result.text, blocking=True)

# 2. Read or write native Windows clipboard without external dependencies:
copy_to_clipboard("Texto copiado desde RoaScan")
print("Clipboard actual:", get_clipboard_text())
```

---

## 4. Model Context Protocol (MCP) Server

Start the MCP server over `stdio`:

```bash
roascan --mcp
# or
roascan-mcp
```

### Claude Desktop / Cursor / Antigravity `mcp_config.json`:

```json
{
  "mcpServers": {
    "roascan": {
      "command": "roascan-mcp",
      "args": [],
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

---

## 3. Licensing & Third-Party Notices

- **RoaScan Source Code (C++17 & Python)**: Licensed under the **Apache License 2.0** (see [`LICENSE`](https://github.com/edisonroaa-code/roascan/blob/main/LICENSE)).
- **Bundled Neural Models (`roascan/models/*.onnx`, `*_dict.txt`)**: Derived from PaddleOCR under **Apache License 2.0**. Exact bundled SHA-256 checksums and an example `paddle2onnx` export command are documented in [`NOTICE`](https://github.com/edisonroaa-code/roascan/blob/main/NOTICE).
- **Bundled Spanish Orthographic Dictionary (`roascan/models/es_ES.dic`)**: Unmodified plain-text dictionary from RLA-ES v2.8, distributed under the elected **Mozilla Public License Version 1.1 (`MPL-1.1`)** option (see [`NOTICE`](https://github.com/edisonroaa-code/roascan/blob/main/NOTICE) and [`THIRD_PARTY_LICENSES.txt`](https://github.com/edisonroaa-code/roascan/blob/main/THIRD_PARTY_LICENSES.txt)).
- **Runtime Dependency `PyMuPDF` (`fitz`)**: Not bundled or redistributed in RoaScan packages; installed from PyPI at runtime under **AGPL-3.0** (or commercial license from Artifex Software, Inc.). See [`NOTICE`](https://github.com/edisonroaa-code/roascan/blob/main/NOTICE) for compliance details.
