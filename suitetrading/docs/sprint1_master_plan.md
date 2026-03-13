# Sprint 1 — Data Infrastructure: Master Plan

> **Objetivo**: Diseñar e implementar un pipeline de datos robusto que alimente
> todo el stack de backtesting (VectorBT), validación (NautilusTrader) y
> producción (live trading). Datos correctos son el prerequisito absoluto —
> ningún indicador, RM o backtest tiene valor si los datos subyacentes son
> defectuosos.

---

## 1. Contexto: ¿Por Qué Sprint 1 es Crítico?

El Sprint 0 produjo:
- Catálogo de 15 indicadores con fórmulas exactas
- Especificación de RM como state machine determinística
- 3 prototipos Numba (Firestorm, SSL, WaveTrend) con 49 tests

**Todo eso opera sobre datos OHLCV**. Sin un pipeline de datos confiable:
- Los indicadores computan basura (garbage in → garbage out)
- Las señales MTF se desalinean y producen look-ahead bias
- Los backtests reportan métricas infladas que no sobreviven producción
- Walk-forward y CSCV (Sprint 5) requieren años de historia limpia

### Dependencias Downstream

```
Sprint 1 (Datos) ──► Sprint 2 (Indicadores) ──► Sprint 4 (VectorBT)
                 ──► Sprint 3 (Risk Mgmt)    ──► Sprint 5 (Optimization)
                                              ──► Sprint 6 (NautilusTrader)
```

Cada sprint posterior **consume datos de Sprint 1** directamente.

---

## 2. Decisiones Arquitectónicas

### 2.1 Estrategia de Descarga: Binance Vision Bulk + CCXT Incremental

| Aspecto | Binance Vision | CCXT |
|---------|---------------|------|
| **Caso de uso** | Historia masiva (años) | Gaps, datos recientes, otros exchanges |
| **Velocidad** | ~500 MB/min (bulk CSV/ZIP) | ~100 requests/min (rate limited) |
| **Cobertura** | Solo Binance Spot+Futures | 100+ exchanges |
| **Formato** | CSV pre-generado por mes | JSON → OHLCV normalizado |
| **Fiabilidad** | Archivos estáticos, no fallan | APIs pueden cambiar, rate limits |

**Decisión**: Binance Vision como fuente primaria (80% de los datos), CCXT como
complemento para gaps, exchanges adicionales (Bybit, OKX), y datos recientes
que aún no están en el bulk.

**Justificación**: Descargar 3 años de 1m data para BTC vía CCXT tomaría
~26 horas (525,600 requests con paginación). Vía Binance Vision: ~5 minutos
(36 archivos ZIP de ~15 MB cada uno).

### 2.2 Almacenamiento: Parquet + ZSTD

| Formato | Read 1y 1m | Write 1y 1m | Size 1y 1m | Random Access |
|---------|-----------|-------------|-----------|---------------|
| CSV | ~8s | ~12s | ~45 MB | No |
| HDF5 | ~1.5s | ~3s | ~30 MB | Sí (chunks) |
| **Parquet+ZSTD** | **~0.6s** | **~1.2s** | **~8 MB** | Sí (row groups) |
| Parquet+Snappy | ~0.5s | ~1.0s | ~12 MB | Sí |
| SQLite | ~3s | ~5s | ~35 MB | Sí (index) |

**Decisión**: Parquet con compresión ZSTD (ratio ~6:1), balance óptimo entre
velocidad de lectura y tamaño. Snappy es ~20% más rápido en lectura pero 50%
más grande — ZSTD gana para nuestro caso (datasets medianos, I/O no es
bottleneck vs cómputo de indicadores).

**Esquema de particionado**:
```
data/
  {exchange}/
    {symbol}/
      {timeframe}/
        {YYYY-MM}.parquet
```

Ejemplo: `data/binance/BTCUSDT/1m/2024-01.parquet`

**Justificación**: Particionado mensual permite descarga incremental (solo meses
nuevos), queries eficientes por rango de fechas, y tamaño manejable por archivo
(~2-8 MB para 1m, <1 MB para 4H+).

### 2.3 Resampling: Desde 1m Base + Validación Cruzada

