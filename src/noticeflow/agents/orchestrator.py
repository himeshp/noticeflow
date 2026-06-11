"""
Orchestrator — ADK SequentialAgent wiring Classifier → Researcher → Drafter.

State flow (via output_key + {key} substitution):
  user message (notice text)
       │
       ▼
  classifier_agent  →  state["classified_notice_json"]
       │
       ▼
  researcher_agent  →  state["legal_context_json"]    (reads {classified_notice_json})
       │
       ▼
  drafter_agent     →  state["response_packet_json"]  (reads both above)
       │
       ▼
  run_pipeline() parses state["response_packet_json"] → ResponsePacket

Human gate: ResponsePacket always leaves the pipeline with
reviewer_status="PENDING_REVIEW". Call approve_packet() or edit_packet()
after human review — never auto-approve.
"""

import json
import pathlib
import sys
import uuid
from typing import Optional

from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters
from google.genai import types
from pydantic import BaseModel, Field

from noticeflow import config
from noticeflow.schemas import (
    Citation,
    ClassifiedNotice,
    LegalContext,
    NoticeType,
    ReconciliationData,
    ResponsePacket,
    RetrievedChunk,
    ReviewResult,
)
from noticeflow.gating import apply_confidence_gate
from noticeflow.localize import localize_packet
from noticeflow.sources import annotate_citation_sources
from noticeflow.verify.citations import apply_citation_verification, collect_grounding

# ── Internal schemas (same as sub-agents' outputs; used for parsing state) ────

from noticeflow.agents.classifier import _ClassifierOutput, _INSTRUCTION as _CLS_INSTRUCTION
from noticeflow.agents.researcher import (
    _ResearcherOutput,
    _INSTRUCTION as _RES_INSTRUCTION,
    _REQUIRED_ANNEXURES,
    _QUERY_TEMPLATES,
)
from noticeflow.agents.drafter import (
    _DrafterOutput,
    _INSTRUCTION as _DFT_INSTRUCTION,
    _ERP_SERVER_PATH,
    _fallback_packet,
)

# ── State keys ────────────────────────────────────────────────────────────────

STATE_CLASSIFIED = "classified_notice_json"
STATE_LEGAL = "legal_context_json"
STATE_PACKET = "response_packet_json"

# ── Sub-agent instructions (augmented with state-key references) ──────────────
# ADK substitutes {key} in instructions from session.state at runtime.

_CLASSIFIER_INST = _CLS_INSTRUCTION  # takes notice text from user message directly

_RESEARCHER_INST = (
    "The following classified GST notice JSON is from the prior agent:\n"
    "{" + STATE_CLASSIFIED + "}\n\n"
    + _RES_INSTRUCTION
)

_DRAFTER_INST = (
    "The following classified GST notice JSON is from the classifier:\n"
    "{" + STATE_CLASSIFIED + "}\n\n"
    "The following legal context JSON is from the researcher:\n"
    "{" + STATE_LEGAL + "}\n\n"
    + _DFT_INSTRUCTION
)

# Appended to the Drafter's instruction only when the review loop is enabled.
# {review_issues} is seeded to "" so the first draft sees no feedback; the Critic
# fills it on a REVISE verdict, and the Drafter must address every point next pass.
_DRAFTER_REVISION_BLOCK = (
    "\n\n--- AUTOMATED REVIEW FEEDBACK ---\n"
    "If the following is non-empty, your PREVIOUS draft failed an automated "
    "compliance check. You are REVISING: fix EVERY point below and output a "
    "complete, corrected JSON packet (same schema). Do not repeat the mistakes.\n"
    "{review_issues}\n"
)

# ── Pipeline factory ──────────────────────────────────────────────────────────

_APP_NAME = "noticeflow"
_USER_ID = "system"

_session_service = InMemorySessionService()
_pipeline: Optional[SequentialAgent] = None
_pipeline_runner: Optional[Runner] = None


