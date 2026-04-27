# SuiteTrading v2

Algorithmic trading research platform. Vectorized backtesting, multi-layer risk management, Bayesian optimization with anti-overfitting, portfolio construction, live execution bridge.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-1468%20passing-brightgreen.svg)](#testing)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)

---

## Status

The 5-phase research pipeline has been exercised end-to-end on US equities across three timeframes (15m / 1h / 4h). Phase 1 random exhaustive discovery, Phase 2 structural analysis, Phase 3 Optuna refinement, and Phase 4 portfolio construction (with TIER A/B/C cross-validation suite) are operational. Phase 5 (live) is intentionally not wired in the public repo.

**~20 K LOC | 1,468 tests passing | 38 indicators | 121 archetypes | US equities + crypto**

**Read first:** [`HANDOFF.md`](HANDOFF.md) (current state) | [`docs/methodology.md`](docs/methodology.md) (rules) | [`docs/cookbook.md`](docs/cookbook.md) (commands) | [`docs/validation_framework.md`](docs/validation_framework.md) (TIER A/B/C suite)

---

## Quick start

```bash
cd suitetrading
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,data,optimization]"
pip install yfinance fredapi

# Verify
pytest -x -q                    # 1,468 passed in ~25 s

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
Phase 1: random exhaustive discovery   (run_random_v9.py + run_v9_*.sh)
Phase 2: post-hoc structural analysis  (pandas + fixed-effects + per-symbol stress)
Phase 3: Optuna refinement on HQ pool  (run_discovery.py with WFO + CSCV/PBO/DSR/SPA gates)
Phase 4: portfolio construction        (correlation-aware pool → weighting → validation suite)
Phase 4b/4c: TIER A/B/C cross-validation suite  (replication, sensitivity, structural diagnostics)
Phase 5: paper / live trading          (run_paper_portfolio.py → Alpaca)
```

See [`docs/methodology.md`](docs/methodology.md) for rules and rationale, [`docs/cookbook.md`](docs/cookbook.md) for the operational recipes per phase.

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
| Validation framework (TIER A/B/C) | [docs/validation_framework.md](docs/validation_framework.md) |
| Cookbook (operational recipes) | [docs/cookbook.md](docs/cookbook.md) |
| History (v1-v9 + multi-TF) | [docs/history.md](docs/history.md) |
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
pytest                                          # All 1,468 tests (~25 s)
pytest tests/risk/test_state_machine.py -v      # FSM (critical)
pytest tests/optimization/ -v                   # Optimization suite
pytest tests/indicators/ -v                     # Indicators
```

---

## Relationship with v1

v2 is a ground-up rewrite of [AutomationTrading-Strategy-Backtesting-Suite v1](../README.md) (Puppeteer + TradingView). v1 proved combinatorial testing works. v2 provides infrastructure to reproduce and extend at scale, without TradingView dependency.
