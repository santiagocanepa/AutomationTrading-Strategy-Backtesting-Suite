# Sprint 5 — Optimización y Anti-Overfitting: Implementation Guide

> **Propósito**: convertir el alcance y los contratos de Sprint 5 en un orden
> de ejecución concreto, con dependencias explícitas, paralelismo realista y
> criterios de salida verificables.

> **Nota de vigencia (2026-03-12)**: Sprint 5 ya fue implementada. Esta guía
> queda como trazabilidad de ejecución; no debe leerse como backlog pendiente.

---

## 1. Orden recomendado de trabajo

```text
Baseline + dependency verification
        │
        ▼
Contracts + ParallelExecutor
        │
        ▼
Optuna optimizer + objective function
        │
        ▼
Walk-Forward Optimization
        │
        ▼
Anti-overfit core (CSCV + DSR)
        │
        ▼
Extensions (DEAP, Hansen SPA, Feature Importance)
        │
        ▼
Reference validation + reporting + closure docs
```

Razón del orden:

- primero se verifica que las dependencias funcionen en Python 3.14,
- luego se fija multiprocessing porque todo lo demás lo necesita,
- después se implementa el optimizer como generador de candidatas,
- walk-forward produce las equity curves OOS necesarias para anti-overfit,
- CSCV y DSR operan sobre equity curves OOS — dependen de WFO,
- extensiones (DEAP, Hansen, feature importance) son opcionales,
- al final se hace validación de referencia sólo si aporta señal y se cierran docs.

---

## 2. Fase 0 — Baseline y gates

### Objetivo

Arrancar Sprint 5 con supuestos explícitos y deps verificadas.

### Tareas

1. Verificar que la suite siga verde (509+ tests passing).
2. Verificar instalabilidad de dependencias core:
   ```bash
   .venv/bin/pip install optuna scikit-learn
   ```
3. Verificar instalabilidad de dependencias condicionales:
   ```bash
   .venv/bin/pip install deap arch xgboost shap
   ```
4. Documentar qué deps son viables y cuáles no.
5. Decidir scope de T5.2 (DEAP), T5.6 (Hansen/arch), T5.7 (SHAP/XGBoost).
6. Actualizar `pyproject.toml` con deps confirmadas.
7. Verificar estructura creada en `src/suitetrading/optimization/`.
8. Verificar suite creada en `tests/optimization/`.

### Criterio de salida

- deps core instaladas y funcionales,
- deps condicionales evaluadas con decisión documentada,
- estructura de directorios lista,
- pyproject.toml actualizado.

---

## 3. Fase 1 — Contratos y ParallelExecutor

### Objetivo

Fijar los contratos del módulo y entregar multiprocessing como primer
deliverable, porque todo lo demás lo necesita.

### Tareas

1. Implementar `_internal/schemas.py` con todos los dataclasses:
   - `ObjectiveResult`
   - `OptimizationResult`
   - `WFOConfig`, `WFOResult`
   - `CSCVResult`, `DSRResult`, `SPAResult`
   - `AntiOverfitResult`
   - `StrategyReport`, `PipelineResult`
2. Implementar `parallel.py`:
   - `ParallelExecutor` con `ProcessPoolExecutor`.
   - Modo `sequential` para debugging.
   - Error handling por worker.
   - Integración con `RunConfig` y `BacktestEngine`.
3. Benchmark paralelo:
   - Ejecutar 1024 backtests single-thread vs multiprocessing.
   - Verificar throughput ≥10× (≥637 bt/sec con 14 cores).
   - Verificar resultados idénticos (determinismo).
4. Tests:
   - `test_schemas.py` — creación y validación de todos los dataclasses.
   - `test_parallel.py` — parallel vs sequential, error handling, max_workers.

### Reglas

- `ParallelExecutor` no depende de Optuna ni de ningún optimizer.
- Es puramente un wrapper de ejecución sobre el engine existente.
- Debe ser usable independientemente desde scripts o notebooks.

### Criterio de salida

- ParallelExecutor funcional con throughput ≥10× verificado,
- schemas completos,
- tests passing.

---

## 4. Fase 2 — Optuna single-objective

### Objetivo

