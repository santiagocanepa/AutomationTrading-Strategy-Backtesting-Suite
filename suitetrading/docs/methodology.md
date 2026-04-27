# Methodology — SuiteTrading v2

## The 5-phase pipeline

```
Phase 1 — Random exhaustive discovery
  Tool: scripts/run_random_v9.py + run_v9_{15m,1h,4h}.sh
  Method: Uniform random sampling over the full parameter space (no optimizer)
  Output: ~2M trials per timeframe, written to Parquet
  Stored: artifacts/exhaustive_v9_{15m,1h,4h}/parquet/  (gitignored)

Phase 2 — Post-hoc structural analysis
  Method: Pandas + fixed-effects regression + per-symbol stress tests
  Output: which structural features (state, TF, parameter range) predict
          viable Sharpe; HQ candidate pool
  Pass criterion: HQ pool ≥ 200 candidates with consistent patterns

Phase 3 — Optuna refinement on the reduced HQ space
  Method: Optuna (TPE/NSGA-II) with k-fold cross-validation, anti-overfit
          gates applied per archetype
  Gates: PBO < 0.20, DSR > 0.95, SPA verified, MIN_TRADES (TF-aware)
  Output: per-archetype validated finalists with full anti-overfit report

Phase 4 — Portfolio construction + cross-validation suite
  Method: greedy minimum-correlation pool selection across (asset, direction,
          archetype, TF); equity-curve dedup; slippage and regime stress
  Output: cross-TF, cross-archetype portfolio with effective N enforced
  Cross-validation: see validation_framework.md (TIER A/B/C tests)

Phase 5 — Paper trading + live
  Tool: scripts/run_paper_portfolio.py (Alpaca paper bridge)
  Live: requires production hardening intentionally out of scope here
```

The pipeline is **iterative** — failures at any phase loop back to the prior one. A failed PBO at Phase 3 means re-evaluating the Phase 2 HQ filter, not loosening the gate.

## Non-negotiable rules

| # | Rule | Rationale |
|---|------|-----------|
| 1 | Phase 1 is random, never an optimizer | The full parameter space is ≈10¹⁶ combinations. A Bayesian optimizer samples <10⁻⁹% and converges to local optima. Random gives unbiased structural signal. |
| 2 | Phase 3+ is Optuna, never random | Once the HQ space is identified (≈10² to 10³ combinations), random is wasteful. TPE/NSGA-II with k-fold CV is the right tool for the reduced space. |
| 3 | Risk management is the first-class citizen | Position management dominates expected value; entry signals select the trade, risk parameters define the outcome distribution. The risk search space is exhaustive (4 sizing × 6 trailing × 3 stop × pyramid/no-pyramid × multipliers). |
| 4 | Smoke test before any run > 1 hour | Past incident: an MDD computation bug cost 13 h of compute before being detected. A 30-trial smoke pass is mandatory before launching long runs. |
| 5 | Holdout is sacred | The chronological split (e.g. last 6 months of data) is never seen by Optuna. It is evaluated **once** at the end of Phase 4. If holdout-vs-IS Sharpe degradation > 30 %, methodology is reconsidered, not parameters. |
| 6 | Anti-overfit gates are gates, not metrics | PBO, DSR, SPA, permutation null are pass/fail conditions for promotion between phases. A strategy that fails any gate is rejected, not flagged. |
| 7 | No methodology change without explicit owner approval | Reverting Phase 1/3 ordering, loosening gates, or skipping validation has been tried in the past and produced spurious finalists (see [history.md](history.md)). |

## Archetype framework

The validated portfolio diversifies across **risk archetypes** rather than just entry indicators. An archetype is a configured combination of:

- **Stop policy** — `atr` (ATR-multiple), `firestorm_tm` (custom volatility band), `fixed_pct`
- **Trailing policy** — `signal` (signal-driven), `atr` (ATR distance), `chandelier`, `parabolic_sar`, `fixed`, `break_even`
- **Sizing policy** — `fixed_fractional`, `atr` (volatility-targeted), `kelly`, `optimal_f`
- **Take-profit policy** — `r_multiple`, `signal`, `fixed_pct`, partial-vs-full
- **Pyramid policy** — `enabled` (max adds, weighting, block bars) or `disabled`
- **Break-even and time-exit** — modular toggles

