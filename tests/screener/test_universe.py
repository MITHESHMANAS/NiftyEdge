"""
tests/screener/test_universe.py

Sprint 3, Day 15 — screener universe builder tests, including the
market_cap closest-available-year fallback (dead in the real dataset,
since every company's latest FYE falls within 2019-2024, but real
defensive logic that needs direct coverage).
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.screener.universe import build_screener_universe


def _build_minimal_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE companies (id TEXT PRIMARY KEY, company_name TEXT);
        CREATE TABLE financial_ratios (
            company_id TEXT, year TEXT, return_on_equity_pct REAL,
            debt_to_equity REAL, free_cash_flow_cr REAL, icr_label TEXT
        );
        CREATE TABLE profitandloss (
            company_id TEXT, year TEXT, net_profit REAL, sales REAL, dividend_payout REAL
        );
        CREATE TABLE market_cap (
            company_id TEXT, year INTEGER, market_cap_crore REAL,
            enterprise_value_crore REAL, pe_ratio REAL, pb_ratio REAL,
            ev_ebitda REAL, dividend_yield_pct REAL
        );
        CREATE TABLE sectors (company_id TEXT, broad_sector TEXT, sub_sector TEXT);
        CREATE TABLE peer_groups (company_id TEXT, peer_group_name TEXT, is_benchmark INTEGER);
        """)
    conn.execute("INSERT INTO companies VALUES ('OLDCO', 'Old Company Ltd')")
    # OLDCO's latest FYE is 2016-03 — well outside market_cap's 2019-2024 coverage.
    conn.execute("INSERT INTO financial_ratios VALUES ('OLDCO', '2016-03', 15.0, 0.5, 100.0, NULL)")
    conn.execute("INSERT INTO profitandloss VALUES ('OLDCO', '2016-03', 200.0, 1000.0, 20.0)")
    # market_cap only has 2020 and 2022 data for this company.
    conn.execute("INSERT INTO market_cap VALUES ('OLDCO', 2020, 5000, 5200, 18.0, 3.0, 12.0, 1.2)")
    conn.execute("INSERT INTO market_cap VALUES ('OLDCO', 2022, 6000, 6300, 20.0, 3.5, 13.0, 1.5)")
    conn.execute("INSERT INTO sectors VALUES ('OLDCO', 'Industrials', 'Widgets')")
    conn.commit()
    return conn


class TestMarketCapFallback:
    def test_falls_back_to_closest_available_year(self):
        conn = _build_minimal_db()
        universe = build_screener_universe(conn)
        conn.close()

        assert len(universe) == 1
        row = universe.iloc[0]
        # FYE calendar year is 2016; closest available market_cap years are
        # 2020 (dist=4) and 2022 (dist=6) -> should pick 2020.
        assert row["pe_ratio"] == 18.0
        assert row["pb_ratio"] == 3.0

    def test_no_market_cap_data_at_all_leaves_nulls(self):
        conn = _build_minimal_db()
        conn.execute("DELETE FROM market_cap")
        conn.commit()
        universe = build_screener_universe(conn)
        conn.close()

        row = universe.iloc[0]
        assert row["pe_ratio"] is None or row["pe_ratio"] != row["pe_ratio"]  # NaN check
