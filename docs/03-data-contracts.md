# 03 — Data Contracts

> These are the **source of truth** for inter-agent data. Implement them in `src/noticeflow/schemas.py` as Pydantic models BEFORE building any agent. Every agent's input/output must conform.

## Enums

```python
from enum import Enum

class NoticeType(str, Enum):
    ASMT_10 = "ASMT_10"        # Scrutiny notice, Sec. 61
    DRC_01 = "DRC_01"          # Show-cause / demand, Sec. 73/74
    ITC_MISMATCH = "ITC_MISMATCH"  # GSTR-2B vs 3B, Sec. 16
    UNKNOWN = "UNKNOWN"        # unsupported -> stop gracefully
```

## 1. ClassifiedNotice  (Classifier output → Researcher input)

```python
from pydantic import BaseModel, Field
from datetime import date
from typing import Optional

class ClassifiedNotice(BaseModel):
    notice_type: NoticeType
    governing_sections: list[str] = Field(
        description="e.g. ['Section 73', 'Section 50'] or ['Section 61']"
    )
    reference_number: Optional[str] = Field(
        None, description="Notice reference / DIN if present"
    )
    gstin: Optional[str] = Field(None, description="15-char GSTIN of taxpayer")
    tax_period: Optional[str] = Field(
        None, description="e.g. 'FY2023-24' or '04/2024' (month/year)"
    )
    response_deadline: Optional[date] = Field(
        None, description="date by which reply is due"
    )
    demanded_amount: Optional[float] = Field(
        None, description="total amount demanded in INR, if any"
    )
    issue_summary: str = Field(
        description="1-3 sentence plain-language summary of what the notice alleges"
    )
    raw_extracted_text: str = Field(
        description="full text the Classifier read from the PDF (for downstream use)"
    )
    confidence: float = Field(
        ge=0, le=1, description="classifier confidence in notice_type"
    )
```

## 2. LegalContext  (Researcher output → Drafter input)

```python
class Citation(BaseModel):
    source_id: str = Field(
        description="e.g. 'CGST Act 2017, Section 73' or 'Circular 31/05/2018-GST'"
    )
    source_type: str = Field(
        description="one of: 'act', 'rule', 'circular', 'instruction', 'notification'"
    )
    snippet: str = Field(description="the relevant retrieved text passage")
    relevance_note: str = Field(
        description="why this applies to the notice (1 sentence)"
    )

class RetrievedChunk(BaseModel):
    """A passage actually returned by Vertex AI Search grounding, captured from
    event.grounding_metadata. The ground truth the citation verifier checks
    against (see §5)."""
    title: str   # corpus doc title, e.g. 'cgst_act_2017'
    uri: str     # source URI, e.g. gs://.../cgst_act_2017.pdf
    text: str    # the retrieved passage, verbatim

class LegalContext(BaseModel):
    notice_type: NoticeType
    citations: list[Citation] = Field(
        description="retrieved, attributed legal passages governing this notice"
    )
    applicable_response_options: list[str] = Field(
        description="what the taxpayer can legitimately argue/do per the law"
    )
    required_annexures: list[str] = Field(
        description="what supporting docs/figures the reply must include "
                    "(drives the MCP reconciliation request)"
    )
    retrieved_evidence: list[RetrievedChunk] = Field(
        default_factory=list,
        description="raw passages returned by Vertex AI Search — basis for citation verification (§5)"
    )
```

## 3. ReconciliationData  (MCP tool output → Drafter input)
> Full schema + sample values in docs/04. Summary here for the contract.

```python
class ReconciliationData(BaseModel):
    gstin: str
    tax_period: str
    gstr3b_tax_paid: float
    gstr2b_itc_available: float
    gstr3b_itc_claimed: float
    itc_mismatch_amount: float        # 3b_claimed - 2b_available
    output_tax_liability: float
    notes: Optional[str] = None
```

## 4. ResponsePacket  (Drafter output → Human gate → final deliverable)

```python
class ResponsePacket(BaseModel):
    notice_type: NoticeType
    reference_number: Optional[str]
    gstin: Optional[str]
    tax_period: Optional[str]
    response_deadline: Optional[date]
    deadline_urgent: bool = Field(
        description="True if deadline within 7 days of today"
    )
    legal_basis: str = Field(
        description="the cited legal grounding for the response, prose"
    )
    reply_body: str = Field(
        description="the full point-by-point reply to the notice, ready to file"
    )
    citations: list[Citation] = Field(
        description="every legal source referenced in reply_body"
    )
    annexure: ReconciliationData = Field(
        description="the reconciliation figures supporting the reply"
    )
    reviewer_status: str = Field(
        default="PENDING_REVIEW",
        description="PENDING_REVIEW | APPROVED | EDITED | NEEDS_HUMAN"
    )
    escalation_reason: Optional[str] = Field(
        default=None,
        description="why the packet was routed to a human (e.g. low classification confidence) (§7)"
    )
    citation_verification: Optional["CitationVerification"] = Field(
        default=None,
        description="programmatic check that every citation traces to retrieved law (§5)"
    )
    language: str = Field(default="en", description="reply language: en | hi | bilingual (§8)")
    legal_basis_localized: Optional[str] = Field(default=None, description="legal_basis in the requested language; display-only (§8)")
    reply_body_localized: Optional[str] = Field(default=None, description="reply_body in the requested language; display-only (§8)")
```

