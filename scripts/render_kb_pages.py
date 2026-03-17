"""
render_kb_pages.py
------------------
One-time script. Renders every page of the three SP50 PDFs as PNG images
and saves them to gard-backend/static/kb_pages/<source_key>/page_<NNN>.png

Run once from the gard-backend directory:
    python scripts/render_kb_pages.py

Requires: pymupdf (pip install pymupdf)
"""

import os
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip3 install pymupdf")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config — PDF source files and their short key names
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_DIR = os.path.dirname(BACKEND_DIR)

PDF_SOURCES = {
    "user_manual":       os.path.join(PROJECT_DIR, "1CenoBots SP50 User Manual.pdf"),
    "mr_manual":         os.path.join(PROJECT_DIR, "4.SP50 Maintenance and Repair Manual.pdf"),
    "maintenance_guide": os.path.join(PROJECT_DIR, "2.SP50 End User Maintenance Guide.pdf"),
}

OUTPUT_BASE = os.path.join(BACKEND_DIR, "static", "kb_pages")

# Resolution: 150 DPI is crisp enough for a UI thumbnail/modal, keeps file size small
DPI = 150
MAT = fitz.Matrix(DPI / 72, DPI / 72)


def render_pdf(source_key: str, pdf_path: str):
    if not os.path.exists(pdf_path):
        print(f"  SKIP — file not found: {pdf_path}")
        return

    out_dir = os.path.join(OUTPUT_BASE, source_key)
    os.makedirs(out_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    total = len(doc)
    print(f"  Rendering {total} pages → {out_dir}")

    for page_num in range(total):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=MAT, alpha=False)
        # Pages are 1-indexed in citations (e.g. "p.32"), so filename uses 1-based index
        out_path = os.path.join(out_dir, f"page_{(page_num + 1):03d}.png")
        pix.save(out_path)

    doc.close()
    print(f"  Done — {total} pages saved.")


def main():
    print(f"Output directory: {OUTPUT_BASE}\n")
    for key, path in PDF_SOURCES.items():
        print(f"[{key}]  {os.path.basename(path)}")
        render_pdf(key, path)
    print("\nAll PDFs rendered. Static files ready to serve.")


if __name__ == "__main__":
    main()
