"""Unit tests for the eval scoring logic (pure, no GCP)."""

from noticeflow.evaluation.scoring import (
    EvalCase,
    aggregate,
    render_markdown,
    score_case,
)
from noticeflow.schemas import (
    Citation,
    CitationVerification,
    NoticeType,
    ReconciliationData,
    ResponsePacket,
    ReviewResult,
)


def _packet(notice_type=NoticeType.DRC_01, mismatch=85000.0, claimed=905000.0,
            available=820000.0, cv=None):
    return ResponsePacket(
        notice_type=notice_type, reference_number="R", gstin="24ABCDE1234F1Z5",
        tax_period="FY2023-24", response_deadline=None, deadline_urgent=False,
        legal_basis="b", reply_body="r",
        citations=[Citation(source_id="Section 73", source_type="act", snippet="s", relevance_note="n")],
        annexure=ReconciliationData(
            gstin="24ABCDE1234F1Z5", tax_period="FY2023-24", gstr3b_tax_paid=0.0,
            gstr2b_itc_available=available, gstr3b_itc_claimed=claimed,
            itc_mismatch_amount=mismatch, output_tax_liability=0.0,
        ),
        citation_verification=cv,
    )


def _cv(total=2, verified=2):
    return CitationVerification(total_citations=total, verified=verified,
                               unverified=[] if total == verified else ["x"],
                               passed=total == verified)


# ── score_case ────────────────────────────────────────────────────────────────

def test_classification_correct():
    case = EvalCase(file="d.txt", expected_type=NoticeType.DRC_01)
    r = score_case(case, _packet(cv=_cv()), 12.3)
    assert r.classification_ok and r.predicted_type == NoticeType.DRC_01
    assert r.latency_s == 12.3


def test_classification_wrong():
    case = EvalCase(file="d.txt", expected_type=NoticeType.ASMT_10)
    r = score_case(case, _packet(NoticeType.DRC_01, cv=_cv()), 1.0)
    assert not r.classification_ok


def test_citations_passed_and_failed():
    case = EvalCase(file="d.txt", expected_type=NoticeType.DRC_01)
    assert score_case(case, _packet(cv=_cv(2, 2)), 1.0).citations_passed is True
    assert score_case(case, _packet(cv=_cv(2, 1)), 1.0).citations_passed is False


def test_reconciliation_identity():
    case = EvalCase(file="d.txt", expected_type=NoticeType.DRC_01)
    assert score_case(case, _packet(mismatch=85000.0, cv=_cv()), 1.0).reconciliation_ok is True
    assert score_case(case, _packet(mismatch=99999.0, cv=_cv()), 1.0).reconciliation_ok is False


def test_unknown_case_scoring():
    case = EvalCase(file="u.txt", expected_type=NoticeType.UNKNOWN, expects_known=False)
    ok = score_case(case, _packet(NoticeType.UNKNOWN), 1.0)
    assert ok.unknown_ok is True and ok.classification_ok is True
    # UNKNOWN cases don't assert citations/recon
    assert ok.citations_passed is None and ok.reconciliation_ok is None
    bad = score_case(case, _packet(NoticeType.DRC_01), 1.0)
    assert bad.unknown_ok is False


# ── aggregate ─────────────────────────────────────────────────────────────────

def test_aggregate_rates_and_latency():
    cases_packets = [
        (EvalCase(file="a", expected_type=NoticeType.DRC_01), _packet(cv=_cv(2, 2)), 10.0),
        (EvalCase(file="b", expected_type=NoticeType.ASMT_10), _packet(NoticeType.ASMT_10, cv=_cv(3, 2)), 20.0),
        (EvalCase(file="u", expected_type=NoticeType.UNKNOWN, expects_known=False), _packet(NoticeType.UNKNOWN), 30.0),
    ]
    results = [score_case(c, p, t) for c, p, t in cases_packets]
    m = aggregate(results)
    assert m.total == 3 and m.classification_correct == 3
    assert m.classification_accuracy == 1.0
    # citation pass rate over the 2 known cases: one passed, one failed -> 0.5
    assert m.citation_pass_rate == 0.5
    # reconciliation over 2 known cases (both identity-valid) -> 1.0
    assert m.reconciliation_pass_rate == 1.0
    # unknown handling over the 1 unknown case -> 1.0
    assert m.unknown_handling_rate == 1.0
    assert m.latency_median_s == 20.0


def test_p90_nearest_rank():
    results = [
        score_case(EvalCase(file=str(i), expected_type=NoticeType.DRC_01), _packet(cv=_cv()), float(i))
        for i in range(1, 11)  # latencies 1..10
    ]
    m = aggregate(results)
    assert m.latency_p90_s == 9.0  # ceil(0.9*10)-1 = index 8 -> value 9


def test_review_metrics_captured():
    case = EvalCase(file="d.txt", expected_type=NoticeType.DRC_01)
    pkt = _packet(cv=_cv())
    pkt = pkt.model_copy(update={"review": ReviewResult(
        citations_grounded=True, figures_reconcile=True, issues=[], verdict="APPROVE", round=2)})
    r = score_case(case, pkt, 1.0)
    assert r.review_verdict == "APPROVE" and r.review_rounds == 2
    m = aggregate([r])
    assert m.reviewed == 1 and m.review_approve_rate == 1.0 and m.avg_review_rounds == 2.0


def test_no_review_means_no_loop_metrics():
    case = EvalCase(file="d.txt", expected_type=NoticeType.DRC_01)
    m = aggregate([score_case(case, _packet(cv=_cv()), 1.0)])
    assert m.reviewed == 0 and m.review_approve_rate is None and m.avg_review_rounds is None


def test_render_markdown_smoke():
    case = EvalCase(file="d.txt", expected_type=NoticeType.DRC_01)
    results = [score_case(case, _packet(cv=_cv()), 5.0)]
    md = render_markdown(aggregate(results), results, generated_at="2026-06-05")
    assert "Classification accuracy" in md
    assert "Citation verification pass rate" in md
    assert "d.txt" in md and "| DRC_01 |" in md
