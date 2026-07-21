"""
src/etl/loader.py

Module 1 — Data Ingestion & ETL. Reads all 7 core + 5 supplementary Excel
files, normalises company_id/year fields, runs the 16 DQ rules, writes a
10/12-table SQLite database, and emits load_audit.csv + validation_failures.csv.

Usage:
    python src/etl/loader.py
    # or: make load

Idempotent: re-running drops and rebuilds all tables from db/schema.sql.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.etl.config import (
    DB_PATH,
    LOG_PATH,
    OUTPUT_DIR,
    RAW_DIR,
    SCHEMA_PATH,
    SUPP_DIR,
    VALIDATE_URLS,
)
from src.etl.constants import TABLE_WRITE_ORDER
from src.etl.logging_setup import get_logger
from src.etl.normaliser import normalize_ticker, normalize_year, parse_period_pct
from src.etl.validator import (
    ValidationResult,
    dq01_company_pk_uniqueness,
    dq02_annual_pk_uniqueness,
    dq03_fk_integrity,
    dq07_year_format,
    dq08_ticker_format,
    dq15_strict_balance_count,
    run_post_normalisation_rules,
)

log = get_logger(__name__)


class LoadAuditRow:
    def __init__(self, table, rows_in, rows_out, rejected, runtime_s, notes=""):
        self.table = table
        self.rows_in = rows_in
        self.rows_out = rows_out
        self.rejected = rejected
        self.runtime_s = round(runtime_s, 3)
        self.notes = notes

    def as_dict(self):
        return {
            "table": self.table,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "rejected": self.rejected,
            "runtime_s": self.runtime_s,
            "notes": self.notes,
            "timestamp": pd.Timestamp.now().isoformat(timespec="seconds"),
        }


def _normalise_ticker_column(
    df: pd.DataFrame, col: str, table: str, vresult: ValidationResult
) -> pd.DataFrame:
    """Normalise a ticker column in-place-ish; rows that fail -> DQ-08 + dropped."""
    raw = df[col]
    normed = raw.map(normalize_ticker)
    bad_mask = normed.isna()
    for raw_val in raw[bad_mask]:
        vresult.add(dq08_ticker_format(table, raw_val))
    df = df.loc[~bad_mask].copy()
    df[col] = normed[~bad_mask]
    return df


def _normalise_year_column(
    df: pd.DataFrame, col: str, table: str, vresult: ValidationResult
) -> pd.DataFrame:
    """Normalise a year/period column; rows that fail -> DQ-07 + dropped."""
    raw = df[col]
    normed = raw.map(normalize_year)
    bad_mask = normed.isna()
    for i in df[bad_mask].index:
        vresult.add(dq07_year_format(table, df.loc[i].get("company_id"), raw.loc[i]))
    df = df.loc[~bad_mask].copy()
    df[col] = normed[~bad_mask]
    return df


def _dedupe_annual_pk(df: pd.DataFrame, table: str, vresult: ValidationResult) -> pd.DataFrame:
    """DQ-02: log duplicates, then keep last occurrence."""
    vresult.extend(dq02_annual_pk_uniqueness(df, table))
    return df.drop_duplicates(subset=["company_id", "year"], keep="last")


def _apply_fk_integrity(
    df: pd.DataFrame, table: str, valid_ids: Set[str], vresult: ValidationResult
) -> pd.DataFrame:
    """DQ-03: log + reject orphan rows whose company_id isn't in companies."""
    vresult.extend(dq03_fk_integrity(df, table, valid_ids))
    return df[df["company_id"].isin(valid_ids)].copy()


# ---------------------------------------------------------------------------
# Individual file loaders
# ---------------------------------------------------------------------------
def load_companies(vresult: ValidationResult) -> Tuple[pd.DataFrame, LoadAuditRow]:
    t0 = time.time()
    path = RAW_DIR / "companies.xlsx"
    df = pd.read_excel(path, header=1)
    rows_in = len(df)

    df = _normalise_ticker_column(df, "id", "companies", vresult)
    rejected_ticker = rows_in - len(df)

    df["company_name"] = (
        df["company_name"].astype(str).str.replace("\n", " ", regex=False).str.strip()
    )

    vresult.extend(dq01_company_pk_uniqueness(df))
    df = df.drop_duplicates(subset=["id"], keep="last")

    audit = LoadAuditRow("companies", rows_in, len(df), rejected_ticker, time.time() - t0)
    return df, audit


