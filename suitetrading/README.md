# SuiteTrading v2

Algorithmic trading research platform. Vectorized backtesting, multi-layer risk management, Bayesian optimization with anti-overfitting, portfolio construction, live execution bridge.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-1467%20passed-brightgreen.svg)](#testing)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)

---

## Status

**v9 Random Exhaustive Search** — Phase 1 exploration (paused, MDD bug fixed, relaunch pending).
Downstream portfolio pipeline operational with 25-strategy portfolio from `discovery_rich_v4/`.

**19.7K LOC | 1467 tests | 38 indicators | 164 archetypes | 10 stocks + 10 cryptos**

**Read first:** [`DIRECTION.md`](DIRECTION.md) (methodology) | [`HANDOFF.md`](HANDOFF.md) (state) | [`RUNBOOK.md`](RUNBOOK.md) (commands)

---

## Quick start

```bash
cd suitetrading
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,data,optimization]"
pip install yfinance fredapi

# Verify
pytest -x -q                    # 1467 passed

# Download data
python scripts/download_data.py --symbols SPY QQQ --timeframes 1m --exchange alpaca

# Smoke test v9 (30 trials)
PYTHONPATH=src python scripts/run_random_v9.py \
    --symbol SPY --direction long --timeframe 1h \
    --trials 30 --step-factor 4 --output-dir /tmp/v9_smoke \
    --months 60 --exchange alpaca --commission 0.0
```

---

## Pipeline

```
Phase 1: run_random_v9.py → Random exhaustive → Parquet (current, v9)
Phase 2: pandas analysis → structural patterns → narrow space
Phase 3: run_discovery.py → Optuna WFO + CSCV/PBO validation
Phase 4: build_candidate_pool → portfolio_walkforward → validate → run_portfolio
Phase 5: run_paper_portfolio.py → Alpaca paper trading
```

See [`docs/methodology.md`](docs/methodology.md) for rules and rationale.

---

## Project structure

```
suitetrading/
├── src/suitetrading/
│   ├── backtesting/     Engine, metrics, slippage, ensemble
│   ├── config/          Archetype configs (164 archetypes)
│   ├── data/            Downloaders (Alpaca, Binance, FRED), ParquetStore
│   ├── execution/       Alpaca bridge, signal/portfolio bridges
│   ├── indicators/      38 indicators, signal combiner, MTF
│   ├── optimization/    Optuna, WFO, CSCV, DSR, feature importance
│   └── risk/            FSM, archetypes, portfolio, sizing, trailing
├── scripts/             Pipeline + analysis scripts
├── tests/               65 test files
├── data/raw/            Parquet (alpaca/, binance/, macro/)
├── artifacts/           Discovery, pool, portfolio outputs
└── docs/                Full documentation → see docs/README.md
```

---

## Documentation

All docs live in [`docs/`](docs/README.md):

| Topic | Link |
|-------|------|
| Architecture | [docs/architecture.md](docs/architecture.md) |
| Methodology | [docs/methodology.md](docs/methodology.md) |
| History (v1-v9) | [docs/history.md](docs/history.md) |
| Setup | [docs/setup.md](docs/setup.md) |
| Data module | [docs/modules/data/](docs/modules/data/README.md) |
| Indicators | [docs/modules/indicators/](docs/modules/indicators/README.md) |
| Risk engine | [docs/modules/risk/](docs/modules/risk/README.md) |
| Optimization | [docs/modules/optimization/](docs/modules/optimization/README.md) |
| Portfolio | [docs/modules/portfolio/](docs/modules/portfolio/README.md) |
| Execution | [docs/modules/execution/](docs/modules/execution/README.md) |

---

## Testing

```bash
pytest                                          # All 1467 tests
pytest tests/risk/test_state_machine.py -v      # FSM (critical)
pytest tests/optimization/ -v                   # Optimization suite
pytest tests/indicators/ -v                     # Indicators
```

---

## Relationship with v1

v2 is a ground-up rewrite of [AutomationTrading-Strategy-Backtesting-Suite v1](../README.md) (Puppeteer + TradingView). v1 proved combinatorial testing works. v2 provides infrastructure to reproduce and extend at scale, without TradingView dependency.
