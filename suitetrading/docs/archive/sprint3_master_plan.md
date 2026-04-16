# Sprint 3 — Risk Management Engine: Master Plan

> **Objetivo**: diseñar e implementar el motor de gestión de riesgo de SuiteTrading
> como un framework determinista, extensible y reusable, capaz de cubrir tanto la
> lógica legacy extraída del Pine Script actual como los arquetipos modernos de
> gestión de riesgo definidos en el research de v2.

---

## 1. Contexto real de inicio

Sprint 3 no parte desde cero. Tampoco parte con todos sus prerequisitos cerrados.

### 1.1. Qué ya está resuelto

- Sprint 1 dejó operativa la capa de datos: descarga, storage, validación,
  resampling multi-timeframe y warmup.
- El paquete `suitetrading.data` ya ofrece contratos reutilizables para RM:
  `OHLCVResampler`, `ParquetStore`, `DataValidator`, `WarmupCalculator` y el
  mapa canónico de timeframes.
- Sprint 0 dejó documentada la lógica legacy de gestión de riesgo en
  `docs/risk_management_spec.md` y el flujo de evaluación en `docs/signal_flow.md`.
- Sprint 2 dejó un núcleo funcional del engine de indicadores: contrato base
  `Indicator`, `IndicatorState`, helpers MTF y combinador de señales.

### 1.2. Qué sigue incompleto y condiciona este sprint

- El módulo `suitetrading.risk` sigue casi vacío: el único artefacto real es el
  enum `PositionState` en `src/suitetrading/risk/state_machine.py`.
- `src/suitetrading/risk/position_sizing.py` y `src/suitetrading/risk/trailing.py`
  siguen como placeholders.
- No existe aún `portfolio.py`, `vbt_simulator.py` ni implementación de arquetipos.
- `tests/risk/` no tiene cobertura efectiva.
- Sprint 2 no cerró todavía el catálogo completo de indicadores ni el registry
  central. Eso no bloquea el diseño de RM, pero sí bloquea parte de la
  integración futura con backtesting y optimización.
- El módulo de backtesting sigue en scaffolding, por lo que la compatibilidad con
  VectorBT en Sprint 3 debe tratarse como diseño de integración y prototipo,
  no como integración final.

### 1.3. Veredicto de readiness

**Sprint 3 está en condición de GO con gates explícitas.**

Se puede avanzar ya en:

- contratos de riesgo,
- state machine,
- models/configuración,
- position sizing,
- trailing policies,
- arquetipos,
- portfolio-level risk,
- test suite de RM.

Debe quedar explícitamente diferido o acotado en este sprint:

- integración final con VectorBT PRO,
- cierre definitivo del registry de indicadores,
- validación Pine/Python del catálogo completo,
- integración end-to-end con backtesting masivo.

---

## 2. Propósito del sprint

La gestión de riesgo es el punto donde la suite deja de ser un catálogo de
señales y pasa a comportarse como un engine de trading real.

Este sprint debe transformar una especificación legacy de Pine Script y una
base de research amplia en un framework Python con estas propiedades:

1. **Determinista**: mismos inputs producen siempre mismos outputs.
2. **Trazable**: cada transición de estado y cada decisión de sizing se puede auditar.
3. **Extensible**: soporta múltiples arquetipos sin reescribir el core.
4. **Compatible**: reusable por el backtesting vectorizado y por el motor
   event-driven de validación/producción.
5. **Separable del alpha**: el risk engine consume señales ya combinadas; no
   vuelve a implementar lógica de indicadores.

---

## 3. Principios de diseño

### 3.1. Dos capas explícitas: Legacy y v2

Sprint 3 debe distinguir dos niveles que conviven pero no se confunden:

- **Legacy RM Profile**: replica la lógica actual documentada en
  `docs/risk_management_spec.md`.
- **V2 Extensible Framework**: generaliza esa lógica para soportar múltiples
  modelos de sizing, trailing y manejo de exposición.

La lógica legacy será un preset del framework, no el framework entero.

### 3.2. Reutilizar contratos ya cerrados

Sprint 3 no debe reintroducir infraestructura ya resuelta:

- señales: `Indicator.compute(...) -> pd.Series`
- quorum de señales: `combine_signals(...)`
- timeframe resolution: `resolve_timeframe(...)`, `align_to_base(...)`
- resampling: `OHLCVResampler`
- warmup: `WarmupCalculator`

### 3.3. Core de RM primero, integración después

La implementación debe construir primero el núcleo reusable del risk engine.
La compatibilidad con VectorBT/NautilusTrader se diseña desde el inicio, pero
la integración concreta no debe forzar el diseño prematuramente.

### 3.4. El orden de evaluación por barra es parte del contrato

La prioridad definida en `risk_management_spec.md` no es una nota incidental.
Es semántica ejecutable:

1. SL
2. TP1
3. Break-even
4. Trailing
5. Nueva entrada / pirámide

Si el código altera ese orden, cambia el comportamiento de la estrategia.

