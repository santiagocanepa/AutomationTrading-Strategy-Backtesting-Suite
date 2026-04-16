# Sprint 2 — Indicator Engine: Technical Specification

> **Propósito**: definir contratos, módulos y criterios técnicos del motor de
> indicadores. Las fórmulas matemáticas canónicas siguen viviendo en
> `indicator_catalog.md`; este documento no las duplica, las operacionaliza.

---

## 1. Relación con la documentación existente

Cada documento tiene una responsabilidad distinta:

- `indicator_catalog.md` → fórmula, parámetros, semántica Pine
- `indicator_availability_matrix.md` → backend elegido (TA-Lib, pandas-ta, custom)
- `signal_flow.md` → cómo se combinan señales y filtros
- `sprint2_technical_spec.md` → contratos Python, estructura de módulos y validación

Esto evita repetir la misma información en cuatro lugares.

---

## 2. Baseline actual del paquete

### 2.1. Ya implementado

| Módulo | Estado |
|--------|--------|
| `indicators/base.py` | Contrato base listo |
| `indicators/mtf.py` | Helpers MTF listos |
| `indicators/signal_combiner.py` | Combiner listo |
| `indicators/custom/firestorm.py` | Implementado |
| `indicators/custom/ssl_channel.py` | Implementado |
| `indicators/custom/wavetrend.py` | Implementado |

### 2.2. Todavía faltante

| Área | Estado |
|------|--------|
| `indicators/standard/` | Placeholder |
| registry central | No existe |
| ASH | No existe |
| Squeeze Momentum | No existe |
| Fibonacci MAI | No existe |
| reporte de validación | No existe |

---

## 3. Estructura objetivo

```text
src/suitetrading/indicators/
├── __init__.py
├── base.py
├── mtf.py
├── signal_combiner.py
├── registry.py                  # nuevo
├── custom/
│   ├── __init__.py
│   ├── firestorm.py
│   ├── ssl_channel.py
│   ├── wavetrend.py
│   ├── ash.py                   # nuevo
│   ├── squeeze_momentum.py      # nuevo
│   └── fibonacci_mai.py         # nuevo
└── standard/
    ├── __init__.py
    ├── momentum.py              # MACD, RSI, RSI+BB
    ├── trend.py                 # EMA filter, MTF conditions
    └── volume.py                # VWAP
```

---

## 4. Contrato base

### 4.1. Interface obligatoria

Todo indicador debe implementar:

```python
class Indicator(ABC):
    def compute(self, df: pd.DataFrame, **params) -> pd.Series: ...
    def params_schema(self) -> dict[str, dict]: ...
```

### 4.2. Semántica del output

- El output es siempre `pd.Series[bool]` indexado como el `df` de entrada.
- `True` significa “señal activa en esta barra”.
- Si el indicador es direccional, la dirección se selecciona vía `direction`.

### 4.3. Reglas comunes

1. Validar OHLCV con `_validate_ohlcv()` al inicio.
2. Preservar exactamente el índice del input.
3. Usar `_hold_bars()` solo cuando el Pine lo requiera.
4. No introducir side effects ni escrituras a disco.
5. No depender de un timeframe implícito distinto al informado por parámetros.

---

## 5. Registry canónico

Se define un registry central para desacoplar backtesting/optimización del
nombre de la clase concreta.

### 5.1. Contrato propuesto

```python
INDICATOR_REGISTRY: dict[str, type[Indicator]]
```

### 5.2. Claves canónicas

| Key | Clase objetivo |
|-----|----------------|
| `firestorm` | `Firestorm` |
| `firestorm_tm` | `FirestormTM` |
| `ssl_channel` | `SSLChannel` |
| `ssl_channel_low` | `SSLChannelLow` |
| `wavetrend_reversal` | `WaveTrendReversal` |
| `wavetrend_divergence` | `WaveTrendDivergence` |
| `absolute_strength_histogram` | `AbsoluteStrengthHistogram` |
| `squeeze_momentum` | `SqueezeMomentum` |
| `fibonacci_mai` | `FibonacciMAI` |
| `macd_signal` | `MACDSignal` |
| `rsi_simple` | `RSISimple` |
| `rsi_bollinger` | `RSIBollingerBands` |
| `ema_filter` | `EMAFilter` |
| `mtf_conditions` | `MTFConditions` |
| `vwap` | `VWAPIndicator` |

---

## 6. Contratos de wrappers estándar

### 6.1. `MACDSignal`

- backend: TA-Lib
- input mínimo: `close`
- parámetros: `fast_length`, `slow_length`, `signal_length`, `hold_bars`, `direction`
- señal: crossover/crossunder de MACD vs signal

### 6.2. `RSISimple`

- backend: TA-Lib
- input mínimo: `close`
- parámetros: `length`, `threshold`, `direction`
- semántica: threshold configurable; default alineado con el catálogo Pine

