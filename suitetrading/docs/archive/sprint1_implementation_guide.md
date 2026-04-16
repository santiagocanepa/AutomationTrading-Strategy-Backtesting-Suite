# Sprint 1 — Data Infrastructure: Implementation Guide

> **Propósito**: Guía paso a paso para implementar Sprint 1. Define el **orden
> exacto** de desarrollo, dependencias entre módulos, estrategia de testing,
> patrones de código a seguir, benchmarks objetivo, y checklists por entregable.
>
> **Prerequisitos**: Leer `sprint1_master_plan.md` (el qué/por qué) y
> `sprint1_technical_spec.md` (el cómo exacto) antes de empezar.

---

## 1. Dependency Graph Between Modules

```
                    ┌─────────────────┐
                    │  config/        │
                    │  settings.py    │  (1) Configuración ampliada
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  data/          │
                    │  timeframes.py  │  (2) Mapeo unificado de TFs
                    └──┬──────────┬───┘
                       │          │
          ┌────────────▼──┐  ┌───▼──────────────┐
          │  data/        │  │  data/            │
          │  validator.py │  │  storage.py       │  (3a, 3b) Paralelos
          └────────────┬──┘  └───┬──────────────┘
                       │         │
                    ┌──▼─────────▼──┐
                    │  data/        │
                    │  downloader.py│  (4) Depende de storage + validator
                    └───────┬──────┘
                            │
                    ┌───────▼──────┐
                    │  data/       │
                    │  resampler.py│  (5) Depende de storage (lee 1m)
                    └───────┬──────┘
                            │
                    ┌───────▼──────┐
                    │  data/       │
                    │  warmup.py   │  (6) Depende de resampler + indicators
                    └───────┬──────┘
                            │
               ┌────────────▼───────────┐
               │  tests/data/           │
               │  test_integration.py   │  (7) End-to-end
               └────────────────────────┘
```

### Dependencias explícitas

| Módulo | Depende de | Consumido por |
|--------|-----------|---------------|
| `settings.py` | — | Todos |
| `timeframes.py` | — | storage, resampler, validator, downloader |
| `validator.py` | timeframes | downloader, integration tests |
| `storage.py` | timeframes | downloader, resampler, integration tests |
| `downloader.py` | storage, validator | orchestrator, integration tests |
| `resampler.py` | storage, timeframes | warmup, integration tests |
| `warmup.py` | resampler, indicators/base | backtesting (Sprint 4) |

---

## 2. Implementation Order: Step by Step

### Phase 1: Foundation (Día 1-2)

#### Step 1.1 — Ampliar `config/settings.py`

**Archivo**: `src/suitetrading/config/settings.py`
**Esfuerzo**: ~30 min

Agregar los campos definidos en `sprint1_master_plan.md §5`:
- `raw_data_dir`, `processed_data_dir`
- `default_exchange`, `binance_vision_base_url`
- `download_rate_limit_weight`, `download_retry_max`, `download_retry_backoff`
- `parquet_compression`, `parquet_compression_level`
- `default_symbols`, `base_timeframe`, `target_timeframes`

**Criterio**: `Settings()` instancia sin errores con valores por defecto.

#### Step 1.2 — Crear `data/timeframes.py`

**Archivo nuevo**: `src/suitetrading/data/timeframes.py`
**Esfuerzo**: ~1h

Este módulo centraliza TODA la lógica de conversión de timeframes. Actualmente
hay duplicación entre `indicators/mtf.py` (Pine Script keys) y la tech spec
(internal keys). Este módulo es la **fuente de verdad única**.

Contenido:
- `TIMEFRAME_MAP`: dict con todas las representaciones (ver tech spec §9.1)
- `normalize_timeframe(tf: str) -> str`: cualquier formato → internal key
- `tf_to_pandas_offset(tf: str) -> str`: internal key → pandas offset
- `tf_to_seconds(tf: str) -> int`: internal key → segundos
- `tf_to_binance(tf: str) -> str | None`: internal key → Binance API string
- `is_intraday(tf: str) -> bool`: True para 1m-4h, False para D/W/M
- `partition_scheme(tf: str) -> str`: "monthly" o "yearly"

**Criterio**: Refactorizar `indicators/mtf.py` para que importe de aquí.

#### Step 1.3 — Tests de foundation

**Archivo**: `tests/data/test_timeframes.py`

- Test cada función de conversión con todos los 11 TFs
- Test edge cases: "60" → "1h", "D" → "1d", "M" → "1M", "45m" → "45m"
- Test que `tf_to_binance("45m")` devuelva `None`
- Test `partition_scheme`: intraday → monthly, daily+ → yearly

