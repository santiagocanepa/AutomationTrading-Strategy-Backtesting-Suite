# Research Methodology: Multi-Timeframe Edge Mapping

**Fecha inicio:** 2026-03-22
**Estado:** En progreso — Paso 1

---

## 1. Por qué este documento existe

Después de ~4,000 WFO studies y meses de trabajo (ver [Research Report](research_report.md) para resultados completos), el portfolio final tiene Sharpe anualizado de 0.39 — por debajo del benchmark CTA (0.80-1.20). El DSR falla: el edge diario no es estadísticamente distinguible del ruido.

**¿Por qué?** Porque el research anterior saltó directamente a backtest + risk optimization sin medir la calidad CRUDA de las señales. Nunca supimos si ROC tiene un IC de 0.03 o de 0.003 en cada timeframe. Nunca medimos cuántas barras persiste el edge cross-TF. Nunca probamos las 33×6 combinaciones indicator×TF de forma sistemática.

Este documento define la metodología de research actual: por capas, midiendo edge crudo primero, backtesting después.

---

## 2. El problema: la dimensionalidad real

El espacio de búsqueda completo tiene estas dimensiones:

| Dimensión | Valores posibles | Ejemplo |
|-----------|-----------------|---------|
| Indicator de entrada | 33 registrados | ROC, MACD, SSL, VRP, Hurst... |
| Params del indicator | 300-600 por indicator | ROC: period(1-30) × mode(2) × hold_bars(1-10) |
| Timeframe operado | 6 | 1W, 1D, 4h, 1h, 15m, 5m |
| Timeframes de confirmación (HTF) | 1-3 layers | 1D→4h, 1W→1D→4h, etc. |
| Indicator HTF | 33 | Puede ser distinto al del TF operado |
| Asset | 15+ | SPY, QQQ, BTC, ETH, SOL... |
| Direction | 2 | long, short |
| Risk params | 8 params, ~87M combos | stop, sizing, TP, BE, pyramid(×3), time_exit |
| Combination mode | 3 | excluyente, opcional, majority |

**Espacio total bruto:** ~52 mil millones de combinaciones por study (1 indicator × 1 asset × 1 TF × 1 direction). Multiplicado por todas las dimensiones: ~3.12 × 10¹³ combinaciones totales. En cuatrillones si incluimos cross-TF.

No se puede explorar exhaustivamente con fuerza bruta. Se explora por capas, cada capa reduciendo inteligentemente el espacio de la siguiente.

---

## 3. Hallazgos previos que informan la metodología

> Los datos completos de ~4,000 WFO studies están en [Research Report](research_report.md) (secciones 4-9). Aquí solo las **implicaciones** que determinan el diseño de esta metodología.

| Hallazgo (detalle en Research Report) | Implicación para esta metodología |
|---------------------------------------|----------------------------------|
| IC de señales es 49-53% — coin flip. El edge viene de la risk chain (§9.1, §6) | Medir IC crudo (Paso 1) es esencial: separar IC=0.03 (explotable) de IC=0.005 (ruido irrecuperable) |
| MTF +44% PBO pass rate vs single-TF (3,778 studies), pero solo se probó `ma_crossover` en 1D | Explorar cascadas cross-TF completas es la mayor oportunidad no explotada |
| PBO < 0.20 por indicator mide overfit de indicator+risk combinados, no del indicator solo | Paso 1 mide edge del indicator AISLADO, sin risk management |
| Macro indicators (VRP, yield_curve, hurst) funcionan como filtros HTF, no como entries | Macro se evalúa en 1W/1D como filtro, nunca como entry en TFs menores |
| Los 8 risk params son interdependientes — no se pueden optimizar de forma marginal | Risk space se explora COMPLETO (8 params juntos), pero solo DESPUÉS de saber qué indicators usar (Pasos 3, 5, 6) |

---

## 4. Filosofía del research

### 4.1. No buscamos estrategias. Construimos un MAPA.

El output final no es "20 estrategias para un portfolio". Es un mapa multidimensional que responde:

- ¿Qué indicadores tienen edge real (IC > 0.02) en cada timeframe?
- ¿Cuánto persiste ese edge en timeframes inferiores?
- ¿Qué combinaciones cross-TF amplifican el edge?
- ¿Qué configuración de risk management maximiza el Sharpe para cada combo?

Con el mapa, construir portfolios es trivial: seleccionar puntos del mapa que diversifiquen entre sí.

### 4.2. De arriba hacia abajo

Las señales de timeframes mayores tienen mayor signal-to-noise ratio y persisten muchas barras en TFs menores. Una señal de 4h que dice "bullish" permanece activa durante 16-48 barras de 15 minutos. Eso crea una VENTANA donde las señales del TF menor tienen mayor probabilidad de éxito.

La cascada natural es:
```
Semanal (régimen) → Diario (dirección) → 4h (timing) → 1h/15m (entry) → 5m (precisión)
```

