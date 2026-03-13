"""Tests for mtf.py — verifies delegation to OHLCVResampler and helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.data.resampler import OHLCVResampler
from suitetrading.indicators.mtf import align_to_base, resample_ohlcv, resolve_timeframe


def _make_1m(days: int = 7) -> pd.DataFrame:
    """Generate 1-minute OHLCV for *days*."""
    n = days * 1440
    idx = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
    rng = np.random.default_rng(42)
    price = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
    return pd.DataFrame(
        {
            "open": price,
            "high": price + rng.uniform(0.1, 1, n),
            "low": price - rng.uniform(0.1, 1, n),
            "close": np.roll(price, -1),
            "volume": rng.uniform(1, 100, n),
        },
        index=idx,
    )


class TestResampleOhlcvDelegation:
    """resample_ohlcv must produce identical output to OHLCVResampler.resample."""

    @pytest.fixture
    def df_1m(self) -> pd.DataFrame:
        return _make_1m(7)

    @pytest.mark.parametrize("target_tf", ["1h", "4h", "1d"])
    def test_parity_with_resampler(self, df_1m: pd.DataFrame, target_tf: str):
        direct = OHLCVResampler().resample(df_1m, target_tf, base_tf="1m")
        via_mtf = resample_ohlcv(df_1m, target_tf, base_tf="1m")
        pd.testing.assert_frame_equal(direct, via_mtf, check_names=False, check_freq=False)

    def test_45m_epoch_alignment(self, df_1m: pd.DataFrame):
        """45m needs origin='epoch' — mtf.py should get this right via delegation."""
        direct = OHLCVResampler().resample(df_1m, "45m", base_tf="1m")
        via_mtf = resample_ohlcv(df_1m, "45m", base_tf="1m")
        pd.testing.assert_frame_equal(direct, via_mtf, check_names=False, check_freq=False)

    def test_1w_monday_alignment(self, df_1m: pd.DataFrame):
        """Weekly resampling must start on Monday (1W-MON)."""
        via_mtf = resample_ohlcv(df_1m, "1w", base_tf="1m")
        # All bars should start on a Monday
        assert all(ts.weekday() == 0 for ts in via_mtf.index), "Weekly bars should start on Monday"

    def test_incomplete_tail_dropped(self, df_1m: pd.DataFrame):
        """Last bar should be dropped if incomplete."""
        df_short = df_1m.iloc[:90]  # 90 minutes → 1 complete 1h bar, 30min incomplete
        result = resample_ohlcv(df_short, "1h", base_tf="1m")
        assert len(result) == 1  # only the complete bar

    def test_pine_style_tf_accepted(self, df_1m: pd.DataFrame):
        """Should accept Pine-style TF strings like '60' for 1h."""
        via_pine = resample_ohlcv(df_1m, "60", base_tf="1m")
        via_canonical = resample_ohlcv(df_1m, "1h", base_tf="1m")
        pd.testing.assert_frame_equal(via_pine, via_canonical, check_names=False, check_freq=False)

    def test_invalid_tf_raises(self, df_1m: pd.DataFrame):
        with pytest.raises(ValueError, match="Unknown timeframe"):
            resample_ohlcv(df_1m, "999z")


class TestResolveTimeframe:
    def test_grafico(self):
        assert resolve_timeframe("60", "grafico") == "60"

    def test_one_higher(self):
        assert resolve_timeframe("60", "1 superior") == "240"

    def test_two_higher(self):
        assert resolve_timeframe("60", "2 superiores") == "D"

    def test_literal(self):
        assert resolve_timeframe("60", "15") == "15"


class TestAlignToBase:
    def test_forward_fill(self):
        base_idx = pd.date_range("2024-01-01", periods=60, freq="1min", tz="UTC")
        htf_idx = pd.date_range("2024-01-01", periods=1, freq="1h", tz="UTC")
        htf = pd.Series([42.0], index=htf_idx, name="signal")
        aligned = align_to_base(htf, base_idx)
        assert len(aligned) == 60
        assert aligned.iloc[-1] == 42.0