---

### Phase 2: Storage + Validation (Día 2-4)

#### Step 2.1 — Implementar `data/validator.py`

**Archivo**: `src/suitetrading/data/validator.py` (nuevo)
**Esfuerzo**: ~3h

Implementar `ValidationIssue` dataclass y `DataValidator` class según tech spec §5.

Orden interno de implementación:
1. `ValidationIssue` dataclass
2. `_validate_schema(df)` → checks columnas y dtypes
3. `_validate_timestamps(df)` → sorted, no dupes, UTC
4. `_validate_ohlcv_logic(df)` → high >= max(open,close), etc.
5. `detect_gaps(df, expected_tf)` → DataFrame de gaps
6. `fill_gaps(df, expected_tf, method)` → ffill o mark
7. `validate(df, expected_tf)` → orquesta todos los checks
8. `generate_report(...)` → dict resumen

**Patrón**: Cada check privado retorna `list[ValidationIssue]`. `validate()`
los concatena y ordena por severity.

#### Step 2.2 — Implementar `data/storage.py`

**Archivo**: `src/suitetrading/data/storage.py` (reemplazar stub)
**Esfuerzo**: ~4h

Implementar `ParquetStore` según tech spec §2.

Orden interno:
1. `__init__` con `base_dir`, `compression`, `compression_level`
2. `_partition_path()` y `_detect_partition_scheme()`
3. `_write_partition()` — helper interno que escribe un solo archivo Parquet
4. `write()` — split por mes/año, dedup, sort, escribe particiones
5. `read()` — identifica particiones en rango, lee y concatena
6. `list_available()` — scanea directorio
7. `info()` — metadata + gap detection vía `DataValidator.detect_gaps()`

**Dependencias en código**:
```python
from suitetrading.data.timeframes import tf_to_pandas_offset, partition_scheme
```

#### Step 2.3 — Tests Phase 2

**Archivos**:
- `tests/data/test_validator.py` (~15 tests)
- `tests/data/test_storage.py` (~12 tests)

##### test_validator.py

| Test | Verifica |
|------|----------|
| `test_valid_ohlcv_passes` | DataFrame correcto no genera issues |
| `test_missing_column_fails` | Falta "volume" → error |
| `test_wrong_dtype_fails` | close como string → error |
| `test_unsorted_timestamps` | Index desordenado → error |
| `test_duplicate_timestamps` | Dupes → error |
| `test_no_timezone_fails` | Index naive (sin UTC) → error |
| `test_high_less_than_low` | high < low → error |
| `test_negative_volume` | volume < 0 → error |
| `test_detect_gaps_finds_missing` | Gap de 5 bars detectado |
| `test_detect_gaps_no_false_positive` | Data continua → 0 gaps |
| `test_fill_gaps_ffill` | Gaps rellenados con ffill, volume=0 |
| `test_fill_gaps_mark` | Gaps rellenados con NaN |
| `test_outlier_warning` | Cambio >50% genera warning |
| `test_zero_volume_warning` | >1% volume=0 genera warning |
| `test_generate_report_structure` | Report contiene keys esperados |

##### test_storage.py

| Test | Verifica |
|------|----------|
| `test_write_read_roundtrip` | Write + read devuelve mismo data |
| `test_write_creates_partitions` | 3 meses → 3 archivos .parquet |
| `test_write_deduplicates` | Datos con dupes → sin dupes al leer |
| `test_write_sorts_timestamps` | Datos desordenados → ordenados |
| `test_read_date_range` | start/end filtra correctamente |
| `test_read_column_projection` | columns=["close"] solo lee close |
| `test_read_nonexistent_raises` | FileNotFoundError si no hay data |
| `test_list_available` | Detecta todos los datasets escritos |
| `test_info_metadata` | date_min, date_max, rows correctos |
| `test_yearly_partitions` | 1d data → archivos anuales |
| `test_overwrite_partition` | Re-write sobreescribe sin duplicar |
| `test_compression_zstd` | Archivo escrito usa ZSTD |

**Patrón de fixtures**:
```python
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

@pytest.fixture
def sample_1m_ohlcv() -> pd.DataFrame:
    """Generate 1 day of 1m OHLCV synthetic data."""
    idx = pd.date_range("2024-01-15", periods=1440, freq="1min", tz="UTC")
    rng = np.random.default_rng(42)
    close = 42000 + rng.standard_normal(1440).cumsum() * 10
    return pd.DataFrame({
        "open": close + rng.uniform(-5, 5, 1440),
        "high": close + abs(rng.standard_normal(1440)) * 20,
        "low": close - abs(rng.standard_normal(1440)) * 20,
        "close": close,
        "volume": abs(rng.standard_normal(1440)) * 100,
    }, index=idx)

@pytest.fixture
def tmp_store(tmp_path: Path) -> ParquetStore:
    return ParquetStore(base_dir=tmp_path / "data")
```

