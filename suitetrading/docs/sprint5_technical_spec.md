# Sprint 5 — Optimización y Anti-Overfitting: Technical Specification

> **Propósito**: definir los contratos técnicos del módulo de optimización de
> SuiteTrading, alineados con el estado real del repo y con los componentes ya
> cerrados de datos, indicadores, risk management y backtesting.

> **Nota de vigencia (2026-03-12)**: este documento describe la especificación
> técnica que guió Sprint 5. El módulo ya existe en el repo; usarlo como
> referencia contractual, no como checklist pendiente.

---

## 1. Relación con la documentación existente

Cada documento cumple una responsabilidad distinta:

- `docs/sprint5_master_plan.md` define alcance, riesgos, dependencias y cierre.
- `docs/sprint5_technical_spec.md` define contratos, módulos, tipos y reglas.
- `docs/sprint5_implementation_guide.md` define el orden real de ejecución.
- `docs/sprint4_completion_report.md` describe el motor de backtesting ya cerrado.
- `docs/backtesting_benchmarks.md` documenta el baseline de throughput.
- `RESEARCH_PLAN.md` sigue siendo la fuente maestra de Sprint 5.

Este documento no sustituye el plan. Lo operacionaliza.

---

## 2. Baseline actual del paquete

### 2.1. Contratos ya disponibles y obligatorios

#### Backtesting

En `src/suitetrading/backtesting/` ya existen:

```python
class BacktestEngine:
    def run(self, *, dataset, signals, risk_config, mode="auto", context=None) -> dict[str, Any]: ...
    def run_batch(self, configs, *, dataset_loader, signal_builder, risk_builder) -> list[dict]: ...
```

```python
class ParameterGridBuilder:
    def build(self, request: GridRequest) -> list[RunConfig]: ...
    def iter_configs(self, request: GridRequest) -> Iterator[RunConfig]: ...
    def chunk(self, configs, chunk_size) -> list[list[RunConfig]]: ...
    def estimate_size(self, request: GridRequest) -> int: ...

def build_indicator_space_from_registry(indicator_names, resolution=5) -> dict: ...
```

```python
class MetricsEngine:
    def compute(self, *, equity_curve, trades, initial_capital=10_000) -> dict[str, float | int]: ...
```

```python
class CheckpointManager:
    def is_chunk_done(self, chunk_id) -> bool: ...
    def mark_running(self, chunk_id) -> None: ...
    def mark_done(self, chunk_id, output_path) -> None: ...
    def save_chunk_results(self, chunk_id, results_df) -> Path: ...
    def load_all_results(self) -> pd.DataFrame: ...
```

Sprint 5 debe consumir estos contratos. No debe redefinir ejecución, métricas ni
persistencia. El optimizer llama al engine; no lo duplica.

#### Schemas de backtesting

En `src/suitetrading/backtesting/_internal/schemas.py` ya existen:

- `BacktestDataset` — bundle OHLCV con HTF aligned frames.
- `StrategySignals` — señales booleanas pre-computadas.
- `RunConfig` — configuración con `run_id` SHA256 determinístico.
- `GridRequest` — especificación de grid combinatorio.
- `BacktestCheckpoint` — estado de checkpoint por chunk.
- `RESULT_COLUMNS` — 16 columnas del schema Parquet de resultados.

#### Indicadores

En `src/suitetrading/indicators/registry.py` ya existe:

```python
INDICATOR_REGISTRY: dict[str, type[Indicator]]  # 12 indicadores registrados
def get_indicator(name: str) -> Indicator: ...
```

Cada indicador expone `params_schema()` que define el espacio de búsqueda.

#### Risk management

En `src/suitetrading/risk/contracts.py` ya existen:

- `RiskConfig` (Pydantic) con todos los parámetros de RM por arquetipo.
- `SizingConfig`, `ExitPolicyConfig`, `PortfolioControlsConfig`.
- 6 arquetipos: trend_following, mean_reversion, mixed, legacy_firestorm,
  pyramidal, grid_dca.

### 2.2. Estado actual del módulo optimization

- `src/suitetrading/optimization/` existe y expone superficie pública.
- Existen contratos, tests y código para optimizer, WFO, anti-overfit,
  paralelización y extensiones condicionales.

### 2.3. Throughput baseline

