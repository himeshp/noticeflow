"""scripts/eval.py — run the NoticeFlow pipeline over the labeled notice set and
report quantified metrics. This is the only part of the eval harness that calls
GCP (Gemini / Vertex AI Search / MCP).

Usage (from repo root):
    python scripts/eval.py             # FULL run -> docs/submission/eval_report.{md,json}
    python scripts/eval.py --fast      # first 3 notices (cheap smoke; no report written)
    python scripts/eval.py --limit 5   # first N (no report written)
    python scripts/eval.py --only drc01_sec73.txt   # single notice (no report written)

Subset runs print to the console only; the committed report is written solely by a
full run so a partial run can never clobber it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from noticeflow import config
from noticeflow.agents.orchestrator import run_pipeline
from noticeflow.evaluation.scoring import (
    CaseResult,
    EvalCase,
    aggregate,
    render_markdown,
    score_case,
)
from noticeflow.schemas import NoticeType

REPO = pathlib.Path(__file__).resolve().parents[1]
SAMPLE_DIR = (REPO / "data" / "sample_notices").resolve()
MANIFEST = SAMPLE_DIR / "manifest.json"
OUT_DIR = REPO / "docs" / "submission"


def _read_notice(filename: str) -> str:
    """Read a notice by name, guarded to stay inside SAMPLE_DIR."""
    candidate = (SAMPLE_DIR / filename).resolve()
    if not candidate.is_relative_to(SAMPLE_DIR) or not candidate.exists():
        raise FileNotFoundError(f"notice not found or outside sample dir: {filename!r}")
    # Resolve {{ISSUE_DATE}}/{{DEADLINE}} placeholders (no-op for files without them)
    # so the classifier never sees a raw token.
    from noticeflow.samples import render_sample_text
    return render_sample_text(filename, candidate.read_text(encoding="utf-8"))


def _load_cases() -> list[EvalCase]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [EvalCase.model_validate(n) for n in data["notices"]]


async def _run(cases: list[EvalCase]) -> list[CaseResult]:
    results: list[CaseResult] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case.file} ...", flush=True)
        t0 = time.perf_counter()
        try:
            packet = await run_pipeline(_read_notice(case.file))
            r = score_case(case, packet, time.perf_counter() - t0)
        except Exception as exc:  # one failure must not abort the whole run
            r = CaseResult(
                file=case.file,
                expected_type=case.expected_type,
                predicted_type=NoticeType.UNKNOWN,
                classification_ok=False,
                latency_s=round(time.perf_counter() - t0, 2),
                error=str(exc)[:300],
            )
            print(f"    ERROR: {exc}")
        results.append(r)
        print(f"    class={'ok' if r.classification_ok else 'X'}  "
              f"pred={r.predicted_type.value}  recon={r.reconciliation_ok}  "
              f"cites={r.citations_passed}  {r.latency_s}s")
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate the NoticeFlow pipeline.")
    ap.add_argument("--fast", action="store_true", help="first 3 notices only")
    ap.add_argument("--limit", type=int, default=0, help="first N notices")
    ap.add_argument("--only", type=str, default="", help="single notice filename")
    args = ap.parse_args()

    cases = _load_cases()
    full = not (args.fast or args.limit or args.only)
    if args.only:
        cases = [c for c in cases if c.file == args.only]
    elif args.fast:
        cases = cases[:3]
    elif args.limit:
        cases = cases[: args.limit]

    if not cases:
        print("No matching notices.")
        return

    results = asyncio.run(_run(cases))
    metrics = aggregate(results)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    mode = "ON" if config.ENABLE_REVIEW_LOOP else "OFF"
    md = render_markdown(metrics, results, generated_at=f"{ts} · review loop: {mode}")
    print("\n" + md)

    if full:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "eval_report.md").write_text(md, encoding="utf-8")
        (OUT_DIR / "eval_report.json").write_text(
            json.dumps(
                {"generated_at": ts, "metrics": metrics.model_dump(),
                 "results": [r.model_dump() for r in results]},
                indent=2, default=str,
            ),
            encoding="utf-8",
        )
        print(f"\nWrote {OUT_DIR / 'eval_report.md'} and eval_report.json")
    else:
        print("\n(subset run — report files not written; run with no flags for the full report)")


if __name__ == "__main__":
    main()
