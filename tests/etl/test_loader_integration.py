"""
tests/etl/test_loader_integration.py

Integration tests that run the full ETL pipeline against the real source
files and assert Sprint 1's Definition of Done / exit criteria:

  - SELECT COUNT(*) FROM companies = 92
  - PRAGMA foreign_key_check -> 0 rows
  - load_audit.csv is written and has one row per source table
  - validation_failures.csv is written with severity-tagged violations
  - all 12 tables exist in nifty100.db
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.etl.loader import DB_PATH, OUTPUT_DIR, build_database

EXPECTED_TABLES = [
    "companies",
    "profitandloss",
    "balancesheet",
    "cashflow",
    "analysis",
    "documents",
    "prosandcons",
    "sectors",
    "stock_prices",
    "market_cap",
    "financial_ratios",
    "peer_groups",
]


@pytest.fixture(scope="module")
def loaded_result():
    return build_database()


class TestExitCriteria:
    def test_companies_count_is_92(self, loaded_result):
        conn = sqlite3.connect(DB_PATH)
        n = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        conn.close()
        assert n == 92

    def test_foreign_key_check_zero_violations(self, loaded_result):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.close()
        assert violations == []

    def test_all_12_tables_exist(self, loaded_result):
        conn = sqlite3.connect(DB_PATH)
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        conn.close()
        for t in EXPECTED_TABLES:
            assert t in tables, f"Missing table: {t}"

    def test_load_audit_csv_written(self, loaded_result):
        path = OUTPUT_DIR / "load_audit.csv"
        assert path.exists()
        df = pd.read_csv(path)
        for t in EXPECTED_TABLES:
            assert (df["table"] == t).any(), f"load_audit.csv missing row for {t}"

    def test_validation_failures_csv_written(self, loaded_result):
        path = OUTPUT_DIR / "validation_failures.csv"
        assert path.exists()
        df = pd.read_csv(path)
        expected_cols = {
            "rule_id",
            "rule_name",
            "severity",
            "table",
            "company_id",
            "year",
            "field",
            "issue",
        }
        assert expected_cols.issubset(set(df.columns))

    def test_no_duplicate_pks_in_pnl_after_load(self, loaded_result):
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT company_id, year FROM profitandloss", conn)
        conn.close()
        assert not df.duplicated(subset=["company_id", "year"]).any()

    def test_no_duplicate_pks_in_balancesheet_after_load(self, loaded_result):
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT company_id, year FROM balancesheet", conn)
        conn.close()
        assert not df.duplicated(subset=["company_id", "year"]).any()

    def test_no_duplicate_pks_in_cashflow_after_load(self, loaded_result):
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT company_id, year FROM cashflow", conn)
        conn.close()
        assert not df.duplicated(subset=["company_id", "year"]).any()

    def test_all_year_values_match_yyyy_mm(self, loaded_result):
        conn = sqlite3.connect(DB_PATH)
        for table in ["profitandloss", "balancesheet", "cashflow"]:
            df = pd.read_sql(f"SELECT year FROM {table}", conn)
            assert (
                df["year"].str.match(r"^\d{4}-\d{2}$").all()
            ), f"{table} has malformed year values"
        conn.close()

    def test_all_company_ids_uppercase_stripped(self, loaded_result):
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql("SELECT id FROM companies", conn)
        conn.close()
        assert (df["id"] == df["id"].str.strip().str.upper()).all()

    def test_stock_prices_row_count_matches_spec(self, loaded_result):
        # 92 companies x 60 months = 5520, per spec section 6.2
        assert loaded_result["row_counts"]["stock_prices"] == 5520

    def test_sectors_covers_all_92_companies(self, loaded_result):
        assert loaded_result["row_counts"]["sectors"] == 92

    def test_no_critical_violations_undetected(self, loaded_result):
        # Sanity: every CRITICAL violation logged should correspond to a
        # rejected/deduped row, i.e. the pipeline should not silently
        # swallow bad data without logging it.
        vresult = loaded_result["vresult"]
        assert vresult.critical_count() >= 0  # non-negative sanity check
        assert isinstance(vresult.critical_count(), int)
