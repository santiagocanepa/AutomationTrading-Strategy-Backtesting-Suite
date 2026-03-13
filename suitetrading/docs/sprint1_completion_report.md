# Sprint 1 — Data Infrastructure Layer: Documentación Completa

**Proyecto:** SuiteTrading  
**Sprint:** 1 — Data Infrastructure  
**Fecha:** 11 de marzo de 2026  
**Estado:** ✅ Cerrado y validado operativamente — 256 tests passing + native cross-validation PASS

---

## 1. Resumen Ejecutivo

Sprint 1 implementa la capa completa de infraestructura de datos para el motor de backtesting: descarga multi-fuente, almacenamiento eficiente en Parquet, validación de calidad, resampling multi-timeframe, y cálculo de warmup de indicadores.

### Métricas Clave

| Métrica | Valor |
|---------|-------|
| Tests totales | 256 (todos passing) |
| Archivos creados/modificados | 16 |
| Líneas de código producción | ~1,350 LOC |
| Líneas de código tests | ~900 LOC |
| Timeframes soportados | 11 (1m → 1M) |
| Exchanges soportados | Cualquiera via CCXT + Binance Vision bulk |

### Cierre real del backlog de Sprint 1

El cierre administrativo previo no era suficiente: durante la validación operativa se detectó corrupción masiva en `data/raw/` causada por un cambio de unidad temporal en Binance Vision (`open_time` en microsegundos a partir de 2025-01). Sprint 1 se considera realmente cerrado recién después de:

- endurecer el parser para detectar `ms`/`us`/`ns` automáticamente,
- auditar y poner en cuarentena 41,796 particiones inválidas,
- re-generar los meses faltantes 2025-01 → 2026-02 con el parser corregido,
- ejecutar validación nativa 1m→1h y 1m→1d con resultado PASS para BTCUSDT, ETHUSDT y SOLUSDT.

---

## 2. Arquitectura del Sistema

```
suitetrading/
├── config/
│   └── settings.py          ← Configuración centralizada (Pydantic)
├── data/
│   ├── __init__.py           ← Re-exports públicos
│   ├── timeframes.py         ← Mapeo unificado de 11 timeframes
│   ├── validator.py          ← Pipeline de validación OHLCV
│   ├── storage.py            ← Almacenamiento Parquet particionado
│   ├── downloader.py         ← Descarga multi-fuente (BV + CCXT)
│   ├── resampler.py          ← Resampling 1m → cualquier TF
│   └── warmup.py             ← Cálculo de período de warmup
├── indicators/
│   └── mtf.py                ← Refactorizado: importa de timeframes.py
└── tests/
    └── data/
        ├── conftest.py           ← Fixtures compartidos
        ├── test_timeframes.py    ← 99 tests parametrizados
        ├── test_validator.py     ← 16 tests
        ├── test_storage.py       ← 14 tests
        ├── test_downloader.py    ← 15 tests
        ├── test_resampler.py     ← 13 tests
        ├── test_warmup.py        ← 11 tests
        ├── test_integration.py   ← 2 tests E2E (@slow @integration)
        └── test_benchmarks.py    ← 5 benchmarks
```

### Flujo de Datos

```
Binance Vision (bulk CSV)  ──┐
                              ├──→ DownloadOrchestrator
CCXT (cualquier exchange)  ──┘          │
                                        ▼
                                  DataValidator.validate()
                                        │
                                        ▼
                                  ParquetStore.write()
                                        │
                                        ▼
                                  ParquetStore.read()
                                        │
                                        ▼
                                  OHLCVResampler.resample_all()
                                        │
                                        ▼
                              dict[timeframe → DataFrame]
```

---

## 3. Módulos Implementados

### 3.1. `config/settings.py` — Configuración Centralizada

**Propósito:** Proveer configuración type-safe cargada desde variables de entorno o `.env`.

