# Research Scripts — IC Scanning Pipeline

Exploratory analysis scripts for Information Coefficient (IC) scanning.
Output from this pipeline informed the 764K-trial search space narrowing
(commit `5359c0e`).

## Canonical versions

| Script | Purpose |
|--------|---------|
| `step1_ic_scanner_v3.py` | Deep param sweep IC scanner (v3, current) |
| `run_ic_scan_parallel.py` | Parallel orchestrator (launches v3) |
| `step1_ic_cross_asset_v2.py` | Cross-asset IC analysis (v2, current) |

## Superseded versions (kept for reference)

| Script | Superseded by |
|--------|---------------|
| `step1_ic_scanner.py` | `step1_ic_scanner_v3.py` |
| `step1_ic_scanner_v2.py` | `step1_ic_scanner_v3.py` |
| `step1_ic_cross_asset.py` | `step1_ic_cross_asset_v2.py` |

## Pipeline (sequential)

```
step1_ic_scanner_v3 → IC per indicator × param × horizon
step1_ic_ensemble   → combined IC for indicator sets
step2_persistence   → IC persistence over rolling windows
step3_cross_tf      → IC stability across timeframes
analyze_ic_heatmap  → visualization
r1_feature_importance + r1_screening.sh → feature importance scoring
```

## Not integrated into production pipeline

These scripts are standalone research tools. Their output was manually
analyzed and the findings incorporated into `config/archetypes.py`
(per-symbol rich_* variants with narrowed indicator sets).
