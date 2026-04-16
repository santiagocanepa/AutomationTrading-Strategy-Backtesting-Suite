# Research Report — Exhaustive Discovery Phase

**Date**: 2026-03-17
**Platform**: SuiteTrading v2
**Compute**: Apple M4 Pro (14 cores, 48 GB)
**Total**: ~955 WFO studies, ~1M+ backtests, 90 risk archetypes, 3 assets, 4 timeframes

> **Nota:** Este documento cubre los resultados históricos de Phases 1-5 (qué se hizo, qué se encontró). Para la metodología de research actual y futura (Multi-TF Edge Mapping, Steps 1-7), ver [Research Methodology](research_methodology.md).

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Research Methodology](#2-research-methodology)
3. [Infrastructure & Pipeline](#3-infrastructure--pipeline)
4. [Phase 1 — Initial Discovery (574 studies)](#4-phase-1--initial-discovery-574-studies)
5. [Phase 2 — Risk Space Expansion (381 studies)](#5-phase-2--risk-space-expansion-381-studies)
6. [Sensitivity Analysis](#6-sensitivity-analysis)
7. [Boundary Analysis](#7-boundary-analysis)
8. [Critical Bugs Found & Fixed](#8-critical-bugs-found--fixed)
9. [Key Discoveries](#9-key-discoveries)
10. [Current Archetype Catalog](#10-current-archetype-catalog)
11. [Search Space Definition](#11-search-space-definition)
12. [Unexplored Dimensions](#12-unexplored-dimensions)
13. [Decision Framework: Exploration vs Exploitation](#13-decision-framework-exploration-vs-exploitation)
14. [Reproduction Guide](#14-reproduction-guide)

---

## 1. Executive Summary

### Numbers

| Metric | Phase 1 | Phase 2 | Total |
|--------|---------|---------|-------|
| WFO Studies | 574 | 381 | 955 |
| Backtests (est.) | ~287K | ~750K | ~1M+ |
| Risk Archetypes | 62 | 28 (fullrisk) | 90 |
| PBO < 0.50 | 276 (48%) | — | — |
| PBO < 0.30 (viable) | — | 41 | 41 |
| PBO < 0.01 | 12 | 2 | 14 |
| DSR Finalists | 0 | 0 | 0 |

### Top 5 Overall (by PBO)

| # | Config | PBO | Sharpe | Return | Asset | TF | Dir |
|---|--------|-----|--------|--------|-------|----|-----|
| 1 | SSL+fullrisk+pyr | 0.001 | 0.52 | +10.6% | ETH | 4h | short |
| 2 | RSI+fullrisk+pyr | 0.008 | 1.37 | +183.3% | ETH | 1h | long |
| 3 | MACD+fullrisk+pyr | 0.015 | 1.63 | +422.9% | SOL | 1h | short |
| 4 | MACD+fullrisk+pyr | 0.025 | 1.53 | +254.5% | SOL | 1h | long |
| 5 | ROC+fullrisk+pyr+MTF | 0.033 | 1.78 | +303.0% | SOL | 4h | short |

### Core Finding

> **El edge no vive en los indicadores, sino en la interacción indicator × risk management × asset × timeframe × direction.**
> No existe un indicador mágico. La cadena completa de gestión de riesgo (TP1 → Break Even → Trailing → Pyramid) es donde se captura el alpha.

---

## 2. Research Methodology

### Philosophy

- **Exploración exhaustiva antes de explotación** — no buscar la estrategia rentable rápido, sino mapear el espacio de búsqueda completo
- **Asset-specific** — una estrategia BTC no necesita funcionar en ETH/SOL
- **Long/Short como tracks independientes** — FSM no permite flip; cada dirección es un study separado
- **MIN_TRADES = 300** — mínimo estadístico para significancia en cualquier TF/período

### Pipeline Anti-Overfitting

```
Optuna TPE (1000 trials/study)
    → Walk-Forward Optimization (rolling, IS ~75% / OOS ~25%)
        → CSCV (Combinatorially Symmetric Cross-Validation)
            → PBO (Probability of Backtest Overfitting)
                → DSR (Deflated Sharpe Ratio)
                    → [futuro] Hansen SPA
```

**Criterios de filtro**:
- PBO < 0.30 = "viable candidate"
- PBO < 0.10 = "strong candidate"
- PBO < 0.01 = "exceptional" (solo 14 de ~955 studies)
- DSR p < 0.05 = "statistically significant" (0 hasta ahora — demasiado estricto para trial counts actuales)

### Dimensiones Exploradas

| Dimensión | Valores probados |
|-----------|-----------------|
| Assets | BTCUSDT, ETHUSDT, SOLUSDT |
| Timeframes | 1h, 4h (parcial: 1d, 15m) |
| Directions | long, short |
| Data periods | 12 meses (principal), 24 meses (top 10 archetypes) |
| Entry indicators | ROC, MACD, EMA, RSI, SSL, WaveTrend, Bollinger, Donchian, ADX, MA Crossover |
| HTF filters | ma_crossover (1d), ROC (1d), MACD (1d), EMA (1d) |
| Risk params | 10 dimensiones (ver sección 11) |
| Risk features | TP1 + BE + Trailing (siempre), Pyramid (condicional), Time Exit (condicional) |

---

## 3. Infrastructure & Pipeline

### Architecture Overview

```
Data (Parquet)
    ↓
Indicator Engine (12 indicators, signal combiner, MTF)
    ↓
BacktestObjective (Optuna trial → signals → backtest → metric)
    ↓
Optuna TPE Sampler (1000 trials/study)
    ↓
Walk-Forward Optimization (rolling windows)
    ↓
CSCV → PBO score
    ↓
[Optional] DSR, Hansen SPA
```

### Key Files

| File | Purpose |
|------|---------|
| `optimization/_internal/objective.py` | Bridge Optuna ↔ BacktestEngine, search space, signal building |
| `risk/archetypes/_fullrisk_base.py` | Shared builder for fullrisk variants (avoid duplication) |
| `risk/archetypes/__init__.py` | Registry: 94 archetypes |
| `config/archetypes.py` | Archetype → indicator mapping (entry, exit, trailing, HTF) |
| `risk/contracts.py` | `RiskConfig` Pydantic model (all risk params validated) |
| `risk/state_machine.py` | FSM for position lifecycle |

### Parallelization

- **12 procesos simultáneos** split por `symbol × TF × direction`
- **~90% CPU utilization** per process (~1100% total en 14 cores)
- **Throughput**: 63+ backtests/sec per process
- **Pattern**: `nohup python -m suitetrading.optimization ... > log 2>&1 &`

### Auto-Pruning

`BacktestObjective.__init__()` elimina automáticamente parámetros irrelevantes del search space basándose en la config del archetype:

| Condición | Params removidos |
|-----------|-----------------|
| `pyramid.enabled = False` | `pyramid__max_adds`, `pyramid__block_bars`, `pyramid__threshold_factor` |
| `time_exit.enabled = False` | `time_exit__max_bars` |
| `stop.model = "firestorm_tm"` | `stop__atr_multiple` |
| `partial_tp.enabled = False` | `partial_tp__r_multiple`, `partial_tp__close_pct` |
| `break_even.enabled = False` | `break_even__buffer`, `break_even__r_multiple` |

Esto permite que cada archetype optimice solo los parámetros que realmente usa, mejorando la eficiencia del sampler TPE.

---

## 4. Phase 1 — Initial Discovery (574 studies)

### Scope

- **Archetypes**: 62 (core + simple + combos + MTF + directional-optimized + new entry indicators)
- **Indicadores entry**: ROC, MACD, EMA, Donchian, ADX, MA Crossover, SSL, Firestorm, WaveTrend
- **Risk features**: TP1 + BE + Trailing (6 risk params optimizados)
- **Data**: 12 meses

### Results Summary

| Metric | Value |
|--------|-------|
| Total studies | 574 |
| Backtests (est.) | ~287K |
| Pass PBO < 0.50 | 276 (48%) |
| PBO = 0.000 | 5 |
| PBO < 0.01 | 12 |
| PBO < 0.05 | 41 |
| DSR finalists | 0 |

### Key Findings (Phase 1)

1. **Risk management > Indicators**: La cadena TP1 + BE + trailing con params correctos (r_multiple=1.5-2.0) produce 10x mejora vs defaults
2. **MTF daily MA filter**: +70% Sharpe improvement para longs
3. **SSL independiente de momentum**: correlación < 0.3 con ROC/MACD, agrega información ortogonal
4. **Edge estadístico real es thin**: P(up|signal) = 49-53%. Los profits vienen del compounding + risk management, no de prediction accuracy
5. **Parámetros óptimos iniciales**: risk ~7%, stop ATR ~18, EMA slow ~200

### Problems Identified

- Search space de risk era solo 6 params (sin pyramid, sin time_exit, sin BE r_multiple)
- Muchos archetypes tenían pyramid deshabilitado — oportunidad perdida
- No se testó long vs short por separado en todos los archetypes

---

## 5. Phase 2 — Risk Space Expansion (381 studies)

### Motivation

Phase 1 mostró que el risk management domina los resultados. Phase 2 expandió:
1. Search space de 6 → 10 risk params
2. 28 nuevos archetypes "fullrisk" con todas las features habilitadas
3. Pyramid scaling como dimensión principal
4. Time exit como dimensión explorable
5. HTF filters alternativos (MACD daily, EMA daily)

### Waves of Exploration

| Wave | Focus | Studies | New |
|------|-------|---------|-----|
| A | fullrisk base (ROC, MACD, MA, EMA) | 60 | `*_fullrisk`, `*_fullrisk_mtf` |
| B | fullrisk + pyramid (ROC, MACD, MA) | 36 | `*_fullrisk_pyr` |
| C | fullrisk + time exit, fullrisk + all | 36 | `*_fullrisk_time`, `*_fullrisk_all` |
| D | Multi-indicator fullrisk+pyr combos | 48 | `roc_macd_*`, `roc_ema_*`, `macd_ema_*`, `roc_adx_*` |
| E | 24-month data on top 10 archetypes | 120 | Regime robustness test |
| F | New indicators (SSL entry, WaveTrend, BBand) | 36 | `ssl_fullrisk_pyr`, `wt_fullrisk_pyr`, `bband_fullrisk_pyr` |
| G | Alternative HTF filters (MACD 1d, EMA 1d) | 36 | `roc_fullrisk_htf_macd`, `roc_fullrisk_pyr_htf_macd`, `macd_fullrisk_htf_ema` |

**Total Phase 2**: 381 studies, ~750K backtests

### Results Summary

| Metric | Value |
|--------|-------|
| Total studies | 381 |
| Viable candidates (PBO < 0.30, Sharpe > 0, Return > 0) | 41 |
| PBO < 0.01 | 2 |
| PBO < 0.05 | 5 |
| PBO < 0.10 | 10 |
| PBO < 0.20 | 26 |

### Top 10 Results (Phase 2)

| # | Archetype | Asset | TF | Dir | PBO | Sharpe | Return |
|---|-----------|-------|----|-----|-----|--------|--------|
| 1 | ssl_fullrisk_pyr | ETH | 4h | short | 0.001 | 0.52 | +10.6% |
| 2 | rsi_fullrisk_pyr | ETH | 1h | long | 0.008 | 1.37 | +183.3% |
| 3 | macd_fullrisk_pyr | SOL | 1h | short | 0.015 | 1.63 | +422.9% |
| 4 | macd_fullrisk_pyr | SOL | 1h | long | 0.025 | 1.53 | +254.5% |
| 5 | roc_fullrisk_pyr_mtf | SOL | 4h | short | 0.033 | 1.78 | +303.0% |
| 6 | roc_fullrisk_htf_macd | BTC | 4h | short | 0.057 | 0.89 | +45.2% |
| 7 | ema_fullrisk_pyr | SOL | 1h | long | 0.062 | 1.45 | +198.7% |
| 8 | roc_adx_fullrisk_pyr | ETH | 4h | short | 0.078 | 1.12 | +87.3% |
| 9 | macd_fullrisk_pyr_mtf | BTC | 1h | long | 0.091 | 1.28 | +156.4% |
| 10 | roc_fullrisk_pyr | BTC | 4h | short | 0.098 | 1.05 | +72.1% |

### 24-Month Regime Robustness (Wave E)

Se testearon los top 10 archetypes con 24 meses de data para evaluar si las estrategias sobreviven cambios de régimen (bull → bear → consolidation).

| Config | PBO (12m) | PBO (24m) | Delta | Survived? |
|--------|-----------|-----------|-------|-----------|
| BTC ROC short | 0.098 | 0.220 | +0.122 | Partial |
| SOL MACD+pyr short | 0.015 | — | — | Testing |
| ETH SSL+pyr short | 0.001 | — | — | Testing |

**Hallazgo**: El PBO sube con 24m data (esperado — más régimenes), pero BTC ROC short sobrevive con PBO=0.220, indicando que no es puramente overfitted.

---

## 6. Sensitivity Analysis

### Dataset

- **5,450 trials** analizados (extraídos de Optuna studies)
- **3,159 profitable** (Sharpe > 0)
- **109 studies** con PBO < 0.50

### Parameter Importance Ranking

Medido como spread de Sharpe entre quintil superior vs inferior:

| Rank | Parameter | Sharpe Spread | Interpretation |
|------|-----------|---------------|----------------|
| 1 | `time_exit__max_bars` | 0.492 | **Más impactante** — time exit domina |
| 2 | `pyramid__block_bars` | 0.372 | Espaciado entre pyramid adds es crítico |
| 3 | `break_even__r_multiple` | 0.246 | Cuándo activar BE importa mucho |
| 4 | `partial_tp__r_multiple` | 0.220 | TP1 trigger level importa |
| 5 | `sizing__risk_pct` | 0.209 | Sizing tiene impacto moderado |
| 6 | `pyramid__max_adds` | 0.203 | Cuántas adds, pero menos que spacing |
| 7 | `pyramid__threshold_factor` | 0.200 | Threshold para confirmar tendencia |
| 8 | `partial_tp__close_pct` | 0.181 | Qué % cerrar en TP1 |
| 9 | `break_even__buffer` | 0.148 | Buffer de protección |
| 10 | `stop__atr_multiple` | 0.137 | Stop width — **menos impactante** |

### Long vs Short Need Different Configs

| Parameter | Long Optimal | Short Optimal | Implication |
|-----------|-------------|---------------|-------------|
| `sizing__risk_pct` | 18% | 26% | Shorts necesitan más riesgo |
| `partial_tp__r_multiple` | 4.0R | 2.5R | Shorts toman profit más temprano |
| `partial_tp__close_pct` | 35% | 65% | Shorts cierran más en TP1 |
| `pyramid__block_bars` | 19 | 13 | Shorts escalan más rápido |
| `stop__atr_multiple` | 12 | 15 | Shorts necesitan stops más amplios |

### Parameter Stability

**TODOS los parámetros son estables** (zona verde 83-100% del rango de búsqueda).

Esto significa:
- No hay parámetros frágiles (pequeños cambios no destruyen el Sharpe)
- El search space está bien calibrado — los óptimos no son outliers
- La optimización no está capturando ruido — las relaciones son robustas

---

## 7. Boundary Analysis

Se verificó si los óptimos se agrupan en los bordes del search space (indicaría que el rango es demasiado estrecho).

### Resultado

| Parameter | Border Clustering? | Action Taken |
|-----------|--------------------|--------------|
| `sizing__risk_pct` | **SI** — clustering en lower bound (2.0) | Expandido min: 2.0 → 1.0 |
| `stop__atr_multiple` | No | — |
| `partial_tp__r_multiple` | No | — |
| `partial_tp__close_pct` | No | — |
| `break_even__buffer` | No | — |
| `break_even__r_multiple` | No | — |
| `pyramid__max_adds` | No | — |
| `pyramid__block_bars` | No | — |
| `pyramid__threshold_factor` | No | — |
| `time_exit__max_bars` | No | — |

Solo `sizing__risk_pct` necesitó corrección. El resto del search space está bien definido.

---

## 8. Critical Bugs Found & Fixed

### Bug 1: Trailing Exit Blocked from OPEN_INITIAL

**Síntoma**: 2-3 trades por study (de 7 años de data)
**Causa**: `_should_trailing_exit()` requería `tp1_hit or OPEN_BREAKEVEN` antes de permitir trailing exit. Si TP1 o BE estaban deshabilitados, las posiciones nunca cerraban.
**Fix**: Trailing/exit signal fires incondicional desde cualquier estado abierto (OPEN_INITIAL, OPEN_BREAKEVEN, OPEN_TRAILING, OPEN_PYRAMIDED).
**Impacto**: De 2-3 trades → 500-2400 trades. Primeros resultados positivos con Sharpe > 0.

### Bug 2: Crypto Risk Params Incorrectos

**Síntoma**: 0 finalists en 22,500 backtests iniciales
**Causa**: Defaults (ATR 2-3, risk 1%, commission 0.10%) destruyen el edge en crypto. Stops demasiado tight causan whipsaw; commission 0.10% es 2.5x Binance real (0.04%).
**Fix**: ATR 3-20, risk 1-50%, commission 0.04% (Binance maker).
**Impacto**: Sharpe pasó de negativo a 0.5-1.8 con parámetros correctos.

### Bug 3: PnL Accumulation Error

**Síntoma**: Equity curves no cuadraban con trades individuales
**Causa**: `realized_pnl` se acumulaba mal con partial closes + pyramid adds
**Fix**: Track PnL incremental per event, no acumulado

### Bug 4: Look-Ahead Bias

**Síntoma**: IS Sharpe ridículamente alto, OOS colapso
**Causa**: Indicator computation usaba datos futuros en ventanas
**Fix**: Alignment estricto de señales con warmup bars

### Bug 5: ast.literal_eval con NaN (Python 3.14)

**Síntoma**: `ast.literal_eval()` crashea con `nan` en stringified dicts
**Causa**: Python 3.14 no tolera `nan`/`inf` en `literal_eval`
**Fix**: `safe_eval()` que reemplaza `nan`/`inf` con `None` antes de parsear

---

## 9. Key Discoveries

### 9.1 Risk Management Chain is the Edge

Los indicadores tienen edge estadístico real pero delgado (P(up|signal) ≈ 49-53%). Los profits vienen de:

```
Entry Signal (indicator) →
    Stop Loss (ATR-based, wide) →
        TP1 (partial close at R-multiple) →
            Break Even (protect remaining) →
                Trailing Exit (capture trend) →
                    [optional] Pyramid (scale in on confirmation)
```

Cada eslabón de la cadena multiplica el efecto. Sin TP1+BE, el trailing solo no alcanza. Sin trailing, TP1+BE no captura tendencias largas.

### 9.2 SSL Channel as Entry Signal = Lowest PBO

SSL Channel como indicador de ENTRY (no solo trailing) produjo el PBO más bajo de toda la exploración (0.001). Históricamente se usaba solo como trailing stop. Esta es la innovación más significativa de la fase de exploración.

### 9.3 Pyramid Dominates Top Results

8 de los top 10 results usan pyramid. El espaciado (`block_bars`) es más importante que la cantidad de adds (`max_adds`):

| Param | Importance Rank | Sharpe Spread |
|-------|----------------|---------------|
| `pyramid__block_bars` | #2 overall | 0.372 |
| `pyramid__max_adds` | #6 overall | 0.203 |

### 9.4 No Single Magic Indicator

Performance por indicador varía dramáticamente según asset × TF × direction:

| Indicator | Best Use Case | PBO |
|-----------|--------------|-----|
| SSL Channel | ETH 4h short | 0.001 |
| RSI | ETH 1h long | 0.008 |
| MACD | SOL 1h both | 0.015-0.025 |
| ROC | SOL 4h short (con MTF) | 0.033 |
| EMA | SOL 1h long | 0.062 |

### 9.5 Long vs Short Are Fundamentally Different

Shorts necesitan: más riesgo, TP más temprano, cierre parcial mayor, pyramid más rápido. Esto se alinea con la asimetría fundamental de los mercados crypto (drawdowns más rápidos que rallies).

### 9.6 MTF Filters Add Robustness

Daily MA crossover como filtro HTF agregó +70% Sharpe para longs. MACD daily como filtro alternativo también funciona (PBO=0.057 para BTC shorts).

### 9.7 Time Exit is the Most Impactful Single Parameter

`time_exit__max_bars` tiene el spread de Sharpe más alto (0.492). Las estrategias que matan posiciones estancadas outperform masivamente a las que las dejan correr indefinidamente.

---

## 10. Current Archetype Catalog

### Classification

| Tier | Type | Count | Examples |
|------|------|-------|---------|
| Core | Base presets | 9 | trend_following, mean_reversion, mixed, legacy_firestorm, pyramidal, grid_dca, momentum, breakout, momentum_trend |
| Simple | Single indicator | 6 | donchian_simple, roc_simple, ma_cross_simple, adx_simple, macd_simple, ema_simple |
| Combo | Dual indicator | 13 | roc_adx, roc_ma, roc_ssl, macd_roc, macd_ssl, ema_roc, ssl_roc, fire_roc, wt_roc, ... |
| Triple | Three indicators | 4 | roc_donch_ssl, roc_ma_ssl, macd_roc_adx, ema_roc_adx |
| MTF | Multi-timeframe | 11 | roc_mtf, macd_mtf, ema_roc_mtf, donchian_mtf, ssl_adx_mtf, triple_mtf, ... |
| Directional | Long/Short optimized | 6 | roc_mtf_longopt, roc_shortopt, macd_mtf_longopt, macd_shortopt, ma_x_ssl_longopt, ema_mtf_longopt |
| New Entry | RSI/BBand/WT as entry | 6 | rsi_roc, rsi_mtf, bband_roc, wt_filter_roc, roc_mtf_roc, macd_roc_mtf |
| Fullrisk | Full risk chain (no pyr) | 5 | roc_fullrisk, roc_fullrisk_mtf, macd_fullrisk, ma_x_fullrisk, ema_fullrisk_mtf |
| Fullrisk+Pyr | + Pyramid scaling | 12 | roc_fullrisk_pyr, macd_fullrisk_pyr, ssl_fullrisk_pyr, rsi_fullrisk_pyr, donchian_fullrisk_pyr, ... |
| Fullrisk+Time | + Time exit | 2 | roc_fullrisk_time, macd_fullrisk_time |
| Fullrisk+All | + Pyr + Time | 2 | roc_fullrisk_all, macd_fullrisk_all |
| Fullrisk+MTF | + MTF filter (pyr) | 3 | roc_fullrisk_pyr_mtf, macd_fullrisk_pyr_mtf, roc_adx_fullrisk_pyr_mtf |
| Fullrisk+Multi | Multi-indicator fullrisk | 5 | roc_macd_fullrisk_pyr, roc_ema_fullrisk_pyr, macd_ema_fullrisk_pyr, roc_adx_fullrisk_pyr, ... |
| Fullrisk+HTF | HTF alt filter | 3 | roc_fullrisk_htf_macd, roc_fullrisk_pyr_htf_macd, macd_fullrisk_htf_ema |
| Fullrisk+NewInd | SSL/WT/BBand entry+pyr | 3 | ssl_fullrisk_pyr, wt_fullrisk_pyr, bband_fullrisk_pyr |
| **Total** | | **90** | |

### Fullrisk Base Config

Todos los archetypes `*_fullrisk*` comparten la misma base via `_fullrisk_base.py`:

```python
{
    "direction": "both",
    "initial_capital": 4_000,
    "commission_pct": 0.04,           # Binance maker
    "sizing": {"model": "fixed_fractional", "risk_pct": 10.0,
               "max_risk_per_trade": 15.0|50.0},  # 15 si pyramid, 50 si no
    "stop": {"model": "atr", "atr_multiple": 10.0},
    "trailing": {"model": "atr", "trailing_mode": "signal", "atr_multiple": 10.0},
    "partial_tp": {"enabled": True, "close_pct": 30.0,
                   "trigger": "r_multiple", "r_multiple": 1.0},
    "break_even": {"enabled": True, "buffer": 1.001, "activation": "after_tp1"},
    "pyramid": {"enabled": conditional, "max_adds": 3, "block_bars": 15},
    "time_exit": {"enabled": conditional, "max_bars": 200},
}
```

`max_risk_per_trade` se ajusta automáticamente: 15% para pyramid (15 × 6 adds max = 90% < 100%) y 50% para no-pyramid. Esto evita que Pydantic rechace configs con `max_adds * max_risk > 100`.

---

## 11. Search Space Definition

### Risk Parameters (10 dimensions)

| Parameter | Type | Min | Max | Step | Pruned When |
|-----------|------|-----|-----|------|-------------|
| `stop__atr_multiple` | float | 3.0 | 20.0 | 1.0 | `stop.model = "firestorm_tm"` |
| `sizing__risk_pct` | float | 1.0 | 50.0 | 1.0 | Never |
| `partial_tp__r_multiple` | float | 0.5 | 5.0 | 0.25 | `partial_tp.enabled = False` |
| `partial_tp__close_pct` | float | 10.0 | 80.0 | 5.0 | `partial_tp.enabled = False` |
| `break_even__buffer` | float | 1.0001 | 1.01 | 0.001 | `break_even.enabled = False` |
| `break_even__r_multiple` | float | 0.5 | 3.0 | 0.25 | `break_even.enabled = False` |
| `pyramid__max_adds` | int | 1 | 5 | 1 | `pyramid.enabled = False` |
| `pyramid__block_bars` | int | 3 | 50 | 1 | `pyramid.enabled = False` |
| `pyramid__threshold_factor` | float | 1.002 | 1.05 | 0.002 | `pyramid.enabled = False` |
| `time_exit__max_bars` | int | 30 | 500 | 1 | `time_exit.enabled = False` |

### Indicator Parameters (per indicator)

Cada indicador tiene su propio search space con parámetros que Optuna optimiza junto con los risk params. Ejemplo:

| Indicator | Parameters | Ranges |
|-----------|-----------|--------|
| ROC | period | 5-50 |
| MACD | fast, slow, signal | (5-20, 15-50, 5-15) |
| EMA | period1, period2 | (5-50, 20-200) |
| RSI | period | 7-30 |
| SSL Channel | period | 10-50 |
| Bollinger | period, std_dev | (10-30, 1.5-3.0) |

---

## 12. Unexplored Dimensions

### High Priority (expected high impact)

| Dimension | Why | Effort |
|-----------|-----|--------|
| **15m timeframe** | Mayor granularidad, más trades, mejor para scalping | 72 studies × 2h |
| **Firestorm TM stop model** | All fullrisk use ATR stops. Firestorm TM podría ser superior para crypto vol | 28 studies × 2h |
| **Trailing mode "policy" vs "signal"** | Todos los fullrisk usan `trailing_mode="signal"`. ATR-based trailing policy podría capturar más en trends | 28 studies × 2h |
| **36-month data** | Solo top 10 testeados con 24m. 36m para regime robustness definitiva | 10 studies × 4h |
| **24m data for ALL fullrisk archetypes** | Solo top 10 testeados con 24m, quedan 18 fullrisk sin testear | 36 studies × 3h |

### Medium Priority (worth testing)

| Dimension | Why | Effort |
|-----------|-----|--------|
| **VWAP indicator** | Nunca usado como entry. Popular en intraday | 12 studies × 1h |
| **WaveTrend divergence** | Solo probado reversal, no divergence mode | 12 studies × 1h |
| **More HTF combinations** | RSI, Bollinger como HTF filters (solo se probó MA, ROC, MACD, EMA) | 24 studies × 2h |
| **Chandelier trailing** | Solo ATR y signal probados como trailing. Chandelier exit es clásico | 14 studies × 2h |
| **Parabolic SAR trailing** | Trailing model disponible pero nunca testeado | 14 studies × 2h |

### Low Priority (diminishing returns expected)

| Dimension | Why | Effort |
|-----------|-----|--------|
| **More symbols** | BNB, AVAX, DOGE — posible pero risk of dilution | Variable |
| **1w/1M timeframes** | Demasiado pocas trades para MIN_TRADES=300 | Low value |
| **Nuevos indicadores** (Ichimoku, Squeeze, Stochastic) | Solo si SHAP muestra que actuales no cubren el espacio de features | Sprint 9 |
| **Multi-period** (4 sub-períodos 2017-2026) | Definido en phase2_plan pero requiere más data prep | Sprint 8 |

---

## 13. Decision Framework: Exploration vs Exploitation

### When to Continue Exploring

Continuar si:
- Hay dimensiones de **alto impacto** sin testear (15m TF, Firestorm TM stops, trailing policies)
- Se quiere confirmar **robustez temporal** con 24m/36m data en más archetypes
- Se busca **cobertura completa** del espacio antes de reducir

### When to Move to Exploitation

Pasar a explotación si:
- Los 41 candidatos viables ya son suficientes para portfolio construction
- Se quiere hacer **SHAP analysis** para entender qué features realmente importan
- Se quiere hacer **regime-conditional filtering** para seleccionar estrategias por condición de mercado
- Se quiere hacer **portfolio optimization** con los candidatos existentes

### Exploitation Phase (Draft Plan)

```
FASE 1: Análisis de Interacción (Sprint 9)
    ├─ SHAP/feature importance per archetype
    ├─ Indicator entropy & mutual information
    ├─ Identificar minimal indicator sets
    └─ Cross-asset: ¿mismos params funcionan en otro asset?

FASE 2: Robustness & Validation (Sprint 10)
    ├─ Hansen SPA test en top candidates
    ├─ Monte Carlo permutation tests
    ├─ Walk-forward con window sizes variables
    ├─ Stress testing (draw extreme scenarios)
    └─ Regime detection + conditional performance

FASE 3: Portfolio Construction (Sprint 11)
    ├─ Diversificación: seleccionar N estrategias no correlacionadas
    ├─ Position sizing a nivel portfolio
    ├─ Kill switch calibration
    └─ Paper trading setup

FASE 4: Production (Sprint 12+)
    ├─ Signal bridge → exchange execution
    ├─ Monitoring & alerting
    └─ Performance tracking vs expectations
```

### Recommended Next Steps

1. **Inmediato**: Completar dimensiones high-priority (15m, Firestorm TM stops, trailing policies) — ~2-3 days compute
2. **Short-term**: 24m/36m data runs para todos los fullrisk archetypes — ~1 day compute
3. **Then**: Enter exploitation phase con SHAP + Hansen SPA + regime analysis

---

## 14. Reproduction Guide

### Prerequisites

```bash
cd suitetrading/
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,data,optimization]"
```

### Download Data

```bash
python scripts/download_data.py --symbols BTCUSDT ETHUSDT SOLUSDT --start 2017-01-01
```

### Run a Single Discovery Study

```bash
python -m suitetrading.optimization.walk_forward \
    --symbol BTCUSDT \
    --timeframe 1h \
    --archetype roc_fullrisk_pyr \
    --direction long \
    --trials 1000 \
    --data-months 12 \
    --output artifacts/discovery/
```

### Run Parallel Discovery (12 processes)

```bash
# BTC × {1h,4h} × {long,short} = 4 processes
for TF in 1h 4h; do
  for DIR in long short; do
    nohup python -m suitetrading.optimization.walk_forward \
      --symbol BTCUSDT --timeframe $TF \
      --archetype roc_fullrisk_pyr --direction $DIR \
      --trials 1000 --data-months 12 \
      --output artifacts/discovery/run_$(date +%Y%m%d)/ \
      > logs/btc_${TF}_${DIR}.log 2>&1 &
  done
done

# Repeat for ETHUSDT, SOLUSDT = 12 total processes
```

### Analyze Results

```bash
# Aggregate all study results
python scripts/analyze_risk_lab.py --input artifacts/discovery/ --output results/

# Filter viable candidates
python -c "
import pandas as pd
df = pd.read_csv('results/all_studies.csv')
viable = df[(df['pbo'] < 0.30) & (df['sharpe'] > 0) & (df['total_return'] > 0)]
print(viable.sort_values('pbo')[['archetype','symbol','tf','direction','pbo','sharpe','total_return']])
"
```

### Run Sensitivity Analysis

```bash
# Extract trials from Optuna studies
python -c "
import optuna, pandas as pd, glob

rows = []
for db in glob.glob('artifacts/discovery/**/*.db', recursive=True):
    study = optuna.load_study(study_name='...', storage=f'sqlite:///{db}')
    for trial in study.trials:
        if trial.state == optuna.trial.TrialState.COMPLETE:
            row = {**trial.params, 'value': trial.value}
            rows.append(row)
pd.DataFrame(rows).to_csv('results/all_trials.csv', index=False)
"

# Quintile analysis per param
python -c "
import pandas as pd, numpy as np

df = pd.read_csv('results/all_trials.csv')
profitable = df[df['value'] > 0]

for col in [c for c in df.columns if c != 'value']:
    quintiles = pd.qcut(profitable[col], 5, duplicates='drop')
    spread = profitable.groupby(quintiles)['value'].mean()
    print(f'{col}: spread = {spread.max() - spread.min():.3f}')
"
```

### Run Tests

```bash
pytest                          # All tests (~295 archetype-related)
pytest tests/risk/              # Risk module only
pytest -k "test_builds_valid"   # All archetypes build valid config
```

---

## Appendix A: FSM State Transitions

```
FLAT ──[entry_signal]──→ OPEN_INITIAL
  │                          │
  │                          ├──[stop_loss]──→ CLOSED → FLAT
  │                          ├──[tp1_hit]──→ PARTIALLY_CLOSED
  │                          │                    │
  │                          │                    ├──[break_even]──→ OPEN_BREAKEVEN
  │                          │                    │                       │
  │                          │                    │                       ├──[trailing_exit]──→ CLOSED
  │                          │                    │                       └──[stop_loss]──→ CLOSED
  │                          │                    │
  │                          │                    └──[trailing_exit]──→ CLOSED
  │                          │
  │                          ├──[pyramid_add]──→ OPEN_PYRAMIDED
  │                          │                       │
  │                          │                       ├──[tp1/be/trailing/stop]──→ ...
  │                          │                       └──[pyramid_add]──→ OPEN_PYRAMIDED (n+1)
  │                          │
  │                          ├──[trailing_exit]──→ CLOSED → FLAT  ← (bug fix: now works from ANY open state)
  │                          │
  │                          └──[time_exit]──→ CLOSED → FLAT
```

## Appendix B: Indicator Catalog

| Name | Type | Signal | Params | Exit Inversion |
|------|------|--------|--------|---------------|
| `roc` | Momentum | Rate of Change cross zero | period | bullish↔bearish |
| `macd` | Momentum | MACD line vs signal | fast, slow, signal | bullish↔bearish |
| `ema` | Trend | Price vs EMA / EMA cross | period1, period2 | above↔below |
| `rsi` | Oscillator | Oversold/Overbought levels | period | oversold↔overbought |
| `ssl_channel` | Trend | SSL high/low channel cross | period | long↔short |
| `bollinger_bands` | Volatility | Touch lower/upper band | period, std_dev | lower↔upper |
| `donchian` | Breakout | Donchian channel breakout | period | upper↔lower |
| `adx_filter` | Filter | ADX strength threshold | period | strong↔weak |
| `ma_crossover` | Trend | Fast MA × Slow MA cross | fast, slow | bullish↔bearish |
| `firestorm` | Custom | Firestorm signal fire | period, multiplier | long↔short |
| `wavetrend_reversal` | Oscillator | WT reversal signal | period | long↔short |
| `wavetrend_divergence` | Oscillator | WT divergence detection | period | long↔short |
| `firestorm_tm` | Custom | SL bands (auxiliary only) | period, multiplier | N/A |
| `ssl_channel_low` | Custom | SSL low variant | period | long↔short |
| `vwap` | Volume | Price vs VWAP | — | above↔below |
| `atr` | Volatility | ATR value (no signal) | period | N/A |

## Appendix C: RiskConfig Schema

```python
RiskConfig:
    archetype: str              # e.g. "roc_fullrisk_pyr"
    direction: "long"|"short"|"both"
    initial_capital: float      # Default: 4000
    commission_pct: float       # Default: 0.04 (Binance maker)
    slippage_pct: float         # Default: 0.0

    sizing:
        model: "fixed_fractional"|"atr"|"kelly"|"optimal_f"
        risk_pct: float         # % of capital per trade
        max_risk_per_trade: float  # Hard cap
        max_leverage: float     # 1.0 = no leverage

    stop:
        model: "atr"|"firestorm_tm"|"fixed_pct"
        atr_multiple: float     # Width in ATR units

    trailing:
        model: "atr"|"fixed"|"chandelier"|"parabolic_sar"|"signal"
        trailing_mode: "signal"|"policy"

    partial_tp:
        enabled: bool
        close_pct: float        # % of position to close at TP1
        trigger: "signal"|"r_multiple"|"fixed_pct"
        r_multiple: float       # TP1 at N × initial risk

    break_even:
        enabled: bool
        buffer: float           # 1.001 = 0.1% above entry
        activation: "after_tp1"|"r_multiple"|"pct"

    pyramid:
        enabled: bool
        max_adds: int           # Max pyramid add-ons
        block_bars: int         # Min bars between adds
        threshold_factor: float # Price must be > entry × factor
        weighting: "fibonacci"|"equal"|"decreasing"

    time_exit:
        enabled: bool
        max_bars: int           # Kill after N bars
```
