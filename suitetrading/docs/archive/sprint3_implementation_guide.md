# Sprint 3 — Risk Management Engine: Implementation Guide

> **Propósito**: convertir el plan y la especificación de Sprint 3 en un orden
> de ejecución concreto, con dependencias claras, paralelismo realista y
> criterios de salida verificables.

---

## 1. Orden recomendado de trabajo

```text
Readiness baseline + contracts
            │
            ▼
position_sizing.py + trailing.py
            │
            ▼
state_machine.py core
            │
            ▼
legacy profile + archetypes A/B/C
            │
            ▼
portfolio.py
            │
            ▼
archetypes D/E + vectorbt bridge prototype
            │
            ▼
tests/risk + integration docs + completion artifact
```

Razón del orden:

- primero se fijan contratos y restricciones;
- luego se implementan piezas reutilizables;
- después se ensambla el state machine sobre esas piezas;
- por último se incorporan presets, portfolio controls y bridge de simulación.

---

## 2. Fase 0 — Baseline y gates

### Objetivo

Arrancar Sprint 3 con supuestos explícitos y no con supuestos implícitos.

### Tareas

1. Verificar que Sprint 1 siga verde y usable como base de datos/timeframes.
2. Confirmar qué contratos de indicadores están estables y cuáles siguen faltando.
3. Confirmar que `risk_management_spec.md` y `signal_flow.md` sigan siendo la
   referencia legacy vigente.
4. Dejar por escrito los gaps blandos que no bloquean Sprint 3:
   - registry inexistente,
   - catálogo incompleto,
   - backtesting vacío,
   - sin `indicator_validation_report.md`.

### Criterio de salida

- baseline técnico aceptado
- riesgos de integración visibles
- alcance de Sprint 3 congelado

---

## 3. Fase 1 — Contratos del módulo risk

### Objetivo

Evitar que cada archivo invente su propia semántica.

### Tareas

1. Consolidar el enum `PositionState` y decidir si se mantiene el set actual o
   si se amplía con estados pendientes.
2. Definir estructuras de estado y resultados de transición.
3. Definir configuración validada del risk engine.
4. Definir interfaces base para:
   - sizers,
   - exit policies,
   - archetypes,
   - portfolio manager.

### Reglas

- contratos pequeños y explícitos;
- config separada de runtime state;
- tipos serializables y numba-friendly cuando sea posible.

### Criterio de salida

- interfaces cerradas
- naming consistente
- sin ambigüedad entre legacy y v2

---

## 4. Fase 2 — Position sizing

### Objetivo

Implementar primero las piezas matemáticas más reusables del sprint.

### Orden sugerido

1. Fixed Fractional
2. ATR-based sizing
3. Kelly / Fractional Kelly
4. Optimal f como experimental

### Razón

- Fixed Fractional y ATR-based cubren la mayoría de los usos reales.
- Kelly necesita caps y validaciones más estrictas.
- Optimal f aporta valor de research, pero no debe dictar el diseño base.

### Tests mínimos por modelo

- output esperado con números controlados
- invalid input handling
- caps duros de riesgo
- cero división / stop inválido / volatilidad nula

### Criterio de salida

- `position_sizing.py` usable sin depender del state machine

---

## 5. Fase 3 — Exit policies y trailing

### Objetivo

Separar la lógica de salida del core de transición de estados.

### Orden sugerido

1. break-even policy
2. fixed trailing
3. ATR trailing
4. Chandelier
5. Parabolic SAR
6. signal trailing para SSL LOW

### Regla clave

No diseñar `trailing.py` como simple cálculo de precio stop. También debe
soportar salidas disparadas por señal, porque la lógica legacy lo necesita.

### Criterio de salida

- `trailing.py` cubre price-based y signal-based exits con la misma semántica de evaluación

---

## 6. Fase 4 — Core del state machine

### Objetivo

Construir la pieza central del sprint usando contratos ya cerrados.

### Tareas

1. Implementar evaluación por barra con prioridad fija:
   - SL
   - TP1
   - BE
   - trailing
   - entry/pyramid
