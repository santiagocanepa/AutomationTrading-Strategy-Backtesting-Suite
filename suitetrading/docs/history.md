# Research history — v1 to current

The pipeline has gone through nine major iterations. Each one was a methodology lesson; the early ones in particular informed the non-negotiable rules in [`methodology.md`](methodology.md).

## Discovery iterations

| Run | Period | Approach | Lesson |
|-----|--------|----------|--------|
| v1 | Mar 2026 | TPE single-obj, hard penalty | Hard penalties destroy the gradient surface — optimizer collapses |
| v2 | Mar 2026 | TPE + relaxed exclusivity | Baseline reference for further iterations |
| v3 | Mar 2026 | NSGA-II, 9 indicators | Indicator set incomplete; missed structural patterns |
| v4 | Mar 2026 | NSGA-II, 11 indicators | Best optimizer-driven result; PBO 0.014–0.27 |
| v5 | Mar 2026 | NSGA-II, 7 indicators (pruned) | Pruning to 7 hurt PBO — fewer candidates not always better |
| v6 | Apr 2026 | Random, no WFO | Concept proof: random > optimizer for ~10¹⁶ space exploration |
| v7 / v8 | Apr 2026 | NSGA-II (unauthorized methodology change) | Regression caught and reverted; rule 7 in methodology was added |
| v9 | Apr 2026 → Apr 2026 | Random, no Optuna, multi-TF | Current. Phase 1 complete across 15m / 1h / 4h |

## v9 — current pipeline

The v9 cycle executed Phase 1 on three timeframes:

- **1h** — 2 M trials across 20 studies (10 assets × 2 directions)
- **4h** — 2 M trials, same study layout
- **15m** — 2 M trials, same study layout

Phase 2 structural analysis on the combined 6 M trial corpus identified the HQ pool: a small fraction of the random space that consistently produces viable Sharpe under the validation gates. The structural findings (which indicator states / TFs / parameter ranges concentrate viable trials) are documented in the modular module docs.

Phase 3 Optuna refinement was applied per archetype on the HQ pool, producing per-archetype finalists that pass the four anti-overfit gates (PBO, DSR, SPA, permutation null).

Phase 4 portfolio construction was run cross-TF and cross-archetype, with a final cross-validation suite that included equity-curve dedup, slippage stress, regime stress, bootstrap CI, Monte Carlo, and borrow haircut estimation. The validation framework template is documented in [`validation_framework.md`](validation_framework.md).

## Key learnings (cross-iteration)

- **Random > optimizer for exploration in high-cardinality spaces.** v6 proved the concept; v9 executes at scale.
- **MACD is structurally destructive in our archetype set.** Across v4 / v6 / v7 it consistently subtracted Sharpe (−8 to −23 percentage points).
- **Firestorm and SSL Channel** are the most consistent positive contributors across all runs.
- **`num_optional_required = 2` is optimal** under the excluyente / opcional / desactivado classification (confirmed in v6 and v7).
- **Pruning indicator sets aggressively hurts PBO** — v5 vs v4 showed that going from 11 to 7 indicators degraded the OOS-vs-IS ratio.
- **`step_factor = 4` for indicators, `= 1` for risk** — regularizes continuous indicator parameters while preserving the risk parameter granularity that already encodes design choices.
- **Risk space dominance** — moving from 3 to 11 risk keys (Phase 3 vs Phase 1) consistently raised the Sharpe ceiling more than expanding the indicator set.

## Methodology lessons that became rules

- v1 → **rule 6**: Anti-overfit metrics must be gates, not advisory metrics.
- v3 / v5 → **rule 5**: Holdout discipline is non-negotiable.
- v6 → **rule 1**: Phase 1 is random, not Optuna.
- v7 / v8 → **rule 7**: No methodology change without explicit owner approval.
- A 13-hour MDD-bug compute loss → **rule 4**: Smoke test before any > 1 h run.

## Engine-level milestones

| Period | Change | Notes |
|--------|--------|-------|
| Mar 2026 | Slippage model formalized as per-symbol-per-TF lookup | `backtesting/slippage.py` |
| Mar 2026 | Walk-forward optimization wired into Phase 3 | `optimization/walk_forward.py` |
| Mar 2026 | Pruned 10-strategy reference portfolio via leave-one-out | First end-to-end pipeline pass |
| Mar 2026 | Cross-asset support: crypto via Binance + US equities via Alpaca | Architecture generalized beyond crypto |
| Apr 2026 | Risk parameter contracts pinned via Pydantic | Eliminated a class of misconfiguration bugs |
| Apr 2026 | Per-asset rich archetypes (`rich_spy`, `rich_aapl`, …) | 764 K-trial feature importance informed subsets |
| Apr 2026 | v9 random exhaustive runner + Parquet pipeline | Replaced Optuna for Phase 1 |
| Apr 2026 | Multi-TF discovery (15m + 1h + 4h) | Three parallel Phase 1 datasets |
| Apr 2026 | Phase 4b/4c cross-validation suite formalized | Eleven empirical tests as reusable template |

## Where to look next

- [`methodology.md`](methodology.md) — current rules and validation gates
- [`validation_framework.md`](validation_framework.md) — the cross-validation harness
- [`architecture.md`](architecture.md) — module map and data flow
- [`HANDOFF.md`](../HANDOFF.md) — operational state for the next session
