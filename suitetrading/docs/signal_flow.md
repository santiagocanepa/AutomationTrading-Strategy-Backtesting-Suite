# Signal Flow — SuiteTrading v2

> End-to-end description of how indicator outputs are combined, filtered and
> routed to the order management layer. Extracted from `Strategy-Indicators.pinescript`.

---

## 1. Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                       INDICATOR LAYER                               │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐                    │
│  │Firestorm │ │SSL Chan. │ │MTF Conditions    │                    │
│  │(hold N)  │ │(hold N)  │ │(5×SMA crosses)   │                    │
│  └────┬─────┘ └────┬─────┘ └───────┬──────────┘                    │
│       │               │              │                              │
│  ┌────┴────┐ ┌────────┴─────┐ ┌─────┴────┐ ┌──────────────────┐   │
│  │WaveTrend│ │Squeeze Mom.  │ │MACD Sig. │ │RSI+BB / Simple   │   │
│  │Rev/Div  │ │              │ │          │ │                  │   │
│  └────┬────┘ └──────┬───────┘ └────┬─────┘ └──────┬───────────┘   │
│       │             │              │               │               │
│  ┌────┴─────────────┴──────────────┴───────────────┴──────┐        │
│  │  VWAP · EMA 9/200 (distance filters)                  │        │
│  └────────────────────────────┬────────────────────────────┘        │
│                               │                                    │
└───────────────────────────────┼────────────────────────────────────┘
                                │  buy_signal / sell_signal per indicator
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     SIGNAL COMBINER                                 │
│                                                                     │
│  Each indicator has a state: Excluyente | Opcional | Desactivado   │
│                                                                     │
│  1. Desactivado → skip entirely                                    │
│  2. Excluyente → AND into gate                                     │
│  3. Opcional   → count +1 toward threshold                         │
│                                                                     │
│  condicion_compra = ALL_excluyentes_buy AND                        │
│                     count_opcionales_buy >= num_opcionales_necesarias│
│                                                                     │
│  condicion_venta  = ALL_excluyentes_sell AND                       │
│                     count_opcionales_sell >= num_opcionales_necesarias│
│                                                                     │
└───────────────────────────────┬─────────────────────────────────────┘
                                │  condicion_compra / condicion_venta
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ORDER MANAGEMENT LAYER                           │
│                                                                     │
│  Filters:                                                          │
│    • can_place_order (block_bars cooldown)                          │
│    • entry_made flag (max 1 entry per bar)                         │
│    • pyramid conditions (max_pyramiding_orders + threshold_dist)   │
│                                                                     │
│  Actions:                                                          │
│    strategy.entry → Fibonacci-sized order                          │
│    SL / TP1 / BE / Trailing → state machine in risk spec          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Three-State Indicator Classification

Each of the 11 entry indicators can be set to one of three states:

| State | Role | Logic |
|-------|------|-------|
| **Excluyente** | Hard requirement — must be true | ANDed into `compra_condiciones_excluyentes` / `venta_condiciones_excluyentes` |
| **Opcional** | Soft vote — counts toward quorum | Increments `count_opcionales_compra` / `count_opcionales_venta` by 1 if true |
| **Desactivado** | Ignored | Not evaluated at all |

### Entry Indicators with States

| # | Indicator | Pine Variable (buy) | Pine Variable (sell) |
|---|-----------|---------------------|----------------------|
| 1 | SSL Channel | `ssl_buy_signal` | `ssl_sell_signal` |
| 2 | RSI + Bollinger | `rsi_compra` | `rsi_venta` |
| 3 | Squeeze Momentum | `sqz_momentum_compra` | `sqz_momentum_venta` |
| 4 | MACD Signal | `macd_compra` | `macd_venta` |
| 5 | MTF Conditions | `mtf_compra` | `mtf_venta` |
| 6 | Firestorm | `firestorm_buy_signal` | `firestorm_sell_signal` |
| 7 | WaveTrend Reversal | `wt_rev_compra_final` | `wt_rev_venta_final` |
| 8 | WaveTrend Divergence | `wtdiv_compra_final` | `wtdiv_venta_final` |
| 9 | VWAP | `vwap_buy` | `vwap_sell` |
| 10 | RSI Simple | `simple_rsi_signal_buy` | `simple_rsi_signal_sell` |
| 11 | EMA 9/200 | *(distance filter only — not in combiner)* | — |

> **Note:** SSL Channel has a bug in the Pine Script — the sell optional branch
> counts both `ssl_sell_signal` AND `ssl_venta` (crossunder). This means SSL
> contributes TWO optional votes on the sell side. Likely unintentional.

---

## 3. Combination Algorithm

```python
def combine_signals(
    signals: dict[str, tuple[bool, bool]],    # indicator → (buy, sell)
    states: dict[str, str],                    # indicator → state
    num_opcionales_necesarias: int,
) -> tuple[bool, bool]:
    """
    Returns (condicion_compra, condicion_venta).
    """
    buy_gate = True     # AND gate for excluyentes
    sell_gate = True
    opt_buy = 0         # counter for opcionales
    opt_sell = 0

    for name, (buy, sell) in signals.items():
        st = states[name]
        if st == "Desactivado":
            continue
        if st == "Excluyente":
            buy_gate &= buy
            sell_gate &= sell
        elif st == "Opcional":
            opt_buy += int(buy)
            opt_sell += int(sell)

    condicion_compra = buy_gate and opt_buy >= num_opcionales_necesarias
    condicion_venta = sell_gate and opt_sell >= num_opcionales_necesarias
    return condicion_compra, condicion_venta
```

### Edge Cases

