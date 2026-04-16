# Sprint 4 — Backtesting Core: Documentación Completa

**Proyecto:** SuiteTrading  
**Sprint:** 4 — Backtesting Core  
**Fecha:** 11 de marzo de 2026  
**Estado:** ✅ Cerrado — 509+ tests passing + benchmark reproducible PASS

---

## 1. Resumen Ejecutivo

Sprint 4 implementa el motor completo de backtesting: ejecución dual (FSM + simple), generación de grids masivos con chunking y checkpointing, cálculo vectorizado de métricas, reporting con dashboards Plotly, y un registry centralizado de 12 indicadores con wrappers estándar TA-Lib.

### Métricas Clave

| Métrica | Valor |
|---------|-------|
| Tests nuevos (backtesting) | 60 |
| Tests totales suite | 509+ (todos passing) |
| Archivos creados | 14 (producción + tests + scripts) |
| Archivos modificados | 3 |
| Módulos públicos | 4 (engine, grid, metrics, reporting) |
| Módulos internos | 4 (schemas, runners, datasets, checkpoints) |
| Indicadores registrados | 12 (6 custom + 6 estándar) |
| Throughput medido | 63.7 backtests/sec (single-thread) |

---

## 2. Arquitectura del Sistema

```
suitetrading/
├── backtesting/
│   ├── __init__.py          ← Superficie pública: exports all 8 public classes
│   ├── engine.py            ← BacktestEngine: run(), run_batch(), auto mode
│   ├── grid.py              ← ParameterGridBuilder: cartesian product + chunking
│   ├── metrics.py           ← MetricsEngine: 11 métricas vectorizadas
│   ├── reporting.py         ← ReportingEngine: dashboards HTML + CSV ranking
│   └── _internal/
│       ├── __init__.py
│       ├── schemas.py       ← Contratos: BacktestDataset, StrategySignals, RunConfig, etc.
│       ├── datasets.py      ← Bridge data→engine: load, resample, align, warmup
│       ├── runners.py       ← run_fsm_backtest() + run_simple_backtest()
│       └── checkpoints.py   ← CheckpointManager: JSON state + Parquet chunks
├── indicators/
│   ├── registry.py          ← INDICATOR_REGISTRY: 12 indicadores centralizados
│   └── standard/
│       ├── __init__.py      ← Exports RSI, EMA, MACD, ATR, VWAP, BollingerBands
│       └── indicators.py    ← 6 wrappers TA-Lib (subclases de Indicator ABC)
└── tests/
    └── backtesting/
        ├── __init__.py
        ├── conftest.py           ← Fixtures compartidos
        ├── test_schemas.py       ← 11 tests: RunConfig, Dataset, Signals, Checkpoint, RESULT_COLUMNS
        ├── test_grid.py          ← 13 tests: cartesian, chunking, dedup, registry space
        ├── test_metrics.py       ← 13 tests: sharpe, sortino, calmar, DD, trade metrics
        ├── test_engine.py        ← 9 tests: simple/fsm/auto mode, batch, determinism
        ├── test_reporting.py     ← 5 tests: CSV, HTML, graceful Plotly fallback
        └── test_integration.py   ← 9 tests: E2E pipeline, grid→metrics, checkpoint resume
```

### Flujo de datos

```
ParquetStore → OHLCVResampler → BacktestDataset
                                    ↓
INDICATOR_REGISTRY → compute_signals() → StrategySignals
                                              ↓
ParameterGridBuilder → RunConfig[] → BacktestEngine.run()
                                          ↓
                           ┌────────────────────────────┐
                           │ "auto" mode selection       │
                           │ A/B → simple (bar-loop)     │
                           │ C/D/E → fsm (StateMachine)  │
                           └────────────────────────────┘
                                          ↓
                              MetricsEngine.compute()
                                          ↓
                     CheckpointManager → Parquet ZSTD chunks
                                          ↓
                         ReportingEngine → HTML + CSV
```

---

## 3. Módulos Implementados

### 3.1 `engine.py` — BacktestEngine

| Método | Descripción |
|--------|-------------|
| `run()` | Ejecución unitaria: dataset + signals + risk_config → dict de resultados |
| `run_batch()` | Ejecución en lote con callables: dataset_loader, signal_builder, risk_builder |
| Auto mode | Selecciona `simple` vs `fsm` basado en `VECTORIZABILITY[archetype]` |

