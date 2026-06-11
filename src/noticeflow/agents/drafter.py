"""
Drafter agent — Gemini Pro + MCP ERP tool, ADK 2.x LlmAgent.

Input : ClassifiedNotice + LegalContext (from prior pipeline stages)
Output: ResponsePacket

MCPToolset is constructed inline (synchronous) — ADK manages the server
process lifecycle. The ERP server path is resolved from inside this package,
never from user-supplied input (prevents command injection / SSRF).
"""

import json
import pathlib
import sys
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from google.adk.agents import LlmAgent
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
)

# ── MCP server path (package-internal, never from user input) ─────────────────
_ERP_SERVER_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "mcp" / "erp_server.py"
)


# ── Internal output schema ────────────────────────────────────────────────────
# Drafter uses MCPToolset → cannot use output_schema. We instruct JSON output
# and parse it. The annexure fields mirror ReconciliationData so Gemini can
# copy them verbatim from the MCP tool result.

class _AnnexureOut(BaseModel):
    gstin: str
    tax_period: str
    gstr3b_tax_paid: float
    gstr2b_itc_available: float
    gstr3b_itc_claimed: float
    itc_mismatch_amount: float
    output_tax_liability: float
    notes: Optional[str] = None
    # Copied verbatim from the MCP record when present (TURNOVER notices, e.g. ASMT-10)
    recon_type: str = "ITC"
    gstr1_outward_tax: Optional[float] = None
    gstr3b_outward_tax: Optional[float] = None
    outward_tax_difference: Optional[float] = None


class _DrafterOutput(BaseModel):
    legal_basis: str = Field(
        description="Prose paragraph citing the governing law for the response"
    )
    reply_body: str = Field(
        description="Full point-by-point reply to the notice, filing-ready"
    )
    cited_source_ids: list[str] = Field(
        description="source_id values from LegalContext actually referenced in reply_body"
    )
    deadline_urgent: bool = Field(
        description="True if response_deadline is within 7 days of today"
    )
    annexure: _AnnexureOut = Field(
        description="Reconciliation figures from get_reconciliation_data tool call"
    )


# ── Prompt ────────────────────────────────────────────────────────────────────

_INSTRUCTION = f"""You are a GST response drafter for Indian tax law.

You will receive:
1. A classified GST notice (JSON) with the taxpayer's GSTIN and tax period.
2. Legal context (JSON) with retrieved law citations and required annexures.

Your job:
STEP 1 — Call get_reconciliation_data(gstin, tax_period) using the GSTIN and tax period
         from the classified notice. Use the returned figures in your reply.

STEP 2 — Draft a filing-ready reply to the notice using:
         - The legal citations provided (cite only those provided, no invented law)
         - The reconciliation figures from step 1
         - The applicable response options from the legal context

STEP 3 — Output a valid JSON object matching the schema below. No prose before or
         after. No markdown fences. Pure JSON only.

Rules:
- cited_source_ids must only contain source_ids from the provided legal context.
- annexure must be populated with the exact figures returned by the MCP tool call.
- deadline_urgent is True if the response_deadline is within 7 days of today ({datetime.now(timezone.utc).date().isoformat()}).
- reply_body must be formal, structured with numbered points, and filing-ready.
- Do NOT invent legal provisions not present in the legal context.

Output schema:
{json.dumps(_DrafterOutput.model_json_schema(), indent=2)}
"""


# ── ADK wiring ────────────────────────────────────────────────────────────────

_APP_NAME = "noticeflow-drafter"
_USER_ID = "system"

_session_service = InMemorySessionService()
_runner: Optional[Runner] = None


def _build_runner() -> Runner:
    mcp_toolset = MCPToolset(
        connection_params=StdioServerParameters(
            # Interpreter resolves at build time: sys.executable locally, or
            # python3 in the Agent Engine runtime (the local path does not exist
            # there). Module invocation works because the package is installed.
            command=config.mcp_python_command(),
            args=["-m", "noticeflow.mcp.erp_server"],
        ),
        tool_filter=["get_reconciliation_data"],
    )
    agent = LlmAgent(
        model=config.MODEL_PRO,
        name="drafter",
        description="Drafts a GST notice reply with reconciliation figures from the ERP.",
        instruction=_INSTRUCTION,
        tools=[mcp_toolset],
        output_key="drafter_result",
        generate_content_config=config.gen_config(),
    )
    return Runner(agent=agent, app_name=_APP_NAME, session_service=_session_service)


def _get_runner() -> Runner:
    global _runner
    if _runner is None:
        _runner = _build_runner()
    return _runner


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _build_prompt(notice: ClassifiedNotice, legal_ctx: LegalContext) -> str:
    """Compose the user message for the Drafter agent."""
    return json.dumps({
        "classified_notice": notice.model_dump(mode="json"),
        "legal_context": legal_ctx.model_dump(mode="json"),
    }, indent=2, default=str)


