"""scripts/monitor.py — a MOCKED deadline monitor for NoticeFlow (#2.6).

Demonstrates the "acts over time" dimension: given a set of pending notices, it
prioritizes them by urgency and emits a reminder/escalation line for each as the
deadline nears. Entirely mocked — no real calendar/email integration, no GCP, no
network. The watchlist below is hardcoded and clearly synthetic (deadlines are
relative to today so the demo always shows a live spread of tiers).

Run (from repo root):
    python scripts/monitor.py
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from noticeflow.deadlines import (
    MonitorItem,
    prioritize,
    reminder_message,
    urgency_label,
)
from noticeflow.schemas import NoticeType

_TODAY = datetime.now(timezone.utc).date()


def _in(days: int):
    return _TODAY + timedelta(days=days)


# Synthetic watchlist — relative deadlines so every tier is represented.
_WATCHLIST = [
    MonitorItem(reference="ZD2705240001234", notice_type=NoticeType.DRC_01, deadline=_in(-3)),
    MonitorItem(reference="ASMT/2024/00891", notice_type=NoticeType.ASMT_10, deadline=_in(4)),
    MonitorItem(reference="DRC01C/2024/0457", notice_type=NoticeType.ITC_MISMATCH, deadline=_in(11)),
    MonitorItem(reference="ZD2705240007788", notice_type=NoticeType.DRC_01, deadline=_in(22)),
    MonitorItem(reference="MISC/2024/0001", notice_type=NoticeType.UNKNOWN, deadline=None),
]


def main() -> None:
    print(f"NoticeFlow deadline monitor (mock) — {_TODAY.isoformat()}\n")
    for item, tier, days in prioritize(_WATCHLIST):
        print(f"  {urgency_label(tier):<22} {reminder_message(item, tier, days)}")


if __name__ == "__main__":
    main()
