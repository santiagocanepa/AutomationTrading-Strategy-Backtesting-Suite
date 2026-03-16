# Plan Integral: Fase 2 — Escalado de Descubrimiento

## Decisiones Cerradas

| Decisión | Valor | Razón |
|----------|-------|-------|
| Long/Short | Tracks independientes | Risk management no permite flip; cada posición tiene su propio lifecycle FSM |
| MIN_TRADES | 300 | Mínimo estadístico para backtesting significativo en cualquier TF |
| Cross-asset | Asset-specific | Una estrategia BTC NO necesita funcionar en ETH/SOL |
| Search space | NO reducir | Combinaciones interconectadas; explorar exhaustivamente con cómputo |
| Indicadores | NO evaluar aislados | Interconectados; medir entropía del sistema completo |
| Data | Máximo disponible | 7+ años; más datos = mejor signal-to-noise |

## Estado Actual (2026-03-14)

### Infraestructura Funcional
- Motor FSM: 754 tests, pipeline Optuna → WFO → CSCV + DSR
- Data: 7+ años BTCUSDT/ETHUSDT/SOLUSDT 1m en Parquet
- 10+ indicadores (custom Numba + TA-Lib)
- 8 archetypes de risk management
- `RiskConfig.direction` ya soporta `"long"` | `"short"` | `"both"`

### Problema: 0 Finalists en 22,500 Backtests

| Métrica | Resultado | Necesario |
|---------|-----------|-----------|
| IS Sharpe | 0.14-0.19 | — |
| OOS Sharpe | -0.5 a -0.6 | > 0.2 |
| DSR | 0.0000 (todos) | p < 0.05 |
| Degradación IS→OOS | ~10x | < 5x |
| MIN_TRADES actual | 30 | **300** |
| Data usada | 12 meses | **7+ años** |
| Direction | long-only | **long + short** |

---

## Pipeline Mejorado

```
FASE 0: DATA & PREPARACIÓN
    ├─ Expandir a 7+ años (ya descargado, validar)
    ├─ MIN_TRADES = 300
    └─ Habilitar direction long + short como tracks independientes

FASE 1: SCREENING MULTI-PERÍODO
    ├─ P1: 2017-2019, P2: 2020-2022, P3: 2022-2024, P4: 2024-2026
    ├─ Por período: {symbols} × {TFs} × {archetypes} × {directions}
    ├─ 1000+ trials/study
    └─ Asset-specific (no cross-asset validation)

FASE 2: VALIDACIÓN
    ├─ WFO (rolling, IS adaptable, OOS ~25%)
    ├─ CSCV (PBO < 0.50)
    ├─ DSR (p < 0.05)
    └─ Hansen SPA

FASE 3: ANÁLISIS DE INTERCONEXIÓN
    ├─ Entropía del sistema de indicadores
    ├─ SHAP por archetype
    └─ Minimal indicator sets
```

---

## Sprints

### Sprint 7: Data Expansion + Long/Short + MIN_TRADES
- Expandir datos a 7+ años, validar integridad
- Subir MIN_TRADES a 300
- Habilitar backtesting long y short como tracks independientes
- Detalle: ver `docs/sprint7_design.md`

### Sprint 8: Multi-Period Discovery
- Ejecutar descubrimiento exhaustivo en 4 períodos históricos
- 1000 trials/study, search space completo
- Cada direction (long/short) como study separado

### Sprint 9: Interaction Analysis
- SHAP, entropía, redundancia entre indicadores
- Resultados informan si necesitamos nuevos indicadores

### Sprint 10: Validation & Robustness
- Hansen SPA, Monte Carlo, sensibilidad de parámetros

### Sprint 11: Documentation & Insights
- Postmortem, calibración, roadmap a producción

---

## Preguntas Abiertas

1. **Entropía**: ¿Mutual information? ¿Conditional entropy? ¿Transfer entropy? — Diseñar en Sprint 9
2. **OOS threshold**: Si 0 finalists con Sharpe > 0.2, ¿relajar? — Decidir en Sprint 10
3. **Nuevos indicadores**: ¿Squeeze Momentum, Stochastic, Ichimoku? — Solo si SHAP muestra que actuales no alcanzan
4. **Multi-TF**: ¿Single-TF o blend? — Resultados de Sprint 8 informan
5. **Períodos solapados**: ¿Los 4 períodos deberían solaparse para más datos IS? — Evaluar
6. **Production**: ¿NautilusTrader vs Alpaca? — Post-Sprint 11
