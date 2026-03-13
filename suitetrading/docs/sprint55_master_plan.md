# Sprint 5.5 — Hardening de Ejecución y Validación Empírica: Master Plan

> **Duración estimada:** 2 semanas  
> **Agente responsable:** Backtesting / Risk Engineer  
> **Prerrequisito:** Sprint 5 cerrada (2026-03-12)

---

## 1. Contexto real de inicio

### 1.1 Qué ya está resuelto

| Sprint | Entrega | Estado |
|--------|---------|--------|
| 0 | Pine Script Audit → catálogo de 15 indicadores | ✅ Cerrada |
| 1 | Data infrastructure (Parquet/ZSTD, resampler, cross-validation) | ✅ Cerrada (256 tests) |
| 2 | Indicator Engine — 12 indicadores registrados (6 custom + 6 TA-Lib) | ✅ Cerrada |
| 3 | Risk Management — FSM, sizing, trailing, archetypes, portfolio controls | ✅ Cerrada |
| 4 | Backtesting Core — dual runner (FSM + simple), metrics, checkpointing | ✅ Cerrada (63.7 bt/sec) |
| 5 | Optimization & Anti-Overfitting — Optuna, WFO, CSCV, DSR, parallelization | ✅ Cerrada (100 tests, 609 total) |

### 1.2 Gaps identificados post-Sprint 5

El módulo de optimización está completo y testeado, pero su **superficie de entrada** tiene huecos que reducen la calidad de los candidatos que produce:

| Gap | Módulo afectado | Impacto práctico |
|-----|-----------------|------------------|
| **Search space sin clasificar** | `optimization/_internal/objective.py` | El optimizer puede explorar dimensiones que el runner no ejerce end-to-end, generando falsos positivos |
| **RM wiring incompleto** | `backtesting/_internal/runners.py` | `PortfolioRiskManager`, `TrailingStopPolicy` y `TimeExitConfig` existen en `risk/` pero no están integrados en el runner FSM |
| **Semántica de ejecución no documentada** | `backtesting/_internal/runners.py` | Prioridades de exit, fees, slippage, intrabar assumptions no tienen spec formal; riesgo de drift silencioso |
| **Risk lab single-symbol** | `scripts/run_risk_lab.py` | Evidencia empírica limitada a BTC; sin campañas multi-activo ni multi-régimen |
| **Standard indicators sin tests** | `indicators/standard/indicators.py` | 6 wrappers TA-Lib sin tests unitarios dedicados; clasificación de madurez insuficiente |
| **Data disponible solo BTC** | `data/raw/binance/` | ETH y SOL necesitan descarga como prerequisito para campañas multi-activo |

### 1.3 Veredicto de readiness

Sprint 5 entrega un pipeline de optimización funcional (Optuna → WFO → CSCV/DSR → finalistas).  
Sin embargo, **invertir esfuerzo en NautilusTrader (Sprint 6) sin antes validar la calidad del search space y la semántica de ejecución es prematuro**.  
Sprint 5.5 cierra estos gaps como gate obligatorio antes de portar candidatas a NautilusTrader.

---

## 2. Propósito del sprint

Sprint 5.5 **no crea módulos nuevos**. Su objetivo es:

1. **Clasificar** el espacio de búsqueda por madurez real de integración
2. **Cerrar** los gaps end-to-end entre el framework de RM y el runner FSM
3. **Documentar** la semántica de ejecución con regresiones reproducibles
4. **Validar** empíricamente con campañas multi-activo y multi-régimen
5. **Definir** un shortlist defendible antes de invertir en NautilusTrader

---

## 3. Alcance — 6 tasks

### T5.5.1 — Mapa de madurez del search space

Auditar cada indicador y parámetro de RM en `fsm`, `simple`, optimizer y risk lab.  
Etiquetar cada dimensión como `active`, `partial` o `experimental`.  
Restringir el optimizer principal a parámetros `active` por defecto.

**Input:** `INDICATOR_REGISTRY` (12 entries), `DEFAULT_RISK_SEARCH_SPACE`, `ParameterGridBuilder`, `run_risk_lab.py`  
**Output:** `docs/search_space_maturity_matrix.md`

### T5.5.2 — Completar wiring de RM crítico

Integrar end-to-end los controles que hoy existen en el framework pero no en el runner:
- `PortfolioRiskManager` → `run_fsm_backtest()` 
- `TrailingStopPolicy` subclases → verificar que el runner las consuma
- `TimeExitConfig` → agregar a presets del risk lab

Agregar 5–8 tests de integración sobre el runner real (no mocks).

**Input:** `risk/portfolio.py`, `risk/trailing.py`, `risk/contracts.py` (`TimeExitConfig`)  
**Output:** Code changes en `runners.py` + integration tests en `tests/backtesting/`

### T5.5.3 — Hardening de semántica de backtest

Documentar:
- Prioridades de exit: SL > TP > trailing > time_exit > signal exit
- Fee model (`commission_pct`), slippage (`slippage_pct`), intrabar assumptions (OHLCV-only)
- Pyramiding semantics (Fibonacci weights, `block_bars`, `threshold_factor`)
- Coherencia FSM vs simple: qué métricas deben coincidir y cuáles divergen legítimamente

Crear 3-5 regression fixtures con OHLCV input + expected trades/metrics.

**Output:** `docs/backtest_execution_semantics.md` + `tests/fixtures/` regression JSONs

### T5.5.4 — Expandir el risk lab