def load_profitandloss(
    vresult: ValidationResult, valid_ids: Set[str]
) -> Tuple[pd.DataFrame, LoadAuditRow]:
    t0 = time.time()
    path = RAW_DIR / "profitandloss.xlsx"
    df = pd.read_excel(path, header=1)
    rows_in = len(df)

    df = _normalise_ticker_column(df, "company_id", "profitandloss", vresult)
    df = _normalise_year_column(df, "year", "profitandloss", vresult)
    df = _apply_fk_integrity(df, "profitandloss", valid_ids, vresult)
    df = _dedupe_annual_pk(df, "profitandloss", vresult)

    rejected = rows_in - len(df)
    audit = LoadAuditRow("profitandloss", rows_in, len(df), rejected, time.time() - t0)
    return df, audit


def load_balancesheet(
    vresult: ValidationResult, valid_ids: Set[str]
) -> Tuple[pd.DataFrame, LoadAuditRow]:
    t0 = time.time()
    path = RAW_DIR / "balancesheet.xlsx"
    df = pd.read_excel(path, header=1)
    rows_in = len(df)

    df = _normalise_ticker_column(df, "company_id", "balancesheet", vresult)
    df = _normalise_year_column(df, "year", "balancesheet", vresult)
    df = _apply_fk_integrity(df, "balancesheet", valid_ids, vresult)
    df = _dedupe_annual_pk(df, "balancesheet", vresult)

    # DQ-10: coerce negative fixed_assets to 0 (violation already logged by
    # run_post_normalisation_rules; this applies the corrective action).
    neg_mask = df["fixed_assets"].astype(float) < 0
    df.loc[neg_mask, "fixed_assets"] = 0

    rejected = rows_in - len(df)
    audit = LoadAuditRow("balancesheet", rows_in, len(df), rejected, time.time() - t0)
    return df, audit


def load_cashflow(
    vresult: ValidationResult, valid_ids: Set[str]
) -> Tuple[pd.DataFrame, LoadAuditRow]:
    t0 = time.time()
    path = RAW_DIR / "cashflow.xlsx"
    df = pd.read_excel(path, header=1)
    rows_in = len(df)

    df = _normalise_ticker_column(df, "company_id", "cashflow", vresult)
    df = _normalise_year_column(df, "year", "cashflow", vresult)
    df = _apply_fk_integrity(df, "cashflow", valid_ids, vresult)
    df = _dedupe_annual_pk(df, "cashflow", vresult)

    rejected = rows_in - len(df)
    audit = LoadAuditRow("cashflow", rows_in, len(df), rejected, time.time() - t0)
    return df, audit


def load_analysis(
    vresult: ValidationResult, valid_ids: Set[str]
) -> Tuple[pd.DataFrame, LoadAuditRow]:
    t0 = time.time()
    path = RAW_DIR / "analysis.xlsx"
    df = pd.read_excel(path, header=1)
    rows_in = len(df)

    df = _normalise_ticker_column(df, "company_id", "analysis", vresult)
    df = _apply_fk_integrity(df, "analysis", valid_ids, vresult)
    df = df.drop_duplicates(subset=["company_id"], keep="last")

    for raw_col, y_col, p_col in [
        ("compounded_sales_growth", "compounded_sales_growth_years", "compounded_sales_growth_pct"),
        (
            "compounded_profit_growth",
            "compounded_profit_growth_years",
            "compounded_profit_growth_pct",
        ),
        ("stock_price_cagr", "stock_price_cagr_years", "stock_price_cagr_pct"),
        ("roe", "roe_years", "roe_pct"),
    ]:
        parsed = df[raw_col].map(parse_period_pct)
        df[y_col] = parsed.map(lambda t: t[0])
        df[p_col] = parsed.map(lambda t: t[1])
        df = df.rename(columns={raw_col: f"{raw_col}_raw"})

    rejected = rows_in - len(df)
    audit = LoadAuditRow("analysis", rows_in, len(df), rejected, time.time() - t0)
    return df, audit


def load_documents(
    vresult: ValidationResult, valid_ids: Set[str]
) -> Tuple[pd.DataFrame, LoadAuditRow]:
    t0 = time.time()
    path = RAW_DIR / "documents.xlsx"
    df = pd.read_excel(path, header=1)
    rows_in = len(df)

    df = df.rename(columns={"Year": "year", "Annual_Report": "annual_report_url"})
    df = _normalise_ticker_column(df, "company_id", "documents", vresult)
    df = _apply_fk_integrity(df, "documents", valid_ids, vresult)
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["year"])
    df["url_status_code"] = pd.NA
    df = df.drop_duplicates(subset=["company_id", "year", "id"], keep="last")

    rejected = rows_in - len(df)
    audit = LoadAuditRow("documents", rows_in, len(df), rejected, time.time() - t0)
    return df, audit


