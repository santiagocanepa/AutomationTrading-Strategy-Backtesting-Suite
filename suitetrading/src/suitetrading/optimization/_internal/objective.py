"""Objective function — bridge between Optuna trials and BacktestEngine.

Translates ``trial.suggest_*()`` calls into indicator params + risk
overrides, computes signals, runs the backtest, and returns the target
metric for Optuna to optimise.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import optuna
import pandas as pd
from loguru import logger

from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.indicators.base import IndicatorState
from suitetrading.indicators.registry import INDICATOR_REGISTRY, get_indicator
from suitetrading.indicators.signal_combiner import combine_signals
from suitetrading.config.archetypes import (
    get_combination_mode,
    get_entry_indicators,
    get_exit_indicators,
    get_htf_filter,
    get_trailing_indicators,
)
from suitetrading.indicators.mtf import align_to_base, resample_ohlcv, resolve_timeframe
from suitetrading.risk.archetypes import get_archetype
from suitetrading.risk.contracts import RiskConfig


# ── Exit signal parameter inversion ──────────────────────────────────

# Maps indicator name → (param_to_flip, {original_value: inverted_value}).
# Custom indicators use "direction"; standard indicators use "mode".
_EXIT_INVERSION: dict[str, tuple[str, dict[str, str]]] = {
    "ash":                  ("signal_mode", {"bullish": "bearish", "bearish": "bullish"}),
    "ssl_channel":          ("direction", {"long": "short", "short": "long"}),
    "firestorm":            ("direction", {"long": "short", "short": "long"}),
    "wavetrend_reversal":   ("direction", {"long": "short", "short": "long"}),
    "wavetrend_divergence": ("direction", {"long": "short", "short": "long"}),
    "rsi":                  ("mode", {"oversold": "overbought", "overbought": "oversold"}),
    "ema":                  ("mode", {"above": "below", "below": "above"}),
    "macd":                 ("mode", {"bullish": "bearish", "bearish": "bullish"}),
    "bollinger_bands":      ("mode", {"lower": "upper", "upper": "lower"}),
    "vwap":                 ("mode", {"above": "below", "below": "above"}),
    # Momentum
    "roc":                  ("mode", {"bullish": "bearish", "bearish": "bullish"}),
    "donchian":             ("mode", {"upper": "lower", "lower": "upper"}),
    "adx_filter":           ("mode", {"strong": "weak", "weak": "strong"}),
    "ma_crossover":         ("mode", {"bullish": "bearish", "bearish": "bullish"}),
    # Phase 3
    "squeeze":              ("mode", {"bullish": "bearish", "bearish": "bullish"}),
    "stoch_rsi":            ("mode", {"oversold": "overbought", "overbought": "oversold"}),
    "ichimoku":             ("mode", {"bullish": "bearish", "bearish": "bullish"}),
    "obv":                  ("mode", {"bullish": "bearish", "bearish": "bullish"}),
    # Regime & anomaly
    "volatility_regime":    ("mode", {"trending": "ranging", "ranging": "trending"}),
    "volume_spike":         ("mode", {"bullish": "bearish", "bearish": "bullish"}),
    "momentum_divergence":  ("mode", {"bullish": "bearish", "bearish": "bullish"}),
    # Futures/derivatives
    "funding_rate":         ("mode", {"reversal_long": "reversal_short", "reversal_short": "reversal_long"}),
    "oi_divergence":        ("mode", {"bullish": "bearish", "bearish": "bullish"}),
    "long_short_ratio":     ("mode", {"contrarian_long": "contrarian_short", "contrarian_short": "contrarian_long"}),
}


_META_PARAMS = frozenset({"__state", "__timeframe"})


def _strip_meta(params: dict[str, Any]) -> dict[str, Any]:
    """Remove meta-params (__state, __timeframe) from indicator params."""
    return {k: v for k, v in params.items() if k not in _META_PARAMS}


def _make_exit_params(
    ind_name: str,
    params: dict[str, Any],
) -> dict[str, Any] | None:
    """Invert direction/mode params to produce exit-signal parameters.

    Returns *None* for non-directional indicators (e.g. ATR) that
    cannot produce a meaningful exit signal.
    """
    inversion = _EXIT_INVERSION.get(ind_name)
    if inversion is None:
        return None
    param_key, value_map = inversion
    exit_params = dict(params)
    current = str(exit_params.get(param_key, next(iter(value_map))))
    inverted = value_map.get(current)
    if inverted is None:
        return None
    exit_params[param_key] = inverted
    return exit_params


# ── Schema → trial.suggest mapping ────────────────────────────────────

def _suggest_param(
    trial: optuna.Trial,
    name: str,
    schema: dict[str, Any],
    step_factor: int = 1,
) -> int | float | str | bool:
    """Map a single param schema entry to an Optuna suggest call.

    Parameters
    ----------
    step_factor
        Multiplier for step sizes (coarse-to-fine search).
        ``1`` = original resolution; ``4`` = 4x coarser steps.
    """
    ptype = schema["type"]
    if ptype == "int":
        lo, hi = schema["min"], schema["max"]
        if step_factor > 1:
            step = max(1, (hi - lo) // max(1, (hi - lo) // step_factor))
            return trial.suggest_int(name, lo, hi, step=step)
        return trial.suggest_int(name, lo, hi)
    if ptype == "float":
        step = schema.get("step")
        if step and step_factor > 1:
            step = step * step_factor
            # Ensure at least 2 values in range
            lo, hi = schema["min"], schema["max"]
            if step > (hi - lo):
                step = hi - lo
        return trial.suggest_float(name, schema["min"], schema["max"], step=step)
    if ptype == "str":
        choices = schema.get("choices")
        if choices:
            return trial.suggest_categorical(name, choices)
        return schema.get("default", "")
    if ptype == "bool":
        return trial.suggest_categorical(name, [True, False])
    raise ValueError(f"Unsupported param type {ptype!r} for {name!r}")


# ── Risk overrides search space ───────────────────────────────────────

# Narrowed from 764K-trial feature importance analysis (2026-03-18).
# Original space: ~80 trillion combinations.
# Narrowed space: ~290 million combinations (~275x reduction).
DEFAULT_RISK_SEARCH_SPACE: dict[str, dict[str, Any]] = {
    # ── Stop ── (top1% median: 12, range 4-20)
    "stop__atr_multiple": {"type": "float", "min": 4.0, "max": 20.0, "step": 1.0},
    # ── Sizing ── (top1%: 3-25%, median 14)
    "sizing__risk_pct": {"type": "float", "min": 3.0, "max": 25.0, "step": 1.0},
    # ── Partial TP ── (top1%: r_mult 0.5-1.5, close 10-45%)
    "partial_tp__r_multiple": {"type": "float", "min": 0.5, "max": 1.5, "step": 0.25},
    "partial_tp__close_pct": {"type": "float", "min": 10.0, "max": 45.0, "step": 5.0},
    # ── Break-even ── (low impact, keep narrow)
    "break_even__buffer": {"type": "float", "min": 1.003, "max": 1.009, "step": 0.001},
    # ── Pyramid ── (top1%: 1-4 adds, 8-40 bars)
    "pyramid__max_adds": {"type": "int", "min": 1, "max": 4},
    "pyramid__block_bars": {"type": "int", "min": 8, "max": 40},
    "pyramid__threshold_factor": {"type": "float", "min": 1.005, "max": 1.03, "step": 0.005},
    # ── Time exit ── (low impact, keep but narrow)
    "time_exit__max_bars": {"type": "int", "min": 50, "max": 400},
}

# Lean variant: only the 3 most impactful risk params.
# Reduces search space from ~290M to ~324 combinations.
# With fewer effective dimensions, Optuna needs fewer trials (100-200),
# which lowers E[max(SR)] in the DSR test, making it feasible to pass.
#
# Full range (DEFAULT_RISK_SEARCH_SPACE) is preserved above for reference.
# The remaining params (break_even, pyramid details, time_exit) use
# archetype defaults without optimization.
LEAN_RISK_SEARCH_SPACE: dict[str, dict[str, Any]] = {
    "stop__atr_multiple": {"type": "float", "min": 4.0, "max": 20.0, "step": 2.0},
    "sizing__risk_pct": {"type": "float", "min": 3.0, "max": 25.0, "step": 2.0},
    "partial_tp__r_multiple": {"type": "float", "min": 0.5, "max": 1.5, "step": 0.5},
}

# Rich variant: DEFAULT + TP trigger mode + BE activation mode.
# Adds 2 categorical dimensions to let Optuna explore how TP1 fires
# (r_multiple vs signal) and when break-even activates (after_tp1 vs
# r_multiple).  These modes are already supported by the FSM.
RICH_RISK_SEARCH_SPACE: dict[str, dict[str, Any]] = {
    **DEFAULT_RISK_SEARCH_SPACE,
    # Override ranges that collapsed to minimums in v4 exploration:
    # stop collapsed to 4.0 → expand down; TP collapsed to 0.5 → expand down
    "stop__atr_multiple": {"type": "float", "min": 2.0, "max": 12.0, "step": 0.5},
    "partial_tp__r_multiple": {"type": "float", "min": 0.25, "max": 1.5, "step": 0.125},
    "partial_tp__trigger": {"type": "str", "choices": ["r_multiple", "signal"]},
    "break_even__activation": {"type": "str", "choices": ["after_tp1", "r_multiple"]},
}

# V8 refined: narrowed from v7 analysis of 229 finalists + 240K trials.
#
# Evidence-based changes:
#   stop__atr_multiple: 100% of top Q4 at 2.0 → explore [0.8, 3.0]
#   partial_tp__r_multiple: 100% at 0.25 → explore [0.10, 0.50]
#   partial_tp__close_pct: 98% at 10 → explore [5, 20]
#   break_even__buffer: collapsed to max 1.007 → explore [1.005, 1.015]
#   pyramid__max_adds: Q4 prefers 1, Q1 prefers 4 → fix at [1, 2]
#   pyramid__block_bars: Q4 slightly higher → [20, 40]
#   sizing__risk_pct: no discrimination → keep but narrow [2, 10]
#   partial_tp__trigger: 99.7% r_multiple → fix as r_multiple (remove)
#   break_even__activation: 73% after_tp1 → keep both
#
# Total reduction: ~95% fewer risk combinations vs RICH_RISK_SEARCH_SPACE
V8_RISK_SEARCH_SPACE: dict[str, dict[str, Any]] = {
    "stop__atr_multiple": {"type": "float", "min": 0.8, "max": 3.0, "step": 0.2},
    "sizing__risk_pct": {"type": "float", "min": 2.0, "max": 10.0, "step": 2.0},
    "partial_tp__r_multiple": {"type": "float", "min": 0.10, "max": 0.50, "step": 0.05},
    "partial_tp__close_pct": {"type": "float", "min": 5.0, "max": 20.0, "step": 5.0},
    "break_even__buffer": {"type": "float", "min": 1.005, "max": 1.015, "step": 0.002},
    "break_even__activation": {"type": "str", "choices": ["after_tp1", "r_multiple"]},
    "pyramid__max_adds": {"type": "int", "min": 1, "max": 2},
    "pyramid__block_bars": {"type": "int", "min": 20, "max": 40},
}

# V9 exhaustive: focused on the 3 most critical risk dimensions.
# No pyramiding, no time exit, no sizing optimization.
# Break-even hardcoded to after_tp1 (best from v7/v8 analysis).
#
# Philosophy: position management >> entry signals.
# These 3 params define how a trade is managed once open:
#   1. Stop distance (ATR multiple) — how much room to give
#   2. TP distance (R-multiple of stop) — when to take partial profit
#   3. Close % — how much to close at TP1 (rest runs with trailing)
#
# Total: 8 × 10 × 6 = 480 risk combinations (exhaustively coverable)
EXHAUSTIVE_RISK_SPACE: dict[str, dict[str, Any]] = {
    "stop__atr_multiple": {"type": "float", "min": 0.5, "max": 4.0, "step": 0.5},
    "partial_tp__r_multiple": {"type": "float", "min": 0.25, "max": 2.5, "step": 0.25},
    "partial_tp__close_pct": {"type": "float", "min": 10.0, "max": 60.0, "step": 10.0},
}


# ── Maturity-based filtering ─────────────────────────────────────────

MATURITY_LEVELS = ("active", "partial", "experimental")


def filter_search_space(
    space: dict[str, dict[str, Any]],
    maturity: dict[str, str],
    *,
    level: str = "active",
) -> dict[str, dict[str, Any]]:
    """Return only dimensions at or above the requested maturity level.

    Parameters
    ----------
    space
        Search space mapping dimension name → schema.
    maturity
        Mapping dimension name → ``"active"`` | ``"partial"`` | ``"experimental"``.
    level
        Minimum maturity required.  ``"active"`` includes only active;
        ``"partial"`` includes active + partial.
    """
    if level == "active":
        allowed = {"active"}
    elif level == "partial":
        allowed = {"active", "partial"}
    else:
        allowed = set(MATURITY_LEVELS)
    return {k: v for k, v in space.items() if maturity.get(k, "experimental") in allowed}


def _suggest_risk_overrides(
    trial: optuna.Trial,
    risk_search_space: dict[str, dict[str, Any]],
    step_factor: int = 1,
) -> dict[str, Any]:
    """Suggest risk overrides and convert flat keys to nested dict."""
    overrides: dict[str, Any] = {}
    for flat_key, schema in risk_search_space.items():
        value = _suggest_param(trial, flat_key, schema, step_factor=step_factor)
        parts = flat_key.split("__")
        target = overrides
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    return overrides


# ── Smart num_optional_required ──────────────────────────────────────

def _smart_optional_range(excl_count: int, opc_count: int) -> tuple[int, int]:
    """Compute sensible (min, max) for num_optional_required.

    Balances total filtering power: excl + optional_required ≈ 3-4.
    More excluyentes → fewer opcionales required.
    """
    if opc_count == 0:
        return (0, 0)
    if excl_count >= 2:
        # 2 hard filters already — need only 1-2 optional for confluence
        return (1, min(2, opc_count))
    if excl_count == 1:
        # 1 hard filter — need 1-3 optional
        return (1, min(3, opc_count))
    # excl_count == 0: no hard filter, need more optionals
    return (min(2, opc_count), min(4, opc_count))


# ── Objective ─────────────────────────────────────────────────────────

class BacktestObjective:
    """Callable that Optuna invokes for each trial.

    Parameters
    ----------
    dataset
        Pre-loaded ``BacktestDataset`` (shared across all trials).
    indicator_names
        Which indicators to include in the search space.
    archetype
        Risk management archetype name.
    direction
        ``"long"`` or ``"short"``.
    metric
        Target metric to optimise (``"sharpe"``, ``"sortino"``, etc.).
    risk_search_space
        Flat key-value dict defining risk param ranges.
        Keys use ``__`` for nesting (e.g. ``"stop__atr_multiple"``).
    mode
        Backtesting mode (``"auto"``/``"simple"``/``"fsm"``).
    """

    def __init__(
        self,
        *,
        dataset: BacktestDataset,
        indicator_names: list[str] | None = None,
        auxiliary_indicators: list[str] | None = None,
        archetype: str = "trend_following",
        direction: str = "long",
        metric: str = "sharpe",
        risk_search_space: dict[str, dict[str, Any]] | None = None,
        mode: str = "auto",
        commission_pct: float | None = None,
        multi_objective: bool = False,
        step_factor: int = 1,
    ) -> None:
        self._dataset = dataset
        self._indicator_names = indicator_names or list(INDICATOR_REGISTRY.keys())
        self._auxiliary_indicators = auxiliary_indicators or []
        self._archetype = archetype
        self._multi_objective = multi_objective
        self._step_factor = step_factor
        self._entry_indicator_names = set(get_entry_indicators(archetype))
        # Dynamic states: only for rich archetypes with 5+ entry indicators.
        # Enables per-indicator state/TF suggestion via Optuna.
        self._dynamic_states = len(self._entry_indicator_names) >= 5
        self._direction = direction
        self._metric = metric
        self._mode = mode
        self._commission_pct = commission_pct
        self._engine = BacktestEngine()
        self._metrics_engine = MetricsEngine()

        # Build effective risk search space: drop dead parameters based
        # on archetype config (stop model, TP1 enabled, etc.)
        # Rich archetypes get expanded space with TP trigger + BE activation modes.
        if risk_search_space is not None:
            base_space = risk_search_space
        elif self._dynamic_states:
            base_space = dict(RICH_RISK_SEARCH_SPACE)
        else:
            base_space = dict(DEFAULT_RISK_SEARCH_SPACE)
        archetype_cfg = get_archetype(archetype).build_config()
        if archetype_cfg.stop.model == "firestorm_tm":
            base_space.pop("stop__atr_multiple", None)
        if not archetype_cfg.partial_tp.enabled:
            base_space.pop("partial_tp__r_multiple", None)
            base_space.pop("partial_tp__close_pct", None)
            base_space.pop("partial_tp__trigger", None)
        if not archetype_cfg.break_even.enabled:
            base_space.pop("break_even__buffer", None)
            base_space.pop("break_even__r_multiple", None)
            base_space.pop("break_even__activation", None)
        if not archetype_cfg.pyramid.enabled:
            base_space.pop("pyramid__max_adds", None)
            base_space.pop("pyramid__block_bars", None)
            base_space.pop("pyramid__threshold_factor", None)
        if not archetype_cfg.time_exit.enabled:
            base_space.pop("time_exit__max_bars", None)
        self._risk_search_space = base_space

        # Detect exhaustive mode: no pyramid keys → force pyramid disabled
        has_pyramid_keys = any(k.startswith("pyramid__") for k in base_space)
        self._force_no_pyramid = not has_pyramid_keys

    # Minimum trades required; configs below this get a harsh penalty
    # so Optuna learns to avoid degenerate low-trade solutions.
    # 300 ensures statistical significance across any TF/period.
    MIN_TRADES: int = 300
    LOW_TRADE_PENALTY: float = -10.0

    # Pine Script pattern: max 2 hard requirements (EXCLUYENTE),
    # rest as OPCIONAL with smart num_optional_required.
    MAX_EXCLUYENTE: int = 2

    def __call__(self, trial: optuna.Trial) -> float:
        """Suggest params, run backtest, return metric value."""
        indicator_params = self._suggest_indicator_params(trial)
        # Risk params use their defined steps directly — step_factor is
        # regularization for indicator params only (prevents overfit of
        # continuous indicator periods/thresholds).
        risk_overrides = _suggest_risk_overrides(
            trial, self._risk_search_space, step_factor=1,
        )

        # Dynamic archetypes: enforce max EXCLUYENTE, then suggest num_optional_required.
        if self._dynamic_states:
            self._enforce_max_excluyente(indicator_params)

            excl_count = sum(
                1 for p in indicator_params.values()
                if isinstance(p, dict) and p.get("__state") == "Excluyente"
            )
            opcional_count = sum(
                1 for p in indicator_params.values()
                if isinstance(p, dict) and p.get("__state") == "Opcional"
            )
            min_opt, max_opt = _smart_optional_range(excl_count, opcional_count)
            if max_opt > 0:
                num_opt = trial.suggest_int("num_optional_required", min_opt, max_opt)
            else:
                num_opt = 1
            indicator_params["__num_optional_required"] = num_opt

        signals = self.build_signals(indicator_params)
        risk_config = self.build_risk_config(risk_overrides)

        result = self._engine.run(
            dataset=self._dataset,
            signals=signals,
            risk_config=risk_config,
            mode=self._mode,
            direction=self._direction,
        )

        metrics = self._metrics_engine.compute(
            equity_curve=result["equity_curve"],
            trades=result.get("trades"),
            initial_capital=risk_config.initial_capital,
            context={"timeframe": self._dataset.base_timeframe},
        )

        # Store for later retrieval
        trial.set_user_attr("run_id", result.get("run_id", ""))
        trial.set_user_attr("metrics", metrics)
        trial.set_user_attr("indicator_params", indicator_params)
        trial.set_user_attr("risk_overrides", risk_overrides)

        total_trades = int(metrics.get("total_trades", 0))
        value = float(metrics.get(self._metric, 0.0))
        if np.isnan(value) or np.isinf(value):
            value = 0.0

        # Multi-objective: return (metric, trades) — NSGA-II optimizes both
        if self._multi_objective:
            return value, float(total_trades)

        # Single-objective: penalize low trade count
        if total_trades < self.MIN_TRADES:
            return self.LOW_TRADE_PENALTY
        return value

    def build_signals(self, indicator_params: dict[str, dict[str, Any]]) -> StrategySignals:
        """Compute entry, exit and trailing signals from indicator params.

        - Entry signals use archetype entry indicators combined per mode.
        - Entry short signals use inverted entry indicators.
        - Exit signals use archetype-designated exit indicators (inverted
          direction for the respective side).
        - Trailing signals use archetype-designated trailing indicators.
        - Auxiliary indicator bands (e.g. firestorm_tm) are passed via
          ``indicators_payload`` for the runner to use as dynamic stops.
        """
        auxiliary = set(self._auxiliary_indicators)
        ohlcv = self._dataset.ohlcv
        idx = ohlcv.index
        base_tf = self._dataset.base_timeframe
        mode, threshold = get_combination_mode(self._archetype)

        # ── Entry signals ────────────────────────────────────────────
        entry_signals: dict[str, pd.Series] = {}
        entry_short_signals: dict[str, pd.Series] = {}
        entry_states: dict[str, IndicatorState] = {}

        # Extract num_optional_required for dynamic archetypes
        # Use .get() not .pop() — caller's dict must not be mutated (WFO reuses it across folds)
        num_optional_required = indicator_params.get("__num_optional_required", 1)

        for ind_name, params in indicator_params.items():
            if ind_name.startswith("__") or ind_name in auxiliary:
                continue

            # Extract meta-params (not passed to compute)
            params = dict(params)  # copy to avoid mutating
            state_str = params.pop("__state", None)
            tf_selection = params.pop("__timeframe", None)

            # Dynamic states: skip DESACTIVADO indicators
            if state_str == "Desactivado":
                continue

            # Resolve dynamic state
            if state_str is not None:
                entry_states[ind_name] = IndicatorState(state_str)
            else:
                entry_states[ind_name] = IndicatorState.EXCLUYENTE

            # Per-indicator TF resampling
            if tf_selection and tf_selection != "grafico":
                pine_tf = self._dataset.base_timeframe
                try:
                    from suitetrading.data.timeframes import tf_to_pine
                    pine_tf = tf_to_pine(base_tf)
                except (ImportError, ValueError):
                    pass
                target_tf = resolve_timeframe(pine_tf, tf_selection.replace("_", " "))
                try:
                    htf_ohlcv = resample_ohlcv(ohlcv, target_tf, base_tf=base_tf)
                    indicator = get_indicator(ind_name)
                    entry_sig = indicator.compute(htf_ohlcv, **params)
                    entry_signals[ind_name] = align_to_base(entry_sig, idx).fillna(False)
                    inv_params = _make_exit_params(ind_name, params)
                    if inv_params is not None:
                        inv_sig = indicator.compute(htf_ohlcv, **inv_params)
                        entry_short_signals[ind_name] = align_to_base(inv_sig, idx).fillna(False)
                except Exception:
                    logger.debug("HTF resampling failed for {}, falling back to base TF", ind_name)
                    indicator = get_indicator(ind_name)
                    entry_signals[ind_name] = indicator.compute(ohlcv, **params)
                    inv_params = _make_exit_params(ind_name, params)
                    if inv_params is not None:
                        entry_short_signals[ind_name] = indicator.compute(ohlcv, **inv_params)
            else:
                indicator = get_indicator(ind_name)
                entry_signals[ind_name] = indicator.compute(ohlcv, **params)
                inv_params = _make_exit_params(ind_name, params)
                if inv_params is not None:
                    entry_short_signals[ind_name] = indicator.compute(ohlcv, **inv_params)

        if not entry_signals:
            entry_long = pd.Series(False, index=idx)
            entry_short = pd.Series(False, index=idx)
        else:
            entry_long = combine_signals(
                entry_signals, entry_states,
                num_optional_required=num_optional_required,
                combination_mode=mode, majority_threshold=threshold,
            )
            if entry_short_signals:
                entry_short = combine_signals(
                    entry_short_signals, entry_states,
                    num_optional_required=num_optional_required,
                    combination_mode=mode, majority_threshold=threshold,
                )
            else:
                entry_short = pd.Series(False, index=idx)

        # ── Exit signals (archetype-designated indicators) ───────────
        exit_indicator_names = get_exit_indicators(self._archetype)
        exit_long_sigs: dict[str, pd.Series] = {}
        exit_short_sigs: dict[str, pd.Series] = {}
        exit_states: dict[str, IndicatorState] = {}

        for ind_name in exit_indicator_names:
            params = _strip_meta(indicator_params.get(ind_name, {}))
            indicator = get_indicator(ind_name)
            # Exit long = bearish signal (inverted direction)
            inv_params = _make_exit_params(ind_name, params)
            if inv_params is not None:
                exit_long_sigs[ind_name] = indicator.compute(ohlcv, **inv_params)
                exit_states[ind_name] = IndicatorState.EXCLUYENTE
            # Exit short = bullish signal (normal direction)
            exit_short_sigs[ind_name] = indicator.compute(ohlcv, **params)

        exit_long = (
            combine_signals(exit_long_sigs, exit_states, combination_mode=mode, majority_threshold=threshold)
            if exit_long_sigs
            else pd.Series(False, index=idx)
        )
        exit_short = (
            combine_signals(exit_short_sigs, exit_states, combination_mode=mode, majority_threshold=threshold)
            if exit_short_sigs
            else pd.Series(False, index=idx)
        )

        # ── Trailing signals (archetype-designated indicators) ───────
        trailing_indicator_names = get_trailing_indicators(self._archetype)
        trail_long_sigs: dict[str, pd.Series] = {}
        trail_short_sigs: dict[str, pd.Series] = {}
        trail_states: dict[str, IndicatorState] = {}

        for ind_name in trailing_indicator_names:
            params = _strip_meta(indicator_params.get(ind_name, {}))
            indicator = get_indicator(ind_name)
            # Trailing long: bearish cross (direction="long" for SSLChannelLow)
            trail_long_sigs[ind_name] = indicator.compute(ohlcv, direction="long", **params)
            trail_states[ind_name] = IndicatorState.EXCLUYENTE
            # Trailing short: bullish cross
            trail_short_sigs[ind_name] = indicator.compute(ohlcv, direction="short", **params)

        trailing_long = (
            combine_signals(trail_long_sigs, trail_states, combination_mode=mode, majority_threshold=threshold)
            if trail_long_sigs
            else exit_long  # Fallback to exit signal
        )
        trailing_short = (
            combine_signals(trail_short_sigs, trail_states, combination_mode=mode, majority_threshold=threshold)
            if trail_short_sigs
            else exit_short
        )

        # ── Auxiliary payload (e.g. firestorm_tm bands for stops) ────
        indicators_payload: dict[str, pd.Series] = {}
        for ind_name in self._auxiliary_indicators:
            if ind_name in indicator_params:
                indicator = get_indicator(ind_name)
                params = indicator_params[ind_name]
                # Store both up/dn bands for firestorm_tm
                if ind_name == "firestorm_tm":
                    from suitetrading.indicators.custom.firestorm import firestorm as _firestorm_fn
                    ftm_result = _firestorm_fn(
                        ohlcv["open"], ohlcv["high"], ohlcv["low"], ohlcv["close"],
                        period=params.get("period", 9),
                        multiplier=params.get("multiplier", 1.8),
                    )
                    indicators_payload["firestorm_tm_up"] = ftm_result["up"]
                    indicators_payload["firestorm_tm_dn"] = ftm_result["dn"]

        # ── HTF filter (higher-timeframe trend confirmation) ────
        htf_ind_name, htf_tf = get_htf_filter(self._archetype)
        if htf_ind_name and htf_tf and hasattr(self._dataset, 'ohlcv'):
            try:
                htf_ohlcv = resample_ohlcv(ohlcv, htf_tf, base_tf=self._dataset.base_timeframe)
                htf_indicator = get_indicator(htf_ind_name)
                htf_params = indicator_params.get(htf_ind_name, {})
                htf_bullish = htf_indicator.compute(htf_ohlcv, **htf_params)
                htf_bearish = ~htf_bullish
                # Align to base TF index
                htf_bull_aligned = align_to_base(htf_bullish, idx).fillna(False)
                htf_bear_aligned = align_to_base(htf_bearish, idx).fillna(False)
                # Apply: long only when HTF bullish, short only when HTF bearish
                entry_long = entry_long & htf_bull_aligned
                entry_short = entry_short & htf_bear_aligned
            except Exception:
                pass  # If HTF computation fails, proceed without filter

        return StrategySignals(
            entry_long=entry_long,
            entry_short=entry_short,
            exit_long=exit_long,
            exit_short=exit_short,
            trailing_long=trailing_long,
            trailing_short=trailing_short,
            indicators_payload=indicators_payload,
        )

    def build_risk_config(self, risk_overrides: dict[str, Any]) -> RiskConfig:
        """Build a RiskConfig from archetype + overrides."""
        if self._commission_pct is not None:
            risk_overrides = {**risk_overrides, "commission_pct": self._commission_pct}
        if self._force_no_pyramid:
            risk_overrides.setdefault("pyramid", {})
            risk_overrides["pyramid"]["enabled"] = False
            risk_overrides["pyramid"]["max_adds"] = 0
        return get_archetype(self._archetype).build_config(**risk_overrides)

    def _enforce_max_excluyente(self, indicator_params: dict[str, dict[str, Any]]) -> None:
        """Cap EXCLUYENTE count at MAX_EXCLUYENTE, downgrade excess to OPCIONAL.

        Replicates the Pine Script pattern: 2-3 hard requirements max,
        rest as flexible optionals.  Modifies params in-place.
        """
        excl_names = [
            name for name, p in indicator_params.items()
            if isinstance(p, dict) and p.get("__state") == "Excluyente"
        ]
        if len(excl_names) <= self.MAX_EXCLUYENTE:
            return
        # Downgrade excess to OPCIONAL (keep first N by iteration order)
        for name in excl_names[self.MAX_EXCLUYENTE:]:
            indicator_params[name]["__state"] = "Opcional"

    def run_single(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run a backtest with explicit params (no Optuna trial needed).

        Parameters
        ----------
        params
            Flat dict as returned by ``trial.params`` (e.g.
            ``{"ssl_channel__length": 12, "stop__atr_multiple": 2.0}``).

        Returns
        -------
        Dict with ``equity_curve``, ``metrics``, and ``trades``.
        """
        indicator_params, risk_overrides = self._split_params(params)
        signals = self.build_signals(indicator_params)
        risk_config = self.build_risk_config(risk_overrides)

        result = self._engine.run(
            dataset=self._dataset,
            signals=signals,
            risk_config=risk_config,
            mode=self._mode,
            direction=self._direction,
        )

        metrics = self._metrics_engine.compute(
            equity_curve=result["equity_curve"],
            trades=result.get("trades"),
            initial_capital=risk_config.initial_capital,
            context={"timeframe": self._dataset.base_timeframe},
        )

        return {
            "equity_curve": result["equity_curve"],
            "metrics": metrics,
            "trades": result.get("trades"),
        }

    def _split_params(
        self, flat_params: dict[str, Any],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Split flat Optuna params into indicator params and risk overrides.

        Indicator params have keys like ``"ssl_channel__length"`` where
        the prefix matches a known indicator name.  Everything else goes
        to risk overrides.

        Meta-params (``__state``, ``__timeframe``) use double-underscore
        after the indicator name (e.g. ``"rsi____state"``).  The global
        ``num_optional_required`` is injected as a special key.
        """
        indicator_params: dict[str, dict[str, Any]] = {}
        risk_overrides: dict[str, Any] = {}
        indicator_set = set(self._indicator_names)

        num_optional_required = flat_params.get("num_optional_required", 1)

        for key, value in flat_params.items():
            if key == "num_optional_required":
                continue
            parts = key.split("__", 1)
            if len(parts) == 2 and parts[0] in indicator_set:
                indicator_params.setdefault(parts[0], {})[parts[1]] = value
            else:
                risk_overrides[key] = value

        if self._dynamic_states:
            indicator_params["__num_optional_required"] = num_optional_required

        return indicator_params, risk_overrides

    def _suggest_indicator_params(
        self,
        trial: optuna.Trial,
    ) -> dict[str, dict[str, Any]]:
        """Suggest parameters for each active indicator.

        When ``_dynamic_states`` is active, also suggests ``__state``
        (Excluyente/Opcional/Desactivado) and ``__timeframe``
        (grafico/1_superior/2_superiores) for each entry indicator.
        These meta-params are stored alongside regular params but
        consumed by ``build_signals`` — not passed to ``compute()``.
        """
        result: dict[str, dict[str, Any]] = {}
        for ind_name in self._indicator_names:
            indicator = get_indicator(ind_name)
            schema = indicator.params_schema()
            params: dict[str, Any] = {}

            # Dynamic state/TF for entry indicators in rich archetypes
            is_entry = ind_name in self._entry_indicator_names
            if self._dynamic_states and is_entry:
                params["__state"] = trial.suggest_categorical(
                    f"{ind_name}____state",
                    ["Excluyente", "Opcional", "Desactivado"],
                )
                params["__timeframe"] = trial.suggest_categorical(
                    f"{ind_name}____timeframe",
                    ["grafico", "1_superior", "2_superiores"],
                )

            for param_name, param_schema in schema.items():
                full_name = f"{ind_name}__{param_name}"
                params[param_name] = _suggest_param(
                    trial, full_name, param_schema, step_factor=self._step_factor,
                )
            result[ind_name] = params
        return result
