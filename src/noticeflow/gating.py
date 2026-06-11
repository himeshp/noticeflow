"""Pure escalation policy — no LLM, no I/O, no network.

#3.8 confidence-gated human escalation. The classifier self-reports a 0-1
confidence in the notice type; when that confidence is low (for an otherwise
KNOWN type) NoticeFlow refuses to present the draft as ready and routes it to a
human instead. "Knows when not to act."

Kept side-effect-free so it is trivially unit-testable and so both the
orchestrator (deployed-engine wrapper / eval path) and api.py (cockpit SSE path)
apply the *same* decision. UNKNOWN notices are already short-circuited upstream;
this only acts on KNOWN types whose confidence is below the threshold.
"""

from __future__ import annotations

from noticeflow import config
from noticeflow.schemas import NoticeType, ResponsePacket

# Human decisions we must never silently downgrade back to NEEDS_HUMAN.
_FINALIZED = ("APPROVED", "EDITED")


def apply_confidence_gate(
    packet: ResponsePacket, notice_type: NoticeType, confidence: float
) -> ResponsePacket:
    """Return the packet flagged NEEDS_HUMAN (with an escalation_reason) when the
    classification confidence is below the threshold for a KNOWN notice type.

    Fails safe toward *more* human oversight: it only ever adds a review gate; it
    never auto-approves, and it leaves a human-finalized packet untouched.
    """
    if notice_type == NoticeType.UNKNOWN or not config.low_confidence(confidence):
        return packet
    if packet.reviewer_status in _FINALIZED:
        return packet
    return packet.model_copy(
        update={
            "reviewer_status": "NEEDS_HUMAN",
            "escalation_reason": config.low_confidence_reason(confidence),
        }
    )
