# Research Journal — SuiteTrading

> Registro condensado de decisiones clave, descubrimientos y pivotes a lo largo de todas las fases de investigacion.
> Para metodologia detallada ver `research_methodology.md`. Para resultados completos ver `research_report.md`.
> Documentos originales de sprint archivados en `docs/archive/`.

---

## Timeline & Fases

### Sprint 1: Infraestructura de Datos (2026-03-11)

**Construido:**
- Pipeline completo de datos: descarga multi-fuente (Binance Vision bulk + CCXT API), almacenamiento Parquet particionado, validacion OHLCV, resampling multi-timeframe (11 TFs), calculo de warmup
- 256 tests, ~1,350 LOC produccion

**Decisiones arquitectonicas:**
- **Binance Vision como fuente primaria historica** — API REST tiene rate limits (1200 weight/min); 7 anios de 1m tardaria horas. Vision descarga en segundos por mes
- **CCXT solo para mes actual** — Vision no genera el mes corriente; minimiza llamadas API
- **Parquet + ZSTD nivel 3** — ratio ~6:1 en datos de mercado con decompresion rapida. Snappy: peor ratio. GZIP: 5x mas lento en decompresion
- **Particionado mensual (intraday) / anual (daily+)** — 1 mes de 1m = ~45K filas = 2-3 MB comprimido. Tamano optimo para writes incrementales
- **`timeframes.py` como fuente unica de verdad** — 11 representaciones (Pine, Binance, CCXT, pandas, segundos) en un solo diccionario. Ningun otro modulo mantiene mapeos propios

**Incidente critico:**
- Binance Vision cambio la unidad temporal de `open_time` (ms a us) a partir de 2025-01. Corrupcio masiva en `data/raw/`: 41,796 particiones invalidadas. Parser endurecido para detectar ms/us/ns automaticamente. Sprint 1 solo se cerro realmente despues de esta correccion.

---

### Sprint 2: Motor de Indicadores (2026-03-11)

**Construido:**
- Catalogo completo de 15 indicadores Pine portados a Python
- Separacion `standard/` (wrappers TA-Lib) vs `custom/` (logica propia + Numba)
- Registry central `indicator_key -> class`

**Decisiones:**
- **Reutilizar contrato existente, no redisenar** — `Indicator.compute(df, **params) -> pd.Series` ya funcionaba; Sprint 2 extiende, no reemplaza
- **MTF como infraestructura compartida** — toda resolucion de temporalidades pasa por `data.resampler` + `indicators.mtf`. Ningun indicador reimplementa `.resample().agg()` localmente
- **No arrastrar bugs del Pine** — SSL contaba doble un voto en sell optional. Python preserva la intencion, no los defectos accidentales

---

### Sprint 3: Motor de Gestion de Riesgo (2026-03-11)

**Construido:**
- Position sizing (fixed fractional, Kelly, ATR-based)
- State machine de posiciones: estados explicitos, transiciones deterministas, trazabilidad de razones de salida
- 5 arquetipos de RM: TrendFollowing (A), MeanReversion (B), Mixed (C), Pyramidal (D), GridDCA (E)
- Trailing stops (fixed, ATR, Chandelier, SAR, signal-based)
- Portfolio-level risk (kill switch por drawdown, portfolio heat, gross/net exposure)
- Prototipo VBT simulator para arquetipos A/B/C

**Decisiones:**
- **Legacy como preset del framework, no el framework** — la logica Pine heredada es un preset; el framework soporta multiples arquetipos sin reescribir el core
- **Orden de evaluacion por barra es contrato semantico**: SL -> TP1 -> Break-even -> Trailing -> Nueva entrada. Alterar el orden cambia el comportamiento
- **Core Python determinista primero, adapter vectorizable despues** — evita que restricciones de VBT simplifiquen artificialmente arquetipos complejos
- **Trailing como familia de exit policies, no solo precio movil** — porque la logica legacy usa SSL LOW como trailing de salida (senial, no precio)

---

### Sprint 4: Motor de Backtesting (2026-03-11)

**Construido:**
- Engine dual: FSM (arquetipos complejos C/D/E) + simple (A/B, ~10x mas rapido)
- Grid masivo con chunking, checkpointing y resume
- 11 metricas vectorizadas (Sharpe, Sortino, Calmar, DD, profit factor, etc.)
- Reporting con dashboards Plotly
- Registry centralizado: 12 indicadores (6 custom Numba + 6 TA-Lib)
- 509+ tests, throughput: 63.7 backtests/sec single-thread

**Decisiones:**
- **Engine Python puro + Numba, sin VBT PRO** — VBT PRO requiere licencia + SSH key no disponible. Bar-loop propio da control total sobre gap-aware fills, slippage y FSM
- **RunConfig con SHA256 determinístico** — misma config = mismo ID = idempotente. Elimina UUIDs, permite deduplicacion trivial
- **Diferimiento de validacion contra TradingView** — automatizacion Puppeteer existe pero no hay baseline pregrabado. Diferido a Sprint 5

