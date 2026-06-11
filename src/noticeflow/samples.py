"""Demo-stable sample-notice dates (#FIX1).

The UI sample notices carry placeholder tokens ({{ISSUE_DATE}}, {{DEADLINE}})
instead of hardcoded dates. At serve time we substitute dates computed RELATIVE
to today, so the deadline-urgency banner always shows a sensible upcoming
deadline (never "overdue") regardless of when the demo is run — no frozen/fake
clock, just relative sample data.

Pure: literal string substitution only (no eval, no user input, no path building).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

# filename -> (deadline_days_from_today, notice_window_days)
# Offsets chosen to exercise all three non-overdue urgency tiers on camera:
#   drc01  +25d -> NORMAL  (green,  "on schedule")
#   asmt10 +12d -> SOON    (amber,  "due within two weeks")
#   itc     +6d -> CRITICAL (red,   "due within a week" — urgent, NOT overdue)
SAMPLE_SCHEDULE: dict[str, tuple[int, int]] = {
    "drc01_sec73.txt": (25, 30),
    "asmt10_sec61.txt": (12, 30),
    "itc_mismatch_sec16.txt": (6, 7),
}

_FMT = "%d/%m/%Y"


def _today() -> date:
    return datetime.now(timezone.utc).date()


def render_sample_text(filename: str, raw: str, today: Optional[date] = None) -> str:
    """Substitute {{ISSUE_DATE}}/{{DEADLINE}} with dates relative to today.

    No-op for files without a schedule or without the placeholder tokens, so it
    is safe to call on any notice (e.g. the broader eval set)."""
    sched = SAMPLE_SCHEDULE.get(filename)
    if sched is None or ("{{DEADLINE}}" not in raw and "{{ISSUE_DATE}}" not in raw):
        return raw
    deadline_days, window = sched
    base = today or _today()
    deadline = base + timedelta(days=deadline_days)
    issue = deadline - timedelta(days=window)
    return raw.replace("{{ISSUE_DATE}}", issue.strftime(_FMT)).replace(
        "{{DEADLINE}}", deadline.strftime(_FMT)
    )
