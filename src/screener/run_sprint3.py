"""
src/screener/run_sprint3.py

Sprint 3 orchestrator — runs the full screener + peer engine pipeline:
    1. Build the screener universe (one row per company, latest FYE)
    2. Run all 6 presets -> output/screener_output.xlsx
    3. Compute peer percentiles -> peer_percentiles table in SQLite
    4. Generate radar charts -> reports/radar_charts/*.png
    5. Generate peer comparison workbook -> output/peer_comparison.xlsx

Usage:
    python src/screener/run_sprint3.py
    # or: make screener
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.analytics.peer import compute_peer_percentiles, populate_peer_percentiles_table
from src.etl.config import DB_PATH, OUTPUT_DIR, PROJECT_ROOT
from src.etl.logging_setup import get_logger
from src.screener.composite import compute_composite_scores
from src.screener.engine import load_screener_config, run_all_presets
from src.screener.export import write_screener_output
from src.screener.peer_export import write_peer_comparison
from src.screener.radar import generate_all_radar_charts
from src.screener.universe import build_screener_universe

log = get_logger(__name__)

RADAR_DIR = PROJECT_ROOT / "reports" / "radar_charts"


def run_sprint3(db_path: Path = None) -> dict:
    db_path = db_path or DB_PATH
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    log.info("Sprint 3 run starting against %s", db_path)

    conn = sqlite3.connect(db_path)
    universe = build_screener_universe(conn)
    financial_ratios = pd.read_sql("SELECT * FROM financial_ratios", conn)
    log.info("Screener universe built: %d companies", len(universe))

    # 1. Screener presets -> screener_output.xlsx
    config = load_screener_config()
    results = run_all_presets(universe, financial_ratios, config)
    for key, df in results.items():
        log.info("Preset '%s': %d companies", key, len(df))
    screener_path = write_screener_output(results, config, OUTPUT_DIR / "screener_output.xlsx")
    log.info("Wrote %s", screener_path)

    # 2. Peer percentiles -> SQLite peer_percentiles table
    peer_result = populate_peer_percentiles_table(db_path)
    log.info(
        "peer_percentiles: %d rows, %d groups, %d companies with no peer group",
        peer_result["row_count"],
        peer_result["n_groups"],
        len(peer_result["no_peer_group_companies"]),
    )

    # 3. Radar charts -> reports/radar_charts/
    radar_paths = generate_all_radar_charts(conn, universe, financial_ratios, RADAR_DIR)
    log.info("Generated %d radar charts in %s", len(radar_paths), RADAR_DIR)

    # 4. Peer comparison workbook -> peer_comparison.xlsx
    scored_universe = compute_composite_scores(universe, financial_ratios)
    percentiles = compute_peer_percentiles(conn)
    peer_comparison_path = write_peer_comparison(
        scored_universe, percentiles, OUTPUT_DIR / "peer_comparison.xlsx"
    )
    log.info("Wrote %s", peer_comparison_path)

    conn.close()

    log.info("Sprint 3 run complete in %.2fs", time.time() - t0)

    return {
        "universe_size": len(universe),
        "preset_counts": {k: len(v) for k, v in results.items()},
        "peer_result": peer_result,
        "radar_chart_count": len(radar_paths),
        "screener_output_path": screener_path,
        "peer_comparison_path": peer_comparison_path,
    }


def main():
    result = run_sprint3()
    print("\nPreset result counts:")
    for k, n in result["preset_counts"].items():
        in_range = 5 <= n <= 50
        print(f"  {k:<22} {n:>3} companies  {'OK' if in_range else 'OUT OF RANGE'}")
    print(
        f"\nPeer percentiles: {result['peer_result']['row_count']} rows, "
        f"{result['peer_result']['n_groups']} groups"
    )
    print(f"Radar charts: {result['radar_chart_count']}")
    print(f"screener_output.xlsx: {result['screener_output_path']}")
    print(f"peer_comparison.xlsx: {result['peer_comparison_path']}")

    if not all(5 <= n <= 50 for n in result["preset_counts"].values()):
        print("\n[FAIL] At least one preset is outside the 5-50 company exit criterion.")
        sys.exit(1)
    if result["peer_result"]["n_groups"] != 11:
        print("\n[FAIL] Expected 11 peer groups.")
        sys.exit(1)
    print("\n[OK] Sprint 3 exit criteria satisfied.")


if __name__ == "__main__":
    main()
