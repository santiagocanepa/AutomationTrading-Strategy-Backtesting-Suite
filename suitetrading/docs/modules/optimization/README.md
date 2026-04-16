# optimization

`src/suitetrading/optimization/`

Hyperparameter search, walk-forward validation, and anti-overfitting filters.
Current pipeline uses **random exhaustive search** (Phase 1) + **Optuna TPE/NSGA-II** (Phase 3 WFO).

---

## Files

| File | LOC | Responsibility |
|---|---|---|
| `_internal/objective.py` | 798 | `BacktestObjective` — Optuna trial → signals → backtest. Defines 5 risk search spaces. |
| `_internal/schemas.py` | 161 | `WFOConfig`, `WFOResult`, `OptimizationResult`, `AntiOverfitResult` |
| `optuna_optimizer.py` | 257 | `OptunaOptimizer` — study creation, TPE / NSGA-II / random samplers, SQLite persistence |
| `walk_forward.py` | 453 | `WalkForwardEngine` — rolling and anchored IS/OOS k-fold splits |
| `anti_overfit.py` | 446 | `CSCVValidator` (PBO), `deflated_sharpe_ratio`, `hansen_spa` |
| `feature_importance.py` | 196 | fANOVA parameter importance from completed study |
| `null_hypothesis.py` | 713 | Null hypothesis permutation tests |
| `rolling_validation.py` | 595 | Rolling walk-forward validator |
| `parallel.py` | 171 | `ProcessPoolExecutor` wrapper for parallel trial evaluation |
| `deap_optimizer.py` | 205 | DEAP NSGA-II — **legacy, not in current pipeline** |

---

## Risk Search Spaces

Defined in `_internal/objective.py`. All spaces optimise the FSM trade-management layer; indicator params are searched separately.

| Space | Dimensions | Approx. combinations | Used in |
|---|---|---|---|
| `EXHAUSTIVE_RISK_SPACE` | 3 (stop, TP R-mult, close %) | 480 | Phase 1 random exhaustive (`run_random_v9.py`) |
| `DEFAULT_RISK_SEARCH_SPACE` | 8 | ~290 M | Phase 3 Optuna baseline |
| `LEAN_RISK_SEARCH_SPACE` | 3 (coarser steps) | ~324 | Phase 3 Optuna fast validation |
| `RICH_RISK_SEARCH_SPACE` | 10 (+TP trigger, BE activation) | >290 M | Phase 3 Optuna with mode search |
| `V8_RISK_SEARCH_SPACE` | 8 (evidence-narrowed from v7/v8) | ~95% fewer than RICH | Phase 3 legacy (v8) |

---

## Pipeline Phases

| Phase | Script | Optimizer | Space |
|---|---|---|---|
| 1 — Exploration | `scripts/run_random_v9.py` | None (random) | `EXHAUSTIVE_RISK_SPACE` × full indicator grid |
| 2 — Filter | `scripts/build_candidate_pool.py` | — | PBO filter + slippage replay |
| 3 — WFO validation | `scripts/run_discovery.py` | Optuna TPE / NSGA-II | `DEFAULT` or `LEAN` |
| 4 — Portfolio | `scripts/run_portfolio.py` | Optuna + `PortfolioOptimizer` | Correlation + weight optimization |

---

## Key API

### `OptunaOptimizer`
```python
opt = OptunaOptimizer(
    objective=my_objective,
    study_name="btcusdt_1h_v3",
    storage="sqlite:///studies.db",   # None for in-memory
    sampler="tpe",                    # "tpe" | "random" | "nsga2" | "cmaes"
    directions=["maximize", "maximize"],  # multi-objective (NSGA-II)
    seed=42,
)
result = opt.optimize(n_trials=500, n_jobs=4)
top = opt.get_top_n(n=50, min_trades=30)
```

### `WalkForwardEngine`
```python
wfe = WalkForwardEngine(config=WFOConfig(n_folds=5, mode="rolling"), metric="sharpe")
splits = wfe.generate_splits(n_bars=len(df))  # list[(is_range, oos_range)]
```

### `CSCVValidator`
```python
validator = CSCVValidator(n_subsamples=16, metric="sharpe")
result = validator.validate(equity_curves)  # returns PBO in [0, 1]
# PBO < 0.30 is the pass threshold used by build_candidate_pool.py
```

---

## Tests

```bash
cd suitetrading && pytest tests/optimization/ -v
```
