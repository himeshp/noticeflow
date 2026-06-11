"""Unit tests for the deterministic Critic logic (no GCP, no LLM)."""

import json

from noticeflow.agents.reviewer import review_drafter_output


def _drafter(cited, claimed=905000.0, available=820000.0, mismatch=85000.0):
    return {
        "legal_basis": "b",
        "reply_body": "r",
        "cited_source_ids": cited,
        "deadline_urgent": False,
        "annexure": {
            "gstin": "24ABCDE1234F1Z5", "tax_period": "FY2023-24",
            "gstr3b_tax_paid": 1450000.0, "gstr2b_itc_available": available,
            "gstr3b_itc_claimed": claimed, "itc_mismatch_amount": mismatch,
            "output_tax_liability": 2355000.0, "notes": None,
        },
    }


_LEGAL = {
    "citations": [
        {"source_id": "CGST Act 2017, Section 73"},
        {"source_id": "CGST Act 2017, Section 50"},
    ]
}


def test_all_good_approves():
    r = review_drafter_output(_drafter(["CGST Act 2017, Section 73"]), _LEGAL, 1)
    assert r.verdict == "APPROVE"
    assert r.citations_grounded and r.figures_reconcile and r.issues == []
    assert r.round == 1


def test_ungrounded_citation_revises():
    r = review_drafter_output(_drafter(["CGST Act 2017, Section 999"]), _LEGAL, 1)
    assert r.verdict == "REVISE"
    assert r.citations_grounded is False
    assert any("Section 999" in i for i in r.issues)


def test_figures_mismatch_revises():
    # mismatch 99999 != 905000 - 820000 = 85000
    r = review_drafter_output(_drafter(["CGST Act 2017, Section 73"], mismatch=99999.0), _LEGAL, 2)
    assert r.verdict == "REVISE"
    assert r.figures_reconcile is False
    assert any("reconcile" in i.lower() for i in r.issues)
    assert r.round == 2


def test_missing_annexure_revises():
    bad = {"cited_source_ids": ["CGST Act 2017, Section 73"], "annexure": {}}
    r = review_drafter_output(bad, _LEGAL, 1)
    assert r.verdict == "REVISE"
    assert any("missing" in i.lower() for i in r.issues)


def test_unparseable_output_is_safe_approve():
    r = review_drafter_output("this is not json {{{", _LEGAL, 1)
    assert r.verdict == "APPROVE"  # don't burn iterations on garbage


def test_accepts_json_string_input():
    raw = json.dumps(_drafter(["CGST Act 2017, Section 50"]))
    r = review_drafter_output(raw, json.dumps(_LEGAL), 1)
    assert r.verdict == "APPROVE"


def test_empty_citations_are_vacuously_grounded():
    r = review_drafter_output(_drafter([]), _LEGAL, 1)
    assert r.citations_grounded is True  # nothing cited -> nothing ungrounded


def test_markdown_fenced_json_parsed():
    raw = "```json\n" + json.dumps(_drafter(["CGST Act 2017, Section 73"])) + "\n```"
    r = review_drafter_output(raw, _LEGAL, 1)
    assert r.verdict == "APPROVE"
