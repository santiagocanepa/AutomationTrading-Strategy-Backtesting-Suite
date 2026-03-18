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
    get_exit_indicators,
    get_htf_filter,
    get_trailing_indicators,
)
from suitetrading.optimization._internal.schemas import ObjectiveResult
from suitetrading.risk.archetypes import get_archetype
from suitetrading.risk.contracts import RiskConfig


# ── Exit signal parameter inversion ──────────────────────────────────

# Maps indicator name → (param_to_flip, {original_value: inverted_value}).
# Custom indicators use "direction"; standard indicators use "mode".
_EXIT_INVERSION: dict[str, tuple[str, dict[str, str]]] = {
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
}


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
) -> int | float | str | bool:
    """Map a single param schema entry to an Optuna suggest call."""
    ptype = schema["type"]
    if ptype == "int":
        return trial.suggest_int(name, schema["min"], schema["max"])
    if ptype == "float":
        step = schema.get("step")
        return trial.suggest_float(name, schema["min"], schema["max"], step=step)
    if ptype == "str":
        return trial.suggest_categorical(name, schema["choices"])
    if ptype == "bool":
        return trial.suggest_categorical(name, [True, False])
    raise ValueError(f"Unsupported param type {ptype!r} for {name!r}")


# ── Risk overrides search space ───────────────────────────────────────