def load_prosandcons(
    vresult: ValidationResult, valid_ids: Set[str]
) -> Tuple[pd.DataFrame, LoadAuditRow]:
    t0 = time.time()
    path = RAW_DIR / "prosandcons.xlsx"
    df = pd.read_excel(path, header=1)
    rows_in = len(df)

    df = _normalise_ticker_column(df, "company_id", "prosandcons", vresult)
    df = _apply_fk_integrity(df, "prosandcons", valid_ids, vresult)
    df = df.drop_duplicates(subset=["id"], keep="last")

    rejected = rows_in - len(df)
    audit = LoadAuditRow("prosandcons", rows_in, len(df), rejected, time.time() - t0)
    return df, audit


def load_sectors(
    vresult: ValidationResult, valid_ids: Set[str]
) -> Tuple[pd.DataFrame, LoadAuditRow]:
    t0 = time.time()
    path = SUPP_DIR / "sectors.xlsx"
    df = pd.read_excel(path, header=0)
    rows_in = len(df)

    df = _normalise_ticker_column(df, "company_id", "sectors", vresult)
    df = _apply_fk_integrity(df, "sectors", valid_ids, vresult)
    df = df.drop_duplicates(subset=["company_id"], keep="last")

    rejected = rows_in - len(df)
    audit = LoadAuditRow("sectors", rows_in, len(df), rejected, time.time() - t0)
    return df, audit


def load_stock_prices(
    vresult: ValidationResult, valid_ids: Set[str]
) -> Tuple[pd.DataFrame, LoadAuditRow]:
    t0 = time.time()
    path = SUPP_DIR / "stock_prices.xlsx"
    df = pd.read_excel(path, header=0)
    rows_in = len(df)

    df = _normalise_ticker_column(df, "company_id", "stock_prices", vresult)
    df = _apply_fk_integrity(df, "stock_prices", valid_ids, vresult)
    df = df.drop_duplicates(subset=["company_id", "date"], keep="last")

    rejected = rows_in - len(df)
    audit = LoadAuditRow("stock_prices", rows_in, len(df), rejected, time.time() - t0)
    return df, audit


def load_market_cap(
    vresult: ValidationResult, valid_ids: Set[str]
) -> Tuple[pd.DataFrame, LoadAuditRow]:
    t0 = time.time()
    path = SUPP_DIR / "market_cap.xlsx"
    df = pd.read_excel(path, header=0)
    rows_in = len(df)

    df = _normalise_ticker_column(df, "company_id", "market_cap", vresult)
    df = _apply_fk_integrity(df, "market_cap", valid_ids, vresult)
    df = df.drop_duplicates(subset=["company_id", "year"], keep="last")

    rejected = rows_in - len(df)
    audit = LoadAuditRow("market_cap", rows_in, len(df), rejected, time.time() - t0)
    return df, audit


def load_financial_ratios(
    vresult: ValidationResult, valid_ids: Set[str]
) -> Tuple[pd.DataFrame, LoadAuditRow]:
    t0 = time.time()
    path = SUPP_DIR / "financial_ratios.xlsx"
    df = pd.read_excel(path, header=0)
    rows_in = len(df)

    df = _normalise_ticker_column(df, "company_id", "financial_ratios", vresult)
    df = _normalise_year_column(df, "year", "financial_ratios", vresult)
    df = _apply_fk_integrity(df, "financial_ratios", valid_ids, vresult)
    df = _dedupe_annual_pk(df, "financial_ratios", vresult)

    rejected = rows_in - len(df)
    audit = LoadAuditRow("financial_ratios", rows_in, len(df), rejected, time.time() - t0)
    return df, audit


