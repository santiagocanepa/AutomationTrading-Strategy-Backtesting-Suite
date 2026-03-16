"""Archetype — ROC Simple.

Single-indicator Rate of Change. Minimal parameters to reduce
overfitting risk. Wide safety-net stop, signal-based exit only.
"""

from __future__ import annotations

from suitetrading.risk.archetypes.momentum_trend import MomentumTrend


class ROCSimple(MomentumTrend):
    name = "roc_simple"