Cada layer filtra: si el semanal dice "bear", no importa lo que diga el 5 minutos — no compramos. Esto reduce drásticamente los trades falsos y es la base de cómo operan los traders institucionales.

### 4.3. Edge puro primero, risk management después

Medir IC y hit rate SIN risk management revela el edge INFORMACIONAL del indicador. Si un indicador tiene IC=0.001, ningún trailing stop o pyramiding va a convertirlo en una estrategia rentable. Pero si tiene IC=0.03 (que parece poco pero con risk management bien calibrado puede dar Sharpe > 1.0), entonces la optimización de risk tiene sentido.

El research anterior mezclaba ambas cosas: corría Optuna optimizando indicador + risk simultáneamente. Eso produce finalists donde no sabemos si el edge viene del indicador o del risk. Y cuando el risk management "crea" edge a partir de ruido (IC ≈ 0), los resultados no son reproducibles forward.

### 4.4. Sin reducción prematura

No descartamos nada sin evidencia. Los 33 indicadores se evalúan en los 3 TFs iniciales. Si wavetrend tiene IC=0.04 en 1D pero IC=-0.01 en 4h, eso es un hallazgo valioso: wavetrend es un indicador de 1D, no de 4h. Descartarlo "porque es retail" sería un sesgo.

### 4.5. El research puede llevar semanas o meses

Cada paso genera datos, se analiza, se documenta, y recién después se define el paso siguiente con detalle. No hay timeline fijo. La rigurosidad es el criterio, no la velocidad. Un hallazgo sólido en el Paso 1 vale más que completar los 7 pasos de forma superficial.

---

## 5. Arquitectura de pasos

### Visión general

```
┌──────────────────────────────────────────────────────────────────┐
│ PASO 1: INDICATOR EDGE MAP (1W, 1D, 4h)                         │
│   33 indicators × 3 TFs × 15 assets × 2 directions              │
│   Métricas: IC, hit rate, frequency, persistence                 │
│   Output: AFFINITY MATRIX (qué indicator tiene edge en qué TF)  │
│   NO hay backtesting, NO hay risk management                     │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASO 2: SIGNAL PERSISTENCE                                       │
│   Para indicators con edge en Paso 1:                            │
│   ¿cuántas barras del TF inferior persiste el edge?              │
│   Ejemplo: ROC fires en 4h → medir return acumulado              │
│   en las siguientes 4, 8, 16, 48 barras de 15m                  │
│   Output: PERSISTENCE MAP (signal half-life por TF cascade)      │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASO 3: CROSS-TF COMBINATIONS → OPERAR EN 4h                    │
│   Mejores indicators de 1W/1D como filtros (EXCLUYENTE/OPCIONAL) │
│   + mejores indicators de 4h como entry                          │
│   AQUÍ se introduce backtesting + WFO + PBO + DSR               │
│   AQUÍ se explora risk space completo (8 params) por primera vez │
│   Output: estrategias de 4h validadas con cascada HTF            │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASO 4: INDICATOR EDGE MAP (15m, 5m, 3m) — CONDICIONADO         │
│   Repetir medición de IC/hit rate pero SOLO cuando la señal      │
│   de 4h o 1D (del Paso 3) esté activa                           │
│   "¿RSI en 15m tiene edge CUANDO ROC 4h dice bullish?"          │
│   Esto es fundamentalmente diferente al Paso 1 porque el edge   │
│   de un indicator en TF menor DEPENDE del contexto HTF           │
│   Output: AFFINITY MATRIX condicionada por HTF signals           │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASO 5: CROSS-TF COMBINATIONS → OPERAR EN 15m/5m                │
│   Cascada completa: 1W/1D/4h como filtros (ya reducidos)         │
│   + mejores indicators de 15m/5m como entry                      │
│   Backtesting + WFO + risk space completo                        │
│   Una señal de 4h que persiste 48 barras de 5m crea una VENTANA │
│   donde el indicator de 5m tiene permiso para entrar             │
│   Output: estrategias de 15m/5m con cascada de TFs              │
│                                                                  │
│   NOTA: a veces NO conviene condicionar en una TF intermedia.    │
│   Ejemplo: 1D signal + 5m entry puede funcionar mejor que        │
│   1D + 1h + 5m. Hay que probar con y sin cada layer intermedio.  │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASO 6: RISK SPACE EXHAUSTIVO                                    │
│   Solo para las mejores combinaciones cross-TF de Pasos 3 y 5   │
│   8 params de risk con Optuna TPE (2000-5000 trials)             │
│   Los 8 params se exploran JUNTOS (interdependencia)             │
│   Sensitivity analysis ±20% para filtrar finalists frágiles      │
│   Output: estrategias con risk optimizado + robustez verificada  │
│                                                                  │
│   NOTA CRÍTICA: el risk space óptimo DEPENDE del cross-TF combo. │
│   Un entry de 5m con filtro de 4h necesita stops y TPs           │
│   completamente diferentes a un entry de 4h sin filtro.          │
│   No hay "un risk config óptimo universal".                      │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│ PASO 7: PORTFOLIOS POR TIMEFRAME                                 │
│   Con cientos de estrategias robustas de múltiples TFs:          │
│   - Portfolio de 4h (swing trading, menos operaciones)            │
│   - Portfolio de 15m (intraday, más operaciones)                  │
│   - Portfolio de 5m (scalping, máxima frecuencia)                 │
│   Cada portfolio usa greedy forward selection + rolling validation│
│   Los portfolios de TFs menores INCLUYEN los filtros HTF          │
│   Output: portfolios validados, listos para paper trading         │
└──────────────────────────────────────────────────────────────────┘
```

