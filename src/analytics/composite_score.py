"""
src/analytics/composite_score.py

Sprint 2, Day 12 — provisional `composite_quality_score` column.

This is NOT the 0-100 health score with Excellent/Good/Average/Weak/Poor
bands from the project spec — that's a Sprint 3 deliverable (Epic 03,
Health Score) which will likely fold in screener/peer-percentile context
this module doesn't have. This is a simpler, purely ratio-driven
composite (same 0-100 scale so Sprint 3 can reuse or replace it) meant to
give the financial_ratios table *some* single-number quality signal for
Day 12's "populate financial_ratios" deliverable, and to give Sprint 3 a
concrete baseline to improve on.

Five equally-weighted-ish components, each clipped to [0, its max]:
    ROE                  0-25 pts   (25 pts at ROE >= 30%)
    ROCE                 0-25 pts   (25 pts at ROCE >= 30%)
    Low leverage (D/E)   0-20 pts   (20 pts at D/E = 0, 0 pts at D/E >= 5)
    Interest coverage    0-15 pts   (15 pts at ICR >= 3, 0 pts at ICR <= 1;
                                      debt-free companies score the full 15)
    Revenue CAGR (5yr)   0-15 pts   (15 pts at CAGR >= 20%, 0 pts at CAGR <= 0)

Any component whose underlying ratio is None (undefined, e.g. negative
equity) contributes 0 points rather than being excluded/reweighted — a
missing ratio is itself informative (something is structurally off) and
shouldn't let the company "skip" that dimension of the score.
"""

from __future__ import annotations

from typing import Optional

from src.analytics.utils import clean


def _clip_scale(value: Optional[float], lo: float, hi: float, max_pts: float) -> float:
    """Linearly scale `value` from [lo, hi] to [0, max_pts], clipped at both ends."""
    value = clean(value)
    if value is None:
        return 0.0
    if value <= lo:
        return 0.0
    if value >= hi:
        return max_pts
    return (value - lo) / (hi - lo) * max_pts


def composite_quality_score(
    roe_pct: Optional[float],
    roce_pct: Optional[float],
    debt_to_equity: Optional[float],
    interest_coverage: Optional[float],
    is_debt_free: bool,
    revenue_cagr_5yr_pct: Optional[float],
) -> float:
    roe_pts = _clip_scale(roe_pct, 0, 30, 25)
    roce_pts = _clip_scale(roce_pct, 0, 30, 25)

    debt_to_equity = clean(debt_to_equity)
    if debt_to_equity is None:
        de_pts = 0.0
    else:
        # Inverted: lower D/E -> higher points.
        de_pts = 20 - _clip_scale(debt_to_equity, 0, 5, 20)

    if is_debt_free:
        icr_pts = 15.0
    else:
        icr_pts = _clip_scale(interest_coverage, 1, 3, 15)

    cagr_pts = _clip_scale(revenue_cagr_5yr_pct, 0, 20, 15)

    return round(roe_pts + roce_pts + de_pts + icr_pts + cagr_pts, 2)
