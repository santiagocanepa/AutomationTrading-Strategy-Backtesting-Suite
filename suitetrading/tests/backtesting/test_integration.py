"""Integration tests — end-to-end backtesting pipeline.

Tests the complete flow: dataset → signals → engine → metrics → reporting.
Uses synthetic data to be independent of external data sources.
"""

import json
import shutil

import numpy as np
import pandas as pd
import pytest

from suitetrading.backtesting._internal.checkpoints import CheckpointManager
from suitetrading.backtesting._internal.datasets import build_dataset_from_df, compute_signals
from suitetrading.backtesting._internal.runners import run_fsm_backtest, run_simple_backtest
from suitetrading.backtesting._internal.schemas import (
    BacktestDataset,
    GridRequest,
    StrategySignals,
)
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.backtesting.grid import ParameterGridBuilder
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.backtesting.reporting import ReportingEngine
from suitetrading.indicators.base import IndicatorConfig, IndicatorState
from suitetrading.risk.archetypes.mean_reversion import MeanReversion
from suitetrading.risk.archetypes.trend_following import TrendFollowing


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def trending_ohlcv():
    """Synthetic trending market (up then down)."""
    n = 1000
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(42)
    t = np.arange(n)
    trend = 100 + 0.05 * t - 0.00005 * t ** 2  # up-then-down parabola
    noise = rng.normal(0, 0.5, n)
    close = np.maximum(trend + noise, 10.0)
    return pd.DataFrame({
        "open": close + rng.normal(0, 0.2, n),
        "high": close + np.abs(rng.normal(0.3, 0.2, n)),
        "low": close - np.abs(rng.normal(0.3, 0.2, n)),
        "close": close,
        "volume": rng.integers(500, 5000, n).astype(float),
    }, index=idx)


@pytest.fixture
def dataset(trending_ohlcv):
    return build_dataset_from_df(trending_ohlcv, symbol="BTCUSDT", base_timeframe="1h")


@pytest.fixture
def entry_signals(trending_ohlcv):
    """Simple momentum: entry when close crosses above 20-bar SMA."""
    close = trending_ohlcv["close"]
    sma = close.rolling(20).mean()
    prev_close = close.shift(1)
    prev_sma = sma.shift(1)
    long_entry = (close > sma) & (prev_close <= prev_sma)
    long_entry = long_entry.fillna(False)
    return StrategySignals(entry_long=long_entry)


# ── End-to-end tests ─────────────────────────────────────────────────

class TestEndToEndSimple:
    """Complete pipeline with simple runner."""

    def test_trend_following_pipeline(self, dataset, entry_signals):
        engine = BacktestEngine()
        metrics_engine = MetricsEngine()

        rc = TrendFollowing().build_config()
        result = engine.run(
            dataset=dataset, signals=entry_signals,
            risk_config=rc, mode="simple",
        )

        metrics = metrics_engine.compute(
            equity_curve=result["equity_curve"],
            trades=result["trades"],
            initial_capital=rc.initial_capital,
        )

        assert metrics["total_trades"] >= 0
        assert isinstance(metrics["sharpe"], float)
        assert isinstance(metrics["max_drawdown_pct"], float)
        assert metrics["max_drawdown_pct"] >= 0

    def test_mean_reversion_pipeline(self, dataset, entry_signals):
        engine = BacktestEngine()
        rc = MeanReversion().build_config()
        result = engine.run(
            dataset=dataset, signals=entry_signals,
            risk_config=rc, mode="simple",
        )
        assert len(result["equity_curve"]) == len(dataset.ohlcv)


class TestEndToEndFSM:
    """Complete pipeline with FSM runner."""

    def test_fsm_trend_following(self, dataset, entry_signals):
        engine = BacktestEngine()
        rc = TrendFollowing().build_config()
        result = engine.run(
            dataset=dataset, signals=entry_signals,
            risk_config=rc, mode="fsm",
        )
        assert result["mode"] == "fsm"
        assert len(result["equity_curve"]) == len(dataset.ohlcv)

    def test_fsm_deterministic(self, dataset, entry_signals):
        engine = BacktestEngine()
        rc = TrendFollowing().build_config()
        r1 = engine.run(dataset=dataset, signals=entry_signals, risk_config=rc, mode="fsm")
        r2 = engine.run(dataset=dataset, signals=entry_signals, risk_config=rc, mode="fsm")
        assert r1["final_equity"] == r2["final_equity"]
        assert r1["total_trades"] == r2["total_trades"]


