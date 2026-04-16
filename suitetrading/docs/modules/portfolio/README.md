# portfolio

Downstream pipeline for constructing and validating a live-tradeable portfolio from backtest finalists.
Implemented as scripts (not a src module); supporting classes live in `src/suitetrading/risk/`.

---

## Pipeline (ordered)

| Step | Script | Input | Output |
|---|---|---|---|
| 1. Build pool | `scripts/build_candidate_pool.py` | `discovery*/wfo_*.json` | `artifacts/candidate_pool/` |
| 2. Portfolio WFO | `scripts/portfolio_walkforward.py` | `artifacts/candidate_pool/` | `artifacts/portfolio_wfo/` |
| 3. Validate | `scripts/validate_portfolio.py` | `artifacts/discovery/evidence/`, `artifacts/portfolio/weights.json` | `artifacts/validation/` |
| 4. Build portfolio | `scripts/run_portfolio.py` | `artifacts/discovery/results/finalists.csv` + evidence dir | `artifacts/portfolio/` |
| 5. Paper trade | `scripts/run_paper_portfolio.py` | `artifacts/portfolio_locked/` | Alpaca paper orders + signal logs |

**Step 1→2→3 are validation gates. Step 4 is construction. Step 5 is execution.**

---

## Scripts

| Script | LOC | What it does |
|---|---|---|
| `build_candidate_pool.py` | 358 | Glob all `wfo_*.json`, filter `PBO < threshold` (default 0.30), replay each candidate with asset-aware slippage, persist equity curves |
| `portfolio_walkforward.py` | 260 | Split each equity curve IS 70% / OOS 30%; build portfolio (select + weights) on IS only; evaluate on OOS holdout |
| `validate_portfolio.py` | 429 | Ensemble PBO (CSCV), Deflated Sharpe Ratio, Hansen SPA, ruin probability; requires all four tests to pass |
| `run_portfolio.py` | 230 | Correlation analysis → strategy selection (`StrategySelector`) → weight optimisation (`PortfolioOptimizer`) → ensemble simulation |
| `run_paper_portfolio.py` | 151 | Load locked portfolio, instantiate one `SignalBridge` per strategy, consolidate via `PortfolioBridge`, submit to Alpaca paper |

---

## Supporting Modules

| Module | Class | Role |
|---|---|---|
| `src/suitetrading/risk/portfolio_optimizer.py` | `PortfolioOptimizer` | Max-Sharpe / risk-parity weight optimisation |
| `src/suitetrading/risk/portfolio_validation.py` | `PortfolioValidator` | Wraps CSCV + DSR + SPA into a single pass/fail |
| `src/suitetrading/risk/correlation.py` | `StrategyCorrelationAnalyzer`, `StrategySelector`, `DiversificationRatio` | Correlation matrix, greedy low-correlation selection |
| `src/suitetrading/backtesting/ensemble.py` | `EnsembleBacktester` | Portfolio equity curve simulation with optional rebalancing |

---

## Artifacts

| Artifact | Produced by | Contains |
|---|---|---|
| `artifacts/candidate_pool/` | `build_candidate_pool.py` | Per-candidate equity curves + metadata (post-slippage) |
| `artifacts/portfolio_wfo/` | `portfolio_walkforward.py` | IS/OOS split results, OOS portfolio metrics |
| `artifacts/validation/` | `validate_portfolio.py` | PBO, DSR, SPA, ruin probability — per-portfolio report |
| `artifacts/portfolio/` | `run_portfolio.py` | `weights.json`, correlation matrix, ensemble equity curve |
| `artifacts/portfolio_locked/` | Manual lock step | Frozen portfolio used for live/paper trading |

---

## Key Thresholds

- PBO filter: `< 0.30` (build_candidate_pool)
- IS / OOS split: 70% / 30% (portfolio_walkforward)
- Ruin probability gate: `< 0.01` (validate_portfolio)

---

## Tests

```bash
cd suitetrading && pytest tests/portfolio/ -v
```
