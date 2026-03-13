"""Tests for OHLCVResampler."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.data.resampler import OHLCVResampler


# ── Fixture helpers ──────────────────────────────────────────────────────────


def _make_1m(hours: int = 24) -> pd.DataFrame:
    """Generate *hours* worth of 1-minute OHLCV with predictable values."""
    n = hours * 60
    idx = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
    rng = np.random.default_rng(42)
    price = 100.0 + np.cumsum(rng.normal(0, 0.1, n))
    open_ = price
    close = np.roll(price, -1)
    close[-1] = price[-1]
    high = np.maximum(open_, close) + rng.uniform(0.01, 0.5, n)
    low = np.minimum(open_, close) - rng.uniform(0.01, 0.5, n)
    volume = rng.uniform(1, 100, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


@pytest.fixture
def resampler() -> OHLCVResampler:
    return OHLCVResampler()


@pytest.fixture
def df_1m_24h() -> pd.DataFrame:
    return _make_1m(24)


@pytest.fixture
def df_1m_7d() -> pd.DataFrame:
    return _make_1m(24 * 7)


# ═══════════════════════════════════════════════════════════════════════════════
# Basic resampling
# ═══════════════════════════════════════════════════════════════════════════════


class TestResampleBasic:
    def test_1m_to_1h_bar_count(self, resampler: OHLCVResampler, df_1m_24h: pd.DataFrame):
        result = resampler.resample(df_1m_24h, "1h")
        assert len(result) == 24

    def test_ohlcv_values(self, resampler: OHLCVResampler, df_1m_24h: pd.DataFrame):
        result = resampler.resample(df_1m_24h, "1h")
        # First hour: bars 0..59
        first_hour = df_1m_24h.iloc[:60]
        assert result.iloc[0]["open"] == first_hour["open"].iloc[0]
        assert result.iloc[0]["high"] == first_hour["high"].max()
        assert result.iloc[0]["low"] == first_hour["low"].min()
        assert result.iloc[0]["close"] == first_hour["close"].iloc[-1]
        assert abs(result.iloc[0]["volume"] - first_hour["volume"].sum()) < 1e-6

    def test_1m_to_4h(self, resampler: OHLCVResampler, df_1m_24h: pd.DataFrame):
        result = resampler.resample(df_1m_24h, "4h")
        assert len(result) == 6

    def test_1m_to_15m(self, resampler: OHLCVResampler, df_1m_24h: pd.DataFrame):
        result = resampler.resample(df_1m_24h, "15m")
        assert len(result) == 96

    def test_target_lte_base_raises(self, resampler: OHLCVResampler, df_1m_24h: pd.DataFrame):
        with pytest.raises(ValueError, match="must be > base_tf"):
            resampler.resample(df_1m_24h, "1m")


class TestResample45m:
    def test_45m_alignment_epoch(self, resampler: OHLCVResampler, df_1m_24h: pd.DataFrame):
        """45m bars should align to epoch, not to first bar."""
        result = resampler.resample(df_1m_24h, "45m")
        # 24h = 1440 min ÷ 45 = 32 full bars
        assert len(result) == 32


class TestResampleWeekly:
    def test_1w_monday_based(self, resampler: OHLCVResampler, df_1m_7d: pd.DataFrame):
        result = resampler.resample(df_1m_7d, "1w")
        assert len(result) >= 1
        # The weekly bar should start on a Monday
        assert result.index[0].dayofweek == 0  # Monday


class TestIncompleteBar:
    def test_incomplete_tail_dropped(self, resampler: OHLCVResampler):
        """If the data ends mid-hour, the partial bar should be dropped."""
        n = 90  # 1h30m = 1 complete + 1 incomplete hour
        idx = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
        rng = np.random.default_rng(0)
        df = pd.DataFrame(
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5,
             "volume": rng.uniform(1, 10, n)},
            index=idx,
        )
        result = resampler.resample(df, "1h")
        assert len(result) == 1  # only the complete hour


# ═══════════════════════════════════════════════════════════════════════════════
# resample_all
# ═══════════════════════════════════════════════════════════════════════════════


class TestResampleAll:
    def test_returns_dict(self, resampler: OHLCVResampler, df_1m_24h: pd.DataFrame):
        result = resampler.resample_all(df_1m_24h)
        assert isinstance(result, dict)
        assert "1h" in result
        assert "4h" in result

    def test_explicit_tfs(self, resampler: OHLCVResampler, df_1m_24h: pd.DataFrame):
        result = resampler.resample_all(df_1m_24h, target_tfs=["5m", "15m"])
        assert set(result.keys()) == {"5m", "15m"}


# ═══════════════════════════════════════════════════════════════════════════════
# validate_against_native
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateAgainstNative:
    def test_identical_data_passes(self, resampler: OHLCVResampler, df_1m_24h: pd.DataFrame):
        resampled = resampler.resample(df_1m_24h, "1h")
        report = resampler.validate_against_native(resampled, resampled)
        assert report["pass"] is True
        assert report["bars_compared"] == len(resampled)

    def test_volume_tiny_float_noise_passes(self, resampler: OHLCVResampler, df_1m_24h: pd.DataFrame):
        resampled = resampler.resample(df_1m_24h, "1h")
        fake_native = resampled.copy()
        fake_native["volume"] = fake_native["volume"] + 1e-12

        report = resampler.validate_against_native(resampled, fake_native)

        assert report["pass"] is True
        assert report["columns"]["volume"]["pass"] is True

    def test_divergent_data_fails(self, resampler: OHLCVResampler, df_1m_24h: pd.DataFrame):
        resampled = resampler.resample(df_1m_24h, "1h")
        fake_native = resampled.copy()
        fake_native["open"] = fake_native["open"] * 1.02  # 2% off
        report = resampler.validate_against_native(resampled, fake_native, tolerance_pct=0.01)
        assert report["pass"] is False
        assert report["columns"]["open"]["pass"] is False

    def test_no_overlap_fails(self, resampler: OHLCVResampler):
        idx1 = pd.date_range("2024-01-01", periods=10, freq="1h", tz="UTC")
        idx2 = pd.date_range("2024-06-01", periods=10, freq="1h", tz="UTC")
        cols = {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0}
        df1 = pd.DataFrame(cols, index=idx1)
        df2 = pd.DataFrame(cols, index=idx2)
        report = resampler.validate_against_native(df1, df2)
        assert report["pass"] is False
