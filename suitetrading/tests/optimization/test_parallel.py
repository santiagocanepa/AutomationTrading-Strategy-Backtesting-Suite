"""Tests for ParallelExecutor."""

import numpy as np
import pandas as pd
import pytest

from suitetrading.backtesting._internal.schemas import (
    BacktestDataset,
    RunConfig,
    StrategySignals,
)
from suitetrading.optimization.parallel import ParallelExecutor
from suitetrading.risk.archetypes import get_archetype


# ── Helpers (must be picklable: module-level functions) ────────────────

def _make_ohlcv(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
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


_SHARED_OHLCV = _make_ohlcv()


def _dataset_loader(cfg: RunConfig) -> BacktestDataset:
    return BacktestDataset(
        exchange="synthetic",
        symbol=cfg.symbol,
        base_timeframe=cfg.timeframe,
        ohlcv=_SHARED_OHLCV,
    )


def _signal_builder(ds: BacktestDataset, cfg: RunConfig) -> StrategySignals:
    close = ds.ohlcv["close"]
    sma = close.rolling(20).mean()
    entry = ((close > sma) & (close.shift(1) <= sma.shift(1))).fillna(False)
    return StrategySignals(entry_long=entry)


def _risk_builder(cfg: RunConfig):
    return get_archetype(cfg.archetype).build_config(**cfg.risk_overrides)


def _failing_dataset_loader(cfg: RunConfig) -> BacktestDataset:
    raise RuntimeError(f"Intentional failure for {cfg.run_id}")


# ── Tests ─────────────────────────────────────────────────────────────

class TestParallelExecutor:
    def test_sequential_returns_results(self, sample_run_configs):
        executor = ParallelExecutor(sequential=True)
        results = executor.run_batch(
            sample_run_configs,
            dataset_loader=_dataset_loader,
            signal_builder=_signal_builder,
            risk_builder=_risk_builder,
        )
        assert len(results) == len(sample_run_configs)
        for r in results:
            assert "equity_curve" in r or "error" in r

    def test_parallel_returns_results(self, sample_run_configs):
        executor = ParallelExecutor(max_workers=2, sequential=False)
        results = executor.run_batch(
            sample_run_configs,
            dataset_loader=_dataset_loader,
            signal_builder=_signal_builder,
            risk_builder=_risk_builder,
        )
        assert len(results) == len(sample_run_configs)
        for r in results:
            assert "equity_curve" in r or "error" in r

    def test_determinism_parallel_vs_sequential(self, sample_run_configs):
        """Parallel and sequential must produce identical metrics."""
        seq = ParallelExecutor(sequential=True)
        par = ParallelExecutor(max_workers=2, sequential=False)

        seq_results = seq.run_batch(
            sample_run_configs,
            dataset_loader=_dataset_loader,
            signal_builder=_signal_builder,
            risk_builder=_risk_builder,
        )
        par_results = par.run_batch(
            sample_run_configs,
            dataset_loader=_dataset_loader,
            signal_builder=_signal_builder,
            risk_builder=_risk_builder,
        )

        for s, p in zip(seq_results, par_results, strict=True):
            assert s["run_id"] == p["run_id"]
            assert s["total_trades"] == p["total_trades"]
            if "final_equity" in s:
                assert abs(s["final_equity"] - p["final_equity"]) < 0.01

    def test_error_in_worker_does_not_abort(self, sample_run_configs):
        """A failing config should produce an error entry, not crash the batch."""
        executor = ParallelExecutor(sequential=True)
        results = executor.run_batch(
            sample_run_configs,
            dataset_loader=_failing_dataset_loader,
            signal_builder=_signal_builder,
            risk_builder=_risk_builder,
        )
        assert len(results) == len(sample_run_configs)
        for r in results:
            assert "error" in r
            assert "Intentional failure" in r["error"]

    def test_error_in_parallel_worker_does_not_abort(self, sample_run_configs):
        executor = ParallelExecutor(max_workers=2, sequential=False)
        results = executor.run_batch(
            sample_run_configs,
            dataset_loader=_failing_dataset_loader,
            signal_builder=_signal_builder,
            risk_builder=_risk_builder,
        )
        assert len(results) == len(sample_run_configs)
        for r in results:
            assert "error" in r

    def test_empty_config_list(self):
        executor = ParallelExecutor(sequential=True)
        results = executor.run_batch(
            [],
            dataset_loader=_dataset_loader,
            signal_builder=_signal_builder,
            risk_builder=_risk_builder,
        )
        assert results == []

    def test_max_workers_respected(self):
        executor = ParallelExecutor(max_workers=3)
        assert executor.max_workers == 3

    def test_map_backtests_sequential(self, sample_run_configs):
        executor = ParallelExecutor(sequential=True)

        def _run(cfg: RunConfig) -> dict:
            return {"run_id": cfg.run_id, "ok": True}

        results = executor.map_backtests(_run, sample_run_configs)
        assert len(results) == len(sample_run_configs)
        assert all(r["ok"] for r in results)