---

### Phase 3: Download Pipeline (Día 4-7)

#### Step 3.1 — Instalar dependencias de datos

```bash
pip install "suitetrading[data]"  # ccxt>=4.2, httpx>=0.27
pip install tqdm                   # Progress bars
pip install aiofiles               # Async file I/O (opcional)
```

Agregar `tqdm>=4.66` a `[project.optional-dependencies] data`.

#### Step 3.2 — Implementar `BinanceVisionDownloader`

**Dentro de**: `src/suitetrading/data/downloader.py`
**Esfuerzo**: ~4h

Orden interno:
1. `__init__(cache_dir, base_url)`
2. `_build_url(symbol, interval, year, month)` — URL pattern
3. `_download_zip(url, dest)` — httpx async GET → save to disk
4. `_parse_csv(csv_path)` — parse Binance Vision format (tech spec §7.2)
5. `download_month(symbol, interval, year, month)` → DataFrame | None
6. `download_range(symbol, interval, start, end)` → DataFrame concatenado

**Decisiones clave**:
- Usar `httpx.AsyncClient` (no requests — async para concurrencia futura)
- Cache de ZIPs: si `cache_dir/BTCUSDT-1m-2024-01.zip` existe, skip download
- HTTP 404 → return None (par no existía), no raise
- Temporalidades nativas de Binance: usar `tf_to_binance()` para mapear

#### Step 3.3 — Implementar `CCXTDownloader`

**Dentro de**: `src/suitetrading/data/downloader.py`
**Esfuerzo**: ~3h

Orden interno:
1. `__init__(exchange_id, rate_limit_weight, max_retries, backoff_base)`
2. `_create_exchange()` — factory para ccxt async instance
3. `_fetch_with_retry(symbol, timeframe, since, limit)` — single fetch + retry
4. `download_range(symbol, timeframe, start, end)` → DataFrame
5. `fetch_latest(symbol, timeframe, bars)` → DataFrame

**Decisiones clave**:
- Rate limiting: track peso acumulado por minuto, sleep si excede
- Paginación: `since = last_timestamp + 1ms` para evitar dupes
- Normalización: tech spec §8.2, aplicar `normalize_ccxt_ohlcv()`
- Context manager: `async with` para cerrar exchange al terminar

#### Step 3.4 — Implementar `DownloadOrchestrator`

**Dentro de**: `src/suitetrading/data/downloader.py`
**Esfuerzo**: ~3h

Orden interno:
1. `__init__(store, cache_dir, settings)` — inyecta dependencias
2. `_identify_missing_months(exchange, symbol, tf, start, end)` — compara
   store vs rango pedido
3. `sync(symbol, start, end, exchange, timeframe, force)`:
   - Identifica meses faltantes
   - Descarga vía BinanceVision (historical) o CCXT (current month)
   - Valida cada chunk con `DataValidator`
   - Almacena con `ParquetStore.write()`
   - Retorna report dict
4. `sync_all(symbols, start, end)` — itera sobre símbolos

**Decisiones clave**:
- Mes actual (`date.today().month`): siempre usar CCXT (Vision tarda ~1 día)
- `force=True`: re-descarga todo, ignora cache
- Validación post-descarga: ejecutar `DataValidator.validate()` antes de
  `store.write()`. Si hay errores severity="error", no almacenar.

#### Step 3.5 — Tests Phase 3

**Archivo**: `tests/data/test_downloader.py` (~15 tests)

**Estrategia de mocking**: Los downloaders hacen I/O externo. En tests unitarios:
- `BinanceVisionDownloader`: mockear `httpx.AsyncClient` responses
- `CCXTDownloader`: mockear `ccxt.exchange.fetch_ohlcv()`
- `DownloadOrchestrator`: mockear ambos downloaders + store

