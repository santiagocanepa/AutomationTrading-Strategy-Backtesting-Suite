"""Archetype Factory — dynamic generation from a combinatorial matrix.

Generates archetypes programmatically from a definition table instead of
requiring one .py file per archetype.  Each combination of entry indicator,
risk variant, stop model, trailing mode, and HTF filter produces a unique
archetype registered in ``ARCHETYPE_REGISTRY`` at import time.
"""

from __future__ import annotations

from typing import Any

from suitetrading.config.archetypes import ArchetypeIndicators
from suitetrading.risk.archetypes._fullrisk_base import fullrisk_config
from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.contracts import RiskConfig


# ── Combinatorial matrix ────────────────────────────────────────────

FACTORY_MATRIX: dict[str, list[Any]] = {
    "entries": [
        # Classic momentum/trend
        "roc", "macd", "ema", "ssl_channel", "rsi", "donchian",
        "ma_crossover", "bollinger_bands",
        # Phase 3
        "squeeze", "stoch_rsi", "ichimoku", "obv",
        # Phase 5: regime & anomaly
        "volume_spike", "momentum_divergence",
        # Phase 5: futures/derivatives (fall back gracefully if no data)
        "funding_rate", "oi_divergence", "long_short_ratio",
    ],
    "risk_variants": ["fullrisk", "fullrisk_pyr", "fullrisk_all"],
    "stop_models": ["atr", "firestorm_tm"],
    "trailing_modes": ["signal", "policy"],
    "htf_filters": [
        None,
        ("ma_crossover", "1d"),
        ("macd", "1d"),
        ("ema", "1d"),
    ],
}

# ── Indicators that work as auxiliary (trailing / FTM stops) ────────

_SSL_TRAILING_INDICATORS = ["ssl_channel"]
_FTM_AUXILIARY = ["firestorm_tm"]

# ── Default per-indicator trailing / auxiliary mapping ───────────────

_TRAILING_MAP: dict[str, list[str]] = {
    "ssl_channel": [],  # SSL is its own trailing
}

# Risk variant → (pyramid_enabled, time_exit_enabled)
_VARIANT_FLAGS: dict[str, tuple[bool, bool]] = {
    "fullrisk": (False, False),
    "fullrisk_pyr": (True, False),
    "fullrisk_all": (True, True),
}


def _archetype_name(
    entry: str,
    variant: str,
    stop_model: str,
    trailing_mode: str,
    htf: tuple[str, str] | None,
) -> str:
    """Build a deterministic name from the combo components."""
    parts = [entry, variant]
    if stop_model == "firestorm_tm":
        parts.append("ftm")
    if trailing_mode == "policy":
        parts.append("tpol")
    if htf is not None:
        parts.append(f"htf_{htf[0]}")
    return "_".join(parts)


def _is_valid_combo(
    entry: str,
    stop_model: str,
    trailing_mode: str,
    htf: tuple[str, str] | None,
) -> bool:
    """Filter out invalid or redundant combinations."""
    # FTM stop only makes sense with firestorm_tm as auxiliary
    # SSL entry with SSL trailing is redundant in some combos — still valid
    # HTF filter cannot be the same as entry (would double-count)
    if htf is not None and htf[0] == entry:
        return False
    return True


def _build_indicator_config(
    entry: str,
    stop_model: str,
    htf: tuple[str, str] | None,
) -> ArchetypeIndicators:
    """Build the ArchetypeIndicators dict for a factory-generated archetype."""
    auxiliary: list[str] = ["ssl_channel"]
    trailing: list[str] = ["ssl_channel"]

    if stop_model == "firestorm_tm":
        auxiliary.append("firestorm_tm")

    # Entry indicator shouldn't be in auxiliary/trailing
    if entry == "ssl_channel":
        auxiliary = [a for a in auxiliary if a != "ssl_channel"]
        trailing = []

    cfg: ArchetypeIndicators = {
        "entry": [entry],
        "auxiliary": auxiliary,
        "exit": [entry],
        "trailing": trailing,
        "combination_mode": "excluyente",
    }

    if htf is not None:
        cfg["htf_filter"] = htf[0]
        cfg["htf_timeframe"] = htf[1]

    return cfg


class _DynamicArchetype(RiskArchetype):
    """Archetype built at runtime by the factory."""

    def __init__(
        self,
        name: str,
        pyramid_enabled: bool,
        time_exit_enabled: bool,
        stop_model: str,
        trailing_mode: str,
    ) -> None:
        self.name = name
        self._pyramid = pyramid_enabled
        self._time_exit = time_exit_enabled
        self._stop_model = stop_model
        self._trailing_mode = trailing_mode

    def build_config(self, **overrides: object) -> RiskConfig:
        return fullrisk_config(
            self.name,
            pyramid_enabled=self._pyramid,
            time_exit_enabled=self._time_exit,
            stop_model=self._stop_model,
            trailing_mode=self._trailing_mode,
            overrides=dict(overrides),
        )


def generate_factory_archetypes() -> tuple[
    dict[str, type[RiskArchetype]],
    dict[str, ArchetypeIndicators],
]:
    """Generate all valid archetypes from the factory matrix.

    Returns
    -------
    registry_additions
        Mapping name → archetype class (to merge into ARCHETYPE_REGISTRY).
    indicator_additions
        Mapping name → ArchetypeIndicators (to merge into ARCHETYPE_INDICATORS).
    """
    registry: dict[str, type[RiskArchetype]] = {}
    indicators: dict[str, ArchetypeIndicators] = {}

    entries = FACTORY_MATRIX["entries"]
    variants = FACTORY_MATRIX["risk_variants"]
    stop_models = FACTORY_MATRIX["stop_models"]
    trailing_modes = FACTORY_MATRIX["trailing_modes"]
    htf_filters = FACTORY_MATRIX["htf_filters"]

    for entry in entries:
        for variant in variants:
            for stop_model in stop_models:
                for trailing_mode in trailing_modes:
                    for htf in htf_filters:
                        if not _is_valid_combo(entry, stop_model, trailing_mode, htf):
                            continue

                        name = _archetype_name(entry, variant, stop_model, trailing_mode, htf)

                        # Skip if already manually registered
                        if name in registry:
                            continue

                        pyramid, time_exit = _VARIANT_FLAGS[variant]

                        # Create a unique class per archetype (needed for registry)
                        arch_instance = _DynamicArchetype(
                            name=name,
                            pyramid_enabled=pyramid,
                            time_exit_enabled=time_exit,
                            stop_model=stop_model,
                            trailing_mode=trailing_mode,
                        )

                        # Register as a type that creates this specific instance
                        cls = type(
                            f"_Factory_{name}",
                            (RiskArchetype,),
                            {
                                "name": name,
                                "_instance": arch_instance,
                                "build_config": lambda self, _inst=arch_instance, **ov: _inst.build_config(**ov),
                            },
                        )

                        registry[name] = cls
                        indicators[name] = _build_indicator_config(entry, stop_model, htf)

    return registry, indicators


def get_factory_archetype_count() -> int:
    """Return the number of valid archetypes the factory would generate."""
    registry, _ = generate_factory_archetypes()
    return len(registry)
