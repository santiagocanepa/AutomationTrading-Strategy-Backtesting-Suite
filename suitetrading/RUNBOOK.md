# SuiteTrading — Runbook v9

**Complementa:** `DIRECTION.md` (metodología), `HANDOFF.md` (estado de sesión)
**Root:** `$ROOT` = directorio `suitetrading/`
**Python:** `$ROOT/.venv/bin/python`

---

## Pre-requisitos

```bash
cd $ROOT
PYTHON=.venv/bin/python
$PYTHON -m pytest tests/ -x -q --tb=no 2>&1 | tail -3   # 1467 tests OK
```

**Datos stocks (5+ años 1m):**
```bash
$PYTHON scripts/download_data.py \
    --symbols SPY QQQ IWM AAPL NVDA TSLA GLD XLK XLE TLT \
    --timeframes 1m --exchange alpaca
```

---

## V9: Exhaustive Random Search (ACTUAL)

### Lanzar exploración completa
```bash
# Borra SQLite viejas si existen
rm -rf artifacts/exhaustive_v9/studies/

# Lanzar (background, resume-safe)
nohup bash scripts/run_exhaustive_v9.sh > artifacts/exhaustive_v9_master.log 2>&1 &
```

### Monitorear progreso
```bash
# Log general
cat artifacts/exhaustive_v9_master.log

# Trials por study
PYTHONPATH=src $PYTHON -c "
import pandas as pd; from pathlib import Path
for name in ['SPY','QQQ','AAPL','NVDA','TSLA','IWM','XLK','XLE','GLD','TLT']:
    for d in ['long','short']:
        sname = f'{name}_1h_rich_stock_{d}'
        files = sorted(Path('artifacts/exhaustive_v9/parquet').glob(f'{sname}_*.parquet'))
        total = sum(len(pd.read_parquet(f, columns=['trial_id'])) for f in files) if files else 0
        status = '✓' if total >= 300000 else '○'
        print(f'  {status} {name} {d}: {total}/300000')
"

# Procesos activos
ps aux | grep run_random_v9 | grep -v grep | wc -l
```

### Smoke test rápido
```bash
PYTHONPATH=src PYTHONWARNINGS="ignore" $PYTHON scripts/run_random_v9.py \
    --symbol SPY --direction long --timeframe 1h \
    --trials 200 --step-factor 4 \
    --output-dir /tmp/v9_smoke --seed 42 \
    --months 60 --exchange alpaca --commission 0.0
```

### Análisis post-hoc (Fase 2, después de completar Fase 1)
```python
import pandas as pd
from pathlib import Path

# Cargar un study
files = sorted(Path('artifacts/exhaustive_v9/parquet').glob('SPY_1h_rich_stock_long_*.parquet'))
df = pd.concat([pd.read_parquet(f) for f in files])

# Filtrar viables
viable = df[(df['sharpe'] > 0) & (df['total_trades'] >= 300)]
print(f"Viables: {len(viable)}/{len(df)} ({len(viable)/len(df)*100:.2f}%)")

# Estado de indicadores en viables vs no-viables
indicators = ['ssl_channel','squeeze','firestorm','wavetrend_reversal',
              'ma_crossover','macd','bollinger_bands','adx_filter','rsi','obv','ash']
for ind in indicators:
    col = f"{ind}____state"
    if col in df.columns:
        viable_dist = viable[col].value_counts(normalize=True)
        all_dist = df[col].value_counts(normalize=True)
        print(f"\n{ind}:")
        for state in ['Excluyente', 'Opcional', 'Desactivado']:
            v = viable_dist.get(state, 0)
            a = all_dist.get(state, 0)
            print(f"  {state}: viable={v:.1%} vs all={a:.1%} (delta={v-a:+.1%})")
```

---

## Runs históricos (referencia)

### v4 — Mejor resultado con optimizer ✅
```bash
$PYTHON scripts/run_discovery.py \
    --symbols SPY --directions long --timeframes 1h \
    --archetypes rich_stock --trials 10000 --top-n 100 \
    --commission 0.0 --exchange alpaca --months 60 \
    --mode fsm --metric sharpe \
    --sampler nsga2 --n-jobs 1 --step-factor 4 \
    --pbo-threshold 0.30 --wfo-splits 5 --holdout-months 6 \
    --seed 42 --output-dir artifacts/discovery_rich_v4
```
- 31 finalists, PBO 0.014-0.271
- Artifacts: `artifacts/discovery_rich_v4/`

