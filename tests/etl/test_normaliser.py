"""
tests/etl/test_normaliser.py

35+ unit tests for normalize_year() (20 cases) and normalize_ticker()
(15 cases), plus a few for parse_period_pct(), per Sprint 1 Day 02 spec.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.etl.normaliser import normalize_ticker, normalize_year, parse_period_pct


# ===========================================================================
# normalize_year() — 20 cases
# ===========================================================================
class TestNormalizeYear:
    # -- 'Mon YYYY' long form --------------------------------------------
    def test_mar_full_year(self):
        assert normalize_year("Mar 2023") == "2023-03"

    def test_dec_full_year(self):
        assert normalize_year("Dec 2012") == "2012-12"

    def test_sep_full_year(self):
        assert normalize_year("Sep 2024") == "2024-09"

    def test_jun_full_year(self):
        assert normalize_year("Jun 2020") == "2020-06"

    def test_mon_year_extra_whitespace(self):
        assert normalize_year("  Mar 2023 ") == "2023-03"

    # -- trailing junk / partial-year notes -------------------------------
    def test_mar_year_trailing_number(self):
        assert normalize_year("Mar 2023 15") == "2023-03"

    def test_mar_year_partial_months_note(self):
        assert normalize_year("Mar 2016 9m") == "2016-03"

    # -- 'Mon-YY' short hyphenated form ------------------------------------
    def test_mar_hyphen_two_digit(self):
        assert normalize_year("Mar-23") == "2023-03"

    def test_mar_hyphen_two_digit_older(self):
        assert normalize_year("Mar-13") == "2013-03"

    def test_dec_hyphen_two_digit(self):
        assert normalize_year("Dec-99") == "1999-12"

    # -- bare 4-digit year (no month) --------------------------------------
    def test_bare_year_assumes_march_fye(self):
        assert normalize_year("2013") == "2013-03"

    def test_bare_year_recent(self):
        assert normalize_year("2024") == "2024-03"

    # -- explicitly rejected / unparseable values ---------------------------
    def test_ttm_rejected(self):
        assert normalize_year("TTM") is None

    def test_ttm_case_insensitive_rejected(self):
        assert normalize_year("ttm") is None

    def test_half_year_marker_rejected(self):
        assert normalize_year("2024.5") is None

    def test_none_input_rejected(self):
        assert normalize_year(None) is None

    def test_empty_string_rejected(self):
        assert normalize_year("") is None

    def test_whitespace_only_rejected(self):
        assert normalize_year("   ") is None

    def test_garbage_string_rejected(self):
        assert normalize_year("not a year") is None

    def test_invalid_month_abbrev_rejected(self):
        assert normalize_year("Xyz 2023") is None

    def test_numeric_input_int(self):
        # openpyxl can sometimes hand back an int for bare-year cells
        assert normalize_year(2019) == "2019-03"


# ===========================================================================
# normalize_ticker() — 15 cases
# ===========================================================================
class TestNormalizeTicker:
    def test_simple_uppercase_passthrough(self):
        assert normalize_ticker("TCS") == "TCS"

    def test_lowercase_converted_to_upper(self):
        assert normalize_ticker("tcs") == "TCS"

    def test_mixed_case_converted(self):
        assert normalize_ticker("Infy") == "INFY"

    def test_strips_leading_trailing_whitespace(self):
        assert normalize_ticker("  HDFCBANK  ") == "HDFCBANK"

    def test_hyphenated_ticker_preserved(self):
        assert normalize_ticker("bajaj-auto") == "BAJAJ-AUTO"

    def test_ampersand_ticker_preserved(self):
        assert normalize_ticker("m&m") == "M&M"

    def test_none_rejected(self):
        assert normalize_ticker(None) is None

    def test_empty_string_rejected(self):
        assert normalize_ticker("") is None

    def test_whitespace_only_rejected(self):
        assert normalize_ticker("   ") is None

    def test_single_char_too_short_rejected(self):
        assert normalize_ticker("A") is None

    def test_two_char_minimum_accepted(self):
        assert normalize_ticker("AB") == "AB"

    def test_twelve_char_maximum_accepted(self):
        assert normalize_ticker("ABCDEFGHIJKL") == "ABCDEFGHIJKL"

    def test_thirteen_char_too_long_rejected(self):
        assert normalize_ticker("ABCDEFGHIJKLM") is None

    def test_invalid_characters_rejected(self):
        assert normalize_ticker("TCS!") is None

    def test_numeric_ticker_accepted(self):
        # Some NSE tickers/ids could theoretically be numeric-only after
        # normalisation; length band still applies.
        assert normalize_ticker("12345") == "12345"


# ===========================================================================
# parse_period_pct() — bonus coverage for analysis.xlsx text parsing
# ===========================================================================
class TestParsePeriodPct:
    def test_standard_format(self):
        assert parse_period_pct("10 Years: 21%") == (10.0, 21.0)

    def test_extra_whitespace(self):
        assert parse_period_pct("10 Years:     17%") == (10.0, 17.0)

    def test_single_year_singular(self):
        assert parse_period_pct("1 Year: 5%") == (1.0, 5.0)

    def test_decimal_percentage(self):
        assert parse_period_pct("5 Years: 6.25%") == (5.0, 6.25)

    def test_none_input(self):
        assert parse_period_pct(None) == (None, None)

    def test_unparseable_string(self):
        assert parse_period_pct("N/A") == (None, None)
