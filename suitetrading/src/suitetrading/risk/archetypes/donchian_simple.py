"""Archetype — Donchian Simple.

Single-indicator Donchian breakout. Minimal parameters to reduce
overfitting risk. Wide safety-net stop, signal-based exit only.
"""

from __future__ import annotations

from suitetrading.risk.archetypes.momentum_trend import MomentumTrend


class DonchianSimple(MomentumTrend):
    name = "donchian_simple"
