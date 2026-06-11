# 10 — Enhancements (Tiered, Gated)

> **Read this whole preamble before building anything here.**
>
> NoticeFlow is already technically complete, compliant, and deployed. Every item below is
> *additive* and therefore also a *new failure surface* before a fixed deadline (June 12,
> 5:30 AM IST). These specs are a **menu with a recommended path**, NOT a to-do list to
> execute top to bottom.
>
> **Hard sequencing rule (revised 2026-06-05 — see "Plan revisions" below):**
> 1. **Spike first** (does ADK expose retrieved chunk text?), then build in this order:
>    **#1.2 verifier → #2.4 form PDF → #1.1 review loop → #1.3 eval** (fold #3.8 into #1.2).
>    Rationale: bank the deterministic wins (#1.2, #2.4) before the non-deterministic loop.
> 2. Re-deploy to Agent Engine and re-run the docs-09 / docs-08 demo path. Confirm all 3
>    notice types still work end-to-end, and that in-graph logic survived the deploy.
> 3. ONLY THEN consider remaining Tier 2. ONLY consider Tier 3 if Tier 2 is done and stable.
>    (#2.5 A2A is the first thing to cut.)
> 4. **Self-imposed freeze: June 9.** After June 9, NO new features. June 10–12 = demo
>    video + writeup + submission only. A feature that breaks the deploy the night before
>    is worse than a simpler system that works.
>
> Every item states its build-gate and a "SKIP IF" condition. Honor them.
>
> Rationale for the rankings: based on what actually wins ADK hackathons — validation/
> correction loops outperform linear pipelines; code-enforced anti-hallucination beats
> prompt-only; winners take a terminal action (not just draft) and quantify reliability.

---

## ⚠️ Plan revisions — 2026-06-05 (read before executing)

Three corrections after stress-testing this plan against the actual codebase, plus two
smaller calls. The sections below already incorporate them; this is the changelog.

1. **#1.2 is re-specified.** The original set-membership design (`retrieved_source_ids:
   set[str]`) does not match how our code works — our `source_id`s are LLM-generated
   strings, while retrieval gives document-level provenance + chunk *text*. The verifier
   must do **text-containment** (cited section/snippet appears in retrieved chunk text),
   not set membership.
2. **Two load-bearing unknowns gate everything — spike them first.** (a) Confirm ADK
   actually exposes grounding metadata / retrieved chunk text for `VertexAiSearchTool`.
   (b) The verifier must run **inside the ADK graph** (FunctionTool / after-agent
   callback), not as a `run_pipeline`/`api.py` post-step — otherwise the loop can't use
   it and it won't exist in the deployed engine (the engine emits raw agent output;
   wrapper logic does not deploy).
3. **Revised build order:** `#1.2 → SPIKE → #2.4 → #1.1 → #1.3`. The DRC-06/ASMT-11 PDF
   (#2.4) is deterministic and low-risk — bank it *before* betting a night on the
   non-deterministic loop. #3.8 (confidence-gated escalation) moves into Tier 1 (≈10
   lines). #2.5 (A2A) is the first thing to cut.

Budget a **half-day for redeploy + re-verify**, not 15 minutes — our deploys take 5–15
min each and have failed repeatedly. Credit burn roughly doubles with the loop/eval
(~₹500/day) — immaterial against the remaining credit.

---

## TIER 1 — Build these (highest score-per-day)

These three are mutually reinforcing: the loop needs the verifier; the eval harness proves
the loop works. Together they convert NoticeFlow from "linear drafting pipeline" into
"self-verifying, measured multi-agent system."

### 1.2 — Programmatic citation verification  ⭐ BUILD FIRST
**Why:** The compliance audit's one real caveat was that citations are prompt-enforced, not
code-enforced — a fabricated `source_id` could slip through. This makes anti-hallucination a
*code guarantee*, which is a named winning technique. Also yields a hard metric for the writeup.

**Build-gate:** none — do this first, it's foundational to #1.1.
**SKIP IF:** never skip; this is the cheapest highest-integrity win (~half day, **but**
budget a full day — the text-matching + the spike below are more than the original estimate).

**⚠️ SPIKE FIRST (≈30 min, gates the entire tier):** before writing the verifier, confirm
in our actual pipeline that ADK exposes the **retrieved chunk text** for
`VertexAiSearchTool` — i.e. `event.grounding_metadata` with `grounding_chunks[]` carrying
`retrieved_context.text` (and `.title`/`.uri`). Add a temporary print in `research_notice`'s
event loop and run one sample notice. **If the retrieved text is not accessible, stop and
rethink** — without it the verifier can only check the LLM's own snippet against the LLM's
own citation, which is circular and proves nothing. Verify the exact field names on
adk.dev / the genai types; do not trust this doc's field names blindly.

**Why set-membership does NOT work here:** our `Citation.source_id`s (e.g. `"CGST Act 2017,
Section 73"`) are **LLM-generated strings**, while Vertex AI Search grounding gives
**document-level** provenance (which PDF) plus **chunk text** — there is no `source_id`
set to match against. The defensible check is **text-containment**.

**Design (text-containment, not set membership):**
- In the Researcher, capture the **concatenated retrieved chunk text** (and per-chunk
  doc title/uri) from `grounding_metadata` into state alongside `LegalContext` — e.g.
  `retrieved_evidence: list[{title, uri, text}]`. This requires reading the **events**
  (we already iterate them in `research_notice`); the in-pipeline path needs the same.
- Add a pure-Python verifier (no LLM) — `src/noticeflow/verify/citations.py`:
  ```python
  def verify_citations(packet: ResponsePacket,
                       retrieved_evidence: list[RetrievedChunk]) -> CitationVerification:
      """Each Citation is 'verified' iff its normalized section/rule id (or its snippet)
      is found within the retrieved chunk text. Document-level match is the floor;
      section/snippet text-containment is the real check."""
  ```
- Output a small result object:
  ```python
  class CitationVerification(BaseModel):
      total_citations: int
      verified: int
      unverified: list[str]          # citations with no text-containment backing
      passed: bool                   # unverified == []
  ```
- Behavior: if `unverified` is non-empty, either (a) drop those citations from the packet, or
  (b) flag them and force a redraft (this is where #1.1 plugs in). For MVP-of-this-feature,
  dropping + logging is fine.
- Surface `CitationVerification` in the cockpit (docs/09) as a small "✓ N/N citations verified
  against retrieved law" badge — high-trust demo moment.

**⚠️ Must run inside the ADK graph, not the wrapper.** If the verifier is to feed the
Reviewer (#1.1) *and* exist in the deployed engine, wire it as an ADK **FunctionTool** the
Reviewer calls, or an **after-agent callback** — NOT as a `run_pipeline`/`api.py`
post-step. Recall: the deployed Agent Engine emits raw agent output; anything living only
in the Python wrapper runs in the cockpit but is absent from what judges test on the engine.

**Contract notes:** normalize section/rule references before the containment test
(e.g. "Section 73" vs "Sec. 73" vs "CGST Act 2017, Section 73" vs "73(1)") so
legitimately-retrieved citations aren't falsely rejected. Also normalize whitespace/case in
the retrieved text. Test the normalizer against all 3 sample notices before trusting the pass rate.

**Demo/writeup payoff:** "100% of emitted citations are programmatically verified against
retrieved source documents — zero unverified citations across the test set."

---

### 1.1 — Reviewer/Critic agent + correction loop  ⭐ THE FLAGSHIP ADD
**Why:** Validation loops are the single most-cited winning pattern. Converts the pipeline
from "draft and hope" to "draft, self-check, correct." Strong Technical + Innovation signal.

**Build-gate:** #1.2 must exist (the reviewer uses the citation verifier).
**SKIP IF:** you cannot get it stable by June 8 — a flaky loop is worse than none. Prefer a
deterministic single-pass verifier (#1.2 alone) over a shaky loop.

**Design:**
- Add a **Reviewer** as an `LlmAgent` (Gemini Pro) that takes the Drafter's `ResponsePacket`
  + `LegalContext` + `ReconciliationData` and returns a structured critique:
  ```python
  class ReviewResult(BaseModel):
      citations_ok: bool          # from the programmatic verifier (#1.2), not the LLM
      figures_reconcile: bool     # annexure math checks out vs ReconciliationData
      deadline_correct: bool
      addresses_all_points: bool  # reply responds to every allegation in the notice
      issues: list[str]           # concrete problems found
      verdict: str                # "APPROVE" | "REVISE"
  ```
- **Critical design point:** `citations_ok` and `figures_reconcile` should come from
  **deterministic code** (the #1.2 verifier + a simple arithmetic check), NOT the LLM's
  opinion. The LLM judges only the soft criteria (completeness, coherence). This keeps the
  loop trustworthy and prevents two LLMs hallucinating agreement.
- Wrap Drafter→Reviewer in an ADK **`LoopAgent`** (verify current API on adk.dev): loop while
  `verdict == "REVISE"`, **max 2–3 iterations**, then escalate to the human gate regardless
  (never infinite-loop; cap is mandatory). Pass the Reviewer's `issues` back into the Drafter's
  next attempt as context.
- New topology:
  ```
  Classifier → Researcher → [ LoopAgent: Drafter ⇄ Reviewer (max 3) ] → Human gate
  ```

**Contract notes:**
- The loop MUST terminate. Hard-cap iterations; on cap-without-approval, mark the packet
  `reviewer_status="NEEDS_HUMAN"` with the outstanding `issues` attached.
- Record iteration count + what changed between attempts — excellent demo material ("watch
  it catch its own missing citation and fix it on attempt 2").

**⚠️ Risks the original spec skipped:**
- **Wall-clock cost on camera.** Drafter (Pro) ⇄ Reviewer over 3 iterations = up to **6
  Gemini Pro calls per notice**, each wrapped in our 5-attempt 429 backoff — that can be
  3–5 minutes for one notice, fatal for a ≤2:00 video. Mitigate: **cap at 2 iterations**,
  use **Flash for the Reviewer's soft criteria** (the hard checks are deterministic
  anyway), and be prepared to time-compress the recording.
- **Reproducible self-correction.** "Fixes it on attempt 2" will NOT happen reliably with
  non-deterministic LLMs. Engineer/seed a specific notice that dependably triggers
  REVISE→APPROVE for the video; don't gamble on it happening live.
- **`citations_ok` comes from the in-graph verifier (#1.2), not the LLM** — see #1.2's
  "must run inside the ADK graph" note; the loop depends on it being callable from within
  the graph.

**ADK note:** verify `LoopAgent` / loop-termination semantics at https://adk.dev/workflows/
— and recall the repo emits a SequentialAgent deprecation warning; check whether the current
recommended primitive is `Workflow`-based. Use whatever the live docs say is current; don't
guess from training data. **But do NOT undertake a full SequentialAgent→Workflow migration
before the June 9 freeze** unless `LoopAgent` genuinely won't compose with the current
deployed `SequentialAgent` — a rewrite re-opens every deploy bug already fixed. Add the loop
with minimal disturbance to what is deployed and working.

**Demo/writeup payoff:** the highest-impact 15 seconds you can show — the system detecting its
own error and self-correcting. This is what separates "LLM wrapper" from "agentic system" in a
judge's mind.

---

### 1.3 — Quantified eval harness
**Why:** Winners quantify ("95% success", "sub-10s"). You currently have no numbers. This
produces real metrics AND a regression safety net for the loop work above.

**Build-gate:** #1.1 + #1.2 built (so the metrics reflect the final system).
**SKIP IF:** time-pressured — but even a *partial* harness (classification accuracy alone) is
worth it for the writeup. Don't skip entirely.

**Design:**
- Expand `data/sample_notices/` to ~15–20 synthetic notices across the 3 types (vary amounts,
  sections, deadlines, edge cases like missing GSTIN or an unsupported type that should return
  `UNKNOWN`). Keep them clearly synthetic.
- `scripts/eval.py` runs every notice through the pipeline and reports:
  - **Classification accuracy** (predicted type vs labeled type)
  - **Citation verification pass rate** (from #1.2)
  - **Annexure reconciliation pass rate**
  - **`UNKNOWN` handling** (does it correctly refuse unsupported types?)
  - **End-to-end latency** (median, p90)
  - **Loop behavior** (avg iterations, % needing human escalation)
- Output a small `eval_report.md` / JSON committed to the repo (`docs/submission/`).
- Label each notice with ground truth in a manifest (`data/sample_notices/manifest.json`).

**⚠️ Cost/time:** with the loop live, a full run ≈ 20 notices × up to 6 Pro calls = ~120
Pro calls **per eval run** — slow and real money across iterations. Keep a **3-notice fast
subset** for iteration; run the full 15–20 **once** for the writeup table. Your p90 latency
will look high *because of* the loop — own that framing ("self-correction trades latency for
correctness"), don't bury it.

**Demo/writeup payoff:** a results table in the Devpost writeup. Concrete, credible, rare among
hackathon entries.

---

## TIER 2 — Strong, pick by appetite (only after Tier 1 stable + redeployed)

### 2.4 — Close the loop: generate the real filing form (DRC-06 / ASMT-11) as PDF
**Why:** Winners take a *terminal action*, not just produce text. Moving from "filing-ready
draft" to "the actual government reply form, filled and downloadable" is a decisive business-case
and demo upgrade.

**⭐ PROMOTED (2026-06-05):** build this **right after #1.2, before #1.1**. It is
**deterministic — no LLM, no loop flakiness** — so it is a lower-risk flagship than the loop
and arguably a higher demo payoff. Bank this terminal-action upgrade before gambling a night
on loop stability. Form mappings confirmed correct: DRC-01→DRC-06, ASMT-10→ASMT-11,
ITC-mismatch (DRC-01C)→DRC-01C Part B.

**Build-gate:** #1.2 done (it's independent of #1.1; do not wait for the loop).
**SKIP IF:** not green by June 9.

**Design:**
- Map each notice type to its reply form: DRC-01 → **DRC-06**, ASMT-10 → **ASMT-11**, ITC
  mismatch (DRC-01C) → **DRC-01C Part B**.
- Templating task (not new agent logic): render `ResponsePacket` into a properly-formatted PDF
  matching the public form layout. Use a PDF lib; keep it a deterministic post-step after the
  human gate.
- Forms are public government formats — replicating the layout for a *reply you're filing* is
  legitimate; mark generated PDFs as system-produced drafts for review.
- Cockpit: add a "Download filing-ready DRC-06" button on the approved packet.

**Payoff:** "NoticeFlow doesn't just advise — it produces the exact form you upload to the GST
portal." Visually decisive in the video.

---

### 2.5 — A2A interoperability (sophistication signal)
**Why:** A2A shows up in winner after winner even when optional; signals enterprise-readiness
and is the bridge toward Track-3 framing.

**Build-gate:** Tier 1 done; you have a clear half-to-full day; comfortable with fiddly wiring.
**SKIP IF:** anything in Tier 1 is shaky, or it's past June 8. A2A wiring is the most likely
Tier-2 item to eat time. This is explicitly optional for Track 1.

**⚠️ DECISION (2026-06-05): this is the first thing to cut.** Given the 4-day window and the
deterministic wins available (#2.4) plus the flagship loop (#1.1), A2A's risk-adjusted value
is lowest. Do not start it unless #1.1, #1.2, #1.3, and #2.4 are all done and stable.

**Design (pick the lighter option):**
- **Option A (lighter):** expose the NoticeFlow orchestrator as an **A2A-discoverable agent**
  with a published agent card describing the intents it accepts/exposes. Demonstrates
  discoverability without restructuring internals.
- **Option B (heavier):** split the ERP/accounting connection into a separate **"Accounting
  Agent"** that the Drafter reaches via A2A instead of (or in addition to) the MCP tool —
  showing true agent-to-agent coordination.
- Verify current A2A support + agent-card format at https://adk.dev/ (and the A2A protocol
  docs). Do NOT hand-roll the protocol.

**Payoff:** "A2A-native — discoverable and composable within an enterprise agent ecosystem."
Also pre-positions a future Track-3 entry.

---

### 2.6 — Deadline-aware autonomy / monitoring
**Why:** Adds an "acts over time" dimension; cheap.

**Build-gate:** Tier 1 done.
**SKIP IF:** low on time — it's a nice-to-have, not a differentiator on its own.

**Design:**
- Compute urgency tiers from `response_deadline` (e.g. >14 days / 7–14 / <7 / overdue).
- A lightweight monitor behavior that, given a set of pending notices, surfaces the most urgent
  and (mock) emits a reminder/escalation as the deadline nears. Keep it mocked — no real
  calendar/email integration needed for the demo.
- Cockpit: an urgency badge + a "next action by DD/MM" line on each packet.

**Payoff:** reinforces the real-world stakes; small effort.

---

## TIER 3 — Only if flush with time (post-Tier-2, pre-June-9)

### 3.7 — Hindi output mode  ✅ DONE (2026-06-07)
**Built as:** an additive `localize_packet` step (`src/noticeflow/localize.py`, Gemini Flash) that
translates only the reply prose into **Hindi or bilingual** (3-way cockpit toggle). English stays
canonical (form PDF + citation verifier read it). Spike confirmed legal-Hindi quality first; the
statutory form remains English (portal-correct; reportlab can't shape Devanagari). No Hindi corpus
(kept the authoritative English CBIC datastore). Deployed engine untouched.

**Why:** Strengthens the APAC moat; CBIC publishes Hindi law versions.
**Build-gate:** Tier 1+2 done, comfortably before June 9.
**SKIP IF:** any earlier tier unstable. This is the original stretch goal — genuinely optional.
**Design:** add a language toggle; Drafter produces the reply in Hindi (or bilingual). Optionally
a separate Hindi-tagged datastore or Hindi law docs in the corpus. Verify Gemini handles the
legal-Hindi register acceptably before committing — test before relying on it in the demo.
**Payoff:** vernacular accessibility — a clean APAC-regional differentiator.

### 3.8 — Confidence-gated human escalation  ⬆ PROMOTED TO TIER 1 (2026-06-05)
**Why:** Demonstrates good judgment about the *limits* of autonomy — judges respect this.
It's ~10 lines on `ClassifiedNotice.confidence` (we already short-circuit `UNKNOWN` in
`orchestrator.py` / `api.py`), so the maturity signal is near-free. Do it during Tier 1.
**Build-gate:** none — fold into the #1.2/#1.1 work.
**SKIP IF:** nothing — it's the cheapest maturity signal in the doc.
**Design:** when `ClassifiedNotice.confidence` is below a threshold (or type == `UNKNOWN`),
short-circuit to an explicit "needs human review — low confidence" state instead of proceeding.
Surface clearly in the cockpit.
**Payoff:** "knows when not to act" — a maturity signal, near-zero cost.

### 3.9 — Observability trace in the cockpit
**Why:** Visual sophistication; low logic risk.
**Build-gate:** Tier 1 done.
**SKIP IF:** time-pressured; it's polish.
**Design:** surface the ADK/Cloud Trace reasoning trace (or the per-agent timing already
captured by the eval harness) as an expandable panel in the cockpit. Read-only display of data
you already have — no new agent logic.
**Payoff:** makes the multi-agent orchestration tangible on screen.

---

## Recommended path (REVISED 2026-06-05 — if you do nothing else, do this)
0. **SPIKE (≈30 min)** — confirm ADK exposes retrieved chunk text for `VertexAiSearchTool`
   in our pipeline. This gates everything; if it fails, re-plan before building.
1. **#1.2 citation verifier** (≈1 day) — text-containment, wired **inside the graph**.
   Closes the audit's one real gap, code-enforced. Fold in **#3.8** (confidence gate) here.
2. **#2.4 real form PDF** (≈1 day) — deterministic terminal-action upgrade; bank it before
   the loop because it can't go flaky.
3. **#1.1 reviewer + loop** (≈1 day) — the flagship "self-correcting" differentiator. Cap
   at 2 iterations; Flash reviewer for soft criteria; engineer a reproducible REVISE→APPROVE
   case for the video.
4. **#1.3 eval harness** (≈1 day, can overlap) — turns the above into hard numbers (fast
   3-notice subset to iterate; full run once for the table).
5. **Re-deploy + re-verify all 3 notice types** — budget a **half-day**, not 15 min. Confirm
   the in-graph verifier and loop survive the deploy (wrapper-only logic won't).
6. **Freeze June 9.** Video + writeup + submit, June 10–12.

This is ~4 days of build against a 4-day window — **near-zero slack**. If anything slips,
the safe cut order is: drop #1.1's loop down to **#1.2's single-pass verifier + #2.4 PDF**
(both deterministic, both strong) and skip the loop rather than ship a flaky one. Each item
still standing produces concrete ammunition (a verified-citations badge, a downloadable
DRC-06, a metrics table) — that's what moves you from "compliant entry" toward "winning
entry" without betting the deploy on untested scope.

## Update these when you add features
- `docs/02-architecture.md` — new topology (Reviewer + LoopAgent)
- `docs/03-data-contracts.md` — `ReviewResult`, `CitationVerification`
- `docs/09-ui-ux.md` — verified-citations badge, self-correction display, (opt) form-download
- `docs/08-demo-and-submission.md` — feature the loop + metrics in the script and writeup
- `CLAUDE.md` doc index — add this doc