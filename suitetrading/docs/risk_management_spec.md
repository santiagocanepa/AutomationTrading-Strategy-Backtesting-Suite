# Risk Management Specification — SuiteTrading v2

> Extracted from `Strategy-Indicators.pinescript`. Describes the **exact** risk
> management logic as a deterministic state machine so it can be re-implemented
> in Python with identical behaviour.

---

## 1. Strategy-Level Configuration

```
initial_capital     = 4 000 USDT
commission          = 0.07 % per side
pyramiding          = 4 (strategy level)  # max_pyramiding_orders input = 3
default_qty_type    = percent_of_equity
default_qty_value   = 5 %
currency            = USDT
max_bars_back       = 5 000
```

---

## 2. Global Risk Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `profit_take_percent` | int | 35 | % of position closed at TP1 |
| `breakeven_buffer` | float | 1.0007 | Multiplier for BE price (≈ 0.07 % commissions) |
| `num_opcionales_necesarias` | int | 3 | Min optional indicators to trigger entry |
| `pyr_threshold_factor` | float | 1.01 | Dampening factor for pyramid spacing |
| `max_pyramiding_orders` | int | 3 | Max additional entries in same direction |
| `block_bars` | int | 15 | Min bars between consecutive orders |

---

## 3. Position State Machine

```
                          ┌──────────────────────────────────────┐
                          │              FLAT                     │
                          └──────────┬───────────────────────────┘
                                     │ condicion_compra/venta
                                     │ AND can_place_order
                                     │ AND pyramid_conditions
                                     ▼
                          ┌──────────────────────────────────────┐
                          │          OPEN_INITIAL                 │
                          │  stop_loss = upTM - distancia_stop   │
                          │  (or dnTM + distancia_stop for short)│
                          │  first_take_profit_hit = false       │
                          └────┬──────────┬──────────┬───────────┘
                               │          │          │
                     SL hit    │   TP1    │   Pyramid│
                     (price ≤  │  trigger │  allowed │
                      SL)      │          │          │
                               ▼          ▼          ▼
                          ┌────────┐ ┌─────────┐ ┌──────────────┐
                          │ CLOSED │ │ PARTIAL │ │ OPEN_INITIAL │
                          │ (SL)   │ │ TP1     │ │ (level N+1)  │
                          └────────┘ └────┬────┘ └──────────────┘
                                          │
                                          │ first_take_profit_hit = true
                                          │ stop_adjusted = avg_price * buffer
                                          ▼
                          ┌──────────────────────────────────────┐
                          │         OPEN_BREAKEVEN               │
                          │  SL = avg_price * breakeven_buffer   │
                          └────┬──────────────────┬──────────────┘
                               │                  │
                     BE hit    │   Trailing        │
                     (price ≤  │   trigger         │
                      adj SL)  │                   │
                               ▼                   ▼
                          ┌────────┐ ┌──────────────────────────┐
                          │ CLOSED │ │      OPEN_TRAILING       │
                          │(Adj SL)│ │  ssl_venta_low triggers  │
                          └────────┘ │  full close              │
                                     └──────────┬───────────────┘
                                                │ ssl_venta_low
                                                │ AND in_profit
                                                │ AND bar > tp1_bar
                                                ▼
                                           ┌────────┐
                                           │ CLOSED │
                                           │(Trail) │
                                           └────────┘
```

---

## 4. Entry Logic

### 4.1 Entry Conditions

```python
can_place_order = (last_order_bar is None) or (bar_index - last_order_bar > block_bars)

# Long entry:
allow_long = (
    condicion_compra                              # signal combiner output
    and position_size >= 0                        # flat or already long
    and current_pyramid_orders < max_pyramiding_orders
    and (
        position_size == 0                        # fresh entry
        or close <= avg_price - threshold_dist    # pyramid: price dipped
    )
)

# Short entry (mirror logic):
allow_short = (
    condicion_venta
    and position_size <= 0
    and current_pyramid_orders < max_pyramiding_orders
    and (
        position_size == 0
        or close >= avg_price + threshold_dist
    )
)
```

