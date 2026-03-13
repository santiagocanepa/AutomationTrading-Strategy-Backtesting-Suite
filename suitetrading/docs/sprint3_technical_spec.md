# Sprint 3 — Risk Management Engine: Technical Specification

> **Propósito**: operacionalizar el motor de gestión de riesgo de SuiteTrading
> como contratos Python concretos, alineados con el estado real del repo y con
> la lógica legacy documentada, pero diseñados para soportar la arquitectura v2.

---

## 1. Relación con la documentación existente

Cada documento cumple una responsabilidad distinta:

- `docs/risk_management_spec.md` define la lógica legacy exacta extraída del Pine.
- `docs/signal_flow.md` define cómo llegan las señales al risk engine y cuál es
  el orden conceptual de evaluación.
- `RISK_MANAGEMENT_RESEARCH.md` amplía la investigación sobre sizing, trailing,
  arquetipos y portfolio risk para la versión v2.
- `docs/sprint3_master_plan.md` define alcance, restricciones, riesgos y entregables.
- `docs/sprint3_technical_spec.md` define contratos, módulos, tipos y reglas de implementación.
- `docs/sprint3_implementation_guide.md` define el orden real de ejecución del sprint.

Este documento no reemplaza la spec legacy. La encapsula dentro de un framework mayor.

---

## 2. Baseline actual del paquete

### 2.1. Contratos ya disponibles y obligatorios

#### Indicadores

En `src/suitetrading/indicators/base.py` ya existe:

```python
class Indicator(ABC):
    def compute(self, df: pd.DataFrame, **params) -> pd.Series: ...
    def params_schema(self) -> dict[str, dict]: ...
```

También existe:

```python
class IndicatorState(StrEnum):
    EXCLUYENTE = "Excluyente"
    OPCIONAL = "Opcional"
    DESACTIVADO = "Desactivado"
```

#### Combinación de señales

En `src/suitetrading/indicators/signal_combiner.py` ya existe:

```python
def combine_signals(
    signals: dict[str, pd.Series],
    states: dict[str, IndicatorState],
    num_optional_required: int = 1,
) -> pd.Series:
    ...
```

Sprint 3 debe consumir señales ya combinadas. No debe duplicar esta lógica.

#### Multi-timeframe

En `src/suitetrading/indicators/mtf.py` y `src/suitetrading/data/resampler.py`
ya existen:

- `resolve_timeframe(...)`
- `resample_ohlcv(...)`
- `align_to_base(...)`
- `OHLCVResampler`

Toda lógica MTF del risk engine debe apoyarse sobre estos contratos.

#### Warmup

`WarmupCalculator` ya calcula warmup por indicador/timeframe. Sprint 3 debe
reutilizarlo y documentar sus límites cuando aparezcan arquetipos multi-stage.

### 2.2. Estado actual del módulo risk

#### Ya existe

- `PositionState` enum en `state_machine.py`

#### No existe aún

- lifecycle state machine ejecutable
- position sizing real
- trailing policies
- portfolio risk manager
- archetypes
- vbt simulator
- test suite de RM

---

## 3. Arquitectura conceptual del motor de riesgo

El motor de riesgo se descompone en seis capas:

1. **Signal Input Layer**
2. **Sizing Layer**
3. **Position State Machine**
4. **Exit Policy Layer**
5. **Archetype Preset Layer**
6. **Portfolio Risk Layer**

```text
Signals already combined
        │
        ▼
PositionSizer ──► initial size / add size
        │
        ▼
PositionStateMachine ──► current state + transition decision
        │
        ▼
ExitPolicy / TrailingPolicy
        │
        ▼
Archetype preset chooses allowed behavior
        │
        ▼
PortfolioRiskManager can approve / throttle / halt
```

---

## 4. State machine contract

### 4.1. Estados concretos

La implementación debe preservar la semántica del enum existente y ampliarlo
solo si es estrictamente necesario.

