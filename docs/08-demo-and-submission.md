# 08 — Demo & Submission

## The 2-minute demo video (20% of score)
Hard cap 2:00 — only the first 2 minutes are evaluated. English (or English subtitles). Show the agents **acting**, not chatting. A polished video is free differentiation since most teams submit a raw console screen-recording.

### Script (target ~1:50)
1. **[0:00–0:18] The pain.** A real-looking GST notice on screen. VO: an SME owner receives this, doesn't understand it, has a tight deadline, and the CA quotes ₹15,000. Set stakes fast.
2. **[0:18–0:30] The drop.** Upload the notice into NoticeFlow. One action.
3. **[0:30–1:05] The agents working (CORE).** Make the orchestration visible:
   - Classifier: "DRC-01, Sec. 73, ₹X demanded, deadline DD/MM" — with the urgency tier (#2.6)
   - Researcher: pulls and **cites real CGST Act sections + a circular** from the datastore
   - MCP tool: fetches reconciliation figures
   - Drafter: assembles the reply
   (Optional 2-sec flash of the **execution-trace panel** (#3.9) — per-agent timing + grounding-chunk count — to make the multi-agent work tangible.)
4. **[1:05–1:20] The integrity beats (DIFFERENTIATORS — this is the moat).**
   - **Code-verified citations (#1.2):** the "✓ N/N citations verified against retrieved law" badge. VO: "every citation is checked *programmatically* against the law actually retrieved — fabricated law can't reach the reply."
   - **Self-correction (#1.1)** — the single highest-impact 15 seconds: show the Drafter↔Critic loop catch a bad draft and fix it on attempt 2. ⚠ The loop is flag-gated OFF on the deployed engine — **film this against the local cockpit with `NOTICEFLOW_ENABLE_REVIEW_LOOP=true`** using a notice engineered to reliably trigger REVISE→APPROVE; do NOT gamble on it happening live. (Fallback: show the eval report's loop metrics on screen instead.)
5. **[1:20–1:40] The payoff + terminal action.** The finished filing-ready packet (legal basis, citations, annexure, deadline flag, human approval gate), then **click "Download FORM DRC-06" (#2.4)** — the actual government reply PDF. VO: "It doesn't just advise — it produces the exact form you upload to the GST portal. What cost ₹15,000 and 3 days — done in 90 seconds, grounded in actual law."
6. **[1:40–1:50] Close.** One line on market (every Indian SME, recurring, B2B) + flash the architecture diagram and the **15/15 metrics** (#1.3).

### Rubric must-haves in the video
- Show the architecture diagram (`docs/submission/architecture.svg`)
- Explicitly name **ADK + Vertex Gemini + MCP + Vertex AI Search** (and A2A discoverability, #2.5, if it fits)
- Make the "pipeline beats single agent" point visible (ideally a quick side-by-side)
- Land at least one integrity differentiator on camera: the **verified-citations badge**, the **self-correction loop**, or the **downloadable form** (all three is ideal)

## Devpost writeup checklist
> Pre-written copy lives in `docs/submission/` — `devpost-writeup.md` (full prose),
> `devpost-fields.md` (field-by-field mapping), `testing-instructions.md`. Paste, don't re-write.

- [ ] **Track:** Build (Net-New Agents)
- [ ] **Region:** APAC
- [ ] Summary of features & functionality
- [ ] Technologies used (ADK, Vertex AI Gemini, Vertex AI Search, MCP, Agent Engine, A2A)
- [ ] **Differentiators called out:** code-verified citations (#1.2), self-correcting Drafter↔Critic loop (#1.1), terminal-action form PDF (#2.4), confidence gate (#3.8)
- [ ] **Quantified results** — paste the metrics table (15/15 classification, 100% reconciliation, 100% UNKNOWN handling, loop approved 100% @ avg 1.0 iters) from `docs/submission/eval_report.md` (#1.3)
- [ ] **Data sources** — disclose CBIC public GST law as a third-party data source; note notices are synthetic and ERP data is mocked
- [ ] **Architecture diagram** (required) — `docs/submission/architecture.svg`
- [ ] **A2A agent card** (optional flex) — `docs/submission/agent-card.json` (#2.5)
- [ ] Findings & learnings
- [ ] **Public code repo URL** (must be accessible to judges)
- [ ] **Testable link / demo / test build** + login creds if private
- [ ] 1–2 min demo video (English / subtitles)

## Compliance final check (from the rules)
- [ ] Net-new, built during contest period
- [ ] Gemini via Vertex AI (not AI Studio)
- [ ] ADK orchestration; multi-agent
- [ ] MCP external-tool connection
- [ ] Grounding/RAG (Vertex AI Search)
- [ ] Deployed on GCP (Agent Engine)
- [ ] B2B use case articulated
- [ ] Repo public; no secrets
- [ ] Third-party content/data disclosed
- [ ] Submission actually submitted (not draft) before deadline — verify date on Devpost

## Positioning for the three prizes (one project, three shots)
- **Grand Prize / Best-of-Theme (Build):** frame as "tax-compliance response automation" — universally legible B2B value.
- **APAC Regional:** frame the moat — real Indian GST law grounding no non-India team can replicate. Lead the writeup's business case with the India MSME market size.
