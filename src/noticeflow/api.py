"""
FastAPI backend for the NoticeFlow demo cockpit.

Streams the three-agent pipeline as SSE so the frontend can animate
each lane completing in real time.

Run locally:
    uvicorn noticeflow.api:app --reload --port 8000

Then start the frontend:
    cd frontend && npm run dev
"""

import base64
import json
import mimetypes
import pathlib
import secrets
import time
from typing import AsyncGenerator

# Ensure StaticFiles serves the pdf.js worker (.mjs) with a JS MIME type — Python's
# mimetypes doesn't always know .mjs, and browsers reject workers/modules served as
# text/plain. (Vite serves it correctly in dev; this fixes the built/deployed SPA.)
mimetypes.add_type("text/javascript", ".mjs")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from noticeflow import config
from noticeflow.schemas import ResponsePacket

app = FastAPI(title="NoticeFlow API", version="0.1.0")


@app.on_event("startup")
async def _require_grounding() -> None:
    """The cockpit is a demo surface — never serve ungrounded citations.

    Fail fast at startup (not mid-demo) if the Vertex AI Search datastore is not
    configured, so the Researcher can never present a fallback as retrieved law.
    """
    config.assert_datastore_configured(strict=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _basic_auth_gate(request, call_next):
    """Server-side HTTP Basic-auth gate for the public demo cockpit.

    When NOTICEFLOW_COCKPIT_PASSWORD is set (production / Cloud Run), every route
    except the health check must present the password before the request reaches
    any handler — so a bot cannot hit /api/run and burn Gemini quota. The browser
    handles the credential prompt and re-sends it on every same-origin request
    (XHR/fetch/SSE/Range), so no frontend change is needed. Username is ignored;
    only the password is checked, in constant time. Unset password = open (local
    dev). The password itself is never echoed back in any response.
    """
    password = config.COCKPIT_PASSWORD
    if password and request.url.path != "/api/health":
        header = request.headers.get("Authorization", "")
        authorized = False
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8", "replace")
                _, _, supplied = decoded.partition(":")
                authorized = secrets.compare_digest(supplied, password)
            except Exception:
                authorized = False
        if not authorized:
            return Response(
                content="Authentication required",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="NoticeFlow"'},
            )
    return await call_next(request)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "data" / "sample_notices"

SAMPLE_FILES = {
    "drc01": "drc01_sec73.txt",
    "asmt10": "asmt10_sec61.txt",
    "itc_mismatch": "itc_mismatch_sec16.txt",
}


class RunRequest(BaseModel):
    text: str
    language: str = "en"  # en | hi | bilingual (#3.7); validated in the handler


async def _pipeline_sse(notice_text: str, language: str = "en") -> AsyncGenerator[str, None]:
    """Yield SSE events as each agent stage completes.

    Each event carries an optional `meta` block (#3.9) with read-only
    observability: per-agent wall-clock timing, the model used, and integer
    counts. The retrieved legal text is NEVER serialized to the browser — only
    its chunk count — so the trace cannot leak corpus content.
    """
    def _event(stage: str, data: dict, meta: dict | None = None) -> str:
        payload: dict = {"stage": stage, "data": data}
        if meta is not None:
            payload["meta"] = meta
        return f"data: {json.dumps(payload)}\n\n"

    try:
        from noticeflow.agents.classifier import classify_notice
        from noticeflow.schemas import NoticeType

        t = time.perf_counter()
        classified = await classify_notice(notice_text)
        yield _event(
            "classifier",
            classified.model_dump(mode="json"),
            {"elapsed_ms": round((time.perf_counter() - t) * 1000), "model": config.MODEL_FLASH},
        )

        if classified.notice_type == NoticeType.UNKNOWN:
            yield "data: [DONE]\n\n"
            return

        from noticeflow.agents.researcher import research_notice
        t = time.perf_counter()
        legal_ctx = await research_notice(classified)
        # Don't ship the raw retrieved chunks to the browser — only the citations.
        yield _event(
            "researcher",
            legal_ctx.model_dump(mode="json", exclude={"retrieved_evidence"}),
            {
                "elapsed_ms": round((time.perf_counter() - t) * 1000),
                "model": config.MODEL_FLASH,
                "citations": len(legal_ctx.citations),
                "evidence_chunks": len(legal_ctx.retrieved_evidence),  # count only, never the text
            },
        )

        from noticeflow.agents.drafter import draft_response
        from noticeflow.gating import apply_confidence_gate
        from noticeflow.localize import localize_packet
        from noticeflow.sources import annotate_citation_sources
        from noticeflow.verify.citations import apply_citation_verification
        t = time.perf_counter()
        packet = await draft_response(classified, legal_ctx)
        # Code-enforced anti-hallucination: drop any citation not traceable to
        # retrieved law, and attach the verification audit (badge data).
        packet = apply_citation_verification(packet, legal_ctx.retrieved_evidence)
        # #3.8 — flag low-confidence (but KNOWN) classifications for a human.
        packet = apply_confidence_gate(packet, classified.notice_type, classified.confidence)
        # #3.7 — localize the reply prose (no-op for English; English stays canonical).
        packet = await localize_packet(packet, language)
        # Attach source PDF + page to each citation (for the in-app source viewer).
        packet = annotate_citation_sources(packet)
        yield _event(
            "drafter",
            packet.model_dump(mode="json"),
            {
                "elapsed_ms": round((time.perf_counter() - t) * 1000),
                "model": config.MODEL_PRO,
                "language": packet.language,
            },
        )

    except Exception as exc:
        yield f"data: {json.dumps({'stage': 'error', 'message': str(exc)})}\n\n"

    yield "data: [DONE]\n\n"


@app.post("/api/run")
async def run_pipeline(req: RunRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Notice text is required")
    from noticeflow.localize import SUPPORTED
    if req.language not in SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language {req.language!r}; expected one of {sorted(SUPPORTED)}",
        )
    return StreamingResponse(
        _pipeline_sse(req.text, req.language),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/samples/{name}")
async def get_sample(name: str):
    if name not in SAMPLE_FILES:
        raise HTTPException(status_code=404, detail=f"Unknown sample: {name!r}")
    filename = SAMPLE_FILES[name]
    path = SAMPLE_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Sample file missing: {filename}")
    # Substitute {{ISSUE_DATE}}/{{DEADLINE}} with dates relative to today so the
    # demo's urgency banner always shows an upcoming deadline (never "overdue").
    from noticeflow.samples import render_sample_text
    text = render_sample_text(filename, path.read_text(encoding="utf-8"))
    return {"name": name, "text": text}


@app.post("/api/form")
async def download_form(packet: ResponsePacket):
    """Render the (human-reviewed) packet into its statutory GST reply form PDF.

    Deterministic post-step — the packet is Pydantic-validated, the PDF is built
    in memory, and the download filename is allow-listed (no header injection).
    """
    from noticeflow.forms import generate_form_pdf, safe_filename

    pdf = generate_form_pdf(packet)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename(packet)}"'},
    )


@app.get("/api/source/{doc_key}")
async def get_source_pdf(doc_key: str):
    """Serve one of the bundled CBIC source PDFs for the in-app pdf.js viewer.

    doc_key is checked against a fixed allow-list (sources.DOC_FILES); the path is
    built only from the allow-listed filename constant — never from raw input — so
    there is no path traversal. FileResponse honors HTTP Range (pdf.js range-loads).
    """
    from noticeflow.sources import source_pdf_path

    path = source_pdf_path(doc_key)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Unknown source document: {doc_key!r}")
    return FileResponse(
        str(path),
        media_type="application/pdf",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve the built React SPA from the same origin (single public URL). Mounted
# LAST so the explicit /api/* routes above always take precedence; this only
# serves index.html + /assets read-only. Absent in dev (Vite serves the SPA).
_DIST = REPO_ROOT / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("noticeflow.api:app", host="0.0.0.0", port=port)
