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

from suitetrading.risk.archetypes.roc_fullrisk_pyr import _Arch as RocFullriskPyr
from suitetrading.risk.archetypes.macd_fullrisk_pyr import _Arch as MacdFullriskPyr
from suitetrading.risk.archetypes.ma_x_fullrisk_pyr import _Arch as MaXFullriskPyr
from suitetrading.risk.archetypes.roc_fullrisk_pyr_mtf import _Arch as RocFullriskPyrMtf
from suitetrading.risk.archetypes.roc_fullrisk_time import _Arch as RocFullriskTime
from suitetrading.risk.archetypes.roc_fullrisk_all import _Arch as RocFullriskAll
from suitetrading.risk.archetypes.donchian_fullrisk_pyr import _Arch as DonchianFullriskPyr
from suitetrading.risk.archetypes.ema_fullrisk_pyr import _Arch as EmaFullriskPyr
from suitetrading.risk.archetypes.rsi_fullrisk_pyr import _Arch as RsiFullriskPyr
from suitetrading.risk.archetypes.roc_macd_fullrisk_pyr import _Arch as RocMacdFullriskPyr
from suitetrading.risk.archetypes.roc_ema_fullrisk_pyr import _Arch as RocEmaFullriskPyr
from suitetrading.risk.archetypes.macd_ema_fullrisk_pyr import _Arch as MacdEmaFullriskPyr
from suitetrading.risk.archetypes.roc_adx_fullrisk_pyr import _Arch as RocAdxFullriskPyr
from suitetrading.risk.archetypes.macd_fullrisk_pyr_mtf import _Arch as MacdFullriskPyrMtf
from suitetrading.risk.archetypes.roc_adx_fullrisk_pyr_mtf import _Arch as RocAdxFullriskPyrMtf
from suitetrading.risk.archetypes.macd_fullrisk_time import _Arch as MacdFullriskTime
from suitetrading.risk.archetypes.macd_fullrisk_all import _Arch as MacdFullriskAll
from suitetrading.risk.archetypes.ssl_fullrisk_pyr import _Arch as SslFullriskPyr
from suitetrading.risk.archetypes.wt_fullrisk_pyr import _Arch as WtFullriskPyr
from suitetrading.risk.archetypes.bband_fullrisk_pyr import _Arch as BbandFullriskPyr
from suitetrading.risk.archetypes.roc_fullrisk_htf_macd import _Arch as RocFullriskHtfMacd
from suitetrading.risk.archetypes.roc_fullrisk_pyr_htf_macd import _Arch as RocFullriskPyrHtfMacd
from suitetrading.risk.archetypes.macd_fullrisk_htf_ema import _Arch as MacdFullriskHtfEma

