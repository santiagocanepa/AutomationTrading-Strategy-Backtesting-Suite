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

## ⚡ SuiteTrading v2 — The New Suite

> **If you're cloning this repo, start here: [`suitetrading/`](suitetrading/)**

SuiteTrading v2 is a ground-up rewrite that replaces TradingView browser automation with a self-contained Python backtesting platform. It runs **63+ backtests per second** locally, with full risk management and statistical anti-overfitting filters.

### Quick Start

```bash
cd suitetrading
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,data,optimization]"
pytest                                     # 647 tests
```

### What's Inside

| Module | Description |
|--------|-------------|
| **Data** | Binance Vision + CCXT + Alpaca downloaders, Parquet/ZSTD storage, OHLCV resampler |
| **Indicators** | 12 indicators: 6 custom Pine Script replicas (Firestorm, SSL Channel, WaveTrend) + 6 TA-Lib wrappers (RSI, EMA, MACD, ATR, VWAP, Bollinger Bands) |
| **Risk** | Position lifecycle FSM, 4 sizing models (fixed fractional, ATR, Kelly, optimal f), 6 exit policies (break-even, trailing, Chandelier, Parabolic SAR), 6 risk archetypes |
| **Backtesting** | Dual-runner engine (FSM + simple), parameter grid builder, vectorized metrics, Plotly reporting |
| **Optimization** | Optuna Bayesian search, Walk-Forward (rolling/anchored), CSCV/PBO, Deflated Sharpe Ratio, Hansen SPA, DEAP NSGA-II, SHAP feature importance, parallel execution |

### Architecture

```
Raw Data → Parquet Store → Resampler → Indicators → Signal Combiner
                                                        │
                                                        ▼
Risk Archetypes → Backtest Engine (FSM/Simple) → Metrics → Optimization
                                                              │
                                                              ▼
                                            Anti-Overfitting Filters → Finalists
                                            (CSCV + DSR + Hansen SPA)
```

### v2 vs v1 Comparison

| Feature | v1 (Puppeteer) | v2 (SuiteTrading) |
|---------|---------------|-------------------|
| **Speed** | ~1 backtest/min (browser) | 63+ backtests/sec (in-memory) |
| **Dependencies** | TradingView account + Chrome | Python only (local execution) |
| **Risk Management** | Basic TV settings | Full FSM with pyramiding, trailing, partial TP |
| **Optimization** | Manual JSON grids | Bayesian (Optuna) + evolutionary (DEAP) |
| **Anti-Overfitting** | None | CSCV, DSR, Hansen SPA statistical filters |
| **Data** | TradingView charts | Custom Parquet store with integrity validation |
| **Parallelism** | Sequential | Multi-core ProcessPoolExecutor |
| **Tests** | None | 647 automated tests |

📖 **Full documentation:** [suitetrading/README.md](suitetrading/README.md)

---

## 📌 v1 — AutomationTrading-Strategy-Backtesting-Suite

The original suite that started it all. Still functional and documented for reference.

### Components

1. **TradingView Strategy** ([Pine Script](AutomationTrading-Strategy-Backtesting-Suite/Indicator%20Strategy%20of%20TradingView/))
   - 15+ configurable indicators in Pine Script
   - Excluyente / Opcional / Desactivado signal combination logic
   - Multi-timeframe support
   - Complete risk management settings

2. **Generate Combination Python** ([Scripts](AutomationTrading-Strategy-Backtesting-Suite/Generate%20Combination%20Python/))
   - Automates creation of indicator parameter combinations
   - Population management for batch backtesting
   - Results comparison and analysis tools
   - Duplicate detection and validation

3. **Puppeteer Automation** ([TypeScript](AutomationTrading-Strategy-Backtesting-Suite/Puppeteer%20Automation%20Backtesting/))
   - Browser automation for TradingView backtesting
   - Applies combinations, extracts results
   - Manages cookies, sessions, and rate limits
   - Results storage in structured JSON

### v1 Setup

```bash
# Pine Script: Import into TradingView
# See: AutomationTrading-Strategy-Backtesting-Suite/Indicator Strategy of TradingView/README.md

# Python combination generator
cd "AutomationTrading-Strategy-Backtesting-Suite/Generate Combination Python"
python -m venv env && source env/bin/activate
pip install -r requirements.txt

# Puppeteer automation
cd "../Puppeteer Automation Backtesting"
pnpm install
```

📖 **v1 Documentation:**
- [English](AutomationTrading-Strategy-Backtesting-Suite/README.md)
- [Español](AutomationTrading-Strategy-Backtesting-Suite/README_español.md)

---

## Workflow: From v1 to v2

The project evolved through a natural progression:

1. **v1 — Discovery**: Pine Script strategy with 15+ indicators → Puppeteer automation tested thousands of combinations on TradingView → identified profitable setups (see images above)

2. **v2 — Scale**: The core indicators were replicated in Python and validated against TradingView → a local backtesting engine was built (63+ bt/sec vs ~1 bt/min) → a risk management FSM was added → Bayesian optimization with anti-overfitting filters replaced brute-force grid search

**The v1 results remain valid** — v2 provides the infrastructure to reproduce them faster and extend the research with proper statistical validation.

---

## Installation Summary

| What | Command |
|------|---------|
| **v2 suite (recommended)** | `cd suitetrading && pip install -e ".[dev,data,optimization]"` |
| **v1 Python scripts** | `cd "AutomationTrading-Strategy-Backtesting-Suite/Generate Combination Python" && pip install -r requirements.txt` |
| **v1 Puppeteer** | `cd "AutomationTrading-Strategy-Backtesting-Suite/Puppeteer Automation Backtesting" && pnpm install` |

---

## License

This project is licensed under the MIT License. See the [LICENSE](AutomationTrading-Strategy-Backtesting-Suite/LICENSE) file for details.