2. Implementar transición por eventos y razones auditables.
3. Implementar soporte long/short.
4. Implementar pyramiding y partial close.
5. Implementar reinicio correcto a `FLAT`.

### Recomendación

Primero construir un `python_mode` muy claro y testeable. No optimizar con
Numba antes de validar la semántica completa.

### Criterio de salida

- state machine determinista
- cobertura alta de transiciones
- sin edge cases abiertos en prioridad de eventos

---

## 7. Fase 5 — Legacy profile

### Objetivo

Capturar la lógica actual del Pine como un preset reusable dentro del framework.

### Tareas

1. Implementar preset con:
   - Firestorm TM como SL base
   - Fibonacci add weighting
   - partial TP por SSL opuesta
   - break-even buffer = 1.0007
   - trailing por SSL LOW
2. Mantener explícito que el Pine original es asimétrico en short side.
3. Soportar long y short en el framework aunque el preset legacy venga de un
   comportamiento principalmente long-only.

### Criterio de salida

- la lógica legacy se puede ejecutar como preset sin hardcodear todo el framework a esa estrategia

---

## 8. Fase 6 — Arquetipos A, B y C

### Objetivo

Cerrar primero los perfiles con más valor para Sprint 4.

### Orden sugerido

1. Trend Following
2. Mean Reversion
3. Mixed

### Razón

- A, B y C son los perfiles más reutilizables para screening y validación inicial.
- Son también los más importantes según el `RESEARCH_PLAN.md` y el research de RM.

### Recomendación de implementación

Cada arquetipo debe construirse como preset compuesto de:

- sizing model,
- stop/exit policy,
- break-even rule,
- pyramiding rule,
- portfolio caps.

No duplicar la lógica del state machine por arquetipo.

### Criterio de salida

- A/B/C ejecutables sobre señales reales del repo

---

## 9. Fase 7 — Arquetipos D y E

### Objetivo

Completar el alcance del sprint sin contaminar el core con lógica específica.

### Arquetipo D — Pyramidal Scaling

Debe definir:

- initial allocation,
- add levels,
- stop mode grupal o individual,
- TP/trailing del total.

### Arquetipo E — Grid/DCA

Debe definir:

- spacing,
- max levels,
- weighted average TP,
- drawdown cap,
- max adverse excursion aceptable.

### Recomendación

Estos dos perfiles deben entrar después de tener core, sizing y portfolio caps,
porque son los más propensos a inducir complejidad accidental.

### Criterio de salida

- Los **cinco arquetipos** (A, B, C, D, E) están implementados, testeados y
  ejecutables (`RESEARCH_PLAN.md:420`)

---

## 10. Fase 8 — Portfolio risk

### Objetivo

Evitar que los modelos por posición se ejecuten sin control agregado.

### Tareas

1. Implementar monitor de drawdown por estrategia.
2. Implementar portfolio heat.
3. Implementar gross/net exposure caps.
4. Implementar kill switch.
5. Implementar evaluación de correlación con criterio pragmático.
6. Implementar Monte Carlo de robustez a nivel de secuencia de trades.

### Regla

Ningún arquetipo puede aprobar exposición nueva sin pasar por `portfolio.py`.

### Criterio de salida

- existe decisión `approve / reduce / halt` documentada y testeada

---

## 11. Fase 9 — Compatibilidad con VectorBT y NautilusTrader

### Objetivo

Entregar un prototipo funcional de VectorBT y una especificación de
compatibilidad con NautilusTrader, según exige `RESEARCH_PLAN.md:327,422`.

### Tareas VectorBT

1. Diseñar el adapter de simulación en `vbt_simulator.py`.
2. Documentar qué estado debe aplanarse para callbacks/loops numba.
3. Clasificar arquetipos por vectorizabilidad:
   - alta: A, B, C simplificados
   - media: C con partial + trail complejo
   - baja: D, E completos
4. Definir fallback para casos no vectorizables.
5. **Implementar prototipo funcional** que ejecute simulaciones básicas de
   A, B y C (entry/exit/SL) sobre arrays numpy.
6. Tests de sanity: no pierde dinero sin trades, trade ganador → PnL > 0.

### Tareas NautilusTrader

