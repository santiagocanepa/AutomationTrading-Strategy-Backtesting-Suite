# Sprint 6 — Technical Specification

> Complements `sprint6_master_plan.md` with contracts, data flows, and
> architecture decisions.

---

## 1. Discovery Orchestrator Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                   run_discovery.py (CLI)                        │
│                                                                 │
│  for symbol in [BTC, ETH, SOL]:                                │
│    for tf in [15m, 1h, 4h, 1d]:                                │
│      load 1m data → resample to tf                             │
│      for archetype in [trend, meanrev, mixed]:                 │
│        ┌──────────────────────────────────┐                    │
│        │ Phase 1: Optuna Discovery        │                    │
│        │  BacktestObjective(dataset, arch)│                    │
│        │  OptunaOptimizer.optimize(N)     │                    │
│        │  → SQLite study + top 50 trials  │                    │
│        └──────────────┬───────────────────┘                    │
│                       ▼                                         │
│        ┌──────────────────────────────────┐                    │
│        │ Phase 2: Walk-Forward Validation │                    │
│        │  WalkForwardEngine.evaluate()    │                    │
│        │  → OOS equity curves per trial   │                    │
│        │  → degradation ratios            │                    │
│        └──────────────┬───────────────────┘                    │
│                       ▼                                         │
│        ┌──────────────────────────────────┐                    │
│        │ Phase 3: Anti-Overfit Filtering  │                    │
│        │  AntiOverfitPipeline.run()       │                    │
│        │  → CSCV (PBO) → DSR → SPA       │                    │
│        │  → finalists with evidence       │                    │
│        └──────────────────────────────────┘                    │
│                                                                 │
│  Aggregate finalists → rank → export                           │
└─────────────────────────────────────────────────────────────────┘
```

### Study Naming Convention

```
{symbol}_{timeframe}_{archetype}

Examples:
  BTCUSDT_1h_trend_following
  SOLUSDT_4h_mean_reversion
  ETHUSDT_15m_mixed
```

### Storage

- **Optuna studies**: `artifacts/discovery/studies/{study_name}.db` (SQLite)
- **Top results CSV**: `artifacts/discovery/results/top50_{study_name}.csv`
- **WFO outputs**: `artifacts/discovery/results/wfo_{study_name}.json`
- **Finalists**: `artifacts/discovery/results/finalists.csv`
- **Evidence**: `artifacts/discovery/evidence/{finalist_id}.json`

---

## 2. BacktestObjective Enhancements

### Current limitation

The existing `BacktestObjective` takes a list of `indicator_names` and
suggests params for **all** of them. For discovery, we need to:

1. Allow Optuna to select a **subset** of indicators (on/off per indicator)
2. Map each archetype to a sensible default indicator subset

### Proposed change

```python
class BacktestObjective:
    def __init__(
        self,
        *,
        dataset: BacktestDataset,
        indicator_names: list[str] | None = None,
        indicator_selection: bool = False,  # NEW: let Optuna toggle indicators
        archetype: str = "trend_following",
        ...
    )
```

When `indicator_selection=True`, the objective adds a `{ind_name}__active`
categorical param (True/False) per indicator. Inactive indicators produce
no signals.

### Archetype → Indicator Mapping

| Archetype | Default indicators | Rationale |
|-----------|-------------------|-----------|
| `trend_following` | ssl_channel, firestorm, firestorm_tm | Trend-change detectors |
| `mean_reversion` | wavetrend_reversal, rsi, bollinger_bands | OB/OS detectors |
| `mixed` | ssl_channel, wavetrend_reversal, firestorm | Mix of trend + reversal |

Standard indicators (ema, macd, atr, vwap) are available as optional filters
when `indicator_selection=True`.

---

## 3. WFO Integration Contract

### Input

```python
wfo = WalkForwardEngine(
    n_splits=5,
    min_is_bars=500,
    min_oos_bars=100,
    gap_bars=20,        # purge gap to prevent leakage
    mode="rolling",
)

# top_trials = list of dicts from OptunaOptimizer.get_top_n(50)
wfo_result = wfo.evaluate(
    dataset=dataset,
    param_sets=[t["params"] for t in top_trials],
    backtest_fn=objective.run_single,
    metric="sharpe",
)
```

### Output

```python
@dataclass
class WFOResult:
    oos_equity_curves: dict[str, pd.Series]   # param_id → equity
    oos_metrics: dict[str, dict[str, float]]   # param_id → {sharpe, sortino, ...}
    degradation: dict[str, float]              # param_id → IS_metric/OOS_metric
```

### Key: Run single backtest function

The `BacktestObjective` needs a `.run_single(params)` method that doesn't
go through Optuna's `trial.suggest_*()`:

```python
def run_single(self, params: dict[str, Any]) -> dict[str, Any]:
    """Run a backtest with explicit params (no Optuna trial)."""
    indicator_params, risk_overrides = self._split_params(params)
    signals = self.build_signals(indicator_params)
    risk_config = self.build_risk_config(risk_overrides)
    result = self._engine.run(...)
    metrics = self._metrics_engine.compute(...)
    return {"equity_curve": result["equity_curve"], "metrics": metrics}
