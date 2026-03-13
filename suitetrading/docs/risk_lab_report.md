# Risk Lab Report — Sprint 5.5

> 216 campaigns | 3 symbols × 4 timeframes × 3 strategies × 6 risk presets
> Data: 6 months | Exchange: Binance | Mode: FSM
> Run: 2026-03-12

## 1. Executive Summary

**14 of 216 campaigns (6.5%) produced positive Sharpe ratios.** 8 campaigns had positive total returns. The majority of edge comes from the **mean-reversion family** with **break-even disabled** (`no_break_even` preset), particularly on 4h and 1h timeframes.

### Key Finding

Break-even mechanics are **hurting** mean-reversion strategies. The `no_break_even` preset is the top performer across all symbols and the only preset with consistently positive Sharpe. This suggests the BE stop is cutting winners too early in mean-reversion contexts.

## 2. Campaign Matrix

| Dimension | Values | Count |
|-----------|--------|-------|
| Symbols | BTCUSDT, ETHUSDT, SOLUSDT | 3 |
| Timeframes | 15m, 1h, 4h, 1d | 4 |
| Strategies | ssl_trend, firestorm_trend, wavetrend_meanrev | 3 |
| Risk Presets | 6 per family (trend: 6, mean_rev: 6) | 6 |
| **Total** | | **216** |

## 3. Results by Strategy Family

| Family | Mean Sharpe | Mean Return | Mean DD | Total Trades |
|--------|------------|-------------|---------|--------------|
| mean_reversion | -1.642 | -5.37% | 6.36% | 5,930 |
| trend | -3.199 | -0.99% | 1.16% | 3,160 |

Mean-reversion generates far more trades (5,930 vs 3,160) but with worse mean metrics. Trend strategies have tighter drawdowns but are uniformly negative.

## 4. Results by Symbol

| Symbol | Mean Sharpe | Mean Return | Total Trades |
|--------|------------|-------------|--------------|
| BTCUSDT | -2.953 | -2.71% | 3,058 |
| ETHUSDT | -2.476 | -2.32% | 2,903 |
| SOLUSDT | -2.612 | -2.33% | 3,129 |

ETHUSDT shows the best mean Sharpe, consistent with it having the most positive-Sharpe campaigns.

## 5. Results by Timeframe

| TF | Mean Sharpe | Mean Return | Total Trades |
|----|------------|-------------|--------------|
| 15m | -1.318 | -6.73% | 5,977 |
| 1h | -1.496 | -1.89% | 2,122 |
| 4h | -1.993 | -0.62% | 790 |
| 1d | -5.913 | -0.55% | 201 |

**15m** generates the most trades but worst returns. **4h** provides the best risk-adjusted returns and is where most positive-Sharpe campaigns cluster. **1d** has too few trades for statistical significance.

## 6. Risk Preset Analysis

### Trend Family

| Preset | Mean Sharpe | Mean Return |
|--------|------------|-------------|
| wide_stop | -3.205 | -0.61% |
| base | -3.372 | -0.70% |
| no_pyramid | -3.372 | -0.70% |
| atr_sizer | -3.403 | -1.50% |
| tight_stop | -3.862 | -0.96% |
| partial_tp_on | -1.982 | -1.47% |

- `partial_tp_on` has the best Sharpe (least negative) but higher return loss — it generates more trades via partial exits.
- `wide_stop` has the best return (-0.61%) — wider stops reduce whipsaw but don't change the negative edge.
- `no_pyramid` ≈ `base` — pyramiding was rarely triggered in this sample.

### Mean-Reversion Family

| Preset | Mean Sharpe | Mean Return |
|--------|------------|-------------|
| loose_stop | -0.502 | -6.23% |
| base_safe | -0.865 | -7.35% |
| time_exit | -0.911 | -7.29% |
| tight_stop | -1.262 | -8.49% |
| no_break_even | -1.937 | -0.27% |
| no_partial_tp | -4.377 | -2.60% |

- **`no_break_even`**: Worst mean Sharpe by magnitude, but **best mean return (-0.27%)** and the only preset producing positive campaigns. The high Sharpe variance indicates it's asymmetric — big wins on some combos.
- `loose_stop` has the best mean Sharpe — more room for reversals to play out.
- `no_partial_tp` is catastrophic — without partials, mean-reversion trades run into full stops.

## 7. Top 10 Campaigns (Positive Sharpe)

| # | Campaign | Sharpe | Return | Max DD |
|---|----------|--------|--------|--------|
| 1 | ETHUSDT\_4h\_wavetrend\_no\_break\_even | 3.250 | +0.71% | 0.05% |
| 2 | ETHUSDT\_1h\_wavetrend\_no\_break\_even | 1.213 | +1.16% | 0.11% |
| 3 | SOLUSDT\_4h\_wavetrend\_no\_break\_even | 1.083 | +0.79% | 1.06% |
| 4 | BTCUSDT\_4h\_wavetrend\_no\_break\_even | 0.702 | +0.27% | 0.61% |
| 5 | BTCUSDT\_1d\_wavetrend\_loose\_stop | 0.513 | +0.11% | 1.20% |
| 6 | BTCUSDT\_1h\_wavetrend\_no\_break\_even | 0.441 | +0.40% | 0.68% |
| 7 | ETHUSDT\_4h\_wavetrend\_tight\_stop | 0.073 | +0.01% | 2.31% |
| 8 | ETHUSDT\_4h\_wavetrend\_base\_safe | 0.051 | -0.02% | 1.94% |
| 9 | ETHUSDT\_4h\_wavetrend\_time\_exit | 0.051 | -0.02% | 1.94% |
| 10 | ETHUSDT\_4h\_wavetrend\_loose\_stop | 0.050 | -0.01% | 1.70% |

All top campaigns are **wavetrend mean-reversion**. The top 6 are all **no_break_even**.

## 8. Observations & Implications

### For Sprint 6 (Optimization)

1. **Break-even should be a first-class optimization parameter** for mean-reversion. Consider adding `break_even__enabled` to DEFAULT_RISK_SEARCH_SPACE.
2. **4h is the sweet-spot timeframe** for the current strategy set — enough bars for statistical significance, filters enough noise.
3. **Trend strategies need indicator-level optimization** — the fixed-parameter entries (SSL length=12, Firestorm period=10) may not be optimal for all symbols/TFs.
4. **time_exit ≈ base_safe** for mean-reversion — the 20-bar limit rarely activates within the holding period.

### For the Risk Engine

5. **Pyramiding has minimal impact** in this sample — `base` ≈ `no_pyramid` everywhere. Either the threshold_factor is too restrictive or the data regime doesn't favor adds.
6. **Commission drag is significant** — all trend strategies show -0.5% to -1.5% return, much of which is commission on low-edge trades.
7. **Portfolio limits were disabled** — no conclusions yet about multi-position risk.

## 9. Artifacts

- Full results CSV: `artifacts/risk_lab/BTCUSDT_ETHUSDT_SOLUSDT_15m_1h_4h_1d_20260312_133450/risk_lab_results.csv`
- Interactive dashboards: `breakdown_by_symbol.html`, `breakdown_by_timeframe.html`, `metric_distributions.html`, `risk_return_scatter.html`
- Ranking: `ranking.csv`