| Test | Verifica |
|------|----------|
| `test_build_url_format` | URL correctamente formateada |
| `test_parse_binance_csv` | CSV de ejemplo → DataFrame correcto |
| `test_download_month_cached` | No re-descarga si ZIP existe |
| `test_download_month_404_returns_none` | HTTP 404 → None |
| `test_download_range_concatenates` | 3 meses → DataFrame continuo |
| `test_ccxt_pagination` | 3 páginas → DataFrame concatenado sin dupes |
| `test_ccxt_retry_on_429` | Rate limit → retry con backoff |
| `test_ccxt_max_retries_exceeded` | 4 failures → raise |
| `test_normalize_ccxt_ohlcv` | Raw list → DataFrame con schema correcto |
| `test_orchestrator_identifies_missing` | 5 meses en store, 2 faltantes |
| `test_orchestrator_sync_incremental` | Solo descarga meses faltantes |
| `test_orchestrator_validates_before_store` | Data inválida no se almacena |
| `test_orchestrator_sync_all` | 3 símbolos sync'd |
| `test_orchestrator_current_month_uses_ccxt` | Mes actual → CCXT |
| `test_orchestrator_force_redownloads` | force=True re-descarga todo |

**Fixture con datos reales (opcional, marcado slow)**:
```python
@pytest.mark.slow
async def test_binance_vision_real_download():
    """Download 1 month of real BTCUSDT 1m data from Binance Vision."""
    dl = BinanceVisionDownloader(cache_dir=tmp_path / "cache")
    df = await dl.download_month("BTCUSDT", "1m", 2024, 1)
    assert df is not None
    assert len(df) > 40_000  # January = 44,640 minutes
    assert set(df.columns) == {"open", "high", "low", "close", "volume"}
```

---

### Phase 4: Resampling + Warmup (Día 7-9)

#### Step 4.1 — Implementar `data/resampler.py`

**Archivo**: `src/suitetrading/data/resampler.py` (reemplazar stub)
**Esfuerzo**: ~3h

Implementar `OHLCVResampler` según tech spec §4.1.

Orden interno:
1. `TF_TO_OFFSET` class variable (copiar de tech spec §4.1)
2. `_agg_rules()` static method
3. `resample(df_base, target_tf)`:
   - Validar que target_tf > base TF
   - `df.resample(offset, origin="epoch").agg(agg_rules)`
   - Drop barras incompletas (trailing bar con menos filas de las esperadas)
   - Caso especial 45m: usar `origin="epoch"` para alineación correcta
4. `resample_all(df_1m, target_tfs)` — dict comprehension
5. `validate_against_native(resampled, native, tolerance_pct)` — comparación

**Refactoring de `mtf.py`**:
- `resample_ohlcv()` en `mtf.py` se convierte en wrapper que llama a
  `OHLCVResampler().resample()` con TF normalization
- `_TF_TO_OFFSET` se reemplaza por import de `timeframes.py`
- `align_to_base()` permanece en `mtf.py` (es lógica de señales, no datos)

#### Step 4.2 — Implementar `data/warmup.py`

**Archivo nuevo**: `src/suitetrading/data/warmup.py`
**Esfuerzo**: ~2h

Implementar `WarmupCalculator` según tech spec §4.2.

Contenido:
1. `INDICATOR_WARMUP` class variable (warmup bars por indicador conocido)
2. `_tf_to_timedelta(tf, bars)` — convierte N bars de un TF a timedelta
3. `calculate(indicators, base_tf)`:
   - Para cada indicador: lookup warmup bars, multiplicar por TF
   - Retornar `max(all_timedeltas)` — el peor caso domina
4. `calculate_from_config(config: dict) -> timedelta`:
   - Convenience method que parsea config de indicadores activos

**Integración con Sprint 2**: El `INDICATOR_WARMUP` dict se extenderá cuando
se implementen los indicadores. Por ahora, hardcodear los valores conocidos de
la tabla en master_plan §3.

#### Step 4.3 — Tests Phase 4

**Archivos**:
- `tests/data/test_resampler.py` (~12 tests)
- `tests/data/test_warmup.py` (~8 tests)

##### test_resampler.py

| Test | Verifica |
|------|----------|
| `test_resample_1m_to_5m` | 1440 bars 1m → 288 bars 5m |
| `test_resample_ohlcv_values` | open=first, high=max, low=min, close=last, vol=sum |
| `test_resample_1m_to_1h` | 1440 → 24 bars, valores correctos |
| `test_resample_1m_to_4h` | 1440 → 6 bars |
| `test_resample_1m_to_1d` | 1440 → 1 bar |
| `test_resample_45m_alignment` | Barras en 00:00, 00:45, 01:30, ... |
| `test_resample_1w_monday_start` | Semana empieza en lunes 00:00 UTC |
| `test_resample_drops_incomplete` | Trailing incompleta eliminada |
| `test_resample_target_lte_base_raises` | "1m" → "1m" = ValueError |
| `test_resample_all_returns_dict` | 10 keys, cada una con DataFrame |
| `test_validate_against_native_passes` | Datos idénticos → passed=True |
| `test_validate_against_native_detects_diff` | Diff >0.01% → passed=False |

