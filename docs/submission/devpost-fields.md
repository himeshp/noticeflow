# Devpost Submission Cheat-Sheet

Literal, field-by-field guide for the Google for Startups AI Agents Challenge entry.
Work top to bottom. `[FILL IN]` = something only you (the human) can provide.

> **Deadline:** June 12, 2026, 5:30 AM IST. Submit (not draft) before this.

---

## Field-by-field

| Devpost field | What to enter |
|---------------|---------------|
| **Project name** | `NoticeFlow` |
| **Tagline / elevator pitch** | "Turns a cryptic Indian GST notice into a filing-ready, legally-grounded response packet — with a human approval gate." |
| **Track** | **Build (Net-New Agents)** |
| **Region** | **APAC** |
| **Inspiration** | Paste the *Inspiration* section from `devpost-writeup.md` |
| **What it does** | Paste *What it does* |
| **How we built it** | Paste *How we built it* |
| **Data sources / third-party content** | Paste *Data sources & disclosure* (this satisfies the third-party-data disclosure rule — do not skip it) |
| **Challenges / what we learned** | Paste *Challenges & learnings* |
| **What's next** | Paste *What's next* |
| **Technologies used / tags** | `Google ADK`, `Vertex AI`, `Gemini 2.5`, `Vertex AI Search`, `MCP`, `Agent Engine`, `Python`, `FastAPI`, `React` |
| **Public code repository URL** | **[FILL IN — public GitHub repo URL]** (confirm it is Public, not Private) |
| **Demo video URL** | **[FILL IN — YouTube/Vimeo link, ≤ 2:00, English or subtitled]** |
| **Testable link / try-it-out URL** | **https://noticeflow-cockpit-205182179995.us-central1.run.app** (Cloud Run; the Agent Engine resource is NOT a public URL — link the cockpit; see `testing-instructions.md`) |
| **Testing instructions / login creds** | Paste/link `testing-instructions.md`; no login required (open demo). Fill remaining `[FILL IN]` markers (contact email) |
| **Architecture diagram** | Upload `docs/submission/architecture.svg` (also embedded in the writeup as Mermaid) |

---

## Attach / upload checklist

- [ ] **Architecture diagram** uploaded (`docs/submission/architecture.svg`) — required.
- [ ] **Demo video** linked — **[FILL IN]**, confirmed ≤ 2:00 and English/subtitled.
- [ ] **Public repo URL** added — **[FILL IN]**, confirmed **Public**.
- [x] **Testable link** added — https://noticeflow-cockpit-205182179995.us-central1.run.app (Cloud Run, public).
- [ ] Writeup sections pasted from `devpost-writeup.md`.
- [ ] Data-source disclosure present in the description.

---

## Pre-submit compliance check (from the rules)

- [ ] Net-new, built during the contest period — yes (git history starts in-contest).
- [ ] Gemini via Vertex AI, not AI Studio — yes (enforced in `config.py`).
- [ ] ADK orchestration, multi-agent — yes (`SequentialAgent` + 3 `LlmAgent`s).
- [ ] MCP external-tool connection — yes (`get_reconciliation_data`).
- [ ] Grounding/RAG (Vertex AI Search) — yes (datastore + `VertexAiSearchTool`).
- [ ] Deployed on GCP (Agent Engine) — yes (engine `…/reasoningEngines/6398074104947146752`).
- [ ] B2B use case articulated — yes.
- [ ] Repo public; no secrets committed — **[FILL IN: confirm repo is Public]** (no secrets verified in repo).
- [ ] Third-party content/data disclosed — yes (CBIC corpus in the writeup).
- [ ] $500 credits applied; no out-of-pocket spend — **[FILL IN: confirm billing draws the challenge credit]**.

---

## Final step — DO NOT skip

1. Click **Submit** on Devpost (saving a draft is **not** submitting).
2. Reload the project page and confirm it shows **"Submitted"** (not "Draft" / "Saved").
3. Confirm the submission timestamp is before **June 12, 2026, 5:30 AM IST**.
4. Open the public repo URL and the testable link in a **logged-out/incognito** window
   to confirm a judge can actually reach them.
