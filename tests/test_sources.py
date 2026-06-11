"""Unit tests for citation→source-PDF resolution (pure, no GCP).

Uses the committed data/source_pdf_index.json + bundled PDFs.
"""

from noticeflow.sources import (
    DOC_FILES,
    annotate_citation_sources,
    lookup_page,
    resolve_doc,
    source_pdf_path,
)
from noticeflow.schemas import (
    Citation,
    NoticeType,
    ReconciliationData,
    ResponsePacket,
)


# ── resolve_doc ─────────────────────────────────────────────────────────────────

def test_resolve_doc_by_type_and_id():
    assert resolve_doc("act", "CGST Act 2017, Section 73(1)") == "cgst_act_2017"
    assert resolve_doc("rule", "CGST Rules 2017, Rule 99") == "cgst_rules_2017"
    assert resolve_doc("circular", "Circular No. 183/15/2022-GST") == "circular_183_2022"
    assert resolve_doc("circular", "Circular 31/05/2018-GST") == "circular_31_2018"
    assert resolve_doc("circular", "Circular 135/05/2020-GST") == "circular_135_2020"


def test_resolve_doc_unknown_returns_none():
    assert resolve_doc("notification", "some notification 12/2020") is None
    assert resolve_doc("", "random text with no refs") is None


# ── lookup_page ─────────────────────────────────────────────────────────────────

def test_lookup_page_circular_is_one():
    assert lookup_page("circular_183_2022", "Circular 183") == 1


def test_lookup_page_act_section_resolves_to_int():
    page = lookup_page("cgst_act_2017", "CGST Act 2017, Section 73(1)")
    assert isinstance(page, int) and page > 0


def test_lookup_page_none_and_unknown():
    assert lookup_page(None, "Section 73") is None
    assert lookup_page("not_a_doc", "Section 73") is None


# ── source_pdf_path allow-list guard ────────────────────────────────────────────

def test_source_pdf_path_allows_only_listed_keys():
    assert source_pdf_path("cgst_act_2017") is not None       # bundled PDF exists
    assert source_pdf_path("../../etc/passwd") is None        # traversal rejected
    assert source_pdf_path("/etc/passwd") is None
    assert source_pdf_path("nope") is None
    assert set(DOC_FILES) == {
        "cgst_act_2017", "cgst_rules_2017",
        "circular_31_2018", "circular_135_2020", "circular_183_2022",
    }


# ── annotate_citation_sources ────────────────────────────────────────────────────

def _packet(citations):
    return ResponsePacket(
        notice_type=NoticeType.DRC_01, reference_number="R", gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24", response_deadline=None, deadline_urgent=False,
        legal_basis="b", reply_body="r", citations=citations,
        annexure=ReconciliationData(
            gstin="24ABCDE1234F1Z5", tax_period="FY2023-24", gstr3b_tax_paid=0.0,
            gstr2b_itc_available=0.0, gstr3b_itc_claimed=0.0, itc_mismatch_amount=0.0,
            output_tax_liability=0.0),
    )


def test_annotate_sets_doc_and_page():
    pkt = _packet([
        Citation(source_id="CGST Act 2017, Section 73(1)", source_type="act", snippet="s", relevance_note="n"),
        Citation(source_id="Circular No. 183/15/2022-GST", source_type="circular", snippet="s", relevance_note="n"),
        Citation(source_id="Some Notification 9/2021", source_type="notification", snippet="s", relevance_note="n"),
    ])
    out = annotate_citation_sources(pkt)
    assert out.citations[0].source_doc == "cgst_act_2017" and out.citations[0].source_page > 0
    assert out.citations[1].source_doc == "circular_183_2022" and out.citations[1].source_page == 1
    assert out.citations[2].source_doc is None and out.citations[2].source_page is None


def test_citation_source_fields_default_none():
    c = Citation(source_id="x", source_type="act", snippet="s", relevance_note="n")
    assert c.source_doc is None and c.source_page is None
