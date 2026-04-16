"""Optuna-based optimiser for backtesting strategies.

Supports single-objective (TPE) and multi-objective (NSGA-II) search
with SQLite persistence and study resume.
"""

from __future__ import annotations

import time
from typing import Any

import optuna
from loguru import logger

from suitetrading.optimization._internal.schemas import OptimizationResult

# Silence Optuna's noisy default logging
optuna.logging.set_verbosity(optuna.logging.WARNING)


# ── Sampler factory ───────────────────────────────────────────────────

_SAMPLERS: dict[str, type] = {
    "tpe": optuna.samplers.TPESampler,
    "random": optuna.samplers.RandomSampler,
    "nsga2": optuna.samplers.NSGAIISampler,
    "cmaes": optuna.samplers.CmaEsSampler,
}

_PRUNERS: dict[str, type] = {
    "median": optuna.pruners.MedianPruner,
    "none": optuna.pruners.NopPruner,
}


def _build_sampler(name: str, *, n_startup_trials: int = 20, seed: int | None = None) -> optuna.samplers.BaseSampler:
    cls = _SAMPLERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown sampler {name!r}. Available: {sorted(_SAMPLERS)}")
    if name == "tpe":
        return cls(n_startup_trials=n_startup_trials, seed=seed)
    if name == "random":
        return cls(seed=seed)
    if name == "nsga2":
        return cls(seed=seed)
    if name == "cmaes":
        return cls(seed=seed)
    return cls()


def _build_pruner(name: str) -> optuna.pruners.BasePruner:
    cls = _PRUNERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown pruner {name!r}. Available: {sorted(_PRUNERS)}")
    return cls()


# ── Optimizer ─────────────────────────────────────────────────────────

