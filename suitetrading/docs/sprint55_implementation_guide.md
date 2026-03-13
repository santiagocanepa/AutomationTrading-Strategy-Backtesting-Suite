# Sprint 5.5 — Hardening de Ejecución y Validación Empírica: Implementation Guide

> **Vigencia:** Guía de ejecución para Sprint 5.5.  
> **Leer primero:** `sprint55_master_plan.md` (scope) y `sprint55_technical_spec.md` (contratos).

---

## 1. Orden recomendado de trabajo

```
Fase 0: Prerequisites (data + verify baseline)
   │
   ▼
Fase 1: Search Space Audit (T5.5.1)
   │
   ├──────────────────────┐
   ▼                      ▼
Fase 2: RM Wiring    Fase 3: Backtest Semantics
  (T5.5.2)              (T5.5.3)
   │                      │
   └──────────┬───────────┘
              ▼
Fase 4: Risk Lab Campaigns (T5.5.4) ← depende de Fase 2
              │
              ▼
Fase 5: Validation & Gate (T5.5.5 + T5.5.6)
```

**Fases 2 y 3 pueden ejecutarse en paralelo** — no tienen dependencia entre sí.  
Fase 4 depende de Fase 2 porque necesita los RM wiring fixes para generar evidencia válida.

---

## 2. Fase 0 — Prerequisites

### 2.1 Descargar data ETH + SOL

```bash
cd suitetrading
.venv/bin/python scripts/download_data.py \
    --symbols ETHUSDT SOLUSDT \
    --timeframe 15m 1h 4h 1d
```

Post-download, validar integridad:

```bash
.venv/bin/python scripts/cross_validate_native.py \
    --symbols ETHUSDT SOLUSDT --days 30
```

Registrar resultado en `data/download_log.txt`.

### 2.2 Verificar baseline de tests

```bash
.venv/bin/python -m pytest -q
# Esperado: 609 passed
```

No empezar ninguna fase si hay tests rotos.

### 2.3 Verificar imports del módulo optimization

```bash
.venv/bin/python -c "from suitetrading.optimization import OptunaOptimizer, WalkForwardEngine, CSCVValidator"
```

---

## 3. Fase 1 — Search Space Audit (T5.5.1)

### 3.1 Auditar indicadores

Para cada entrada en `INDICATOR_REGISTRY` (12 total):

1. **Smoke test:** Ejecutar `indicator.compute(df_btc_1h)` y verificar output no-NaN
2. **Signal wiring:** Verificar que `StrategySignals` consume el output
3. **Tests existentes:** Verificar si existe `tests/indicators/test_*.py`
4. **Risk lab coverage:** Verificar si algún preset en `run_risk_lab.py` usa el indicador

**Resultado por indicador:**

| Indicador | compute() OK | Signals wired | Tests | Risk lab | → Maturity |
|-----------|-------------|---------------|-------|----------|-----------|
| firestorm | ✓ | ✓ | ✓ | ✓ (firestorm_trend) | `active` |
| ssl_channel | ✓ | ✓ | ✓ | ✓ (ssl_trend) | `active` |
| rsi | ✓ | ? | ✗ | ✗ | → `partial` o `active` según wiring |
| ... | | | | | |

### 3.2 Auditar parámetros de RM

Para cada parámetro de `RiskConfig` y sus sub-configs:

1. **Runner ejerce el parámetro:** Trazar el path desde config → FSM → efecto en equity
2. **Está en `DEFAULT_RISK_SEARCH_SPACE`:** Si no, evaluar si debería estar
3. **Risk lab lo varía:** Verificar si algún preset cambia el parámetro

### 3.3 Clasificar indicadores pendientes del catálogo

Verificar que Squeeze Momentum, MTF Conditions (5×SMA), Fibonacci MAI **no están** en `INDICATOR_REGISTRY` y clasificar como `experimental`.

### 3.4 Producir maturity matrix

Crear `docs/search_space_maturity_matrix.md` con formato tabla (ver technical spec §2.4).