- Single-thread: 63.7 backtests/sec (Sprint 4 benchmark, BTCUSDT 1h, 2160 barras).
- Proyección con 14 cores: ~890 bt/sec (target de Sprint 5).
- Target de RESEARCH_PLAN: 100K backtests < 5 minutos.

---

## 3. Arquitectura conceptual del módulo optimization

El módulo se descompone en cinco capas:

1. **Parallel Execution Layer**
2. **Optimization Layer**
3. **Walk-Forward Validation Layer**
4. **Statistical Validation Layer**
5. **Feature Analysis Layer** (condicional)

```text
Search space from INDICATOR_REGISTRY + RiskConfig
        │
        ▼
OptunaOptimizer / DEAPOptimizer
        │ (ParallelExecutor wraps BacktestEngine)
        ▼
Top N candidates (sorted by objective)
        │
        ▼
WalkForwardEngine (IS/OOS splits)
        │
        ▼
OOS equity curves per candidate
        │
        ▼
┌─────────────────────────────────────────┐
│ Anti-Overfit Pipeline                   │
│  1. CSCV → PBO per candidate            │
│  2. DSR → statistical significance      │
│  3. Hansen SPA → superiority vs B&H     │
└─────────────────────────────────────────┘
        │
        ▼
Finalists with evidence
```

---

## 4. Estructura objetivo del módulo

```text
src/suitetrading/optimization/
├── __init__.py
├── optuna_optimizer.py
├── walk_forward.py
├── anti_overfit.py
├── parallel.py
├── feature_importance.py    (condicional)
├── deap_optimizer.py        (condicional)
└── _internal/
    ├── __init__.py
    ├── schemas.py
    └── objective.py
```

La superficie pública mínima de Sprint 5 son `optuna_optimizer.py`,
`walk_forward.py`, `anti_overfit.py` y `parallel.py`.

---

## 5. Parallel execution contract

### 5.1. ParallelExecutor

```python
class ParallelExecutor:
    def __init__(self, max_workers: int | None = None) -> None: ...

    def run_batch(
        self,
        configs: list[RunConfig],
        *,
        dataset_loader: Callable[[RunConfig], BacktestDataset],
        signal_builder: Callable[[RunConfig, BacktestDataset], StrategySignals],
        risk_builder: Callable[[RunConfig], RiskConfig],
    ) -> list[dict[str, Any]]: ...

    def map_backtests(
        self,
        fn: Callable[[RunConfig], dict[str, Any]],
        configs: list[RunConfig],
    ) -> list[dict[str, Any]]: ...
```

### 5.2. Reglas obligatorias

- `max_workers=None` usa `os.cpu_count()`.
- Cada worker recibe inputs serializables — no estado compartido mutable.
- Errores por worker se capturan sin abortar el batch completo.
- Integración transparente: el caller no necesita saber si es paralelo o secuencial.
- Debe soportar un modo `sequential` para debugging.

### 5.3. Integración con CheckpointManager

`ParallelExecutor` debe ser compatible con chunking + checkpointing:

- recibe chunk de `RunConfig`,
- ejecuta en paralelo,
- devuelve resultados al caller que persiste via `CheckpointManager`.

No duplica la lógica de checkpoint dentro del executor.

---

## 6. Objective function contract

### 6.1. ObjectiveResult

```python
@dataclass
class ObjectiveResult:
    run_id: str
    params: dict[str, Any]
    metrics: dict[str, float | int]
    equity_curve: np.ndarray
    trades: list[dict]
    is_error: bool = False
    error_msg: str | None = None
```

### 6.2. BacktestObjective

```python
class BacktestObjective:
    def __init__(
        self,
        *,
        dataset: BacktestDataset,
        archetype: str,
        direction: str = "long",
        metric: str = "sharpe",
        parallel_executor: ParallelExecutor | None = None,
    ) -> None: ...

    def __call__(self, trial: optuna.Trial) -> float: ...

    def build_signals(self, params: dict[str, Any]) -> StrategySignals: ...
    def build_risk_config(self, params: dict[str, Any]) -> RiskConfig: ...
```

### 6.3. Reglas obligatorias

- El objective reutiliza `BacktestEngine.run()` — no implementa su propio loop.
- Los parámetros se sugieren via `trial.suggest_*()` de Optuna.
- El espacio de búsqueda se construye desde `INDICATOR_REGISTRY.params_schema()`
  y `RiskConfig` schema, mapeando tipo→suggest method.
