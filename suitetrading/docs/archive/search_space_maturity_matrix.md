# Search Space Maturity Matrix — v1

> Frozen at Sprint 5.5 gate. Any promotion requires evidence + regression run.

## Classification Criteria

| Level | Definition |
|-------|-----------|
| **active** | Fully tested, covered by regression fixtures, safe for production optimization. |
| **partial** | Implemented and wired, targeted tests exist, but not yet validated across multiple symbols/TFs. |
| **experimental** | Implemented but untested in real campaigns, or high-dimensional risk. |

---

## Risk Parameters

| Dimension (flat key) | Config Path | Type | Range | Default | Maturity | Notes |
|---------------------|-------------|------|-------|---------|----------|-------|
| `stop__atr_multiple` | `stop.atr_multiple` | float | [1.0, 5.0] step 0.5 | 2.0 | **active** | In DEFAULT_RISK_SEARCH_SPACE. Regression-covered. |
| `sizing__risk_pct` | `sizing.risk_pct` | float | [0.5, 3.0] step 0.25 | 1.0 | **active** | In DEFAULT_RISK_SEARCH_SPACE. Regression-covered. |
| `stop__fixed_pct` | `stop.fixed_pct` | float | [0.01, 50.0] | 2.0 | partial | Fallback when ATR=0 (warmup). Not in search space. |
| `sizing__model` | `sizing.model` | str | fixed_fractional, atr, kelly, optimal_f | fixed_fractional | partial | 4 models implemented: fixed_fractional, atr, kelly, optimal_f. |
| `sizing__kelly_fraction` | `sizing.kelly_fraction` | float | [0.01, 1.0] | 0.5 | experimental | Kelly requires strategy_stats — not wired yet. |
| `sizing__max_leverage` | `sizing.max_leverage` | float | [1.0, 125.0] | 1.0 | experimental | No leverage logic in runner beyond sizer. |
| `trailing__model` | `trailing.model` | str | atr, chandelier, sar, etc. | atr | partial | 6 policies implemented. Only "atr" tested in integration. |
| `trailing__atr_multiple` | `trailing.atr_multiple` | float | [0.1, 20.0] | 2.5 | partial | Used by ATRTrailingStop policy. |
| `trailing__trailing_mode` | `trailing.trailing_mode` | str | signal, policy | signal | partial | Wired in Sprint 5.5. Integration-tested. |
| `partial_tp__enabled` | `partial_tp.enabled` | bool | — | True | **active** | Regression-covered in fixtures. |
| `partial_tp__close_pct` | `partial_tp.close_pct` | float | [1.0, 100.0] | 35.0 | partial | Tested at 35% only. |
| `partial_tp__profit_distance_factor` | `partial_tp.profit_distance_factor` | float | [1.0, 5.0] | 1.01 | partial | Controls how much profit needed for TP1. |
| `break_even__enabled` | `break_even.enabled` | bool | — | True | **active** | Regression-covered. |
| `break_even__buffer` | `break_even.buffer` | float | [1.0, 1.05] | 1.0007 | partial | Integration-tested at 1.0007. |
| `pyramid__enabled` | `pyramid.enabled` | bool | — | True | **active** | Regression-covered. |
| `pyramid__max_adds` | `pyramid.max_adds` | int | [0, 20] | 3 | partial | Integration-tested. |
| `pyramid__block_bars` | `pyramid.block_bars` | int | [0, 500] | 15 | partial | Integration-tested at 20. |
| `pyramid__threshold_factor` | `pyramid.threshold_factor` | float | [1.0, 2.0] | 1.01 | experimental | Interacts with stop distance. |
| `pyramid__weighting` | `pyramid.weighting` | str | fibonacci, equal, decreasing | fibonacci | experimental | Not fully wired in runner. |
| `time_exit__enabled` | `time_exit.enabled` | bool | — | False | **active** | Regression fixture + integration tests. |
| `time_exit__max_bars` | `time_exit.max_bars` | int | [1, 10000] | 100 | partial | Tested at 10 and 20. |
| `portfolio__enabled` | `portfolio.enabled` | bool | — | False | partial | Feature-flagged. Integration-tested. |
| `portfolio__max_portfolio_heat` | `portfolio.max_portfolio_heat` | float | [0.1, 100.0] | 15.0 | experimental | Single-symbol runner, limited utility. |
| `portfolio__kill_switch_drawdown` | `portfolio.kill_switch_drawdown` | float | [1.0, 100.0] | 25.0 | experimental | Not tested E2E with real data. |
| `commission_pct` | `commission_pct` | float | [0.0, 10.0] | 0.07 | **active** | Baked into all regression fixtures. |
| `slippage_pct` | `slippage_pct` | float | [0.0, 5.0] | 0.0 | partial | Implemented but default 0, not tested with >0. |

---

## Indicators

| Name | Type | Params | Maturity | Notes |
|------|------|--------|----------|-------|
| `ssl_channel` | custom | length [2,200], hold_bars [1,20] | **active** | Primary trend strategy. Grid-validated in Sprints 3-4. |
| `ssl_channel_low` | custom | length [2,200] | **active** | Low variant of SSL. Grid-validated. |
| `firestorm` | custom | period [2,100], multiplier [0.1,10], hold_bars [1,20] | **active** | Primary trend strategy. Grid-validated. |
| `firestorm_tm` | custom | period [2,100], multiplier [0.1,10] | **active** | Firestorm trend momentum variant. |
| `wavetrend_reversal` | custom | channel_len, average_len, ma_len, ob/os_level, hold_bars | **active** | Mean-reversion strategy. Grid-validated. |
| `wavetrend_divergence` | custom | channel_len, average_len, ma_len, ob/os_level, lookback_left/right, divergence_length, hold_bars | partial | 9 params = high dimensional. Grid-validated but expensive. |
| `rsi` | standard | period [2,100], threshold [5,95], mode | partial | Smoke-tested. Not yet used in grid campaigns. |
| `ema` | standard | period [2,600], mode | partial | Smoke-tested. Filter use only. |
| `macd` | standard | fast, slow, signal, mode | partial | Smoke-tested. Not in grid campaigns. |
| `atr` | standard | period [2,100], ma_period, multiplier | partial | Smoke-tested. Used internally by sizer. |
| `vwap` | standard | mode | partial | Smoke-tested. Session-anchor — 24h crypto. |
| `bollinger_bands` | standard | period [5,100], nbdev [0.5,5], mode | partial | Smoke-tested. Not in grid campaigns. |

---

## Summary Counts

| Maturity | Risk Params | Indicators | Total |
|----------|-------------|------------|-------|
| active | 7 | 5 | 12 |
| partial | 14 | 7 | 21 |
| experimental | 6 | 0 | 6 |
| **Total** | **27** | **12** | **39** |

## Promotion Path

To promote a dimension from partial → active:
1. Run ≥ 3 symbols × 2 TFs with the dimension in the search space
2. Verify no NaN/inf in objective values
3. Add regression fixture covering the dimension
4. Update this matrix version

To promote from experimental → partial:
1. Write targeted integration test
2. Run at least 1 full campaign with the dimension active
3. Verify no crashes or degenerate results