### Principio de reducción progresiva

Cada paso reduce el espacio para el siguiente:

| Paso | Input | Output | Reducción |
|------|-------|--------|-----------|
| 1 | 33 ind × 3 TFs | ~10-15 ind con edge por TF | ~60-70% eliminados |
| 2 | 10-15 ind con edge | ~8-10 con persistencia cross-TF | ~30% eliminados |
| 3 | 8-10 combos × 8 risk params | ~20-50 estrategias 4h validadas | WFO+PBO+DSR filtra |
| 4 | 33 ind × 3 TFs menores (condicionados) | ~8-12 ind con edge condicionado | Filtro más estricto que Paso 1 |
| 5 | 8-12 combos × cascada HTF × risk | ~20-50 estrategias 15m/5m | WFO+PBO+DSR filtra |
| 6 | Mejores combos × 87M risk combos | Finalists con sensitivity < 50% | Robustez filtra |
| 7 | Todos los finalists | 3 portfolios (4h, 15m, 5m) | Diversificación selecciona |

---

## 6. PASO 1: Indicator Edge Map (1W, 1D, 4h)

### 6.1. Objetivo

Medir el edge CRUDO de cada uno de los 33 indicadores registrados, en 3 timeframes (1W, 1D, 4h), para cada asset y dirección. **Sin backtest, sin risk management, sin optimización de parámetros.** Solo: "cuando este indicador dice entry con parámetros default, ¿el precio se mueve a favor?"

### 6.2. Por qué parámetros default

Si optimizáramos los params por asset/TF, estaríamos haciendo overfitting al medir el edge. Params default (los que define cada indicador en `params_schema()["default"]`) son la línea base neutra. Si un indicador NO tiene edge con params default, puede que los tenga con params optimizados — pero eso se descubrirá en pasos posteriores (3, 5, 6) cuando Optuna optimice. Lo que Paso 1 identifica es: ¿tiene ALGÚN edge inherente en este timeframe, sin torturar los datos?

### 6.3. Métricas a computar

Para cada combinación (indicator, TF, asset, direction):

| Métrica | Qué mide | Fórmula | Umbral "tiene edge" |
|---------|----------|---------|---------------------|
| **IC** | Correlación signal-return | `spearman(signal_boolean, forward_return_1bar)` | > 0.02 |
| **Hit Rate** | % señales correctas | `P(ret > 0 \| signal=True, direction=long)` | > 52% |
| **Avg Forward Return** | Retorno promedio post-señal | `mean(ret[signal=True])` | > 0 con p < 0.05 |
| **Signal Frequency** | Señales por mes | `count(signal=True) / n_months` | > 5/mes para operabilidad |
| **Edge Ratio** | Calidad neta del edge | `(hit_rate × avg_win) / ((1-hit_rate) × avg_loss)` | > 1.05 |
| **Temporal Stability** | IC rolling consistente | `% de ventanas de 3 meses con IC > 0` | > 60% |
| **Statistical Significance** | p-value del IC | `t-test(IC_rolling_windows)` | p < 0.05 |

**Forward return**: Para longs, `close[t+1] / close[t] - 1`. Para shorts, inverso. Se usa 1 bar forward porque estamos midiendo el edge INMEDIATO, no el efecto de risk management.

**IC rolling**: Se divide la serie en ventanas de 3 meses. Se computa IC en cada ventana. Si el IC es positivo en >60% de las ventanas, la señal es temporalmente estable (no fue un artefacto de un período específico).

### 6.4. Datos

| Asset Class | Symbols | Exchange | Barras 1D (~5.5y) | Barras 4h | Barras 1W |
|-------------|---------|----------|-------------------|-----------|-----------|
| Stocks | SPY, QQQ, GLD, TLT, XLE, XLK, IWM, AAPL, NVDA, TSLA | alpaca | ~1,386 | ~8,316 | ~277 |
| Crypto | BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, AVAXUSDT | binance | ~2,000 | ~12,000 | ~290 |