### 3.5 Implementar filtro en optimizer

Agregar `filter_search_space()` (ver technical spec §2.3) para que el optimizer restrinja a `active` por defecto.

**Tests:**
- `test_filter_active_only` — Filtra correctamente
- `test_filter_active_plus_partial` — Incluye `partial` con opt-in

---

## 4. Fase 2 — RM Wiring (T5.5.2)

### 4.1 Time exit en risk lab

**Cambio mínimo — hacer primero:**

En `scripts/run_risk_lab.py`, agregar preset `time_exit` a la familia mean_reversion:

```python
"time_exit": {
    "time_exit": {"enabled": True, "max_bars": 20},
    # rest from base_safe
}
```

Verificar que `run_risk_lab.py` produce resultados diferentes con time_exit ON vs OFF.

### 4.2 Trailing policy verification

**Investigar antes de codificar:**

El runner FSM usa `trailing_signal: bool` que viene del signal combiner (ej: SSL LOW crossover). Las clases `ExitPolicy` en `trailing.py` ofrecen trailing ATR/Chandelier/SAR independiente de señales de indicador.

**Decisión:**
- Si el trailing basado en señales es suficiente para los archetypes actuales → documentar en maturity matrix como `active` (trailing via signal) y `partial` (trailing via policy)
- Si hay beneficio en usar policy objects → wire como opción alternativa

### 4.3 Portfolio controls (gate blando)

Si se decide implementar:

1. Agregar `enabled: bool = False` a `PortfolioLimits`
2. En `run_fsm_backtest()`: instanciar `PortfolioRiskManager` si `risk_config.portfolio.enabled`
3. Antes de entry: `approve_new_risk()` → block si not approved
4. Post-orders: `portfolio_mgr.update(equity=equity, open_positions=[...])`

**Si no se implementa:** documentar como `partial` en maturity matrix y como gap remanente en hardening report.

### 4.4 Escribir integration tests

7 tests sobre el runner real (ver technical spec §3.3):

```
tests/backtesting/test_rm_integration.py
├── test_fsm_time_exit_closes_after_max_bars
├── test_fsm_time_exit_disabled_by_default
├── test_trailing_signal_triggers_exit_after_tp1
├── test_pyramid_respects_block_bars
├── test_break_even_buffer_covers_commission
├── test_portfolio_limits_block_entry (si wired)
└── test_fsm_determinism_same_input_same_output
```

Cada test debe:
- Construir `BacktestDataset` con datos sintéticos (controlados)
- Construir `StrategySignals` con señales predefinidas
- Ejecutar `run_fsm_backtest()` directamente
- Assertar sobre `BacktestResult.trades` y `equity_curve`

---

## 5. Fase 3 — Backtest Semantics (T5.5.3)

### 5.1 Documentar exit priorities

Crear `docs/backtest_execution_semantics.md` con:

1. Exit priority table (ver technical spec §4.1)
2. Fee model (§4.2)
3. Intrabar fill assumptions (§4.3)
4. Pyramiding semantics (§4.4)
5. FSM vs Simple coherence table (§4.5)
6. Limitaciones conocidas (slippage no implementado, no gap handling)

### 5.2 Crear regression fixtures

Crear directorio `tests/fixtures/backtest_regressions/` con ≥3 JSONs:

1. **`basic_long_sl.json`**
   - Setup: 20 barras, entry signal en bar 2, SL hit en bar 8
   - Expected: 1 trade, exit_reason="stop_loss", PnL negativo

2. **`long_with_tp1_trailing.json`**
   - Setup: 50 barras, entry → price rises → TP1 → BE → trailing exit
   - Expected: 2 "trades" (partial + final), exit_reasons incluyen "take_profit_1" y "trailing_exit"

3. **`pyramid_3_adds.json`**
   - Setup: 80 barras, entry → 3 pyramid adds → trailing exit
   - Expected: 4 entries (initial + 3 adds), Fibonacci weighted sizes, 1 exit

### 5.3 Crear test runner para fixtures

