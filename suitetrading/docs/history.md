# Research History — v1 to current

## Discovery runs

| Run | Date | Approach | Trials | Result | Status |
|-----|------|----------|--------|--------|--------|
| v1 | Mar 2026 | TPE single-obj, penalty -10 | 80K | 0 finalists | Penalty destroys surface |
| v2 | Mar 2026 | TPE + MAX_EXCL=3 | 80K | 27 finalists | Baseline reference |
| v3 | Mar 2026 | NSGA-II, 9 indicators | 400K | 139 finalists | Incomplete indicator set |
| **v4** | **Mar 2026** | **NSGA-II, 11 ind, step=4** | **200K** | **31 finalists, PBO 0.014-0.27** | **Best optimizer result** |
| v5 | Mar 2026 | NSGA-II, 7 ind, step=1 | 400K | 11 finalists | Pruning hurts PBO |
| v6 | Apr 2026 | Random, no WFO | 1.27M | 1,333 viables (0.10%) | Direction bug (fixed) |
| v7 | Apr 2026 | NSGA-II (deviation) | 300K | 291 finalists | Unauthorized methodology change |
| v8 | Apr 2026 | NSGA-II (deviation) | 400K | 87 finalists | Same deviation |
| **v9** | **Apr 14** | **Random, no Optuna, Parquet** | **1.74M** | **Paused (MDD bug)** | **Current Phase 1** |

## Key learnings

- **v4 is the reference standard** — 31 finalists with PBO 0.014-0.271, artifacts in `discovery_rich_v4/`
- **Random > optimizer for exploration** in ~10^16 space (v6 proved concept, v9 executes at scale)
- **MACD destructive** across v4, v6, v7 (−8 to −23pp Sharpe contribution)
- **firestorm + ssl_channel** most consistent contributors across all runs
- **num_optional_required = 2** optimal (v6, v7 confirmed)
- **Risk collapses to minimums** in v7/v8 → v9 widened range below those minimums
- **step_factor=4** prevents indicator param overfit (v5 vs v4 comparison)

## Downstream pipeline (Mar 13-29 2026)

Built in parallel as the portfolio construction layer. Commits:

| Commit | Change |
|--------|--------|
| `d7c9040` | Phase 3 infrastructure: new indicators, FTM stops, 6 symbols |
| `4fb99b8` | Realistic slippage model |
| `e1d47b1` | Portfolio walk-forward validation script |
| `9638fce` | Slippage into pool builder + portfolio defaults |
| `a4c232f` | Stability filter + walk-forward tuning |
| `bd420b9` | Pruned 10-strategy portfolio via leave-one-out |
| `46f879e` | Risk defaults from 764K-trial feature importance |
| `5359c0e` | Narrow indicator search spaces → per-symbol rich_* archetypes |
| `7fc7c3e` | Expand to 10 crypto assets |
| `c6bbb39` | Stock market support (annualization, slippage, Alpaca) |
| `6e3c0ce` | Cross-asset portfolio: crypto + stocks via Alpaca |

## Current state

- **v9 Phase 1:** paused. Bug MDD fixed in runner (`bug_history.md`). Relaunch pending user decision (A/B/C in `v9_current_state.md`).
- **Downstream:** operational. `artifacts/portfolio_rich/` (25 strategies, Mar 29) built from `discovery_rich_v4/` as interim input.
- **Next:** relaunch v9 → Phase 2 analysis → Phase 3 Optuna validation → rebuild portfolio with v9 finalists.

## Structural findings (cross-run)

| Pattern | Source | Confidence |
|---------|--------|------------|
| EXCL toxic for most indicators (~5% viable vs 33% baseline) | v6 | High |
| obv, adx_filter, ma_crossover, firestorm tolerate EXCL | v6 | High |
| squeeze, rsi, bollinger, macd NEVER as EXCL | v6, v7 | High |
| Long bias for US equities (10x more viables than short) | v9 SPY/QQQ | Medium |
| ~30% zero-trade rate suggests over-restrictive random space | v9 SPY/QQQ | Medium |
