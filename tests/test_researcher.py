"""
Researcher tests.

Offline tests: query building, schema parsing, fallback logic — zero GCP calls.
Integration tests: marked skip unless GOOGLE_CLOUD_PROJECT + VERTEX_SEARCH_DATASTORE_ID set.
"""

import json
import os
import pathlib

import pytest

from noticeflow.schemas import Citation, ClassifiedNotice, LegalContext, NoticeType
from noticeflow.agents.researcher import (
    _REQUIRED_ANNEXURES,
    _ResearcherOutput,
    _CitationOut,
    _build_query,
    _fallback_context,
    _parse_response,
)

SAMPLE_DIR = pathlib.Path(__file__).parents[1] / "data" / "sample_notices"


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _notice(notice_type: NoticeType, sections: list[str]) -> ClassifiedNotice:
    return ClassifiedNotice(
        notice_type=notice_type,
        governing_sections=sections,
        gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24",
        issue_summary="Short payment of tax alleged.",
        raw_extracted_text="<notice text>",
        confidence=0.95,
    )


DRC01_NOTICE = _notice(NoticeType.DRC_01, ["Section 73", "Section 50"])
ASMT10_NOTICE = _notice(NoticeType.ASMT_10, ["Section 61"])
ITC_NOTICE = _notice(NoticeType.ITC_MISMATCH, ["Section 16"])
UNKNOWN_NOTICE = _notice(NoticeType.UNKNOWN, [])


# ── Query building ────────────────────────────────────────────────────────────

def test_build_query_drc01_contains_section73():
    q = _build_query(DRC01_NOTICE)
    assert "73" in q


def test_build_query_asmt10_contains_section61():
    q = _build_query(ASMT10_NOTICE)
    assert "61" in q


def test_build_query_itc_contains_section16():
    q = _build_query(ITC_NOTICE)
    assert "16" in q


def test_build_query_unknown_returns_general():
    q = _build_query(UNKNOWN_NOTICE)
    assert len(q) > 0


def test_build_query_appends_extra_governing_sections():
    notice = _notice(NoticeType.DRC_01, ["Section 73", "Section 122"])
    q = _build_query(notice)
    assert "122" in q


# ── Schema validation ─────────────────────────────────────────────────────────

def _make_researcher_output(**kwargs) -> dict:
    defaults = dict(
        citations=[{
            "source_id": "CGST Act 2017, Section 73",
            "source_type": "act",
            "snippet": "Where any tax has not been paid...",
            "relevance_note": "Governs demand for short payment.",
        }],
        applicable_response_options=["Explain ITC availment basis."],
        required_annexures=["GSTR-2B vs 3B comparison"],
    )
    defaults.update(kwargs)
    return defaults


def test_researcher_output_parses_valid_json():
    raw = _make_researcher_output()
    out = _ResearcherOutput.model_validate(raw)
    assert len(out.citations) == 1
    assert out.citations[0].source_type == "act"


def test_researcher_output_empty_citations_allowed():
    raw = _make_researcher_output(citations=[])
    out = _ResearcherOutput.model_validate(raw)
    assert out.citations == []


def test_citation_out_all_fields():
    c = _CitationOut(
        source_id="Circular 31/05/2018-GST",
        source_type="circular",
        snippet="The proper officer shall...",
        relevance_note="Defines officer authority under Sec 73.",
    )
    assert c.source_type == "circular"


# ── Response parsing ──────────────────────────────────────────────────────────

def test_parse_response_valid_json():
    payload = json.dumps(_make_researcher_output())
    result = _parse_response(payload, DRC01_NOTICE)
    assert isinstance(result, LegalContext)
    assert result.notice_type == NoticeType.DRC_01
    assert len(result.citations) == 1
    assert result.citations[0].source_id == "CGST Act 2017, Section 73"


