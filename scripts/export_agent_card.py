"""scripts/export_agent_card.py — write the A2A agent card to a static file (#2.5).

Produces docs/submission/agent-card.json: a spec-compliant A2A AgentCard that
judges can read without running the server. Pure (no GCP, no network); writes one
fixed in-repo path.

Run (from repo root, with the a2a extra installed):
    pip install -e ".[a2a]"
    python scripts/export_agent_card.py
"""

from __future__ import annotations

import json
import pathlib

from noticeflow.a2a_app import build_agent_card

REPO = pathlib.Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "submission" / "agent-card.json"


def main() -> None:
    card = build_agent_card()
    # Official A2A serialization: camelCase aliases, drop unset optional fields.
    data = json.loads(card.model_dump_json(by_alias=True, exclude_none=True))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(REPO)}  ({len(card.skills)} skill(s))")


if __name__ == "__main__":
    main()
