"""
src/analytics/ratios.py

Sprint 2, Day 08-09 — Profitability, Leverage & Efficiency Ratios.

Every function returns `None` for a genuinely undefined ratio (e.g. dividing
by a zero or negative denominator that makes the ratio meaningless) rather
than raising or returning 0 / inf, so downstream consumers (screener,
health score) can distinguish "ratio is zero" from "ratio doesn't apply
here". The one deliberate exception is `debt_to_equity`, which returns 0.0
for debt-free companies per the spec (0 is a meaningful, correct D/E value
when borrowings = 0, unlike the other ratios).

Every function runs its inputs through `clean()` first, so it's safe to
call directly with values pulled out of a pandas row/Series (where a
missing value surfaces as NaN, not None) as well as with plain Python
values (as the unit tests do).
"""

from __future__ import annotations

from typing import Optional

from src.analytics.utils import clean

# Sector name used for the Financials carve-out (D/E flag suppression,
# sector-relative ROCE benchmarking). Matches the `broad_sector` value in
# the `sectors` table.
FINANCIALS_SECTOR = "Financials"

HIGH_LEVERAGE_DE_THRESHOLD = 5.0
ICR_RISK_THRESHOLD = 1.5
OPM_CROSS_CHECK_TOLERANCE_PP = 1.0


# ---------------------------------------------------------------------------
# Day 08 — Profitability Ratios
# ---------------------------------------------------------------------------
def net_profit_margin(net_profit: Optional[float], sales: Optional[float]) -> Optional[float]:
    """NPM = net_profit / sales x 100. None if sales = 0 or either input missing."""
    net_profit, sales = clean(net_profit), clean(sales)
    if net_profit is None or sales is None or sales == 0:
        return None
    return (net_profit / sales) * 100


def operating_profit_margin(
    operating_profit: Optional[float], sales: Optional[float]
) -> Optional[float]:
    """OPM = operating_profit / sales x 100. None if sales = 0 or either input missing."""
    operating_profit, sales = clean(operating_profit), clean(sales)
    if operating_profit is None or sales is None or sales == 0:
        return None
    return (operating_profit / sales) * 100


def opm_cross_check(computed_opm: Optional[float], source_opm: Optional[float]) -> bool:
    """
    Returns True (mismatch) if the computed OPM differs from the source
    `opm_percentage` field by more than 1 percentage point. Used to set
    the `opm_cross_check_mismatch` flag written to financial_ratios.
    """
    computed_opm, source_opm = clean(computed_opm), clean(source_opm)
    if computed_opm is None or source_opm is None:
        return False
    return abs(computed_opm - source_opm) > OPM_CROSS_CHECK_TOLERANCE_PP


def return_on_equity(
    net_profit: Optional[float], equity_capital: Optional[float], reserves: Optional[float]
) -> Optional[float]:
    """ROE = net_profit / (equity_capital + reserves) x 100.
    None if net worth <= 0 (negative-equity companies) or inputs missing."""
    net_profit = clean(net_profit)
    equity_capital = clean(equity_capital)
    reserves = clean(reserves)
    if net_profit is None or equity_capital is None or reserves is None:
        return None
    net_worth = equity_capital + reserves
    if net_worth <= 0:
        return None
    return (net_profit / net_worth) * 100


def ebit(profit_before_tax: Optional[float], interest: Optional[float]) -> Optional[float]:
    """EBIT = PBT + Interest expense (added back). Used by ROCE."""
    profit_before_tax, interest = clean(profit_before_tax), clean(interest)
    if profit_before_tax is None or interest is None:
        return None
    return profit_before_tax + interest


def return_on_capital_employed(
    ebit_value: Optional[float],
    equity_capital: Optional[float],
    reserves: Optional[float],
    borrowings: Optional[float],
) -> Optional[float]:
    """
    ROCE = EBIT / (equity_capital + reserves + borrowings) x 100.
    None if capital employed <= 0 or inputs missing.

    Note: for Financials-sector companies, ROCE is not comparable to an
    absolute threshold (see `high_leverage_flag` below) — the absolute
    ROCE value is still computed here; the sector-relative interpretation
    happens at screening/scoring time using the sector median from the
    `sectors`/`financial_ratios` join.
    """
    ebit_value = clean(ebit_value)
    equity_capital = clean(equity_capital)
    reserves = clean(reserves)
    borrowings = clean(borrowings)
    if ebit_value is None or equity_capital is None or reserves is None or borrowings is None:
        return None
    capital_employed = equity_capital + reserves + borrowings
    if capital_employed <= 0:
        return None
    return (ebit_value / capital_employed) * 100