**Opciones evaluadas**:

| Estrategia | Pros | Contras |
|------------|------|---------|
| Descargar cada TF nativo | Datos "oficiales" del exchange | 10x storage, 10x tiempo descarga, divergencias entre TFs |
| **Resamplear desde 1m** | Una sola fuente de verdad, consistencia total | Requiere validación contra datos nativos |
| Mixto: 1m + validar contra nativos | Mejor de ambos mundos | Más complejo, pero correcto |

**Decisión**: Descargar datos nativos de 1m como base. Resamplear a todos los
TFs superiores (3m → M). Descargar datos nativos de 1H y 1D para **validación
cruzada** (no como fuente operativa). Tolerancia: OHLC < 0.01%, Volume exact.

**Justificación**: Pine Script usa `request.security()` que internamente
resamplea. Si nuestro resampling coincide con TradingView (que usa datos de
exchange nativos), las señales serán idénticas. Validar contra datos nativos de
1H/1D confirma que nuestro resampling es correcto.

### 2.4 Pares y Cobertura Temporal

| Par | Disponible desde | Historia objetivo | Justificación |
|-----|-----------------|-------------------|---------------|
| **BTCUSDT** | 2017-08 (Binance) | 2017-08 → presente | Referencia universal, más liquid |
| **ETHUSDT** | 2017-08 (Binance) | 2017-08 → presente | 2do más liquid, correlación con BTC |
| **SOLUSDT** | 2020-08 (Binance) | 2020-08 → presente | Par principal del usuario, historial Puppeteer |

**Extensiones futuras** (no Sprint 1, pero el pipeline debe soportar):
- Bybit: BTCUSDT perpetual (post Sprint 6)
- OKX: BTCUSDT perpetual (post Sprint 6)
- Pares adicionales: BNBUSDT, AVAXUSDT, etc.

### 2.5 Timeframes a Generar

Desde la base 1m, generar los 10 TFs que usa el Pine Script:

```
1m (base, descargado)
├── 3m  (resampleado)
├── 5m  (resampleado)
├── 15m (resampleado)
├── 30m (resampleado)
├── 45m (resampleado)
├── 1H  (resampleado + validación contra nativo)
├── 4H  (resampleado)
├── D   (resampleado + validación contra nativo)
├── W   (resampleado)
└── M   (resampleado)
```

**Nota**: 45m no existe como TF nativo en Binance. Solo se puede obtener por
resampling desde 1m/3m/5m/15m. Esto confirma que el enfoque de resampling
desde base es obligatorio.

---

## 3. Warmup: Cálculo Exacto por Indicador

El warmup es la cantidad de datos **antes del inicio del backtest** necesarios
para que los indicadores se estabilicen. Sin warmup suficiente, las primeras
señales son ruido.

### Warmup por Indicador (bars del TF donde opera)

| Indicador | TF Operativo | Período Máx | Warmup (bars) | Warmup (días si TF=1H) |
|-----------|-------------|-------------|---------------|------------------------|
| EMA 200 | Base | 200 | 250 | 10.4 |
| MTF SMA 600 | 4H | 600 | 700 | 116.7 |
| Firestorm TM | D | 50 | 60 | 60.0 |
| WaveTrend | 4H | 30+12+3 | 60 | 10.0 |
| RSI+BB | Base | 14+50 | 70 | 2.9 |
| Squeeze Mom | W | 20+20 | 50 | 350.0 |
| MACD | D | 26+9 | 40 | 40.0 |

**Caso peor**: Squeeze Momentum en Weekly con SMA(20) → necesita 50 barras
semanales = **350 días** de pre-data antes de la ventana de backtest.

**Decisión**: El pipeline debe exponer un `warmup_calculator(indicators_config,
base_tf) → timedelta` que determine cuánta historia extra se necesita.

**Implementación práctica**: Para cada backtest, cargar `backtest_start -
max_warmup` como inicio de datos. Los indicadores se computan desde ese punto,
pero las métricas de backtest solo cuentan desde `backtest_start`.

---

## 4. Tareas Detalladas

### T1.1 — Evaluación y Setup de Fuentes de Datos
**Prioridad**: P0 (bloqueante para todo lo demás)

