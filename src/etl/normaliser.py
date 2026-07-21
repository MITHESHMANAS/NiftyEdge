"""
src/etl/normaliser.py

Field normalisation utilities for the N100 ETL pipeline.

    normalize_year(raw)   -> 'YYYY-MM' | None
    normalize_ticker(raw) -> 'TICKER'  | None

Both return None on unparseable / invalid input; the caller (loader.py /
validator.py) is responsible for logging and rejecting the row per DQ-07 /
DQ-08.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from src.etl.constants import (
    NON_PERIOD_VALUES,
    SUPPORTED_MONTHS,
    TICKER_MAX_LEN,
    TICKER_MIN_LEN,
)

_MONTH_MAP = SUPPORTED_MONTHS

# 'Mar 2023', 'Dec 2012', trailing garbage allowed ('Mar 2023 15', 'Mar 2016 9m')
_RE_MONTH_YEAR_LONG = re.compile(r"^(?P<mon>[A-Za-z]{3})[a-z]*\s+(?P<year>\d{4})\b")
# 'Mar-23', 'Mar-13' (2-digit year, hyphenated)
_RE_MONTH_YEAR_SHORT = re.compile(r"^(?P<mon>[A-Za-z]{3})[a-z]*-(?P<year>\d{2})$")
# Bare 4-digit year: '2013', '2024' (no month given -> assume Indian FY-end March)
_RE_BARE_YEAR = re.compile(r"^(?P<year>\d{4})$")


def normalize_year(raw) -> Optional[str]:
    """
    Standardise a raw year/period label to 'YYYY-MM'.

    Handles, in order:
      - 'Mar 2023' / 'Dec 2012' / 'Sep 2024' / 'Jun 2020'   -> 'YYYY-MM'
      - 'Mar 2023 15' / 'Mar 2016 9m' (trailing junk/partial-year note)
                                                              -> base 'YYYY-MM'
      - 'Mar-23' / 'Mar-13'  (2-digit year)                  -> 'YYYY-MM'
      - '2013' (bare year, no month)                         -> 'YYYY-03'
                                                                 (assume Mar FYE)
      - 'TTM', '2024.5', empty/None, or anything else unparseable -> None

    Returns None (never raises) so the validator can log DQ-07 violations
    uniformly.
    """
    if raw is None:
        return None

    s = str(raw).strip()
    if not s:
        return None

    if s.lower() in NON_PERIOD_VALUES:
        return None

    m = _RE_MONTH_YEAR_LONG.match(s)
    if m:
        mon = m.group("mon").lower()
        year = m.group("year")
        if mon in _MONTH_MAP:
            return f"{year}-{_MONTH_MAP[mon]}"
        return None

    m = _RE_MONTH_YEAR_SHORT.match(s)
    if m:
        mon = m.group("mon").lower()
        yy = int(m.group("year"))
        if mon in _MONTH_MAP:
            year = 2000 + yy if yy <= 79 else 1900 + yy
            return f"{year}-{_MONTH_MAP[mon]}"
        return None

    m = _RE_BARE_YEAR.match(s)
    if m:
        # No month component supplied (e.g. balancesheet.xlsx some rows).
        # Assume standard Indian fiscal year-end (March) per project convention.
        return f"{m.group('year')}-03"

    # Anything else (e.g. '2024.5', garbage strings) is unparseable.
    return None


# Valid NSE ticker length band per DQ-08 (2-12 chars after normalisation).
_RE_TICKER_CHARS = re.compile(r"^[A-Z0-9&\-]+$")


def normalize_ticker(raw) -> Optional[str]:
    """
    Standardise a raw company_id / ticker: strip whitespace, uppercase.
    Returns None if the result is empty or outside the valid length band
    (2-12 chars) or contains characters not seen in real NSE tickers
    (letters, digits, '&', '-').
    """
    if raw is None:
        return None

    s = str(raw).strip().upper()
    if not s:
        return None

    if not (TICKER_MIN_LEN <= len(s) <= TICKER_MAX_LEN):
        return None

    if not _RE_TICKER_CHARS.match(s):
        return None

    return s


# ---------------------------------------------------------------------------
# analysis.xlsx text-field parser (compounded_sales_growth, roe, etc.)
# e.g. '10 Years: 21%' -> (10.0, 21.0)
# ---------------------------------------------------------------------------
_RE_PERIOD_PCT = re.compile(r"(\d+)\s*Years?:?\s*([\d.]+)\s*%")


def parse_period_pct(raw) -> Tuple[Optional[float], Optional[float]]:
    """
    Parse a 'analysis.xlsx' style string like '10 Years: 21%' into
    (period_years, pct_value). Returns (None, None) if unparseable.
    """
    if raw is None:
        return (None, None)
    s = str(raw)
    m = _RE_PERIOD_PCT.search(s)
    if not m:
        return (None, None)
    return (float(m.group(1)), float(m.group(2)))
