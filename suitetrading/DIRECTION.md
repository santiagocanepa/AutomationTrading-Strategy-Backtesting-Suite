# DIRECTION — Exhaustive Random Search (v9)

**Última actualización:** 2026-04-14
**Estado:** v9 listo para ejecutar. Runner sin Optuna, output Parquet.

---

## ⚠️ REGLAS ABSOLUTAS — LEER ANTES DE HACER CUALQUIER COSA

1. **NUNCA cambiar la metodología** de búsqueda sin confirmación explícita del usuario
2. **NUNCA usar NSGA-II, TPE, ni Optuna** en la fase de exploración
3. **NUNCA usar `run_discovery.py`** para exploración exhaustiva — usar `run_random_v9.py`
4. **NUNCA reintroducir SQLite** como storage — usar Parquet
5. Un agente anterior ignoró estas reglas y perdió semanas de trabajo

---

## §1 — Enfoque actual: Random exhaustivo → Parquet → análisis post-hoc

### Filosofía

En un espacio de ~10^16 combinaciones:
- Un optimizer (NSGA-II/TPE) explora 20K trials = 0.000000002% → sesgado por óptimos locales
- Los params de indicadores y riesgo son interdependientes → optimizer los trata semi-independientemente
- **Random sampling genera un dataset no sesgado.** Los datos hablan, no el optimizer.
- **La gestión de posición es más importante que las señales de entrada.** El risk space debe ser amplio.

### Evolución técnica (2026-04-14)

Se eliminó Optuna del loop de ejecución:
- **Antes:** `run_discovery.py` → Optuna → `trial.suggest_*()` → SQLite → 4.3 GB/study, 5.8 bt/sec
- **Ahora:** `run_random_v9.py` → random params → `run_single()` → Parquet → 110 MB/study, 7.3 bt/sec

| Métrica | Optuna + SQLite | Random + Parquet |
|---------|:--------------:|:----------------:|
| Velocidad | 5.8 bt/sec | **7.3 bt/sec** (+26%) |
| Disco 300K trials | 4.3 GB | **~110 MB** (39x menor) |
| Disco 20 studies | 86 GB | **~2.2 GB** |
| Resume | Minutos (cargar DB) | Instantáneo |
| I/O contention | SQLite locks | Ninguna |

### Pipeline v9

```
Fase 1: EXPLORACIÓN (run_random_v9.py)
──────────────────────────────────────
  300K random trials × 20 studies (10 assets × 2 directions)
  = 6M backtests totales
  step_factor=4 (indicadores), step_factor=1 (risk)
  Output: artifacts/exhaustive_v9/parquet/*.parquet
  Tiempo estimado: ~57h en M4 Pro (4 procesos paralelos)

Fase 2: ANÁLISIS POST-HOC
─────────────────────────
  Cargar Parquet con pandas
  Filtrar: Sharpe > 0 AND trades ≥ 300
  Análisis condicional por combinación estructural
  (estados × TFs × risk params)
  Identificar top ~1000 configuraciones consistentes

Fase 3: VALIDACIÓN SELECTIVA (WFO + PBO)
────────────────────────────────────────
  Usar run_discovery.py (CON Optuna) SOLO para validar
  las top ~1000 configuraciones de Fase 2
  Gates: PBO < 0.20, DSR > 0.95, trades ≥ 300

Fase 4: EXTENSIÓN A 15min
─────────────────────────
  Repetir pipeline con TF base 15min
  grafico=15min, 1_superior=1h, 2_superiores=4h
```

---

## §2 — Diseño v9

### Indicadores (sin cambios en el set)

11 entry indicators en `rich_stock` archetype:
```
ssl_channel, squeeze, firestorm, wavetrend_reversal,
ma_crossover, macd, bollinger_bands, adx_filter,
rsi, obv, ash
```
- Auxiliary: `firestorm_tm` (bandas para stop dinámico)
- Exit: `ssl_channel`, `wavetrend_reversal` (invertidos)
- Trailing: `ssl_channel_low`
- 72 parámetros totales por trial (46 de indicadores + 22 state/TF + 3 risk + 1 num_opt_req)

### Estados de indicadores

- **MAX_EXCLUYENTE = 2** (reducido de 3)
- **Smart num_optional_required:** rango dinámico según count de EXCL y OPC

```python
def _smart_optional_range(excl_count, opc_count):
    if opc_count == 0:    return (0, 0)
    if excl_count >= 2:   return (1, min(2, opc_count))   # total 3-4
    if excl_count == 1:   return (1, min(3, opc_count))   # total 2-4
    if excl_count == 0:   return (min(2, opc), min(4, opc))  # total 2-4
```

### Risk management

