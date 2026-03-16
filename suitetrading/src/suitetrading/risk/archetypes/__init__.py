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
from suitetrading.risk.archetypes.momentum_trend import MomentumTrend
from suitetrading.risk.archetypes.donchian_simple import DonchianSimple
from suitetrading.risk.archetypes.roc_simple import ROCSimple
from suitetrading.risk.archetypes.ma_cross_simple import _Arch as MACrossSimple
from suitetrading.risk.archetypes.adx_simple import _Arch as ADXSimple
from suitetrading.risk.archetypes.roc_adx import _Arch as ROCAdx
from suitetrading.risk.archetypes.roc_ma import _Arch as ROCMA
from suitetrading.risk.archetypes.roc_ssl import _Arch as ROCSSL
from suitetrading.risk.archetypes.donchian_adx import _Arch as DonchianADX
from suitetrading.risk.archetypes.ma_ssl import _Arch as MaSsl
from suitetrading.risk.archetypes.ma_adx import _Arch as MaAdx
from suitetrading.risk.archetypes.donchian_ssl import _Arch as DonchianSsl
from suitetrading.risk.archetypes.donchian_roc import _Arch as DonchianRoc
from suitetrading.risk.archetypes.triple_momentum import _Arch as TripleMomentum
from suitetrading.risk.archetypes.roc_fire import _Arch as RocFire
from suitetrading.risk.archetypes.ssl_roc import _Arch as SslRoc
from suitetrading.risk.archetypes.ssl_ma import _Arch as SslMa
from suitetrading.risk.archetypes.fire_roc import _Arch as FireRoc
from suitetrading.risk.archetypes.fire_ma import _Arch as FireMa
from suitetrading.risk.archetypes.wt_roc import _Arch as WtRoc
from suitetrading.risk.archetypes.macd_simple import _Arch as MacdSimple
from suitetrading.risk.archetypes.macd_roc import _Arch as MacdRoc
from suitetrading.risk.archetypes.macd_ssl import _Arch as MacdSsl
from suitetrading.risk.archetypes.macd_adx import _Arch as MacdAdx
from suitetrading.risk.archetypes.ema_simple import _Arch as EmaSimple
from suitetrading.risk.archetypes.ema_roc import _Arch as EmaRoc
from suitetrading.risk.archetypes.ema_adx import _Arch as EmaAdx
from suitetrading.risk.archetypes.roc_donch_ssl import _Arch as RocDonchSsl
from suitetrading.risk.archetypes.roc_ma_ssl import _Arch as RocMaSsl
from suitetrading.risk.archetypes.macd_roc_adx import _Arch as MacdRocAdx
from suitetrading.risk.archetypes.ema_roc_adx import _Arch as EmaRocAdx

from suitetrading.risk.archetypes.roc_mtf import _Arch as RocMtf
from suitetrading.risk.archetypes.ma_cross_mtf import _Arch as MaCrossMtf
from suitetrading.risk.archetypes.macd_mtf import _Arch as MacdMtf
from suitetrading.risk.archetypes.roc_ssl_mtf import _Arch as RocSslMtf
from suitetrading.risk.archetypes.ema_roc_mtf import _Arch as EmaRocMtf

from suitetrading.risk.archetypes.roc_mtf_longopt import _Arch as RocMtfLongopt
from suitetrading.risk.archetypes.roc_shortopt import _Arch as RocShortopt
from suitetrading.risk.archetypes.macd_mtf_longopt import _Arch as MacdMtfLongopt
from suitetrading.risk.archetypes.macd_shortopt import _Arch as MacdShortopt
from suitetrading.risk.archetypes.ma_x_ssl_longopt import _Arch as MaXSslLongopt
from suitetrading.risk.archetypes.ema_mtf_longopt import _Arch as EmaMtfLongopt

from suitetrading.risk.archetypes.rsi_roc import _Arch as RsiRoc
from suitetrading.risk.archetypes.rsi_mtf import _Arch as RsiMtf
from suitetrading.risk.archetypes.bband_roc import _Arch as BbandRoc
from suitetrading.risk.archetypes.wt_filter_roc import _Arch as WtFilterRoc
from suitetrading.risk.archetypes.roc_mtf_roc import _Arch as RocMtfRoc
from suitetrading.risk.archetypes.macd_roc_mtf import _Arch as MacdRocMtf

