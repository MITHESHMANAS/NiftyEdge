"""
tests/screener/test_engine.py

Sprint 3, Day 15-16 — filter engine + preset unit tests.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.screener.engine import apply_metric_filter, compute_de_trend, load_screener_config

NAN = float("nan")


@pytest.fixture(scope="module")
def config():
    return load_screener_config()


def _df(**cols):
    return pd.DataFrame(cols)


class TestApplyMetricFilter:
    def test_min_direction_keeps_rows_above_threshold(self, config):
        df = _df(company_id=["A", "B", "C"], return_on_equity_pct=[10, 20, 30])
        result = apply_metric_filter(df, "roe_min", 15, config)
        assert set(result["company_id"]) == {"B", "C"}

    def test_max_direction_keeps_rows_below_threshold(self, config):
        df = _df(
            company_id=["A", "B", "C"], debt_to_equity=[0.5, 1.5, 2.5], broad_sector=["X", "X", "X"]
        )
        result = apply_metric_filter(df, "de_max", 1.0, config)
        assert set(result["company_id"]) == {"A"}

    def test_de_filter_skips_financials_sector(self, config):
        df = _df(
            company_id=["BANK1", "NONBANK"],
            debt_to_equity=[8.0, 8.0],
            broad_sector=["Financials", "Industrials"],
        )
        result = apply_metric_filter(df, "de_max", 1.0, config)
        # BANK1 has D/E=8 (way over threshold) but is in Financials -> kept anyway
        assert set(result["company_id"]) == {"BANK1"}

    def test_icr_filter_debt_free_always_passes(self, config):
        df = _df(
            company_id=["DEBTFREE", "LOWICR"],
            interest_coverage=[NAN, 0.5],
            icr_label=["Debt Free", None],
        )
        result = apply_metric_filter(df, "icr_min", 3.0, config)
        assert set(result["company_id"]) == {"DEBTFREE"}

    def test_nan_values_excluded_not_erroring(self, config):
        df = _df(company_id=["A", "B"], return_on_equity_pct=[NAN, 20])
        result = apply_metric_filter(df, "roe_min", 15, config)
        assert set(result["company_id"]) == {"B"}


class TestComputeDeTrend:
    def test_declining_de_detected(self):
        fr = pd.DataFrame(
            {
                "company_id": ["A", "A", "A"],
                "year": ["2022-03", "2023-03", "2024-03"],
                "debt_to_equity": [1.0, 0.8, 0.5],
            }
        )
        trend = compute_de_trend(fr)
        assert trend["A"] is True

    def test_rising_de_detected(self):
        fr = pd.DataFrame(
            {
                "company_id": ["A", "A"],
                "year": ["2023-03", "2024-03"],
                "debt_to_equity": [0.5, 0.8],
            }
        )
        trend = compute_de_trend(fr)
        assert trend["A"] is False

    def test_insufficient_history_omitted(self):
        fr = pd.DataFrame(
            {
                "company_id": ["A"],
                "year": ["2024-03"],
                "debt_to_equity": [0.5],
            }
        )
        trend = compute_de_trend(fr)
        assert "A" not in trend
