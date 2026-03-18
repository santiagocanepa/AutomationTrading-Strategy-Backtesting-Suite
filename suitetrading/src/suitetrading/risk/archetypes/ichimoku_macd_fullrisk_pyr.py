"""Archetype — Ichimoku + MACD + full risk chain + pyramid."""
from __future__ import annotations

from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.archetypes._fullrisk_base import fullrisk_config
from suitetrading.risk.contracts import RiskConfig


class _Arch(RiskArchetype):
    name = "ichimoku_macd_fullrisk_pyr"

    def build_config(self, **overrides: object) -> RiskConfig:
        return fullrisk_config(self.name, pyramid_enabled=True, overrides=dict(overrides))