- Instalar CCXT y validar conexión a Binance (public API, sin API key)
- Descargar muestra de prueba: BTCUSDT 1m, enero 2024, vía CCXT
- Descargar misma muestra vía Binance Vision bulk
- Comparar: filas, timestamps, OHLCV values, volumen
- Documentar rate limits reales de Binance (peso por request, requests/min)
- Documentar historia disponible por par (fecha más antigua con datos)

**Entregable**: `docs/data_source_evaluation.md`

### T1.2 — Diseño e Implementación del Storage Manager
**Prioridad**: P0

- Definir schema Parquet: columnas, tipos, metadata
- Implementar `ParquetStore` class con operaciones:
  - `write(exchange, symbol, timeframe, df)` → escribe/appende Parquet particionado
  - `read(exchange, symbol, timeframe, start, end)` → lee rango de fechas
  - `list_available()` → inventario de datos disponibles
  - `info(exchange, symbol, timeframe)` → fecha min/max, #rows, gaps
- Benchmark: escritura y lectura de 1 año de 1m (target: lectura < 2s)
- Implementar compresión ZSTD con fallback configurable

**Entregable**: `src/suitetrading/data/storage.py` + tests

### T1.3 — Pipeline de Descarga
**Prioridad**: P0

- **Binance Vision downloader**:
  - Descarga de archivos ZIP mensuales para klines
  - URL pattern: `https://data.binance.vision/data/spot/monthly/klines/{symbol}/{interval}/`
  - Descompresión, parsing CSV, conversión a DataFrame
  - Manejo de archivos faltantes (par no existía en ese mes)
- **CCXT downloader**:
  - `fetch_ohlcv()` con paginación correcta (since/limit)
  - Rate limiting con exponential backoff
  - Normalización de timestamps a UTC
- **Orquestador**:
  - `download_historical(symbol, start, end, source="auto")` → elige fuente
  - Descarga incremental: solo meses/días faltantes
  - Progress bar (tqdm o rich)
  - Retry con backoff para errores transitorios
  - Validación post-descarga inmediata

**Entregable**: `src/suitetrading/data/downloader.py` + tests

### T1.4 — Motor de Resampling Multi-Timeframe
**Prioridad**: P1

- Implementar resampler que genera todos los TFs desde 1m base:
  - `resample(df_1m, target_tf) → DataFrame`
  - Reglas: open=first, high=max, low=min, close=last, volume=sum
  - Manejo correcto de barras incompletas (última barra del día si mercado 24/7)
- Validar contra datos nativos de 1H y 1D:
  - Descargar 1 mes de 1H y 1D nativos para BTCUSDT
  - Comparar con resampled: OHLC tolerance < 0.01%, Volume exact
  - Documentar discrepancias y sus causas
- Integrar con `mtf.py` existente (refactorizar `resample_ohlcv()`)
- Implementar `WarmupCalculator`:
  - Input: lista de (indicador, params, timeframe)
  - Output: timedelta necesario antes del backtest_start

**Entregable**: `src/suitetrading/data/resampler.py` + validación report

### T1.5 — Validación de Calidad de Datos
**Prioridad**: P1

- Implementar `DataValidator` class:
  - `validate_ohlcv(df)` → lista de issues encontrados
  - Checks: gaps, duplicados, OHLCV lógico, volume negativo, timestamps no-UTC
  - `detect_gaps(df, expected_interval)` → DataFrame de gaps con duración
  - `fill_strategy(df, method="ffill")` → DataFrame rellenado con marking
- Generar reporte de calidad para los 3 pares × historia completa
- Documentar gaps conocidos (mantenimiento Binance, etc.)
- Survivorship check: verificar que pares existían durante todo el período

**Entregable**: `src/suitetrading/data/validator.py` + `docs/data_quality_report.md`

---

## 5. Configuración del Proyecto

### Settings a agregar (`config/settings.py`)

