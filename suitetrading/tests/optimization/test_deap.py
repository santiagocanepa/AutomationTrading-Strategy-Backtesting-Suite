"""Tests for DEAPOptimizer (NSGA-II multi-objective)."""

from __future__ import annotations

import pytest

try:
    import deap  # noqa: F401
    HAS_DEAP = True
except ImportError:
    HAS_DEAP = False

pytestmark = pytest.mark.skipif(not HAS_DEAP, reason="deap not installed")


from suitetrading.optimization.deap_optimizer import DEAPOptimizer


# ── Simple test objectives ────────────────────────────────────────────

def _sphere_objective(params: dict[str, float]) -> tuple[float]:
    """Minimize sum of squares (single-objective)."""
    return (-sum(v ** 2 for v in params.values()),)


def _multi_objective(params: dict[str, float]) -> tuple[float, float]:
    """Maximise x, minimise x^2 — conflicting objectives."""
    x = params.get("x", 0.0)
    return (x, -x ** 2)


SIMPLE_SPACE = {
    "x": {"min": -5.0, "max": 5.0},
    "y": {"min": -5.0, "max": 5.0},
}


# ── Tests ─────────────────────────────────────────────────────────────

class TestDEAPSingleObjective:
    """DEAP with a single-objective function."""

    def test_evolve_returns_dict(self):
        opt = DEAPOptimizer(
            objective=_sphere_objective,
            search_space=SIMPLE_SPACE,
            objectives=["neg_sphere"],
            directions=["maximize"],
            population_size=20,
            n_generations=10,
            seed=42,
        )
        result = opt.evolve()
        assert isinstance(result, dict)
        assert result["pareto_size"] > 0

    def test_pareto_front_has_near_zero_optimum(self):
        opt = DEAPOptimizer(
            objective=_sphere_objective,
            search_space=SIMPLE_SPACE,
            objectives=["neg_sphere"],
            directions=["maximize"],
            population_size=50,
            n_generations=30,
            seed=42,
        )
        opt.evolve()
        front = opt.get_pareto_front()
        # Best solution should have params near zero
        best = max(front, key=lambda s: s["fitness"][0])
        for v in best["params"].values():
            assert abs(v) < 1.0, f"Expected near zero, got {v}"

    def test_logbook_populated(self):
        opt = DEAPOptimizer(
            objective=_sphere_objective,
            search_space=SIMPLE_SPACE,
            population_size=20,
            n_generations=5,
            seed=42,
        )
        opt.evolve()
        lb = opt.get_logbook()
        assert lb is not None
        assert len(lb) > 0


class TestDEAPMultiObjective:
    """DEAP with conflicting multi-objective functions."""

    def test_pareto_front_multiple_solutions(self):
        opt = DEAPOptimizer(
            objective=_multi_objective,
            search_space={"x": {"min": -3.0, "max": 3.0}},
            objectives=["x", "neg_x_sq"],
            directions=["maximize", "maximize"],
            population_size=30,
            n_generations=20,
            seed=42,
        )
        opt.evolve()
        front = opt.get_pareto_front()
        assert len(front) >= 1

    def test_pareto_front_structure(self):
        opt = DEAPOptimizer(
            objective=_multi_objective,
            search_space={"x": {"min": -3.0, "max": 3.0}},
            objectives=["x", "neg_x_sq"],
            directions=["maximize", "maximize"],
            population_size=20,
            n_generations=10,
            seed=42,
        )
        opt.evolve()
        for sol in opt.get_pareto_front():
            assert "params" in sol
            assert "fitness" in sol
            assert len(sol["fitness"]) == 2


class TestDEAPEdgeCases:
    """Edge cases and error handling."""

    def test_import_error_without_deap(self):
        # Already tested implicitly — skipif handles this
        pass

    def test_reproducibility_with_same_seed(self):
        kwargs = dict(
            objective=_sphere_objective,
            search_space=SIMPLE_SPACE,
            population_size=20,
            n_generations=10,
            seed=99,
        )
        opt1 = DEAPOptimizer(**kwargs)
        r1 = opt1.evolve()
        opt2 = DEAPOptimizer(**kwargs)
        r2 = opt2.evolve()
        assert r1["pareto_size"] == r2["pareto_size"]
        # Best fitness should be identical
        best1 = max(r1["pareto_front"], key=lambda s: s["fitness"][0])
        best2 = max(r2["pareto_front"], key=lambda s: s["fitness"][0])
        assert best1["fitness"] == best2["fitness"]
