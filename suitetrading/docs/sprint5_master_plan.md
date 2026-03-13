# Sprint 5 — Optimización y Anti-Overfitting: Master Plan

> **Objetivo**: implementar un pipeline completo de optimización de estrategias
> con validación estadística rigurosa de anti-overfitting, capaz de reducir
> millones de combinaciones a un conjunto defendible de estrategias finalistas
> con evidencia cuantificable de robustez.

> **Nota de vigencia (2026-03-12)**: Sprint 5 ya fue implementada y cerrada.
> Este documento queda como plan histórico de referencia. Para el estado real,
> usar `docs/sprint5_completion_report.md`. TradingView no forma parte del
> criterio operativo principal del sprint y sólo se conserva como referencia
> visual puntual cuando aporta señal.

---

## 1. Contexto real de inicio

Sprint 5 arrancó sobre cuatro sprints cerrados y un módulo target vacío.

### 1.1. Qué ya está resuelto

- Sprint 1 dejó operativa la capa de datos: descarga, storage, validación,
  resampling multi-timeframe y warmup.
- Sprint 2 dejó funcionando el núcleo de indicadores custom y el combinador de
  señales, con helpers MTF reutilizables.
- Sprint 3 dejó cerrado el framework de risk management:
  - `RiskConfig` validado con Pydantic,
  - `PositionStateMachine` determinista,
  - sizers, exit policies y portfolio controls,
  - seis arquetipos configurables,
  - prototipo de bridge hacia VectorBT.
- Sprint 4 dejó cerrado el motor de backtesting:
  - `BacktestEngine` con ejecución dual (FSM + simple) y auto mode selection,
  - `ParameterGridBuilder` con producto cartesiano, chunking y deduplicación,
  - `MetricsEngine` con 11 métricas vectorizadas (Sharpe, Sortino, Calmar, DD),
  - `ReportingEngine` con dashboards Plotly + CSV ranking,
  - `CheckpointManager` con persistencia Parquet ZSTD + resume,
  - `INDICATOR_REGISTRY` con 12 indicadores (6 custom Numba + 6 estándar TA-Lib),
  - benchmark reproducible: 63.7 backtests/sec single-thread, 3823/min,
  - 60 tests de backtesting, 509 tests totales, todos passing.

### 1.2. Qué quedó pendiente o requiere replanificación post-cierre

- `src/suitetrading/optimization/` existe y quedó integrado al paquete público.
- Existe suite dedicada en `tests/optimization/`.
- Existe `docs/optimization_methodology.md` como artefacto de cierre.
- `docs/anti_overfitting_report.md` no existe todavía como artefacto independiente.
- `docs/validation_report.md` siguió diferido desde Sprint 4 y no debe tratarse
  como gate duro de cierre de Sprint 5.
- La siguiente incertidumbre relevante ya no es el optimizer, sino la madurez
  real del search space y del wiring de RM en el runner actual.

### 1.3. Veredicto de readiness

**Sprint 5 quedó cerrada.**

El readiness que importa ahora pertenece al sprint siguiente: hardening del
runner actual, clasificación del espacio de búsqueda y selección de candidatas
antes de una validación externa más costosa.

---

## 2. Propósito del sprint

Sprint 5 convierte el motor de backtesting de Sprint 4 en una herramienta de
descubrimiento de estrategias con validación científica. Sin este sprint, los
resultados de backtesting no tienen valor predictivo — cualquier grid masivo
produce estrategias ganadoras in-sample que colapsan out-of-sample.

El pipeline target es:

```
Grid screening masivo (Sprint 4)
        │
        ▼
Optimización bayesiana (Optuna TPE)
        │
        ▼
Walk-Forward Optimization (IS/OOS splits)
        │
        ▼
CSCV → PBO < 50% (filtro anti-overfitting)
        │
        ▼
Deflated Sharpe Ratio (ajuste por múltiples trials)
        │
        ▼
Hansen SPA Test (superioridad vs benchmark)
        │
        ▼
Estrategias finalistas justificables
```

---

## 3. Principios de diseño

### 3.1. Estadística antes que ML

Los filtros de anti-overfitting son estadísticos, no modelos entrenados.
CSCV, DSR y Hansen SPA tienen fundamentos teóricos publicados (Bailey &
López de Prado, 2014; Hansen, 2005). Feature importance es complementario,
no sustituto.

