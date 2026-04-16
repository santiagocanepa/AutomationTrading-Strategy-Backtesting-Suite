"""Tests for rolling portfolio validation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from suitetrading.optimization.rolling_validation import (
    RollingPortfolioEvaluator,
    RollingValidationResult,
    StrategySpec,
    WindowResult,
    _align_to_daily,
    _binomial_pvalue,
    _classify_window_regime,
    _flatten_params,
    _regime_adaptive_weights,
)


# ── Fixtures ──────────────────────────────────────────────────────────

def _make_evidence_card(
    *,
    symbol: str = "SOLUSDT",
    timeframe: str = "4h",
    archetype: str = "roc_volspike_fullrisk_pyr",
    direction: str = "long",
    pbo: float = 0.05,
    candidate_id: str = "abc12345deadbeef",
) -> dict:
    return {
        "candidate_id": candidate_id,
        "trial_number": 1,
        "pbo": pbo,
        "dsr": 0.95,
        "observed_sharpe": 0.1,
        "degradation": 0.2,
        "oos_metrics": {"sharpe": 1.5, "total_return_pct": 20.0},
        "indicator_params": {
            "roc": {"period": 10, "mode": "bullish", "hold_bars": 2},
        },
        "risk_overrides": {
            "stop__atr_multiple": 5.0,
            "sizing__risk_pct": 4.0,
        },
        "study": f"{symbol}_{timeframe}_{archetype}_{direction}",
        "symbol": symbol,
        "timeframe": timeframe,
        "archetype": archetype,
        "direction": direction,
        "rank": 1,
    }


def _make_synthetic_ohlcv(
    n_bars: int = 2000,
    freq: str = "4h",
    seed: int = 42,
    trend: float = 0.02,
) -> pd.DataFrame:
    """Deterministic trending OHLCV data."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n_bars, freq=freq, tz="UTC")
    close = 100.0 + np.cumsum(rng.normal(trend, 1.0, n_bars))
    close = np.maximum(close, 10.0)
    return pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.2, n_bars),
            "high": close + np.abs(rng.normal(0.5, 0.3, n_bars)),
            "low": close - np.abs(rng.normal(0.5, 0.3, n_bars)),
            "close": close,
            "volume": rng.integers(500, 5000, n_bars).astype(float),
        },
        index=idx,
    )


# ── Test 1: Parse evidence card ──────────────────────────────────────

class TestStrategySpecFromEvidenceCard:
    def test_parses_correctly(self, tmp_path: Path):
        card = _make_evidence_card(symbol="BTCUSDT", direction="long", pbo=0.016)
        card_path = tmp_path / "finalist_001.json"
        card_path.write_text(json.dumps(card))

        spec = StrategySpec.from_evidence_card(card_path)

        assert spec.symbol == "BTCUSDT"
        assert spec.direction == "long"
        assert spec.pbo == 0.016
        assert spec.archetype == "roc_volspike_fullrisk_pyr"
        assert "roc" in spec.indicator_params
        assert spec.indicator_params["roc"]["period"] == 10
        assert spec.risk_overrides["stop__atr_multiple"] == 5.0
        assert "BTCUSDT" in spec.label

    def test_label_includes_candidate_id(self, tmp_path: Path):
        card = _make_evidence_card(candidate_id="1234567890abcdef")
        card_path = tmp_path / "finalist_002.json"
        card_path.write_text(json.dumps(card))

        spec = StrategySpec.from_evidence_card(card_path)
        assert "12345678" in spec.label


# ── Test 2: Window generation ─────────────────────────────────────────

class TestWindowGeneration:
    def test_window_count_and_boundaries(self):
        # 84 months of 4h data ≈ 84*30*6 = 15120 bars
        ohlcv = _make_synthetic_ohlcv(n_bars=15120, freq="4h")
        cache = {"SOLUSDT_4h": ohlcv}

        evaluator = RollingPortfolioEvaluator(
            window_months=6, slide_months=2,
            weight_methods=("equal",),
        )
        windows = evaluator._generate_windows(cache)

        # (84 - 6) / 2 + 1 = 40 windows approximately
        assert len(windows) >= 35
        assert len(windows) <= 45

        # All windows should be 6 months long
        for start, end in windows:
            delta = end - start
            assert 170 <= delta.days <= 190  # ~6 months

    def test_windows_cover_full_range(self):
        ohlcv = _make_synthetic_ohlcv(n_bars=5000, freq="1h")
        cache = {"TEST_1h": ohlcv}

        evaluator = RollingPortfolioEvaluator(
            window_months=3, slide_months=1,
            weight_methods=("equal",),
        )
        windows = evaluator._generate_windows(cache)

        # First window should start at or near data start
        data_start = ohlcv.index[0]
        assert windows[0][0] == data_start

        # Last window end should be close to data end
        data_end = ohlcv.index[-1]
        last_end = windows[-1][1]
        assert (data_end - last_end).days < 90


