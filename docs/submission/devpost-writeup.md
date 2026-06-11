# NoticeFlow — Devpost Writeup

> Track: **Build (Net-New Agents)** · Region: **APAC**
> Paste these sections into the matching Devpost fields. See
> [`devpost-fields.md`](devpost-fields.md) for the field-by-field mapping.

---

## Inspiration

Indian businesses receive cryptic GST notices with hard response deadlines — often
7 to 30 days. A small-business owner who gets an ASMT-10 scrutiny notice or a
DRC-01 demand usually has no idea what it means, panics, and pays a chartered
accountant ₹5,000–₹25,000 per notice — or misses the deadline and faces escalating
demand and penalty. Yet the CA's work is largely mechanical: identify the notice
type, find the governing section of the CGST Act, pull the relevant figures from the
books, and draft a structured, citation-backed reply. That is exactly the shape of
work a well-grounded multi-agent system can do — fast, consistently, and with a human
sign-off before anything is filed.

## What it does

NoticeFlow ingests an Indian GST notice and autonomously produces a **filing-ready
response packet**:

- **Classification** — notice type, governing sections, GSTIN, tax period, reference
  number, demanded amount, and the response deadline.
- **Legal grounding** — citations retrieved from a corpus of **real CBIC GST law**
  (the Act, the Rules, and relevant circulars), with section/circular identifiers and
  the retrieved text — not paraphrase without attribution.
- **Code-verified citations (anti-hallucination guarantee)** — every citation in the
  reply is checked **programmatically** (no LLM) against the text actually returned by
  Vertex AI Search; any citation that cannot be traced to retrieved law is dropped, and
  the packet carries a "N/N citations verified" audit. Fabricated law cannot survive to
  the filed reply.
- **Reconciliation annexure** — GSTR-3B vs GSTR-2B figures and the ITC mismatch
  amount, fetched from an accounting/ERP system over **MCP**.
- **A drafted reply** — point-by-point, in the correct procedural form (e.g. ASMT-11
  for a scrutiny notice, Part B of DRC-01C for an ITC-difference intimation), citing
  only the law that was actually retrieved.
- **The actual filing form, downloadable** — the reviewed packet renders to the
  statutory reply PDF (DRC-01→**DRC-06**, ASMT-10→**ASMT-11**, ITC mismatch→**DRC-01C
  Part B**), watermarked as a draft for human signature. NoticeFlow doesn't just advise —
  it produces the form you upload to the GST portal.
- **A deadline flag** and a **human approval gate** — every packet leaves the pipeline
  with `reviewer_status = "PENDING_REVIEW"`. A human approves or edits before anything
  is treated as final. NoticeFlow drafts; it does not file.
- **Hindi / bilingual output (APAC accessibility)** — the taxpayer-facing reply can be
  rendered in **Hindi** or **bilingual** (English + Hindi) at the click of a toggle, in a
  formal legal register, while the filed statutory form stays English (as the GST portal
  requires). Citations, figures, and the anti-hallucination guarantee are untouched —
  localization translates only the explanatory prose.

It supports three of the most common notice types: **ASMT-10** (scrutiny, Sec. 61),
**DRC-01** (show-cause/demand, Sec. 73/74), and **ITC mismatch / DRC-01C** (Sec. 16).

## How we built it

**Orchestration — Google ADK (Python).** The pipeline is an ADK **`SequentialAgent`**
that runs three **`LlmAgent`** sub-agents in order, passing typed state between them
(`classified_notice_json` → `legal_context_json` → `response_packet_json`):

1. **Classifier** — `LlmAgent` on **`gemini-2.5-flash`** with a Pydantic
   `output_schema`, so classification returns structured, validated fields.
2. **Researcher** — `LlmAgent` on **`gemini-2.5-flash`** with ADK's
   **`VertexAiSearchTool`** attached, querying a **Vertex AI Search** datastore built
   over the CBIC corpus. It is prompted to cite only retrieved passages.
3. **Drafter** — `LlmAgent` on **`gemini-2.5-pro`** with an **`MCPToolset`**
   (`StdioServerParameters`) connected to our mock-ERP **MCP** server. It calls the
   tool `get_reconciliation_data(gstin, tax_period)`, then composes the reply,
   citing only the source IDs the Researcher returned.

**Intelligence — Gemini via Vertex AI.** All model calls route through Vertex AI
(`GOOGLE_GENAI_USE_VERTEXAI=true`, enforced in `config.py`). No Google AI Studio keys
are used anywhere. Calls use client-side exponential backoff (`HttpRetryOptions` on
429/503) to ride out Dynamic Shared Quota bursts.

**Grounding — Vertex AI Search.** `scripts/build_datastore.py` downloads the CBIC PDFs,
stages them in Cloud Storage, and builds a Vertex AI Search (Discovery Engine)
datastore. The Researcher retrieves attributed passages from it.

**External tool — MCP.** The Drafter's reconciliation figures come from an MCP server
(`src/noticeflow/mcp/erp_server.py`, `FastMCP`) exposing a single least-privilege tool
(`tool_filter=["get_reconciliation_data"]`). The server validates GSTIN/period with
strict regexes and resolves data files only from inside its own package directory
(path-traversal-guarded) — the path is never built from model/user input.

