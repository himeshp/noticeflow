"""Unit tests for deadline urgency tiers + the mocked monitor (#2.6) — pure."""

from datetime import date

from noticeflow.deadlines import (
    MonitorItem,
    UrgencyTier,
    days_until,
    next_action_line,
    prioritize,
    reminder_message,
    urgency_tier,
)
from noticeflow.schemas import NoticeType

TODAY = date(2026, 6, 7)


def _d(offset: int) -> date:
    from datetime import timedelta
    return TODAY + timedelta(days=offset)


# ── days_until ──────────────────────────────────────────────────────────────────

def test_days_until():
    assert days_until(None, TODAY) is None
    assert days_until(_d(0), TODAY) == 0
    assert days_until(_d(5), TODAY) == 5
    assert days_until(_d(-2), TODAY) == -2


# ── urgency_tier boundaries ──────────────────────────────────────────────────────

def test_tier_boundaries():
    assert urgency_tier(None, TODAY) == UrgencyTier.NONE
    assert urgency_tier(_d(-1), TODAY) == UrgencyTier.OVERDUE
    assert urgency_tier(_d(0), TODAY) == UrgencyTier.CRITICAL
    assert urgency_tier(_d(7), TODAY) == UrgencyTier.CRITICAL    # matches deadline_urgent <= 7
    assert urgency_tier(_d(8), TODAY) == UrgencyTier.SOON
    assert urgency_tier(_d(14), TODAY) == UrgencyTier.SOON
    assert urgency_tier(_d(15), TODAY) == UrgencyTier.NORMAL


# ── next_action_line ─────────────────────────────────────────────────────────────

def test_next_action_line():
    assert next_action_line(None, TODAY) is None
    assert "due today" in next_action_line(_d(0), TODAY)
    assert "1 day remaining" in next_action_line(_d(1), TODAY)
    assert "5 days remaining" in next_action_line(_d(5), TODAY)
    overdue = next_action_line(_d(-3), TODAY)
    assert "overdue" in overdue and "3 days" in overdue


# ── prioritize ordering ──────────────────────────────────────────────────────────

def test_prioritize_orders_overdue_then_soonest():
    items = [
        MonitorItem(reference="N", notice_type=NoticeType.UNKNOWN, deadline=None),
        MonitorItem(reference="A", notice_type=NoticeType.DRC_01, deadline=_d(22)),
        MonitorItem(reference="B", notice_type=NoticeType.ASMT_10, deadline=_d(4)),
        MonitorItem(reference="C", notice_type=NoticeType.DRC_01, deadline=_d(-3)),
    ]
    order = [it.reference for it, _, _ in prioritize(items, TODAY)]
    assert order == ["C", "B", "A", "N"]  # overdue, soonest, later, no-deadline last


# ── reminder_message ─────────────────────────────────────────────────────────────

def test_reminder_messages_by_tier():
    overdue = MonitorItem(reference="X", notice_type=NoticeType.DRC_01, deadline=_d(-3))
    crit = MonitorItem(reference="Y", notice_type=NoticeType.ASMT_10, deadline=_d(4))
    none = MonitorItem(reference="Z", notice_type=NoticeType.UNKNOWN, deadline=None)
    assert "ESCALATE" in reminder_message(overdue, UrgencyTier.OVERDUE, -3)
    assert "URGENT" in reminder_message(crit, UrgencyTier.CRITICAL, 4)
    assert "no response deadline" in reminder_message(none, UrgencyTier.NONE, None)