- **Prerequisito:** descargar ETH + SOL en todos los TFs operativos
- Ejecutar campañas: 3 símbolos × 4 TFs (15m, 1h, 4h, 1d) × 3 estrategias × 6+ risk presets
- Comparar familias trend vs mean reversion
- Identificar qué controles de RM realmente cambian las métricas

**Output:** `docs/risk_lab_report.md` con evidencia empírica

### T5.5.5 — Validación de referencia

- Mantener TradingView como spot-check visual para 2-3 indicadores clave (Firestorm, SSL Channel)
- **No** usar Puppeteer masivo como gate
- Priorizar consistencia interna: signals → FSM → metrics reproducible

### T5.5.6 — Gate previo a NautilusTrader

- Seleccionar top 10-20 candidatas con evidencia OOS y risk lab
- Documentar qué queda listo para NautilusTrader y qué no
- Congelar la versión del search space usada para validación externa

**Output:** `docs/sprint55_hardening_report.md`

---

## 4. Dependencias

| Dependencia | Tipo | Acción requerida |
|-------------|------|-----------------|
| Data ETH+SOL multi-TF | Data | `scripts/download_data.py --symbols ETHUSDT SOLUSDT --timeframe 15m 1h 4h 1d` |
| Módulo optimization funcional | Sprint 5 | Ya disponible (OptunaOptimizer, WFO, CSCV, DSR) |
| `run_risk_lab.py` operativo | Sprint 4-5 | Ya disponible, solo sobre BTC |
| `PortfolioRiskManager` | Sprint 3 | Existe en `risk/portfolio.py`, no wired en runner |
| `TrailingStopPolicy` subclases | Sprint 3 | Existen en `risk/trailing.py`, runner usa señales directas |
| Tests 609 green | Sprint 5 | Verificar antes de empezar; no romper base existente |

---

## 5. Riesgos principales

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|--------|-------|---------|------------|
| R1 | Wiring de `PortfolioRiskManager` en FSM runner es intrusivo y rompe tests existentes | Media | Alto | Feature flag: `portfolio_controls_enabled` en `RiskConfig`, off por defecto; tests nuevos separados |
| R2 | Standard indicators (TA-Lib wrappers) tienen bugs no detectados por falta de tests | Baja | Medio | T5.5.1 incluye smoke tests sobre cada wrapper antes de clasificar como `active` |
| R3 | Risk lab campaigns multi-symbol son lentas (>1h por combinación) | Alta | Medio | Excluir 1m del risk lab; usar 4 TFs (15m–1d); paralelizar con `ParallelExecutor` |
| R4 | Regression fixtures FSM vs simple divergen más de lo esperado | Baja | Medio | Documentar divergencias legítimas (pyramid, partial TP); sólo exigir coherencia en métricas base |
| R5 | Descarga ETH+SOL falla o data tiene gaps | Media | Alto | Usar `cross_validate_native.py` post-descarga; quarantine automático |

---

## 6. Readiness gates

### 6.1 Gates duros (bloquean cierre)

- [ ] `search_space_maturity_matrix.md` completado; cada parámetro clasificado `active/partial/experimental`
- [ ] Optimizer principal restringe a `active` params por defecto
- [ ] Gaps críticos de RM tienen ≥5 integration tests end-to-end sobre runner real
- [ ] `backtest_execution_semantics.md` documenta prioridades de exit, fees, slippage, pyramid
- [ ] ≥3 regression fixtures ejecutados y green
- [ ] Shortlist top 10-20 candidatas con evidencia OOS documentada

### 6.2 Gates blandos (opcionales, no bloquean)

- [ ] Risk lab campaigns completas sobre 3 símbolos × 4 TFs
- [ ] TV spot-check visual de Firestorm + SSL Channel
- [ ] PortfolioRiskManager wired end-to-end en runner (puede quedar como feature flag)
- [ ] Standard indicators con test unitario dedicado cada uno

---

## 7. Deliverables

| Entregable | Tipo | Descripción |
|------------|------|-------------|
| `docs/search_space_maturity_matrix.md` | Documento | Clasificación `active/partial/experimental` de cada dimensión |
| `docs/backtest_execution_semantics.md` | Documento | Reglas de ejecución del runner actual (exit priorities, fees, slippage, intrabar) |
| `docs/risk_lab_report.md` | Documento | Evidencia empírica multi-activo/multi-régimen |
| `docs/sprint55_hardening_report.md` | Documento | Cierre del gate previo a NautilusTrader + shortlist candidatas |
| Integration tests RM | Código | ≥5 tests en `tests/backtesting/` sobre runner FSM con RM controls |
| Regression fixtures | Código | ≥3 JSONs en `tests/fixtures/backtest_regressions/` con OHLCV + expected output |

---

## 8. Criterio de cierre

1. Cada parámetro optimizable está clasificado por madurez real
2. El optimizer principal usa por defecto sólo parámetros `active`
3. Los gaps críticos de RM tienen tests de integración end-to-end
4. Existe un shortlist de candidatas justificadas para portar a NautilusTrader

---

## 9. Trazabilidad con el plan maestro

| Task | Área | Deliverable |
|------|------|-------------|
| T5.5.1 | Indicadores + Optimization | `search_space_maturity_matrix.md` |
| T5.5.2 | Risk + Backtesting | Integration tests + code changes |
| T5.5.3 | Backtesting | `backtest_execution_semantics.md` + fixtures |
| T5.5.4 | Risk + Data | `risk_lab_report.md` |
| T5.5.5 | Indicadores | TV spot-check (no artifact formal) |
| T5.5.6 | Meta | `sprint55_hardening_report.md` |
