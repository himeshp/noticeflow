"""Unit tests for the programmatic citation verifier (no LLM, no GCP)."""

from noticeflow.schemas import (
    Citation,
    NoticeType,
    ReconciliationData,
    ResponsePacket,
    RetrievedChunk,
)
from noticeflow.verify.citations import (
    apply_citation_verification,
    verify_citations,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

def _chunk(text: str, title: str = "cgst_act_2017", uri: str = "gs://c/cgst_act_2017.pdf"):
    return RetrievedChunk(title=title, uri=uri, text=text)


def _cite(source_id: str, snippet: str = "", source_type: str = "act"):
    return Citation(
        source_id=source_id,
        source_type=source_type,
        snippet=snippet,
        relevance_note="n/a",
    )


# Realistic retrieved law text (mirrors what the spike printed).
S73_TEXT = (
    "CHAPTER XV DEMANDS AND RECOVERY 107 73. Determination of tax not paid or "
    "short paid or erroneously refunded or input tax credit wrongly availed or "
    "utilised. Where it appears to the proper officer that any tax has not been "
    "paid under section 73, he shall serve notice."
)
S16_TEXT = (
    "Every registered person shall, subject to such conditions as may be "
    "prescribed under section 16, be entitled to take credit of input tax "
    "charged on any supply of goods or services."
)
CIRC183_TEXT = (
    "Circular No. 183/15/2022 - GST. Clarification to deal with difference in "
    "input tax credit availed in FORM GSTR-3B as compared to GSTR-2A."
)
RULE142_TEXT = (
    "Notice and order for demand of amounts payable under the Act. The proper "
    "officer shall serve a summary electronically in FORM GST DRC-01 specifying "
    "the details of the amount payable."
)


def _packet(citations):
    return ResponsePacket(
        notice_type=NoticeType.DRC_01,
        reference_number="REF-1",
        gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24",
        response_deadline=None,
        deadline_urgent=False,
        legal_basis="basis",
        reply_body="body",
        citations=citations,
        annexure=ReconciliationData(
            gstin="24ABCDE1234F1Z5", tax_period="FY2023-24",
            gstr3b_tax_paid=0.0, gstr2b_itc_available=0.0, gstr3b_itc_claimed=0.0,
            itc_mismatch_amount=0.0, output_tax_liability=0.0,
        ),
    )


# ── verify_citations: section-reference matching ──────────────────────────────

def test_section_reference_verified():
    res = verify_citations([_cite("CGST Act 2017, Section 73")], [_chunk(S73_TEXT)])
    assert res.verified == 1 and res.passed and res.unverified == []


def test_section_reference_normalization_variants():
    evidence = [_chunk(S73_TEXT)]
    for sid in ["Section 73", "Sec. 73", "CGST Act 2017, Section 73(1)", "section 73"]:
        res = verify_citations([_cite(sid)], evidence)
        assert res.passed, f"{sid!r} should verify against retrieved s.73 text"


def test_circular_reference_verified():
    res = verify_citations(
        [_cite("Circular 183/15/2022-GST", source_type="circular")],
        [_chunk(CIRC183_TEXT, title="circular_183")],
    )
    assert res.passed


# ── snippet-overlap fallback (rule number not printed in chunk body) ──────────

def test_snippet_overlap_verifies_when_ref_absent():
    # "rule 142" string is not in RULE142_TEXT, but the snippet is verbatim.
    cite = _cite(
        "CGST Rules 2017, Rule 142",
        snippet="Notice and order for demand of amounts payable under the Act",
        source_type="rule",
    )
    res = verify_citations([cite], [_chunk(RULE142_TEXT, title="cgst_rules_2017")])
    assert res.passed, "verbatim snippet should verify via overlap"


# ── fabrication is caught ─────────────────────────────────────────────────────

def test_fabricated_citation_flagged():
    fake = _cite(
        "CGST Act 2017, Section 999",
        snippet="There shall be a special exemption of ninety percent for all taxpayers.",
    )
    res = verify_citations([fake], [_chunk(S73_TEXT)])
    assert res.verified == 0 and not res.passed
    assert res.unverified == ["CGST Act 2017, Section 999"]


def test_mixed_real_and_fake():
    cites = [_cite("Section 73"), _cite("Section 999", snippet="invented text here")]
    res = verify_citations(cites, [_chunk(S73_TEXT)])
    assert res.total_citations == 2 and res.verified == 1
    assert res.unverified == ["Section 999"] and not res.passed


# ── boundary / edge cases ─────────────────────────────────────────────────────

def test_section_boundary_no_false_positive():
    # retrieved text mentions section 730, must NOT verify a citation for s.73
    res = verify_citations([_cite("Section 73")], [_chunk("levy under section 730 applies")])
    assert not res.passed


def test_empty_evidence_all_unverified():
    res = verify_citations([_cite("Section 73"), _cite("Section 16")], [])
    assert res.verified == 0 and not res.passed and len(res.unverified) == 2


def test_no_citations_passes_vacuously():
    res = verify_citations([], [_chunk(S73_TEXT)])
    assert res.total_citations == 0 and res.verified == 0 and res.passed


# ── apply_citation_verification: dropping + audit ─────────────────────────────

def test_apply_drops_unverified_when_evidence_present():
    pkt = _packet([_cite("Section 73"), _cite("Section 999", snippet="made up")])
    out = apply_citation_verification(pkt, [_chunk(S73_TEXT)])
    kept = [c.source_id for c in out.citations]
    assert kept == ["Section 73"]
    assert out.citation_verification.total_citations == 2
    assert out.citation_verification.verified == 1
    assert out.citation_verification.unverified == ["Section 999"]
    assert out.citation_verification.passed is False


def test_apply_keeps_all_when_evidence_absent():
    # degraded mode: can't verify -> retain citations, but flag passed=False
    pkt = _packet([_cite("Section 73"), _cite("Section 16")])
    out = apply_citation_verification(pkt, [])
    assert len(out.citations) == 2  # not destroyed
    assert out.citation_verification.passed is False
    assert out.citation_verification.verified == 0


def test_apply_all_verified_passes():
    pkt = _packet([_cite("Section 73"), _cite("Section 16")])
    out = apply_citation_verification(pkt, [_chunk(S73_TEXT), _chunk(S16_TEXT)])
    assert len(out.citations) == 2
    assert out.citation_verification.passed is True
    assert out.citation_verification.verified == 2
