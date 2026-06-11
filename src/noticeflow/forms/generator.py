"""Render a ResponsePacket into the correct GST reply FORM as a PDF.

Deterministic, no LLM. The reply forms are public government formats; each notice
type maps to its statutory reply form. Output is explicitly watermarked as a
SYSTEM-GENERATED DRAFT for human review before filing.

Security: all dynamic text (reply body, legal basis, citations, notes — sourced
from the LLM) is escaped with xml.sax.saxutils.escape before being placed into a
reportlab Paragraph, which otherwise interprets a mini-XML markup. PDF is built
in memory (no filesystem writes). safe_filename() strips the download filename to
an allow-list to prevent HTTP header injection.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from noticeflow.schemas import NoticeType, ResponsePacket


@dataclass(frozen=True)
class FormSpec:
    code: str        # e.g. "DRC-06"
    rule_ref: str    # e.g. "See rule 142(4)"
    title: str       # statutory description of the reply form


# Notice type -> the statutory reply form the taxpayer files.
FORM_FOR_TYPE: dict[NoticeType, FormSpec] = {
    NoticeType.DRC_01: FormSpec(
        code="DRC-06",
        rule_ref="See rule 142(4)",
        title="Reply to the Show Cause Notice",
    ),
    NoticeType.ASMT_10: FormSpec(
        code="ASMT-11",
        rule_ref="See rule 99(2)",
        title="Reply to the notice issued under section 61 intimating "
        "discrepancies in the return",
    ),
    NoticeType.ITC_MISMATCH: FormSpec(
        code="DRC-01C",
        rule_ref="See rule 88D",
        title="Intimation of difference in input tax credit — Reply (Part B)",
    ),
    NoticeType.UNKNOWN: FormSpec(
        code="REPLY",
        rule_ref="",
        title="Reply to GST Notice",
    ),
}


def form_spec_for(notice_type: NoticeType) -> FormSpec:
    return FORM_FOR_TYPE.get(notice_type, FORM_FOR_TYPE[NoticeType.UNKNOWN])


_FILENAME_RE = re.compile(r"[^A-Za-z0-9_-]+")


def safe_filename(packet: ResponsePacket) -> str:
    """Build a download filename from form code + reference, allow-listed.

    Strips everything outside [A-Za-z0-9_-] so it can't inject newlines or
    quotes into a Content-Disposition header.
    """
    spec = form_spec_for(packet.notice_type)
    ref = packet.reference_number or "draft"
    raw = f"GST_{spec.code}_{ref}"
    cleaned = _FILENAME_RE.sub("_", raw).strip("_") or "GST_reply"
    return f"{cleaned}.pdf"


def _esc(value) -> str:
    """Escape for reportlab Paragraph markup; preserve newlines as <br/>."""
    return escape("" if value is None else str(value)).replace("\n", "<br/>")


def _money(value) -> str:
    try:
        return f"Rs. {float(value):,.2f}"
    except (TypeError, ValueError):
        return "Rs. 0.00"


def _annexure_rows(packet: ResponsePacket) -> tuple[list[list[str]], int]:
    """Annexure rows (incl. header) + the index of the highlighted variance row.

    Notice-type-aware (#FIX2): ASMT-10 scrutiny is a GSTR-1-vs-GSTR-3B OUTWARD
    SUPPLY (turnover) discrepancy, so it renders a turnover table — not an ITC
    table. DRC-01 and ITC-mismatch render the ITC reconciliation. Falls back to
    the ITC table if an ASMT-10 record lacks turnover figures.
    """
    a = packet.annexure
    is_turnover = (
        packet.notice_type == NoticeType.ASMT_10 and a.gstr1_outward_tax is not None
    )
    if is_turnover:
        return [
            ["Particulars", "Amount"],
            ["Outward Tax as per GSTR-1", _money(a.gstr1_outward_tax)],
            ["Outward Tax as per GSTR-3B (Table 3.1)", _money(a.gstr3b_outward_tax)],
            ["Difference (under-declared in GSTR-3B)", _money(a.outward_tax_difference)],
            ["Total Output Tax Liability", _money(a.output_tax_liability)],
        ], 3
    return [
        ["Particulars", "Amount"],
        ["GSTR-3B Tax Paid", _money(a.gstr3b_tax_paid)],
        ["GSTR-2B ITC Available", _money(a.gstr2b_itc_available)],
        ["GSTR-3B ITC Claimed", _money(a.gstr3b_itc_claimed)],
        ["ITC Mismatch", _money(a.itc_mismatch_amount)],
        ["Output Tax Liability", _money(a.output_tax_liability)],
    ], 4


def generate_form_pdf(packet: ResponsePacket) -> bytes:
    """Render the packet into its reply-form PDF and return the bytes."""
    spec = form_spec_for(packet.notice_type)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title=f"FORM GST {spec.code}",
        author="NoticeFlow",
    )

    styles = getSampleStyleSheet()
    h_form = ParagraphStyle("hForm", parent=styles["Title"], fontSize=16, spaceAfter=2)
    h_rule = ParagraphStyle("hRule", parent=styles["Normal"], alignment=TA_CENTER,
                            fontSize=9, textColor=colors.HexColor("#555555"), spaceAfter=2)
    h_title = ParagraphStyle("hTitle", parent=styles["Normal"], alignment=TA_CENTER,
                             fontSize=10.5, leading=14, spaceAfter=8)
    draft = ParagraphStyle("draft", parent=styles["Normal"], alignment=TA_CENTER,
                           fontSize=9, textColor=colors.HexColor("#B45309"))
    block_label = ParagraphStyle("blockLabel", parent=styles["Heading4"], fontSize=10.5,
                                 spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1B4FD8"))
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, leading=14,
                          alignment=TA_JUSTIFY)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5,
                           textColor=colors.HexColor("#6B7280"))

    flow = []
    flow.append(Paragraph(f"FORM GST {_esc(spec.code)}", h_form))
    if spec.rule_ref:
        flow.append(Paragraph(f"[{_esc(spec.rule_ref)}]", h_rule))
    flow.append(Paragraph(_esc(spec.title), h_title))

    # Draft disclaimer banner
    flow.append(Table(
        [[Paragraph("SYSTEM-GENERATED DRAFT — review and verify before filing on the GST portal.", draft)]],
        colWidths=[doc.width],
        style=TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D97706")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFBEB")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]),
    ))
    flow.append(Spacer(1, 8))

    # Taxpayer / notice details
    details = [
        ["GSTIN", _esc(packet.gstin or "—"), "Tax Period", _esc(packet.tax_period or "—")],
        ["Notice Ref.", _esc(packet.reference_number or "—"),
         "Response Due", _esc(packet.response_deadline.isoformat() if packet.response_deadline else "—")],
    ]
    det_tbl = Table(
        [[Paragraph(f"<b>{c}</b>" if i % 2 == 0 else c, small) for i, c in enumerate(row)] for row in details],
        colWidths=[doc.width * 0.16, doc.width * 0.34, doc.width * 0.16, doc.width * 0.34],
    )
    det_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(det_tbl)

    # 1. Legal basis + citations
    flow.append(Paragraph("1. Legal Basis", block_label))
    flow.append(Paragraph(_esc(packet.legal_basis), body))
    if packet.citations:
        flow.append(Spacer(1, 4))
        for c in packet.citations:
            flow.append(Paragraph(f"&bull; {_esc(c.source_id)}", small))
    if packet.citation_verification is not None:
        cv = packet.citation_verification
        flow.append(Spacer(1, 3))
        flow.append(Paragraph(
            f"Citations programmatically verified against retrieved law: "
            f"{cv.verified}/{cv.total_citations}.", small))

    # 2. Reply
    flow.append(Paragraph("2. Reply", block_label))
    flow.append(Paragraph(_esc(packet.reply_body), body))

    # 3. Annexure — reconciliation statement
    a = packet.annexure
    flow.append(Paragraph("3. Annexure — Reconciliation Statement", block_label))
    ann_rows, highlight = _annexure_rows(packet)
    ann_tbl = Table([[Paragraph(_esc(c0), small), Paragraph(_esc(c1), small)] for c0, c1 in ann_rows],
                    colWidths=[doc.width * 0.6, doc.width * 0.4])
    ann_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F2EF")),
        ("BACKGROUND", (0, highlight), (-1, highlight), colors.HexColor("#FEF2F2")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(ann_tbl)
    if a.notes:
        flow.append(Spacer(1, 3))
        flow.append(Paragraph(f"Note: {_esc(a.notes)}", small))

    # Verification / declaration
    flow.append(Paragraph("Verification", block_label))
    flow.append(Paragraph(
        "I hereby solemnly affirm and declare that the information given above is "
        "true and correct to the best of my knowledge and belief and nothing has "
        "been concealed therefrom.", body))
    flow.append(Spacer(1, 14))
    sign = Table([[Paragraph("Place: __________________", small),
                   Paragraph("Signature of Authorised Signatory: __________________", small)],
                  [Paragraph("Date: __________________", small),
                   Paragraph("Name / Designation: __________________", small)]],
                 colWidths=[doc.width * 0.4, doc.width * 0.6])
    sign.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 6)]))
    flow.append(sign)

    flow.append(Spacer(1, 10))
    flow.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E7EB")))
    flow.append(Paragraph(
        "Generated by NoticeFlow. This is a draft prepared for human review; it is "
        "not a filed return and has no legal effect until reviewed, signed and "
        "submitted by the taxpayer.", small))

    doc.build(flow)
    return buf.getvalue()