### 3.2. Separación optimizer / validator

El módulo que busca estrategias (Optuna, DEAP) no es el mismo que las
valida (WFO, CSCV, DSR, Hansen). Deben ser componentes independientes
que se conectan via contratos explícitos.

### 3.3. Reproducibilidad total

Todo run de optimización debe ser reproducible con las mismas semillas,
datos y configuración. Los studies de Optuna se persisten. Los splits de
WFO son determinísticos. Los resultados de CSCV son verificables.

### 3.4. Paralelizable desde el diseño

Multiprocessing no es una optimización tardía — entra en Fase 1. Cada
componente debe soportar ejecución paralela sin estado compartido mutable.

### 3.5. No acoplar a un solo optimizer

Optuna es el optimizer principal, pero el pipeline de validación (WFO →
CSCV → DSR → Hansen) debe funcionar con cualquier fuente de estrategias
candidatas, sea Optuna, DEAP, grid exhaustivo o selección manual.

---

## 4. Alcance del Sprint 5

### T5.1 — Optimización single-objective con Optuna

- Implementar objective function que ejecuta backtest via `BacktestEngine.run()`.
- Configurar `TPESampler` con pruning (`MedianPruner`).
- Definir espacio de búsqueda desde `INDICATOR_REGISTRY.params_schema()`.
- Incluir parámetros de RM en el search space (SL mult, TP ratios, trailing).
- Priorizar por defecto sólo parámetros con integración `active`; los
        `partial`/`experimental` no deben entrar al optimizer principal.
- Persistir studies en SQLite para resume.
- Evaluar convergencia: cuántos trials son suficientes para el espacio actual.
- Comparar TPE vs Random Search en nuestro espacio.

### T5.2 — Optimización multi-objetivo con DEAP (condicional)

- Implementar individuo = [indicator_states + rm_params].
- Definir fitness multi-objetivo: maximize(Sharpe, -MaxDD, ProfitFactor).
- Configurar NSGA-II: population size, crossover/mutation rates, generations.
- Visualizar frente de Pareto.
- Comparar resultados DEAP vs Optuna `NSGAIISampler`.
- **Gate**: solo si DEAP es compatible con Python 3.14.

### T5.3 — Walk-Forward Optimization

- Implementar WFO rolling y anchored.
- Definir ventanas IS/OOS con ratios configurables (4:1, 3:1, 2:1).
- Implementar gap entre IS y OOS para evitar data leakage.
- Para cada combinación optimizada, concatenar resultados OOS.
- Comparar WFO rolling vs anchored para crypto (regímenes cambiantes).

### T5.4 — Combinatorially Symmetric Cross-Validation (CSCV)

- Implementar CSCV basado en Bailey & López de Prado (2014).
- S=16 sub-muestras, C(16,8) = 12,870 combinaciones.
- Calcular Probability of Backtest Overfitting (PBO).
- Threshold: PBO < 50% → estrategia posiblemente válida.
- Aplicar a las top N estrategias post-optimization.

### T5.5 — Deflated Sharpe Ratio

- Implementar DSR según López de Prado (2014).
- Ajustar por: número de trials, skewness, kurtosis, sample length.
- Aplicar como filtro post-CSCV: solo estrategias con DSR significativo pasan.

### T5.6 — Hansen's Superior Predictive Ability Test

- Implementar usando la librería `arch` de Python.
- Benchmark: buy-and-hold del activo.
- Null hypothesis: ninguna estrategia supera al benchmark.
- Aplicar a los finalistas post-DSR.

### T5.7 — Feature importance y reducción de espacio (condicional)

- Entrenar XGBoost/LightGBM: features = params → target = Sharpe.
- Calcular SHAP values para cada indicador/parámetro.
- Mutual Information entre indicadores → detectar redundancia.
- Reducir espacio de búsqueda eliminando regiones improductivas.
- **Gate**: solo si xgboost/shap son compatibles con Python 3.14.

### T5.8 — Paralelización del engine

