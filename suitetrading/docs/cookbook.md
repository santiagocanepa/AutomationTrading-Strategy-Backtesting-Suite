# Cookbook — operational recipes

Common operational tasks: how to run discovery, monitor it, validate, build a portfolio, and paper-trade.

For methodology and rules see [`methodology.md`](methodology.md). For installation see [`setup.md`](setup.md).

---

## Phase 1 — random exhaustive discovery

### Smoke test (mandatory before any > 1 h run)

```bash
PYTHONPATH=src .venv/bin/python scripts/run_random_v9.py \
    --symbol SPY --direction long --timeframe 1h \
    --trials 30 --step-factor 4 \
    --output-dir /tmp/v9_smoke --seed 42 \
    --months 60 --exchange alpaca --commission 0.0
```

Inspect the output Parquet:

```bash
PYTHONPATH=src .venv/bin/python -c "
import pandas as pd; from pathlib import Path
files = sorted(Path('/tmp/v9_smoke/parquet').glob('*.parquet'))
df = pd.concat([pd.read_parquet(f) for f in files])
print(df[['sharpe','max_drawdown_pct','total_trades']].describe())
"
```

Verify `max_drawdown_pct` has variance (not all zero) — that bug has bitten in the past.

### Full discovery (one timeframe)

```bash
nohup bash scripts/run_exhaustive_v9.sh > artifacts/exhaustive_v9_master.log 2>&1 &

# Multi-TF variants
nohup bash scripts/run_v9_15m.sh > artifacts/exhaustive_v9_15m.log 2>&1 &
nohup bash scripts/run_v9_4h.sh  > artifacts/exhaustive_v9_4h.log  2>&1 &
```

Each shell launches up to 8 parallel `run_random_v9.py` processes (configurable via `MAX_CONCURRENT`), one per `(symbol, direction)` study. The script is resume-safe: it checks existing Parquet trial counts and skips completed studies.

### Monitoring discovery progress

```bash
# Trials per study
PYTHONPATH=src .venv/bin/python -c "
import pandas as pd; from pathlib import Path
TF = '1h'  # or '15m', '4h'
base = Path(f'artifacts/exhaustive_v9_{TF}/parquet') if TF != '1h' else Path('artifacts/exhaustive_v9/parquet')
for sym in ['SPY','QQQ','AAPL','NVDA','TSLA','IWM','XLK','XLE','GLD','TLT']:
    for d in ['long','short']:
        files = sorted(base.glob(f'{sym}_{TF}_rich_stock_{d}_*.parquet'))
        n = sum(len(pd.read_parquet(f, columns=['trial_id'])) for f in files) if files else 0
        status = 'OK' if n >= 100_000 else '..'
        print(f'  {status} {sym} {d}: {n:>7}/100000')
"

# Active processes
ps aux | grep run_random_v9 | grep -v grep | wc -l
```

---

## Phase 2 — post-hoc structural analysis

```python
import pandas as pd
from pathlib import Path

# Load all studies for a timeframe
files = sorted(Path('artifacts/exhaustive_v9/parquet').glob('*_1h_rich_stock_*.parquet'))
df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)

# Filter viable trials (TF-aware threshold)
viable = df[(df['sharpe'] > 0) & (df['total_trades'] >= 300)]
print(f"Viables: {len(viable)}/{len(df)} ({100*len(viable)/len(df):.2f}%)")

# State distribution: viable vs all
indicators = [
    'ssl_channel','squeeze','firestorm','wavetrend_reversal',
    'ma_crossover','macd','bollinger_bands','adx_filter','rsi','obv','ash'
]
for ind in indicators:
    col = f'{ind}____state'
    if col not in df.columns:
        continue
    v_dist = viable[col].value_counts(normalize=True)
    a_dist = df[col].value_counts(normalize=True)
    print(f'\n{ind}:')
    for state in ['Excluyente', 'Opcional', 'Desactivado']:
        v, a = v_dist.get(state, 0), a_dist.get(state, 0)
        print(f"  {state}: viable={v:.1%} vs all={a:.1%} (delta={v-a:+.1%})")
```

The HQ candidate pool is the subset of `viable` that meets the additional thresholds documented in [`methodology.md`](methodology.md).

---

## Phase 3 — Optuna refinement on the HQ space

```bash
.venv/bin/python scripts/run_discovery.py \
    --symbols SPY --directions long --timeframes 1h \
    --archetypes rich_stock --trials 1000 --top-n 100 \
    --commission 0.0 --exchange alpaca --months 60 \
    --mode fsm --metric sharpe \
    --sampler nsga2 --step-factor 4 \
    --pbo-threshold 0.20 --wfo-splits 5 --holdout-months 6 \
    --output-dir artifacts/validation_v9
```

Phase 3 *does* use Optuna — that is the methodology. The rule against Optuna applies only to Phase 1 (exploration of the full space). See [`methodology.md`](methodology.md) for the rationale.

### Anti-overfit gates (applied automatically)

