"""
tests/kpi/test_ratios.py

Sprint 2, Day 08 (8 tests) + Day 09 (8 tests) — profitability, leverage,
and efficiency ratio formula unit tests, plus NaN-safety coverage since
these functions are called directly with pandas-sourced values in
production.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.analytics.ratios import (
    asset_turnover,
    debt_to_equity,
    ebit,
    high_leverage_flag,
    icr_label,
    icr_risk_flag,
    interest_coverage,
    is_financials_sector,
    net_debt,
    net_profit_margin,
    operating_profit_margin,
    opm_cross_check,
    return_on_assets,
    return_on_capital_employed,
    return_on_equity,
)

NAN = float("nan")


# ===========================================================================
# Day 08 — Profitability Ratios (8 required tests)
# ===========================================================================
class TestNetProfitMargin:
    def test_normal_case(self):
        assert net_profit_margin(100, 1000) == 10.0

    def test_zero_sales_returns_none(self):
        assert net_profit_margin(100, 0) is None

    def test_none_input_returns_none(self):
        assert net_profit_margin(None, 1000) is None


class TestOperatingProfitMargin:
    def test_normal_case(self):
        assert operating_profit_margin(200, 1000) == 20.0

    def test_opm_cross_check_mismatch_detected(self):
        # computed OPM = 20%, source says 25% -> mismatch (>1pp)
        assert opm_cross_check(20.0, 25.0) is True

    def test_opm_cross_check_within_tolerance(self):
        assert opm_cross_check(20.0, 20.5) is False


class TestReturnOnEquity:
    def test_normal_case(self):
        # net_profit=100, equity_capital=50, reserves=450 -> net worth=500
        assert return_on_equity(100, 50, 450) == 20.0

    def test_negative_equity_returns_none(self):
        assert return_on_equity(100, 50, -500) is None

    def test_zero_denominator_returns_none(self):
        assert return_on_equity(100, 0, 0) is None


class TestReturnOnCapitalEmployedAndAssets:
    def test_roce_normal_case(self):
        ebit_val = ebit(profit_before_tax=80, interest=20)  # EBIT = 100
        assert ebit_val == 100
        roce = return_on_capital_employed(ebit_val, equity_capital=50, reserves=450, borrowings=500)
        assert roce == 10.0  # 100 / 1000 * 100

    def test_roce_none_when_capital_employed_non_positive(self):
        assert return_on_capital_employed(100, 0, 0, 0) is None

    def test_roa_normal_case(self):
        assert return_on_assets(100, 1000) == 10.0

    def test_roa_zero_total_assets_returns_none(self):
        assert return_on_assets(100, 0) is None

    def test_is_financials_sector(self):
        assert is_financials_sector("Financials") is True
        assert is_financials_sector("Energy") is False


# ===========================================================================
# Day 09 — Leverage & Efficiency Ratios (8 required tests)
# ===========================================================================
class TestDebtToEquity:
    def test_normal_case(self):
        assert debt_to_equity(200, 50, 450) == 0.4

    def test_debt_free_returns_zero_not_none(self):
        assert debt_to_equity(0, 50, 450) == 0.0

    def test_negative_net_worth_returns_none(self):
        assert debt_to_equity(200, 50, -500) is None


class TestHighLeverageFlag:
    def test_flag_true_for_high_de_non_financials(self):
        assert high_leverage_flag(6.0, "Industrials") is True

    def test_flag_false_for_high_de_financials_carveout(self):
        assert high_leverage_flag(6.0, "Financials") is False

    def test_flag_false_for_low_de(self):
        assert high_leverage_flag(2.0, "Industrials") is False


class TestInterestCoverage:
    def test_normal_case(self):
        assert interest_coverage(operating_profit=200, other_income=20, interest=50) == 4.4

    def test_interest_zero_returns_none(self):
        assert interest_coverage(200, 20, 0) is None

    def test_icr_label_debt_free(self):
        assert icr_label(0) == "Debt Free"

    def test_icr_label_none_when_has_debt(self):
        assert icr_label(50) is None

    def test_icr_risk_flag_true_below_threshold(self):
        assert icr_risk_flag(1.2) is True

    def test_icr_risk_flag_false_above_threshold(self):
        assert icr_risk_flag(2.0) is False

    def test_icr_risk_flag_false_when_none(self):
        assert icr_risk_flag(None) is False


class TestNetDebtAndAssetTurnover:
    def test_net_debt_normal(self):
        assert net_debt(borrowings=500, investments=200) == 300

    def test_net_debt_negative_cash_position(self):
        assert net_debt(borrowings=100, investments=300) == -200

    def test_asset_turnover_normal(self):
        assert asset_turnover(1000, 500) == 2.0

    def test_asset_turnover_zero_assets_returns_none(self):
        assert asset_turnover(1000, 0) is None


# ===========================================================================
# NaN-safety — every formula function must treat float('nan') exactly like
# None (values pulled from pandas rows surface missing data as NaN, not
# None; see src/analytics/utils.clean()).
# ===========================================================================
class TestNaNSafety:
    def test_net_profit_margin_nan_sales(self):
        assert net_profit_margin(100, NAN) is None

    def test_return_on_equity_nan_inputs(self):
        assert return_on_equity(NAN, 50, 450) is None

    def test_debt_to_equity_nan_borrowings(self):
        assert debt_to_equity(NAN, 50, 450) is None

    def test_interest_coverage_nan_interest(self):
        assert interest_coverage(200, 20, NAN) is None

    def test_high_leverage_flag_nan_de_ratio(self):
        assert high_leverage_flag(NAN, "Industrials") is False

    def test_asset_turnover_nan_total_assets(self):
        assert asset_turnover(1000, NAN) is None

    def test_ebit_nan_input(self):
        assert ebit(NAN, 20) is None

    def test_icr_label_nan_interest_not_treated_as_zero(self):
        # NaN != 0, so this should NOT return 'Debt Free'
        assert icr_label(NAN) is None
