"""Risk management archetypes: presets for common trading styles.

Each archetype assembles a ``RiskConfig`` from sensible defaults.
Use ``get_archetype(name)`` to obtain an instance by key.
"""

from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.archetypes.breakout import Breakout
from suitetrading.risk.archetypes.grid_dca import GridDCA
from suitetrading.risk.archetypes.legacy import LegacyFirestormProfile
from suitetrading.risk.archetypes.mean_reversion import MeanReversion
from suitetrading.risk.archetypes.mixed import Mixed
from suitetrading.risk.archetypes.momentum import Momentum
from suitetrading.risk.archetypes.pyramidal import PyramidalScaling
from suitetrading.risk.archetypes.trend_following import TrendFollowing

ARCHETYPE_REGISTRY: dict[str, type[RiskArchetype]] = {
    "legacy_firestorm": LegacyFirestormProfile,
    "trend_following": TrendFollowing,
    "mean_reversion": MeanReversion,
    "mixed": Mixed,
    "pyramidal": PyramidalScaling,
    "grid_dca": GridDCA,
    "momentum": Momentum,
    "breakout": Breakout,
}


def get_archetype(name: str) -> RiskArchetype:
    """Return an archetype instance by name."""
    cls = ARCHETYPE_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown archetype: {name!r}. Available: {list(ARCHETYPE_REGISTRY)}")
    return cls()


__all__ = [
    "RiskArchetype",
    "LegacyFirestormProfile",
    "TrendFollowing",
    "MeanReversion",
    "Mixed",
    "Momentum",
    "Breakout",
    "PyramidalScaling",
    "GridDCA",
    "ARCHETYPE_REGISTRY",
    "get_archetype",
]
