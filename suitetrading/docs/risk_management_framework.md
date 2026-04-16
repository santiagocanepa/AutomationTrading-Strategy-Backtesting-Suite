# Risk Management Framework — SuiteTrading v2

> Final reference document for the risk management engine implemented in
> Sprint 3. Synthesises the Pine Script legacy spec, the Python implementation,
> and the architectural decisions that connect indicators, state machine,
> sizing, portfolio controls and the VBT compatibility layer.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Indicator Layer                          │
│  Firestorm · SSL Channel · WaveTrend · VWAP · Squeeze …  │
│  Each indicator: compute(df) → pd.Series[bool]              │
└───────────────┬─────────────────────────────────────────────┘
                │ entry_signal, exit_signal, trailing_signal
                ▼
┌─────────────────────────────────────────────────────────────┐
│              Signal Combiner (three-state gates)             │
│  Excluyente (AND) · Opcional (count ≥ threshold) · Desact.  │
│  → condicion_compra / condicion_venta                        │
└───────────────┬─────────────────────────────────────────────┘
                │ entry_signal, exit_signal, trailing_signal
                ▼
┌─────────────────────────────────────────────────────────────┐
│            Position State Machine (bar-based FSM)            │
│  Priority: SL → TP1 → BE → Trail → Time → Entry/Pyramid    │
│  Gap-aware fills · Slippage · Deterministic transitions      │
│  → TransitionResult (snapshot + orders)                      │
└───────────────┬─────────────────────────────────────────────┘
                │ position risk, notional, direction
                ▼
┌─────────────────────────────────────────────────────────────┐
│              Portfolio Risk Manager                           │
│  Heat limits · Drawdown · Exposure · Kill switch · Monte C. │
│  → approve / reject new risk                                 │
└───────────────┬─────────────────────────────────────────────┘
                │ approved orders
                ▼
┌─────────────────────────────────────────────────────────────┐
│              Execution / VBT Simulator                        │
│  Sprint 3: prototype run_simple_backtest (numpy loop)        │
│  Sprint 4: Numba callback for VectorBT PRO                  │
│  Sprint 6: NautilusTrader event-driven adapter               │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Position Lifecycle State Machine

### 2.1 States

| State | Description |
|-------|-------------|
| `FLAT` | No open position |
| `OPEN_INITIAL` | Position open, initial stop active |
| `PARTIALLY_CLOSED` | TP1 triggered, partial quantity closed |
| `OPEN_BREAKEVEN` | Stop moved to break-even after TP1 |
| `OPEN_TRAILING` | Trailing exit active |
| `OPEN_PYRAMIDED` | Additional entry filled |
| `CLOSED` | Position fully closed |

### 2.2 Transition Diagram

```
FLAT ──entry_filled──▶ OPEN_INITIAL
                           │
              ┌────────────┼──────────────┐
              │            │              │
           SL hit       TP1 hit    pyramid_add
              │            │              │
              ▼            ▼              ▼
           CLOSED   PARTIALLY_CLOSED  OPEN_INITIAL
                           │            (level N+1)
                           │
                    ┌──────┼──────┐
                    │             │
                 BE hit     trail active
                    │             │
                    ▼             ▼
                 CLOSED    OPEN_TRAILING
                                  │
                           trail signal
                           + in_profit
                                  │
                                  ▼
                               CLOSED
```

### 2.3 Evaluation Priority (Immutable Contract)

Each bar is evaluated in strict order. The first matching condition exits:

1. **Stop-loss** — Checked against `bar["low"]` (long) / `bar["high"]` (short)
2. **Partial TP1** — Signal-based, R-multiple, or fixed-pct trigger
3. **Break-even** — After TP1, stop moves to `entry × buffer`
4. **Trailing exit** — Signal-based (e.g. SSL LOW cross) + in-profit guard
5. **Time exit** — Max bars in position exceeded
6. **Entry / Pyramid** — Only if no higher-priority event fired

This priority chain guarantees deterministic, reproducible outcomes.

### 2.4 Gap-Aware Fills

When the market gaps past the stop level on bar open:

- **Long SL**: `fill = min(stop_price, bar["open"])` (gap down → worse fill)
- **Short SL**: `fill = max(stop_price, bar["open"])` (gap up → worse fill)
- Falls back to `bar["close"]` only when stop price is not set

### 2.5 Slippage Model

All fills (SL, TP1, BE, trailing) include configurable slippage:

```python
# Long: slippage worsens fills downward
fill = price × (1 - slippage_pct / 100)

# Short: slippage worsens fills upward
fill = price × (1 + slippage_pct / 100)
```