# ── Test 3: Single window evaluation ─────────────────────────────────

class TestClassifyWindowRegime:
    def test_crash(self):
        # Simulate -50% drop with -60% max DD
        n = 500
        idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
        close = np.linspace(100, 40, n)  # -60%
        df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000.0}, index=idx)
        assert _classify_window_regime(df) == "crash"

    def test_trend_up(self):
        n = 500
        idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
        close = np.linspace(100, 150, n)  # +50%
        df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000.0}, index=idx)
        assert _classify_window_regime(df) == "trend_up"

    def test_trend_down(self):
        n = 500
        idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
        close = np.linspace(100, 65, n)  # -35%, max DD ~35% (no crash, DD < 40%)
        df = pd.DataFrame({"open": close, "high": close + 0.1, "low": close - 0.1, "close": close, "volume": 1000.0}, index=idx)
        assert _classify_window_regime(df) == "trend_down"

    def test_range(self):
        n = 500
        idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
        rng = np.random.default_rng(42)
        close = 100 + rng.normal(0, 0.5, n).cumsum()  # sideways
        close = np.clip(close, 80, 120)
        df = pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5, "close": close, "volume": 1000.0}, index=idx)
        regime = _classify_window_regime(df)
        assert regime in ("range", "high_vol")  # depends on vol realization

    def test_empty_df(self):
        df = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
        assert _classify_window_regime(df) == "range"


class TestSingleWindowEvaluation:
    def test_returns_valid_metrics(self):
        """Smoke test with a real BacktestObjective — requires real archetype."""
        ohlcv_4h = _make_synthetic_ohlcv(n_bars=2000, freq="4h", seed=42, trend=0.05)
        cache = {"SOLUSDT_4h": ohlcv_4h}

        spec = StrategySpec(
            symbol="SOLUSDT",
            timeframe="4h",
            archetype="roc_volspike_fullrisk_pyr",
            direction="long",
            indicator_params={
                "roc": {"period": 10, "mode": "bullish", "hold_bars": 2},
                "volume_spike": {"lookback": 36, "threshold": 1.5, "mode": "bearish", "hold_bars": 3},
                "ssl_channel": {"length": 50, "hold_bars": 5},
            },
            risk_overrides={
                "stop__atr_multiple": 5.0,
                "sizing__risk_pct": 4.0,
                "partial_tp__r_multiple": 1.25,
                "partial_tp__close_pct": 10.0,
                "break_even__buffer": 1.007,
                "pyramid__max_adds": 2,
                "pyramid__block_bars": 20,
                "pyramid__threshold_factor": 1.015,
            },
            pbo=0.05,
            label="SOLUSDT_4h_roc_volspike_long_test",
        )

        evaluator = RollingPortfolioEvaluator(
            window_months=6, slide_months=2,
            weight_methods=("equal",),
            mode="fsm",
        )

        start = ohlcv_4h.index[0]
        end = start + pd.DateOffset(months=6)

        wr = evaluator._evaluate_window([spec], cache, start, end, window_id=0)

        assert isinstance(wr, WindowResult)
        assert wr.window_id == 0
        assert wr.dominant_regime in ("trend_up", "trend_down", "range", "high_vol", "crash")


# ── Test 4: Regime adaptive weights ──────────────────────────────────

class TestRegimeAdaptiveWeights:
    def _make_specs(self) -> list[StrategySpec]:
        base = dict(
            symbol="SOL", timeframe="4h", archetype="test",
            indicator_params={}, risk_overrides={}, pbo=0.1,
        )
        return [
            StrategySpec(**base, direction="long", label="long_1"),
            StrategySpec(**base, direction="short", label="short_1"),
        ]

    def test_trend_up_favors_long(self):
        specs = self._make_specs()
        w = _regime_adaptive_weights(specs, "trend_up")
        assert w[0] > w[1]  # long > short
        assert abs(w.sum() - 1.0) < 1e-9

    def test_crash_favors_short(self):
        specs = self._make_specs()
        w = _regime_adaptive_weights(specs, "crash")
        assert w[1] > w[0]  # short > long
        assert abs(w.sum() - 1.0) < 1e-9

    def test_range_is_equal(self):
        specs = self._make_specs()
        w = _regime_adaptive_weights(specs, "range")
        assert abs(w[0] - w[1]) < 1e-9

    def test_unknown_regime_defaults_equal(self):
        specs = self._make_specs()
        w = _regime_adaptive_weights(specs, "unknown_regime")
        assert abs(w[0] - w[1]) < 1e-9


# ── Test 5: Multi-TF alignment ───────────────────────────────────────

