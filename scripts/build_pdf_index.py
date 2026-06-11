"""scripts/build_pdf_index.py — OFFLINE/build-time only.

Parse the bundled CBIC PDFs and emit data/source_pdf_index.json, mapping each
section/rule reference to its 1-based page, so the in-app source viewer can fall
back to the right page when pdf.js find can't locate the passage.

Build-time only — needs the `tools` extra (pypdf). The runtime reads only the
committed JSON.

Usage:
    pip install -e ".[tools]"
    python scripts/build_pdf_index.py
"""

from __future__ import annotations

import json
import pathlib
import re

from pypdf import PdfReader

from noticeflow.verify.citations import _normalize

REPO = pathlib.Path(__file__).resolve().parents[1]
PDF_DIR = REPO / "data" / "source_pdfs"
OUT = REPO / "data" / "source_pdf_index.json"

# doc_key -> (filename, ref-label). Circulars are short -> no index (viewer uses page 1).
DOCS = {
    "cgst_act_2017": ("cgst_act_2017.pdf", "section"),
    "cgst_rules_2017": ("cgst_rules_2017.pdf", "rule"),
}

# A heading at a line start: "73. Determination ...", "88D. Manner ...".
_HEADING_RE = re.compile(r"(?m)^\s*(\d{1,3}[A-Za-z]?)\.\s+\S")
# Table-of-contents / arrangement pages — skip so we record the body page, not the TOC.
_TOC_MARKERS = ("ARRANGEMENT OF SECTIONS", "ARRANGEMENT OF RULES", "CONTENTS", "INDEX")


def _index_doc(path: pathlib.Path, label: str) -> dict[str, int]:
    reader = PdfReader(str(path))
    refs: dict[str, int] = {}
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if any(marker in text.upper() for marker in _TOC_MARKERS):
            continue  # skip TOC pages
        for m in _HEADING_RE.finditer(text):
            key = _normalize(f"{label} {m.group(1)}")
            refs.setdefault(key, page_num)  # first body occurrence wins
    return refs


def main() -> None:
    index: dict[str, dict[str, int]] = {}
    for doc_key, (filename, label) in DOCS.items():
        path = PDF_DIR / filename
        if not path.exists():
            print(f"  SKIP {doc_key}: {filename} not found")
            continue
        refs = _index_doc(path, label)
        index[doc_key] = refs
        print(f"  {doc_key}: {len(refs)} {label} refs indexed")
    OUT.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(REPO)}")
    # Spot-check a few well-known references.
    for doc, ref in [("cgst_act_2017", "section 73"), ("cgst_act_2017", "section 16"),
                     ("cgst_act_2017", "section 61"), ("cgst_rules_2017", "rule 88d"),
                     ("cgst_rules_2017", "rule 142")]:
        print(f"    {doc} / {ref!r} -> page {index.get(doc, {}).get(ref)}")


if __name__ == "__main__":
    main()
