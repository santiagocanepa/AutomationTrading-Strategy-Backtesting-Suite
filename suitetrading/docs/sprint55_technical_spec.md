# Sprint 5.5 — Hardening de Ejecución y Validación Empírica: Technical Specification

> **Vigencia:** Este documento define los contratos técnicos para Sprint 5.5.  
> **Prerequisito:** Sprint 5 cerrada — módulo `optimization/` completo y testeado.

---

## 1. Baseline actual

Sprint 5.5 no crea módulos nuevos. Opera sobre contratos y módulos ya existentes.

### 1.1 Contratos que Sprint 5.5 consume

| Contrato | Módulo | Rol en Sprint 5.5 |
|----------|--------|--------------------|
| `BacktestEngine.run()` | `backtesting/engine.py` | Target de T5.5.3 (semántica), invocado por risk lab (T5.5.4) |
| `run_fsm_backtest()` | `backtesting/_internal/runners.py` | Target principal de T5.5.2 (RM wiring) y T5.5.3 (regression fixtures) |
| `run_simple_backtest()` | `backtesting/_internal/runners.py` | Comparación coherencia con FSM en T5.5.3 |
| `PositionStateMachine.evaluate_bar()` | `risk/state_machine.py` | FSM con 6 prioridades de exit; T5.5.2 verifica cobertura completa |
| `PortfolioRiskManager` | `risk/portfolio.py` | Gap: existe pero `run_fsm_backtest()` pasa `portfolio_state=None` |
| `ExitPolicy` subclases | `risk/trailing.py` | Gap: runner usa `trailing_signal` bool, no invoca policy objects |
| `TimeExitConfig` | `risk/contracts.py` | FSM sí evalúa `_should_time_exit()`; gap: risk lab presets no lo incluyen |
| `RiskConfig` | `risk/contracts.py` | Pydantic model con 9 sub-configs; fuente de verdad para parámetros RM |
| `INDICATOR_REGISTRY` | `indicators/registry.py` | 12 entries; input para clasificación maturity (T5.5.1) |
| `DEFAULT_RISK_SEARCH_SPACE` | `optimization/_internal/objective.py` | Solo `stop__atr_multiple` + `sizing__risk_pct`; T5.5.1 debe evaluar completitud |
| `BacktestObjective` | `optimization/_internal/objective.py` | Callable Optuna; T5.5.1 evalúa qué dimensiones explora realmente |
| `ParameterGridBuilder` | `backtesting/grid.py` | Builder de search space; target de filtro `active`-only |
| `OptunaOptimizer.optimize()` | `optimization/optuna_optimizer.py` | Consumer de BacktestObjective; recibe restricción de espacio |

### 1.2 Estado de la FSM

La `PositionStateMachine` evalúa cada barra con esta prioridad fija:

```
1. Stop-loss       → CLOSED (TransitionEvent.STOP_LOSS_HIT)
2. Partial TP1     → PARTIALLY_CLOSED (TAKE_PROFIT_1_HIT)
3. Break-even      → OPEN_BREAKEVEN o CLOSED (BREAK_EVEN_HIT)
4. Trailing exit   → CLOSED (TRAILING_EXIT_HIT)
5. Time exit       → CLOSED (TIME_EXIT_HIT)
6. Entry / Pyramid → OPEN_INITIAL / OPEN_PYRAMIDED (ENTRY_FILLED / PYRAMID_ADD_FILLED)
```

**Estados:** `FLAT → OPEN_INITIAL → OPEN_BREAKEVEN → OPEN_TRAILING → OPEN_PYRAMIDED → PARTIALLY_CLOSED → CLOSED`

### 1.3 Throughput baseline

- Single-thread: **63.7 bt/sec** (BTCUSDT 1h, ~2160 bars)
- `ParallelExecutor` con 14 cores: target **≥890 bt/sec**
- Risk lab campaigns (T5.5.4): ~216 combinaciones (3×4×3×6) → ~3.4 sec teórico con parallelización

---

