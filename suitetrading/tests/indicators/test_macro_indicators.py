"""Tests for macro indicators (VRP, YieldCurve, CreditSpread, Hurst)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.indicators.macro.credit_spread import CreditSpreadIndicator
from suitetrading.indicators.macro.hurst import HurstIndicator
from suitetrading.indicators.macro.vrp import VRPIndicator
from suitetrading.indicators.macro.yield_curve import YieldCurveIndicator
from suitetrading.indicators.registry import get_indicator


# ── Fixtures ──────────────────────────────────────────────────────────

def _ohlcv(
    n: int = 500, seed: int = 42, vix: float | None = None,
    yield_spread: float | None = None, credit_spread: float | None = None,
    hy_spread: float | None = None,
) -> pd.DataFrame:
    """Synthetic OHLCV with optional macro columns."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n, freq="4h", tz="UTC")
    close = 100.0 + np.cumsum(rng.normal(0.01, 0.5, n))
    close = np.maximum(close, 10.0)
    df = pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.2, n),
            "high": close + np.abs(rng.normal(0.3, 0.2, n)),
            "low": close - np.abs(rng.normal(0.3, 0.2, n)),
            "close": close,
            "volume": rng.integers(500, 5000, n).astype(float),
        },
        index=idx,
    )
    if vix is not None:
        df["vix"] = vix + rng.normal(0, 1, n)
    if yield_spread is not None:
        df["yield_spread"] = yield_spread + rng.normal(0, 0.1, n)
    if credit_spread is not None:
        df["credit_spread"] = credit_spread + rng.normal(0, 0.005, n)
    if hy_spread is not None:
        df["hy_spread"] = hy_spread + rng.normal(0, 0.1, n)
    return df


# ── VRP Tests ─────────────────────────────────────────────────────────

class TestVRP:
    def test_risk_on_when_vix_high_vol_low(self):
        """High VIX (30) + low realized vol → positive VRP → risk_on True."""
        df = _ohlcv(300, vix=30.0)
        # Low vol data: close barely moves
        df["close"] = 100.0 + np.arange(300) * 0.001
        ind = VRPIndicator()
        sig = ind.compute(df, realized_window=20, mode="risk_on")
        assert isinstance(sig, pd.Series)
        assert sig.dtype == bool
        # With VIX=30 and near-zero realized vol, VRP should be strongly positive
        assert sig.iloc[50:].sum() > 200

    def test_risk_off_when_vix_low_vol_high(self):
        """Low VIX (10) + high realized vol → negative VRP → risk_off True."""
        rng = np.random.default_rng(42)
        df = _ohlcv(300, vix=10.0)
        # High vol data: close jumps wildly
        df["close"] = 100.0 + np.cumsum(rng.normal(0, 5.0, 300))
        df["close"] = np.maximum(df["close"], 10.0)
        ind = VRPIndicator()
        sig = ind.compute(df, realized_window=20, mode="risk_off")
        assert sig.iloc[50:].sum() > 100

    def test_missing_vix_column_returns_all_false(self):
        df = _ohlcv(100)  # No vix column
        ind = VRPIndicator()
        sig = ind.compute(df)
        assert not sig.any()
        assert len(sig) == 100

    def test_hold_bars(self):
        df = _ohlcv(200, vix=30.0)
        df["close"] = 100.0 + np.arange(200) * 0.001
        ind = VRPIndicator()
        sig_1 = ind.compute(df, hold_bars=1, realized_window=20, mode="risk_on")
        sig_5 = ind.compute(df, hold_bars=5, realized_window=20, mode="risk_on")
        # More hold_bars → more True values
        assert sig_5.sum() >= sig_1.sum()

    def test_params_schema(self):
        ind = VRPIndicator()
        schema = ind.params_schema()
        assert "realized_window" in schema
        assert "mode" in schema
        assert "hold_bars" in schema
        assert schema["realized_window"]["type"] == "int"
        assert schema["mode"]["type"] == "str"


# ── YieldCurve Tests ──────────────────────────────────────────────────