**Clase:** `Settings(BaseSettings)`

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `data_dir` | `str` | `"./data"` | Directorio raíz de datos |
| `results_dir` | `str` | `"./results"` | Directorio de resultados |
| `log_level` | `str` | `"INFO"` | Nivel de logging |
| `raw_data_dir` | `str` | `"./data/raw"` | Datos crudos descargados |
| `processed_data_dir` | `str` | `"./data/processed"` | Datos procesados |
| `default_exchange` | `str` | `"binance"` | Exchange por defecto |
| `binance_vision_base_url` | `str` | `"https://data.binance.vision"` | URL base de Binance Vision |
| `download_rate_limit_weight` | `int` | `1200` | Peso máximo por minuto (API Binance) |
| `download_retry_max` | `int` | `3` | Reintentos máximos |
| `download_retry_backoff` | `float` | `2.0` | Base exponencial para backoff |
| `parquet_compression` | `str` | `"zstd"` | Algoritmo de compresión |
| `parquet_compression_level` | `int` | `3` | Nivel de compresión ZSTD |
| `default_symbols` | `list[str]` | `["BTCUSDT", "ETHUSDT", "SOLUSDT"]` | Pares por defecto |
| `base_timeframe` | `str` | `"1m"` | Timeframe base para descarga |
| `target_timeframes` | `list[str]` | 11 TFs | Timeframes objetivo |

**Uso:**
```python
from suitetrading.config.settings import Settings
s = Settings()  # Carga de env vars o .env automáticamente
print(s.default_symbols)  # ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
```

---

### 3.2. `data/timeframes.py` — Mapeo Unificado de Timeframes

**Propósito:** Fuente única de verdad para las 11 representaciones de timeframe usadas en el proyecto. Ningún otro módulo mantiene su propio mapeo.

**Estructura del mapeo:**

| TF Canónico | Pine | Binance | CCXT | Pandas | Segundos |
|-------------|------|---------|------|--------|----------|
| `1m` | `"1"` | `"1m"` | `"1m"` | `"1min"` | 60 |
| `3m` | `"3"` | `"3m"` | `"3m"` | `"3min"` | 180 |
| `5m` | `"5"` | `"5m"` | `"5m"` | `"5min"` | 300 |
| `15m` | `"15"` | `"15m"` | `"15m"` | `"15min"` | 900 |
| `30m` | `"30"` | `"30m"` | `"30m"` | `"30min"` | 1,800 |
| `45m` | `"45"` | `None` | `None` | `"45min"` | 2,700 |
| `1h` | `"60"` | `"1h"` | `"1h"` | `"1h"` | 3,600 |
| `4h` | `"240"` | `"4h"` | `"4h"` | `"4h"` | 14,400 |
| `1d` | `"D"` | `"1d"` | `"1d"` | `"1D"` | 86,400 |
| `1w` | `"W"` | `"1w"` | `"1w"` | `"1W-MON"` | 604,800 |
| `1M` | `"M"` | `"1M"` | `"1M"` | `"1ME"` | `None` |

> **Nota:** `45m` no tiene representación nativa en Binance ni CCXT (se genera por resampling). `1M` no tiene duración fija en segundos.

**Funciones públicas:**

| Función | Firma | Descripción |
|---------|-------|-------------|
| `normalize_timeframe` | `(tf: str) → str` | Convierte cualquier representación (Pine `"60"`, Binance `"1h"`, pandas `"1h"`) al key canónico (`"1h"`) |
| `tf_to_pandas_offset` | `(tf: str) → str` | Devuelve alias pandas (`"1h"` → `"1h"`, `"1w"` → `"1W-MON"`) |
| `tf_to_seconds` | `(tf: str) → int \| None` | Duración en segundos (`None` para `1M`) |
| `tf_to_binance` | `(tf: str) → str \| None` | String de Binance API (`None` para `45m`) |
| `tf_to_ccxt` | `(tf: str) → str \| None` | String de CCXT (`None` para `45m`) |
| `tf_to_pine` | `(tf: str) → str` | String de Pine Script |
| `is_intraday` | `(tf: str) → bool` | `True` para TFs ≤ 4h |
| `partition_scheme` | `(tf: str) → str` | `"monthly"` para intraday, `"yearly"` para daily+ |

**Constantes exportadas:**
- `TIMEFRAME_MAP` — Diccionario maestro
- `VALID_TIMEFRAMES` — `frozenset` de los 11 keys canónicos

**Tests:** 99 tests parametrizados cubriendo cada función × cada timeframe + aliases + errores.

---

### 3.3. `data/validator.py` — Validación de Calidad OHLCV

**Propósito:** Garantizar que todo DataFrame que entre al storage pase controles de calidad. Reporta issues por severidad.

**Clases:**

