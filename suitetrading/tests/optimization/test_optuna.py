"""Tests for Optuna optimizer and objective function."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.optimization._internal.objective import (
    BacktestObjective,
    _suggest_param,
    filter_search_space,
)
from suitetrading.optimization.optuna_optimizer import OptunaOptimizer


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def small_dataset():
    """Tiny dataset for fast optimizer tests."""
    n = 200
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(42)
    close = 100.0 + np.cumsum(rng.normal(0.05, 1.0, n))
    close = np.maximum(close, 10.0)
    ohlcv = pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.2, n),
            "high": close + np.abs(rng.normal(0.3, 0.2, n)),
            "low": close - np.abs(rng.normal(0.3, 0.2, n)),
            "close": close,
            "volume": rng.integers(500, 5000, n).astype(float),
        },
        index=idx,
    )
    return BacktestDataset(exchange="synthetic", symbol="BTCUSDT", base_timeframe="1h", ohlcv=ohlcv)


@pytest.fixture
def rsi_objective(small_dataset):
    """Objective with only RSI indicator for speed."""
    return BacktestObjective(
        dataset=small_dataset,
        indicator_names=["rsi"],
        archetype="trend_following",
        metric="sharpe",
        risk_search_space={
            "stop__atr_multiple": {"type": "float", "min": 1.0, "max": 4.0, "step": 0.5},
        },
        mode="simple",
    )


# ── Objective tests ───────────────────────────────────────────────────

class TestBacktestObjective:
    def test_returns_float(self, rsi_objective):
        """Objective returns a finite float."""
        import optuna

        study = optuna.create_study(direction="maximize")
        study.optimize(rsi_objective, n_trials=1, show_progress_bar=False)
        assert study.best_trial.state.name == "COMPLETE"
        assert isinstance(study.best_trial.value, float)
        assert np.isfinite(study.best_trial.value)

    def test_stores_user_attrs(self, rsi_objective):
        import optuna

        study = optuna.create_study(direction="maximize")
        study.optimize(rsi_objective, n_trials=1, show_progress_bar=False)
        trial = study.best_trial
        assert "metrics" in trial.user_attrs
        assert "indicator_params" in trial.user_attrs
        assert "risk_overrides" in trial.user_attrs

    def test_build_signals_returns_strategy_signals(self, rsi_objective):
        params = {"rsi": {"period": 14, "threshold": 30.0, "mode": "oversold"}}
        signals = rsi_objective.build_signals(params)
        assert isinstance(signals, StrategySignals)
        assert signals.entry_long.dtype == bool

    def test_build_risk_config(self, rsi_objective):
        from suitetrading.risk.contracts import RiskConfig

        rc = rsi_objective.build_risk_config({"stop": {"atr_multiple": 2.5}})
        assert isinstance(rc, RiskConfig)


class TestSuggestParam:
    def test_int_param(self):
        import optuna

        study = optuna.create_study()

        def _obj(trial):
            v = _suggest_param(trial, "period", {"type": "int", "min": 5, "max": 50})
            return float(v)

        study.optimize(_obj, n_trials=1, show_progress_bar=False)
        val = study.best_trial.params["period"]
        assert isinstance(val, int)
        assert 5 <= val <= 50

    def test_float_param(self):
        import optuna

        study = optuna.create_study()

        def _obj(trial):
            v = _suggest_param(trial, "mult", {"type": "float", "min": 0.5, "max": 5.0, "step": 0.1})
            return v

        study.optimize(_obj, n_trials=1, show_progress_bar=False)
        val = study.best_trial.params["mult"]
        assert isinstance(val, float)

    def test_categorical_param(self):
        import optuna

        study = optuna.create_study()

        def _obj(trial):
            v = _suggest_param(trial, "mode", {"type": "str", "choices": ["a", "b"]})
            return 1.0 if v == "a" else 0.0

        study.optimize(_obj, n_trials=1, show_progress_bar=False)
        assert study.best_trial.params["mode"] in ("a", "b")


# ── OptunaOptimizer tests ─────────────────────────────────────────────

class TestOptunaOptimizer:
    def test_optimize_in_memory(self, rsi_objective):
        optimizer = OptunaOptimizer(
            objective=rsi_objective,
            study_name="test_inmem",
            storage=None,
            sampler="random",
            pruner="none",
            n_startup_trials=2,
            seed=42,
        )
        result = optimizer.optimize(n_trials=5)
        assert result.n_completed >= 1
        assert result.study_name == "test_inmem"
        assert isinstance(result.best_value, float)
        assert result.wall_time_sec > 0

    def test_get_top_n(self, rsi_objective):
        optimizer = OptunaOptimizer(
            objective=rsi_objective,
            study_name="test_topn",
            storage=None,
            sampler="random",
            pruner="none",
            seed=42,
        )
        optimizer.optimize(n_trials=10)
        top = optimizer.get_top_n(3)
        assert len(top) == 3
        # Should be sorted descending (maximize)
        assert top[0]["value"] >= top[1]["value"]

    def test_study_persistence_sqlite(self, rsi_objective):
        """Study persists and resumes from SQLite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"sqlite:///{tmpdir}/studies.db"

            # First run: 5 trials
            opt1 = OptunaOptimizer(
                objective=rsi_objective,
                study_name="persist_test",
                storage=db_path,
                sampler="random",
                pruner="none",
                seed=42,
            )
            opt1.optimize(n_trials=5)
            n_first = len(opt1.get_study().trials)
            assert n_first == 5

            # Second run: 3 more trials (resumes)
            opt2 = OptunaOptimizer(
                objective=rsi_objective,
                study_name="persist_test",
                storage=db_path,
                sampler="random",
                pruner="none",
                seed=43,
            )
            opt2.optimize(n_trials=3)
            n_total = len(opt2.get_study().trials)
            assert n_total == 8  # 5 + 3

    def test_get_study_returns_optuna_study(self, rsi_objective):
        import optuna

        optimizer = OptunaOptimizer(
            objective=rsi_objective,
            study_name="test_access",
            storage=None,
            sampler="random",
            pruner="none",
        )
        assert isinstance(optimizer.get_study(), optuna.Study)

    def test_sampler_tpe(self, rsi_objective):
        optimizer = OptunaOptimizer(
            objective=rsi_objective,
            study_name="test_tpe",
            storage=None,
            sampler="tpe",
            n_startup_trials=3,
            seed=42,
        )
        result = optimizer.optimize(n_trials=5)
        assert result.n_completed >= 1