### 6.3. `RSIBollingerBands`

- backend: TA-Lib
- input mínimo: `close`
- pipeline: RSI -> Bollinger sobre RSI -> crossover/crossunder
- parámetros: `rsi_length`, `bb_length`, `bb_mult`, `direction`

### 6.4. `EMAFilter`

- backend: TA-Lib
- input mínimo: `close`
- parámetros: `fast_period`, `slow_period`, `direction`
- salida: máscara estructural booleana, no señal de cruce

### 6.5. `MTFConditions`

- backend: TA-Lib + infraestructura MTF propia
- input mínimo: `close`
- parámetros:
  - `timeframes: list[str]`
  - `lengths: list[int]`
  - `mode: "all" | "any"`
  - `base_tf`
  - `direction`
- requerimiento: todo resampling debe pasar por `indicators.mtf` / `OHLCVResampler`

### 6.6. `VWAPIndicator`

- backend: pandas-ta o implementación mínima propia si el wrapper externo no alcanza
- input mínimo: `high`, `low`, `close`, `volume`
- parámetros: `anchor`, `direction`

---

## 7. Contratos de custom indicators faltantes

### 7.1. `AbsoluteStrengthHistogram`

- archivo: `custom/ash.py`
- backend: NumPy/Numba según necesidad
- parámetros mínimos:
  - `length`
  - `smooth`
  - `mode`
  - `ma_type`
  - `alma_offset`
  - `alma_sigma`
  - `direction`

### 7.2. `SqueezeMomentum`

- archivo: `custom/squeeze_momentum.py`
- backend: NumPy con linreg explícito o implementación optimizada equivalente
- parámetros mínimos:
  - `bb_length`
  - `bb_mult`
  - `kc_length`
  - `kc_mult`
  - `use_true_range`
  - `direction`

### 7.3. `FibonacciMAI`

- archivo: `custom/fibonacci_mai.py`
- backend: NumPy / TA-Lib para medias subyacentes
- parámetros mínimos:
  - `long_period`
  - `cross_period`
  - `short_period`
  - `crossunder_period`
  - `ma_type`
  - `direction`

---

## 8. Contrato MTF

### 8.1. Entrada de timeframe

Todo indicador MTF debe aceptar cualquiera de estas formas:

- canónica: `1m`, `15m`, `1h`, `1d`
- estilo Pine: `1`, `15`, `60`, `D`, `W`, `M`
- selectores: `grafico`, `1 superior`, `2 superiores`

### 8.2. Resolución

La resolución de TF debe pasar por:

```python
resolve_timeframe(current_tf, selection)
normalize_timeframe(tf)
```

### 8.3. Alineación

Si un indicador calcula en TF superior, la serie debe volver al índice base con:

```python
align_to_base(htf_series, base_index)
```

No se permite forward-fill ad hoc duplicado dentro de cada indicador.

---

## 9. Contrato del signal combiner

`combine_signals()` ya existe y se mantiene como combinador base.

### Reglas a preservar

1. Un indicador aporta como máximo **un voto por lado**.
2. `DESACTIVADO` no participa.
3. `EXCLUYENTE` entra por AND.
4. `OPCIONAL` suma 1 si la condición está activa.

### Regla explícita de Sprint 2

No se debe reproducir el bug del Pine donde SSL aporta doble voto opcional en
venta. El motor Python representa intención canónica, no glitches del script UI.

---

## 10. Testing mínimo requerido

### 10.1. Unit tests por indicador

Cada indicador nuevo debe cubrir:

- dtype y shape del output
- validación de columnas faltantes
- paridad contra una implementación manual simple cuando sea posible
- comportamiento `direction="long"` / `"short"`
- hold-bars si aplica

### 10.2. Integration tests

Se requieren tests que prueben:

- un indicador estándar + `signal_combiner`
- un indicador custom + MTF alignment
- catálogo mixto en una combinación de compra representativa

### 10.3. Validación externa

Se define un script reproducible:

```text
scripts/validate_indicators.py
```

Salida esperada:

- `docs/indicator_validation_report.md`
- resumen por indicador: PASS / FAIL / discrepancias abiertas

---

## 11. Benchmarks objetivo

| Métrica | Meta |
|--------|------|
| Catálogo completo sobre 1 año de 1h | < 1 segundo en caso representativo |
| Wrappers estándar | sin overhead material sobre backend subyacente |
| Indicadores custom | vectorizados o Numba cuando haya loops/path dependence |

---

## 12. Criterio técnico de cierre

Sprint 2 queda técnicamente listo cuando:

1. `standard/` deja de ser placeholder.
2. El registry central permite construir indicadores por clave canónica.
3. El catálogo completo está testeado.
4. El reporte de validación existe y no deja discrepancias críticas abiertas.