## 2. T5.5.1 — Search Space Maturity Specification

### 2.1 Taxonomía

| Nivel | Definición | Consecuencia |
|-------|-----------|--------------|
| **`active`** | Implementado, wired end-to-end en runner, testeado, incluido en optimizer por defecto | Entra en `DEFAULT_RISK_SEARCH_SPACE` y en grid builder |
| **`partial`** | Implementado en framework pero gap en runner, tests, o risk lab | Excluido del optimizer por defecto; disponible con opt-in explícito |
| **`experimental`** | Stub, no integrado, o indicador del catálogo Pine no implementado | Nunca entra en optimizer; requiere Sprint dedicada |

### 2.2 Dimensiones a auditar

#### A. Indicadores (12 registrados)

Para cada indicador en `INDICATOR_REGISTRY`:

| Criterio de auditoría | Qué verificar |
|-----------------------|---------------|
| `compute()` produce output correcto | Smoke test con datos reales (BTC 1h, ≥500 bars) |
| Señales llegan al runner | `StrategySignals` consume el output; runner reacciona |
| Tests unitarios existen | `tests/indicators/test_*.py` cubre el indicador |
| Risk lab lo ejerce | Al menos 1 preset en `run_risk_lab.py` usa el indicador |

**Estado conocido:**
- 6 custom (Firestorm, FirestormTM, SSL, SSL Low, WaveTrend Rev, WaveTrend Div): testeados ✓
- 6 standard (RSI, EMA, MACD, ATR, VWAP, BollingerBands): implementados, sin tests dedicados

#### B. Parámetros de RM

El `DEFAULT_RISK_SEARCH_SPACE` actual solo incluye 2 dimensiones:

```python
DEFAULT_RISK_SEARCH_SPACE = {
    "stop__atr_multiple": {"type": "float", "min": 1.0, "max": 5.0, "step": 0.5},
    "sizing__risk_pct":   {"type": "float", "min": 0.5, "max": 3.0, "step": 0.25},
}
```

Sin embargo, `RiskConfig` tiene 9 sub-configs con ~30 parámetros individuales. La auditoría debe evaluar cada uno:

| Sub-config | Parámetros clave | Estado esperado |
|------------|-----------------|-----------------|
| `SizingConfig` | `risk_pct`, `model`, `max_leverage` | `active` (risk_pct ya en space) |
| `StopConfig` | `atr_multiple`, `fixed_pct` | `active` (atr_multiple ya en space) |
| `TrailingConfig` | `model`, `atr_multiple`, `chandelier_period` | `partial` (FSM usa `trailing_signal`, no policy objects) |
| `PartialTPConfig` | `enabled`, `close_pct`, `trigger`, `r_multiple` | `active` (FSM ejerce TP1 end-to-end) |
| `BreakEvenConfig` | `enabled`, `buffer`, `activation` | `active` (FSM ejerce BE end-to-end) |
| `PyramidConfig` | `enabled`, `max_adds`, `block_bars`, `threshold_factor` | `active` (FSM ejerce pyramiding end-to-end) |
| `TimeExitConfig` | `enabled`, `max_bars` | `partial` (FSM evalúa, risk lab no lo ejerce) |
| `PortfolioLimits` | `max_portfolio_heat`, `kill_switch_drawdown` | `partial` (existe, runner pasa `None`) |
| Fee/slippage | `commission_pct`, `slippage_pct` | `active` (runner los aplica) |

#### C. Indicadores del catálogo no implementados

3+ indicadores del catálogo Pine que no están en `INDICATOR_REGISTRY`:
- Squeeze Momentum (LazyBear)
- MTF Conditions (5×SMA)
- Fibonacci MAI

Clasificación esperada: `experimental`.

### 2.3 Contrato de filtro

Agregar la capacidad de restringir el search space a dimensiones `active`:

```python
# En optimization/_internal/objective.py o backtesting/grid.py

def filter_search_space(
    space: dict[str, dict[str, Any]],
    maturity: dict[str, str],
    *,
    level: str = "active",
) -> dict[str, dict[str, Any]]:
    """Return only dimensions at or above the requested maturity level."""
    allowed = {"active"} if level == "active" else {"active", "partial"}
    return {k: v for k, v in space.items() if maturity.get(k, "experimental") in allowed}
```

El optimizer debe invocar este filtro antes de sugerir parámetros. El nivel por defecto es `"active"`.

### 2.4 Deliverable

`docs/search_space_maturity_matrix.md` con formato:

```markdown
| Dimensión | Sub-config | Tipo | Rango | Maturity | Justificación |
|-----------|-----------|------|-------|----------|---------------|
| stop__atr_multiple | StopConfig | float | 1.0–5.0 | active | Wired E2E, tested, in default space |
| trailing__model | TrailingConfig | str | atr/chandelier/sar | partial | Policy classes exist, runner uses signal bool |
| squeeze_momentum | — | indicator | — | experimental | Not in INDICATOR_REGISTRY |
```

---

## 3. T5.5.2 — RM Wiring Specification

### 3.1 Gap analysis

| Componente | Contrato existente | Estado en runner | Acción T5.5.2 |
|------------|-------------------|-----------------|---------------|
| `PortfolioRiskManager.approve_new_risk()` | Retorna `(approved, reason)` | Runner pasa `portfolio_state=None` al sizer | **Opcional (gate blando):** Wire `PortfolioRiskManager` en `run_fsm_backtest()` con feature flag |
| `ExitPolicy.evaluate()` → `(should_exit, updated_stop, reason)` | 5 policies: BE, Fixed, ATR, Chandelier, SAR | Runner usa `trailing_signal: bool` del signal combiner | **Verificar:** ¿Las policies de `trailing.py` agregan valor sobre el trailing signal actual? Si sí, wire; si no, documentar por qué señales bastan |
| `TimeExitConfig.max_bars` | FSM evalúa `_should_time_exit()` correctamente | `run_risk_lab.py` presets no habilitan `time_exit.enabled` | **Obligatorio:** Agregar presets con `time_exit.enabled=True` en risk lab (mean_reversion family) |

### 3.2 Contrato de integración PortfolioRiskManager (opcional)

Si se implementa:

```python
# En run_fsm_backtest() — antes de processar entry_sig
portfolio_mgr = PortfolioRiskManager(risk_config.portfolio)

# En el loop de barras, antes de entry:
if entry_sig:
    portfolio_mgr.update(equity=equity, open_positions=[...])
    approved, reason = portfolio_mgr.approve_new_risk(
        proposed_risk=entry_size * abs(closes[i] - stop_override),
    )
    if not approved:
        entry_sig = False  # Block entry
```

**Feature flag:** `risk_config.portfolio.enabled` (agregar field a `PortfolioLimits`, default `False`).

### 3.3 Tests de integración requeridos

| # | Test | Qué verifica |
|---|------|-------------|
| 1 | `test_fsm_time_exit_closes_after_max_bars` | TimeExit funciona end-to-end en runner |
| 2 | `test_fsm_time_exit_disabled_by_default` | No interfiere cuando `enabled=False` |
| 3 | `test_trailing_signal_triggers_exit_after_tp1` | Trailing via signal bool funciona post-TP1 |
| 4 | `test_pyramid_respects_block_bars` | No pyramid add dentro de `block_bars` ventana |
| 5 | `test_break_even_buffer_covers_commission` | BE price incluye commission buffer |
| 6 | `test_portfolio_limits_block_entry` (si wired) | `approve_new_risk()` bloquea entry cuando heat > max |
| 7 | `test_fsm_determinism_same_input_same_output` | Replay idéntico → equity curve idéntica |

Todos los tests deben ejecutarse sobre el runner real (`run_fsm_backtest()`), no sobre la FSM aislada.

---

## 4. T5.5.3 — Backtest Execution Semantics Specification

### 4.1 Exit priority order (contrato inmutable)