Entregar el primer optimizer funcional que produce candidatas ordenadas.

### Tareas

1. Implementar `_internal/objective.py`:
   - `BacktestObjective` como callable para Optuna.
   - Mapping de `params_schema()` a `trial.suggest_*()`.
   - Integración de parámetros de RM en el search space.
2. Implementar `optuna_optimizer.py`:
   - `OptunaOptimizer` con TPESampler, MedianPruner.
   - Persistence en SQLite.
   - Resume de studies existentes.
   - `get_top_n()` para extraer candidatas.
3. Test de convergencia:
   - 100 trials sobre datos sintéticos controlados.
   - Verificar que el optimizer converge hacia el óptimo conocido.
   - Comparar TPE vs Random Search.
4. Tests:
   - `test_optuna.py` — objective, study persistence, pruning, top_n.

### Orden sugerido

1. Objective function (es el puente entre Optuna y el engine).
2. OptunaOptimizer wrapper.
3. Convergence test.
4. Study persistence y resume.

### Criterio de salida

- Optuna optimizer funcional sobre datos sintéticos y reales,
- study persistente y resumable,
- convergencia demostrada en test controlado,
- tests pasando.

---

## 5. Fase 3 — Walk-Forward Optimization

### Objetivo

Producir equity curves OOS como base para todos los filtros de anti-overfitting.

### Tareas

1. Implementar `walk_forward.py`:
   - `WalkForwardEngine` con `generate_splits()`.
   - Modo rolling: ventana deslizante de tamaño fijo.
   - Modo anchored: inicio fijo, ventana creciente.
   - Gap configurable entre IS y OOS.
2. Implementar lógica de re-optimización por fold:
   - En cada fold IS, correr optimización (Optuna o grid exhaustivo).
   - Aplicar best params de IS al periodo OOS.
   - Recolectar equity curve y métricas OOS.
3. Implementar concatenación de OOS:
   - Concatenar equity curves OOS de todos los folds.
   - Calcular métricas agregadas sobre OOS completo.
   - Calcular degradación IS→OOS por candidato.
4. Tests:
   - `test_walk_forward.py` — splits correctos, gap respetado, OOS concat,
     degradación calculada, rolling vs anchored.

### Recomendación

Primero soportar un caso simple:

- un símbolo, un timeframe, un arquetipo,
- 5 folds rolling con IS:OOS = 3:1,
- grid pequeño (100 combos) por fold,
- verificar que OOS cubra todo el rango sin huecos.

### Criterio de salida

- WFO rolling y anchored funcionales,
- OOS equity curves concatenadas correctamente,
- degradación ratio calculada por candidato,
- tests pasando.

---

## 6. Fase 4 — Anti-overfitting core

### Objetivo

Implementar los filtros estadísticos que separan estrategias genuinas de
artefactos de overfitting.

### Tareas

1. Implementar CSCV en `anti_overfit.py`:
   - `CSCVValidator.compute_pbo()`.
   - División en S=16 sub-muestras.
   - C(16,8) combinaciones IS/OOS.
   - Cálculo de ω (logit del rank relativo OOS).
   - PBO = proporción de ω ≤ 0.
2. Implementar DSR en `anti_overfit.py`:
   - `deflated_sharpe_ratio()`.
   - E[max(SR)] bajo null hypothesis.
   - Ajuste por skewness, kurtosis, sample length, n_trials.
3. Implementar `AntiOverfitPipeline`:
   - Encadena CSCV → DSR → (Hansen SPA si disponible).
   - Produce lista de finalistas con evidencia.
4. Tests:
   - `test_anti_overfit.py`:
     - CSCV overfit sintético → PBO ~1.0.
     - CSCV genuino sintético → PBO ~0.0.
     - DSR con muchos trials → penaliza.
     - DSR con pocos trials y Sharpe alto → significativo.
     - Pipeline completo → filtra correctamente.

### Diseño de tests sintéticos para CSCV

Para validar CSCV necesitamos dos tipos de equity curves:

- **Overfit**: equity curve que sube en la primera mitad y baja en la segunda
  (in-sample mining que colapsa out-of-sample).
- **Genuina**: equity curve con drift positivo consistente en todo el período
  (alpha real que no depende del período).

