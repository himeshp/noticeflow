# 02 — Architecture

> Verify ADK 2.0 API specifics at https://adk.dev/ before implementing. This doc describes intent; the live docs govern exact API calls.

## Topology
```
   Notice text / PDF
        │
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR  (ADK SequentialAgent — packaged + deployed on Agent      │
│ Engine). Emits raw agent output; deterministic guards run in the       │
│ wrapper/serving layer (see "Two layers" below).                        │
│                                                                        │
│   CLASSIFIER ──▶ RESEARCHER ──────▶ DRAFTER                            │
│   Gemini Flash   Gemini Flash       Gemini Pro                         │
│   output_schema  + Vertex AI        + MCP tool (mock ERP) ──┐          │
│                    Search RAG            ▲                  ▼          │
│                    │ captures            │ issues   ┌────────────────┐ │
│                    ▼ retrieved_evidence  │          │ MCP TOOL       │ │
│              (grounding chunks)          │          │ reconciliation │ │
│                                    ┌─────┴───────┐  └────────────────┘ │
│                                    │ CRITIC      │  flag-gated loop:   │
│                                    │ deterministic│ LoopAgent(max 2)   │
│                                    │ (no LLM)    │  Drafter ⇄ Critic   │
│                                    └─────────────┘  (#1.1)             │
└──────────────────────────────────────────────────────────────────────┘
        │
        ▼   post-pipeline guards (deterministic, no LLM) + optional localize
┌──────────────────────────────────────────────────────────────────────┐
│ CITATION VERIFIER (#1.2)  drops citations not traceable to retrieved   │
│                           law; attaches N/N audit          [no LLM]    │
│ CONFIDENCE GATE  (#3.8)   low-confidence KNOWN type → NEEDS_HUMAN [no LLM] │
│ DEADLINE URGENCY (#2.6)   overdue / critical / soon / normal tier [no LLM] │
│ LOCALIZE (#3.7)           Hindi / bilingual reply prose (display-only; │
│                           English stays canonical) — Gemini Flash      │
└──────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────┐
│ HUMAN GATE   │  review / approve / edit   (PENDING_REVIEW | NEEDS_HUMAN)
└──────────────┘
        │
        ▼
  Response Packet ──▶ Filing-form PDF (#2.4: DRC-01→DRC-06, ASMT-10→ASMT-11,
   (deliverable)                       ITC-mismatch→DRC-01C Part B)

  Surfaces:  Demo cockpit (FastAPI + React, SSE, execution-trace panel #3.9)
             A2A agent card + to_a2a() server (#2.5, discoverable)
```

## Two layers: deployed graph vs. serving wrapper
A recurring architectural fact (it dictates *where* logic lives):
- **The deployed Agent Engine emits raw agent output.** The `SequentialAgent`
  graph (Classifier → Researcher → Drafter, optionally the review loop) is what
  ships in the wheel and runs in the cloud.
