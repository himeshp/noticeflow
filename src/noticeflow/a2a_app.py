"""A2A discoverability surface for NoticeFlow (#2.5, Option A).

Exposes the existing orchestrator as an **A2A-discoverable agent** with a
published, spec-compliant agent card, using the official `a2a-sdk` types and
ADK's sanctioned `to_a2a()` helper — the JSON-RPC protocol is NOT hand-rolled.

This is an *additive, separate* serving surface (like `api.py`). Nothing in the
Agent Engine deploy path imports it, and the orchestrator / `root_agent` are
reused unchanged — so the deployed engine is untouched.

The card is published by the running server at the A2A well-known path; a static
copy for judges lives at `docs/submission/agent-card.json` (see
`scripts/export_agent_card.py`).

Run the discoverable agent locally (requires the optional extra):
    pip install -e ".[a2a]"
    uvicorn noticeflow.a2a_app:get_app --factory --host 0.0.0.0 --port 8001

⚠ Demo surface: the A2A server uses in-memory stores and has NO authentication.
Do not expose it publicly with sensitive data.
"""

from __future__ import annotations

import os

# Public RPC URL advertised in the agent card. Override for a real deployment.
A2A_PUBLIC_URL = os.environ.get("A2A_PUBLIC_URL", "http://localhost:8001/")
A2A_HOST = os.environ.get("A2A_HOST", "localhost")
A2A_PORT = int(os.environ.get("A2A_PORT", "8001"))
A2A_PROTOCOL = os.environ.get("A2A_PROTOCOL", "http")

_INSTALL_HINT = (
    "The A2A extra is not installed. Install it with:  pip install -e \".[a2a]\""
)


def _require_a2a():
    """Import a2a types lazily with a clear message if the extra is missing."""
    try:
        from a2a.types import AgentCapabilities, AgentCard, AgentSkill  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(_INSTALL_HINT) from exc
    return AgentCard, AgentSkill, AgentCapabilities


def build_agent_card(rpc_url: str = A2A_PUBLIC_URL):
    """Build the spec-compliant A2A AgentCard describing NoticeFlow.

    Pure (no GCP, no network) — safe to call for the static export and in tests.
    """
    AgentCard, AgentSkill, AgentCapabilities = _require_a2a()

    skill = AgentSkill(
        id="gst-notice-response",
        name="GST Notice Response",
        description=(
            "Ingest an Indian GST notice (ASMT-10 scrutiny, DRC-01 demand, or "
            "ITC-mismatch / DRC-01C) and return a filing-ready response packet: "
            "classified, grounded in real CBIC GST law with code-verified "
            "citations, with a reconciliation annexure and a deadline flag. A "
            "human approves before anything is filed."
        ),
        tags=["tax", "gst", "india", "compliance", "legal", "multi-agent"],
        examples=[
            "Reply to this ASMT-10 scrutiny notice under Section 61.",
            "Draft a response to a DRC-01 demand for FY2023-24.",
            "Resolve an ITC mismatch (GSTR-3B vs GSTR-2B) intimation.",
        ],
        inputModes=["text/plain"],
        outputModes=["application/json"],
    )

    return AgentCard(
        name="NoticeFlow",
        description=(
            "Autonomous multi-agent system (Google ADK on Vertex AI) that turns "
            "an Indian GST notice into a filing-ready, legally grounded response "
            "packet with a human approval gate."
        ),
        version="0.1.0",
        url=rpc_url,
        defaultInputModes=["text/plain"],
        defaultOutputModes=["application/json"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )


def get_app():
    """Factory for the A2A Starlette app (for `uvicorn ... --factory`).

    Wraps the existing orchestrator `root_agent` via ADK's `to_a2a()`; the card
    and JSON-RPC routes are wired by the sanctioned helper, not by us.
    """
    try:
        from google.adk.a2a.utils.agent_to_a2a import to_a2a
    except ImportError as exc:
        raise RuntimeError(_INSTALL_HINT) from exc

    from noticeflow.agents.orchestrator import root_agent

    return to_a2a(
        root_agent,
        host=A2A_HOST,
        port=A2A_PORT,
        protocol=A2A_PROTOCOL,
        agent_card=build_agent_card(),
    )
