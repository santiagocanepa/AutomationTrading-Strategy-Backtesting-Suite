"""Shared fixtures for optimization tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.backtesting._internal.schemas import (
    BacktestDataset,
    RunConfig,
    StrategySignals,
)
from suitetrading.risk.archetypes import get_archetype


# ── Synthetic OHLCV data ─────────────────────────────────────────────

@pytest.fixture
def synthetic_ohlcv():
    """500-bar trending OHLCV with deterministic seed."""
    n = 500
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(42)
    close = 100.0 + np.cumsum(rng.normal(0.05, 1.0, n))
    close = np.maximum(close, 10.0)
    return pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.2, n),
            "high": close + np.abs(rng.normal(0.3, 0.2, n)),
            "low": close - np.abs(rng.normal(0.3, 0.2, n)),
            "close": close,
            "volume": rng.integers(500, 5000, n).astype(float),
        },
        index=idx,
    )


@pytest.fixture
def synthetic_dataset(synthetic_ohlcv):
    """BacktestDataset wrapping synthetic_ohlcv."""
    return BacktestDataset(
        exchange="synthetic",
        symbol="BTCUSDT",
        base_timeframe="1h",
        ohlcv=synthetic_ohlcv,
    )


@pytest.fixture
def synthetic_signals(synthetic_ohlcv):
    """Simple momentum: entry when close > 20-bar SMA."""
    close = synthetic_ohlcv["close"]
    sma = close.rolling(20).mean()
    entry = (close > sma) & (close.shift(1) <= sma.shift(1))
    entry = entry.fillna(False)
    return StrategySignals(entry_long=entry)


@pytest.fixture
def trend_risk_config():
    """Trend-following archetype RiskConfig."""
    return get_archetype("trend_following").build_config()


@pytest.fixture
def sample_run_configs():
    """Small batch of deterministic RunConfigs."""
    configs = []
    for mult in [1.5, 2.0, 2.5, 3.0]:
        configs.append(
            RunConfig(
                symbol="BTCUSDT",
                timeframe="1h",
                archetype="trend_following",
                indicator_params={"rsi": {"period": 14, "threshold": 30.0, "mode": "oversold"}},
                risk_overrides={"stop": {"atr_multiple": mult}},
            )
        )
    return configs


# ── Synthetic equity curves for anti-overfitting tests ────────────────

@pytest.fixture
def genuine_equity_curves():
    """Equity curves with consistent positive drift (genuinely profitable)."""
    rng = np.random.default_rng(123)
    curves = {}
    for i in range(5):
        n = 1000
        drift = 0.001 + rng.uniform(0, 0.0005)
        noise = rng.normal(0, 0.01, n)
        returns = drift + noise
        equity = 10_000.0 * np.cumprod(1 + returns)
        curves[f"genuine_{i}"] = equity
    return curves


@pytest.fixture
def overfit_equity_curves():
    """Equity curves that look great in first half, collapse in second half."""
    rng = np.random.default_rng(456)
    curves = {}
    for i in range(5):
        n = 1000
        half = n // 2
        returns_up = rng.normal(0.002, 0.01, half)
        returns_down = rng.normal(-0.002, 0.01, n - half)
        returns = np.concatenate([returns_up, returns_down])
        equity = 10_000.0 * np.cumprod(1 + returns)
        curves[f"overfit_{i}"] = equity
    return curves