### 3.5. Riesgo por perfil, no por indicador

El risk engine no debe acoplarse a un set fijo de indicadores. Debe operar sobre:

- señales de entrada/salida,
- precios y OHLCV,
- metadata de timeframe,
- configuración de arquetipo,
- estado de posición,
- estado de portfolio.

---

## 4. Alcance del Sprint 3

### 4.1. Dentro del sprint

#### T3.1 — Position sizing

- Fixed fractional
- Kelly y fractional Kelly
- ATR-based sizing
- investigación y decisión sobre Optimal f
- matriz de uso por arquetipo

#### T3.2 — Position state machine

- modelo explícito de estados y eventos
- transiciones deterministas
- manejo de edge cases
- trazabilidad de razones de salida

#### T3.3 — Arquetipos de RM

- Arquetipo A: Trend Following
- Arquetipo B: Mean Reversion
- Arquetipo C: Mixed
- Arquetipo D: Pyramidal Scaling
- Arquetipo E: Grid/DCA

#### T3.4 — Trailing stops avanzados

- fixed
- ATR-based
- Chandelier Exit
- Parabolic SAR
- trailing por señal para compatibilidad legacy

#### T3.5 — Break-even y commission buffer

- break-even configurable
- buffer por costos
- reglas por arquetipo

#### T3.6 — Portfolio-level risk

- kill switch por drawdown
- portfolio heat
- gross/net exposure
- correlation-aware throttling
- Monte Carlo y robustez

#### T3.7 — Compatibilidad con VectorBT

- diseño de interfaz para simulación vectorizable
- prototipo funcional de adapter/bridge que ejecute arquetipos A, B y C
- tabla de vectorizabilidad por arquetipo
- documentación de limitaciones y fallback para arquetipos no vectorizables

El `RESEARCH_PLAN.md` exige un custom simulator funcional al menos para A, B y
C. Sprint 3 debe entregar ese prototipo ejecutable, aunque la integración
completa con VectorBT PRO sea responsabilidad de Sprint 4.

#### T3.8 — Compatibilidad con NautilusTrader (diseño de interfaces)

El `RESEARCH_PLAN.md` exige compatibilidad con VectorBT **y** NautilusTrader.
Sprint 3 no integra NautilusTrader, pero debe dejar definido qué significa
"compatible" a nivel técnico:

- modelo de estados: mapeo explícito de `PositionState` a estados NT
  (`INITIALIZED`, `SUBMITTED`, `ACCEPTED`, `PARTIALLY_FILLED`, `FILLED`,
  `CLOSED`)
- modelo de eventos: mapeo de `TransitionEvent` a eventos NT (`OrderFilled`,
  `PositionChanged`, `PositionClosed`)
- modelo de fills: el state machine debe poder recibir fills parciales y
  asincrónicos sin romper su invariante de determinismo
- modelo de órdenes: `orders` en `TransitionResult` debe ser traducible a
  `OrderRequest` (limit, market, stop) sin ambigüedad

El entregable es un documento de mapeo en `vbt_simulator.py` o sección dedicada
que Sprint 6 pueda consumir directamente.

### 4.2. Fuera de alcance

Para mantener Sprint 3 limpio, no entran como objetivo de cierre:

- engine completo de backtesting masivo,
- reporting de métricas finales de portfolio,
- optimización multiobjetivo,
- integración live con exchanges,
- integración real ni validación end-to-end con NautilusTrader (Sprint 6),
- anti-overfitting estadístico de Sprint 5.

---

## 5. Arquitectura objetivo del módulo risk

```text
src/suitetrading/risk/
├── __init__.py
├── position_sizing.py
├── state_machine.py
├── trailing.py
├── portfolio.py
├── vbt_simulator.py
└── archetypes/
    ├── __init__.py
    ├── base.py
    ├── trend_following.py
    ├── mean_reversion.py
    ├── mixed.py
    ├── pyramidal.py
    └── grid_dca.py
```

Se permiten archivos internos adicionales si simplifican el diseño sin romper
la superficie pública, pero los entregables canónicos del sprint siguen siendo
los definidos en `RESEARCH_PLAN.md`.

---

## 6. Readiness gates del sprint

### 6.1. Gates duros

Estos ítems deben existir antes de cerrar Sprint 3:

- suite de tests de `tests/risk/` con cobertura efectiva del state machine;
- implementación del core de `state_machine.py`;
- implementación de `position_sizing.py` y `trailing.py`;
- por lo menos un arquetipo legacy-compatible y los arquetipos A, B y C;
- `portfolio.py` con controles mínimos de drawdown y exposure;
- documentación técnica cerrada.

### 6.2. Gates blandos

Estos ítems no bloquean iniciar Sprint 3, pero sí limitan integración:

- registry central de indicadores todavía faltante;
- catálogo Sprint 2 incompleto;
- `indicator_validation_report.md` inexistente;
- `backtesting/` aún vacío;
- VectorBT PRO aún no integrado en el repo.

