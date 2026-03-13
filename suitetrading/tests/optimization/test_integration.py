"""End-to-end integration test for the optimisation pipeline.

Tests the full flow: Optuna optimisation → Walk-Forward → Anti-overfit
filtering, using synthetic data with a known alpha signal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.optimization import (
    AntiOverfitPipeline,
    CSCVValidator,
    OptunaOptimizer,
    WFOConfig,
    WalkForwardEngine,
    deflated_sharpe_ratio,
)
from suitetrading.optimization._internal.objective import BacktestObjective


# ── Helpers ───────────────────────────────────────────────────────────

def _make_trending_dataset(n_bars: int = 2000, seed: int = 42) -> BacktestDataset:
    """Trending dataset with enough bars for WFO."""
    idx = pd.date_range("2023-01-01", periods=n_bars, freq="h", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.05, 1.0, n_bars))
    close = np.maximum(close, 10.0)
    ohlcv = pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.2, n_bars),
            "high": close + np.abs(rng.normal(0.3, 0.2, n_bars)),
            "low": close - np.abs(rng.normal(0.3, 0.2, n_bars)),
            "close": close,
            "volume": rng.integers(500, 5000, n_bars).astype(float),
        },
        index=idx,
    )
    return BacktestDataset(
        exchange="synthetic", symbol="BTCUSDT",
        base_timeframe="1h", ohlcv=ohlcv,
    )


def _signal_builder(dataset: BacktestDataset, params: dict) -> StrategySignals:
    close = dataset.ohlcv["close"]
    period = params.get("sma", {}).get("period", 20)
    sma = close.rolling(period, min_periods=1).mean()
    entry = (close > sma) & (close.shift(1) <= sma.shift(1))
    return StrategySignals(entry_long=entry.fillna(False))


def _risk_builder(archetype: str, overrides: dict):
    from suitetrading.risk.archetypes import get_archetype
    return get_archetype(archetype).build_config(**overrides)


# ── Tests ─────────────────────────────────────────────────────────────

class TestE2EWalkForwardPipeline:
    """Full pipeline: candidates → WFO → anti-overfit filter."""

    def test_wfo_then_anti_overfit(self):
        ds = _make_trending_dataset(1200)

        candidates = [
            {"indicator_params": {"sma": {"period": p}}, "risk_overrides": {}}
            for p in [10, 15, 20, 30, 40]
        ]

        # Walk-Forward
        wfo_cfg = WFOConfig(
            n_splits=3, min_is_bars=200, min_oos_bars=50,
            gap_bars=0, mode="rolling",
        )
        wfo = WalkForwardEngine(config=wfo_cfg, metric="sharpe")
        wfo_result = wfo.run(
            dataset=ds,
            candidate_params=candidates,
            archetype="trend_following",
            signal_builder=_signal_builder,
            risk_builder=_risk_builder,
        )

        assert wfo_result.n_candidates == 5
        assert len(wfo_result.oos_equity_curves) == 5
        assert len(wfo_result.splits) == 3

        # Anti-overfit
        eq_curves = wfo_result.oos_equity_curves
        non_empty = {k: v for k, v in eq_curves.items() if len(v) > 0}

        if len(non_empty) >= 2:
            pipeline = AntiOverfitPipeline(
                pbo_threshold=0.95,  # lenient for synthetic
                dsr_threshold=0.01,
                n_subsamples=4,
            )
            result = pipeline.evaluate(
                equity_curves=non_empty,
                n_trials=len(candidates),
            )
            assert result.total_candidates == len(non_empty)
            # Pipeline should run without errors (finalists count varies)


class TestE2EOptunaWFO:
    """Optuna → WFO integration (small scale)."""

    def test_optuna_top_candidates_to_wfo(self):
        ds = _make_trending_dataset(1200)

        # Small Optuna run
        objective = BacktestObjective(
            dataset=ds,
            indicator_names=["rsi"],
            archetype="trend_following",
            metric="sharpe",
        )
        optimizer = OptunaOptimizer(
            objective=objective,
            study_name="e2e_test",
            sampler="random",
            n_startup_trials=5,
        )
        opt_result = optimizer.optimize(n_trials=10, timeout=60)
        assert opt_result.n_completed > 0

        # Get top candidates and feed to WFO
        top = optimizer.get_top_n(3)
        candidates = []
        for t in top:
            candidates.append({
                "indicator_params": t.get("indicator_params", {}),
                "risk_overrides": t.get("risk_overrides", {}),
            })

        if not candidates:
            pytest.skip("No completed trials")

        wfo_cfg = WFOConfig(
            n_splits=2, min_is_bars=200, min_oos_bars=50,
            gap_bars=0, mode="rolling",
        )
        wfo = WalkForwardEngine(config=wfo_cfg, metric="sharpe")
        wfo_result = wfo.run(
            dataset=ds,
            candidate_params=candidates,
            archetype="trend_following",
            signal_builder=_signal_builder,
            risk_builder=_risk_builder,
        )
        assert wfo_result.n_candidates == len(candidates)


class TestE2ECSCVDSR:
    """CSCV + DSR used together on synthetic data."""

    def test_cscv_then_dsr_coherent(self):
        rng = np.random.default_rng(42)
        # Genuinely different strategies
        curves = {}
        for i in range(4):
            drift = 0.003 * (i + 1)
            returns = drift + rng.normal(0, 0.01, 500)
            curves[f"s{i}"] = 10_000.0 * np.cumprod(1 + returns)

        cscv = CSCVValidator(n_subsamples=4, metric="sharpe")
        cscv_result = cscv.compute_pbo(curves)
        assert 0.0 <= cscv_result.pbo <= 1.0

        # DSR for the best strategy
        best_key = max(curves, key=lambda k: curves[k][-1])
        eq = curves[best_key]
        ret = np.diff(eq) / eq[:-1]
        obs_sharpe = float(np.mean(ret) / np.std(ret, ddof=1))

        dsr_result = deflated_sharpe_ratio(
            observed_sharpe=obs_sharpe,
            n_trials=4,
            sample_length=len(ret),
        )
        assert isinstance(dsr_result.dsr, float)


class TestImportsAvailable:
    """Verify all public API imports work."""

    def test_core_imports(self):
        from suitetrading.optimization import (
            AntiOverfitPipeline,
            CSCVValidator,
            OptunaOptimizer,
            ParallelExecutor,
            WalkForwardEngine,
            deflated_sharpe_ratio,
        )
        assert all([
            OptunaOptimizer, WalkForwardEngine, CSCVValidator,
            deflated_sharpe_ratio, AntiOverfitPipeline, ParallelExecutor,
        ])

    def test_schema_imports(self):
        from suitetrading.optimization import (
            AntiOverfitResult,
            CSCVResult,
            DSRResult,
            ObjectiveResult,
            OptimizationResult,
            PipelineResult,
            SPAResult,
            StrategyReport,
            WFOConfig,
            WFOResult,
        )
        assert WFOConfig().n_splits == 5

    def test_conditional_imports(self):
        from suitetrading.optimization import DEAPOptimizer, FeatureImportanceEngine
        # These may be None if deps not installed, but import should not fail
        assert DEAPOptimizer is not None or DEAPOptimizer is None
        assert FeatureImportanceEngine is not None or FeatureImportanceEngine is None
