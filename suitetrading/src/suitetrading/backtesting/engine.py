"""Backtesting engine — orchestrator for single and batch runs.

This is the main public entry point of the backtesting module.  It
connects datasets, signals, risk configs and runners into a unified
pipeline.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from suitetrading.backtesting._internal.runners import (
    BacktestResult,
    run_fsm_backtest,
    run_simple_backtest,
)
from suitetrading.backtesting._internal.schemas import (
    BacktestDataset,
    RunConfig,
    StrategySignals,
)
from suitetrading.risk.contracts import RiskConfig
from suitetrading.risk.vbt_simulator import VECTORIZABILITY


# ── Execution mode selection ──────────────────────────────────────────

EXECUTION_MODES = ("fsm", "simple", "auto")


def _select_mode(archetype: str, requested: str) -> str:
    """Choose the right runner based on archetype vectorizability."""
    if requested != "auto":
        return requested
    level = VECTORIZABILITY.get(archetype, "low")
    if level == "high":
        return "simple"
    return "fsm"


# ── Single run ────────────────────────────────────────────────────────

class BacktestEngine:
    """Orchestrates single and batch backtesting runs.

    Stateless — each ``run`` call is independent and deterministic.
    """

    def run(
        self,
        *,
        dataset: BacktestDataset,
        signals: StrategySignals,
        risk_config: RiskConfig,
        mode: str = "auto",
        direction: str = "long",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a single backtest and return raw results.

        Parameters
        ----------
        mode
            ``"auto"`` selects based on archetype vectorizability.
            ``"fsm"`` forces full state-machine loop.
            ``"simple"`` forces lightweight bar loop (no pyramiding/partial TP).
        """
        if mode not in EXECUTION_MODES:
            raise ValueError(f"Invalid mode {mode!r}. Choose from {EXECUTION_MODES}")

        effective_mode = _select_mode(risk_config.archetype, mode)
        logger.debug(
            "Running backtest: {} {} mode={} (requested={})",
            dataset.symbol,
            dataset.base_timeframe,
            effective_mode,
            mode,
        )

        if effective_mode == "simple":
            result = run_simple_backtest(
                dataset=dataset,
                signals=signals,
                risk_config=risk_config,
            )
        else:
            result = run_fsm_backtest(
                dataset=dataset,
                signals=signals,
                risk_config=risk_config,
                direction=direction,
            )

        return _result_to_dict(result, dataset, risk_config, effective_mode, context)

    def run_batch(
        self,
        *,
        configs: list[RunConfig],
        dataset_loader,
        signal_builder,
        risk_builder,
        mode: str = "auto",
    ) -> list[dict[str, Any]]:
        """Run multiple configs sequentially and return list of results.

        Parameters
        ----------
        dataset_loader
            Callable(RunConfig) -> BacktestDataset
        signal_builder
            Callable(BacktestDataset, RunConfig) -> StrategySignals
        risk_builder
            Callable(RunConfig) -> RiskConfig
        """
        results: list[dict[str, Any]] = []
        for i, cfg in enumerate(configs):
            logger.info("Batch run {}/{}: {}", i + 1, len(configs), cfg.run_id)
            try:
                ds = dataset_loader(cfg)
                sigs = signal_builder(ds, cfg)
                rc = risk_builder(cfg)
                res = self.run(
                    dataset=ds,
                    signals=sigs,
                    risk_config=rc,
                    mode=mode,
                )
                res["run_id"] = cfg.run_id
                results.append(res)
            except Exception as exc:
                logger.error("Run {} failed: {}", cfg.run_id, exc)
                results.append({
                    "run_id": cfg.run_id,
                    "error": str(exc),
                    "symbol": cfg.symbol,
                    "timeframe": cfg.timeframe,
                })
        return results


# ── Helpers ───────────────────────────────────────────────────────────

def _result_to_dict(
    result: BacktestResult,
    dataset: BacktestDataset,
    risk_config: RiskConfig,
    mode: str,
    context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Flatten BacktestResult into a serialisable dict."""
    trades_df = pd.DataFrame([
        {
            "entry_bar": t.entry_bar,
            "exit_bar": t.exit_bar,
            "direction": t.direction,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "quantity": t.quantity,
            "pnl": t.pnl,
            "commission": t.commission,
            "exit_reason": t.exit_reason,
        }
        for t in result.trades
    ]) if result.trades else pd.DataFrame()

    out: dict[str, Any] = {
        "symbol": dataset.symbol,
        "timeframe": dataset.base_timeframe,
        "archetype": risk_config.archetype,
        "mode": mode,
        "equity_curve": result.equity_curve,
        "trades": trades_df,
        "final_equity": result.final_equity,
        "total_return_pct": result.total_return_pct,
        "total_trades": len(result.trades),
        "initial_capital": risk_config.initial_capital,
    }
    if context:
        out["context"] = context
    return out
