# 09 — UI/UX: The Demo Cockpit

> **Purpose:** make the multi-agent action *visible and cinematic* for judges. Demo is 20% of the score, and the rubric rewards showing that agent collaboration beats a single agent. This UI is a **demo amplifier, not a dependency.**
>
> **Build gate:** Build this ONLY after the Day-3 end-to-end checkpoint passes (agents work via `adk web`). If Day 3 slips, fall back to dressing up `adk web` (Level 1) and still submit. Do NOT build this before the agents work.
>
> **Scope discipline:** This is a THIN presentation layer. It reads the same `ResponsePacket` / `ClassifiedNotice` / `LegalContext` schemas (docs/03) the agents already produce. It contains NO business logic, NO new agent behavior, NO auth, NO persistence. If you find yourself adding logic here, stop.

## Design intent (3 jobs, all tied to the rubric)
1. **Make sequential collaboration legible** — the judge watches Classifier → Researcher → Drafter light up in turn, each revealing its real structured output. (Technical + Innovation score.)
2. **End on a credible artifact** — the finished response packet rendered as a real document: legal basis, clickable citations to actual GST law, the reconciliation annexure as a clean table, a prominent deadline flag. (Business case + Demo score.)
3. **Prove pipeline > single-shot** — an optional toggle that runs the same notice through one naive prompt and shows it mis-citing / mis-typing, side by side. (The single most persuasive 10 seconds in the video.)

## Tech
- **React SPA** (single file is fine). Binds naturally to the agent JSON, makes the lane animation trivial via state, and fits the `adk web` / Agent Engine frontend model.
- Styling: minimal, clean, "fintech-credible" — not flashy. White/neutral base, one accent color, generous whitespace, real typography. Judges trust restraint over gradients.
- Talks to the deployed orchestrator (Agent Engine endpoint) — one call that streams or returns the three agents' outputs + final packet. If streaming is hard in the time, poll/step through stages; the *appearance* of sequential progress is what matters.
- **Fallback (if React stalls):** a single static HTML+vanilla-JS page with the same three-lane layout, fed by the JSON. Lower polish, same story. Don't spend more than the budgeted day either way.

## Screen layout (single page, top to bottom)

