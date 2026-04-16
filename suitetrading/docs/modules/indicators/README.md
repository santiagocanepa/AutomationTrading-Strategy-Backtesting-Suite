# Indicators Module

## Overview
- 38 indicators across 6 categories, all implementing the `Indicator` ABC (`base.py`).
- Each indicator exposes `compute(df, **params) -> pd.Series[bool]` and `params_schema()` for Optuna/grid auto-enumeration.
- Signal combination replicates Pine Script's EXCL/OPC/DESACT three-state logic via `signal_combiner.py`.

## Categories

| Category     | Count | Registry keys (examples)                                                                 |
|--------------|-------|------------------------------------------------------------------------------------------|
| custom       | 7     | `firestorm`, `firestorm_tm`, `ssl_channel`, `ssl_channel_low`, `wavetrend_reversal`, `wavetrend_divergence`, `ash` |
| standard     | 15    | `ema`, `rsi`, `macd`, `bollinger_bands`, `squeeze`, `stoch_rsi`, `ichimoku`, `obv`, `adx_filter`, `ma_crossover`, `donchian`, `roc`, `atr`, `vwap`, `momentum_divergence` |
| regime       | 3     | `volatility_regime`, `volume_spike`, `cs_momentum`                                       |
| cross_asset  | 4     | `cross_asset_momentum`, `cross_asset_momentum_inv`, `vol_scaled_momentum`, `macro_regime_signal` |
| futures      | 5     | `funding_rate`, `oi_divergence`, `long_short_ratio`, `taker_volume`, `basis`             |
| macro        | 4     | `vrp`, `yield_curve`, `hurst`, `credit_spread`                                           |

## Files

| File                              | Responsibility                                                         | LOC |
|-----------------------------------|------------------------------------------------------------------------|-----|
| `base.py`                         | `Indicator` ABC, `IndicatorState` enum, `_hold_bars` helper            |  83 |
| `registry.py`                     | `INDICATOR_REGISTRY` dict + `get_indicator(name)` factory              | 128 |
| `signal_combiner.py`              | `combine_signals()` — EXCL/OPC/DESACT + majority-vote modes            | 100 |
| `mtf.py`                          | `resolve_timeframe`, `resample_ohlcv`, `align_to_base`                 |  67 |
| `regime.py`                       | Market-regime helpers used by regime/volatility indicators             | 224 |
| `custom/firestorm.py`             | Firestorm + FirestormTM (Pine Script replicas)                         | 216 |
| `custom/ssl_channel.py`           | SSLChannel + SSLChannelLow                                             | 211 |
| `custom/wavetrend.py`             | WaveTrendReversal + WaveTrendDivergence                                | 384 |
| `custom/ash.py`                   | ASH (Absolute Strength Histogram)                                      | 153 |
| `standard/indicators.py`          | EMA, RSI, MACD, ATR, VWAP, BollingerBands                             | 202 |
| `standard/momentum.py`            | ROC, DonchianBreakout, ADXFilter, MACrossover                          | 188 |
| `standard/squeeze.py`             | SqueezeMomentum                                                        |  77 |
| `standard/stoch_rsi.py`           | StochasticRSI                                                          |  93 |
| `standard/ichimoku.py`            | IchimokuTKCross                                                        |  71 |
| `standard/obv.py`                 | OBVTrend                                                               |  56 |
| `standard/volatility_regime.py`   | VolatilityRegime                                                       |  80 |
| `standard/volume_anomaly.py`      | VolumeSpike                                                            |  65 |
| `standard/momentum_divergence.py` | MomentumDivergence                                                     |  76 |
| `standard/cs_momentum.py`         | CrossSectionalMomentum                                                 |  60 |
| `cross_asset/momentum.py`         | CrossAssetMomentum, Inverse, VolScaled, MacroRegime                    | 201 |
| `futures/funding_rate.py`         | FundingRate                                                            |  74 |
| `futures/open_interest.py`        | OIDivergence + LongShortRatio                                          | 128 |
| `futures/taker_volume.py`         | TakerVolumeIndicator                                                   |  62 |
| `futures/basis.py`                | BasisIndicator                                                         |  67 |
| `macro/vrp.py`                    | VRPIndicator (volatility risk premium)                                 |  75 |
| `macro/yield_curve.py`            | YieldCurveIndicator                                                    |  72 |
| `macro/hurst.py`                  | HurstIndicator                                                         | 110 |
| `macro/credit_spread.py`          | CreditSpreadIndicator                                                  |  77 |

## Three-State Classification

Every indicator instance carries an `IndicatorState` that controls how it participates in `combine_signals()`:

| State          | Behavior                                                                |
|----------------|-------------------------------------------------------------------------|
| `Excluyente`   | AND gate — all EXCL indicators must be `True` for entry                 |
| `Opcional`     | Vote pool — at least `num_optional_required` OPC indicators must be `True` |
| `Desactivado`  | Skipped entirely — not evaluated, not counted                           |

Two combination modes:
- **`excluyente`** (default): EXCL AND-chain, then check optional count ≥ threshold.
- **`majority`**: ignores EXCL/OPC distinction; entry when ≥ N active indicators agree (`N = ceil(active/2)` by default).

## `rich_stock` Entry Indicators (11)

These are the 11 indicators active in the `rich_stock` archetype:

```
ssl_channel, squeeze, firestorm, wavetrend_reversal,
ma_crossover, macd, bollinger_bands, adx_filter, rsi, obv, ash
```

## Multi-Timeframe (MTF)

`mtf.py` exposes three functions:

| Function              | Purpose                                                          |
|-----------------------|------------------------------------------------------------------|
| `resolve_timeframe`   | Maps `"grafico"`, `"1 superior"`, `"2 superiores"` → literal TF |
| `resample_ohlcv`      | Resample base OHLCV to a higher TF (delegates to `OHLCVResampler`) |
| `align_to_base`       | Forward-fill a higher-TF series onto the base-TF index          |

TF resolution ladder: `1→3→5→15→30→45→60→240→D→W→M`

## Signal Flow

See [signal_flow.md](../../signal_flow.md) for the full entry-signal pipeline (data → indicators → combine → engine).

## Tests

```bash
# From suitetrading/
pytest tests/indicators/ -v
```

15 test files cover: `ash`, `firestorm`, `ichimoku`, `mtf`, `obv`, `regime`, `signal_combiner`, `ssl_channel`, `squeeze`, `standard_indicators`, `stoch_rsi`, `tier1_signals`, `wavetrend`, `macro_indicators`.