##### test_warmup.py

| Test | Verifica |
|------|----------|
| `test_single_indicator_1h` | EMA(200) en 1H = ~10.4 días |
| `test_single_indicator_weekly` | Squeeze(20) en W = ~350 días |
| `test_multiple_indicators_returns_max` | Max de todos los warmups |
| `test_unknown_indicator_fallback` | Indicador desconocido → default conservador |
| `test_tf_to_timedelta_1m` | 100 bars × 1m = 100 minutos |
| `test_tf_to_timedelta_1d` | 60 bars × 1D = 60 días |
| `test_tf_to_timedelta_1w` | 50 bars × 1W = 350 días |
| `test_calculate_from_config` | Config dict → timedelta correcto |

---

### Phase 5: Integration + Benchmarks (Día 9-11)

#### Step 5.1 — Test de integración end-to-end

**Archivo**: `tests/data/test_integration.py`
**Esfuerzo**: ~3h

```python
@pytest.mark.slow
@pytest.mark.integration
class TestDataPipelineE2E:
    """End-to-end: download → validate → store → resample → warmup."""

    async def test_full_pipeline_btcusdt_one_month(self, tmp_path):
        """Download 1 month, validate, store, resample to all TFs."""
        # 1. Download
        dl = BinanceVisionDownloader(cache_dir=tmp_path / "cache")
        df_1m = await dl.download_month("BTCUSDT", "1m", 2024, 1)

        # 2. Validate
        validator = DataValidator()
        issues = validator.validate(df_1m, "1m")
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

        # 3. Store
        store = ParquetStore(base_dir=tmp_path / "data")
        paths = store.write(df_1m, "binance", "BTCUSDT", "1m", source="binance_vision")
        assert len(paths) == 1  # 1 month = 1 partition

        # 4. Read back
        df_read = store.read("binance", "BTCUSDT", "1m")
        pd.testing.assert_frame_equal(df_1m, df_read)

        # 5. Resample
        resampler = OHLCVResampler()
        all_tfs = resampler.resample_all(df_read)
        assert "1h" in all_tfs
        assert len(all_tfs["1h"]) == 24 * 31  # ~744 hours in January

        # 6. Warmup
        calc = WarmupCalculator()
        warmup = calc.calculate(
            [{"name": "ema", "params": {"period": 200}, "timeframe": "1h"}],
            base_tf="1m",
        )
        assert warmup.days >= 8  # 250 bars × 1h ≈ 10.4 days

    async def test_cross_validation_1h(self, tmp_path):
        """Resample 1m→1h and validate against native 1h from Binance."""
        # Download both
        dl = BinanceVisionDownloader(cache_dir=tmp_path / "cache")
        df_1m = await dl.download_month("BTCUSDT", "1m", 2024, 1)
        df_1h_native = await dl.download_month("BTCUSDT", "1h", 2024, 1)

        # Resample
        resampler = OHLCVResampler()
        df_1h_resampled = resampler.resample(df_1m, "1h")

        # Validate
        report = resampler.validate_against_native(
            df_1h_resampled, df_1h_native, tolerance_pct=0.01
        )
        assert report["passed"]
```

#### Step 5.2 — Benchmarks

**Archivo**: `tests/data/test_benchmarks.py`
**Esfuerzo**: ~2h

Usar `pytest-benchmark` (agregar a dev dependencies).

| Benchmark | Target | Medición |
|-----------|--------|----------|
| `bench_read_1y_1m` | < 2.0s | Lectura de 525k rows desde Parquet |
| `bench_write_1y_1m` | < 3.0s | Escritura con ZSTD compression |
| `bench_resample_1y_all_tfs` | < 5.0s | 1m → 10 TFs para 1 año |
| `bench_validate_1y_1m` | < 2.0s | Validación completa de 1 año |
| `bench_parquet_size_1y_1m` | < 12 MB | Tamaño en disco con ZSTD |

```python
import pytest

@pytest.mark.benchmark
def test_bench_read_1y_1m(benchmark, populated_store):
    """Benchmark: read 1 year of 1m data from Parquet."""
    result = benchmark(
        populated_store.read,
        "binance", "BTCUSDT", "1m",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 12, 31, tzinfo=UTC),
    )
    assert len(result) > 500_000

@pytest.mark.benchmark
def test_bench_resample_all_tfs(benchmark, sample_1y_1m):
    """Benchmark: resample 1 year 1m → all TFs."""
    resampler = OHLCVResampler()
    result = benchmark(resampler.resample_all, sample_1y_1m)
    assert len(result) == 10
```

