"""Quantified evaluation of the NoticeFlow pipeline (scoring is pure; runner is scripts/eval.py)."""

from noticeflow.evaluation.scoring import (
    CaseResult,
    EvalCase,
    EvalMetrics,
    aggregate,
    render_markdown,
    score_case,
)

__all__ = [
    "EvalCase",
    "CaseResult",
    "EvalMetrics",
    "score_case",
    "aggregate",
    "render_markdown",
]