Configuration: `RiskConfig.slippage_pct` (0.0 – 5.0%, default 0.0).

### 2.6 Partial Fills Contract

In bar-based mode (Sprint 3–4), `filled_qty == quantity` always. Order dicts
include a `filled_qty` key to pre-establish the contract for event-driven mode
(Sprint 6), where partial fills may produce intermediate snapshots.

---

## 3. Risk Configuration

All parameters live in `RiskConfig` (Pydantic-validated, `contracts.py`):

### 3.1 Top-Level

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `archetype` | str | `"mixed"` | Active archetype preset |
| `direction` | str | `"both"` | `"long"` / `"short"` / `"both"` |
| `initial_capital` | float | 4 000 | Starting equity (USDT) |
| `commission_pct` | float | 0.07 | Per-side commission |
| `slippage_pct` | float | 0.0 | Slippage applied to all fills |

### 3.2 Nested Configs

| Section | Key Parameters |
|---------|---------------|
| **SizingConfig** | `model` (fixed_fractional / atr / kelly / optimal_f), `risk_pct`, `max_risk_per_trade`, `max_leverage` |
| **StopConfig** | `model` (atr / signal / fixed_pct), `atr_multiple`, `fixed_pct` |
| **TrailingConfig** | `model` (atr / signal / chandelier / sar), `atr_multiple`, `fixed_offset` |
| **PartialTPConfig** | `enabled`, `close_pct` (35%), `trigger` (signal / r_multiple / fixed_pct), `profit_distance_factor` |
| **BreakEvenConfig** | `enabled`, `buffer` (1.0007), `activation` (after_tp1 / r_multiple / pct) |
| **PyramidConfig** | `enabled`, `max_adds` (3), `block_bars` (15), `threshold_factor`, `weighting` (fibonacci / equal / decreasing) |
| **TimeExitConfig** | `enabled`, `max_bars` |
| **PortfolioLimits** | `max_portfolio_heat`, `max_drawdown_pct`, `max_gross_exposure`, `kill_switch_drawdown` |

### 3.3 Cross-Validation

A `model_validator` ensures `pyramid.max_adds × sizing.max_risk_per_trade` cannot exceed 100% equity.

---

## 4. Exit Policies

Standalone policy objects in `trailing.py`, each with `evaluate() → (should_exit, updated_stop, reason)`:

| Policy | Description | Use Case |
|--------|-------------|----------|
| `BreakEvenPolicy` | Move SL to entry ± commission buffer | After TP1 hit |
| `FixedTrailingStop` | Trail by fixed offset from peak | Simple trend |
| `ATRTrailingStop` | Trail by ATR × multiple from peak | Volatility-adaptive |
| `ChandelierExit` | N-period highest high − ATR × multiple | Trend following |
| `ParabolicSARStop` | Acceleration factor convergence | Classic momentum |
| `SignalTrailingExit` | External boolean signal triggers close | SSL LOW, custom |

All policies share the same ABC interface and can be composed with the state machine.

---

## 5. Position Sizing Models

Implemented in `position_sizing.py`, all respecting hard safety caps (`max_leverage`, `max_position_size`):

| Model | Formula | Best For |
|-------|---------|----------|
| **FixedFractionalSizer** | `equity × risk_pct / \|entry − stop\|` | Default, most archetypes |
| **ATRSizer** | `equity × risk_pct / (ATR × multiple)` | Volatility-adaptive |
| **KellySizer** | `equity × kelly_fraction × edge` | When win-rate/payoff known |
| **OptimalFSizer** | Monte Carlo optimal fraction | Maximum geometric growth |

Factory function: `create_sizer(model_name) → PositionSizer`.

---

## 6. Archetype Presets

Each archetype is a `RiskArchetype` subclass with `build_config(**overrides) → RiskConfig`:

### A — Trend Following

| Property | Value |
|----------|-------|
| Stop | ATR × 3.0 |
| Trail | ATR × 2.5 |
| Partial TP | Disabled (let winners run) |
| Pyramid | 3 adds, decreasing weight, 20-bar block |
| Break-even | R-multiple = 2.0 |
| Portfolio heat | 12% |
| Vectorizability | **High** |

### B — Mean Reversion

| Property | Value |
|----------|-------|
| Stop | ATR × 1.5 |
| Trail | Disabled |
| Partial TP | 60% close at 1R |
| Pyramid | Disabled |
| Time exit | 50 bars max |
| Portfolio heat | 10% |
| Vectorizability | **High** |

### C — Mixed

