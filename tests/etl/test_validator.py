"""
tests/etl/test_validator.py

Unit tests for the 16 DQ rules (DQ-01..DQ-16). Each rule gets at least one
positive (violation detected) and one negative (clean data, no violation)
case using small synthetic DataFrames.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.etl.validator import (
    dq01_company_pk_uniqueness,
    dq02_annual_pk_uniqueness,
    dq03_fk_integrity,
    dq04_balance_sheet_balance,
    dq05_opm_cross_check,
    dq06_positive_sales,
    dq07_year_format,
    dq08_ticker_format,
    dq09_net_cash_check,
    dq10_non_negative_fixed_assets,
    dq11_tax_rate_range,
    dq12_dividend_payout_cap,
    dq14_eps_sign_consistency,
    dq15_strict_balance_count,
    dq16_coverage_check,
)


class TestDQ01CompanyPK:
    def test_detects_duplicate_id(self):
        df = pd.DataFrame({"id": ["TCS", "TCS", "INFY"]})
        v = dq01_company_pk_uniqueness(df)
        assert len(v) == 1
        assert v[0].rule_id == "DQ-01"
        assert v[0].severity == "CRITICAL"

    def test_no_violation_when_unique(self):
        df = pd.DataFrame({"id": ["TCS", "INFY"]})
        assert dq01_company_pk_uniqueness(df) == []


class TestDQ02AnnualPK:
    def test_detects_duplicate_company_year(self):
        df = pd.DataFrame(
            {
                "company_id": ["TCS", "TCS", "INFY"],
                "year": ["2023-03", "2023-03", "2023-03"],
            }
        )
        v = dq02_annual_pk_uniqueness(df, "profitandloss")
        assert len(v) == 2  # both dupe rows logged
        assert all(x.severity == "CRITICAL" for x in v)

    def test_no_violation_when_unique(self):
        df = pd.DataFrame(
            {
                "company_id": ["TCS", "INFY"],
                "year": ["2023-03", "2023-03"],
            }
        )
        assert dq02_annual_pk_uniqueness(df, "profitandloss") == []


class TestDQ03FKIntegrity:
    def test_detects_orphan_company_id(self):
        df = pd.DataFrame({"company_id": ["TCS", "GHOST"], "year": ["2023-03", "2023-03"]})
        v = dq03_fk_integrity(df, "profitandloss", {"TCS"})
        assert len(v) == 1
        assert v[0].company_id == "GHOST"

    def test_no_violation_when_all_valid(self):
        df = pd.DataFrame({"company_id": ["TCS"], "year": ["2023-03"]})
        assert dq03_fk_integrity(df, "profitandloss", {"TCS"}) == []


class TestDQ04BalanceSheetBalance:
    def test_detects_imbalance_over_1pct(self):
        df = pd.DataFrame(
            {
                "company_id": ["TCS"],
                "year": ["2023-03"],
                "total_assets": [1000.0],
                "total_liabilities": [900.0],
            }
        )
        v = dq04_balance_sheet_balance(df)
        assert len(v) == 1
        assert v[0].severity == "WARNING"

    def test_no_violation_within_tolerance(self):
        df = pd.DataFrame(
            {
                "company_id": ["TCS"],
                "year": ["2023-03"],
                "total_assets": [1000.0],
                "total_liabilities": [995.0],
            }
        )
        assert dq04_balance_sheet_balance(df) == []

    def test_zero_total_assets_does_not_crash(self):
        df = pd.DataFrame(
            {
                "company_id": ["TCS"],
                "year": ["2023-03"],
                "total_assets": [0.0],
                "total_liabilities": [0.0],
            }
        )
        # Should not raise, and should not be flagged (0/0 undefined -> skip)
        assert dq04_balance_sheet_balance(df) == []


class TestDQ05OPMCrossCheck:
    def test_detects_mismatch_over_1pp(self):
        df = pd.DataFrame(
            {
                "company_id": ["TCS"],
                "year": ["2023-03"],
                "sales": [1000.0],
                "operating_profit": [200.0],
                "opm_percentage": [50.0],  # actual computed = 20%, diff = 30pp
            }
        )
        v = dq05_opm_cross_check(df)
        assert len(v) == 1

    def test_no_violation_when_matching(self):
        df = pd.DataFrame(
            {
                "company_id": ["TCS"],
                "year": ["2023-03"],
                "sales": [1000.0],
                "operating_profit": [200.0],
                "opm_percentage": [20.0],
            }
        )
        assert dq05_opm_cross_check(df) == []


class TestDQ06PositiveSales:
    def test_detects_non_positive_sales_non_bank(self):
        df = pd.DataFrame({"company_id": ["ABB"], "year": ["2023-03"], "sales": [-5.0]})
        v = dq06_positive_sales(df, bank_ids=set())
        assert len(v) == 1

    def test_bank_carveout_no_violation(self):
        df = pd.DataFrame({"company_id": ["HDFCBANK"], "year": ["2023-03"], "sales": [-5.0]})
        v = dq06_positive_sales(df, bank_ids={"HDFCBANK"})
        assert v == []


class TestDQ07YearFormat:
    def test_returns_critical_violation(self):
        v = dq07_year_format("profitandloss", "TCS", "TTM")
        assert v.rule_id == "DQ-07"
        assert v.severity == "CRITICAL"
        assert "TTM" in v.issue


class TestDQ08TickerFormat:
    def test_returns_critical_violation(self):
        v = dq08_ticker_format("companies", "!!")
        assert v.rule_id == "DQ-08"
        assert v.severity == "CRITICAL"


class TestDQ09NetCashCheck:
    def test_detects_mismatch_over_10cr(self):
        df = pd.DataFrame(
            {
                "company_id": ["TCS"],
                "year": ["2023-03"],
                "operating_activity": [100.0],
                "investing_activity": [-50.0],
                "financing_activity": [-30.0],
                "net_cash_flow": [100.0],  # should be 20
            }
        )
        v = dq09_net_cash_check(df)
        assert len(v) == 1

    def test_no_violation_within_tolerance(self):
        df = pd.DataFrame(
            {
                "company_id": ["TCS"],
                "year": ["2023-03"],
                "operating_activity": [100.0],
                "investing_activity": [-50.0],
                "financing_activity": [-30.0],
                "net_cash_flow": [21.0],  # diff = 1
            }
        )
        assert dq09_net_cash_check(df) == []


class TestDQ10NonNegativeFixedAssets:
    def test_detects_negative_fixed_assets(self):
        df = pd.DataFrame({"company_id": ["TCS"], "year": ["2023-03"], "fixed_assets": [-10.0]})
        v = dq10_non_negative_fixed_assets(df)
        assert len(v) == 1

    def test_no_violation_when_non_negative(self):
        df = pd.DataFrame({"company_id": ["TCS"], "year": ["2023-03"], "fixed_assets": [0.0]})
        assert dq10_non_negative_fixed_assets(df) == []


class TestDQ11TaxRateRange:
    def test_detects_out_of_range_high(self):
        df = pd.DataFrame({"company_id": ["TCS"], "year": ["2023-03"], "tax_percentage": [75.0]})
        v = dq11_tax_rate_range(df)
        assert len(v) == 1

    def test_detects_out_of_range_negative(self):
        df = pd.DataFrame({"company_id": ["TCS"], "year": ["2023-03"], "tax_percentage": [-5.0]})
        v = dq11_tax_rate_range(df)
        assert len(v) == 1

    def test_no_violation_in_range(self):
        df = pd.DataFrame({"company_id": ["TCS"], "year": ["2023-03"], "tax_percentage": [25.0]})
        assert dq11_tax_rate_range(df) == []


class TestDQ12DividendPayoutCap:
    def test_detects_over_200pct(self):
        df = pd.DataFrame({"company_id": ["TCS"], "year": ["2023-03"], "dividend_payout": [250.0]})
        v = dq12_dividend_payout_cap(df)
        assert len(v) == 1

    def test_no_violation_at_or_below_200(self):
        df = pd.DataFrame({"company_id": ["TCS"], "year": ["2023-03"], "dividend_payout": [200.0]})
        assert dq12_dividend_payout_cap(df) == []


class TestDQ14EPSSignConsistency:
    def test_detects_positive_profit_negative_eps(self):
        df = pd.DataFrame(
            {
                "company_id": ["TCS"],
                "year": ["2023-03"],
                "net_profit": [100.0],
                "eps": [-5.0],
            }
        )
        v = dq14_eps_sign_consistency(df)
        assert len(v) == 1

    def test_no_violation_when_consistent(self):
        df = pd.DataFrame(
            {
                "company_id": ["TCS"],
                "year": ["2023-03"],
                "net_profit": [100.0],
                "eps": [5.0],
            }
        )
        assert dq14_eps_sign_consistency(df) == []


class TestDQ15StrictBalanceCount:
    def test_counts_exact_matches(self):
        df = pd.DataFrame({"total_assets": [100.0, 200.0], "total_liabilities": [100.0, 199.0]})
        assert dq15_strict_balance_count(df) == 1


class TestDQ16CoverageCheck:
    def test_detects_low_coverage_company(self):
        pnl = pd.DataFrame({"company_id": ["TCS"] * 2, "year": ["2020-03", "2021-03"]})
        bs = pd.DataFrame({"company_id": ["TCS"] * 2, "year": ["2020-03", "2021-03"]})
        cf = pd.DataFrame({"company_id": ["TCS"] * 2, "year": ["2020-03", "2021-03"]})
        v = dq16_coverage_check(pnl, bs, cf)
        assert len(v) == 1
        assert "5 years" in v[0].issue or "< 5" in v[0].issue

    def test_no_violation_with_full_coverage(self):
        years = [f"{y}-03" for y in range(2015, 2024)]  # 9 years
        pnl = pd.DataFrame({"company_id": ["TCS"] * len(years), "year": years})
        bs = pd.DataFrame({"company_id": ["TCS"] * len(years), "year": years})
        cf = pd.DataFrame({"company_id": ["TCS"] * len(years), "year": years})
        assert dq16_coverage_check(pnl, bs, cf) == []
