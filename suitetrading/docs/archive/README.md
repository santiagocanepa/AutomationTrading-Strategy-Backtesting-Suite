# Archive — Historical Documentation

Sprint documentation and phase reports from the development history.
Kept for reference, not for active use.

## Sprint docs (v1-v7)

| Sprint | Files | Phase |
|--------|-------|-------|
| Sprint 1 | master_plan, technical_spec, implementation_guide, completion_report | Core data + indicators |
| Sprint 2 | master_plan, technical_spec, implementation_guide, go_no_go_checklist | Risk FSM |
| Sprint 3 | master_plan, technical_spec, implementation_guide | Backtesting engine |
| Sprint 4 | master_plan, technical_spec, implementation_guide, completion_report | Optimization |
| Sprint 5 | master_plan, technical_spec, implementation_guide, completion_report | Anti-overfit (CSCV, DSR) |
| Sprint 5.5 | master_plan, technical_spec, implementation_guide, completion_report | Risk archetypes |
| Sprint 6 | master_plan, technical_spec, implementation_guide | Execution bridge |
| Sprint 7 | design | Research pipeline |

## Reports

| File | Content |
|------|---------|
| `backtesting_benchmarks.md` | Engine performance benchmarks |
| `cross_validation_report.md` | Native vs resampled data validation |
| `data_quality_report.md` | Raw data integrity analysis |
| `raw_data_integrity_report.md` | OHLCV gap/duplicate analysis |
| `risk_lab_report.md` | Risk parameter sensitivity analysis |
| `search_space_maturity_matrix.md` | Search space evolution |
| `phase2_discovery_plan.md` | Phase 2 post-hoc analysis plan |

## Research

| File | Content |
|------|---------|
| `research_journal.md` | Chronological research notes |
| `research_methodology.md` | Research principles and methods |
| `research_report.md` | Consolidated research findings |
| `sprint_1a_cross_asset_momentum.md` | Cross-asset momentum exploration |

## Diagnostic scripts (deleted, available in git history)

15 diagnostic scripts removed in commit `bf2a594`. Available via:
```bash
git show bf2a594^:suitetrading/scripts/_check_metrics_keys.py
```