| Property | Value |
|----------|-------|
| Stop | ATR × 2.0 |
| Trail | ATR × 2.0 |
| Partial TP | 30% close (signal) |
| Pyramid | 2 adds |
| Portfolio heat | 15% |
| Vectorizability | Medium |

### D — Pyramidal Scaling

| Property | Value |
|----------|-------|
| Stop | ATR × 3.0 |
| Pyramid | 4 adds, decreasing weight |
| Partial TP | 25% close at 2R |
| Portfolio heat | 10% |
| Vectorizability | Low |

### E — Grid DCA

| Property | Value |
|----------|-------|
| Stop | ATR × 5.0 |
| DCA | 8 levels, equal weight |
| Close | 100% at 0.5R |
| Direction | Long-only |
| Portfolio heat | 8% |
| Vectorizability | Low |

### Legacy Firestorm (Pine Script Replica)

| Property | Value |
|----------|-------|
| Capital | $4 000 USDT |
| Commission | 0.07% per side |
| Stop | Signal-based (Firestorm TM band) |
| Trail | Signal-based (SSL LOW cross) |
| Partial TP | 35% (SSL cross + in_profit) |
| Break-even | Buffer 1.0007 (≈ commission coverage) |
| Pyramid | 3 adds, Fibonacci [25%, 25%, 50%], 15-bar block |
| Threshold | `1.01 × distance / remaining_adds` |
| Direction | Long-only |

---

## 7. Portfolio Risk Controls

`PortfolioRiskManager` (in `portfolio.py`) operates above individual positions:

| Control | Mechanism |
|---------|-----------|
| **Portfolio heat** | Sum of dollar-risk across open positions ≤ `max_portfolio_heat` % of equity |
| **Drawdown** | `(peak − equity) / peak ≤ max_drawdown_pct` |
| **Gross exposure** | Sum of absolute notionals / equity ≤ limit |
| **Net exposure** | Sum of signed notionals / equity ≤ limit |
| **Kill switch** | When drawdown ≥ `kill_switch_drawdown` → killed = True, all new risk rejected |
| **Correlation guard** | Max N correlated positions (threshold configurable) |
| **Monte Carlo** | Shuffle trade returns, measure tail risk across N simulations |

Gate function: `approve_new_risk(proposed_risk, notional, direction) → (bool, reason)`.

---

## 8. Indicator–Risk Integration

### 8.1 Signal Flow

1. **Entry signal**: Firestorm cross (or custom indicator) → Signal Combiner → `entry_signal=True`
2. **Exit signal (TP1)**: SSL Channel cross → `exit_signal=True` → triggers partial close if in_profit
3. **Trailing signal**: SSL Channel LOW cross → `trailing_signal=True` → triggers full close after TP1
4. **Stop level**: Firestorm TM `up` band (long) / `dn` band (short) → `stop_override` per bar

### 8.2 Three-State Classification

Each indicator operates in one of three states:

| State | Behaviour |
|-------|-----------|
| **Excluyente** | AND gate — all must be True for entry |
| **Opcional** | Count toward threshold (`num_opcionales_necesarias`) |
| **Desactivado** | Skipped entirely |

### 8.3 Hold-Bars Mechanism

Indicators that fire instantaneous signals apply a hold-bars extension:

| Indicator | Default Hold Bars |
|-----------|-------------------|
| Firestorm | 1 |
| SSL Channel | 4 |
| WaveTrend Reversal | 3 |
| WaveTrend Divergence | 3 |

Signal stays active for exactly `hold_bars` bars (inclusive of trigger).

---

## 9. VBT Compatibility Layer

### 9.1 Current State (Sprint 3 — Prototype)

- **`VBTSimulatorAdapter`**: Flattens `RiskConfig` into scalar dict for Numba closures
- **`run_simple_backtest()`**: Pure-numpy bar loop, single-position, no pyramiding
- **Gap-aware + slippage**: Implemented in the numpy loop
- **Returns**: `equity_curve`, `final_equity`, `total_return_pct`

### 9.2 Vectorizability Classification

| Archetype | Level | Reason |
|-----------|-------|--------|
| trend_following | High | Linear stop/trail, no partial TP |
| mean_reversion | High | Simple stop, time exit, no trail |
| mixed | Medium | Partial TP + trailing adds branching |
| legacy_firestorm | Medium | Signal-based stops need indicator arrays |
| pyramidal | Low | Sequential add logic |
| grid_dca | Low | Sequential DCA levels |

### 9.3 Sprint 4 Roadmap

