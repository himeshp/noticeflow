# CLAUDE.md — NoticeFlow

> Read this first. This file is your operating context for the whole build.
> Detailed specs live in `/docs`. Read them before writing code for a given component.

## What we are building
**NoticeFlow** — an autonomous multi-agent system that ingests an Indian GST notice (PDF) and produces a **filing-ready response packet**: classified, legally grounded in real GST law, with a reconciliation annexure populated from accounting data, and a deadline flag. A human approves before finalization.

This is a **competition submission** (Google for Startups AI Agents Challenge, Track 1 — Build). The architecture choices below are partly dictated by competition rules; **do not substitute them.**

## Current status (updated 2026-06-05)
**The MVP is complete, compliant, and deployed.** The full Classifier → Researcher → Drafter pipeline runs on **Vertex AI Agent Engine** (engine `…/reasoningEngines/6398074104947146752`); all 3 notice types (ASMT-10 / DRC-01 / ITC-mismatch) are verified end-to-end including live Vertex AI Search retrieval and the MCP reconciliation tool. 74 tests pass; the demo cockpit (FastAPI + React) runs end-to-end.

We are now in the **gated-enhancements phase** — see `docs/10-enhancements.md` (tiered menu, build-gates, **feature freeze June 9**). **Submission deadline: June 12, 2026, 5:30 AM IST.** The "Build order" section below is the original Day 1–5 plan, kept for historical context — it is DONE, not a live to-do list.

> Note: mock ERP data now lives package-internal at `src/noticeflow/mcp/erp_data/` (shipped with the wheel for the Agent Engine runtime), not `data/mock_erp/` as the structure diagram shows.

## Hard constraints (competition rules — NON-NEGOTIABLE)
1. **Intelligence = Gemini via Vertex AI.** NEVER use Google AI Studio keys (they don't draw competition credits and may fail the mandatory-tech bar). Use Vertex AI Gemini only.
2. **Orchestration = Google ADK (Python).** Do not swap to LangChain/CrewAI — ADK usage is directly scored.
3. **Infrastructure = Agent Engine (Agent Runtime) on GCP.** Deploy target. Not local-only.
4. **MCP** must be used for at least one external-tool connection (our mock ERP).
5. **Grounding** via Vertex AI Search (RAG over real GST law corpus).
6. **Multi-agent** — the system must have ≥2 collaborating agents (we have 3 + orchestrator). The collaboration must demonstrably beat a single agent.
7. **Net-new code.** Everything in this repo is written fresh during the contest. Do not import prior project code.
8. **No secrets in the repo.** Use env vars / Secret Manager. The repo is PUBLIC for judging.

## ⚠️ Before you write ADK code — verify the API
ADK Python **2.0 is GA** and its API differs from 1.x. Your training data may be stale.
**Always check current usage at https://adk.dev/ (docs) and the `google/adk-python` repo before implementing.**
Key pages: `/get-started/python/`, `/workflows/`, `/agents/workflow-agents/sequential-agents/`, `/grounding/`, `/mcp/`, `/tools-custom/mcp-tools/`, `/deploy/agent-runtime/`.
If a doc and this file conflict on an ADK API detail, the live doc wins — flag it to the user.

## Documents — read the relevant one before building a component
| Doc | Read before… |
|-----|--------------|
| `docs/01-overview.md` | anything — the vision & scope |
| `docs/02-architecture.md` | wiring agents together / orchestration |
| `docs/03-data-contracts.md` | implementing ANY agent (the JSON passed between them) |
| `docs/04-mcp-tool.md` | the MCP mock-ERP server |
| `docs/05-grounding.md` | the Researcher / Vertex AI Search datastore |
| `docs/06-setup-runbook.md` | first-time env setup (Day 1) |
| `docs/07-build-plan.md` | sequencing your work / what to build next |
| `docs/08-demo-and-submission.md` | near the end — demo video & Devpost writeup |
| `docs/09-ui-ux.md` | the demo cockpit UI — build ONLY after Day-3 checkpoint passes |
| `docs/10-enhancements.md` | considering ANY post-MVP enhancement — tiered/gated menu with a June-9 feature freeze. Read its preamble + "Plan revisions" before building. |

## Repo structure (target)
```
noticeflow/
├── CLAUDE.md                 # this file
├── README.md
├── pyproject.toml            # or requirements.txt
├── .env.example              # never commit real .env
├── docs/                     # all specs (read these)
├── data/
│   ├── sample_notices/       # synthetic notice text/PDFs (3 types)
│   └── mock_erp/             # mock reconciliation JSON
├── corpus/                   # downloaded CBIC GST law PDFs (gitignored if large)
├── src/noticeflow/
│   ├── __init__.py
│   ├── agents/
│   │   ├── classifier.py
│   │   ├── researcher.py
│   │   ├── drafter.py
│   │   └── orchestrator.py
│   ├── mcp/
│   │   └── erp_server.py     # MCP server exposing reconciliation tool
│   ├── schemas.py            # pydantic models = the data contracts
│   └── config.py             # model IDs, region, project (from env)
├── scripts/
│   ├── build_datastore.py    # ingest corpus -> Vertex AI Search
│   └── gen_notices.py        # (optional) regenerate synthetic notices
├── frontend/                 # demo cockpit (React SPA) — built Day 4, see docs/09
└── tests/
```

## Build order (high level — see docs/07 for detail)
1. Env + repo skeleton + corpus download (Day 1)
2. `schemas.py` (data contracts) — **build this before any agent**
3. Vertex AI Search datastore (Day 2)
4. Classifier → Researcher (Day 2)
5. MCP ERP server → Drafter → Orchestrator → **demo-able** (Day 3)
6. Deploy to Agent Engine + test all 3 notice types (Day 4)
7. Demo video + Devpost writeup + submit (Day 5)

## Definition of done (MVP)
Upload any of the 3 supported notices → correct classification → correct cited law → drafted reply with populated annexure → human gate → deployed, publicly testable link.

## Working style
- Build the smallest end-to-end happy path FIRST (one notice type, all agents), then widen to 3 types. Do not build all agents to completion in isolation.
- Pin versions. Pydantic schemas are the source of truth for inter-agent data.
- Keep the grounding corpus FOCUSED (3 notice types' law only) — bloat hurts retrieval.
- When unsure about an ADK API: check adk.dev, don't guess.
