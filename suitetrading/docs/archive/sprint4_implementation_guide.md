# Sprint 4 — Backtesting Core: Implementation Guide

> **Propósito**: convertir el alcance y los contratos de Sprint 4 en un orden
> de ejecución concreto, con dependencias explícitas, paralelismo realista y
> criterios de salida verificables.

---

## 1. Orden recomendado de trabajo

```text
Baseline + contracts
        │
        ▼
dataset + signal preparation
        │
        ▼
engine path for A/B/C
        │
        ▼
grid + checkpoints + persistence
        │
        ▼
metrics + reporting
        │
        ▼
validation + benchmarks + closure docs
```

Razón del orden:

- primero se fijan contratos del módulo,
- luego se conectan datos y señales,
- después se implementa el camino de ejecución más valioso,
- recién entonces se escala a grids masivos,
- al final se validan performance y paridad histórica.

---

## 2. Fase 0 — Baseline y gates

### Objetivo

Arrancar Sprint 4 con supuestos explícitos y con el cierre real de Sprint 3.

### Tareas

1. Verificar que la suite siga verde.
2. Confirmar que `risk_management_framework.md` sea la referencia del engine de RM.
3. Confirmar qué indicadores custom están listos y qué gaps del catálogo siguen abiertos.
4. Confirmar que `backtesting/` siga en stub para no documentar sobre código inexistente.
5. Decidir el modo operativo inicial:
   - VectorBT PRO disponible,
   - fallback loop-based disponible,
   - ambos.

### Criterio de salida

- baseline técnico aceptado,
- prerequisitos documentados,
- alcance de Sprint 4 congelado.

---

## 3. Fase 1 — Contratos del módulo backtesting

### Objetivo

Evitar que el sprint se fragmente en scripts sin interfaz estable.

### Tareas

1. Definir `BacktestDataset`.
2. Definir `StrategySignals`.
3. Definir `GridRequest` y esquema mínimo de combinaciones.
4. Definir `BacktestCheckpoint`.
5. Definir interfaces de `BacktestEngine`, `MetricsEngine` y `ReportingEngine`.

### Reglas

- contratos pequeños y serializables,
- separación explícita entre config, runtime state y resultados,
- tipos compatibles con persistencia y benchmarking.

### Criterio de salida

- interfaces cerradas,
- naming consistente,
- sin ambigüedad entre input, execution y output.

---

## 4. Fase 2 — Datos y preparación de señales

### Objetivo

Construir una entrada estable para el engine antes de pensar en escala.

### Tareas

1. Implementar loader de datasets desde `ParquetStore`.
2. Integrar resampling y alineación MTF.
3. Integrar warmup trimming.
4. Definir pipeline de cálculo/pre-cálculo de indicadores.
5. Definir conversión a `StrategySignals`.
6. Formalizar el registry mínimo de indicadores para grids.

### Recomendación

Primero soportar un caso simple y confiable:

- un símbolo,
- un timeframe base,
- dos o tres indicadores reales del repo,
- arquetipo A o B.

### Criterio de salida

- dataset reproducible,
- señales alineadas y testeables,
- sin ambigüedad entre signal generation y execution.

---

## 5. Fase 3 — Engine de ejecución para A/B/C

### Objetivo

Entregar primero el camino con más valor y más chances de escalar.

### Orden sugerido

1. Trend Following
2. Mean Reversion
3. Mixed

### Tareas

1. Implementar `engine.py` con un run simple end-to-end.
2. Integrar `RiskConfig` y arquetipos A/B/C.
3. Conectar `PositionStateMachine` sin duplicar la lógica de prioridad.
4. Definir qué parte corre por VectorBT y qué parte por loop explícito.
5. Validar equity curve, trades y outputs mínimos.

### Criterio de salida

- A/B/C ejecutables de extremo a extremo,
- resultados persistibles,
- tests de integración pasando.

---

## 6. Fase 4 — Grid, chunking y checkpointing

### Objetivo

Escalar el engine a workloads reales sin perder control operativo.

### Tareas

1. Implementar `grid.py`.
2. Generar combinaciones reproducibles desde params de indicadores y RM.
3. Implementar chunking por tamaño de lote.
4. Implementar checkpointing y resume.
5. Persistir resultados intermedios en Parquet.
6. Registrar progreso y tiempo estimado restante.

### Regla clave

Ningún batch grande debe depender de memoria completa en RAM.

### Criterio de salida

