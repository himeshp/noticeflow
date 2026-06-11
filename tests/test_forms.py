"""Unit tests for GST reply-form PDF generation (deterministic, no GCP)."""

import pytest

from noticeflow.forms import form_spec_for, generate_form_pdf, safe_filename
from noticeflow.forms.generator import _annexure_rows
from noticeflow.schemas import (
    Citation,
    NoticeType,
    ReconciliationData,
    ResponsePacket,
)


def _turnover_packet():
    """An ASMT-10 packet whose annexure is a GSTR-1 vs GSTR-3B turnover table."""
    return ResponsePacket(
        notice_type=NoticeType.ASMT_10,
        reference_number="ZA2706240005678",
        gstin="27PQRSX5678G2Z9",
        tax_period="FY2023-24",
        response_deadline=None,
        deadline_urgent=False,
        legal_basis="Under Section 61 of the CGST Act, 2017.",
        reply_body="The turnover variance is explained by timing.",
        citations=[Citation(source_id="CGST Act 2017, Section 61", source_type="act",
                            snippet="...", relevance_note="...")],
        annexure=ReconciliationData(
            gstin="27PQRSX5678G2Z9", tax_period="FY2023-24",
            gstr3b_tax_paid=952000.0, gstr2b_itc_available=0.0, gstr3b_itc_claimed=0.0,
            itc_mismatch_amount=0.0, output_tax_liability=954000.0,
            recon_type="TURNOVER", gstr1_outward_tax=954000.0,
            gstr3b_outward_tax=952000.0, outward_tax_difference=2000.0,
        ),
    )


def _packet(notice_type=NoticeType.DRC_01, reference_number="ZD2705240001234", reply_body="Reply text."):
    return ResponsePacket(
        notice_type=notice_type,
        reference_number=reference_number,
        gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24",
        response_deadline=None,
        deadline_urgent=False,
        legal_basis="Under Section 73 of the CGST Act, 2017.",
        reply_body=reply_body,
        citations=[Citation(source_id="CGST Act 2017, Section 73", source_type="act",
                            snippet="...", relevance_note="...")],
        annexure=ReconciliationData(
            gstin="24ABCDE1234F1Z5", tax_period="FY2023-24",
            gstr3b_tax_paid=1450000.0, gstr2b_itc_available=820000.0,
            gstr3b_itc_claimed=905000.0, itc_mismatch_amount=85000.0,
            output_tax_liability=2355000.0, notes="Sample note.",
        ),
    )


# ── form mapping ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ntype,code,rule", [
    (NoticeType.DRC_01, "DRC-06", "See rule 142(4)"),
    (NoticeType.ASMT_10, "ASMT-11", "See rule 99(2)"),
    (NoticeType.ITC_MISMATCH, "DRC-01C", "See rule 88D"),
])
def test_form_mapping(ntype, code, rule):
    spec = form_spec_for(ntype)
    assert spec.code == code
    assert spec.rule_ref == rule


def test_unknown_maps_to_generic():
    assert form_spec_for(NoticeType.UNKNOWN).code == "REPLY"


# ── PDF generation ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ntype", [NoticeType.DRC_01, NoticeType.ASMT_10, NoticeType.ITC_MISMATCH])
def test_generate_pdf_per_type(ntype):
    pdf = generate_form_pdf(_packet(notice_type=ntype))
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1500  # a real document, not an empty shell


def test_markup_in_reply_is_escaped_not_executed():
    # reportlab Paragraph interprets a mini-XML markup; raw markup must not break it
    nasty = "Refer <b>clause</b> & <para>inject</para> <unknown attr='x'> 3 < 5 > 1"
    pdf = generate_form_pdf(_packet(reply_body=nasty))
    assert pdf.startswith(b"%PDF") and len(pdf) > 1500


# ── notice-type-aware annexure (#FIX2) ──────────────────────────────────────────

def test_itc_notices_render_itc_annexure():
    for ntype in (NoticeType.DRC_01, NoticeType.ITC_MISMATCH):
        rows, highlight = _annexure_rows(_packet(notice_type=ntype))
        labels = [r[0] for r in rows]
        assert "GSTR-2B ITC Available" in labels and "ITC Mismatch" in labels
        assert "Outward Tax as per GSTR-1" not in labels
        assert rows[highlight][0] == "ITC Mismatch"


def test_asmt10_renders_turnover_annexure():
    rows, highlight = _annexure_rows(_turnover_packet())
    labels = [r[0] for r in rows]
    assert "Outward Tax as per GSTR-1" in labels
    assert "GSTR-2B ITC Available" not in labels and "ITC Mismatch" not in labels
    assert rows[highlight][0].startswith("Difference")
    # the Rs 2,000 variance is shown
    assert any("2,000" in r[1] for r in rows)


def test_asmt10_without_turnover_fields_falls_back_to_itc():
    # an ASMT-10 packet whose record lacked turnover figures still renders a table
    pkt = _packet(notice_type=NoticeType.ASMT_10)  # ITC-shaped annexure, no turnover fields
    rows, highlight = _annexure_rows(pkt)
    assert rows[highlight][0] == "ITC Mismatch"


def test_turnover_pdf_builds():
    pdf = generate_form_pdf(_turnover_packet())
    assert pdf.startswith(b"%PDF") and len(pdf) > 1500


def test_reconciliation_defaults():
    a = _packet().annexure
    assert a.recon_type == "ITC"
    assert a.gstr1_outward_tax is None and a.outward_tax_difference is None


# ── filename sanitization ─────────────────────────────────────────────────────

def test_safe_filename_basic():
    fn = safe_filename(_packet(reference_number="ZD2705240001234"))
    assert fn == "GST_DRC-06_ZD2705240001234.pdf"


def test_safe_filename_strips_header_injection():
    fn = safe_filename(_packet(reference_number='evil"\r\nSet-Cookie: x=1'))
    assert "\r" not in fn and "\n" not in fn and '"' not in fn
    assert fn.endswith(".pdf") and fn.startswith("GST_DRC-06_")


def test_safe_filename_none_reference():
    fn = safe_filename(_packet(reference_number=None))
    assert fn == "GST_DRC-06_draft.pdf"