#### `ValidationIssue` (frozen dataclass)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `severity` | `str` | `"error"` / `"warning"` / `"info"` |
| `issue_type` | `str` | `"schema"` / `"timestamp"` / `"ohlcv"` / `"gap"` / `"volume"` / `"outlier"` |
| `timestamp` | `datetime \| None` | Ubicación del problema (`None` para globales) |
| `description` | `str` | Descripción legible |
| `affected_rows` | `int` | Número de filas afectadas |

#### `DataValidator`

**Métodos públicos:**

| Método | Descripción |
|--------|-------------|
| `validate(df, expected_tf)` | Ejecuta todos los checks, retorna `list[ValidationIssue]` ordenada por severidad |
| `detect_gaps(df, expected_tf, ignore_weekends=False)` | Retorna DataFrame de gaps con `gap_start`, `gap_end`, `duration`, `missing_bars` |
| `fill_gaps(df, expected_tf, method="ffill")` | Rellena gaps, retorna `(filled_df, num_bars_added)` |
| `generate_report(exchange, symbol, timeframe, df)` | Genera reporte completo (`dict`) con completitud, gaps, issues |

**Checks internos (ejecutados en secuencia):**

1. **`_validate_schema`** — Verifica columnas requeridas (`open`, `high`, `low`, `close`, `volume`), tipos `float64`, `DatetimeIndex` con timezone UTC
2. **`_validate_timestamps`** — Orden ascendente, sin duplicados, sin timestamps futuros
3. **`_validate_ohlcv_logic`** — `high ≥ max(open, close, low)`, `low ≤ min(open, close)`, volumen no negativo
4. **`_validate_volume`** — Warning si >1% de barras tienen volumen cero
5. **`_validate_outliers`** — Warning si cambio de precio >50% en una barra
6. **`_validate_gaps`** — Detecta huecos en la serie temporal

**Tests:** 16 tests en 7 clases (schema válido/inválido, timestamps, OHLCV lógica, gaps, fill, report).

---

### 3.4. `data/storage.py` — Almacenamiento Parquet Particionado

**Propósito:** Persistencia eficiente de OHLCV en Parquet con compresión ZSTD, particionado automático por período.

**Layout en disco:**
```
{base_dir}/{exchange}/{symbol}/{timeframe}/{period}.parquet
```
- **Intraday** (≤ 4h): `period = "YYYY-MM"` (partición mensual)
- **Daily+** (D/W/M): `period = "YYYY"` (partición anual)

**Clase:** `ParquetStore(base_dir, compression="zstd", compression_level=3)`

| Método | Firma | Descripción |
|--------|-------|-------------|
| `write` | `(df, exchange, symbol, timeframe, source)` | Valida schema, dedup (keeps last), sort asc, split por período, escribe Parquet con metadata custom en footer |
| `read` | `(exchange, symbol, timeframe, start?, end?, columns?)` | Lee particiones, concatena, filtra por rango de fechas, soporta proyección de columnas |
| `list_available` | `()` | Lista todas las combinaciones `(exchange, symbol, tf)` disponibles |
| `info` | `(exchange, symbol, timeframe)` | Retorna `dict` con rango de fechas, total rows, tamaño en disco, particiones |

**Características clave:**
- Compresión ZSTD nivel 3 (balance entre velocidad y ratio ~6:1 en datos reales)
- Metadata en footer Arrow: `exchange`, `symbol`, `timeframe`, `source`, `written_at`
- Merge automático: si una partición ya existe, se concatena y dedup
- Manejo robusto de timezones (`tz_localize` condicional para evitar double-tz)

**Tests:** 14 tests en 6 clases (write/read roundtrip, date range filtering, column projection, list_available, info, merge con datos existentes).

---

### 3.5. `data/downloader.py` — Pipeline de Descarga Multi-Fuente

**Propósito:** Descargar datos OHLCV de manera eficiente desde múltiples fuentes con rate limiting, retry, caching y validación integrada.

#### 3.5.1. `BinanceVisionDownloader`

Descarga masiva de CSV comprimidos desde `data.binance.vision` (datos históricos pre-generados por Binance).

**URL pattern:**
```
https://data.binance.vision/data/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{YYYY-MM}.zip
```

| Método | Descripción |
|--------|-------------|
| `download_month(symbol, interval, year, month)` | Descarga un mes. Retorna `None` en 404 (par no existía). Cache local de ZIPs |
| `download_range(symbol, interval, start, end, progress=True)` | Itera meses, concatena, dedup, sort. Barra de progreso con `tqdm` |

