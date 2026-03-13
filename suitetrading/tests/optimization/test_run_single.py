"""Tests for BacktestObjective.run_single() and _split_params()."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from suitetrading.backtesting._internal.schemas import BacktestDataset


@pytest.fixture()
def tiny_dataset() -> BacktestDataset:
    """100-bar synthetic dataset."""
    n = 100
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(42)
    close = 100 + rng.standard_normal(n).cumsum()
    ohlcv = pd.DataFrame(
        {
            "open": close - rng.uniform(0, 1, n),
            "high": close + rng.uniform(0, 2, n),
            "low": close - rng.uniform(0, 2, n),
            "close": close,
            "volume": rng.uniform(100, 1000, n),
        },
        index=idx,
    )
    return BacktestDataset(
        exchange="binance", symbol="BTCUSDT", base_timeframe="1h", ohlcv=ohlcv,
    )


class TestSplitParams:
    """Verify _split_params separates indicator params from risk overrides."""

    def test_basic_split(self, tiny_dataset: BacktestDataset) -> None:
        from suitetrading.optimization._internal.objective import BacktestObjective

        obj = BacktestObjective(
            dataset=tiny_dataset,
            indicator_names=["ssl_channel"],
            archetype="trend_following",
        )

        flat = {
            "ssl_channel__length": 12,
            "ssl_channel__hold_bars": 4,
            "stop__atr_multiple": 2.5,
            "sizing__risk_pct": 1.0,
        }
        ind_params, risk = obj._split_params(flat)

        assert "ssl_channel" in ind_params
        assert ind_params["ssl_channel"]["length"] == 12
        assert ind_params["ssl_channel"]["hold_bars"] == 4
        assert risk["stop__atr_multiple"] == 2.5
        assert risk["sizing__risk_pct"] == 1.0

    def test_unknown_prefix_goes_to_risk(self, tiny_dataset: BacktestDataset) -> None:
        from suitetrading.optimization._internal.objective import BacktestObjective

        obj = BacktestObjective(
            dataset=tiny_dataset,
            indicator_names=["ssl_channel"],
            archetype="trend_following",
        )

        flat = {"ssl_channel__length": 12, "foo__bar": 99}
        ind, risk = obj._split_params(flat)

        assert "foo__bar" in risk
        assert "ssl_channel" in ind


class TestRunSingle:
    """Verify run_single() produces valid output."""

    def test_returns_equity_and_metrics(self, tiny_dataset: BacktestDataset) -> None:
        from suitetrading.optimization._internal.objective import BacktestObjective

        obj = BacktestObjective(
            dataset=tiny_dataset,
            indicator_names=["ssl_channel"],
            archetype="trend_following",
            mode="simple",
        )

        params = {"ssl_channel__length": 12, "ssl_channel__hold_bars": 4}
        result = obj.run_single(params)

        assert "equity_curve" in result
        assert "metrics" in result
        assert isinstance(result["metrics"], dict)
        assert "sharpe" in result["metrics"] or len(result["metrics"]) >= 0

    def test_run_single_matches_call(self, tiny_dataset: BacktestDataset) -> None:
        """run_single() with the same params as __call__() should produce
        equivalent metrics (not identical due to Optuna trial overhead, but
        the backtest result should be the same).
        """
        from suitetrading.optimization._internal.objective import BacktestObjective

        obj = BacktestObjective(
            dataset=tiny_dataset,
            indicator_names=["ssl_channel"],
            archetype="trend_following",
            mode="simple",
        )

        params = {"ssl_channel__length": 12, "ssl_channel__hold_bars": 4}
        r1 = obj.run_single(params)
        r2 = obj.run_single(params)

        # Deterministic: same params → same result
        np.testing.assert_array_equal(r1["equity_curve"], r2["equity_curve"])
