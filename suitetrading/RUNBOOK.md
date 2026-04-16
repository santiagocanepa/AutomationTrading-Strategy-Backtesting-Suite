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

## Artifacts

| Directorio | Run | Estado |
|-----------|-----|--------|
| **`artifacts/exhaustive_v9/parquet/`** | **v9 random Parquet** | **🎯 ACTUAL** |
| `artifacts/discovery_rich_v4/` | v4 NSGA-II (31 finalists) | ✓ Referencia |
| Otros (v5-v8, exploration_random) | Históricos | Borrados |

---

## Tests

```bash
$PYTHON -m pytest tests/ -x -q                                    # Todos
$PYTHON -m pytest tests/optimization/test_rich_archetype.py -v    # Rich archetype
$PYTHON -m pytest tests/indicators/test_ash.py -v                 # ASH indicator
$PYTHON -m pytest tests/ -k "test_max_excluyente" -v              # MAX_EXCL=2
```