# ── Sprint 8: FTM stop variants ─────────────────────────────────────
from suitetrading.risk.archetypes.roc_fullrisk_pyr_ftm import _Arch as RocFullriskPyrFtm
from suitetrading.risk.archetypes.macd_fullrisk_pyr_ftm import _Arch as MacdFullriskPyrFtm
from suitetrading.risk.archetypes.ma_x_fullrisk_pyr_ftm import _Arch as MaXFullriskPyrFtm
from suitetrading.risk.archetypes.roc_fullrisk_pyr_mtf_ftm import _Arch as RocFullriskPyrMtfFtm
from suitetrading.risk.archetypes.donchian_fullrisk_pyr_ftm import _Arch as DonchianFullriskPyrFtm
from suitetrading.risk.archetypes.ema_fullrisk_pyr_ftm import _Arch as EmaFullriskPyrFtm
from suitetrading.risk.archetypes.rsi_fullrisk_pyr_ftm import _Arch as RsiFullriskPyrFtm
from suitetrading.risk.archetypes.roc_macd_fullrisk_pyr_ftm import _Arch as RocMacdFullriskPyrFtm
from suitetrading.risk.archetypes.roc_ema_fullrisk_pyr_ftm import _Arch as RocEmaFullriskPyrFtm
from suitetrading.risk.archetypes.macd_ema_fullrisk_pyr_ftm import _Arch as MacdEmaFullriskPyrFtm
# ── Sprint 8: Trailing policy variants ──────────────────────────────
from suitetrading.risk.archetypes.roc_fullrisk_pyr_trail_policy import _Arch as RocFullriskPyrTrailPolicy
from suitetrading.risk.archetypes.macd_fullrisk_pyr_trail_policy import _Arch as MacdFullriskPyrTrailPolicy
from suitetrading.risk.archetypes.ma_x_fullrisk_pyr_trail_policy import _Arch as MaXFullriskPyrTrailPolicy
from suitetrading.risk.archetypes.roc_fullrisk_pyr_mtf_trail_policy import _Arch as RocFullriskPyrMtfTrailPolicy
from suitetrading.risk.archetypes.donchian_fullrisk_pyr_trail_policy import _Arch as DonchianFullriskPyrTrailPolicy
# ── Sprint 9: New indicator archetypes ──────────────────────────────
from suitetrading.risk.archetypes.squeeze_fullrisk_pyr import _Arch as SqueezeFullriskPyr
from suitetrading.risk.archetypes.stochrsi_fullrisk_pyr import _Arch as StochrsiFullriskPyr
from suitetrading.risk.archetypes.ichimoku_fullrisk_pyr import _Arch as IchimokuFullriskPyr
from suitetrading.risk.archetypes.obv_fullrisk_pyr import _Arch as ObvFullriskPyr
from suitetrading.risk.archetypes.squeeze_roc_fullrisk_pyr import _Arch as SqueezeRocFullriskPyr
from suitetrading.risk.archetypes.ichimoku_macd_fullrisk_pyr import _Arch as IchimokuMacdFullriskPyr
from suitetrading.risk.archetypes.stochrsi_ema_fullrisk_pyr import _Arch as StochrsiEmaFullriskPyr
from suitetrading.risk.archetypes.squeeze_fullrisk_pyr_mtf import _Arch as SqueezeFullriskPyrMtf
from suitetrading.risk.archetypes.ichimoku_fullrisk_pyr_mtf import _Arch as IchimokuFullriskPyrMtf
from suitetrading.risk.archetypes.obv_roc_fullrisk_pyr import _Arch as ObvRocFullriskPyr
from suitetrading.risk.archetypes.squeeze_ssl_fullrisk_pyr import _Arch as SqueezeSslFullriskPyr
from suitetrading.risk.archetypes.ichimoku_ssl_fullrisk_pyr import _Arch as IchimokuSslFullriskPyr

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
    "roc_fullrisk_pyr": RocFullriskPyr,
    "macd_fullrisk_pyr": MacdFullriskPyr,
    "ma_x_fullrisk_pyr": MaXFullriskPyr,
    "roc_fullrisk_pyr_mtf": RocFullriskPyrMtf,
    "roc_fullrisk_time": RocFullriskTime,
    "roc_fullrisk_all": RocFullriskAll,
    "donchian_fullrisk_pyr": DonchianFullriskPyr,
    "ema_fullrisk_pyr": EmaFullriskPyr,
    "rsi_fullrisk_pyr": RsiFullriskPyr,
    "roc_macd_fullrisk_pyr": RocMacdFullriskPyr,
    "roc_ema_fullrisk_pyr": RocEmaFullriskPyr,
    "macd_ema_fullrisk_pyr": MacdEmaFullriskPyr,
    "roc_adx_fullrisk_pyr": RocAdxFullriskPyr,
    "macd_fullrisk_pyr_mtf": MacdFullriskPyrMtf,
    "roc_adx_fullrisk_pyr_mtf": RocAdxFullriskPyrMtf,
    "macd_fullrisk_time": MacdFullriskTime,
    "macd_fullrisk_all": MacdFullriskAll,
    "ssl_fullrisk_pyr": SslFullriskPyr,
    "wt_fullrisk_pyr": WtFullriskPyr,
    "bband_fullrisk_pyr": BbandFullriskPyr,
    "roc_fullrisk_htf_macd": RocFullriskHtfMacd,
    "roc_fullrisk_pyr_htf_macd": RocFullriskPyrHtfMacd,
    "macd_fullrisk_htf_ema": MacdFullriskHtfEma,
    # Sprint 8: FTM stop variants
    "roc_fullrisk_pyr_ftm": RocFullriskPyrFtm,
    "macd_fullrisk_pyr_ftm": MacdFullriskPyrFtm,
    "ma_x_fullrisk_pyr_ftm": MaXFullriskPyrFtm,
    "roc_fullrisk_pyr_mtf_ftm": RocFullriskPyrMtfFtm,
    "donchian_fullrisk_pyr_ftm": DonchianFullriskPyrFtm,
    "ema_fullrisk_pyr_ftm": EmaFullriskPyrFtm,
    "rsi_fullrisk_pyr_ftm": RsiFullriskPyrFtm,
    "roc_macd_fullrisk_pyr_ftm": RocMacdFullriskPyrFtm,
    "roc_ema_fullrisk_pyr_ftm": RocEmaFullriskPyrFtm,
    "macd_ema_fullrisk_pyr_ftm": MacdEmaFullriskPyrFtm,
    # Sprint 8: Trailing policy variants
    "roc_fullrisk_pyr_trail_policy": RocFullriskPyrTrailPolicy,
    "macd_fullrisk_pyr_trail_policy": MacdFullriskPyrTrailPolicy,
    "ma_x_fullrisk_pyr_trail_policy": MaXFullriskPyrTrailPolicy,
    "roc_fullrisk_pyr_mtf_trail_policy": RocFullriskPyrMtfTrailPolicy,
    "donchian_fullrisk_pyr_trail_policy": DonchianFullriskPyrTrailPolicy,
    # Sprint 9: New indicator archetypes
    "squeeze_fullrisk_pyr": SqueezeFullriskPyr,
    "stochrsi_fullrisk_pyr": StochrsiFullriskPyr,
    "ichimoku_fullrisk_pyr": IchimokuFullriskPyr,
    "obv_fullrisk_pyr": ObvFullriskPyr,
    "squeeze_roc_fullrisk_pyr": SqueezeRocFullriskPyr,
    "ichimoku_macd_fullrisk_pyr": IchimokuMacdFullriskPyr,
    "stochrsi_ema_fullrisk_pyr": StochrsiEmaFullriskPyr,
    "squeeze_fullrisk_pyr_mtf": SqueezeFullriskPyrMtf,
    "ichimoku_fullrisk_pyr_mtf": IchimokuFullriskPyrMtf,
    "obv_roc_fullrisk_pyr": ObvRocFullriskPyr,
    "squeeze_ssl_fullrisk_pyr": SqueezeSslFullriskPyr,
    "ichimoku_ssl_fullrisk_pyr": IchimokuSslFullriskPyr,
}

