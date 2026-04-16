# backtesting

`src/suitetrading/backtesting/`

Single and batch backtesting of strategies across crypto and stock assets.
Two execution paths: FSM (full state-machine, supports pyramiding / partial TP) and simple (bar-loop, vectorisable archetypes). Mode selected automatically via `VECTORIZABILITY` map.

---

## Files

| File | LOC | Responsibility |
|---|---|---|
| `engine.py` | 186 | `BacktestEngine` — orchestrates single and batch runs |
| `_internal/runners.py` | 471 | `run_fsm_backtest()`, `run_simple_backtest()` — core loops |
| `_internal/datasets.py` | 132 | `BacktestDataset`, `build_dataset_from_df()` |
| `_internal/schemas.py` | 141 | `StrategySignals`, `RunConfig`, `BacktestCheckpoint`, `RESULT_COLUMNS` |
| `_internal/checkpoints.py` | 144 | Checkpoint write/read/resume for long batch runs |
| `metrics.py` | 225 | `MetricsEngine` — vectorised performance stats |
| `slippage.py` | 104 | `estimate_slippage_pct()` — empirical slippage per symbol × TF |
| `ensemble.py` | 199 | `EnsembleBacktester` — weighted blend of N equity curves |
| `grid.py` | 179 | Grid builder for parameter sweep configs |
| `reporting.py` | 147 | Plotly HTML reports |

---

## Key API

### `BacktestEngine.run()`
```python
engine = BacktestEngine()
result = engine.run(
    dataset=dataset,        # BacktestDataset
    signals=signals,        # StrategySignals
    risk_config=risk_config,
    mode="auto",            # "auto" | "fsm" | "simple"
    direction="long",
)
# result keys: symbol, timeframe, archetype, equity_curve, trades (DataFrame),
#              final_equity, total_return_pct, total_trades, initial_capital
```

### `BacktestEngine.run_batch()`
```python
results = engine.run_batch(
    configs=run_configs,       # list[RunConfig]
    dataset_loader=...,        # Callable(RunConfig) -> BacktestDataset
    signal_builder=...,        # Callable(BacktestDataset, RunConfig) -> StrategySignals
    risk_builder=...,          # Callable(RunConfig) -> RiskConfig
)
```

### `MetricsEngine.compute()`
```python
metrics = MetricsEngine().compute(
    equity_curve=equity,
    trades=trades_df,
    initial_capital=10_000.0,
    context={"timeframe": "1h", "market": "crypto"},  # or "stock"
)
# Returns: net_profit, total_return_pct, sharpe, sortino, max_drawdown_pct,
#          calmar, win_rate, profit_factor, average_trade, max_consecutive_losses, total_trades
```
- Annualisation: crypto uses 365×24 bars/year; stocks use 252×6.5 bars/year.

### `estimate_slippage_pct()`
```python
slip = estimate_slippage_pct(symbol="BTCUSDT", timeframe="1h")  # → 0.01
# Auto-detects crypto (USDT/USD suffix) vs stock.
# Total per-trade cost = commission + slip_entry + slip_exit
```

---

## Tests

```bash
cd suitetrading && pytest tests/backtesting/ -v
```
