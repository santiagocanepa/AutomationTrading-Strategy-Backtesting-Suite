# Indicator Availability Matrix — SuiteTrading v2

> Maps each Pine Script indicator to its Python implementation strategy.
> "Available" = existing library function. "Custom" = must be hand-coded.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ LIB | Available in TA-Lib, pandas-ta, or similar |
| 🔧 CUSTOM | Requires custom implementation |
| ⚠️ PARTIAL | Library covers base calc, custom logic needed on top |

---

## Entry Indicators

| # | Indicator | TA-Lib | pandas-ta | Custom | Decision | Notes |
|---|-----------|--------|-----------|--------|----------|-------|
| 1 | **Firestorm** | — | — | 🔧 | **Custom (Numba)** | Supertrend variant with `ohlc4` src, ratchet logic, hold-bars. No library matches the exact variant. |
| 2 | **ASH (Absolute Strength Histogram)** | — | `pta.aberration` (no) | 🔧 | **Custom** | 3 modes (RSI/Stochastic/ADX) × 6 MA types (ALMA/EMA/WMA/SMA/SMMA/HMA). No library implements this combo. |
| 3 | **SSL Channel** | — | `pta.ssl` ⚠️ | ⚠️ | **Custom** | pandas-ta `ssl()` exists but the SuiteTrading variant uses EMA(high/low), Pine-style Hlv flips, and hold-bars. Reimplementation is required for exact parity. |
| 4 | **SSL Channel LOW** | — | — | 🔧 | **Custom (Numba-backed)** | Same EMA/Hlv core as SSL Channel, but used as trailing trigger on an independent timeframe. |
| 5 | **MTF Conditions** | ✅ `ta.SMA` | ✅ `pta.sma` | — | **TA-Lib** | 5 × SMA(close, 50) on different TFs. SMA is trivially available. Custom part: multi-TF resampling + "all above/below" logic. |
| 6 | **MACD Signal** | ✅ `ta.MACD` | ✅ `pta.macd` | — | **TA-Lib** | Standard MACD(12,26,9). Signal = histogram crossover. |
| 7 | **WaveTrend Reversal** | — | — | 🔧 | **Custom (Numba)** | WT oscillator (EMA of EMA of hlc3) + reversal detection with fractal pivots. No library. |
| 8 | **WaveTrend Divergence** | — | — | 🔧 | **Custom (Numba)** | Same WT oscillator + divergence detection (price vs WT highs/lows). |
| 9 | **RSI + Bollinger Bands** | ✅ `ta.RSI` + `ta.BBANDS` | ✅ | — | **TA-Lib** | RSI(14) + BB(RSI, 50, 1.0). Buy = RSI crosses above lower BB. |
| 10 | **RSI Simple** | ✅ `ta.RSI` | ✅ | — | **TA-Lib** | RSI(14) > 50 buy, < 50 sell. Trivial. |
| 11 | **Squeeze Momentum** | — | `pta.squeeze` ⚠️ | ⚠️ | **Custom** | LazyBear version: BB(20,2) vs KC(20,1.5), momentum = linreg(close-avg(highest,lowest,SMA),20). pandas-ta's squeeze is close but uses different momentum formula. |
| 12 | **VWAP** | — | ✅ `pta.vwap` | — | **pandas-ta** | Standard VWAP. Signal: close > vwap = buy. |
| 13 | **Fibonacci MAI** | — | — | 🔧 | **Custom** | EMA of EMAs at Fibonacci periods [1,2,3,5,8,13,21]. No library. |
| 14 | **EMA 9/200** | ✅ `ta.EMA` | ✅ | — | **TA-Lib** | Distance filter only. |

---

## Risk Management Indicators (Not in combiner)

| # | Indicator | Purpose | Decision | Notes |
|---|-----------|---------|----------|-------|
| 15 | **Firestorm TM** | Stop-Loss bands | **Custom (Numba)** | Same as Firestorm but on configurable TF (default: Daily). ATR via `request.security()`. |

---

## Summary by Implementation Type

| Category | Count | Indicators |
|----------|-------|------------|
| **TA-Lib** (drop-in) | 5 | MTF Conditions (SMA), MACD Signal, RSI+BB, RSI Simple, EMA 9/200 |
| **pandas-ta** (drop-in) | 1 | VWAP |
| **Custom (Numba-backed)** | 6 | Firestorm, Firestorm TM, SSL Channel, SSL Channel LOW, WaveTrend Reversal, WaveTrend Divergence |
| **Custom (pure NumPy)** | 3 | ASH, Squeeze Momentum, Fibonacci MAI |

---

## Sprint 0 Prototype Priorities

These 3 indicators are prioritized for Sprint 0 because they are:
1. **Custom-only** (no library shortcut)
2. **Core to the strategy** (high usage in default configuration)
3. **Representative of different patterns** (supertrend, oscillator, channel)

| Priority | Indicator | Why |
|----------|-----------|-----|
| P1 | **SSL Channel** | Used for TP1 trigger and optional entry signal. Pattern: EMA high/low channel with Hlv flip. |
| P2 | **Firestorm** | Core entry indicator + SL generator (TM variant). Pattern: Supertrend with ratchet. |
| P3 | **WaveTrend** | Reversal + divergence modes. Pattern: oscillator with fractal pivot detection. |

---

## Dependency Map

```
numpy ─────┬──► All custom indicators (array ops)
           │
numba ─────┤  ► Firestorm, Firestorm TM, WaveTrend (hot loops)
           │
TA-Lib ────┤  ► MACD, RSI, RSI+BB, EMA, SMA
           │    TA-Lib provides: ATR, EMA, SMA, RSI, BBANDS, MACD
           │
pandas-ta ─┤  ► VWAP (uses cumulative volume)
           │
pandas ────┴──► All indicators (Series I/O, resampling)
```

---

## Implementation Contract

Every indicator must implement the `Indicator` ABC from `src/suitetrading/indicators/base.py`:

```python
class MyIndicator(Indicator):
    @staticmethod
    def params_schema() -> dict:
        """Return {param_name: (type, default, min, max)}"""

    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Return boolean Series: True where signal is active."""
```

For indicators with both buy and sell signals, `compute()` returns the side
requested by a `direction` parameter (`"long"` / `"short"`). New standard
wrappers in Sprint 2 should preserve that contract.
