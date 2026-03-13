"""Base class for risk management archetypes.

An archetype is a *preset composer* — it assembles a ``RiskConfig`` from
sensible defaults for a particular trading style without reimplementing
the state machine or sizing logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from suitetrading.risk.contracts import RiskConfig


class RiskArchetype(ABC):
    """ABC that every archetype preset must implement."""

    name: str = "base"

    @abstractmethod
    def build_config(self, **overrides: object) -> RiskConfig:
        """Return a fully-validated ``RiskConfig`` for this archetype.

        Callers may pass keyword *overrides* to tweak individual fields
        without subclassing.
        """
        ...

    @staticmethod
    def _apply_overrides(data: dict, overrides: dict) -> dict:
        """Recursively merge *overrides* into *data*."""
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                RiskArchetype._apply_overrides(data[key], value)
            else:
                data[key] = value
        return data
