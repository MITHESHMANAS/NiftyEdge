"""
src/analytics/peer.py

Sprint 3, Day 18 — Peer Percentile Rankings.

Computes PERCENT_RANK for 10 metrics within each of the 11 peer groups
(from peer_groups.xlsx, loaded into the `peer_groups` table in Sprint 1),
using each company's latest standard-March-FYE `financial_ratios` row.
Writes the result into a new `peer_percentiles` table:
    company_id, peer_group_name, metric, value, percentile_rank, year

For D/E, lower is better, so the percentile is inverted (1 - raw
percent-rank) so that the *lowest*-leverage company in a peer group gets
the *highest* D/E percentile — consistent with every other metric where
"higher percentile = better".

Companies not in any peer group are simply absent from `peer_percentiles`
(no row is written) — this function does not raise for them; the caller
can check membership via `no_peer_group_message()`.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.analytics.populate_financial_ratios import _latest_standard_fye_per_company
from src.etl.config import DB_PATH
from src.etl.logging_setup import get_logger

log = get_logger(__name__)

# 10 metrics ranked per peer group (Day 18). Column name in the latest-FYE
# financial_ratios snapshot -> whether higher is better (D/E is inverted).
PEER_METRICS = {
    "ROE": ("return_on_equity_pct", True),
    "ROCE": ("return_on_capital_employed_pct", True),
    "Net Profit Margin": ("net_profit_margin_pct", True),
    "D/E": ("debt_to_equity", False),
    "FCF": ("free_cash_flow_cr", True),
    "PAT CAGR 5yr": ("pat_cagr_5yr", True),
    "Revenue CAGR 5yr": ("revenue_cagr_5yr", True),
    "EPS CAGR 5yr": ("eps_cagr_5yr", True),
    "Interest Coverage": ("interest_coverage", True),
    "Asset Turnover": ("asset_turnover", True),
}

NO_PEER_GROUP_MESSAGE = "No peer group assigned"


def _percent_rank(series: pd.Series) -> pd.Series:
    """
    Matches SQL PERCENT_RANK() semantics: rank / (n - 1), 0 for the lowest
    value, 1 for the highest, evenly spaced in between. A single-member
    group gets percentile 1.0 (there's no one to rank against, so by
    convention it's treated as top-of-group rather than undefined).
    Missing values are excluded from ranking and get NaN back.
    """
    valid = series.dropna()
    n = len(valid)
    if n == 0:
        return pd.Series(index=series.index, dtype=float)
    if n == 1:
        result = pd.Series(index=series.index, dtype=float)
        result.loc[valid.index] = 1.0
        return result

    ranks = valid.rank(method="average", ascending=True)
    pct = (ranks - 1) / (n - 1)
    result = pd.Series(index=series.index, dtype=float)
    result.loc[valid.index] = pct
    return result


def compute_peer_percentiles(conn: sqlite3.Connection) -> pd.DataFrame:
    fr = pd.read_sql("SELECT * FROM financial_ratios", conn)
    latest = _latest_standard_fye_per_company(fr)

    peer_groups = pd.read_sql("SELECT company_id, peer_group_name FROM peer_groups", conn)
    joined = latest.merge(
        peer_groups, on="company_id", how="inner"
    )  # only companies WITH a peer group

    rows = []
    for group_name, group_df in joined.groupby("peer_group_name"):
        for metric_label, (col, higher_is_better) in PEER_METRICS.items():
            values = group_df[col]
            pct = _percent_rank(values)
            if not higher_is_better:
                pct = 1 - pct
            for idx in group_df.index:
                cid = group_df.at[idx, "company_id"]
                year = group_df.at[idx, "year"]
                val = values.at[idx]
                p = pct.at[idx]
                rows.append(
                    {
                        "company_id": cid,
                        "peer_group_name": group_name,
                        "metric": metric_label,
                        "value": None if pd.isna(val) else float(val),
                        "percentile_rank": None if pd.isna(p) else round(float(p), 4),
                        "year": year,
                    }
                )

    return pd.DataFrame(rows)


def no_peer_group_companies(conn: sqlite3.Connection) -> list:
    """Companies present in `companies` but not in `peer_groups` — for
    these, the caller should show NO_PEER_GROUP_MESSAGE rather than a
    percentile table."""
    all_ids = pd.read_sql("SELECT id FROM companies", conn)["id"].tolist()
    grouped_ids = set(
        pd.read_sql("SELECT DISTINCT company_id FROM peer_groups", conn)["company_id"]
    )
    return sorted(set(all_ids) - grouped_ids)


def populate_peer_percentiles_table(db_path: Path = None) -> dict:
    db_path = db_path or DB_PATH
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS peer_percentiles (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id       TEXT NOT NULL,
            peer_group_name  TEXT NOT NULL,
            metric           TEXT NOT NULL,
            value            REAL,
            percentile_rank  REAL,
            year             TEXT,
            FOREIGN KEY (company_id) REFERENCES companies(id)
        )
    """)
    conn.execute("DELETE FROM peer_percentiles")

    df = compute_peer_percentiles(conn)
    df.to_sql("peer_percentiles", conn, if_exists="append", index=False)
    conn.commit()

    no_peer = no_peer_group_companies(conn)
    row_count = conn.execute("SELECT COUNT(*) FROM peer_percentiles").fetchone()[0]
    n_groups = conn.execute(
        "SELECT COUNT(DISTINCT peer_group_name) FROM peer_percentiles"
    ).fetchone()[0]
    conn.close()

    log.info(
        "peer_percentiles populated: %d rows, %d peer groups, %d companies with %s",
        row_count,
        n_groups,
        len(no_peer),
        repr(NO_PEER_GROUP_MESSAGE),
    )

    return {"row_count": row_count, "n_groups": n_groups, "no_peer_group_companies": no_peer}


if __name__ == "__main__":
    result = populate_peer_percentiles_table()
    print(f"peer_percentiles: {result['row_count']} rows across {result['n_groups']} peer groups")
    print(f"Companies with {NO_PEER_GROUP_MESSAGE!r}: {len(result['no_peer_group_companies'])}")