## 5. CitationVerification  (programmatic anti-hallucination — no LLM)

```python
class CitationVerification(BaseModel):
    total_citations: int          # citations the Drafter emitted
    verified: int                 # citations traceable to retrieved text
    unverified: list[str]         # source_ids with no retrieval backing (dropped)
    passed: bool                  # True iff unverified == []
```

Produced by `src/noticeflow/verify/citations.py` (pure Python). A citation is
**verified** iff (a) its section/rule/circular reference appears in
`LegalContext.retrieved_evidence` text (e.g. "section 73", "rule 88d",
"31/05/2018"), OR (b) a run of ≥6 consecutive words from its `snippet` appears in
that text. `apply_citation_verification(packet, evidence)` drops unverified
citations and attaches this audit; with no evidence it retains citations but sets
`passed=False` (degraded mode — it never silently destroys a legitimate reply).

## 6. ReviewResult  (Drafter↔Critic loop — optional, flag-gated)

```python
class ReviewResult(BaseModel):
    citations_grounded: bool   # every cited source_id was returned by the Researcher
    figures_reconcile: bool    # itc_mismatch_amount == gstr3b_itc_claimed - gstr2b_itc_available
    issues: list[str]          # concrete fixes fed back to the Drafter
    verdict: str               # "APPROVE" | "REVISE"
    round: int                 # 1-based review iteration
```

When `NOTICEFLOW_ENABLE_REVIEW_LOOP=true`, the orchestrator wraps Drafter↔Critic in an
ADK `LoopAgent` (max 2 iterations). The **Critic is deterministic (no LLM)**: it runs the
two code checks above, escalates (stops the loop) on APPROVE, or feeds `issues` back so the
Drafter re-drafts. A REVISE verdict surviving the iteration cap sets
`ResponsePacket.reviewer_status = "NEEDS_HUMAN"`. The result is attached as
`ResponsePacket.review`.

## 7. Confidence gate  (knows when not to act — pure, no LLM)

The Classifier self-reports `ClassifiedNotice.confidence` (0–1). When a notice is a
**KNOWN** type but its confidence is below `NOTICEFLOW_CONFIDENCE_THRESHOLD`
(default `0.55`), `src/noticeflow/gating.py::apply_confidence_gate` sets
`ResponsePacket.reviewer_status = "NEEDS_HUMAN"` and records a
human-readable `escalation_reason` — NoticeFlow refuses to present a low-confidence
draft as ready to file. It fails safe toward *more* human oversight: it only ever
adds a review gate, never auto-approves, and never downgrades a human-finalized
(`APPROVED`/`EDITED`) packet. `UNKNOWN` is short-circuited upstream and untouched
here. Applied identically in `orchestrator.run_pipeline` and the cockpit SSE path.

## 8. Reply localization  (Hindi / bilingual — additive, display-only)

The cockpit can request the reply in **Hindi** or **bilingual**. After the Drafter
(and the citation verifier / confidence gate), `src/noticeflow/localize.py::localize_packet`
translates only the two prose fields into `legal_basis_localized` / `reply_body_localized`
and sets `language`. **English stays canonical:** `legal_basis` / `reply_body` are never
mutated, so the statutory form PDF (`forms/generator.py`) and citation verification (§5) —
which read the English fields — are unaffected. Citations, `cited_source_ids`, figures,
GSTIN, dates, and classification are never translated. `language="en"` is a pure no-op (no
LLM call); any translation failure degrades silently to English. The cockpit prefers the
localized fields for display; the form download always renders English (GST forms are filed
in English). Threaded via `api.py` (`/api/run` `language` param, validated) and
`orchestrator.run_pipeline(language=...)`.

## Contract rules
- Every field a downstream agent needs MUST be populated upstream; if unknown, use `None` and note it, never fabricate (esp. GSTIN, amounts, dates).
- The Drafter MUST only cite sources present in `LegalContext.citations`. No citing un-retrieved law. **This is now code-enforced**: `CitationVerification` (§5) drops any citation not traceable to `retrieved_evidence` — prompt discipline is the first line, the verifier is the guarantee.
- `UNKNOWN` notice_type short-circuits the pipeline with a graceful "unsupported notice type" message.
- Dates are real `date` objects; `deadline_urgent` computed against `today` at draft time.
