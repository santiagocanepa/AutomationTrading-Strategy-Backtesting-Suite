# AutomationTrading Suite

**A production-grade quantitative research platform for algorithmic trading strategy discovery, validation, and deployment.**

[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-1468%20passing-brightgreen.svg)](#engineering-quality)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Type Checked](https://img.shields.io/badge/mypy-strict-blue.svg)](#engineering-quality)
[![Code Style](https://img.shields.io/badge/ruff-passing-brightgreen.svg)](#engineering-quality)

This repository is a Python research stack designed around a single thesis: **finding strategies that survive out-of-sample requires more discipline than finding strategies that look good in-sample.** Most of the engineering investment lives in the anti-overfitting validation layer (CSCV/PBO + Deflated Sharpe + Hansen SPA + permutation tests) and the deterministic finite-state-machine risk engine that separates it from typical "trading bot" repositories.

> **Where to look first:** [`suitetrading/`](./suitetrading/) is the v2 platform — ~20,000 LOC of Python that comprises ~95% of the value of this repository. Sections below describe v2 in detail. The original Pine Script + Puppeteer suite (v1) is documented at the [bottom of this README](#historical-context-v1) for completeness.

### Research status

The research pipeline has been exercised end-to-end on US equities across three timeframes (15m / 1h / 4h) with **6M random discovery trials** as Phase 1 input. The downstream pipeline (Phase 2 structural analysis → Phase 3 Optuna refinement → Phase 4 portfolio construction → cross-validation suite) is operational and has produced a validated multi-TF, multi-archetype portfolio gated by:

- **CSCV/PBO** (Combinatorially Symmetric Cross-Validation)
- **Deflated Sharpe Ratio** (with trial-count adjustment for the full 2M-trial search)
- **Equity-curve correlation dedup** (effective N enforcement)
- **Slippage stress** (BPS sweep, retention curve)
- **Regime stress** (out-of-window replay under contrary regime)
- **Permutation null hypothesis** (FP rate of the optimization sub-pipeline on shuffled OHLCV)

Strategy-specific configurations and concrete portfolio results are intentionally **not** published in this public repository. The research framework itself, the validation harness, and the reproducible methodology are. See [`suitetrading/docs/methodology.md`](./suitetrading/docs/methodology.md) for the methodology narrative.

---

## Table of Contents

- [At a Glance](#at-a-glance)
- [Why This Exists](#why-this-exists)
- [Architecture](#architecture)
- [Core Capabilities](#core-capabilities)
  - [1. Data Infrastructure](#1-data-infrastructure)
  - [2. Indicator Engine](#2-indicator-engine)
  - [3. Risk Management Engine](#3-risk-management-engine)
  - [4. Backtesting Engine](#4-backtesting-engine)
  - [5. Anti-Overfitting Validation Stack](#5-anti-overfitting-validation-stack)
  - [6. Optimization Layer](#6-optimization-layer)
  - [7. Portfolio Construction](#7-portfolio-construction)
  - [8. Execution Bridge](#8-execution-bridge)
- [Research Methodology — 5-Phase Pipeline](#research-methodology--5-phase-pipeline)
- [Engineering Quality](#engineering-quality)
- [Quick Start](#quick-start)
- [Repository Structure](#repository-structure)
- [Documentation Index](#documentation-index)
- [Limitations and Honest Caveats](#limitations-and-honest-caveats)
- [Historical Context (v1)](#historical-context-v1)
- [License](#license)

---

## At a Glance

| Component | Quantity | Notes |
|-----------|----------|-------|
| **Source code (Python)** | 19,718 LOC | `suitetrading/src/` |
| **Test code** | 12,093 LOC | 856 test functions, 1,468 collected (with parametrization) |
| **Risk archetypes** | 121 | Configuration-as-code modules in `risk/archetypes/` |
| **Indicators** | 28 modules | Custom (Numba-accelerated), TA-Lib wrappers, cross-asset, futures-specific, macro |
| **Anti-overfitting tests** | 4 frameworks | CSCV/PBO, Deflated Sharpe, Hansen SPA, permutation null hypothesis |
| **Optimization backends** | 3 | Optuna (TPE/Random/NSGA-II/CMA-ES), DEAP NSGA-II, Random exhaustive |
| **Data sources** | 4 | Alpaca (US equities), Binance Vision (crypto), CCXT (live), FRED (macro) |
| **Documentation** | ~70 markdown files | Architecture, methodology, sprints, runbook, history, ADRs |

---

## Why This Exists

The vast majority of public algorithmic trading projects suffer from one or more of these failure modes:

1. **In-sample overfitting** disguised as performance (no walk-forward, no PBO test).
2. **Lookahead bias** in backtest semantics (signal evaluated with future data).
3. **Risk management as an afterthought** (fixed stop-loss, no FSM, no portfolio constraints).
4. **Data integrity assumed** (no validation, no resampling sanity checks, single-source).
5. **Optimization without validation** (Optuna run on the entire dataset; the "best" config is the one that overfits the most).

This platform addresses each one explicitly:

| Failure Mode | This Platform's Response |
|--------------|--------------------------|
| In-sample overfitting | CSCV/PBO + Deflated Sharpe + Hansen SPA + permutation null hypothesis (all 4 standard tests, applied as gates, not afterthoughts) |
| Lookahead bias | Frozen execution semantics (`docs/execution_semantics.md`): entry at bar close, gap-aware stops, deterministic FSM order of operations |
| Risk as afterthought | 564-line deterministic FSM (`risk/state_machine.py`) with immutable evaluation order: SL → TP1 partial → break-even → trailing → entry/pyramid |
| Data integrity | Multi-source validator, OHLCV consistency checks, Parquet partitioned storage with zstd compression, documented incident in `research_journal/` (Binance changed timestamp unit ms→μs in 2025, broke 41,796 partitions, parser was rewritten) |
| Optimization without validation | Methodology mandates Phase 1 random exhaustive (no optimizer) for unbiased structural discovery → Phase 3 Optuna + Walk-Forward Optimization with PBO/DSR/SPA gates only on the reduced space |

The methodology is grounded in *Advances in Financial Machine Learning* (López de Prado), Bailey & López de Prado 2017 (CSCV/PBO), Bailey et al. 2014 (Deflated Sharpe), and Hansen 2005 (Superior Predictive Ability test). These are not name-dropped — they are implemented as code paths that gate strategy promotion.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                         RESEARCH WORKFLOW                              │
└────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────┐                ┌──────────────────────────┐
    │  DATA SOURCES   │                │   INDICATOR ENGINE       │
    │                 │                │                          │
    │  • Binance      │                │  • Custom (Numba):       │
    │    Vision       │   ──────────▶  │    Firestorm, ASH,       │
    │  • CCXT         │                │    SSL, WaveTrend        │
    │  • Alpaca       │                │  • TA-Lib wrappers       │
    │  • FRED (macro) │                │  • Cross-asset, futures  │
    │                 │                │  • MTF resolution        │
    │                 │                │  • Signal combiner       │
    └─────────────────┘                │    (excluyente / vote)   │
            │                          └──────────────────────────┘
            ▼                                       │
    ┌─────────────────┐                             ▼
    │  ParquetStore   │              ┌──────────────────────────┐
    │  (zstd, monthly │              │     SIGNALS              │
    │   partitioned)  │              │  (booleans + metadata)   │
    └─────────────────┘              └──────────────────────────┘
                                                    │
                                                    ▼
                            ┌────────────────────────────────────────┐
                            │       BACKTESTING ENGINE               │
                            │  ┌──────────────┐  ┌────────────────┐  │
                            │  │ FSM mode     │  │ Vectorized     │  │
                            │  │ (full        │  │ mode           │  │
                            │  │  lifecycle)  │  │ (A/B speed)    │  │
                            │  └──────┬───────┘  └────────┬───────┘  │
                            │         │                   │          │
                            │         ▼                   ▼          │
                            │  ┌──────────────────────────────────┐  │
                            │  │  RISK ENGINE (deterministic FSM) │  │
                            │  │  SL → TP1 → BE → Trailing → PYR  │  │
                            │  │  + 121 archetypes (config)       │  │
                            │  │  + portfolio kill-switches       │  │
                            │  └──────────────────────────────────┘  │
                            │  ┌──────────────────────────────────┐  │
                            │  │  Slippage model (per symbol/TF)  │  │
                            │  │  Metrics (Sharpe/Sortino/Calmar) │  │
                            │  └──────────────────────────────────┘  │
                            └────────────────────────────────────────┘
                                                    │
                                                    ▼
            ┌──────────────────────────────────────────────────────────┐
            │            OPTIMIZATION + ANTI-OVERFITTING               │
            │                                                          │
            │  Phase 1: Random exhaustive (no optimizer)               │
            │  Phase 2: Post-hoc structural analysis                   │
            │  Phase 3: Optuna + Walk-Forward Optimization             │
            │           ↓ gates ↓                                      │
            │  CSCV/PBO  ·  Deflated Sharpe  ·  Hansen SPA  ·  Null    │
            └──────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
                        ┌──────────────────────────────────────┐
                        │    PORTFOLIO CONSTRUCTION            │
                        │  Markowitz / Risk Parity / Kelly /   │
                        │  Equal Weight / Shrinkage Kelly      │
                        │  + correlation-adjusted sizing       │
                        └──────────────────────────────────────┘
                                                    │
                                                    ▼
                        ┌──────────────────────────────────────┐
                        │    EXECUTION BRIDGE                  │
                        │    Alpaca paper trading API          │
                        └──────────────────────────────────────┘
```

The platform is **modular by design**: each layer has a typed interface, allowing components to be tested in isolation and replaced (e.g. swap optimizer, swap data source) without disturbing dependents.

---

## Core Capabilities

### 1. Data Infrastructure

**Location:** `suitetrading/src/suitetrading/data/`

- **`storage.py`** — `ParquetStore`: monthly/yearly partitioned Parquet store with zstd compression. Designed for multi-million-row OHLCV data with cheap range queries.
- **`downloader.py`** — Multi-source downloader abstraction.
- **`alpaca.py`, `fred.py`, `futures.py`** — Source-specific clients (US equities via Alpaca, macro series via FRED, perpetual futures via CCXT).
- **`resampler.py`** — Multi-timeframe resampling (1m → 15m, 1h, 4h, 1d, etc.) with documented edge cases.
- **`timeframes.py`** — Single source of truth for the 11 supported timeframes; eliminates parsing inconsistencies across the codebase.
- **`validator.py`** — OHLCV integrity checks: monotonic timestamps, no duplicate bars, no impossible bars (high < low), no nulls in critical columns.
- **`warmup.py`** — Indicator warmup management (avoid using indicator values before they have stabilized).

**Documented incident:** in 2025 Binance Vision changed its timestamp unit from milliseconds to microseconds, silently invalidating 41,796 of our partitions. The `research_journal/` documents the discovery, the root cause analysis, and the parser rewrite. This is an example of the kind of failure mode that destroys research integrity if not caught — and the kind of postmortem this platform documents publicly.

### 2. Indicator Engine

**Location:** `suitetrading/src/suitetrading/indicators/`

The indicator layer separates indicator *computation* from indicator *evaluation*. Each indicator returns a numerical series; a separate `signal_combiner` aggregates indicator outputs into entry/exit signals.

**Three categories of indicators:**

1. **Custom (Numba-accelerated, `custom/`):** Hand-implemented to match Pine Script semantics exactly.
   - **WaveTrend** (channel + reversal variants)
   - **Firestorm** (custom SuperTrend variant with TM bands)
   - **ASH** (Ashley Oscillator)
   - **SSL Channel**

2. **Standard (TA-Lib wrappers, `standard/`):** RSI, MACD, ADX, Bollinger Bands, MA Crossover, Donchian, ROC, OBV, Stoch RSI, Squeeze, Volume Anomaly. All use TA-Lib under the hood for correctness; the wrappers provide consistent interfaces and parameter handling.

3. **Domain-specific:**
   - **`cross_asset/`** — momentum indicators across assets (e.g. SPY/QQQ ratio).
   - **`futures/`** — basis, funding rate, open interest, taker volume.
   - **`regime.py`** — volatility regime detection.

**Signal combiner (`signal_combiner.py`):**

Two combination modes are supported:

- **`excluyente` mode** (faithful Pine Script replica): AND-chain of "excluding" indicators + ≥N "optional" indicators. Replicates the original strategy semantics from v1 exactly.
- **`majority vote` mode** (N-of-M): N indicators must agree out of M active.

A notable detail: there is an `_EXIT_INVERSION` lookup table that maps each indicator to *how* to invert its directional parameter when constructing the corresponding exit signal (e.g. `rsi.mode='oversold'` → `'overbought'` for the exit). This is the kind of thing that makes the difference between code that "works in a notebook" and code that holds together across a 38-indicator portfolio.

### 3. Risk Management Engine

**Location:** `suitetrading/src/suitetrading/risk/`

This is the core of the platform. Most public trading bot codebases use ad-hoc stop-loss logic with mutable state. This module uses a **deterministic finite-state machine with immutable snapshots and a frozen contract** for the order of operations within each bar.

**Key design choices:**

- **`state_machine.py` (564 LOC):** Per-bar state evaluation in a fixed order:
  ```
  1. Stop loss        (gap-aware: stop_price = min(stop_price, bar.open) for longs)
  2. TP1 partial      (configurable trigger: signal | r_multiple | fixed_pct)
  3. Break-even       (configurable activation: after_tp1 | r_multiple | pct)
  4. Trailing         (atr | chandelier | parabolic_sar; signal-mode or policy-mode)
  5. Entry / pyramid  (max_adds, block_bars, weighting: fibonacci | equal | decreasing)
  ```
  This order is *frozen* and documented in `docs/execution_semantics.md`. Changing it would silently invalidate years of backtests, so the contract is treated as a public API.

- **Immutable snapshots:** State transitions use `dataclasses.replace()` and `copy.deepcopy()` to avoid the entire class of bugs that come from mutating shared state during multi-position management.

- **121 archetypes (`risk/archetypes/`):** Pre-configured combinations of risk parameters for common trading styles. Each archetype is a small (~10–15 LOC) configuration module on top of `_fullrisk_base.py`. The high count is intentional: archetypes are configuration-as-code, not behavior. Examples:
  - `donchian_fullrisk_pyr_ftm` — Donchian breakout with full pyramid + Firestorm trailing stop
  - `roc_macd_mtf` — ROC + MACD multi-timeframe
  - `ichimoku_ssl_fullrisk_pyr` — Ichimoku + SSL with pyramid

- **Position sizing models (`position_sizing.py`):**
  - `fixed_fractional` — risk a fixed % of equity per trade
  - `atr` — size inversely proportional to ATR (volatility targeting)
  - `kelly` — fractional Kelly with configurable fraction
  - `optimal_f` — Ralph Vince's optimal_f

- **Portfolio-level constraints (`portfolio.py`, `portfolio_validation.py`):**
  - Drawdown kill-switch (auto-stop at configurable threshold)
  - Gross/net exposure caps
  - Portfolio heat (sum of risk across open positions)
  - Maximum correlated positions
  - Monte Carlo robustness simulation

### 4. Backtesting Engine

**Location:** `suitetrading/src/suitetrading/backtesting/`

**Two engine modes** for different research stages:

| Mode | Use Case | Throughput | Features |
|------|----------|------------|----------|
| **FSM mode** (`engine.py` + `risk/state_machine.py`) | Production-quality backtests with full lifecycle | ~63 backtests/sec single-thread | All FSM behavior, partial fills, pyramid, all 121 archetypes |
| **Vectorized/numpy mode** (`risk/vbt_simulator.py`) | A/B screening at scale | Significantly faster (vectorized) | Simplified semantics — useful for parameter sweeps where exact fills don't matter |

**Slippage model (`slippage.py`):**

Per-symbol, per-timeframe slippage table calibrated from historical execution data. Configurable multiplier for stress testing. The model is parameterized so you can re-evaluate any candidate pool under a more conservative slippage assumption without rerunning the entire pipeline.

**Metrics (`metrics.py`):**

Sharpe, Sortino, Calmar, max drawdown, profit factor, average trade, max consecutive losses, win rate, total return. All metrics annualized using the correct factor for the timeframe (1d → 252, 1h → 252×7, etc.).

**Frozen execution semantics (`docs/execution_semantics.md`):**

This document fixes the answer to questions like:
- "When does a market entry fill — bar close or next bar open?" (Answer: bar close.)
- "How is a stop priced when the bar gaps through the stop?" (Answer: `min(stop_price, bar.open)` for longs.)
- "What price is used for time-based exits?" (Answer: bar close at `max_bars`, with documented edge cases.)

Pinning these decisions in a versioned document (rather than scattered across the code) means backtests are *reproducible* and *auditable* across releases.

### 5. Anti-Overfitting Validation Stack

**Location:** `suitetrading/src/suitetrading/optimization/`

**This is the most important module in the repository for distinguishing valid edge from random noise.** Public trading repos usually have one or none of these tests. This platform has all four, applied as gates between research phases:

#### **CSCV/PBO — Combinatorially Symmetric Cross-Validation**

`anti_overfit.py:CSCVValidator`

Implements Bailey & López de Prado (2014) "The Probability of Backtest Overfitting." Splits OOS performance into all C(N, N/2) combinations to estimate the probability that the in-sample best is not the OOS best. **Output: PBO ∈ [0, 1].** Strategies are rejected at PBO > 0.20 (configurable).

#### **Deflated Sharpe Ratio**

`anti_overfit.py:deflated_sharpe_ratio`

Implements Bailey et al. (2014) "The Deflated Sharpe Ratio." Adjusts the observed Sharpe ratio for the number of trials, returns skewness, returns kurtosis, and series length. Reports the probability that the true Sharpe is greater than zero given the observed performance. **Output: probability ∈ [0, 1].** Strategies are rejected at DSR < 0.95.

#### **Hansen Superior Predictive Ability (SPA)**

`anti_overfit.py:HansenSPA`

Implements Hansen (2005) test for whether the best-performing strategy in a set has performance significantly above the others. Mitigates data-snooping bias from testing many models on the same data. **Output: p-value.** Configurable bootstrap with stationary block bootstrap.

#### **Permutation Null Hypothesis Test**

`null_hypothesis.py`

Permutes the OHLCV time series itself (not just the labels), runs the entire pipeline on the permuted data, and verifies that the discovery process produces no significant strategies on noise. This is a *meta-validation* of the pipeline itself: if the pipeline finds "great" strategies on shuffled data, the pipeline is overfitting and the strategies it finds on real data are suspect.

#### **AntiOverfitPipeline** (orchestrator)

Sequentially applies CSCV → DSR → (optional) Hansen SPA. Strategies that fail any gate are eliminated. Output is a typed `AntiOverfitResult` dataclass with all intermediate metrics for inspection.

### 6. Optimization Layer

**Location:** `suitetrading/src/suitetrading/optimization/`

- **`optuna_optimizer.py`** — Bayesian optimization with TPE, Random, NSGA-II, and CMA-ES samplers. SQLite study persistence (resume after interruption).
- **`deap_optimizer.py`** — DEAP NSGA-II for explicit Pareto-frontier exploration of multi-objective problems.
- **`walk_forward.py`** — Rolling and anchored walk-forward optimization with configurable train/test windows.
- **`rolling_validation.py`** — Rolling regime-based validation (split data by volatility quintile or trend strength).
- **`feature_importance.py`** — SHAP-based feature importance with proper handling of correlated features.
- **`parallel.py`** — Process-pool parallel execution with backpressure.

**Methodology gate:** Optuna is **not** used in Phase 1 (random exhaustive discovery). The reason is methodologically explicit in `docs/methodology.md`: a Bayesian optimizer applied to ~10^16 combinations samples 0.000000002% of the space, leading to local-optimum bias. Phase 1 must be unbiased random sampling. Optuna only enters in Phase 3 on the *reduced* space identified by Phase 2 structural analysis.

### 7. Portfolio Construction

**Location:** `suitetrading/src/suitetrading/risk/portfolio_optimizer.py` and related

Five weight-allocation methods, all evaluated empirically against the holdout period:

| Method | Description | When to Use |
|--------|-------------|-------------|
| **Equal Weight** | 1/N each | Robust baseline; minimal overfitting risk |
| **Inverse Volatility** | Weight ∝ 1/σ | Volatility-targeted exposure |
| **Markowitz Max-Sharpe** | Solve for weights maximizing portfolio Sharpe | Highest in-sample; requires honest covariance |
| **Markowitz Capped** | Max-Sharpe with per-strategy weight cap (e.g. 10%) | Recommended default — limits over-concentration |
| **Risk Parity** | Equal risk contribution per strategy | Robust if returns dispersion is large |
| **Min Variance** | Solve for minimum portfolio variance | Conservative; not recommended unless variance is the explicit objective |
| **Fractional Kelly** | Kelly with fraction adjustment for parameter uncertainty | Aggressive; requires honest Sharpe estimates |

Selection is data-driven: the pipeline runs all methods, reports each one's holdout Sharpe with bootstrap 95% confidence intervals, and surfaces the trade-off between expected Sharpe and concentration (HHI / effective N).

### 8. Execution Bridge

**Location:** `suitetrading/src/suitetrading/execution/`

Bridge to **Alpaca** for paper trading. Translates portfolio signals to order flow with proper handling of:
- Market hours
- Position size rounding to lot constraints
- Order rejection retry logic
- State reconciliation between local positions and broker positions

Live trading requires additional production hardening (monitoring, alerting, killswitch wiring) that is documented but intentionally not yet wired in the public repository.

---

## Research Methodology — 5-Phase Pipeline

The platform implements an **iterative, gated research pipeline**. Each phase has a defined input, output, and pass criterion. Phases are not independent — they form a feedback loop.

```
┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 1 — RANDOM EXHAUSTIVE DISCOVERY                               │
│  Tool: scripts/run_random_v9.py                                      │
│  Method: Uniform random sampling over the full parameter space       │
│  Why no optimizer: ~10^16 combinations; an optimizer would sample    │
│                    <10^-9% of space and converge to local optima     │
│  Output: ~2M trials per study (asset × direction)                    │
│  Stored: artifacts/exhaustive_v9_{15m,1h,4h}/parquet/               │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 2 — POST-HOC STRUCTURAL ANALYSIS                              │
│  Tool: scripts/analyze_discovery.py + ad-hoc analysis                │
│  Method: pandas + fixed-effects regression + stress testing on the   │
│          random discovery dataset                                    │
│  Output: identification of which structural features (state,         │
│          timeframe, parameter range) produce viable Sharpe;          │
│          high-quality (HQ) trial subset                              │
│  Pass criterion: HQ pool ≥ 200 candidates with consistent patterns   │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 3 — OPTUNA WFO + ANTI-OVERFITTING GATES                       │
│  Tool: scripts/run_discovery.py + scripts/cross_validate_native.py   │
│  Method: Optuna (TPE/NSGA-II) on the reduced HQ space, with          │
│          walk-forward optimization; anti-overfit gates applied       │
│  Gates:                                                              │
│    • PBO < 0.20  (Combinatorially Symmetric Cross-Validation)       │
│    • DSR > 0.95  (Deflated Sharpe Ratio probability)                │
│    • SPA p-val verified  (Hansen Superior Predictive Ability)        │
│    • Trades ≥ 300                                                    │
│  Output: validated finalists with full anti-overfit report           │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 4 — PORTFOLIO CONSTRUCTION + VALIDATION                       │
│  Tools: build_candidate_pool.py → portfolio_walkforward.py           │
│         → validate_portfolio.py → run_portfolio.py                  │
│  Method: greedy minimum-correlation pool selection, multi-method     │
│          weight allocation, ensemble PBO/DSR/SPA, ruin probability   │
│  Output: production_portfolio.json with weight assignments           │
└──────────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 5 — PAPER TRADING + LIVE                                      │
│  Tool: scripts/run_paper_portfolio.py                                │
│  Bridge: Alpaca paper API (live wiring documented but not yet        │
│          activated in this public repository)                        │
└──────────────────────────────────────────────────────────────────────┘
```

**Holdout discipline:** the methodology mandates separating a chronological holdout window (e.g. last 6 months) that is *never seen* during Optuna optimization. The holdout is evaluated **once** at the end of Phase 4. If the holdout-vs-IS Sharpe degradation exceeds 30%, the pipeline is reconsidered (not the parameters — the methodology).

For the full methodology including non-negotiable rules and decision criteria, see [`suitetrading/docs/methodology.md`](./suitetrading/docs/methodology.md).

---

## Engineering Quality

### Type Safety
- `from __future__ import annotations` everywhere
- Strict mypy configuration in `pyproject.toml`
- Pydantic v2 schemas for all configurations (`risk/contracts.py`)
- Dataclasses with `frozen=True` for immutable state

### Code Style
- Ruff with extended rule set (`E, F, W, I, N, UP, B, A, SIM`)
- Zero `TODO` / `FIXME` markers in `src/`
- Consistent naming, no magic strings (constants in `config/`)

### Testing
- **856 test functions** (1,468 collected with parametrization), `tests/` mirrors `src/` structure
- **Regression fixtures** in `tests/fixtures/`: frozen JSON snapshots of OHLCV inputs + parameters + expected outputs. Any change that modifies a numerical output must update fixtures explicitly with justification — prevents silent semantic regressions.
- **Property-based tests** for core invariants (FSM order, no double fills, position sizing bounds)
- **Integration tests** for end-to-end pipeline coherence (`tests/integration/`)

### Reproducibility
- `RunConfig` with deterministic SHA256 hash for full reproducibility
- All randomness seeded explicitly
- ParquetStore with content-addressable file naming

### Dependency Hygiene
- `pyproject.toml` with separate extras: `dev`, `data`, `optimization` — install only what you need
- Pinned production dependencies; flexible dev dependencies

---

## Quick Start

### Requirements
- Python 3.14+
- macOS / Linux (Windows untested but should work)
- ~10 GB disk for typical data + artifacts

### Installation
```bash
git clone <repo-url>
cd AutomationTrading-Strategy-Backtesting-Suite/suitetrading
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,data,optimization]"
```

### Verify installation
```bash
pytest tests/ -q --no-header
# Expected: 1,468 tests collected, all pass in ~30 seconds
```

### First run — single backtest
```bash
python scripts/download_data.py --symbol SPY --exchange alpaca --timeframe 1h
python -c "
from pathlib import Path
import pandas as pd
from suitetrading.data.storage import ParquetStore
from suitetrading.backtesting._internal.schemas import BacktestDataset
from suitetrading.config.archetypes import get_entry_indicators
from suitetrading.optimization._internal.objective import BacktestObjective, EXHAUSTIVE_RISK_SPACE
from suitetrading.data.resampler import OHLCVResampler

store = ParquetStore(base_dir=Path('data/raw'))
df = store.read('alpaca', 'SPY', '1m')
ohlcv = OHLCVResampler().resample(df, '1h', base_tf='1m')
ds = BacktestDataset(exchange='alpaca', symbol='SPY', base_timeframe='1h', ohlcv=ohlcv)
obj = BacktestObjective(
    dataset=ds,
    indicator_names=list(get_entry_indicators('rich_stock')),
    archetype='rich_stock',
    direction='long',
    metric='sharpe',
    risk_search_space=EXHAUSTIVE_RISK_SPACE,
    mode='fsm',
)
result = obj.run_single({
    'firestorm__period': 14,
    'firestorm____state': 'Opcional',
    'firestorm____timeframe': 'grafico',
    'num_optional_required': 1,
    'stop__atr_multiple': 2.0,
    'partial_tp__r_multiple': 1.0,
    'partial_tp__close_pct': 30.0,
})
print(f'Sharpe: {result[\"metrics\"][\"sharpe\"]:.3f}')
print(f'Trades: {result[\"metrics\"][\"total_trades\"]}')
print(f'MDD%:   {result[\"metrics\"][\"max_drawdown_pct\"]:.2f}')
"
```

### Run the full discovery pipeline
```bash
# Phase 1: random exhaustive (overnight for production-grade run)
bash scripts/run_exhaustive_v9.sh

# Phase 2-3: anti-overfit validation
python scripts/run_discovery.py --config config/discovery.yaml
python scripts/cross_validate_native.py --pool artifacts/discovery/...

# Phase 4: portfolio construction
python scripts/build_candidate_pool.py --pool ...
python scripts/portfolio_walkforward.py
python scripts/run_portfolio.py
```

### Operational scripts
```bash
scripts/audit_raw_data.py          # data integrity check
scripts/benchmark_backtesting.py   # measure backtest throughput
scripts/run_null_hypothesis.py     # permutation test for pipeline overfitting
scripts/replay_with_slippage.py    # re-evaluate finalists under conservative slippage
scripts/run_paper_portfolio.py     # bridge to Alpaca paper account
```

---

## Repository Structure

```
.
├── README.md                                  ← This file (v2-focused)
├── LICENSE                                    ← MIT
├── suitetrading/                              ← v2: production research platform
│   ├── README.md                              ← Detailed v2 technical docs
│   ├── pyproject.toml                         ← Dependencies + tooling config
│   ├── src/suitetrading/                      ← Source (19,718 LOC)
│   │   ├── data/                              ← ParquetStore, downloaders, validators
│   │   ├── indicators/                        ← Custom + standard + cross-asset + futures
│   │   ├── risk/                              ← FSM + 121 archetypes + portfolio constraints
│   │   ├── backtesting/                       ← Engine (FSM + vectorized) + metrics
│   │   ├── optimization/                      ← Optuna + DEAP + WFO + anti-overfit gates
│   │   ├── execution/                         ← Alpaca paper bridge
│   │   └── config/                            ← Archetypes registry + settings
│   ├── tests/                                 ← 856 functions / 1,468 collected
│   ├── scripts/                               ← CLI tools (~30 scripts)
│   ├── docs/                                  ← Architecture, methodology, modules, ADRs
│   ├── config/                                ← YAML configs + production_portfolio.json
│   ├── artifacts/                             ← Discovery outputs (Parquet)
│   └── data/                                  ← Cached OHLCV data
│
└── AutomationTrading-Strategy-Backtesting-Suite/   ← v1: TradingView + Puppeteer
    ├── Indicator Strategy of TradingView/     ← Pine Script (15+ indicators, 1,258 LOC)
    ├── Generate Combination Python/           ← Parameter combinatorial generator
    └── Puppeteer Automation Backtesting/      ← Browser automation (525 LOC TypeScript)
```

---

## Documentation Index

The platform ships with extensive documentation in `suitetrading/docs/`:

| Document | Purpose |
|----------|---------|
| [`docs/architecture.md`](./suitetrading/docs/architecture.md) | Module structure, data flow, design patterns |
| [`docs/methodology.md`](./suitetrading/docs/methodology.md) | The 5-phase pipeline + non-negotiable rules |
| [`docs/setup.md`](./suitetrading/docs/setup.md) | Installation, data services, first execution |
| [`docs/history.md`](./suitetrading/docs/history.md) | Pipeline iteration history (v1 → v9) |
| [`docs/modules/data/`](./suitetrading/docs/modules/data/) | Per-module deep dives |
| [`docs/modules/indicators/`](./suitetrading/docs/modules/indicators/) | |
| [`docs/modules/risk/`](./suitetrading/docs/modules/risk/) | |
| [`docs/modules/backtesting/`](./suitetrading/docs/modules/backtesting/) | |
| [`docs/modules/optimization/`](./suitetrading/docs/modules/optimization/) | |
| [`docs/modules/portfolio/`](./suitetrading/docs/modules/portfolio/) | |
| [`docs/modules/execution/`](./suitetrading/docs/modules/execution/) | |

Sprint completion reports, technical specs, and historical decisions are archived in `suitetrading/docs/archive/`.

---

## Limitations and Honest Caveats

In keeping with the methodology of explicit rigor, this section documents what the platform **does not yet do** or where conclusions should be qualified:

1. **No live trading wiring.** The Alpaca bridge is wired for paper. Live trading requires production hardening (monitoring, alerting, kill-switch dashboards, broker reconciliation jobs) that is intentionally out of scope for the public repository.

2. **Slippage model is per-symbol-per-TF lookup, not non-linear.** A more realistic model would account for order size, volatility regime, and time-of-day. The conservative path is to re-validate pre-deployment with `scripts/replay_with_slippage.py` using a stress-test multiplier.

3. **Borrow fees not modeled inside the engine.** Short positions in equities incur borrow costs (typically 0.5–10% APR, sometimes higher for hard-to-borrow names). The engine does not subtract them per-trade; instead, the validation harness estimates a per-config haircut post-hoc using IBKR-style rates per symbol. For typical names the median Sharpe haircut is small, but specific hard-to-borrow names (e.g. high-borrow-cost tech) require a config-level review before live deployment.

4. **Discovery pipeline is single-threaded per study.** Multi-process parallelism is at the *study* level (one process per asset × direction), not within-study. For machines with many cores, this leaves throughput on the table. Documented as a future optimization.

5. **Holdout is "parcial" not "genuine"** in the strict sense. The high-quality candidate pool was filtered using statistics computed over the full dataset (including the period later used as holdout). True out-of-sample evaluation would require regenerating the discovery dataset excluding the holdout window. The current methodology compensates by validating Optuna parameter refinement only on pre-holdout data, with explicit degradation criteria.

6. **Headline performance numbers (e.g. `oos_sharpe_ann=4.83` in `production_portfolio.json`) require defense.** Sharpe > 4 OOS is alarmingly good and warrants careful examination of: (a) the time window, (b) the regime, (c) the slippage assumption, (d) whether selection bias from post-LOO pruning inflates the number. The configuration documents these assumptions but a reviewer should verify them independently before staking capital.

7. **Single git commit visible at HEAD on first clone in some configurations.** The repository has 60+ commits; if you see only one, check `git log --all` and verify branches.

These limitations are intentionally surfaced because the alternative — burying them in docs that no one reads — is exactly the failure mode this platform exists to oppose.

---

## Historical Context (v1)

Before the v2 Python rewrite, this project began as a Pine Script + Puppeteer automation suite that ran systematic combinatorial backtests directly on TradingView. The v1 stack:

- **Pine Script (1,258 LOC):** 15+ indicators with configurable combination logic
- **Python combinatorial generator (~656 LOC):** parameter space enumeration
- **Puppeteer / TypeScript (525 LOC):** headless browser automation to drive TradingView's strategy tester

The v1 results validated the conceptual approach: systematic enumeration over indicator combinations finds patterns that ad-hoc tuning misses. These backtest visualizations come from real campaigns executed by the v1 stack:

![Results Overview](https://github.com/user-attachments/assets/b010edf3-5c6f-4c78-9410-bbe50daf1c42)
![Strategy Performance](https://github.com/user-attachments/assets/9553eb5f-d0ba-485a-99c0-e7f8f2a994f9)
![Detailed Metrics](https://github.com/user-attachments/assets/8a423216-0c8e-4e37-86bb-aacafb8d35f3)
![Equity Curves](https://github.com/user-attachments/assets/39c03c50-b0b7-42fb-b6ed-0861bab68386)

The transition to v2 was driven by hard limits in the v1 stack:
- TradingView's strategy tester does not support walk-forward optimization
- Pine Script cannot host a deterministic FSM with configurable evaluation order
- No way to apply CSCV/PBO or Deflated Sharpe to TradingView results
- Throughput limited by browser automation (~1 backtest/minute via Puppeteer vs. ~63/sec native)
- Anti-overfitting validation impossible to run at scale

The v1 source remains in this repository for reference and is fully functional. New research and development happens exclusively in v2.

---

## License

MIT — see [LICENSE](./LICENSE).

---

## Contact and Contributing

This is a personal research repository. Issues and pull requests are welcome but are evaluated against the methodology rigor that the platform exists to enforce: changes that affect numerical outputs require updated regression fixtures with justification; changes to the FSM order of operations require an architecture decision record (ADR); changes to the methodology require explicit owner approval.

For questions about specific modules, the per-module documentation in `suitetrading/docs/modules/` is the authoritative reference.