class TestGridPipeline:
    """Grid → engine → metrics → reporting."""

    def test_small_grid_end_to_end(self, dataset, entry_signals, tmp_path):
        grid = ParameterGridBuilder()
        engine = BacktestEngine()
        metrics_engine = MetricsEngine()
        reporting = ReportingEngine()

        req = GridRequest(
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            indicator_space={},
            risk_space={},
            archetypes=["trend_following", "mean_reversion"],
        )
        configs = grid.build(req)
        assert len(configs) == 2

        all_results = []
        for cfg in configs:
            rc = TrendFollowing().build_config() if cfg.archetype == "trend_following" else MeanReversion().build_config()
            res = engine.run(dataset=dataset, signals=entry_signals, risk_config=rc, mode="simple")
            m = metrics_engine.compute(
                equity_curve=res["equity_curve"],
                trades=res["trades"],
                initial_capital=rc.initial_capital,
            )
            m["run_id"] = cfg.run_id
            m["symbol"] = cfg.symbol
            m["timeframe"] = cfg.timeframe
            m["archetype"] = cfg.archetype
            m["mode"] = res["mode"]
            all_results.append(m)

        results_df = pd.DataFrame(all_results)
        assert len(results_df) == 2

        artefacts = reporting.build_dashboard(results=results_df, output_dir=tmp_path / "report")
        assert "summary_csv" in artefacts


class TestCheckpointResume:
    """Checkpoint, interrupt, and resume."""

    def test_checkpoint_and_resume(self, dataset, entry_signals, tmp_path):
        cm = CheckpointManager(tmp_path / "checkpoints")

        # Simulate chunk 0 done
        cm.mark_running(0)
        cm.save_chunk_results(0, [{"run_id": "r0", "net_profit": 100.0}])
        cm.mark_done(0, str(tmp_path / "checkpoints" / "chunk_000000.parquet"))

        # Simulate chunk 1 error
        cm.mark_running(1)
        cm.mark_error(1, "OOM")

        # Resume: chunk 0 skipped, chunk 1 reprocessed
        assert cm.is_chunk_done(0)
        assert not cm.is_chunk_done(1)
        assert cm.completed_count() == 1

        # New manager from same dir should load state
        cm2 = CheckpointManager(tmp_path / "checkpoints")
        assert cm2.is_chunk_done(0)
        assert not cm2.is_chunk_done(1)

    def test_load_all_results(self, tmp_path):
        cm = CheckpointManager(tmp_path / "cp")
        cm.save_chunk_results(0, [{"run_id": "r0", "net_profit": 100}])
        cm.save_chunk_results(1, [{"run_id": "r1", "net_profit": 200}])
        df = cm.load_all_results()
        assert len(df) == 2


class TestRunnerDirectCalls:
    """Direct runner invocations (bypass engine)."""

    def test_simple_runner_no_trades(self, dataset):
        no_entry = pd.Series(np.zeros(len(dataset.ohlcv), dtype=bool), index=dataset.ohlcv.index)
        signals = StrategySignals(entry_long=no_entry)
        rc = TrendFollowing().build_config()
        result = run_simple_backtest(dataset=dataset, signals=signals, risk_config=rc)
        assert result.final_equity == pytest.approx(rc.initial_capital, rel=0.001)
        assert len(result.trades) == 0

    def test_fsm_runner_no_trades(self, dataset):
        no_entry = pd.Series(np.zeros(len(dataset.ohlcv), dtype=bool), index=dataset.ohlcv.index)
        signals = StrategySignals(entry_long=no_entry)
        rc = TrendFollowing().build_config()
        result = run_fsm_backtest(dataset=dataset, signals=signals, risk_config=rc)
        assert result.final_equity == pytest.approx(rc.initial_capital, rel=0.001)
