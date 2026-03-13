# Sprint 2 — Indicator Engine: Implementation Guide

> **Propósito**: ordenar la ejecución del sprint para minimizar retrabajo. Este
> documento traduce `sprint2_master_plan.md` y `sprint2_technical_spec.md` a un
> plan de implementación por fases, con dependencias y checklists concretos.

---

## 1. Orden recomendado de trabajo

```text
base.py / mtf.py / signal_combiner.py (baseline existente)
                 │
                 ▼
         registry.py + exports públicos
                 │
        ┌────────┴────────┐
        ▼                 ▼
standard/            custom/ faltantes
        └────────┬────────┘
                 ▼
       tests unitarios + integración
                 ▼
     validate_indicators.py + reporte
```

La razón de este orden es simple:

- primero se estabilizan contratos y superficie pública,
- después se agregan indicadores,
- y recién al final se congela la paridad externa.

---

## 2. Fase 1 — Consolidar contratos y exports

### Objetivo

Dejar el paquete preparado para recibir el resto del catálogo sin cambios de API.

### Tareas

1. Revisar `indicators/__init__.py` y `standard/__init__.py`.
2. Crear `indicators/registry.py`.
3. Normalizar naming canónico por key.
4. Verificar que los custom actuales exporten clases y helpers coherentes.

### Criterio de salida

- existe un registry único
- `from suitetrading.indicators...` tiene una surface clara
- no hay docstrings engañosos sobre indicadores inexistentes

---

## 3. Fase 2 — Implementar wrappers estándar

### Objetivo

Cerrar primero los indicadores con menor incertidumbre matemática y mayor valor
operativo.

### Orden sugerido

1. `RSISimple`
2. `MACDSignal`
3. `EMAFilter`
4. `VWAPIndicator`
5. `RSIBollingerBands`
6. `MTFConditions`

### Razón del orden

- los cuatro primeros validan rápido el contrato base;
- `RSI + BB` y `MTFConditions` ya introducen composición y/o MTF;
- `MTFConditions` debe implementarse cuando el camino estándar ya esté firme.

### Tests mínimos por wrapper

- output booleano
- schema válido
- dirección long/short
- validación de columnas requeridas
- caso manual sencillo de paridad

---

## 4. Fase 3 — Completar custom indicators faltantes

### Objetivo

Cerrar los tres indicadores que hoy bloquean el 15/15 del catálogo.

### Orden sugerido

1. `AbsoluteStrengthHistogram`
2. `SqueezeMomentum`
3. `FibonacciMAI`

### Razón

- ASH es el más “aislado” conceptualmente y sirve para fijar estilo de kernels custom.
- Squeeze Momentum agrega una validación más rica de momentum compuesto.
- Fibonacci MAI puede reutilizar infraestructura de medias ya cerrada en fases previas.

### Recomendación de implementación

- NumPy primero, Numba solo donde el perfil lo justifique.
- no optimizar prematuramente antes de tener tests de paridad.

---

## 5. Fase 4 — Integración del catálogo

### Objetivo

Probar el engine como sistema, no solo como suma de piezas.

### Tareas

1. Extender `tests/indicators/` con una suite por indicador faltante.
2. Agregar tests de integración del catálogo mixto.
3. Verificar que `combine_signals()` funcione con señales estándar y custom.
4. Verificar flujos MTF con `align_to_base()`.

### Casos de integración recomendados

- Firestorm + SSL + MTF Conditions
- MACD Signal + RSI + VWAP
- WaveTrend + ASH + Squeeze Momentum

---

## 6. Fase 5 — Validación externa y reporte

### Objetivo

Cerrar el sprint con evidencia documental de paridad, no solo con pruebas internas.

### Script objetivo

```text
scripts/validate_indicators.py
```

### Inputs mínimos del script

- símbolo
- timeframe
- rango temporal
- indicador o combinación
- fuente de referencia / snapshot

### Output requerido

`docs/indicator_validation_report.md` con:

- metodología
- indicadores evaluados
- parámetros usados
- porcentaje de coincidencia
- discrepancias abiertas y explicación

---

## 7. Estructura sugerida de tests

```text
tests/indicators/
├── test_firestorm.py
├── test_ssl_channel.py
├── test_wavetrend.py
├── test_mtf.py
├── test_ash.py                    # nuevo
├── test_squeeze_momentum.py       # nuevo
├── test_fibonacci_mai.py          # nuevo
├── test_standard_momentum.py      # nuevo
├── test_standard_trend.py         # nuevo
└── test_standard_volume.py        # nuevo
```

---

## 8. Checklist de implementación

### Infraestructura

- [ ] `registry.py` creado
- [ ] exports públicos normalizados
- [ ] `standard/__init__.py` deja de ser placeholder

### Estándar

- [ ] `RSISimple`
- [ ] `MACDSignal`
- [ ] `RSIBollingerBands`
- [ ] `EMAFilter`
- [ ] `MTFConditions`
- [ ] `VWAPIndicator`

### Custom

- [ ] `AbsoluteStrengthHistogram`
- [ ] `SqueezeMomentum`
- [ ] `FibonacciMAI`

### Calidad

- [ ] tests unitarios de todo lo nuevo
- [ ] tests de integración del catálogo
- [ ] benchmark básico del engine
- [ ] `indicator_validation_report.md` generado

---

## 9. Riesgos a controlar

### Riesgo 1 — Duplicación MTF

Si un indicador resamplea localmente, el sprint vuelve a introducir la clase de
problemas que ya se corrigieron en Sprint 1.

**Mitigación**: toda lógica MTF pasa por `indicators.mtf`.

### Riesgo 2 — Wrappers estándar con semántica Pine incompleta

Un wrapper puede calcular bien el valor base pero mal la señal compuesta.

**Mitigación**: validar no solo arrays numéricos, también timestamps de señal.

### Riesgo 3 — Sobreingeniería del registry

No hace falta convertir el sprint en un framework complejo.

**Mitigación**: registry simple `dict[str, type[Indicator]]`.

### Riesgo 4 — Paridad difusa por falta de snapshots reproducibles

Sin fixtures de referencia, cualquier diferencia contra Pine queda ambigua.

**Mitigación**: guardar casos de validación documentados y repetirlos siempre igual.

---

## 10. Cierre del sprint

No crear `sprint2_completion_report.md` hasta que el sprint esté ejecutado.
Generarlo antes introduciría documentación muerta y mezclaría plan con resultado.

El cierre documental correcto de Sprint 2 será:

1. ejecutar implementación,
2. correr tests,
3. generar `indicator_validation_report.md`,
4. recién entonces escribir el completion report.