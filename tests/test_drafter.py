"""
Drafter tests.

Offline: schema parsing, deadline computation, fallback, citation filtering.
Integration: gated on GOOGLE_CLOUD_PROJECT env var.
"""

import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from noticeflow.schemas import (
    Citation, ClassifiedNotice, LegalContext, NoticeType, ReconciliationData, ResponsePacket,
)
from noticeflow.agents.drafter import (
    _AnnexureOut,
    _DrafterOutput,
    _ERP_SERVER_PATH,
    _build_prompt,
    _fallback_packet,
    _parse_response,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _notice() -> ClassifiedNotice:
    return ClassifiedNotice(
        notice_type=NoticeType.DRC_01,
        governing_sections=["Section 73", "Section 50"],
        gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24",
        response_deadline=date(2026, 6, 10),
        demanded_amount=105900.0,
        issue_summary="Short payment due to excess ITC claimed.",
        raw_extracted_text="<notice>",
        confidence=0.95,
    )


def _legal_ctx() -> LegalContext:
    return LegalContext(
        notice_type=NoticeType.DRC_01,
        citations=[
            Citation(
                source_id="CGST Act 2017, Section 73",
                source_type="act",
                snippet="Where any tax has not been paid or short paid...",
                relevance_note="Governs demand for short payment.",
            ),
            Citation(
                source_id="Circular 31/05/2018-GST",
                source_type="circular",
                snippet="The proper officer shall issue SCN...",
                relevance_note="Defines officer authority.",
            ),
        ],
        applicable_response_options=["Explain ITC availment basis."],
        required_annexures=["GSTR-2B vs 3B comparison"],
    )


def _annexure_dict() -> dict:
    return {
        "gstin": "24ABCDE1234F1Z5",
        "tax_period": "FY2023-24",
        "gstr3b_tax_paid": 1450000.0,
        "gstr2b_itc_available": 820000.0,
        "gstr3b_itc_claimed": 905000.0,
        "itc_mismatch_amount": 85000.0,
        "output_tax_liability": 2355000.0,
        "notes": "ITC claimed exceeds 2B.",
    }


def _valid_drafter_output() -> dict:
    return {
        "legal_basis": "Under Section 73 of the CGST Act 2017, the demand is being contested.",
        "reply_body": "1. We submit our reply as follows:\n2. The ITC was validly availed.",
        "cited_source_ids": ["CGST Act 2017, Section 73"],
        "deadline_urgent": False,
        "annexure": _annexure_dict(),
    }


# ── ERP server path ───────────────────────────────────────────────────────────

def test_erp_server_path_is_absolute():
    assert _ERP_SERVER_PATH.is_absolute()


def test_erp_server_path_inside_package():
    # Must resolve inside the noticeflow package, not from user input
    assert "noticeflow" in str(_ERP_SERVER_PATH)
    assert "erp_server.py" in str(_ERP_SERVER_PATH)


# ── Schema validation ─────────────────────────────────────────────────────────

def test_drafter_output_parses_valid():
    out = _DrafterOutput.model_validate(_valid_drafter_output())
    assert out.deadline_urgent is False
    assert out.annexure.itc_mismatch_amount == 85000.0


def test_annexure_out_all_fields():
    a = _AnnexureOut(**_annexure_dict())
    assert a.gstin == "24ABCDE1234F1Z5"
    assert a.notes == "ITC claimed exceeds 2B."


def test_drafter_output_deadline_urgent_true():
    d = {**_valid_drafter_output(), "deadline_urgent": True}
    out = _DrafterOutput.model_validate(d)
    assert out.deadline_urgent is True


# ── Prompt building ───────────────────────────────────────────────────────────

def test_build_prompt_contains_gstin():
    prompt = _build_prompt(_notice(), _legal_ctx())
    assert "24ABCDE1234F1Z5" in prompt


def test_build_prompt_contains_notice_type():
    prompt = _build_prompt(_notice(), _legal_ctx())
    assert "DRC_01" in prompt


def test_build_prompt_contains_citation():
    prompt = _build_prompt(_notice(), _legal_ctx())
    assert "Section 73" in prompt


def test_build_prompt_is_valid_json():
    prompt = _build_prompt(_notice(), _legal_ctx())
    parsed = json.loads(prompt)
    assert "classified_notice" in parsed
    assert "legal_context" in parsed


# ── Response parsing ──────────────────────────────────────────────────────────

def test_parse_response_valid():
    raw = json.dumps(_valid_drafter_output())
    packet = _parse_response(raw, _notice(), _legal_ctx())
    assert isinstance(packet, ResponsePacket)
    assert packet.notice_type == NoticeType.DRC_01
    assert packet.reviewer_status == "PENDING_REVIEW"
    assert packet.annexure.itc_mismatch_amount == 85000.0


def test_parse_response_filters_citations_to_cited_only():
    raw = json.dumps(_valid_drafter_output())  # only cites Section 73
    packet = _parse_response(raw, _notice(), _legal_ctx())
    source_ids = [c.source_id for c in packet.citations]
    assert "CGST Act 2017, Section 73" in source_ids
    # Circular was NOT cited → should be excluded
    assert "Circular 31/05/2018-GST" not in source_ids


def test_parse_response_falls_back_to_all_citations_when_none_match():
    d = {**_valid_drafter_output(), "cited_source_ids": ["nonexistent-source"]}
    raw = json.dumps(d)
    packet = _parse_response(raw, _notice(), _legal_ctx())
    # Should include all citations as fallback
    assert len(packet.citations) == len(_legal_ctx().citations)


def test_parse_response_strips_markdown_fences():
    raw = "```json\n" + json.dumps(_valid_drafter_output()) + "\n```"
    packet = _parse_response(raw, _notice(), _legal_ctx())
    assert isinstance(packet, ResponsePacket)


def test_parse_response_falls_back_on_invalid_json():
    packet = _parse_response("not json at all", _notice(), _legal_ctx())
    assert isinstance(packet, ResponsePacket)
    assert packet.reviewer_status == "PENDING_REVIEW"


def test_parse_response_always_pending_review():
    raw = json.dumps(_valid_drafter_output())
    packet = _parse_response(raw, _notice(), _legal_ctx())
    assert packet.reviewer_status == "PENDING_REVIEW"


# ── Fallback packet ───────────────────────────────────────────────────────────

def test_fallback_packet_structure():
    packet = _fallback_packet(_notice(), _legal_ctx())
    assert packet.notice_type == NoticeType.DRC_01
    assert packet.gstin == "24ABCDE1234F1Z5"
    assert packet.reviewer_status == "PENDING_REVIEW"
    assert packet.annexure.gstin == "24ABCDE1234F1Z5"


def test_fallback_packet_deadline_urgent_within_7_days():
    notice = _notice()
    today = datetime.now(timezone.utc).date()
    notice = notice.model_copy(update={"response_deadline": today + timedelta(days=3)})
    packet = _fallback_packet(notice, _legal_ctx())
    assert packet.deadline_urgent is True


def test_fallback_packet_deadline_not_urgent():
    notice = _notice()
    today = datetime.now(timezone.utc).date()
    notice = notice.model_copy(update={"response_deadline": today + timedelta(days=30)})
    packet = _fallback_packet(notice, _legal_ctx())
    assert packet.deadline_urgent is False


# ── Integration tests ─────────────────────────────────────────────────────────

integration = pytest.mark.skipif(
    not os.environ.get("GOOGLE_CLOUD_PROJECT"),
    reason="GOOGLE_CLOUD_PROJECT not set — skipping live Gemini + MCP call",
)


@integration
@pytest.mark.asyncio
async def test_draft_drc01_live():
    from noticeflow.agents.drafter import draft_response
    packet = await draft_response(_notice(), _legal_ctx())
    assert packet.notice_type == NoticeType.DRC_01
    assert packet.reviewer_status == "PENDING_REVIEW"
    assert len(packet.reply_body) > 100
    assert packet.annexure.gstin == "24ABCDE1234F1Z5"
