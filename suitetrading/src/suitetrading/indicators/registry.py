"""Central indicator registry.

Provides a single ``INDICATOR_REGISTRY`` mapping from stable string
names to ``Indicator`` subclasses.  Used by ``grid.py`` to enumerate
searchable indicator spaces and by ``engine.py`` to instantiate
indicators on the fly.
"""

from __future__ import annotations

from suitetrading.indicators.base import Indicator

# ── Custom indicators (Pine Script replicas) ──────────────────────────
from suitetrading.indicators.custom.firestorm import Firestorm, FirestormTM
from suitetrading.indicators.custom.ssl_channel import SSLChannel, SSLChannelLow
from suitetrading.indicators.custom.wavetrend import WaveTrendDivergence, WaveTrendReversal

# ── Standard indicators (TA-Lib wrappers) ─────────────────────────────
from suitetrading.indicators.standard.indicators import (
    ATR,
    EMA,
    MACD,
    RSI,
    VWAP,
    BollingerBands,
)

# ── Momentum indicators ───────────────────────────────────────────────
from suitetrading.indicators.standard.momentum import (
    ADXFilter,
    DonchianBreakout,
    MACrossover,
    ROC,
)

# ── Phase 3 indicators ───────────────────────────────────────────────
from suitetrading.indicators.standard.squeeze import SqueezeMomentum
from suitetrading.indicators.standard.stoch_rsi import StochRSI as StochasticRSI
from suitetrading.indicators.standard.ichimoku import IchimokuTKCross
from suitetrading.indicators.standard.obv import OBVTrend

INDICATOR_REGISTRY: dict[str, type[Indicator]] = {
    # Custom
    "firestorm": Firestorm,
    "firestorm_tm": FirestormTM,
    "ssl_channel": SSLChannel,
    "ssl_channel_low": SSLChannelLow,
    "wavetrend_reversal": WaveTrendReversal,
    "wavetrend_divergence": WaveTrendDivergence,
    # Standard
    "rsi": RSI,
    "ema": EMA,
    "macd": MACD,
    "atr": ATR,
    "vwap": VWAP,
    "bollinger_bands": BollingerBands,
    # Momentum
    "roc": ROC,
    "donchian": DonchianBreakout,
    "adx_filter": ADXFilter,
    "ma_crossover": MACrossover,
    # Phase 3
    "squeeze": SqueezeMomentum,
    "stoch_rsi": StochasticRSI,
    "ichimoku": IchimokuTKCross,
    "obv": OBVTrend,
}


def get_indicator(name: str) -> Indicator:
    """Instantiate an indicator by registry name."""
    cls = INDICATOR_REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"Unknown indicator: {name!r}. Available: {sorted(INDICATOR_REGISTRY)}")
    return cls()