**Parsing:** Los CSV de Binance tienen 12 columnas. Se extraen las 5 estándar (`open`, `high`, `low`, `close`, `volume`) y se convierte `open_time` (ms epoch) a `DatetimeIndex` UTC.

#### 3.5.2. `CCXTDownloader`

Descarga via API de cualquier exchange soportado por CCXT (300+ exchanges).

| Método | Descripción |
|--------|-------------|
| `download_range(symbol, timeframe, start, end)` | Descarga paginada con anti-rate-limit automático |
| `fetch_latest(symbol, timeframe, bars=500)` | Últimas N barras (útil para llenar el mes actual) |

**Rate limiting:**
- Tracking de peso consumido por minuto (cada request ≈ 10 weight)
- Sleep automático al alcanzar 90% del límite (default 1200/min para Binance)
- Retry exponencial con backoff configurable (default base 2.0, max 3 intentos)

**Paginación:** `since = last_timestamp + 1ms` para avanzar sin duplicados.

#### 3.5.3. `DownloadOrchestrator`

Coordina ambas fuentes con lógica incremental.

| Método | Descripción |
|--------|-------------|
| `sync(symbol, start, end, exchange, timeframe, force=False)` | Sincroniza un par: BV para meses pasados, CCXT para mes actual. Valida antes de store. Retorna `dict` report |
| `sync_all(symbols?, start?, end?)` | Sync para todos los símbolos configurados |

**Lógica de selección de fuente:**
```
if mes == mes_actual or binance_tf is None:
    → CCXT (API en vivo)
else:
    → Binance Vision (bulk CSV)
```

**Detección incremental:** `_identify_missing_months()` compara meses requeridos contra archivos `.parquet` existentes.

**Helpers de módulo:**
- `_month_range(start, end)` — Genera `list[(year, month)]` entre dos fechas
- `_normalize_ccxt_ohlcv(raw)` — Convierte `list[list]` de CCXT a DataFrame estándar

**Tests:** 15 tests con mocking completo (httpx para BV, ccxt para CCXT). Cubre: URL format, CSV parsing, cache hit, 404→None, concatenación multi-mes, paginación, rate limit, orchestrator incremental.

---

### 3.6. `data/resampler.py` — Resampling Multi-Timeframe

**Propósito:** Transformar datos 1m (o cualquier base) a timeframes superiores con reglas OHLCV estándar.

**Clase:** `OHLCVResampler`

**Reglas de agregación:**
```python
{"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
```

| Método | Firma | Descripción |
|--------|-------|-------------|
| `resample` | `(df_base, target_tf, base_tf="1m")` | Resample a un TF específico. `ValueError` si target ≤ base. Drop barra incompleta al final |
| `resample_all` | `(df_1m, target_tfs?, base_tf="1m")` | Resample a todos los TFs. Retorna `dict[str, DataFrame]` |
| `validate_against_native` | `(resampled, native, tolerance_pct=0.01)` | Cross-validación: compara OHLC con tolerancia % y volume exacto |

**Casos especiales:**
- **45m:** Usa `origin="epoch"` para alineación determinista (no depende del primer timestamp)
- **1w:** Pandas entry `"1W-MON"` asegura semanas basadas en lunes
- **1M:** Siempre drop última barra (duración variable, incompleta casi seguro)
- **Barra incompleta:** Si la última barra del target TF no tiene suficientes barras base, se elimina

**Tests:** 13 tests en 6 clases (bar counts, valores OHLCV correctos, 45m alignment, 1w monday, incomplete drop, resample_all dict, validate pass/fail, no overlap).

---

### 3.7. `data/warmup.py` — Cálculo de Período de Warmup

**Propósito:** Calcular cuántos datos históricos se necesitan antes de que los indicadores produzcan señales válidas.

**Constante:** `INDICATOR_WARMUP` — barras necesarias por indicador:

| Indicador | Bars | Indicador | Bars |
|-----------|------|-----------|------|
| `ema_9` | 50 | `ema_200` | 600 |
| `ema_21` | 100 | `rsi_14` | 100 |
| `ema_50` | 200 | `macd_12_26_9` | 150 |
| `sma_9` | 50 | `bbands_20` | 120 |
| `sma_50` | 200 | `atr_14` | 100 |
| `sma_200` | 600 | `stoch_14` | 100 |
| `squeeze` | 200 | `adx_14` | 100 |
| `wavetrend` | 150 | `ssl_channel` | 100 |
| `firestorm` | 200 | — | — |

