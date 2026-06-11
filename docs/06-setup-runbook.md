# 06 — Setup Runbook (Day 1)

> Commands are indicative — verify current ADK CLI / gcloud syntax against https://adk.dev/ and Google Cloud docs, as flags change. Do NOT paste real keys anywhere committed.

## 0. Prereqs
- A Google account with the **$500 challenge credits** applied (request via the Contest Site; approval can take up to ~72h — do this FIRST).
- A GCP project (e.g. `noticeflow-prod`), Organization = "No organization".
- **Develop in Cloud Shell** to avoid local macOS `_dyld_start` / Node issues.

## 1. GCP project + APIs
```bash
gcloud config set project YOUR_PROJECT_ID

# Enable required services
gcloud services enable \
  aiplatform.googleapis.com \
  discoveryengine.googleapis.com \
  run.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com
```
> `aiplatform` = Vertex AI (Gemini + Agent Engine). `discoveryengine` = Vertex AI Search.
> Region: pick one supporting Gemini + Vertex AI Search (e.g. `us-central1`). Set it in `config.py`.

## 2. Python env (Cloud Shell)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install google-adk
# plus: pydantic, the Vertex AI SDK, MCP libs — pin versions in pyproject.toml
```

## 3. Auth (Vertex, NOT AI Studio)
```bash
gcloud auth application-default login
# Vertex uses ADC / service account — NEVER an AI Studio API key.
```
Set env (see `.env.example`):
```
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=us-central1
```
> `GOOGLE_GENAI_USE_VERTEXAI=true` is what routes ADK/Gemini through Vertex instead of AI Studio. Confirm the exact env var name in current ADK docs.

## 4. Smoke test — hello agent on Vertex Gemini
Create a minimal `LlmAgent` (model `gemini-flash-latest` or current pinned ID), run it via `adk web` or CLI, confirm it responds **through Vertex** (check it's billing to the project, not erroring on a missing AI Studio key).

## 5. Corpus → Cloud Storage
```bash
gsutil mb -l us-central1 gs://YOUR_BUCKET-gst-corpus
# download CBIC PDFs into corpus/ (see docs/05), then:
gsutil -m cp corpus/*.pdf gs://YOUR_BUCKET-gst-corpus/
```

## 6. Vertex AI Search datastore
Run `scripts/build_datastore.py` (you'll write it) to create a data store over the bucket. Verify with the 3 retrieval checks in docs/05.

## 7. Repo hygiene
- `.gitignore`: `.env`, `.venv/`, `corpus/` (if large), `__pycache__/`, any creds.
- `.env.example` committed with placeholder values only.
- Repo PUBLIC before submission (required for judging).

## Config source of truth
Put all IDs in `src/noticeflow/config.py`, read from env:
```python
PROJECT_ID   = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION     = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
MODEL_FLASH  = "gemini-flash-latest"   # verify current ID on adk.dev
MODEL_PRO    = "gemini-pro-latest"     # verify current ID
DATASTORE_ID = os.environ["VERTEX_SEARCH_DATASTORE_ID"]
```
> Pin model IDs once verified. `*-latest` is convenient for the hackathon but confirm it resolves to a Vertex-served model.

## Day-1 done when
- Credits applied, APIs enabled, Cloud Shell env works
- Hello agent responds via Vertex Gemini
- Corpus uploaded to GCS
- Repo skeleton pushed (public), `.env` NOT committed
