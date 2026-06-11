from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class NoticeType(str, Enum):
    ASMT_10 = "ASMT_10"
    DRC_01 = "DRC_01"
    ITC_MISMATCH = "ITC_MISMATCH"
    UNKNOWN = "UNKNOWN"


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


class Citation(BaseModel):
    source_id: str = Field(
        description="e.g. 'CGST Act 2017, Section 73' or 'Circular 31/05/2018-GST'"
    )
    source_type: str = Field(
        description="one of: act, rule, circular, instruction, notification"
    )
    snippet: str = Field(description="the relevant retrieved text passage")
    relevance_note: str = Field(
        description="why this applies to the notice (1 sentence)"
    )
    source_doc: Optional[str] = Field(
        default=None,
        description="allow-listed key of the source PDF (for the in-app viewer), or None",
    )
    source_page: Optional[int] = Field(
        default=None,
        description="1-based page of the cited section/rule in source_doc, or None",
    )


class RetrievedChunk(BaseModel):
    """A passage actually returned by Vertex AI Search grounding, captured from
    event.grounding_metadata. This is the ground truth the citation verifier
    checks against — citations not traceable to this text are flagged."""
    title: str = Field(description="corpus document title, e.g. 'cgst_act_2017'")
    uri: str = Field(description="source URI, e.g. gs://.../cgst_act_2017.pdf")
    text: str = Field(description="the retrieved passage text, verbatim")


class CitationVerification(BaseModel):
    """Result of programmatically verifying packet citations against retrieved
    law. Produced by pure code (no LLM) — the anti-hallucination guarantee."""
    total_citations: int = Field(description="citations the drafter emitted")
    verified: int = Field(description="citations traceable to retrieved text")
    unverified: list[str] = Field(
        default_factory=list,
        description="source_ids with no retrieval backing (dropped from the packet)",
    )
    passed: bool = Field(description="True iff unverified is empty")


class ReviewResult(BaseModel):
    """Output of the deterministic Critic in the Drafter<->Critic review loop.

    Both checks are code-enforced (no LLM): the citation set must be grounded in
    what the Researcher retrieved, and the annexure arithmetic must reconcile."""
    citations_grounded: bool = Field(
        description="every cited source_id is one the Researcher actually returned"
    )
    figures_reconcile: bool = Field(
        description="annexure ITC mismatch equals claimed minus available"
    )
    issues: list[str] = Field(
        default_factory=list, description="concrete problems for the Drafter to fix"
    )
    verdict: str = Field(description="APPROVE | REVISE")
    round: int = Field(description="1-based review iteration that produced this verdict")


class LegalContext(BaseModel):
    notice_type: NoticeType
    citations: list[Citation] = Field(
        description="retrieved, attributed legal passages governing this notice"
    )
    applicable_response_options: list[str] = Field(
        description="what the taxpayer can legitimately argue/do per the law"
    )
    required_annexures: list[str] = Field(
        description="what supporting docs/figures the reply must include"
    )
    retrieved_evidence: list[RetrievedChunk] = Field(
        default_factory=list,
        description="raw passages returned by Vertex AI Search — basis for citation verification",
    )


class ReconciliationData(BaseModel):
    gstin: str
    tax_period: str
    gstr3b_tax_paid: float
    gstr2b_itc_available: float
    gstr3b_itc_claimed: float
    itc_mismatch_amount: float
    output_tax_liability: float
    notes: Optional[str] = None
    # Annexure shape (#FIX2). "ITC" = GSTR-3B vs GSTR-2B input-tax-credit table
    # (DRC-01, ITC-mismatch). "TURNOVER" = GSTR-1 vs GSTR-3B outward-supply table
    # (ASMT-10 scrutiny). The turnover fields are populated only when TURNOVER.
    recon_type: str = Field(
        default="ITC", description="ITC | TURNOVER — which reconciliation the annexure shows"
    )
    gstr1_outward_tax: Optional[float] = Field(
        default=None, description="outward tax declared in GSTR-1 (TURNOVER only)"
    )
    gstr3b_outward_tax: Optional[float] = Field(
        default=None, description="outward tax declared in GSTR-3B (TURNOVER only)"
    )
    outward_tax_difference: Optional[float] = Field(
        default=None, description="GSTR-1 minus GSTR-3B outward tax (TURNOVER only)"
    )


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
        description="PENDING_REVIEW | APPROVED | EDITED | NEEDS_HUMAN",
    )
    escalation_reason: Optional[str] = Field(
        default=None,
        description="why the packet was routed to a human (e.g. low classification confidence)",
    )
    citation_verification: Optional[CitationVerification] = Field(
        default=None,
        description="programmatic check that every citation traces to retrieved law",
    )
    review: Optional[ReviewResult] = Field(
        default=None,
        description="verdict from the Drafter<->Critic review loop, if it ran",
    )
    language: str = Field(
        default="en",
        description="language of the localized reply: en | hi | bilingual",
    )
    legal_basis_localized: Optional[str] = Field(
        default=None,
        description="legal_basis in the requested language (None when en); display-only — English legal_basis stays canonical",
    )
    reply_body_localized: Optional[str] = Field(
        default=None,
        description="reply_body in the requested language (None when en); display-only — English reply_body stays canonical",
    )

    @classmethod
    def compute_deadline_urgent(cls, deadline: Optional[date]) -> bool:
        if deadline is None:
            return False
        today = datetime.now(timezone.utc).date()
        return (deadline - today).days <= 7
