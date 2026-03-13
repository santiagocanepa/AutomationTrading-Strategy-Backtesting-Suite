# Sprint 4 — Backtesting Core: Technical Specification

> **Propósito**: definir los contratos técnicos del módulo de backtesting de
> SuiteTrading, alineados con el estado real del repo y con los componentes ya
> cerrados de datos, indicadores y risk management.

---

## 1. Relación con la documentación existente

Cada documento cumple una responsabilidad distinta:

- `docs/sprint4_master_plan.md` define alcance, riesgos, dependencias y cierre.
- `docs/sprint4_technical_spec.md` define contratos, módulos, tipos y reglas.
- `docs/sprint4_implementation_guide.md` define el orden real de ejecución.
- `docs/risk_management_framework.md` describe el motor de RM ya implementado.
- `docs/signal_flow.md` describe cómo se forman y fluyen las señales.
- `RESEARCH_PLAN.md` sigue siendo la fuente maestra de Sprint 4.

Este documento no sustituye el plan. Lo operacionaliza.

---

## 2. Baseline actual del paquete

### 2.1. Contratos ya disponibles y obligatorios

#### Datos

En `src/suitetrading/data/` ya existen:

- `ParquetStore`
- `OHLCVResampler`
- `DataValidator`
- `WarmupCalculator`
- normalización canónica de timeframes

Sprint 4 debe consumir OHLCV desde esta capa. No debe inventar loaders paralelos.

#### Indicadores

En `src/suitetrading/indicators/base.py` ya existe:

```python
class Indicator(ABC):
    def compute(self, df: pd.DataFrame, **params) -> pd.Series: ...
    def params_schema(self) -> dict[str, dict]: ...
```

En `src/suitetrading/indicators/signal_combiner.py` ya existe:

```python
def combine_signals(
    signals: dict[str, pd.Series],
    states: dict[str, IndicatorState],
    num_optional_required: int = 1,
) -> pd.Series:
    ...
```

Sprint 4 debe tratar a los indicadores como productores de señales y metadata de
parámetros. No debe mezclar la lógica de señal con la ejecución del backtest.

#### Risk management

En `src/suitetrading/risk/` ya existen:

- `RiskConfig`
- `PositionSnapshot`
- `TransitionResult`
- `PositionStateMachine`
- arquetipos A/B/C/D/E + legacy profile
- `VBTSimulatorAdapter`

Sprint 4 debe reutilizar este paquete como contrato de riesgo; no redefinirlo.

### 2.2. Estado actual del módulo backtesting

#### Ya existe

- `src/suitetrading/backtesting/__init__.py` con intención declarativa.

#### No existe aún

- engine de backtesting,
- generación de grids,
- cálculo de métricas,
- reporting,
- suite `tests/backtesting/`.

---

## 3. Arquitectura conceptual del motor de backtesting

El módulo se descompone en cinco capas:

1. **Dataset Layer**
2. **Signal Preparation Layer**
3. **Execution Layer**
4. **Metrics Layer**
5. **Reporting Layer**

```text
OHLCV from ParquetStore
        │
        ▼
Resample / align / warmup
        │
        ▼
Indicators.compute(...) + combine_signals(...)
        │
        ▼
BacktestEngine
    ├── VectorBT path (A/B/C)
    └── LoopBatch path (D/E or complex runs)
        │
        ▼
MetricsEngine
        │
        ▼
ResultStore (Parquet) + Reporting
```

---

## 4. Estructura objetivo del módulo

```text
src/suitetrading/backtesting/
├── __init__.py
├── engine.py
├── grid.py
├── metrics.py
├── reporting.py
└── _internal/
    ├── checkpoints.py
    ├── datasets.py
    ├── runners.py
    └── schemas.py
```

La superficie pública mínima de Sprint 4 son `engine.py`, `grid.py`,
`metrics.py` y `reporting.py`.

---

## 5. Dataset contract

### 5.1. Dataset bundle

Sprint 4 debe exponer una estructura autocontenida para cada run:

```python
@dataclass
class BacktestDataset:
    exchange: str
    symbol: str
    base_timeframe: str
    ohlcv: pd.DataFrame
    aligned_frames: dict[str, pd.DataFrame]
    metadata: dict[str, Any]
```

### 5.2. Reglas obligatorias

