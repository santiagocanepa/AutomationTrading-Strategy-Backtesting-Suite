# Validation framework — cross-validation suite for a trading portfolio

This document describes the test suite applied to a portfolio at the end of Phase 4. The framework is **independent of the specific portfolio** — it accepts any pool of (config, equity-curve, return-stream) tuples and produces a pass/fail / quantified-haircut report per test.

The goal is not to validate one portfolio: it is to provide a reusable harness that any future portfolio (this v9 cycle, v10, a different asset class) must pass through before promotion to live.

---

## Why this exists

A backtest Sharpe is a noisy point estimate. A portfolio Sharpe is more robust but still subject to:

1. **Selection bias** — the "best" configs from a search are biased upward
2. **Effective N illusion** — N nominal configs may have effective diversification of <0.3·N
3. **Slippage / borrow / latency haircuts** — the engine doesn't model production friction perfectly
4. **Regime fragility** — configs selected on a specific holdout regime may collapse outside it
5. **Tail risk** — finite-sample Sharpe and MDD don't bound left-tail outcomes

The validation framework addresses each one explicitly with an empirical test, not a hand-wave.

---

## Tiers

The suite is organized into three tiers by risk-of-promotion:

### TIER A — Replication and consistency

Tests that verify the portfolio can be replayed deterministically and that the metrics are internally consistent.

| Test | What it measures | Pass criterion |
|------|------------------|----------------|
| **A1 — Permutation null hypothesis** | FP rate of the optimization sub-pipeline on shuffled OHLCV | < 5–10 % (configurable; depends on whether Optuna is the discoverer) |
| **A2 — Replication exactness** | Δ Sharpe between original run and replay | = 0 (deterministic) |
| **A3 — Anti-overfit reaffirmation** | PBO + DSR recomputed on the final selected portfolio | PBO < 0.5, portfolio DSR > 0.95 |
| **A4 — Metric consistency** | Spearman correlation between Sharpe / Sortino / Calmar | > 0.9 (low correlation = fat-tailed, suspicious) |

### TIER B — Sensitivity and robustness

Tests that probe the portfolio under perturbations.

| Test | What it measures | Pass criterion |
|------|------------------|----------------|
| **B1 — Borrow haircut** | Per-config Sharpe haircut from borrow fees on shorts | Median haircut < 5 % |
| **B2 — Slippage stress** | Sharpe retention curve at BPS ∈ {0, 2, 5, 10} | ≥ 70 % retention at 5 BPS for ≥ 80 % of configs |
| **B3 — Bootstrap CI** | Block-bootstrap 95 % CI on portfolio Sharpe | P(Sharpe < 0) = 0 |
| **B4 — Monte Carlo** | Stationary block-bootstrap on returns; final wealth distribution + MDD probability | P(loss at 1y) < 5 %, P(MDD < −20 %) bounded |
| **B5 — Regime stress** | Replay portfolio over a contrary historical regime | Aggregate Sharpe stays positive; regime-fragile configs flagged |

### TIER C — Structural diagnostics

Tests that characterize the portfolio's diversification and selection quality.

| Test | What it measures | Pass criterion |
|------|------------------|----------------|
| **C1 — Equity-curve correlation matrix** | N × N pairwise correlation on aligned daily returns | Median ρ < 0.1 |
| **C2 — Greedy dedup** | Drop configs at ρ > 0.9 within a cluster, keep best Sharpe | Effective N / nominal N ≥ 50 % post-dedup |
| **C3 — HO vs IS scatter** | Selection-bias diagnosis: are HO configs systematically below diagonal? | Median (HO − IS) > −0.5 (mild regression-to-mean acceptable) |
| **C4 — Effective N (eigenvalue)** | Eigenvalue-based participation ratio of the correlation matrix | ≥ 8–12 for a portfolio of 26 configs (case-dependent) |

---

## Order of operations

The tests are not independent — running them in the wrong order produces misleading conclusions:

```
1. C1 + C2 (correlation + dedup)
   → produces the *deduplicated* portfolio used by every subsequent test

2. A1 + A2 + A3 + A4 (replication + anti-overfit reaffirmation)
   → confirms the deduplicated portfolio is well-formed

3. B1 + B2 (borrow + slippage)
   → friction haircut, applied per-config

4. B5 (regime stress)
   → identifies regime-fragile configs that survived dedup but fail under contrary regime

5. C3 (selection bias check)
   → done last because it requires the full pre-selection pool for comparison

6. B3 + B4 (bootstrap + Monte Carlo)
   → final aggregate confidence intervals on the cleaned portfolio
```

Failing a test at step 1 invalidates everything downstream — re-run from there.

---

## Effective N — eigenvalue method vs correlation-mean

Two formulas are commonly used:

```
# Newton-Lewis correlation-mean estimator (conservative)
N_eff = 1 + (N − 1) / (1 + (N − 1) · ρ̄)     where ρ̄ is the mean off-diagonal correlation

# Eigenvalue participation ratio (sensitive to outliers)
N_eff = (Σ λᵢ)² / Σ λᵢ²                       where λᵢ are eigenvalues of the corr matrix
```

Both are reported. The eigenvalue method is more sensitive to a few highly correlated pairs; the correlation-mean is more conservative. A portfolio that passes both is structurally well-diversified.

For a portfolio of 26 configs, an effective N of 14–17 (53–65 %) is acceptable. Below 50 % is a flag for further dedup.

---

## What the framework deliberately does *not* do

1. **It does not validate the methodology itself** — that is the job of the permutation null hypothesis test, run *before* portfolio selection (it lives in `optimization/null_hypothesis.py`).
2. **It does not produce live trading sizing** — the haircuts inform sizing, but the sizing decision is a separate step that requires position-level risk inputs (per-config volatility, correlation with existing book, etc.).
3. **It does not certify the portfolio for live deployment** — passing the suite is a *necessary* condition. The recommended path is microsize live (1 % of target capital) for 8–12 weeks with rolling 4-week Sharpe monitoring before ramping up.

---

## When to re-run the suite

The suite must be re-run whenever:

- The underlying engine changes (e.g. FSM order of operations, slippage model)
- A new archetype is added to the portfolio
- The holdout window is rolled forward (this requires regenerating Phase 1 too)
- A live cycle completes and the portfolio is reconstituted with feedback

It should **not** be re-run as a way of "looking for a better portfolio" on the same data — that defeats the purpose. The suite is a gate, not an exploration tool.

---

## Implementation notes

- The harness lives under `analysis_work/phase4{b,c}_*.py` (gitignored — contains portfolio-specific paths). The structure is reusable: each test is a small script that consumes a `(config, params, equity_curve, returns)` tuple and emits a JSON / Parquet result.
- For replication, equity curves are recomputed from the engine using the original parameters; an exact match (Δ Sharpe = 0.0000) confirms determinism.
- Bootstrap and Monte Carlo use stationary block bootstrap with block size = 5 days (a typical compromise between preserving autocorrelation and producing enough variation).
- The borrow rates are IBKR-style annualized estimates per symbol; revise per broker.

---

## References

- Bailey, D. & López de Prado, M. (2014). The Probability of Backtest Overfitting.
- Bailey, D., Borwein, J., López de Prado, M., & Zhu, Q. J. (2014). The Deflated Sharpe Ratio.
- Hansen, P. R. (2005). A Test for Superior Predictive Ability.
- Politis, D. N. & Romano, J. P. (1994). The Stationary Bootstrap.
- Newton-Lewis, J. (effective N estimator, communicated in industry practice)
