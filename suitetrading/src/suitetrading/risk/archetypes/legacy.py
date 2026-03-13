"""Legacy Firestorm RM profile — exact replica of the Pine Script logic.

Recreates the risk management behaviour documented in
``docs/risk_management_spec.md`` as a reusable archetype preset.
"""

from __future__ import annotations

from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.contracts import RiskConfig


class LegacyFirestormProfile(RiskArchetype):
    """Pine Script legacy profile: Firestorm TM stops, Fibonacci sizing,
    SSL-based trailing, partial TP at 35%, break-even buffer 1.0007.
    """

    name = "legacy_firestorm"

    def build_config(self, **overrides: object) -> RiskConfig:
        data: dict = {
            "archetype": self.name,
            "direction": "long",  # Pine original is long-only
            "initial_capital": 4000.0,
            "commission_pct": 0.10,
            "sizing": {
                "model": "fixed_fractional",
                "risk_pct": 5.0,
                "max_risk_per_trade": 5.0,
                "max_leverage": 1.0,
            },
            "stop": {
                "model": "signal",  # Firestorm TM band, not ATR
                "atr_multiple": 1.0,
            },
            "trailing": {
                "model": "signal",  # SSL LOW
                "atr_multiple": 2.5,
            },
            "partial_tp": {
                "enabled": True,
                "close_pct": 35.0,
                "trigger": "signal",  # SSL opposite cross
                "profit_distance_factor": 1.01,
            },
            "break_even": {
                "enabled": True,
                "buffer": 1.0007,
                "activation": "after_tp1",
            },
            "pyramid": {
                "enabled": True,
                "max_adds": 3,
                "block_bars": 15,
                "threshold_factor": 1.01,
                "weighting": "fibonacci",
            },
            "time_exit": {"enabled": False},
            "portfolio": {
                "max_portfolio_heat": 20.0,
                "max_drawdown_pct": 25.0,
                "kill_switch_drawdown": 30.0,
            },
        }
        self._apply_overrides(data, dict(overrides))
        return RiskConfig(**data)


# ── Fibonacci weighting helper ────────────────────────────────────────

def fibonacci_weights(max_orders: int) -> list[float]:
    """Return normalized Fibonacci weights for *max_orders* pyramid levels.

    Legacy Pine Script pattern: ``[1, 1, 2]`` for 3 orders → ``[25%, 25%, 50%]``.
    """
    if max_orders <= 0:
        return []
    fib = [1.0]
    for i in range(1, max_orders):
        if i < 2:
            fib.append(1.0)
        else:
            fib.append(fib[i - 1] + fib[i - 2])
    total = sum(fib)
    return [f / total for f in fib]