### 3.2 `grid.py` — ParameterGridBuilder

| Método | Descripción |
|--------|-------------|
| `build(GridRequest)` | Producto cartesiano completo → `list[RunConfig]` |
| `iter_configs()` | Generación lazy (memory-friendly para grids grandes) |
| `chunk(configs, size)` | Partición determinística para ejecución por lotes |
| `estimate_size()` | Estimación rápida sin expandir el grid |
| `deduplicate()` | Eliminación de duplicados por `run_id` |

Función auxiliar: `build_indicator_space_from_registry()` genera automáticamente el `indicator_space` desde los `params_schema()` del registry.

### 3.3 `metrics.py` — MetricsEngine

11 métricas vectorizadas:

| Métrica | Tipo | Annualización |
|---------|------|---------------|
| `net_profit` | float | — |
| `total_return_pct` | float | — |
| `sharpe` | float | √(365×24) (crypto 24/7, hourly) |
| `sortino` | float | √(365×24) |
| `max_drawdown_pct` | float | — |
| `calmar` | float | return/DD ratio |
| `win_rate` | float (%) | — |
| `profit_factor` | float | gross_profit/gross_loss |
| `average_trade` | float | mean PnL |
| `max_consecutive_losses` | int | — |
| `total_trades` | int | — |

### 3.4 `reporting.py` — ReportingEngine

Genera dashboard en `output_dir/`:
- `results_summary.csv` — tabla completa de resultados
- `ranking.csv` — top configs por Sharpe
- `metric_distributions.html` — distribuciones Plotly
- `risk_return_scatter.html` — scatter Sharpe vs DD
- `breakdown_by_symbol.html` — box plots por símbolo
- `breakdown_by_timeframe.html` — box plots por timeframe

Graceful degradation: si Plotly no está instalado, genera solo CSVs sin error.

### 3.5 `_internal/schemas.py` — Contratos

| Clase | Responsabilidad |
|-------|----------------|
| `BacktestDataset` | Bundle OHLCV validado + HTF aligned frames + metadata |
| `StrategySignals` | Señales booleanas pre-computadas (entry/exit long/short/trailing) |
| `GridRequest` | Especificación de grid: symbols, timeframes, indicator_space, risk_space, archetypes |
| `RunConfig` | Configuración fully-resolved con `run_id` SHA256 determinístico |
| `BacktestCheckpoint` | Estado persistido de un chunk (pending/running/done/error) |
| `RESULT_COLUMNS` | 16 columnas del schema Parquet de resultados |

### 3.6 `_internal/runners.py` — Ejecución

| Runner | Uso | Características |
|--------|-----|-----------------|
| `run_simple_backtest()` | Archetypes A/B (alta vectorizabilidad) | Single-position, gap-aware SL, sin pyramiding |
| `run_fsm_backtest()` | Archetypes C/D/E (complejidad alta) | PositionStateMachine completa, sizing dinámico, todos los eventos |

Ambos producen `BacktestResult` (equity_curve, trades, final_equity, total_return_pct, mode). Son 100% determinísticos.

### 3.7 `_internal/checkpoints.py` — Persistencia

- Estado en `checkpoints.json` (chunk_id → status, output_path, error)
- Resultados en `chunk_XXXXXX.parquet` (ZSTD compression)
- Resume: `is_chunk_done()` permite saltar chunks ya completados
- `load_all_results()` concatena todos los Parquets en un DataFrame

### 3.8 `_internal/datasets.py` — Bridge

| Función | Descripción |
|---------|-------------|
| `load_dataset()` | Carga desde ParquetStore + resample HTF + warmup trimming |
| `build_dataset_from_df()` | Constructor from DataFrame (testing) |
| `compute_signals()` | Registry → indicadores → combine_signals → StrategySignals |

### 3.9 `indicators/registry.py` — Registry centralizado

12 indicadores registrados:

| Nombre | Clase | Tipo |
|--------|-------|------|
| `firestorm` | Firestorm | Custom (Numba) |
| `firestorm_tm` | FirestormTM | Custom (Numba) |
| `ssl_channel` | SSLChannel | Custom (Numba) |
| `ssl_channel_low` | SSLChannelLow | Custom (Numba) |
| `wavetrend_reversal` | WaveTrendReversal | Custom (Numba) |
| `wavetrend_divergence` | WaveTrendDivergence | Custom (Numba) |
| `rsi` | RSI | Standard (TA-Lib) |
| `ema` | EMA | Standard (TA-Lib) |
| `macd` | MACD | Standard (TA-Lib) |
| `atr` | ATR | Standard (TA-Lib) |
| `vwap` | VWAP | Standard (TA-Lib) |
| `bollinger_bands` | BollingerBands | Standard (TA-Lib) |

---

## 4. Tests

### 4.1 Distribución

| Archivo | Tests | Cobertura |
|---------|-------|-----------|
| `test_schemas.py` | 11 | Contratos, RunConfig SHA256, RESULT_COLUMNS |
| `test_grid.py` | 13 | Cartesian, chunking, dedup, estimate, registry space |
| `test_metrics.py` | 13 | Sharpe, Sortino, Calmar, DD, trade metrics, edge cases |
| `test_engine.py` | 9 | Simple/FSM/auto mode, batch, determinismo, errors |
| `test_reporting.py` | 5 | CSV, HTML, Plotly fallback, output_dir creation |
| `test_integration.py` | 9 | E2E pipeline, grid→metrics, checkpoint resume, direct runners |
| **Total backtesting** | **60** | |

### 4.2 Suite completa

| Scope | Tests | Estado |
|-------|-------|--------|
| Data (Sprint 1) | 256 | ✅ PASS |
| Indicators (Sprint 2) | 88 | ✅ PASS |
| Risk (Sprint 3) | 95 | ✅ PASS |
| **Backtesting (Sprint 4)** | **60** | **✅ PASS** |
| Benchmarks | 4 | ✅ PASS |
| **Total** | **509+** | **✅ ALL PASS** |

---

## 5. Decisiones de Diseño

### 5.1 Engine Python puro + Numba (sin VBT PRO)

**Decisión:** Implementar el engine de backtesting como bar-loop Python con Numba para indicadores, sin depender de VectorBT PRO como runtime.

**Razón:**
- VBT PRO requiere licencia + instalación vía SSH (GitHub repo privado). Clave SSH no configurada al momento de Sprint 4.
- El bar-loop propio ofrece control total sobre gap-aware fills, slippage y la FSM de posiciones.
- El `VECTORIZABILITY` dict del prototipo Sprint 3 se reutiliza para auto-select modo simple/FSM.

**Path forward:** Integrar VBT PRO como execution path alternativo en Sprint 5+ cuando SSH key esté configurada. La interfaz `BacktestEngine.run(mode=...)` ya contempla esta extensión.

### 5.2 Dual runner (FSM + simple)

**Decisión:** Dos runners independientes — `run_simple_backtest()` para archetipos de alta vectorizabilidad (A/B), `run_fsm_backtest()` para arquetipos complejos (C/D/E).

**Razón:**
- Archetypes A (TrendFollowing) y B (MeanReversion) no necesitan pyramiding, partial TP, ni multi-portfolio. Un bar-loop ligero es suficiente y ~10× más rápido.
- Archetypes C/D/E (Mixed, Pyramidal, GridDCA) requieren la PositionStateMachine completa.
- El auto-select es transparente: el usuario no necesita elegir — `mode="auto"` decide correctamente.

### 5.3 Parquet + ZSTD para persistencia

**Decisión:** Checkpoints persisten estado en JSON y resultados en Parquet con compresión ZSTD por chunk.

**Razón:**
- Parquet es el formato nativo del stack (ya usado en data/). No introduce dependencias adicionales.
- ZSTD ofrece buen ratio compresión/velocidad.
- Chunks independientes permiten resume y paralelismo futuro.
- Overhead de serialización medido: <0.2% del tiempo total.

### 5.4 RunConfig con SHA256 determinístico

**Decisión:** Cada `RunConfig.run_id` es un hash SHA256[:16] del payload completo (symbol, timeframe, archetype, indicator_params, risk_overrides).

**Razón:**
- Determinístico: misma configuración → mismo ID → idempotente.
- Elimina la necesidad de UUIDs o contadores globales.
- Permite deduplicación trivial en grids con solapamiento.

---

## 6. Bugs Encontrados y Resueltos

### 6.1 `create_sizer()` API mismatch