| Metric | Threshold |
|--------|-----------|
| DSR | > 0.95 |
| Sharpe (annualized) | > 0.80 |
| PBO | < 0.20 |
| Trades (per fold) | ≥ 300 (1h) |
| Max DD (p95) | < 25 % |

### fANOVA importance on a completed study

```bash
PYTHONPATH=src .venv/bin/python -c "
import optuna, warnings
warnings.filterwarnings('ignore')
from optuna.importance import get_param_importances, FanovaImportanceEvaluator
study = optuna.load_study(
    study_name='SPY_1h_rich_stock_long',
    storage='sqlite:///artifacts/validation_v9/studies/SPY_1h_rich_stock_long.db'
)
items = get_param_importances(study, evaluator=FanovaImportanceEvaluator(),
                              target=lambda t: t.values[0])
for p, v in sorted(items.items(), key=lambda x: -x[1])[:15]:
    print(f'{v:.3f}  {p}')
"
```

---

## Phase 4 — portfolio construction

### Build candidate pool

```bash
.venv/bin/python scripts/build_candidate_pool.py \
    --pbo-threshold 0.30 --max-per-study 3 \
    --output-dir artifacts/candidate_pool \
    --months 36 --apply-slippage
```

### Walk-forward validation

```bash
.venv/bin/python scripts/portfolio_walkforward.py \
    --pool-dir artifacts/candidate_pool \
    --output-dir artifacts/portfolio_wfo \
    --is-fraction 0.70
```

### Ensemble PBO + DSR + SPA

```bash
.venv/bin/python scripts/validate_portfolio.py \
    --finalists-dir artifacts/candidate_pool \
    --output-dir artifacts/portfolio_validation
```

### Construct portfolio (correlation + selection + weighting)

```bash
.venv/bin/python scripts/run_portfolio.py \
    --finalists artifacts/candidate_pool/finalists.csv \
    --evidence-dir artifacts/candidate_pool \
    --output-dir artifacts/portfolio \
    --target-count 100 --max-avg-corr 0.60 \
    --methods equal shrinkage_kelly \
    --n-trials 2500
```

---

## Phase 4b/4c — cross-validation suite

The TIER A/B/C tests are documented in [`validation_framework.md`](validation_framework.md). The harness is reusable for any portfolio output. Implementation lives under `analysis_work/phase4{b,c}_*.py` (gitignored — contains portfolio-specific paths).

A typical sequence:

```bash
# Each script reads phase4_portfolio_final.parquet and writes phase4{b,c}_*.parquet/json/csv
.venv/bin/python analysis_work/phase4b_corr.py        # correlation matrix + dedup
.venv/bin/python analysis_work/phase4b_slippage.py    # slippage stress
.venv/bin/python analysis_work/phase4b_regime.py      # regime stress
.venv/bin/python analysis_work/phase4b_leak.py        # HO vs IS scatter
.venv/bin/python analysis_work/phase4c_tier_b_master.py
.venv/bin/python analysis_work/phase4c_tier_c.py
```

---

## Replay with realistic slippage

```bash
.venv/bin/python scripts/replay_with_slippage.py \
    --evidence-dir artifacts/candidate_pool/evidence \
    --output-dir artifacts/slippage_analysis
```

Useful for re-evaluating any candidate pool under a more conservative slippage assumption without rerunning the entire pipeline.

---

## Permutation null hypothesis test

```bash
.venv/bin/python scripts/run_null_hypothesis.py \
    --output-dir artifacts/null_hypothesis
```

This is the meta-validation of the optimization sub-pipeline: it permutes OHLCV (preserving marginals, destroying serial structure), runs the entire pipeline, and verifies that no significant strategies emerge from noise. A high false-positive rate (> 10 %) on the noise data indicates the pipeline itself is overfitting.

---

## Paper trading

```bash
.venv/bin/python scripts/run_paper_portfolio.py \
    --portfolio-dir artifacts/portfolio \
    --exchange alpaca
```

Requires `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` in environment (paper account is sufficient).

---

## Tests

```bash
.venv/bin/python -m pytest tests/ -x -q                                   # all (1,468)
.venv/bin/python -m pytest tests/optimization/ -v                         # optimization
.venv/bin/python -m pytest tests/risk/test_state_machine.py -v            # FSM
.venv/bin/python -m pytest tests/indicators/ -v                           # indicators
.venv/bin/python -m pytest tests/ -k "test_max_excluyente" -v             # state-classification rules
```

Test execution is ~25 seconds for the full suite on an M4 Pro.

---

## Hardware notes

- **M4 Pro 48 GB** — empirically saturates at ~8 parallel `run_random_v9.py` processes; throughput is I/O-bound on the 1-minute Parquet reads, not CPU-bound.
- **Discovery throughput** — ~5–10 K trials per hour per study (TF-dependent: 4h faster, 15m slower because of the bar-count differential).
- **Disk** — full multi-TF discovery (15m + 1h + 4h × 20 studies × 100 K trials) writes ~7 GB of Parquet (zstd-compressed).
