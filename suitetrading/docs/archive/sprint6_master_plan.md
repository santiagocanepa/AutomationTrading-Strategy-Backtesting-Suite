# Sprint 6 — Mass Discovery & Paper Trading

> Date: 2026-03-12
> Baseline: Sprint 5.5 CLOSED — 668 tests, 0 failures, 216 risk lab campaigns

## 1. Rationale

The full optimization pipeline (Optuna + WFO + CSCV + DSR) was built and
unit-tested in Sprint 5, but **it has never been run at scale with real data**.
The risk lab (Sprint 5.5, 216 campaigns) used fixed indicator params and only
varied risk presets. There are zero documented Optuna studies, zero WFO reports,
and zero anti-overfit finalists.

Without real discovery results, there's nothing to port to production — not to
NautilusTrader, not to Alpaca, not to anything.

**Key decisions:**

1. **NautilusTrader → DEFERRED.** It solves tick-by-tick L2 fill simulation,
   which is relevant only for HFT or sub-minute strategies. Our archetypes
   operate on 15m–1d bars. Papertrading on Alpaca is a faster, simpler path to
   live validation.
2. **Alpaca already integrated** (data download, `alpaca-py>=0.43`). The same
   library includes `TradingClient` for paper/live execution with zero API
   change between paper and production.
3. **Discovery first, execution second.** No point building a live layer without
   candidates worth running.

## 2. Sprint Goal

> Execute the first large-scale strategy discovery, apply the full
> anti-overfitting pipeline, document 10-20 evidence-backed finalists,
> and stand up a lightweight Alpaca paper-trading execution layer.

## 3. Scope

### Phase A — Mass Discovery (Task 6.1–6.3)

| Dimension | Values |
|-----------|--------|
| Symbols | BTCUSDT, ETHUSDT, SOLUSDT |
| Timeframes | 15m, 1h, 4h, 1d |
| Archetypes | trend_following, mean_reversion, mixed |
| Optuna trials | 500–1000 per cell |
| Optimizer | TPE (single-obj: Sharpe) + optional NSGA-II (Sharpe × -MaxDD) |
| Search space | `active` maturity only (7 risk + 5 indicator dims) |
| WFO | rolling, 5 folds, 500 IS / 100 OOS bars |
| Anti-overfit | CSCV (PBO < 0.50) → DSR (p < 0.05) → SPA (p < 0.10) |

**Matrix size**: 3 symbols × 4 TFs × 3 archetypes = **36 Optuna studies**.
At 500 trials each → 18,000 backtests. At ~64 bt/sec → ~5 min per study,
~3 hours total. At 1000 trials → ~6 hours total.

### Phase B — Analysis & Finalist Selection (Task 6.4–6.5)

- Aggregate results across all 36 studies
- Apply WFO + CSCV + DSR per study
- Rank survivors by OOS Sharpe × degradation ratio
- Produce top 10-20 finalists with evidence cards
- Feature importance analysis (SHAP) on top performers

### Phase C — Lightweight Execution Layer (Task 6.6–6.8)

- `AlpacaExecutor` class (paper/live via `TradingClient`)
- Signal-to-order bridge using existing `StrategySignals` + `RiskConfig`
- Position monitoring and state reconciliation
- Minimal CLI: `run_paper.py --strategy <finalist_id>`

## 4. Explicit Non-Goals

- NautilusTrader integration (deferred to Sprint 7+, only if HFT needed)
- VectorBT PRO dependency (engine is custom, no VBT needed)
- Multi-exchange execution (Alpaca only for now)
- Short-side paper trading (long-only initially)
- Full portfolio optimizer (single-strategy execution first)

## 5. Task Breakdown

### Phase A — Discovery

| ID | Task | Depends | Deliverable |
|----|------|---------|-------------|
| T6.1 | Create `run_discovery.py` orchestrator | — | `scripts/run_discovery.py` |
| T6.2 | Extend `BacktestObjective` for multi-indicator subsets | T6.1 | Updated `objective.py` |
| T6.3 | Execute 36 Optuna studies (500-1000 trials each) | T6.1 | `artifacts/discovery/` SQLite + CSV |

### Phase B — Analysis

| ID | Task | Depends | Deliverable |
|----|------|---------|-------------|
| T6.4 | Run WFO on top 50 per study | T6.3 | WFO results per study |
| T6.5 | Apply CSCV + DSR + SPA filters | T6.4 | Filtered finalists |
| T6.6 | Generate finalist evidence cards | T6.5 | `docs/discovery_report.md` |
| T6.7 | Feature importance analysis | T6.3 | `docs/feature_importance_report.md` |

### Phase C — Execution

| ID | Task | Depends | Deliverable |
|----|------|---------|-------------|
| T6.8 | Implement `AlpacaExecutor` | — | `src/suitetrading/execution/alpaca_executor.py` |
| T6.9 | Implement signal-to-order bridge | T6.8 | `src/suitetrading/execution/signal_bridge.py` |
| T6.10 | Implement `run_paper.py` CLI | T6.8-9, T6.6 | `scripts/run_paper.py` |
| T6.11 | Paper trading tests (mocked) | T6.8-9 | `tests/execution/` |

## 6. Dependencies

| Dependency | Status | Action |
|-----------|--------|--------|
| `alpaca-py>=0.43` | Installed | Already in `[data]` optional group |
| `optuna>=3.5` | Installed | Core dependency |
| `arch>=7.0` | Installed | For Hansen SPA |
| Alpaca paper API key | NEEDED | User must configure `.env` / settings |
| 3 symbols × 1m data | Available | 4.5M+ rows each, 2017-2026 |

## 7. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Zero strategies survive anti-overfit | Medium | High | Relax DSR to p<0.10, analyze CSCV distribution, expand indicator set |
| Discovery run takes >12h | Low | Medium | Start with 500 trials, parallelize studies on separate cores |
| Alpaca API latency causes missed fills | Low | Low | Paper mode tolerates latency; log all fill discrepancies |
| Search space too narrow (only `active` dims) | Medium | Medium | Phase 2: promote `partial` dims and re-run |

## 8. Success Criteria

| Criterion | Threshold |
|-----------|-----------|
| Optuna studies completed | 36/36 (3 sym × 4 TF × 3 arch) |
| Trials per study | ≥ 500 |
| WFO applied to | Top 50 per study |
| Finalists with PBO < 0.50 | ≥ 10 |
| Finalists with DSR p < 0.05 | ≥ 5 |
| Paper trading running | ≥ 1 finalist on Alpaca paper |
| Paper runtime without crash | ≥ 48h |

## 9. Artifacts

```
artifacts/discovery/
├── studies/                          # Optuna SQLite DBs
│   ├── BTCUSDT_15m_trend_following.db
│   ├── BTCUSDT_15m_mean_reversion.db
│   └── ... (36 total)
├── results/                          # Exported CSV summaries
│   ├── top50_per_study.csv
│   ├── wfo_results.csv
│   └── finalists.csv
├── evidence/                         # Per-finalist evidence cards
│   ├── finalist_001.json
│   └── ...
└── reports/
    ├── discovery_summary.md
    └── feature_importance.md

scripts/
├── run_discovery.py                  # NEW: Mass discovery orchestrator
├── analyze_discovery.py              # NEW: Post-run analysis
└── run_paper.py                      # NEW: Paper trading runner

src/suitetrading/execution/
├── __init__.py
├── alpaca_executor.py               # NEW: Alpaca paper/live execution
└── signal_bridge.py                 # NEW: Signal → Order translation
```