**Síntoma:** `TypeError` en `run_fsm_backtest()` al invocar `create_sizer(risk_config.sizing.model, risk_config)`.

**Causa:** La firma real de `create_sizer()` (Sprint 3) es `create_sizer(cfg: SizingConfig)`, no acepta dos argumentos.

**Fix:** Cambiar a `create_sizer(risk_config.sizing)`.

### 6.2 NumPy RuntimeWarning en equity curves cortas

**Síntoma:** `RuntimeWarning: Degrees of freedom <= 0 for slice` en `np.std(returns, ddof=1)` cuando la equity curve tiene <2 puntos.

**Fix:** Envolver llamadas a `np.std()` con `np.errstate(divide='ignore', invalid='ignore')`. Los early returns pre-existentes (`len < 2`) ya protegen la lógica, pero NumPy emitía el warning antes de llegar al guard.

---

## 7. Benchmarks

Benchmark completo documentado en [`docs/backtesting_benchmarks.md`](backtesting_benchmarks.md).

### Resumen

| Métrica | Valor |
|---------|-------|
| Configuración | 1,024 combos × 2,160 barras 1h (3 meses BTCUSDT) |
| Throughput | **63.7 backtests/sec** (3,823/min) |
| Memoria peak (exec) | 0.9 MB |
| Serialización Parquet | 0.15% del tiempo total |
| Proyección 100K | ~26 min (single-thread) |
| Proyección 100K (14-core) | ~1.9 min (estimado con multiprocessing) |

El target de "100K < 5 min" es alcanzable vía multiprocessing sin cambios arquitectónicos.

---

## 8. Gates y Diferidos

| Gate (§6.1 / §9) | Estado | Nota |
|-------------------|--------|------|
| engine.py con run() + run_batch() | ✅ PASS | |
| grid.py con chunking + dedup | ✅ PASS | |
| metrics.py con métricas exportables | ✅ PASS | |
| reporting.py con dashboard exploratorio | ✅ PASS | |
| tests/backtesting/ con cobertura real | ✅ PASS | 60 tests |
| Bridge funcional A/B/C en dataset real/sintético | ✅ PASS | |
| Persistencia intermedia en Parquet | ✅ PASS | |
| Benchmark reproducible | ✅ PASS | `backtesting_benchmarks.md` |
| **Validación histórica vs TV** | **⏳ DIFERIDO a Sprint 5** | Ver §8.1 |

### 8.1 Diferimiento de `validation_report.md`

**Decisión:** Diferir la validación contra TradingView (T4.6) a Sprint 5.

**Justificación:**
1. La automatización Puppeteer para extraer resultados de TV existe, pero requiere ejecución manual con TV abierto (~30-60 min por lote).
2. Los datos de TV no están persistidos — no hay baseline pregrabado contra el cual comparar.
3. El engine produce resultados coherentes internamente (FSM vs simple consistency, determinismo verificado, equity monotonicity) pero la paridad bit-level con TV requiere investigación de las diferencias en: fill model, gap handling, comisiones, y MTF alignment.
4. Sprint 5 (Optimización + Anti-Overfitting) es el contexto natural para hacer esta validación, ya que la optimización necesita resultados confiables.

**Plan de validación para Sprint 5:**
- Seleccionar 10 combinaciones (2 archetypes × 5 param sets) representativas.
- Ejecutar en SuiteTrading y extraer resultados de TV vía Puppeteer.
- Comparar 4 métricas con tolerancias: Net Profit (±5%), Win Rate (±5pp), Profit Factor (±5%), Max DD (±10%).
- Documentar causas de divergencia aceptables (gap fills, slippage, timing).

---

## 9. Próximos Pasos — Sprint 5

| Área | Descripción |
|------|-------------|
| Multiprocessing | Paralelizar `run_batch()` con `ProcessPoolExecutor` (target: 100K < 5 min) |
| Anti-overfitting | Walk-forward, Monte Carlo, out-of-sample splits |
| Optimización | Grid screening → refinamiento bayesiano |
| Validación TV | 10 combinaciones comparadas vs TradingView (T4.6 retomado) |
| VBT PRO (opcional) | Integración como execution path alternativo cuando SSH key disponible |
| Numba runners | JIT-compile los bar-loops para rendimiento C-like |
