# NoticeFlow — Evaluation Report

_Generated 2026-06-05 12:37 UTC · review loop: ON · 15 synthetic notices_

## Summary

| Metric | Result |
|--------|--------|
| Classification accuracy | 15/15 (100.0%) |
| Citation verification pass rate | 92.3% |
| Annexure reconciliation pass rate | 100.0% |
| UNKNOWN handling rate | 100.0% |
| End-to-end latency (median / p90) | 71.94s / 85.33s |
| Review loop — drafts approved | 100.0% of 13 |
| Review loop — avg iterations | 1.0 |

## Per-notice

| Notice | Expected | Predicted | Class | Citations | Recon | Unknown | Review | Latency |
|--------|----------|-----------|:-----:|:---------:|:-----:|:-------:|:-----:|--------:|
| drc01_sec73.txt | DRC_01 | DRC_01 | ✓ | ✓ (3) | ✓ | — | APPROVE (r1) | 62.67s |
| drc01_sec74_fraud.txt | DRC_01 | DRC_01 | ✓ | ✓ (6) | ✓ | — | APPROVE (r1) | 85.32s |
| drc01_sec73_b.txt | DRC_01 | DRC_01 | ✓ | ✓ (4) | ✓ | — | APPROVE (r1) | 61.8s |
| drc01_sec73_c.txt | DRC_01 | DRC_01 | ✓ | ✓ (6) | ✓ | — | APPROVE (r1) | 73.56s |
| asmt10_sec61.txt | ASMT_10 | ASMT_10 | ✓ | ✓ (5) | ✓ | — | APPROVE (r1) | 63.21s |
| asmt10_sec61_b.txt | ASMT_10 | ASMT_10 | ✓ | ✓ (4) | ✓ | — | APPROVE (r1) | 85.33s |
| asmt10_sec61_c.txt | ASMT_10 | ASMT_10 | ✓ | ✓ (6) | ✓ | — | APPROVE (r1) | 58.82s |
| asmt10_sec61_d.txt | ASMT_10 | ASMT_10 | ✓ | ✓ (3) | ✓ | — | APPROVE (r1) | 73.39s |
| itc_mismatch_sec16.txt | ITC_MISMATCH | ITC_MISMATCH | ✓ | ✗ (7) | ✓ | — | APPROVE (r1) | 71.94s |
| itc_sec16_b.txt | ITC_MISMATCH | ITC_MISMATCH | ✓ | ✓ (3) | ✓ | — | APPROVE (r1) | 77.12s |
| itc_sec16_c.txt | ITC_MISMATCH | ITC_MISMATCH | ✓ | ✓ (2) | ✓ | — | APPROVE (r1) | 65.5s |
| itc_sec16_d.txt | ITC_MISMATCH | ITC_MISMATCH | ✓ | ✓ (7) | ✓ | — | APPROVE (r1) | 67.45s |
| drc01_sec73_missing_gstin.txt | DRC_01 | DRC_01 | ✓ | ✓ (4) | ✓ | — | APPROVE (r1) | 97.38s |
| unknown_reg17.txt | UNKNOWN | UNKNOWN | ✓ | — | — | ✓ | — | 48.0s |
| unknown_rfd08.txt | UNKNOWN | UNKNOWN | ✓ | — | — | ✓ | — | 83.13s |

> Synthetic notices; CBIC law corpus is real. Citation pass rate is code-enforced (see `src/noticeflow/verify/citations.py`).
