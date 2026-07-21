"""
tests/screener/test_composite.py

Sprint 3, Day 17 — composite score unit tests.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.screener.composite import _winsorize_scale, compute_composite_scores

NAN = float("nan")


class TestWinsorizeScale:
    def test_scales_to_0_100(self):
        s = pd.Series([0, 25, 50, 75, 100])
        scaled = _winsorize_scale(s, low_pct=10, high_pct=90, higher_is_better=True)
        assert scaled.min() >= 0
        assert scaled.max() <= 100

    def test_higher_is_better_orders_correctly(self):
        s = pd.Series([10, 20, 30])
        scaled = _winsorize_scale(s, low_pct=0, high_pct=100, higher_is_better=True)
        assert scaled.iloc[0] < scaled.iloc[1] < scaled.iloc[2]

    def test_lower_is_better_inverts_order(self):
        s = pd.Series([10, 20, 30])
        scaled = _winsorize_scale(s, low_pct=0, high_pct=100, higher_is_better=False)
        assert scaled.iloc[0] > scaled.iloc[1] > scaled.iloc[2]

    def test_extreme_outlier_clipped_not_dominant(self):
        s = pd.Series([10, 12, 11, 13, 12, 10000])  # one wild outlier
        scaled = _winsorize_scale(s, low_pct=10, high_pct=90, higher_is_better=True)
        # the outlier should be clipped to the P90 band, not stretch the
        # normal values into a degenerate near-identical cluster at 0
        normal_scores = scaled.iloc[:5]
        assert normal_scores.max() > 0
        assert normal_scores.nunique() > 1

    def test_missing_values_score_zero(self):
        s = pd.Series([10, 20, NAN])
        scaled = _winsorize_scale(s, low_pct=0, high_pct=100, higher_is_better=True)
        assert scaled.iloc[2] == 0.0

    def test_all_identical_values_score_50(self):
        s = pd.Series([5, 5, 5])
        scaled = _winsorize_scale(s, low_pct=10, high_pct=90, higher_is_better=True)
        assert (scaled == 50.0).all()

    def test_all_missing_returns_all_zero(self):
        s = pd.Series([NAN, NAN])
        scaled = _winsorize_scale(s, low_pct=10, high_pct=90, higher_is_better=True)
        assert (scaled == 0.0).all()


class TestComputeCompositeScores:
    @pytest.fixture
    def sample_universe(self):
        return pd.DataFrame(
            {
                "company_id": ["A", "B", "C", "D"],
                "year": ["2024-03"] * 4,
                "return_on_equity_pct": [25, 15, 5, 30],
                "return_on_capital_employed_pct": [20, 12, 4, 25],
                "net_profit_margin_pct": [15, 10, 3, 20],
                "debt_to_equity": [0.2, 1.0, 3.0, 0.5],
                "interest_coverage": [10, 3, 0.8, 8],
                "icr_label": [None, None, None, None],
                "free_cash_flow_cr": [500, 100, -50, 800],
                "revenue_cagr_5yr": [12, 8, 2, 18],
                "pat_cagr_5yr": [15, 5, -5, 22],
                "cfo_quality_score": [1.2, 0.7, 0.3, 1.5],
                "broad_sector": ["Industrials", "Industrials", "Energy", "Energy"],
            }
        )

    @pytest.fixture
    def sample_financial_ratios(self):
        # Minimal history so FCF CAGR can compute for each company
        rows = []
        for cid, base_fcf in [("A", 300), ("B", 80), ("C", -20), ("D", 500)]:
            for i, year in enumerate(["2020-03", "2021-03", "2022-03", "2023-03", "2024-03"]):
                rows.append(
                    {"company_id": cid, "year": year, "free_cash_flow_cr": base_fcf + i * 20}
                )
        return pd.DataFrame(rows)

    def test_composite_score_column_added(self, sample_universe, sample_financial_ratios):
        result = compute_composite_scores(sample_universe, sample_financial_ratios)
        assert "composite_score" in result.columns
        assert "composite_score_sector_relative" in result.columns

    def test_scores_bounded_0_100(self, sample_universe, sample_financial_ratios):
        result = compute_composite_scores(sample_universe, sample_financial_ratios)
        assert (result["composite_score"] >= 0).all()
        assert (result["composite_score"] <= 100).all()

    def test_stronger_company_scores_higher(self, sample_universe, sample_financial_ratios):
        result = compute_composite_scores(sample_universe, sample_financial_ratios)
        # D has the best fundamentals across the board in the fixture
        best = result.set_index("company_id")["composite_score"]["D"]
        worst = result.set_index("company_id")["composite_score"]["C"]
        assert best > worst

    def test_debt_free_company_gets_full_icr_score(self, sample_universe, sample_financial_ratios):
        sample_universe.loc[0, "icr_label"] = "Debt Free"
        sample_universe.loc[0, "interest_coverage"] = None
        result = compute_composite_scores(sample_universe, sample_financial_ratios)
        assert result.set_index("company_id")["icr_score"]["A"] == 100.0

    def test_sector_relative_differs_from_global(self, sample_universe, sample_financial_ratios):
        result = compute_composite_scores(sample_universe, sample_financial_ratios)
        # At least one company's sector-relative score should differ from
        # its global score, since sub-population percentiles differ.
        diffs = (result["composite_score"] != result["composite_score_sector_relative"]).sum()
        assert diffs > 0