- `ohlcv` debe venir validado y con `DatetimeIndex` ordenado.
- toda señal HTF debe alinearse al timeframe base antes de ejecutarse.
- warmup debe truncarse antes de cualquier simulación.
- no se ejecuta un backtest sobre datos que no pasaron por la capa `data`.

---

## 6. Signal preparation contract

### 6.1. Definición de strategy inputs

El engine debe operar sobre una estructura explícita:

```python
@dataclass
class StrategySignals:
    entry_long: pd.Series
    entry_short: pd.Series
    exit_long: pd.Series | None
    exit_short: pd.Series | None
    trailing_long: pd.Series | None
    trailing_short: pd.Series | None
    indicators_payload: dict[str, pd.Series | pd.DataFrame | float]
```

### 6.2. Estrategia de integración

Sprint 4 debe soportar dos modos:

- **from_signals mode**: para estrategias simples y pruebas rápidas.
- **custom simulator mode**: para arquetipos que dependen del state machine.

### 6.3. Registry mínimo de indicadores

Aunque el registry hoy no exista, Sprint 4 debe definir un contrato mínimo:

```python
INDICATOR_REGISTRY: dict[str, type[Indicator]]
```

Con requirements:

- nombre estable por indicador,
- clase instanciable,
- `params_schema()` obligatoria,
- soporte explícito de direction cuando aplique.

Sin este registry, `grid.py` no puede construir espacios de búsqueda auditables.

---

## 7. Execution contract

### 7.1. Backtest engine interface

```python
class BacktestEngine:
    def run(
        self,
        *,
        dataset: BacktestDataset,
        signals: StrategySignals,
        risk_config: RiskConfig,
        mode: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...
```

### 7.2. Supported execution modes

- `vectorbt_signals`
- `vectorbt_custom`
- `python_loop_batch`

Regla:

- A/B/C deben priorizar `vectorbt_custom` o equivalente compatible.
- D/E pueden bajar a `python_loop_batch` si la lógica secuencial lo exige.

### 7.3. Vectorizability matrix

| Archetype | Sprint 4 path | Notes |
|---|---|---|
| trend_following | vectorizable | candidato principal para benchmark |
| mean_reversion | vectorizable | candidato principal para benchmark |
| mixed | vectorizable con límites | partial TP + trail complejizan estado |
| legacy_firestorm | híbrido | útil para validación comparativa |
| pyramidal | loop batch | sequential adds |
| grid_dca | loop batch | sequential DCA levels |

### 7.4. Bridge con el state machine

Cuando el modo requiera RM completa, el engine debe ejecutar:

```python
result = position_state_machine.evaluate_bar(
    snapshot,
    bar,
    bar_index=i,
    entry_signal=...,
    exit_signal=...,
    trailing_signal=...,
    entry_size=...,
    stop_override=...,
)
```

La ejecución de Sprint 4 no debe duplicar la prioridad de eventos ya definida en
`state_machine.py`.

---

## 8. Grid generation contract

### 8.1. Grid request

```python
@dataclass
class GridRequest:
    symbols: list[str]
    timeframes: list[str]
    indicator_space: dict[str, dict[str, list[Any]]]
    risk_space: dict[str, list[Any]]
    archetypes: list[str]
```

### 8.2. Grid engine interface

```python
class ParameterGridBuilder:
    def build(self, request: GridRequest) -> Iterable[dict[str, Any]]:
        ...

    def chunk(self, combinations: Iterable[dict[str, Any]], chunk_size: int) -> Iterable[list[dict[str, Any]]]:
        ...
```

### 8.3. Reglas obligatorias

- cada combinación debe tener `run_id` estable y reproducible,
- el grid debe poder serializarse antes de ejecutarse,
- el chunking debe ser determinista,
- debe existir estrategia de deduplicación si una combinación reaparece.

---

## 9. Checkpointing and persistence contract

### 9.1. Checkpoint schema

```python
@dataclass
class BacktestCheckpoint:
    run_id: str
    chunk_id: int
    status: str
    started_at: str
    finished_at: str | None
    output_path: str | None
    error: str | None
```

### 9.2. Reglas obligatorias

- resultados parciales se escriben en Parquet, no CSV,
- los checkpoints deben permitir resume idempotente,
- un chunk exitoso no se recalcula salvo invalidación explícita,
- los errores se registran sin abortar necesariamente todo el batch.

---

## 10. Metrics contract

### 10.1. Métricas mínimas requeridas

