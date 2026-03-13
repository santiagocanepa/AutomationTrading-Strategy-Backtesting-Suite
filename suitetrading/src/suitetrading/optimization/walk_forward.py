"""Walk-Forward Optimization — rolling and anchored IS/OOS splits.

Produces out-of-sample equity curves by re-optimising on each
in-sample fold and applying the best parameters to the corresponding
out-of-sample period.  The concatenated OOS results are the basis
for all anti-overfitting filters.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
from loguru import logger

from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.optimization._internal.schemas import WFOConfig, WFOResult


class WalkForwardEngine:
    """Walk-Forward Optimization with rolling or anchored splits.

    Parameters
    ----------
    config
        Split configuration (number of folds, IS/OOS ratios, gap, mode).
    metric
        Metric to optimise during IS phase (``"sharpe"`` by default).
    """

    def __init__(
        self,
        *,
        config: WFOConfig | None = None,
        metric: str = "sharpe",
        auxiliary_indicators: list[str] | None = None,
    ) -> None:
        self._config = config or WFOConfig()
        self._metric = metric
        self._auxiliary_indicators: set[str] = set(auxiliary_indicators or [])
        self._engine = BacktestEngine()
        self._metrics_engine = MetricsEngine()

    # ── Split generation ──────────────────────────────────────────────

    def generate_splits(self, n_bars: int) -> list[tuple[range, range]]:
        """Generate (IS_range, OOS_range) index pairs.

        Returns
        -------
        List of ``(is_range, oos_range)`` tuples where each range contains
        integer bar indices into the dataset.

        Raises
        ------
        ValueError
            If the dataset is too small for the requested configuration.
        """
        cfg = self._config
        splits: list[tuple[range, range]] = []

        if cfg.mode == "rolling":
            splits = self._rolling_splits(n_bars)
        elif cfg.mode == "anchored":
            splits = self._anchored_splits(n_bars)

        if not splits:
            raise ValueError(
                f"Could not generate any splits: n_bars={n_bars}, "
                f"config={cfg}"
            )
        return splits

    def _rolling_splits(self, n_bars: int) -> list[tuple[range, range]]:
        """Fixed-width sliding window."""
        cfg = self._config
        total_per_fold = cfg.min_is_bars + cfg.gap_bars + cfg.min_oos_bars

        # Calculate the step between successive folds
        usable = n_bars
        if usable < total_per_fold:
            raise ValueError(
                f"Not enough bars ({n_bars}) for rolling WFO with "
                f"min_is={cfg.min_is_bars}, gap={cfg.gap_bars}, "
                f"min_oos={cfg.min_oos_bars}"
            )

        if cfg.n_splits <= 1:
            raise ValueError("n_splits must be >= 2 for rolling WFO")

        # The window size is the minimum fold size
        is_size = cfg.min_is_bars
        oos_size = cfg.min_oos_bars
        gap = cfg.gap_bars
        fold_size = is_size + gap + oos_size
        step = (n_bars - fold_size) // (cfg.n_splits - 1) if cfg.n_splits > 1 else 0

        splits = []
        for i in range(cfg.n_splits):
            start = i * step
            is_start = start
            is_end = is_start + is_size
            oos_start = is_end + gap
            oos_end = oos_start + oos_size

            if oos_end > n_bars:
                break

            splits.append((range(is_start, is_end), range(oos_start, oos_end)))

        if len(splits) < cfg.n_splits:
            logger.warning(
                "WFO rolling: requested {} splits but generated {} (n_bars={})",
                cfg.n_splits, len(splits), n_bars,
            )

        return splits

    def _anchored_splits(self, n_bars: int) -> list[tuple[range, range]]:
        """Expanding IS window with fixed start."""
        cfg = self._config

        # Reserve space for OOS + gap at the end of each fold
        # IS grows from the beginning, OOS slides forward
        oos_size = cfg.min_oos_bars
        gap = cfg.gap_bars

        # Total OOS coverage = n_splits * oos_size (approximately)
        # We need at least min_is_bars for the first fold
        min_total = cfg.min_is_bars + gap + oos_size
        if n_bars < min_total:
            raise ValueError(
                f"Not enough bars ({n_bars}) for anchored WFO with "
                f"min_is={cfg.min_is_bars}, gap={gap}, min_oos={oos_size}"
            )

        # Place OOS windows from the end backward
        available_for_oos = n_bars - cfg.min_is_bars - gap
        if available_for_oos < oos_size:
            raise ValueError("Not enough bars after minimum IS window for OOS")

        # Step through OOS regions
        total_oos_bars = cfg.n_splits * oos_size
        if total_oos_bars > available_for_oos:
            # Adjust: use all available space, distribute evenly
            oos_size = available_for_oos // cfg.n_splits

        splits = []
        for i in range(cfg.n_splits):
            oos_end = n_bars - (cfg.n_splits - 1 - i) * oos_size
            oos_start = oos_end - oos_size
            is_end = oos_start - gap
            is_start = 0  # anchored: always starts at 0

            if is_end - is_start < cfg.min_is_bars:
                continue

            splits.append((range(is_start, is_end), range(oos_start, oos_end)))

        if len(splits) < cfg.n_splits:
            logger.warning(
                "WFO anchored: requested {} splits but generated {} (n_bars={})",
                cfg.n_splits, len(splits), n_bars,
            )

        return splits

    # ── Main run ──────────────────────────────────────────────────────

    def run(
        self,
        *,
        dataset: BacktestDataset,
        candidate_params: list[dict[str, Any]],
        archetype: str = "trend_following",
        signal_builder: Callable[[BacktestDataset, dict[str, Any]], StrategySignals] | None = None,
        risk_builder: Callable[[str, dict[str, Any]], Any] | None = None,
        mode: str = "auto",
    ) -> WFOResult:
        """Execute walk-forward optimization across all folds.

        Parameters
        ----------
        dataset
            Full dataset to be sliced into IS/OOS.
        candidate_params
            List of parameter dicts to evaluate.  Each dict has
            ``"indicator_params"`` and ``"risk_overrides"`` keys.
        archetype
            Risk management archetype.
        signal_builder
            Callable(dataset_slice, params) → StrategySignals.
            If None, uses default from objective module.
        risk_builder
            Callable(archetype, risk_overrides) → RiskConfig.
            If None, uses default archetype factory.
        mode
            Backtesting mode.
        """
        from suitetrading.optimization._internal.objective import BacktestObjective
        from suitetrading.risk.archetypes import get_archetype

        n_bars = len(dataset.ohlcv)
        splits = self.generate_splits(n_bars)

        ohlcv = dataset.ohlcv
        oos_equity_curves: dict[str, list[np.ndarray]] = {
            self._param_id(p): [] for p in candidate_params
        }
        oos_metrics_all: dict[str, list[dict[str, float]]] = {
            self._param_id(p): [] for p in candidate_params
        }
        is_metrics_all: dict[str, list[dict[str, float]]] = {
            self._param_id(p): [] for p in candidate_params
        }
        split_details: list[dict[str, Any]] = []

        for fold_idx, (is_range, oos_range) in enumerate(splits):
            logger.info(
                "WFO fold {}/{}: IS=[{}:{}] OOS=[{}:{}]",
                fold_idx + 1, len(splits),
                is_range.start, is_range.stop,
                oos_range.start, oos_range.stop,
            )

            is_ohlcv = ohlcv.iloc[is_range.start : is_range.stop]
            oos_ohlcv = ohlcv.iloc[oos_range.start : oos_range.stop]

            is_ds = BacktestDataset(
                exchange=dataset.exchange, symbol=dataset.symbol,
                base_timeframe=dataset.base_timeframe, ohlcv=is_ohlcv,
            )
            oos_ds = BacktestDataset(
                exchange=dataset.exchange, symbol=dataset.symbol,
                base_timeframe=dataset.base_timeframe, ohlcv=oos_ohlcv,
            )

            # Evaluate all candidates on IS, find best
            best_is_metric = float("-inf")
            best_params_idx = 0

            for ci, params in enumerate(candidate_params):
                pid = self._param_id(params)
                ind_params = params.get("indicator_params", {})
                risk_overrides = params.get("risk_overrides", {})

                # IS evaluation
                is_result = self._evaluate(
                    is_ds, ind_params, risk_overrides, archetype,
                    signal_builder, risk_builder, mode,
                )
                is_metric_val = is_result.get(self._metric, 0.0)
                is_metrics_all[pid].append(is_result)

                if is_metric_val > best_is_metric:
                    best_is_metric = is_metric_val
                    best_params_idx = ci

                # OOS evaluation (apply same params, no re-optimization)
                oos_result = self._evaluate(
                    oos_ds, ind_params, risk_overrides, archetype,
                    signal_builder, risk_builder, mode,
                )
                oos_metrics_all[pid].append(oos_result)

                # Extract OOS equity curve
                oos_eq = oos_result.get("_equity_curve")
                if oos_eq is not None:
                    oos_equity_curves[pid].append(oos_eq)

            split_details.append({
                "fold": fold_idx,
                "is_range": (is_range.start, is_range.stop),
                "oos_range": (oos_range.start, oos_range.stop),
                "best_is_params_idx": best_params_idx,
                "best_is_metric": best_is_metric,
            })

        # Aggregate results
        agg_oos_equity = {}
        agg_oos_metrics: dict[str, dict[str, float]] = {}
        degradation: dict[str, float] = {}

        # Determine initial_capital from the first candidate's RiskConfig
        _agg_initial_capital = self._resolve_initial_capital(
            archetype, candidate_params[0] if candidate_params else {}, risk_builder,
        )

        for params in candidate_params:
            pid = self._param_id(params)

            # Concatenate OOS equity curves via RETURNS to avoid jumps (B16)
            curves = oos_equity_curves.get(pid, [])
            if curves:
                returns_per_fold = []
                for c in curves:
                    if len(c) >= 2:
                        r = np.diff(c) / np.maximum(c[:-1], 1e-12)
                        returns_per_fold.append(r)
                if returns_per_fold:
                    all_returns = np.concatenate(returns_per_fold)
                    concat_eq = _agg_initial_capital * np.cumprod(
                        np.concatenate([[1.0], 1.0 + all_returns]),
                    )
                else:
                    concat_eq = np.array([_agg_initial_capital])
                agg_oos_equity[pid] = concat_eq

                agg_oos_metrics[pid] = self._metrics_engine.compute(
                    equity_curve=concat_eq,
                    initial_capital=_agg_initial_capital,
                    context={"timeframe": dataset.base_timeframe},
                )
            else:
                agg_oos_equity[pid] = np.array([])
                agg_oos_metrics[pid] = {}

            # Degradation ratio — per-fold ratio then average (B25)
            is_mets = is_metrics_all.get(pid, [])
            oos_mets = oos_metrics_all.get(pid, [])
            fold_ratios: list[float] = []
            for is_m, oos_m in zip(is_mets, oos_mets):
                oos_val = oos_m.get(self._metric, 0.0)
                is_val = is_m.get(self._metric, 0.0)
                if oos_val != 0:
                    fold_ratios.append(is_val / oos_val)
            degradation[pid] = float(np.mean(fold_ratios)) if fold_ratios else float("inf")

        return WFOResult(
            config=self._config,
            n_candidates=len(candidate_params),
            splits=split_details,
            oos_equity_curves=agg_oos_equity,
            oos_metrics=agg_oos_metrics,
            degradation=degradation,
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _evaluate(
        self,
        dataset: BacktestDataset,
        indicator_params: dict[str, Any],
        risk_overrides: dict[str, Any],
        archetype: str,
        signal_builder: Callable | None,
        risk_builder: Callable | None,
        mode: str,
    ) -> dict[str, Any]:
        """Run a single backtest and return metrics + equity curve."""
        from suitetrading.risk.archetypes import get_archetype

        if signal_builder:
            signals = signal_builder(dataset, indicator_params)
        else:
            signals = self._default_signal_builder(dataset, indicator_params, archetype)

        if risk_builder:
            rc = risk_builder(archetype, risk_overrides)
        else:
            rc = get_archetype(archetype).build_config(**risk_overrides)

        result = self._engine.run(
            dataset=dataset, signals=signals, risk_config=rc, mode=mode,
        )

        metrics = self._metrics_engine.compute(
            equity_curve=result["equity_curve"],
            trades=result.get("trades"),
            initial_capital=rc.initial_capital,
            context={"timeframe": dataset.base_timeframe},
        )
        # Include raw equity for concatenation
        metrics["_equity_curve"] = np.asarray(result["equity_curve"], dtype=np.float64)
        return metrics

    def _default_signal_builder(
        self, dataset: BacktestDataset, indicator_params: dict[str, Any],
        archetype: str = "trend_following",
    ) -> StrategySignals:
        """Build signals using indicator registry (same logic as objective)."""
        from suitetrading.backtesting._internal.schemas import StrategySignals
        from suitetrading.config.archetypes import (
            get_combination_mode,
            get_exit_indicators,
            get_trailing_indicators,
        )
        from suitetrading.indicators.base import IndicatorState
        from suitetrading.indicators.registry import get_indicator
        from suitetrading.indicators.signal_combiner import combine_signals
        from suitetrading.optimization._internal.objective import _make_exit_params

        ohlcv = dataset.ohlcv
        idx = ohlcv.index
        mode, threshold = get_combination_mode(archetype)

        # ── Entry signals ────────────────────────────────────────────
        entry_signals: dict[str, pd.Series] = {}
        entry_short_signals: dict[str, pd.Series] = {}
        entry_states: dict[str, IndicatorState] = {}

        for ind_name, params in indicator_params.items():
            if ind_name in self._auxiliary_indicators:
                continue
            indicator = get_indicator(ind_name)
            entry_signals[ind_name] = indicator.compute(ohlcv, **params)
            entry_states[ind_name] = IndicatorState.EXCLUYENTE
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
            entry_short = (
                combine_signals(
                    entry_short_signals, entry_states,
                    combination_mode=mode, majority_threshold=threshold,
                )
                if entry_short_signals
                else pd.Series(False, index=idx)
            )

        # ── Exit signals ─────────────────────────────────────────────
        exit_ind_names = get_exit_indicators(archetype)
        exit_long_sigs: dict[str, pd.Series] = {}
        exit_short_sigs: dict[str, pd.Series] = {}
        exit_states: dict[str, IndicatorState] = {}

        for ind_name in exit_ind_names:
            params = indicator_params.get(ind_name, {})
            indicator = get_indicator(ind_name)
            inv_params = _make_exit_params(ind_name, params)
            if inv_params is not None:
                exit_long_sigs[ind_name] = indicator.compute(ohlcv, **inv_params)
                exit_states[ind_name] = IndicatorState.EXCLUYENTE
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

        # ── Trailing signals ─────────────────────────────────────────
        trail_ind_names = get_trailing_indicators(archetype)
        trail_long_sigs: dict[str, pd.Series] = {}
        trail_short_sigs: dict[str, pd.Series] = {}
        trail_states: dict[str, IndicatorState] = {}

        for ind_name in trail_ind_names:
            params = indicator_params.get(ind_name, {})
            indicator = get_indicator(ind_name)
            trail_long_sigs[ind_name] = indicator.compute(ohlcv, direction="long", **params)
            trail_states[ind_name] = IndicatorState.EXCLUYENTE
            trail_short_sigs[ind_name] = indicator.compute(ohlcv, direction="short", **params)

        trailing_long = (
            combine_signals(trail_long_sigs, trail_states, combination_mode=mode, majority_threshold=threshold)
            if trail_long_sigs
            else exit_long
        )
        trailing_short = (
            combine_signals(trail_short_sigs, trail_states, combination_mode=mode, majority_threshold=threshold)
            if trail_short_sigs
            else exit_short
        )

        # ── Auxiliary payload ────────────────────────────────────────
        indicators_payload: dict[str, pd.Series] = {}
        for ind_name in self._auxiliary_indicators:
            if ind_name in indicator_params and ind_name == "firestorm_tm":
                from suitetrading.indicators.custom.firestorm import firestorm as _firestorm_fn
                params = indicator_params[ind_name]
                ftm_result = _firestorm_fn(
                    ohlcv["open"], ohlcv["high"], ohlcv["low"], ohlcv["close"],
                    period=params.get("period", 9),
                    multiplier=params.get("multiplier", 1.8),
                )
                indicators_payload["firestorm_tm_up"] = ftm_result["up"]
                indicators_payload["firestorm_tm_dn"] = ftm_result["dn"]

        return StrategySignals(
            entry_long=entry_long,
            entry_short=entry_short,
            exit_long=exit_long,
            exit_short=exit_short,
            trailing_long=trailing_long,
            trailing_short=trailing_short,
            indicators_payload=indicators_payload,
        )

    @staticmethod
    def _resolve_initial_capital(
        archetype: str,
        params: dict[str, Any],
        risk_builder: Callable | None,
    ) -> float:
        """Get the actual initial_capital from the RiskConfig."""
        from suitetrading.risk.archetypes import get_archetype

        if risk_builder:
            rc = risk_builder(archetype, params.get("risk_overrides", {}))
        else:
            rc = get_archetype(archetype).build_config(
                **params.get("risk_overrides", {}),
            )
        return float(rc.initial_capital)

    @staticmethod
    def _param_id(params: dict[str, Any]) -> str:
        """Create a stable ID for a parameter set."""
        import hashlib
        import json

        payload = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
