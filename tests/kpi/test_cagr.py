"""
tests/kpi/test_cagr.py

Sprint 2, Day 10 — CAGR Engine unit tests (10 required): normal CAGR,
turnaround flag, decline-to-loss, both negative, zero base, insufficient
data, plus NaN-safety and the Series-based window helper.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.analytics.cagr import (
    BOTH_NEGATIVE,
    DECLINE_TO_LOSS,
    INSUFFICIENT,
    TURNAROUND,
    ZERO_BASE,
    compute_all_cagr_windows,
    compute_cagr,
    compute_cagr_for_window,
)

NAN = float("nan")


class TestComputeCAGRNormalCase:
    def test_positive_to_positive_growth(self):
        # 100 -> 200 over 5 years
        value, flag = compute_cagr(100, 200, 5)
        assert flag is None
        assert value == pytest.approx(14.87, abs=0.01)

    def test_positive_to_positive_no_change(self):
        value, flag = compute_cagr(100, 100, 5)
        assert flag is None
        assert value == pytest.approx(0.0)

    def test_positive_to_positive_decline_but_still_positive(self):
        value, flag = compute_cagr(200, 100, 5)
        assert flag is None
        assert value < 0


class TestComputeCAGREdgeCases:
    def test_decline_to_loss(self):
        value, flag = compute_cagr(100, -50, 5)
        assert value is None
        assert flag == DECLINE_TO_LOSS

    def test_turnaround(self):
        value, flag = compute_cagr(-50, 100, 5)
        assert value is None
        assert flag == TURNAROUND

    def test_both_negative(self):
        value, flag = compute_cagr(-100, -50, 5)
        assert value is None
        assert flag == BOTH_NEGATIVE

    def test_zero_base(self):
        value, flag = compute_cagr(0, 100, 5)
        assert value is None
        assert flag == ZERO_BASE

    def test_insufficient_missing_start(self):
        value, flag = compute_cagr(None, 100, 5)
        assert value is None
        assert flag == INSUFFICIENT

    def test_insufficient_missing_end(self):
        value, flag = compute_cagr(100, None, 5)
        assert value is None
        assert flag == INSUFFICIENT

    def test_insufficient_zero_years(self):
        value, flag = compute_cagr(100, 200, 0)
        assert value is None
        assert flag == INSUFFICIENT

    def test_insufficient_none_years(self):
        value, flag = compute_cagr(100, 200, None)
        assert value is None
        assert flag == INSUFFICIENT


class TestNaNSafety:
    def test_nan_start_value_is_insufficient(self):
        value, flag = compute_cagr(NAN, 200, 5)
        assert value is None
        assert flag == INSUFFICIENT

    def test_nan_end_value_is_insufficient(self):
        value, flag = compute_cagr(100, NAN, 5)
        assert value is None
        assert flag == INSUFFICIENT


class TestComputeCAGRForWindow:
    def test_insufficient_when_series_too_short(self):
        series = pd.Series([100, 110, 120], index=["2020-03", "2021-03", "2022-03"])
        value, flag = compute_cagr_for_window(series, window_years=5)
        assert value is None
        assert flag == INSUFFICIENT

    def test_computes_over_full_window(self):
        years = [f"{y}-03" for y in range(2019, 2025)]  # 6 points, 5yr window
        series = pd.Series([100, 110, 121, 133, 146, 161], index=years)
        value, flag = compute_cagr_for_window(series, window_years=5)
        assert flag is None
        assert value == pytest.approx(10.0, abs=0.5)

    def test_none_series_is_insufficient(self):
        value, flag = compute_cagr_for_window(None, window_years=5)
        assert value is None
        assert flag == INSUFFICIENT


class TestComputeAllCAGRWindows:
    def test_returns_all_default_windows(self):
        years = [f"{y}-03" for y in range(2013, 2025)]  # 12 points
        series = pd.Series(range(100, 100 + 12 * 10, 10), index=years)
        result = compute_all_cagr_windows(series)
        assert set(result.keys()) == {
            "cagr_3yr",
            "cagr_3yr_flag",
            "cagr_5yr",
            "cagr_5yr_flag",
            "cagr_10yr",
            "cagr_10yr_flag",
        }

    def test_custom_windows(self):
        years = [f"{y}-03" for y in range(2020, 2025)]
        series = pd.Series([100, 110, 120, 130, 140], index=years)
        result = compute_all_cagr_windows(series, windows=[2])
        assert "cagr_2yr" in result
        assert "cagr_2yr_flag" in result