- **The deterministic guards are wrapper/serving logic** — the citation verifier
  (#1.2), confidence gate (#3.8), urgency annotation (#2.6), form PDF (#2.4), and
  the A2A surface (#2.5) live in `run_pipeline()` / `api.py` / dedicated modules,
  not inside the graph. They run in the cockpit and the local pipeline, the same
  place the original `UNKNOWN` short-circuit already lived. (Exception: the
  citation evidence is *captured inside* the Researcher so the verifier and the
  in-graph Critic can both use it.)

## Why multi-agent beats single-agent (the rubric scores this — make it true)
- **Separation of concerns improves reliability:** classification accuracy is independent of legal-retrieval accuracy is independent of drafting quality. A single prompt conflates them and degrades all three.
- **Grounding is isolated to the Researcher**, so citations are auditable and the Drafter can't hallucinate law it didn't retrieve.
- **The Drafter consumes structured, verified inputs** (classified facts + retrieved law + real figures), so its job is composition, not reasoning-from-scratch — which is where LLMs are most reliable.
Demonstrate this contrast in the demo: show that a single-shot prompt mis-cites or mixes up the notice type, while the pipeline gets it right.

## Agent responsibilities
### Classifier (Gemini Flash, multimodal)
- Input: notice PDF (bytes/path)
- Reads the PDF, extracts: notice type, governing section, deadline date, demanded amount, taxpayer GSTIN, tax period, reference number
- Output: `ClassifiedNotice` (see docs/03)
- Must handle the 3 supported types; for anything else, return type=`UNKNOWN` and stop gracefully.

### Researcher (Gemini Flash + Vertex AI Search)
- Input: `ClassifiedNotice`
- Queries the Vertex AI Search datastore for law governing the identified notice type/section
- Optionally Google Search grounding for recent circulars (stretch)
- Output: `LegalContext` — list of cited passages (section/circular id, text snippet, source) (see docs/03)
- Must return citations with source identifiers, not paraphrase without attribution.
- **Also captures `retrieved_evidence`** (the verbatim grounding-chunk text from
  `event.grounding_metadata`) into state — this is the ground truth the citation
  verifier (#1.2) and the Critic (#1.1) check citations against.

### Drafter (Gemini Pro)
- Input: `ClassifiedNotice` + `LegalContext` + `ReconciliationData` (from MCP)
- Calls the MCP tool `get_reconciliation_data(gstin, period)` to fetch figures
- Composes the reply packet: legal basis, point-by-point response, citations, populated annexure, deadline flag
- Output: `ResponsePacket` (see docs/03)
- When the review loop is on, re-drafts to fix the Critic's `issues` on a REVISE verdict.

### Critic (deterministic — no LLM) — flag-gated, #1.1
- Input: the Drafter's `ResponsePacket` + the Researcher's `retrieved_evidence`
- Runs two **code** checks: every cited source is grounded in retrieved law, and
  the annexure arithmetic reconciles (`itc_mismatch == claimed − available`)
- Output: `ReviewResult` (APPROVE | REVISE + concrete `issues`). On APPROVE it
  escalates (stops the loop); on REVISE the Drafter re-drafts, capped at 2 rounds.
  A REVISE surviving the cap sets `reviewer_status="NEEDS_HUMAN"`.
- Kept deterministic on purpose: two LLMs can hallucinate agreement; code cannot.

### Orchestrator (ADK SequentialAgent)
- Runs the three in order, passing typed state between them
- Surfaces the final packet to the human gate
- Use ADK session/state to carry the contracts between sub-agents

## Human gate
After the Drafter (and any guards), present the packet for human review/approve/edit
before it's marked final. Every packet leaves the pipeline `PENDING_REVIEW`, or
`NEEDS_HUMAN` when the confidence gate (#3.8) or an unresolved review (#1.1) flagged
it. A visible approval action is enough; NoticeFlow drafts, it does not file.

## ADK primitive choices (verify on adk.dev)
- Orchestrator: **SequentialAgent** (simple, deterministic order). Note: ADK 2.x
  emits `DeprecationWarning: SequentialAgent ... use Workflow instead`. It runs
  correctly today and is deployed; migrating to the Workflow API is the clear next
  maintenance step but was **deliberately not done before the June-9 freeze** (a
  rewrite re-opens every deploy bug already fixed).
- Self-correction: **LoopAgent** wrapping `[Drafter, Critic]`, `max_iterations=2`,
  flag-gated behind `NOTICEFLOW_ENABLE_REVIEW_LOOP` (default OFF). The Critic stops
  the loop by escalating via `EventActions(escalate=True)`; state is persisted with
  `state_delta` (a direct `ctx.session.state` write is not reliably committed).
- Sub-agents: **LlmAgent** with `model`, `instruction`, `tools`. The Classifier uses
  `output_schema` (structured output, **no tools**); the Researcher/Drafter use tools
  and we parse their JSON. (`output_schema` and tools are mutually exclusive in ADK.)
- Researcher grounding: **VertexAiSearchTool** over the Discovery Engine datastore.
- Drafter MCP: **MCPToolset** + `StdioServerParameters`, `tool_filter` least-privilege.

## Deployment
The orchestrator is packaged as a wheel and deployed to **Agent Engine** via
`reasoning_engines.AdkApp` + `agent_engines.create` (see docs/06 and
`scripts/deploy_agent_engine.py`). The deployed engine runs the proven **linear**
pipeline (review loop flag OFF); all 3 notice types are verified end-to-end in the
cloud including live Vertex AI Search retrieval and the MCP tool call. The review
loop is built, tested, and proven via `run_pipeline`/the eval harness; enabling it
on the engine needs a small deploy-safe state-seeding callback (deferred).
