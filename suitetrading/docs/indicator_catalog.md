# Indicator Catalog — SuiteTrading v2

> Extracted from `Strategy-Indicators.pinescript` (~1 400 lines, Pine Script v5).
> Each indicator is documented with its exact formula, parameters, signal
> conditions, multi-timeframe support, and Python availability so that
> re-implementation requires **zero** reference to the original Pine code.

---

## Table of Contents

1. [Firestorm (SuperTrend Variant)](#1-firestorm-supertrend-variant)
2. [Firestorm TM (Stop-Loss Band)](#2-firestorm-tm-stop-loss-band)
3. [SSL Channel](#3-ssl-channel)
4. [SSL Channel LOW (Trailing)](#4-ssl-channel-low-trailing)
5. [MTF Conditions (5 × SMA)](#5-mtf-conditions-5--sma)
6. [MACD Signal](#6-macd-signal)
7. [WaveTrend — Reversal](#7-wavetrend--reversal)
8. [WaveTrend — Divergence](#8-wavetrend--divergence)
9. [RSI + Bollinger Bands](#9-rsi--bollinger-bands)
10. [RSI Simple](#10-rsi-simple)
11. [Squeeze Momentum (LazyBear)](#11-squeeze-momentum-lazybear)
12. [VWAP](#12-vwap)
13. [EMA 9 / EMA 200 (Auxiliary Filter)](#13-ema-9--ema-200-auxiliary-filter)

---

## 1. Firestorm (SuperTrend Variant)

**Role:** Trend-direction signal + entry filter.

### Formula

```
atr = EMA(TR, Periods)

up = src - Multiplier * atr
up = max(up, up[1])   if close[1] > up[1]   else up

dn = src + Multiplier * atr
dn = min(dn, dn[1])   if close[1] < dn[1]   else dn

trend =  1  if (trend[1] == -1 AND close > dn[1])
        -1  if (trend[1] ==  1 AND close < up[1])
        trend[1]  otherwise

buy_signal  = (trend == 1) AND (trend[1] == -1)   # bullish flip
sell_signal = (trend == -1) AND (trend[1] == 1)    # bearish flip
```

Where `src = ohlc4`, `TR = True Range`.

### Parameters

| Param | Type | Default | Range | Notes |
|-------|------|---------|-------|-------|
| `Periods` | int | 10 | 5–50 | EMA period for ATR smoothing |
| `src` | price | ohlc4 | — | Source price for band calc |
| `Multiplier_atr` | float | 1.8 | 0.5–5.0 | ATR multiplier for band width |
| `hold_bars` | int | 1 | 1–10 | Keep signal True for N bars after flip |

### Signal

- **Long:** `buy_signal` (or held for `hold_bars`)
- **Short:** `sell_signal` (or held for `hold_bars`)

### Multi-TF

Single timeframe (chart TF only).

### Python Availability

**Custom (NumPy).** Path-dependent ratchet requires a loop or Numba. No direct TA-Lib equivalent (SuperTrend in pandas-ta is similar but uses ATR differently — EMA vs RMA).

---

## 2. Firestorm TM (Stop-Loss Band)

**Role:** Determines Stop-Loss price level. Not a signal indicator — used by
the Risk Management engine.

### Formula

Identical structure to Firestorm (§1) but with **independent parameters** and
calculated on a **configurable timeframe** via `request.security`.

```
atr_tm = EMA(TR, firestorm_tm_period)          # on selected TF

upTM = ohlc4 - firestorm_tm_multiplier * atr_tm
upTM = max(upTM, upTM[1])   if close[1] > upTM[1]

dnTM = ohlc4 + firestorm_tm_multiplier * atr_tm
dnTM = min(dnTM, dnTM[1])   if close[1] < dnTM[1]

trend_tm = same flip logic as §1
```

The strategy uses `upTM` as the SL price for longs and `dnTM` for shorts, with
an additional buffer: `distancia_stop = (dnTM - upTM) * 0.01`.

### Parameters

| Param | Type | Default | Range |
|-------|------|---------|-------|
| `firestorm_tm_period` | int | 9 | 5–50 |
| `firestorm_tm_multiplier_atr` | float | 1.8 | 0.5–5.0 |
| `temporalidadTM_selection` | TF | "D" | any TF |

### Python Availability

Same as Firestorm — custom NumPy/Numba.

---

## 3. SSL Channel

**Role:** Trend signal AND first Take-Profit trigger (via crossunder).

### Formula

```
smaHigh = EMA(high, ssl_length)    # on selected TF
smaLow  = EMA(low,  ssl_length)    # on selected TF

Hlv =  1  if close > smaHigh
      -1  if close < smaLow
      Hlv[1]  otherwise

sslDown = smaHigh if Hlv < 0 else smaLow
sslUp   = smaLow  if Hlv < 0 else smaHigh

# Signal (state-based):
ssl_compra = sslUp > sslDown     # bullish state
ssl_venta  = sslUp < sslDown     # bearish state

# Crossover signal (event-based):
ssl_compra1 = crossover(sslUp, sslDown)
ssl_venta1  = crossunder(sslUp, sslDown)
```

The crossover signals use `hold_bars` pattern (default 4 bars).

**TP1 trigger:** The RM engine uses `ssl_venta` (state, not cross) to trigger
partial close for long positions, and `ssl_compra` for shorts.

### Parameters

| Param | Type | Default | Range |
|-------|------|---------|-------|
| `ssl_length` | int | 12 | 5–50 |
| `ssl_selection` | TF | "30" | any TF |
| `ssl_hold_bars` | int | 4 | 1–10 |

### Multi-TF

Single configurable TF via `request.security`.

### Python Availability

**Custom (NumPy).** Simple: EMA of high/low + stateful crossover. No library
has this exact variant (pandas-ta has `ssl_channel` but with SMA, not EMA).

---

## 4. SSL Channel LOW (Trailing)

**Role:** Trailing stop trigger after TP1 is hit.

Identical formula to SSL Channel (§4) but with **independent parameters** and
used exclusively for trailing exit logic.

### Parameters

| Param | Type | Default | Range |
|-------|------|---------|-------|
| `ssl_length_low` | int | 12 | 5–50 |
| `ssl_low_selection` | TF | "grafico" | any TF |

### Signal

- **Trailing exit long:** `ssl_venta_low` (crossunder of sslUp_low / sslDown_low)
- **Trailing exit short:** `ssl_compra_low` (crossover)

### Python Availability

Reuses SSL Channel implementation with different parameters.

---

## 5. MTF Conditions (5 × SMA)

**Role:** Trend filter — price must be above/below N configurable SMAs on
independent timeframes.

### Formula

```
mtf_i = SMA(close, mtf_i_length)   # on mtf_i_timeframe, for i in 1..5
```

**Combination modes:**

- **Excluyentes:** ALL enabled MTFs must agree (`close > mtf_i` for buy).
- **Opcionales:** ANY enabled MTF must agree.

```
# Excluyentes (buy):
condition = AND(close > mtf_i  for all enabled i)

# Opcionales (buy):
condition = OR(close > mtf_i  for any enabled i)
```

### Parameters

| Param | Type | Default | Range |
|-------|------|---------|-------|
| `mtf1_length` | int | 20 | 5–600 |
| `mtf1_selection` | TF | "D" | any TF |
| `mtf2_length` | int | 200 | 5–600 |
| `mtf2_selection` | TF | "240" | any TF |
| `mtf3_length` | int | 240 | 5–600 |
| `mtf3_selection` | TF | "240" | any TF |
| `mtf4_length` | int | 55 | 5–600 |
| `mtf4_selection` | TF | "60" | any TF |
| `mtf5_length` | int | 200 | 5–600 |
| `mtf5_selection` | TF | "1 superior" | any TF |
| `mtf_condition_mode` | enum | "Excluyentes" | Excluyentes / Opcionales |
| `mtf[1-5]_enabled` | bool | T,T,F,F,F | — |

### Multi-TF

5 independent timeframes (the most MTF-heavy indicator).

### Python Availability

**TA-Lib SMA + resample.** Trivial: `talib.SMA()` per TF + forward-fill align.

---

## 6. MACD Signal

**Role:** Momentum confirmation via MACD line / signal line crossover.

### Formula

```
fastMA  = EMA(close, 12)     # on selected TF
slowMA  = EMA(close, 26)     # on selected TF
macd    = fastMA - slowMA
signal  = SMA(macd, 9)
hist    = macd - signal

buy  = crossover(macd, signal)    # any enabled TF
sell = crossunder(macd, signal)   # any enabled TF
```

Supports 3 independent timeframes (T1, T2, T3). Signal is OR across enabled TFs.
Uses `hold_bars` pattern (default 3).

### Parameters

| Param | Type | Default | Range |
|-------|------|---------|-------|
| `fastLength` | int | 12 | fixed |
| `slowLength` | int | 26 | fixed |
| `signalLength` | int | 9 | fixed |
| `macd_signal_t1_selection` | TF | "grafico" | — |
| `macd_signal_t2_selection` | TF | "240" | — |
| `macd_signal_t3_selection` | TF | "D" | — |
| `macd_hold_bars` | int | 3 | 1–10 |

### Python Availability

**TA-Lib** `MACD()`. Trivial.

---

## 7. WaveTrend — Reversal

**Role:** Detect reversals when WaveTrend crosses in oversold/overbought zones.

### Formula

```
esa = EMA(hlc3, wtChannelLen)
de  = EMA(|hlc3 - esa|, wtChannelLen)
ci  = (hlc3 - esa) / (0.015 * de)

wt1 = EMA(ci, wtAverageLen)
wt2 = SMA(wt1, wtMALen)

oversold   = wt2 <= osLevel      # default -60
overbought = wt2 >= obLevel      # default  60

buy_reversal  = crossover(wt1, wt2) AND oversold
sell_reversal = crossunder(wt1, wt2) AND overbought
```

Calculated on 3 TFs. Signal is OR across enabled TFs. Uses `hold_bars`
(default `rev_lookback = 3`).

### Parameters

| Param | Type | Default | Range |
|-------|------|---------|-------|
| `wtChannelLen` | int | 9 | 5–30 |
| `wtAverageLen` | int | 12 | 5–30 |
| `wtMALen` | int | 3 | 2–10 |
| `osLevel` | int | -60 | -80 to -40 |
| `obLevel` | int | 60 | 40 to 80 |
| `wt_t[1-3]_selection` | TF | 240, D, W | — |
| `rev_lookback` | int | 3 | 1–10 |

### Python Availability

**Custom (NumPy).** Straightforward EMA chain. No library implements this
specific oscillator.

---

## 8. WaveTrend — Divergence

**Role:** Detect bullish/bearish divergences of WaveTrend against price.

### Formula

Builds on the WT1/WT2 from §8.

```
# Pivot detection (on wt2):
fractalTop = pivothigh(wt2, lookbackLeft=20, lookbackRight=1)
             AND wt2[2] >= obLevel
fractalBot = pivotlow(wt2, lookbackLeft=20, lookbackRight=1)
             AND wt2[2] <= osLevel

# Previous pivot values:
highPrev  = valuewhen(fractalTop, wt2[2], 0)[2]
highPrice = valuewhen(fractalTop, high[2], 0)[2]
lowPrev   = valuewhen(fractalBot, wt2[2], 0)[2]
lowPrice  = valuewhen(fractalBot, low[2], 0)[2]

# Divergence:
bearDiv = fractalTop AND high[2] > highPrice AND wt2[2] < highPrev   # regular bearish
bullDiv = fractalBot AND low[2] < lowPrice AND wt2[2] > lowPrev      # regular bullish

# Alternative detection:
bullishDiv2 = crossover(wt1, lowest(wt1, wtDivergenceLength=20))
bearishDiv2 = crossunder(wt1, highest(wt1, wtDivergenceLength=20))
```

Uses `hold_bars` (`div_lookbackwt = 3`). Signal is OR across enabled TFs.

### Parameters

| Param | Type | Default | Range |
|-------|------|---------|-------|
| `lookbackLeft` | int | 20 | 10–50 |
| `lookbackRight` | int | 1 | 1–5 |
| `wtDivergenceLength` | int | 20 | 10–50 |
| `div_lookbackwt` | int | 3 | 1–10 |

### Python Availability

**Custom (NumPy + scipy.signal).** `scipy.signal.argrelextrema` for pivots.
Most complex indicator to reimplement due to `valuewhen` semantics.

---

## 9. RSI + Bollinger Bands

**Role:** Mean-reversion signal — RSI crosses above/below a dispersion band.

### Formula

```
rsi_value = RSI(hlc3, 14)
basis     = EMA(rsi_value, 20)
dev       = 2 * StdDev(rsi_value, 20)
upper     = basis + dev
lower     = basis - dev

disp_up   = basis + (upper - lower) * 0.1
disp_down = basis - (upper - lower) * 0.1

buy  = crossover(rsi_value, disp_up)
sell = crossunder(rsi_value, disp_down)
```

Calculated on 3 independent TFs (T1, T2, T3). Signal is OR across enabled TFs.

### Parameters

| Param | Type | Default | Range |
|-------|------|---------|-------|
| `rsi_bb_period` | int | 14 | 5–30 |
| `rsi_bb_ma_period` | int | 20 | 10–50 |
| `rsi_bb_mult` | float | 2.0 | 1.0–3.0 |
| `rsi_bb_dispersion` | float | 0.1 | 0.0–0.5 |
| `rsi_t[1-3]_selection` | TF | grafico, 240, D | — |

### Python Availability

**TA-Lib `RSI()` + custom BB on RSI values.** Medium complexity.

---

## 10. RSI Simple

**Role:** Basic oversold/overbought filter.

### Formula

```
rsi = RSI(close, 14)
buy  = rsi < 30    # oversold
sell = rsi > 70    # overbought
```

### Parameters

| Param | Type | Default | Range |
|-------|------|---------|-------|
| `simple_rsi_length` | int | 14 | 5–30 |
| `rsi_ob_level` | int | 70 | 60–90 |
| `rsi_os_level` | int | 30 | 10–40 |

### Multi-TF

Single timeframe (chart TF).

### Python Availability

**TA-Lib** `RSI()`. Trivial.

---

## 11. Squeeze Momentum (LazyBear)

**Role:** Momentum direction + squeeze detection (volatility compression).

### Formula

```
# Bollinger Bands:
basis_bb = SMA(close, 20)
dev_bb   = 2.0 * StdDev(close, 20)     # NOTE: uses multKC, not mult
upperBB  = basis_bb + dev_bb
lowerBB  = basis_bb - dev_bb

# Keltner Channel:
basis_kc  = SMA(close, 20)
range_val = useTrueRange ? TR : (high - low)
rangema   = SMA(range_val, 20)
upperKC   = basis_kc + 1.5 * rangema
lowerKC   = basis_kc - 1.5 * rangema

# Squeeze states:
sqzOn  = lowerBB > lowerKC AND upperBB < upperKC     # BB inside KC
sqzOff = lowerBB < lowerKC AND upperBB > upperKC     # BB outside KC

# Momentum value:
midline = avg(avg(highest(high, 20), lowest(low, 20)), SMA(close, 20))
val     = linreg(close - midline, 20, 0)

# Colors (= signal):
lime   = val > 0 AND val > val[1]     # bullish accelerating
green  = val > 0 AND val <= val[1]    # bullish decelerating
red    = val < 0 AND val < val[1]     # bearish accelerating
maroon = val < 0 AND val >= val[1]    # bearish decelerating

# Signal:
buy  = (lime OR maroon)    # positive or bearish-decelerating
sell = (red OR green)      # negative or bullish-decelerating
```

Calculated on 3 TFs. Signal is OR across enabled TFs.

### Parameters

| Param | Type | Default | Range |
|-------|------|---------|-------|
| `length` | int | 20 | 10–50 |
| `mult` (BB) | float | 2.0 | 1.0–3.0 |
| `lengthKC` | int | 20 | 10–50 |
| `multKC` | float | 1.5 | 1.0–3.0 |
| `sqz_t[1-3]_selection` | TF | W, D, 240 | — |

### Python Availability

**Custom (NumPy).** `SMA`, `StdDev`, `TR` from TA-Lib. `linreg` = `numpy.polyfit`
or `scipy.stats.linregress`. No library has this exact combination.

---

## 12. VWAP

**Role:** Volume-weighted price level filter.

### Formula

```
vwap = ta.vwap    # built-in Pine Script cumulative VWAP

buy  = close > vwap
sell = close < vwap
```

### Parameters

| Param | Type | Default | Range |
|-------|------|---------|-------|
| `vwap_sel` | TF | "grafico" | any TF |

### Python Availability

**pandas-ta** `vwap()` or manual: `cumsum(typical_price * volume) / cumsum(volume)`.

---

## 13. EMA 9 / EMA 200 (Auxiliary Filter)

**Role:** Structural filter (not a signal indicator). Used in distance
calculations for the RM engine.

### Formula

```
ema_9   = EMA(close, 9)
ema_200 = EMA(close, 200)

por_encima_de_emas = close > ema_200 AND close < ema_9
por_debajo_de_emas = close < ema_200 AND close > ema_9
```

### Distance Filters

```
distancia_ssl           = |sslUp - sslDown|
distancia_stop_compra   = |close - up| <= distancia_ssl
distancia_stop_venta    = |close - dn| <= distancia_ssl
distancia_emas_valida   = distancia_ssl <= |ema_200 - ema_9|
```

These distance checks are auxiliary structural filters. They are documented
because they exist in the Pine strategy, but they are **not** currently part of
the Python `combine_signals()` contract and should be treated separately from
entry indicators during Sprint 2.

### Python Availability

**TA-Lib** `EMA()`. Trivial.

---

## Summary: Implementation Priority

| Priority | Indicator | Approach | Effort |
|----------|-----------|----------|--------|
| 🟢 Trivial | RSI Simple, MACD, VWAP, EMA 9/200 | TA-Lib wrapper | < 1h each |
| 🟡 Medium | SSL Channel, SSL LOW, MTF Conditions, RSI+BB | TA-Lib + custom logic | 2–4h each |
| 🔴 Complex | Firestorm, Firestorm TM, Squeeze Momentum, WaveTrend Rev, WaveTrend Div | Full custom NumPy/Numba | 4–8h each |

**Total estimated implementation effort (Sprint 2):** ~50–65 hours for all 13.
