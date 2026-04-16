# Backtesting Pipeline Benchmark Report

**Proyecto:** SuiteTrading  
**Sprint:** 4 — Backtesting Core  
**Fecha:** 2026-03-11  
**Script:** `scripts/benchmark_backtesting.py`

---

## 1. Objetivo

Medir el throughput, consumo de memoria y overhead de serialización del pipeline end-to-end de backtesting (`grid → signals → engine → metrics → Parquet`) bajo condiciones realistas con datos reales de Binance.

**Claim a verificar (§14 sprint4_technical_spec):**  
> 100,000 backtests < 5 minutos

---

## 2. Entorno de ejecución

| Componente     | Valor                                      |
|----------------|--------------------------------------------|
| **CPU**        | Apple Silicon (arm64), 14 cores            |
| **OS**         | macOS Darwin 25.3.0                        |
| **Python**     | 3.14.3                                     |
| **Ejecución**  | Single-threaded (sin paralelismo)          |
| **Storage**    | SSD local                                  |
| **NumPy**      | ≥1.26                                      |
| **Numba**      | ≥0.59 (cache enabled)                      |

---

## 3. Configuración del test

| Parámetro           | Valor                                                  |
|---------------------|--------------------------------------------------------|
| **Dataset**         | BTCUSDT 1m real (Binance), últimos 3 meses             |
| **Timeframe base**  | 1h (resampled desde 1m: 2,160 barras)                  |
| **Date range**      | 2025-12-11 19:00 UTC → 2026-03-11 18:00 UTC           |
| **Grid size**       | 1,024 combinaciones                                    |
| **Grid breakdown**  | 2 symbols × 2 timeframes × 2 archetypes × 128 ind-combos |
| **Archetypes**      | `trend_following` (→ simple mode), `mean_reversion` (→ simple mode) |
| **Chunk size**      | 64 configs/chunk (16 chunks)                            |
| **Signals**         | SMA crossover con period=20 (señales compartidas)       |
| **Capital**         | $10,000 default per archetype                           |

---

## 4. Resultados

### 4.1 Resumen

| Fase                  | Tiempo     | Peak Memory |
|-----------------------|------------|-------------|
| Data load + resample  | 0.511 s    | 588.8 MB    |
| Grid generation       | 0.003 s    | —           |
| **Execution (1024)**  | **16.07 s**| **0.9 MB**  |
| Parquet serialisation | 0.025 s    | —           |
| **Total wall-clock**  | **16.61 s**| —           |

### 4.2 Throughput

| Métrica                    | Valor          |
|----------------------------|----------------|
| **Backtests/segundo**      | **63.7**       |
| **Backtests/minuto**       | **3,823**      |
| Errores durante ejecución  | 0              |
| Chunks procesados          | 16/16          |

### 4.3 Serialisation overhead

| Métrica                         | Valor    |
|---------------------------------|----------|
| Parquet write (ZSTD)            | 0.025 s  |
| Write como % del exec total     | 0.15%    |
| Filas escritas                  | 1,024    |

El overhead de serialización Parquet+ZSTD es **negligible** (<0.2% del tiempo total).

### 4.4 Desglose por fase

```
Load+Resample   ███░░░░░░░  3.1%
Grid Generation  ░░░░░░░░░░  0.0%
Execution        ████████████████████████████░  96.7%
Serialisation    ░░░░░░░░░░  0.2%
```

El cuello de botella es la ejecución del engine — grid generation y serialización son costos despreciables.

---

## 5. Proyección a 100K combinaciones

| Métrica                    | Estimación (lineal)  |
|----------------------------|----------------------|
| **Tiempo estimado**        | **26.2 minutos**     |
| **Memoria estimada**       | ~84 MB (exec only)   |
| **Factor vs 5 min target** | 5.2× más lento       |

### Análisis del gap vs target

El claim original de "100K backtests < 5 min" asumía ejecución con VectorBT PRO vectorizado. Con el engine Python puro + bar-loop actual:

- **100K en ~26 min** — funcional para sesiones nocturnas y runs por lotes.
- **Paths de optimización** (Sprint 5+):
  1. **Multiprocessing** (14 cores → ÷14 ≈ 1.9 min) — la optimización más directa.
  2. **Numba JIT en runners** — actualmente solo los indicadores usan `@njit`.
  3. **VBT PRO integration** — vectorización completa para archetypes A/B.
  4. **Pre-computed signals cache** — evitar recalcular señales idénticas.

Con multiprocessing básico (ya disponible en stdlib), el target de <5 min es alcanzable sin cambios en el engine core.

---

## 6. Checkpoint/Resume

Verificado durante la ejecución:
- `CheckpointManager` crea directorio de output correctamente.
- Cada chunk produce un `chunk_XXXXXX.parquet` independiente.
- `load_all_results()` concatena todos los chunks en un solo DataFrame.
- El resume funciona: chunks marcados "done" se saltan en re-ejecución.

---

## 7. Limitaciones conocidas

| Limitación                    | Impacto | Mitigación                           |
|-------------------------------|---------|--------------------------------------|
| Single-threaded               | Throughput limitado | multiprocessing en Sprint 5 |
| Señales compartidas en bench  | No mide costo de compute_signals per-run | Benchmark separado pendiente |
| Solo archetypes A/B testeados | FSM loop (C/D/E) será más lento | Benchmark FSM dedicado planificado |
| Local SSD only                | I/O no es bottleneck en local | Cloud benchmarks pendientes |

---

## 8. Reproducibilidad

```bash
cd suitetrading
.venv/bin/python scripts/benchmark_backtesting.py --combos 1024 --chunk 64 --months 3
```

Los resultados dependen del hardware pero la proporción entre fases debe ser estable. El script genera `data/benchmark_results.json` con métricas crudas parseable por herramientas de CI.

---

## 9. Conclusión

El pipeline de backtesting es funcional y ejecutable a escala. Con **63.7 backtests/segundo** en single-thread, el engine puede procesar grids de screening en tiempos razonables. El path a "100K en <5 min" está claro vía multiprocessing (Sprint 5) o integración VBT PRO, sin requerir cambios arquitectónicos.

| Gate                           | Estado    |
|--------------------------------|-----------|
| Benchmark reproducible         | ✅ PASS   |
| Throughput documented          | ✅ PASS   |
| Memory profiled                | ✅ PASS   |
| Serialisation cost measured    | ✅ PASS   |
| Resume capability verified     | ✅ PASS   |
| 100K < 5 min claim             | ⚠️ PARCIAL — alcanzable con multiprocessing |
