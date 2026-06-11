"""
Classifier agent — Gemini Flash, ADK 2.x LlmAgent with structured output.

Input : raw notice text (str).  Sample notices are .txt; for real PDFs pass the
        extracted text or upgrade to multimodal file upload via Gemini Files API.
Output: ClassifiedNotice (Pydantic model from schemas.py).
"""

import json
import uuid
from datetime import date
from typing import Optional

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from noticeflow import config
from noticeflow.schemas import ClassifiedNotice, NoticeType


# ── Internal output schema ────────────────────────────────────────────────────
# Omits raw_extracted_text (we already have it) and uses str for date fields
# so Gemini outputs ISO strings we convert to date objects after parsing.

class _ClassifierOutput(BaseModel):
    notice_type: NoticeType
    governing_sections: list[str] = Field(
        description="Legal sections cited, e.g. ['Section 73', 'Section 50']"
    )
    reference_number: Optional[str] = None
    gstin: Optional[str] = None
    tax_period: Optional[str] = None
    response_deadline: Optional[str] = None  # ISO "YYYY-MM-DD" or null
    demanded_amount: Optional[float] = None
    issue_summary: str
    confidence: float = Field(ge=0.0, le=1.0)


# ── Prompt ────────────────────────────────────────────────────────────────────

_INSTRUCTION = f"""You are a GST notice classifier for Indian tax law.

You will receive the full text of a GST notice. Extract the following fields precisely.

notice_type — one of:
  "ASMT_10"       Form GST ASMT-10, scrutiny under Section 61
  "DRC_01"        Form GST DRC-01 or DRC-01A, show-cause / demand under Section 73 or 74
  "ITC_MISMATCH"  Form GST DRC-01C, ITC mismatch under Section 16 / Rule 88D
  "UNKNOWN"       anything else — still extract whatever is present

governing_sections  all legal sections mentioned, e.g. ["Section 73", "Section 50"]
reference_number    the Reference No or DIN printed on the notice, or null
gstin               15-character GSTIN of the taxpayer, or null
tax_period          e.g. "FY2023-24" or "04/2024", or null
response_deadline   ISO date "YYYY-MM-DD" of the reply deadline, or null
demanded_amount     TOTAL amount demanded in INR (tax + interest + penalty), or null
issue_summary       1-3 sentence plain-language summary of what the notice alleges
confidence          your confidence in notice_type, 0.0 to 1.0

Rules:
- Do not fabricate any field. When unsure, use null.
- demanded_amount is the combined total, not just the base tax.
- Respond ONLY with a valid JSON object matching the schema below.
  No prose, no markdown fences, no commentary outside the JSON.

Required output schema:
{json.dumps(_ClassifierOutput.model_json_schema(), indent=2)}
"""


# ── ADK wiring (module-level singletons — one runner per process) ─────────────

_APP_NAME = "noticeflow-classifier"
_USER_ID = "system"

_session_service = InMemorySessionService()

_agent = LlmAgent(
    model=config.MODEL_FLASH,
    name="classifier",
    description="Classifies Indian GST notices into structured data.",
    instruction=_INSTRUCTION,
    output_schema=_ClassifierOutput,
    output_key="classifier_result",
    generate_content_config=config.gen_config(),
)

_runner = Runner(
    agent=_agent,
    app_name=_APP_NAME,
    session_service=_session_service,
)


# ── Public API ────────────────────────────────────────────────────────────────

async def classify_notice(notice_text: str) -> ClassifiedNotice:
    """Classify raw GST notice text and return a ClassifiedNotice.

    Callers should check result.notice_type != NoticeType.UNKNOWN before
    proceeding — the orchestrator short-circuits the pipeline on UNKNOWN.

    Raises RuntimeError if Gemini returns no parseable response.
    """
    session_id = str(uuid.uuid4())
    await _session_service.create_session(
        app_name=_APP_NAME,
        user_id=_USER_ID,
        session_id=session_id,
    )

    final_text: str | None = None
    async for event in _runner.run_async(
        user_id=_USER_ID,
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text=notice_text)],
        ),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_text = part.text
                    break

    if not final_text:
        raise RuntimeError("Classifier agent returned no response")

    try:
        raw = json.loads(final_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Classifier response is not valid JSON: {exc}\n"
            f"Raw response (first 500 chars): {final_text[:500]}"
        ) from exc

    output = _ClassifierOutput.model_validate(raw)

    deadline: date | None = None
    if output.response_deadline:
        try:
            deadline = date.fromisoformat(output.response_deadline)
        except ValueError:
            deadline = None

    return ClassifiedNotice(
        notice_type=output.notice_type,
        governing_sections=output.governing_sections,
        reference_number=output.reference_number,
        gstin=output.gstin,
        tax_period=output.tax_period,
        response_deadline=deadline,
        demanded_amount=output.demanded_amount,
        issue_summary=output.issue_summary,
        raw_extracted_text=notice_text,
        confidence=output.confidence,
    )


# ── Manual smoke-test entry point ─────────────────────────────────────────────
# Usage: python -m noticeflow.agents.classifier data/sample_notices/drc01_sec73.txt

if __name__ == "__main__":
    import asyncio
    import pathlib
    import sys

    if len(sys.argv) != 2:
        print("Usage: python -m noticeflow.agents.classifier <notice_file.txt>")
        sys.exit(1)

    notice_path = pathlib.Path(sys.argv[1])
    if not notice_path.exists():
        print(f"File not found: {notice_path}")
        sys.exit(1)

    text = notice_path.read_text(encoding="utf-8")
    result = asyncio.run(classify_notice(text))
    print(result.model_dump_json(indent=2))
