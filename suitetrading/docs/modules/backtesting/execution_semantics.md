# Backtest Execution Semantics

> Frozen contract — any change requires a new version and full regression run.

## 1. Execution Modes

| Mode | Module | Use case |
|------|--------|----------|
| **FSM** | `runners.run_fsm_backtest()` | Full lifecycle: pyramid, partial TP, BE, trailing, time exit. All archetypes. |
| **Simple** | `runners.run_simple_backtest()` | Lightweight single-position loop for high-throughput A/B screening. |

Both modes are **deterministic**: same inputs → same outputs, same equity curve.

## 2. Bar-Loop Model

Each bar is processed sequentially. Within a single bar:

1. **Update snapshot**: increment `bars_in_position`, recompute `unrealized_pnl`.
2. **Evaluate exit priorities** (immutable order — see §3).
3. **Evaluate entry / pyramid** (lowest priority).
4. **Record equity** at bar close.

### Intra-Bar Fill Assumptions

- **Entry fills at `close`** of the signal bar. The entry signal is read on the same bar where the fill happens (no next-bar delay). This models a close-to-close regime.
- **Stop-loss fills**: `min(stop_price, bar.open)` for longs, `max(stop_price, bar.open)` for shorts. This models overnight gap handling: if the open gaps through the stop, the fill is at the gap price.
- **Trailing exit fills at `close`** (after TP1 confirmation).
- **Break-even fills at `break_even_price`** when `bar.low ≤ be_price` (long) or `bar.high ≥ be_price` (short).
- **Time exit**: no fill price computed — uses the snapshot's accumulated PnL.

### Signal-to-Fill Timing

All signals (entry, exit, trailing) are consumed **on the same bar** they fire. There is no explicit next-bar latency. The rationale: TradingView `strategy.entry()` also fires on the close of the signal bar.

## 3. Exit Priority Order (Immutable Contract)

```
Priority 1: Stop-Loss          → immediate return (no further evaluation)
Priority 2: Partial TP (TP1)   → continue to Priority 3 (BE may activate same bar)
Priority 3: Break-Even          → if hit → immediate return; else update state
Priority 4: Trailing Exit       → immediate return
Priority 5: Time Exit           → immediate return
Priority 6: Entry / Pyramid     → lowest priority
```

### Key Rules

- **SL is king**: always evaluated first. If `bar.low ≤ stop_price` (long), the position closes regardless of any other signal.
- **After TP1**: the stop is automatically moved to break-even price (`entry * buffer`). SL evaluation no longer applies because `tp1_hit` is True — BE takes over.
- **Trailing requires**: (a) `tp1_hit == True`, (b) `bar_index > tp1_bar_index`, (c) `trailing_signal == True`, (d) position is in profit.
- **Time exit requires**: (a) `time_exit.enabled`, (b) `bars_in_position >= max_bars`.

## 4. Fee Model

| Component | Formula | Default |
|-----------|---------|---------|
| Commission | `abs(filled_qty × fill_price) × commission_pct / 100` | 0.07% |
| Slippage | Long exit: `price × (1 - slippage_pct/100)`, Short exit: `price × (1 + slippage_pct/100)` | 0.0% |

Commissions are deducted from equity on every order: entry, pyramid add, partial close, full close.

Slippage is applied to fill prices adversely (reduces effective exit price for longs, increases for shorts).

## 5. Position Sizing

The sizer is called once per entry signal (not per pyramid add in current implementation).

```
entry_size = sizer.size(
    equity       = current_equity,
    entry_price  = bar.close,
    stop_price   = computed_stop,
    volatility   = ATR[bar],
    ...
)
```

Stop distance is computed as:
- If ATR > 0: `ATR × stop.atr_multiple` (primary model)
- If ATR == 0 (warmup period): `close × stop.fixed_pct / 100` (fallback)

ATR uses Wilder's smoothing (period=14). **Warning**: first 13 bars have ATR=0, causing the fixed_pct fallback. Entry signals during warmup will use the tighter fallback stop.

## 6. Pyramiding Semantics

| Parameter | Effect |
|-----------|--------|
| `pyramid.enabled` | Master gate |
| `pyramid.max_adds` | Maximum pyramids beyond initial entry |
| `pyramid.block_bars` | Minimum bars between any two orders (including initial entry) |
| `pyramid.threshold_factor` | Price must dip by `(stop_distance / remaining_adds) × threshold_factor` before next add |

`block_bars` applies to **all** orders, not just pyramids. If `block_bars=15`, no entry or pyramid can happen within 15 bars of the previous order, including the initial entry.

New pyramid entries:
- Use `weighted average` for avg_entry_price
- Increment `pyramid_level`
- Transition state to `OPEN_PYRAMIDED`

## 7. Portfolio Risk Gate (Feature-Flagged)

When `portfolio.enabled == True`:

```
portfolio_mgr.update(equity, open_positions)
approved, reason = portfolio_mgr.approve_new_risk(
    proposed_risk,
    proposed_notional,
    proposed_direction,
)
```

If not approved, the entry signal is suppressed — no entry order is created.

Checks (in order): kill_switch_drawdown → max_drawdown_pct → max_portfolio_heat → max_gross_exposure.

**Default**: `enabled=False` — all entries proceed without portfolio checks.

## 8. Trailing Policy Mode

| Mode | Config | Behavior |
|------|--------|----------|
| `"signal"` (default) | `trailing.trailing_mode = "signal"` | FSM uses `trailing_signal` from strategy |
| `"policy"` | `trailing.trailing_mode = "policy"` | ExitPolicy object evaluates each bar; can override `trail_sig` to True and tighten `stop_price` |

In policy mode:
- The trailing policy is instantiated via `create_exit_policy(model, **kwargs)`.
- Each bar: `policy.evaluate(snapshot, bar, indicators, bar_index)` returns `(should_exit, new_stop, reason)`.
- If `should_exit`, `trail_sig` is set to True (consumed by FSM priority 4).
- If `new_stop` is provided and is **tighter** than current stop, it replaces `snapshot.stop_price`.
- Policies never loosen stops.

## 9. FSM vs Simple Coherence

The simple runner is a strict **subset** of FSM behavior:
- No pyramiding, no partial TP, no break-even, no trailing.
- Single-position: SL or full exit only.
- Uses the same `_compute_atr` and fee model.

**Invariant**: for a config with all optional features disabled, `run_fsm_backtest` and `run_simple_backtest` should produce comparable equity curves (minor float differences from order of operations).

## 10. Trade Recording

A trade is recorded when `snapshot.state` transitions from any active state to `CLOSED`:

```python
TradeRecord(
    entry_bar    = bar index where initial entry occurred,
    exit_bar     = current bar index,
    direction    = snapshot.direction,
    entry_price  = price at initial entry,
    exit_price   = close of exit bar,
    quantity     = 0.0 (placeholder),
    pnl          = snapshot.realized_pnl - sum(prior_trades.pnl),
    exit_reason  = result.reason (e.g. "SL L", "TP1 L", "Trail L", "BE L", "Time exit"),
)
```

After recording, the snapshot is `reset()` back to FLAT.

## 11. Equity Curve

Equity is updated at every bar and stored in `equity_curve[i]`:
- **Commission deductions** happen on each order fill.
- **PnL credit** happens at trade close (net of all prior trades' PnL).
- During an open position, equity only reflects commission costs (unrealized PnL is NOT added to equity).

`BacktestResult.total_return_pct = (final_equity / initial_capital - 1) × 100`
