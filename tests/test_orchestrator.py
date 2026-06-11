"""
Orchestrator tests.

Offline: state key names, human gate utilities, UNKNOWN short-circuit,
         parse helpers, packet immutability.
Integration: full pipeline gated on GOOGLE_CLOUD_PROJECT + VERTEX_SEARCH_DATASTORE_ID.
"""

import json
import os
import pathlib

import pytest

from noticeflow.schemas import (
    Citation, ClassifiedNotice, LegalContext, NoticeType, ReconciliationData, ResponsePacket,
)
from noticeflow.agents.orchestrator import (
    STATE_CLASSIFIED,
    STATE_LEGAL,
    STATE_PACKET,
    _parse_classified,
    _parse_legal_context,
    approve_packet,
    edit_packet,
)

SAMPLE_DIR = pathlib.Path(__file__).parents[1] / "data" / "sample_notices"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_packet(**kwargs) -> ResponsePacket:
    annexure = ReconciliationData(
        gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24",
        gstr3b_tax_paid=1450000.0,
        gstr2b_itc_available=820000.0,
        gstr3b_itc_claimed=905000.0,
        itc_mismatch_amount=85000.0,
        output_tax_liability=2355000.0,
    )
    defaults = dict(
        notice_type=NoticeType.DRC_01,
        reference_number="ZD2403240001234",
        gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24",
        response_deadline=None,
        deadline_urgent=False,
        legal_basis="Under Section 73 CGST Act.",
        reply_body="Draft reply body.",
        citations=[],
        annexure=annexure,
        reviewer_status="PENDING_REVIEW",
    )
    defaults.update(kwargs)
    return ResponsePacket(**defaults)


# ── State key names ───────────────────────────────────────────────────────────

def test_state_key_names_are_stable():
    assert STATE_CLASSIFIED == "classified_notice_json"
    assert STATE_LEGAL == "legal_context_json"
    assert STATE_PACKET == "response_packet_json"


# ── Human gate ────────────────────────────────────────────────────────────────

def test_approve_packet_sets_approved():
    packet = _make_packet()
    assert packet.reviewer_status == "PENDING_REVIEW"
    approved = approve_packet(packet)
    assert approved.reviewer_status == "APPROVED"


def test_approve_packet_does_not_mutate_original():
    packet = _make_packet()
    approve_packet(packet)
    assert packet.reviewer_status == "PENDING_REVIEW"  # original unchanged


def test_edit_packet_sets_edited():
    packet = _make_packet()
    edited = edit_packet(packet, reply_body="Corrected reply.")
    assert edited.reviewer_status == "EDITED"
    assert edited.reply_body == "Corrected reply."


def test_edit_packet_does_not_mutate_original():
    packet = _make_packet()
    edit_packet(packet, reply_body="Changed")
    assert packet.reply_body == "Draft reply body."


def test_edit_packet_preserves_other_fields():
    packet = _make_packet()
    edited = edit_packet(packet, reply_body="New reply.")
    assert edited.gstin == packet.gstin
    assert edited.notice_type == packet.notice_type


# ── _parse_classified ─────────────────────────────────────────────────────────

def _classifier_json(notice_type: str = "DRC_01") -> str:
    return json.dumps({
        "notice_type": notice_type,
        "governing_sections": ["Section 73"],
        "reference_number": "ZD123",
        "gstin": "24ABCDE1234F1Z5",
        "tax_period": "FY2023-24",
        "response_deadline": "2026-06-20",
        "demanded_amount": 105900.0,
        "issue_summary": "Short payment alleged.",
        "confidence": 0.95,
    })


def test_parse_classified_valid():
    notice = _parse_classified(_classifier_json())
    assert notice is not None
    assert notice.notice_type == NoticeType.DRC_01
    assert notice.gstin == "24ABCDE1234F1Z5"


def test_parse_classified_unknown_type():
    notice = _parse_classified(_classifier_json(notice_type="UNKNOWN"))
    assert notice is not None
    assert notice.notice_type == NoticeType.UNKNOWN


