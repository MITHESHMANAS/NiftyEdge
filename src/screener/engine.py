"""
src/screener/engine.py

Sprint 3, Day 15-16 — Filter Engine Core + 6 Preset Screeners.

Usage:
    from src.screener.engine import load_screener_config, run_preset
    config = load_screener_config()
    result_df = run_preset("quality_compounder", universe_df, financial_ratios_df, config)
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yaml

from src.analytics.utils import clean
from src.etl.config import PROJECT_ROOT
from src.screener.composite import compute_composite_scores

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "screener_config.yaml"

FINANCIALS_SECTOR = "Financials"


def load_screener_config(path: Path = None) -> dict:
    path = path or DEFAULT_CONFIG_PATH
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Day 15 — generic threshold filter engine
# ---------------------------------------------------------------------------
def apply_metric_filter(
    df: pd.DataFrame, metric_key: str, threshold: float, config: dict
) -> pd.DataFrame:
    """
    Applies a single filterable-metric threshold (as defined in
    config/screener_config.yaml's `filterable_metrics` block) to `df`.

    Special cases handled here rather than via a bare column comparison:
      - D/E filters (`skip_financials_sector: true`) never exclude a
        Financials-sector company, regardless of its D/E value — high
        leverage is structurally normal for banks/NBFCs/insurers.
      - ICR filters (`debt_free_is_infinity: true`) always pass a
        debt-free company (icr_label = 'Debt Free'), since ICR = infinity
        clears any minimum threshold.
    """
    spec = config["filterable_metrics"][metric_key]
    col = spec["column"]
    direction = spec["direction"]

    values = df[col].map(clean)

    if direction == "min":
        passes = values >= threshold
    elif direction == "max":
        passes = values <= threshold
    else:
        raise ValueError(f"Unknown filter direction: {direction}")

    passes = passes.fillna(False)

    if spec.get("skip_financials_sector") and "broad_sector" in df.columns:
        is_financials = df["broad_sector"] == FINANCIALS_SECTOR
        passes = passes | is_financials

    if spec.get("debt_free_is_infinity") and "icr_label" in df.columns:
        is_debt_free = df["icr_label"] == "Debt Free"
        passes = passes | is_debt_free

    return df[passes]


def apply_filters(df: pd.DataFrame, filters: List[dict], config: dict) -> pd.DataFrame:
    """Applies a list of {metric, threshold} filters with AND logic."""
    result = df
    for f in filters:
        metric_key = f["metric"]
        if metric_key not in config["filterable_metrics"]:
            # Handled specially by the preset runner (e.g. the Turnaround
            # Watch preset's revenue_cagr_3yr_min_special).
            continue
        result = apply_metric_filter(result, metric_key, f["threshold"], config)
    return result


# ---------------------------------------------------------------------------
# Day 16 — preset-specific special-case helpers
# ---------------------------------------------------------------------------
def compute_de_trend(financial_ratios: pd.DataFrame) -> Dict[str, Optional[bool]]:
    """
    Returns {company_id: True} if D/E declined from the second-most-recent
    to the most-recent standard-March-FYE year, {company_id: False} if it
    rose or stayed flat, or omits the company if fewer than 2 comparable
    years of data are available (debt-free-to-debt-free, i.e. 0 -> 0,
    counts as "not declining" since there's no leverage to reduce).
    """
    march_rows = financial_ratios[financial_ratios["year"].str.endswith("-03")]
    trend = {}
    for cid, group in march_rows.groupby("company_id"):
        g = group.sort_values("year")
        de = g["debt_to_equity"].map(clean)
        de = de.dropna()
        if len(de) < 2:
            continue
        trend[cid] = bool(de.iloc[-1] < de.iloc[-2])
    return trend


def run_preset(
    preset_key: str,
    universe: pd.DataFrame,
    financial_ratios: pd.DataFrame,
    config: dict,
) -> pd.DataFrame:
    """
    Runs one preset screener (per config/screener_config.yaml's `presets`
    block) against the one-row-per-company `universe` DataFrame, adding
    the composite_score / composite_score_sector_relative columns, and
    returns the result sorted by composite_score descending.
    """
    preset = config["presets"][preset_key]
    df = universe.copy()

    df = apply_filters(df, preset.get("filters", []), config)

    # Turnaround Watch's revenue_cagr_3yr_min_special filter.
    for f in preset.get("filters", []):
        if f["metric"] == "revenue_cagr_3yr_min_special":
            values = df["revenue_cagr_3yr"].map(clean)
            df = df[(values >= f["threshold"]).fillna(False)]

    if preset.get("dividend_payout_max") is not None:
        values = df["dividend_payout_ratio_pct"].map(clean)
        df = df[(values < preset["dividend_payout_max"]).fillna(False)]

    if preset.get("de_max_near_zero") is not None:
        de = df["debt_to_equity"].map(clean)
        df = df[(de <= preset["de_max_near_zero"]).fillna(False)]

    if preset.get("fcf_positive_latest_year"):
        fcf = df["free_cash_flow_cr"].map(clean)
        df = df[(fcf > 0).fillna(False)]

    if preset.get("de_declining_yoy"):
        trend = compute_de_trend(financial_ratios)
        df = df[df["company_id"].map(lambda cid: trend.get(cid, False))]

    if df.empty:
        return df

    df = compute_composite_scores(df, financial_ratios)
    return df.sort_values("composite_score", ascending=False).reset_index(drop=True)


def run_all_presets(
    universe: pd.DataFrame, financial_ratios: pd.DataFrame, config: dict = None
) -> Dict[str, pd.DataFrame]:
    config = config or load_screener_config()
    return {key: run_preset(key, universe, financial_ratios, config) for key in config["presets"]}