from suitetrading.risk.archetypes.donchian_mtf import _Arch as DonchianMtf
from suitetrading.risk.archetypes.donchian_roc_mtf import _Arch as DonchianRocMtf
from suitetrading.risk.archetypes.ema_adx_mtf import _Arch as EmaAdxMtf
from suitetrading.risk.archetypes.roc_macd_mtf import _Arch as RocMacdMtf
from suitetrading.risk.archetypes.ssl_adx_mtf import _Arch as SslAdxMtf
from suitetrading.risk.archetypes.triple_mtf import _Arch as TripleMtf

from suitetrading.risk.archetypes.roc_fullrisk import _Arch as RocFullrisk
from suitetrading.risk.archetypes.roc_fullrisk_mtf import _Arch as RocFullriskMtf
from suitetrading.risk.archetypes.macd_fullrisk import _Arch as MacdFullrisk
from suitetrading.risk.archetypes.ma_x_fullrisk import _Arch as MaXFullrisk
from suitetrading.risk.archetypes.ema_fullrisk_mtf import _Arch as EmaFullriskMtf

ARCHETYPE_REGISTRY: dict[str, type[RiskArchetype]] = {
    "legacy_firestorm": LegacyFirestormProfile,
    "trend_following": TrendFollowing,
    "mean_reversion": MeanReversion,
    "mixed": Mixed,
    "pyramidal": PyramidalScaling,
    "grid_dca": GridDCA,
    "momentum": Momentum,
    "breakout": Breakout,
    "momentum_trend": MomentumTrend,
    "donchian_simple": DonchianSimple,
    "roc_simple": ROCSimple,
    "ma_cross_simple": MACrossSimple,
    "adx_simple": ADXSimple,
    "roc_adx": ROCAdx,
    "roc_ma": ROCMA,
    "roc_ssl": ROCSSL,
    "donchian_adx": DonchianADX,
    "ma_ssl": MaSsl,
    "ma_adx": MaAdx,
    "donchian_ssl": DonchianSsl,
    "donchian_roc": DonchianRoc,
    "triple_momentum": TripleMomentum,
    "roc_fire": RocFire,
    "ssl_roc": SslRoc,
    "ssl_ma": SslMa,
    "fire_roc": FireRoc,
    "fire_ma": FireMa,
    "wt_roc": WtRoc,
    "macd_simple": MacdSimple,
    "macd_roc": MacdRoc,
    "macd_ssl": MacdSsl,
    "macd_adx": MacdAdx,
    "ema_simple": EmaSimple,
    "ema_roc": EmaRoc,
    "ema_adx": EmaAdx,
    "roc_donch_ssl": RocDonchSsl,
    "roc_ma_ssl": RocMaSsl,
    "macd_roc_adx": MacdRocAdx,
    "ema_roc_adx": EmaRocAdx,
    "roc_mtf": RocMtf,
    "ma_cross_mtf": MaCrossMtf,
    "macd_mtf": MacdMtf,
    "roc_ssl_mtf": RocSslMtf,
    "ema_roc_mtf": EmaRocMtf,
    "roc_mtf_longopt": RocMtfLongopt,
    "roc_shortopt": RocShortopt,
    "macd_mtf_longopt": MacdMtfLongopt,
    "macd_shortopt": MacdShortopt,
    "ma_x_ssl_longopt": MaXSslLongopt,
    "ema_mtf_longopt": EmaMtfLongopt,
    "rsi_roc": RsiRoc,
    "rsi_mtf": RsiMtf,
    "bband_roc": BbandRoc,
    "wt_filter_roc": WtFilterRoc,
    "roc_mtf_roc": RocMtfRoc,
    "macd_roc_mtf": MacdRocMtf,
    "donchian_mtf": DonchianMtf,
    "donchian_roc_mtf": DonchianRocMtf,
    "ema_adx_mtf": EmaAdxMtf,
    "roc_macd_mtf": RocMacdMtf,
    "ssl_adx_mtf": SslAdxMtf,
    "triple_mtf": TripleMtf,
    "roc_fullrisk": RocFullrisk,
    "roc_fullrisk_mtf": RocFullriskMtf,
    "macd_fullrisk": MacdFullrisk,
    "ma_x_fullrisk": MaXFullrisk,
    "ema_fullrisk_mtf": EmaFullriskMtf,
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
