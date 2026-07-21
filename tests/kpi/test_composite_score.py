"""
tests/kpi/test_composite_score.py

Tests for the provisional composite_quality_score heuristic (Sprint 2,
Day 12).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.analytics.composite_score import composite_quality_score

NAN = float("nan")


class TestCompositeQualityScore:
    def test_strong_company_scores_high(self):
        score = composite_quality_score(
            roe_pct=25,
            roce_pct=25,
            debt_to_equity=0.2,
            interest_coverage=5,
            is_debt_free=False,
            revenue_cagr_5yr_pct=18,
        )
        assert score > 80

    def test_weak_company_scores_low(self):
        score = composite_quality_score(
            roe_pct=2,
            roce_pct=2,
            debt_to_equity=6,
            interest_coverage=0.8,
            is_debt_free=False,
            revenue_cagr_5yr_pct=-5,
        )
        assert score < 20

    def test_debt_free_gets_full_icr_points_even_without_icr_value(self):
        score_debt_free = composite_quality_score(
            roe_pct=10,
            roce_pct=10,
            debt_to_equity=0,
            interest_coverage=None,
            is_debt_free=True,
            revenue_cagr_5yr_pct=5,
        )
        score_leveraged_low_icr = composite_quality_score(
            roe_pct=10,
            roce_pct=10,
            debt_to_equity=0,
            interest_coverage=0.5,
            is_debt_free=False,
            revenue_cagr_5yr_pct=5,
        )
        assert score_debt_free > score_leveraged_low_icr

    def test_missing_ratios_contribute_zero_not_crash(self):
        score = composite_quality_score(
            roe_pct=None,
            roce_pct=None,
            debt_to_equity=None,
            interest_coverage=None,
            is_debt_free=False,
            revenue_cagr_5yr_pct=None,
        )
        assert score == 0.0

    def test_score_is_bounded_0_to_100(self):
        score = composite_quality_score(
            roe_pct=1000,
            roce_pct=1000,
            debt_to_equity=0,
            interest_coverage=100,
            is_debt_free=False,
            revenue_cagr_5yr_pct=1000,
        )
        assert 0 <= score <= 100

    def test_nan_inputs_treated_as_missing(self):
        score = composite_quality_score(
            roe_pct=NAN,
            roce_pct=NAN,
            debt_to_equity=NAN,
            interest_coverage=NAN,
            is_debt_free=False,
            revenue_cagr_5yr_pct=NAN,
        )
        assert score == 0.0