Eight archetypes (A1 through A8) span the meaningful design space: classic trend, wide-pyramid trend, tight scalp, firestorm-signal, fixed-percent, let-it-run, chandelier-trail, ATR-sized. Each is benchmarked under all four anti-overfit gates per asset × direction × timeframe.

The framework is general — adding a ninth archetype is a configuration change in `risk/archetypes/`, not a code change.

## Risk search spaces

| Space | Keys | Used in | Notes |
|-------|------|---------|-------|
| `EXHAUSTIVE` | 3 keys (stop, TP_R, close_pct) | Phase 1 (random) | 480 combos, no pyramid |
| `RICH` | 11 keys | Phase 3+ (Optuna) | Full risk space with pyramid, sizing, BE |
| `DEFAULT` | 9 keys | Fallback | |
| `LEAN` | 3 keys | Smoke tests | |

Phase 1 deliberately uses the smaller `EXHAUSTIVE` space because the goal is to find what *entry indicator* combinations are viable; full risk exploration happens in Phase 3 on the already-pruned space.

## Validation gates (Phase 3 + 4)

| Metric | Threshold | Reference |
|--------|-----------|-----------|
| Deflated Sharpe Ratio | > 0.95 | Bailey et al. 2014 |
| Annualized Sharpe | > 0.80 | Per archetype × asset × direction |
| PBO (Combinatorially Symmetric CV) | < 0.20 | Bailey & López de Prado 2014 |
| Hansen SPA p-value | verified | Hansen 2005 |
| Trades (per fold) | ≥ TF-aware threshold | 1h: 300, 4h: 80, 15m: 500 |
| Max DD (p95 across folds) | < 25 % | Risk constraint |
| Permutation null FP rate | < 5 % | Pipeline meta-validation |

The TF-aware trade thresholds reflect the bar-count differences across timeframes: 4 h holdout produces ~10× fewer bars than 15m holdout, so applying the same minimum-trades threshold cross-TF is meaningless.

## Holdout discipline

The chronological split is fixed at `2025-10-01 → 2026-03-18` for the current research cycle. During Phase 1–3 the holdout is **inaccessible** to any optimizer, filter, or sampler. At the end of Phase 4 it is evaluated **once**, producing the final pre-live performance number.

If the deployment cycle requires re-tuning, the methodology mandates:

1. Roll the holdout forward (define a new cutoff)
2. Regenerate Phase 1 discovery on the new pre-holdout window (so the new HQ pool is honest OOS)
3. Re-run the entire pipeline

Under no circumstances does Phase 3 see the original holdout, even after a deployment cycle.

## Cross-validation suite (Phase 4b/4c)

After Phase 4 produces a portfolio, the cross-validation suite runs:

- **Equity-curve correlation matrix** + greedy dedup at ρ > 0.9 (preserves the best Sharpe per cluster)
- **Effective N** enforcement (eigenvalue-based participation ratio)
- **Slippage stress** at multiple BPS levels (retention curve)
- **Regime stress** (out-of-window replay under contrary regime)
- **HO vs IS scatter** (selection-bias diagnosis)
- **Bootstrap CI** on portfolio Sharpe (block-bootstrap, ≥10 k iterations)
- **Monte Carlo** simulation (block-bootstrap, MDD probability bounds)
- **Borrow haircut** (per-symbol annualized estimates × short trade time-in-position)

Each test produces a pass/fail or a quantified haircut. Failures generate a config-level remediation list (drop / reduce / remediate). The framework is documented as a reusable template in [`validation_framework.md`](validation_framework.md).

## References

- López de Prado, M. (2018). *Advances in Financial Machine Learning*.
- Bailey, D. & López de Prado, M. (2014). The Probability of Backtest Overfitting.
- Bailey, D., Borwein, J., López de Prado, M., & Zhu, Q. J. (2014). The Deflated Sharpe Ratio.
- Hansen, P. R. (2005). A Test for Superior Predictive Ability.
