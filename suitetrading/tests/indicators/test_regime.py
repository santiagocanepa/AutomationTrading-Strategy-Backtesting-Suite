"""Tests for market regime classifier."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.indicators.regime import MarketRegime, RegimeClassifier


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 500
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.5, 2.0, n)
    low = close - rng.uniform(0.5, 2.0, n)
    return pd.DataFrame({
        "open": close + rng.normal(0, 0.3, n),
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.uniform(1000, 5000, n),
    })


class TestRegimeClassifier:
    def test_returns_series(self, ohlcv_df):
        clf = RegimeClassifier()
        result = clf.classify(ohlcv_df)
        assert isinstance(result, pd.Series)
        assert len(result) == len(ohlcv_df)

    def test_valid_regime_values(self, ohlcv_df):
        clf = RegimeClassifier()
        result = clf.classify(ohlcv_df)
        valid = set(MarketRegime)
        for val in result.unique():
            assert val in valid

    def test_all_bars_classified(self, ohlcv_df):
        clf = RegimeClassifier()
        result = clf.classify(ohlcv_df)
        assert not result.isna().any()

    def test_crash_detection_on_sharp_drop(self):
        n = 200
        close = np.concatenate([
            np.full(100, 100.0),
            np.linspace(100.0, 70.0, 50),  # -30% crash
            np.full(50, 70.0),
        ])
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "open": close + rng.normal(0, 0.1, n),
            "high": close + rng.uniform(0, 1, n),
            "low": close - rng.uniform(0, 1, n),
            "close": close,
            "volume": rng.uniform(1000, 5000, n),
        })
        clf = RegimeClassifier(crash_dd_threshold=5.0)
        result = clf.classify(df)
        # Should detect crash somewhere in the drop zone
        crash_bars = result[result == MarketRegime.CRASH]
        assert len(crash_bars) > 0