---

### Sprint 5: Optimizacion y Anti-Overfitting (2026-03-12)

**Construido:**
- Optuna optimizer (TPE, Random, NSGA-II, CMA-ES)
- Walk-Forward Optimization (rolling + anchored)
- CSCV + PBO + DSR + AntiOverfitPipeline
- DEAP NSGA-II multi-objetivo (opcional)
- Feature importance con XGBoost + SHAP (opcional)
- Ejecucion paralela
- 100 tests nuevos (total: 609)

**Decisiones:**
- **Optuna + DEAP ambos** — Optuna como primario (TPE, SQLite persistence, pruning). DEAP como alternativa para exploracion explicita de frente Pareto
- **CSCV como primer filtro** — captura overfitting antes de DSR, reduce computacion
- **WFO evalua todos los candidatos por fold** — habilita CSCV sobre el set completo (necesita equity curves de todas las estrategias, no solo la mejor IS)
- **Feature importance como analisis post-hoc** — no integrado en loop de optimizacion para evitar dependencia circular

---

### Sprint 5.5: Hardening y Risk Lab (2026-03-12)

**Construido:**
- 17 smoke tests de indicadores estandar
- Portfolio risk wired en FSM runner (feature-flagged)
- Trailing policy como modo alternativo
- 216 campanas de risk lab (3 symbols x 4 TFs x 3 strategies x 6 risk presets)
- Search space maturity matrix (39 dimensiones clasificadas)
- Regression fixtures y execution semantics doc
- 647 tests totales

**Hallazgos del Risk Lab:**
- Solo 14/216 campanas (6.5%) produjeron Sharpe positivo
- Todas las top campanas: **wavetrend mean-reversion con break-even deshabilitado**
- **4h es el timeframe optimo** para el set actual
- **Break-even perjudica mean-reversion** — corta ganadores demasiado temprano
- **Trend strategies necesitan optimizacion de indicadores** antes de que risk tuning agregue valor
- Conclusiones: el risk lab con params fijos no alcanza. Se necesita Optuna a escala.

---

### Sprint 6: Discovery Masivo (2026-03-12)

**Construido:**
- `run_discovery.py` orquestador de estudios masivos
- Pipeline completo: Optuna TPE (1000 trials) -> WFO rolling -> CSCV/PBO -> DSR
- Primera ejecucion a escala real: 36 estudios Optuna, 18K+ backtests
- AlpacaExecutor para paper trading

**Decisiones:**
- **NautilusTrader diferido** — resuelve tick-by-tick L2 fill simulation, relevante solo para HFT/sub-minuto. Nuestros arquetipos operan en 15m-1d. Alpaca paper es un path mas rapido
- **Discovery first, execution second** — sin candidatos validados no tiene sentido construir capa live
- **Asset-specific, no cross-asset** — una estrategia BTC no necesita funcionar en ETH/SOL
- **Long/Short como tracks independientes** — FSM no permite flip; cada direccion es un study separado

---

### Sprint 7: Expansion de Datos + Long/Short (2026-03-14)

**Construido:**
- Datos expandidos a 7+ anios (3.7M+ barras/simbolo)
- MIN_TRADES subido de 30 a 300
- Direction como parametro en BacktestObjective y WFO
- run_discovery.py con `--directions long short`
- Verificacion de FSM short-side

**Decisiones:**
- **MIN_TRADES = 300** — minimo estadístico para significancia en cualquier TF/periodo. 30 era insuficiente
- **Long/Short como tracks separados (nunca flip)** — asimetria fundamental de crypto: drawdowns mas rapidos que rallies requieren configs distintas

---

## Descubrimientos Cientificos Clave

### 1. El edge esta en la cadena de riesgo, no en los indicadores

> Los indicadores tienen edge estadistico real pero delgado: P(up|signal) = 49-53%.
> Los profits vienen del compounding + risk management, no de prediction accuracy.

La cadena completa: Entry -> SL (ATR wide) -> TP1 (partial close) -> Break Even -> Trailing -> Pyramid. Cada eslabon multiplica el efecto. Sin TP1+BE el trailing solo no alcanza. Sin trailing, TP1+BE no captura tendencias largas.

### 2. PBO solo tiene 12.1% de falsos positivos. DSR es el filtro real.

Test de hipotesis nula: con PBO como unico filtro, 12.1% de estrategias random pasan. Agregando DSR: 0% de falsas. DSR es el gate definitivo contra overfitting.

### 3. SSL Channel como senial de entrada = PBO mas bajo (0.001)

Historicamente SSL se usaba solo como trailing stop. Como indicador de ENTRY produjo el PBO mas bajo de toda la exploracion. Innovacion mas significativa de la fase de discovery.

### 4. Pyramid domina los top results

