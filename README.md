# AutomationTrading Strategy & Backtesting Suite

A comprehensive algorithmic trading research platform that evolved from TradingView Puppeteer automation into a full-stack Python backtesting and optimization engine.

---

## 📊 Strategy Results (v1)

These visualizations come from real backtesting campaigns executed on TradingView using the original Puppeteer automation suite. They represent the tangible, verified outcomes of systematic combinatorial strategy testing:

![Results Overview](https://github.com/user-attachments/assets/b010edf3-5c6f-4c78-9410-bbe50daf1c42)
![Strategy Performance](https://github.com/user-attachments/assets/9553eb5f-d0ba-485a-99c0-e7f8f2a994f9)
![Detailed Metrics](https://github.com/user-attachments/assets/8a423216-0c8e-4e37-86bb-aacafb8d35f3)
![Equity Curves](https://github.com/user-attachments/assets/39c03c50-b0b7-42fb-b6ed-0861bab68386)

---

## Repository Structure

This repository contains **two generations** of the trading suite:

```
├── suitetrading/                              ← v2: Python backtesting suite (START HERE)
│   ├── src/suitetrading/                      # Source code
│   │   ├── data/                              # Data infrastructure
│   │   ├── indicators/                        # 12 indicators (6 custom + 6 TA-Lib)
│   │   ├── risk/                              # Risk engine (FSM + archetypes)
│   │   ├── backtesting/                       # Vectorized backtesting
│   │   └── optimization/                      # Optuna + anti-overfitting
│   ├── tests/                                 # 647 tests
│   ├── scripts/                               # CLI tools
│   └── README.md                              # ⭐ Full technical documentation
│
└── AutomationTrading-Strategy-Backtesting-Suite/   ← v1: TradingView + Puppeteer
    ├── Indicator Strategy of TradingView/     # Pine Script (15+ indicators)
    ├── Generate Combination Python/           # Parameter space generator
    └── Puppeteer Automation Backtesting/      # Browser automation
```

---
# SuiteTrading v2

**Algorithmic Trading Suite** — vectorized backtesting, multi-layer risk management, Bayesian optimization with anti-overfitting filters, and production-ready data infrastructure.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-647%20passed-brightgreen.svg)](#testing)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../AutomationTrading-Strategy-Backtesting-Suite/LICENSE)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
  - [Requirements](#requirements)
  - [Installation](#installation)
  - [First Run](#first-run)
- [Modules](#modules)
  - [Data Infrastructure](#1-data-infrastructure)
  - [Indicator Engine](#2-indicator-engine)
  - [Risk Management Engine](#3-risk-management-engine)
  - [Backtesting Core](#4-backtesting-core)
  - [Optimization & Anti-Overfitting](#5-optimization--anti-overfitting)
- [Scripts Reference](#scripts-reference)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Usage Examples](#usage-examples)
  - [Download Data](#download-data)
  - [Run a Single Backtest](#run-a-single-backtest)
  - [Run a Grid Search](#run-a-grid-search)
  - [Walk-Forward Optimization](#walk-forward-optimization)
  - [Risk Lab Batch](#risk-lab-batch)
  - [Indicator Validation](#indicator-validation)
- [Development Roadmap](#development-roadmap)
- [Relationship with v1](#relationship-with-v1-automationtrading-strategy-backtesting-suite)

---

## Overview

SuiteTrading v2 is a ground-up rewrite of the original [AutomationTrading-Strategy-Backtesting-Suite](../AutomationTrading-Strategy-Backtesting-Suite/), designed to move from TradingView-dependent Puppeteer automation to a fully self-contained Python trading research platform.

### Key Capabilities

| Area | v1 (Puppeteer Suite) | v2 (SuiteTrading) |
|------|--------|---------|
| **Backtesting** | TradingView UI via Puppeteer | Vectorized in-memory engine (63+ bt/sec) |
| **Data** | TradingView charts | Binance Vision + CCXT + Alpaca, Parquet store |
| **Indicators** | Pine Script only | Python replicas + TA-Lib, validated vs TradingView |
| **Risk Management** | Basic TradingView strategy settings | Full FSM: pyramiding, trailing, partial TP, break-even, kill switch |
| **Optimization** | Manual grid via JSON combinations | Optuna (TPE/NSGA-II), Walk-Forward, CSCV, DSR, SPA |
| **Anti-Overfitting** | None | CSCV + Deflated Sharpe Ratio + Hansen's SPA |
| **Parallelism** | Sequential Puppeteer | `ProcessPoolExecutor` across all CPU cores |

### What v1 Did Well (and We Keep)

The v1 suite proved that systematic combinatorial testing works. Its Pine Script strategy with 15+ configurable indicators, the Python combination generator, and Puppeteer automator produced real results — the images in the [main README](../AutomationTrading-Strategy-Backtesting-Suite/README.md) show the tangible outcomes of that process. **v2 doesn't replace those results**; it provides the infrastructure to reproduce and extend them at scale, without TradingView dependency.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        SuiteTrading v2                          │
├─────────────┬───────────────┬──────────────┬───────────────────┤
│   Data      │  Indicators   │    Risk      │   Optimization    │
│ ─────────── │ ───────────── │ ──────────── │ ───────────────── │
│ Binance     │ 6 Custom      │ FSM Engine   │ Optuna Bayesian   │
│ Vision      │ (Pine replicas│ 4 Sizers     │ DEAP NSGA-II      │
│ CCXT        │  + validated) │ 6 Exit       │ Walk-Forward      │
│ Alpaca      │ 6 TA-Lib      │   Policies   │ CSCV (PBO)        │
│ Parquet/    │ Multi-TF      │ 6 Archetypes │ Deflated Sharpe   │
│ ZSTD Store  │ Signal        │ Portfolio    │ Hansen SPA        │
│ Resampler   │   Combiner    │   Limits     │ Feature Importance│
│ Validator   │               │              │ Parallel Executor │
├─────────────┴───────────────┴──────────────┴───────────────────┤
│                     Backtesting Engine                          │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────┐ │
│  │ Grid     │  │ Dual Runner  │  │ Metrics    │  │ Reporting│ │
│  │ Builder  │  │ (FSM+Simple) │  │ Engine     │  │ (Plotly) │ │
│  └──────────┘  └──────────────┘  └────────────┘  └──────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Data flow:** Raw exchange data → Parquet store → Resampler → Indicator engine → Signal combiner → Backtest engine (FSM or simple runner) → Metrics → Optimization loop → Anti-overfit filters → Final report.

---

## Quick Start

### Requirements

- **Python 3.11+** (tested on 3.11, 3.12, 3.13, 3.14)
- **TA-Lib C library** must be installed before pip install:
  ```bash
  # macOS
  brew install ta-lib

  # Ubuntu/Debian
  sudo apt-get install libta-lib-dev

  # Arch
  sudo pacman -S ta-lib
  ```

### Installation

```bash
cd suitetrading

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# Install core + dev dependencies
pip install -e ".[dev]"

# Install data download support (CCXT, httpx)
pip install -e ".[data]"

# Install optional optimization extensions (DEAP, XGBoost, SHAP, arch)
pip install -e ".[optimization]"

# Or install everything at once
pip install -e ".[dev,data,optimization]"
```

### First Run

```bash
# 1. Verify installation — run the test suite
pytest

# 2. Download historical data (BTC, ETH, SOL from Binance)
python scripts/download_data.py --symbols BTCUSDT ETHUSDT SOLUSDT

# 3. Cross-validate resampled vs native exchange data
python scripts/cross_validate_native.py --symbols BTCUSDT --days 30

# 4. Run your first risk lab (batch backtesting)
python scripts/run_risk_lab.py --symbols BTCUSDT --timeframes 1h 4h
```

---

## Modules

### 1. Data Infrastructure

**Module:** `suitetrading.data`

The data layer provides a complete pipeline from exchange download to analysis-ready DataFrames.

#### Components

| Class | Purpose |
|-------|---------|
| `BinanceVisionDownloader` | Bulk CSV download from data.binance.vision (monthly archives) |
| `CCXTDownloader` | Any exchange via CCXT async API (current month, any timeframe) |
| `DownloadOrchestrator` | Coordinates both downloaders + validates + stores |
| `ParquetStore` | Columnar storage with ZSTD compression, monthly/yearly partitions |
| `OHLCVResampler` | Single source of truth for timeframe resampling (1m base → any target) |
| `DataValidator` | Validates OHLCV integrity: gaps, duplicates, negative prices, volume anomalies |
| `WarmupCalculator` | Computes warmup bars needed per indicator/timeframe combination |

#### Key Design Decisions

- **1-minute base timeframe**: All data is stored at 1m granularity, then resampled on demand. This ensures consistency across all timeframes and eliminates discrepancies from different exchange aggregation methods.
- **Parquet + ZSTD**: Columnar format with high compression ratio. Monthly partitions for intraday (≤4h), yearly for daily+.
- **Binance Vision + CCXT hybrid**: Historical bulk from Binance Vision (fast, free) + current month via CCXT API (real-time).
- **Auto-detection of timestamp formats**: Handles Binance Vision's `ms` → `us` switch (starting 2025 archives) transparently.

#### Storage Layout

```
data/raw/binance/
├── BTCUSDT/
│   └── 1m/
│       ├── 2017-08.parquet
│       ├── 2017-09.parquet
│       ├── ...
│       └── 2026-03.parquet
├── ETHUSDT/
│   └── 1m/
└── SOLUSDT/
    └── 1m/
```

#### Usage

```python
from suitetrading.data import ParquetStore, OHLCVResampler

store = ParquetStore(base_dir="data/raw")
df_1m = store.read("binance", "BTCUSDT", "1m")       # Full history
df_1h = OHLCVResampler().resample(df_1m, "1h")        # Resample to 1h
df_4h = OHLCVResampler().resample(df_1m, "4h")        # Resample to 4h
```

---

### 2. Indicator Engine

**Module:** `suitetrading.indicators`

12 indicators organized in two groups: 6 custom Pine Script replicas and 6 standard TA-Lib wrappers.

#### Indicator Registry

| Key | Class | Type | Description |
|-----|-------|------|-------------|
| `firestorm` | `Firestorm` | Custom | Pine Script Firestorm indicator replica |
| `firestorm_tm` | `FirestormTM` | Custom | Firestorm Trend Mode variant |
| `ssl_channel` | `SSLChannel` | Custom | SSL Channel crossover system |
| `ssl_channel_low` | `SSLChannelLow` | Custom | SSL Channel Low variant |
| `wavetrend_reversal` | `WaveTrendReversal` | Custom | WaveTrend divergence-based reversal |
| `wavetrend_divergence` | `WaveTrendDivergence` | Custom | WaveTrend divergence detector |
| `rsi` | `RSI` | TA-Lib | Relative Strength Index |
| `ema` | `EMA` | TA-Lib | Exponential Moving Average crossover |
| `macd` | `MACD` | TA-Lib | MACD signal line cross |
| `atr` | `ATR` | TA-Lib | Average True Range (used by risk engine) |
| `vwap` | `VWAP` | TA-Lib | Volume Weighted Average Price |
| `bollinger_bands` | `BollingerBands` | TA-Lib | Bollinger Bands squeeze/expansion |

#### Indicator Interface

Every indicator implements a standard interface:

```python
from suitetrading.indicators.base import Indicator

class MyIndicator(Indicator):
    def compute(self, df: pd.DataFrame, **params) -> pd.Series:
        """Return boolean Series: True = signal active."""
        ...

    def params_schema(self) -> dict[str, dict]:
        """Return tuneable parameter ranges for optimization."""
        return {
            "period": {"type": "int", "min": 5, "max": 50, "default": 14},
        }
```

#### Signal Combination Logic

The signal combiner replicates the Pine Script Excluyente/Opcional/Desactivado pattern:

```python
from suitetrading.indicators.signal_combiner import combine_signals
from suitetrading.indicators.base import IndicatorState

# All "Excluyente" indicators must be True AND
# at least N "Opcional" indicators must be True
combined = combine_signals(
    signals={"ssl": ssl_signal, "rsi": rsi_signal, "wavetrend": wt_signal},
    states={
        "ssl": IndicatorState.EXCLUYENTE,
        "rsi": IndicatorState.OPCIONAL,
        "wavetrend": IndicatorState.OPCIONAL,
    },
    num_optional_required=1,
)
```

#### Multi-Timeframe Support

```python
from suitetrading.indicators.mtf import resample_ohlcv, align_to_base

# Compute indicator on higher timeframe, align back to base
df_4h = resample_ohlcv(df_1m, "4h")
signal_4h = indicator.compute(df_4h, period=14)
signal_aligned = align_to_base(signal_4h, df_1m.index)
```

#### Visual Validation

Custom indicators were visually validated against TradingView charts. The SSL Channel on BTCUSDT 1h was confirmed to match exactly via HTML exports in `artifacts/indicator_validation/`.

---

### 3. Risk Management Engine

**Module:** `suitetrading.risk`

A complete position lifecycle management system built around a finite state machine (FSM).

#### Position State Machine

```
    FLAT ──entry_filled──► OPEN_INITIAL
       ▲                        │
       │                   ┌────┴────┐
       │               pyramid   break_even
       │                   │         │
       │            OPEN_PYRAMIDED  OPEN_BREAKEVEN
       │                   │         │
       │                   └────┬────┘
       │                   trailing
       │                        │
       │               OPEN_TRAILING
       │                        │
       │                 ┌──────┴──────┐
       │            partial_tp    exit_signal
       │                 │            │
       │         PARTIALLY_CLOSED    │
       │                 │            │
       └────────────CLOSED◄───────────┘
```

**Evaluation priority per bar (immutable):**
1. Stop-loss
2. Partial take-profit (TP1)
3. Break-even activation
4. Trailing exit
5. New entry / pyramid add

#### Position Sizing Models

| Model | Class | Description |
|-------|-------|-------------|
| Fixed Fractional | `FixedFractionalSizer` | Risk a fixed % of equity per trade |
| ATR-Based | `ATRSizer` | Size = `equity × risk_pct / (ATR × multiplier)` |
| Kelly Criterion | `KellySizer` | Optimal fraction based on win rate and payoff ratio |
| Optimal f | `OptimalFSizer` | Ralph Vince's Optimal f position sizing |

#### Exit Policies

| Policy | Class | Description |
|--------|-------|-------------|
| Break-Even | `BreakEvenPolicy` | Move stop to entry + buffer after R-multiple target |
| Fixed Trailing | `FixedTrailingStop` | Trail by fixed percentage offset |
| ATR Trailing | `ATRTrailingStop` | Trail by ATR multiple |
| Chandelier Exit | `ChandelierExit` | Highest high - ATR×mult (classic Chuck LeBeau) |
| Parabolic SAR | `ParabolicSARStop` | Wilder's parabolic SAR as trailing stop |
| Signal Exit | `SignalTrailingExit` | Exit on indicator signal reversal |

#### Risk Archetypes (Presets)

Archetypes are preset composers — they assemble a complete `RiskConfig` from sensible defaults for a particular trading style:

| Archetype | Key | Description |
|-----------|-----|-------------|
| Trend Following | `trend_following` | Wide stops, aggressive trailing, pyramiding, no early TP |
| Mean Reversion | `mean_reversion` | Tight stops, quick partial TP, no pyramiding |
| Mixed | `mixed` | Moderate stops, partial TP + trailing |
| Legacy Firestorm | `legacy_firestorm` | Replicates v1 Pine Script risk parameters |
| Pyramidal Scaling | `pyramidal` | Up to 5 add-on entries, decreasing size |
| Grid DCA | `grid_dca` | Dollar-cost average into positions at grid levels |

#### Usage

```python
from suitetrading.risk.archetypes import get_archetype

# Get a preset and optionally override specific parameters
risk_config = get_archetype("trend_following").build_config(
    stop={"atr_multiple": 2.5},
    pyramid={"max_adds": 2},
)

# Or build from scratch
from suitetrading.risk.contracts import RiskConfig

risk_config = RiskConfig(
    archetype="custom",
    initial_capital=10_000,
    sizing={"model": "fixed_fractional", "risk_pct": 1.0},
    stop={"model": "atr", "atr_multiple": 2.0},
    trailing={"model": "atr", "atr_multiple": 1.5},
)
```

---

### 4. Backtesting Core

**Module:** `suitetrading.backtesting`

Vectorized backtesting engine with dual-runner architecture, achieving 63+ backtests/second throughput.

#### Components

| Class | Purpose |
|-------|---------|
| `BacktestEngine` | Main orchestrator for single and batch runs |
| `ParameterGridBuilder` | Cartesian product grid expansion with chunking |
| `MetricsEngine` | Vectorized performance metrics (Sharpe, Sortino, Calmar, etc.) |
| `ReportingEngine` | Plotly HTML dashboard generation |

#### Dual Runner

The engine automatically selects the optimal runner based on the risk archetype's vectorizability:

| Archetype | Vectorizability | Runner | Reason |
|-----------|----------------|--------|--------|
| `trend_following` | High | Simple bar loop | No pyramiding/partial TP needed |
| `mean_reversion` | High | Simple bar loop | Single-position patterns |
| `mixed` | Medium | FSM | Partial TP + trailing branching |
| `pyramidal` | Low | FSM | Sequential add logic |
| `grid_dca` | Low | FSM | Sequential DCA levels |

```python
from suitetrading.backtesting import BacktestEngine

engine = BacktestEngine()
result = engine.run(
    dataset=dataset,
    signals=signals,
    risk_config=risk_config,
    mode="auto",        # "auto" | "fsm" | "simple"
    direction="long",
)
```

#### Metrics Computed

| Metric | Description |
|--------|-------------|
| `net_profit` | Absolute P&L in account currency |
| `total_return_pct` | Percentage return from initial capital |
| `sharpe` | Annualized Sharpe ratio (365 trading days for crypto) |
| `sortino` | Sortino ratio (downside deviation only) |
| `max_drawdown_pct` | Maximum peak-to-trough drawdown |
| `calmar` | Return / max drawdown |
| `win_rate` | Percentage of winning trades |
| `profit_factor` | Gross profit / gross loss |
| `average_trade` | Mean P&L per trade |
| `max_consecutive_losses` | Longest losing streak |
| `total_trades` | Number of completed round-trips |

#### Grid Search

```python
from suitetrading.backtesting import ParameterGridBuilder
from suitetrading.backtesting._internal.schemas import GridRequest

request = GridRequest(
    symbols=["BTCUSDT"],
    timeframes=["1h", "4h"],
    archetypes=["trend_following"],
    indicator_space={
        "ssl_channel": {"period": [10, 14, 20]},
        "rsi": {"period": [10, 14, 21]},
    },
    risk_space={
        "stop__atr_multiple": [2.0, 3.0],
        "trailing__atr_multiple": [1.5, 2.5],
    },
)

grid = ParameterGridBuilder()
configs = grid.build(request)
print(f"Grid size: {grid.estimate_size(request)} combinations")

# Execute in chunks
chunks = grid.chunk(configs, chunk_size=64)
```

---

### 5. Optimization & Anti-Overfitting

**Module:** `suitetrading.optimization`

Multi-stage optimization pipeline with statistical filters to prevent backtest overfitting.

#### Pipeline

```
   Parameter Grid
        │
        ▼
  ┌─────────────┐
  │   Optuna     │  Bayesian search (TPE) or NSGA-II multi-objective
  │   or DEAP    │
  └──────┬──────┘
         │  Top N candidates
         ▼
  ┌─────────────┐
  │ Walk-Forward │  Rolling/anchored IS/OOS splits
  │ Optimization │  Re-optimize on each fold
  └──────┬──────┘
         │  OOS equity curves
         ▼
  ┌─────────────┐
  │    CSCV      │  Probability of Backtest Overfitting
  │    (PBO)     │
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │   Deflated   │  Controls for multiple testing bias
  │ Sharpe Ratio │
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │  Hansen SPA  │  Reality check: is the best strategy
  │    Test      │  significantly better than a benchmark?
  └──────┬──────┘
         │
         ▼
    Finalist strategies
```

#### Core Components

| Class | Description |
|-------|-------------|
| `OptunaOptimizer` | Bayesian optimization via Optuna (TPE, NSGA-II, CMA-ES, Random) |
| `WalkForwardEngine` | Walk-Forward Optimization with rolling/anchored modes |
| `CSCVValidator` | Combinatorially Symmetric Cross-Validation — Probability of Backtest Overfitting |
| `deflated_sharpe_ratio()` | Bailey et al. (2014) DSR test |
| `AntiOverfitPipeline` | Sequential CSCV → DSR → SPA filter |
| `ParallelExecutor` | Distribute backtests across CPU cores via `ProcessPoolExecutor` |

#### Optional Extensions (require extra dependencies)

| Class | Dependencies | Description |
|-------|-------------|-------------|
| `DEAPOptimizer` | `deap` | NSGA-II multi-objective evolutionary optimization |
| `FeatureImportanceEngine` | `xgboost`, `shap` | XGBoost + SHAP search-space analysis |

#### Usage

```python
from suitetrading.optimization import (
    OptunaOptimizer,
    WalkForwardEngine,
    AntiOverfitPipeline,
    WFOConfig,
)

# 1. Bayesian optimization
optimizer = OptunaOptimizer(
    objective=my_objective_fn,
    study_name="btcusdt_trend",
    sampler="tpe",
    direction="maximize",
    n_trials=500,
)
result = optimizer.run()

# 2. Walk-Forward validation
wfo = WalkForwardEngine(
    config=WFOConfig(
        n_splits=5,
        mode="rolling",
        min_is_bars=5000,
        min_oos_bars=1000,
    ),
    metric="sharpe",
)
splits = wfo.generate_splits(n_bars=len(df_1h))

# 3. Anti-overfitting filter
pipeline = AntiOverfitPipeline()
filtered = pipeline.run(
    equity_curves=candidate_curves,
    benchmark_returns=spy_returns,
)
# filtered.pbo, filtered.dsr_pvalue, filtered.spa_pvalue
```

#### Parallel Execution

```python
from suitetrading.optimization import ParallelExecutor

executor = ParallelExecutor(max_workers=8)
results = executor.run_batch(
    configs=run_configs,
    dataset_loader=load_dataset,
    signal_builder=build_signals,
    risk_builder=build_risk_config,
    mode="auto",
)
```

---

## Scripts Reference

All scripts are in the `scripts/` directory and should be run from the `suitetrading/` root:

| Script | Purpose | Example |
|--------|---------|---------|
| `download_data.py` | Download OHLCV data from Binance Vision + CCXT | `python scripts/download_data.py --symbols BTCUSDT` |
| `cross_validate_native.py` | Validate resampled vs native exchange data | `python scripts/cross_validate_native.py --symbols BTCUSDT --days 30` |
| `audit_raw_data.py` | Audit and quarantine corrupt Parquet files | `python scripts/audit_raw_data.py --apply` |
| `run_risk_lab.py` | Batch backtesting with risk parameter variations | `python scripts/run_risk_lab.py --symbols BTCUSDT --timeframes 1h 4h` |
| `analyze_risk_lab.py` | Analyze risk lab results (CSV summary) | `python scripts/analyze_risk_lab.py` |
| `benchmark_backtesting.py` | Benchmark: throughput, memory, phase timings | `python scripts/benchmark_backtesting.py --combos 1024` |
| `plot_indicator_validation.py` | Generate interactive HTML charts for indicator validation | `python scripts/plot_indicator_validation.py --indicator ssl_channel` |
| `gen_regression_fixtures.py` | Generate regression test fixtures from real data | `python scripts/gen_regression_fixtures.py` |

---

## Configuration

### Environment Variables

Configuration is managed via Pydantic Settings, loaded from environment variables or a `.env` file:

```env
# .env (place in suitetrading/ root)

# General
DATA_DIR=./data
RESULTS_DIR=./results
LOG_LEVEL=INFO

# Exchange
DEFAULT_EXCHANGE=binance

# Download
DOWNLOAD_RATE_LIMIT_WEIGHT=1200
DOWNLOAD_RETRY_MAX=3

# Storage
PARQUET_COMPRESSION=zstd
PARQUET_COMPRESSION_LEVEL=3

# Default symbols and timeframes
DEFAULT_SYMBOLS=["BTCUSDT","ETHUSDT","SOLUSDT"]
BASE_TIMEFRAME=1m
TARGET_TIMEFRAMES=["1m","3m","5m","15m","30m","45m","1h","4h","1d","1w","1M"]

# Alpaca (optional — for US equities)
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_FEED=iex
ALPACA_SYMBOLS=["AAPL","SPY","QQQ","MSFT","AMZN"]
```

### Supported Timeframes

```
1m  3m  5m  15m  30m  45m  1h  4h  1d  1w  1M
```

All timeframes are derived from the 1m base via `OHLCVResampler`. The resampler handles 45m epoch alignment, weekly Monday start, and incomplete bar removal.

---

## Project Structure

```
suitetrading/
├── pyproject.toml                          # Package metadata, dependencies, tool config
├── README.md                               # This file
├── .gitignore
│
├── src/suitetrading/                       # Source code (PEP 621 src layout)
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py                     # Pydantic BaseSettings
│   │
│   ├── data/                               # Sprint 1: Data Infrastructure
│   │   ├── __init__.py
│   │   ├── downloader.py                   # BinanceVision + CCXT + Orchestrator
│   │   ├── storage.py                      # ParquetStore (read/write/append)
│   │   ├── resampler.py                    # OHLCVResampler (1m → any TF)
│   │   ├── validator.py                    # DataValidator (integrity checks)
│   │   ├── timeframes.py                   # TF normalization, mapping, utilities
│   │   ├── warmup.py                       # WarmupCalculator
│   │   └── alpaca.py                       # Alpaca equities downloader
│   │
│   ├── indicators/                         # Sprint 2: Indicator Engine
│   │   ├── __init__.py
│   │   ├── base.py                         # Indicator ABC + IndicatorState
│   │   ├── registry.py                     # INDICATOR_REGISTRY (12 indicators)
│   │   ├── signal_combiner.py              # Excluyente/Opcional/Desactivado logic
│   │   ├── mtf.py                          # Multi-timeframe helpers
│   │   ├── custom/                         # Pine Script replicas
│   │   │   ├── firestorm.py                # Firestorm + FirestormTM
│   │   │   ├── ssl_channel.py              # SSLChannel + SSLChannelLow
│   │   │   └── wavetrend.py                # WaveTrend Reversal + Divergence
│   │   └── standard/                       # TA-Lib wrappers
│   │       └── indicators.py               # RSI, EMA, MACD, ATR, VWAP, Bollinger
│   │
│   ├── risk/                               # Sprint 3: Risk Management Engine
│   │   ├── __init__.py
│   │   ├── contracts.py                    # RiskConfig, PositionState, events, snapshots
│   │   ├── state_machine.py                # PositionStateMachine (FSM)
│   │   ├── position_sizing.py              # 4 sizing models
│   │   ├── trailing.py                     # 6 exit policies
│   │   ├── portfolio.py                    # PortfolioRiskManager (feature-flagged)
│   │   ├── vbt_simulator.py                # VectorBT adapter + vectorizability map
│   │   └── archetypes/                     # Risk presets
│   │       ├── base.py                     # RiskArchetype ABC
│   │       ├── trend_following.py
│   │       ├── mean_reversion.py
│   │       ├── mixed.py
│   │       ├── legacy.py                   # LegacyFirestormProfile
│   │       ├── pyramidal.py
│   │       └── grid_dca.py
│   │
│   ├── backtesting/                        # Sprint 4: Backtesting Core
│   │   ├── __init__.py
│   │   ├── engine.py                       # BacktestEngine (single + batch)
│   │   ├── grid.py                         # ParameterGridBuilder
│   │   ├── metrics.py                      # MetricsEngine (vectorized)
│   │   ├── reporting.py                    # ReportingEngine (Plotly)
│   │   └── _internal/                      # Internal implementation
│   │       ├── runners.py                  # FSM + simple backtest runners
│   │       ├── datasets.py                 # Dataset construction helpers
│   │       ├── schemas.py                  # BacktestDataset, RunConfig, etc.
│   │       └── checkpoints.py              # Checkpoint/resume support
│   │
│   └── optimization/                       # Sprint 5: Optimization + Anti-Overfitting
│       ├── __init__.py
│       ├── optuna_optimizer.py             # Bayesian search (TPE/NSGA-II/CMA-ES)
│       ├── walk_forward.py                 # Walk-Forward engine (rolling/anchored)
│       ├── anti_overfit.py                 # CSCV + DSR + pipeline
│       ├── parallel.py                     # ParallelExecutor (multiprocessing)
│       ├── deap_optimizer.py               # [optional] NSGA-II via DEAP
│       ├── feature_importance.py           # [optional] XGBoost + SHAP
│       └── _internal/
│           ├── schemas.py                  # All optimization data classes
│           └── objective.py                # Objective function utilities
│
├── tests/                                  # 647 tests
│   ├── data/                               # Data layer tests
│   ├── indicators/                         # Indicator tests (including smoke tests)
│   ├── risk/                               # Risk engine tests (FSM, sizing, archetypes)
│   ├── backtesting/                        # Engine, grid, metrics, reporting tests
│   ├── optimization/                       # Optuna, WFO, CSCV, DSR, SPA, parallel tests
│   └── fixtures/                           # Regression fixtures (real data snapshots)
│
├── scripts/                                # Executable scripts (see Scripts Reference)
│
├── data/                                   # Downloaded data (not tracked by git)
│   ├── raw/binance/{SYMBOL}/{TF}/          # Parquet partitions
│   ├── cache/                              # Download cache (ZIPs)
│   └── quarantine/                         # Quarantined corrupt files
│
├── artifacts/                              # Generated artifacts
│   ├── indicator_validation/               # HTML charts for indicator validation
│   └── risk_lab/                           # Risk lab batch results
│
└── docs/                                   # Sprint plans, specs, reports
    ├── sprint{1..5}_master_plan.md
    ├── sprint{1..5}_technical_spec.md
    ├── sprint{1..5}_implementation_guide.md
    ├── backtest_execution_semantics.md     # Backtesting behavior contracts
    ├── risk_management_framework.md        # Risk engine design
    ├── signal_flow.md                      # Signal flow documentation
    ├── indicator_catalog.md                # Indicator parameter reference
    └── risk_lab_report.md                  # Risk Lab findings
```

---

## Testing

The test suite covers all modules with 647 tests:

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific module tests
pytest tests/data/
pytest tests/indicators/
pytest tests/risk/
pytest tests/backtesting/
pytest tests/optimization/

# Skip slow tests (external API calls)
pytest -m "not slow"

# Run only integration tests
pytest -m integration

# Run with coverage
pytest --cov=suitetrading --cov-report=html
```

### Test Categories

| Category | Approximate Count | Coverage |
|----------|-------------------|----------|
| Data infrastructure | ~60 | Downloaders, storage, resampler, validator |
| Indicators | ~80 | All 12 indicators + smoke tests + signal combiner |
| Risk management | ~120 | FSM states, sizing, trailing, archetypes, portfolio |
| Backtesting | ~140 | Engine, grid, metrics, reporting, checkpoints |
| Optimization | ~200 | Optuna, WFO, CSCV, DSR, SPA, DEAP, parallel |
| Regression | ~47 | Fixtures from real data to catch silent changes |

---

## Usage Examples

### Download Data

```bash
# Download default symbols (BTCUSDT, ETHUSDT, SOLUSDT) from genesis
python scripts/download_data.py

# Download specific symbols with date range
python scripts/download_data.py --symbols BTCUSDT --start 2023-01-01 --end 2024-12-31

# Download specific timeframe
python scripts/download_data.py --symbols BTCUSDT ETHUSDT SOLUSDT --timeframe 1m
```

### Run a Single Backtest

```python
from pathlib import Path
from suitetrading.data import ParquetStore, OHLCVResampler
from suitetrading.backtesting import BacktestEngine, MetricsEngine
from suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.backtesting._internal.schemas import StrategySignals
from suitetrading.indicators.registry import get_indicator
from suitetrading.risk.archetypes import get_archetype

# 1. Load and resample data
store = ParquetStore(base_dir=Path("data/raw"))
df_1m = store.read("binance", "BTCUSDT", "1m")
df_1h = OHLCVResampler().resample(df_1m, "1h")

# 2. Compute indicators
ssl = get_indicator("ssl_channel")
entries = ssl.compute(df_1h, period=14)

# 3. Build dataset and signals
dataset = build_dataset_from_df(df_1h, symbol="BTCUSDT", base_timeframe="1h")
signals = StrategySignals(entries=entries, exits=~entries)

# 4. Configure risk
risk_config = get_archetype("trend_following").build_config()

# 5. Run backtest
engine = BacktestEngine()
result = engine.run(
    dataset=dataset,
    signals=signals,
    risk_config=risk_config,
)

# 6. Compute metrics
metrics = MetricsEngine().compute(
    equity_curve=result["equity_curve"],
    trades=result.get("trades"),
)
print(f"Sharpe: {metrics['sharpe']:.2f}, Return: {metrics['total_return_pct']:.1f}%")
```

### Run a Grid Search

```python
from suitetrading.backtesting import ParameterGridBuilder, BacktestEngine
from suitetrading.backtesting._internal.schemas import GridRequest

request = GridRequest(
    symbols=["BTCUSDT", "ETHUSDT"],
    timeframes=["1h", "4h"],
    archetypes=["trend_following", "mean_reversion"],
    indicator_space={
        "ssl_channel": {"period": [10, 14, 20, 30]},
    },
    risk_space={
        "stop__atr_multiple": [2.0, 2.5, 3.0],
    },
)

grid = ParameterGridBuilder()
configs = grid.build(request)
print(f"Total combinations: {len(configs)}")

# Execute in batches
engine = BacktestEngine()
results = engine.run_batch(configs=configs, chunk_size=64)
```

### Walk-Forward Optimization

```python
from suitetrading.optimization import WalkForwardEngine, WFOConfig

wfo = WalkForwardEngine(
    config=WFOConfig(
        n_splits=5,
        mode="rolling",       # "rolling" or "anchored"
        min_is_bars=5000,
        min_oos_bars=1000,
        gap_bars=100,
    ),
    metric="sharpe",
)

splits = wfo.generate_splits(n_bars=len(df_1h))
print(f"Generated {len(splits)} IS/OOS folds")
```

### Risk Lab Batch

```bash
# Run risk lab with all strategy/risk preset combinations
python scripts/run_risk_lab.py \
    --symbols BTCUSDT ETHUSDT SOLUSDT \
    --timeframes 15m 1h 4h 1d

# Results saved to artifacts/risk_lab/
# Includes CSV results + Plotly HTML dashboards
```

### Indicator Validation

```bash
# Generate interactive HTML chart for manual TradingView comparison
python scripts/plot_indicator_validation.py --indicator ssl_channel --bars 500
python scripts/plot_indicator_validation.py --indicator firestorm --bars 300

# Output: artifacts/indicator_validation/*.html
```

---

## Development Roadmap

### Completed Sprints

| Sprint | Focus | Status | Key Deliverables |
|--------|-------|--------|------------------|
| **0** | Pine Script Audit + Scaffolding | ✅ Done | Project structure, prototypes |
| **1** | Data Infrastructure | ✅ Done (256 tests) | BinanceVision + CCXT downloaders, Parquet store, resampler, cross-validation |
| **2** | Indicator Engine | ✅ Done | 12 indicators (6 custom + 6 TA-Lib), signal combiner, MTF support |
| **3** | Risk Management | ✅ Done | FSM, 4 sizers, 6 exit policies, 6 archetypes, portfolio limits |
| **4** | Backtesting Core | ✅ Done (63.7 bt/sec) | Dual runner, grid builder, metrics engine, Plotly reporting |
| **5** | Optimization + Anti-Overfitting | ✅ Done (609 tests) | Optuna, WFO, CSCV, DSR, DEAP, SHAP, parallel executor |
| **5.5** | Hardening + Risk Lab | ✅ Done (647 tests) | Portfolio wiring, trailing policies, risk lab, regression fixtures |

### Upcoming Sprints

| Sprint | Focus | Description |
|--------|-------|-------------|
| **6** | TradingView Validation | Visual validation of full pipeline vs TradingView results |
| **7** | Production Infrastructure | Live paper trading, monitoring, alerting |
| **8** | Integration & Stress Testing | Full pipeline stress tests, edge cases |

---

## Relationship with v1 (AutomationTrading-Strategy-Backtesting-Suite)

The [v1 suite](../AutomationTrading-Strategy-Backtesting-Suite/) remains in the repository as a reference and is still fully functional:

- **Pine Script indicators**: The TradingView strategy with 15+ indicators that generated the original results
- **Generate Combination Python**: The combination generator scripts that create the parameter search space
- **Puppeteer Automation**: The browser automation that runs backtests on TradingView

**v2 (this directory) supersedes the need for v1 for research and backtesting**, because it:

1. Runs backtests locally at 63+ bt/sec instead of through browser automation
2. Replicates the Pine Script indicators in Python with validation
3. Adds a complete risk management engine not available in TradingView
4. Includes statistical anti-overfitting filters (CSCV, DSR, SPA)
5. Supports multi-core parallelism for large-scale parameter sweeps

However, the v1 results and visualizations remain valuable evidence of strategy effectiveness. The images in the v1 README show real performance metrics from the original Puppeteer-driven backtesting campaigns.

---

## Dependencies

### Core (always installed)

```
numpy>=1.26    pandas>=2.1      TA-Lib>=0.4.28   numba>=0.59
pydantic>=2.5  pydantic-settings>=2.1  polars>=0.20   pyarrow>=14
loguru>=0.7    optuna>=3.5      scikit-learn>=1.4
```

### Data download (optional: `pip install -e ".[data]"`)

```
ccxt>=4.2      httpx>=0.27      tqdm>=4.66
```

### Optimization extensions (optional: `pip install -e ".[optimization]"`)

```
deap>=1.4      arch>=7.0        xgboost>=2.0     shap>=0.44
```

### Development (optional: `pip install -e ".[dev]"`)

```
pytest>=7.4    pytest-cov>=4.1  pytest-asyncio>=0.23  pytest-benchmark>=4.0
ruff>=0.3      mypy>=1.7
```

---

## License

This project is licensed under the MIT License. See the [LICENSE](../AutomationTrading-Strategy-Backtesting-Suite/LICENSE) file for details.

