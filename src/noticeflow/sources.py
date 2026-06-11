"""Map a citation to its source PDF + page for the in-app pdf.js viewer.

Pure + fail-safe. Resolves each Citation to one of the 5 bundled CBIC PDFs
(allow-listed) and, via an offline-built section/rule -> page index, the page the
cited provision sits on. The cockpit's /api/source endpoint serves ONLY the
allow-listed filenames (no path built from raw input).

Reuses the section/rule regexes + normalizer from verify/citations.py so the
index keys and the lookup keys are produced identically.
"""

from __future__ import annotations

import json
import pathlib
import re
from functools import lru_cache
from typing import Optional

from noticeflow.schemas import ResponsePacket
from noticeflow.verify.citations import _RULE_RE, _SECTION_RE, _normalize

# Allow-list: doc_key -> filename. ONLY these are ever resolved or served.
DOC_FILES: dict[str, str] = {
    "cgst_act_2017": "cgst_act_2017.pdf",
    "cgst_rules_2017": "cgst_rules_2017.pdf",
    "circular_31_2018": "circular_31_2018_sec73_74.pdf",
    "circular_135_2020": "circular_135_2020_itc_sec16.pdf",
    "circular_183_2022": "circular_183_2022_sec16_itc.pdf",
}

_CIRCULAR_NUM_RE = re.compile(r"circular[^0-9]{0,8}(\d{1,3})", re.IGNORECASE)
_CIRCULAR_TO_DOC = {
    "31": "circular_31_2018",
    "135": "circular_135_2020",
    "183": "circular_183_2022",
}

_REPO = pathlib.Path(__file__).resolve().parents[2]
_PDF_DIR = _REPO / "data" / "source_pdfs"
_INDEX_PATH = _REPO / "data" / "source_pdf_index.json"


@lru_cache(maxsize=1)
def _index() -> dict:
    """The committed section/rule -> page index ({doc_key: {ref: page}}). {} if absent."""
    try:
        data = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_doc(source_type: str, source_id: str) -> Optional[str]:
    """Which bundled PDF backs this citation, or None if not one of the 5."""
    st = (source_type or "").strip().lower()
    sid = source_id or ""
    low = sid.lower()
    if st == "circular" or "circular" in low:
        m = _CIRCULAR_NUM_RE.search(sid)
        return _CIRCULAR_TO_DOC.get(m.group(1)) if m else None
    if st == "rule" or _RULE_RE.search(sid):
        return "cgst_rules_2017"
    if st == "act" or _SECTION_RE.search(sid) or "act" in low:
        return "cgst_act_2017"
    return None


def lookup_page(doc_key: Optional[str], source_id: str) -> Optional[int]:
    """1-based page of the cited section/rule in doc_key, or None. Circulars -> 1."""
    if not doc_key:
        return None
    if doc_key.startswith("circular_"):
        return 1
    refs = _index().get(doc_key) or {}
    if not refs:
        return None
    for m in _SECTION_RE.finditer(source_id or ""):
        page = refs.get(_normalize(f"section {m.group(1)}"))
        if page:
            return int(page)
    for m in _RULE_RE.finditer(source_id or ""):
        page = refs.get(_normalize(f"rule {m.group(1)}"))
        if page:
            return int(page)
    return None


def source_pdf_path(doc_key: str) -> Optional[pathlib.Path]:
    """Resolved path of an allow-listed PDF, or None. Path is built only from the
    allow-list filename constant — never from raw client input."""
    filename = DOC_FILES.get(doc_key)
    if not filename:
        return None
    path = (_PDF_DIR / filename).resolve()
    if not path.is_relative_to(_PDF_DIR.resolve()) or not path.exists():
        return None
    return path


def annotate_citation_sources(packet: ResponsePacket) -> ResponsePacket:
    """Attach source_doc + source_page to every citation (pure, fail-safe)."""
    try:
        annotated = [
            c.model_copy(update={
                "source_doc": (doc := resolve_doc(c.source_type, c.source_id)),
                "source_page": lookup_page(doc, c.source_id),
            })
            for c in packet.citations
        ]
        return packet.model_copy(update={"citations": annotated})
    except Exception:
        return packet
