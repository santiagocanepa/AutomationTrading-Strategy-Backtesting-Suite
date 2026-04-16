"""Tests for Rich Archetype: dynamic states, per-indicator TFs, num_optional_required."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import optuna

from suitetrading.backtesting._internal.schemas import BacktestDataset
from suitetrading.config.archetypes import (
    ARCHETYPE_INDICATORS,
    get_entry_indicators,
)
from suitetrading.indicators.base import IndicatorState
from suitetrading.indicators.signal_combiner import combine_signals
from suitetrading.optimization._internal.objective import (
    BacktestObjective,
    DEFAULT_RISK_SEARCH_SPACE,
    RICH_RISK_SEARCH_SPACE,
)


def _default_params(schema: dict) -> dict:
    """Build default params from an indicator's params_schema."""
    params = {}
    for pname, pschema in schema.items():
        if "default" in pschema:
            params[pname] = pschema["default"]
        elif pschema["type"] == "int":
            params[pname] = pschema["min"]
        elif pschema["type"] == "float":
            params[pname] = pschema["min"]
        elif pschema["type"] == "str":
            params[pname] = pschema.get("choices", [""])[0]
        elif pschema["type"] == "bool":
            params[pname] = True
    return params


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def rich_ohlcv():
    """1000-bar OHLCV with ref_close for vol_scaled_momentum."""
    n = 1000
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
            # ref_close needed by vol_scaled_momentum
            "ref_close": close * (1 + rng.normal(0, 0.01, n)),
        },
        index=idx,
    )


@pytest.fixture
def rich_dataset(rich_ohlcv):
    """BacktestDataset for rich archetype tests."""
    return BacktestDataset(
        exchange="synthetic",
        symbol="SPY",
        base_timeframe="1h",
        ohlcv=rich_ohlcv,
    )


@pytest.fixture
def rich_objective(rich_dataset):
    """BacktestObjective with rich_stock archetype."""
    return BacktestObjective(
        dataset=rich_dataset,
        indicator_names=get_entry_indicators("rich_stock") + ["firestorm_tm"],
        auxiliary_indicators=["firestorm_tm"],
        archetype="rich_stock",
        metric="sharpe",
        risk_search_space={
            "stop__atr_multiple": {"type": "float", "min": 4.0, "max": 10.0, "step": 2.0},
        },
        mode="simple",
    )


# ── Archetype registration ──────────────────────────────────────────

class TestRichArchetypeConfig:
    def test_rich_stock_in_registry(self):
        assert "rich_stock" in ARCHETYPE_INDICATORS

    def test_rich_stock_has_11_entry_indicators(self):
        entry = get_entry_indicators("rich_stock")
        assert len(entry) == 11

    def test_max_excluyente_enforced(self, rich_objective):
        """Excess EXCLUYENTE should be downgraded to OPCIONAL."""
        params = {}
        for i, name in enumerate(get_entry_indicators("rich_stock")):
            params[name] = {"__state": "Excluyente", "__timeframe": "grafico", "dummy": 1}
        # All 11 are EXCLUYENTE — should cap at MAX_EXCLUYENTE (2)
        rich_objective._enforce_max_excluyente(params)
        excl = [n for n, p in params.items() if p["__state"] == "Excluyente"]
        opc = [n for n, p in params.items() if p["__state"] == "Opcional"]
        assert len(excl) == 2
        assert len(opc) == 9

    def test_max_excluyente_no_op_when_under(self, rich_objective):
        """2 EXCLUYENTE should not be modified."""
        params = {
            "rsi": {"__state": "Excluyente"},
            "ssl_channel": {"__state": "Excluyente"},
            "squeeze": {"__state": "Opcional"},
            "adx_filter": {"__state": "Desactivado"},
        }
        rich_objective._enforce_max_excluyente(params)
        assert params["rsi"]["__state"] == "Excluyente"
        assert params["ssl_channel"]["__state"] == "Excluyente"
        assert params["squeeze"]["__state"] == "Opcional"

    def test_trial_respects_max_excluyente(self, rich_objective):
        """Optuna trial should never have >MAX_EXCLUYENTE after constraint."""
        study = optuna.create_study(direction="maximize")
        study.optimize(rich_objective, n_trials=5, show_progress_bar=False)
        for trial in study.trials:
            ind_params = trial.user_attrs.get("indicator_params", {})
            excl = sum(
                1 for p in ind_params.values()
                if isinstance(p, dict) and p.get("__state") == "Excluyente"
            )
            assert excl <= 2, f"Trial {trial.number}: {excl} EXCLUYENTE > 2"

    def test_dynamic_states_flag_activates(self, rich_objective):
        assert rich_objective._dynamic_states is True

    def test_dynamic_states_flag_inactive_for_small_archetypes(self, rich_dataset):
        obj = BacktestObjective(
            dataset=rich_dataset,
            indicator_names=["rsi"],
            archetype="trend_following",
            metric="sharpe",
            risk_search_space={},
            mode="simple",
        )
        assert obj._dynamic_states is False


