# Sprint 7 — Data Expansion + MIN_TRADES + Long/Short

**Date**: 2026-03-14
**Ref**: [phase2_discovery_plan.md](phase2_discovery_plan.md)
**Baseline**: Sprint 6 complete — 754 tests, pipeline Optuna → WFO → CSCV + DSR

## Goal

> Expandir datos a 7+ años, MIN_TRADES=300, long/short como tracks independientes. Sprint 8 ejecuta discovery a escala.

## Decisions Applied

| Decision | Value |
|----------|-------|
| Long/Short | Tracks independientes (NUNCA flip) |
| MIN_TRADES | 300 (cualquier TF/período) |
| Cross-asset | No. Asset-specific |
| Data | 7+ años, máximo disponible |

---

## Tasks

### T7.1: Validate Data Integrity (S)

**Qué**: Confirmar 7+ años Parquet completos para BTCUSDT/ETHUSDT/SOLUSDT.

**Archivo**: `scripts/validate_data.py` (NEW)

**Criterios**:
- Reportar: start_date, end_date, total_bars, completeness_pct por símbolo
- Detectar gaps (barras faltantes consecutivas)
- Output: tabla + `docs/data_gaps.md` si hay gaps
- Éxito: >99% completeness, 3.7M+ bars/símbolo

**Deps**: Ninguna

---

### T7.2: MIN_TRADES = 300 (S)

**Qué**: Subir threshold de 30 a 300.

**Archivo**: `src/suitetrading/optimization/_internal/objective.py` (línea 207)

**Cambio**:
```python
MIN_TRADES: int = 300  # was 30
```

**Tests**:
- `test_min_trades_threshold_300`: 299 trades → penalty, 300 → metric ok

**Deps**: Ninguna

---

### T7.3: Direction en BacktestObjective (M)

**Qué**: `BacktestObjective` acepta `direction="long"|"short"`.

**Archivo**: `src/suitetrading/optimization/_internal/objective.py`

**Cambios**:
- Constructor ya tiene `direction: str = "long"` — validar que acepta `"short"`
- `__call__()` ya pasa `self._direction` al engine — verificar
- `trial.set_user_attr("direction", self._direction)` para tracking

**Tests**:
- `test_objective_direction_short`: instance con direction="short" produce trades short
- `test_objective_direction_stored_in_trial`: direction en trial.user_attrs

**Deps**: Ninguna

---

### T7.4: run_discovery.py Multi-Direction (M)

**Qué**: Iterar sobre `--directions long short` como studies separados.

**Archivo**: `scripts/run_discovery.py`

**Cambios**:
- Arg: `--directions` (default `["long"]`, opción `["long", "short"]`)
- `study_name()`: `{symbol}_{tf}_{archetype}_{direction}`
- Loop en main(): nested sobre `args.directions`
- Pass `direction=dir` a `BacktestObjective`

**Criterios**:
- `--directions long short` crea 2 DBs por celda
- Backward compatible: `--directions long` = comportamiento actual
- No crosstalk entre studies

**Deps**: T7.3

---

### T7.5: Verificar FSM Short-Side (M)

**Qué**: Confirmar que `run_fsm_backtest()` maneja shorts correctamente.

**Archivos**:
- `src/suitetrading/risk/state_machine.py` (review, no cambios esperados)
- `src/suitetrading/backtesting/_internal/runners.py` (review)
- `tests/backtesting/test_fsm_short_direction.py` (NEW)

**Tests**:
- `test_fsm_short_full_lifecycle`: entry short → SL above entry → exit → PnL correcto
- `test_fsm_short_stop_loss_above_entry`: stop price > entry price para shorts
- `test_fsm_short_trailing`: trailing funciona en dirección correcta

**Deps**: Ninguna (paralelo)

---

### T7.6: WFO Direction Support (M)

**Qué**: `WalkForwardEngine.run()` acepta y propaga `direction`.

**Archivo**: `src/suitetrading/optimization/walk_forward.py`

**Cambios**:
- `run(..., direction: str = "long")` parameter
- Internal backtests usan direction proporcionado
- Signal building respeta direction

**Tests**:
- `test_wfo_direction_param`: direction="short" produce OOS curves distintas a "long"

**Deps**: T7.3, T7.4

---

### T7.7: Smoke Test End-to-End (M)

**Qué**: Primera ejecución con 7+ años, MIN_TRADES=300, long+short.

**Comando**:
```bash
python scripts/run_discovery.py \
  --symbols BTCUSDT \
  --timeframes 1h \
  --archetypes trend_following \
  --directions long short \
  --trials 50 \
  --top-n 25 \
  --months 84 \
  --wfo-splits 3
```

**Criterios**:
- Completa sin errores
- 2 studies: `BTCUSDT_1h_trend_following_long.db` y `..._short.db`
- Log documenta: runtime, IS/OOS Sharpe, trades count, finalists
- Si 0 finalists: documentar degradation ratios para Sprint 8

**Deps**: T7.1–T7.6

---

### T7.8: Tests & Docs (M)

**Qué**: Test suite verde, documentación actualizada.

**Criterios**:
- 0 regresiones en tests existentes
- 8+ tests nuevos para direction + MIN_TRADES
- `docs/sprint7_technical_changes.md` con cambios y rationale
- Coverage >85% en módulos modificados

**Deps**: Todos (paralelo a implementación)

---

## Dependency Graph

```
T7.1 (Data)  T7.2 (MIN_TRADES)  T7.5 (FSM Review)
     \            |                    |
      \           v                    | (parallel)
       \     T7.3 (Direction Objective)|
        \         |                    |
         \        v                    |
          \  T7.4 (run_discovery.py)   |
           \      |                    |
            \     v                    |
             → T7.6 (WFO Direction) ←─┘
                  |
                  v
              T7.7 (Smoke Test)
                  |
                  v
              T7.8 (Tests & Docs)
```

**Critical path**: T7.3 → T7.4 → T7.6 → T7.7

---

## Deliverables

```
MODIFIED:
  src/suitetrading/optimization/_internal/objective.py  (MIN_TRADES, direction)
  src/suitetrading/optimization/walk_forward.py         (direction param)
  scripts/run_discovery.py                              (--directions, study naming)

NEW:
  scripts/validate_data.py
  tests/backtesting/test_fsm_short_direction.py

ARTIFACTS (post smoke test):
  artifacts/discovery/sprint7_smoke/*.db
```

---

## Risks

| Risk | Mitigation |
|------|-----------|
| FSM short-side bugs | T7.5 lifecycle test + PnL validation |
| 0 finalists in smoke (MIN_TRADES=300 too strict) | Expected; documento degradation para Sprint 8 |
| WFO signal building duplicated (tech debt) | No bloquea; refactor en Sprint 9 |
| Data gaps in 2017-2019 | T7.1 valida; CCXT fallback si necesario |

---

## Open Questions (for Sprint 8+)

- ¿1000 trials/study suficiente o 2000?
- ¿Períodos solapados o disjuntos?
- ¿Incluir 15m timeframe o solo 1h/4h/1d?
