"""
deploy_agent_engine.py — deploy the NoticeFlow orchestrator to Vertex AI Agent Engine.

Agent Engine runs Python 3.10/3.12, so deploy from a 3.12 venv (see below), NOT
the default 3.14 dev venv — cloudpickle must match the runtime.

Usage (from repo root):
    /usr/local/bin/python3.12 -m venv .venv312
    source .venv312/bin/activate
    pip install -e . "google-cloud-aiplatform[adk,agent_engines]"
    python scripts/deploy_agent_engine.py            # deploy
    python scripts/deploy_agent_engine.py --test     # smoke-test the latest deployment
    python scripts/deploy_agent_engine.py --list      # list deployed engines

Env (from .env): GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION,
VERTEX_SEARCH_LOCATION, VERTEX_SEARCH_DATASTORE_ID, MODEL_FLASH, MODEL_PRO.
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

import vertexai
from vertexai import agent_engines
from vertexai.preview import reasoning_engines

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
STAGING_BUCKET = os.environ.get(
    "AGENT_ENGINE_STAGING_BUCKET", "gs://notice-flow-agent-staging"
)
DISPLAY_NAME = "NoticeFlow"

# Config the deployed runtime needs (no .env in the cloud — pass via env_vars).
# NOTE: GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION are RESERVED — Agent Engine
# injects them automatically, so passing them here is rejected. config.py reads
# them from the runtime-provided values.
_RUNTIME_ENV = {
    "GOOGLE_GENAI_USE_VERTEXAI": "true",
    # Forbid the ungrounded fallback citation path in the deployed engine —
    # config.assert_datastore_configured() raises if the datastore is missing.
    "NOTICEFLOW_REQUIRE_DATASTORE": "true",
    "VERTEX_SEARCH_LOCATION": os.environ.get("VERTEX_SEARCH_LOCATION", "global"),
    "VERTEX_SEARCH_DATASTORE_ID": os.environ.get("VERTEX_SEARCH_DATASTORE_ID", ""),
    "MODEL_FLASH": os.environ.get("MODEL_FLASH", "gemini-2.5-flash"),
    "MODEL_PRO": os.environ.get("MODEL_PRO", "gemini-2.5-pro"),
}

# Runtime dependencies. google-cloud-aiplatform[adk,agent_engines] pulls google-adk;
# discoveryengine (Vertex AI Search) and mcp (ERP server) must be listed explicitly.
_REQUIREMENTS = [
    "google-cloud-aiplatform[adk,agent_engines]",
    "google-cloud-discoveryengine>=0.13.0",
    "mcp>=1.0.0",
    "pydantic>=2.7.0",
    "python-dotenv>=1.0.0",
]

# Ship a built wheel (not the raw src/ dir): the runtime pip-installs it so
# `import noticeflow` works during cloudpickle load, and `python -m
# noticeflow.mcp.erp_server` launches the MCP server. erp_data/*.json is bundled
# via [tool.setuptools.package-data]. Built fresh by _build_wheel().
import glob
import subprocess


def _build_wheel() -> str:
    """Build the noticeflow wheel into the repo root and return its filename.

    The wheel sits at the deploy CWD (repo root) so it can be referenced by bare
    filename in BOTH extra_packages (uploads it) and requirements (installs it).
    extra_packages only *copies* a .whl; requirements is what pip-installs it.
    """
    import shutil

    print("Building wheel ...")
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", "dist"],
        check=True,
    )
    wheels = sorted(glob.glob("dist/noticeflow-*.whl"))
    if not wheels:
        print("[ERROR] wheel build produced no .whl in dist/")
        sys.exit(1)
    name = os.path.basename(wheels[-1])
    shutil.copyfile(wheels[-1], name)  # copy to repo root (CWD)
    return name


def _require_env() -> None:
    missing = [
        k for k in ("GOOGLE_CLOUD_PROJECT", "VERTEX_SEARCH_DATASTORE_ID")
        if not os.environ.get(k)
    ]
    if missing:
        print(f"[ERROR] Missing env vars: {', '.join(missing)} — fill .env first.")
        sys.exit(1)


def deploy() -> None:
    _require_env()
    print("=" * 60)
    print("Deploying NoticeFlow to Vertex AI Agent Engine")
    print(f"  Project : {PROJECT}")
    print(f"  Location: {LOCATION}")
    print(f"  Staging : {STAGING_BUCKET}")
    print(f"  Datastore: {_RUNTIME_ENV['VERTEX_SEARCH_DATASTORE_ID']} @ {_RUNTIME_ENV['VERTEX_SEARCH_LOCATION']}")
    print("=" * 60)

    vertexai.init(project=PROJECT, location=LOCATION, staging_bucket=STAGING_BUCKET)

    # Bake the MCP launch command BEFORE building the agent. It must be the
    # runtime venv interpreter where our wheel is installed — bare "python3"
    # resolves to /usr/local/bin/python3 (system, no noticeflow). Agent Engine
    # installs deps into /code/.venv.
    os.environ["MCP_PYTHON_COMMAND"] = "/code/.venv/bin/python"

    # Build the concrete pipeline (NOT the lazy proxy — it must serialize cleanly).
    from noticeflow.agents.orchestrator import _get_root_agent

    root = _get_root_agent()
    app = reasoning_engines.AdkApp(agent=root, enable_tracing=True)

    wheel = _build_wheel()
    print(f"Shipping wheel: {wheel} (uploaded via extra_packages, installed via requirements)")

    print("\nUploading + building (this can take 5-15 min) ...")
    remote = agent_engines.create(
        agent_engine=app,
        display_name=DISPLAY_NAME,
        requirements=_REQUIREMENTS + [wheel],   # install the wheel in the runtime
        extra_packages=[wheel],                 # upload the wheel file
        env_vars=_RUNTIME_ENV,
    )
    print("\n" + "=" * 60)
    print("✓ Deployed.")
    print(f"  Resource name: {remote.resource_name}")
    print("\nTest it:  python scripts/deploy_agent_engine.py --test")
    print("=" * 60)


def _latest_engine():
    engines = list(agent_engines.list())
    matches = [e for e in engines if getattr(e, "display_name", "") == DISPLAY_NAME]
    if not matches:
        print(f"[ERROR] No deployed engine named {DISPLAY_NAME!r}. Deploy first.")
        sys.exit(1)
    return matches[0]


def list_engines() -> None:
    vertexai.init(project=PROJECT, location=LOCATION, staging_bucket=STAGING_BUCKET)
    for e in agent_engines.list():
        print(f"  {getattr(e, 'display_name', '?'):20s}  {e.resource_name}")


def test() -> None:
    vertexai.init(project=PROJECT, location=LOCATION, staging_bucket=STAGING_BUCKET)
    remote = _latest_engine()
    print(f"Testing {remote.resource_name}")

    notice = open("data/sample_notices/drc01_sec73.txt", encoding="utf-8").read()
    session = remote.create_session(user_id="judge")
    print("Streaming pipeline events ...\n")
    for event in remote.stream_query(
        user_id="judge",
        session_id=session["id"],
        message=notice,
    ):
        # Print compact author + any text part
        author = event.get("author", "?") if isinstance(event, dict) else "?"
        print(f"  [{author}] {str(event)[:160]}")
    print("\n✓ Stream complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy/test NoticeFlow on Agent Engine.")
    parser.add_argument("--test", action="store_true", help="Smoke-test the latest deployment")
    parser.add_argument("--list", action="store_true", help="List deployed engines")
    args = parser.parse_args()

    if args.list:
        list_engines()
    elif args.test:
        test()
    else:
        deploy()