#### Step 5.3 — Descarga completa de datos

Una vez validado el pipeline con 1 mes, ejecutar la descarga completa:

```bash
# CLI provisional (o script en scripts/download_data.py)
python -m suitetrading.data.downloader sync \
    --symbols BTCUSDT ETHUSDT SOLUSDT \
    --start 2017-08-01 \
    --end today \
    --exchange binance

# Verificar
python -m suitetrading.data.storage info --all
```

Generar el reporte de calidad final:
```bash
python -m suitetrading.data.validator report \
    --exchange binance \
    --symbols BTCUSDT ETHUSDT SOLUSDT \
    --output docs/data_quality_report.md
```

---

### Phase 6: Documentation + Cleanup (Día 11-12)

#### Step 6.1 — Generar reportes

- `docs/data_source_evaluation.md`: Benchmark Binance Vision vs CCXT
  (velocidad, fiabilidad, cobertura)
- `docs/data_quality_report.md`: Gaps, issues, completeness por par
- `docs/sprint1_benchmarks.md`: Resultados de benchmarks de read/write/resample

#### Step 6.2 — Refactorizar `indicators/mtf.py`

- Reemplazar `_TF_TO_OFFSET` por import de `data/timeframes.py`
- `resample_ohlcv()` → wrapper de `OHLCVResampler().resample()`
- `resolve_timeframe()` y `align_to_base()` permanecen (son lógica de señales)
- Actualizar tests existentes si cambian imports

#### Step 6.3 — Verificación final

- [ ] `pytest` — todos los tests pasan
- [ ] `pytest --cov` — ≥80% coverage para `src/suitetrading/data/`
- [ ] `ruff check src/suitetrading/data/` — sin violations
- [ ] `mypy src/suitetrading/data/` — sin errors
- [ ] Los 3 pares descargados y validados
- [ ] Reportes de documentación generados

---

## 3. Testing Strategy

### 3.1 Test Pyramid

```
              ┌──────────┐
              │  E2E     │  2 tests (download real → validate → store → resample)
              │ (slow)   │  Marked: @pytest.mark.slow @pytest.mark.integration
              ├──────────┤
              │  Integ.  │  5 tests (storage + validator, orchestrator + store)
              │          │  Use real Parquet I/O, tmp_path fixtures
              ├──────────┤
              │  Unit    │  ~50 tests (pure logic, mocked I/O)
              │          │  Fast, isolated, deterministic
              └──────────┘
```

### 3.2 Pytest Markers

Agregar a `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: Tests that hit external APIs or do heavy I/O (deselect with -m 'not slow')",
    "integration: End-to-end pipeline tests",
    "benchmark: Performance benchmarks",
]
```

### 3.3 Comandos de ejecución

```bash
# Solo tests rápidos (CI default)
pytest -m "not slow and not benchmark"

# Todos los tests
pytest

# Solo benchmarks
pytest -m benchmark --benchmark-only

# Coverage report
pytest --cov=suitetrading.data --cov-report=html -m "not slow"
```

### 3.4 Fixtures compartidas

Crear `tests/data/conftest.py`:

```python
"""Shared fixtures for data module tests."""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from suitetrading.data.storage import ParquetStore


@pytest.fixture
def sample_1m_1day() -> pd.DataFrame:
    """1 day of synthetic 1m OHLCV data (1440 bars)."""
    idx = pd.date_range("2024-01-15", periods=1440, freq="1min", tz="UTC")
    rng = np.random.default_rng(42)
    price = 42000 + rng.standard_normal(1440).cumsum() * 10
    return pd.DataFrame({
        "open": price + rng.uniform(-5, 5, 1440),
        "high": price + abs(rng.standard_normal(1440)) * 20,
        "low": price - abs(rng.standard_normal(1440)) * 20,
        "close": price,
        "volume": abs(rng.standard_normal(1440)) * 100,
    }, index=idx)


@pytest.fixture
def sample_1m_1month() -> pd.DataFrame:
    """1 month of synthetic 1m OHLCV data (~44,640 bars)."""
    idx = pd.date_range("2024-01-01", "2024-01-31 23:59", freq="1min", tz="UTC")
    rng = np.random.default_rng(42)
    n = len(idx)
    price = 42000 + rng.standard_normal(n).cumsum() * 5
    return pd.DataFrame({
        "open": price + rng.uniform(-3, 3, n),
        "high": price + abs(rng.standard_normal(n)) * 15,
        "low": price - abs(rng.standard_normal(n)) * 15,
        "close": price,
        "volume": abs(rng.standard_normal(n)) * 50,
    }, index=idx)


@pytest.fixture
def tmp_store(tmp_path: Path) -> ParquetStore:
    """ParquetStore with a temporary directory."""
    return ParquetStore(base_dir=tmp_path / "processed")
```