- Net Profit
- Total Return %
- Sharpe
- Sortino
- Max Drawdown
- Calmar
- Win Rate
- Profit Factor
- Average Trade
- Max Consecutive Losses
- Total Trades

### 10.2. Interface base

```python
class MetricsEngine:
    def compute(self, *, equity_curve: pd.Series, trades: pd.DataFrame, context: dict[str, Any] | None = None) -> dict[str, float | int]:
        ...
```

### 10.3. Result schema

Cada fila de resultado debe incluir al menos:

```python
{
    "run_id": str,
    "symbol": str,
    "timeframe": str,
    "archetype": str,
    "mode": str,
    "net_profit": float,
    "total_return_pct": float,
    "sharpe": float,
    "sortino": float,
    "max_drawdown_pct": float,
    "calmar": float,
    "win_rate": float,
    "profit_factor": float,
    "average_trade": float,
    "max_consecutive_losses": int,
    "total_trades": int,
}
```

---

## 11. Reporting contract

### 11.1. Reporting interface

```python
class ReportingEngine:
    def build_dashboard(self, *, results: pd.DataFrame, output_dir: str) -> dict[str, str]:
        ...
```

### 11.2. Sprint 4 scope

El dashboard de Sprint 4 debe ser exploratorio, no una aplicación full-stack.

Mínimos requeridos:

- distribución de métricas,
- ranking por filtros,
- scatter riesgo/retorno,
- breakdown por símbolo y timeframe,
- export reproducible del artefacto generado.

---

## 12. Validation contract against TradingView

### 12.1. Validation sample

Sprint 4 debe tomar 10 combinaciones históricas como muestra fija.

### 12.2. Métricas comparables

- Net Profit
- Win Rate
- Profit Factor
- Max Drawdown

### 12.3. Tolerance matrix

| Metric | Target tolerance |
|---|---|
| Net Profit | +-5% |
| Win Rate | +-5 pp |
| Profit Factor | +-5% |
| Max Drawdown | +-10% |

### 12.4. Causas esperables de divergencia

- fills gap-aware del engine Python,
- slippage configurable,
- timing distinto de comisiones,
- diferencias entre ejecución TradingView y callback Python,
- diferencias de MTF alignment.

---

## 13. Testing contract

### 13.1. Unit tests obligatorios

#### `test_grid.py`

- construcción de combinaciones,
- chunking determinista,
- ids estables,
- deduplicación.

#### `test_metrics.py`

- fórmulas básicas,
- casos límite,
- equity curve vacía,
- trades vacíos.

#### `test_engine.py`

- run simple con signals mode,
- run con RM integrada,
- persistencia mínima,
- checkpoint básico.

#### `test_reporting.py`

- generación de artefactos,
- validación del esquema esperado,
- manejo de resultados vacíos.

### 13.2. Integration tests mínimos

Debe haber pruebas end-to-end con componentes reales del repo:

- ParquetStore -> indicadores -> combine_signals -> PositionStateMachine -> métricas,
- A/B/C sobre datasets sintéticos o reales controlados,
- pipeline resumible tras checkpoint preexistente.

### 13.3. Bench tests

Debe existir al menos un benchmark reproducible para:

- throughput de backtests simples,
- costo de grids por chunk,
- costo de serialización a Parquet.

---

## 14. Benchmarks objetivos

Sprint 4 debe producir evidencia de performance, no una promesa abstracta.

Metas razonables del sprint:

- camino A/B o B sobre pipeline principal corre a escala útil,
- engine soporta chunking sin explosión de memoria,
- serialización incremental no domina el tiempo total,
- benchmark documentado y repetible.

El claim de `100,000 backtests < 5 minutos` debe tratarse como objetivo a
medir, no como supuesto garantizado ex ante.

---

## 15. Criterio técnico de cierre

Sprint 4 está técnicamente cerrado cuando:

1. El módulo `backtesting/` expone una superficie pública usable.
2. El engine integra datos, señales y RM sin duplicar contratos existentes.
3. Existe estrategia explícita de ejecución para A/B/C y fallback para D/E.
4. El grid masivo soporta chunking, persistencia y resume.
5. Las métricas mínimas están implementadas y exportables.
6. Existe reporting exploratorio sobre resultados persistidos.
7. Existe benchmark reproducible del pipeline.
8. Existe validación documentada contra TradingView sobre la muestra elegida.
