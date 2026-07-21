"""
src/analytics/cashflow_kpis.py

Sprint 2, Day 11 — Cash Flow KPIs & Capital Allocation.
"""

from __future__ import annotations

from typing import Iterable, Optional, Tuple

from src.analytics.utils import clean

# CFO Quality Score bands
CFO_QUALITY_HIGH = "High Quality"
CFO_QUALITY_MODERATE = "Moderate"
CFO_QUALITY_ACCRUAL_RISK = "Accrual Risk"

# CapEx Intensity bands
CAPEX_ASSET_LIGHT = "Asset Light"
CAPEX_MODERATE = "Moderate"
CAPEX_CAPITAL_INTENSIVE = "Capital Intensive"

# Capital allocation 8-pattern classifier labels
PATTERN_REINVESTOR = "Reinvestor"
PATTERN_SHAREHOLDER_RETURNS = "Shareholder Returns"
PATTERN_LIQUIDATING_ASSETS = "Liquidating Assets"
PATTERN_DISTRESS_SIGNAL = "Distress Signal"
PATTERN_GROWTH_FUNDED_BY_DEBT = "Growth Funded by Debt"
PATTERN_CASH_ACCUMULATOR = "Cash Accumulator"
PATTERN_PRE_REVENUE = "Pre-Revenue"
PATTERN_MIXED = "Mixed"
# Sign combination (-,+,-) isn't defined by the spec's 8 labels (which cover
# 7 of the 8 possible sign tuples, splitting (+,-,-) into two by CFO/PAT
# quality). We label the undefined combination explicitly rather than
# mis-bucketing it, and log it as an edge case.
PATTERN_UNCLASSIFIED = "Unclassified"

# CFO/PAT threshold above which a (+,-,-) company is labelled "Shareholder
# Returns" (distributing more than it retains) rather than "Reinvestor".
SHAREHOLDER_RETURNS_CFO_PAT_THRESHOLD = 1.0


def free_cash_flow(
    operating_activity: Optional[float], investing_activity: Optional[float]
) -> Optional[float]:
    """FCF = CFO + CFI. Negative values are allowed (and meaningful)."""
    operating_activity, investing_activity = clean(operating_activity), clean(investing_activity)
    if operating_activity is None or investing_activity is None:
        return None
    return operating_activity + investing_activity


def cfo_quality_score(
    cfo_series: Iterable[Optional[float]], pat_series: Iterable[Optional[float]]
) -> Tuple[Optional[float], Optional[str]]:
    """
    CFO Quality Score = mean(CFO_i / PAT_i) across up to 5 years, computed
    only over years where PAT > 0 (a CFO/PAT ratio for a loss-making year
    is not meaningful for "quality of earnings" purposes and is skipped).

    Returns (None, None) if no valid (PAT > 0) years are available.

        > 1.0        -> High Quality   (cash generation exceeds reported profit)
        0.5 - 1.0     -> Moderate
        < 0.5         -> Accrual Risk  (profit not backed by cash)
    """
    ratios = []
    for cfo, pat in zip(cfo_series, pat_series):
        cfo, pat = clean(cfo), clean(pat)
        if cfo is None or pat is None or pat <= 0:
            continue
        ratios.append(cfo / pat)

    if not ratios:
        return None, None

    score = sum(ratios) / len(ratios)
    if score > 1.0:
        label = CFO_QUALITY_HIGH
    elif score >= 0.5:
        label = CFO_QUALITY_MODERATE
    else:
        label = CFO_QUALITY_ACCRUAL_RISK
    return score, label


def capex_intensity(
    investing_activity: Optional[float], sales: Optional[float]
) -> Tuple[Optional[float], Optional[str]]:
    """
    CapEx Intensity = abs(investing_activity) / sales x 100.
        < 3%   -> Asset Light
        3-8%   -> Moderate
        > 8%   -> Capital Intensive
    Returns (None, None) if sales is 0/None or investing_activity is None.
    """
    investing_activity, sales = clean(investing_activity), clean(sales)
    if investing_activity is None or sales is None or sales == 0:
        return None, None

    pct = abs(investing_activity) / sales * 100
    if pct < 3:
        label = CAPEX_ASSET_LIGHT
    elif pct <= 8:
        label = CAPEX_MODERATE
    else:
        label = CAPEX_CAPITAL_INTENSIVE
    return pct, label


def fcf_conversion_rate(fcf: Optional[float], operating_profit: Optional[float]) -> Optional[float]:
    """FCF Conversion Rate = FCF / operating_profit x 100. None if operating_profit = 0."""
    fcf, operating_profit = clean(fcf), clean(operating_profit)
    if fcf is None or operating_profit is None or operating_profit == 0:
        return None
    return (fcf / operating_profit) * 100


def _sign(value: Optional[float]) -> str:
    """Two-way sign bucket used for the capital-allocation pattern: '+' for
    strictly positive, '-' for zero or negative (financing/investing
    activity of exactly 0 is rare and behaves like a non-event, so it's
    grouped with negative rather than given its own bucket)."""
    value = clean(value)
    if value is None:
        return "-"
    return "+" if value > 0 else "-"


def classify_capital_allocation(
    cfo: Optional[float],
    cfi: Optional[float],
    cff: Optional[float],
    cfo_over_pat: Optional[float] = None,
) -> Tuple[str, str, str, str]:
    """
    Classifies a company-year into one of the 8 capital-allocation
    patterns based on the sign of (CFO, CFI, CFF), per spec Day 11.

    Returns (cfo_sign, cfi_sign, cff_sign, pattern_label) — the three sign
    strings ('+'/'-') are also what gets written to
    output/capital_allocation.csv.
    """
    cfo_sign = _sign(cfo)
    cfi_sign = _sign(cfi)
    cff_sign = _sign(cff)

    key = (cfo_sign, cfi_sign, cff_sign)
    cfo_over_pat = clean(cfo_over_pat)

    if key == ("+", "-", "-"):
        if cfo_over_pat is not None and cfo_over_pat > SHAREHOLDER_RETURNS_CFO_PAT_THRESHOLD:
            label = PATTERN_SHAREHOLDER_RETURNS
        else:
            label = PATTERN_REINVESTOR
    elif key == ("+", "+", "-"):
        label = PATTERN_LIQUIDATING_ASSETS
    elif key == ("-", "+", "+"):
        label = PATTERN_DISTRESS_SIGNAL
    elif key == ("-", "-", "+"):
        label = PATTERN_GROWTH_FUNDED_BY_DEBT
    elif key == ("+", "+", "+"):
        label = PATTERN_CASH_ACCUMULATOR
    elif key == ("-", "-", "-"):
        label = PATTERN_PRE_REVENUE
    elif key == ("+", "-", "+"):
        label = PATTERN_MIXED
    else:
        # (-, +, -) — not defined by the spec's 8 labels.
        label = PATTERN_UNCLASSIFIED

    return cfo_sign, cfi_sign, cff_sign, label
