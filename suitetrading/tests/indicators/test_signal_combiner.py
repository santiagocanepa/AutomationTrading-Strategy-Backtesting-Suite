"""Tests for combine_signals() — validates excluyente/opcional/desactivado logic."""

import pandas as pd
import pytest

from suitetrading.indicators.base import IndicatorState
from suitetrading.indicators.signal_combiner import combine_signals


@pytest.fixture
def index() -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=10, freq="h")


class TestCombineExcluyenteOnly:
    """When all indicators are EXCLUYENTE (AND logic)."""

    def test_single_excluyente_returns_same_signal(self, index: pd.DatetimeIndex):
        sig = pd.Series([True, False, True, False, True, False, True, False, True, False], index=index)
        result = combine_signals(
            {"ind_a": sig},
            {"ind_a": IndicatorState.EXCLUYENTE},
        )
        pd.testing.assert_series_equal(result, sig, check_names=False)

    def test_two_excluyente_returns_and_of_both(self, index: pd.DatetimeIndex):
        sig_a = pd.Series([True, True, False, False, True, True, False, False, True, True], index=index)
        sig_b = pd.Series([True, False, True, False, True, False, True, False, True, False], index=index)
        result = combine_signals(
            {"a": sig_a, "b": sig_b},
            {"a": IndicatorState.EXCLUYENTE, "b": IndicatorState.EXCLUYENTE},
        )
        expected = sig_a & sig_b
        pd.testing.assert_series_equal(result, expected, check_names=False)

    def test_three_excluyente_returns_and_of_all(self, index: pd.DatetimeIndex):
        """Regression: previously this always returned False due to optional_count bug."""
        sig_a = pd.Series([True] * 10, index=index)
        sig_b = pd.Series([True] * 10, index=index)
        sig_c = pd.Series([True] * 10, index=index)
        result = combine_signals(
            {"a": sig_a, "b": sig_b, "c": sig_c},
            {"a": IndicatorState.EXCLUYENTE, "b": IndicatorState.EXCLUYENTE, "c": IndicatorState.EXCLUYENTE},
        )
        assert result.all(), "All-True excluyente signals must produce all-True combined"

    def test_three_excluyente_partial_overlap(self, index: pd.DatetimeIndex):
        """Regression: ensures non-trivial AND works with 3 indicators."""
        sig_a = pd.Series([True, True, True, False, False, True, True, True, False, True], index=index)
        sig_b = pd.Series([True, True, False, True, False, True, True, False, True, True], index=index)
        sig_c = pd.Series([True, False, True, True, False, True, False, True, True, True], index=index)
        result = combine_signals(
            {"a": sig_a, "b": sig_b, "c": sig_c},
            {"a": IndicatorState.EXCLUYENTE, "b": IndicatorState.EXCLUYENTE, "c": IndicatorState.EXCLUYENTE},
        )
        expected = sig_a & sig_b & sig_c
        pd.testing.assert_series_equal(result, expected, check_names=False)
        assert result.sum() > 0, "Partial overlap must produce some True entries"


class TestCombineOpcionalOnly:
    """When all indicators are OPCIONAL (quorum logic)."""

    def test_single_opcional_requires_one(self, index: pd.DatetimeIndex):
        sig = pd.Series([True, False, True, False, True, False, True, False, True, False], index=index)
        result = combine_signals(
            {"a": sig},
            {"a": IndicatorState.OPCIONAL},
            num_optional_required=1,
        )
        pd.testing.assert_series_equal(result, sig, check_names=False)

    def test_two_opcional_requires_two(self, index: pd.DatetimeIndex):
        sig_a = pd.Series([True, True, False, False, True, True, False, False, True, True], index=index)
        sig_b = pd.Series([True, False, True, False, True, False, True, False, True, False], index=index)
        result = combine_signals(
            {"a": sig_a, "b": sig_b},
            {"a": IndicatorState.OPCIONAL, "b": IndicatorState.OPCIONAL},
            num_optional_required=2,
        )
        expected = sig_a & sig_b
        pd.testing.assert_series_equal(result, expected, check_names=False)