```python
class Settings(BaseSettings):
    # Existing
    data_dir: str = "./data"
    results_dir: str = "./results"
    log_level: str = "INFO"

    # Sprint 1 additions
    raw_data_dir: str = "./data/raw"          # Descargas sin procesar
    processed_data_dir: str = "./data/processed"  # Parquet particionado

    # Exchange config
    default_exchange: str = "binance"
    binance_vision_base_url: str = "https://data.binance.vision"

    # Download config
    download_rate_limit_weight: int = 1200     # Binance weight limit per minute
    download_retry_max: int = 3
    download_retry_backoff: float = 2.0        # Exponential backoff base

    # Storage config
    parquet_compression: str = "zstd"
    parquet_compression_level: int = 3         # ZSTD level (1-22, 3 = good balance)

    # Default pairs and timeframes
    default_symbols: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    base_timeframe: str = "1m"
    target_timeframes: list[str] = ["1m","3m","5m","15m","30m","45m","1h","4h","1d","1w","1M"]
```

---

## 6. Criterios de Éxito

| # | Criterio | Medición |
|---|----------|----------|
| 1 | Descarga completa de 3 pares × 1m base × 3+ años | `storage.info()` muestra cobertura continua |
| 2 | Resampling a 10 TFs validado contra datos nativos | OHLC diff < 0.01%, Volume diff = 0 |
| 3 | Lectura de 1 año de 1m < 2 segundos desde Parquet | Benchmark reproducible con `pytest-benchmark` |
| 4 | Gaps documentados y estrategia de handling definida | `data_quality_report.md` generado |
| 5 | Pipeline incremental: solo descarga datos nuevos | Re-run no re-descarga meses ya almacenados |
| 6 | Tests unitarios para cada módulo (≥80% coverage) | `pytest --cov` report |

---

## 7. Riesgos y Mitigaciones

| Riesgo | Prob | Impacto | Mitigación |
|--------|------|---------|------------|
| Binance Vision no tiene 45m data | Seguro | Bajo | Solo generamos 45m por resampling (confirmado: 45m no es TF nativo) |
| Rate limits de CCXT bloquean descargas largas | Media | Medio | Exponential backoff + switch a Binance Vision para bulk |
| Gaps en datos de Binance (mantenimiento) | Alta | Medio | Forward-fill + marking + documentación en quality report |
| Datos 1m de 2017 tienen baja calidad | Media | Bajo | Marcar períodos pre-2019 como "low confidence" en metadata |
| Resampling no coincide con TradingView | Media | Alto | Validación cruzada obligatoria contra datos nativos 1H/1D |
| ZSTD no disponible en PyArrow build | Baja | Bajo | Fallback a Snappy (ya configurado en settings) |

---

## 8. Estimación de Storage

| Par | TF | 3 Años | 7 Años |
|-----|----|--------|--------|
| BTCUSDT | 1m | ~24 MB (ZSTD) | ~56 MB |
| BTCUSDT | Todos (10 TFs) | ~28 MB | ~65 MB |
| 3 pares × Todos TFs | — | **~85 MB** | **~170 MB** |

Totalmente manejable en local. Cloud no necesario para datos.

---

## 9. Entregables Finales del Sprint

### Código
- `src/suitetrading/data/downloader.py` — Pipeline multi-fuente
- `src/suitetrading/data/storage.py` — ParquetStore con particionado
- `src/suitetrading/data/resampler.py` — Motor de resampling + WarmupCalculator
- `src/suitetrading/data/validator.py` — Validación de calidad
- `src/suitetrading/config/settings.py` — Configuración ampliada

### Documentación
- `docs/data_source_evaluation.md` — Benchmark de fuentes
- `docs/data_quality_report.md` — Reporte de calidad por par
- `docs/sprint1_benchmarks.md` — Benchmarks de lectura/escritura/resampling

### Tests
- `tests/data/test_downloader.py`
- `tests/data/test_storage.py`
- `tests/data/test_resampler.py`
- `tests/data/test_validator.py`
- `tests/data/test_integration.py` — End-to-end: download → store → resample → validate

### Datasets
- BTCUSDT 1m: 2017-08 → presente
- ETHUSDT 1m: 2017-08 → presente
- SOLUSDT 1m: 2020-08 → presente
- Validación: BTCUSDT 1H y 1D nativos (1 mes para cross-check)
