"""Unit tests for the A2A agent card (#2.5). Pure — no GCP, no network, no server.

Skipped automatically if the optional `a2a` extra is not installed."""

import json

import pytest

pytest.importorskip("a2a", reason="install the a2a extra: pip install -e '.[a2a]'")

from noticeflow.a2a_app import build_agent_card


def test_card_has_required_fields():
    card = build_agent_card("http://example.test:9000/")
    assert card.name == "NoticeFlow"
    assert card.version
    assert card.url == "http://example.test:9000/"
    assert card.description
    assert card.default_input_modes and card.default_output_modes
    assert card.capabilities is not None


def test_card_advertises_gst_skill():
    card = build_agent_card()
    ids = {s.id for s in card.skills}
    assert "gst-notice-response" in ids
    skill = next(s for s in card.skills if s.id == "gst-notice-response")
    assert skill.name and skill.description and skill.tags
    assert "gst" in [t.lower() for t in skill.tags]


def test_card_serializes_camelcase_spec_shape():
    card = build_agent_card()
    data = json.loads(card.model_dump_json(by_alias=True, exclude_none=True))
    # A2A spec uses camelCase keys; these must be present
    for key in ("defaultInputModes", "defaultOutputModes", "capabilities",
                "skills", "url", "name", "version", "description"):
        assert key in data, f"missing spec field: {key}"
    assert isinstance(data["skills"], list) and data["skills"]


def test_exported_card_matches_builder():
    """The committed static artifact must stay in sync with the builder."""
    import pathlib
    repo = pathlib.Path(__file__).resolve().parents[1]
    artifact = repo / "docs" / "submission" / "agent-card.json"
    if not artifact.exists():
        pytest.skip("agent-card.json not exported yet")
    on_disk = json.loads(artifact.read_text(encoding="utf-8"))
    fresh = json.loads(build_agent_card().model_dump_json(by_alias=True, exclude_none=True))
    assert on_disk == fresh, "run scripts/export_agent_card.py to refresh the artifact"
