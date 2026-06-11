# How to Test NoticeFlow (for judges)

> **Important:** NoticeFlow is deployed on **Vertex AI Agent Engine**. An Agent Engine
> resource (`projects/.../reasoningEngines/<id>`) is **not a public web URL** you can
> open in a browser — it is reached through the Vertex AI SDK/API. We therefore give
> you two ways to exercise the agent: a **hosted demo cockpit** (no setup), and a
> **direct call to the deployed engine** (for technical reviewers).

There is nothing to install for Option A. Pick whichever you prefer.

---

## What you're testing

A GST notice goes through three collaborating agents and comes out as a filing-ready
response packet. You should see, in order:

1. **Classifier** — identifies the notice type, governing sections, GSTIN, tax period,
   deadline, and (where present) the demanded amount.
2. **Researcher** — returns **citations from real CBIC GST law** (section/circular IDs
   + retrieved text) via Vertex AI Search.
3. **Drafter** — calls the **MCP** ERP tool for reconciliation figures, then produces a
   drafted reply that cites only the retrieved law and embeds those figures.
4. **Human gate** — the packet is marked `PENDING_REVIEW`; an Approve/Edit action
   finalizes it. NoticeFlow drafts; it never auto-files.

Use any of the three bundled sample notices (these match the mock ERP records, so the
reconciliation lookup succeeds end-to-end):

| Sample | Notice type | What to expect |
|--------|-------------|----------------|
| `data/sample_notices/asmt10_sec61.txt` | ASMT-10 (scrutiny, Sec. 61) | Cites Sec. 61 / Rule 99; ITC mismatch ₹2,000; reply in FORM ASMT-11 |
| `data/sample_notices/drc01_sec73.txt` | DRC-01 (demand, Sec. 73/74) | Cites Sec. 73 / Sec. 50; ITC mismatch ₹85,000 |
| `data/sample_notices/itc_mismatch_sec16.txt` | ITC mismatch / DRC-01C (Sec. 16) | Cites Sec. 16 / Rule 88D / **Circular 183**; ITC mismatch ₹45,000 |

---

## Option A — Hosted demo cockpit (recommended, no setup)

1. Open: **https://noticeflow-cockpit-205182179995.us-central1.run.app**
   - Your browser will show a sign-in prompt (this is a light password gate to stop
     bots from abusing our AI quota). The credentials are provided in the **Devpost
     submission's "Additional information" field** (kept out of this public repo on
     purpose). Username can be anything; only the password is checked.
2. On the landing screen, click one of the three **sample notice** buttons
   (ASMT-10 / DRC-01 / ITC-mismatch) — or paste your own notice text into the upload box.
3. Click **Run**.
4. Watch the three agent lanes fill in sequence:
   - **Classifier lane** → structured fields appear (type, sections, GSTIN, period,
     deadline).
   - **Researcher lane** → citation chips appear, each with a section/circular ID and a
     snippet of the actual law.
   - **Drafter lane** → the reconciliation annexure (GSTR-3B vs 2B, ITC mismatch amount)
     and the drafted reply body appear.
5. Review the final **response packet**: legal basis, cited sources, populated annexure,
   deadline flag, and the **PENDING_REVIEW** status with the Approve/Edit control.

Expected runtime: roughly 30–90 seconds end-to-end (it's calling Gemini 2.5 three times
plus retrieval and the tool).

---

## Option B — Call the deployed Agent Engine directly (technical reviewers)

This exercises the exact engine running in the cloud, including live Vertex AI Search
retrieval and the MCP tool call.

- **Deployed engine resource name:**
  `projects/205182179995/locations/us-central1/reasoningEngines/6398074104947146752`
- **Project:** `notice-flow` · **Region:** `us-central1`

> Direct invocation requires Google Cloud credentials with access to the project. If you
> would like temporary access to call the engine yourself, contact us at
> **[FILL IN — contact email]** and we will share scoped access.

From a clone of the public repo, with the project's `.env` configured and authenticated
(`gcloud auth application-default login`):

```bash
python -m venv .venv312 && source .venv312/bin/activate
pip install -e . "google-cloud-aiplatform[adk,agent_engines]"

# Smoke-test the deployed engine with the DRC-01 sample:
python scripts/deploy_agent_engine.py --test
```

You will see the streamed pipeline events: the **classifier** JSON, the **researcher**
citations, the **drafter**'s `get_reconciliation_data` tool call and its response, and
the drafted reply. To try the other two notice types, point the same `stream_query`
flow at `asmt10_sec61.txt` or `itc_mismatch_sec16.txt`.

> Note: the deployed engine emits the agents' raw structured output. The human-gate
> status (`PENDING_REVIEW`) and citation-merge presentation are applied by the cockpit
> layer (Option A) — that is the surface to use if you want to see the full reviewed
> packet exactly as an end user would.

---

## Running the cockpit yourself (optional)

If you'd rather run the cockpit locally from the public repo:

```bash
# backend (requires .env with a Vertex AI Search datastore configured)
uvicorn noticeflow.api:app --port 8000
# frontend
cd frontend && npm install && npm run dev
```

The backend **intentionally refuses to start without a configured Vertex AI Search
datastore** — this guarantees every citation you see is retrieved from real GST law,
never a fallback.

### Deploying it yourself (Cloud Run)

The cockpit ships as a single container (FastAPI serves the API **and** the built
React SPA). Build the frontend, then deploy from source:

```bash
cd frontend && npm install && npm run build && cd ..
gcloud run deploy noticeflow-cockpit --source . --region us-central1 \
  --allow-unauthenticated --memory 1Gi --max-instances 4 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<project>,GOOGLE_CLOUD_LOCATION=us-central1,\
GOOGLE_GENAI_USE_VERTEXAI=true,VERTEX_SEARCH_LOCATION=global,\
VERTEX_SEARCH_DATASTORE_ID=noticeflow-gst-corpus,NOTICEFLOW_REQUIRE_DATASTORE=true
```

The Cloud Run service account needs **Vertex AI User** + **Discovery Engine** access
(it calls Gemini and Vertex AI Search). `Dockerfile` + `.gcloudignore` are in the repo.

---

## A2A discoverability (optional)

NoticeFlow publishes a spec-compliant **A2A agent card** so other agents can
discover and call it. The static card is committed at
[`docs/submission/agent-card.json`](agent-card.json) (regenerate with
`python scripts/export_agent_card.py`).

To run NoticeFlow as a discoverable A2A agent (uses ADK's sanctioned `to_a2a()`
helper — the protocol is not hand-rolled):

```bash
pip install -e ".[a2a]"
uvicorn noticeflow.a2a_app:get_app --factory --host 0.0.0.0 --port 8001
# card is then served at the A2A well-known path on :8001
```

> ⚠ The A2A server is a demo/discoverability surface: in-memory stores, **no
> authentication**. Don't expose it publicly with sensitive data.
