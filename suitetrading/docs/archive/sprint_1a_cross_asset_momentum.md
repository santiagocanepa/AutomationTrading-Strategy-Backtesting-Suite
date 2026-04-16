# Sprint 1A — Cross-Asset Momentum Indicator

**Fecha:** 2026-03-24
**Duración estimada:** 3-4 días
**Prerequisito:** Datos de stocks + crypto + macro en `data/raw/`
**Referencia académica:** Moskowitz, Ooi & Pedersen (2012) "Time Series Momentum"

---

## Objetivo

Implementar y medir IC de un indicador de cross-asset momentum: el retorno reciente de un asset de referencia predice el retorno futuro de un asset target.

## Tesis

Los mercados están interconectados. Cuando SPY sube, crypto tiende a seguir con lag. Cuando VIX sube, risk assets caen. Cuando BTC sube, altcoins siguen. Este lag temporal crea IC > 0.03 documentado en literatura.

## Pares a testear

### Crypto leader-follower
| Reference | Target | Lógica |
|-----------|--------|--------|
| BTC retorno 24h | ETH, SOL, BNB, AVAX | BTC lidera el mercado crypto |
| ETH retorno 24h | SOL, BNB, AVAX | ETH lidera altcoins DeFi |

### Cross-market
| Reference | Target | Lógica |
|-----------|--------|--------|
| SPY retorno 1d | BTC, ETH | Risk-on flows de equities a crypto |
| VIX nivel/cambio | Todos (inverso) | Fear → risk-off |
| TLT retorno 1d | SPY, QQQ (inverso) | Flight to safety |
| DXY nivel | BTC, ETH (inverso) | Dollar strength → crypto weakness |

### Stock sector rotation
| Reference | Target | Lógica |
|-----------|--------|--------|
| XLE retorno 1w | SPY, XLK | Sector rotation signal |
| QQQ retorno 1d | AAPL, NVDA, TSLA | Index leads constituents |

## Implementación

### 1. Indicator class

```python
# src/suitetrading/indicators/cross_asset/cross_asset_momentum.py

class CrossAssetMomentum(Indicator):
    """Cross-asset momentum: reference asset return predicts target asset direction.

    Requires pre-merged DataFrame with column '{reference_col}' containing
    the reference asset's close price, resampled and aligned to target index.
    """

    def params_schema(self):
        return {
            "reference_col": {"type": "str", "default": "ref_close"},
            "lookback": {"type": "int", "min": 1, "max": 60, "default": 24},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 3},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
        }

    def compute(self, df, **params):
        ref = df[params["reference_col"]]
        ret = ref.pct_change(params["lookback"])
        if params["mode"] == "bullish":
            signal = ret > 0
        else:
            signal = ret < 0
        return _hold_bars(signal, params.get("hold_bars", 3))
```

### 2. Data preparation

El IC scanner necesita un DataFrame que contenga TANTO el OHLCV del target como el close del reference. Opciones:

**Opción A (preferida):** Pre-merge en el scanner script
```python
# En el scanner, antes de scan_indicator():
ref_raw = store.read(exchange, ref_symbol, "1m")
ref_resampled = resampler.resample(ref_raw, tf, base_tf="1m")
ohlcv["ref_close"] = ref_resampled["close"].reindex(ohlcv.index, method="ffill")
```

**Opción B:** Indicator carga sus propios datos (más acoplado, menos preferible)

### 3. IC Scanner script

Nuevo script `step1_ic_scanner_cross_asset.py` que:
1. Define la lista de pares (reference, target)
2. Para cada par: merge reference close → target OHLCV
3. Corre `scan_indicator("cross_asset_momentum", ohlcv, ...)`
4. Genera CSV con resultados

### 4. Archetypes

Si IC > 0.03, crear archetypes:
- `cross_momentum_fullrisk_pyr` — entry: cross_asset_momentum, exit: rsi, trail: ssl_channel
- `cross_momentum_bband_fullrisk_pyr` — entry: cross_asset_momentum + bollinger_bands (ensemble)
- `cross_momentum_regime_fullrisk_pyr` — entry: cross_asset_momentum + volatility_regime

## Criterio de éxito

| Métrica | Threshold |
|---------|-----------|
| IC OOS promedio (across targets) | > 0.03 |
| % de pares con IC > 0.02 | > 50% |
| FDR significant | > 3 pares |
| Consistencia temporal (multi-horizon) | IC no decae > 50% en h=5 |

## Riesgos

1. **Lag insuficiente:** Si los mercados están demasiado sincronizados, no hay ventana de predicción
2. **Datos desalineados:** Crypto 24/7 vs stocks market hours. Resamplear a daily resuelve parcialmente
3. **Régimen-dependiente:** Cross-asset momentum puede funcionar solo en risk-on/risk-off extremos
4. **Look-ahead bias:** Asegurar que reference close es ANTERIOR al target bar (gap temporal)

## Outputs esperados

- `artifacts/research/cross_asset_ic/edge_summary.csv` — IC por par × TF × dir
- `artifacts/research/cross_asset_ic/analysis/finalists.csv` — pares con IC > 0.03
- Si IC pasa: nuevos archetypes listos para discovery pipeline
