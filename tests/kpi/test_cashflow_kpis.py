"""
tests/kpi/test_cashflow_kpis.py

Sprint 2, Day 11 — Cash Flow KPIs & Capital Allocation classifier tests.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.analytics.cashflow_kpis import (
    CAPEX_ASSET_LIGHT,
    CAPEX_CAPITAL_INTENSIVE,
    CAPEX_MODERATE,
    CFO_QUALITY_ACCRUAL_RISK,
    CFO_QUALITY_HIGH,
    CFO_QUALITY_MODERATE,
    PATTERN_CASH_ACCUMULATOR,
    PATTERN_DISTRESS_SIGNAL,
    PATTERN_GROWTH_FUNDED_BY_DEBT,
    PATTERN_LIQUIDATING_ASSETS,
    PATTERN_MIXED,
    PATTERN_PRE_REVENUE,
    PATTERN_REINVESTOR,
    PATTERN_SHAREHOLDER_RETURNS,
    PATTERN_UNCLASSIFIED,
    capex_intensity,
    cfo_quality_score,
    classify_capital_allocation,
    fcf_conversion_rate,
    free_cash_flow,
)

NAN = float("nan")


class TestFreeCashFlow:
    def test_normal_case(self):
        assert free_cash_flow(operating_activity=500, investing_activity=-200) == 300

    def test_negative_fcf_allowed(self):
        assert free_cash_flow(operating_activity=100, investing_activity=-300) == -200

    def test_none_input_returns_none(self):
        assert free_cash_flow(None, -200) is None


class TestCFOQualityScore:
    def test_high_quality(self):
        score, label = cfo_quality_score([150, 160, 170], [100, 100, 100])
        assert label == CFO_QUALITY_HIGH
        assert score > 1.0

    def test_moderate_quality(self):
        score, label = cfo_quality_score([70, 75, 80], [100, 100, 100])
        assert label == CFO_QUALITY_MODERATE

    def test_accrual_risk(self):
        score, label = cfo_quality_score([20, 25, 30], [100, 100, 100])
        assert label == CFO_QUALITY_ACCRUAL_RISK

    def test_skips_years_with_non_positive_pat(self):
        # only the middle year has PAT > 0
        score, label = cfo_quality_score([100, 150, 100], [-50, 100, 0])
        assert score == pytest.approx(1.5)
        assert label == CFO_QUALITY_HIGH

    def test_no_valid_years_returns_none(self):
        score, label = cfo_quality_score([100, 100], [-50, 0])
        assert score is None
        assert label is None


class TestCapexIntensity:
    def test_asset_light(self):
        pct, label = capex_intensity(investing_activity=-20, sales=1000)
        assert pct == 2.0
        assert label == CAPEX_ASSET_LIGHT

    def test_moderate(self):
        pct, label = capex_intensity(investing_activity=-50, sales=1000)
        assert pct == 5.0
        assert label == CAPEX_MODERATE

    def test_capital_intensive(self):
        pct, label = capex_intensity(investing_activity=-100, sales=1000)
        assert pct == 10.0
        assert label == CAPEX_CAPITAL_INTENSIVE

    def test_zero_sales_returns_none(self):
        pct, label = capex_intensity(-50, 0)
        assert pct is None
        assert label is None


class TestFCFConversionRate:
    def test_normal_case(self):
        assert fcf_conversion_rate(fcf=150, operating_profit=200) == 75.0

    def test_zero_operating_profit_returns_none(self):
        assert fcf_conversion_rate(150, 0) is None


class TestCapitalAllocationClassifier:
    def test_reinvestor(self):
        _, _, _, label = classify_capital_allocation(100, -50, -20, cfo_over_pat=0.8)
        assert label == PATTERN_REINVESTOR

    def test_shareholder_returns(self):
        _, _, _, label = classify_capital_allocation(100, -50, -20, cfo_over_pat=1.5)
        assert label == PATTERN_SHAREHOLDER_RETURNS

    def test_liquidating_assets(self):
        _, _, _, label = classify_capital_allocation(100, 50, -20)
        assert label == PATTERN_LIQUIDATING_ASSETS

    def test_distress_signal(self):
        _, _, _, label = classify_capital_allocation(-100, 50, 20)
        assert label == PATTERN_DISTRESS_SIGNAL

    def test_growth_funded_by_debt(self):
        _, _, _, label = classify_capital_allocation(-100, -50, 200)
        assert label == PATTERN_GROWTH_FUNDED_BY_DEBT

    def test_cash_accumulator(self):
        _, _, _, label = classify_capital_allocation(100, 50, 20)
        assert label == PATTERN_CASH_ACCUMULATOR

    def test_pre_revenue(self):
        _, _, _, label = classify_capital_allocation(-100, -50, -20)
        assert label == PATTERN_PRE_REVENUE

    def test_mixed(self):
        _, _, _, label = classify_capital_allocation(100, -50, 20)
        assert label == PATTERN_MIXED

    def test_unclassified_combo(self):
        # (-, +, -) isn't one of the spec's 8 defined labels
        _, _, _, label = classify_capital_allocation(-100, 50, -20)
        assert label == PATTERN_UNCLASSIFIED

    def test_signs_returned_correctly(self):
        cfo_sign, cfi_sign, cff_sign, _ = classify_capital_allocation(100, -50, -20)
        assert (cfo_sign, cfi_sign, cff_sign) == ("+", "-", "-")

    def test_zero_treated_as_negative_bucket(self):
        cfo_sign, _, _, _ = classify_capital_allocation(0, -50, -20)
        assert cfo_sign == "-"


class TestNaNSafety:
    def test_free_cash_flow_nan(self):
        assert free_cash_flow(NAN, -200) is None

    def test_capex_intensity_nan_sales(self):
        pct, label = capex_intensity(-50, NAN)
        assert pct is None and label is None

    def test_classify_nan_values_default_to_negative_bucket(self):
        cfo_sign, cfi_sign, cff_sign, _ = classify_capital_allocation(NAN, NAN, NAN)
        assert (cfo_sign, cfi_sign, cff_sign) == ("-", "-", "-")
