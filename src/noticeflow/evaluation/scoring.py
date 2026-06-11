"""Pure scoring for the eval harness — no LLM, no GCP, no I/O.

Given a ground-truth EvalCase and the ResponsePacket the pipeline produced,
compute per-notice correctness and aggregate metrics. Kept side-effect-free so
it is unit-testable with fabricated packets; scripts/eval.py supplies the real
pipeline output and latencies.
"""

from __future__ import annotations

import math
import statistics
from typing import Optional

from pydantic import BaseModel

from noticeflow.schemas import NoticeType, ResponsePacket

# Annexure identity tolerance (rupees) — guards float rounding only.
_RECON_TOLERANCE = 1.0


class EvalCase(BaseModel):
    file: str
    expected_type: NoticeType
    expected_gstin: Optional[str] = None
    expected_period: Optional[str] = None
    expects_known: bool = True  # False for notices that should classify UNKNOWN


class CaseResult(BaseModel):
    file: str
    expected_type: NoticeType
    predicted_type: NoticeType
    classification_ok: bool
    citations_passed: Optional[bool] = None  # None when not applicable (UNKNOWN)
    citation_count: Optional[int] = None
    reconciliation_ok: Optional[bool] = None
    unknown_ok: Optional[bool] = None        # set only for expects_known=False
    review_verdict: Optional[str] = None     # APPROVE | REVISE, if the loop ran
    review_rounds: Optional[int] = None      # iterations the review loop took
    latency_s: float
    error: Optional[str] = None


class EvalMetrics(BaseModel):
    total: int
    classification_correct: int
    classification_accuracy: float
    citation_pass_rate: Optional[float] = None
    reconciliation_pass_rate: Optional[float] = None
    unknown_handling_rate: Optional[float] = None
    latency_median_s: float
    latency_p90_s: float
    reviewed: int = 0                              # notices that went through the review loop
    review_approve_rate: Optional[float] = None    # APPROVE / reviewed
    avg_review_rounds: Optional[float] = None       # mean loop iterations


def _recon_ok(packet: ResponsePacket) -> bool:
    a = packet.annexure
    return abs(a.itc_mismatch_amount - (a.gstr3b_itc_claimed - a.gstr2b_itc_available)) <= _RECON_TOLERANCE


def score_case(case: EvalCase, packet: ResponsePacket, latency_s: float) -> CaseResult:
    predicted = packet.notice_type
    classification_ok = predicted == case.expected_type

    citations_passed: Optional[bool] = None
    citation_count: Optional[int] = None
    reconciliation_ok: Optional[bool] = None
    unknown_ok: Optional[bool] = None

    if case.expects_known:
        cv = packet.citation_verification
        if cv is not None:
            citations_passed = cv.passed
            citation_count = cv.total_citations
        reconciliation_ok = _recon_ok(packet)
    else:
        unknown_ok = predicted == NoticeType.UNKNOWN

    review_verdict = packet.review.verdict if packet.review else None
    review_rounds = packet.review.round if packet.review else None

    return CaseResult(
        file=case.file,
        expected_type=case.expected_type,
        predicted_type=predicted,
        classification_ok=classification_ok,
        citations_passed=citations_passed,
        citation_count=citation_count,
        reconciliation_ok=reconciliation_ok,
        unknown_ok=unknown_ok,
        review_verdict=review_verdict,
        review_rounds=review_rounds,
        latency_s=round(latency_s, 2),
    )


def _rate(flags: list[bool]) -> Optional[float]:
    return (sum(flags) / len(flags)) if flags else None


def _p90(values: list[float]) -> float:
    """Nearest-rank 90th percentile."""
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, math.ceil(0.9 * len(s)) - 1)
    return s[k]


def aggregate(results: list[CaseResult]) -> EvalMetrics:
    total = len(results)
    correct = sum(r.classification_ok for r in results)
    latencies = [r.latency_s for r in results]
    reviewed = [r for r in results if r.review_verdict is not None]
    rounds = [r.review_rounds for r in reviewed if r.review_rounds is not None]
    return EvalMetrics(
        total=total,
        classification_correct=correct,
        classification_accuracy=(correct / total) if total else 0.0,
        citation_pass_rate=_rate([r.citations_passed for r in results if r.citations_passed is not None]),
        reconciliation_pass_rate=_rate([r.reconciliation_ok for r in results if r.reconciliation_ok is not None]),
        unknown_handling_rate=_rate([r.unknown_ok for r in results if r.unknown_ok is not None]),
        latency_median_s=round(statistics.median(latencies), 2) if latencies else 0.0,
        latency_p90_s=round(_p90(latencies), 2),
        reviewed=len(reviewed),
        review_approve_rate=_rate([r.review_verdict == "APPROVE" for r in reviewed]),
        avg_review_rounds=round(sum(rounds) / len(rounds), 2) if rounds else None,
    )


def _pct(rate: Optional[float]) -> str:
    return "n/a" if rate is None else f"{rate * 100:.1f}%"


def _flag(value: Optional[bool]) -> str:
    if value is None:
        return "—"
    return "✓" if value else "✗"


def render_markdown(metrics: EvalMetrics, results: list[CaseResult], generated_at: str = "") -> str:
    lines: list[str] = []
    lines.append("# NoticeFlow — Evaluation Report")
    lines.append("")
    if generated_at:
        lines.append(f"_Generated {generated_at} · {metrics.total} synthetic notices_")
        lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Result |")
    lines.append("|--------|--------|")
    lines.append(f"| Classification accuracy | {metrics.classification_correct}/{metrics.total} ({_pct(metrics.classification_accuracy)}) |")
    lines.append(f"| Citation verification pass rate | {_pct(metrics.citation_pass_rate)} |")
    lines.append(f"| Annexure reconciliation pass rate | {_pct(metrics.reconciliation_pass_rate)} |")
    lines.append(f"| UNKNOWN handling rate | {_pct(metrics.unknown_handling_rate)} |")
    lines.append(f"| End-to-end latency (median / p90) | {metrics.latency_median_s}s / {metrics.latency_p90_s}s |")
    if metrics.reviewed:
        lines.append(f"| Review loop — drafts approved | {_pct(metrics.review_approve_rate)} of {metrics.reviewed} |")
        lines.append(f"| Review loop — avg iterations | {metrics.avg_review_rounds} |")
    lines.append("")
    lines.append("## Per-notice")
    lines.append("")
    show_review = any(r.review_verdict is not None for r in results)
    review_hdr = " Review |" if show_review else ""
    review_sep = ":-----:|" if show_review else ""
    lines.append(f"| Notice | Expected | Predicted | Class | Citations | Recon | Unknown |{review_hdr} Latency |")
    lines.append(f"|--------|----------|-----------|:-----:|:---------:|:-----:|:-------:|{review_sep}--------:|")
    for r in results:
        cites = "—" if r.citations_passed is None else f"{_flag(r.citations_passed)} ({r.citation_count})"
        review_cell = ""
        if show_review:
            rv = "—" if r.review_verdict is None else f"{r.review_verdict} (r{r.review_rounds})"
            review_cell = f" {rv} |"
        lines.append(
            f"| {r.file} | {r.expected_type.value} | {r.predicted_type.value} | "
            f"{_flag(r.classification_ok)} | {cites} | {_flag(r.reconciliation_ok)} | "
            f"{_flag(r.unknown_ok)} |{review_cell} {r.latency_s}s |"
        )
    lines.append("")
    lines.append("> Synthetic notices; CBIC law corpus is real. Citation pass rate is "
                 "code-enforced (see `src/noticeflow/verify/citations.py`).")
    lines.append("")
    return "\n".join(lines)
