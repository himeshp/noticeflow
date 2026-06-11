"""Unit tests for the confidence-gated escalation policy (#3.8) — pure, no GCP."""

from noticeflow import config
from noticeflow.gating import apply_confidence_gate
from noticeflow.schemas import (
    Citation,
    NoticeType,
    ReconciliationData,
    ResponsePacket,
)


def _packet(reviewer_status="PENDING_REVIEW"):
    return ResponsePacket(
        notice_type=NoticeType.DRC_01,
        reference_number="R",
        gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24",
        response_deadline=None,
        deadline_urgent=False,
        legal_basis="b",
        reply_body="r",
        citations=[Citation(source_id="Section 73", source_type="act",
                            snippet="s", relevance_note="n")],
        annexure=ReconciliationData(
            gstin="24ABCDE1234F1Z5", tax_period="FY2023-24", gstr3b_tax_paid=0.0,
            gstr2b_itc_available=820000.0, gstr3b_itc_claimed=905000.0,
            itc_mismatch_amount=85000.0, output_tax_liability=0.0,
        ),
        reviewer_status=reviewer_status,
    )


# ── config helpers ──────────────────────────────────────────────────────────────

def test_low_confidence_boundary():
    t = config.CONFIDENCE_THRESHOLD
    assert config.low_confidence(t - 0.01) is True
    assert config.low_confidence(t) is False        # at threshold = confident enough
    assert config.low_confidence(t + 0.01) is False


def test_low_confidence_reason_is_safe_text():
    reason = config.low_confidence_reason(0.4)
    assert "40%" in reason and "verify the notice type" in reason
    # server-constant string: no leftover format placeholders, no HTML tags
    # (the lone "<" in "40% < 55%" is a benign comparison glyph, escaped by React)
    assert "{" not in reason and "}" not in reason and "</" not in reason


# ── apply_confidence_gate ───────────────────────────────────────────────────────

def test_known_low_confidence_escalates():
    gated = apply_confidence_gate(_packet(), NoticeType.DRC_01, 0.30)
    assert gated.reviewer_status == "NEEDS_HUMAN"
    assert gated.escalation_reason and "confidence" in gated.escalation_reason


def test_known_high_confidence_untouched():
    pkt = _packet()
    gated = apply_confidence_gate(pkt, NoticeType.DRC_01, 0.95)
    assert gated.reviewer_status == "PENDING_REVIEW"
    assert gated.escalation_reason is None


def test_unknown_never_escalated_here():
    # UNKNOWN is short-circuited upstream; the gate must not touch it even at 0.0
    gated = apply_confidence_gate(_packet(), NoticeType.UNKNOWN, 0.0)
    assert gated.reviewer_status == "PENDING_REVIEW"
    assert gated.escalation_reason is None


def test_human_decision_not_downgraded():
    for status in ("APPROVED", "EDITED"):
        gated = apply_confidence_gate(_packet(status), NoticeType.DRC_01, 0.10)
        assert gated.reviewer_status == status
        assert gated.escalation_reason is None