def test_parse_response_strips_markdown_fences():
    payload = "```json\n" + json.dumps(_make_researcher_output()) + "\n```"
    result = _parse_response(payload, DRC01_NOTICE)
    assert isinstance(result, LegalContext)
    assert len(result.citations) == 1


def test_parse_response_falls_back_on_invalid_json():
    result = _parse_response("this is not json at all", DRC01_NOTICE)
    assert isinstance(result, LegalContext)
    assert len(result.citations) == 1
    assert "this is not json at all" in result.citations[0].snippet


def test_parse_response_falls_back_on_empty_string():
    result = _parse_response("", DRC01_NOTICE)
    assert isinstance(result, LegalContext)


def test_parse_response_uses_default_annexures_when_empty():
    payload = json.dumps(_make_researcher_output(required_annexures=[]))
    result = _parse_response(payload, DRC01_NOTICE)
    # Falls back to deterministic annexures for DRC_01
    assert result.required_annexures == _REQUIRED_ANNEXURES[NoticeType.DRC_01]


# ── Fallback context ──────────────────────────────────────────────────────────

def test_fallback_context_structure():
    ctx = _fallback_context(DRC01_NOTICE)
    assert ctx.notice_type == NoticeType.DRC_01
    assert len(ctx.citations) == 1
    assert ctx.citations[0].source_type == "act"
    assert len(ctx.applicable_response_options) >= 1
    assert ctx.required_annexures == _REQUIRED_ANNEXURES[NoticeType.DRC_01]


def test_fallback_context_unknown_type():
    ctx = _fallback_context(UNKNOWN_NOTICE)
    assert ctx.notice_type == NoticeType.UNKNOWN


def test_required_annexures_all_notice_types_covered():
    for nt in (NoticeType.DRC_01, NoticeType.ASMT_10, NoticeType.ITC_MISMATCH):
        assert nt in _REQUIRED_ANNEXURES
        assert len(_REQUIRED_ANNEXURES[nt]) > 0


# ── Integration tests (require GCP + configured datastore) ───────────────────

integration = pytest.mark.skipif(
    not (os.environ.get("GOOGLE_CLOUD_PROJECT") and os.environ.get("VERTEX_SEARCH_DATASTORE_ID")),
    reason="GOOGLE_CLOUD_PROJECT or VERTEX_SEARCH_DATASTORE_ID not set",
)


@integration
@pytest.mark.asyncio
async def test_research_drc01_live():
    from noticeflow.agents.researcher import research_notice
    text = (SAMPLE_DIR / "drc01_sec73.txt").read_text(encoding="utf-8")
    notice = ClassifiedNotice(
        notice_type=NoticeType.DRC_01,
        governing_sections=["Section 73", "Section 50"],
        gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24",
        issue_summary="Short payment of tax due to excess ITC claimed.",
        raw_extracted_text=text,
        confidence=0.95,
    )
    result = await research_notice(notice)
    assert result.notice_type == NoticeType.DRC_01
    assert len(result.citations) >= 1
    # At least one citation must reference Section 73
    sources = " ".join(c.source_id for c in result.citations)
    assert "73" in sources, f"Expected Section 73 citation, got: {sources}"


@integration
@pytest.mark.asyncio
async def test_research_itc_mismatch_live():
    from noticeflow.agents.researcher import research_notice
    notice = ClassifiedNotice(
        notice_type=NoticeType.ITC_MISMATCH,
        governing_sections=["Section 16"],
        gstin="29LMNOP9012H3Z4",
        tax_period="04/2024",
        issue_summary="ITC claimed exceeds GSTR-2B by Rs 45,000.",
        raw_extracted_text="",
        confidence=0.92,
    )
    result = await research_notice(notice)
    assert result.notice_type == NoticeType.ITC_MISMATCH
    assert len(result.citations) >= 1
    sources = " ".join(c.source_id for c in result.citations)
    assert "16" in sources, f"Expected Section 16 citation, got: {sources}"
