"""Programmatic citation verification — the anti-hallucination code guarantee.

Pure Python, NO LLM. Confirms that every Citation in a ResponsePacket traces to
text actually retrieved from the Vertex AI Search datastore (captured into
LegalContext.retrieved_evidence). A citation is "verified" iff:

  (a) its section/rule/circular reference appears in the retrieved text
      (e.g. "section 73", "rule 88d", "31/05/2018"), OR
  (b) a run of consecutive words from its snippet appears in the retrieved text
      (covers rules whose number isn't printed in the chunk body).

Citations with no backing are reported and dropped, so a fabricated source_id
can never reach the filed reply. The retrieved text is treated purely as data
for substring matching — never executed, never used to build paths.
"""

from __future__ import annotations

import re
from typing import Iterable

from noticeflow.schemas import (
    Citation,
    CitationVerification,
    ResponsePacket,
    RetrievedChunk,
)

# Non-alphanumeric runs collapse to a single space, so "Section 73(1)" and
# "Sec. 73" both normalize toward a comparable "section 73 ..." form.
_NONALNUM_RE = re.compile(r"[^a-z0-9]+")
_SECTION_RE = re.compile(r"(?:section|sec)\s*\.?\s*(\d+[a-z]?)", re.IGNORECASE)
_RULE_RE = re.compile(r"rule\s*\.?\s*(\d+[a-z]?)", re.IGNORECASE)
_CIRCULAR_RE = re.compile(r"(\d{1,3}/\d{1,2}/\d{4})")
_CIRCULAR_SHORT_RE = re.compile(r"circular[^0-9]{0,12}(\d{1,4})", re.IGNORECASE)

# A snippet "overlaps" retrieved text if this many consecutive words co-occur.
# 6 is long enough to make accidental matches on boilerplate vanishingly rare,
# short enough to tolerate minor paraphrase at the snippet's edges.
_MIN_SNIPPET_NGRAM = 6


def _normalize(s: str) -> str:
    """Lowercase, collapse non-alphanumeric runs to single spaces."""
    return _NONALNUM_RE.sub(" ", s.lower()).strip()


def _extract_refs(source_id: str) -> set[str]:
    """Normalized search tokens (section/rule/circular ids) from a source_id."""
    refs: set[str] = set()
    for m in _SECTION_RE.finditer(source_id):
        refs.add(_normalize(f"section {m.group(1)}"))
    for m in _RULE_RE.finditer(source_id):
        refs.add(_normalize(f"rule {m.group(1)}"))
    for m in _CIRCULAR_RE.finditer(source_id):
        refs.add(_normalize(m.group(1)))
    for m in _CIRCULAR_SHORT_RE.finditer(source_id):
        refs.add(_normalize(m.group(1)))
    return refs


def _build_haystack(evidence: Iterable[RetrievedChunk]) -> str:
    """Space-padded normalized concatenation of all retrieved text + titles.

    Padding lets us match whole tokens with f" {token} " so "section 73" does
    not spuriously match "section 730".
    """
    parts: list[str] = []
    for ch in evidence:
        if ch.title:
            parts.append(_normalize(ch.title))
        if ch.text:
            parts.append(_normalize(ch.text))
    return " " + " ".join(parts) + " "


def _token_in(token: str, haystack: str) -> bool:
    return bool(token) and f" {token} " in haystack


def _snippet_overlaps(snippet: str, haystack: str) -> bool:
    words = _normalize(snippet).split()
    if not words:
        return False
    if len(words) < _MIN_SNIPPET_NGRAM:
        return _token_in(" ".join(words), haystack)
    for i in range(len(words) - _MIN_SNIPPET_NGRAM + 1):
        gram = " ".join(words[i : i + _MIN_SNIPPET_NGRAM])
        if _token_in(gram, haystack):
            return True
    return False


def _is_verified(citation: Citation, haystack: str) -> bool:
    if any(_token_in(ref, haystack) for ref in _extract_refs(citation.source_id)):
        return True
    return _snippet_overlaps(citation.snippet, haystack)


def verify_citations(
    citations: list[Citation],
    evidence: list[RetrievedChunk],
) -> CitationVerification:
    """Pure check: which citations trace to retrieved text. No mutation.

    With no evidence, nothing can be verified — every citation is reported as
    unverified (passed=False).
    """
    haystack = _build_haystack(evidence)
    have_evidence = bool(evidence)
    unverified: list[str] = []
    verified = 0
    for c in citations:
        if have_evidence and _is_verified(c, haystack):
            verified += 1
        else:
            unverified.append(c.source_id)
    return CitationVerification(
        total_citations=len(citations),
        verified=verified,
        unverified=unverified,
        passed=not unverified,
    )


def apply_citation_verification(
    packet: ResponsePacket,
    evidence: list[RetrievedChunk],
) -> ResponsePacket:
    """Attach a CitationVerification audit and drop unverified citations.

    Safety: when evidence is present, unverified citations are dropped (the
    anti-hallucination guarantee). When evidence is ABSENT, verification could
    not run (an operational issue, not a fabrication) — citations are retained
    and the audit records passed=False so the gap is visible, rather than
    silently destroying a legitimate reply's citations.
    """
    result = verify_citations(packet.citations, evidence)
    if evidence:
        haystack = _build_haystack(evidence)
        kept = [c for c in packet.citations if _is_verified(c, haystack)]
    else:
        kept = packet.citations
    return packet.model_copy(
        update={"citations": kept, "citation_verification": result}
    )


def collect_grounding(event, evidence: list[RetrievedChunk], seen: set) -> None:
    """Accumulate retrieved chunks from one ADK event into `evidence` (deduped).

    Duck-typed against event.grounding_metadata.grounding_chunks[]
    .retrieved_context.{title,uri,text} — the shape confirmed live on the SDK.
    Safe to call on every event; no-ops when an event carries no grounding.
    """
    gm = getattr(event, "grounding_metadata", None)
    if gm is None:
        return
    for ch in getattr(gm, "grounding_chunks", None) or []:
        rc = getattr(ch, "retrieved_context", None)
        text = getattr(rc, "text", None) if rc is not None else None
        if not text:
            continue
        uri = getattr(rc, "uri", "") or ""
        key = (uri, text[:80])
        if key in seen:
            continue
        seen.add(key)
        evidence.append(
            RetrievedChunk(title=getattr(rc, "title", "") or "", uri=uri, text=text)
        )