- El metric target es configurable (Sharpe por defecto, pero acepta Sortino,
  Calmar, net_profit, etc.).
- Pruning: se reporta valor intermedio via `trial.report()` en cada WFO fold
  cuando opera dentro del pipeline WFO+Optuna.

---

## 7. Optuna optimizer contract

### 7.1. OptunaOptimizer

```python
class OptunaOptimizer:
    def __init__(
        self,
        *,
        objective: BacktestObjective,
        study_name: str,
        storage: str | None = None,
        sampler: str = "tpe",
        pruner: str = "median",
        direction: str = "maximize",
        n_startup_trials: int = 20,
    ) -> None: ...

    def optimize(
        self,
        n_trials: int,
        timeout: float | None = None,
    ) -> OptimizationResult: ...

    def get_top_n(self, n: int = 50) -> list[dict[str, Any]]: ...
    def get_study(self) -> optuna.Study: ...
```

### 7.2. OptimizationResult

```python
@dataclass
class OptimizationResult:
    study_name: str
    n_trials: int
    n_completed: int
    n_pruned: int
    best_value: float
    best_params: dict[str, Any]
    best_run_id: str
    wall_time_sec: float
    trials_per_sec: float
```

### 7.3. Sampler options

| Sampler | Uso |
|---------|-----|
| `tpe` | Default. Tree-structured Parzen Estimator. Mejor para espacios mixtos. |
| `random` | Baseline de comparación. |
| `nsga2` | Multi-objetivo (maximize Sharpe + minimize MaxDD). |
| `cmaes` | Espacios puramente numéricos. |

### 7.4. Persistence

- `storage=None` → in-memory (para tests).
- `storage="sqlite:///optimization/studies.db"` → persistente en SQLite.
- Resume: si el study_name ya existe en storage, se continúa.

### 7.5. Reglas obligatorias

- Optuna study se crea con `load_if_exists=True` para resume.
- Cada trial persiste su `run_id` como user attribute.
- El sampler y pruner son configurables pero con defaults sensatos.
- `get_top_n()` ordena por objective value y devuelve parámetros completos.

---

## 8. DEAP optimizer contract (condicional)

### 8.1. DEAPOptimizer

```python
class DEAPOptimizer:
    def __init__(
        self,
        *,
        objective: BacktestObjective,
        population_size: int = 100,
        n_generations: int = 50,
        crossover_prob: float = 0.7,
        mutation_prob: float = 0.2,
        objectives: list[str] = ["sharpe", "max_drawdown_pct"],
        directions: list[str] = ["maximize", "minimize"],
    ) -> None: ...

    def evolve(self) -> DEAPResult: ...
    def get_pareto_front(self) -> list[dict[str, Any]]: ...
```

### 8.2. Gate

Este módulo solo se implementa si:

1. `deap` es instable en Python 3.14.
2. Optuna `NSGAIISampler` no cubre el caso multi-objetivo suficientemente.

Si DEAP no es viable, Optuna multi-objetivo cubre este espacio.

---

## 9. Walk-Forward Optimization contract

### 9.1. WFOConfig

```python
@dataclass
class WFOConfig:
    n_splits: int = 5
    is_ratio: float = 0.75
    oos_ratio: float = 0.25
    gap_bars: int = 0
    mode: str = "rolling"       # "rolling" | "anchored"
    min_is_bars: int = 500
    min_oos_bars: int = 100
```

### 9.2. WalkForwardEngine

```python
class WalkForwardEngine:
    def __init__(
        self,
        *,
        config: WFOConfig,
        optimizer: OptunaOptimizer | None = None,
        parallel_executor: ParallelExecutor | None = None,
    ) -> None: ...

    def run(
        self,
        *,
        dataset: BacktestDataset,
        candidate_params: list[dict[str, Any]],
        archetype: str,
        metric: str = "sharpe",
    ) -> WFOResult: ...

    def generate_splits(
        self, n_bars: int,
    ) -> list[tuple[range, range]]: ...
```

### 9.3. WFOResult