### Criterio de salida

- CSCV produce PBO correcto en ambos extremos,
- DSR ajusta correctamente por trials,
- pipeline integrado filtra overfit y acepta genuinas,
- tests pasando.

---

## 7. Fase 5 — Extensiones condicionales

### Objetivo

Implementar las extensiones que dependen de libs condicionales.

### 7.1. Hansen SPA (si `arch` disponible)

1. Implementar `hansen_spa_test()` en `anti_overfit.py`.
2. Integrar en `AntiOverfitPipeline` como filtro final.
3. Tests con estrategia que supera B&H vs que no supera.
4. Fallback: si `arch` no está, implementar bootstrap manual de bloques.

### 7.2. DEAP NSGA-II (si `deap` disponible)

1. Implementar `deap_optimizer.py`.
2. Individual encoding → float array.
3. NSGA-II con crossover SBX y mutation polynomial.
4. Comparar vs Optuna NSGAIISampler en benchmark pequeño.
5. Si Optuna multi-obj es suficiente, DEAP queda como alternativa.

### 7.3. Feature importance (si `xgboost` + `shap` disponibles)

1. Implementar `feature_importance.py`.
2. Entrenar meta-model sobre resultados de optimization.
3. SHAP values por parámetro.
4. Mutual information entre pares de indicadores.
5. `suggest_space_reduction()` para eliminar parámetros irrelevantes.

### Criterio de salida por extensión

Cada extensión es independiente. Se cierra cuando sus tests pasan y está
integrada (o documentada como no viable).

---

## 8. Fase 6 — Validación de referencia + reporting

### Objetivo

Cerrar el diferido de Sprint 4 sólo si aporta evidencia útil y generar los
documentos de cierre del sprint.

### Tareas

1. Seleccionar 10 combinaciones representativas.
2. Ejecutar en SuiteTrading con datos reales.
3. Priorizar validación con artifacts internos reproducibles del engine actual.
4. Usar TradingView sólo como spot-check manual si la comparación agrega señal.
5. Comparar 4 métricas con tolerancias (±5% NP, ±5pp WR, ±5% PF, ±10% DD).
6. Documentar divergencias con causas técnicas.
7. Redactar `docs/validation_report.md` sólo si el ejercicio aporta claridad material.
8. Redactar `docs/optimization_methodology.md`:
   - Descripción de cada componente del pipeline.
   - Fundamentación teórica de CSCV, DSR, Hansen SPA.
   - Configuraciones recomendadas.
9. Redactar `docs/anti_overfitting_report.md`:
   - Resultados de cada filtro aplicado.
   - Cuántas estrategias sobreviven cada etapa.
   - Distribución de PBO y DSR.

### Criterio de salida

- validation_report.md escrito sólo si la referencia externa agrega valor,
- optimization_methodology.md escrito,
- anti_overfitting_report.md escrito o diferido explícitamente.

---

## 9. Fase 7 — Hardening y cierre

### Objetivo

Evitar que Sprint 5 quede como demo útil pero arquitectura frágil.

### Tareas

1. Revisar edge cases:
   - optimizer con 0 trials completados,
   - WFO con datos insuficientes para min_is_bars,
   - CSCV con S > len(equity_curve),
   - DSR con n_trials=1.
2. Revisar consistencia del pipeline E2E.
3. Revisar que multiprocessing no introduce non-determinism.
4. Ejecutar suite completa: todos los tests de todos los sprints.
5. Redactar `docs/sprint5_completion_report.md`.
6. Actualizar la memoria del repo con estado post-Sprint 5.

### Criterio de salida

- suite completa verde,
- deuda explícita documentada,
- cierre del sprint auditable.

---

## 10. Estructura sugerida de tests

```text
tests/optimization/
├── __init__.py
├── conftest.py                  ← Fixtures: synthetic datasets, equity curves
├── test_schemas.py              ← Dataclasses creation and validation
├── test_parallel.py             ← ParallelExecutor: parallel vs sequential
├── test_optuna.py               ← Optimizer: objective, study, pruning
├── test_walk_forward.py         ← WFO: splits, concat, degradation
├── test_anti_overfit.py         ← CSCV, DSR, Hansen, pipeline
├── test_feature_importance.py   ← SHAP, MI (condicional)
└── test_integration.py          ← E2E pipeline
```