```python
class PositionState(Enum):
    FLAT = auto()
    OPEN_INITIAL = auto()
    OPEN_BREAKEVEN = auto()
    OPEN_TRAILING = auto()
    OPEN_PYRAMIDED = auto()
    PARTIALLY_CLOSED = auto()
    CLOSED = auto()
```

### 4.2. Decisión sobre `ENTRY` / `EXIT`

El `RESEARCH_PLAN.md` menciona estados de alto nivel como `ENTRY` y `EXIT`.
Para el primer corte de implementación no son obligatorios como estados
persistentes si el simulador usa fills síncronos por barra.

Regla:

- si la simulación sigue siendo bar-based y fill-at-bar, la entrada/salida puede
  modelarse como transición directa;
- si más adelante Sprint 4 o 6 necesita fills asincrónicos, podrán agregarse
  estados `PENDING_ENTRY` / `PENDING_EXIT` sin romper el contrato actual.

### 4.3. Semántica de ejecución: gaps, slippage y fills parciales

`RESEARCH_PLAN.md` T3.2 exige manejar edge cases de gaps, slippage en SL y
fills parciales. Esta sección define la semántica obligatoria para Sprint 3 y
los puntos de extensión explícitos para sprints posteriores.

#### 4.3.1. Modelo de fill por defecto: bar-based síncrono

Sprint 3 opera en modo **fill-at-bar**: toda orden se ejecuta al precio de la
barra actual sin latencia ni rechazo. Este es el modelo estándar para
simulación vectorizada y es suficiente para la validación inicial.

#### 4.3.2. Gaps de precio en stop loss

Cuando el mercado abre más allá del precio de stop (gap overnight, flash crash),
el simulador debe usar la siguiente regla:

- **Long SL**: si `bar.low < stop_price`, el fill price es `min(stop_price,
  bar.open)`. Si `bar.open < stop_price` (gap down), se usa `bar.open`.
- **Short SL**: si `bar.high > stop_price`, el fill price es `max(stop_price,
  bar.open)`. Si `bar.open > stop_price` (gap up), se usa `bar.open`.

Esto modela slippage adverso real: en un gap, el precio de ejecución es peor
que el stop teórico.

> **Estado actual**: la implementación bar-based de Sprint 3 usa `stop_price`
> como fill price. El ajuste a gap-aware fill es un delta de implementación
> acotado que debe completarse antes del cierre del sprint.

#### 4.3.3. Slippage configurable

Más allá de gaps, el simulador debe aceptar un parámetro de slippage
aplicable a toda ejecución:

- `slippage_pct: float = 0.0` en `RiskConfig` o estructura equivalente
- aplicable como ajuste adverso al fill price: `fill *= (1 + slippage_pct/100)`
  para compras, `fill *= (1 - slippage_pct/100)` para ventas

El break-even buffer (`1.0007`) ya modela implícitamente comisiones +
slippage. Ambos mecanismos son complementarios: el buffer protege el BE,
el slippage ajusta el fill general.

#### 4.3.4. Fills parciales

Sprint 3 opera con fills completos: toda orden se ejecuta al 100% en la
barra actual. No existen fills parciales en modo bar-based.

Para compatibilidad futura con NautilusTrader (Sprint 6), el contrato debe
respetar esta invariante:

- `TransitionResult.orders` describe la intención de orden, no la ejecución.
- En modo bar-based, el caller asume fill completo.
- En modo event-driven, un fill parcial puede producir múltiples
  `TransitionResult` por la misma orden, siempre respetando el invariante
  de que `snapshot.quantity` refleja solo la cantidad efectivamente filled.

#### 4.3.5. Prioridad cuando hay exit trigger y fill incompleto

En modo bar-based este caso no existe (todo fill es completo). En modo
event-driven (Sprint 6), la regla es:

- un fill parcial de exit no cancela la prioridad de evaluación;
- si un SL fill parcial deja cantidad remanente, la siguiente barra
  re-evalúa ese remanente con la misma prioridad fija;