---

## 4. Code Patterns & Conventions

### 4.1 Import Structure

```python
# Standard library
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

# Third-party
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Internal
from suitetrading.config.settings import Settings
from suitetrading.data.timeframes import normalize_timeframe, tf_to_pandas_offset
```

### 4.2 Logging

Usar `loguru` (ya en dependencias):

```python
from loguru import logger

# En funciones:
logger.info("Downloading {symbol} {tf} for {year}-{month:02d}", symbol=symbol, ...)
logger.warning("Gap detected: {gap_start} to {gap_end} ({bars} bars missing)")
logger.error("OHLCV validation failed: {issue}")
```

**No** usar `print()` para nada excepto CLI output temporal de desarrollo.

### 4.3 Async Pattern

Downloaders son async. Patrón consistente:

```python
import httpx

class BinanceVisionDownloader:
    def __init__(self, cache_dir: Path, base_url: str = "..."):
        self._cache_dir = cache_dir
        self._base_url = base_url

    async def download_month(self, symbol: str, interval: str, year: int, month: int) -> pd.DataFrame | None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            ...
```

Para tests:
```python
import pytest

@pytest.mark.asyncio
async def test_download_month():
    ...
```

Agregar `pytest-asyncio>=0.23` a dev dependencies.

### 4.4 Error Handling

```python
# Específico, nunca genérico
try:
    response = await client.get(url)
    response.raise_for_status()
except httpx.HTTPStatusError as exc:
    if exc.response.status_code == 404:
        logger.info("No data for {symbol} {year}-{month:02d}", ...)
        return None
    raise  # Re-raise otros HTTP errors
except httpx.TimeoutException:
    logger.warning("Timeout downloading {url}, retrying...")
    # retry logic
```

### 4.5 Path Convention

Siempre `pathlib.Path`, nunca `os.path`:

```python
from pathlib import Path

path = self._base_dir / exchange / symbol / timeframe / f"{year}-{month:02d}.parquet"
path.parent.mkdir(parents=True, exist_ok=True)
```

### 4.6 Type Hints

Type hints en todas las funciones públicas. Internal helpers pueden omitirlas
si son triviales:

```python
# Público: siempre typed
def read(self, exchange: str, symbol: str, timeframe: str,
         start: datetime | None = None, end: datetime | None = None) -> pd.DataFrame: ...

# Privado trivial: optional
def _build_url(self, symbol, interval, year, month):
    return f"{self._base_url}/data/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{year}-{month:02d}.zip"
```

---

## 5. File Inventory: What Gets Created

### Archivos nuevos

| File | Phase | Lines (est.) |
|------|-------|-------------|
| `src/suitetrading/data/timeframes.py` | 1 | ~80 |
| `src/suitetrading/data/validator.py` | 2 | ~200 |
| `src/suitetrading/data/warmup.py` | 4 | ~100 |
| `tests/data/__init__.py` | 1 | 0 |
| `tests/data/conftest.py` | 2 | ~50 |
| `tests/data/test_timeframes.py` | 1 | ~60 |
| `tests/data/test_validator.py` | 2 | ~120 |
| `tests/data/test_storage.py` | 2 | ~100 |
| `tests/data/test_downloader.py` | 3 | ~150 |
| `tests/data/test_resampler.py` | 4 | ~100 |
| `tests/data/test_warmup.py` | 4 | ~70 |
| `tests/data/test_integration.py` | 5 | ~80 |
| `tests/data/test_benchmarks.py` | 5 | ~60 |

### Archivos modificados

| File | Changes |
|------|---------|
| `src/suitetrading/data/storage.py` | Stub → full implementation (~250 lines) |
| `src/suitetrading/data/downloader.py` | Stub → full implementation (~350 lines) |
| `src/suitetrading/data/resampler.py` | Stub → full implementation (~150 lines) |
| `src/suitetrading/config/settings.py` | Add ~15 fields |
| `src/suitetrading/indicators/mtf.py` | Refactor to use timeframes.py |
| `pyproject.toml` | Add pytest-asyncio, pytest-benchmark, tqdm, markers |

### Documentación generada

| File | Content |
|------|---------|
| `docs/data_source_evaluation.md` | Benchmark Binance Vision vs CCXT |
| `docs/data_quality_report.md` | Gaps, completeness, issues por par |
| `docs/sprint1_benchmarks.md` | Read/write/resample performance |

