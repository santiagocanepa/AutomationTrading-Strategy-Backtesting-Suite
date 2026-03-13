"""End-to-end integration tests for the data pipeline.

These tests exercise the full chain: generate → validate → store → read → resample.
Marked @slow and @integration so they can be skipped in fast CI runs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.data.validator import DataValidator
from suitetrading.data.warmup import WarmupCalculator


def _generate_1m(days: int = 30) -> pd.DataFrame:
    """Generate realistic 1-minute OHLCV data."""
    n = days * 1440
    idx = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
    rng = np.random.default_rng(12345)
    price = 42_000.0 + np.cumsum(rng.normal(0, 5, n))
    open_ = price
    close = np.roll(price, -1)
    close[-1] = price[-1]
    high = np.maximum(open_, close) + rng.uniform(1, 50, n)
    low = np.minimum(open_, close) - rng.uniform(1, 50, n)
    volume = rng.uniform(0.1, 100, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


@pytest.mark.slow
@pytest.mark.integration
class TestFullPipeline:
    """Test the complete pipeline: generate → validate → store → read → resample → warmup."""

    def test_full_pipeline_one_month(self, tmp_path):
        # 1) Generate
        df = _generate_1m(30)
        assert len(df) == 30 * 1440

        # 2) Validate
        validator = DataValidator()
        issues = validator.validate(df, "1m")
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0, f"Validation errors: {errors}"

        # 3) Store
        store = ParquetStore(base_dir=tmp_path / "data")
        store.write(df, "binance", "BTCUSDT", "1m", source="test")

        # 4) Read back
        df_read = store.read("binance", "BTCUSDT", "1m")
        assert len(df_read) == len(df)
        pd.testing.assert_frame_equal(df, df_read, check_names=False, check_freq=False)

        # 5) Resample
        resampler = OHLCVResampler()
        all_tfs = resampler.resample_all(df_read, target_tfs=["5m", "15m", "1h", "4h", "1d"])
        assert set(all_tfs.keys()) == {"5m", "15m", "1h", "4h", "1d"}
        assert len(all_tfs["1h"]) == 30 * 24  # 720 hourly bars
        assert len(all_tfs["1d"]) == 30

        # 6) Warmup
        calc = WarmupCalculator()
        td = calc.calculate(
            [{"key": "ema_200", "timeframe": "1h"}, {"key": "rsi_14", "timeframe": "15m"}],
        )
        assert td.total_seconds() > 0


@pytest.mark.slow
@pytest.mark.integration
class TestCrossValidation:
    """Verify resampled 1m→1h against independently-aggregated 1h data.

    This is NOT self-comparison: we compute 1h from raw 1m using plain pandas
    (no OHLCVResampler), then compare against OHLCVResampler output.
    """

    def test_resample_vs_manual_1h(self):
        """Aggregate 1m→1h manually vs OHLCVResampler → must match."""
        df = _generate_1m(7)
        resampler = OHLCVResampler()

        # Resampler result
        df_1h = resampler.resample(df, "1h")

        # Manual aggregation (independent implementation)
        manual_1h = df.resample("1h").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna(subset=["open"])
        # Drop incomplete trailing bar to match resampler behavior
        if len(manual_1h) > len(df_1h):
            manual_1h = manual_1h.iloc[: len(df_1h)]

        report = resampler.validate_against_native(df_1h, manual_1h)
        assert report["pass"] is True
        assert report["bars_compared"] > 0
        assert report["columns"]["volume"]["pass"] is True

    def test_resample_vs_manual_1d(self):
        """Aggregate 1m→1d manually vs OHLCVResampler → must match."""
        df = _generate_1m(30)
        resampler = OHLCVResampler()

        df_1d = resampler.resample(df, "1d")

        manual_1d = df.resample("1D").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna(subset=["open"])
        if len(manual_1d) > len(df_1d):
            manual_1d = manual_1d.iloc[: len(df_1d)]

        report = resampler.validate_against_native(df_1d, manual_1d)
        assert report["pass"] is True
        assert report["bars_compared"] >= 29

    def test_resample_idempotent(self):
        """Resampling the same source twice → identical."""
        df = _generate_1m(7)
        resampler = OHLCVResampler()
        a = resampler.resample(df, "1h")
        b = resampler.resample(df, "1h")
        pd.testing.assert_frame_equal(a, b)
