# Architecture — SuiteTrading v2

## Pipeline overview

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA LAYER                                │
│  Alpaca (stocks) · Binance (crypto) · FRED (macro)         │
│  → ParquetStore (zstd) → OHLCVResampler → DataValidator    │
└──────────────────────────┬──────────────────────────────────┘
                           │ OHLCV DataFrames
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  INDICATOR LAYER                             │
│  38 indicators: custom · standard · cross_asset · futures  │
│  · macro                                                    │
│  Signal combiner: Excluyente (AND) · Opcional (≥ threshold)│
│  · Desactivado (skip)                                       │
│  MTF resolution: grafico · 1_superior · 2_superiores       │
└──────────────────────────┬──────────────────────────────────┘
                           │ entry/exit/trailing signals
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 BACKTESTING ENGINE                           │
│  BacktestEngine → run_fsm_backtest (bar-by-bar FSM)        │
│                 → run_simple_backtest (numpy loop)          │
│  MetricsEngine: sharpe, sortino, calmar, max_drawdown_pct  │
│  Slippage model: estimate_slippage_pct(symbol, TF)         │
└──────────────────────────┬──────────────────────────────────┘
                           │ metrics + equity curves
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               OPTIMIZATION LAYER                             │
│                                                              │
│  Phase 1 (v9): Random exhaustive → Parquet (no Optuna)     │
│  Phase 2: Post-hoc analysis (pandas structural patterns)    │
│  Phase 3: Optuna (TPE/NSGA-II) + WFO + CSCV/PBO + DSR     │
│                                                              │
│  164 archetypes × 5 risk search spaces                      │
│  BacktestObjective: suggest params → backtest → metrics     │
└──────────────────────────┬──────────────────────────────────┘
                           │ finalists (WFO validated)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               PORTFOLIO LAYER                                │
│  build_candidate_pool (PBO filter + slippage replay)        │
│  → portfolio_walkforward (IS 70% / OOS 30%)                │
│  → validate_portfolio (Ensemble PBO + DSR + SPA + ruin)    │
│  → run_portfolio (correlation + selection + Kelly/HRP)      │
└──────────────────────────┬──────────────────────────────────┘
                           │ weights + selection
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                EXECUTION LAYER                               │
│  AlpacaExecutor · SignalBridge · PortfolioBridge            │
│  Paper trading → Live trading (Alpaca API)                  │
└─────────────────────────────────────────────────────────────┘
```

## Module dependencies

| Module | Depends on | Used by |
|--------|-----------|---------|
| `data/` | — | indicators, backtesting, optimization |
| `indicators/` | data | backtesting, optimization |
| `backtesting/` | data, indicators | optimization, portfolio scripts |
| `optimization/` | backtesting, indicators | discovery/validation scripts |
| `risk/` | — | backtesting, optimization, portfolio scripts |
| `config/` | — | indicators, optimization, risk |
| `execution/` | data, indicators, risk | paper/live scripts |

## Key files

| File | LOC | Role |
|------|-----|------|
| `risk/state_machine.py` | 564 | FSM bar-by-bar — **DO NOT MODIFY** |
| `optimization/_internal/objective.py` | 798 | BacktestObjective + 5 risk spaces |
| `config/archetypes.py` | 997 | ARCHETYPE_INDICATORS (161 configs) |
| `optimization/null_hypothesis.py` | 713 | SPA testing |
| `data/downloader.py` | 613 | Multi-exchange download |
| `scripts/run_discovery.py` | 897 | Optuna + WFO + CSCV + DSR pipeline |
| `scripts/run_random_v9.py` | 306 | v9 random exhaustive runner |

## Stats

- **~19.7K LOC** source, **~7K LOC** scripts, **65 test files**
- **1467 tests** passing (32s)
- **38 indicators**, **164 archetypes**
- **10 stocks** (Alpaca), **10 cryptos** (Binance), **macro** (FRED)

## Directory structure

```
suitetrading/
├── src/suitetrading/
│   ├── backtesting/     Engine, metrics, slippage, ensemble
│   ├── config/          Archetype indicator configs (997 LOC)
│   ├── data/            Downloaders, ParquetStore, resampler
│   ├── execution/       Alpaca bridge, signal/portfolio bridges
│   ├── indicators/      38 indicators, signal combiner, MTF
│   ├── optimization/    Optuna, WFO, CSCV, DSR, feature importance
│   └── risk/            FSM, archetypes (164), portfolio, sizing
├── scripts/             26 pipeline + analysis scripts
│   ├── research/        IC scanning (exploratory)
│   └── archive/         v6/v7/v8 shells (superseded)
├── tests/               65 test files (1467 tests)
├── data/raw/            Parquet data (alpaca/, binance/, macro/)
├── artifacts/           Pipeline outputs (discovery, pool, portfolio)
└── docs/                Modular documentation
```
