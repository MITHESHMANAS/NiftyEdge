"""
src/analytics/cagr.py

Sprint 2, Day 10 — CAGR Engine.

CAGR = ((end / start) ** (1/n) - 1) x 100

Six edge cases are handled explicitly (spec Day 10). Every one of them
returns (None, <flag>) instead of raising, computing a nonsensical value,
or silently returning 0 — a screener or dashboard consuming this data
needs to know *why* a CAGR is missing, not just that it is.

    start   end     n_years available   -> value              flag
    -----   -----   -----------------   -> -----               ----
    >0      >0      >= n                -> computed normally   None
    >0      <=0     >= n                -> None                DECLINE_TO_LOSS
    <=0     >0      >= n                -> None                TURNAROUND
    <=0     <=0     >= n                -> None                BOTH_NEGATIVE
    == 0    any      any                -> None                ZERO_BASE   (checked first)
    any     any     < n                 -> None                INSUFFICIENT (checked before sign matrix)
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pandas as pd

from src.analytics.utils import clean

# Flags
DECLINE_TO_LOSS = "DECLINE_TO_LOSS"
TURNAROUND = "TURNAROUND"
BOTH_NEGATIVE = "BOTH_NEGATIVE"
ZERO_BASE = "ZERO_BASE"
INSUFFICIENT = "INSUFFICIENT"

CAGR_WINDOWS = (3, 5, 10)


def compute_cagr(
    start_value: Optional[float], end_value: Optional[float], n_years: Optional[int]
) -> Tuple[Optional[float], Optional[str]]:
    """
    Compute CAGR between `start_value` and `end_value` over `n_years`.
    Returns (cagr_pct, flag). flag is None when the CAGR was computed
    normally; otherwise it's one of the module-level flag constants above
    and cagr_pct is None.
    """
    # Insufficient data: missing inputs or non-positive year count.
    start_value = clean(start_value)
    end_value = clean(end_value)
    n_years = clean(n_years)
    if start_value is None or end_value is None or n_years is None or n_years <= 0:
        return None, INSUFFICIENT

    # Zero base: growth from a zero starting point is undefined (any
    # nonzero end value would imply infinite growth).
    if start_value == 0:
        return None, ZERO_BASE

    start_positive = start_value > 0
    end_positive = end_value > 0

    if start_positive and end_positive:
        cagr = ((end_value / start_value) ** (1.0 / n_years) - 1) * 100
        return cagr, None

    if start_positive and not end_positive:
        # Company went from profit to loss (or exactly breakeven) over the window.
        return None, DECLINE_TO_LOSS

    if not start_positive and end_positive:
        # Company recovered from loss to profit over the window.
        return None, TURNAROUND

    # not start_positive and not end_positive
    return None, BOTH_NEGATIVE


def compute_cagr_for_window(
    series: pd.Series, window_years: int
) -> Tuple[Optional[float], Optional[str]]:
    """
    Given a company's metric series indexed by ascending fiscal year
    (e.g. a pandas Series of `sales` indexed by `year` string 'YYYY-MM',
    sorted ascending), compute the CAGR over the trailing `window_years`
    using the latest available year as the end point and the value
    `window_years` periods earlier as the start point.

    Returns (None, INSUFFICIENT) if fewer than `window_years` + 1 distinct
    annual data points are available.
    """
    if series is None or len(series) < window_years + 1:
        return None, INSUFFICIENT

    ordered = series.sort_index()
    end_value = ordered.iloc[-1]
    start_value = ordered.iloc[-(window_years + 1)]
    return compute_cagr(start_value, end_value, window_years)


def compute_all_cagr_windows(series: pd.Series, windows: List[int] = None) -> dict:
    """
    Convenience wrapper: computes CAGR for each window in `windows`
    (default 3/5/10yr) and returns a flat dict like:
        {'cagr_3yr': 12.3, 'cagr_3yr_flag': None,
         'cagr_5yr': None,  'cagr_5yr_flag': 'TURNAROUND',
         'cagr_10yr': None, 'cagr_10yr_flag': 'INSUFFICIENT'}
    """
    windows = windows or list(CAGR_WINDOWS)
    result = {}
    for w in windows:
        value, flag = compute_cagr_for_window(series, w)
        result[f"cagr_{w}yr"] = value
        result[f"cagr_{w}yr_flag"] = flag
    return result