```python
@dataclass
class WFOResult:
    config: WFOConfig
    n_candidates: int
    splits: list[dict]             # {is_range, oos_range, best_params, oos_metrics}
    oos_equity_curves: dict[str, np.ndarray]   # run_id → concatenated OOS equity
    oos_metrics: dict[str, dict[str, float]]   # run_id → aggregated OOS metrics
    degradation: dict[str, float]  # run_id → IS_sharpe / OOS_sharpe ratio
```

### 9.4. Modos de operación

#### Rolling

```text
|--IS1--|--OOS1--|
     |--IS2--|--OOS2--|
          |--IS3--|--OOS3--|
```

La ventana IS se desplaza hacia adelante. El tamaño IS es fijo.

#### Anchored

```text
|------IS1------|--OOS1--|
|----------IS2---------|--OOS2--|
|---------------IS3-----------|--OOS3--|
```

El inicio de IS es fijo. El tamaño IS crece en cada fold.

### 9.5. Gap entre IS y OOS

Para evitar data leakage por autocorrelación:

```text
|--IS--|--gap--|--OOS--|
```

`gap_bars` se configura en `WFOConfig`. Default 0, recomendado: longitud del
indicador más lento (ej: EMA 200 = 200 bars).

### 9.6. Reglas obligatorias

- `generate_splits()` es determinista y solo depende de `n_bars` y config.
- En cada fold IS, el optimizer busca los mejores parámetros.
- Los mejores parámetros de IS se aplican al periodo OOS sin re-optimizar.
- Los resultados OOS se concatenan para formar la equity curve real.
- La degradación IS→OOS se calcula para cada candidato.

---

## 10. Anti-overfitting contract

### 10.1. CSCV — Combinatorially Symmetric Cross-Validation

```python
class CSCVValidator:
    def __init__(
        self,
        *,
        n_subsamples: int = 16,
        metric: str = "sharpe",
    ) -> None: ...

    def compute_pbo(
        self,
        equity_curves: dict[str, np.ndarray],
    ) -> CSCVResult: ...
```

```python
@dataclass
class CSCVResult:
    pbo: float                          # Probability of Backtest Overfitting
    n_subsamples: int
    n_combinations: int                 # C(S, S/2)
    omega_values: np.ndarray            # distribution of logits
    is_overfit: bool                    # pbo > 0.50
    details: dict[str, Any] | None = None
```

#### Algoritmo

1. Dividir la equity curve en S sub-muestras temporales.
2. Para cada combinación C(S, S/2):
   a. Asignar mitad a IS, mitad a OOS.
   b. En IS, seleccionar la mejor estrategia por metric.
   c. Calcular el rank relativo de esa misma estrategia en OOS.
   d. Computar ω = logit(rank relativo).
3. PBO = proporción de ω ≤ 0 (estrategia IS-best que underperforms en OOS).

#### Reglas

- S=16 produce C(16,8) = 12,870 combinaciones — suficiente para distribución.
- Entrada: equity curves pre-computadas (no re-ejecuta backtests).
- PBO < 0.50 → pasa el filtro. PBO ≥ 0.50 → overfitting probable.

### 10.2. Deflated Sharpe Ratio

```python
def deflated_sharpe_ratio(
    *,
    observed_sharpe: float,
    n_trials: int,
    sample_length: int,
    skewness: float,
    kurtosis: float,
    sharpe_std: float | None = None,
) -> DSRResult: ...
```

```python
@dataclass
class DSRResult:
    dsr: float                # Probability that observed Sharpe is genuine
    expected_max_sharpe: float  # E[max(SR)] under null
    observed_sharpe: float
    is_significant: bool      # dsr > 0.95
```

#### Fórmula

DSR ajusta el Sharpe observado por:

- Número de trials ejecutados (más trials → más chances de false positive).
- Skewness y kurtosis de los returns (non-normality penalty).
- Longitud de la muestra.

Un DSR > 0.95 indica que el Sharpe observado probablemente no es producto del
azar dado el número de estrategias probadas.

### 10.3. Hansen's Superior Predictive Ability

```python
def hansen_spa_test(
    *,
    strategy_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    n_bootstrap: int = 1000,
    block_size: int | None = None,
) -> SPAResult: ...
```

```python
@dataclass
class SPAResult:
    p_value: float          # H0: strategy ≤ benchmark
    is_superior: bool       # p_value < 0.05
    statistic: float
    benchmark: str
```