### 4.2 Pyramid Threshold

```python
remaining = max_pyramiding_orders - current_pyramid_orders
if remaining > 0:
    threshold_dist = abs(stop_loss_price - avg_price) / remaining * pyr_threshold_factor
```

This creates **evenly-spaced** pyramid levels between the current average price
and the stop-loss, adjusted by `pyr_threshold_factor`.

### 4.3 Position Sizing — Fibonacci Weighting

```python
# At bar 0, build Fibonacci sequence:
fib = [1.0]
for i in range(1, max_pyramiding_orders):
    if i < 2:
        fib.append(1.0)
    else:
        fib.append(fib[i-1] + fib[i-2])
# For max_pyramiding_orders=3: fib = [1, 1, 2]

# Normalize to percentages:
total = sum(fib)
fibPct = [f / total * 100 for f in fib]
# = [25%, 25%, 50%]  — first entries are smaller, last is largest

# For each order:
fibSizePct = fibPct[current_pyramid_orders]
orderValue = equity * fibSizePct / 100
contracts_pre = orderValue / close
```

### 4.4 Dynamic Size Adjustment (Distance Weighting)

```python
dist_up = abs(upTM - close)      # distance to upper Firestorm TM band
dist_dn = abs(close - dnTM)      # distance to lower Firestorm TM band

# Weight: more size when closer to SL (favorable risk)
contracts = contracts_pre * (1 + (0.5 - dist_up / (dist_up + dist_dn)))

# For longs:  closer to upTM (SL) → dist_up small → ratio small → weight > 1
# For shorts: closer to dnTM (SL) → dist_dn small → ratio large → weight > 1 (inverted formula)
```

---

## 5. Stop-Loss: Firestorm TM

The SL is **not** a fixed ATR multiple from entry. It's the Firestorm TM band
value at the time of entry, with a small buffer.

### Long SL

```python
stop_loss_price = upTM - distancia_stop
# where distancia_stop = (dnTM - upTM) * 0.01
```

### Short SL

```python
stop_loss_price = dnTM + distancia_stop
```

### Trigger

```python
# Long: exit if low <= stop_loss_price AND NOT first_take_profit_hit
if low <= stop_loss_price and not first_take_profit_hit:
    close_all("SL L")

# Short: exit if high >= stop_loss_price AND NOT first_take_profit_hit
if high >= stop_loss_price and not first_take_profit_hit:
    close_all("SL S")
```

**Important:** SL only applies before TP1. After TP1, the break-even logic
takes over.

---

## 6. Take Profit: Partial Close (TP1)

### Profit Distance Check

```python
distancia_profit = (dn - up) * 1.01    # Firestorm bands spread × 1.01

is_position_in_profit = (
    (position_size > 0 and close > avg_price and abs(close - avg_price) >= distancia_profit)
    or
    (position_size < 0 and close < avg_price and abs(avg_price - close) >= distancia_profit)
)
```

### Trigger

```python
# Long TP1:
if ssl_venta and not first_take_profit_hit and is_position_in_profit:
    qty_to_close = abs(position_size) * profit_take_percent / 100
    close_partial("TP1 L", qty=qty_to_close)
    first_take_profit_hit = True
    stop_adjusted_price = avg_price * breakeven_buffer
    tp1_bar_index = bar_index

# Short TP1:
if ssl_compra and not first_take_profit_hit and is_position_in_profit:
    qty_to_close = abs(position_size) * profit_take_percent / 100
    close_partial("TP1 S", qty=qty_to_close)
    first_take_profit_hit = True
    stop_adjusted_price = avg_price / breakeven_buffer
    tp1_bar_index = bar_index
```

---

## 7. Break-Even Stop

After TP1, the stop-loss moves to a **commission-adjusted entry price**.

