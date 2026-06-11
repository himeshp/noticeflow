"""
Researcher agent — Gemini Flash + Vertex AI Search RAG, ADK 2.x LlmAgent.

Input : ClassifiedNotice (from Classifier)
Output: LegalContext — attributed citations from the real CBIC GST law corpus

Design note: ADK's output_schema disables tool usage, so we cannot combine
VertexAiSearchTool with structured JSON output directly. Instead we instruct
the model to emit JSON, parse it explicitly, and fall back gracefully on
parse failure. This is a deliberate tradeoff for hackathon reliability.
"""

import json
import uuid
from typing import Optional

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import VertexAiSearchTool
from google.genai import types
from pydantic import BaseModel, Field

from noticeflow import config
from noticeflow.schemas import (
    Citation,
    ClassifiedNotice,
    LegalContext,
    NoticeType,
    RetrievedChunk,
)
from noticeflow.verify.citations import collect_grounding


# ── Internal output schema (no NoticeType — caller supplies it) ───────────────

class _CitationOut(BaseModel):
    source_id: str = Field(
        description="e.g. 'CGST Act 2017, Section 73' or 'Circular 31/05/2018-GST'"
    )
    source_type: str = Field(
        description="one of: act, rule, circular, instruction, notification"
    )
    snippet: str = Field(description="the retrieved text passage verbatim or near-verbatim")
    relevance_note: str = Field(description="why this applies — one sentence")


class _ResearcherOutput(BaseModel):
    citations: list[_CitationOut]
    applicable_response_options: list[str] = Field(
        description="what the taxpayer can legitimately argue per the law"
    )
    required_annexures: list[str] = Field(
        description="supporting docs/figures the reply must include"
    )


# ── Prompt ────────────────────────────────────────────────────────────────────

_INSTRUCTION = f"""You are a GST legal researcher for Indian tax law.

You will receive a search query describing a GST notice type and the legal issue raised.
Use the search tool to retrieve relevant passages from the GST law knowledge base, then
return a structured JSON object with the findings.

STRICT RULES:
1. Only cite passages you actually retrieved via the search tool. Do NOT invent citations.
2. Use exact section numbers, rule numbers, and circular references from the retrieved text.
3. If retrieval returns weak results, return fewer citations — never fabricate.
4. source_type must be exactly one of: act, rule, circular, instruction, notification
5. Respond ONLY with a valid JSON object matching the schema below.
   No prose before or after. No markdown code fences. Pure JSON only.

Output schema:
{json.dumps(_ResearcherOutput.model_json_schema(), indent=2)}
"""


# ── Notice-type query templates ───────────────────────────────────────────────
# These focus retrieval on the right law for each notice type, keeping the
# corpus search tight to what the Drafter actually needs.

_QUERY_TEMPLATES: dict[NoticeType, str] = {
    NoticeType.DRC_01: (
        "Section 73 show cause notice demand short payment of tax input tax credit "
        "Section 50 interest Section 74 fraud penalty DRC-01 response reply"
    ),
    NoticeType.ASMT_10: (
        "Section 61 scrutiny of returns GSTR-3B discrepancy ASMT-10 ASMT-11 "
        "Rule 99 explanation taxpayer response"
    ),
    NoticeType.ITC_MISMATCH: (
        "Section 16 input tax credit eligibility conditions GSTR-2B GSTR-3B "
        "Rule 88D DRC-01C ITC mismatch excess availment response"
    ),
    NoticeType.UNKNOWN: "GST notice response general provisions",
}


def _build_query(notice: ClassifiedNotice) -> str:
    """Construct a focused retrieval query from the notice details."""
    base = _QUERY_TEMPLATES.get(notice.notice_type, _QUERY_TEMPLATES[NoticeType.UNKNOWN])
    # Append governing sections mentioned in the notice for extra precision
    extras = " ".join(s for s in notice.governing_sections if s not in base)
    return f"{base} {extras}".strip()


# ── Required annexures by notice type (deterministic — law-defined) ───────────

_REQUIRED_ANNEXURES: dict[NoticeType, list[str]] = {
    NoticeType.DRC_01: [
        "Reconciliation of ITC claimed vs GSTR-2B (Annexure A)",
        "GSTR-3B vs GSTR-2B comparison table",
        "Copies of supplier invoices for disputed ITC",
    ],
    NoticeType.ASMT_10: [
        "Reconciliation of GSTR-1 vs GSTR-3B outward supplies",
        "Explanation of timing differences or amendments",
    ],
    NoticeType.ITC_MISMATCH: [
        "GSTR-2B vs GSTR-3B ITC comparison (Annexure B)",
        "Supplier-wise ITC detail with invoice references",
        "Evidence of payment to suppliers",
    ],
    NoticeType.UNKNOWN: ["Relevant supporting documents as applicable"],
}


# ── Lazy ADK wiring ───────────────────────────────────────────────────────────
# Built on first real call so module import succeeds without GCP credentials.

_APP_NAME = "noticeflow-researcher"
_USER_ID = "system"

_session_service = InMemorySessionService()
_runner: Optional[Runner] = None