# ── Dynamic states ───────────────────────────────────────────────────

class TestDynamicStates:
    def test_desactivado_excludes_indicator(self, rich_objective, rich_ohlcv):
        """DESACTIVADO indicator should not appear in entry signals."""
        from suitetrading.indicators.registry import get_indicator

        indicator_params = {}
        for ind_name in get_entry_indicators("rich_stock"):
            indicator = get_indicator(ind_name)
            params = _default_params(indicator.params_schema())
            if ind_name == "rsi":
                params["__state"] = "Desactivado"
            else:
                params["__state"] = "Excluyente"
            params["__timeframe"] = "grafico"
            indicator_params[ind_name] = params

        aux_ind = get_indicator("firestorm_tm")
        indicator_params["firestorm_tm"] = _default_params(aux_ind.params_schema())
        indicator_params["__num_optional_required"] = 1

        signals = rich_objective.build_signals(indicator_params)
        assert hasattr(signals, "entry_long")
        assert len(signals.entry_long) == len(rich_ohlcv)

    def test_opcional_with_num_optional_required(self):
        """OPCIONAL indicators respect num_optional_required in combine_signals."""
        idx = pd.RangeIndex(5)
        signals = {
            "a": pd.Series([True, True, False, True, False], index=idx),
            "b": pd.Series([True, False, False, True, True], index=idx),
            "c": pd.Series([False, True, True, False, False], index=idx),
        }
        states = {
            "a": IndicatorState.EXCLUYENTE,
            "b": IndicatorState.OPCIONAL,
            "c": IndicatorState.OPCIONAL,
        }
        # Need 2 opcionals: bar 0 has b=T,c=F (1 opt) → False; bar 3 has b=T,c=F → False
        result = combine_signals(signals, states, num_optional_required=2)
        # Bar 0: a=T, opts=1 < 2 → False
        assert result.iloc[0] is np.bool_(False)
        # Bar 1: a=T, b=F,c=T → opts=1 < 2 → False
        assert result.iloc[1] is np.bool_(False)

    def test_opcional_with_num_optional_1(self):
        """With num_optional_required=1, a single OPCIONAL suffices."""
        idx = pd.RangeIndex(3)
        signals = {
            "a": pd.Series([True, True, True], index=idx),
            "b": pd.Series([True, False, False], index=idx),
            "c": pd.Series([False, False, True], index=idx),
        }
        states = {
            "a": IndicatorState.EXCLUYENTE,
            "b": IndicatorState.OPCIONAL,
            "c": IndicatorState.OPCIONAL,
        }
        result = combine_signals(signals, states, num_optional_required=1)
        assert result.iloc[0] is np.bool_(True)   # b is True
        assert result.iloc[1] is np.bool_(False)  # neither optional True
        assert result.iloc[2] is np.bool_(True)   # c is True


# ── Per-indicator TF resampling ──────────────────────────────────────

class TestPerIndicatorTF:
    def test_resampling_produces_valid_signal(self, rich_objective, rich_ohlcv):
        """Indicator with __timeframe='1_superior' should produce aligned signal."""
        from suitetrading.indicators.registry import get_indicator

        indicator_params = {}
        for ind_name in get_entry_indicators("rich_stock"):
            indicator = get_indicator(ind_name)
            params = _default_params(indicator.params_schema())
            params["__state"] = "Excluyente"
            params["__timeframe"] = "1_superior" if ind_name == "rsi" else "grafico"
            indicator_params[ind_name] = params

        aux_ind = get_indicator("firestorm_tm")
        indicator_params["firestorm_tm"] = _default_params(aux_ind.params_schema())
        indicator_params["__num_optional_required"] = 1

        signals = rich_objective.build_signals(indicator_params)
        assert len(signals.entry_long) == len(rich_ohlcv)
        assert signals.entry_long.dtype == bool