#### Reglas

- Benchmark default: buy-and-hold del activo.
- Si `arch` no está disponible, se implementa con bootstrap manual (circular block).
- p_value < 0.05 → la estrategia supera al benchmark con significancia estadística.

### 10.4. Pipeline integrado

```python
class AntiOverfitPipeline:
    def __init__(
        self,
        *,
        cscv_validator: CSCVValidator,
        pbo_threshold: float = 0.50,
        dsr_threshold: float = 0.95,
        spa_significance: float = 0.05,
        benchmark_returns: np.ndarray | None = None,
    ) -> None: ...

    def evaluate(
        self,
        candidates: dict[str, np.ndarray],  # run_id → OOS equity curve
        n_trials: int,
    ) -> AntiOverfitResult: ...
```

```python
@dataclass
class AntiOverfitResult:
    total_candidates: int
    passed_cscv: int
    passed_dsr: int
    passed_spa: int
    finalists: list[str]                 # run_ids that passed all filters
    cscv_results: dict[str, CSCVResult]
    dsr_results: dict[str, DSRResult]
    spa_results: dict[str, SPAResult]
```

---

## 11. Feature importance contract (condicional)

### 11.1. FeatureImportanceEngine

```python
class FeatureImportanceEngine:
    def __init__(
        self,
        *,
        results_df: pd.DataFrame,
        target_metric: str = "sharpe",
    ) -> None: ...

    def compute_shap(self) -> dict[str, float]: ...
    def mutual_information(self) -> pd.DataFrame: ...
    def suggest_space_reduction(self, threshold: float = 0.01) -> dict[str, list]: ...
```

### 11.2. Reglas

- Entrada: DataFrame de resultados completo con run params y métricas.
- Meta-model: XGBoost o LightGBM entrenado sobre params → target_metric.
- SHAP values: importancia de cada parámetro individual.
- Mutual Information: detectar redundancia entre pares de indicadores.
- `suggest_space_reduction()`: retorna un search space reducido eliminando
  parámetros con SHAP < threshold.

### 11.3. Gate

Solo se implementa si `xgboost` (o `lightgbm`) y `shap` son instalables en
Python 3.14.

---

## 12. Validation reference against TradingView

Retomado de Sprint 4 §12 como referencia puntual, no como ground truth rígido.

### 12.1. Validation sample

10 combinaciones representativas:

- 2 archetipos × 5 parameter sets.
- Arquetipos: trend_following + mean_reversion.
- Símbolo fijo: BTCUSDT.
- Período: 3 meses de datos 1h.

### 12.2. Métricas comparables

| Metric | Target tolerance |
|---|---|
| Net Profit | ±5% |
| Win Rate | ±5 pp |
| Profit Factor | ±5% |
| Max Drawdown | ±10% |

### 12.3. Causas esperables de divergencia

- Fills gap-aware del engine Python.
- Slippage configurable (SuiteTrading) vs fijo (TV).
- Timing de comisiones.
- MTF alignment differences.
- Rounding de precios.

### 12.4. Procedimiento

1. Ejecutar las 10 combinaciones en SuiteTrading.
2. Priorizar artifacts internos reproducibles del engine actual.
3. Usar TradingView sólo como spot-check manual si la comparación agrega señal.
4. Comparar métricas con tolerancias cuando el caso realmente sea comparable.
5. Documentar causas de divergencia por combinación y decidir si amerita
    `docs/validation_report.md` o sólo una nota de referencia.

---

## 13. Result schemas

### 13.1. StrategyReport

```python
@dataclass
class StrategyReport:
    run_id: str
    params: dict[str, Any]
    archetype: str
    symbol: str
    timeframe: str
    is_metrics: dict[str, float]
    oos_metrics: dict[str, float]
    degradation_ratio: float
    pbo: float
    dsr: float
    spa_p_value: float
    passed_all_filters: bool
```

### 13.2. PipelineResult

```python
@dataclass
class PipelineResult:
    optimizer_result: OptimizationResult
    wfo_result: WFOResult
    anti_overfit_result: AntiOverfitResult
    finalists: list[StrategyReport]
    total_wall_time_sec: float
```

---

## 14. Testing contract

### 14.1. Unit tests obligatorios

#### `test_parallel.py`

