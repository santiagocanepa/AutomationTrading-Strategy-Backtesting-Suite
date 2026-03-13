# Optimization Methodology — Sprint 5

## Overview

The `suitetrading.optimization` module provides a statistically rigorous pipeline for strategy parameter optimisation with built-in anti-overfitting protections. The pipeline transforms raw parameter search into defended finalist strategies.

## Pipeline Architecture

```
Parameter Space → Optuna/DEAP Optimisation → Walk-Forward Validation → Anti-Overfit Filters → Finalists
```

### 1. Parameter Optimisation

**OptunaOptimizer** — Bayesian single-objective optimisation via Optuna TPE (Tree-structured Parzen Estimator).

- Samplers: TPE (default), Random, NSGA-II (multi-objective), CMA-ES
- Persistence: SQLite storage with `load_if_exists=True` for resume
- Pruning: Median pruner for early stopping of unpromising trials
- Search space: Automatically derived from `INDICATOR_REGISTRY.params_schema()` + configurable risk overrides

**DEAPOptimizer** — Multi-objective NSGA-II via DEAP (optional).

- Operators: Simulated Binary Crossover (SBX), Polynomial Mutation
- Output: Pareto-optimal front with trade-off solutions
- Use when: You need explicit Pareto front exploration beyond Optuna's NSGA-II sampler

### 2. Walk-Forward Optimization (WFO)

**WalkForwardEngine** — Produces out-of-sample equity curves to validate parameter stability.

- **Rolling mode**: Fixed-size IS/OOS windows slide forward in time
- **Anchored mode**: IS window anchors at t=0 and grows each fold; OOS slides forward
- Gap parameter: Optional bar gap between IS and OOS to prevent look-ahead
- Output: Concatenated OOS equity curves + degradation ratio (IS metric / OOS metric)

Recommended configuration:
- `n_splits=5`, `min_is_bars=500`, `min_oos_bars=100`
- Gap: 0 for daily data, up to 24 for hourly (one day buffer)
- Mode: `rolling` for regime sensitivity, `anchored` for maximum IS data

### 3. Anti-Overfitting Filters

**CSCVValidator** — Combinatorially Symmetric Cross-Validation (Bailey et al., 2017)

- Splits equity curves into S sub-samples
- Tests C(S, S/2) IS/OOS combinations
- PBO = P(ω ≤ 0) where ω = logit(relative OOS rank of IS-best)
- PBO > 0.50 → likely overfit

**deflated_sharpe_ratio()** — DSR (Bailey & López de Prado, 2014)

- Adjusts observed Sharpe for selection bias (number of trials tested)
- Accounts for non-normality (skewness, kurtosis)
- DSR > 0.95 → statistically significant
- Critical for large search spaces where E[max(SR)] under null is high

**Hansen SPA Test** — Superior Predictive Ability (optional, requires `arch`)

- Tests if strategy returns significantly exceed a benchmark (buy-and-hold)
- Bootstrap-based p-value < 0.05 → strategy is genuinely superior

**AntiOverfitPipeline** — Sequential filter combining all three tests.

### 4. Feature Importance (Optional)

**FeatureImportanceEngine** — XGBoost meta-model + SHAP for search space analysis.

- Identifies which parameters actually drive performance
- Suggests search space reduction (drop irrelevant parameters)
- Mutual Information matrix for detecting parameter interactions

## Recommended Configuration

| Parameter | Conservative | Moderate | Aggressive |
|-----------|-------------|----------|------------|
| Optuna trials | 200 | 500 | 2000 |
| WFO splits | 5 | 5 | 7 |
| WFO mode | rolling | rolling | anchored |
| CSCV subsamples | 16 | 16 | 16 |
| PBO threshold | 0.40 | 0.50 | 0.60 |
| DSR threshold | 0.95 | 0.95 | 0.90 |
| SPA significance | 0.05 | 0.05 | 0.10 |

## Theoretical Foundation

1. **CSCV** prevents selecting strategies that appear best only due to data snooping in-sample
2. **DSR** corrects the Sharpe ratio for the multiple-testing problem inherent in parameter search
3. **Hansen SPA** provides a formal test of predictive superiority against a naive benchmark
4. **WFO degradation ratio** quantifies how much performance degrades out-of-sample (ratio > 2 is concerning)

Together, these filters ensure that only strategies with genuine out-of-sample alpha and statistical significance enter the finalist pool.
