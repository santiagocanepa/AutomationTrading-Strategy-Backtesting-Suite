"""Archetype — ROC + full risk chain + pyramid + time exit (kitchen sink)."""
from __future__ import annotations
from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.archetypes._fullrisk_base import fullrisk_config
from suitetrading.risk.contracts import RiskConfig


class _Arch(RiskArchetype):
    name = "roc_fullrisk_all"

    def build_config(self, **overrides: object) -> RiskConfig:
        return fullrisk_config(
            self.name, pyramid_enabled=True, time_exit_enabled=True,
            overrides=dict(overrides),
        )
