"""
src/etl/validator.py

Schema / data-quality validator implementing the 16 DQ rules (DQ-01..DQ-16)
defined in Section 14 of the project spec.

Design:
    Each rule is implemented as a function that takes the relevant
    already-normalised DataFrame(s) and yields Violation records. The loader
    calls `run_all_rules()` once all core tables have been normalised (but
    BEFORE final dedup/write for the CRITICAL PK/FK rules, and after, for
    row-level WARNING rules — see loader.py for exact sequencing) and
    receives back a single DataFrame that is written to
    output/validation_failures.csv.

Severity handling:
    CRITICAL -> loader halts the load OR rejects the offending rows
                (see action column in the spec table).
    WARNING  -> row is flagged and logged, but NOT rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
import requests

from src.etl.constants import (
    BALANCE_SHEET_TOLERANCE_PCT,
    BANK_TICKERS,
    COVERAGE_MIN_YEARS_CAGR,
    COVERAGE_MIN_YEARS_FLAG,
    DIVIDEND_PAYOUT_MAX_PCT,
    DQ_CRITICAL,
    DQ_WARNING,
    NET_CASH_TOLERANCE_CR,
    OPM_CROSS_CHECK_TOLERANCE_PP,
    TAX_RATE_MAX_PCT,
    TAX_RATE_MIN_PCT,
)


@dataclass
class Violation:
    rule_id: str
    rule_name: str
    severity: str  # 'CRITICAL' | 'WARNING' | 'INFO'
    table: str
    company_id: Optional[str] = None
    year: Optional[str] = None
    field: Optional[str] = None
    issue: str = ""

    def as_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity,
            "table": self.table,
            "company_id": self.company_id,
            "year": self.year,
            "field": self.field,
            "issue": self.issue,
        }


class ValidationResult:
    """Accumulates Violation records across all rules and tables."""

    def __init__(self):
        self.violations: List[Violation] = []

    def add(self, v: Violation):
        self.violations.append(v)

    def extend(self, vs: List[Violation]):
        self.violations.extend(vs)

    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == DQ_CRITICAL)

    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == DQ_WARNING)

    def to_dataframe(self) -> pd.DataFrame:
        cols = ["rule_id", "rule_name", "severity", "table", "company_id", "year", "field", "issue"]
        if not self.violations:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame([v.as_dict() for v in self.violations])[cols]


# ---------------------------------------------------------------------------
# DQ-01 — Company PK Uniqueness (CRITICAL)
# ---------------------------------------------------------------------------
def dq01_company_pk_uniqueness(companies: pd.DataFrame) -> List[Violation]:
    violations = []
    dupes = companies["id"][companies["id"].duplicated(keep=False)]
    for tid in sorted(set(dupes)):
        violations.append(
            Violation(
                "DQ-01",
                "Company PK Uniqueness",
                DQ_CRITICAL,
                "companies",
                company_id=tid,
                issue=f"Duplicate company id '{tid}' appears "
                f"{int((companies['id'] == tid).sum())} times.",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# DQ-02 — Annual PK Uniqueness in P&L / BS / CF (CRITICAL -> dedup action)
# ---------------------------------------------------------------------------
def dq02_annual_pk_uniqueness(df: pd.DataFrame, table: str) -> List[Violation]:
    violations = []
    dupe_mask = df.duplicated(subset=["company_id", "year"], keep=False)
    for _, row in df[dupe_mask].iterrows():
        violations.append(
            Violation(
                "DQ-02",
                "Annual PK Uniqueness",
                DQ_CRITICAL,
                table,
                company_id=row["company_id"],
                year=row["year"],
                issue=f"Duplicate (company_id, year) in {table}; "
                f"deduplicated, keeping last occurrence.",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# DQ-03 — FK Integrity: child.company_id must exist in companies.id (CRITICAL)
# ---------------------------------------------------------------------------
def dq03_fk_integrity(df: pd.DataFrame, table: str, valid_ids: set) -> List[Violation]:
    violations = []
    orphans = df[~df["company_id"].isin(valid_ids)]
    for _, row in orphans.iterrows():
        violations.append(
            Violation(
                "DQ-03",
                "FK Integrity",
                DQ_CRITICAL,
                table,
                company_id=row.get("company_id"),
                year=row.get("year"),
                issue=f"company_id '{row.get('company_id')}' in {table} "
                f"has no matching row in companies. Row rejected.",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# DQ-04 — Balance Sheet Balance (WARNING)
# ---------------------------------------------------------------------------
def dq04_balance_sheet_balance(bs: pd.DataFrame) -> List[Violation]:
    violations = []
    import numpy as np

    ta = bs["total_assets"].astype(float)
    tl = bs["total_liabilities"].astype(float)
    denom = ta.replace(0, np.nan)
    pct_diff = (ta - tl).abs() / denom
    pct_diff = pct_diff.replace([np.inf, -np.inf], np.nan)
    bad = (pct_diff > BALANCE_SHEET_TOLERANCE_PCT).fillna(False)
    for idx in bs[bad].index:
        row = bs.loc[idx]
        violations.append(
            Violation(
                "DQ-04",
                "Balance Sheet Balance",
                DQ_WARNING,
                "balancesheet",
                company_id=row["company_id"],
                year=row["year"],
                field="total_assets/total_liabilities",
                issue=f"total_assets ({row['total_assets']}) vs "
                f"total_liabilities ({row['total_liabilities']}) differ "
                f"by >1%.",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# DQ-05 — OPM Cross-Check (WARNING)
# ---------------------------------------------------------------------------
def dq05_opm_cross_check(pnl: pd.DataFrame) -> List[Violation]:
    violations = []
    import numpy as np

    sales = pnl["sales"].astype(float)
    op = pnl["operating_profit"].astype(float)
    opm_src = pnl["opm_percentage"].astype(float)
    computed = (op / sales.replace(0, np.nan)) * 100
    diff = (opm_src - computed).abs()
    bad = (diff > OPM_CROSS_CHECK_TOLERANCE_PP).fillna(False)
    for idx in pnl[bad].index:
        row = pnl.loc[idx]
        violations.append(
            Violation(
                "DQ-05",
                "OPM Cross-Check",
                DQ_WARNING,
                "profitandloss",
                company_id=row["company_id"],
                year=row["year"],
                field="opm_percentage",
                issue=f"Source OPM {row['opm_percentage']}% vs computed "
                f"{computed.loc[idx]:.2f}% differ by >1pp.",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# DQ-06 — Positive Sales (WARNING, non-bank companies)
# ---------------------------------------------------------------------------
def dq06_positive_sales(pnl: pd.DataFrame, bank_ids: set) -> List[Violation]:
    violations = []
    mask = (pnl["sales"].astype(float) <= 0) & (~pnl["company_id"].isin(bank_ids))
    for idx in pnl[mask].index:
        row = pnl.loc[idx]
        violations.append(
            Violation(
                "DQ-06",
                "Positive Sales",
                DQ_WARNING,
                "profitandloss",
                company_id=row["company_id"],
                year=row["year"],
                field="sales",
                issue=f"sales = {row['sales']} (<= 0) for non-bank company. "
                f"Excluded from growth CAGR.",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# DQ-07 — Year Format (CRITICAL -> reject row if unparseable)
#   Applied inline during normalisation in loader.py (raw values that
#   normalize_year() returns None for are logged here).
# ---------------------------------------------------------------------------
def dq07_year_format(table: str, company_id, raw_year) -> Violation:
    return Violation(
        "DQ-07",
        "Year Format",
        DQ_CRITICAL,
        table,
        company_id=company_id,
        year=None,
        field="year",
        issue=f"Raw year value '{raw_year}' could not be parsed to " f"YYYY-MM. Row rejected.",
    )


# ---------------------------------------------------------------------------
# DQ-08 — Ticker Format (CRITICAL if out of 2-12 char range after normalise)
# ---------------------------------------------------------------------------
def dq08_ticker_format(table: str, raw_id) -> Violation:
    return Violation(
        "DQ-08",
        "Ticker Format",
        DQ_CRITICAL,
        table,
        company_id=str(raw_id),
        field="company_id",
        issue=f"Raw company_id '{raw_id}' failed normalisation "
        f"(empty, or outside 2-12 char band, or invalid characters). "
        f"Row rejected.",
    )


# ---------------------------------------------------------------------------
# DQ-09 — Net Cash Check (WARNING, tolerance 10 Cr)
# ---------------------------------------------------------------------------
def dq09_net_cash_check(cf: pd.DataFrame) -> List[Violation]:
    violations = []
    computed = (
        cf["operating_activity"].astype(float)
        + cf["investing_activity"].astype(float)
        + cf["financing_activity"].astype(float)
    )
    diff = (cf["net_cash_flow"].astype(float) - computed).abs()
    bad = diff > NET_CASH_TOLERANCE_CR
    for idx in cf[bad].index:
        row = cf.loc[idx]
        violations.append(
            Violation(
                "DQ-09",
                "Net Cash Check",
                DQ_WARNING,
                "cashflow",
                company_id=row["company_id"],
                year=row["year"],
                field="net_cash_flow",
                issue=f"net_cash_flow {row['net_cash_flow']} vs "
                f"CFO+CFI+CFF {computed.loc[idx]:.1f} differ by "
                f">10 Cr. Recomputed from components.",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# DQ-10 — Non-Negative Fixed Assets (WARNING -> coerce to 0)
# ---------------------------------------------------------------------------
def dq10_non_negative_fixed_assets(bs: pd.DataFrame) -> List[Violation]:
    violations = []
    mask = bs["fixed_assets"].astype(float) < 0
    for idx in bs[mask].index:
        row = bs.loc[idx]
        violations.append(
            Violation(
                "DQ-10",
                "Non-Negative Fixed Assets",
                DQ_WARNING,
                "balancesheet",
                company_id=row["company_id"],
                year=row["year"],
                field="fixed_assets",
                issue=f"fixed_assets = {row['fixed_assets']} (<0). " f"Coerced to 0.",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# DQ-11 — Tax Rate Range (WARNING, 0-60%)
# ---------------------------------------------------------------------------
def dq11_tax_rate_range(pnl: pd.DataFrame) -> List[Violation]:
    violations = []
    tax = pnl["tax_percentage"].astype(float)
    mask = ((tax < TAX_RATE_MIN_PCT) | (tax > TAX_RATE_MAX_PCT)) & tax.notna()
    for idx in pnl[mask].index:
        row = pnl.loc[idx]
        violations.append(
            Violation(
                "DQ-11",
                "Tax Rate Range",
                DQ_WARNING,
                "profitandloss",
                company_id=row["company_id"],
                year=row["year"],
                field="tax_percentage",
                issue=f"tax_percentage = {row['tax_percentage']} outside "
                f"[0, 60]. May indicate one-off deferred tax reversal.",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# DQ-12 — Dividend Payout Cap (WARNING, <= 200%)
# ---------------------------------------------------------------------------
def dq12_dividend_payout_cap(pnl: pd.DataFrame) -> List[Violation]:
    violations = []
    dp = pnl["dividend_payout"].astype(float)
    mask = (dp > DIVIDEND_PAYOUT_MAX_PCT) & dp.notna()
    for idx in pnl[mask].index:
        row = pnl.loc[idx]
        violations.append(
            Violation(
                "DQ-12",
                "Dividend Payout Cap",
                DQ_WARNING,
                "profitandloss",
                company_id=row["company_id"],
                year=row["year"],
                field="dividend_payout",
                issue=f"dividend_payout = {row['dividend_payout']}% (>200%). "
                f"Likely data entry error; analyst confirmation required.",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# DQ-13 — URL Validity for documents.xlsx (WARNING)
#   Network validation is OPTIONAL / off by default (slow, 1585 URLs, and
#   this sandbox's egress allowlist does not include bseindia.com). The
#   function is implemented for completeness and can be enabled via
#   loader.py's --validate-urls flag when run in an environment with
#   unrestricted network access.
# ---------------------------------------------------------------------------
def dq13_url_validity(docs: pd.DataFrame, timeout: float = 5.0) -> List[Violation]:
    violations = []
    for idx, row in docs.iterrows():
        url = row.get("annual_report_url")
        if not url:
            continue
        try:
            resp = requests.head(url, timeout=timeout, allow_redirects=True)
            status = resp.status_code
        except Exception:
            status = None
        if status != 200:
            violations.append(
                Violation(
                    "DQ-13",
                    "URL Validity",
                    DQ_WARNING,
                    "documents",
                    company_id=row["company_id"],
                    year=str(row["year"]),
                    field="annual_report_url",
                    issue=f"URL returned status {status} (expected 200). "
                    f"URL decay expected over time; row not rejected.",
                )
            )
    return violations


# ---------------------------------------------------------------------------
# DQ-14 — EPS Sign Consistency (WARNING)
# ---------------------------------------------------------------------------
def dq14_eps_sign_consistency(pnl: pd.DataFrame) -> List[Violation]:
    violations = []
    net_profit = pnl["net_profit"].astype(float)
    eps = pnl["eps"].astype(float)
    mask = (net_profit > 0) & (eps <= 0) & eps.notna() & net_profit.notna()
    for idx in pnl[mask].index:
        row = pnl.loc[idx]
        violations.append(
            Violation(
                "DQ-14",
                "EPS Sign Consistency",
                DQ_WARNING,
                "profitandloss",
                company_id=row["company_id"],
                year=row["year"],
                field="eps",
                issue=f"net_profit = {row['net_profit']} (positive) but "
                f"eps = {row['eps']} (<= 0). May indicate adjustments; "
                f"use net_profit/shares as fallback.",
            )
        )
    return violations


# ---------------------------------------------------------------------------
# DQ-15 — BSE/ASE Balance, strict (Informational — counted only, not
#   surfaced as a per-row violation; recorded once as a summary count in
#   load_audit.csv by the loader).
# ---------------------------------------------------------------------------
def dq15_strict_balance_count(bs: pd.DataFrame) -> int:
    """Returns count of rows where total_liabilities == total_assets exactly
    (after DQ-04 tolerance flag), for informational reporting only."""
    ta = bs["total_assets"].astype(float)
    tl = bs["total_liabilities"].astype(float)
    return int((ta == tl).sum())


# ---------------------------------------------------------------------------
# DQ-16 — Coverage Check (WARNING, < 5yr history flagged; < 3yr excluded
#   from CAGR downstream in the Ratio Engine)
# ---------------------------------------------------------------------------
def dq16_coverage_check(pnl: pd.DataFrame, bs: pd.DataFrame, cf: pd.DataFrame) -> List[Violation]:
    violations = []
    all_ids = set(pnl["company_id"]) | set(bs["company_id"]) | set(cf["company_id"])
    pnl_counts = pnl.groupby("company_id")["year"].nunique()
    bs_counts = bs.groupby("company_id")["year"].nunique()
    cf_counts = cf.groupby("company_id")["year"].nunique()
    for cid in sorted(all_ids):
        n_pnl = int(pnl_counts.get(cid, 0))
        n_bs = int(bs_counts.get(cid, 0))
        n_cf = int(cf_counts.get(cid, 0))
        min_years = min(n_pnl, n_bs, n_cf)
        if min_years < COVERAGE_MIN_YEARS_FLAG:
            violations.append(
                Violation(
                    "DQ-16",
                    "Coverage Check",
                    DQ_WARNING,
                    "multi",
                    company_id=cid,
                    issue=f"Company has < {COVERAGE_MIN_YEARS_FLAG} years of history "
                    f"(P&L={n_pnl}, BS={n_bs}, CF={n_cf}, min={min_years}). "
                    f"{'Excluded from CAGR (< ' + str(COVERAGE_MIN_YEARS_CAGR) + 'yr).' if min_years < COVERAGE_MIN_YEARS_CAGR else 'Flagged for review.'}",
                )
            )
    return violations


# ---------------------------------------------------------------------------
# Orchestrator — runs the row-level (post-normalisation, post-dedup) rules
# that don't require special sequencing in loader.py. DQ-01/02/03/07/08 are
# structural and are invoked directly from loader.py at the point in the
# pipeline where they're actionable (PK checks need the deduped frame, FK
# checks need `companies` loaded first, year/ticker format checks happen
# during normalisation itself). This function covers the remaining
# straightforward WARNING/INFO rules (DQ-04..DQ-06, DQ-09..DQ-12, DQ-14,
# DQ-16) that can run in one pass once tables are normalised and deduped.
# ---------------------------------------------------------------------------
def run_post_normalisation_rules(
    pnl: pd.DataFrame, bs: pd.DataFrame, cf: pd.DataFrame
) -> ValidationResult:
    result = ValidationResult()
    result.extend(dq04_balance_sheet_balance(bs))
    result.extend(dq05_opm_cross_check(pnl))
    result.extend(dq06_positive_sales(pnl, BANK_TICKERS))
    result.extend(dq09_net_cash_check(cf))
    result.extend(dq10_non_negative_fixed_assets(bs))
    result.extend(dq11_tax_rate_range(pnl))
    result.extend(dq12_dividend_payout_cap(pnl))
    result.extend(dq14_eps_sign_consistency(pnl))
    result.extend(dq16_coverage_check(pnl, bs, cf))
    return result
