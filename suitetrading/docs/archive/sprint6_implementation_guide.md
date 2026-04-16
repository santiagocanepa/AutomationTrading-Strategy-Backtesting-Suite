# Sprint 6 — Implementation Guide

> Execution order, phases, and checklist for Mass Discovery & Paper Trading.

---

## Phase 0: Pre-Flight (before coding)

- [ ] Verify 668 tests passing: `cd suitetrading && .venv/bin/pytest -q`
- [ ] Verify data freshness: 3 symbols × 1m range includes recent data
- [ ] Configure Alpaca paper credentials in `.env` or environment variables
- [ ] Ensure `arch` package is installed (for Hansen SPA): `.venv/bin/pip install arch>=7.0`

---

## Phase A: Discovery Infrastructure (T6.1–T6.2)

### Step A.1 — Add `run_single()` to BacktestObjective

**File**: `src/suitetrading/optimization/_internal/objective.py`

Add ability to run a single backtest with explicit params (no Optuna trial needed).
This is required by WFO, which re-evaluates the top-N param sets on different
data splits.

```python
def run_single(self, params: dict[str, Any]) -> dict[str, Any]:
    indicator_params, risk_overrides = self._split_params(params)
    signals = self.build_signals(indicator_params)
    risk_config = self.build_risk_config(risk_overrides)
    result = self._engine.run(
        dataset=self._dataset, signals=signals,
        risk_config=risk_config, mode=self._mode, direction=self._direction,
    )
    metrics = self._metrics_engine.compute(
        equity_curve=result["equity_curve"],
        trades=result.get("trades"),
        initial_capital=risk_config.initial_capital,
    )
    return {"equity_curve": result["equity_curve"], "metrics": metrics, "trades": result.get("trades")}
```

Also add `_split_params()` that partitions a flat Optuna params dict into
`indicator_params` and `risk_overrides`.

**Tests**: Verify `run_single(best_trial.params)` produces same metrics as `__call__(trial)`.

### Step A.2 — Define archetype → indicator mapping

**File**: `scripts/run_discovery.py`

```python
ARCHETYPE_INDICATORS = {
    "trend_following": ["ssl_channel", "firestorm", "firestorm_tm"],
    "mean_reversion": ["wavetrend_reversal"],
    "mixed": ["ssl_channel", "wavetrend_reversal", "firestorm"],
}
```

Keep it simple: each archetype gets 1-3 indicators, no Optuna indicator selection
in phase 1. Can add `indicator_selection=True` later for phase 2+ re-runs.

### Step A.3 — Create `run_discovery.py` orchestrator

**File**: `scripts/run_discovery.py`

Core logic:

```python
for symbol in symbols:
    ohlcv_1m = store.read("binance", symbol, "1m")
    for tf in timeframes:
        ohlcv = resampler.resample(ohlcv_1m, tf)
        dataset = build_dataset_from_df(ohlcv, ...)

        for archetype in archetypes:
            study_name = f"{symbol}_{tf}_{archetype}"
            indicators = ARCHETYPE_INDICATORS[archetype]
            storage = f"sqlite:///{artifacts_dir}/studies/{study_name}.db"

            objective = BacktestObjective(
                dataset=dataset,
                indicator_names=indicators,
                archetype=archetype,
                metric="sharpe",
                mode="fsm",
            )

            optimizer = OptunaOptimizer(
                objective=objective,
                study_name=study_name,
                storage=storage,
                sampler="tpe",
                n_trials=args.trials,
            )
            result = optimizer.optimize(n_trials=args.trials)
            top50 = optimizer.get_top_n(50)

            # Export top 50
            pd.DataFrame(top50).to_csv(results_dir / f"top50_{study_name}.csv")
```

CLI:
```bash
python scripts/run_discovery.py \
    --symbols BTCUSDT ETHUSDT SOLUSDT \
    --timeframes 15m 1h 4h 1d \
    --archetypes trend_following mean_reversion mixed \
    --trials 500 \
    --output-dir artifacts/discovery
```

Features:
- Resume support (Optuna `load_if_exists=True`)
- Progress logging per study
- Skip completed studies (check trial count ≥ n_trials)
- Export top-50 per study to CSV

### Step A.4 — Tests for orchestrator

**File**: `tests/optimization/test_discovery.py`

- E2E test with synthetic 200-bar data, 10 trials, 1 symbol, 1 TF, 1 archetype
- Verify study persisted to SQLite
- Verify top-50 CSV created
- Verify `run_single()` roundtrip

---

## Phase B: Analysis Pipeline (T6.4–T6.7)

### Step B.1 — WFO on top-50 per study

After all 36 studies complete, run WFO:

```python
wfo = WalkForwardEngine(n_splits=5, min_is_bars=500, min_oos_bars=100, gap_bars=20)

for study_name in completed_studies:
    top50 = load_top50(study_name)
    dataset = load_dataset(study_name)
    objective = build_objective(study_name, dataset)

    wfo_result = wfo.evaluate(
        dataset=dataset,
        param_sets=[row["params"] for row in top50],
        backtest_fn=objective.run_single,
        metric="sharpe",
    )
    # Save degradation ratios + OOS metrics
```