7. Documentar mapeo de `PositionState` → conceptos NT (sección 11b del
   tech spec).
8. Documentar mapeo de `TransitionEvent` → eventos NT.
9. Documentar modelo de fills parciales y cómo la interfaz los admite
   contractualmente.
10. Documentar mapeo de `orders.action` → tipos de orden NT.

### Criterio de salida

- Prototipo funcional de VectorBT ejecuta A, B y C con tests que pasan
- Sprint 4 recibe un contrato claro de integración, no un experimento ambiguo
- Sprint 6 recibe un mapeo completo de estados/eventos/órdenes NT

---

## 12. Fase 10 — Testing y validación

### Objetivo

Que Sprint 3 no termine con documentación fuerte y confianza débil.

### Suite sugerida

```text
tests/risk/
├── test_position_sizing.py
├── test_state_machine.py
├── test_trailing.py
├── test_portfolio.py
├── test_archetype_trend_following.py
├── test_archetype_mean_reversion.py
├── test_archetype_mixed.py
├── test_archetype_pyramidal.py
└── test_archetype_grid_dca.py
```

### Casos prioritarios

- SL y nueva señal en la misma barra
- TP1 y trailing en la misma barra
- BE activado y golpeado en la barra siguiente
- pyramiding cerca del límite máximo
- Kelly con inputs incoherentes
- Grid con DD cap disparado
- portfolio heat bloqueando una nueva entrada válida a nivel local

### Criterio de salida

- suite de `tests/risk/` es parte real del sprint, no tarea postergada

---

## 13. Checklist de implementación

### Infraestructura

- [ ] contratos del módulo risk definidos
- [ ] naming consistente de estados y eventos
- [ ] diferencia explícita entre legacy profile y framework v2

### Core

- [ ] `position_sizing.py`
- [ ] `trailing.py`
- [ ] `state_machine.py`

### Perfiles

- [ ] legacy profile
- [ ] archetype A
- [ ] archetype B
- [ ] archetype C
- [ ] archetype D
- [ ] archetype E

### Portfolio

- [ ] `portfolio.py`
- [ ] heat / drawdown / exposure / kill switch
- [ ] Monte Carlo básico

### Integración futura

- [ ] `vbt_simulator.py` con prototipo funcional para A, B, C
- [ ] tabla de vectorizabilidad por arquetipo
- [ ] mapeo de estados/eventos/fills/órdenes para NautilusTrader (sección 11b tech spec)

### Semántica de ejecución

- [ ] gap-aware SL fill implementado (sección 4.3.2 tech spec)
- [ ] slippage configurable en `RiskConfig` (sección 4.3.3 tech spec)
- [ ] fills parciales admitidos contractualmente (sección 4.3.4 tech spec)

### Calidad

- [ ] tests unitarios
- [ ] tests de transición
- [ ] tests de integración mínima
- [ ] documentación de cierre preparada

---

## 14. Riesgos a controlar durante ejecución

### Riesgo 1 — Over-engineering del core

No convertir Sprint 3 en un framework abstracto sin casos reales.

**Mitigación**: legacy profile y A/B/C deben ser implementables temprano.

### Riesgo 2 — Under-engineering por copiar Pine uno a uno

No trasladar la lógica legacy como ifs rígidos sin separación de concerns.

**Mitigación**: state machine + sizing + exit policies + presets.

### Riesgo 3 — Tests demasiado tardíos

Si los tests aparecen al final, el sprint acumula deuda semántica.

**Mitigación**: cada fase deja tests propios antes de avanzar.

### Riesgo 4 — Fijar Sprint 3 a indicadores aún faltantes

No esperar a que Sprint 2 quede 100% completo para avanzar.

**Mitigación**: validar primero con Firestorm, SSL y WaveTrend; dejar gates de integración para Sprint 4.

---

## 15. Cierre documental del sprint

No generar `docs/risk_management_framework.md` como documento definitivo hasta
que el sprint esté implementado y validado.

El orden correcto es:

1. cerrar contratos,
2. implementar core,
3. correr tests,
4. validar límites y presets,
5. recién entonces sintetizar el framework final en ese documento.

Esto evita mezclar planificación con resultado ejecutado.