1. **No excluyentes active** → `buy_gate = True` (vacuously), entry depends
   only on optional quorum.
2. **No opcionales active** → `opt_buy = 0`, needs `num_opcionales_necesarias = 0`
   for any entry.
3. **All desactivado** → gate stays True but opt count = 0. If threshold = 0,
   entries fire every bar. If threshold > 0, no entries.

---

## 4. Hold-Bars Pattern

Several indicators apply a "hold bars" mechanism. When a raw signal fires, a
countdown counter is set. The signal remains active for N additional bars.

```python
# Pattern used by: Firestorm, SSL Channel, WaveTrend Reversal, WaveTrend Divergence
var hold_counter_buy: int = 0
var hold_counter_sell: int = 0

if raw_buy_signal:
    hold_counter_buy = hold_bars    # e.g., 4 for SSL, 1 for Firestorm
elif hold_counter_buy > 0:
    hold_counter_buy -= 1

if raw_sell_signal:
    hold_counter_sell = hold_bars
elif hold_counter_sell > 0:
    hold_counter_sell -= 1

final_buy = hold_counter_buy > 0
final_sell = hold_counter_sell > 0
```

**Important:** The counter is set to `hold_bars` (not `hold_bars - 1`), so the
signal is active for exactly `hold_bars` bars *including* the trigger bar.

### Hold-Bars per Indicator

| Indicator | Default hold_bars | Configurable |
|-----------|-------------------|--------------|
| Firestorm | 1 | Yes |
| SSL Channel | 4 | Yes |
| WaveTrend Reversal | 3 | Yes |
| WaveTrend Divergence | 3 | Yes |
| Others | N/A | No (signal is instantaneous) |

---

## 5. Multi-Timeframe Resolution

Some indicators compute their values on a higher timeframe than the chart. The
Pine Script uses `request.security()` for this.

### Timeframe Ladder

```
Chart TF → 1 superior    → 2 superiores
───────────────────────────────────────
1m       → 3m            → 5m
3m       → 5m            → 15m
5m       → 15m           → 30m
15m      → 30m           → 45m
30m      → 45m           → 60m
45m      → 60m           → 240m
60m      → 240m          → D
240m     → D             → W
D        → W             → M
W        → M             → M (capped)
M        → M (capped)    → M
```

### Timeframe Selector Options

Each MTF-capable indicator has a dropdown with options:
`'1','3','5','15','30','45','60','240','D','W','M','1 superior','2 superiores','grafico'`

- Fixed values (`'1'` through `'M'`): use that exact timeframe
- `'1 superior'`: resolve to `higher_tf1`
- `'2 superiores'`: resolve to `higher_tf2`
- `'grafico'`: use chart timeframe (no resampling)

### MTF-Capable Indicators

| Indicator | TF Parameter | Default |
|-----------|-------------|---------|
| Firestorm TM (SL) | `temporalidadTM_selection` | `'D'` |
| SSL LOW (Trailing) | `ssl_low_selection` | `'grafico'` |
| SSL Channel (TP1) | `ssl_selection` | `'30'` |
| VWAP | `vwap_sel` | `'grafico'` |
| MTF Conditions | Fixed 5 TFs (15,30,60,240,D) | — |

---

## 6. Distance Filters (Auxiliary)

These are not entry indicators but pre/post conditions used in risk management.

### 6.1 EMA Distance Filter

```python
ema9   = EMA(close, 9)
ema200 = EMA(close, 200)

distancia_emas_valida = abs(ema9 - ema200) / close * 100

# Currently used for visualization only, but available as a filter:
# "EMAs are too far apart" → trend too extended
```

### 6.2 SSL Distance for Entry

```python
# Pine: distancia_ssl
distancia_ssl = abs(close - sslUp) / close * 100

# Available to filter "entry too far from SSL line"
# Not currently wired into entry conditions
```

### 6.3 Firestorm Band Spread for Stops

```python
distancia_stop = (dnTM - upTM) * 0.01    # SL buffer
distancia_loss = (dn - up) * 4           # loss detection
distancia_profit = (dn - up) * 1.01      # profit detection
```

---

## 7. Python Implementation Notes

1. **Signal combiner is pure logic** — no state, no pandas. It's a function of
   `(signals_dict, states_dict, threshold) → (bool, bool)`. Already implemented
   in `src/suitetrading/indicators/signal_combiner.py`.

2. **Hold-bars requires stateful tracking** per indicator. For vectorized
   backtesting, implement as a forward-fill over a boolean series:

   ```python
   def apply_hold_bars(raw_signal: pd.Series, hold: int) -> pd.Series:
       """Extend True signals for `hold` bars (inclusive)."""
       result = raw_signal.copy()
       counter = 0
       for i in range(len(result)):
           if raw_signal.iloc[i]:
               counter = hold
           if counter > 0:
               result.iloc[i] = True
               counter -= 1
           else:
               result.iloc[i] = False
       return result
   ```

   For vectorized performance, use rolling max:
   ```python
   def apply_hold_bars_vectorized(raw_signal: pd.Series, hold: int) -> pd.Series:
       return raw_signal.rolling(hold, min_periods=1).max().astype(bool)
   ```

3. **MTF resolution** is already implemented in `src/suitetrading/indicators/mtf.py`
   with `resolve_timeframe()`, `resample_ohlcv()`, and `align_to_base()`.

4. **Per-bar evaluation order** matters for the state machine (see
   `risk_management_spec.md §13`), but the signal combiner itself is
   order-independent — all indicators are evaluated independently then combined.

5. **The SSL Channel optional-sell double-count bug** (§2 note) should be
   configurable. Default to Pine-compatible behaviour for validation, then
   offer a "fixed" mode.