- Implementar `ParallelExecutor` con `ProcessPoolExecutor`.
- Integrar con `BacktestEngine.run_batch()`.
- Benchmark: confirmar throughput ≥10× vs single-thread (target ~890 bt/sec).
- Soporte de chunk distribution para WFO y CSCV.
- Documentar guía de scaling: cuándo local es suficiente vs cloud.

---

## 5. Arquitectura objetivo del módulo optimization

### 5.1. Estructura de archivos

```text
src/suitetrading/optimization/
├── __init__.py              ← Superficie pública: exports principales
├── optuna_optimizer.py      ← OptunaOptimizer: single y multi-objective
├── walk_forward.py          ← WalkForwardEngine: rolling + anchored
├── anti_overfit.py          ← CSCV, DSR, Hansen SPA
├── parallel.py              ← ParallelExecutor: multiprocessing wrapper
├── feature_importance.py    ← SHAP + Mutual Info (condicional)
├── _internal/
│   ├── __init__.py
│   ├── schemas.py           ← Contratos: ObjectiveResult, WFOConfig, etc.
│   └── objective.py         ← BacktestObjective: bridge optimizer→engine
└── deap_optimizer.py        ← DEAPOptimizer: NSGA-II (condicional)
```

### 5.2. Flujo de datos

```text
INDICATOR_REGISTRY + RiskConfig
        │
        ▼
Search Space Definition
        │
        ▼
┌─────────────────────────────┐
│  OptunaOptimizer / DEAP     │
│  (ParallelExecutor inside)  │
└─────────────┬───────────────┘
              │ top N candidates
              ▼
┌─────────────────────────────┐
│  WalkForwardEngine          │
│  rolling + anchored splits  │
└─────────────┬───────────────┘
              │ OOS performance
              ▼
┌─────────────────────────────┐
│  Anti-Overfit Pipeline      │
│  CSCV → DSR → Hansen SPA   │
└─────────────┬───────────────┘
              │ finalistas
              ▼
ReportingEngine + docs
```

---

## 6. Readiness gates del sprint

### 6.1. Gates duros

Estos ítems deben existir antes de cerrar Sprint 5:

- optimizer funcional (Optuna) con objective function integrada al engine,
- walk-forward optimization (rolling + anchored) implementado,
- CSCV con PBO calculable sobre top N estrategias,
- DSR implementado como filtro post-CSCV,
- multiprocessing funcional con throughput ≥10× vs single-thread,
- suite de `tests/optimization/` con cobertura real,
- `docs/optimization_methodology.md` como artefacto de cierre,
- `docs/sprint5_completion_report.md` como artefacto auditable de cierre.

### 6.2. Gates blandos

Estos ítems no bloquean cierre pero condicionan alcance:

- DEAP/NSGA-II puede no funcionar en Python 3.14,
- feature importance con SHAP/XGBoost depende de compatibilidad,
- Hansen SPA puede requerir `arch` — verificar install en Python 3.14,
- `validation_report.md` (retomado de T4.6) queda como referencia opcional,
- escalado a cloud es investigación documentada, no implementación.

---

## 7. Deliverables del sprint

### Código

- `src/suitetrading/optimization/optuna_optimizer.py`
- `src/suitetrading/optimization/walk_forward.py`
- `src/suitetrading/optimization/anti_overfit.py`
- `src/suitetrading/optimization/parallel.py`
- `src/suitetrading/optimization/_internal/schemas.py`
- `src/suitetrading/optimization/_internal/objective.py`
- `src/suitetrading/optimization/deap_optimizer.py` (condicional)
- `src/suitetrading/optimization/feature_importance.py` (condicional)

### Tests

- `tests/optimization/test_optuna.py`
- `tests/optimization/test_walk_forward.py`
- `tests/optimization/test_anti_overfit.py`
- `tests/optimization/test_parallel.py`
- `tests/optimization/test_integration.py`
- `tests/optimization/test_schemas.py`

### Documentación

- `docs/sprint5_master_plan.md` (este documento)
- `docs/sprint5_technical_spec.md`
- `docs/sprint5_implementation_guide.md`
- `docs/optimization_methodology.md` — artefacto de cierre
- `docs/sprint5_completion_report.md` — artefacto auditable de cierre
- `docs/anti_overfitting_report.md` — artefacto opcional si se ejecuta campaña completa
- `docs/validation_report.md` — referencia diferida desde Sprint 4