**1W (semanal):** 277 barras es insuficiente para WFO (necesita 1,100+) pero suficiente para medir IC y hit rate. 1W se usa exclusivamente como indicador de régimen en pasos posteriores, nunca como TF operada.

**Nota para macro indicators:** VRP, yield_curve, credit_spread requieren columnas externas (VIX, T10Y2Y, HYG/LQD) inyectadas via `MacroCacheManager.get_aligned()`. Los datos macro están cacheados en `data/raw/macro/`. Para taker_volume y basis, se necesitan datos de Binance Futures (funding_rate, open_interest, etc.) cargados via `BinanceFuturesDownloader.load_and_merge()`.

### 6.5. Indicadores a evaluar (33 totales)

Cada indicador con sus params default (como están en `params_schema()["default"]`):

**Entry / Momentum (12):**
| Indicator | Default params relevantes |
|-----------|-------------------------|
| `roc` | period=12, mode="bullish", hold_bars=1 |
| `macd` | fast=12, slow=26, signal=9, mode="bullish" |
| `ema` | period=20, mode="bullish" |
| `rsi` | period=14, threshold=30, mode="oversold" |
| `donchian` | period=20 |
| `ma_crossover` | fast=10, slow=30 |
| `ssl_channel` | length=14 |
| `bollinger_bands` | period=20, nbdev=2.0 |
| `momentum_divergence` | roc_period=14, lookback=50 |
| `stoch_rsi` | period=14 |
| `ichimoku` | tenkan=9, kijun=26, senkou_b=52 |
| `squeeze` | bb_length=20, kc_length=20 |

**Volume / Anomaly (3):**
| Indicator | Default params |
|-----------|---------------|
| `obv` | period=20 |
| `volume_spike` | lookback=20, threshold=2.0 |
| `vwap` | (session-based) |

**Custom / Pine replicas (6):**
| Indicator | Notas |
|-----------|-------|
| `firestorm` | Custom trend indicator |
| `firestorm_tm` | Variant con trailing mode |
| `ssl_channel_low` | SSL variant |
| `wavetrend_reversal` | LazyBear WaveTrend |
| `wavetrend_divergence` | WT con divergence |
| `adx_filter` | ADX > threshold |

**Macro (4):**
| Indicator | Fuente de datos | Default params |
|-----------|----------------|---------------|
| `vrp` | FRED VIX + realized vol | realized_window=20, mode="risk_on" |
| `yield_curve` | FRED T10Y2Y | threshold=0.0, mode="normal" |
| `credit_spread` | yfinance HYG/LQD | lookback=20, mode="risk_on" |
| `hurst` | Calculado de OHLCV | window=100, mode="trending" |

**Futures / Cross-sectional (5):**
| Indicator | Fuente de datos | Default params |
|-----------|----------------|---------------|
| `funding_rate` | Binance Futures | lookback=30, extreme_z=2.0 |
| `oi_divergence` | Binance Futures | lookback=20 |
| `long_short_ratio` | Binance Futures | lookback=20 |
| `taker_volume` | Binance Futures | lookback=20, threshold=0.55 |
| `basis` | Binance Futures | lookback=30, extreme_z=2.0 |

**`cs_momentum`** (cross-sectional) requiere un ranking pre-computado. Se excluye del Paso 1 porque es un meta-indicator que compara entre assets, no mide edge de un solo asset.

**`atr`** se excluye porque es un indicator de volatilidad, no de dirección. No genera señales de entry.

**Total evaluable: 30 indicadores** (33 - atr - cs_momentum - algún edge case).

### 6.6. Output esperado

```
artifacts/research/step1_edge_map/
├── raw/                          # datos intermedios
│   ├── signals_{indicator}_{tf}_{asset}.parquet   # señal booleana completa
│   └── forward_returns_{tf}_{asset}.parquet       # retornos forward por TF
├── ic_matrix.csv                 # IC por (indicator, tf, asset, direction)
├── hit_rate_matrix.csv           # hit rate por (indicator, tf, asset, direction)
├── frequency_matrix.csv          # señales/mes
├── stability_matrix.csv          # % ventanas con IC > 0
├── significance_matrix.csv       # p-values
├── edge_summary.csv              # tabla consolidada con todas las métricas
├── rankings/
│   ├── by_tf.csv                 # ranking de indicators por TF
│   ├── by_asset_class.csv        # ranking por asset class (stocks vs crypto)
│   ├── by_direction.csv          # ranking por direction (long vs short)
│   └── overall.csv               # ranking global
└── report.md                     # análisis narrativo con hallazgos
```

### 6.7. Criterios de clasificación

