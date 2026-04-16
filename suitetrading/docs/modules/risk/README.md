# Risk Module

`src/suitetrading/risk/`

## Overview

- Bar-by-bar position lifecycle via an FSM with gap-aware fills and slippage; single source of truth for entry/exit logic.
- 164 registered archetypes (120 explicit .py files + auto-generated variants) covering all indicator families used in Optuna/WFO runs.
- Portfolio-level controls (heat, drawdown, exposure, kill switch) are enforced above individual positions via `PortfolioRiskManager`.

---

## Files

| File | Responsibility | LOC |
|---|---|---|
| `state_machine.py` | Bar-by-bar FSM: position lifecycle, exit priority, gap fills, slippage | 564 |
| `trailing.py` | 6 exit/trailing policies | 354 |
| `position_sizing.py` | 4 position sizers | 241 |
| `portfolio.py` | `PortfolioRiskManager`: heat, drawdown, exposure, kill switch | 227 |
| `portfolio_optimizer.py` | `PortfolioOptimizer`: Kelly, HRP, MVO, equal-weight | 376 |
| `portfolio_validation.py` | `PortfolioValidator`: pre-run config validation | 512 |
| `correlation.py` | `StrategyCorrelationAnalyzer` | 314 |
| `stress_testing.py` | `StressTester`: scenario + Monte Carlo stress tests | 351 |
| `contracts.py` | `RiskConfig` + all sub-configs (`PortfolioLimits`, etc.) | 215 |
| `vbt_simulator.py` | VectorBT simulation adapter | 186 |
| `archetypes/__init__.py` | `ARCHETYPE_REGISTRY` + `get_archetype()` + auto-register hooks | 334 |
| `archetypes/_factory.py` | Combinatorial factory matrix for dynamic archetype generation | 223 |
| `archetypes/_fullrisk_base.py` | Shared base config for all `fullrisk_*` archetypes | — |

---

## FSM States

`FLAT → OPEN_INITIAL → PARTIALLY_CLOSED → OPEN_BREAKEVEN → OPEN_TRAILING → CLOSED`

Exit priority per bar (evaluated in order):
1. **SL** — stop loss (gap-fill aware)
2. **TP1** — first take-profit (partial close → `PARTIALLY_CLOSED`)
3. **BE** — move stop to breakeven (`OPEN_BREAKEVEN`)
4. **Trail** — trailing exit (`OPEN_TRAILING`)
5. **Time** — max-bars time exit
6. **Entry** — new position entry (only if `FLAT`)

---

## Exit Policies (`trailing.py`)

| Policy | Description |
|---|---|
| `BreakEvenPolicy` | Moves SL to entry after TP1 hit |
| `FixedTrailingStop` | Fixed-offset trailing stop |
| `ATRTrailingStop` | ATR-multiple trailing stop |
| `ChandelierExit` | Highest-high minus ATR multiple |
| `ParabolicSARStop` | SAR-based dynamic stop |
| `SignalTrailingExit` | Exit on signal reversal |

---

## Position Sizers (`position_sizing.py`)

| Sizer | Description |
|---|---|
| `FixedFractionalSizer` | Fixed % of equity per trade |
| `ATRSizer` | Risk a % of equity per ATR unit |
| `KellySizer` | Kelly criterion (win rate + R:R) |
| `OptimalFSizer` | Optimal-f (Ralph Vince) |

---

## Archetypes (164 registered)

121 `.py` files (including `__init__`, `_factory`, `_fullrisk_base`, `base`) + auto-generated variants.

| Family | Count | Notes |
|---|---|---|
| `fullrisk_pyr` variants | ~70 | Core Optuna targets: `roc_*`, `macd_*`, `ema_*`, `donchian_*`, `ssl_*`, `rsi_*`, `squeeze_*`, `ichimoku_*`, etc. Includes `_ftm`, `_trail_policy`, `_mtf`, `_htf_*` suffixes |
| `donchian/ema/macd/roc` combos | ~60 | `_simple`, `_adx`, `_roc`, `_mtf`, `_longopt`, `_shortopt`, multi-indicator combos |
| `rich_*` per-symbol | 11 | Auto-registered from `config/archetypes.py`; one per traded asset |
| Base presets | 6 | `trend_following`, `mean_reversion`, `mixed`, `pyramidal`, `grid_dca`, `legacy_firestorm` |

Auto-registration at import time:
- `_register_phase5_archetypes()` — any key in `ARCHETYPE_INDICATORS` ending in `_fullrisk_pyr` not already in registry
- `_register_rich_archetypes()` — any key starting with `rich_` not already in registry

---

## Portfolio Controls (`PortfolioRiskManager`)

`approve_new_risk()` returns `(bool, reason)` — blocks new entries when any gate fails.

| Gate | Default | Trigger |
|---|---|---|
| Kill switch | 25% DD | Permanent block; no new entries |
| Max drawdown | 20% DD | Block new entries until DD recovers |
| Portfolio heat | 15% of equity at risk | Block if `open_risk + proposed > 15%` |
| Gross exposure | 1.0× equity | Block if `gross_exposure + proposed > 1.0` |

---

## Tests

```bash
cd suitetrading
pytest tests/risk/ -v
```

Test files: `test_state_machine.py`, `test_trailing.py`, `test_position_sizing.py`, `test_portfolio.py`, `test_portfolio_optimizer.py`, `test_portfolio_validation.py`, `test_stress_testing.py`, `test_correlation.py`, `test_contracts.py`, `test_factory.py`, `test_vbt_simulator.py`.

---

> **DO NOT MODIFY `state_machine.py` without full regression on `tests/risk/test_state_machine.py`.**
> The FSM is the only authoritative position lifecycle implementation; silent behavior changes propagate to all backtests.
