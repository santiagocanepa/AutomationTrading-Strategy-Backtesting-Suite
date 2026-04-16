# Cross-Validation Report: Resampled vs Native Exchange Data

Generated: 2026-03-11

## Methodology

- Download native 1h and 1d klines from exchange via CCXT
- Resample stored 1m data → 1h and 1m → 1d using OHLCVResampler
- Exclude the leading partial bar and compare only fully covered target candles
- Compare OHLC (tolerance ≤ 0.01%) and Volume (absolute diff ≤ 1e-9)

## Results

### BTCUSDT

#### 1m → 1h: **PASS**

- Comparison start: 2026-02-09T20:00:00+00:00
- Bars compared: 719
- open: max diff = 0.000000% (PASS)
- high: max diff = 0.000000% (PASS)
- low: max diff = 0.000000% (PASS)
- close: max diff = 0.000000% (PASS)
- volume: max abs diff = 0.000000 (PASS)

#### 1m → 1d: **PASS**

- Comparison start: 2026-02-10T00:00:00+00:00
- Bars compared: 29
- open: max diff = 0.000000% (PASS)
- high: max diff = 0.000000% (PASS)
- low: max diff = 0.000000% (PASS)
- close: max diff = 0.000000% (PASS)
- volume: max abs diff = 0.000000 (PASS)

### ETHUSDT

#### 1m → 1h: **PASS**

- Comparison start: 2026-02-09T20:00:00+00:00
- Bars compared: 719
- open: max diff = 0.000000% (PASS)
- high: max diff = 0.000000% (PASS)
- low: max diff = 0.000000% (PASS)
- close: max diff = 0.000000% (PASS)
- volume: max abs diff = 0.000000 (PASS)

#### 1m → 1d: **PASS**

- Comparison start: 2026-02-10T00:00:00+00:00
- Bars compared: 29
- open: max diff = 0.000000% (PASS)
- high: max diff = 0.000000% (PASS)
- low: max diff = 0.000000% (PASS)
- close: max diff = 0.000000% (PASS)
- volume: max abs diff = 0.000000 (PASS)

### SOLUSDT

#### 1m → 1h: **PASS**

- Comparison start: 2026-02-09T20:00:00+00:00
- Bars compared: 719
- open: max diff = 0.000000% (PASS)
- high: max diff = 0.000000% (PASS)
- low: max diff = 0.000000% (PASS)
- close: max diff = 0.000000% (PASS)
- volume: max abs diff = 0.000000 (PASS)

#### 1m → 1d: **PASS**

- Comparison start: 2026-02-10T00:00:00+00:00
- Bars compared: 29
- open: max diff = 0.000000% (PASS)
- high: max diff = 0.000000% (PASS)
- low: max diff = 0.000000% (PASS)
- close: max diff = 0.000000% (PASS)
- volume: max abs diff = 0.000000 (PASS)
