"""Archetype — Donchian + full risk chain + pyramid + ATR trailing policy."""
from __future__ import annotations
from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.archetypes._fullrisk_base import fullrisk_config
from suitetrading.risk.contracts import RiskConfig


class _Arch(RiskArchetype):
    name = "donchian_fullrisk_pyr_trail_policy"

    def build_config(self, **overrides: object) -> RiskConfig:
        return fullrisk_config(self.name, pyramid_enabled=True, trailing_mode="policy", overrides=dict(overrides))
