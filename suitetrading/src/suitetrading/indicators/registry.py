"""Central indicator registry.

Provides a single ``INDICATOR_REGISTRY`` mapping from stable string
names to ``Indicator`` subclasses.  Used by ``grid.py`` to enumerate
searchable indicator spaces and by ``engine.py`` to instantiate
indicators on the fly.
"""

from __future__ import annotations

from suitetrading.indicators.base import Indicator

# ── Custom indicators (Pine Script replicas) ──────────────────────────
from suitetrading.indicators.custom.ash import ASH
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

# ── Regime & anomaly indicators ──────────────────────────────────────
from suitetrading.indicators.standard.volatility_regime import VolatilityRegime
from suitetrading.indicators.standard.volume_anomaly import VolumeSpike
from suitetrading.indicators.standard.momentum_divergence import MomentumDivergence

# ── Futures/derivatives indicators ───────────────────────────────────
from suitetrading.indicators.futures.basis import BasisIndicator
from suitetrading.indicators.futures.funding_rate import FundingRate
from suitetrading.indicators.futures.open_interest import LongShortRatio, OIDivergence
from suitetrading.indicators.futures.taker_volume import TakerVolumeIndicator

# ── Cross-sectional indicators ──────────────────────────────────────
from suitetrading.indicators.standard.cs_momentum import CrossSectionalMomentum

# ── Cross-asset momentum ──────────────────────────────────────────
from suitetrading.indicators.cross_asset.momentum import (
    CrossAssetMomentum,
    CrossAssetMomentumInverse,
    MacroRegimeSignal,
    VolScaledMomentum,
)

# ── Macro indicators ────────────────────────────────────────────────
from suitetrading.indicators.macro.credit_spread import CreditSpreadIndicator
from suitetrading.indicators.macro.hurst import HurstIndicator
from suitetrading.indicators.macro.vrp import VRPIndicator
from suitetrading.indicators.macro.yield_curve import YieldCurveIndicator

INDICATOR_REGISTRY: dict[str, type[Indicator]] = {
    # Custom
    "ash": ASH,
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
    # Regime & anomaly
    "volatility_regime": VolatilityRegime,
    "volume_spike": VolumeSpike,
    "momentum_divergence": MomentumDivergence,
    # Futures/derivatives
    "funding_rate": FundingRate,
    "oi_divergence": OIDivergence,
    "long_short_ratio": LongShortRatio,
    # Macro
    "vrp": VRPIndicator,
    "yield_curve": YieldCurveIndicator,
    "credit_spread": CreditSpreadIndicator,
    "hurst": HurstIndicator,
    # Futures tier-1
    "taker_volume": TakerVolumeIndicator,
    "basis": BasisIndicator,
    # Cross-sectional
    "cs_momentum": CrossSectionalMomentum,
    # Cross-asset momentum
    "cross_asset_momentum": CrossAssetMomentum,
    "cross_asset_momentum_inv": CrossAssetMomentumInverse,
    "vol_scaled_momentum": VolScaledMomentum,
    "macro_regime_signal": MacroRegimeSignal,
}


def get_indicator(name: str) -> Indicator:
    """Instantiate an indicator by registry name."""
    cls = INDICATOR_REGISTRY.get(name)
    if cls is None:
        raise KeyError(f"Unknown indicator: {name!r}. Available: {sorted(INDICATOR_REGISTRY)}")
    return cls()