```

---

## 4. Anti-Overfit Pipeline Contract

### Input

```python
pipeline = AntiOverfitPipeline(
    cscv_n_subsamples=16,
    dsr_significance=0.05,
    spa_significance=0.10,
    benchmark_returns=buy_and_hold_returns,
)

result = pipeline.run(
    equity_curves=wfo_result.oos_equity_curves,
    n_trials=len(study.trials),
)
```

### Output

```python
@dataclass
class PipelineResult:
    cscv: CSCVResult          # pbo, rank_correlations
    strategies: list[StrategyReport]  # per-strategy DSR + SPA results
    finalists: list[str]      # IDs that passed all filters
```

---

## 5. Execution Layer Architecture

### `AlpacaExecutor`

```python
class AlpacaExecutor:
    """Thin wrapper around alpaca-py TradingClient for paper/live execution."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        paper: bool = True,
    ) -> None:
        from alpaca.trading.client import TradingClient
        self._client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper,
        )

    async def get_account(self) -> AccountInfo: ...
    async def get_positions(self) -> list[PositionInfo]: ...

    async def submit_market_order(
        self,
        symbol: str,
        qty: float,
        side: Literal["buy", "sell"],
    ) -> OrderResult: ...

    async def submit_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: Literal["buy", "sell"],
        take_profit_price: float,
        stop_loss_price: float,
    ) -> OrderResult: ...

    async def cancel_order(self, order_id: str) -> bool: ...
    async def close_position(self, symbol: str) -> OrderResult: ...
```

### `SignalBridge`

The bridge converts backtest-style signals to execution commands:

```python
class SignalBridge:
    """Translates StrategySignals + RiskConfig into execution commands."""

    def __init__(
        self,
        executor: AlpacaExecutor,
        risk_config: RiskConfig,
        symbol: str,
    ) -> None: ...

    async def on_bar(self, bar: pd.Series, signals: dict[str, bool]) -> None:
        """Called on each new bar. Decides whether to enter/exit/adjust."""
```

The bridge:
1. Checks current position state (from executor)
2. Evaluates entry signals → submits bracket orders
3. Evaluates exit signals → closes positions
4. Adjusts trailing stops when conditions change
5. Logs every action to structured JSON

### Paper Trading Loop

```python
# run_paper.py pseudo-code
executor = AlpacaExecutor(api_key, secret_key, paper=True)
bridge = SignalBridge(executor, risk_config, symbol)

# Option A: Poll-based (simplest)
while True:
    bar = fetch_latest_bar(symbol, timeframe)
    signals = compute_signals(bar, indicator_params)
    await bridge.on_bar(bar, signals)
    sleep(timeframe_seconds)

# Option B: WebSocket stream (future)
# async for bar in alpaca_stream(symbol, timeframe):
#     signals = compute_signals(...)
#     await bridge.on_bar(bar, signals)
```

---

## 6. Settings Extensions

```python
# New fields for config/settings.py

# Execution
alpaca_paper: bool = True
alpaca_base_url: str = ""  # auto-resolved from paper flag

# Discovery
discovery_trials: int = 500
discovery_top_n: int = 50
discovery_wfo_splits: int = 5
discovery_cscv_subsamples: int = 16
discovery_dsr_alpha: float = 0.05
discovery_spa_alpha: float = 0.10
```

---

## 7. New Test Coverage

| Area | Tests | Focus |
|------|-------|-------|
| `test_discovery_orchestrator.py` | 5-8 | E2E with small data (100 bars, 10 trials) |
| `test_objective_run_single.py` | 3-5 | `run_single()` vs `__call__()` parity |
| `test_alpaca_executor.py` | 8-12 | Mocked TradingClient (orders, fills, errors) |
| `test_signal_bridge.py` | 5-8 | Signal → order translation logic |

---

## 8. Performance Estimates

| Operation | Estimated time | Bottleneck |
|-----------|---------------|------------|
| 1 Optuna study (500 trials) | ~8 min | BacktestEngine FSM (~64 bt/s) |
| 36 studies sequential | ~5 hours | CPU-bound |
| 36 studies parallel (8 cores) | ~40 min | Memory (data per process) |
| WFO (50 params × 5 folds) | ~4 min per study | 250 backtests |
| CSCV + DSR per study | < 10 sec | Vectorized numpy |
| Full pipeline (36 studies) | ~6-8 hours sequential | Optimization phase |

### Memory Considerations

Each study loads one dataset (symbol × TF). At 4h:
- BTCUSDT 4h: ~18K bars × ~6 cols × 8 bytes = ~0.8 MB
- Indicator pre-computation: ~5 MB overhead
- Per study total: < 50 MB

→ Can safely run 8+ studies in parallel on 16 GB RAM.

At 1m resolution (if ever needed):
- 4.5M rows × 6 cols × 8 bytes = ~216 MB per symbol
- Resampled at load time, so only the target TF is in memory during optimization
