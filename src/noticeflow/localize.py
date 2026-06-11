"""Reply localization (#3.7) — an additive, post-draft translation step.

NoticeFlow's reply can be shown in **Hindi** or **bilingual** as an APAC-regional
accessibility layer. This runs *after* the Drafter (and the citation verifier /
confidence gate), translating only the two prose fields (`legal_basis`,
`reply_body`) into the requested language.

The English fields stay **canonical**: the form PDF (`forms/generator.py`) and the
citation verifier read them, so anti-hallucination and the statutory form are
unaffected by translation. The Hindi/bilingual text lands in display-only fields
(`*_localized`) the cockpit prefers. Citations, figures, GSTIN, dates, and
classification are never translated.

Fail-safe: on any error the packet is returned unchanged (English shown).

Mirrors the Classifier's ADK wiring (agents/classifier.py): a module-level
`LlmAgent` with `output_schema` (no tools) + `Runner`. Built at import — no GCP
call happens until `run_async` is invoked (so `en`/unsupported is a pure no-op).
"""

from __future__ import annotations

import json
import uuid

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from noticeflow import config
from noticeflow.schemas import ResponsePacket

SUPPORTED = {"en", "hi", "bilingual"}


class _Localized(BaseModel):
    legal_basis: str = Field(description="legal_basis in the target language")
    reply_body: str = Field(description="reply_body in the target language")


_INSTRUCTION = f"""You are a legal translator for Indian GST notice replies.

You receive a JSON object with: "mode" (either "hi" or "bilingual") and two English
fields, "legal_basis" and "reply_body". Produce the SAME two fields, transformed per
the mode. Output ONLY a valid JSON object matching the schema below — no prose, no
markdown fences.

Modes:
- "hi"        : render both fields in FORMAL LEGAL HINDI (Devanagari script), the
                register a tax practitioner would file. Statutory labels may be
                Hindi (e.g. "Section 73" -> "धारा 73", "Rule 36(4)" -> "नियम 36(4)"),
                but the numeric part stays exactly as given.
- "bilingual" : for each numbered point / sentence, give the original English line,
                then on the NEXT line its formal legal Hindi (Devanagari) translation.

Hard rules (both modes):
- Preserve EXACTLY, as digits: all amounts (e.g. 85,000), GSTINs (e.g.
  24ABCDE1234F1Z5), circular numbers (e.g. 183/15/2022-GST), and the numeric part of
  every section/rule reference.
- Preserve the numbered-list structure and line breaks (newlines between points).
- Translate only — do NOT add, remove, or reinterpret any legal content.

Required output schema:
{json.dumps(_Localized.model_json_schema(), indent=2)}
"""

_APP_NAME = "noticeflow-localize"
_USER_ID = "system"

_session_service = InMemorySessionService()

_agent = LlmAgent(
    model=config.MODEL_FLASH,
    name="localizer",
    description="Translates a GST reply's prose into Hindi or bilingual.",
    instruction=_INSTRUCTION,
    output_schema=_Localized,
    output_key="localize_result",
    generate_content_config=config.gen_config(),
)

_runner = Runner(
    agent=_agent,
    app_name=_APP_NAME,
    session_service=_session_service,
)


async def localize_packet(packet: ResponsePacket, language: str) -> ResponsePacket:
    """Return the packet with `*_localized` prose in `language`.

    `en` (or any unsupported value) is a pure no-op — no LLM call. Any failure
    degrades to English (localized fields left None). The canonical English
    `legal_basis`/`reply_body` are never mutated.
    """
    if language not in SUPPORTED or language == "en":
        return packet.model_copy(update={"language": "en"})

    try:
        session_id = str(uuid.uuid4())
        await _session_service.create_session(
            app_name=_APP_NAME, user_id=_USER_ID, session_id=session_id,
        )
        user_msg = json.dumps({
            "mode": language,
            "legal_basis": packet.legal_basis,
            "reply_body": packet.reply_body,
        })

        final_text: str | None = None
        async for event in _runner.run_async(
            user_id=_USER_ID,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=user_msg)]),
        ):
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        final_text = part.text
                        break

        if not final_text:
            return packet.model_copy(update={"language": language})

        out = _Localized.model_validate(json.loads(final_text))
        return packet.model_copy(update={
            "language": language,
            "legal_basis_localized": out.legal_basis,
            "reply_body_localized": out.reply_body,
        })
    except Exception:
        # Never break the pipeline for a translation failure — show English.
        return packet.model_copy(update={"language": language})