def is_financials_sector(broad_sector: Optional[str]) -> bool:
    return clean(broad_sector) == FINANCIALS_SECTOR


def return_on_assets(net_profit: Optional[float], total_assets: Optional[float]) -> Optional[float]:
    """ROA = net_profit / total_assets x 100. None if total_assets = 0 or inputs missing."""
    net_profit, total_assets = clean(net_profit), clean(total_assets)
    if net_profit is None or total_assets is None or total_assets == 0:
        return None
    return (net_profit / total_assets) * 100


# ---------------------------------------------------------------------------
# Day 09 — Leverage & Efficiency Ratios
# ---------------------------------------------------------------------------
def debt_to_equity(
    borrowings: Optional[float], equity_capital: Optional[float], reserves: Optional[float]
) -> Optional[float]:
    """
    D/E = borrowings / (equity_capital + reserves).
    Returns 0.0 (NOT None) if borrowings = 0 — a debt-free company has a
    genuinely, meaningfully zero D/E ratio. Returns None only if net worth
    is non-positive (ratio undefined) or inputs are missing.
    """
    borrowings = clean(borrowings)
    equity_capital = clean(equity_capital)
    reserves = clean(reserves)
    if borrowings is None or equity_capital is None or reserves is None:
        return None
    if borrowings == 0:
        return 0.0
    net_worth = equity_capital + reserves
    if net_worth <= 0:
        return None
    return borrowings / net_worth


def high_leverage_flag(de_ratio: Optional[float], broad_sector: Optional[str]) -> bool:
    """True if D/E > 5 and the company is NOT in the Financials sector
    (high leverage is structurally normal for banks/NBFCs/insurers)."""
    de_ratio = clean(de_ratio)
    if de_ratio is None:
        return False
    if is_financials_sector(broad_sector):
        return False
    return de_ratio > HIGH_LEVERAGE_DE_THRESHOLD


def interest_coverage(
    operating_profit: Optional[float], other_income: Optional[float], interest: Optional[float]
) -> Optional[float]:
    """ICR = (operating_profit + other_income) / interest. None if interest = 0
    (debt-free company — see `icr_label` for the display value in that case)."""
    operating_profit = clean(operating_profit)
    other_income = clean(other_income)
    interest = clean(interest)
    if operating_profit is None or interest is None:
        return None
    oi = other_income or 0
    if interest == 0:
        return None
    return (operating_profit + oi) / interest


def icr_label(interest: Optional[float]) -> Optional[str]:
    """Returns 'Debt Free' when interest = 0 (ICR is undefined/None in that
    case); otherwise None (no special label — the numeric ICR applies)."""
    interest = clean(interest)
    if interest == 0:
        return "Debt Free"
    return None


def icr_risk_flag(icr: Optional[float]) -> bool:
    """True if ICR < 1.5 — company may struggle to cover interest payments."""
    icr = clean(icr)
    if icr is None:
        return False
    return icr < ICR_RISK_THRESHOLD


def net_debt(borrowings: Optional[float], investments: Optional[float]) -> Optional[float]:
    """Net Debt = borrowings - investments (investments used as a liquid-
    asset proxy). Can be negative (net cash position)."""
    borrowings, investments = clean(borrowings), clean(investments)
    if borrowings is None or investments is None:
        return None
    return borrowings - investments


def asset_turnover(sales: Optional[float], total_assets: Optional[float]) -> Optional[float]:
    """Asset Turnover = sales / total_assets. None if total_assets = 0."""
    sales, total_assets = clean(sales), clean(total_assets)
    if sales is None or total_assets is None or total_assets == 0:
        return None
    return sales / total_assets
