"""Tests for engine.py — BacktestEngine orchestrator."""

import numpy as np
import pandas as pd
import pytest

from suitetrading.backtesting._internal.schemas import BacktestDataset, RunConfig, StrategySignals
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.risk.contracts import RiskConfig
from suitetrading.risk.archetypes.trend_following import TrendFollowing
from suitetrading.risk.archetypes.mean_reversion import MeanReversion


@pytest.fixture
def sample_ohlcv():
    """Synthetic trending OHLCV data."""
    n = 500
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    base = 100.0
    close = base + np.cumsum(np.random.default_rng(42).normal(0.05, 1.0, n))
    close = np.maximum(close, 10.0)
    high = close + np.abs(np.random.default_rng(43).normal(0.5, 0.3, n))
    low = close - np.abs(np.random.default_rng(44).normal(0.5, 0.3, n))
    open_ = close + np.random.default_rng(45).normal(0, 0.3, n)
    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": np.random.default_rng(46).integers(100, 10000, n).astype(float),
    }, index=idx)


@pytest.fixture
def dataset(sample_ohlcv):
    return BacktestDataset(
        exchange="synthetic", symbol="BTCUSDT",
        base_timeframe="1h", ohlcv=sample_ohlcv,
    )


def _make_signals(ohlcv: pd.DataFrame, entry_prob: float = 0.03) -> StrategySignals:
    """Create sparse random entry signals."""
    rng = np.random.default_rng(99)
    entries = rng.random(len(ohlcv)) < entry_prob
    entries[:20] = False  # warmup
    return StrategySignals(entry_long=pd.Series(entries, index=ohlcv.index))


class TestBacktestEngine:
    @pytest.fixture
    def engine(self):
        return BacktestEngine()

    def test_run_simple_mode(self, engine, dataset):
        signals = _make_signals(dataset.ohlcv)
        rc = TrendFollowing().build_config()
        result = engine.run(dataset=dataset, signals=signals, risk_config=rc, mode="simple")
        assert "equity_curve" in result
        assert result["total_trades"] >= 0
        assert len(result["equity_curve"]) == len(dataset.ohlcv)

    def test_run_fsm_mode(self, engine, dataset):
        signals = _make_signals(dataset.ohlcv)
        rc = TrendFollowing().build_config()
        result = engine.run(dataset=dataset, signals=signals, risk_config=rc, mode="fsm")
        assert "equity_curve" in result
        assert result["mode"] == "fsm"

    def test_auto_mode_selects_fsm_for_trend(self, engine, dataset):
        signals = _make_signals(dataset.ohlcv)
        rc = TrendFollowing().build_config()
        result = engine.run(dataset=dataset, signals=signals, risk_config=rc, mode="auto")
        assert result["mode"] == "fsm"

    def test_auto_mode_selects_fsm_for_pyramidal(self, engine, dataset):
        signals = _make_signals(dataset.ohlcv)
        rc = RiskConfig(archetype="pyramidal")
        result = engine.run(dataset=dataset, signals=signals, risk_config=rc, mode="auto")
        assert result["mode"] == "fsm"

    def test_no_entries_no_trades(self, engine, dataset):
        no_entry = pd.Series(np.zeros(len(dataset.ohlcv), dtype=bool), index=dataset.ohlcv.index)
        signals = StrategySignals(entry_long=no_entry)
        rc = TrendFollowing().build_config()
        result = engine.run(dataset=dataset, signals=signals, risk_config=rc, mode="simple")
        assert result["total_trades"] == 0
        assert result["final_equity"] == pytest.approx(rc.initial_capital, rel=0.01)

    def test_result_has_required_keys(self, engine, dataset):
        signals = _make_signals(dataset.ohlcv)
        rc = MeanReversion().build_config()
        result = engine.run(dataset=dataset, signals=signals, risk_config=rc, mode="simple")
        required = {"symbol", "timeframe", "archetype", "mode", "equity_curve",
                     "trades", "final_equity", "total_return_pct", "total_trades"}
        assert required.issubset(result.keys())

    def test_invalid_mode_raises(self, engine, dataset):
        signals = _make_signals(dataset.ohlcv)
        rc = TrendFollowing().build_config()
        with pytest.raises(ValueError, match="Invalid mode"):
            engine.run(dataset=dataset, signals=signals, risk_config=rc, mode="invalid")

    def test_batch_run(self, engine, dataset):
        configs = [
            RunConfig(symbol="BTCUSDT", timeframe="1h", archetype="trend_following",
                      indicator_params={}, risk_overrides={}),
            RunConfig(symbol="BTCUSDT", timeframe="1h", archetype="mean_reversion",
                      indicator_params={}, risk_overrides={}),
        ]
        signals = _make_signals(dataset.ohlcv)

        results = engine.run_batch(
            configs=configs,
            dataset_loader=lambda cfg: dataset,
            signal_builder=lambda ds, cfg: signals,
            risk_builder=lambda cfg: TrendFollowing().build_config(),
            mode="simple",
        )
        assert len(results) == 2
        assert all("run_id" in r for r in results)


class TestDeterminism:
    def test_same_inputs_same_outputs(self, dataset):
        engine = BacktestEngine()
        signals = _make_signals(dataset.ohlcv)
        rc = TrendFollowing().build_config()

        r1 = engine.run(dataset=dataset, signals=signals, risk_config=rc, mode="simple")
        r2 = engine.run(dataset=dataset, signals=signals, risk_config=rc, mode="simple")
        assert np.array_equal(r1["equity_curve"], r2["equity_curve"])
        assert r1["final_equity"] == r2["final_equity"]
        assert r1["total_trades"] == r2["total_trades"]