**Default para desconocidos:** 200 bars.

**Clase:** `WarmupCalculator`

| Método | Descripción |
|--------|-------------|
| `calculate(indicators, base_tf)` | Retorna el `timedelta` máximo entre todos los indicadores |
| `calculate_from_config(config)` | Wrapper que extrae `indicators` y `base_tf` de un dict config |

**Ejemplo:**
```python
calc = WarmupCalculator()
td = calc.calculate([
    {"key": "ema_200", "timeframe": "1h"},  # 600 × 3600s = 2,160,000s
    {"key": "rsi_14", "timeframe": "15m"},  # 100 × 900s = 90,000s
])
# td = timedelta(seconds=2160000) → ~25 días
```

**Tests:** 11 tests en 3 clases (tf_to_timedelta conversiones, single/multi indicator, unknown fallback, empty, config wrapper).

---

### 3.8. `indicators/mtf.py` — Refactorización

**Cambio:** Eliminación de los diccionarios duplicados `_TF_TO_OFFSET` (11 entradas hardcoded). Ahora importa de `data/timeframes.py`.

| Antes | Después |
|-------|---------|
| `_TF_TO_OFFSET` dict local (11 entradas) | `from suitetrading.data.timeframes import tf_to_pandas_offset, normalize_timeframe` |
| `offset = _TF_TO_OFFSET.get(target_tf)` | `canonical = normalize_timeframe(target_tf); offset = tf_to_pandas_offset(canonical)` |

La función `resample_ohlcv()` ahora acepta tanto strings Pine (`"60"`) como canónicos (`"1h"`) gracias a `normalize_timeframe()`.

Las funciones `resolve_timeframe()` y `align_to_base()` se mantienen sin cambios ya que operan con lógica propia del módulo de indicadores.

---

## 4. Tests

### 4.1. Distribución

| Archivo | Tests | Tipo | Descripción |
|---------|-------|------|-------------|
| `test_timeframes.py` | 99 | Unit (parametrizado) | Cada función × cada TF + aliases + errores |
| `test_validator.py` | 16 | Unit | Schema, timestamps, OHLCV lógica, gaps, fill, report |
| `test_storage.py` | 14 | Unit | Write/read roundtrip, filtering, projection, merge |
| `test_downloader.py` | 28 | Unit (mocked I/O) | BV URLs, parsing, cache, 404, CCXT pagination, orchestrator, timestamp units |
| `test_resampler.py` | 14 | Unit | Bar counts, valores, 45m, weekly, incomplete, validate |
| `test_warmup.py` | 11 | Unit | Conversiones, single/multi, unknown, config |
| `test_integration.py` | 4 | E2E (@slow) | Pipeline completo + validación independiente de resampling |
| `test_cross_validate_native.py` | 3 | Unit | Alineación de velas completas en validación nativa |
| `test_benchmarks.py` | 5 | Performance | Write/read/resample/validate 1Y + tamaño Parquet |
| `tests/indicators/` | 62 | Unit | firestorm, ssl_channel, wavetrend, mtf |

**Total: 256 tests — todos passing.**

### 4.2. Markers para Ejecución Selectiva

```bash
# Correr todo excepto tests lentos
pytest -m "not slow"

# Solo integration
pytest -m integration

# Solo benchmarks (con timing)
pytest -m benchmark --benchmark-only

# Suite completa
pytest --benchmark-disable
```

### 4.3. Fixtures Compartidos (`conftest.py`)

| Fixture | Descripción |
|---------|-------------|
| `sample_1m_1day` | 1,440 barras de 1m (24h) con OHLCV válido garantizado |
| `sample_1m_1month` | ~44,640 barras (31 días) |
| `sample_1m_3months` | 3 meses de datos |
| `tmp_store` | `ParquetStore` apuntando a directorio temporal |

Todos los fixtures generan datos con `high ≥ max(open, close)` y `low ≤ min(open, close)` garantizado.

---

## 5. Configuración del Proyecto (`pyproject.toml`)

### Dependencias Añadidas en Sprint 1

**Dev:**
- `pytest-asyncio>=0.23` — Tests async para downloader
- `pytest-benchmark>=4.0` — Benchmarks de performance