class TestMultiTFAlignment:
    def test_aligns_1h_and_4h_to_daily(self):
        n_1h = 720  # ~30 days
        n_4h = 180  # ~30 days
        idx_1h = pd.date_range("2024-01-01", periods=n_1h, freq="h", tz="UTC")
        idx_4h = pd.date_range("2024-01-01", periods=n_4h, freq="4h", tz="UTC")

        eq_1h = np.linspace(100_000, 110_000, n_1h)
        eq_4h = np.linspace(100_000, 105_000, n_4h)

        daily_1h = _align_to_daily(eq_1h, idx_1h)
        daily_4h = _align_to_daily(eq_4h, idx_4h)

        # Both should have ~30 daily values
        assert 28 <= len(daily_1h) <= 32
        assert 28 <= len(daily_4h) <= 32

        # Last value should be close to original last
        assert abs(daily_1h.iloc[-1] - 110_000) < 200
        assert abs(daily_4h.iloc[-1] - 105_000) < 200

    def test_ffill_handles_gaps(self):
        idx = pd.date_range("2024-01-01", periods=100, freq="4h", tz="UTC")
        eq = np.linspace(1000, 2000, 100)
        daily = _align_to_daily(eq, idx)
        assert not daily.isna().any()


# ── Test 6: Aggregation % positive ───────────────────────────────────

class TestAggregationPctPositive:
    def test_calculates_correctly(self):
        evaluator = RollingPortfolioEvaluator(
            window_months=6, slide_months=2,
            weight_methods=("equal",),
        )

        # Build mock windows: 8 positive, 2 negative
        windows = []
        for i in range(10):
            sharpe = 0.5 if i < 8 else -0.5
            wr = WindowResult(
                window_id=i, start="2020-01-01", end="2020-07-01",
                n_bars=1000, dominant_regime="trend_up", is_oos=False,
                strategy_metrics={},
                portfolio_metrics={"equal": {"sharpe": sharpe, "total_return_pct": 10.0, "max_drawdown_pct": 5.0}},
            )
            windows.append(wr)

        agg = evaluator._aggregate(windows)
        assert abs(agg["pct_positive_sharpe"]["equal"] - 80.0) < 0.1


# ── Test 7: Binomial p-value ─────────────────────────────────────────

class TestBinomialPvalue:
    def test_strong_signal(self):
        # 30 out of 40 positive → should be significant
        p = _binomial_pvalue(30, 40)
        assert p < 0.005

    def test_chance_level(self):
        # 20 out of 40 → not significant (p ≈ 0.5)
        p = _binomial_pvalue(20, 40)
        assert p > 0.4

    def test_edge_case_zero_total(self):
        p = _binomial_pvalue(0, 0)
        assert p == 1.0


# ── Test 8: Full evaluation smoke test ────────────────────────────────

class TestFullEvaluationSmoke:
    def test_end_to_end_with_synthetic_data(self):
        """Full evaluation with short windows for speed."""
        ohlcv = _make_synthetic_ohlcv(n_bars=3000, freq="4h", seed=123, trend=0.03)
        cache = {"SOLUSDT_4h": ohlcv}

        spec_long = StrategySpec(
            symbol="SOLUSDT",
            timeframe="4h",
            archetype="roc_volspike_fullrisk_pyr",
            direction="long",
            indicator_params={
                "roc": {"period": 10, "mode": "bullish", "hold_bars": 2},
                "volume_spike": {"lookback": 36, "threshold": 1.5, "mode": "bearish", "hold_bars": 3},
                "ssl_channel": {"length": 50, "hold_bars": 5},
            },
            risk_overrides={
                "stop__atr_multiple": 5.0,
                "sizing__risk_pct": 4.0,
                "partial_tp__r_multiple": 1.25,
                "partial_tp__close_pct": 10.0,
                "break_even__buffer": 1.007,
                "pyramid__max_adds": 2,
                "pyramid__block_bars": 20,
                "pyramid__threshold_factor": 1.015,
            },
            pbo=0.05,
            label="SOLUSDT_4h_long_test",
        )

        evaluator = RollingPortfolioEvaluator(
            window_months=4, slide_months=4,  # Larger slide for fewer windows = faster
            weight_methods=("equal",),
            mode="fsm",
        )

        result = evaluator.evaluate([spec_long], cache)

        assert isinstance(result, RollingValidationResult)
        assert result.n_windows >= 1
        assert result.timestamp
        assert "equal" in result.pct_positive_sharpe
        assert "equal" in result.binomial_p_value
        assert result.best_method == "equal"

    def test_flatten_params_roundtrip(self):
        indicator_params = {
            "roc": {"period": 10, "mode": "bullish"},
            "ssl_channel": {"length": 50},
        }
        risk_overrides = {"stop__atr_multiple": 5.0, "sizing__risk_pct": 4.0}

        flat = _flatten_params(indicator_params, risk_overrides)

        assert flat["roc__period"] == 10
        assert flat["roc__mode"] == "bullish"
        assert flat["ssl_channel__length"] == 50
        assert flat["stop__atr_multiple"] == 5.0
        assert flat["sizing__risk_pct"] == 4.0