class OptunaOptimizer:
    """Wrapper around Optuna study creation, execution and result extraction.

    Parameters
    ----------
    objective
        Callable compatible with ``optuna.Study.optimize()``.
    study_name
        Unique name for the study (used for persistence/resume).
    storage
        Optuna storage URL.  ``None`` for in-memory, or
        ``"sqlite:///path/to/studies.db"`` for persistent SQLite.
    sampler
        Sampler key: ``"tpe"`` | ``"random"`` | ``"nsga2"`` | ``"cmaes"``.
    pruner
        Pruner key: ``"median"`` | ``"none"``.
    direction
        ``"maximize"`` or ``"minimize"``.  Ignored when *directions* is set.
    directions
        Multi-objective: list of ``"maximize"``/``"minimize"`` per objective.
        When set, overrides *direction* and enables Pareto-front extraction.
    n_startup_trials
        Random trials before TPE kicks in.
    seed
        RNG seed for reproducibility.
    """

    def __init__(
        self,
        *,
        objective: Any,
        study_name: str,
        storage: str | None = None,
        sampler: str = "tpe",
        pruner: str = "median",
        direction: str = "maximize",
        directions: list[str] | None = None,
        n_startup_trials: int = 20,
        seed: int | None = None,
    ) -> None:
        self._objective = objective
        self._study_name = study_name
        self._multi_objective = directions is not None
        self._direction = direction

        sampler_obj = _build_sampler(sampler, n_startup_trials=n_startup_trials, seed=seed)
        pruner_obj = _build_pruner(pruner)

        if self._multi_objective:
            self._study = optuna.create_study(
                study_name=study_name,
                storage=storage,
                sampler=sampler_obj,
                directions=directions,
                load_if_exists=True,
            )
        else:
            self._study = optuna.create_study(
                study_name=study_name,
                storage=storage,
                sampler=sampler_obj,
                pruner=pruner_obj,
                direction=direction,
                load_if_exists=True,
            )

    def optimize(
        self,
        n_trials: int,
        timeout: float | None = None,
        n_jobs: int = 1,
    ) -> OptimizationResult:
        """Run the optimization loop.

        Parameters
        ----------
        n_trials
            Number of trials to execute.
        timeout
            Maximum wall-clock seconds (``None`` for unlimited).
        n_jobs
            Parallel trial workers (1 = sequential).
        """
        t0 = time.perf_counter()

        self._study.optimize(
            self._objective,
            n_trials=n_trials,
            timeout=timeout,
            n_jobs=n_jobs,
            show_progress_bar=False,
        )

        elapsed = time.perf_counter() - t0
        n_completed = len([t for t in self._study.trials if t.state == optuna.trial.TrialState.COMPLETE])
        n_pruned = len([t for t in self._study.trials if t.state == optuna.trial.TrialState.PRUNED])

        if self._multi_objective:
            pareto = self._study.best_trials
            best_value = len(pareto)  # Pareto front size as summary
            best_params = pareto[0].params if pareto else {}
            best_run_id = pareto[0].user_attrs.get("run_id", "") if pareto else ""
        else:
            best = self._study.best_trial
            best_value = best.value
            best_params = best.params
            best_run_id = best.user_attrs.get("run_id", "")

        result = OptimizationResult(
            study_name=self._study_name,
            n_trials=len(self._study.trials),
            n_completed=n_completed,
            n_pruned=n_pruned,
            best_value=best_value,
            best_params=best_params,
            best_run_id=best_run_id,
            wall_time_sec=elapsed,
            trials_per_sec=n_completed / elapsed if elapsed > 0 else 0,
        )

        if self._multi_objective:
            logger.info(
                "Optuna study '{}': {} trials ({} completed), "
                "Pareto front={} in {:.1f}s ({:.1f} trials/sec, {} jobs)",
                self._study_name, result.n_trials, n_completed,
                len(pareto), elapsed, result.trials_per_sec, n_jobs,
            )
        else:
            logger.info(
                "Optuna study '{}': {} trials ({} completed, {} pruned), "
                "best={:.4f} in {:.1f}s ({:.1f} trials/sec)",
                self._study_name, result.n_trials, n_completed, n_pruned,
                result.best_value, elapsed, result.trials_per_sec,
            )
        return result

    def get_top_n(self, n: int = 50, min_trades: int = 0) -> list[dict[str, Any]]:
        """Extract the top *n* completed trials sorted by objective value.

        For multi-objective studies, returns Pareto-optimal trials filtered
        by *min_trades* (objective index 1) and sorted by Sharpe (index 0).

        Returns a list of dicts with keys: ``trial_number``, ``value``,
        ``params``, and all user_attrs.
        """
        if self._multi_objective:
            return self._get_top_n_pareto(n, min_trades)

        completed = [
            t for t in self._study.trials
            if t.state == optuna.trial.TrialState.COMPLETE
        ]
        reverse = self._direction == "maximize"
        completed.sort(key=lambda t: t.value, reverse=reverse)

        top = []
        for t in completed[:n]:
            entry: dict[str, Any] = {
                "trial_number": t.number,
                "value": t.value,
                "params": t.params,
            }
            entry.update(t.user_attrs)
            top.append(entry)
        return top

    def _get_top_n_pareto(self, n: int, min_trades: int) -> list[dict[str, Any]]:
        """Extract top-N from Pareto front for multi-objective studies.

        Filters trials where objective[1] (total_trades) >= min_trades,
        then sorts by objective[0] (sharpe) descending.
        """
        completed = [
            t for t in self._study.trials
            if t.state == optuna.trial.TrialState.COMPLETE
        ]
        # Filter by min trades (objective index 1)
        if min_trades > 0:
            completed = [t for t in completed if t.values[1] >= min_trades]

        # Sort by Sharpe (objective index 0) descending
        completed.sort(key=lambda t: t.values[0], reverse=True)

        top = []
        for t in completed[:n]:
            entry: dict[str, Any] = {
                "trial_number": t.number,
                "value": t.values[0],  # Sharpe for downstream compat
                "values": list(t.values),  # [sharpe, trades]
                "params": t.params,
            }
            entry.update(t.user_attrs)
            top.append(entry)
        return top

    def get_study(self) -> optuna.Study:
        """Access the underlying Optuna study directly."""
        return self._study
