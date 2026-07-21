"""
src/screener/universe.py

Builds the "screener universe": one row per company, using each company's
most recent standard March-fiscal-year-end `financial_ratios` row, joined
with:
    - profitandloss (net_profit, sales for that same fiscal year — the 15
      filterable metrics include absolute Net Profit and Sales thresholds
      that aren't in financial_ratios)
    - market_cap (pe_ratio, pb_ratio, dividend_yield_pct, market_cap_crore
      — matched by calendar year; market_cap only covers 2019-2024, so
      for a company whose latest FYE falls outside that range we fall
      back to that company's closest available market_cap year)
    - sectors (broad_sector, for the Financials D/E carve-out)
    - companies (company_name, for display)
    - peer_groups (peer_group_name — LEFT join; a company can have none)
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from src.analytics.populate_financial_ratios import _latest_standard_fye_per_company


def build_screener_universe(conn: sqlite3.Connection) -> pd.DataFrame:
    fr = pd.read_sql("SELECT * FROM financial_ratios", conn)
    latest = _latest_standard_fye_per_company(fr)

    pnl = pd.read_sql(
        "SELECT company_id, year, net_profit, sales, dividend_payout FROM profitandloss", conn
    )
    latest = latest.merge(pnl, on=["company_id", "year"], how="left", suffixes=("", "_pnl"))

    market_cap = pd.read_sql("SELECT * FROM market_cap", conn)
    latest["fye_calendar_year"] = latest["year"].str.slice(0, 4).astype(int)
    latest = latest.merge(
        market_cap,
        left_on=["company_id", "fye_calendar_year"],
        right_on=["company_id", "year"],
        how="left",
        suffixes=("", "_mc"),
    )

    # For companies whose FYE year has no exact market_cap match (FYE
    # outside 2019-2024), fall back to that company's closest available
    # market_cap year rather than leaving valuation metrics entirely null.
    missing_mc = latest["pe_ratio"].isna() & latest["company_id"].isin(market_cap["company_id"])
    if missing_mc.any():
        mc_by_company = {cid: g.sort_values("year") for cid, g in market_cap.groupby("company_id")}
        for idx in latest[missing_mc].index:
            cid = latest.at[idx, "company_id"]
            target_year = latest.at[idx, "fye_calendar_year"]
            g = mc_by_company.get(cid)
            if g is None or g.empty:
                continue
            g = g.copy()
            g["dist"] = (g["year"] - target_year).abs()
            closest = g.sort_values("dist").iloc[0]
            for col in [
                "market_cap_crore",
                "enterprise_value_crore",
                "pe_ratio",
                "pb_ratio",
                "ev_ebitda",
                "dividend_yield_pct",
            ]:
                latest.at[idx, col] = closest[col]

    sectors = pd.read_sql("SELECT company_id, broad_sector, sub_sector FROM sectors", conn)
    latest = latest.merge(sectors, on="company_id", how="left")

    companies = pd.read_sql("SELECT id AS company_id, company_name FROM companies", conn)
    latest = latest.merge(companies, on="company_id", how="left")

    peer = pd.read_sql("SELECT company_id, peer_group_name, is_benchmark FROM peer_groups", conn)
    latest = latest.merge(peer, on="company_id", how="left")

    return latest.reset_index(drop=True)