### fANOVA en study de Optuna (v4 reference)
```bash
PYTHONPATH=src $PYTHON -c "
import optuna, warnings; warnings.filterwarnings('ignore')
from optuna.importance import get_param_importances, FanovaImportanceEvaluator
study = optuna.load_study(
    study_name='SPY_1h_rich_stock_long',
    storage='sqlite:///artifacts/discovery_rich_v4/studies/SPY_1h_rich_stock_long.db'
)
for p, v in sorted(
    get_param_importances(study, evaluator=FanovaImportanceEvaluator(),
                          target=lambda t: t.values[0]).items(),
    key=lambda x: -x[1])[:15]:
    print(f'{v:.3f}  {p}')
"
```

---

## Validación WFO (Fase 3, sobre top ~1000 de Fase 2)

```bash
# Usar run_discovery.py CON Optuna para validar configuraciones específicas
$PYTHON scripts/run_discovery.py \
    --symbols SPY --directions long --timeframes 1h \
    --archetypes rich_stock --trials 1000 --top-n 100 \
    --commission 0.0 --exchange alpaca --months 60 \
    --mode fsm --metric sharpe \
    --sampler nsga2 --step-factor 4 \
    --pbo-threshold 0.20 --wfo-splits 5 --holdout-months 6 \
    --output-dir artifacts/validation_v9
```

### Gates
| Métrica | Threshold |
|---------|-----------|
| DSR | > 0.95 |
| Sharpe | > 0.80 |
| PBO | < 0.20 |
| MIN_TRADES | ≥ 300 |
| Max DD p95 | < 25% |

---

## Capa Downstream (Portfolio Construction)

### Build candidate pool
```bash
$PYTHON scripts/build_candidate_pool.py \
    --pbo-threshold 0.30 --max-per-study 3 \
    --output-dir artifacts/candidate_pool_rich \
    --months 36 --apply-slippage
```

### Portfolio walk-forward validation
```bash
$PYTHON scripts/portfolio_walkforward.py \
    --pool-dir artifacts/candidate_pool_rich \
    --output-dir artifacts/portfolio_wfo \
    --is-fraction 0.70
```

### Validate portfolio (Ensemble PBO + DSR + SPA)
```bash
$PYTHON scripts/validate_portfolio.py \
    --finalists-dir artifacts/candidate_pool_rich \
    --output-dir artifacts/portfolio_rich_validation
```

### Construct portfolio (correlation + selection + optimization)
```bash
$PYTHON scripts/run_portfolio.py \
    --finalists artifacts/discovery_rich_v4/results/finalists.csv \
    --evidence-dir artifacts/candidate_pool_rich \
    --output-dir artifacts/portfolio_rich \
    --target-count 100 --max-avg-corr 0.60 \
    --methods equal shrinkage_kelly \
    --n-trials 2500
```

### Paper trading (multi-strategy)
```bash
$PYTHON scripts/run_paper_portfolio.py \
    --portfolio-dir artifacts/portfolio_rich \
    --exchange alpaca
```

### Replay with slippage
```bash
$PYTHON scripts/replay_with_slippage.py \
    --evidence-dir artifacts/discovery_rich_v4/evidence \
    --output-dir artifacts/slippage_analysis
```

---

## Artifacts

| Directorio | Run | Estado |
|-----------|-----|--------|
| **`artifacts/exhaustive_v9/parquet/`** | **v9 random Parquet** | **Phase 1 (pausado)** |
| `artifacts/candidate_pool_rich/` | Pool con slippage | ✅ Downstream vivo |
| `artifacts/portfolio_rich/` | Portfolio final (25 strat) | ✅ Downstream vivo |
| `artifacts/portfolio_rich_validation/` | Validation results | ✅ Downstream vivo |
| `artifacts/discovery_rich_v4/` | v4 NSGA-II (31 finalists) | Input temporal downstream |
| `artifacts/null_hypothesis*/` | FPR testing | Referencia |

---

## Tests

```bash
$PYTHON -m pytest tests/ -x -q                                    # Todos (1467)
$PYTHON -m pytest tests/optimization/test_rich_archetype.py -v    # Rich archetype
$PYTHON -m pytest tests/indicators/test_ash.py -v                 # ASH indicator
$PYTHON -m pytest tests/ -k "test_max_excluyente" -v              # MAX_EXCL=2
$PYTHON -m pytest tests/risk/test_portfolio_validation.py -v      # Portfolio validation
```