def load_peer_groups(
    vresult: ValidationResult, valid_ids: Set[str]
) -> Tuple[pd.DataFrame, LoadAuditRow]:
    t0 = time.time()
    path = SUPP_DIR / "peer_groups.xlsx"
    df = pd.read_excel(path, header=0)
    rows_in = len(df)

    df = _normalise_ticker_column(df, "company_id", "peer_groups", vresult)
    df = _apply_fk_integrity(df, "peer_groups", valid_ids, vresult)
    df["is_benchmark"] = df["is_benchmark"].astype(bool).astype(int)
    df = df.drop_duplicates(subset=["id"], keep="last")

    rejected = rows_in - len(df)
    audit = LoadAuditRow("peer_groups", rows_in, len(df), rejected, time.time() - t0)
    return df, audit


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def build_database(validate_urls: bool = None) -> dict:
    """Run the full ETL pipeline. Returns a dict with the ValidationResult,
    the list of LoadAuditRow, and the row counts of each loaded table
    (useful for tests / the CLI summary)."""
    if validate_urls is None:
        validate_urls = VALIDATE_URLS

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.mkdir(parents=True, exist_ok=True)

    log.info("Starting ETL run (validate_urls=%s)", validate_urls)
    t_start = time.time()

    vresult = ValidationResult()
    audit_rows: List[LoadAuditRow] = []

    companies_df, a = load_companies(vresult)
    audit_rows.append(a)
    log.info("Loaded companies: %d rows (%d rejected)", len(companies_df), a.rejected)
    valid_ids = set(companies_df["id"])

    pnl_df, a = load_profitandloss(vresult, valid_ids)
    audit_rows.append(a)
    log.info("Loaded profitandloss: %d rows (%d rejected)", len(pnl_df), a.rejected)
    bs_df, a = load_balancesheet(vresult, valid_ids)
    audit_rows.append(a)
    log.info("Loaded balancesheet: %d rows (%d rejected)", len(bs_df), a.rejected)
    cf_df, a = load_cashflow(vresult, valid_ids)
    audit_rows.append(a)
    log.info("Loaded cashflow: %d rows (%d rejected)", len(cf_df), a.rejected)
    analysis_df, a = load_analysis(vresult, valid_ids)
    audit_rows.append(a)
    log.info("Loaded analysis: %d rows (%d rejected)", len(analysis_df), a.rejected)
    documents_df, a = load_documents(vresult, valid_ids)
    audit_rows.append(a)
    log.info("Loaded documents: %d rows (%d rejected)", len(documents_df), a.rejected)
    prosandcons_df, a = load_prosandcons(vresult, valid_ids)
    audit_rows.append(a)
    log.info("Loaded prosandcons: %d rows (%d rejected)", len(prosandcons_df), a.rejected)
    sectors_df, a = load_sectors(vresult, valid_ids)
    audit_rows.append(a)
    log.info("Loaded sectors: %d rows (%d rejected)", len(sectors_df), a.rejected)
    stock_prices_df, a = load_stock_prices(vresult, valid_ids)
    audit_rows.append(a)
    log.info("Loaded stock_prices: %d rows (%d rejected)", len(stock_prices_df), a.rejected)
    market_cap_df, a = load_market_cap(vresult, valid_ids)
    audit_rows.append(a)
    log.info("Loaded market_cap: %d rows (%d rejected)", len(market_cap_df), a.rejected)
    financial_ratios_df, a = load_financial_ratios(vresult, valid_ids)
    audit_rows.append(a)
    log.info("Loaded financial_ratios: %d rows (%d rejected)", len(financial_ratios_df), a.rejected)
    peer_groups_df, a = load_peer_groups(vresult, valid_ids)
    audit_rows.append(a)
    log.info("Loaded peer_groups: %d rows (%d rejected)", len(peer_groups_df), a.rejected)

    # Post-normalisation row-level DQ rules (DQ-04..06, 09..12, 14, 16)
    post_result = run_post_normalisation_rules(pnl_df, bs_df, cf_df)
    vresult.extend(post_result.violations)
    log.info("Post-normalisation DQ rules: %d violations", len(post_result.violations))

    # DQ-09 corrective action: recompute net_cash_flow from components where
    # mismatched beyond tolerance.
    computed_ncf = (
        cf_df["operating_activity"].astype(float)
        + cf_df["investing_activity"].astype(float)
        + cf_df["financing_activity"].astype(float)
    )
    mismatch = (cf_df["net_cash_flow"].astype(float) - computed_ncf).abs() > 10
    cf_df.loc[mismatch, "net_cash_flow"] = computed_ncf[mismatch]

    # DQ-15 informational count
    dq15_count = dq15_strict_balance_count(bs_df)

    if validate_urls:
        from src.etl.validator import dq13_url_validity

        log.info("Validating %d document URLs via HTTP HEAD...", len(documents_df))
        vresult.extend(dq13_url_validity(documents_df))

    # ---- Write to SQLite (single transaction, executemany bulk insert) ---
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")  # re-enabled after bulk load
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    table_map: Dict[str, pd.DataFrame] = {
        "companies": companies_df,
        "profitandloss": pnl_df,
        "balancesheet": bs_df,
        "cashflow": cf_df,
        "analysis": analysis_df,
        "documents": documents_df,
        "prosandcons": prosandcons_df,
        "sectors": sectors_df,
        "stock_prices": stock_prices_df,
        "market_cap": market_cap_df,
        "financial_ratios": financial_ratios_df,
        "peer_groups": peer_groups_df,
    }

    t_write = time.time()
    cur = conn.cursor()
    try:
        for table in TABLE_WRITE_ORDER:
            df = table_map[table]
            cols = [c[1] for c in cur.execute(f"PRAGMA table_info({table})").fetchall()]
            df_to_write = df.reindex(columns=cols)
            # Convert NaN -> None so sqlite stores NULL rather than 'nan'.
            records = df_to_write.where(pd.notnull(df_to_write), None).values.tolist()
            placeholders = ", ".join("?" for _ in cols)
            col_list = ", ".join(cols)
            cur.executemany(
                f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})",
                records,
            )
            log.info("Bulk-inserted %d rows into %s", len(records), table)
        conn.commit()
    except Exception:
        conn.rollback()
        log.exception("Bulk insert failed; transaction rolled back.")
        raise
    log.info("SQLite bulk write completed in %.3fs", time.time() - t_write)

    conn.execute("PRAGMA foreign_keys = ON")
    fk_check = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.commit()
    conn.close()

    # ---- Write load_audit.csv --------------------------------------------
    audit_df = pd.DataFrame([a.as_dict() for a in audit_rows])
    audit_df.loc[len(audit_df)] = {
        "table": "_summary_dq15_strict_balance_matches",
        "rows_in": dq15_count,
        "rows_out": dq15_count,
        "rejected": 0,
        "runtime_s": 0,
        "notes": "Rows where total_assets == total_liabilities exactly (DQ-15, informational).",
        "timestamp": pd.Timestamp.now().isoformat(timespec="seconds"),
    }
    audit_df.loc[len(audit_df)] = {
        "table": "_summary_fk_check",
        "rows_in": len(fk_check),
        "rows_out": 0,
        "rejected": len(fk_check),
        "runtime_s": 0,
        "notes": "PRAGMA foreign_key_check violations (should be 0).",
        "timestamp": pd.Timestamp.now().isoformat(timespec="seconds"),
    }
    audit_df.to_csv(OUTPUT_DIR / "load_audit.csv", index=False)
    log.info("Wrote %s", OUTPUT_DIR / "load_audit.csv")

    # ---- Write validation_failures.csv ------------------------------------
    vresult.to_dataframe().to_csv(OUTPUT_DIR / "validation_failures.csv", index=False)
    log.info("Wrote %s", OUTPUT_DIR / "validation_failures.csv")

    log.info(
        "ETL run complete in %.3fs — %d CRITICAL / %d WARNING DQ violations, "
        "%d FK check violations",
        time.time() - t_start,
        vresult.critical_count(),
        vresult.warning_count(),
        len(fk_check),
    )

    return {
        "vresult": vresult,
        "audit_rows": audit_rows,
        "fk_check": fk_check,
        "row_counts": {t: len(df) for t, df in table_map.items()},
        "dq15_count": dq15_count,
    }


def main():
    print(f"Building nifty100.db at {DB_PATH} ...")
    result = build_database()
    print(f"\n{'Table':<20}{'Rows':>10}")
    print("-" * 30)
    for t, n in result["row_counts"].items():
        print(f"{t:<20}{n:>10}")
    print("-" * 30)
    print(
        f"\nDQ violations: {result['vresult'].critical_count()} CRITICAL, "
        f"{result['vresult'].warning_count()} WARNING"
    )
    print(f"PRAGMA foreign_key_check violations: {len(result['fk_check'])}")
    print(f"\nWrote: {OUTPUT_DIR / 'load_audit.csv'}")
    print(f"Wrote: {OUTPUT_DIR / 'validation_failures.csv'}")
    print(f"Wrote: {DB_PATH}")

    if result["vresult"].critical_count() > 0:
        print(
            "\n[WARNING] CRITICAL data-quality violations were found "
            "(rows already rejected/deduped per DQ action rules). "
            "Review output/validation_failures.csv."
        )
    if len(result["fk_check"]) > 0:
        print(
            "\n[FAIL] Foreign key check found violations after load. "
            "This should not happen given FK enforcement in loaders."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