DEFAULT_RISK_SEARCH_SPACE: dict[str, dict[str, Any]] = {
    # ── Stop ──
    "stop__atr_multiple": {"type": "float", "min": 3.0, "max": 20.0, "step": 1.0},
    # ── Sizing ──
    "sizing__risk_pct": {"type": "float", "min": 1.0, "max": 50.0, "step": 1.0},
    # ── Partial TP ──
    "partial_tp__r_multiple": {"type": "float", "min": 0.5, "max": 5.0, "step": 0.25},
    "partial_tp__close_pct": {"type": "float", "min": 10.0, "max": 80.0, "step": 5.0},
    # ── Break-even ──
    "break_even__buffer": {"type": "float", "min": 1.0001, "max": 1.01, "step": 0.001},
    "break_even__r_multiple": {"type": "float", "min": 0.5, "max": 3.0, "step": 0.25},
    # ── Pyramid ──
    "pyramid__max_adds": {"type": "int", "min": 1, "max": 5},
    "pyramid__block_bars": {"type": "int", "min": 3, "max": 50},
    "pyramid__threshold_factor": {"type": "float", "min": 1.002, "max": 1.05, "step": 0.002},
    # ── Time exit ──
    "time_exit__max_bars": {"type": "int", "min": 30, "max": 500},
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
) -> dict[str, Any]:
    """Suggest risk overrides and convert flat keys to nested dict."""
    overrides: dict[str, Any] = {}
    for flat_key, schema in risk_search_space.items():
        value = _suggest_param(trial, flat_key, schema)
        parts = flat_key.split("__")
        target = overrides
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    return overrides


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
    ) -> None:
        self._dataset = dataset
        self._indicator_names = indicator_names or list(INDICATOR_REGISTRY.keys())
        self._auxiliary_indicators = auxiliary_indicators or []
        self._archetype = archetype
        self._direction = direction
        self._metric = metric
        self._mode = mode
        self._commission_pct = commission_pct
        self._engine = BacktestEngine()
        self._metrics_engine = MetricsEngine()

        # Build effective risk search space: drop dead parameters based
        # on archetype config (stop model, TP1 enabled, etc.)
        base_space = risk_search_space or dict(DEFAULT_RISK_SEARCH_SPACE)
        archetype_cfg = get_archetype(archetype).build_config()
        if archetype_cfg.stop.model == "firestorm_tm":
            base_space.pop("stop__atr_multiple", None)
        if not archetype_cfg.partial_tp.enabled:
            base_space.pop("partial_tp__r_multiple", None)
            base_space.pop("partial_tp__close_pct", None)
        if not archetype_cfg.break_even.enabled:
            base_space.pop("break_even__buffer", None)
            base_space.pop("break_even__r_multiple", None)
        if not archetype_cfg.pyramid.enabled:
            base_space.pop("pyramid__max_adds", None)
            base_space.pop("pyramid__block_bars", None)
            base_space.pop("pyramid__threshold_factor", None)
        if not archetype_cfg.time_exit.enabled:
            base_space.pop("time_exit__max_bars", None)
        self._risk_search_space = base_space

    # Minimum trades required; configs below this get a harsh penalty
    # so Optuna learns to avoid degenerate low-trade solutions.
    # 300 ensures statistical significance across any TF/period.
    MIN_TRADES: int = 300
    LOW_TRADE_PENALTY: float = -10.0

    def __call__(self, trial: optuna.Trial) -> float:
        """Suggest params, run backtest, return metric value."""
        indicator_params = self._suggest_indicator_params(trial)
        risk_overrides = _suggest_risk_overrides(trial, self._risk_search_space)

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
        if total_trades < self.MIN_TRADES:
            return self.LOW_TRADE_PENALTY

        value = float(metrics.get(self._metric, 0.0))
        if np.isnan(value) or np.isinf(value):
            logger.warning(
                "Metric '{}' returned {} for trial — applying low-trade penalty",
                self._metric, value,
            )
            value = self.LOW_TRADE_PENALTY
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
        mode, threshold = get_combination_mode(self._archetype)

        # ── Entry signals ────────────────────────────────────────────
        entry_signals: dict[str, pd.Series] = {}
        entry_short_signals: dict[str, pd.Series] = {}
        entry_states: dict[str, IndicatorState] = {}

        for ind_name, params in indicator_params.items():
            if ind_name in auxiliary:
                continue
            indicator = get_indicator(ind_name)

            entry_sig = indicator.compute(ohlcv, **params)
            entry_signals[ind_name] = entry_sig
            entry_states[ind_name] = IndicatorState.EXCLUYENTE

            # Inverted entry → entry_short
            inv_params = _make_exit_params(ind_name, params)
            if inv_params is not None:
                entry_short_signals[ind_name] = indicator.compute(ohlcv, **inv_params)

        if not entry_signals:
            entry_long = pd.Series(False, index=idx)
            entry_short = pd.Series(False, index=idx)
        else:
            entry_long = combine_signals(
                entry_signals, entry_states,
                combination_mode=mode, majority_threshold=threshold,
            )
            if entry_short_signals:
                entry_short = combine_signals(
                    entry_short_signals, entry_states,
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
            params = indicator_params.get(ind_name, {})
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
            params = indicator_params.get(ind_name, {})
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
            from suitetrading.indicators.mtf import resample_ohlcv, align_to_base
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
        return get_archetype(self._archetype).build_config(**risk_overrides)

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
        """
        indicator_params: dict[str, dict[str, Any]] = {}
        risk_overrides: dict[str, Any] = {}
        indicator_set = set(self._indicator_names)

        for key, value in flat_params.items():
            parts = key.split("__", 1)
            if len(parts) == 2 and parts[0] in indicator_set:
                indicator_params.setdefault(parts[0], {})[parts[1]] = value
            else:
                risk_overrides[key] = value

        return indicator_params, risk_overrides

    def _suggest_indicator_params(
        self,
        trial: optuna.Trial,
    ) -> dict[str, dict[str, Any]]:
        """Suggest parameters for each active indicator."""
        result: dict[str, dict[str, Any]] = {}
        for ind_name in self._indicator_names:
            indicator = get_indicator(ind_name)
            schema = indicator.params_schema()
            params: dict[str, Any] = {}
            for param_name, param_schema in schema.items():
                full_name = f"{ind_name}__{param_name}"
                params[param_name] = _suggest_param(trial, full_name, param_schema)
            result[ind_name] = params
        return result
