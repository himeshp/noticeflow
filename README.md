# NoticeFlow

Autonomous multi-agent system that turns a cryptic Indian GST notice into a **filing-ready response packet** — classified, grounded in real GST law with **code-verified citations**, a reconciliation annexure, the actual statutory reply form as a PDF, and a human approval gate.

Built for the **Google for Startups AI Agents Challenge — Track 1 (Build)**, APAC.

## How it works
A GST notice flows through three collaborating agents orchestrated with Google's ADK (`SequentialAgent`):

1. **Classifier** (Gemini 2.5 Flash) — reads the notice and extracts type, governing sections, deadline, demanded amount, GSTIN, and tax period as validated structured output.
2. **Researcher** (Gemini 2.5 Flash + Vertex AI Search) — retrieves and cites the governing GST law from a datastore over real CBIC documents.
3. **Drafter** (Gemini 2.5 Pro + MCP) — calls a mock-ERP **MCP** tool for reconciliation figures and composes the cited, filing-ready reply.

Every packet leaves the pipeline as `PENDING_REVIEW`; a human approves or edits before anything is finalized. NoticeFlow drafts — it never auto-files.

Supports three notice types: **ASMT-10** (scrutiny, Sec. 61), **DRC-01** (demand, Sec. 73/74), and **ITC-mismatch / DRC-01C** (Sec. 16).

## What makes it trustworthy
- **Code-verified citations (anti-hallucination).** A pure-Python verifier (no LLM) checks every citation against the text Vertex AI Search actually returned; untraceable citations are dropped, and the packet carries an "N/N citations verified" audit. Fabricated law cannot reach the reply.
- **See the real law.** Click any citation to open the actual CBIC government PDF in an in-app viewer, jumped to the page and highlighted at the cited passage.
- **The real filing form.** The reviewed packet renders to the statutory reply PDF (DRC-01→**DRC-06**, ASMT-10→**ASMT-11**, ITC mismatch→**DRC-01C Part B**) — the document you submit, not just advice.
- **Hindi / bilingual output.** The taxpayer-facing reply can render in Hindi or bilingual (English + Hindi); the filed statutory form stays English as the GST portal requires.
- **Deadline & confidence gates.** Tiered urgency flag on the response deadline; low-confidence classifications are routed to a human instead of presented as ready to file.

## Stack
Google ADK (Python) · Gemini 2.5 via Vertex AI · Vertex AI Search (grounding) · MCP (external ERP tool) · Vertex AI Agent Engine (deploy) · A2A (discoverability) · FastAPI + React (demo cockpit) · Cloud Run.

NoticeFlow also publishes an [A2A agent card](docs/submission/agent-card.json) and can run as a
discoverable A2A agent (`pip install -e ".[a2a]"; uvicorn noticeflow.a2a_app:get_app --factory`).

## Live demo
**Cockpit:** https://noticeflow-cockpit-205182179995.us-central1.run.app (Cloud Run, public)

> The cockpit has a lightweight password gate to stop bots from abusing the AI quota.
> Credentials are provided in the Devpost submission. See
> [`docs/submission/testing-instructions.md`](docs/submission/testing-instructions.md) for a full walkthrough.

## Repo guide
- **Start with [`CLAUDE.md`](CLAUDE.md)** — operating context and constraints.
- **[`docs/`](docs/)** — full specs (overview, architecture, data contracts, MCP, grounding, setup, build plan, demo).
- **[`docs/submission/`](docs/submission/)** — Devpost writeup, architecture diagram, testing instructions, eval report.
- `src/noticeflow/agents/` — the four agents (classifier, researcher, drafter, orchestrator).
- `src/noticeflow/mcp/` — the MCP ERP server; mock reconciliation data ships package-internal in `src/noticeflow/mcp/erp_data/` (values fabricated).
- `data/sample_notices/` — synthetic notices (3 types; formats are public, values fabricated).
- `data/source_pdfs/` — the public CBIC law PDFs served by the in-app citation viewer.

## Data & disclosure
GST law grounding uses **real, public CBIC documents** (cbic-gst.gov.in) — the CGST Act 2017, the CGST Rules 2017, and Circulars 31/05/2018, 135/05/2020, and 183/15/2022-GST. Sample notices are synthetic and ERP/reconciliation figures are mocked — **no real taxpayer data is used anywhere**.

## Status
Deployed on **Vertex AI Agent Engine**; the full Classifier → Researcher → Drafter pipeline runs in the cloud, including live GST-law retrieval and MCP reconciliation lookups. All three notice types verified end-to-end. Evaluated over 15 synthetic notices: 100% classification accuracy and 100% reconciliation accuracy (see [`docs/submission/eval_report.md`](docs/submission/eval_report.md)).
