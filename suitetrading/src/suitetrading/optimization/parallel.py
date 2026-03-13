"""Parallel execution wrapper for the backtesting engine.

Distributes ``RunConfig`` batches across ``ProcessPoolExecutor`` workers
while keeping every worker stateless and pure (no shared mutable state).
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Callable

from loguru import logger

from suitetrading.backtesting._internal.schemas import RunConfig


def _run_single(
    cfg: RunConfig,
    dataset_loader: Callable[[RunConfig], Any],
    signal_builder: Callable[[Any, RunConfig], Any],
    risk_builder: Callable[[RunConfig], Any],
    mode: str,
) -> dict[str, Any]:
    """Execute one backtest in a worker process.

    Creates a fresh ``BacktestEngine`` per call — fully stateless.
    """
    from suitetrading.backtesting.engine import BacktestEngine

    try:
        engine = BacktestEngine()
        ds = dataset_loader(cfg)
        sigs = signal_builder(ds, cfg)
        rc = risk_builder(cfg)
        result = engine.run(dataset=ds, signals=sigs, risk_config=rc, mode=mode)
        result["run_id"] = cfg.run_id
        return result
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": cfg.run_id,
            "error": str(exc),
            "symbol": cfg.symbol,
            "timeframe": cfg.timeframe,
        }


class ParallelExecutor:
    """Multiprocessing wrapper over ``BacktestEngine.run()``.

    Parameters
    ----------
    max_workers
        Number of worker processes.  ``None`` uses ``os.cpu_count()``.
    sequential
        If True, run all configs in a plain loop (no multiprocessing).
        Useful for debugging.
    """

    def __init__(
        self,
        max_workers: int | None = None,
        sequential: bool = False,
    ) -> None:
        self._max_workers = max_workers or os.cpu_count() or 1
        self._sequential = sequential

    @property
    def max_workers(self) -> int:
        return self._max_workers

    def run_batch(
        self,
        configs: list[RunConfig],
        *,
        dataset_loader: Callable[[RunConfig], Any],
        signal_builder: Callable[[Any, RunConfig], Any],
        risk_builder: Callable[[RunConfig], Any],
        mode: str = "auto",
    ) -> list[dict[str, Any]]:
        """Execute *configs* in parallel and return results in order.

        - Each worker creates its own ``BacktestEngine`` (stateless).
        - Errors in individual workers are captured without aborting.
        - Results maintain the same order as *configs*.
        """
        if not configs:
            return []

        t0 = time.perf_counter()

        if self._sequential:
            results = self._run_sequential(configs, dataset_loader, signal_builder, risk_builder, mode)
        else:
            results = self._run_parallel(configs, dataset_loader, signal_builder, risk_builder, mode)

        elapsed = time.perf_counter() - t0
        throughput = len(configs) / elapsed if elapsed > 0 else 0
        logger.info(
            "ParallelExecutor: {} configs in {:.2f}s ({:.1f} bt/sec, workers={}, sequential={})",
            len(configs), elapsed, throughput, self._max_workers, self._sequential,
        )
        return results

    def map_backtests(
        self,
        fn: Callable[[RunConfig], dict[str, Any]],
        configs: list[RunConfig],
    ) -> list[dict[str, Any]]:
        """Execute a generic callable over configs in parallel."""
        if not configs:
            return []

        if self._sequential:
            return [fn(cfg) for cfg in configs]

        results: dict[int, dict[str, Any]] = {}
        with ProcessPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {pool.submit(fn, cfg): i for i, cfg in enumerate(configs)}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:  # noqa: BLE001
                    results[idx] = {"error": str(exc), "run_id": configs[idx].run_id}
        return [results[i] for i in range(len(configs))]

    # ── Private ───────────────────────────────────────────────────────

    def _run_sequential(
        self,
        configs: list[RunConfig],
        dataset_loader: Callable,
        signal_builder: Callable,
        risk_builder: Callable,
        mode: str,
    ) -> list[dict[str, Any]]:
        return [
            _run_single(cfg, dataset_loader, signal_builder, risk_builder, mode)
            for cfg in configs
        ]

    def _run_parallel(
        self,
        configs: list[RunConfig],
        dataset_loader: Callable,
        signal_builder: Callable,
        risk_builder: Callable,
        mode: str,
    ) -> list[dict[str, Any]]:
        results: dict[int, dict[str, Any]] = {}
        with ProcessPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {
                pool.submit(
                    _run_single, cfg, dataset_loader, signal_builder, risk_builder, mode,
                ): i
                for i, cfg in enumerate(configs)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:  # noqa: BLE001
                    results[idx] = {
                        "run_id": configs[idx].run_id,
                        "error": str(exc),
                        "symbol": configs[idx].symbol,
                        "timeframe": configs[idx].timeframe,
                    }
        return [results[i] for i in range(len(configs))]