- nunca se emite un nuevo entry mientras exista un exit parcial pendiente.

#### 4.3.6. Resumen de modos

| Modo | Sprint | Fill model | Gaps | Slippage | Partial fills |
|------|--------|-----------|------|----------|---------------|
| bar-based | 3, 4 | síncrono, completo | gap-aware SL | configurable | no |
| event-driven | 6 | asincrónico, parcial | real por feed | real por feed | sí |

### 4.4. Eventos de transición

El state machine debe reaccionar a eventos explícitos, no a ifs dispersos.

```python
class TransitionEvent(StrEnum):
    ENTRY_FILLED = "entry_filled"
    PYRAMID_ADD_FILLED = "pyramid_add_filled"
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_1_HIT = "take_profit_1_hit"
    BREAK_EVEN_HIT = "break_even_hit"
    TRAILING_EXIT_HIT = "trailing_exit_hit"
    TIME_EXIT_HIT = "time_exit_hit"
    KILL_SWITCH_TRIGGERED = "kill_switch_triggered"
    FLAT_RESET = "flat_reset"
```

### 4.4. Orden de evaluación por barra

Contrato obligatorio:

1. stop loss
2. partial TP1
3. break-even
4. trailing
5. entry / pyramid

Si varios triggers ocurren en la misma barra, gana el de mayor prioridad.

### 4.5. Requisitos del state machine

Debe cumplir:

- determinismo total
- serialización simple del estado
- trazabilidad de razón de transición
- soporte long y short
- soporte pyramiding y partial close
- soporte break-even y trailing
- independencia del origen de la señal

---

## 5. Tipos y estructuras de estado

### 5.1. Position snapshot

La implementación debe exponer una estructura de estado autocontenida.

```python
@dataclass
class PositionSnapshot:
    state: PositionState
    direction: str
    quantity: float
    avg_entry_price: float
    stop_price: float | None
    break_even_price: float | None
    realized_pnl: float
    unrealized_pnl: float
    pyramid_level: int
    tp1_hit: bool
    tp1_bar_index: int | None
    entry_bar_index: int | None
    last_order_bar_index: int | None
    bars_in_position: int
```

### 5.2. Transition result

```python
@dataclass
class TransitionResult:
    snapshot: PositionSnapshot
    event: str | None
    reason: str | None
    orders: list[dict]
    state_changed: bool
```

### 5.3. Configuración validada

Sprint 3 debe usar Pydantic para validar configuración de RM.

La configuración debe modelar al menos:

- sizing model
- stop model
- trailing model
- partial TP rules
- break-even rules
- pyramiding rules
- time exit rules
- portfolio limits
- archetype preset

La ubicación concreta de los modelos puede resolverse internamente, pero el
contrato público debe poder serializarse a dict sin pérdida de información.

---

## 6. Position sizing contract

### 6.1. Interface base

```python
class PositionSizer(ABC):
    def size(self, *, equity: float, entry_price: float, stop_price: float | None,
             volatility_value: float | None = None,
             strategy_stats: dict | None = None,
             portfolio_state: dict | None = None) -> float:
        ...
```

### 6.2. Implementaciones requeridas

#### Fixed Fractional

- input clave: `% risk per trade`
- requiere stop distance conocida
- uso por defecto en live/conservador

#### Kelly / Fractional Kelly

- input clave: `win_rate`, `payoff_ratio`, `kelly_fraction`
- no puede ser modelo por defecto sin caps explícitos
- debe exponer cap duro de riesgo por trade

#### ATR-based

- input clave: `ATR`, `atr_multiple`, `% risk`
- normaliza exposición por volatilidad

#### Optimal f

- se admite como implementación `experimental`
- no debe ser default ni quedar sin warning

### 6.3. Reglas de seguridad del sizing

Todo sizing debe respetar:

- `max_risk_per_trade`
- `min_position_size`
- `max_position_size`
- `max_leverage`
- `portfolio heat` disponible

El sizing nunca puede aprobar por sí solo una orden que viole límites de portfolio.

---

## 7. Exit policies y trailing contract

### 7.1. Decisión de diseño

`trailing.py` no debe modelar solo trailing stops de precio. Debe modelar una
familia de políticas de salida posteriores a la entrada.

### 7.2. Interface base

```python
class ExitPolicy(ABC):
    def evaluate(self, *, snapshot: PositionSnapshot, bar: dict,
                 indicators: dict[str, pd.Series | float | bool],
                 bar_index: int) -> tuple[bool, float | None, str | None]:
        ...
```

Return contract:

- `should_exit`: bool
- `updated_stop`: nuevo stop si aplica
- `reason`: etiqueta auditable

### 7.3. Políticas requeridas

#### Fixed Trailing Stop

- offset fijo en precio o porcentaje

#### ATR Trailing Stop

- stop móvil = extremo favorable ± `N * ATR`

#### Chandelier Exit

- stop desde highest high / lowest low menos o más `N * ATR`

#### Parabolic SAR Exit

- salida basada en SAR

#### Signal Trailing Exit

- salida disparada por señal externa
- necesaria para encapsular el trailing legacy por SSL LOW

### 7.4. Break-even policy

Break-even no debe quedar hardcodeado en la state machine.

Debe modelarse como regla configurable:

- activación por `R multiple`, porcentaje o evento
- buffer por comisión/slippage
- comportamiento distinto por arquetipo

---

## 8. Legacy profile contract

La lógica actual extraída del Pine debe implementarse como preset nombrado,
por ejemplo `LegacyFirestormProfile`.

### 8.1. Reglas legacy que deben preservarse

- stop inicial basado en Firestorm TM
- spacing de pirámide desde distancia a SL
- weighting Fibonacci para adds
- TP1 parcial basado en condición SSL opuesta + profit distance
- break-even con `breakeven_buffer = 1.0007`
- trailing posterior con SSL LOW
- prioridad de ejecución por barra fija

### 8.2. Reglas legacy que no deben contaminar el framework global

- short side deshabilitada en el Pine actual
- sizing agresivo basado en proximity weighting como default universal
- cualquier bug accidental del script legacy

Regla: el framework soporta long y short aunque el perfil legacy haya nacido long-only.

---

## 9. Archetype contract

### 9.1. Interface base

Cada arquetipo debe ser un preset compuesto, no una reimplementación del core.

```python
class RiskArchetype(ABC):
    name: str

    def build_config(self) -> dict:
        ...
```

### 9.2. Arquetipos requeridos

#### A — Trend Following

- low win rate / high R:R
- wide stop
- trailing agresivo
- pyramiding permitido
- sin TP parcial temprano por defecto

#### B — Mean Reversion

- high win rate / low R:R
- stop tight
- take profit fijo
- sin pyramiding
- break-even temprano opcional
- time exit recomendado

#### C — Mixed

- TP1 parcial
- break-even posterior
- trailing del remanente

#### D — Pyramidal Scaling

- adds estructurados por levels
- group stop o per-level stop configurable

#### E — Grid/DCA

- entries escalonadas
- control explícito de max levels
- drawdown cap obligatorio

### 9.3. Presets y overrides

Cada arquetipo debe ofrecer:

- preset seguro por defecto
- posibilidad de override de sizing / exit / caps
- validación contra combinaciones incoherentes

Ejemplo: Grid no puede usar Kelly como sizing default.

---

## 10. Portfolio risk contract

### 10.1. Responsabilidades

`portfolio.py` debe concentrar controles que operan por encima de una sola posición.

Debe cubrir como mínimo:

- strategy drawdown monitor
- portfolio heat
- exposure caps
- gross / net exposure
- correlation-aware throttling
- kill switch

### 10.2. Interface base

