# Day 06 — Manual Data Quality Review

Sample of 5 random companies (seed=42): **SUNPHARMA, BAJFINANCE, ADANIGREEN, HAL, EICHERMOT**

## Findings

| Company | Sector | P&L yrs | BS yrs | CF yrs | Notes |
|---|---|---|---|---|---|
| SUNPHARMA | Healthcare / Pharmaceuticals | 12 (2013-03 → 2024-03) | 13 | 12 | Clean, full FY history. BS has an extra 2024-09 half-year snapshot row (legitimate — company reports semi-annual BS updates in the raw source). |
| BAJFINANCE | Financials / Consumer Finance | 10 (2015-03 → 2024-03) | 11 | 10 | Clean. Shorter history (listed/expanded later); still well above the 5yr coverage minimum. |
| ADANIGREEN | Energy / Renewable Energy | 8 (2017-03 → 2024-03) | 9 | 8 | Clean. Younger company — history starts 2017, consistent with its 2018 IPO. |
| HAL | Industrials / Defence & Aerospace | 12 (2013-03 → 2024-03) | 10 (2016-03 → 2024-09) | 8 (2017-03 → 2024-03) | **Gap found**: BS/CF start later than P&L (2016 / 2017 vs 2013). Consistent with the dataset's documented ~91-97% completeness for BS/CF (Section 7.2) — not a loader bug; confirmed by cross-checking raw balancesheet.xlsx / cashflow.xlsx directly (no HAL rows exist for 2013-2015). |
| EICHERMOT | Consumer Discretionary / Two Wheelers | 12 | 13 | 12 | **Format quirk found**: years 2012-12 / 2013-12 / 2014-12 (Dec-ending) then jumps straight to 2016-03 (no 2015 row at all), then normal Mar-ending FYs. Correctly normalised by `normalize_year()`; the 2015 gap exists in the raw source, not introduced by the loader. |

## Loader bugs found & fixed during this review
None — all gaps/irregularities above trace back to genuine gaps or format
changes in the raw Excel source files, not to `normalize_year()` /
`normalize_ticker()` logic. Confirmed by re-checking each irregular case
directly against `data/raw/*.xlsx` with `header=1`.

## Cross-check against `load_audit.csv`
- `companies`: 92 in, 92 out, 0 rejected. ✅ matches exit criteria.
- Every child table's `rows_in` exactly matches the row count quoted in
  the project spec (P&L 1,276 / BS 1,312 / CF 1,187 / documents 1,585 /
  financial_ratios 1,184 / stock_prices 5,520 / market_cap 552 /
  peer_groups 56) — confirms the Excel loader (`header=1` for core files,
  `header=0` for supplementary) is reading every source row correctly
  before any DQ rejection is applied.
- Rejections are concentrated in a small number of genuinely orphaned
  tickers (8 companies present in the child tables but absent from
  `companies.xlsx`: ULTRACEMCO, UNIONBANK, UNITDSPR, VBL, VEDL, WIPRO,
  ZYDUSLIFE, ZOMATO) plus non-FY period labels (`TTM`, half-year `2024.5`
  markers) that DQ-07 correctly rejects rather than mis-parses.

## Sign-off
Manual review complete — no loader bugs found; all 5 sampled companies'
data is correct, consistent with the source Excel files, and properly
normalised.
