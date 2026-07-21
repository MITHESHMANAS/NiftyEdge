"""
src/etl/constants.py

Central location for literals shared across the ETL pipeline, so they're
defined once instead of scattered as magic strings through loader.py /
validator.py / normaliser.py.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Table names — write order matters (companies must be written before any
# child table with a FK into it).
# ---------------------------------------------------------------------------
TABLE_COMPANIES = "companies"
TABLE_PROFITANDLOSS = "profitandloss"
TABLE_BALANCESHEET = "balancesheet"
TABLE_CASHFLOW = "cashflow"
TABLE_ANALYSIS = "analysis"
TABLE_DOCUMENTS = "documents"
TABLE_PROSANDCONS = "prosandcons"
TABLE_SECTORS = "sectors"
TABLE_STOCK_PRICES = "stock_prices"
TABLE_MARKET_CAP = "market_cap"
TABLE_FINANCIAL_RATIOS = "financial_ratios"
TABLE_PEER_GROUPS = "peer_groups"

TABLE_WRITE_ORDER = [
    TABLE_COMPANIES,
    TABLE_PROFITANDLOSS,
    TABLE_BALANCESHEET,
    TABLE_CASHFLOW,
    TABLE_ANALYSIS,
    TABLE_DOCUMENTS,
    TABLE_PROSANDCONS,
    TABLE_SECTORS,
    TABLE_STOCK_PRICES,
    TABLE_MARKET_CAP,
    TABLE_FINANCIAL_RATIOS,
    TABLE_PEER_GROUPS,
]

CORE_TABLES = [
    TABLE_COMPANIES,
    TABLE_PROFITANDLOSS,
    TABLE_BALANCESHEET,
    TABLE_CASHFLOW,
    TABLE_ANALYSIS,
    TABLE_DOCUMENTS,
    TABLE_PROSANDCONS,
]
SUPPLEMENTARY_TABLES = [
    TABLE_SECTORS,
    TABLE_STOCK_PRICES,
    TABLE_MARKET_CAP,
    TABLE_FINANCIAL_RATIOS,
    TABLE_PEER_GROUPS,
]

# ---------------------------------------------------------------------------
# DQ severity levels
# ---------------------------------------------------------------------------
DQ_CRITICAL = "CRITICAL"
DQ_WARNING = "WARNING"
DQ_INFO = "INFO"
DQ_LEVELS = (DQ_CRITICAL, DQ_WARNING, DQ_INFO)

# ---------------------------------------------------------------------------
# Month abbreviations recognised by normalize_year(). Mar/Jun/Sep/Dec are
# the ones actually observed in the source data (Indian quarter-end
# labels); the rest are included for robustness against future source
# files that may use other month-ends.
# ---------------------------------------------------------------------------
SUPPORTED_MONTHS = {
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}

# Period labels that look like a year but are NOT a normal fiscal-year
# period and must be rejected by normalize_year() rather than guessed at.
NON_PERIOD_VALUES = {"ttm"}

# ---------------------------------------------------------------------------
# Ticker format constraints (DQ-08)
# ---------------------------------------------------------------------------
TICKER_MIN_LEN = 2
TICKER_MAX_LEN = 12

# ---------------------------------------------------------------------------
# Bank / financial-services tickers exempt from DQ-06's positive-sales
# check (banks report "sales" as interest income, structured differently).
# ---------------------------------------------------------------------------
BANK_TICKERS = {
    "HDFCBANK",
    "ICICIBANK",
    "AXISBANK",
    "KOTAKBANK",
    "INDUSINDBK",
    "SBIN",
    "BANKBARODA",
    "CANBK",
    "PNB",
}

# ---------------------------------------------------------------------------
# DQ tolerance thresholds
# ---------------------------------------------------------------------------
BALANCE_SHEET_TOLERANCE_PCT = 0.01  # DQ-04
OPM_CROSS_CHECK_TOLERANCE_PP = 1.0  # DQ-05
NET_CASH_TOLERANCE_CR = 10  # DQ-09
TAX_RATE_MIN_PCT = 0  # DQ-11
TAX_RATE_MAX_PCT = 60  # DQ-11
DIVIDEND_PAYOUT_MAX_PCT = 200  # DQ-12
COVERAGE_MIN_YEARS_FLAG = 5  # DQ-16 (flag below this)
COVERAGE_MIN_YEARS_CAGR = 3  # DQ-16 (exclude from CAGR below this)