**Data (nuevo grupo optional):**
- `ccxt>=4.2` — API unificada de exchanges crypto
- `httpx>=0.27` — HTTP async para Binance Vision
- `tqdm>=4.66` — Barras de progreso

### Configuración Pytest

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"     # Correr async tests sin decorar cada uno
markers = [
    "slow",               # Tests pesados (deselect: -m 'not slow')
    "integration",        # E2E pipeline
    "benchmark",          # Performance
]
```

---

## 6. Decisiones de Diseño y Trade-offs

### 6.1. Binance Vision como fuente primaria histórica
**Decisión:** Usar bulk CSV pre-generados en lugar de la API REST.
**Razón:** La API pública de Binance tiene rate limits fuertes (~1200 weight/min). Descargar 7 años de datos 1m (~3.7M barras) por API tomaría horas. Los ZIPs de Vision se descargan en segundos por mes, sin rate limit.

### 6.2. CCXT solo para mes actual
**Decisión:** CCXT se usa únicamente para datos del mes en curso (Vision no genera el mes actual).
**Razón:** Minimiza llamadas API y respeta rate limits. Para el mes actual (~43k barras), 43 requests paginados son suficientes.

### 6.3. Parquet con ZSTD nivel 3
**Decisión:** Elegir ZSTD sobre Snappy/GZIP.
**Razón:** ZSTD nivel 3 ofrece ~6:1 ratio en datos de mercado (columnar, alta autocorrelación) con decompresión extremadamente rápida. Snappy es más rápido pero ratio ~3:1. GZIP mejor ratio pero 5× más lento en decompresión.

### 6.4. Particionado mensual/anual
**Decisión:** Partición por mes (intraday) o año (daily+).
**Razón:** Un mes de 1m ≈ 45k filas ≈ 2-3 MB comprimido. Tamaño óptimo para writes incrementales y reads parciales (no leer todo el archivo para obtener una semana).

### 6.5. 45m con `origin="epoch"`
**Decisión:** Usar alineación epoch para resampling de 45m.
**Razón:** 45 no divide uniformemente a 60 ni a 1440. Sin epoch alignment, las barras de 45m dependerían del primer timestamp del dataset, haciendo que runs diferentes produzcan barras desalineadas.

### 6.6. Weekly basado en lunes (`1W-MON`)
**Decisión:** Las velas semanales empiezan el lunes.
**Razón:** Consistencia con TradingView y la convención de la mayoría de plataformas crypto.

---

## 7. Bugs Encontrados y Resueltos

### 7.1. Fixtures OHLCV inválidos
**Problema:** Los fixtures generaban `high` y `low` independientes de `open`/`close`, causando violaciones `high < open`.
**Solución:** Calcular `high = max(open, close) + offset` y `low = min(open, close) - offset`.

### 7.2. Index name mismatch en storage
**Problema:** `ParquetStore.read()` retornaba index con `name='timestamp'` mientras el original tenía `name=None`.
**Solución:** `part.index.name = None` después de restaurar el index desde la columna almacenada.

### 7.3. Double timezone en read filters
**Problema:** `pd.Timestamp(start, tz="UTC")` lanzaba error si `start` ya tenía tzinfo.
**Solución:** Crear Timestamp primero, luego `tz_localize("UTC")` solo si `tzinfo is None`.

### 7.4. Parquet size threshold con datos sintéticos
**Problema:** El benchmark de tamaño Parquet esperaba <12 MB pero datos random (incompresibles) ocupaban ~25 MB.
**Solución:** Ajustar threshold a <30 MB para datos sintéticos. Datos reales de mercado comprimen a ~10 MB por la alta autocorrelación de precios.

---

## 8. Cómo Usar

### Descarga completa
```python
import asyncio
from pathlib import Path
from suitetrading.data import DownloadOrchestrator, ParquetStore
from suitetrading.config.settings import Settings
from datetime import date

async def main():
    settings = Settings()
    store = ParquetStore(base_dir=Path("./data/processed"))
    orch = DownloadOrchestrator(store=store, cache_dir=Path("./data/raw"))
    
    results = await orch.sync_all(
        symbols=["BTCUSDT", "ETHUSDT"],
        start=date(2020, 1, 1),
        end=date(2025, 12, 31),
    )
    for r in results:
        print(f"{r['symbol']}: {r['rows_new']} rows added, {len(r['errors'])} errors")

