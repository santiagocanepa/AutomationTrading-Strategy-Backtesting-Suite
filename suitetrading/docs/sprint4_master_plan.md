# Sprint 4 — Backtesting Core: Master Plan

> **Objetivo**: diseñar e implementar el core de backtesting de SuiteTrading
> como una capa de integración entre datos, indicadores y risk management,
> capaz de ejecutar backtests masivos con una estrategia explícita de
> vectorización, fallback secuencial, métricas auditables y validación contra
> referencias históricas.

---

## 1. Contexto real de inicio

Sprint 4 no arranca sobre una base neutra. Arranca sobre dos sprints ya
cerrados y un módulo target todavía vacío.

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
  - prototipo de bridge hacia VectorBT,
  - documento final `docs/risk_management_framework.md`.
- La suite completa del repo está verde y el módulo risk ya tiene cobertura
  fuerte, incluyendo tests de integración con indicadores reales.

### 1.2. Qué sigue incompleto y condiciona este sprint

- `src/suitetrading/backtesting/` sigue vacío salvo un `__init__.py` con
  intención declarativa.
- No existe todavía `engine.py`, `grid.py`, `metrics.py` ni `reporting.py`.
- VectorBT PRO aún no está integrado ni validado dentro del repo.
- El catálogo de indicadores estándar sigue incompleto y el registry central de
  indicadores no existe todavía como superficie pública.
- No existe aún `docs/backtesting_benchmarks.md` ni `docs/validation_report.md`.
- No hay suite dedicada en `tests/backtesting/`.

### 1.3. Veredicto de readiness

**Sprint 4 está en condición de GO, pero con gates explícitas.**

Se puede avanzar ya en:

- contratos del módulo backtesting,
- integración datos -> señales -> risk -> simulación,
- bridge VectorBT para arquetipos A/B/C,
- grid masivo con chunking y checkpointing,
- métricas y reporting,
- validación histórica acotada y benchmarks.

Debe quedar explícitamente acotado o diferido:

- vectorización completa de arquetipos D/E,
- integración live o event-driven real,
- optimización multiobjetivo de Sprint 5,
- integración NautilusTrader funcional de Sprint 6.

---

## 2. Propósito del sprint

Sprint 4 es el punto donde la suite deja de ser un conjunto de componentes
correctos por separado y pasa a comportarse como una plataforma de backtesting
usable a escala.

Este sprint debe producir un core con estas propiedades:

1. **Integrado**: consume datos validados, señales de indicadores y perfiles de riesgo reales.
2. **Escalable**: soporta grids grandes sin colapsar memoria ni perder trazabilidad.
3. **Determinista**: mismos inputs y misma config producen los mismos resultados.
4. **Medible**: genera métricas estandarizadas y artefactos comparables.
5. **Auditado**: permite contrastar resultados contra TradingView y explicar discrepancias.

---

## 3. Principios de diseño

### 3.1. Reusar contratos cerrados, no duplicarlos

Sprint 4 no debe reimplementar lo que ya existe:

- datos desde `suitetrading.data`,
- señales desde `Indicator.compute(...)`,
- quorum de señales desde `combine_signals(...)`,
- riesgo desde `RiskConfig`, `PositionStateMachine` y arquetipos.

### 3.2. Python legible primero, vectorización donde aporte valor real

No toda lógica de RM es igualmente vectorizable. Sprint 4 debe aceptar una
arquitectura híbrida:

- camino principal vectorizado para A/B/C,
- fallback secuencial + joblib para casos de baja vectorizabilidad.

### 3.3. El grid masivo es un problema de sistemas, no solo de loops

La dificultad real no es ejecutar un backtest, sino ejecutar miles o cientos de
miles sin desbordar RAM, perder progreso o generar resultados ilegibles.

### 3.4. Benchmarks y validación no son un apéndice

El sprint no se considera sólido si solo "corre". Debe medir:

