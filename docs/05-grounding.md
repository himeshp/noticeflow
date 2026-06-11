# 05 — Grounding (Vertex AI Search over GST Law)

> Verify current grounding APIs: https://adk.dev/grounding/ and the Vertex AI Search / Agent Search docs. This defines the corpus and retrieval intent.

## Goal
The Researcher agent must cite **real Indian GST law**. We build a Vertex AI Search datastore over a focused corpus of CBIC documents, and the Researcher retrieves attributed passages from it.

## Corpus — what to download (FOCUSED, not all of GST law)
All from **cbic-gst.gov.in** (public, downloadable PDFs). Keep it tight to the 3 notice types — a focused corpus retrieves more accurately.

| Document | Covers notice type | Source |
|----------|-------------------|--------|
| Consolidated **CGST Act 2017** (latest updated PDF) | all 3 | `cbic-gst.gov.in/pdf/CGST-Act-Updated-*.pdf` |
| **CGST Rules 2017** (latest) | all 3 | cbic-gst.gov.in (Acts/Rules section) |
| Circulars/instructions on **Sec. 73 & 74** (demands) | DRC-01 | cbic-gst.gov.in circulars (e.g. Circular 31/05/2018-GST on proper officers u/s 73,74) |
| Material on **Sec. 61** (scrutiny of returns) | ASMT-10 | CGST Act/Rules + relevant circulars |
| Material on **Sec. 16** (eligibility/conditions for ITC) | ITC mismatch | CGST Act + ITC circulars |

> The consolidated Act PDF carries a CBIC disclaimer that only the official Gazette has legal force. That's fine for grounding — and the Drafter may correctly note it cites the Act for reference.

## Pipeline
1. `scripts/build_datastore.py`:
   - Download/collect the corpus PDFs into `corpus/` (or a Cloud Storage bucket).
   - Upload to a **Cloud Storage** bucket.
   - Create a **Vertex AI Search** data store indexed over that bucket.
2. The **Researcher** attaches this datastore as its grounding/RAG source (per current ADK grounding docs).
3. (Optional/stretch) Add **Google Search grounding** as a second tool for recent circulars beyond the static corpus.

## Retrieval contract
- The Researcher queries with the notice type + governing sections + issue summary.
- It must return `Citation` objects (docs/03) with real `source_id`s (section / circular numbers), the retrieved `snippet`, and a one-line relevance note.
- It must NOT invent citations. If retrieval is weak, return fewer citations rather than fabricated ones.

## Quality checks before moving on
- Query "Section 73 short payment of tax" → returns Sec.73 text.
- Query "Section 16 input tax credit conditions" → returns Sec.16 text.
- Query "scrutiny of returns Section 61" → returns Sec.61 / Rule 99 material.
If these three fail, fix the datastore before building the Drafter — the whole value prop rides on retrieval quality.

## Notes
- Keep chunking sane (section-level chunks retrieve better than whole-Act blobs).
- Hindi versions of the law exist on CBIC if pursuing the Hindi stretch goal — separate datastore or tagged docs.