# ── Phase 5: auto-register new archetypes using fullrisk_pyr config ──
# These archetypes use the same risk template (pyramid enabled, ATR stop,
# signal trailing) and differ only in their indicator combinations,
# which are defined in config/archetypes.py ARCHETYPE_INDICATORS.

def _register_phase5_archetypes() -> None:
    """Auto-register Phase 5 archetypes that lack explicit risk classes."""
    from suitetrading.config.archetypes import ARCHETYPE_INDICATORS
    from suitetrading.risk.archetypes._fullrisk_base import fullrisk_config as _fc

    phase5_names = [
        k for k in ARCHETYPE_INDICATORS
        if k not in ARCHETYPE_REGISTRY and k.endswith("_fullrisk_pyr")
    ]
    for name in phase5_names:
        cls = type(
            f"_Auto_{name}",
            (RiskArchetype,),
            {
                "name": name,
                "build_config": lambda self, _n=name, **ov: _fc(
                    _n, pyramid_enabled=True, overrides=dict(ov),
                ),
            },
        )
        ARCHETYPE_REGISTRY[name] = cls

_register_phase5_archetypes()


# ── Rich archetypes: full risk chain + pyramid ───────────────────────
# Registered explicitly because they don't follow _fullrisk_pyr suffix.

def _register_rich_archetypes() -> None:
    from suitetrading.config.archetypes import ARCHETYPE_INDICATORS
    from suitetrading.risk.archetypes._fullrisk_base import fullrisk_config as _fc

    rich_names = [k for k in ARCHETYPE_INDICATORS if k.startswith("rich_") and k not in ARCHETYPE_REGISTRY]
    for name in rich_names:
        cls = type(
            f"_Auto_{name}",
            (RiskArchetype,),
            {
                "name": name,
                "build_config": lambda self, _n=name, **ov: _fc(
                    _n, pyramid_enabled=True, overrides=dict(ov),
                ),
            },
        )
        ARCHETYPE_REGISTRY[name] = cls

_register_rich_archetypes()


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