```python
# tests/backtesting/test_regression_fixtures.py

import json
from pathlib import Path
import pytest

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "backtest_regressions"

@pytest.fixture(params=sorted(FIXTURE_DIR.glob("*.json")))
def fixture_data(request):
    return json.loads(request.param.read_text())

def test_regression(fixture_data):
    """Run backtest with fixture input and verify expected output."""
    # build dataset, signals, risk_config from fixture_data
    # run_fsm_backtest(...)
    # assert result matches fixture_data["expected"]
```

### 5.4 Comparación FSM vs Simple

Para archetypes sin pyramid ni partial TP (mean_reversion arch con pyramid.enabled=False, partial_tp.enabled=False):

```python
def test_fsm_simple_coherence_no_pyramid():
    """FSM and Simple produce identical results when no pyramid/TP1."""
    result_fsm = run_fsm_backtest(dataset=ds, signals=sigs, risk_config=cfg_no_pyramid)
    result_simple = run_simple_backtest(dataset=ds, signals=sigs, risk_config=cfg_no_pyramid)
    assert result_fsm.trades == result_simple.trades
    np.testing.assert_allclose(result_fsm.equity_curve, result_simple.equity_curve, rtol=1e-6)
```

---

## 6. Fase 4 — Risk Lab Campaigns (T5.5.4)

### 6.1 Prerequisitos

- [ ] Data ETH + SOL descargada y validada (Fase 0)
- [ ] RM wiring fixes aplicados (Fase 2) — al menos time_exit en presets
- [ ] Tests green después de cambios en Fase 2

### 6.2 Expandir `run_risk_lab.py`

Modificar `scripts/run_risk_lab.py` para soportar:

1. **Multi-symbol:** Parametrizar `--symbols` (no hardcoded BTC)
2. **Multi-TF:** Parametrizar `--timeframes` (default: 15m, 1h, 4h, 1d)
3. **Time exit preset:** Agregar a mean reversion family
4. **Output path:** `--output-dir` para separar campañas

```bash
.venv/bin/python scripts/run_risk_lab.py \
    --symbols BTCUSDT ETHUSDT SOLUSDT \
    --timeframes 15m 1h 4h 1d \
    --output-dir artifacts/risk_lab_v2/
```

### 6.3 Ejecutar campañas

Total: 216 combinaciones (3 symbols × 4 TFs × 3 strategies × 6 risk presets).

Si es lento, usar `ParallelExecutor` o batch por símbolo:

```bash
# Batch sequential por símbolo
for sym in BTCUSDT ETHUSDT SOLUSDT; do
    .venv/bin/python scripts/run_risk_lab.py --symbols $sym \
        --timeframes 15m 1h 4h 1d \
        --output-dir artifacts/risk_lab_v2/$sym/
done
```

### 6.4 Analizar y producir report

Crear `docs/risk_lab_report.md` con:

1. **Resumen ejecutivo:** Top 5 combinaciones por Sharpe risk-adjusted
2. **Trend vs mean reversion:** Tabla comparativa
3. **RM impact analysis:** ¿Qué controles (pyramid, TP1, BE, time_exit) cambian Sharpe/DD?
4. **Cross-symbol:** ¿Resultados estables o artefactos de BTC?
5. **Cross-TF:** ¿TF dominante o estable?
6. **Heatmaps/scatter:** Incluir paths a dashboards HTML

---

## 7. Fase 5 — Validation & Gate (T5.5.5 + T5.5.6)

### 7.1 TV spot-check (T5.5.5)

- Comparar Firestorm signals en BTC 1h contra TradingView (~100 barras)
- Comparar SSL Channel flip points (parcialmente hecho; validar con data reciente)
- Guardar evidencia en `artifacts/indicator_validation/`

### 7.2 Seleccionar shortlist (T5.5.6)

Del risk lab report, filtrar candidatas que cumplan:

1. OOS Sharpe ≥ 0.5
2. CSCV PBO < 0.50
3. DSR > 0
4. Max DD < 25%
5. ≥30 trades en OOS
6. Patrón mantenido en ≥2 símbolos