| Nivel | IC | Hit Rate (long) | Temporal Stability | Acción |
|-------|-----|----------|---------------------|--------|
| **Edge fuerte** | > 0.03 | > 53% | > 70% ventanas IC+ | Candidato a entry signal |
| **Edge moderado** | 0.02 - 0.03 | 51-53% | > 60% ventanas IC+ | Candidato a filtro (OPCIONAL) |
| **Edge marginal** | 0.01 - 0.02 | 50-51% | > 50% ventanas IC+ | Investigar en combinación |
| **Sin edge** | < 0.01 | ~50% | < 50% ventanas IC+ | Descartar para este TF |
| **Edge negativo** | < -0.01 | < 49% | — | Investigar como contrarian |

Un indicator puede tener edge fuerte en 4h pero sin edge en 1D. Eso es información valiosa, no descarte.

### 6.8. Lo que NO se hace en Paso 1

- **No se optimizan parámetros de indicadores.** Params default únicamente.
- **No se hace backtesting con risk management.** Cero stops, cero TPs, cero sizing.
- **No se combinan indicadores entre sí.** Cada indicador se mide aislado.
- **No se evalúan TFs menores (15m, 5m, 3m).** Eso es Paso 4.
- **No se construyen estrategias ni portfolios.**
- **No se descarta nada definitivamente.** Un indicator sin edge en 4h puede tener edge en 15m (Paso 4).

### 6.9. Preguntas que Paso 1 debe responder

1. ¿Cuáles de los 33 indicators tienen IC > 0.02 en al menos un TF?
2. ¿Hay indicadores con edge en 1W/1D que podrían servir como filtros HTF?
3. ¿Los macro indicators (VRP, Hurst, yield_curve) tienen IC diferente en 1D vs 4h?
4. ¿Hay indicadores con edge solo para shorts? ¿Solo para longs?
5. ¿Hay diferencias significativas entre stocks y crypto?
6. ¿El edge de algún indicador es temporalmente inestable (solo funcionó en 2021-2023)?

---

## 7. PASO 2: Signal Persistence (definición preliminar)

### 7.1. Objetivo

Para cada indicator×TF con edge (Paso 1), medir: **cuando la señal se activa en TF_high, ¿cuántas barras de TF_low persiste el edge?**

### 7.2. Por qué es crítico

Si ROC en 4h tiene IC=0.03 pero el edge se desvanece en 2 barras de 15m (= 30 minutos), no sirve como filtro para operar en 15m. Pero si persiste 32 barras de 15m (= 8 horas = 2 barras de 4h), entonces podemos usar la señal de 4h como "ventana de oportunidad" para que los indicators de 15m operen.

### 7.3. Método

Para cada (indicator, TF_high, TF_low):
1. Computar señal en TF_high (e.g., ROC en 4h)
2. En cada activación de la señal, medir el retorno acumulado en TF_low para los siguientes N barras
3. Plot: retorno acumulado forward vs número de barras de TF_low
4. Identificar el "half-life": ¿en cuántas barras el exceso de retorno cae a la mitad?

### 7.4. Output

```
artifacts/research/step2_persistence/
├── persistence_{indicator}_{tf_high}_{tf_low}.csv  # retorno acumulado por N barras
├── half_life_matrix.csv                             # half-life por (indicator, TF_high→TF_low)
└── report.md
```

---

## 8. PASO 3: Cross-TF Combinations para 4h (definición preliminar)

### 8.1. Objetivo

Construir estrategias REALES de 4h usando:
- Indicadores de 1W/1D como **filtros** (EXCLUYENTE u OPCIONAL)
- Indicadores de 4h como **entry signals**
- Risk management completo (8 params)

### 8.2. La diferencia fundamental con el approach anterior

Antes: `roc_fullrisk_pyr` significaba "ROC solo en 4h, con risk management optimizado en 4h".

Ahora: `roc_4h_filtered_by_macd_1D` significa "ROC en 4h como entry, PERO solo cuando MACD en 1D dice bullish (señal activa en 1D persiste ~6 barras de 4h)". El filtro de 1D NO se optimiza — usa los params que tuvieron mejor IC en Paso 1. Solo el entry (ROC 4h) y el risk management se optimizan.

### 8.3. Combination modes a probar

| Mode | Significado | Cuándo usar |
|------|-------------|-------------|
| **EXCLUYENTE** | HTF Y entry deben estar activos | Filtro estricto, menos trades, mayor hit rate |
| **OPCIONAL** | Entry opera siempre, HTF da "conviction bonus" | Más trades, hit rate moderado |
| **MAJORITY** | N-of-M indicadores cross-TF deben estar de acuerdo | Equilibrio entre ambos |

### 8.4. Risk space

AQUÍ se usa el risk space completo (8 params, ~87M combinaciones). Optuna TPE con 2000+ trials. El risk space se explora PER cross-TF combo, no globalmente, porque la config óptima depende del entry.

---

## 9. PASOS 4-7: Definición detallada PENDIENTE

Cada paso se detallará DESPUÉS de completar y analizar el paso anterior. La definición exacta depende de los hallazgos.

