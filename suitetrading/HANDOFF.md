# Handoff — current state of the research pipeline

**Last update:** 2026-04-27

This document captures the operational state of the research suite for the next person (or future-self) walking into the codebase. Read [`docs/methodology.md`](docs/methodology.md) first for the methodology contract.

---

## Where things stand

**Phase 1 (random exhaustive discovery) — complete across three timeframes.**
Discovery has been executed end-to-end on US equities at 15m, 1h, and 4h with ~2M random trials per timeframe (≈6M trials total). Outputs live under `artifacts/exhaustive_v9_*/parquet/` (gitignored, regenerable from raw data).

**Phase 2 (post-hoc structural analysis) — complete.**
Filed-effects regression and stress testing identified the structural patterns that produce viable Sharpe (state classification, optional/exclusive indicator policy, parameter ranges). The high-quality (HQ) candidate pool feeds Phase 3.

**Phase 3 (Optuna refinement on the reduced HQ space) — complete.**
Per-archetype Optuna with 3-fold cross-validation, holdout split frozen at `2025-10-01 → 2026-03-18`.

**Phase 4 (portfolio construction) — complete.**
Multi-TF cross-validated portfolio with risk-architecture diversification (8 archetypes spanning ATR/firestorm/fixed-pct stops × signal/chandelier/SAR trailing × fixed-fractional/ATR/Kelly sizing).

**Phase 4b/4c (validation suite) — complete.**
Eleven empirical tests applied to the final portfolio: equity-curve correlation matrix + greedy dedup, slippage stress (BPS sweep), regime stress (out-of-window replay), HO-vs-IS leak check, PBO, deflated Sharpe, bootstrap CI, Monte Carlo, borrow haircut, Hansen SPA, permutation null hypothesis. Results documented internally; the harness is reusable as a template (see [`docs/validation_framework.md`](docs/validation_framework.md)).

**Phase 5 (live) — pending.**
Recommended path: microsize 1% target × 8–12 weeks with rolling 4-week Sharpe monitoring. Triggers for ramp-up and stop are defined in the validation framework doc.

---

## What you can run

| Goal | Command |
|---|---|
| Verify install | `pytest -x -q` (1,468 tests, ~30 s) |
| Single backtest | See [`README.md`](README.md) "First run" example |
| Multi-TF discovery | `bash scripts/run_v9_15m.sh`, `run_v9_4h.sh`, `run_exhaustive_v9.sh` (overnight each) |
| Discovery analysis | `python scripts/analyze_discovery.py` |
| Anti-overfit gates | `python scripts/cross_validate_native.py`, `python scripts/run_null_hypothesis.py` |
| Portfolio replay with slippage | `python scripts/replay_with_slippage.py` |
| Paper trading | `python scripts/run_paper_portfolio.py` (requires Alpaca credentials) |

For per-step recipes see [`docs/cookbook.md`](docs/cookbook.md).

---

## Architecture invariants (do not change without an ADR)

1. **Frozen execution semantics** — `docs/modules/backtesting/execution_semantics.md` pins entry/exit timing, gap-aware stops, FSM evaluation order. Changes here invalidate prior backtests silently.
2. **Risk FSM contract** — `docs/modules/risk/spec.md` is the immutable per-bar evaluation order: `SL → TP1 → BE → trailing → entry/pyramid`.
3. **Holdout discipline** — split is fixed; never optimize on holdout, evaluate once at the end of Phase 4.
4. **Phase 1 = random, Phase 3 = Optuna** — see methodology rationale in [`docs/methodology.md`](docs/methodology.md). Reversing this order has been tried and failed (see [`docs/history.md`](docs/history.md)).
5. **Anti-overfit gates are mandatory, not optional** — PBO < 0.20, DSR > 0.95, SPA verified, permutation FP rate documented.

---

## Known limitations and honest caveats

These are intentionally surfaced (and also listed in the parent [`README.md`](../README.md#limitations-and-honest-caveats)):

1. **Borrow fees** are not subtracted inside the engine; the validation harness estimates a per-config haircut post-hoc.
2. **Slippage model** is per-symbol-per-TF lookup, not non-linear in size or volatility.
3. **Holdout is *partial* not *genuine* out-of-sample** in the strict sense — the HQ pool was filtered using statistics computed over the full dataset. The discipline compensates by isolating Optuna refinement and the final 6-month evaluation, but a fully clean OOS would require regenerating discovery without the holdout window.
4. **Live execution requires production hardening** (monitoring, alerting, kill-switch wiring, broker reconciliation) intentionally out of scope for the public repo.
5. **Tail risk in MC simulations** is bounded by sample length (168 days); not a substitute for stressed-scenario replay against historical extremes.

---

## Where the documentation lives

- [`docs/methodology.md`](docs/methodology.md) — pipeline, non-negotiable rules, risk search spaces
- [`docs/architecture.md`](docs/architecture.md) — module map, data flow, design patterns
- [`docs/history.md`](docs/history.md) — timeline of pipeline iterations and decisions
- [`docs/validation_framework.md`](docs/validation_framework.md) — TIER A/B/C test suite as reusable template
- [`docs/setup.md`](docs/setup.md) — installation and first run
- [`docs/modules/`](docs/modules/) — per-module deep dives

Internal research notes (`ANALYSIS_RESULTS.md`, `analysis_work/`, etc.) are gitignored and contain portfolio-specific configurations that are not part of the public deliverable.