class TestCombineMixed:
    """Mixed excluyente + opcional."""

    def test_excluyente_plus_opcional(self, index: pd.DatetimeIndex):
        excl = pd.Series([True, True, True, False, False, True, True, True, False, True], index=index)
        opt = pd.Series([True, False, True, False, True, False, True, False, True, False], index=index)
        result = combine_signals(
            {"excl": excl, "opt": opt},
            {"excl": IndicatorState.EXCLUYENTE, "opt": IndicatorState.OPCIONAL},
            num_optional_required=1,
        )
        expected = excl & opt
        pd.testing.assert_series_equal(result, expected, check_names=False)


class TestCombineDesactivado:
    """DESACTIVADO indicators are ignored."""

    def test_desactivado_ignored(self, index: pd.DatetimeIndex):
        active = pd.Series([True, False, True, False, True, False, True, False, True, False], index=index)
        inactive = pd.Series([False] * 10, index=index)
        result = combine_signals(
            {"active": active, "inactive": inactive},
            {"active": IndicatorState.EXCLUYENTE, "inactive": IndicatorState.DESACTIVADO},
        )
        pd.testing.assert_series_equal(result, active, check_names=False)

    def test_all_desactivado_returns_all_true(self, index: pd.DatetimeIndex):
        sig = pd.Series([False] * 10, index=index)
        result = combine_signals(
            {"a": sig},
            {"a": IndicatorState.DESACTIVADO},
        )
        assert result.all(), "No active indicators → excluyente_mask stays all-True"


class TestCombineMajority:
    """Majority-vote combination mode."""

    def test_majority_two_of_three(self, index: pd.DatetimeIndex):
        sig_a = pd.Series([True, True, False, False, True, True, False, False, True, True], index=index)
        sig_b = pd.Series([True, False, True, False, True, False, True, False, True, False], index=index)
        sig_c = pd.Series([False, True, True, False, False, True, True, False, False, True], index=index)
        result = combine_signals(
            {"a": sig_a, "b": sig_b, "c": sig_c},
            {"a": IndicatorState.EXCLUYENTE, "b": IndicatorState.EXCLUYENTE, "c": IndicatorState.EXCLUYENTE},
            combination_mode="majority",
        )
        # ceil(3/2) = 2 needed
        vote = sig_a.astype(int) + sig_b.astype(int) + sig_c.astype(int)
        expected = vote >= 2
        pd.testing.assert_series_equal(result, expected, check_names=False)

    def test_majority_with_custom_threshold(self, index: pd.DatetimeIndex):
        sig_a = pd.Series([True] * 10, index=index)
        sig_b = pd.Series([False] * 10, index=index)
        sig_c = pd.Series([True] * 10, index=index)
        result = combine_signals(
            {"a": sig_a, "b": sig_b, "c": sig_c},
            {"a": IndicatorState.EXCLUYENTE, "b": IndicatorState.EXCLUYENTE, "c": IndicatorState.EXCLUYENTE},
            combination_mode="majority",
            majority_threshold=3,
        )
        # Need all 3, but only 2 are True → all False
        assert not result.any()

    def test_majority_desactivado_excluded(self, index: pd.DatetimeIndex):
        sig_a = pd.Series([True] * 10, index=index)
        sig_b = pd.Series([False] * 10, index=index)
        result = combine_signals(
            {"a": sig_a, "b": sig_b},
            {"a": IndicatorState.EXCLUYENTE, "b": IndicatorState.DESACTIVADO},
            combination_mode="majority",
        )
        # Only 1 active, threshold=ceil(1/2)=1 → a's signal
        pd.testing.assert_series_equal(result, sig_a, check_names=False)

    def test_majority_produces_more_signals_than_and(self, index: pd.DatetimeIndex):
        sig_a = pd.Series([True, True, False, True, False, True, True, False, True, False], index=index)
        sig_b = pd.Series([True, False, True, True, False, False, True, True, False, True], index=index)
        sig_c = pd.Series([False, True, True, False, True, True, False, True, True, False], index=index)

        and_result = combine_signals(
            {"a": sig_a, "b": sig_b, "c": sig_c},
            {"a": IndicatorState.EXCLUYENTE, "b": IndicatorState.EXCLUYENTE, "c": IndicatorState.EXCLUYENTE},
            combination_mode="excluyente",
        )
        majority_result = combine_signals(
            {"a": sig_a, "b": sig_b, "c": sig_c},
            {"a": IndicatorState.EXCLUYENTE, "b": IndicatorState.EXCLUYENTE, "c": IndicatorState.EXCLUYENTE},
            combination_mode="majority",
        )
        # Majority should always produce >= signals than AND
        assert majority_result.sum() >= and_result.sum()