8 de 10 mejores resultados usan pyramid. El espaciado (`block_bars`, rank #2 global) es mas importante que la cantidad de adds (`max_adds`, rank #6).

### 5. Time exit es el parametro individual mas impactante

`time_exit__max_bars` tiene el spread de Sharpe mas alto (0.492). Matar posiciones estancadas outperforma masivamente a dejarlas correr indefinidamente.

### 6. Long y Short necesitan configuraciones fundamentalmente distintas

| Parametro | Long Optimo | Short Optimo |
|-----------|-------------|--------------|
| risk_pct | 18% | 26% |
| tp_r_multiple | 4.0R | 2.5R |
| tp_close_pct | 35% | 65% |
| pyramid_block_bars | 19 | 13 |
| stop_atr_multiple | 12 | 15 |

Shorts: mas riesgo, TP mas temprano, cierre parcial mayor, pyramid mas rapido, stops mas amplios.

### 7. Todos los parametros son estables

Analisis de sensibilidad (±20% perturbacion): zona verde 83-100% del rango de busqueda. No hay parametros fragiles. El search space esta bien calibrado.

### 8. HTF filters agregan robustez

Daily MA crossover como filtro HTF: +70% Sharpe para longs. MACD daily como alternativa tambien funciona (PBO=0.057 para BTC shorts).

---

## Numeros Consolidados

| Metrica | Phase 1 | Phase 2 | Total |
|---------|---------|---------|-------|
| WFO Studies | 574 | 381 | 955 |
| Backtests (est.) | ~287K | ~750K | ~1M+ |
| Risk Archetypes | 62 | 28 (fullrisk) | 90 |
| PBO < 0.50 | 276 (48%) | -- | -- |
| PBO < 0.30 (viable) | -- | 41 | 41 |
| PBO < 0.01 (excepcional) | 12 | 2 | 14 |
| DSR Finalists | 0 | 0 | 0 |

**Top 5 global por PBO:**
1. SSL+fullrisk+pyr — ETH 4h short — PBO 0.001, Sharpe 0.52
2. RSI+fullrisk+pyr — ETH 1h long — PBO 0.008, Sharpe 1.37
3. MACD+fullrisk+pyr — SOL 1h short — PBO 0.015, Sharpe 1.63
4. MACD+fullrisk+pyr — SOL 1h long — PBO 0.025, Sharpe 1.53
5. ROC+fullrisk+pyr+MTF — SOL 4h short — PBO 0.033, Sharpe 1.78

---

## Pivotes y Correcciones de Rumbo

### Bug FSM Trailing (Sprint 6+)
`_should_trailing_exit()` requeria TP1 hit o OPEN_BREAKEVEN antes de permitir trailing exit. Si TP1/BE estaban deshabilitados, posiciones nunca cerraban: 2-3 trades de 7 anios de data. **Fix**: trailing/exit signal fires incondicional desde cualquier estado abierto. Impacto: de 2-3 trades a 500-2400.

### Parametros de riesgo crypto (Sprint 6+)
Defaults (ATR 2-3, risk 1%, commission 0.10%) destruyen el edge en crypto. Stops demasiado tight causan whipsaw; commission 0.10% es 2.5x Binance real. **Fix**: ATR 3-20, risk 1-50%, commission 0.04%. Sharpe paso de negativo a 0.5-1.8.

### NautilusTrader diferido
Planeado originalmente para Sprint 6. Diferido porque resuelve tick-by-tick L2 fills, irrelevante para arquetipos en 15m-1d. Alpaca paper es path mas directo a validacion live.

### VBT PRO descartado como runtime
Sprint 3 planeo prototipo VBT. Sprint 4 descubrio que engine propio con Numba da control total sobre FSM, gap-aware fills y slippage sin dependencia de licencia.

### Break-even perjudica mean-reversion
Risk lab (216 campanas) mostro que BE corta ganadores demasiado temprano en mean-reversion. Solo funciona bien en trend following.

### Risk lab con params fijos insuficiente
6.5% Sharpe positivo con presets fijos. Se necesitaba optimizacion Optuna a escala para encontrar las combinaciones viables.

### Look-ahead bias en indicadores
IS Sharpe ridiculamente alto, OOS colapso. Indicator computation usaba datos futuros en ventanas. Fix: alignment estricto de seniales con warmup bars.

---

## Estado Actual

### Validado
- Pipeline completo Data -> Indicators -> Backtest -> Optuna -> WFO -> CSCV/PBO -> DSR
- ~955 WFO studies, ~1M+ backtests ejecutados
- 41 candidatos viables (PBO < 0.30), 14 excepcionales (PBO < 0.01)
- Todos los parametros estables (sensibilidad ±20%)
- FSM determinista para 5 arquetipos, dual runner (simple + FSM)
- 754+ tests passing, zero regressions

### Pendiente / Proximo
- DSR aun no produce finalists (p < 0.05) — posiblemente necesita mas trials o ajuste de threshold
- Hansen SPA no aplicado a escala
- Portfolio multi-estrategia con rolling validation
- Paper trading prolongado en Alpaca
- Expansion de indicadores y dimensiones no exploradas (ver `research_report.md` seccion 12)