```
PRIORIDAD    EVALUACIÓN           TRANSICIÓN                    NOTAS
──────────────────────────────────────────────────────────────────────────
   1         Stop-loss            → CLOSED                      Intrabar: usa low (long) / high (short)
   2         Partial TP1          → PARTIALLY_CLOSED            Señal exit + profit confirmation
   3         Break-even           → OPEN_BREAKEVEN o CLOSED     Buffer = 1.0007 (≈0.07% fees)
   4         Trailing exit        → CLOSED                      trailing_signal bool + TP1 ya hit
   5         Time exit            → CLOSED                      bars_in_position >= max_bars
   6         Entry / Pyramid      → OPEN_INITIAL / PYRAMIDED    entry_signal + can_enter()
```

Este orden está implementado en `PositionStateMachine.evaluate_bar()` y **no debe cambiar** durante Sprint 5.5.

### 4.2 Fee model

```
commission_cost = abs(filled_qty × price) × commission_pct / 100.0
```

- Se cobra en **entry**, **exit** (close_all, close_partial) y **pyramid_add**
- Default: `commission_pct = 0.07` (Binance spot maker/taker)
- Slippage: `slippage_pct = 0.0` (no implementado en runner actual; documentar como limitación)

### 4.3 Intrabar fill assumptions

- **OHLCV-only:** No hay orderbook ni tick data
- **Fill price:** `close[i]` para entries y pyramids; stop/TP1/BE/trailing usan precio calculado por FSM
- **No partial fills:** bar-based mode siempre `filled_qty == requested_qty`
- **No gap handling:** El runner no detecta gaps entre barras; SL puede ser peor que `stop_price` si low < stop (documentar)

### 4.4 Pyramiding semantics

- **Weighting:** Fibonacci `[1,1,2]` → normalizado a `[25%, 25%, 50%]` del sizing base
- **Block bars:** `pyramid.block_bars` barras de cooldown entre adds
- **Threshold:** `close > avg_entry × threshold_factor` para add long
- **Max adds:** `pyramid.max_adds` (default 3, configurable)

### 4.5 FSM vs Simple coherence

| Métrica | FSM | Simple | ¿Debe coincidir? |
|---------|-----|--------|-------------------|
| Total trades | Sí (con pyramid splitting) | Sí (1 trade = 1 entry+exit) | No — FSM puede generar más trades por pyramids |
| Net PnL | Sí | Sí | Aproximado — sin pyramid/TP1 → deben coincidir ±commission |
| Sharpe | Sí | Sí | Aproximado — equity curves divergen por timing de partial exits |
| Win rate | Sí | Sí | No — partial TP cambia what counts as "win" |
| Max drawdown | Sí | Sí | No — pyramid adds can deepen DD |

**Contrato:** Para archetypes `mean_reversion` y `grid_dca` (sin pyramid, sin partial TP), FSM y Simple deben producir **idénticos** net PnL y trade count. Esto es un regression test.

### 4.6 Regression fixtures

Formato JSON en `tests/fixtures/backtest_regressions/`:

```json
{
  "name": "basic_long_entry_exit",
  "description": "Single long entry → SL exit",
  "ohlcv": [[1000,1010,990,1005,100], ...],
  "signals": {"entry_long": [false,true,...], "exit_long": [false,...], ...},
  "risk_config": {"stop": {"atr_multiple": 2.0}, ...},
  "expected": {
    "total_trades": 1,
    "net_pnl": -15.03,
    "exit_reason": "stop_loss",
    "final_equity": 3984.97
  }
}
```

**Mínimo 3 fixtures:**
1. `basic_long_sl.json` — Entry → SL hit → CLOSED
2. `long_with_tp1_trailing.json` — Entry → TP1 → BE → trailing exit
3. `pyramid_3_adds.json` — Entry → 3 pyramid adds → trailing exit

---

## 5. T5.5.4 — Risk Lab Expansion Specification

### 5.1 Prerequisito: data download

```bash
cd suitetrading
.venv/bin/python scripts/download_data.py --symbols ETHUSDT SOLUSDT \
    --timeframe 15m 1h 4h 1d
```

