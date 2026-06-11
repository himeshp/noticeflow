"""Deadline-aware urgency tiers + a lightweight monitor (#2.6).

Pure date logic — no LLM, no I/O, no network. Urgency is derived deterministically
from a notice's response_deadline; the cockpit and the (mocked) monitor both use
these helpers so the thresholds live in exactly one place on the Python side.

Tier boundaries (days remaining, inclusive) — chosen to stay consistent with the
existing ResponsePacket.deadline_urgent flag (urgent iff days <= 7):

    days < 0   -> OVERDUE
    0 .. 7     -> CRITICAL   (== deadline_urgent)
    8 .. 14    -> SOON
    > 14       -> NORMAL
    no date    -> NONE
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from noticeflow.schemas import NoticeType

_CRITICAL_DAYS = 7   # matches ResponsePacket.deadline_urgent (<= 7)
_SOON_DAYS = 14


class UrgencyTier(str, Enum):
    OVERDUE = "OVERDUE"
    CRITICAL = "CRITICAL"
    SOON = "SOON"
    NORMAL = "NORMAL"
    NONE = "NONE"


_TIER_LABELS = {
    UrgencyTier.OVERDUE: "Overdue",
    UrgencyTier.CRITICAL: "Due within a week",
    UrgencyTier.SOON: "Due within two weeks",
    UrgencyTier.NORMAL: "On schedule",
    UrgencyTier.NONE: "No deadline",
}

# Sort key: OVERDUE first, then by ascending days remaining.
_TIER_RANK = {
    UrgencyTier.OVERDUE: 0,
    UrgencyTier.CRITICAL: 1,
    UrgencyTier.SOON: 2,
    UrgencyTier.NORMAL: 3,
    UrgencyTier.NONE: 4,
}


def _today(today: Optional[date]) -> date:
    return today or datetime.now(timezone.utc).date()


def days_until(deadline: Optional[date], today: Optional[date] = None) -> Optional[int]:
    """Whole days from today to the deadline (negative = overdue, None = no date)."""
    if deadline is None:
        return None
    return (deadline - _today(today)).days


def urgency_tier(deadline: Optional[date], today: Optional[date] = None) -> UrgencyTier:
    d = days_until(deadline, today)
    if d is None:
        return UrgencyTier.NONE
    if d < 0:
        return UrgencyTier.OVERDUE
    if d <= _CRITICAL_DAYS:
        return UrgencyTier.CRITICAL
    if d <= _SOON_DAYS:
        return UrgencyTier.SOON
    return UrgencyTier.NORMAL


def urgency_label(tier: UrgencyTier) -> str:
    return _TIER_LABELS[tier]


def next_action_line(deadline: Optional[date], today: Optional[date] = None) -> Optional[str]:
    """One-line 'next action by' string, or None when there is no deadline."""
    if deadline is None:
        return None
    d = days_until(deadline, today)
    when = deadline.strftime("%d %b %Y")
    if d is None:  # unreachable given the guard above, kept for type-narrowing
        return f"Next action by {when}"
    if d < 0:
        return f"Reply was due {when} — {abs(d)} day{'s' if abs(d) != 1 else ''} overdue"
    if d == 0:
        return f"Next action by {when} — due today"
    return f"Next action by {when} — {d} day{'s' if d != 1 else ''} remaining"


# ── Mocked monitor (the "acts over time" gesture; no real calendar/email) ───────

class MonitorItem(BaseModel):
    reference: str
    notice_type: NoticeType
    deadline: Optional[date] = None


def prioritize(
    items: list[MonitorItem], today: Optional[date] = None
) -> list[tuple[MonitorItem, UrgencyTier, Optional[int]]]:
    """Sort pending notices most-urgent-first: overdue, then soonest deadline.
    Items with no deadline sort last. Returns (item, tier, days_remaining)."""
    annotated = [
        (it, urgency_tier(it.deadline, today), days_until(it.deadline, today))
        for it in items
    ]
    # Primary: tier rank. Secondary: days remaining (None sorts last).
    annotated.sort(key=lambda t: (_TIER_RANK[t[1]], t[2] if t[2] is not None else 10**9))
    return annotated


def reminder_message(item: MonitorItem, tier: UrgencyTier, days: Optional[int]) -> str:
    """Mock reminder line for a pending notice. Server-constant template with only
    the reference / notice type / day count interpolated."""
    ref = f"{item.notice_type.value} {item.reference}".strip()
    if tier == UrgencyTier.NONE:
        return f"[INFO] {ref}: no response deadline on record."
    if tier == UrgencyTier.OVERDUE:
        return f"[ESCALATE] {ref}: OVERDUE by {abs(days)} day(s) — escalate to a human now."
    if tier == UrgencyTier.CRITICAL:
        return f"[URGENT] {ref}: due in {days} day(s) — prepare and file the reply."
    if tier == UrgencyTier.SOON:
        return f"[REMINDER] {ref}: due in {days} day(s) — begin drafting."
    return f"[OK] {ref}: due in {days} day(s) — on schedule."
