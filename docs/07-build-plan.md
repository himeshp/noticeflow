# 07 — Build Plan (5-Day Schedule)

> **Target: demo-able by end of Day 3.** If Days 4–5 slip, you still have a submittable project.
> ⚠️ Confirm the operative deadline on Devpost. Build toward **June 5** as a safety buffer (email says June 11; old rules PDF says June 5).

## Golden rule
Build the **smallest end-to-end happy path first** — ONE notice type (DRC-01) through ALL agents — then widen to 3 types. Do not perfect agents in isolation.

## Day 1 — Foundation & data
- [ ] Apply for $500 credits (do first — approval lag)
- [ ] GCP project, enable APIs (docs/06)
- [ ] Cloud Shell env; `pip install google-adk`; hello agent on Vertex Gemini
- [ ] Public GitHub repo (ik-labs) + skeleton + `.gitignore` + `.env.example`
- [ ] Implement `src/noticeflow/schemas.py` from docs/03 — **do this before any agent**
- [ ] Download CBIC corpus → `corpus/` → GCS bucket (docs/05)
- [ ] Confirm synthetic notices exist in `data/sample_notices/` (provided) and mock ERP in `data/mock_erp/` (docs/04)

## Day 2 — Grounding + first two agents
- [ ] `scripts/build_datastore.py` → Vertex AI Search datastore; pass the 3 retrieval checks (docs/05)
- [ ] **Classifier** (Gemini Flash, multimodal): notice PDF → `ClassifiedNotice`. Test on all 3 sample types.
- [ ] **Researcher** (Gemini Flash + Vertex AI Search): `ClassifiedNotice` → `LegalContext` with real citations
- [ ] Draft the demo script (docs/08) — forces the build to serve the demo

## Day 3 — Drafter + MCP + orchestration → DEMO-ABLE ✅
- [ ] **MCP server** (`erp_server.py`) exposing `get_reconciliation_data` (docs/04)
- [ ] **Drafter** (Gemini Pro): `ClassifiedNotice` + `LegalContext` + MCP data → `ResponsePacket`
- [ ] **Orchestrator** (SequentialAgent) wires all three + human gate
- [ ] **CHECKPOINT:** full happy path runs end-to-end on DRC-01. If this works, you have a submission.
- [ ] Then widen: confirm ASMT-10 and ITC-mismatch also flow through

## Day 4 — Deploy, harden, test
- [ ] Deploy orchestrator to **Agent Engine** (docs/06 / adk.dev deploy)
- [ ] Confirm a PUBLIC testable link for judges
- [ ] Run all 3 notice types; fix retrieval/citation/format bugs
- [ ] Polish `adk web` UI, OR build the **demo cockpit** (React SPA, docs/09) — only if Day-3 checkpoint passed. The cockpit makes the multi-agent action cinematic for judges; `adk web` is the fallback.
- [ ] Clean architecture diagram for submission

## Day 5 — Submit
- [ ] Record 2-min demo video (English; subtitles if any non-English) — docs/08
- [ ] Devpost writeup: features, tech used, data sources (disclose CBIC public data), arch diagram, learnings
- [ ] Final repo pass — public, no secrets, testing instructions + creds if private
- [ ] **SUBMIT** on Devpost → confetti. Verify it shows as submitted, not draft.

## Stretch (only if ahead of schedule)
- Hindi output mode (CBIC Hindi corpus)
- 4th notice type
- Custom React frontend
- Side-by-side "single agent vs NoticeFlow pipeline" comparison for the demo (strong rubric point)

## Risk register
| Risk | Mitigation |
|------|-----------|
| Credit approval delay | Apply Day 1 first thing |
| ADK 2.0 API drift from training data | Check adk.dev before each component |
| Weak retrieval | Focused corpus + Day-2 retrieval checks before Drafter |
| MCP wiring eats time | Mock server is tiny + deterministic; static JSON lookup |
| Deadline ambiguity | Target June 5; verify on Devpost |
| Scope creep | The "NOT in MVP" list in docs/01 is binding |