```python
# Long:
stop_adjusted_price = avg_price * breakeven_buffer   # 1.0007 → 0.07% above entry

# Short:
stop_adjusted_price = avg_price / breakeven_buffer   # 0.07% below entry

# Trigger long:
if first_take_profit_hit and low <= stop_adjusted_price:
    close_all("Adjusted L")

# Trigger short:
if first_take_profit_hit and high >= stop_adjusted_price:
    close_all("Adjusted S")
```

---

## 8. Trailing Stop: SSL Channel LOW

After TP1, the remaining position is managed by SSL Channel LOW crossover.

```python
# Long trailing:
if (first_take_profit_hit
    and ssl_venta_low             # SSL LOW bearish cross
    and is_position_in_profit     # still profitable
    and bar_index > tp1_bar_index # not on the same bar as TP1
):
    close_all("Trailing L")

# Short trailing:
if (first_take_profit_hit
    and ssl_compra_low            # SSL LOW bullish cross
    and is_position_in_profit
    and bar_index > tp1_bar_index
):
    close_all("Trailing S")
```

---

## 9. Loss Distance Check

Used to prevent pyramiding into badly losing positions:

```python
distancia_loss = (dn - up) * 4    # Firestorm bands spread × 4

is_position_in_loss = (
    (position_size > 0 and close < avg_price and abs(avg_price - close) >= distancia_loss)
    or
    (position_size < 0 and close > avg_price and abs(avg_price - close) >= distancia_loss)
)
```

**Note:** `is_position_in_loss` is defined but not currently used in the entry
conditions. It's available for future use or may have been used in previous
versions.

---

## 10. Order Block (Anti-Overtrading)

```python
block_bars = 15
can_place_order = (last_order_bar is None) or (bar_index - last_order_bar > block_bars)

# Additionally, only one entry per bar:
entry_made = False  # reset each bar
if entry_made:
    skip
```

---

## 11. Pyramid Counter Reset

```python
if position_size == 0:
    current_pyramid_orders = 0
```

---

## 12. OKX Alert JSON Structure

For live execution via OKX webhook:

```python
# Entry:
entryJSON = {
    "investmentType": "base",
    "amount": str(contracts)
}

# Partial TP:
tpJSON = {
    "investmentType": "percentage_position",
    "amount": str(profit_take_percent)
}

# Full close (SL, BE, Trailing):
fullJSON = {
    "investmentType": "percentage_position",
    "amount": "100"
}
```

All JSON payloads include: order ID, action, market position, instrument,
signal token, timestamp, max lag (300s), order type (market).

---

## 13. Execution Priority

On each bar, the strategy evaluates in this order:

1. **SL check** (before TP1)
2. **TP1 partial close** (SSL cross + in profit)
3. **BE check** (after TP1)
4. **Trailing check** (after TP1 + SSL LOW cross)
5. **New entry / pyramid** (if can_place_order + signal + conditions)

This order matters because a bar can trigger both SL and a new signal — SL
takes priority.

---

## 14. Implementation Notes for Python

1. **State must be tracked per-position**, not globally, for vectorized backtesting
   compatibility (VectorBT custom simulator).

2. **Pyramid orders share the same SL level** — it's set at entry and only moves
   to BE after TP1. There's no per-level SL.

3. **avg_price is the weighted average** of all pyramid entries — calculated by
   the strategy engine, not manually.

4. **Fibonacci sizing is inverted from typical practice:** the LAST pyramid
   level gets the LARGEST allocation (50% for 3 orders). This is unusual —
   most literature recommends decreasing size. The rationale is that the last
   entry has the best average price.

5. **Distance-based dynamic sizing** adjusts position size based on proximity
   to the Firestorm TM bands. Closer to SL = more contracts (better risk/reward).
   This is an unusual and potentially aggressive optimization.

6. **condicion_venta is currently hardcoded to `false`** in the Pine Script.
   The short logic exists but is disabled. The v2 implementation should support
   both directions.
