#!/usr/bin/env python3
"""R1-A Post-screening: Extract feature importance from Optuna studies.

Reads all Optuna SQLite DBs from r1_screening, compiles trial results,
and runs FeatureImportanceEngine (XGBoost + SHAP) to rank the 8 risk
params by importance.

Groups results by: asset_class (stocks/crypto), timeframe, direction.

Usage
-----
python scripts/research/r1_feature_importance.py
python scripts/research/r1_feature_importance.py --studies-dir artifacts/research/r1_screening/studies
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.optimization.feature_importance import FeatureImportanceEngine


STOCK_SYMBOLS = {"SPY", "QQQ", "TLT", "XLE", "GLD", "IWM", "XLK", "AAPL", "NVDA", "TSLA"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="R1-A Feature importance analysis")
    p.add_argument(
        "--studies-dir",
        default=str(ROOT / "artifacts" / "research" / "r1_screening" / "studies"),
    )
    p.add_argument(
        "--output",
        default=str(ROOT / "artifacts" / "research" / "r1_feature_importance.json"),
    )
    p.add_argument("--min-trials", type=int, default=100)
    return p.parse_args()


def load_study_trials(db_path: Path) -> pd.DataFrame | None:
    """Load completed trials from an Optuna SQLite DB."""
    import optuna

    try:
        study = optuna.load_study(
            study_name=db_path.stem,
            storage=f"sqlite:///{db_path}",
        )
    except Exception:
        logger.warning("Failed to load study: {}", db_path.stem)
        return None

    trials = study.trials
    rows = []
    for t in trials:
        if t.state.name != "COMPLETE":
            continue
        row = dict(t.params)
        row["sharpe"] = t.value if t.value is not None else np.nan
        # Extract user attrs for additional metrics
        for k, v in t.user_attrs.items():
            if isinstance(v, (int, float)):
                row[k] = v
        rows.append(row)

    if not rows:
        return None
    return pd.DataFrame(rows)


def parse_study_name(name: str) -> dict:
    """Parse study name into components."""
    parts = name.split("_")
    direction = parts[-1] if parts[-1] in ("long", "short") else "unknown"
    symbol = parts[0]

    # Find timeframe (1h, 4h, 1d, etc.)
    tf = "unknown"
    for p in parts[1:]:
        if p in ("1h", "4h", "1d", "15m"):
            tf = p
            break

    asset_class = "stocks" if symbol in STOCK_SYMBOLS else "crypto"
    return {
        "symbol": symbol,
        "timeframe": tf,
        "direction": direction,
        "asset_class": asset_class,
    }


def main() -> None:
    args = parse_args()
    studies_dir = Path(args.studies_dir)

    if not studies_dir.exists():
        logger.error("Studies dir not found: {}", studies_dir)
        sys.exit(1)

    db_files = sorted(studies_dir.glob("*.db"))
    logger.info("Found {} Optuna study DBs in {}", len(db_files), studies_dir)

    # Compile all trials with metadata
    all_trials: list[pd.DataFrame] = []
    study_meta: list[dict] = []

    for db_path in db_files:
        df = load_study_trials(db_path)
        if df is None or len(df) < args.min_trials:
            continue
        meta = parse_study_name(db_path.stem)
        for col in meta:
            df[col] = meta[col]
        all_trials.append(df)
        study_meta.append({**meta, "n_trials": len(df), "study": db_path.stem})

    if not all_trials:
        logger.error("No studies with sufficient trials found")
        sys.exit(1)

    combined = pd.concat(all_trials, ignore_index=True)
    logger.info(
        "Combined {} trials from {} studies",
        len(combined), len(all_trials),
    )

    # Identify risk params (columns present in most trials that look like risk params)
    risk_param_prefixes = ("stop__", "sizing__", "partial_tp__", "break_even__", "pyramid__", "time_exit__")
    risk_cols = [c for c in combined.columns if any(c.startswith(p) for p in risk_param_prefixes)]
    logger.info("Risk params found: {}", risk_cols)

    # Run feature importance by grouping
    results: dict[str, dict] = {}
    engine = FeatureImportanceEngine(metric="sharpe")

    # 1. Global importance (all studies)
    global_df = combined[risk_cols + ["sharpe"]].dropna()
    if len(global_df) > 100:
        imp = engine.fit(global_df)
        results["global"] = {
            "importances": imp,
            "n_trials": len(global_df),
            "ranking": [k for k, _ in sorted(imp.items(), key=lambda x: -x[1])],
        }
        logger.info("Global ranking: {}", results["global"]["ranking"])

    # 2. By asset class
    for ac in ["stocks", "crypto"]:
        subset = combined[combined["asset_class"] == ac]
        df_ac = subset[risk_cols + ["sharpe"]].dropna()
        if len(df_ac) > 100:
            imp = engine.fit(df_ac)
            results[f"asset_class_{ac}"] = {
                "importances": imp,
                "n_trials": len(df_ac),
                "ranking": [k for k, _ in sorted(imp.items(), key=lambda x: -x[1])],
            }

    # 3. By direction
    for direction in ["long", "short"]:
        subset = combined[combined["direction"] == direction]
        df_dir = subset[risk_cols + ["sharpe"]].dropna()
        if len(df_dir) > 100:
            imp = engine.fit(df_dir)
            results[f"direction_{direction}"] = {
                "importances": imp,
                "n_trials": len(df_dir),
                "ranking": [k for k, _ in sorted(imp.items(), key=lambda x: -x[1])],
            }

    # 4. By timeframe
    for tf in ["1h", "4h"]:
        subset = combined[combined["timeframe"] == tf]
        df_tf = subset[risk_cols + ["sharpe"]].dropna()
        if len(df_tf) > 100:
            imp = engine.fit(df_tf)
            results[f"timeframe_{tf}"] = {
                "importances": imp,
                "n_trials": len(df_tf),
                "ranking": [k for k, _ in sorted(imp.items(), key=lambda x: -x[1])],
            }

    # Generate reduced space recommendation
    if "global" in results:
        top_params = results["global"]["ranking"][:6]  # Top 6
        logger.info("Recommended reduced space (top 6): {}", top_params)
        results["reduced_space_recommendation"] = top_params

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2, default=str))
    logger.info("Saved feature importance to {}", output_path)

    # Print summary
    print("\n" + "=" * 70)
    print("  R1-A FEATURE IMPORTANCE RESULTS")
    print("=" * 70)
    for group, data in results.items():
        if group == "reduced_space_recommendation":
            continue
        if "ranking" in data:
            print(f"\n  {group} ({data['n_trials']} trials):")
            for i, param in enumerate(data["ranking"], 1):
                score = data["importances"][param]
                bar = "█" * int(score * 200)
                print(f"    {i:>2d}. {param:<35s} {score:.4f} {bar}")

    if "reduced_space_recommendation" in results:
        print(f"\n  RECOMMENDATION: Use top 6 params for R1-B:")
        for p in results["reduced_space_recommendation"]:
            print(f"    → {p}")
    print("=" * 70)


if __name__ == "__main__":
    main()
