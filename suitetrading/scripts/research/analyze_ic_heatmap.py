#!/usr/bin/env python3
"""Analyze IC scan results and generate edge heatmap.

Reads the merged CSV from run_ic_scan_parallel.py and produces:
  1. Heatmap: (indicator × TF × direction) with IC_OOS averaged across assets
  2. Finalists: combinations with IC_OOS > threshold AND FDR significant
  3. Per-asset breakdown for finalists
  4. Multi-horizon decay curves for top indicators

Usage:
    python scripts/research/analyze_ic_heatmap.py \
        --input artifacts/research/ic_scan_crypto_phase1/edge_summary_v3_merged.csv \
        --output-dir artifacts/research/ic_scan_crypto_phase1/analysis
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

FORWARD_HORIZONS = [1, 2, 3, 5, 8, 10, 15, 20]

# Thresholds from DIRECTION.md
IC_THRESHOLD = 0.02       # IC_OOS > 0.02 to consider edge
IC_SOFT_THRESHOLD = 0.01  # IC_OOS > 0.01 for "promising"
FDR_ALPHA = 0.10          # FDR significance level
PCT_IC_POS_MIN = 0.50     # >50% of configs must have IC > 0 in OOS


def apply_fdr(pvals: np.ndarray, alpha: float = 0.05) -> np.ndarray:
    n = len(pvals)
    idx = np.argsort(pvals)
    sorted_p = pvals[idx]
    bh = np.arange(1, n + 1) / n * alpha
    sig = np.zeros(n, dtype=bool)
    max_k = -1
    for k in range(n):
        if sorted_p[k] <= bh[k]:
            max_k = k
    if max_k >= 0:
        sig[idx[: max_k + 1]] = True
    return sig


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Path to edge_summary_v3_merged.csv")
    p.add_argument("--output-dir", default=None)
    p.add_argument("--ic-threshold", type=float, default=IC_THRESHOLD)
    p.add_argument("--fdr-alpha", type=float, default=FDR_ALPHA)
    args = p.parse_args()

    df = pd.read_csv(args.input)
    output_dir = Path(args.output_dir) if args.output_dir else Path(args.input).parent / "analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    ok = df[df["status"] == "ok"].copy()
    print(f"\nTotal measurements: {len(df)} ({len(ok)} valid)")
    print(f"Assets: {sorted(ok['asset'].unique())}")
    print(f"Timeframes: {sorted(ok['timeframe'].unique())}")
    print(f"Indicators: {sorted(ok['indicator'].unique())}")

    # FDR correction on all valid h=1 results
    h1 = ok[ok["horizon"] == 1].copy()
    if len(h1) > 0:
        h1["fdr_sig"] = apply_fdr(h1["ic_val_pvalue"].values, alpha=args.fdr_alpha)
    else:
        print("ERROR: No horizon=1 results found!")
        return

    # ── 1. HEATMAP: (indicator × TF × direction) averaged across assets ──
    print("\n" + "=" * 120)
    print("  EDGE HEATMAP — IC_OOS averaged across assets (horizon=1)")
    print("=" * 120)

    tf_order = {"1w": 0, "1d": 1, "4h": 2, "1h": 3, "15m": 4, "5m": 5}
    report_tfs = sorted(h1["timeframe"].unique(), key=lambda t: tf_order.get(t, 9))

    for tf in report_tfs:
        for direction in ["long", "short"]:
            sub = h1[(h1["timeframe"] == tf) & (h1["direction"] == direction)]
            if sub.empty:
                continue

            ranking = sub.groupby("indicator").agg(
                ic_avg=("ic_val_avg", "mean"),
                ic_std=("ic_val_avg", "std"),
                ic_best=("ic_val_best_config", "mean"),
                hr=("hr_val_avg", "mean"),
                pct_ic_pos=("pct_configs_ic_pos_val", "mean"),
                fdr_n=("fdr_sig", "sum"),
                n_assets=("asset", "nunique"),
                n_pos_assets=("ic_val_avg", lambda x: (x > 0).sum()),
                edge_ret=("edge_return_val_avg", "mean"),
            ).sort_values("ic_avg", ascending=False)

            confirmed = (
                (ranking["ic_avg"] > args.ic_threshold)
                & (ranking["pct_ic_pos"] > PCT_IC_POS_MIN)
                & (ranking["fdr_n"] > 0)
            ).sum()
            promising = (ranking["ic_avg"] > IC_SOFT_THRESHOLD).sum()

            print(f"\n  ── {tf} {direction.upper()} ({confirmed} confirmed, {promising} promising) ──")
            print(f"  {'Indicator':<28s} {'IC_avg':>7s} {'IC_std':>7s} {'IC_best':>8s} {'HR':>6s} "
                  f"{'%IC+':>5s} {'FDR':>5s} {'A+':>4s} {'EdgeRet':>8s} Status")
            print(f"  {'-'*28} {'-'*7} {'-'*7} {'-'*8} {'-'*6} {'-'*5} {'-'*5} {'-'*4} {'-'*8} {'-'*12}")

            for ind, r in ranking.iterrows():
                fdr_str = f"{int(r['fdr_n'])}/{int(r['n_assets'])}"
                apos = f"{int(r['n_pos_assets'])}/{int(r['n_assets'])}"

                if r["ic_avg"] > args.ic_threshold and r["pct_ic_pos"] > PCT_IC_POS_MIN and r["fdr_n"] > 0:
                    status = "** CONFIRMED **"
                elif r["ic_avg"] > args.ic_threshold and r["pct_ic_pos"] > PCT_IC_POS_MIN:
                    status = "robust"
                elif r["ic_avg"] > IC_SOFT_THRESHOLD:
                    status = "promising"
                elif r["ic_avg"] > 0:
                    status = "weak"
                else:
                    status = "."

                print(f"  {ind:<28s} {r['ic_avg']:>7.4f} {r['ic_std']:>7.4f} {r['ic_best']:>8.4f} "
                      f"{r['hr']:>5.1%} {r['pct_ic_pos']:>4.0%} {fdr_str:>5s} {apos:>4s} "
                      f"{r['edge_ret']*100:>7.3f}% {status}")

    # ── 2. FINALISTS ──
    print("\n" + "=" * 120)
    print(f"  FINALISTS — IC_OOS > {args.ic_threshold}, >50% configs IC+, FDR significant")
    print("=" * 120)

    finalists = []
    for tf in report_tfs:
        for direction in ["long", "short"]:
            sub = h1[(h1["timeframe"] == tf) & (h1["direction"] == direction)]
            for ind in sub["indicator"].unique():
                d = sub[sub["indicator"] == ind]
                ic = d["ic_val_avg"].mean()
                ic_std = d["ic_val_avg"].std()
                pct = d["pct_configs_ic_pos_val"].mean()
                fdr = d["fdr_sig"].sum()
                n_a = d["asset"].nunique()
                hr = d["hr_val_avg"].mean()
                edge = d["edge_return_val_avg"].mean()

                if ic > args.ic_threshold and pct > PCT_IC_POS_MIN and fdr > 0:
                    finalists.append({
                        "indicator": ind, "tf": tf, "direction": direction,
                        "ic_avg": round(ic, 5), "ic_std": round(ic_std, 5),
                        "hr": round(hr, 4), "pct_ic_pos": round(pct, 3),
                        "fdr_significant": f"{int(fdr)}/{n_a}",
                        "edge_ret_pct": round(edge * 100, 4),
                    })

    if finalists:
        finalists_df = pd.DataFrame(finalists).sort_values("ic_avg", ascending=False)
        finalists_df.to_csv(output_dir / "finalists.csv", index=False)

        for _, row in finalists_df.iterrows():
            print(f"  {row['indicator']:<28s} {row['tf']} {row['direction']:<6s} "
                  f"IC={row['ic_avg']:.4f} HR={row['hr']:.1%} "
                  f"%IC+={row['pct_ic_pos']:.0%} FDR={row['fdr_significant']} "
                  f"EdgeRet={row['edge_ret_pct']:.3f}%")

        print(f"\n  Total finalists: {len(finalists_df)}")
    else:
        print("  NO FINALISTS FOUND with current thresholds.")
        print(f"  Consider lowering --ic-threshold (current: {args.ic_threshold})")

    # ── 3. PER-ASSET BREAKDOWN for finalists ──
    if finalists:
        print(f"\n  ── PER-ASSET BREAKDOWN (top 10 finalists) ──")
        for _, row in finalists_df.head(10).iterrows():
            sub = h1[
                (h1["indicator"] == row["indicator"])
                & (h1["timeframe"] == row["tf"])
                & (h1["direction"] == row["direction"])
            ]
            assets_str = "  ".join(
                f"{r['asset']}={r['ic_val_avg']:+.4f}"
                for _, r in sub.sort_values("ic_val_avg", ascending=False).iterrows()
            )
            print(f"  {row['indicator']:<20s} {row['tf']} {row['direction']:<5s}: {assets_str}")

    # ── 4. MULTI-HORIZON DECAY for finalists ──
    if finalists:
        print(f"\n  ── MULTI-HORIZON IC DECAY (top finalists) ──")
        for _, row in finalists_df.head(10).iterrows():
            print(f"\n  {row['indicator']} {row['tf']} {row['direction']}:", end="")
            for h in FORWARD_HORIZONS:
                hd = ok[
                    (ok["indicator"] == row["indicator"])
                    & (ok["timeframe"] == row["tf"])
                    & (ok["direction"] == row["direction"])
                    & (ok["horizon"] == h)
                ]
                v = hd["ic_val_avg"].mean() if not hd.empty else 0
                marker = " *" if v > args.ic_threshold else ""
                print(f"  h={h}:{v:+.4f}{marker}", end="")
            print()

    # ── 5. SAVE FULL ANALYSIS ──
    h1.to_csv(output_dir / "h1_full.csv", index=False)
    ok.to_csv(output_dir / "all_horizons.csv", index=False)

    # Summary stats
    summary = {
        "total_measurements": len(df),
        "valid_measurements": len(ok),
        "h1_measurements": len(h1),
        "n_finalists": len(finalists),
        "ic_threshold": args.ic_threshold,
        "fdr_alpha": args.fdr_alpha,
        "assets": sorted(ok["asset"].unique().tolist()),
        "timeframes": sorted(ok["timeframe"].unique().tolist()),
        "indicators": sorted(ok["indicator"].unique().tolist()),
    }
    pd.Series(summary).to_json(output_dir / "summary.json")

    print(f"\n  Analysis saved to: {output_dir}")
    print("=" * 120)


if __name__ == "__main__":
    main()