def _build_pipeline() -> tuple[SequentialAgent, Runner]:
    """Build the SequentialAgent and Runner. Called once on first use."""
    # Classifier — uses output_schema, no tools needed
    from google.adk.tools import VertexAiSearchTool

    classifier_agent = LlmAgent(
        model=config.MODEL_FLASH,
        name="classifier",
        description="Classifies the GST notice into structured data.",
        instruction=_CLASSIFIER_INST,
        output_schema=_ClassifierOutput,
        output_key=STATE_CLASSIFIED,
        generate_content_config=config.gen_config(),
    )

    # Researcher — Vertex AI Search tool; builds datastore path from config.
    # In the deployed runtime NOTICEFLOW_REQUIRE_DATASTORE=true, so a missing
    # datastore raises here rather than silently building a tool-less researcher
    # that could answer from the model's own (ungrounded) knowledge.
    config.assert_datastore_configured()
    researcher_tools = []
    if config.DATASTORE_ID:
        datastore_path = (
            f"projects/{config.get_project_id()}/locations/{config.VERTEX_SEARCH_LOCATION}"
            f"/collections/default_collection/dataStores/{config.DATASTORE_ID}"
        )
        researcher_tools = [VertexAiSearchTool(data_store_id=datastore_path)]

    researcher_agent = LlmAgent(
        model=config.MODEL_FLASH,
        name="researcher",
        description="Retrieves GST law citations for the classified notice.",
        instruction=_RESEARCHER_INST,
        tools=researcher_tools,
        output_key=STATE_LEGAL,
        generate_content_config=config.gen_config(),
    )

    # Drafter — MCP ERP tool; path is package-internal (not user-supplied).
    # With the review loop on, append the revision block so re-drafts consume
    # the Critic's feedback ({review_issues} is seeded to "" for the first pass).
    drafter_instruction = _DRAFTER_INST + (
        _DRAFTER_REVISION_BLOCK if config.ENABLE_REVIEW_LOOP else ""
    )
    drafter_agent = LlmAgent(
        model=config.MODEL_PRO,
        name="drafter",
        description="Drafts the GST reply packet with reconciliation figures.",
        instruction=drafter_instruction,
        tools=[
            MCPToolset(
                connection_params=StdioServerParameters(
                    # Interpreter resolves at build time: sys.executable locally,
                    # python3 in the Agent Engine runtime (see config helper).
                    command=config.mcp_python_command(),
                    args=["-m", "noticeflow.mcp.erp_server"],
                ),
                tool_filter=["get_reconciliation_data"],
            )
        ],
        output_key=STATE_PACKET,
        generate_content_config=config.gen_config(),
    )

    if config.ENABLE_REVIEW_LOOP:
        # Drafter <-> deterministic Critic, capped at 2 iterations. The Critic
        # escalates (stops the loop) on APPROVE; otherwise the Drafter re-drafts.
        from noticeflow.agents.reviewer import CriticAgent

        draft_review = LoopAgent(
            name="draft_review",
            description="Draft, deterministically review, and re-draft up to 2x.",
            sub_agents=[drafter_agent, CriticAgent(name="critic")],
            max_iterations=2,
        )
        final_stage = draft_review
    else:
        final_stage = drafter_agent

    pipeline = SequentialAgent(
        name="noticeflow_pipeline",
        description="Classifier → Researcher → Drafter (+ review loop) for GST notices.",
        sub_agents=[classifier_agent, researcher_agent, final_stage],
    )

    runner = Runner(
        agent=pipeline,
        app_name=_APP_NAME,
        session_service=_session_service,
    )
    return pipeline, runner


def _get_pipeline() -> tuple[SequentialAgent, Runner]:
    global _pipeline, _pipeline_runner
    if _pipeline is None:
        _pipeline, _pipeline_runner = _build_pipeline()
    return _pipeline, _pipeline_runner


# ── Response parsing ──────────────────────────────────────────────────────────