```python
class PortfolioRiskManager:
    def approve_new_risk(self, *, portfolio_state: dict, proposed_risk: dict) -> bool:
        ...

    def evaluate_portfolio(self, *, portfolio_state: dict, returns_frame=None) -> dict:
        ...
```

### 10.3. Robustez y research

Monte Carlo y métricas de robustez deben vivir aquí o en helpers asociados.

Mínimos requeridos:

- reshuffle / bootstrap de trades
- percentiles de max drawdown
- probability of ruin aproximada
- recomendación de `reduce / pause / halt`

---

## 11. Compatibilidad con VectorBT

### 11.1. Decisión de alcance

Sprint 3 debe entregar un prototipo funcional de custom simulator VectorBT que
ejecute al menos los arquetipos A, B y C, según exige `RESEARCH_PLAN.md:422`.
La integración completa con VectorBT PRO (registro como custom simulator,
Numba nativo, optimización masiva) es responsabilidad de Sprint 4.

### 11.2. Objetivo técnico

El core de riesgo debe poder correr en dos modos:

- `python_mode`: legible, testeable, referencia de verdad
- `simulator_mode`: reducible a estructuras simples para callback/loop numba

### 11.3. Restricciones de diseño para no romper Sprint 4

- evitar objetos no serializables como estado crítico
- evitar side effects en la evaluación de barra
- separar config de runtime state
- usar tipos planos cuando sea posible
- documentar qué arquetipos requieren loop secuencial

### 11.4. Resultado esperado en Sprint 3

- `vbt_simulator.py` define adapter contract
- existe una tabla de vectorizabilidad por arquetipo
- el prototipo ejecuta simulaciones básicas de A, B y C (entry/exit/SL) sobre
  arrays numpy, produciendo equity curve y return total
- el prototipo pasa tests que verifican que no pierde dinero sin trades y que
  un trade ganador produce PnL positivo

---

## 11b. Compatibilidad con NautilusTrader

### 11b.1. Decisión de alcance

`RESEARCH_PLAN.md:327` exige compatibilidad con VectorBT **y** NautilusTrader.
Sprint 3 no integra NautilusTrader. Sprint 6 lo hará. Pero Sprint 3 debe dejar
resuelto qué significa "compatible" a nivel técnico para que Sprint 6 no
necesita rediseñar el core.

### 11b.2. Mapeo de estados

NautilusTrader usa un modelo de posición con estados implícitos derivados de
orthogonal concerns (orden, fill, posición). El mapeo mínimo entre
`PositionState` y conceptos NT es:

| PositionState | Concepto NautilusTrader |
|---|---|
| FLAT | No `Position` activa o `Position.is_closed == True` |
| OPEN_INITIAL | `Position.is_open` tras primer `OrderFilled` |
| OPEN_BREAKEVEN | `Position.is_open` + SL movido a entry (no nativo, requiere handler) |
| OPEN_TRAILING | `Position.is_open` + `TrailingStopMarketOrder` activa |
| OPEN_PYRAMIDED | `Position.is_open` tras `OrderFilled` adicional |
| PARTIALLY_CLOSED | `Position.is_open` + qty < initial qty (fill parcial de exit) |
| CLOSED | `Position.is_closed` |

### 11b.3. Mapeo de eventos

| TransitionEvent | Evento NautilusTrader |
|---|---|
| ENTRY_FILLED | `OrderFilled` para orden de entrada |
| PYRAMID_ADD_FILLED | `OrderFilled` para orden adicional |
| STOP_LOSS_HIT | `OrderFilled` para `StopMarketOrder` |
| TAKE_PROFIT_1_HIT | `OrderFilled` parcial de `LimitOrder` de TP |
| BREAK_EVEN_HIT | `OrderFilled` tras modify de SL a BE price |
| TRAILING_EXIT_HIT | `OrderFilled` de `TrailingStopMarketOrder` |
| TIME_EXIT_HIT | `OrderFilled` de market order programada |
| KILL_SWITCH_TRIGGERED | `PositionClosed` forzado por risk manager externo |

