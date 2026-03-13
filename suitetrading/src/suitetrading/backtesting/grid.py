"""Parameter grid generation and chunking.

Builds the Cartesian product of indicator parameters, risk overrides,
symbols, timeframes and archetypes into a stream of ``RunConfig``
objects.  Supports deterministic chunking for memory-bounded execution.
"""

from __future__ import annotations

import itertools
from typing import Any, Iterator

from suitetrading.backtesting._internal.schemas import GridRequest, RunConfig
from suitetrading.indicators.registry import INDICATOR_REGISTRY


class ParameterGridBuilder:
    """Build and chunk parameter grids from a ``GridRequest``."""

    def build(self, request: GridRequest) -> list[RunConfig]:
        """Expand into a flat list of ``RunConfig``."""
        return list(self.iter_configs(request))

    def iter_configs(self, request: GridRequest) -> Iterator[RunConfig]:
        """Lazily expand the grid (memory-friendly)."""
        indicator_combos = list(self._expand_indicator_space(request.indicator_space))
        risk_combos = list(self._expand_risk_space(request.risk_space))

        for symbol in request.symbols:
            for tf in request.timeframes:
                for archetype in request.archetypes:
                    for ind_params in indicator_combos:
                        for risk_params in risk_combos:
                            yield RunConfig(
                                symbol=symbol,
                                timeframe=tf,
                                archetype=archetype,
                                indicator_params=ind_params,
                                risk_overrides=risk_params,
                            )

    def estimate_size(self, request: GridRequest) -> int:
        """Estimate total number of combinations without expanding."""
        n_ind = max(1, self._count_indicator_combos(request.indicator_space))
        n_risk = max(1, self._count_risk_combos(request.risk_space))
        return (
            len(request.symbols)
            * len(request.timeframes)
            * len(request.archetypes)
            * n_ind
            * n_risk
        )

    @staticmethod
    def chunk(
        configs: list[RunConfig],
        chunk_size: int,
    ) -> list[list[RunConfig]]:
        """Split configs into deterministic chunks."""
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        return [
            configs[i : i + chunk_size]
            for i in range(0, len(configs), chunk_size)
        ]

    @staticmethod
    def deduplicate(configs: list[RunConfig]) -> list[RunConfig]:
        """Remove duplicate configs by run_id."""
        seen: set[str] = set()
        unique: list[RunConfig] = []
        for cfg in configs:
            if cfg.run_id not in seen:
                seen.add(cfg.run_id)
                unique.append(cfg)
        return unique

    # ── Internal expansion ────────────────────────────────────────────

    @staticmethod
    def _expand_indicator_space(
        space: dict[str, dict[str, list[Any]]],
    ) -> Iterator[dict[str, dict[str, Any]]]:
        """Cartesian product of indicator parameters.

        ``space`` maps indicator_name -> {param_name: [values]}.
        """
        if not space:
            yield {}
            return

        names = sorted(space.keys())
        per_indicator: list[list[dict[str, Any]]] = []

        for name in names:
            params = space[name]
            if not params:
                per_indicator.append([{}])
                continue
            keys = sorted(params.keys())
            vals = [params[k] for k in keys]
            combos = [dict(zip(keys, combo)) for combo in itertools.product(*vals)]
            per_indicator.append(combos)

        for combo in itertools.product(*per_indicator):
            yield {name: params for name, params in zip(names, combo)}

    @staticmethod
    def _expand_risk_space(space: dict[str, list[Any]]) -> Iterator[dict[str, Any]]:
        """Cartesian product of risk overrides."""
        if not space:
            yield {}
            return
        keys = sorted(space.keys())
        vals = [space[k] for k in keys]
        for combo in itertools.product(*vals):
            yield dict(zip(keys, combo))

    @staticmethod
    def _count_indicator_combos(space: dict[str, dict[str, list[Any]]]) -> int:
        total = 1
        for params in space.values():
            if not params:
                continue
            n = 1
            for vals in params.values():
                n *= len(vals)
            total *= n
        return total

    @staticmethod
    def _count_risk_combos(space: dict[str, list[Any]]) -> int:
        if not space:
            return 1
        total = 1
        for vals in space.values():
            total *= len(vals)
        return total


def build_indicator_space_from_registry(
    indicator_names: list[str],
    resolution: int = 3,
) -> dict[str, dict[str, list[Any]]]:
    """Auto-generate indicator param space from registry schemas.

    *resolution* controls how many values to sample per numeric range.
    """
    space: dict[str, dict[str, list[Any]]] = {}
    for name in indicator_names:
        cls = INDICATOR_REGISTRY.get(name)
        if cls is None:
            continue
        schema = cls().params_schema()
        params: dict[str, list[Any]] = {}
        for pname, pspec in schema.items():
            ptype = pspec.get("type", "float")
            if "choices" in pspec:
                params[pname] = pspec["choices"]
            elif ptype in ("int", "float"):
                lo = pspec.get("min", 0)
                hi = pspec.get("max", 100)
                default = pspec.get("default", lo)
                if ptype == "int":
                    step = max(1, (hi - lo) // max(1, resolution - 1))
                    vals = list(range(int(lo), int(hi) + 1, step))
                    if int(default) not in vals:
                        vals.append(int(default))
                    params[pname] = sorted(set(vals))
                else:
                    step = (hi - lo) / max(1, resolution - 1)
                    vals = [round(lo + step * j, 6) for j in range(resolution)]
                    if default not in vals:
                        vals.append(default)
                    params[pname] = sorted(set(vals))
            else:
                params[pname] = [pspec.get("default")]
        space[name] = params
    return space
