"""
kb_pages.py
-----------
FastAPI routes for serving KB page screenshots.

Endpoints:
  GET /api/v1/kb/page?citation=User+Manual+p.32
      → Returns the PNG image for that citation

  GET /api/v1/kb/pages?citations=User+Manual+p.32,M%26R+Manual+p.5
      → Returns a list of { citation, url } objects for the dashboard to render

Citation format accepted (case-insensitive):
  "User Manual p.32"            → user_manual / page_032.png
  "M&R Manual p.5"              → mr_manual   / page_005.png
  "Maintenance & Repair Manual p.5" → mr_manual / page_005.png
  "End User Maintenance Guide p.1"  → maintenance_guide / page_001.png
  "Maintenance Guide p.1"           → maintenance_guide / page_001.png
"""

import os
import re
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter()

# ---------------------------------------------------------------------------
# Path to pre-rendered pages (created by scripts/render_kb_pages.py)
# ---------------------------------------------------------------------------
STATIC_DIR = os.path.join(os.path.dirname(__file__), "../../static/kb_pages")

# ---------------------------------------------------------------------------
# Citation → source_key mapping
# ---------------------------------------------------------------------------
SOURCE_ALIASES = {
    "user manual":                "user_manual",
    "sp50 user manual":           "user_manual",
    "cenobot":                    "user_manual",
    "cenobot user manual":        "user_manual",
    "m&r manual":                 "mr_manual",
    "maintenance & repair manual":"mr_manual",
    "maintenance and repair manual": "mr_manual",
    "maintenance manual":         "mr_manual",
    "repair manual":              "mr_manual",
    "end user maintenance guide": "maintenance_guide",
    "maintenance guide":          "maintenance_guide",
    "end user guide":             "maintenance_guide",
}


def citation_to_path(citation: str) -> str | None:
    """
    Convert a citation string like 'User Manual p.32' to an absolute file path.
    Returns None if the citation cannot be mapped.
    """
    citation = citation.strip()

    # Extract page number — accepts "p.32", "p32", "page 32", "page32"
    page_match = re.search(r"p(?:age)?[\.\s]?(\d+)", citation, re.IGNORECASE)
    if not page_match:
        return None
    page_num = int(page_match.group(1))

    # Remove the page portion and normalise the remainder to find the source key
    source_part = re.sub(r"\s*p(?:age)?[\.\s]?\d+\s*", "", citation, flags=re.IGNORECASE).strip().lower()
    source_key = SOURCE_ALIASES.get(source_part)

    # Fuzzy fallback: check if any alias is a substring of the source_part
    if not source_key:
        for alias, key in SOURCE_ALIASES.items():
            if alias in source_part:
                source_key = key
                break

    if not source_key:
        return None

    filename = f"page_{page_num:03d}.png"
    full_path = os.path.join(STATIC_DIR, source_key, filename)
    return full_path if os.path.exists(full_path) else None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/kb/page")
async def get_kb_page(citation: str = Query(..., description="e.g. 'User Manual p.32'")):
    """
    Return the PNG image for a single citation.
    Used when the dashboard renders a citation inline.
    """
    path = citation_to_path(citation)
    if not path:
        raise HTTPException(
            status_code=404,
            detail=f"No page image found for citation: '{citation}'. "
                   "Run scripts/render_kb_pages.py first."
        )
    return FileResponse(path, media_type="image/png")


@router.get("/kb/pages")
async def get_kb_pages(citations: str = Query(..., description="Comma-separated citation strings")):
    """
    Resolve multiple citations at once.
    Returns: [{ citation, url, found }]
    Used by the post-call dashboard to display all cited pages for a call.
    """
    citation_list = [c.strip() for c in citations.split(",") if c.strip()]
    results = []

    for citation in citation_list:
        path = citation_to_path(citation)
        results.append({
            "citation": citation,
            "url": f"/api/v1/kb/page?citation={citation}" if path else None,
            "found": path is not None,
        })

    return JSONResponse(content={"pages": results})
