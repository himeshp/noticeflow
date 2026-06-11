"""
Mock ERP MCP server.

Exposes a single tool: get_reconciliation_data(gstin, tax_period)
Backed by static JSON files in this package's erp_data/ directory (shipped
with the package so it is available in the Agent Engine runtime).

Run locally:
    python -m noticeflow.mcp.erp_server

The Drafter agent connects to this via MCP (stdio or SSE transport).
"""

import json
import pathlib
import re
from typing import Any

from mcp.server.fastmcp import FastMCP

# Resolve the data directory relative to this file — never from user input.
# Primary: package-internal erp_data/ (ships with the package, works in the
# Agent Engine runtime). Fallback: legacy repo-root data/mock_erp/ for local dev.
_ERP_DIR = pathlib.Path(__file__).resolve().parent / "erp_data"
if not _ERP_DIR.is_dir():
    _ERP_DIR = pathlib.Path(__file__).resolve().parents[3] / "data" / "mock_erp"

_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
_PERIOD_RE = re.compile(r"^(FY\d{4}-\d{2}|\d{2}/\d{4})$")

_FALLBACK: dict[str, Any] = {
    "gstin": "",
    "tax_period": "",
    "gstr3b_tax_paid": 0.0,
    "gstr2b_itc_available": 0.0,
    "gstr3b_itc_claimed": 0.0,
    "itc_mismatch_amount": 0.0,
    "output_tax_liability": 0.0,
    "notes": "Fallback record — no matching ERP data found for this GSTIN/period.",
}

mcp = FastMCP("noticeflow-erp")


def _load_record(gstin: str, tax_period: str) -> dict[str, Any]:
    """Look up the mock ERP file for this GSTIN/period. Returns fallback if not found."""
    # Normalise period: LLMs emit "FY 2023-24" but the canonical form is "FY2023-24".
    # Collapsing whitespace happens BEFORE the strict regex validates, so the path
    # guard still only ever sees known-safe characters.
    tax_period = re.sub(r"\s+", "", tax_period)

    # Sanitize inputs: only allow known-safe characters before building any path
    if not _GSTIN_RE.match(gstin):
        return {**_FALLBACK, "gstin": gstin, "tax_period": tax_period}
    if not _PERIOD_RE.match(tax_period):
        return {**_FALLBACK, "gstin": gstin, "tax_period": tax_period}

    # Normalise period for filename (replace / with -)
    period_safe = tax_period.replace("/", "-")
    filename = f"{gstin}_{period_safe}.json"

    # Resolve and verify the path stays inside _ERP_DIR (prevent traversal)
    candidate = (_ERP_DIR / filename).resolve()
    if not candidate.is_relative_to(_ERP_DIR.resolve()):
        return {**_FALLBACK, "gstin": gstin, "tax_period": tax_period}

    if candidate.exists():
        return json.loads(candidate.read_text(encoding="utf-8"))

    return {**_FALLBACK, "gstin": gstin, "tax_period": tax_period}


@mcp.tool()
def get_reconciliation_data(gstin: str, tax_period: str) -> dict[str, Any]:
    """
    Fetch GST reconciliation figures for a taxpayer.

    Args:
        gstin: 15-character GSTIN of the taxpayer.
        tax_period: Period string — 'FY2023-24' or '04/2024'.

    Returns:
        ReconciliationData dict with GSTR-3B, GSTR-2B, ITC, and liability figures.
    """
    return _load_record(gstin.strip().upper(), tax_period.strip())


if __name__ == "__main__":
    mcp.run()