# ── Optuna integration ───────────────────────────────────────────────

class TestRichOptunaIntegration:
    def test_objective_returns_finite_float(self, rich_objective):
        """Rich archetype objective produces a finite float via Optuna."""
        study = optuna.create_study(direction="maximize")
        study.optimize(rich_objective, n_trials=2, show_progress_bar=False)
        assert study.best_trial.state.name == "COMPLETE"
        assert isinstance(study.best_trial.value, float)
        assert np.isfinite(study.best_trial.value)

    def test_trial_params_contain_state_and_tf(self, rich_objective):
        """Trial params should include __state and __timeframe for entry indicators."""
        study = optuna.create_study(direction="maximize")
        study.optimize(rich_objective, n_trials=1, show_progress_bar=False)
        params = study.best_trial.params
        # At least one entry indicator should have __state suggested
        state_keys = [k for k in params if k.endswith("____state")]
        tf_keys = [k for k in params if k.endswith("____timeframe")]
        assert len(state_keys) >= 1
        assert len(tf_keys) >= 1


# ── Backward compatibility ───────────────────────────────────────────

class TestBackwardCompatibility:
    def test_existing_archetype_unchanged(self, rich_ohlcv):
        """Existing archetypes (< 5 entry) should work without dynamic states."""
        dataset = BacktestDataset(
            exchange="synthetic", symbol="BTCUSDT",
            base_timeframe="1h", ohlcv=rich_ohlcv,
        )
        obj = BacktestObjective(
            dataset=dataset,
            indicator_names=["rsi"],
            archetype="trend_following",
            metric="sharpe",
            risk_search_space={
                "stop__atr_multiple": {"type": "float", "min": 1.0, "max": 4.0, "step": 0.5},
            },
            mode="simple",
        )
        assert obj._dynamic_states is False

        study = optuna.create_study(direction="maximize")
        study.optimize(obj, n_trials=1, show_progress_bar=False)
        params = study.best_trial.params
        # Should NOT have __state or __timeframe keys
        state_keys = [k for k in params if "____state" in k]
        assert len(state_keys) == 0

    def test_existing_archetype_returns_finite(self, rich_ohlcv):
        """Existing archetype still returns a valid metric."""
        dataset = BacktestDataset(
            exchange="synthetic", symbol="BTCUSDT",
            base_timeframe="1h", ohlcv=rich_ohlcv,
        )
        obj = BacktestObjective(
            dataset=dataset,
            indicator_names=["roc"],
            archetype="roc_simple",
            metric="sharpe",
            risk_search_space={
                "stop__atr_multiple": {"type": "float", "min": 4.0, "max": 10.0, "step": 2.0},
            },
            mode="simple",
        )
        study = optuna.create_study(direction="maximize")
        study.optimize(obj, n_trials=1, show_progress_bar=False)
        assert study.best_trial.state.name == "COMPLETE"
        assert np.isfinite(study.best_trial.value)


# ══ Sprint 2: Risk Search Space Expansion ════════════════════════════