**Paso 4** repetirá el IC scan pero en TFs menores, CONDICIONADO a que la señal HTF (del Paso 3) esté activa. Esto responde: "¿RSI en 15m tiene edge cuando ROC 4h dice bullish?" — que es una pregunta fundamentalmente diferente a "¿RSI tiene edge en 15m?" (Paso 1 extendido).

**Paso 5** construirá estrategias de 15m/5m con cascada completa de HTF filters. La señal de 4h que persiste 48 barras de 5m (Paso 2) crea la ventana. El indicator de 5m con mejor IC condicionado (Paso 4) define la entry.

**Paso 6** es risk optimization exhaustivo solo para las mejores combinaciones.

**Paso 7** construye portfolios separados por TF operada.

**Nota importante para Pasos 4-5:** A veces condicionar en TODAS las TFs intermedias empeora las cosas. `1D + 5m` puede funcionar mejor que `1D + 4h + 1h + 5m` porque cada layer adicional es un filtro que reduce trades. Hay que probar con y sin cada layer intermedio para encontrar la cascada óptima.

---

## 10. Infraestructura existente reutilizable

> Arquitectura completa y key files en [Research Report §3](research_report.md#3-infrastructure--pipeline). Aquí solo el mapeo componente → paso de esta metodología.

| Componente | Archivo | Uso en este research |
|-----------|---------|---------------------|
| 33 indicators | `indicators/registry.py` | Paso 1: compute señales |
| ParquetStore + Resampler | `data/storage.py`, `data/resampler.py` | Cargar OHLCV en cualquier TF |
| MacroCacheManager | `data/macro_cache.py` | Inyectar VIX, yield curve, credit spread |
| BinanceFuturesDownloader | `data/futures.py` | Cargar funding rate, OI, taker volume |
| BacktestObjective | `optimization/objective.py` | Pasos 3, 5, 6: backtest + Optuna |
| WalkForwardEngine | `optimization/walk_forward.py` | Pasos 3, 5, 6: WFO validation |
| CSCVValidator + DSR | `optimization/anti_overfit.py` | Pasos 3, 5, 6: anti-overfitting |
| RollingPortfolioEvaluator | `optimization/rolling_validation.py` | Paso 7: portfolio validation |
| PortfolioStressTester | `risk/stress_testing.py` | Paso 7: stress testing |
| FeatureImportanceEngine | `optimization/feature_importance.py` | Paso 6: risk param ranking |
| Signal combiner | `indicators/signal_combiner.py` | Pasos 3, 5: EXCLUYENTE/OPCIONAL/MAJORITY |

### Lo que hay que implementar

| Componente | Paso | Descripción |
|-----------|------|-------------|
| IC Scanner | 1 | Script que computa IC/hit rate para cada indicator×TF×asset |
| Persistence Analyzer | 2 | Script que mide signal half-life cross-TF |
| Cross-TF Archetype Generator | 3 | Generación programática de archetypes con HTF filters |
| Conditioned IC Scanner | 4 | IC scan de TFs menores condicionado a señal HTF activa |
| Sensitivity Module | 6 | Perturbación ±20% de params para filtrar frágiles |

---

## 11. Datos disponibles

### Stocks (Alpaca, ~5.5 años desde julio 2020)

| Symbol | Tipo | Barras 4h | Barras 1h |
|--------|------|-----------|-----------|
| SPY | S&P 500 ETF | 4,149 | 10,754 |
| QQQ | Nasdaq 100 ETF | 4,093 | 10,991 |
| GLD | Gold ETF | 3,395 | 9,245 |
| TLT | 20+ Year Treasury Bond ETF | 3,919 | 10,506 |
| XLE | Energy Sector ETF | 3,394 | 9,181 |
| XLK | Technology Sector ETF | 3,370 | — |
| IWM | Russell 2000 Small Cap ETF | 4,087 | 10,521 |
| AAPL | Apple | 3,561 | — |
| NVDA | NVIDIA | 3,508 | — |
| TSLA | Tesla | 3,568 | — |

### Crypto (Binance, ~5-8 años)

| Symbol | Barras 4h | Barras 1h |
|--------|-----------|-----------|
| BTCUSDT | 18,754 | 74,960 |
| ETHUSDT | 18,754 | 74,960 |
| SOLUSDT | 12,231 | 48,906 |
| BNBUSDT | ~18,000 | ~72,000 |
| AVAXUSDT | ~12,000 | ~48,000 |

### Macro (FRED + yfinance, cached en `data/raw/macro/`)

| Serie | Fuente | Frecuencia | Desde |
|-------|--------|------------|-------|
| VIX (VIXCLS) | FRED | Daily | 2015 |
| Yield Spread (T10Y2Y) | FRED | Daily | 2015 |
| HY Spread (BAMLH0A0HYM2) | FRED | Daily | 2015 |
| HYG (High Yield ETF) | yfinance | Daily | 2015 |
| LQD (Investment Grade ETF) | yfinance | Daily | 2015 |
| Dollar Index (DTWEXBGS) | FRED | Daily | 2015 |

---

## 12. Estimaciones de compute

| Paso | Qué computa | Backtests estimados | Tiempo estimado (M4 Pro 12 cores) |
|------|-------------|--------------------|------------------------------------|
| 1 | IC scan: 30 ind × 3 TFs × 15 assets × 2 dirs | 0 (solo compute signals + stats) | ~30 min |
| 2 | Persistence: ~15 ind × 5 cascadas TF × 15 assets | 0 (solo forward returns) | ~15 min |
| 3 | Cross-TF 4h: ~50 combos × 15 assets × 2 dirs × 2000 trials | ~3M | ~4-6 horas |
| 4 | IC scan condicionado: 30 ind × 3 TFs × 15 assets × 2 dirs | 0 | ~30 min |
| 5 | Cross-TF 15m/5m: ~50 combos × 15 assets × 2 dirs × 2000 trials | ~3M | ~6-8 horas |
| 6 | Risk exhaustivo: ~100 combos × 5000 trials | ~500K | ~2-3 horas |
| 7 | Portfolio construction + validation | ~50K | ~1 hora |

**Total estimado: ~6.5M backtests, ~15-20 horas de compute.**

Nota: las estimaciones de Pasos 3+ dependen de cuántos indicators pasan el filtro de Paso 1. Si solo 5 tienen edge, hay menos combos. Si 15 tienen edge, hay más.

---

## 13. Principios operativos

1. **Un paso a la vez.** No empezar Paso 2 hasta que Paso 1 esté completamente analizado y documentado.
2. **Artifacts antes de avanzar.** Cada paso genera archivos de output que el siguiente paso lee. Sin artifacts, no se avanza.
3. **El report de cada paso tiene conclusiones accionables.** "ROC tiene IC=0.028 en 4h, estable en 75% de ventanas" → acción: incluir en Paso 3 como entry candidate.
4. **No descartar sin evidencia.** Si un indicator no tiene edge en 4h, puede tenerlo en 15m (Paso 4). Solo se descarta un indicator cuando tiene IC < 0.01 en TODOS los TFs evaluados.
5. **Documentar decisiones.** Cada vez que se elige incluir/excluir algo, el razonamiento queda en el report del paso correspondiente.
6. **Re-evaluar al avanzar.** Los hallazgos de Paso 3 pueden invalidar conclusiones del Paso 1 (e.g., un indicator sin edge en 4h solo pero con edge cuando se combina con HTF filter). Si eso pasa, se actualiza el mapa.

---

## PASO 1 — RESULTADOS (completado 2026-03-22)

### Resumen ejecutivo

67,950 mediciones: 31 indicators × 5 param configs × 5 forward horizons × 15 assets × 3 TFs × 2 directions. Datos en `artifacts/research/step1_edge_map/`.

### Mapa de edge por TF

| TF | Long STRONG (IC>0.03) | Short STRONG (IC>0.03) | Observación |
|----|----------------------|----------------------|-------------|
| **1w** | 13 indicators | 13 indicators | Edge masivo y generalizado |
| **1d** | 2 indicators | 3 indicators | Edge moderado pero temporalmente estable |
| **4h** | 0 indicators | 0 indicators | Solo marginal (IC 0.01-0.023), necesita HTF filters |

### Top indicators por TF×direction (IC promedio cross-asset, best param config)

**Weekly LONG:**
| Rank | Indicator | IC | HR | IC+ (assets) | Tipo |
|------|-----------|-----|-----|--------------|------|
| 1 | ssl_channel | 0.073 | 65.3% | 15/15 | Trend |
| 2 | macd | 0.059 | 63.0% | 15/15 | Momentum |
| 3 | volume_spike | 0.057 | 62.7% | 5/6 | Anomaly |
| 4 | firestorm | 0.049 | 62.1% | 14/15 | Custom |
| 5 | momentum_divergence | 0.046 | 60.3% | 14/15 | Divergence |

**Weekly SHORT:**
| Rank | Indicator | IC | HR | IC+ (assets) | Tipo |
|------|-----------|-----|-----|--------------|------|
| 1 | macd | 0.070 | 54.1% | 14/15 | Momentum |
| 2 | momentum_divergence | 0.066 | 51.3% | 15/15 | Divergence |
| 3 | vrp | 0.060 | 46.0% | 10/10 | Macro |
| 4 | hurst | 0.058 | 48.5% | 14/15 | Meta-signal |
| 5 | ema | 0.056 | 52.5% | 11/15 | Trend |

**Daily LONG:**
| Rank | Indicator | IC | HR | Stability | Tipo |
|------|-----------|-----|-----|-----------|------|
| 1 | yield_curve | 0.035 | 53.9% | **67%** | Macro |
| 2 | ssl_channel_low | 0.031 | 64.6% | 51% | Trend |
| 3 | adx_filter | 0.026 | 54.3% | 53% | Filter |
| 4 | ema | 0.024 | 55.4% | 60% | Trend |
| 5 | wavetrend_reversal | 0.024 | 55.4% | 70% | Reversal |

**Daily SHORT:**
| Rank | Indicator | IC | HR | Stability | Tipo |
|------|-----------|-----|-----|-----------|------|
| 1 | ichimoku | 0.035 | 60.2% | N/A | Cloud |
| 2 | vrp | 0.035 | 48.0% | **62%** | Macro |
| 3 | yield_curve | 0.032 | 50.2% | **65%** | Macro |
| 4 | ssl_channel_low | 0.030 | 56.8% | 48% | Trend |
| 5 | hurst | 0.028 | 48.0% | 57% | Meta-signal |

**4h (mejor es MODERATE, no hay STRONG):**
- Long: volatility_regime (IC=0.023, stab=70%), ssl_channel (IC=0.022, stab=66%)
- Short: ssl_channel_low (IC=0.019), ema (IC=0.017), hurst (IC=0.016)

### Multi-horizon: trend vs reversal indicators

Indicadores de **TENDENCIA** (IC crece con el horizonte — predicen dirección sostenida):
| Indicator | TF | Dir | h=1 | h=10 | Ratio | Uso ideal |
|-----------|-----|------|------|------|-------|-----------|
| momentum_divergence | 1w | short | 0.066 | **0.192** | 2.9x | Filtro HTF largo plazo |
| vrp | 1w | short | 0.060 | **0.151** | 2.5x | Filtro macro bear |
| hurst | 1w | short | 0.058 | **0.115** | 2.0x | Meta-signal de régimen |
| adx_filter | 1d | long | 0.026 | **0.078** | 3.0x | Filtro trend strength |
| volatility_regime | 4h | long | 0.023 | **0.047** | 2.0x | Filtro vol regime |

Indicadores de **REVERSIÓN** (IC máximo en h=1, decae después):
| Indicator | TF | Dir | h=1 | h=10 | Ratio | Uso ideal |
|-----------|-----|------|------|------|-------|-----------|
| ssl_channel | 1w | long | **0.073** | 0.067 | 0.9x | Entry timing |
| ichimoku | 1d | short | **0.035** | 0.021 | 0.6x | Entry timing |
| ssl_channel_low | 1d | short | **0.030** | 0.016 | 0.5x | Entry timing |

### Hallazgos sobre indicadores macro

| Indicator | Mejor TF×Dir | IC | Rol validado |
|-----------|-------------|-----|-------------|
| VRP | 1w short (0.060), 1d short (0.035) | Trend (h=10: 0.151) | Predictor macro de bear markets |
| yield_curve | 1d long (0.035, stab 67%), 1d short (0.032, stab 65%) | Estable | Filtro macro más estable del scan |
| credit_spread | 1w short (0.031) | Moderate | Señal de stress crediticio |
| hurst | 1w short (0.058), 1d short (0.028) | Trend (h=10: 0.115) | Meta-signal de régimen |

### Consistencia cross-asset

Los mejores indicators son positivos en **14-15 de 15 assets** (columna IC+). Los hallazgos NO son artefactos de 1-2 assets sino patrones robustos cross-asset.

### Conclusiones accionables para Paso 2

1. **HTF filters candidates (weekly, tendencia):** momentum_divergence, vrp, hurst, macd, adx_filter — estos tienen IC que CRECE con el horizonte, ideales como filtros de dirección a largo plazo
2. **HTF filters candidates (daily, estabilidad):** yield_curve, vrp, ema, adx_filter, wavetrend_reversal — edge moderado pero temporalmente estable
3. **Entry candidates (4h):** volatility_regime, ssl_channel, wavetrend_reversal, macd, adx_filter — edge marginal solo pero con potencial de mejora con HTF conditioning
4. **Los macro indicators (vrp, yield_curve, hurst, credit_spread) tienen edge REAL** pero en 1w/1d, no en 4h. Deben usarse como filtros HTF, exactamente como la metodología predice.

---

## Changelog

| Fecha | Cambio |
|-------|--------|
| 2026-03-22 | Documento inicial completo. Paso 1 definido en detalle. Pasos 2-7 con definición preliminar. |
| 2026-03-22 | Paso 1 completado. 67,950 mediciones. Resultados documentados. Weekly = edge masivo, Daily = moderado estable, 4h = marginal sin HTF. |
| 2026-03-22 | Paso 2 completado. Signal persistence medida para 18 HTF candidates. Weekly signals persisten ~96 barras daily (5 meses). Edge CRECE con horizonte — son signals de tendencia, no timing. |