---

## 7. Deliverables del sprint

### Código

- `src/suitetrading/risk/position_sizing.py`
- `src/suitetrading/risk/state_machine.py`
- `src/suitetrading/risk/trailing.py`
- `src/suitetrading/risk/portfolio.py`
- `src/suitetrading/risk/vbt_simulator.py`
- `src/suitetrading/risk/archetypes/`

### Tests

- `tests/risk/test_position_sizing.py`
- `tests/risk/test_state_machine.py`
- `tests/risk/test_trailing.py`
- `tests/risk/test_portfolio.py`
- `tests/risk/test_archetypes_*.py`
- tests de integración mínima con señales ya implementadas

### Documentación

- `docs/sprint3_master_plan.md`
- `docs/sprint3_technical_spec.md`
- `docs/sprint3_implementation_guide.md`
- `docs/risk_management_framework.md` como artefacto de cierre del sprint,
  no como documento de planificación inicial

---

## 8. Riesgos principales

### Riesgo 1 — Diseñar RM acoplado al Pine actual

Si todo el sprint replica la lógica heredada sin abstraerla, la suite queda
atada a un único estilo de estrategia.

**Mitigación**: legacy profile como preset del framework.

### Riesgo 2 — Diseñar RM acoplado a VectorBT demasiado temprano

Si el diseño del core queda gobernado por restricciones prematuras de
vectorización, los arquetipos complejos se simplificarán artificialmente.

**Mitigación**: core Python determinista primero; adapter vectorizable después.

### Riesgo 3 — Falta de tests de transición

La lógica de riesgo tiene más riesgo de regresión que los indicadores.

**Mitigación**: tests por transición, por prioridad y por edge case desde la
primera fase del sprint.

### Riesgo 4 — Mezclar price-based trailing con signal-based exits

La lógica legacy usa SSL LOW como trailing de salida. Eso no encaja limpio si
el módulo `trailing.py` solo modela stops de precio.

**Mitigación**: modelar trailing como familia de exit policies, no solo como
un precio stop móvil.

### Riesgo 5 — Usar sizing agresivo sin control de portfolio heat

Kelly, Optimal f o pyramiding sin límites de exposición pueden destruir el
perfil de drawdown del sistema.

**Mitigación**: portfolio-level controls forman parte del sprint, no son opcionales.

---

## 9. Criterio de cierre

Sprint 3 se considera cerrado cuando:

1. El core de RM es ejecutable y testeado.
2. La state machine es determinista y trazable.
3. Los **cinco arquetipos** (A, B, C, D, E) están implementados, testeados y
   ejecutables, según exige `RESEARCH_PLAN.md`.
4. El módulo de portfolio risk aplica límites de drawdown, exposure y calor.
5. Existe un prototipo funcional de custom simulator VectorBT que ejecuta al
   menos los arquetipos A, B y C, según exige `RESEARCH_PLAN.md`.
6. La semántica de gaps, slippage en SL y fills parciales está definida
   explícitamente en la spec técnica, con decisiones documentadas sobre
   el comportamiento bar-based vs event-driven.
7. La compatibilidad con NautilusTrader está especificada como mapeo de
   estados, eventos, fills y órdenes, consumible por Sprint 6.
8. La documentación distingue sin ambigüedad paridad legacy vs framework v2.

> **Nota sobre cambio de alcance**: versiones anteriores de este documento
> aceptaban D/E solo como "contratos y límites" y VectorBT como "estrategia
> documentada". Esos criterios fueron endurecidos para restaurar la alineación
> con `RESEARCH_PLAN.md:420-422`.

---

## 10. Dependencias documentales

Sprint 3 se apoya directamente en:

- `docs/risk_management_spec.md`
- `docs/signal_flow.md`
- `docs/indicator_catalog.md`
- `docs/sprint1_completion_report.md`
- `docs/sprint2_master_plan.md`
- `docs/sprint2_technical_spec.md`
- `docs/sprint2_implementation_guide.md`
- `RISK_MANAGEMENT_RESEARCH.md`
- `RESEARCH_PLAN.md`

---

## 11. Trazabilidad con el plan maestro

| Task | Área principal en Sprint 3 |
|------|----------------------------|
| T3.1 | `position_sizing.py` + sección de sizing en technical spec |
| T3.2 | `state_machine.py` + sección de lifecycle contract |
| T3.3 | `archetypes/` + matriz de perfiles y presets |
| T3.4 | `trailing.py` + interfaz de exit policies |
| T3.5 | reglas de break-even + presets por arquetipo |
| T3.6 | `portfolio.py` + controles de capital y robustez |
| T3.7 | `vbt_simulator.py` + prototipo funcional para A/B/C |
| T3.8 | mapeo de compatibilidad NautilusTrader (estados, eventos, fills, órdenes) |

La implementación concreta de estas áreas queda operacionalizada en
`docs/sprint3_technical_spec.md` y `docs/sprint3_implementation_guide.md`.