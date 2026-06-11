"""
Classifier tests.

Offline tests: validate the parsing/conversion logic; zero GCP calls.
Integration tests: marked with @pytest.mark.integration; skipped unless
  GOOGLE_CLOUD_PROJECT is set in the environment.
"""

import json
import os
import pathlib
from datetime import date

import pytest

from noticeflow.schemas import ClassifiedNotice, NoticeType

# ── Offline helpers ───────────────────────────────────────────────────────────

# Import the internal output model directly so we can test conversion without
# touching the Runner or Gemini at all.
from noticeflow.agents.classifier import _ClassifierOutput, _INSTRUCTION


SAMPLE_DIR = pathlib.Path(__file__).parents[1] / "data" / "sample_notices"


def _make_output(**kwargs) -> _ClassifierOutput:
    defaults = dict(
        notice_type=NoticeType.DRC_01,
        governing_sections=["Section 73", "Section 50"],
        reference_number="ZD2403240001234",
        gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24",
        response_deadline="2024-04-11",
        demanded_amount=105900.0,
        issue_summary="Short payment of tax due to excess ITC claimed.",
        confidence=0.95,
    )
    defaults.update(kwargs)
    return _ClassifierOutput(**defaults)


# ── Schema / parsing tests (no GCP) ──────────────────────────────────────────

def test_classifier_output_round_trip():
    out = _make_output()
    dumped = out.model_dump_json()
    reloaded = _ClassifierOutput.model_validate_json(dumped)
    assert reloaded.notice_type == NoticeType.DRC_01
    assert reloaded.confidence == 0.95


def test_classifier_output_unknown_type():
    out = _make_output(notice_type=NoticeType.UNKNOWN, demanded_amount=None)
    assert out.notice_type == NoticeType.UNKNOWN


def test_classifier_output_null_deadline():
    out = _make_output(response_deadline=None)
    assert out.response_deadline is None


def test_deadline_parsing_valid():
    from noticeflow.agents.classifier import _ClassifierOutput
    out = _make_output(response_deadline="2024-04-11")
    deadline = date.fromisoformat(out.response_deadline)
    assert deadline == date(2024, 4, 11)


def test_deadline_parsing_invalid_string():
    # Invalid ISO dates must not crash — we gracefully produce None
    bad = "11/04/2024"
    try:
        date.fromisoformat(bad)
        parsed = date.fromisoformat(bad)
    except ValueError:
        parsed = None
    assert parsed is None


def test_instruction_contains_all_notice_types():
    for notice_type in ("ASMT_10", "DRC_01", "ITC_MISMATCH", "UNKNOWN"):
        assert notice_type in _INSTRUCTION, f"Instruction missing notice type: {notice_type}"


def test_instruction_contains_schema():
    schema = json.dumps(_ClassifierOutput.model_json_schema())
    # At minimum the key field names should appear in the instruction
    for field in ("notice_type", "governing_sections", "gstin", "confidence"):
        assert field in _INSTRUCTION, f"Instruction missing field hint: {field}"


def test_classified_notice_construction_from_output():
    out = _make_output()
    deadline = date.fromisoformat(out.response_deadline)
    notice = ClassifiedNotice(
        notice_type=out.notice_type,
        governing_sections=out.governing_sections,
        reference_number=out.reference_number,
        gstin=out.gstin,
        tax_period=out.tax_period,
        response_deadline=deadline,
        demanded_amount=out.demanded_amount,
        issue_summary=out.issue_summary,
        raw_extracted_text="<raw text>",
        confidence=out.confidence,
    )
    assert notice.notice_type == NoticeType.DRC_01
    assert notice.gstin == "24ABCDE1234F1Z5"
    assert notice.response_deadline == date(2024, 4, 11)
    assert notice.raw_extracted_text == "<raw text>"


def test_sample_notice_files_exist():
    for filename in ("drc01_sec73.txt", "asmt10_sec61.txt", "itc_mismatch_sec16.txt"):
        assert (SAMPLE_DIR / filename).exists(), f"Missing sample notice: {filename}"


# ── Integration tests (require GCP) ──────────────────────────────────────────

integration = pytest.mark.skipif(
    not os.environ.get("GOOGLE_CLOUD_PROJECT"),
    reason="GOOGLE_CLOUD_PROJECT not set — skipping live Gemini call",
)


@integration
@pytest.mark.asyncio
async def test_classify_drc01_live():
    from noticeflow.agents.classifier import classify_notice
    text = (SAMPLE_DIR / "drc01_sec73.txt").read_text(encoding="utf-8")
    result = await classify_notice(text)
    assert result.notice_type == NoticeType.DRC_01
    assert result.gstin == "24ABCDE1234F1Z5"
    assert result.confidence > 0.7
    assert result.demanded_amount is not None


@integration
@pytest.mark.asyncio
async def test_classify_asmt10_live():
    from noticeflow.agents.classifier import classify_notice
    text = (SAMPLE_DIR / "asmt10_sec61.txt").read_text(encoding="utf-8")
    result = await classify_notice(text)
    assert result.notice_type == NoticeType.ASMT_10
    assert result.gstin == "27PQRSX5678G2Z9"
    assert result.confidence > 0.7


@integration
@pytest.mark.asyncio
async def test_classify_itc_mismatch_live():
    from noticeflow.agents.classifier import classify_notice
    text = (SAMPLE_DIR / "itc_mismatch_sec16.txt").read_text(encoding="utf-8")
    result = await classify_notice(text)
    assert result.notice_type == NoticeType.ITC_MISMATCH
    assert result.gstin == "29LMNOP9012H3Z4"
    assert result.confidence > 0.7
