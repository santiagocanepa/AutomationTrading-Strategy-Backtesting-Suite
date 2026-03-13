"""DEAP-based multi-objective optimiser using NSGA-II.

Provides an alternative to Optuna's ``NSGAIISampler`` with finer
control over crossover/mutation operators and population dynamics.

Requires ``deap>=1.4`` (optional dependency).
"""

from __future__ import annotations

import array
import random
from typing import Any, Callable

import numpy as np
from loguru import logger

try:
    from deap import algorithms, base, creator, tools

    HAS_DEAP = True
except ImportError:
    HAS_DEAP = False


class DEAPOptimizer:
    """Multi-objective optimizer using DEAP NSGA-II.

    Parameters
    ----------
    objective
        Callable(params_dict) → tuple[float, ...] returning one value per
        objective.
    search_space
        Mapping ``param_name → {"min": float, "max": float}``.
        All params are treated as continuous floats in [min, max].
    objectives
        List of objective names (for labelling only).
    directions
        ``"maximize"`` or ``"minimize"`` per objective.
    population_size
        NSGA-II population size per generation.
    n_generations
        Number of evolutionary generations.
    crossover_prob
        Probability of SBX crossover.
    mutation_prob
        Probability of polynomial mutation.
    seed
        Random seed for reproducibility.
    """

    def __init__(
        self,
        *,
        objective: Callable[[dict[str, float]], tuple[float, ...]],
        search_space: dict[str, dict[str, float]],
        objectives: list[str] | None = None,
        directions: list[str] | None = None,
        population_size: int = 100,
        n_generations: int = 50,
        crossover_prob: float = 0.7,
        mutation_prob: float = 0.2,
        seed: int = 42,
    ) -> None:
        if not HAS_DEAP:
            raise ImportError(
                "deap is required for DEAPOptimizer. "
                "Install with: pip install deap>=1.4"
            )

        self._objective = objective
        self._space = search_space
        self._param_names = list(search_space.keys())
        self._objectives = objectives or ["obj_0"]
        self._directions = directions or ["maximize"] * len(self._objectives)
        self._pop_size = population_size
        self._n_gen = n_generations
        self._cx_prob = crossover_prob
        self._mut_prob = mutation_prob
        self._seed = seed

        # Build DEAP fitness weights: +1 for maximize, -1 for minimize
        self._weights = tuple(
            1.0 if d == "maximize" else -1.0 for d in self._directions
        )

        self._logbook: tools.Logbook | None = None
        self._pareto_front: list[dict[str, Any]] = []

    def evolve(self) -> dict[str, Any]:
        """Run the NSGA-II evolution and return a summary dict."""
        random.seed(self._seed)
        np.random.seed(self._seed)

        n_params = len(self._param_names)
        lows = [self._space[p]["min"] for p in self._param_names]
        highs = [self._space[p]["max"] for p in self._param_names]

        # ── DEAP setup (use local toolbox to avoid global state) ──
        # Create unique fitness and individual classes per instance
        fitness_name = f"_Fitness_{id(self)}"
        individual_name = f"_Individual_{id(self)}"

        if hasattr(creator, fitness_name):
            delattr(creator, fitness_name)
        if hasattr(creator, individual_name):
            delattr(creator, individual_name)

        creator.create(fitness_name, base.Fitness, weights=self._weights)
        creator.create(
            individual_name, array.array, typecode="d",
            fitness=getattr(creator, fitness_name),
        )

        fitness_cls = getattr(creator, fitness_name)
        individual_cls = getattr(creator, individual_name)

        tb = base.Toolbox()

        def _random_individual():
            vals = [random.uniform(lo, hi) for lo, hi in zip(lows, highs)]
            ind = individual_cls(vals)
            return ind

        tb.register("individual", _random_individual)
        tb.register("population", tools.initRepeat, list, tb.individual)

        def _evaluate(individual):
            params = {
                name: float(individual[i])
                for i, name in enumerate(self._param_names)
            }
            return self._objective(params)

        tb.register("evaluate", _evaluate)
        tb.register(
            "mate", tools.cxSimulatedBinaryBounded,
            low=lows, up=highs, eta=20.0,
        )
        tb.register(
            "mutate", tools.mutPolynomialBounded,
            low=lows, up=highs, eta=20.0, indpb=1.0 / n_params,
        )
        tb.register("select", tools.selNSGA2)

        # ── Run evolution ──
        pop = tb.population(n=self._pop_size)
        hof = tools.ParetoFront()
        stats = tools.Statistics(lambda ind: ind.fitness.values)
        stats.register("min", np.min, axis=0)
        stats.register("max", np.max, axis=0)
        stats.register("avg", np.mean, axis=0)

        pop, logbook = algorithms.eaMuPlusLambda(
            pop, tb,
            mu=self._pop_size,
            lambda_=self._pop_size,
            cxpb=self._cx_prob,
            mutpb=self._mut_prob,
            ngen=self._n_gen,
            stats=stats,
            halloffame=hof,
            verbose=False,
        )

        self._logbook = logbook

        # ── Extract Pareto front ──
        self._pareto_front = []
        for ind in hof:
            params = {
                name: float(ind[i])
                for i, name in enumerate(self._param_names)
            }
            self._pareto_front.append({
                "params": params,
                "fitness": tuple(ind.fitness.values),
            })

        logger.info(
            "DEAP NSGA-II: {} generations × {} pop → {} Pareto-optimal",
            self._n_gen, self._pop_size, len(self._pareto_front),
        )

        # Cleanup
        if hasattr(creator, fitness_name):
            delattr(creator, fitness_name)
        if hasattr(creator, individual_name):
            delattr(creator, individual_name)

        return {
            "n_generations": self._n_gen,
            "population_size": self._pop_size,
            "pareto_size": len(self._pareto_front),
            "pareto_front": self._pareto_front,
        }

    def get_pareto_front(self) -> list[dict[str, Any]]:
        """Return the Pareto-optimal solutions found during evolution."""
        return list(self._pareto_front)

    def get_logbook(self) -> Any:
        """Return the DEAP logbook with per-generation statistics."""
        return self._logbook
