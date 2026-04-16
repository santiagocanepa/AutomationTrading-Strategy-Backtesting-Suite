# Handoff — V9 Exhaustive Random Search (sin Optuna)

**Fecha:** 2026-04-14
**Contexto:** Sesión de reorientación y optimización. Se eliminó Optuna del loop, se migró a Parquet.

---

## ⚠️ LEE DIRECTION.md PRIMERO

**REGLA ABSOLUTA:** No cambiar metodología sin confirmación explícita del usuario.
El enfoque es **random exhaustivo sin Optuna**. NO usar NSGA-II/TPE. NO usar `run_discovery.py` para exploración.

---

## Qué se hizo en esta sesión

### 1. Reorientación (el problema)
- v7/v8 desviaron la línea de investigación al volver a NSGA-II
- El usuario retomó la dirección correcta: exhaustivo random sin optimizer

### 2. Cambios en el código
| Archivo | Cambio |
|---------|--------|
| `objective.py` | MAX_EXCLUYENTE=2, `_smart_optional_range()`, `EXHAUSTIVE_RISK_SPACE` (480 combos, sin pyramid), `_force_no_pyramid`, risk params sin step_factor |
| `run_random_v9.py` | **NUEVO** — runner sin Optuna: random params → `run_single()` → Parquet |
| `run_exhaustive_v9.sh` | Orquestador: batches de 4, resume por Parquet, progress check |
| `test_rich_archetype.py` | Tests actualizados para MAX_EXCLUYENTE=2 |

### 3. Resultados del smoke test
- 200 trials SPY long: **7.3 trials/sec** (vs 5.8 con Optuna, +26%)
- Output: **73 KB** Parquet (vs ~1 MB SQLite, 14x menor)
- 0 errores, 1467 tests pasando

### 4. Artifacts existentes
| Directorio | Contenido | Estado |
|-----------|-----------|--------|
| `artifacts/exhaustive_v9/studies/` | 5 SQLite DBs viejas (19 GB) | ❌ **BORRAR** — obsoletas, incompatibles con v9 |
| `artifacts/exhaustive_v9/parquet/` | Vacío (solo smoke test en /tmp) | Aquí va el output de v9 |
| `artifacts/discovery_rich_v4/` | 31 finalists NSGA-II (3.1 GB) | ✓ Referencia |

---

## Estado actual (2026-04-16)

### v9 (Phase 1 exploration) — PAUSADO
- Bug MDD fixed en `run_random_v9.py` (ver `bug_history.md`)
- 1.74M trials con MDD broken en `artifacts/exhaustive_v9/` (irrecuperable)
- Relanzamiento pendiente decisión del usuario (opciones A/B/C en `v9_current_state.md` de memoria)
- Smoke test del runner fixed: OK (30 trials, 23 unique MDD values)

### Capa downstream — OPERATIVA
- `artifacts/portfolio_rich/` (Mar 29): 25 strategies, weights optimizados
- Input temporal: `discovery_rich_v4/` (31 finalists, PBO 0.014-0.27)
- Pipeline completo funcional: build_pool → wfo → validate → portfolio → paper
- Paper trading NO invocado aún (`run_paper_portfolio.py` default path pendiente fix)

### Tests — ✅ 1467/1467 pasando (32s)

## Qué debe hacer el siguiente agente

### Opción A — Relanzar v9 desde cero (~57h)
```bash
cd suitetrading
rm -rf artifacts/exhaustive_v9/
nohup bash scripts/run_exhaustive_v9.sh </dev/null > artifacts/exhaustive_v9_master.log 2>&1 &
disown
```

### Opción B — Conservar SPY+QQQ partials, relanzar faltantes (~46h)
Conservar los Parquets existentes (no tienen MDD pero sí structural data).
Relanzar solo los studies faltantes con runner fixed.

### Opción C — Solo SPY+QQQ primero (~11h)
Validar el pipeline fixed antes de comprometer 57h.
```bash
nohup bash scripts/run_exhaustive_v9_resume.sh </dev/null > artifacts/exhaustive_v9_master.log 2>&1 &
disown
```