---

## 8. Riesgos principales

### Riesgo 1 — Scope explosion

Sprint 5 tiene 8 task areas, el más amplio hasta ahora. Sin priorización
estricta, el sprint se extiende indefinidamente.

**Mitigación**: core obligatorio es T5.1 + T5.3 + T5.4 + T5.5 + T5.8.
T5.2, T5.6 y T5.7 son extensiones condicionadas a disponibilidad de deps.

### Riesgo 2 — CSCV computacionalmente prohibitivo

C(16,8) = 12,870 combinaciones × N estrategias × backtest completo. Sin
paralelismo, CSCV de 50 estrategias puede tomar horas.

**Mitigación**: multiprocessing (T5.8) entra antes que CSCV (T5.4). Los
backtests de CSCV reutilizan equity curves pre-computadas, no re-ejecutan
el engine completo.

### Riesgo 3 — Dependencias incompatibles con Python 3.14

DEAP, XGBoost, SHAP y `arch` pueden no tener wheels para Python 3.14.

**Mitigación**: verificar compatibilidad en Fase 0 antes de commitear
scope. Los módulos condicionales (T5.2, T5.7) tienen flag explícito.
Si `arch` no funciona, Hansen SPA baja a gate blando.

### Riesgo 4 — Optuna + DEAP duplican esfuerzo

Ambos son optimizers. Si Optuna con `NSGAIISampler` cubre multi-objetivo,
DEAP puede ser redundante.

**Mitigación**: comparar Optuna NSGA-II vs DEAP NSGA-II con un benchmark
pequeño. Si Optuna es suficiente, DEAP no se implementa.

### Riesgo 5 — Validación TV manual y lenta

Usar TradingView como gate duro implica ejecución manual con Puppeteer
(~30-60 min por lote). No debe bloquear el cierre del sprint.

**Mitigación**: tratar TradingView sólo como spot-check visual acotado. Si no
aporta claridad material, documentarlo como referencia diferida y seguir con
validación interna/OOS del engine actual.

---

## 9. Criterio de cierre

Sprint 5 se considera cerrado cuando:

1. Existe un optimizer funcional (Optuna) que produce top N candidatas.
2. Existe WFO (rolling + anchored) con concatenación de resultados OOS.
3. CSCV produce PBO calculable y aplicable como filtro.
4. DSR está implementado como filtro post-CSCV.
5. Multiprocessing alcanza throughput ≥10× vs single-thread (≥637 bt/sec).
6. Existe pipeline E2E: screening → optimization → WFO → CSCV → DSR → finalistas.
7. Suite de tests en `tests/optimization/` con cobertura real.
8. Existen `optimization_methodology.md` y `sprint5_completion_report.md`.

---

## 10. Dependencias documentales

Sprint 5 se apoya directamente en:

- `RESEARCH_PLAN.md` (§ Sprint 5: Optimización y Anti-Overfitting)
- `docs/sprint4_completion_report.md` (§8.1 diferimiento validation_report, §9 next steps)
- `docs/sprint4_master_plan.md`
- `docs/sprint4_technical_spec.md`
- `docs/backtesting_benchmarks.md` (baseline de throughput)
- `docs/risk_management_framework.md` (arquetipos y RiskConfig)
- `docs/signal_flow.md` (flujo de señales)
- `docs/indicator_catalog.md` (indicadores disponibles)

---

## 11. Trazabilidad con el plan maestro

| Task | Área principal en Sprint 5 |
|------|----------------------------|
| T5.1 | Optuna optimizer + objective function + convergencia |
| T5.2 | DEAP NSGA-II multi-objetivo (condicional) |
| T5.3 | Walk-Forward Optimization rolling + anchored |
| T5.4 | CSCV + PBO como filtro primario de anti-overfitting |
| T5.5 | DSR como filtro post-CSCV |
| T5.6 | Hansen SPA como test final vs benchmark |
| T5.7 | Feature importance + reducción de espacio (condicional) |
| T5.8 | Multiprocessing + benchmark de escalabilidad |

La implementación concreta de estas áreas queda operacionalizada en
`docs/sprint5_technical_spec.md` y `docs/sprint5_implementation_guide.md`.