- throughput,
- consumo aproximado de recursos,
- divergencia contra referencias históricas,
- resiliencia ante interrupciones.

### 3.5. Reporting sirve para explorar resultados, no para ocultar deuda

Primero deben existir métricas y esquemas de salida correctos. El dashboard se
construye sobre datos confiables, no al revés.

---

## 4. Alcance del Sprint 4

### 4.1. Dentro del sprint

#### T4.1 — Setup y evaluación de VectorBT PRO

- validación de instalación y uso real,
- prueba de custom simulators,
- benchmark inicial con nuestro workload,
- registro de limitaciones observadas.

#### T4.2 — Integración de indicadores

- convertir señales del engine actual a arrays consumibles por backtesting,
- soportar multi-timeframe mediante alineación explícita,
- precomputar indicadores una sola vez por dataset base,
- separar claramente generación de señales de ejecución del backtest.

#### T4.3 — Integración de risk management

- conectar arquetipos de Sprint 3 al engine de simulación,
- definir camino vectorizable para A/B/C,
- definir fallback secuencial para D/E y casos complejos,
- formalizar qué parte del state machine se reduce a callback/loop numba.

#### T4.4 — Pipeline de backtesting masivo

- generación de grids,
- chunking por memoria,
- persistencia incremental,
- progress tracking,
- checkpointing y resume.

#### T4.5 — Métricas y reporting

- cálculo de métricas clave,
- export en Parquet,
- dashboard exploratorio con Plotly,
- separación entre resultados brutos y vistas analíticas.

#### T4.6 — Validación contra resultados históricos

- selección de 10 combinaciones comparables,
- replay con mismos parámetros y datos equivalentes,
- comparación de métricas principales,
- documentación explícita de discrepancias razonables.

### 4.2. Fuera de alcance

Para mantener Sprint 4 limpio, no entran como objetivo de cierre:

- optimización Optuna/DEAP de Sprint 5,
- anti-overfitting estadístico,
- integración live con exchanges,
- ejecución event-driven real con fills parciales,
- integración funcional con NautilusTrader,
- reporting ejecutivo final de estrategias productivas.

---

## 5. Arquitectura objetivo del módulo backtesting

```text
src/suitetrading/backtesting/
├── __init__.py
├── engine.py
├── grid.py
├── metrics.py
├── reporting.py
└── _internal/
    ├── datasets.py
    ├── runners.py
    ├── checkpoints.py
    └── schemas.py
```

Los cuatro archivos públicos canónicos son los definidos en
`RESEARCH_PLAN.md`. Se permiten helpers internos si reducen complejidad sin
romper la superficie pública.

---

## 6. Readiness gates del sprint

### 6.1. Gates duros

Estos ítems deben existir antes de cerrar Sprint 4:

- `engine.py`, `grid.py`, `metrics.py` y `reporting.py` implementados;
- suite de `tests/backtesting/` con cobertura real;
- bridge funcional para A/B/C sobre datasets reales o sintéticos controlados;
- persistencia de resultados intermedios en Parquet;
- benchmark reproducible del pipeline;
- documento de validación histórica contra TradingView.

### 6.2. Gates blandos

Estos ítems no bloquean iniciar Sprint 4, pero sí condicionan alcance:

- VectorBT PRO puede requerir licencia/instalación separada;
- registry de indicadores inexistente;
- catálogo estándar de indicadores incompleto;
- arquetipos D/E probablemente requieran fallback secuencial;
- la comparación con TradingView no será bit-perfect por diferencias de ejecución.

---

## 7. Deliverables del sprint

### Código

- `src/suitetrading/backtesting/engine.py`
- `src/suitetrading/backtesting/grid.py`
- `src/suitetrading/backtesting/metrics.py`
- `src/suitetrading/backtesting/reporting.py`

### Tests