---

## 11. Casos prioritarios de test

- optimizer con espacio de 1 combinación → converge inmediatamente,
- optimizer con estrategia sintética conocida → encuentra el óptimo,
- optimizer resume desde study existente → no pierde trials,
- WFO rolling: 5 folds cubren los datos sin gaps no-intencionados,
- WFO anchored: IS crece en cada fold,
- WFO gap: barra de gap respetada en cada split,
- WFO OOS concat: equity curves concatenadas producen métricas coherentes,
- CSCV con equity curve monotónicamente creciente → PBO bajo,
- CSCV con equity curve overfit (up then down) → PBO alto,
- DSR con Sharpe=2.0 y 10 trials → significativo,
- DSR con Sharpe=0.5 y 10,000 trials → no significativo,
- Hansen SPA con strategy >> benchmark → p_value bajo,
- pipeline E2E: 20 candidatas → X finalistas (con X razonable),
- multiprocessing: resultados idénticos a single-thread.

---

## 12. Checklist de implementación

### Infraestructura

- [ ] dependencias core instaladas (optuna, scikit-learn)
- [ ] dependencias condicionales evaluadas
- [ ] pyproject.toml actualizado
- [ ] estructura de directorios creada
- [ ] contratos (schemas) definidos

### Core

- [ ] `parallel.py` — ParallelExecutor
- [ ] `_internal/objective.py` — BacktestObjective
- [ ] `optuna_optimizer.py` — OptunaOptimizer
- [ ] `walk_forward.py` — WalkForwardEngine
- [ ] `anti_overfit.py` — CSCV + DSR + pipeline

### Extensiones

- [ ] Hansen SPA (si `arch` viable)
- [ ] `deap_optimizer.py` (si `deap` viable)
- [ ] `feature_importance.py` (si `xgboost` + `shap` viables)

### Calidad

- [ ] tests unitarios por módulo
- [ ] tests de integración E2E
- [ ] benchmark paralelo vs single-thread
- [ ] convergencia de optimizer verificada
- [ ] optimization_methodology.md
- [ ] anti_overfitting_report.md
- [ ] validation_report.md (o diferimiento documentado)

---

## 13. Riesgos a controlar durante ejecución

### Riesgo 1 — Multiprocessing no-determinista

**Síntoma**: resultados paralelos difieren de secuenciales.
**Mitigación**: test explícito de determinismo (same configs → same results).
Cada worker debe ser puro (sin estado global mutable).

### Riesgo 2 — Optuna no converge en espacio grande

**Síntoma**: 500 trials y best_value sigue moviéndose.
**Mitigación**: empezar con espacio reducido, verificar convergencia, luego
escalar. Usar `n_startup_trials` suficiente (20-50) para warm-up del TPE.

### Riesgo 3 — CSCV produce PBO ininterpretable

**Síntoma**: PBO ~0.50 para todas las estrategias.
**Mitigación**: validar primero con equity curves sintéticas de extremos
conocidos. Si PBO no discrimina, revisar implementación o ajustar S.

### Riesgo 4 — Walk-Forward demasiado lento

**Síntoma**: WFO de 50 candidatas × 5 folds toma días.
**Mitigación**: ParallelExecutor dentro de cada fold. Pre-computar señales
una vez por fold y reutilizar. Limitar trials por fold IS.

### Riesgo 5 — Ninguna estrategia sobrevive todos los filtros

**Síntoma**: CSCV o DSR eliminan todo.
**Mitigación**: no es un error — es el resultado esperado si el espacio no
tiene alpha genuino. Documentar honestamente. Ajustar thresholds solo si
hay justificación teórica, nunca para "que algo pase".

---

## 14. Cierre documental del sprint

El orden correcto es:

1. fijar contratos y multiprocessing,
2. implementar optimizer y verificar convergencia,
3. implementar WFO y verificar OOS equity curves,
4. implementar anti-overfit y verificar filtros,
5. extensiones condicionales según disponibilidad de deps,
6. validación TV y reporting,
7. recién entonces consolidar methodology y anti_overfitting_report.