# ── Filter search space tests ────────────────────────────────────────

class TestFilterSearchSpace:
    SPACE = {
        "stop__atr_multiple": {"type": "float", "min": 1.0, "max": 5.0},
        "sizing__risk_pct": {"type": "float", "min": 0.5, "max": 3.0},
        "trailing__model": {"type": "str", "choices": ["atr", "chandelier"]},
        "squeeze_momentum": {"type": "float", "min": 0.1, "max": 1.0},
    }
    MATURITY = {
        "stop__atr_multiple": "active",
        "sizing__risk_pct": "active",
        "trailing__model": "partial",
        "squeeze_momentum": "experimental",
    }

    def test_filter_active_only(self):
        result = filter_search_space(self.SPACE, self.MATURITY, level="active")
        assert set(result.keys()) == {"stop__atr_multiple", "sizing__risk_pct"}

    def test_filter_active_plus_partial(self):
        result = filter_search_space(self.SPACE, self.MATURITY, level="partial")
        assert set(result.keys()) == {"stop__atr_multiple", "sizing__risk_pct", "trailing__model"}

    def test_unknown_key_defaults_to_experimental(self):
        space = {"unknown_param": {"type": "float", "min": 0, "max": 1}}
        result = filter_search_space(space, {}, level="active")
        assert result == {}