- `tests/backtesting/test_engine.py`
- `tests/backtesting/test_grid.py`
- `tests/backtesting/test_metrics.py`
- `tests/backtesting/test_reporting.py`
- `tests/backtesting/test_integration.py`
- benchmarks reproducibles del pipeline principal

### Documentación

- `docs/sprint4_master_plan.md`
- `docs/sprint4_technical_spec.md`
- `docs/sprint4_implementation_guide.md`
- `docs/backtesting_benchmarks.md` como artefacto de cierre del sprint
- `docs/validation_report.md` como artefacto de cierre del sprint

---

## 8. Riesgos principales

### Riesgo 1 — Acoplar todo el sprint a VectorBT PRO

Si el diseño depende de una sola integración cerrada, cualquier bloqueo de
licencia, API o performance frena el sprint completo.

**Mitigación**: arquitectura dual con camino principal VectorBT y fallback
loop-based/joblib documentado desde el inicio.

### Riesgo 2 — Intentar vectorizar arquetipos secuenciales demasiado pronto

Pyramidal y Grid/DCA pueden degradar el diseño si se fuerzan en el mismo molde
que A/B/C.

**Mitigación**: A/B/C primero; D/E con tratamiento explícito de baja
vectorizabilidad.

### Riesgo 3 — Explosión de combinaciones sin estrategia de memoria

El grid combinatorio puede inutilizar el sprint si no se define chunking,
persistencia y resume antes de correrlo.

**Mitigación**: `grid.py` y checkpointing entran en el core del sprint, no como
optimización tardía.

### Riesgo 4 — Comparación ingenua con TradingView

Diferencias de fill model, comisiones, slippage y manejo de gaps pueden generar
desvíos que no implican error del engine.

**Mitigación**: matriz de tolerancias y registro explícito de causas esperables
de divergencia.

### Riesgo 5 — Reporting vistoso sobre resultados opacos

Un dashboard bonito no compensa métricas mal definidas o resultados sin
esquema estable.

**Mitigación**: métricas y schemas primero; visualización después.

---

## 9. Criterio de cierre

Sprint 4 se considera cerrado cuando:

1. Existe un engine de backtesting ejecutable que conecta datos, señales y RM.
2. A/B/C pueden correr de extremo a extremo con el bridge definido para Sprint 4.
3. El pipeline soporta grids grandes con chunking, persistencia y resume.
4. Las métricas clave se calculan de forma consistente y exportable.
5. Existe un benchmark reproducible que soporta o refuta el objetivo de escala.
6. Existe un `validation_report.md` con comparación explícita contra TradingView.
7. La documentación distingue sin ambigüedad camino vectorizado vs fallback.
8. El módulo `backtesting/` deja de ser scaffolding y pasa a ser superficie pública usable.

---

## 10. Dependencias documentales

Sprint 4 se apoya directamente en:

- `RESEARCH_PLAN.md`
- `docs/sprint1_completion_report.md`
- `docs/sprint2_master_plan.md`
- `docs/sprint2_technical_spec.md`
- `docs/sprint2_implementation_guide.md`
- `docs/sprint3_master_plan.md`
- `docs/sprint3_technical_spec.md`
- `docs/sprint3_implementation_guide.md`
- `docs/risk_management_framework.md`
- `docs/signal_flow.md`

---

## 11. Trazabilidad con el plan maestro

| Task | Área principal en Sprint 4 |
|------|----------------------------|
| T4.1 | setup VectorBT + benchmark base + límites observados |
| T4.2 | integración de señales y MTF desde indicators/data |
| T4.3 | bridge RM -> simulación, A/B/C vectorizados y fallback D/E |
| T4.4 | `grid.py` + chunking + checkpointing + persistencia |
| T4.5 | `metrics.py` + `reporting.py` + esquema Parquet |
| T4.6 | validación histórica + `validation_report.md` |

La implementación concreta de estas áreas queda operacionalizada en
`docs/sprint4_technical_spec.md` y `docs/sprint4_implementation_guide.md`.