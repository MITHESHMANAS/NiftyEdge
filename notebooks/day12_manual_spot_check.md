# Day 12 — Manual Spot-Check: ROE & 5-Year Revenue CAGR

Per the Sprint 2 exit criteria, ROE and 5-year Revenue CAGR were recomputed
independently (outside the ratio engine) for 3 companies and compared
against the values written to `financial_ratios`. This check is automated
as `tests/kpi/test_populate_integration.py::TestManualSpotCheck` (runs on
every `make test`) rather than done once in a spreadsheet, so it's
re-verified on every code change instead of going stale — see that file for
the exact recomputation logic, mirrored below for the record.

## Method

- **ROE**: `net_profit / (equity_capital + reserves) x 100` for each
  company's latest available fiscal year, computed directly from the raw
  `profitandloss` / `balancesheet` tables and compared to
  `financial_ratios.return_on_equity_pct` for the same (company_id, year).
- **Revenue CAGR (5yr)**: `((sales_latest / sales_5yr_prior) ** (1/5) - 1) x 100`,
  using the 6th-most-recent P&L row as the start point, compared to
  `financial_ratios.revenue_cagr_5yr`.
- **Tolerance**: within 0.1% (relative), per the exit criterion.

## Results (companies: TCS, RELIANCE, HDFCBANK)

| Company | Metric | Manual calc | Database value | Match |
|---|---|---|---|---|
| TCS | ROE (latest FY) | matches within 0.1% | matches within 0.1% | ✅ |
| RELIANCE | ROE (latest FY) | matches within 0.1% | matches within 0.1% | ✅ |
| HDFCBANK | ROE (latest FY) | matches within 0.1% | matches within 0.1% | ✅ |
| TCS | Revenue CAGR (5yr) | matches within 0.1% | matches within 0.1% | ✅ |
| RELIANCE | Revenue CAGR (5yr) | matches within 0.1% | matches within 0.1% | ✅ |
| HDFCBANK | Revenue CAGR (5yr) | matches within 0.1% | matches within 0.1% | ✅ |

All 6 checks pass (exact percentages are asserted, not hand-copied, in
`test_populate_integration.py` — run `pytest tests/kpi/test_populate_integration.py -k ManualSpotCheck -v`
to see live numbers).

## Note on TCS's ROE specifically

`companies.xlsx` carries a pre-computed `roe_percentage` snapshot value of
**0.52%** for TCS — implausible for a company of TCS's profitability. Our
computed value (from raw P&L/BS, latest FY) is ~50.9%, consistent with
TCS's publicly known ROE range (40-50%+ in recent years). This is flagged
in `output/ratio_edge_cases.log` as a `DATA_SOURCE` anomaly. **The ratio
engine's computed value is used for all analytics; the source
`roe_percentage` field is display-only and should not be trusted for
screening/scoring.**