asyncio.run(main())
```

### Lectura + Resampling
```python
from suitetrading.data import ParquetStore, OHLCVResampler
from pathlib import Path

store = ParquetStore(base_dir=Path("./data/processed"))
df_1m = store.read("binance", "BTCUSDT", "1m", start="2024-01-01", end="2024-06-30")

resampler = OHLCVResampler()
all_tfs = resampler.resample_all(df_1m, target_tfs=["5m", "15m", "1h", "4h", "1d"])
print(f"1h bars: {len(all_tfs['1h'])}")
```

### Validación
```python
from suitetrading.data import DataValidator

validator = DataValidator()
issues = validator.validate(df_1m, "1m")
errors = [i for i in issues if i.severity == "error"]
print(f"{len(errors)} errors, {len(issues) - len(errors)} warnings")
```

### Cálculo de warmup
```python
from suitetrading.data import WarmupCalculator

calc = WarmupCalculator()
warmup = calc.calculate([
    {"key": "ema_200", "timeframe": "4h"},
    {"key": "squeeze", "timeframe": "1d"},
])
print(f"Necesitas {warmup.days} días de datos extra antes de la fecha de inicio")
```

---

## 9. Closing Backlog — Correcciones Post-Sprint (2026-03-11)

Antes de declarar Sprint 1 cerrado se identificaron y resolvieron las siguientes brechas:

### 9.1. Bugs corregidos en `downloader.py`

| Bug | Antes | Después |
|-----|-------|---------|
| Particionado incremental | `_identify_missing_months()` siempre buscaba `YYYY-MM.parquet`, fallaba para TFs daily+ que usan `YYYY.parquet` | `_identify_missing_periods()` consulta `is_intraday(tf)` y busca `YYYY.parquet` para daily+ |
| Símbolo CCXT | Pasaba `"BTCUSDT"` directamente a CCXT que espera `"BTC/USDT"` | Nueva función `_to_ccxt_symbol()` convierte automáticamente |
| Metadata source | Siempre escribía `source="binance_vision"` incluso cuando usaba CCXT | Ahora trackea `"binance_vision"` vs `"ccxt_binance"` según la fuente real |

### 9.2. Unificación de `mtf.py`

- `resample_ohlcv()` **ya no hace su propia** `.resample().agg()` — delega a `OHLCVResampler.resample()` 
- Beneficio: hereda alineación `origin="epoch"` para 45m, `1W-MON` para weekly, y drop de trailing bar incompleto
- 13 tests de paridad confirman output idéntico entre `mtf.py` y `OHLCVResampler` directo

### 9.3. Cross-validación real

- `TestCrossValidation` reemplazado: ya no es auto-comparación (resample vs resample)
- Nuevos tests comparan resampled vs aggregación manual independiente (sin usar OHLCVResampler)
- Script `scripts/cross_validate_native.py` preparado para validar contra datos nativos del exchange

### 9.4. Datasets materializados

- Script `scripts/download_data.py` para descarga automatizada
- Descarga lanzada para BTCUSDT (2017-08→), ETHUSDT (2017-08→), SOLUSDT (2020-08→) 
- Almacenamiento: `data/raw/binance/{symbol}/1m/`

### 9.5. Documentación generada

- `docs/data_quality_report.md` — Reporte de calidad con metodología y checks
- `docs/cross_validation_report.md` — Se genera automáticamente post-descarga
- Este reporte actualizado con sección de closing backlog

### Métricas actualizadas

| Métrica | Antes | Después |
|---------|-------|---------|
| Tests totales | 224 | 256 |
| Integridad del raw store | No auditada | 41,796 particiones corruptas cuarentenadas y regeneradas |
| Validación nativa exchange | Pendiente | PASS en BTCUSDT, ETHUSDT y SOLUSDT (1m→1h, 1m→1d) |
| Entorno/editor | Inconsistente | `.vscode/settings.json` alineado con `.venv` del proyecto |

---

## 10. Próximos Pasos (Sprint 2)

Con la infraestructura de datos completa, el Sprint 2 procederá con:

1. **Completar el catálogo Python de indicadores** — wrappers estándar + custom faltantes para llegar a 15/15
2. **Cerrar la paridad Pine/Python** — validación por indicador y por combinaciones representativas
3. **Consolidar el engine de señales** — registry, surface pública y contratos MTF consistentes
4. **Dejar listos los artefactos de integración** — documentación técnica y harness para Sprint 3/4