- Numba `@njit` callback for VectorBT PRO custom simulator
- Pyramid support in vectorised loop
- Multi-position tracking
- Full equity/drawdown analytics array output

### 9.4 Sprint 6 — NautilusTrader Mapping

| Risk Engine Concept | Nautilus Equivalent |
|---------------------|---------------------|
| `PositionSnapshot` | `Position` object |
| `TransitionResult.orders` | `Order` + `OrderSubmitted` events |
| `PortfolioRiskManager` | `RiskEngine` / custom `Actor` |
| `ExitPolicy.evaluate()` | `Strategy.on_bar()` signal logic |
| `slippage_pct` | `FillModel` configuration |
| Gap-aware SL | N/A (tick-level, no bar gaps) |

---

## 10. Testing Summary

### 10.1 Coverage by Module

| Module | Tests | Coverage Areas |
|--------|-------|----------------|
| `contracts.py` | Validation, enums, defaults, edge cases |
| `state_machine.py` | All transitions, priority chain, gap-aware SL, slippage, PnL, block bars |
| `trailing.py` | All 6 exit policies, edge cases, activation conditions |
| `position_sizing.py` | All 4 sizers, safety caps, zero-division guards |
| `portfolio.py` | Heat, drawdown, exposure, kill switch, Monte Carlo, approve/reject |
| `vbt_simulator.py` | Archetypes A/B/C, adapter contract, config flattening, gap + slippage |
| `archetypes/` | All 6 presets build validly, override mechanism |

### 10.2 Key Test Categories

- **Gap-Aware SL**: Gap-down/up fills at open, no-gap fills at stop, PnL correctly worse
- **Slippage**: Reduces long fills, increases short fills, zero = no effect, applied to TP1
- **Archetype Smoke**: Each archetype builds a valid `RiskConfig`, adapter accepts it
- **VBT Archetypes**: Trending data → profit, tight stop → loss, no-trades → flat, curve valid

---

## 11. Module Map

```
src/suitetrading/risk/
├── __init__.py              # Public API exports
├── contracts.py             # PositionState, TransitionEvent, PositionSnapshot,
│                            # TransitionResult, RiskConfig + all sub-configs
├── state_machine.py         # PositionStateMachine (bar-based FSM)
├── trailing.py              # ExitPolicy ABC + 6 concrete policies
├── position_sizing.py       # PositionSizer ABC + 4 concrete sizers
├── portfolio.py             # PortfolioRiskManager (aggregate controls)
├── vbt_simulator.py         # VBTSimulatorAdapter + run_simple_backtest
└── archetypes/
    ├── __init__.py          # Registry + get_archetype()
    ├── base.py              # RiskArchetype ABC
    ├── trend_following.py   # Archetype A
    ├── mean_reversion.py    # Archetype B
    ├── mixed.py             # Archetype C
    ├── pyramidal.py         # Archetype D
    ├── grid_dca.py          # Archetype E
    └── legacy.py            # Pine Script replica + fibonacci_weights()
```

---

## 12. Design Decisions & Rationale

1. **Pure FSM with no side effects**: `evaluate_bar()` returns a new `TransitionResult`
   without mutating the input snapshot. This enables both sequential and vectorised usage.

2. **Priority chain over event queue**: A fixed evaluation order (SL → TP1 → BE → trail →
   time → entry) avoids ambiguity when multiple conditions fire on the same bar. The first
   match wins and returns immediately (except TP1 → BE which can chain in the same bar).

3. **Archetype presets over raw config**: Six curated profiles cover the main trading
   styles. Users can still override any parameter via `build_config(**overrides)`.

4. **Pydantic for validation**: All configuration is validated at construction time.
   Cross-field checks (e.g. pyramid risk cap) are enforced by model validators.

5. **Separation of concerns**: Indicators produce boolean signals. The signal combiner
   gates them. The state machine handles position lifecycle. Portfolio manager approves
   risk. Each layer is independently testable.

6. **Gap-aware + slippage from Sprint 3**: Rather than deferring realism to later sprints,
   fills account for opening gaps and configurable slippage in both the state machine and
   the VBT prototype. This prevents over-optimistic backtests.

7. **VBT as Sprint 4 debt**: The current `run_simple_backtest` is intentionally minimal.
   Full VectorBT PRO integration (Numba callbacks, multi-position, pyramiding) is Sprint 4
   scope. The adapter contract and flat config are already established.

---

*Document generated as Sprint 3 closure artifact. References: `risk_management_spec.md`,
`sprint3_technical_spec.md`, `sprint3_implementation_guide.md`.*