### Después del relanzamiento — seguir pipeline
1. Phase 2: análisis post-hoc (pandas sobre Parquet, patrones estructurales)
2. Phase 3: WFO + PBO validation (`run_discovery.py` con Optuna sobre top ~1000)
3. Reconstruir portfolio con nuevos finalists
- Tiempo estimado: ~57 horas
- Output: `artifacts/exhaustive_v9/parquet/`
- Disco estimado: ~2.2 GB total

### PASO 2: Monitorear progreso
```bash
# Ver log general
cat suitetrading/artifacts/exhaustive_v9_master.log

# Contar trials completados por study
cd suitetrading && PYTHONPATH=src .venv/bin/python -c "
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

### PASO 3: Análisis post-hoc (cuando Fase 1 termine)
```python
import pandas as pd
from pathlib import Path

# Cargar todos los trials de un study
study_files = sorted(Path('artifacts/exhaustive_v9/parquet').glob('SPY_1h_rich_stock_long_*.parquet'))
df = pd.concat([pd.read_parquet(f) for f in study_files])

# Filtrar viables
viable = df[(df['sharpe'] > 0) & (df['total_trades'] >= 300)]

# Análisis por combinación estructural
# ¿Qué estados (EXCL/OPC/DESACT × 11 indicadores) producen Sharpe > 0 consistentemente?
# ¿Qué risk params (stop, TP, close_pct) dominan en las mejores configuraciones?
# ¿Hay patrones cross-asset?
```

### PASO 4: Validación selectiva (WFO + PBO)
- Tomar top ~1000 configuraciones del análisis post-hoc
- Usar `run_discovery.py` (CON Optuna) para validar solo esas
- Gates: PBO < 0.20, DSR > 0.95

### PASO 5: Extensión a 15min
- Repetir pipeline con TF base = 15min
- `run_random_v9.py --timeframe 15m`
- grafico=15min, 1_superior=1h, 2_superiores=4h

---

## Lo que NO hacer

| Acción prohibida | Por qué |
|-----------------|---------|
| Usar NSGA-II/TPE sin confirmación | Desvía la línea de investigación |
| Usar `run_discovery.py` para exploración | Es para Fase 3 (validación), no exploración |
| Reintroducir Optuna/SQLite en el loop | Overhead innecesario, resuelto con Parquet |
| Activar WFO en fase exploración | Es para Fase 3 sobre top ~1000 |
| Reducir indicadores (< 11) | v5 probó que empeora PBO |
| Usar step_factor=1 para indicadores | Permite overfit de params continuos |
| Aplicar step_factor a risk params | Risk params ya tienen granularidad diseñada |
| Correr > 4 procesos simultáneos | Contención en M4 Pro |
| Cambiar FSM/signal_combiner/data | Estable, no tocar |
| Armar portfolio antes de tener finalists v9 | Prematuro |

---

## Estructura de archivos relevantes

```
suitetrading/
├── DIRECTION.md              ← Leer PRIMERO
├── HANDOFF.md                ← Este archivo
├── scripts/
│   ├── run_random_v9.py      ← Runner v9 (sin Optuna, Parquet)
│   ├── run_exhaustive_v9.sh  ← Orquestador shell
│   └── run_discovery.py      ← Runner Optuna (SOLO para Fase 3)
├── src/suitetrading/
│   ├── optimization/_internal/
│   │   └── objective.py      ← BacktestObjective, EXHAUSTIVE_RISK_SPACE, _smart_optional_range
│   ├── risk/state_machine.py ← FSM (NO TOCAR)
│   ├── indicators/
│   │   ├── signal_combiner.py ← EXCL/OPC/DESACT (NO TOCAR)
│   │   └── custom/           ← 11 indicadores (NO TOCAR)
│   └── config/archetypes.py  ← rich_stock (NO TOCAR)
├── artifacts/
│   ├── exhaustive_v9/
│   │   ├── parquet/          ← Output v9 (Parquet zstd)
│   │   └── studies/          ← SQLite viejas (BORRAR)
│   └── discovery_rich_v4/    ← Referencia (conservar)
└── tests/                    ← 1467 tests, todos pasando
```