class TestYieldCurve:
    def test_normal_positive_spread(self):
        """Positive spread → mode=normal → True."""
        df = _ohlcv(200, yield_spread=1.5)  # Healthy 1.5% spread
        ind = YieldCurveIndicator()
        sig = ind.compute(df, mode="normal", threshold=0.0)
        assert sig.sum() > 150  # Most bars should be True

    def test_inverted_negative_spread(self):
        """Negative spread → mode=inverted → True."""
        df = _ohlcv(200, yield_spread=-0.5)  # Inverted
        ind = YieldCurveIndicator()
        sig = ind.compute(df, mode="inverted", threshold=0.0)
        assert sig.sum() > 150

    def test_steepening_rising_spread(self):
        """Spread rising above SMA → steepening True."""
        df = _ohlcv(200, yield_spread=0.0)
        # Create a rising spread
        df["yield_spread"] = np.linspace(-1.0, 2.0, 200)
        ind = YieldCurveIndicator()
        sig = ind.compute(df, mode="steepening", lookback=20)
        # After lookback period, rising spread should trigger
        assert sig.iloc[30:].sum() > 100

    def test_missing_column_returns_all_false(self):
        df = _ohlcv(100)  # No yield_spread column
        ind = YieldCurveIndicator()
        sig = ind.compute(df)
        assert not sig.any()
        assert len(sig) == 100

    def test_hold_bars(self):
        df = _ohlcv(200, yield_spread=1.5)
        ind = YieldCurveIndicator()
        sig_1 = ind.compute(df, mode="normal", hold_bars=1)
        sig_10 = ind.compute(df, mode="normal", hold_bars=10)
        assert sig_10.sum() >= sig_1.sum()

    def test_params_schema(self):
        ind = YieldCurveIndicator()
        schema = ind.params_schema()
        assert "threshold" in schema
        assert "mode" in schema
        assert "lookback" in schema
        assert "hold_bars" in schema
        assert schema["threshold"]["type"] == "float"


# ── Registry Tests ────────────────────────────────────────────────────

class TestMacroRegistry:
    def test_vrp_registered(self):
        ind = get_indicator("vrp")
        assert isinstance(ind, VRPIndicator)

    def test_yield_curve_registered(self):
        ind = get_indicator("yield_curve")
        assert isinstance(ind, YieldCurveIndicator)

    def test_credit_spread_registered(self):
        ind = get_indicator("credit_spread")
        assert isinstance(ind, CreditSpreadIndicator)

    def test_hurst_registered(self):
        ind = get_indicator("hurst")
        assert isinstance(ind, HurstIndicator)


# ── CreditSpread Tests ───────────────────────────────────────────────

class TestCreditSpread:
    def test_risk_on_ratio_above_sma(self):
        """Steadily rising ratio → above SMA → risk_on True."""
        df = _ohlcv(300, credit_spread=0.80)
        df["credit_spread"] = np.linspace(0.70, 0.90, 300)
        ind = CreditSpreadIndicator()
        sig = ind.compute(df, mode="risk_on", lookback=20)
        assert isinstance(sig, pd.Series)
        assert sig.dtype == bool
        assert sig.iloc[30:].sum() > 200

    def test_risk_off_ratio_below_sma(self):
        """Steadily falling ratio → below SMA → risk_off True."""
        df = _ohlcv(300, credit_spread=0.80)
        df["credit_spread"] = np.linspace(0.90, 0.70, 300)
        ind = CreditSpreadIndicator()
        sig = ind.compute(df, mode="risk_off", lookback=20)
        assert sig.iloc[30:].sum() > 200

    def test_momentum_rising(self):
        """Spread crossing above SMA triggers momentum."""
        df = _ohlcv(200, credit_spread=0.80)
        # Create crossover: low then high
        df["credit_spread"] = np.concatenate([
            np.full(100, 0.75),
            np.full(100, 0.85),
        ])
        ind = CreditSpreadIndicator()
        sig = ind.compute(df, mode="momentum", lookback=20, hold_bars=5)
        # Should trigger around bar 100 when crossing SMA
        assert sig.sum() > 0

    def test_hy_spread_fallback(self):
        """Uses hy_spread column when credit_spread absent (inverted logic)."""
        df = _ohlcv(200, hy_spread=3.5)
        # Falling spread = improving conditions → risk_on (inverted: value < sma)
        df["hy_spread"] = np.linspace(6.0, 2.0, 200)
        ind = CreditSpreadIndicator()
        sig = ind.compute(df, mode="risk_on", lookback=20)
        # Falling spread → value below SMA → risk_on True
        assert sig.iloc[30:].sum() > 100

    def test_missing_column_returns_false(self):
        df = _ohlcv(100)
        ind = CreditSpreadIndicator()
        sig = ind.compute(df)
        assert not sig.any()

    def test_params_schema(self):
        ind = CreditSpreadIndicator()
        schema = ind.params_schema()
        assert "lookback" in schema
        assert "mode" in schema
        assert "hold_bars" in schema
        assert schema["lookback"]["type"] == "int"


