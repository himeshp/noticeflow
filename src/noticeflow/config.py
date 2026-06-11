import os
import sys
from dotenv import load_dotenv
from google.genai import types

load_dotenv()


def mcp_python_command() -> str:
    """Interpreter used to launch the stdio MCP ERP server.

    Locally: sys.executable (the active venv). For Agent Engine, the deploy
    script sets MCP_PYTHON_COMMAND=python3 before the agent is built, so the
    baked command resolves to the runtime's venv python (the local absolute
    path from sys.executable does not exist in the cloud container).
    """
    return os.environ.get("MCP_PYTHON_COMMAND") or sys.executable


def _require(key: str) -> str:
    """Return env var value or raise a clear error at call time (not import time)."""
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(
            f"Required env var '{key}' is not set. "
            "Copy .env.example to .env and fill in your GCP values."
        )
    return val


def _get_project_id() -> str:
    return _require("GOOGLE_CLOUD_PROJECT")


LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

# Vertex AI Search (Discovery Engine) only exists in "global", "us", or "eu" —
# NOT regional zones like us-central1. Decoupled from LOCATION (used by Gemini /
# Agent Engine). "global" uses the default API endpoint (no client_options needed).
VERTEX_SEARCH_LOCATION = os.environ.get("VERTEX_SEARCH_LOCATION", "global")

# Model IDs verified GA-served on Vertex AI (us-central1) on 2026-06-04.
# gemini-2.0-* and *-latest aliases 404 in this region; 2.5 is the current GA line.
MODEL_FLASH = os.environ.get("MODEL_FLASH", "gemini-2.5-flash")
MODEL_PRO = os.environ.get("MODEL_PRO", "gemini-2.5-pro")

DATASTORE_ID = os.environ.get("VERTEX_SEARCH_DATASTORE_ID", "")
GCS_CORPUS_BUCKET = os.environ.get("GCS_CORPUS_BUCKET", "")

# When true, the Researcher MUST be backed by a real Vertex AI Search datastore —
# the ungrounded fallback citation path is forbidden. The deploy script sets this
# for the Agent Engine runtime; the demo cockpit (api.py) forces it on at startup.
# Left false for local dev so the pipeline can still be exercised without GCP.
REQUIRE_DATASTORE = (
    os.environ.get("NOTICEFLOW_REQUIRE_DATASTORE", "false").lower() == "true"
)

# When true, the orchestrator wraps Drafter<->Critic in an ADK LoopAgent so the
# draft is deterministically reviewed (and re-drafted up to a cap) before the
# human gate. Default OFF — the linear pipeline is the proven/deployed default.
ENABLE_REVIEW_LOOP = (
    os.environ.get("NOTICEFLOW_ENABLE_REVIEW_LOOP", "false").lower() == "true"
)

# Optional HTTP Basic-auth gate for the public demo cockpit. When set (on Cloud
# Run), every cockpit route except /api/health requires this password before any
# Gemini call can fire — so bots/scrapers can't burn AI quota. Kept out of the
# PUBLIC repo: supply it via env (gcloud --set-env-vars), never hard-code it.
# Empty (the default) = no auth, so local dev stays open.
COCKPIT_PASSWORD = os.environ.get("NOTICEFLOW_COCKPIT_PASSWORD", "").strip()


# Confidence-gated human escalation (#3.8). The classifier self-reports a 0-1
# confidence in the notice type; below this threshold (for an otherwise KNOWN
# type) the packet is routed to a human ("needs human review — low confidence")
# rather than presented as ready to file. Env-overridable. Gemini tends to report
# high confidence on the supported types, so this fires only when the model is
# genuinely unsure — the "knows when not to act" maturity signal.
CONFIDENCE_THRESHOLD = float(
    os.environ.get("NOTICEFLOW_CONFIDENCE_THRESHOLD", "0.55")
)


def low_confidence(confidence: float) -> bool:
    """True if a classification confidence falls below the escalation threshold."""
    return confidence < CONFIDENCE_THRESHOLD


def low_confidence_reason(confidence: float) -> str:
    """Human-readable reason string for a low-confidence escalation. The only
    interpolated value is the numeric confidence (formatted as a percent), so
    the string is safe to render as text in the cockpit."""
    return (
        f"Low classification confidence ({confidence:.0%} < "
        f"{CONFIDENCE_THRESHOLD:.0%}) — a human should verify the notice type "
        "before filing."
    )


def assert_datastore_configured(strict: bool = False) -> None:
    """Raise if a datastore is required but VERTEX_SEARCH_DATASTORE_ID is unset.

    Guards the Researcher's ungrounded fallback so it can never silently emit a
    fake-looking citation in the deployed engine or the demo cockpit. Pass
    strict=True to require a datastore regardless of the env flag (the cockpit
    is always a demo surface). The message names the env var, never its value.
    """
    if (strict or REQUIRE_DATASTORE) and not DATASTORE_ID:
        raise RuntimeError(
            "VERTEX_SEARCH_DATASTORE_ID is not set, but grounding is required "
            "in this configuration. Refusing to run: an ungrounded fallback "
            "citation must never be presented as retrieved GST law. Set the "
            "datastore env var (see .env.example), or unset "
            "NOTICEFLOW_REQUIRE_DATASTORE for local dev-without-datastore."
        )


def get_project_id() -> str:
    """Returns GCP project ID. Raises RuntimeError if env var not set."""
    return _get_project_id()


def gen_config(**overrides) -> types.GenerateContentConfig:
    """GenerateContentConfig with client-side retry/backoff on transient errors.

    Gemini 2.5 on Vertex uses Dynamic Shared Quota — bursts can hit 429
    RESOURCE_EXHAUSTED even at low average rates. Exponential backoff with
    jitter (the ADK-recommended mitigation) lets calls survive transient
    rate-limiting instead of failing. Retry config lives in http_options, so
    it composes cleanly with output_schema (classifier) and tools
    (researcher / drafter). Pass **overrides for per-agent params (e.g. temperature).
    """
    return types.GenerateContentConfig(
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                attempts=5,
                initial_delay=1.0,
                max_delay=30.0,
                exp_base=2.0,
                jitter=0.5,
                http_status_codes=[429, 503],
            )
        ),
        **overrides,
    )


# Convenience constant — resolves at import time only if the var is already set.
# Use get_project_id() in code that runs in CI or offline tests.
PROJECT_ID: str = os.environ.get("GOOGLE_CLOUD_PROJECT", "")

# Validate Vertex AI routing when project is configured
if PROJECT_ID and os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() != "true":
    raise RuntimeError(
        "GOOGLE_GENAI_USE_VERTEXAI must be 'true' — never use AI Studio keys"
    )