Post-download: ejecutar `scripts/cross_validate_native.py --symbols ETHUSDT SOLUSDT --days 30` para verificar integridad.

### 5.2 Campaign specification

| Dimensión | Valores | Count |
|-----------|---------|-------|
| Symbol | BTCUSDT, ETHUSDT, SOLUSDT | 3 |
| Timeframe | 15m, 1h, 4h, 1d | 4 |
| Strategy | ssl_trend, firestorm_trend, wavetrend_meanrev | 3 |
| Risk preset | 6 por familia (ver detalle abajo) | 6 |
| **Total** | | **216** |

**Presets por familia de estrategia:**

- **Trend (ssl_trend, firestorm_trend):** `base, tight_stop, wide_stop, atr_sizer, no_pyramid, partial_tp_on`
- **Mean reversion (wavetrend_meanrev):** `base_safe, tight_stop, loose_stop, time_exit, no_partial_tp, no_break_even`

### 5.3 Output schema CSV

Columnas del CSV expandido (sobre el schema actual de `run_risk_lab.py`):

```
symbol, timeframe, strategy, archetype, risk_preset,
stop_model, stop_atr_mult, sizing_model, sizing_risk_pct,
pyramid_enabled, partial_tp_enabled, break_even_enabled, time_exit_enabled, time_exit_bars,
trailing_model,
total_trades, win_rate, sharpe, sortino, calmar,
max_drawdown_pct, total_return_pct, net_profit,
avg_trade_pnl, profit_factor, max_consecutive_losses,
wall_time_sec
```

### 5.4 Análisis requerido

- **Trend vs mean reversion:** ¿Qué familia produce mejores risk-adjusted returns?
- **RM impact:** ¿Qué controles (pyramid, TP1, BE, time_exit) cambian materialmente Sharpe/DD?
- **Cross-symbol:** ¿Los patrones se mantienen en ETH y SOL o son artefactos de BTC?
- **Cross-TF:** ¿Hay TFs dominantes o es estable?

---

## 6. T5.5.5 — Reference Validation Specification

### 6.1 Scope

- **No es gate duro.** TV es referencia visual puntual.
- Spot-check manual de 2-3 indicadores clave contra TradingView:
  - **Firestorm:** Comparar señales entry/exit en un rango de ~100 barras
  - **SSL Channel:** Comparar flip points (ya validado parcialmente con HTML export)
- Usar `artifacts/indicator_validation/` para generar HTML overlays

### 6.2 Consistencia interna (prioridad)

- Signals → FSM → metrics debe ser **reproducible** (mismo input → mismo output)
- Test de determinismo ya cubierto en T5.5.2 test #7

---

## 7. T5.5.6 — NautilusTrader Gate Specification

### 7.1 Criterios de selección top 10-20

Del conjunto de candidatas producidas por el optimizer + WFO + anti-overfit pipeline:

1. **OOS Sharpe ≥ 0.5** (post walk-forward)
2. **CSCV PBO < 0.50** (no overfit)
3. **DSR > 0** (Sharpe sobrevive penalización por trials múltiples)
4. **Max DD < 25%**
5. **≥30 trades** en período OOS (significancia estadística)
6. **Risk lab confirms** el patrón OOS se mantiene en ≥2 símbolos

### 7.2 Search space freeze

- Snapshot del `search_space_maturity_matrix.md` como versión vX.Y
- Registrar hash SHA-256 del archivo como control de integridad
- NautilusTrader (Sprint 6) debe operar sobre el **mismo** search space frozen

### 7.3 Input para NautilusTrader

`sprint55_hardening_report.md` debe incluir:

| Sección | Contenido |
|---------|-----------|
| Shortlist | Top 10-20 candidatas con params, métricas OOS, CSCV PBO |
| Search space frozen | Versión + hash del maturity matrix |
| Gaps remanentes | Qué no se validó (ej: portfolio controls, slippage) |
| Recomendaciones | Qué tests replicar en NautilusTrader tick-by-tick |