def _parse_classified(raw) -> Optional[ClassifiedNotice]:
    try:
        # output_schema agents store a dict in state; tool agents store a JSON string.
        if isinstance(raw, dict):
            d = raw
        else:
            text = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            d = json.loads(text)
        out = _ClassifierOutput.model_validate(d)
        from datetime import date
        deadline = None
        if out.response_deadline:
            try:
                deadline = date.fromisoformat(out.response_deadline)
            except ValueError:
                pass
        return ClassifiedNotice(
            notice_type=out.notice_type,
            governing_sections=out.governing_sections,
            reference_number=out.reference_number,
            gstin=out.gstin,
            tax_period=out.tax_period,
            response_deadline=deadline,
            demanded_amount=out.demanded_amount,
            issue_summary=out.issue_summary,
            raw_extracted_text="",
            confidence=out.confidence,
        )
    except Exception:
        return None


def _parse_legal_context(raw, notice: ClassifiedNotice) -> Optional[LegalContext]:
    try:
        if isinstance(raw, dict):
            d = raw
        else:
            text = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            d = json.loads(text)
        out = _ResearcherOutput.model_validate(d)
        citations = [
            Citation(
                source_id=c.source_id,
                source_type=c.source_type,
                snippet=c.snippet,
                relevance_note=c.relevance_note,
            )
            for c in out.citations
        ]
        return LegalContext(
            notice_type=notice.notice_type,
            citations=citations,
            applicable_response_options=out.applicable_response_options,
            required_annexures=out.required_annexures
            or _REQUIRED_ANNEXURES.get(notice.notice_type, []),
        )
    except Exception:
        return None


def _parse_packet(raw: str, notice: ClassifiedNotice, legal_ctx: LegalContext) -> ResponsePacket:
    from noticeflow.agents.drafter import _parse_response
    return _parse_response(raw, notice, legal_ctx)


# ── Human gate ────────────────────────────────────────────────────────────────

def approve_packet(packet: ResponsePacket) -> ResponsePacket:
    """Mark a response packet as human-approved. Must be called explicitly."""
    return packet.model_copy(update={"reviewer_status": "APPROVED"})


def edit_packet(packet: ResponsePacket, **fields) -> ResponsePacket:
    """Apply human edits to a response packet and mark it EDITED."""
    updates = {**fields, "reviewer_status": "EDITED"}
    return packet.model_copy(update=updates)


# ── Public API ────────────────────────────────────────────────────────────────

