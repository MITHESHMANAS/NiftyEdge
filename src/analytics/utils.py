"""
src/analytics/utils.py

Shared helper for the ratio engine. Every formula function in ratios.py /
cagr.py / cashflow_kpis.py / composite_score.py checks `x is None` to
detect "missing input" — that's correct when called directly with plain
Python values (as the unit tests do), but the orchestrator
(populate_financial_ratios.py) reads values out of pandas DataFrames/
Series, where a missing value (e.g. a SQL NULL from a LEFT JOIN, or a
`None` that got written into a float64 column) surfaces as `float('nan')`,
not `None`. `nan is None` is False, so unpatched formula functions would
silently do arithmetic on NaN instead of correctly returning "undefined".

`clean()` normalises both cases to a real `None` at the boundary where
values are pulled out of pandas, so the formula functions' `is None`
checks work correctly regardless of source.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd


def clean(value: Any) -> Optional[float]:
    """Returns None for None, NaN, NaT, or pandas.NA; otherwise returns the
    value unchanged. Use when reading a value out of a pandas row/Series
    before passing it into a ratio/CAGR/cashflow-KPI function."""
    if value is None:
        return None
    if pd.isna(value):
        return None
    return value