```
┌──────────────────────────────────────────────────────────────┐
│  NoticeFlow            [ ⚙ single-shot comparison: OFF/ON ]    │  header
├──────────────────────────────────────────────────────────────┤
│                                                                │
│   ┌────────────────────────────────────────────────────┐     │
│   │   ⬆  Drop a GST notice PDF  (or pick a sample ▾)     │     │  upload zone
│   │       [ DRC-01 ]  [ ASMT-10 ]  [ ITC mismatch ]      │     │  (sample buttons
│   └────────────────────────────────────────────────────┘     │   = demo-safe)
│                                                                │
│   PIPELINE                                                     │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐     │
│   │ ① CLASSIFIER │ → │ ② RESEARCHER │ → │ ③ DRAFTER     │     │  three agent
│   │   ◐ running… │   │   ○ waiting  │   │   ○ waiting   │     │  "lanes"
│   │              │   │              │   │              │     │
│   │ type: DRC-01 │   │ Sec 73 ✓     │   │ packet ✓      │     │  fill w/ real
│   │ Sec 73       │   │ Circ 31/2018 │   │              │     │  structured
│   │ ₹1,05,900    │   │ + 2 more     │   │              │     │  output as each
│   │ due 11/04 ⚠  │   │              │   │              │     │  completes
│   └──────────────┘   └──────────────┘   └──────────────┘     │
│                                                                │
│   RESPONSE PACKET                                  [ Approve ] │  the payoff
│   ┌────────────────────────────────────────────────────┐     │
│   │  Re: SCN ZD2403240001234 · GSTIN 24ABCDE1234F1Z5    │     │
│   │  ⚠ Response due 11/04/2024 (urgent)                  │     │
│   │                                                      │     │
│   │  Legal basis: …prose with inline [Sec 73] [Circ…]   │     │  citations are
│   │  Reply: …point-by-point, filing-ready…              │     │  chips → click
│   │                                                      │     │  opens the real
│   │  Annexure (reconciliation):                          │     │  retrieved snippet
│   │  ┌────────────────────────┬───────────┐             │     │
│   │  │ GSTR-3B ITC claimed    │ 9,05,000  │             │     │  annexure = clean
│   │  │ GSTR-2B ITC available  │ 8,20,000  │             │     │  table from
│   │  │ Mismatch               │   85,000  │             │     │  ReconciliationData
│   │  └────────────────────────┴───────────┘             │     │
│   └────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

## Component breakdown
| Component | Binds to | Behavior |
|-----------|----------|----------|
| **UploadZone** | — | Drag-drop PDF + 3 sample buttons. Sample buttons load the `data/sample_notices/` files → demo is deterministic and fast. |
| **AgentLane ×3** | `ClassifiedNotice`, `LegalContext`, `ResponsePacket` | Three states: `waiting` (grey ○) → `running` (pulsing ◐) → `done` (green ✓). On done, reveals that agent's real output fields. Sequential reveal is the core animation. |
| **PacketView** | `ResponsePacket` | Renders the packet as a document. `deadline_urgent` → red flag. `citations` → clickable chips. `annexure` → table. |
| **CitationChip** | `Citation` | Click → popover with `source_id` + retrieved `snippet`. Proves the law is REAL, not hallucinated — high-trust moment. |
| **ApproveButton** | sets `reviewer_status` | The human gate. One click → "APPROVED". Visible, simple. |
| **ComparisonToggle** (stretch) | — | ON → also shows a single naive-prompt result alongside, typically wrong on type/citation. |

## Interaction flow (matches the demo script beats, docs/08)
1. Page loads clean. Judge sees the upload zone + dormant pipeline. *(demo beat 0:00–0:20 over a notice)*
2. Click a sample notice (or drop PDF). *(beat 0:20–0:35 "the drop")*
3. Lane ① pulses → fills with classification. Lane ② pulses → fills with citations. Lane ③ pulses → fills. *(beat 0:35–1:20 — the core; sequential reveal makes collaboration legible)*
4. Packet renders below; click a citation chip to reveal the real law snippet; the annexure table is populated from MCP data. *(beat 1:20–1:40 "the payoff")*
5. Click **Approve**. *(human gate)*
6. (Optional) flip the comparison toggle to show single-shot fumbling. *(strongest 10s)*

## Post-MVP cockpit additions (built in the enhancements phase)
- **Verified-citations badge** (#1.2) — "✓ N/N citations verified against retrieved law"; warns + lists dropped citations when any fail.
- **Human-escalation banner** (#3.8) — amber "needs human review" banner when a KNOWN notice classifies below the confidence threshold (`reviewer_status=NEEDS_HUMAN`, `escalation_reason`).
- **Tiered deadline urgency** (#2.6) — one banner colored by tier (overdue/critical = red, soon = amber, on-schedule = green) with a "Next action by DD Mon YYYY — N days remaining" line. Mirrors `src/noticeflow/deadlines.py`; a mocked multi-notice monitor is demonstrated by `scripts/monitor.py`.
- **Download filing form** (#2.4) — "⬇ Download FORM DRC-06/ASMT-11/DRC-01C" once the packet is approved.
- **Reply language** (#3.7) — a 3-way toggle (English / हिंदी / Both) in the upload zone. The reply prose renders in the chosen language (browser shapes Devanagari natively) with a "भाषा/Language" chip on the packet; citations/figures are unchanged and the form download stays English (portal-correct).

## Visual/UX rules for credibility
- Currency in Indian format (₹1,05,900) — small detail, big trust signal for an APAC judge.
- Show the deadline flag in red when urgent — conveys the real-world stakes instantly.
- Don't animate gratuitously; the lane sequence is the only motion that matters.
- Keep one screen, no scrolling during the core pipeline reveal if possible (judges watch a 2-min video; scrolling reads as clutter).
- Citation chips MUST resolve to real retrieved text — never a fabricated snippet. This is the integrity of the whole demo.

## Day-4 build checklist (time-boxed to ~1 day)
- [ ] Scaffold single React page; neutral fintech styling
- [ ] UploadZone with 3 sample-notice buttons (deterministic demo)
- [ ] Wire one call to the deployed orchestrator; map response → the 3 schema objects
- [ ] AgentLane component with waiting/running/done states + sequential reveal
- [ ] PacketView: prose + citation chips + annexure table + deadline flag
- [ ] CitationChip popover showing real snippet
- [ ] Approve button → status change
- [ ] (Stretch, only if ahead) ComparisonToggle
- [ ] Dry-run all 3 sample notices on the UI before recording

## Explicit non-goals (do not build)
- ❌ Auth / login / users
- ❌ Notice history / dashboard / list views
- ❌ Real file persistence or a backend DB
- ❌ Editing the packet inline (Approve is enough for MVP)
- ❌ Responsive/mobile polish (it's filmed on desktop)
- ❌ Any agent logic in the frontend — presentation only