**Principio:** La gestión de posición >> señales de entrada.

| Param | Rango | Step | Valores |
|-------|-------|------|---------|
| stop__atr_multiple | 0.5–4.0 | 0.5 | 8 |
| partial_tp__r_multiple | 0.25–2.5 | 0.25 | 10 |
| partial_tp__close_pct | 10–60 | 10 | 6 |

- **Pyramiding: DESACTIVADO** (hardcoded max_adds=0, enabled=False)
- **Break-even: activado automáticamente post-TP1**
- **Trailing: ssl_channel_low** (TF es parámetro del indicador)
- **Risk combos: 480** (exhaustivamente cubribles)
- **step_factor NO se aplica a risk params** (ya tienen la granularidad diseñada)

### Temporalidades

- **Fase 1-3:** TF base = 1h (probado, genera ≥300 trades)
- **Fase 4:** TF base = 15min (más trades, indicadores en 1h/4h)

---

## §3 — Archivos clave

| Archivo | Propósito |
|---------|-----------|
| `scripts/run_random_v9.py` | Runner v9: random params → run_single() → Parquet |
| `scripts/run_exhaustive_v9.sh` | Orquestador: batches de 4, resume, progress check |
| `scripts/run_discovery.py` | Runner Optuna (SOLO para Fase 3 validación WFO) |
| `src/suitetrading/optimization/_internal/objective.py` | BacktestObjective, EXHAUSTIVE_RISK_SPACE, _smart_optional_range |
| `src/suitetrading/risk/state_machine.py` | FSM bar-by-bar (NO TOCAR) |
| `src/suitetrading/indicators/signal_combiner.py` | EXCL/OPC/DESACT logic (NO TOCAR) |
| `src/suitetrading/config/archetypes.py` | rich_stock archetype (NO TOCAR) |

---

## §4 — Historial de runs

| Run | Enfoque | Trials | Resultado | Estado |
|-----|---------|--------|-----------|--------|
| v1 | TPE single-obj | 80K | 0 finalists | ❌ Penalty -10 destruye surface |
| v2 | TPE + MAX_EXCL=3 | 80K | 27 finalists | Referencia |
| v3 | NSGA-II, 9 ind | 400K | 139 finalists | Referencia |
| v4 | NSGA-II, 11 ind, step=4 | 200K | **31 finalists, PBO 0.014-0.271** | ✓ Mejor con optimizer |
| v5 | NSGA-II, 7 ind, step=1 | 400K | 11 finalists | ❌ Overfit |
| v6 | Random, sin WFO | 552K | Análisis parcial | ⏸ Interrumpido |
| v7 | NSGA-II (desvío) | 300K | 63 finalists | ⚠️ Desvío |
| v8 | NSGA-II (desvío) | 400K | 87 finalists | ⚠️ Desvío |
| **v9** | **Random, sin Optuna, Parquet** | **6M target** | **Pendiente** | 🎯 **ACTUAL** |

---

## §5 — Lecciones críticas

1. Random exhaustive > optimizer para exploración en espacios ~10^16
2. NUNCA cambiar metodología sin confirmación del usuario
3. Risk management >> entry signals
4. step_factor=4 para indicadores (regularización), =1 para risk (granularidad diseñada)
5. Parquet + zstd >> SQLite para almacenamiento de trials (39x menor, 26% más rápido)
6. Los 11 indicadores contribuyen — nunca reducir el set
7. Cada mercado tiene su combinación óptima
8. Max 4 procesos simultáneos en M4 Pro 48GB
9. Flush cada 5000 trials para checkpoint/resume
10. No usar Optuna en el loop exhaustivo — overhead innecesario

---

## §6 — Lo que NO se toca

| Componente | Archivo | Motivo |
|-----------|---------|--------|
| FSM | `risk/state_machine.py` | Funciona, bien testeado |
| Signal combiner | `indicators/signal_combiner.py` | EXCL/OPC/DESACT correcto |
| Pipeline validación | `optimization/anti_overfit.py` | WFO + CSCV + DSR (para Fase 3) |
| Data infrastructure | `data/` | Estable |
| Indicators | `indicators/custom/` | Todos los 11 implementados |
| Archetype config | `config/archetypes.py` | rich_stock con 11 indicadores |

---

## §7 — Gates de validación (Fase 3 solamente)

| Métrica | Threshold | Motivo |
|---------|-----------|--------|
| DSR | > 0.95 | Ajusta por múltiple testing |
| Sharpe anualizado | > 0.80 | Viabilidad económica |
| PBO | < 0.20 | Probabilidad de overfitting |
| MIN_TRADES | ≥ 300 | Significancia estadística |
| Max drawdown p95 | < 25% | Riesgo acotado |
