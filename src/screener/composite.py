"""
src/screener/composite.py

Sprint 3, Day 17 — the "official" 0-100 composite quality score, replacing
Sprint 2's provisional `composite_quality_score` (which is still stored in
`financial_ratios` for reference/backward-compat but is no longer what the
screener ranks by).

Formula (weights sum to 100):
    35% Profitability = 15% ROE + 10% ROCE + 10% NPM
    30% Cash Quality   = 15% FCF CAGR(5yr) + 10% CFO/PAT ratio + 5% FCF-positive flag
    20% Growth         = 10% Revenue CAGR(5yr) + 10% PAT CAGR(5yr)
    15% Leverage       = 10% D/E score (inverted — lower D/E is better) + 5% ICR score

Each continuous metric is P10/P90-winsorized (values are clipped to the
10th/90th percentile of the *scoring population* before scaling) so a
single extreme outlier (e.g. the BEL/HAL/LT ROCE data-quality issue from
Sprint 2) can't blow up or collapse the 0-100 scale for everyone else.
D/E is scored inverted (low D/E -> high score). The FCF-positive flag is
a binary 0/100 component, not winsorized.

`compute_composite_scores()` can be called globally (one percentile
distribution across the whole universe) or per-sector (a separate
distribution computed within each `broad_sector` group) — the sector-
relative call is just the global one applied group-by-group.
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from src.analytics.utils import clean

DEFAULT_WEIGHTS: Dict[str, float] = {
    "roe": 15,
    "roce": 10,
    "npm": 10,
    "fcf_cagr": 15,
    "cfo_pat_ratio": 10,
    "fcf_positive_flag": 5,
    "revenue_cagr": 10,
    "pat_cagr": 10,
    "de_score": 10,
    "icr_score": 5,
}

# Column -> composite-score component name, and whether higher-is-better
# (used by `_winsorize_scale`; D/E is the one inverted component).
_METRIC_COLUMNS = {
    "roe": ("return_on_equity_pct", True),
    "roce": ("return_on_capital_employed_pct", True),
    "npm": ("net_profit_margin_pct", True),
    "fcf_cagr": ("fcf_cagr_5yr", True),
    "cfo_pat_ratio": ("cfo_quality_score", True),
    "revenue_cagr": ("revenue_cagr_5yr", True),
    "pat_cagr": ("pat_cagr_5yr", True),
    "de_score": ("debt_to_equity", False),  # inverted: lower D/E -> higher score
}


def _winsorize_scale(
    series: pd.Series, low_pct: float = 10, high_pct: float = 90, higher_is_better: bool = True
) -> pd.Series:
    """
    Clips `series` to its [low_pct, high_pct] percentile band, then scales
    linearly to [0, 100]. Missing values score 0 (a missing ratio is
    itself informative — see composite_score.py's identical design
    decision in Sprint 2). If every value is missing or the band has zero
    width (e.g. all values identical), everyone with a value scores 50.
    """
    numeric = series.map(clean).astype(float)
    valid = numeric.dropna()

    if valid.empty:
        return pd.Series(0.0, index=series.index)

    lo = valid.quantile(low_pct / 100)
    hi = valid.quantile(high_pct / 100)

    clipped = numeric.clip(lower=lo, upper=hi)

    if hi == lo:
        scaled = clipped.map(lambda v: 50.0 if pd.notna(v) else 0.0)
        return scaled

    if higher_is_better:
        scaled = (clipped - lo) / (hi - lo) * 100
    else:
        scaled = (hi - clipped) / (hi - lo) * 100

    return scaled.fillna(0.0)


def compute_fcf_cagr_5yr(financial_ratios: pd.DataFrame) -> pd.Series:
    """
    FCF CAGR isn't stored in financial_ratios (Sprint 2 only stores the
    per-year absolute free_cash_flow_cr). Computed here, per company,
    using the same trailing-window CAGR engine as everything else.
    Returns a Series indexed by company_id (one value per company, using
    each company's full FCF history through their latest year).
    """
    from src.analytics.cagr import compute_cagr_for_window

    results = {}
    for cid, group in financial_ratios.groupby("company_id"):
        series = group.sort_values("year").set_index("year")["free_cash_flow_cr"]
        value, _flag = compute_cagr_for_window(series, window_years=5)
        results[cid] = value
    return pd.Series(results, name="fcf_cagr_5yr")


def compute_composite_scores(
    universe: pd.DataFrame,
    financial_ratios: pd.DataFrame,
    weights: Optional[Dict[str, float]] = None,
    low_pct: float = 10,
    high_pct: float = 90,
) -> pd.DataFrame:
    """
    Adds `composite_score` (global percentile distribution) and
    `composite_score_sector_relative` (percentile distribution computed
    within each company's broad_sector) columns to `universe` and returns
    the augmented DataFrame. `universe` must have one row per company
    (the screener snapshot from universe.py); `financial_ratios` is the
    full multi-year table, needed for the FCF CAGR calculation.
    """
    weights = weights or DEFAULT_WEIGHTS
    assert abs(sum(weights.values()) - 100) < 1e-6, "Composite score weights must sum to 100"

    universe = universe.copy()
    fcf_cagr = compute_fcf_cagr_5yr(financial_ratios)
    universe["fcf_cagr_5yr"] = universe["company_id"].map(fcf_cagr)

    universe["fcf_positive_flag_score"] = universe["free_cash_flow_cr"].map(
        lambda v: 100.0 if (clean(v) is not None and clean(v) > 0) else 0.0
    )
    universe["icr_score"] = universe.apply(
        lambda r: 100.0 if r.get("icr_label") == "Debt Free" else None, axis=1
    )
    # ICR score for companies WITH debt: winsorized scale of interest_coverage,
    # computed only over the non-debt-free subset so debt-free companies
    # (already scored 100 above) don't skew the percentile band.
    has_debt_mask = universe["icr_label"] != "Debt Free"
    icr_scaled = _winsorize_scale(
        universe.loc[has_debt_mask, "interest_coverage"], low_pct, high_pct, higher_is_better=True
    )
    universe.loc[has_debt_mask, "icr_score"] = icr_scaled
    universe["icr_score"] = universe["icr_score"].fillna(0.0)

    def _score_block(df: pd.DataFrame) -> pd.Series:
        component_scores = {}
        for name, (col, higher_is_better) in _METRIC_COLUMNS.items():
            component_scores[name] = _winsorize_scale(df[col], low_pct, high_pct, higher_is_better)
        component_scores["fcf_positive_flag"] = df["fcf_positive_flag_score"]
        component_scores["icr_score"] = df["icr_score"]

        total = pd.Series(0.0, index=df.index)
        for name, weight in weights.items():
            total = total + component_scores[name] * (weight / 100.0)
        return total.round(2)

    universe["composite_score"] = _score_block(universe)

    sector_scores = []
    for _sector, group in universe.groupby("broad_sector", dropna=False):
        scored = _score_block(group)
        sector_scores.append(scored)
    universe["composite_score_sector_relative"] = pd.concat(sector_scores).reindex(universe.index)

    return universe