- ejecución paralela produce mismos resultados que secuencial,
- errores por worker no abortan batch,
- respeta max_workers,
- modo sequential funciona.

#### `test_optuna.py`

- objective function devuelve resultado válido,
- study se persiste y resume correctamente,
- pruning funciona (trial reporta + se poda),
- get_top_n devuelve N resultados ordenados,
- sampler options (tpe, random, nsga2).

#### `test_walk_forward.py`

- splits rolling son correctos (sizes, no overlap con gap),
- splits anchored crecen correctamente,
- IS+OOS cubren todos los datos sin huecos,
- gap entre IS y OOS se respeta,
- resultados OOS se concatenan correctamente,
- degradación ratio se calcula bien.

#### `test_anti_overfit.py`

- CSCV con datos sintéticos controlados: PBO ~1.0 para estrategia overfit,
- CSCV con datos sintéticos: PBO ~0.0 para estrategia genuina,
- DSR penaliza correctamente por número de trials,
- DSR es significativo para Sharpe alto con pocos trials,
- Hansen SPA rechaza benchmark-matching strategy,
- Hansen SPA acepta strategy genuinamente superior,
- Pipeline integrado filtra correctamente.

#### `test_schemas.py`

- creación y serialización de todos los dataclasses,
- ObjectiveResult, WFOConfig, CSCVResult, DSRResult, SPAResult,
- OptimizationResult, WFOResult, StrategyReport.

### 14.2. Integration tests mínimos

Debe haber pruebas end-to-end con componentes reales del repo:

- Optuna optimizer → BacktestEngine → MetricsEngine → top N,
- WFO rolling con datos sintéticos → OOS equity curves,
- CSCV sobre OOS curves → PBO calculable,
- pipeline completo: optimize → WFO → anti-overfit → finalists,
- multiprocessing: mismos resultados que single-thread.

### 14.3. Bench tests

Debe existir al menos un benchmark reproducible para:

- throughput paralelo vs single-thread,
- tiempo de CSCV para N candidatas × S sub-muestras,
- convergencia de Optuna: trials vs best_value curve.

---

## 15. Benchmarks objetivos

Sprint 5 debe producir evidencia de performance paralelizada.

Metas razonables:

- multiprocessing (14 cores) alcanza ≥637 bt/sec (10× single-thread),
- 100K backtests en <5 minutos con multiprocessing,
- WFO de 50 estrategias × 5 folds < 30 minutos,
- CSCV de top 50 con S=16 < 1 hora,
- Optuna convergence: 500 trials en < 2 horas.

El claim de `100,000 backtests < 5 minutos` (RESEARCH_PLAN) ahora tiene un path
concreto: 14 cores × 63.7 bt/sec ÷ scheduling overhead.

---

## 16. Dependencias nuevas

### 16.1. Core (obligatorias)

| Paquete | Versión mínima | Uso |
|---------|----------------|-----|
| `optuna` | ≥3.5 | TPE, NSGA-II, pruning, study persistence |
| `scikit-learn` | ≥1.4 | TimeSeriesSplit, métricas auxiliares |

### 16.2. Condicionales (verificar Python 3.14)

| Paquete | Uso | Fallback |
|---------|-----|----------|
| `deap` | NSGA-II nativo | Optuna NSGAIISampler |
| `arch` | Hansen SPA | Bootstrap manual |
| `xgboost` | Meta-model | Omitir feature importance |
| `shap` | Feature importance | Omitir SHAP |

### 16.3. Regla

Verificar instalabilidad de cada paquete condicional en Python 3.14 durante
Fase 0. No commitear scope que dependa de una lib no instalable.

---

## 17. Criterio técnico de cierre

Sprint 5 está técnicamente cerrado cuando:

1. El módulo `optimization/` expone una superficie pública usable.
2. El optimizer integra engine, métricas y persistencia sin duplicar contratos.
3. WFO produce OOS equity curves concatenadas y degradaciones calculadas.
4. CSCV produce PBO por candidato como filtro de overfitting.
5. DSR ajusta por trials y no-normalidad como segundo filtro.
6. Multiprocessing alcanza throughput ≥10× vs single-thread.
7. Existe pipeline E2E: optimize → WFO → CSCV → DSR → finalists.
8. Existe benchmark reproducible del pipeline paralelo.
