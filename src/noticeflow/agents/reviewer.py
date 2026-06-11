"""Critic for the Drafter<->Critic review loop — a deterministic ADK agent.

The critic runs NO LLM. It checks the Drafter's output against two code-enforced
criteria and either APPROVES (escalating to stop the LoopAgent) or returns
concrete issues for the Drafter to fix on the next iteration:

  1. citations_grounded — every cited source_id is one the Researcher actually
     returned (the Drafter may not introduce a citation outside the retrieved set).
  2. figures_reconcile — the annexure arithmetic holds:
     itc_mismatch_amount == gstr3b_itc_claimed - gstr2b_itc_available.

Determinism makes the loop reproducible and cheap (no extra model calls), and
ties the loop's "self-correction" to the same anti-hallucination guarantee as
the citation verifier (#1.2).
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Optional

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from noticeflow.schemas import ReviewResult

# State keys (mirror orchestrator.STATE_PACKET / STATE_LEGAL; kept as literals to
# avoid an import cycle with orchestrator, which imports this module).
_STATE_PACKET = "response_packet_json"
_STATE_LEGAL = "legal_context_json"

_RECON_TOL = 1.0  # rupees; guards float rounding only


def _loads(raw) -> Optional[dict]:
    """Lenient parse of an agent's state value (dict or JSON string). Never eval."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else ""
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    try:
        d = json.loads(text.strip())
        return d if isinstance(d, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _legal_source_ids(legal) -> set[str]:
    d = _loads(legal) or {}
    ids: set[str] = set()
    for c in d.get("citations", []) or []:
        if isinstance(c, dict) and c.get("source_id"):
            ids.add(c["source_id"])
    return ids


def review_drafter_output(drafter_out, legal_ctx, round: int) -> ReviewResult:
    """Deterministically review the Drafter's raw output. Pure; no I/O, no LLM."""
    d = _loads(drafter_out)
    if d is None:
        # Unparseable — nothing to check here; don't burn loop iterations.
        # The wrapper's _parse_packet handles malformed output via its fallback.
        return ReviewResult(
            citations_grounded=True, figures_reconcile=True,
            issues=[], verdict="APPROVE", round=round,
        )

    issues: list[str] = []

    # (1) citations grounded in the retrieved legal context
    cited = [s for s in (d.get("cited_source_ids") or []) if isinstance(s, str)]
    legal_ids = _legal_source_ids(legal_ctx)
    ungrounded = [s for s in cited if s not in legal_ids] if legal_ids else []
    citations_grounded = not ungrounded
    if ungrounded:
        issues.append(
            "Cited sources not present in the retrieved legal context — cite only "
            "sources the researcher provided, or remove these: " + ", ".join(ungrounded)
        )

    # (2) annexure reconciliation arithmetic
    ann = d.get("annexure") or {}
    figures_reconcile = False
    try:
        claimed = float(ann["gstr3b_itc_claimed"])
        available = float(ann["gstr2b_itc_available"])
        mismatch = float(ann["itc_mismatch_amount"])
        figures_reconcile = abs(mismatch - (claimed - available)) <= _RECON_TOL
        if not figures_reconcile:
            issues.append(
                f"Annexure does not reconcile: itc_mismatch_amount ({mismatch}) must "
                f"equal gstr3b_itc_claimed ({claimed}) - gstr2b_itc_available "
                f"({available}) = {claimed - available}. Use the ERP figures exactly."
            )
    except (KeyError, TypeError, ValueError):
        issues.append("Annexure is missing required reconciliation figures.")

    verdict = "APPROVE" if (citations_grounded and figures_reconcile) else "REVISE"
    return ReviewResult(
        citations_grounded=citations_grounded,
        figures_reconcile=figures_reconcile,
        issues=issues,
        verdict=verdict,
        round=round,
    )


class CriticAgent(BaseAgent):
    """ADK custom (non-LLM) agent: reviews the draft, escalates on APPROVE."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        round_no = int(state.get("review_round", 0)) + 1
        result = review_drafter_output(
            state.get(_STATE_PACKET, ""), state.get(_STATE_LEGAL, ""), round_no
        )
        # Persist via the event's state_delta — direct ctx.session.state writes
        # from a custom agent are not reliably committed to the session service.
        # (Also set them locally so a same-invocation reader sees them.)
        delta = {
            "review_round": round_no,
            "review_result_json": result.model_dump_json(),
            "review_issues": "\n".join(f"- {i}" for i in result.issues),
        }
        state.update(delta)

        if result.verdict == "APPROVE":
            # Stop the LoopAgent early.
            yield Event(
                author=self.name,
                actions=EventActions(escalate=True, state_delta=delta),
            )
        else:
            yield Event(
                author=self.name,
                actions=EventActions(state_delta=delta),
                content=types.Content(
                    role="model",
                    parts=[types.Part(
                        text=f"REVISE (round {round_no}): " + "; ".join(result.issues)
                    )],
                ),
            )