def test_parse_classified_invalid_json_returns_none():
    assert _parse_classified("not json") is None


def test_parse_classified_empty_string_returns_none():
    assert _parse_classified("") is None


def test_parse_classified_strips_markdown_fences():
    raw = "```json\n" + _classifier_json() + "\n```"
    notice = _parse_classified(raw)
    assert notice is not None
    assert notice.notice_type == NoticeType.DRC_01


def test_parse_classified_deadline_parsed():
    notice = _parse_classified(_classifier_json())
    from datetime import date
    assert notice.response_deadline == date(2026, 6, 20)


# ── _parse_legal_context ──────────────────────────────────────────────────────

def _legal_json() -> str:
    return json.dumps({
        "citations": [{
            "source_id": "CGST Act 2017, Section 73",
            "source_type": "act",
            "snippet": "Where any tax has not been paid...",
            "relevance_note": "Governs demand for short payment.",
        }],
        "applicable_response_options": ["Explain ITC basis."],
        "required_annexures": ["GSTR-2B vs 3B"],
    })


def _stub_notice() -> ClassifiedNotice:
    return ClassifiedNotice(
        notice_type=NoticeType.DRC_01,
        governing_sections=["Section 73"],
        issue_summary="Short payment.",
        raw_extracted_text="",
        confidence=0.9,
    )


def test_parse_legal_context_valid():
    ctx = _parse_legal_context(_legal_json(), _stub_notice())
    assert ctx is not None
    assert ctx.notice_type == NoticeType.DRC_01
    assert len(ctx.citations) == 1
    assert ctx.citations[0].source_id == "CGST Act 2017, Section 73"


def test_parse_legal_context_invalid_json_returns_none():
    assert _parse_legal_context("garbage", _stub_notice()) is None


def test_parse_legal_context_empty_returns_none():
    assert _parse_legal_context("", _stub_notice()) is None


def test_parse_legal_context_uses_default_annexures_on_empty():
    from noticeflow.agents.orchestrator import _REQUIRED_ANNEXURES
    d = json.loads(_legal_json())
    d["required_annexures"] = []
    ctx = _parse_legal_context(json.dumps(d), _stub_notice())
    assert ctx.required_annexures == _REQUIRED_ANNEXURES[NoticeType.DRC_01]


# ── Integration tests ─────────────────────────────────────────────────────────

integration = pytest.mark.skipif(
    not (os.environ.get("GOOGLE_CLOUD_PROJECT") and os.environ.get("VERTEX_SEARCH_DATASTORE_ID")),
    reason="GOOGLE_CLOUD_PROJECT or VERTEX_SEARCH_DATASTORE_ID not set",
)


@integration
@pytest.mark.asyncio
async def test_run_pipeline_drc01_end_to_end():
    from noticeflow.agents.orchestrator import run_pipeline, approve_packet
    text = (SAMPLE_DIR / "drc01_sec73.txt").read_text(encoding="utf-8")
    packet = await run_pipeline(text)

    assert packet.notice_type == NoticeType.DRC_01
    assert packet.reviewer_status == "PENDING_REVIEW"
    assert packet.gstin == "24ABCDE1234F1Z5"
    assert len(packet.reply_body) > 50
    assert len(packet.citations) >= 1
    assert packet.annexure.gstin == "24ABCDE1234F1Z5"

    # Human gate must be explicitly called
    approved = approve_packet(packet)
    assert approved.reviewer_status == "APPROVED"


@integration
@pytest.mark.asyncio
async def test_run_pipeline_unknown_notice_returns_fallback():
    from noticeflow.agents.orchestrator import run_pipeline
    packet = await run_pipeline("This is not a GST notice at all. Random text.")
    # Should not crash — should return a fallback packet
    assert isinstance(packet, ResponsePacket)
    assert packet.reviewer_status == "PENDING_REVIEW"
