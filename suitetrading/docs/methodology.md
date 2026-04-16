# Methodology — SuiteTrading v2

## Pipeline iterativo (fases secuenciales)

```
Phase 1: Random exhaustive (v9)     ← ACTUAL (pausado, bug MDD fixed)
  run_random_v9.py → Parquet
  300K trials × 20 studies = 6M backtests
  Output: structural data sin sesgo de optimizer

Phase 2: Post-hoc analysis
  pandas sobre Parquet → patrones estructurales
  ¿Qué estados/TFs/risk producen Sharpe > 0?
  Output: top ~1000 configuraciones + search space reducido

Phase 3: WFO + PBO validation (Optuna OK aquí)
  run_discovery.py --sampler nsga2 sobre top ~1000
  Gates: PBO < 0.20, DSR > 0.95, trades ≥ 300
  Output: finalists validados anti-overfit

Phase 4: Portfolio construction
  build_candidate_pool.py → portfolio_walkforward.py →
  validate_portfolio.py → run_portfolio.py
  Output: portfolio diversificado con pesos optimizados

Phase 5: Paper/Live trading
  run_paper_portfolio.py → Alpaca
```

## Reglas no negociables

| # | Regla | Motivo |
|---|-------|--------|
| 1 | **Phase 1: random exhaustivo, NO Optuna** | En ~10^16 combos, optimizer explora 0.000000002% → sesgo local |
| 2 | **Phase 3+: Optuna SÍ** | Validación dirigida sobre espacio ya reducido — no viola regla 1 |
| 3 | **Risk management >> entry signals** | Position management define outcomes. 480 risk combos exhaustivos |
| 4 | **Smoke test antes de runs > 1h** | Bug MDD costó 13h de compute (ver bug_history.md) |
| 5 | **11 indicators en rich_stock** | v5 probó que podar a 7 empeora PBO |
| 6 | **step_factor=4 para indicators, =1 para risk** | Regularización en params continuos; risk ya tiene granularidad diseñada |
| 7 | **No cambiar metodología sin confirmación del usuario** | v7/v8 costaron semanas por desvío no autorizado |

## Relación v9 ↔ Optuna

No son competidores — son fases distintas del mismo pipeline:

- **v9 (Phase 1):** genera dataset random no sesgado para descubrir qué combinaciones estructurales funcionan
- **Optuna (Phase 3):** valida las mejores ~1000 con WFO + PBO — optimización dirigida sobre espacio ya reducido
- **Después de Phase 3:** se vuelve a Optuna para portfolio discovery con el espacio reducido

El ciclo es iterativo: random → analyze → narrow → Optuna → portfolio → live → feedback.

## Risk search spaces

| Space | Keys | Fase | Notas |
|-------|------|------|-------|
| `EXHAUSTIVE` | 3 (stop, TP_R, close) | Phase 1 (v9) | 480 combos, sin pyramid |
| `RICH` | 11 | Phase 3+ | Full risk space con pyramid, sizing, BE |
| `DEFAULT` | 9 | Fallback | |
| `V8` | 8 | Histórico | Iteración v8 |
| `LEAN` | 3 | Smoke tests | |

## Archetype activo

**`rich_stock`** es el archetype genérico con 11 entry indicators. Tras el 764K-trial analysis (commit `5359c0e`), se crearon 10 variantes per-symbol (`rich_spy`, `rich_aapl`, etc.) con subsets basados en feature importance. El discovery actual (`discovery_rich_v4/`) usó `rich_stock` genérico. Las variantes per-symbol están listas para el próximo discovery.

## Validación gates (Phase 3)

| Métrica | Threshold |
|---------|-----------|
| DSR | > 0.95 |
| Sharpe (anualizado) | > 0.80 |
| PBO | < 0.20 |
| MIN_TRADES | ≥ 300 |
| Max DD p95 | < 25% |

## Referencias

- `DIRECTION.md` — reglas absolutas v9
- `RUNBOOK.md` — comandos operativos
- [Research history](history.md) — timeline v1-v9
- [Optimization module](modules/optimization/README.md)
