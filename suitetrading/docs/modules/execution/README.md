# execution

`src/suitetrading/execution/`

Paper and live order execution via Alpaca. Translates backtester-style strategy signals into real orders and manages multi-strategy position consolidation.

---

## Files

| File | LOC | Responsibility |
|---|---|---|
| `alpaca_executor.py` | 263 | `AlpacaExecutor` — thin wrapper around `alpaca-py TradingClient`. Market/limit orders, position queries, close operations. |
| `signal_bridge.py` | 323 | `SignalBridge` — single-strategy signal → order lifecycle. State: FLAT → OPEN → FLAT. ATR-based SL/TP matching the backtester. |
| `portfolio_bridge.py` | 216 | `PortfolioBridge` — orchestrates 100+ strategies in parallel, consolidates net positions per asset, enforces `PortfolioLimits`. |

---

## Key API

### `AlpacaExecutor`
```python
executor = AlpacaExecutor(api_key=KEY, secret_key=SECRET, paper=True)
executor.get_account()                         # → AccountInfo
executor.get_positions()                       # → list[PositionInfo]
executor.submit_market_order("BTC/USD", qty=0.01, side="buy")   # → OrderResult
executor.submit_limit_order("AAPL", qty=10, side="sell", limit_price=195.0)
executor.close_position("BTC/USD")
executor.close_all_positions()                 # returns count of close orders
```

### `SignalBridge`
- Long-only, single position per strategy instance.
- Accepts indicator signals (same format as `StrategySignals`), computes ATR-based stop/TP sizes from `RiskConfig`, and calls `AlpacaExecutor` when entry/exit conditions fire.
- Persists `BridgeState` + `TradeLog` to disk for recovery after restart.

### `PortfolioBridge`
```python
bridge = PortfolioBridge(
    portfolio_limits=limits,           # PortfolioLimits
    strategy_weights={"strat_id": w},  # optional dict
    initial_capital=100_000.0,
)
# Register strategies, then call bridge.process_bar(bar_data) each bar.
```
- Aggregates `StrategyPosition` entries into `ConsolidatedPosition` per asset.
- Respects `PortfolioLimits` before forwarding net orders to `AlpacaExecutor`.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `APCA_API_KEY_ID` | Yes | Alpaca API key ID |
| `APCA_API_SECRET_KEY` | Yes | Alpaca secret key |

Set `paper=True` (default) for paper trading endpoint. Set `paper=False` for live.

---

## Dependency

```
alpaca-py >= 0.43
```
Install: `pip install 'alpaca-py>=0.43'`
Module gracefully degrades (`_ALPACA_AVAILABLE = False`) if not installed — import won't fail, but instantiation raises `ImportError`.

---

## Tests

```bash
cd suitetrading && pytest tests/execution/ -v
```