**Code-enforced citation verification.** The Researcher captures the *actual* text
Vertex AI Search returned (`grounding_metadata`) into state. A pure-Python verifier
(`src/noticeflow/verify/citations.py`, no LLM) then confirms each emitted citation by
text-containment — its section/rule/circular reference or a run of its snippet must
appear in that retrieved text. Unverifiable citations are dropped and audited. Anti-
hallucination is a code guarantee, not a prompt request.

**Terminal action — the real filing form.** A deterministic renderer
(`src/noticeflow/forms/`, reportlab) turns the reviewed packet into the statutory reply
PDF (DRC-06 / ASMT-11 / DRC-01C Part B), watermarked as a draft for signature, served
from `POST /api/form`.

**Deployment — Vertex AI Agent Engine.** The orchestrator is packaged as a wheel and
deployed to Agent Engine (`reasoning_engines.AdkApp` + `agent_engines.create`). The
full pipeline — including live Vertex AI Search retrieval and the MCP tool call — runs
in the cloud, not just locally.

**Why three agents beat one.** Separation of concerns makes each step independently
reliable and auditable. Grounding is isolated to the Researcher, so the Drafter
physically cannot cite law it did not retrieve. The Drafter receives structured,
verified inputs (classified facts + retrieved law + real figures), so its job is
composition — where LLMs are most reliable — rather than reasoning the whole problem
from scratch in one prompt, where notice type, citations, and figures tend to bleed
into each other and degrade together.

## Results (measured)

Evaluated over **15 synthetic notices** with ground-truth labels (`scripts/eval.py`,
report in `docs/submission/eval_report.md`):

| Metric | Result |
|--------|--------|
| Classification accuracy | **15/15 (100%)** |
| Annexure reconciliation accuracy | **100%** |
| UNKNOWN handling (unsupported notices correctly refused) | **100%** |
| Citations code-verified against retrieved law | unverifiable citations dropped automatically |
| Review loop — drafts approved by the deterministic critic | **100%** (avg 1.0 iterations) |
| End-to-end latency (median / p90) | ~72s / ~85s |

Every citation is checked programmatically against the retrieved source text, so the
"grounded in real law" claim is enforced by code, not asserted by a prompt. The
Drafter↔Critic loop validates each draft before the human gate; self-correction
(detect a bad draft, re-draft, approve) is demonstrated end-to-end in the test suite.

## Data sources & disclosure

- **GST law corpus — REAL, public (cbic-gst.gov.in).** This is the capability layer
  and it is genuine government source material:
  - CGST Act 2017 (consolidated, updated 31-08-2021)
  - CGST Rules 2017, Part A (Rules)
  - Circular 31/05/2018-GST (proper officers for Sec. 73/74 demands)
  - Circular 135/05/2020-GST (ITC / GSTR-2A reflection, Sec. 16 / Rule 36(4))
  - Circular 183/15/2022-GST (ITC mismatch GSTR-3B vs GSTR-2A resolution)
- **Notice inputs — SYNTHETIC.** The three sample notices are self-generated from
  public CBIC form formats. The formats are public; the taxpayer details are fabricated.
- **ERP / reconciliation figures — MOCKED.** Served by our MCP server from static JSON.
  The *format* of GST reconciliation data is public and standardized; only the *values*
  are fabricated. No real taxpayer data is used anywhere in this project.

The principle: the part that proves capability (citing real Indian tax law) is real;
the parts we fake are plumbing whose format is public.

## Challenges & learnings

- **ADK 2.x API surface moves fast.** We verified primitives against the live ADK docs
  rather than trusting prior knowledge. A concrete signal: ADK now emits
  `DeprecationWarning: SequentialAgent is deprecated ... use Workflow instead`. Our
  `SequentialAgent` pipeline runs correctly today and is deployed, but the migration to
  the Workflow API is the clear next maintenance step — a real lesson in building on a
  GA SDK that is still evolving.
- **Structured output vs. tools is a genuine trade-off in ADK.** An agent with an
  `output_schema` cannot also use tools. So the Classifier uses `output_schema` (clean
  structured output, no tools), while the Researcher and Drafter use tools and we
  parse their JSON explicitly. State written by an `output_schema` agent arrives as a
  dict; a tool-using agent's output arrives as a JSON string — handling both correctly
  was necessary to make the pipeline read its own state reliably.
- **Region coupling is not what you'd assume.** Vertex AI Search datastores live in
  `global`/`us`/`eu`, decoupled from the `us-central1` region used for Gemini and Agent
  Engine. We had to separate those locations in config.
- **Cloudpickle bakes construction-time values.** The deployed agent is pickled at build
  time, so any local absolute path (e.g. the MCP interpreter) gets frozen in. We made
  the MCP launch command resolve to the Agent Engine runtime's own interpreter so the
  stdio server starts in the cloud.
- **Grounding integrity must be enforced, not hoped for.** We added a config assertion
  so the deployed engine and the demo cockpit refuse to run without a datastore — the
  ungrounded fallback citation path cannot fire where it would be seen, so a fallback
  can never be mistaken for retrieved law.

## What's next

- Migrate the orchestrator from `SequentialAgent` to the ADK Workflow API.
- Add a fourth notice type, and a Hindi-tagged law corpus so retrieved citations (not just
  the reply prose) can be surfaced in Hindi.
- Replace the mock ERP with a real Tally/Zoho MCP connector (the tool contract already
  matches a real reconciliation payload).
- A Reviewer/critic agent in a correction loop that consumes the citation verifier to
  self-revise drafts before the human gate.