async def run_pipeline(notice_text: str, language: str = "en") -> ResponsePacket:
    """Run the full NoticeFlow pipeline on raw notice text.

    Returns a ResponsePacket with reviewer_status="PENDING_REVIEW".
    Call approve_packet() or edit_packet() after human review.

    Short-circuits with a fallback packet for UNKNOWN notice types.
    `language` ("en"|"hi"|"bilingual", #3.7) localizes the reply prose at the end;
    "en" is a no-op. English fields stay canonical (form/citation verifier use them).
    """
    _, runner = _get_pipeline()

    session_id = str(uuid.uuid4())
    # Seed review state so the Drafter's {review_issues} template resolves on the
    # first pass (empty = no feedback yet). Only relevant when the loop is on.
    initial_state = {"review_issues": "", "review_round": 0} if config.ENABLE_REVIEW_LOOP else None
    await _session_service.create_session(
        app_name=_APP_NAME,
        user_id=_USER_ID,
        session_id=session_id,
        state=initial_state,
    )

    evidence: list[RetrievedChunk] = []
    seen: set = set()
    async for event in runner.run_async(
        user_id=_USER_ID,
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=notice_text)],
        ),
    ):
        # SequentialAgent drives the pipeline; we read state after completion.
        # Capture the Researcher's retrieved chunks for citation verification.
        collect_grounding(event, evidence, seen)

    # Re-fetch the session — the runner writes agent outputs to the service's
    # stored session, not the local object returned by create_session.
    updated = await _session_service.get_session(
        app_name=_APP_NAME,
        user_id=_USER_ID,
        session_id=session_id,
    )
    state = updated.state if updated else {}

    # Parse classified notice for UNKNOWN short-circuit check
    classified_raw = state.get(STATE_CLASSIFIED, "")
    notice = _parse_classified(classified_raw)

    if notice is None or notice.notice_type == NoticeType.UNKNOWN:
        # Minimal fallback — can't proceed without a known notice type.
        # (LegalContext/Citation are imported at module level; importing them
        # here again would shadow them as function-locals and make the
        # non-UNKNOWN fallback path below raise UnboundLocalError.)
        unknown_notice = notice or ClassifiedNotice(
            notice_type=NoticeType.UNKNOWN,
            governing_sections=[],
            issue_summary="Could not classify this notice.",
            raw_extracted_text=notice_text[:500],
            confidence=0.0,
        )
        empty_legal = LegalContext(
            notice_type=NoticeType.UNKNOWN,
            citations=[],
            applicable_response_options=[],
            required_annexures=[],
        )
        return _fallback_packet(unknown_notice, empty_legal)

    legal_raw = state.get(STATE_LEGAL, "")
    legal_ctx = _parse_legal_context(legal_raw, notice) or LegalContext(
        notice_type=notice.notice_type,
        citations=[],
        applicable_response_options=[],
        required_annexures=_REQUIRED_ANNEXURES.get(notice.notice_type, []),
    )

    packet_raw = state.get(STATE_PACKET, "")
    if not packet_raw:
        packet = _fallback_packet(notice, legal_ctx)
    else:
        packet = _parse_packet(packet_raw, notice, legal_ctx)

    packet = apply_citation_verification(packet, evidence)
    packet = _attach_review(packet, state)
    # #3.8 — route low-confidence (but KNOWN) classifications to a human instead
    # of presenting the draft as ready to file.
    packet = apply_confidence_gate(packet, notice.notice_type, notice.confidence)
    # #3.7 — localize the reply prose (no-op for English; English stays canonical).
    packet = await localize_packet(packet, language)
    # Attach source PDF + page to each citation (for the in-app source viewer).
    return annotate_citation_sources(packet)


def _attach_review(packet: ResponsePacket, state: dict) -> ResponsePacket:
    """Attach the review-loop verdict (if the loop ran). A REVISE verdict that
    survived the iteration cap escalates the human gate to NEEDS_HUMAN."""
    raw = state.get("review_result_json")
    if not raw:
        return packet
    try:
        review = ReviewResult.model_validate_json(raw)
    except Exception:
        return packet
    updates: dict = {"review": review}
    if review.verdict == "REVISE":
        updates["reviewer_status"] = "NEEDS_HUMAN"
    return packet.model_copy(update=updates)


# ── root_agent for `adk web` ──────────────────────────────────────────────────
# ADK's `adk web` command looks for a module-level `root_agent`.
# We expose the SequentialAgent pipeline directly.

def _get_root_agent() -> SequentialAgent:
    pipeline, _ = _get_pipeline()
    return pipeline


class _LazyRootAgent:
    """Proxy that defers pipeline construction until first attribute access."""
    _agent: Optional[SequentialAgent] = None

    def _ensure(self) -> SequentialAgent:
        if self._agent is None:
            self._agent = _get_root_agent()
        return self._agent

    def __getattr__(self, name: str):
        return getattr(self._ensure(), name)


root_agent = _LazyRootAgent()


# ── Manual smoke-test entry point ─────────────────────────────────────────────
# Usage: python -m noticeflow.agents.orchestrator data/sample_notices/drc01_sec73.txt

if __name__ == "__main__":
    import asyncio
    import pathlib
    import sys

    if len(sys.argv) != 2:
        print("Usage: python -m noticeflow.agents.orchestrator <notice_file.txt>")
        sys.exit(1)

    notice_path = pathlib.Path(sys.argv[1])
    if not notice_path.exists():
        print(f"File not found: {notice_path}")
        sys.exit(1)

    text = notice_path.read_text(encoding="utf-8")
    result = asyncio.run(run_pipeline(text))
    print(result.model_dump_json(indent=2))
    print(f"\nStatus: {result.reviewer_status} — call approve_packet() to finalize.")
