# NoticeFlow — Demo Video Shotlist (≤ 2:00)

> Hard cap **2:00** — only the first two minutes are judged. Must (a) name **Google ADK +
> Gemini on Vertex AI + MCP + Vertex AI Search**, (b) show the **architecture diagram**, (c) make
> the **multi-agent collaboration visible**. This shotlist is the *hero cut* that fits 2:00; optional
> beats (self-correction loop, urgency, confidence gate) are listed after — swap in only if you cut something.

## ⚠️ The #1 production reality: latency
A real run is **~60–90s** (3 Gemini calls + retrieval + MCP). **You cannot run live inside 2:00.**
- Record each beat **separately**, then **time-compress** the "agents working" stretch (speed-ramp 4–8×, or hard-cut between lane completions).
- Pre-load everything; never show a spinner for more than ~1s on screen.
- It's fine (and honest) to flash the **trace panel** real timings briefly to prove it's genuinely doing the work — then cut.

## Pre-production checklist
- [ ] Use the **deployed cockpit**: https://noticeflow-cockpit-205182179995.us-central1.run.app (incognito, clean window, 1920×1080, 100% zoom).
- [ ] **Spine notice = DRC-01** (cleanest, internally-consistent reply; citations Section 73 / 50 / Rule 142 all highlight in the PDF viewer).
- [ ] Pre-open the `architecture.svg` in a tab for the diagram beat.
- [ ] Do 2–3 dry runs; capture the best take of each beat.
- [ ] Citations to click on camera: **Section 73 (→ Act p.108)** or **Section 50 (→ p.82)**. **Avoid Rule 88D** (not in the 2021 Rules PDF → no highlight).
- [ ] Hindi beat: set the **हिंदी** toggle *first*, then click the sample (toggle is read at run time).
- [ ] Capture at 1080p/60; plan to add **captions/subtitles** (judges may watch muted).

## Hero cut — shot by shot

| # | Time | Dur | On screen | Action | VO (captioned) |
|---|------|-----|-----------|--------|----------------|
| 1 | 0:00–0:14 | 14s | A real-looking GST DRC-01 notice, deadline circled | Slow zoom on the deadline + demand amount | "Every month, Indian businesses get GST notices like this — cryptic, legalese, a hard deadline. Miss it and penalties stack up. A CA charges ₹15,000 to reply." |
| 2 | 0:14–0:22 | 8s | Cockpit upload zone | Click the **DRC-01** sample (one action) | "NoticeFlow does it in ninety seconds." |
| 3 | 0:22–0:52 | 30s | The three agent lanes filling in sequence (**time-compressed**) | Let Classifier → Researcher → Drafter complete; each lane shows its blurb + output | "Three specialized agents, orchestrated with **Google's ADK**. The **Classifier** reads the notice with **Gemini on Vertex AI**. The **Researcher** retrieves the governing law from real CBIC statutes via **Vertex AI Search**. The **Drafter** pulls the taxpayer's figures over an **MCP** tool and writes the reply." |
| 4 | 0:52–1:12 | 20s | Response packet → Legal Basis + **✓ N/N citations verified** badge → click a citation → **real CBIC PDF opens & highlights** | Click **Section 73** chip → "View in source PDF ↗" → PDF scrolls to p.108, passage highlighted | "Every citation is verified **in code** against the law actually retrieved — and you can open the real government PDF, highlighted at the exact passage. No hallucinated law." |
| 5 | 1:12–1:28 | 16s | Approve → **Download FORM DRC-06** → the generated PDF | Click **Approve**, then **Download FORM DRC-06**; flash the PDF | "Approve, and it generates the actual filing form — **DRC-06** — ready for the GST portal. Not advice. The document you submit." |
| 6 | 1:28–1:40 | 12s | Flip language → reply re-renders in Hindi/bilingual | Toggle **हिंदी** (or **Both**), re-run; show the Hindi reply + "भाषा" chip (**time-compress the re-run**) | "And for the millions who don't read legal English — the same reply, in Hindi." |
| 7 | 1:40–1:52 | 12s | Architecture diagram + metrics overlay | Show `architecture.svg`; overlay **15/15 classification · 100% reconciliation** + "Deployed on **Vertex AI Agent Engine**" | "Multi-agent, grounded, measured — 15 out of 15 on our eval set, deployed on Agent Engine." |
| 8 | 1:52–2:00 | 8s | Logo / tagline / URL | Static end card | "NoticeFlow — from notice to filing-ready reply, grounded in real law." |

**Mandatory-tech coverage:** ADK + Gemini/Vertex AI + Vertex AI Search + MCP all named in shot 3; Agent Engine in shot 7; diagram in shot 7. ✔

## Optional / extended beats (only if you cut something or do a 2:30 cut)
- **Self-correction loop (#1.1)** — the strongest "agentic" beat, but it's **flag-gated and runs only locally**. To film: run the **local** cockpit/pipeline with `NOTICEFLOW_ENABLE_REVIEW_LOOP=true` on a notice engineered to trigger REVISE→APPROVE, and show the Critic catching a bad draft and the redraft. *Don't gamble on it live; pre-record a known-good take, or instead show the eval report's "review approved 100% @ 1.0 iters" line.* High payoff if you can fit it — would swap for shot 6.
- **Deadline urgency** — pre-run shows green/amber/red tiers; a 3s cut of the **red "due in N days"** banner reinforces stakes (samples are date-relative, never "overdue").
- **Confidence gate / human approval** — the `PENDING_REVIEW` gate + "needs human review" is the maturity beat: "It drafts; a human always approves before filing."

## Recording tips
- OBS or QuickTime; hide bookmarks/extensions; enlarge cursor; add subtle click-highlights.
- Zoom into the citation chip → popover → PDF highlight (shot 4) — it's the unique trust moment; give it room.
- Keep motion purposeful: the **lane-by-lane reveal** is the only animation that matters.
- Subtitles burned in (English) — many judges watch muted.

## Final QA before export
- [ ] Runtime **≤ 2:00** (check the timeline, not your gut).
- [ ] ADK / Gemini-Vertex / MCP / Vertex AI Search all said **and** visible.
- [ ] Architecture diagram on screen.
- [ ] No "739 days overdue", no Rule-88D dead-highlight, no raw spinner > 1s.
- [ ] Citation → real PDF highlight is crisp and legible.
- [ ] Captions accurate; end card has the testable URL.