### 11b.4. Modelo de fills

NautilusTrader soporta fills parciales nativamente. El state machine de
SuiteTrading debe poder recibir fills parciales sin violar su invariante:

- `snapshot.quantity` siempre refleja qty filled acumulada, no qty pedida
- un fill parcial de entry produce `OPEN_INITIAL` con qty < size pedido
- un fill parcial de exit produce `PARTIALLY_CLOSED`
- la re-evaluación de prioridad en la siguiente barra/evento usa la qty real

En Sprint 3, este soporte es contractual (la interfaz lo admite). En Sprint 6,
será funcional (el event loop lo ejecuta).

### 11b.5. Modelo de órdenes

Cada dict en `TransitionResult.orders` debe poder traducirse a un tipo de
orden NT sin ambigüedad:

| `orders.action` | Orden NautilusTrader |
|---|---|
| `entry` (market) | `MarketOrder` |
| `entry` (limit) | `LimitOrder` |
| `close_all` | `MarketOrder` reduce-only |
| `close_partial` | `MarketOrder` reduce qty parcial |
| `modify_stop` | `ModifyOrder` sobre SL existente |

Sprint 3 emite órdenes como dicts genéricos. Sprint 6 los traduce a tipos NT.

---

## 12. Testing contract

### 12.1. Unit tests obligatorios

#### `test_position_sizing.py`

- fórmulas base
- caps de seguridad
- invalid config
- Kelly fraccional
- ATR-based con edge cases

#### `test_state_machine.py`

- transición por cada evento
- prioridad de eventos por barra
- reset a flat
- pyramiding
- partial TP
- break-even
- trailing
- determinismo

#### `test_trailing.py`

- fixed, ATR, Chandelier, SAR, signal trailing

#### `test_portfolio.py`

- drawdown monitor
- heat limit
- exposure caps
- kill switch

### 12.2. Integration tests mínimos

Debe haber pruebas con señales reales ya implementadas en el repo:

- Firestorm + SSL + legacy profile
- SSL + WaveTrend + mixed archetype
- Firestorm TM + ATR sizing + trend archetype

### 12.3. Property tests deseables

Si el costo es razonable:

- mismos inputs → mismos outputs
- ningún estado inválido tras transición
- ninguna orden aprobada excede caps de portfolio

---

## 13. Benchmarks objetivos

Sprint 3 debe producir un core correcto primero, pero no puede ignorar performance.

Metas razonables:

- state machine por barra sin asignaciones excesivas
- sizing y trailing vectorizables o numba-friendly donde tenga sentido
- simulación del legacy profile sobre 1 año 1h en tiempo práctico para tests

El benchmark de millones de backtests pertenece a Sprint 4.

---

## 14. Criterio técnico de cierre

Sprint 3 está técnicamente cerrado cuando:

1. El framework soporta legacy profile y los cinco arquetipos A, B, C, D y E,
   todos implementados y testeados según exige `RESEARCH_PLAN.md:420`.
2. Los modelos de sizing y exit policies están desacoplados del state machine.
3. El portfolio risk manager puede aprobar, reducir o bloquear nuevas entradas.
4. Existe un prototipo funcional de VectorBT que ejecuta A, B y C, según exige
   `RESEARCH_PLAN.md:422`.
5. La compatibilidad con NautilusTrader está especificada como mapeo de
   estados, eventos, fills y órdenes (sección 11b).
6. La semántica de gaps, slippage y fills parciales está definida
   explícitamente (sección 4.3), con gap-aware SL implementado y slippage
   configurable en `RiskConfig`.
7. La test suite de `tests/risk/` da confianza real, no simbólica.

> **Nota**: criterios anteriores aceptaban D/E como "preferentemente
> implementados" y VBT como "diseño explícito". Fueron endurecidos para
> alineación 1:1 con `RESEARCH_PLAN.md`.