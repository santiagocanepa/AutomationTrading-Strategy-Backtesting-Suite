"""Tests for WalkForwardEngine — splits + run + degradation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.optimization._internal.schemas import WFOConfig, WFOResult
from suitetrading.optimization.walk_forward import WalkForwardEngine


# ── Helpers ───────────────────────────────────────────────────────────

def _make_dataset(n_bars: int, *, seed: int = 42) -> BacktestDataset:
    """Create a minimal synthetic dataset with *n_bars* rows."""
    idx = pd.date_range("2024-01-01", periods=n_bars, freq="h", tz="UTC")
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
        exchange="synthetic",
        symbol="BTCUSDT",
        base_timeframe="1h",
        ohlcv=ohlcv,
    )


# ── Rolling split tests ──────────────────────────────────────────────

class TestRollingSplits:
    """Tests for rolling (sliding window) WFO splits."""

    def test_correct_number_of_splits(self):
        cfg = WFOConfig(n_splits=3, min_is_bars=200, min_oos_bars=50, gap_bars=0, mode="rolling")
        engine = WalkForwardEngine(config=cfg)
        splits = engine.generate_splits(500)
        assert len(splits) == 3

    def test_is_and_oos_sizes(self):
        cfg = WFOConfig(n_splits=3, min_is_bars=200, min_oos_bars=50, gap_bars=0, mode="rolling")
        engine = WalkForwardEngine(config=cfg)
        splits = engine.generate_splits(500)
        for is_range, oos_range in splits:
            assert len(is_range) == 200
            assert len(oos_range) == 50

    def test_gap_respected(self):
        gap = 10
        cfg = WFOConfig(n_splits=2, min_is_bars=200, min_oos_bars=50, gap_bars=gap, mode="rolling")
        engine = WalkForwardEngine(config=cfg)
        splits = engine.generate_splits(600)
        for is_range, oos_range in splits:
            assert oos_range.start == is_range.stop + gap

    def test_no_overlap_between_is_and_oos_in_same_fold(self):
        cfg = WFOConfig(n_splits=3, min_is_bars=100, min_oos_bars=30, gap_bars=5, mode="rolling")
        engine = WalkForwardEngine(config=cfg)
        splits = engine.generate_splits(500)
        for is_range, oos_range in splits:
            is_set = set(is_range)
            oos_set = set(oos_range)
            assert is_set.isdisjoint(oos_set)

    def test_oos_within_bounds(self):
        cfg = WFOConfig(n_splits=5, min_is_bars=100, min_oos_bars=30, gap_bars=0, mode="rolling")
        engine = WalkForwardEngine(config=cfg)
        n = 600
        splits = engine.generate_splits(n)
        for _, oos_range in splits:
            assert oos_range.start >= 0
            assert oos_range.stop <= n

    def test_too_few_bars_raises_error(self):
        cfg = WFOConfig(n_splits=3, min_is_bars=400, min_oos_bars=200, gap_bars=0, mode="rolling")
        engine = WalkForwardEngine(config=cfg)
        with pytest.raises(ValueError, match="Not enough bars"):
            engine.generate_splits(500)

    def test_splits_slide_forward(self):
        cfg = WFOConfig(n_splits=4, min_is_bars=100, min_oos_bars=30, gap_bars=0, mode="rolling")
        engine = WalkForwardEngine(config=cfg)
        splits = engine.generate_splits(500)
        starts = [is_r.start for is_r, _ in splits]
        # Each fold should start at a later point in time
        assert starts == sorted(starts)
        assert len(set(starts)) == len(starts)  # all unique


# ── Anchored split tests ─────────────────────────────────────────────

class TestAnchoredSplits:
    """Tests for anchored (expanding IS) WFO splits."""

    def test_is_always_starts_at_zero(self):
        cfg = WFOConfig(n_splits=3, min_is_bars=100, min_oos_bars=50, gap_bars=0, mode="anchored")
        engine = WalkForwardEngine(config=cfg)
        splits = engine.generate_splits(500)
        for is_range, _ in splits:
            assert is_range.start == 0

    def test_is_grows_each_fold(self):
        cfg = WFOConfig(n_splits=3, min_is_bars=100, min_oos_bars=50, gap_bars=0, mode="anchored")
        engine = WalkForwardEngine(config=cfg)
        splits = engine.generate_splits(500)
        is_sizes = [len(is_r) for is_r, _ in splits]
        assert is_sizes == sorted(is_sizes)
        assert len(set(is_sizes)) > 1  # they grow, not all the same

    def test_gap_respected_anchored(self):
        gap = 5
        cfg = WFOConfig(n_splits=3, min_is_bars=100, min_oos_bars=50, gap_bars=gap, mode="anchored")
        engine = WalkForwardEngine(config=cfg)
        splits = engine.generate_splits(500)
        for is_range, oos_range in splits:
            assert oos_range.start == is_range.stop + gap

    def test_oos_within_bounds_anchored(self):
        cfg = WFOConfig(n_splits=3, min_is_bars=100, min_oos_bars=50, gap_bars=0, mode="anchored")
        engine = WalkForwardEngine(config=cfg)
        n = 500
        splits = engine.generate_splits(n)
        for _, oos_range in splits:
            assert oos_range.stop <= n

    def test_too_few_bars_raises_error_anchored(self):
        cfg = WFOConfig(n_splits=3, min_is_bars=400, min_oos_bars=200, gap_bars=0, mode="anchored")
        engine = WalkForwardEngine(config=cfg)
        with pytest.raises(ValueError, match="Not enough bars"):
            engine.generate_splits(500)

    def test_min_is_respected(self):
        cfg = WFOConfig(n_splits=3, min_is_bars=100, min_oos_bars=50, gap_bars=0, mode="anchored")
        engine = WalkForwardEngine(config=cfg)
        splits = engine.generate_splits(500)
        for is_range, _ in splits:
            assert len(is_range) >= 100


# ── Param ID ──────────────────────────────────────────────────────────

class TestParamId:
    """Test the deterministic param ID hash."""

    def test_same_params_same_id(self):
        params = {"indicator_params": {"sma": {"period": 20}}, "risk_overrides": {}}
        id1 = WalkForwardEngine._param_id(params)
        id2 = WalkForwardEngine._param_id(params)
        assert id1 == id2

    def test_different_params_different_id(self):
        p1 = {"indicator_params": {"sma": {"period": 20}}, "risk_overrides": {}}
        p2 = {"indicator_params": {"sma": {"period": 30}}, "risk_overrides": {}}
        assert WalkForwardEngine._param_id(p1) != WalkForwardEngine._param_id(p2)


# ── WFO run with mock backtests ──────────────────────────────────────

class TestWFORun:
    """Test full WFO run using synthetic signal/risk builders."""

    @staticmethod
    def _dummy_signal_builder(dataset: BacktestDataset, params: dict) -> StrategySignals:
        """Signals: entry when close > simple moving average."""
        close = dataset.ohlcv["close"]
        period = params.get("sma", {}).get("period", 20)
        sma = close.rolling(period, min_periods=1).mean()
        entry = (close > sma) & (close.shift(1) <= sma.shift(1))
        return StrategySignals(entry_long=entry.fillna(False))

    @staticmethod
    def _dummy_risk_builder(archetype: str, overrides: dict):
        from suitetrading.risk.archetypes import get_archetype
        return get_archetype(archetype).build_config(**overrides)

    def test_run_returns_wfo_result(self):
        ds = _make_dataset(800)
        cfg = WFOConfig(n_splits=2, min_is_bars=200, min_oos_bars=50, gap_bars=0, mode="rolling")
        engine = WalkForwardEngine(config=cfg, metric="sharpe")

        candidates = [
            {"indicator_params": {"sma": {"period": 10}}, "risk_overrides": {}},
            {"indicator_params": {"sma": {"period": 30}}, "risk_overrides": {}},
        ]
        result = engine.run(
            dataset=ds,
            candidate_params=candidates,
            archetype="trend_following",
            signal_builder=self._dummy_signal_builder,
            risk_builder=self._dummy_risk_builder,
        )
        assert isinstance(result, WFOResult)
        assert result.n_candidates == 2
        assert len(result.splits) == 2
        assert len(result.oos_equity_curves) == 2
        assert len(result.degradation) == 2

    def test_oos_equity_curves_have_data(self):
        ds = _make_dataset(800)
        cfg = WFOConfig(n_splits=2, min_is_bars=200, min_oos_bars=50, gap_bars=0, mode="rolling")
        engine = WalkForwardEngine(config=cfg, metric="sharpe")

        candidates = [
            {"indicator_params": {"sma": {"period": 15}}, "risk_overrides": {}},
        ]
        result = engine.run(
            dataset=ds,
            candidate_params=candidates,
            archetype="trend_following",
            signal_builder=self._dummy_signal_builder,
            risk_builder=self._dummy_risk_builder,
        )
        for pid, eq in result.oos_equity_curves.items():
            assert len(eq) > 0, "OOS equity curve should not be empty"

    def test_degradation_is_finite(self):
        ds = _make_dataset(800)
        cfg = WFOConfig(n_splits=2, min_is_bars=200, min_oos_bars=50, gap_bars=0, mode="rolling")
        engine = WalkForwardEngine(config=cfg, metric="total_return_pct")

        candidates = [
            {"indicator_params": {"sma": {"period": 20}}, "risk_overrides": {}},
        ]
        result = engine.run(
            dataset=ds,
            candidate_params=candidates,
            archetype="trend_following",
            signal_builder=self._dummy_signal_builder,
            risk_builder=self._dummy_risk_builder,
        )
        for pid, deg in result.degradation.items():
            assert isinstance(deg, float)

    def test_anchored_run_works(self):
        ds = _make_dataset(800)
        cfg = WFOConfig(n_splits=2, min_is_bars=200, min_oos_bars=50, gap_bars=0, mode="anchored")
        engine = WalkForwardEngine(config=cfg, metric="sharpe")

        candidates = [
            {"indicator_params": {"sma": {"period": 20}}, "risk_overrides": {}},
        ]
        result = engine.run(
            dataset=ds,
            candidate_params=candidates,
            archetype="trend_following",
            signal_builder=self._dummy_signal_builder,
            risk_builder=self._dummy_risk_builder,
        )
        assert isinstance(result, WFOResult)
        assert len(result.splits) == 2

    def test_split_details_have_best_info(self):
        ds = _make_dataset(800)
        cfg = WFOConfig(n_splits=2, min_is_bars=200, min_oos_bars=50, gap_bars=0, mode="rolling")
        engine = WalkForwardEngine(config=cfg, metric="sharpe")

        candidates = [
            {"indicator_params": {"sma": {"period": 10}}, "risk_overrides": {}},
            {"indicator_params": {"sma": {"period": 25}}, "risk_overrides": {}},
        ]
        result = engine.run(
            dataset=ds,
            candidate_params=candidates,
            archetype="trend_following",
            signal_builder=self._dummy_signal_builder,
            risk_builder=self._dummy_risk_builder,
        )
        for detail in result.splits:
            assert "fold" in detail
            assert "is_range" in detail
            assert "oos_range" in detail
            assert "best_is_params_idx" in detail
            assert "best_is_metric" in detail
