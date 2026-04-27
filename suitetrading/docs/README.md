# Documentation Index — SuiteTrading v2

## Global

| Doc | Content |
|-----|---------|
| [Architecture](architecture.md) | Pipeline diagram, module dependencies, directory structure |
| [Methodology](methodology.md) | The 5-phase pipeline, non-negotiable rules, risk search spaces, validation gates |
| [Validation framework](validation_framework.md) | TIER A/B/C cross-validation suite (replication, sensitivity, structural diagnostics) |
| [Cookbook](cookbook.md) | Operational recipes — discovery, monitoring, validation, portfolio, paper |
| [History](history.md) | Timeline v1-v9, methodology lessons, engine-level milestones |
| [Setup](setup.md) | Installation, env vars, first run, hardware |

## Modules

| Module | Doc | Key content |
|--------|-----|-------------|
| Data | [README](modules/data/README.md) | Downloaders (Alpaca, Binance, FRED), ParquetStore, resampler |
| Indicators | [README](modules/indicators/README.md) | 38 indicators, 3-state classification, signal combiner, MTF |
|  | [Catalog](modules/indicators/catalog.md) | Pine Script → Python indicator mapping |
|  | [Signal Flow](modules/indicators/signal_flow.md) | EXCL/OPC/DESACT logic, hold-bars, MTF resolution |
|  | [Availability](modules/indicators/availability.md) | Indicator × feature matrix |
| Risk | [README](modules/risk/README.md) | FSM, 6 exit policies, 4 sizers, 164 archetypes |
|  | [Framework](modules/risk/framework.md) | Risk architecture, portfolio controls, VBT adapter |
|  | [Spec](modules/risk/spec.md) | FSM evaluation contract (frozen) |
| Backtesting | [README](modules/backtesting/README.md) | Dual runner, metrics, slippage model |
|  | [Execution Semantics](modules/backtesting/execution_semantics.md) | Bar-loop model, exit priority (frozen) |
| Optimization | [README](modules/optimization/README.md) | Optuna, WFO, CSCV, DSR, risk spaces, v9 pipeline |
| Portfolio | [README](modules/portfolio/README.md) | Candidate pool → WFO → validation → construction |
| Execution | [README](modules/execution/README.md) | Alpaca bridge, signal/portfolio bridges |

## Archive

| Doc | Content |
|-----|---------|
| [Archive manifest](archive/README.md) | Sprint docs, historical reports, what and why |

## Key concepts

- **Excluyente / Opcional / Desactivado** — three-state indicator classification (see [signal flow](modules/indicators/signal_flow.md))
- **rich_stock** — primary archetype with 11 entry indicators (see [methodology](methodology.md))
- **PBO** — Probability of Backtest Overfitting via CSCV (see [optimization](modules/optimization/README.md))
- **Effective N** — eigenvalue-based participation ratio of the equity-curve correlation matrix (see [validation framework](validation_framework.md))
- **v9** — Phase 1 random exhaustive discovery, executed across 15m / 1h / 4h timeframes
