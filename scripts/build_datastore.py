"""
build_datastore.py — one-shot setup script for the Vertex AI Search datastore.

Run this ONCE after GCP credentials are configured and before running agents.

Steps:
  1. Download CBIC GST law PDFs into corpus/
  2. Upload corpus/ to GCS
  3. Create the Vertex AI Search datastore (idempotent)
  4. Import documents from GCS
  5. Run 3 mandatory retrieval quality checks

Usage:
    python scripts/build_datastore.py [--skip-download] [--skip-upload] [--checks-only]

Options:
    --skip-download   Skip PDF download (corpus/ already populated)
    --skip-upload     Skip GCS upload (files already in bucket)
    --checks-only     Only run the quality checks against an existing datastore

Requirements:
    pip install google-cloud-storage google-cloud-discoveryengine requests
    (all included in pyproject.toml)

Env vars required (copy .env.example → .env and fill in):
    GOOGLE_CLOUD_PROJECT
    GOOGLE_CLOUD_LOCATION
    GCS_CORPUS_BUCKET
    VERTEX_SEARCH_DATASTORE_ID
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

# Load .env before importing config
from dotenv import load_dotenv
load_dotenv()

import os
import requests
from google.api_core import exceptions as gcp_exceptions
from google.cloud import discoveryengine_v1 as discoveryengine
from google.cloud import storage

# ── Config (all from env — never hardcoded) ───────────────────────────────────

PROJECT_ID    = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
LOCATION      = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")  # GCS bucket region
# Vertex AI Search datastore location — must be "global", "us", or "eu" (NOT us-central1).
SEARCH_LOCATION = os.environ.get("VERTEX_SEARCH_LOCATION", "global")
BUCKET_NAME   = os.environ.get("GCS_CORPUS_BUCKET", "")
# `or` (not get default) so an empty-but-present env var falls back, not "".
DATASTORE_ID  = os.environ.get("VERTEX_SEARCH_DATASTORE_ID") or "noticeflow-gst-corpus"

COLLECTION    = "default_collection"
PARENT        = f"projects/{PROJECT_ID}/locations/{SEARCH_LOCATION}/collections/{COLLECTION}"
DATASTORE_RES = f"{PARENT}/dataStores/{DATASTORE_ID}"
BRANCH        = f"{DATASTORE_RES}/branches/default_branch"
SERVING_CFG   = f"{DATASTORE_RES}/servingConfigs/default_config"

REPO_ROOT  = pathlib.Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "corpus"

# ── CBIC corpus — public government PDFs ─────────────────────────────────────
# All URLs are hardcoded constants pointing to cbic-gst.gov.in (official source).
# ⚠️  VERIFY these URLs before running — CBIC updates document paths without
#     notice. Check https://cbic-gst.gov.in and update if a 404 is returned.
# Do NOT replace with user-supplied URLs — that would open an SSRF vector.

CORPUS_DOCS: dict[str, str] = {
    # CGST Act 2017 (consolidated, updated 31-08-2021) — Sec 61, 73, 74, 16
    "cgst_act_2017.pdf": (
        "https://cbic-gst.gov.in/pdf/CGST-Act-Updated-31082021.pdf"
    ),
    # CGST Rules 2017, Part A (Rules) — Rule 88D, 36(4), 142
    "cgst_rules_2017.pdf": (
        "https://cbic-gst.gov.in/pdf/01062021-CGST-Rules-2017-Part-A-Rules.pdf"
    ),
    # Circular 31/05/2018-GST: Proper officers for Sec 73/74 demands
    "circular_31_2018_sec73_74.pdf": (
        "https://cbic-gst.gov.in/pdf/circularno-31-cgst.pdf"
    ),
    # Circular 135/05/2020-GST: ITC refund / GSTR-2A reflection (Sec 16, Rule 36(4))
    "circular_135_2020_itc_sec16.pdf": (
        "https://cbic-gst.gov.in/pdf/Circular_Refund_135_5_2020.pdf"
    ),
    # Circular 183/15/2022-GST: ITC mismatch GSTR-3B vs GSTR-2A resolution
    "circular_183_2022_sec16_itc.pdf": (
        "https://cbic-gst.gov.in/pdf/circular-183.pdf"
    ),
}

# ── Retrieval quality checks (from docs/05-grounding.md) ─────────────────────
# All three must return ≥1 result before moving to Day 3.

QUALITY_CHECKS: list[tuple[str, str]] = [
    ("DRC-01 / Sec 73",    "Section 73 short payment of tax show cause notice demand"),
    ("ITC / Sec 16",       "Section 16 input tax credit eligibility conditions GSTR-2B"),
    ("ASMT-10 / Sec 61",   "scrutiny of returns Section 61 discrepancy explanation"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_env() -> None:
    missing = [k for k in ("GOOGLE_CLOUD_PROJECT", "GCS_CORPUS_BUCKET") if not os.environ.get(k)]
    if missing:
        print(f"[ERROR] Missing required env vars: {', '.join(missing)}")
        print("        Copy .env.example → .env and fill in your GCP values.")
        sys.exit(1)


def _corpus_dir() -> pathlib.Path:
    CORPUS_DIR.mkdir(exist_ok=True)
    return CORPUS_DIR


def _safe_corpus_path(filename: str) -> pathlib.Path:
    """Resolve corpus path and verify it stays inside CORPUS_DIR (path traversal guard)."""
    candidate = (CORPUS_DIR / filename).resolve()
    if not candidate.is_relative_to(CORPUS_DIR.resolve()):
        raise ValueError(f"Unsafe corpus path rejected: {filename!r}")
    return candidate


# ── Step 1: Download ──────────────────────────────────────────────────────────

def download_corpus() -> None:
    """Download CBIC PDFs into corpus/. Skips files that already exist."""
    _corpus_dir()
    print("\n[1/5] Downloading CBIC corpus PDFs ...")

    # Only HTTPS requests to the hardcoded CBIC domain are made here.
    # SSRF prevention: URLs are constants, not user-supplied.
    for filename, url in CORPUS_DOCS.items():
        dest = _safe_corpus_path(filename)
        if dest.exists():
            print(f"  SKIP  {filename} (already downloaded)")
            continue

        print(f"  GET   {url}")
        try:
            resp = requests.get(url, timeout=60, allow_redirects=True)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            print(f"  OK    {filename} ({len(resp.content) // 1024} KB)")
        except requests.RequestException as exc:
            print(f"  WARN  {filename}: {exc}")
            print(f"        Download manually from {url} → corpus/{filename}")
            print("        Then re-run with --skip-download")

    pdfs = list(CORPUS_DIR.glob("*.pdf"))
    if not pdfs:
        print("\n[ERROR] corpus/ is empty. Download PDFs manually and retry.")
        print("        See docs/05-grounding.md for source URLs.")
        sys.exit(1)

    print(f"  Corpus ready: {len(pdfs)} PDF(s) in corpus/")


# ── Step 2: Upload to GCS ─────────────────────────────────────────────────────

def upload_to_gcs() -> None:
    """Upload corpus/*.pdf to GCS_CORPUS_BUCKET. Skips files already uploaded."""
    print(f"\n[2/5] Uploading corpus to gs://{BUCKET_NAME}/ ...")
    client = storage.Client(project=PROJECT_ID)

    try:
        bucket = client.get_bucket(BUCKET_NAME)
    except gcp_exceptions.NotFound:
        print(f"  Creating bucket gs://{BUCKET_NAME} in {LOCATION} ...")
        bucket = client.create_bucket(BUCKET_NAME, location=LOCATION)
        print(f"  Created gs://{BUCKET_NAME}")

    pdfs = list(CORPUS_DIR.glob("*.pdf"))
    if not pdfs:
        print("[ERROR] corpus/ is empty — run without --skip-download first.")
        sys.exit(1)

    for pdf in pdfs:
        blob = bucket.blob(pdf.name)
        if blob.exists():
            print(f"  SKIP  gs://{BUCKET_NAME}/{pdf.name} (already uploaded)")
            continue
        blob.upload_from_filename(str(pdf))
        print(f"  UP    gs://{BUCKET_NAME}/{pdf.name} ({pdf.stat().st_size // 1024} KB)")

    print(f"  Upload complete: {len(pdfs)} PDF(s) in gs://{BUCKET_NAME}/")


# ── Step 3: Create datastore ──────────────────────────────────────────────────

def create_datastore() -> None:
    """Create the Vertex AI Search datastore. Idempotent — safe to rerun."""
    print(f"\n[3/5] Creating Vertex AI Search datastore '{DATASTORE_ID}' ...")
    client = discoveryengine.DataStoreServiceClient()

    datastore = discoveryengine.DataStore(
        display_name="NoticeFlow GST Law Corpus",
        industry_vertical=discoveryengine.IndustryVertical.GENERIC,
        content_config=discoveryengine.DataStore.ContentConfig.CONTENT_REQUIRED,
    )

    try:
        operation = client.create_data_store(
            parent=PARENT,
            data_store=datastore,
            data_store_id=DATASTORE_ID,
        )
        print(f"  Creating ... (operation: {operation.operation.name})")
        result = operation.result(timeout=120)
        print(f"  Created: {result.name}")
    except gcp_exceptions.AlreadyExists:
        print(f"  EXISTS  Datastore '{DATASTORE_ID}' already exists — skipping create.")

    print(f"\n  ✓ Set VERTEX_SEARCH_DATASTORE_ID={DATASTORE_ID} in your .env")


# ── Step 4: Import documents ──────────────────────────────────────────────────

def import_documents() -> None:
    """Import PDFs from GCS into the datastore. Waits for completion."""
    print(f"\n[4/5] Importing documents from gs://{BUCKET_NAME}/ ...")
    client = discoveryengine.DocumentServiceClient()

    gcs_uri = f"gs://{BUCKET_NAME}/*.pdf"
    print(f"  Source: {gcs_uri}")

    operation = client.import_documents(
        request=discoveryengine.ImportDocumentsRequest(
            parent=BRANCH,
            gcs_source=discoveryengine.GcsSource(
                input_uris=[gcs_uri],
                data_schema="content",
            ),
            reconciliation_mode=(
                discoveryengine.ImportDocumentsRequest.ReconciliationMode.FULL
            ),
        )
    )

    print(f"  Import started (operation: {operation.operation.name})")
    print("  Waiting for indexing to complete — this can take 5–20 minutes ...")

    # Poll manually so we can show progress dots
    start = time.time()
    while not operation.done():
        elapsed = int(time.time() - start)
        print(f"  ... {elapsed}s elapsed", end="\r", flush=True)
        time.sleep(30)

    print()
    result = operation.result()
    meta = operation.metadata

    success = getattr(getattr(result, "success_count", None), "value", "?")
    failure = getattr(getattr(result, "failure_count", None), "value", "?")
    print(f"  Import complete: {success} succeeded, {failure} failed")

    if failure and str(failure) not in ("0", "?"):
        print(f"  WARN  Some documents failed to import. Check GCS error logs.")


# ── Step 5: Quality checks ────────────────────────────────────────────────────

def run_quality_checks() -> bool:
    """Run the 3 mandatory retrieval checks from docs/05-grounding.md.

    Returns True if all checks pass (≥1 result each). Exits 1 if any fail.
    """
    print(f"\n[5/5] Running retrieval quality checks ...")
    client = discoveryengine.SearchServiceClient()

    all_pass = True
    for label, query in QUALITY_CHECKS:
        try:
            response = client.search(
                request=discoveryengine.SearchRequest(
                    serving_config=SERVING_CFG,
                    query=query,
                    page_size=3,
                    content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                        snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                            return_snippet=True,
                            max_snippet_count=1,
                        ),
                    ),
                )
            )

            results = list(response.results)
            hit_count = len(results)

            if hit_count == 0:
                print(f"  FAIL  [{label}] query returned 0 results")
                print(f"        Query: {query!r}")
                all_pass = False
            else:
                # Print the top snippet for manual inspection
                top = results[0]
                snippets = (
                    top.document.derived_struct_data.get("snippets", [{}])
                    if top.document.derived_struct_data
                    else [{}]
                )
                snippet_text = snippets[0].get("snippet", "(no snippet)") if snippets else "(no snippet)"
                print(f"  PASS  [{label}] {hit_count} result(s)")
                print(f"        Top snippet: {snippet_text[:120].strip()!r}")

        except Exception as exc:
            print(f"  ERROR [{label}] {exc}")
            all_pass = False

    return all_pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the Vertex AI Search datastore for NoticeFlow."
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="Skip PDF download (corpus/ already populated)",
    )
    parser.add_argument(
        "--skip-upload", action="store_true",
        help="Skip GCS upload (files already in bucket)",
    )
    parser.add_argument(
        "--checks-only", action="store_true",
        help="Only run retrieval quality checks against an existing datastore",
    )
    args = parser.parse_args()

    _check_env()

    print("=" * 60)
    print("NoticeFlow — Build Datastore")
    print(f"  Project  : {PROJECT_ID}")
    print(f"  Location : {LOCATION}")
    print(f"  Bucket   : gs://{BUCKET_NAME}/")
    print(f"  Datastore: {DATASTORE_ID}")
    print("=" * 60)

    if args.checks_only:
        ok = run_quality_checks()
        sys.exit(0 if ok else 1)

    if not args.skip_download:
        download_corpus()

    if not args.skip_upload:
        upload_to_gcs()

    create_datastore()
    import_documents()
    ok = run_quality_checks()

    print("\n" + "=" * 60)
    if ok:
        print("✓ Datastore ready. All quality checks passed.")
        print(f"\nAdd to your .env:")
        print(f"  VERTEX_SEARCH_DATASTORE_ID={DATASTORE_ID}")
        print("\nNext: run the Researcher integration tests:")
        print("  pytest tests/test_researcher.py -v")
    else:
        print("✗ One or more quality checks FAILED.")
        print("  Fix retrieval before building the Drafter — the whole")
        print("  value prop rides on citation quality. See docs/05-grounding.md.")
        sys.exit(1)
    print("=" * 60)


if __name__ == "__main__":
    main()
