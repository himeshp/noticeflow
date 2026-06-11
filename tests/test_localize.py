"""Tests for reply localization (#3.7).

Pure tests (no GCP) cover the en/no-op + fail-safe contract and that the form
generator ignores the localized fields. A live test (skipped without
GOOGLE_CLOUD_PROJECT) exercises the real Gemini translation.
"""

import asyncio
import os

import pytest

from noticeflow.localize import SUPPORTED, _Localized, localize_packet
from noticeflow.forms import generate_form_pdf
from noticeflow.schemas import (
    Citation,
    NoticeType,
    ReconciliationData,
    ResponsePacket,
)


def _packet(**over):
    base = dict(
        notice_type=NoticeType.DRC_01, reference_number="ZD2705240001234",
        gstin="24ABCDE1234F1Z5", tax_period="FY2023-24", response_deadline=None,
        deadline_urgent=False,
        legal_basis="This reply is filed under Section 73 of the CGST Act, 2017.",
        reply_body="1. The taxpayer disputes the demand of Rs. 85,000.",
        citations=[Citation(source_id="CGST Act 2017, Section 73", source_type="act",
                            snippet="s", relevance_note="n")],
        annexure=ReconciliationData(
            gstin="24ABCDE1234F1Z5", tax_period="FY2023-24", gstr3b_tax_paid=0.0,
            gstr2b_itc_available=820000.0, gstr3b_itc_claimed=905000.0,
            itc_mismatch_amount=85000.0, output_tax_liability=0.0),
    )
    base.update(over)
    return ResponsePacket(**base)


# ── contract: en / unsupported are no-ops (no LLM) ──────────────────────────────

def test_supported_set():
    assert SUPPORTED == {"en", "hi", "bilingual"}


def test_en_is_noop():
    p = asyncio.run(localize_packet(_packet(), "en"))
    assert p.language == "en"
    assert p.legal_basis_localized is None and p.reply_body_localized is None


def test_unsupported_language_falls_back_to_en():
    p = asyncio.run(localize_packet(_packet(), "klingon"))
    assert p.language == "en"
    assert p.legal_basis_localized is None and p.reply_body_localized is None


def test_canonical_fields_never_mutated():
    src = _packet()
    p = asyncio.run(localize_packet(src, "en"))
    assert p.legal_basis == src.legal_basis
    assert p.reply_body == src.reply_body


# ── schema defaults ─────────────────────────────────────────────────────────────

def test_new_fields_default():
    p = _packet()
    assert p.language == "en"
    assert p.legal_basis_localized is None
    assert p.reply_body_localized is None


def test_localized_output_model_roundtrips():
    out = _Localized.model_validate({"legal_basis": "धारा 73", "reply_body": "1. ..."})
    assert out.legal_basis == "धारा 73"


# ── the form ignores localized fields (English stays canonical) ─────────────────

def test_form_builds_with_localized_fields_present():
    # Populating the localized (Hindi) fields must not break the English PDF —
    # generate_form_pdf reads only the canonical English legal_basis/reply_body.
    pkt = _packet(language="hi",
                  legal_basis_localized="धारा 73 के तहत दाखिल।",
                  reply_body_localized="1. करदाता रु. 85,000 की मांग का विरोध करता है।")
    pdf = generate_form_pdf(pkt)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 1000


# ── live translation (skipped without GCP) ──────────────────────────────────────

live = pytest.mark.skipif(
    not os.environ.get("GOOGLE_CLOUD_PROJECT"),
    reason="GOOGLE_CLOUD_PROJECT not set — skipping live Gemini translation",
)


@live
def test_hindi_localization_live():
    p = asyncio.run(localize_packet(_packet(), "hi"))
    assert p.language == "hi"
    blob = (p.legal_basis_localized or "") + (p.reply_body_localized or "")
    assert any("ऀ" <= ch <= "ॿ" for ch in blob), "expected Devanagari output"
    assert "85,000" in blob  # figures preserved verbatim
    # English canonical untouched
    assert p.reply_body.startswith("1. The taxpayer")


@live
def test_bilingual_localization_live():
    p = asyncio.run(localize_packet(_packet(), "bilingual"))
    assert p.language == "bilingual"
    blob = (p.reply_body_localized or "")
    assert any("ऀ" <= ch <= "ॿ" for ch in blob)   # has Hindi
    assert "taxpayer" in blob.lower()                         # and English
