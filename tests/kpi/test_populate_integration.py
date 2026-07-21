"""
tests/kpi/test_populate_integration.py

Sprint 2, Day 12-14 — integration tests that run the full Ratio Engine
against the real database (built by Sprint 1's loader) and assert the
Sprint 2 Definition of Done / exit criteria:

  - SELECT COUNT(*) FROM financial_ratios >= 1,100 rows
  - All 14+ required KPI columns populated — zero null-only columns
  - ratio_edge_cases.log exists with documented entries
  - output/capital_allocation.csv exists with a valid 8-pattern label
    for every row
  - Manual spot-check: recomputing ROE / 5yr revenue CAGR by hand for a
    few companies matches the database value within 0.1%
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.analytics.populate_financial_ratios import run_ratio_engine
from src.etl.config import DB_PATH, OUTPUT_DIR
from src.etl.loader import build_database

REQUIRED_KPI_COLUMNS = [
    "net_profit_margin_pct",
    "operating_profit_margin_pct",
    "return_on_equity_pct",
    "debt_to_equity",
    "interest_coverage",
    "asset_turnover",
    "free_cash_flow_cr",
    "capex_cr",
    "earnings_per_share",
    "book_value_per_share",
    "dividend_payout_ratio_pct",
    "total_debt_cr",
    "cash_from_operations_cr",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "eps_cagr_5yr",
    "composite_quality_score",
]

VALID_PATTERN_LABELS = {
    "Reinvestor",
    "Shareholder Returns",
    "Liquidating Assets",
    "Distress Signal",
    "Growth Funded by Debt",
    "Cash Accumulator",
    "Pre-Revenue",
    "Mixed",
    "Unclassified",
}


@pytest.fixture(scope="module")
def engine_result():
    build_database()  # Sprint 1 must run first to (re)create the schema/tables
    return run_ratio_engine()


class TestExitCriteria:
    def test_row_count_at_least_1100(self, engine_result):
        assert engine_result["row_count"] >= 1100

    def test_fk_check_zero_violations(self, engine_result):
        assert engine_result["fk_check"] == []

    def test_all_required_kpi_columns_populated(self, engine_result):
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT * FROM financial_ratios", conn)
        conn.close()
        for col in REQUIRED_KPI_COLUMNS:
            assert col in df.columns, f"Missing column: {col}"
            non_null = df[col].notna().sum()
            assert non_null > 0, f"Column {col} is entirely NULL"

    def test_composite_quality_score_never_null(self, engine_result):
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT composite_quality_score FROM financial_ratios", conn)
        conn.close()
        assert df["composite_quality_score"].notna().all()

    def test_composite_quality_score_in_valid_range(self, engine_result):
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT composite_quality_score FROM financial_ratios", conn)
        conn.close()
        assert (df["composite_quality_score"] >= 0).all()
        assert (df["composite_quality_score"] <= 100).all()

    def test_ratio_edge_cases_log_exists_and_documented(self, engine_result):
        path = OUTPUT_DIR / "ratio_edge_cases.log"
        assert path.exists()
        content = path.read_text()
        assert "ROCE anomalies" in content
        assert "ROE anomalies" in content
        # Every anomaly line should carry one of the three documented categories.
        for line in content.splitlines():
            if line.startswith("[ROCE]") or line.startswith("[ROE]"):
                assert any(
                    cat in line
                    for cat in ("DATA_SOURCE", "VERSION_DIFFERENCE", "FORMULA_DISCREPANCY")
                ), f"Undocumented anomaly category: {line}"

    def test_capital_allocation_csv_exists_with_valid_labels(self, engine_result):
        path = OUTPUT_DIR / "capital_allocation.csv"
        assert path.exists()
        df = pd.read_csv(path)
        expected_cols = {"company_id", "year", "cfo_sign", "cfi_sign", "cff_sign", "pattern_label"}
        assert expected_cols.issubset(set(df.columns))
        assert set(df["pattern_label"].unique()).issubset(VALID_PATTERN_LABELS)
        assert set(df["cfo_sign"].unique()).issubset({"+", "-"})

    def test_debt_free_companies_have_icr_label(self, engine_result):
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql(
            "SELECT interest_coverage, icr_label FROM financial_ratios "
            "WHERE icr_label = 'Debt Free'",
            conn,
        )
        conn.close()
        assert len(df) > 0  # at least some debt-free company-years exist
        assert df["interest_coverage"].isna().all()

    def test_financials_sector_never_flagged_high_leverage(self, engine_result):
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql(
            "SELECT f.high_leverage_flag FROM financial_ratios f "
            "JOIN sectors s ON f.company_id = s.company_id "
            "WHERE s.broad_sector = 'Financials'",
            conn,
        )
        conn.close()
        assert (df["high_leverage_flag"] == 0).all()


class TestManualSpotCheck:
    """Day 12 — recompute ROE and 5yr Revenue CAGR by hand for 3 companies
    and compare to the database value (must match within 0.1%)."""

    @staticmethod
    @pytest.fixture(scope="class")
    def raw_data():
        conn = sqlite3.connect(DB_PATH)
        pnl = pd.read_sql("SELECT * FROM profitandloss", conn)
        bs = pd.read_sql("SELECT * FROM balancesheet", conn)
        fr = pd.read_sql("SELECT * FROM financial_ratios", conn)
        conn.close()
        return pnl, bs, fr

    @pytest.mark.parametrize("company_id", ["TCS", "RELIANCE", "HDFCBANK"])
    def test_roe_matches_manual_calc(self, engine_result, raw_data, company_id):
        pnl, bs, fr = raw_data
        pnl_row = pnl[pnl.company_id == company_id].sort_values("year").iloc[-1]
        bs_row = bs[(bs.company_id == company_id) & (bs.year == pnl_row["year"])]
        if bs_row.empty:
            pytest.skip(f"No matching BS row for {company_id} {pnl_row['year']}")
        bs_row = bs_row.iloc[0]

        net_worth = bs_row["equity_capital"] + bs_row["reserves"]
        if net_worth <= 0:
            pytest.skip(f"{company_id} has non-positive net worth; ROE undefined")
        manual_roe = (pnl_row["net_profit"] / net_worth) * 100

        db_row = fr[(fr.company_id == company_id) & (fr.year == pnl_row["year"])]
        assert not db_row.empty
        db_roe = db_row.iloc[0]["return_on_equity_pct"]

        assert db_roe == pytest.approx(manual_roe, abs=abs(manual_roe) * 0.001 + 1e-6)

    @pytest.mark.parametrize("company_id", ["TCS", "RELIANCE", "HDFCBANK"])
    def test_revenue_cagr_5yr_matches_manual_calc(self, engine_result, raw_data, company_id):
        pnl, bs, fr = raw_data
        company_pnl = pnl[pnl.company_id == company_id].sort_values("year").reset_index(drop=True)
        if len(company_pnl) < 6:
            pytest.skip(f"{company_id} has < 6 years of P&L history")

        end_row = company_pnl.iloc[-1]
        start_row = company_pnl.iloc[-6]
        if start_row["sales"] <= 0 or end_row["sales"] <= 0:
            pytest.skip(f"{company_id} sales non-positive in window; CAGR edge case")

        manual_cagr = ((end_row["sales"] / start_row["sales"]) ** (1 / 5) - 1) * 100

        db_row = fr[(fr.company_id == company_id) & (fr.year == end_row["year"])]
        assert not db_row.empty
        db_cagr = db_row.iloc[0]["revenue_cagr_5yr"]

        assert db_cagr == pytest.approx(manual_cagr, abs=abs(manual_cagr) * 0.001 + 1e-6)
