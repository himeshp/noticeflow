# 04 — MCP Tool (Mock ERP / Reconciliation)

> Verify ADK's MCP integration at https://adk.dev/tools-custom/mcp-tools/ and https://adk.dev/mcp/ before wiring. This doc defines the tool's contract and mock data.

## Purpose
Track 1 requires using **MCP to securely connect to an external tool**. NoticeFlow's Drafter needs the taxpayer's accounting/reconciliation figures to populate the reply annexure. In production this is Tally/Zoho/an ERP; for the MVP it's a **mock MCP server** returning realistic reconciliation JSON keyed by GSTIN + period.

This is honest: the *format* of GST reconciliation data is public and standardized; only the *values* are mocked.

## The tool

**Tool name:** `get_reconciliation_data`
**Params:**
- `gstin: str` — 15-char GSTIN
- `tax_period: str` — e.g. `"FY2023-24"` or `"04/2024"`

**Returns:** JSON matching `ReconciliationData` (docs/03):
```json
{
  "gstin": "24ABCDE1234F1Z5",
  "tax_period": "FY2023-24",
  "gstr3b_tax_paid": 1450000.0,
  "gstr2b_itc_available": 820000.0,
  "gstr3b_itc_claimed": 905000.0,
  "itc_mismatch_amount": 85000.0,
  "output_tax_liability": 2355000.0,
  "notes": "ITC claimed exceeds 2B; 85,000 difference under query."
}
```

## Implementation notes
- Build a minimal MCP server (`src/noticeflow/mcp/erp_server.py`) exposing the single tool above.
- Back it with a static lookup over `data/mock_erp/*.json` (one file per sample GSTIN/period), so demo runs are deterministic.
- If a GSTIN/period isn't found, return a sensible default record (don't error the pipeline) but set `notes` to indicate it's a fallback.
- Keep the server runnable both locally (for dev) and reachable by the deployed agent. Document how the Drafter connects to it.
- Do NOT put real taxpayer data here. All values are fabricated.

## Mock dataset — provide one record per sample notice
Create these in `data/mock_erp/`. The GSTINs must match the GSTINs in the synthetic notices (`data/sample_notices/`) so the Drafter's lookup succeeds end-to-end.

### Record A — for the DRC-01 / Sec.73 demand notice
```json
{
  "gstin": "24ABCDE1234F1Z5",
  "tax_period": "FY2023-24",
  "gstr3b_tax_paid": 1450000.0,
  "gstr2b_itc_available": 820000.0,
  "gstr3b_itc_claimed": 905000.0,
  "itc_mismatch_amount": 85000.0,
  "output_tax_liability": 2355000.0,
  "notes": "Short payment of tax alleged; taxpayer contends ITC was validly availed."
}
```

### Record B — for the ASMT-10 / Sec.61 scrutiny notice
```json
{
  "gstin": "27PQRSX5678G2Z9",
  "tax_period": "FY2023-24",
  "gstr3b_tax_paid": 640000.0,
  "gstr2b_itc_available": 310000.0,
  "gstr3b_itc_claimed": 312000.0,
  "itc_mismatch_amount": 2000.0,
  "output_tax_liability": 952000.0,
  "notes": "Minor turnover discrepancy between GSTR-1 and 3B; explainable by timing."
}
```

### Record C — for the ITC-mismatch / Sec.16 notice
```json
{
  "gstin": "29LMNOP9012H3Z4",
  "tax_period": "04/2024",
  "gstr3b_tax_paid": 210000.0,
  "gstr2b_itc_available": 95000.0,
  "gstr3b_itc_claimed": 140000.0,
  "itc_mismatch_amount": 45000.0,
  "output_tax_liability": 350000.0,
  "notes": "ITC claimed exceeds 2B due to supplier's late GSTR-1 filing; reversible/recoverable."
}
```

## How the Drafter uses it
1. Reads `required_annexures` from `LegalContext`.
2. Calls `get_reconciliation_data(gstin, tax_period)` via MCP.
3. Embeds the returned figures into the `ResponsePacket.annexure` and references them in `reply_body` (e.g. "As reconciled, the ₹85,000 difference arises from…").
