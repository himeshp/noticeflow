"""Smoke tests for Pydantic schemas and the MCP ERP server lookup."""

import json
from datetime import date, timedelta, timezone, datetime

import pytest

from noticeflow.schemas import (
    ClassifiedNotice,
    Citation,
    LegalContext,
    NoticeType,
    ReconciliationData,
    ResponsePacket,
)
from noticeflow.mcp.erp_server import get_reconciliation_data


def test_classified_notice_round_trip():
    n = ClassifiedNotice(
        notice_type=NoticeType.DRC_01,
        governing_sections=["Section 73"],
        gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24",
        response_deadline=date(2026, 6, 20),
        demanded_amount=85000.0,
        issue_summary="Short payment of tax alleged.",
        raw_extracted_text="<full notice text>",
        confidence=0.95,
    )
    assert n.notice_type == NoticeType.DRC_01
    assert n.confidence == 0.95


def test_response_packet_deadline_urgent():
    assert ResponsePacket.compute_deadline_urgent(None) is False
    past = datetime.now(timezone.utc).date() + timedelta(days=3)
    assert ResponsePacket.compute_deadline_urgent(past) is True
    future = datetime.now(timezone.utc).date() + timedelta(days=30)
    assert ResponsePacket.compute_deadline_urgent(future) is False


def test_erp_lookup_drc01():
    result = get_reconciliation_data("24ABCDE1234F1Z5", "FY2023-24")
    assert result["gstin"] == "24ABCDE1234F1Z5"
    assert result["itc_mismatch_amount"] == 85000.0


def test_erp_lookup_asmt10():
    result = get_reconciliation_data("27PQRSX5678G2Z9", "FY2023-24")
    assert result["gstin"] == "27PQRSX5678G2Z9"


def test_erp_lookup_itc_mismatch():
    result = get_reconciliation_data("29LMNOP9012H3Z4", "04/2024")
    assert result["gstin"] == "29LMNOP9012H3Z4"
    assert result["itc_mismatch_amount"] == 45000.0


def test_erp_fallback_unknown_gstin():
    result = get_reconciliation_data("99ZZZZZ9999Z9Z9", "FY2023-24")
    assert "Fallback" in result["notes"]


def test_erp_path_traversal_rejected():
    # Malformed GSTIN with traversal characters must return fallback, not raise
    result = get_reconciliation_data("../../../etc/passwd", "FY2023-24")
    assert "Fallback" in result["notes"]