def _build_runner() -> Runner:
    datastore_path = (
        f"projects/{config.get_project_id()}/locations/{config.VERTEX_SEARCH_LOCATION}"
        f"/collections/default_collection/dataStores/{config.DATASTORE_ID}"
    )
    search_tool = VertexAiSearchTool(data_store_id=datastore_path)
    agent = LlmAgent(
        model=config.MODEL_FLASH,
        name="researcher",
        description="Retrieves relevant GST law citations for a classified notice.",
        instruction=_INSTRUCTION,
        tools=[search_tool],
        output_key="researcher_result",
        generate_content_config=config.gen_config(),
    )
    return Runner(agent=agent, app_name=_APP_NAME, session_service=_session_service)


def _get_runner() -> Runner:
    global _runner
    if _runner is None:
        _runner = _build_runner()
    return _runner


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _parse_response(raw_text: str, notice: ClassifiedNotice) -> LegalContext:
    """Parse Gemini's JSON response into LegalContext. Falls back on parse errors."""
    # Strip accidental markdown fences the model sometimes adds despite instructions
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    try:
        raw = json.loads(text)
        output = _ResearcherOutput.model_validate(raw)
    except (json.JSONDecodeError, Exception):
        # Fallback: wrap the raw text as a single unstructured citation
        return _fallback_context(notice, raw_text)

    citations = [
        Citation(
            source_id=c.source_id,
            source_type=c.source_type,
            snippet=c.snippet,
            relevance_note=c.relevance_note,
        )
        for c in output.citations
    ]

    return LegalContext(
        notice_type=notice.notice_type,
        citations=citations,
        applicable_response_options=output.applicable_response_options,
        required_annexures=output.required_annexures
        or _REQUIRED_ANNEXURES.get(notice.notice_type, []),
    )


def _fallback_context(notice: ClassifiedNotice, raw_text: str = "") -> LegalContext:
    """Minimal LegalContext used when datastore is unconfigured or parsing fails."""
    return LegalContext(
        notice_type=notice.notice_type,
        citations=[
            Citation(
                source_id="CGST Act 2017",
                source_type="act",
                snippet=raw_text[:500] if raw_text else "(retrieval not available)",
                relevance_note="Fallback — datastore not configured or retrieval failed.",
            )
        ],
        applicable_response_options=[
            "File a detailed reply within the stipulated deadline.",
            "Provide reconciliation of figures with supporting documents.",
        ],
        required_annexures=_REQUIRED_ANNEXURES.get(notice.notice_type, []),
    )


# ── Public API ────────────────────────────────────────────────────────────────

async def research_notice(notice: ClassifiedNotice) -> LegalContext:
    """Retrieve GST law citations relevant to a classified notice.

    Returns a stub LegalContext (without Vertex AI Search) if the datastore
    is not yet configured — safe for pipeline testing pre-GCP.

    Raises RuntimeError only on unexpected ADK/Gemini failures.
    """
    # Refuse to fall back to an ungrounded citation when grounding is required
    # (deployed engine / demo cockpit). Only pure local dev may take the fallback.
    config.assert_datastore_configured()
    if not config.DATASTORE_ID:
        return _fallback_context(notice)

    query = _build_query(notice)
    runner = _get_runner()

    session_id = str(uuid.uuid4())
    await _session_service.create_session(
        app_name=_APP_NAME,
        user_id=_USER_ID,
        session_id=session_id,
    )

    final_text: str | None = None
    evidence: list[RetrievedChunk] = []
    seen: set = set()
    async for event in runner.run_async(
        user_id=_USER_ID,
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=query)],
        ),
    ):
        # Capture what Vertex AI Search actually returned so citations can be
        # verified against it downstream (the anti-hallucination guarantee).
        collect_grounding(event, evidence, seen)
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_text = part.text
                    break

    legal_ctx = _parse_response(final_text, notice) if final_text else _fallback_context(notice)
    return legal_ctx.model_copy(update={"retrieved_evidence": evidence})


# ── Manual smoke-test entry point ─────────────────────────────────────────────
# Usage: python -m noticeflow.agents.researcher <notice_type>
# e.g.:  python -m noticeflow.agents.researcher DRC_01

if __name__ == "__main__":
    import asyncio
    import sys

    from noticeflow.schemas import ClassifiedNotice, NoticeType

    notice_type_str = sys.argv[1].upper() if len(sys.argv) > 1 else "DRC_01"
    try:
        nt = NoticeType(notice_type_str)
    except ValueError:
        print(f"Unknown notice type: {notice_type_str}. Use DRC_01, ASMT_10, or ITC_MISMATCH.")
        sys.exit(1)

    stub_notice = ClassifiedNotice(
        notice_type=nt,
        governing_sections={"DRC_01": ["Section 73", "Section 50"],
                            "ASMT_10": ["Section 61"],
                            "ITC_MISMATCH": ["Section 16"]}.get(nt.value, ["Section 73"]),
        issue_summary="Stub notice for manual testing.",
        raw_extracted_text="",
        confidence=1.0,
    )
    result = asyncio.run(research_notice(stub_notice))
    print(result.model_dump_json(indent=2))
