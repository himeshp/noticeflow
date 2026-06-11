# 01 — Overview & Scope

## Problem
Indian businesses receive cryptic GST notices with strict response deadlines (often 7–30 days). SMEs don't understand them, panic, and pay a CA ₹5,000–25,000 per notice — or miss the deadline and face escalating demands. The CA's work is largely mechanical: identify the notice type, find the governing law, pull relevant figures from the books, draft a structured reply with citations.

## Solution
NoticeFlow ingests a GST notice PDF and autonomously produces a **filing-ready response packet** — classified, legally grounded, figure-backed, citation-complete — with a human approval gate before finalization.

## Target user (B2B)
Indian SMEs / their in-house accountants, and small CA firms wanting to handle more notices per analyst.

## Core autonomous action
NoticeFlow does not merely *explain* a notice. It **produces a submission-ready reply document**: legal basis, cited sections/circulars, a reconciliation annexure populated from accounting data, and a deadline flag.

## Supported notice types (EXACTLY THREE — do not add more in MVP)
| # | Notice | Section | Why |
|---|--------|---------|-----|
| 1 | **ASMT-10** (Scrutiny) | Sec. 61 | Most common first-contact notice |
| 2 | **DRC-01** (Show-cause/demand) | Sec. 73/74 | Highest stakes, clearest grounding |
| 3 | **ITC Mismatch** (GSTR-2B vs 3B) | Sec. 16 | Most frequent real-world dispute |

## Real vs. mocked data
| Layer | Source | Real? |
|-------|--------|-------|
| GST law grounding corpus | CBIC PDFs (cbic-gst.gov.in) | ✅ REAL — the capability layer |
| Notice inputs | Self-generated from public form templates | ⚠️ Synthetic (formats are public) |
| ERP / reconciliation figures | Mock JSON via MCP server | ⚠️ Mocked (rules permit) |

Principle: the part that proves capability (citing real Indian tax law) is real; the part we fake is plumbing whose format is public.

## Out of scope (v1)
- Actual e-filing to the GST portal (we produce the packet; we don't submit)
- Live ERP integrations (Tally/Zoho) — mocked via MCP
- 4th+ notice type
- User auth / multi-tenancy / billing
- Custom frontend (use `adk web` unless time allows)
- Hindi output mode (stretch goal)
- Legal guarantees — NoticeFlow drafts; a human reviews

## Definition of done (MVP acceptance)
1. Upload one of the 3 notice PDFs → correct classification
2. Researcher returns correct governing section(s) with real citations
3. Drafter produces a coherent reply packet with populated recon annexure
4. Human approval gate visible
5. Deployed and testable via a public link
