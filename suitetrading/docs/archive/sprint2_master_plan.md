# Sprint 2 — Indicator Engine: Master Plan

> **Objetivo**: cerrar el motor de indicadores de SuiteTrading sobre la capa de
> datos ya validada en Sprint 1. Este sprint debe dejar el catálogo completo de
> indicadores de Pine disponible en Python, con contratos estables, soporte
> multi-timeframe consistente y validación explícita de paridad.

---

## 1. Contexto: punto de partida real

Sprint 1 ya dejó resuelta la base operacional que Sprint 2 necesita:

- `data/raw/` reparado y validado contra exchange nativo
- `OHLCVResampler` y `mtf.py` unificados
- `signal_combiner.py` disponible con lógica `Excluyente / Opcional / Desactivado`
- entorno y tests corriendo de forma consistente en `.venv`

Además, el repositorio ya trae una parte del engine adelantada desde Sprint 0:

- `Indicator`, `IndicatorConfig`, `IndicatorState` en `indicators/base.py`
- `Firestorm`, `FirestormTM`
- `SSLChannel`, `SSLChannelLow`
- `WaveTrendReversal`, `WaveTrendDivergence`
- tests de indicadores y MTF ya verdes

**Conclusión**: Sprint 2 no parte desde cero. Parte desde un núcleo custom ya
implementado y probado, pero todavía incompleto frente al catálogo Pine.

---

## 2. Alcance del Sprint 2

### 2.1. Lo que ya existe

| Área | Estado actual |
|------|---------------|
| Contrato base de indicadores | Implementado |
| Helpers MTF | Implementados |
| Signal combiner base | Implementado |
| Firestorm / Firestorm TM | Implementados |
| SSL Channel / SSL LOW | Implementados |
| WaveTrend Reversal / Divergence | Implementados |

### 2.2. Lo que falta para cerrar Sprint 2

| Grupo | Faltantes |
|-------|-----------|
| Estándar | MACD Signal, RSI Simple, RSI + Bollinger, EMA 9/200, MTF Conditions, VWAP |
| Custom | ASH, Squeeze Momentum, Fibonacci MAI |
| Infraestructura | registry/export surface, harness de validación, reporte de paridad |
| Testing | tests unitarios de wrappers estándar, tests de integración del catálogo completo |

### 2.3. Definición de terminado

Sprint 2 se considera cerrado cuando:

1. Los 15 indicadores del catálogo Pine estén disponibles desde Python.
2. Todos respeten el contrato `Indicator.compute(df, **params) -> pd.Series`.
3. La capa MTF use únicamente la infraestructura de `data.resampler` + `indicators.mtf`.
4. Exista una superficie pública clara para importar indicadores.
5. La validación Pine/Python deje un reporte explícito en `docs/indicator_validation_report.md`.

---

## 3. Decisiones de diseño

### 3.1. Mantener separación entre `standard/` y `custom/`

- `standard/`: wrappers delgados sobre TA-Lib y/o pandas-ta.
- `custom/`: indicadores que requieren lógica propia, loops o kernels Numba.

Esto evita mezclar problemas de fórmula propietaria con wrappers triviales.

### 3.2. Reutilizar el contrato actual, no rediseñarlo

Los indicadores custom actuales ya exponen un patrón consistente:

- validan OHLCV con `_validate_ohlcv()`
- aceptan `direction="long" | "short"` cuando aplica
- usan `_hold_bars()` cuando el Pine lo requiere

Sprint 2 debe **extender** ese patrón, no reemplazarlo.

### 3.3. MTF como infraestructura compartida, no como lógica duplicada

Toda resolución de temporalidades y resampling debe pasar por:

- `suitetrading.data.timeframes`
- `suitetrading.data.resampler.OHLCVResampler`
- `suitetrading.indicators.mtf`

Ningún indicador nuevo debe volver a implementar `.resample().agg()` localmente.

### 3.4. Paridad contra Pine como entrega explícita

La implementación no se considerará suficiente solo porque los tests sintéticos
pasen. El sprint exige un mecanismo de validación trazable contra el catálogo y
contra snapshots reproducibles del comportamiento Pine.

### 3.5. No arrastrar bugs accidentales del Pine al contrato Python

Ejemplo ya detectado: el Pine cuenta doble un voto de SSL en el sell optional
branch. Sprint 2 documenta esos casos, pero la implementación Python debe
preservar la intención del sistema, no los defectos accidentales de la UI.

---

## 4. Workstreams

### T2.1 — Consolidar la superficie pública del engine

- normalizar exports en `indicators/__init__.py`, `custom/__init__.py`, `standard/__init__.py`
- agregar un registry central `indicator_key -> class`
- documentar claves canónicas reutilizables por optimización y backtesting

### T2.2 — Implementar wrappers estándar

- `MACDSignal`
- `RSISimple`
- `RSIBollingerBands`
- `EMAFilter`
- `MTFConditions`
- `VWAPIndicator`

### T2.3 — Completar custom indicators faltantes

- `AbsoluteStrengthHistogram`
- `SqueezeMomentum`
- `FibonacciMAI`

### T2.4 — Endurecer validación y testing

- tests unitarios por indicador
- tests de integración del catálogo
- tests MTF para indicadores que resuelven TF superior
- snapshots de paridad contra referencias externas / Pine exportado

### T2.5 — Generar reporte de validación

- script reproducible de validación
- reporte Markdown con metodología, casos y discrepancias

---

## 5. Entregables

### Código

- `src/suitetrading/indicators/standard/` con wrappers funcionales
- `src/suitetrading/indicators/custom/` completado con los 3 faltantes
- `src/suitetrading/indicators/registry.py`
- mejoras puntuales en `signal_combiner.py` y `mtf.py` solo si el sprint lo requiere

### Tests

- `tests/indicators/` ampliado para cubrir el catálogo completo
- integración de señales estándar + custom + MTF

### Documentación

- `docs/sprint2_master_plan.md`
- `docs/sprint2_technical_spec.md`
- `docs/sprint2_implementation_guide.md`
- `docs/indicator_validation_report.md`

---

## 6. Fuera de alcance

Para mantener este sprint limpio, **no** entra aquí:

- position sizing
- state machine de riesgo
- trailing/partial TP live
- engine VectorBT
- optimización multiobjetivo

Todo eso empieza en Sprint 3 y Sprint 4 y debe consumir el engine de
indicadores ya estabilizado.

---

## 7. Criterios de éxito

| Criterio | Meta |
|---------|------|
| Cobertura del catálogo Pine | 15/15 indicadores |
| Tests del repositorio | Verdes al final del sprint |
| Validación Pine/Python | >99% de coincidencia en los casos seleccionados |
| Reutilización MTF | 100% sobre la infraestructura común |
| Surface pública | Importación consistente y registry documentado |

---

## 8. Dependencias de referencia

Sprint 2 se apoya directamente en:

- `docs/indicator_catalog.md` — fórmulas y parámetros canónicos
- `docs/indicator_availability_matrix.md` — estrategia de implementación por indicador
- `docs/signal_flow.md` — cómo combinan las señales en la estrategia
- `docs/sprint1_completion_report.md` — baseline operativo ya validado
- `docs/sprint2_go_no_go_checklist.md` — gate de entrada al sprint