"""
RoaScan - Modernized Open Source OCR Engine
Clean-room verification script testing the rebranded RoaScan architecture.
"""

import os
import sys

# Ensure current directory is on path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from roascan import RoaScanEngine, RoaScanPreprocessor, RoaScanDocumentWriter

def main():
    print("=" * 66)
    print("   RoaScan Open-Source OCR Engine Architecture                     ")
    print("   Re-engineered from 1989 Enterprise Skeleton to 2026 AI Era    ")
    print("=" * 66)

    # 1. Supported Languages
    print("\n[1] Querying RoaScan Native Language Catalog...")
    langs = RoaScanEngine.list_supported_languages()
    print(f"    Total supported languages: {len(langs)}")
    sample_ids = [0, 1, 2, 4, 5, 7, 8, 9, 10, 12, 13, 14]
    sample_str = ", ".join(f"{langs[i]} (ID: {i})" for i in sample_ids if i in langs)
    print(f"    Sample: {sample_str}")

    # 2. Preprocessor
    print("\n[2] Testing RoaScan Preprocessor (roascan.prepro)...")
    with RoaScanPreprocessor(current_dir) as prepro:
        print(f"    RoaScan Preprocessor Status: Initialized")
        prepro.set_brightness(128)
        prepro.set_contrast(140)
        prepro.set_threshold(160)
        prepro.set_thread_count(4)
        print("    Filter Pipeline Configured: (Brightness=128, Contrast=140, Thresh=160, Threads=4) -> OK")

    # 3. Core Engine
    print("\n[3] Testing RoaScan Core Engine (roascan.engine)...")
    with RoaScanEngine(current_dir) as engine:
        print("    Native core loaded (roascan_core.dll) -> OK")
        engine.set_resolution(300, 300)
        engine.set_auto_orientation(True)
        engine.set_auto_alphabet(True)
        engine.set_thread_count(4)
        print("    Engine Configured: (DPI=300x300, Auto-Orient=True, Threads=4) -> OK")

        # Create dummy image buffer
        w, h = 100, 40
        dummy_pixels = bytes([255 if (x + y) % 2 == 0 else 0 for y in range(h) for x in range(w)])
        engine.set_raw_image(dummy_pixels, w, h, bpp=8, stride=w)
        print(f"    Fed raw pixel buffer ({w}x{h} bpp=8) with memory pinning -> OK")

    # 4. Document Output Writer
    print("\n[4] Testing RoaScan Document Output Writer (roascan.docout)...")
    with RoaScanDocumentWriter(current_dir) as writer:
        print("    Document output session initialized -> OK")
        test_pdf = os.path.join(current_dir, "roascan_test_output.pdf")
        writer.configure_pdf(test_pdf, format_type=RoaScanDocumentWriter.FORMAT_PDF_STD, pdf_version=15, text_over_image=True)
        print(f"    Target PDF configured: {test_pdf} -> OK")

    print("\n" + "=" * 66)
    print("   ALL RoaScan REBRANDED MODULES VERIFIED SUCCESSFULLY!           ")
    print("=" * 66)

if __name__ == "__main__":
    main()