def _parse_response(
    raw_text: str,
    notice: ClassifiedNotice,
    legal_ctx: LegalContext,
) -> ResponsePacket:
    """Parse Drafter's JSON into ResponsePacket. Falls back on parse errors."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    try:
        raw = json.loads(text)
        output = _DrafterOutput.model_validate(raw)
    except Exception:
        return _fallback_packet(notice, legal_ctx)

    # Only include citations from LegalContext that Drafter actually referenced
    citation_map = {c.source_id: c for c in legal_ctx.citations}
    cited = [
        citation_map[sid]
        for sid in output.cited_source_ids
        if sid in citation_map
    ]
    # Fall back to all citations if the model cited nothing (still needs something)
    if not cited:
        cited = legal_ctx.citations

    annexure = ReconciliationData(
        gstin=output.annexure.gstin,
        tax_period=output.annexure.tax_period,
        gstr3b_tax_paid=output.annexure.gstr3b_tax_paid,
        gstr2b_itc_available=output.annexure.gstr2b_itc_available,
        gstr3b_itc_claimed=output.annexure.gstr3b_itc_claimed,
        itc_mismatch_amount=output.annexure.itc_mismatch_amount,
        output_tax_liability=output.annexure.output_tax_liability,
        notes=output.annexure.notes,
        recon_type=output.annexure.recon_type,
        gstr1_outward_tax=output.annexure.gstr1_outward_tax,
        gstr3b_outward_tax=output.annexure.gstr3b_outward_tax,
        outward_tax_difference=output.annexure.outward_tax_difference,
    )

    return ResponsePacket(
        notice_type=notice.notice_type,
        reference_number=notice.reference_number,
        gstin=notice.gstin,
        tax_period=notice.tax_period,
        response_deadline=notice.response_deadline,
        deadline_urgent=output.deadline_urgent,
        legal_basis=output.legal_basis,
        reply_body=output.reply_body,
        citations=cited,
        annexure=annexure,
        reviewer_status="PENDING_REVIEW",
    )


def _fallback_packet(
    notice: ClassifiedNotice,
    legal_ctx: LegalContext,
) -> ResponsePacket:
    """Minimal ResponsePacket used when Drafter fails or GCP is unavailable."""
    today = datetime.now(timezone.utc).date()
    urgent = (
        (notice.response_deadline - today).days <= 7
        if notice.response_deadline
        else False
    )
    fallback_annexure = ReconciliationData(
        gstin=notice.gstin or "UNKNOWN",
        tax_period=notice.tax_period or "UNKNOWN",
        gstr3b_tax_paid=0.0,
        gstr2b_itc_available=0.0,
        gstr3b_itc_claimed=0.0,
        itc_mismatch_amount=0.0,
        output_tax_liability=0.0,
        notes="Fallback record — Drafter could not retrieve ERP data.",
    )
    return ResponsePacket(
        notice_type=notice.notice_type,
        reference_number=notice.reference_number,
        gstin=notice.gstin,
        tax_period=notice.tax_period,
        response_deadline=notice.response_deadline,
        deadline_urgent=urgent,
        legal_basis=(
            "Reply drafted under the provisions cited in the legal context. "
            "Please verify citations before filing."
        ),
        reply_body=(
            "DRAFT REPLY\n\n"
            "This is a fallback draft. Please review and complete before filing.\n\n"
            f"Notice type   : {notice.notice_type.value}\n"
            f"GSTIN         : {notice.gstin}\n"
            f"Tax period    : {notice.tax_period}\n"
            f"Issue summary : {notice.issue_summary}\n"
        ),
        citations=legal_ctx.citations,
        annexure=fallback_annexure,
        reviewer_status="PENDING_REVIEW",
    )


# ── Public API ────────────────────────────────────────────────────────────────

async def draft_response(
    notice: ClassifiedNotice,
    legal_ctx: LegalContext,
) -> ResponsePacket:
    """Draft a GST reply packet from classified notice + legal context.

    Calls the MCP ERP tool for reconciliation figures, then drafts the reply.
    Always returns reviewer_status="PENDING_REVIEW" — human must approve.
    Falls back to a stub packet on MCP/LLM failures.
    """
    runner = _get_runner()
    session_id = str(uuid.uuid4())
    await _session_service.create_session(
        app_name=_APP_NAME,
        user_id=_USER_ID,
        session_id=session_id,
    )

    prompt = _build_prompt(notice, legal_ctx)
    final_text: str | None = None

    async for event in runner.run_async(
        user_id=_USER_ID,
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=prompt)],
        ),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_text = part.text
                    break

    if not final_text:
        return _fallback_packet(notice, legal_ctx)

    return _parse_response(final_text, notice, legal_ctx)


# ── Manual smoke-test entry point ─────────────────────────────────────────────
# Usage: python -m noticeflow.agents.drafter
# (uses stub notice/legal_ctx so GCP + MCP must be running)

if __name__ == "__main__":
    import asyncio
    from noticeflow.schemas import Citation, ClassifiedNotice, LegalContext, NoticeType

    stub_notice = ClassifiedNotice(
        notice_type=NoticeType.DRC_01,
        governing_sections=["Section 73", "Section 50"],
        gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24",
        issue_summary="Short payment due to excess ITC claimed.",
        raw_extracted_text="",
        confidence=0.95,
    )
    stub_legal = LegalContext(
        notice_type=NoticeType.DRC_01,
        citations=[Citation(
            source_id="CGST Act 2017, Section 73",
            source_type="act",
            snippet="Where any tax has not been paid or short paid...",
            relevance_note="Governs demand for short payment of tax.",
        )],
        applicable_response_options=["Explain ITC availment basis."],
        required_annexures=["GSTR-2B vs 3B comparison"],
    )
    result = asyncio.run(draft_response(stub_notice, stub_legal))
    print(result.model_dump_json(indent=2))