### Step B.2 — Anti-overfit filtering

```python
pipeline = AntiOverfitPipeline(
    cscv_n_subsamples=16,
    dsr_significance=0.05,
    spa_significance=0.10,
)

for study_name in studies_with_wfo:
    wfo_result = load_wfo_result(study_name)
    buy_hold = compute_buy_and_hold(dataset)

    result = pipeline.run(
        equity_curves=wfo_result.oos_equity_curves,
        n_trials=len(all_trials),
        benchmark_returns=buy_hold,
    )

    for finalist_id in result.finalists:
        save_evidence_card(study_name, finalist_id, result)
```

### Step B.3 — Create `analyze_discovery.py`

**File**: `scripts/analyze_discovery.py`

Reads all study artifacts, produces:
1. `finalists.csv` — Global ranking of all finalists across studies
2. `discovery_report.md` — Summary statistics + evidence
3. Per-finalist JSON evidence cards

### Step B.4 — Feature importance (optional)

If `xgboost` + `shap` are available:

```python
from suitetrading.optimization import FeatureImportanceEngine

fie = FeatureImportanceEngine()
for study_name in top_studies:
    importance = fie.analyze(study_trials, target="sharpe")
    # Save SHAP plots + importance ranking
```

---

## Phase C: Execution Layer (T6.8–T6.11)

### Step C.1 — Create execution module structure

```
src/suitetrading/execution/
├── __init__.py
├── alpaca_executor.py
└── signal_bridge.py
```

### Step C.2 — Implement `AlpacaExecutor`

**Key design decisions**:
- Uses `alpaca-py` `TradingClient` (same package already installed)
- `paper=True` sets `paper=True` in `TradingClient` constructor (automatic URL routing)
- Synchronous API (alpaca-py's `TradingClient` is sync, wrapping in async unnecessary for now)
- All orders logged with timestamp + params + result
- No retries on order submission — fail fast, log, continue

```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
```

### Step C.3 — Implement `SignalBridge`

Maps backtest signals to execution actions:

```
Entry signal + no position → submit bracket order (entry + SL + TP)
Exit signal + has position → close position
Neither → no-op
```

State tracking:
- Current position (from executor.get_positions())
- Last signal bar (to avoid double-entry)
- Entry price (for break-even/trailing calculations)

**Simplification for v1**: No pyramiding, no partial TP, no trailing in paper v1.
Just entry → bracket (SL + TP) → wait for fill or signal exit.

### Step C.4 — Create `run_paper.py`

**File**: `scripts/run_paper.py`

```bash
python scripts/run_paper.py \
    --finalist-id BTCUSDT_4h_mean_reversion__trial_42 \
    --paper \
    --poll-interval 240  # 4 min for 4h bars
```

Core loop:
1. Load finalist config (indicator params + risk config)
2. Initialize executor + bridge
3. Poll for new bars at timeframe interval
4. Compute signals on latest data (rolling window)
5. Call `bridge.on_bar()`
6. Log everything

### Step C.5 — Tests

**File**: `tests/execution/test_alpaca_executor.py`

- Mock `TradingClient` entirely
- Test order submission → OrderResult mapping
- Test error handling (insufficient funds, market closed, etc.)
- Test position reconciliation

**File**: `tests/execution/test_signal_bridge.py`

- Test entry signal → order created
- Test exit signal → position closed
- Test no signal → no action
- Test duplicate signal suppression

---

## Phase D: Validation (Sprint close)

### Step D.1 — Run full test suite

```bash
cd suitetrading && .venv/bin/pytest -q
# Target: all pre-existing tests pass + all new tests pass
```

### Step D.2 — Execute mass discovery

Run the full 36 studies. This is the real deliverable.

### Step D.3 — Document finalists

Create `docs/discovery_report.md` with:
- How many strategies entered each filter stage
- How many survived CSCV, DSR, SPA
- Top 10-20 finalist cards with: params, OOS Sharpe, OOS MaxDD, PBO, DSR
- Recommendations for paper trading

### Step D.4 — Start paper trading

Launch ≥1 finalist on Alpaca paper. Let it run ≥48h.

---

## Checklist

### Phase A
- [ ] `run_single()` added to `BacktestObjective`
- [ ] `_split_params()` utility
- [ ] `scripts/run_discovery.py` created
- [ ] Discovery E2E test passing
- [ ] Small-scale test run (1 symbol, 1 TF, 1 archetype, 20 trials) succeeds

### Phase B
- [ ] WFO integration in discovery pipeline
- [ ] Anti-overfit filtering integrated
- [ ] `scripts/analyze_discovery.py` created
- [ ] Evidence card generation working

### Phase C
- [ ] `src/suitetrading/execution/` module created
- [ ] `AlpacaExecutor` implemented + tested
- [ ] `SignalBridge` implemented + tested
- [ ] `scripts/run_paper.py` created

### Phase D
- [ ] Full test suite green
- [ ] 36 Optuna studies completed (or max feasible)
- [ ] `docs/discovery_report.md` written
- [ ] ≥1 finalist running on Alpaca paper
- [ ] All docs created: master plan, tech spec, impl guide, discovery report