# ── Hurst Tests ───────────────────────────────────────────────────────

class TestHurst:
    def test_trending_on_strong_trend(self):
        """Strong uptrend → H > 0.55 → trending mode True."""
        df = _ohlcv(500, seed=42)
        # Replace with strong deterministic trend
        df["close"] = 100.0 + np.arange(500) * 0.5
        ind = HurstIndicator()
        sig = ind.compute(df, window=100, mode="trending", threshold_high=0.55)
        # Strong trend should produce Hurst > 0.55 in most windows
        assert sig.iloc[150:].sum() > 200

    def test_mean_reverting_on_oscillating_data(self):
        """Zigzag/oscillating → H < 0.45 → mean_reverting True."""
        df = _ohlcv(500, seed=42)
        # Oscillating: alternating +/- with small noise
        rng = np.random.default_rng(99)
        osc = np.cumsum(np.where(np.arange(500) % 2 == 0, 0.5, -0.5) + rng.normal(0, 0.05, 500))
        df["close"] = 100 + osc
        df["close"] = np.maximum(df["close"], 10.0)
        ind = HurstIndicator()
        sig = ind.compute(df, window=100, mode="mean_reverting", threshold_low=0.45)
        assert sig.iloc[150:].sum() > 100

    def test_any_edge_detects_both(self):
        """any_edge mode detects both trending and mean-reverting."""
        df = _ohlcv(500, seed=42)
        df["close"] = 100.0 + np.arange(500) * 0.5  # Strong trend
        ind = HurstIndicator()
        sig = ind.compute(df, window=100, mode="any_edge")
        assert sig.iloc[150:].sum() > 200

    def test_random_walk_few_signals(self):
        """Random walk (H ≈ 0.5) → few signals in trending mode."""
        rng = np.random.default_rng(42)
        df = _ohlcv(500, seed=42)
        df["close"] = 100.0 + np.cumsum(rng.normal(0, 1, 500))
        df["close"] = np.maximum(df["close"], 10.0)
        ind = HurstIndicator()
        sig_trend = ind.compute(df, window=100, mode="trending", threshold_high=0.60)
        sig_mr = ind.compute(df, window=100, mode="mean_reverting", threshold_low=0.40)
        # Random walk should produce fewer signals than structured data
        total_signals = sig_trend.iloc[150:].sum() + sig_mr.iloc[150:].sum()
        assert total_signals < 300  # Less than 85% of bars

    def test_hold_bars(self):
        df = _ohlcv(300, seed=42)
        df["close"] = 100.0 + np.arange(300) * 0.3
        ind = HurstIndicator()
        sig_1 = ind.compute(df, window=100, mode="trending", hold_bars=1)
        sig_10 = ind.compute(df, window=100, mode="trending", hold_bars=10)
        assert sig_10.sum() >= sig_1.sum()

    def test_params_schema(self):
        ind = HurstIndicator()
        schema = ind.params_schema()
        assert "window" in schema
        assert "mode" in schema
        assert "threshold_high" in schema
        assert "threshold_low" in schema
        assert "hold_bars" in schema
        assert schema["window"]["type"] == "int"
