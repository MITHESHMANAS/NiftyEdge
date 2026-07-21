"""
tests/screener/test_peer.py

Sprint 3, Day 18 — peer percentile ranking unit tests.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.analytics.peer import NO_PEER_GROUP_MESSAGE, _percent_rank


class TestPercentRank:
    def test_highest_value_gets_percentile_1(self):
        s = pd.Series([10, 20, 30, 40, 50])
        pct = _percent_rank(s)
        assert pct.iloc[4] == 1.0

    def test_lowest_value_gets_percentile_0(self):
        s = pd.Series([10, 20, 30, 40, 50])
        pct = _percent_rank(s)
        assert pct.iloc[0] == 0.0

    def test_evenly_spaced_for_5_values(self):
        s = pd.Series([10, 20, 30, 40, 50])
        pct = _percent_rank(s)
        assert list(pct) == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0])

    def test_single_member_group_gets_1(self):
        s = pd.Series([42])
        pct = _percent_rank(s)
        assert pct.iloc[0] == 1.0

    def test_missing_values_excluded_and_return_nan(self):
        s = pd.Series([10, None, 30])
        pct = _percent_rank(s)
        assert pd.isna(pct.iloc[1])
        assert pct.iloc[0] == 0.0
        assert pct.iloc[2] == 1.0

    def test_empty_series_returns_empty(self):
        s = pd.Series([], dtype=float)
        pct = _percent_rank(s)
        assert len(pct) == 0

    def test_tied_values_get_averaged_rank(self):
        s = pd.Series([10, 20, 20, 30])
        pct = _percent_rank(s)
        # both 20s should get the same (averaged) percentile
        assert pct.iloc[1] == pct.iloc[2]


class TestNoPeerGroupMessage:
    def test_message_constant_is_exact_spec_string(self):
        assert NO_PEER_GROUP_MESSAGE == "No peer group assigned"