class TestRichRiskSearchSpace:
    def test_rich_space_extends_default(self):
        """RICH_RISK_SEARCH_SPACE contains all DEFAULT keys plus trigger/activation."""
        for key in DEFAULT_RISK_SEARCH_SPACE:
            assert key in RICH_RISK_SEARCH_SPACE
        assert "partial_tp__trigger" in RICH_RISK_SEARCH_SPACE
        assert "break_even__activation" in RICH_RISK_SEARCH_SPACE

    def test_rich_objective_uses_expanded_space(self, rich_dataset):
        """Rich archetype auto-selects RICH_RISK_SEARCH_SPACE (no explicit space)."""
        obj = BacktestObjective(
            dataset=rich_dataset,
            indicator_names=get_entry_indicators("rich_stock") + ["firestorm_tm"],
            auxiliary_indicators=["firestorm_tm"],
            archetype="rich_stock",
            metric="sharpe",
            mode="simple",
        )
        assert "partial_tp__trigger" in obj._risk_search_space
        assert "break_even__activation" in obj._risk_search_space

    def test_default_archetype_no_trigger_activation(self, rich_dataset):
        """Non-rich archetype should NOT have trigger/activation in search space."""
        obj = BacktestObjective(
            dataset=rich_dataset,
            indicator_names=["roc"],
            archetype="roc_fullrisk_pyr",
            metric="sharpe",
            mode="simple",
        )
        assert "partial_tp__trigger" not in obj._risk_search_space
        assert "break_even__activation" not in obj._risk_search_space

    def test_rich_trial_includes_trigger_activation(self, rich_dataset):
        """Optuna trial for rich archetype should suggest trigger/activation."""
        obj = BacktestObjective(
            dataset=rich_dataset,
            indicator_names=get_entry_indicators("rich_stock") + ["firestorm_tm"],
            auxiliary_indicators=["firestorm_tm"],
            archetype="rich_stock",
            metric="sharpe",
            mode="simple",
        )
        study = optuna.create_study(direction="maximize")
        study.optimize(obj, n_trials=1, show_progress_bar=False)
        params = study.best_trial.params
        assert "partial_tp__trigger" in params
        assert params["partial_tp__trigger"] in ("r_multiple", "signal")
        assert "break_even__activation" in params
        assert params["break_even__activation"] in ("after_tp1", "r_multiple")

    def test_explicit_space_overrides_rich(self, rich_dataset):
        """Explicit risk_search_space should override auto-selection."""
        custom = {"stop__atr_multiple": {"type": "float", "min": 5.0, "max": 10.0, "step": 1.0}}
        obj = BacktestObjective(
            dataset=rich_dataset,
            indicator_names=get_entry_indicators("rich_stock") + ["firestorm_tm"],
            auxiliary_indicators=["firestorm_tm"],
            archetype="rich_stock",
            metric="sharpe",
            risk_search_space=custom,
            mode="simple",
        )
        # Should use custom, not RICH
        assert "partial_tp__trigger" not in obj._risk_search_space


# ══ Sprint 3: Discovery pipeline meta-param handling ═════════════════

class TestExtractCandidateParams:
    def test_num_optional_required_in_indicator_params(self):
        """num_optional_required should end up in indicator_params, not risk_overrides."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from run_discovery import extract_candidate_params

        flat = {
            "rsi__period": 14,
            "rsi____state": "Excluyente",
            "rsi____timeframe": "grafico",
            "ssl_channel__length": 12,
            "ssl_channel____state": "Opcional",
            "ssl_channel____timeframe": "1_superior",
            "num_optional_required": 2,
            "stop__atr_multiple": 8.0,
            "partial_tp__trigger": "signal",
        }
        trials = [{"params": flat, "trial_number": 0, "value": 1.5}]
        candidates = extract_candidate_params(trials, ["rsi", "ssl_channel"])

        c = candidates[0]
        # num_optional_required injected as meta-key
        assert c["indicator_params"]["__num_optional_required"] == 2
        # Meta-params inside indicator dicts
        assert c["indicator_params"]["rsi"]["__state"] == "Excluyente"
        assert c["indicator_params"]["ssl_channel"]["__timeframe"] == "1_superior"
        # Risk overrides are clean
        assert "num_optional_required" not in c["risk_overrides"]
        assert c["risk_overrides"]["stop__atr_multiple"] == 8.0
        assert c["risk_overrides"]["partial_tp__trigger"] == "signal"

    def test_legacy_params_unchanged(self):
        """Legacy params without meta-params should work as before."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
        from run_discovery import extract_candidate_params

        flat = {
            "roc__period": 12,
            "stop__atr_multiple": 6.0,
        }
        trials = [{"params": flat, "trial_number": 0, "value": 1.0}]
        candidates = extract_candidate_params(trials, ["roc"])

        c = candidates[0]
        assert c["indicator_params"]["roc"]["period"] == 12
        assert c["risk_overrides"]["stop__atr_multiple"] == 6.0
        assert "__num_optional_required" not in c["indicator_params"]