- grid reproducible,
- chunks reanudables,
- runs interrumpidos recuperables.

---

## 7. Fase 5 — Métricas y reporting

### Objetivo

Convertir resultados crudos en artefactos auditables y explorables.

### Tareas

1. Implementar `metrics.py`.
2. Definir esquema unificado de resultados.
3. Implementar `reporting.py`.
4. Generar dashboard exploratorio con Plotly.
5. Validar consistencia entre resultados persistidos y visualizaciones.

### Recomendación

No construir el dashboard sobre estructuras ad hoc. Primero congelar el schema.

### Criterio de salida

- métricas mínimas calculadas,
- resultados exportados en Parquet,
- dashboard reproducible sobre outputs reales.

---

## 8. Fase 6 — Validación histórica y benchmarks

### Objetivo

Demostrar que el engine no solo corre, sino que produce resultados defendibles.

### Tareas

1. Seleccionar 10 combinaciones históricas comparables.
2. Reproducir sus condiciones de datos y parámetros.
3. Comparar métricas clave frente a TradingView.
4. Documentar divergencias con causas técnicas explícitas.
5. Ejecutar benchmark del pipeline principal.
6. Redactar `docs/backtesting_benchmarks.md`.
7. Redactar `docs/validation_report.md`.

### Criterio de salida

- benchmark reproducible disponible,
- validación histórica documentada,
- tolerancias evaluadas contra objetivos del sprint.

---

## 9. Fase 7 — Hardening y cierre

### Objetivo

Evitar que Sprint 4 quede como demo útil pero arquitectura frágil.

### Tareas

1. Revisar fallbacks para D/E.
2. Revisar manejo de errores por chunk.
3. Revisar consistencia del schema Parquet.
4. Revisar costo real del camino VectorBT vs loop batch.
5. Cerrar checklist del sprint.

### Criterio de salida

- módulo `backtesting/` usable,
- deuda explícita documentada,
- cierre del sprint auditable.

---

## 10. Estructura sugerida de tests

```text
tests/backtesting/
├── test_engine.py
├── test_grid.py
├── test_metrics.py
├── test_reporting.py
├── test_integration.py
└── test_benchmarks.py
```

---

## 11. Casos prioritarios de test

- run simple sin trades,
- run con un trade ganador y uno perdedor,
- A/B/C con señales reales del repo,
- chunk ya procesado que se salta correctamente,
- resume tras interrupción,
- resultado persistido y re-leído sin pérdida de schema,
- divergencia controlada frente a TradingView,
- fallback D/E sin colapsar el batch completo.

---

## 12. Checklist de implementación

### Infraestructura

- [ ] contratos del módulo backtesting definidos
- [ ] decisión explícita sobre VectorBT PRO y fallback
- [ ] registry mínimo de indicadores definido

### Core

- [ ] `engine.py`
- [ ] `grid.py`
- [ ] `metrics.py`
- [ ] `reporting.py`

### Integración

- [ ] datos -> señales -> risk -> engine
- [ ] A/B/C integrados
- [ ] fallback D/E documentado o implementado

### Operación

- [ ] chunking
- [ ] checkpointing
- [ ] resume
- [ ] persistencia Parquet

### Calidad

- [ ] tests unitarios
- [ ] tests de integración
- [ ] benchmarks reproducibles
- [ ] validación histórica documentada

---

## 13. Riesgos a controlar durante ejecución

### Riesgo 1 — Forzar VectorBT en todo el dominio

**Mitigación**: aceptar híbrido vectorizable + loop batch.

### Riesgo 2 — Grids gigantes sin estrategia de persistencia

**Mitigación**: grid y checkpointing entran antes de correr benchmarks grandes.

### Riesgo 3 — Métricas inconsistentes entre runs

**Mitigación**: schema único en `metrics.py` y pruebas específicas de consistencia.

### Riesgo 4 — Validación histórica mal interpretada

**Mitigación**: documentar tolerancias y causas esperables de divergencia.

### Riesgo 5 — Empezar por D/E y atascar el sprint

**Mitigación**: A/B/C primero; D/E solo después de estabilizar el camino principal.

---

## 14. Cierre documental del sprint

El orden correcto es:

1. cerrar contratos,
2. integrar datos y señales,
3. cerrar engine para A/B/C,
4. escalar con grid y persistencia,
5. medir y validar,
6. recién entonces consolidar benchmarks y validation report.

Esto evita escribir documentos de cierre sobre un engine todavía ambiguo.