---

## 6. Dependency Changes to `pyproject.toml`

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
    "pytest-asyncio>=0.23",      # NEW: async test support
    "pytest-benchmark>=4.0",     # NEW: benchmarks
    "ruff>=0.3",
    "mypy>=1.7",
]
data = [
    "ccxt>=4.2",
    "httpx>=0.27",
    "tqdm>=4.66",                # NEW: progress bars
]
```

---

## 7. Sprint Completion Checklist

### Código (todos deben pasar)

- [ ] `settings.py` ampliado con campos de Sprint 1
- [ ] `timeframes.py` implementado, `mtf.py` refactorizado
- [ ] `validator.py` implementado con 6 tipos de checks
- [ ] `storage.py` implementado con Parquet + ZSTD
- [ ] `downloader.py` con BinanceVision + CCXT + Orchestrator
- [ ] `resampler.py` implementado con resample + validate_against_native
- [ ] `warmup.py` implementado con cálculo por indicador/TF

### Tests

- [ ] ≥50 tests unitarios pasando
- [ ] ≥80% code coverage en `src/suitetrading/data/`
- [ ] Tests de integración pasando (marcados @slow)
- [ ] Benchmarks dentro de targets

### Datos

- [ ] BTCUSDT 1m descargado: 2017-08 → presente
- [ ] ETHUSDT 1m descargado: 2017-08 → presente
- [ ] SOLUSDT 1m descargado: 2020-08 → presente
- [ ] Cross-validation 1H y 1D pasando (< 0.01% diff)
- [ ] Todos los 10 TFs generados por resampling

### Calidad

- [ ] `ruff check` sin violations
- [ ] `mypy` sin errors
- [ ] No secrets en código (solo env vars en settings)
- [ ] Logging con loguru, cero `print()`

### Documentación

- [ ] `data_source_evaluation.md` escrito
- [ ] `data_quality_report.md` generado
- [ ] `sprint1_benchmarks.md` con resultados

---

## 8. Benchmark Targets Summary

| Metric | Target | Measured By |
|--------|--------|-------------|
| Read 1y 1m from Parquet | < 2.0s | `bench_read_1y_1m` |
| Write 1y 1m to Parquet | < 3.0s | `bench_write_1y_1m` |
| Resample 1y 1m → 10 TFs | < 5.0s | `bench_resample_all_tfs` |
| Validate 1y 1m | < 2.0s | `bench_validate_1y_1m` |
| Parquet size 1y 1m (ZSTD) | < 12 MB | `bench_parquet_size_1y_1m` |
| Download 1 month BV | < 15s | `bench_download_1month_bv` |
| Download 1 month CCXT | < 120s | `bench_download_1month_ccxt` |
| Cross-validation OHLC diff | < 0.01% | `test_cross_validation_1h` |
| Cross-validation Volume diff | Exact (0%) | `test_cross_validation_1h` |
| Total unit tests | ≥ 50 | `pytest --co -q | wc -l` |
| Code coverage data/ | ≥ 80% | `pytest --cov` |

---

## 9. Risk Checkpoints

Puntos donde PARAR y evaluar antes de continuar:

### Checkpoint 1: Post-Phase 2

> "¿El storage y validator funcionan correctamente con datos sintéticos?"

- Si los tests de storage fallan con datos edge-case (empty, huge, malformed):
  ajustar antes de seguir.
- Si ZSTD no funciona con la build de PyArrow: switch a Snappy.

### Checkpoint 2: Post-Phase 3 (Step 3.2)

> "¿Binance Vision devuelve datos en el formato esperado?"

- Si los CSV cambiaron de formato: ajustar parser.
- Si archivos antes de 2019 tienen formato diferente: agregar parser legacy.
- Si rate limits bloquean: ajustar concurrencia o usar mirror.

### Checkpoint 3: Post-Phase 4 (Step 4.1)

> "¿El resampling 1m→1H coincide con datos nativos de Binance 1H?"

- Si OHLC diff > 0.01%: investigar causa (timezone, alineación, barras incompletas).
- Si Volume no coincide exactamente: posible issue con barras parciales —
  documentar y decidir tolerancia.
- **Este es el checkpoint más crítico.** Si el resampling no valida, la
  señalización MTF del Sprint 2 estará rota.

### Checkpoint 4: Post-Phase 5

> "¿Los datos completos de 3 pares están limpios y los benchmarks cumplen?"

- Si hay gaps grandes (>1h) sin explicación: investigar con Binance status.
- Si benchmarks de lectura exceden 2s: investigar row group size, compression level.