### 7.3 Freeze search space

- Copiar `search_space_maturity_matrix.md` a `search_space_maturity_matrix_v1.md`
- Calcular SHA-256 del archivo
- Registrar en `sprint55_hardening_report.md`

### 7.4 Producir hardening report

Crear `docs/sprint55_hardening_report.md` con:

1. **Shortlist:** Top 10-20 candidatas con params, métricas OOS, CSCV PBO
2. **Search space frozen:** Versión + hash
3. **Maturity summary:** Cuántos params `active/partial/experimental`
4. **Gaps remanentes:** Qué no se validó (portfolio controls, slippage, gap handling)
5. **Recomendaciones para Sprint 6:** Qué tests replicar en NautilusTrader

---

## 8. Checklist de implementación

### Fase 0 — Prerequisites
- [ ] Data ETH descargada (15m, 1h, 4h, 1d)
- [ ] Data SOL descargada (15m, 1h, 4h, 1d)
- [ ] `cross_validate_native.py` green para ETH+SOL
- [ ] 609 tests passing
- [ ] Optimization module imports OK

### Fase 1 — Search Space Audit
- [ ] 12 indicadores smoke-tested con datos reales
- [ ] 6 standard indicators con tests de humo
- [ ] Parámetros RM auditados contra runner
- [ ] Indicadores no implementados clasificados `experimental`
- [ ] `search_space_maturity_matrix.md` completado
- [ ] `filter_search_space()` implementado con tests

### Fase 2 — RM Wiring
- [ ] Time exit preset agregado a risk lab (mean_reversion)
- [ ] Trailing policy decisión documentada
- [ ] Portfolio controls decisión tomada (wire o documentar gap)
- [ ] ≥5 integration tests escritos y green
- [ ] Suite completa sigue green

### Fase 3 — Backtest Semantics
- [ ] `backtest_execution_semantics.md` escrito
- [ ] ≥3 regression fixtures creados
- [ ] Test runner para fixtures implementado
- [ ] FSM vs Simple coherence test green

### Fase 4 — Risk Lab
- [ ] `run_risk_lab.py` soporta multi-symbol y multi-TF
- [ ] 216 combinaciones ejecutadas
- [ ] `risk_lab_report.md` con análisis comparativo
- [ ] Dashboards HTML generados

### Fase 5 — Validation & Gate
- [ ] TV spot-check de Firestorm + SSL Channel
- [ ] Shortlist top 10-20 con criterios cumplidos
- [ ] Search space frozen con hash
- [ ] `sprint55_hardening_report.md` completado

---

## 9. Cierre documental del sprint

Orden de producción de deliverables:

```
1. docs/search_space_maturity_matrix.md     ← Fase 1
2. docs/backtest_execution_semantics.md     ← Fase 3
3. docs/risk_lab_report.md                  ← Fase 4
4. docs/sprint55_hardening_report.md        ← Fase 5 (cierre)
```

Los docs 1 y 2 pueden escribirse en paralelo.  
Doc 3 depende de Fase 2 (RM wiring) + Fase 4 (campañas).  
Doc 4 se escribe al final, consolidando evidencia de todas las fases.

---

## 10. Riesgos a controlar durante ejecución

| # | Riesgo | Señal de alerta | Acción |
|---|--------|----------------|--------|
| 1 | Descarga ETH/SOL falla | Gaps en cross-validation | Quarantine y re-download parcial |
| 2 | RM wiring rompe tests existentes | Pytest failures post Fase 2 | Feature flag; revert si necesario |
| 3 | Risk lab campaigns > 1h | Wall time per batch | Reducir a 2 TFs (1h, 4h); parallelizar |
| 4 | Regression fixtures divergen más de lo esperado | FSM vs Simple net PnL > 1% | Documentar divergencias legítimas vs bugs |
| 5 | Shortlist vacía (ninguna candidata cumple criterios) | <10 candidatas post-filtro | Relajar criterios o expandir search space a `partial` |
