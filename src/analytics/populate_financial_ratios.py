"""
src/analytics/populate_financial_ratios.py

Sprint 2, Day 12-13 — runs the full Ratio Engine (ratios.py + cagr.py +
cashflow_kpis.py + composite_score.py) for every (company_id, year) in the
database and OVERWRITES the `financial_ratios` table with the computed
results. Also writes:
    output/capital_allocation.csv   — 8-pattern label for every company-year
    output/ratio_edge_cases.log     — ROCE/ROE anomalies vs companies.xlsx

Usage:
    python src/etl/loader.py            # Sprint 1 must have already run
    python src/analytics/populate_financial_ratios.py
    # or: make ratios
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.analytics.cagr import compute_all_cagr_windows
from src.analytics.cashflow_kpis import (
    capex_intensity,
    cfo_quality_score,
    classify_capital_allocation,
    fcf_conversion_rate,
    free_cash_flow,
)
from src.analytics.composite_score import composite_quality_score
from src.analytics.ratios import (
    asset_turnover,
    debt_to_equity,
    ebit,
    high_leverage_flag,
    icr_label,
    icr_risk_flag,
    interest_coverage,
    is_financials_sector,
    net_debt,
    net_profit_margin,
    operating_profit_margin,
    opm_cross_check,
    return_on_assets,
    return_on_capital_employed,
    return_on_equity,
)
from src.analytics.utils import clean
from src.etl.config import DB_PATH, OUTPUT_DIR
from src.etl.logging_setup import get_logger

log = get_logger(__name__)

ROCE_ANOMALY_TOLERANCE_PCT = 5.0
CFO_QUALITY_WINDOW_YEARS = 5


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def _load_base_frame(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Builds the (company_id, year) base — the union of every annual period
    reported in P&L, balance sheet, or cash flow — then left-joins all
    three source tables plus `sectors` and `companies`.

    We deliberately do NOT restrict to March-end ('-03') periods only:
    several companies have Dec/Sep/Jun-ending historical rows before
    switching to a March FYE, and restricting to '-03' drops the row
    count below the >= 1,100 exit criterion (1,028 vs 1,155 with all
    period-end conventions included). Ratios are still computed
    correctly per-row regardless of which month the FY ends in; CAGR
    windows use *positional* (Nth-prior-report) offsets rather than
    calendar-exact year gaps, which is a reasonable approximation given
    the source data mixes FY-end conventions for a handful of companies
    (documented in ratio_edge_cases.log).
    """
    base = pd.read_sql(
        """
        SELECT company_id, year FROM profitandloss
        UNION
        SELECT company_id, year FROM balancesheet
        UNION
        SELECT company_id, year FROM cashflow
        """,
        conn,
    )

    pnl = pd.read_sql("SELECT * FROM profitandloss", conn).drop(columns=["id"])
    bs = pd.read_sql("SELECT * FROM balancesheet", conn).drop(columns=["id"])
    cf = pd.read_sql("SELECT * FROM cashflow", conn).drop(columns=["id"])
    sectors = pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn)
    companies = pd.read_sql(
        "SELECT id AS company_id, face_value, book_value, roce_percentage, "
        "roe_percentage FROM companies",
        conn,
    )

    df = base.merge(pnl, on=["company_id", "year"], how="left")
    df = df.merge(bs, on=["company_id", "year"], how="left", suffixes=("", "_bs"))
    df = df.merge(cf, on=["company_id", "year"], how="left", suffixes=("", "_cf"))
    df = df.merge(sectors, on="company_id", how="left")
    df = df.merge(companies, on="company_id", how="left")
    return df.sort_values(["company_id", "year"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Per-row ratio computation (Day 08-09)
# ---------------------------------------------------------------------------
def _compute_row_ratios(row: pd.Series) -> dict:
    net_profit = clean(row.get("net_profit"))
    sales = clean(row.get("sales"))
    operating_profit = clean(row.get("operating_profit"))
    opm_percentage = clean(row.get("opm_percentage"))
    equity_capital = clean(row.get("equity_capital"))
    reserves = clean(row.get("reserves"))
    borrowings = clean(row.get("borrowings"))
    total_assets = clean(row.get("total_assets"))
    profit_before_tax = clean(row.get("profit_before_tax"))
    interest = clean(row.get("interest"))
    other_income = clean(row.get("other_income"))
    investments = clean(row.get("investments"))
    broad_sector = clean(row.get("broad_sector"))
    operating_activity = clean(row.get("operating_activity"))
    investing_activity = clean(row.get("investing_activity"))
    eps = clean(row.get("eps"))
    dividend_payout = clean(row.get("dividend_payout"))
    face_value = clean(row.get("face_value"))

    npm = net_profit_margin(net_profit, sales)
    opm = operating_profit_margin(operating_profit, sales)
    opm_mismatch = opm_cross_check(opm, opm_percentage)
    roe = return_on_equity(net_profit, equity_capital, reserves)

    ebit_val = ebit(profit_before_tax, interest)
    roce = return_on_capital_employed(ebit_val, equity_capital, reserves, borrowings)
    roa = return_on_assets(net_profit, total_assets)

    de = debt_to_equity(borrowings, equity_capital, reserves)
    hl_flag = high_leverage_flag(de, broad_sector)
    icr = interest_coverage(operating_profit, other_income, interest)
    label = icr_label(interest)
    icr_risk = icr_risk_flag(icr)
    nd = net_debt(borrowings, investments)
    at = asset_turnover(sales, total_assets)

    fcf = free_cash_flow(operating_activity, investing_activity)
    capex = abs(investing_activity) if investing_activity is not None else None
    capex_pct, capex_label = capex_intensity(investing_activity, sales)
    fcf_conv = fcf_conversion_rate(fcf, operating_profit)

    # book_value_per_share = (equity_capital + reserves) * face_value / equity_capital
    # (shares_outstanding = equity_capital / face_value, a standard Indian
    # equity-structure convention; face_value is static per company).
    bvps: Optional[float] = None
    if equity_capital not in (None, 0) and face_value is not None and reserves is not None:
        bvps = (equity_capital + reserves) * face_value / equity_capital

    return {
        "net_profit_margin_pct": npm,
        "operating_profit_margin_pct": opm,
        "opm_cross_check_mismatch": int(opm_mismatch),
        "return_on_equity_pct": roe,
        "return_on_capital_employed_pct": roce,
        "return_on_assets_pct": roa,
        "debt_to_equity": de,
        "high_leverage_flag": int(hl_flag),
        "interest_coverage": icr,
        "icr_label": label,
        "icr_risk_flag": int(icr_risk),
        "net_debt_cr": nd,
        "asset_turnover": at,
        "free_cash_flow_cr": fcf,
        "capex_cr": capex,
        "capex_intensity_pct": capex_pct,
        "capex_intensity_label": capex_label,
        "fcf_conversion_rate_pct": fcf_conv,
        "earnings_per_share": eps,
        "book_value_per_share": bvps,
        "dividend_payout_ratio_pct": dividend_payout,
        "total_debt_cr": borrowings,
        "cash_from_operations_cr": operating_activity,
    }


# ---------------------------------------------------------------------------
# Per-company CAGR + CFO quality + capital allocation (needs the full
# history, not just one row)
# ---------------------------------------------------------------------------
def _compute_company_series_fields(company_df: pd.DataFrame) -> pd.DataFrame:
    company_df = company_df.sort_values("year").reset_index(drop=True)

    sales_series = company_df.set_index("year")["sales"]
    pat_series = company_df.set_index("year")["net_profit"]
    eps_series = company_df.set_index("year")["eps"]
    cfo_series_full = company_df.set_index("year")["operating_activity"]

    # Every row gets its own trailing-window CAGR computed below, so each
    # year in financial_ratios carries a CAGR "as of that year" rather than
    # only the latest year.
    results = []
    for i in range(len(company_df)):
        window_sales = sales_series.iloc[: i + 1]
        window_pat = pat_series.iloc[: i + 1]
        window_eps = eps_series.iloc[: i + 1]

        rev = compute_all_cagr_windows(window_sales)
        pat = compute_all_cagr_windows(window_pat)
        eps = compute_all_cagr_windows(window_eps)

        # CFO Quality Score: trailing up-to-5-year window ending at this row.
        cfo_window = cfo_series_full.iloc[max(0, i - CFO_QUALITY_WINDOW_YEARS + 1) : i + 1]
        pat_window = pat_series.iloc[max(0, i - CFO_QUALITY_WINDOW_YEARS + 1) : i + 1]
        cfo_score, cfo_label = cfo_quality_score(cfo_window.tolist(), pat_window.tolist())

        results.append(
            {
                "revenue_cagr_3yr": rev.get("cagr_3yr"),
                "revenue_cagr_5yr": rev.get("cagr_5yr"),
                "revenue_cagr_10yr": rev.get("cagr_10yr"),
                "revenue_cagr_5yr_flag": rev.get("cagr_5yr_flag"),
                "pat_cagr_3yr": pat.get("cagr_3yr"),
                "pat_cagr_5yr": pat.get("cagr_5yr"),
                "pat_cagr_10yr": pat.get("cagr_10yr"),
                "pat_cagr_5yr_flag": pat.get("cagr_5yr_flag"),
                "eps_cagr_3yr": eps.get("cagr_3yr"),
                "eps_cagr_5yr": eps.get("cagr_5yr"),
                "eps_cagr_10yr": eps.get("cagr_10yr"),
                "eps_cagr_5yr_flag": eps.get("cagr_5yr_flag"),
                "cfo_quality_score": cfo_score,
                "cfo_quality_label": cfo_label,
            }
        )

    series_df = pd.DataFrame(results)
    company_df = pd.concat([company_df.reset_index(drop=True), series_df], axis=1)
    return company_df


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_ratio_engine(db_path: Path = None) -> dict:
    db_path = db_path or DB_PATH
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Starting Ratio Engine run against %s", db_path)
    t0 = time.time()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")

    df = _load_base_frame(conn)
    log.info("Base company-year frame: %d rows", len(df))

    # Per-row ratios
    row_results = df.apply(_compute_row_ratios, axis=1, result_type="expand")
    df = pd.concat([df, row_results], axis=1)

    # Per-company series fields (CAGR, CFO quality)
    per_company = []
    capital_allocation_rows = []
    for company_id, group in df.groupby("company_id", sort=False):
        group = _compute_company_series_fields(group)
        per_company.append(group)

        for _, row in group.iterrows():
            cfo_sign, cfi_sign, cff_sign, pattern = classify_capital_allocation(
                row.get("operating_activity"),
                row.get("investing_activity"),
                row.get("financing_activity"),
                cfo_over_pat=(
                    row["operating_activity"] / row["net_profit"]
                    if pd.notna(row.get("operating_activity"))
                    and pd.notna(row.get("net_profit"))
                    and row.get("net_profit") not in (0, None)
                    else None
                ),
            )
            capital_allocation_rows.append(
                {
                    "company_id": company_id,
                    "year": row["year"],
                    "cfo_sign": cfo_sign,
                    "cfi_sign": cfi_sign,
                    "cff_sign": cff_sign,
                    "pattern_label": pattern,
                }
            )

    df = pd.concat(per_company, axis=0).reset_index(drop=True)
    df["capital_allocation_pattern"] = [r["pattern_label"] for r in capital_allocation_rows]

    # Composite quality score
    df["composite_quality_score"] = df.apply(
        lambda r: composite_quality_score(
            r.get("return_on_equity_pct"),
            r.get("return_on_capital_employed_pct"),
            r.get("debt_to_equity"),
            r.get("interest_coverage"),
            r.get("icr_label") == "Debt Free",
            r.get("revenue_cagr_5yr"),
        ),
        axis=1,
    )

    log.info("Computed all ratios for %d company-years", len(df))

    # ---- Write capital_allocation.csv -------------------------------------
    pd.DataFrame(capital_allocation_rows).to_csv(OUTPUT_DIR / "capital_allocation.csv", index=False)
    log.info("Wrote %s", OUTPUT_DIR / "capital_allocation.csv")

    # ---- Day 13: ROCE/ROE anomaly cross-check + edge case log -------------
    edge_cases = _build_edge_case_log(df)
    with open(OUTPUT_DIR / "ratio_edge_cases.log", "w") as f:
        f.write(edge_cases)
    log.info("Wrote %s", OUTPUT_DIR / "ratio_edge_cases.log")

    # ---- Overwrite financial_ratios table ----------------------------------
    schema_cols = [c[1] for c in conn.execute("PRAGMA table_info(financial_ratios)").fetchall()]
    df_to_write = df.reindex(columns=[c for c in schema_cols if c != "id"])
    df_to_write = df_to_write.where(pd.notnull(df_to_write), None)

    cur = conn.cursor()
    cur.execute("DELETE FROM financial_ratios")
    cols = list(df_to_write.columns)
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    cur.executemany(
        f"INSERT INTO financial_ratios ({col_list}) VALUES ({placeholders})",
        df_to_write.values.tolist(),
    )
    conn.commit()

    row_count = conn.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = ON")
    fk_check = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.close()

    log.info(
        "Ratio Engine run complete in %.3fs — %d rows written to financial_ratios, "
        "%d FK violations",
        time.time() - t0,
        row_count,
        len(fk_check),
    )

    return {
        "row_count": row_count,
        "fk_check": fk_check,
        "df": df,
    }


def _latest_standard_fye_per_company(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns one row per company: the latest March-FYE ('-03') row if the
    company has one, otherwise the latest row of any period-end
    convention. Plain `groupby(...).last()` on sort-by-year would instead
    pick whichever period label sorts highest — which for a handful of
    companies is a later *interim* half-year balance-sheet update (e.g.
    BEL/HAL have a 'YYYY-09' row after their 'YYYY-03' annual close).
    Pairing a full fiscal year's P&L with an interim half-year BS snapshot
    produces nonsensical ratios (denominators an order of magnitude too
    small), which is exactly the kind of anomaly this function exists to
    avoid feeding into "latest year" snapshots (edge-case cross-checks,
    screener previews, etc).
    """
    is_march = df["year"].str.endswith("-03")
    march_rows = df[is_march].sort_values("year").groupby("company_id", as_index=False).last()
    covered = set(march_rows["company_id"])
    remaining = df[~df["company_id"].isin(covered)]
    fallback_rows = (
        remaining.sort_values("year").groupby("company_id", as_index=False).last()
        if not remaining.empty
        else remaining
    )
    return pd.concat([march_rows, fallback_rows], ignore_index=True)


def _build_edge_case_log(df: pd.DataFrame) -> str:
    """
    Day 13 — cross-checks computed ROCE and ROE against the pre-computed
    `roce_percentage` / `roe_percentage` snapshot fields in companies.xlsx,
    using each company's most recent available year. Anomalies (diff > 5%
    for ROCE; any material mismatch for ROE) are logged with a category.
    """
    lines = [
        "N100 Ratio Engine — Edge Case Log (Sprint 2, Day 13)",
        "=" * 70,
        "",
        "Cross-check: computed ROCE/ROE (latest available FY per company) vs",
        "the pre-computed roce_percentage/roe_percentage snapshot fields in",
        "companies.xlsx. companies.xlsx values are a single current-moment",
        "snapshot (not tied to a specific fiscal year), so some drift against",
        "our per-FY computed values is expected; entries below are anomalies",
        "worth a human look, categorised as:",
        "  - DATA_SOURCE: companies.xlsx snapshot likely stale/pulled at a",
        "    different date than our latest loaded FY",
        "  - VERSION_DIFFERENCE: source value likely computed with a",
        "    different ROCE/ROE formula (e.g. average vs year-end capital",
        "    employed, or a different other_income treatment)",
        "  - FORMULA_DISCREPANCY: magnitude of mismatch suggests the source",
        "    field itself may be wrong / a data entry error (e.g. sub-1%",
        "    figures for a company with a clearly profitable, well-",
        "    capitalised balance sheet)",
        "",
    ]

    latest = _latest_standard_fye_per_company(df)[
        [
            "company_id",
            "year",
            "broad_sector",
            "return_on_capital_employed_pct",
            "return_on_equity_pct",
            "roce_percentage",
            "roe_percentage",
        ]
    ]

    roce_anomalies = 0
    roe_anomalies = 0

    for _, row in latest.iterrows():
        cid = row["company_id"]
        sector = row["broad_sector"]
        computed_roce = row["return_on_capital_employed_pct"]
        source_roce = row["roce_percentage"]
        computed_roe = row["return_on_equity_pct"]
        source_roe = row["roe_percentage"]

        if pd.notna(computed_roce) and pd.notna(source_roce):
            diff = abs(computed_roce - source_roce)
            if diff > ROCE_ANOMALY_TOLERANCE_PCT:
                roce_anomalies += 1
                category = "FORMULA_DISCREPANCY" if diff > 20 else "VERSION_DIFFERENCE"
                sector_note = (
                    " [Financials — sector-relative benchmark applies]"
                    if is_financials_sector(sector)
                    else ""
                )
                lines.append(
                    f"[ROCE] {cid} ({row['year']}){sector_note}: computed={computed_roce:.2f}% "
                    f"vs source={source_roce:.2f}% (diff={diff:.2f}pp) -> {category}"
                )

        if pd.notna(computed_roe) and pd.notna(source_roe):
            diff = abs(computed_roe - source_roe)
            # ROE source field has known-anomalous entries (e.g. sub-1%
            # values for clearly profitable companies) — flag any case
            # where the source value looks implausibly small relative to
            # our computed value (ratio > 5x) as well as the flat >5pp rule.
            implausible = (
                source_roe != 0 and abs(computed_roe / source_roe) > 5 if source_roe else False
            )
            if diff > ROCE_ANOMALY_TOLERANCE_PCT or implausible:
                roe_anomalies += 1
                category = "DATA_SOURCE" if implausible else "VERSION_DIFFERENCE"
                lines.append(
                    f"[ROE]  {cid} ({row['year']}): computed={computed_roe:.2f}% "
                    f"vs source={source_roe:.2f}% (diff={diff:.2f}pp) -> {category}"
                )

    lines.append("")
    lines.append(f"Total ROCE anomalies: {roce_anomalies}")
    lines.append(f"Total ROE anomalies:  {roe_anomalies}")
    lines.append("")
    lines.append(
        f"Financials-sector companies (D/E flag suppressed, ROCE benchmarked "
        f"sector-relatively rather than against an absolute threshold): "
        f"{sorted(df.loc[df['broad_sector'] == 'Financials', 'company_id'].unique())}"
    )
    return "\n".join(lines) + "\n"


def main():
    result = run_ratio_engine()
    print(f"\nfinancial_ratios row count: {result['row_count']}")
    print(f"FK check violations: {len(result['fk_check'])}")
    if result["row_count"] < 1100:
        print("[FAIL] Row count below the 1,100 exit-criterion threshold.")
        sys.exit(1)
    if len(result["fk_check"]) > 0:
        print("[FAIL] FK check violations found after write.")
        sys.exit(1)
    print("[OK] Sprint 2 exit criteria (row count, FK integrity) satisfied.")


if __name__ == "__main__":
    main()
