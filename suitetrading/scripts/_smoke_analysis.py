"""Quick analysis of smoke test WFO results."""
import json
import statistics
from pathlib import Path

results_dir = Path(__file__).resolve().parent.parent / "artifacts" / "discovery" / "results"

for wf in sorted(results_dir.glob("wfo_*.json")):
    with open(wf) as f:
        data = json.load(f)
    study = data.get("study", wf.stem)
    pbo = data.get("pbo", "N/A")
    n_cand = data.get("n_candidates", 0)
    n_fin = data.get("n_finalists", 0)
    oos = data.get("oos_metrics", {})
    if not oos:
        print(f"{study}: EMPTY OOS. Keys: {list(data.keys())}")
        continue

    sharpes = []
    trades = []
    rets = []
    for cid, met in oos.items():
        sharpes.append(met.get("sharpe", 0))
        trades.append(met.get("total_trades", 0))
        rets.append(met.get("total_return_pct", 0))

    print(f"{study} | PBO={pbo} | cands={n_cand} | fin={n_fin}")
    print(f"  Sharpe:  min={min(sharpes):.3f}  max={max(sharpes):.3f}  mean={statistics.mean(sharpes):.3f}")
    print(f"  Trades:  min={min(trades)}  max={max(trades)}  mean={statistics.mean(trades):.0f}")
    print(f"  Return%: min={min(rets):.1f}  max={max(rets):.1f}  mean={statistics.mean(rets):.1f}")
    print(f"  Positive Sharpe: {sum(1 for s in sharpes if s > 0)}/{len(sharpes)}")
    print()

# Also check Optuna best values
print("=" * 60)
print("OPTUNA BEST VALUES (best_value = IS metric before WFO)")
import pandas as pd
csv = results_dir / "study_summaries.csv"
if csv.exists():
    df = pd.read_csv(csv)
    for _, row in df.iterrows():
        print(f"  {row['study']}: best_value={row['best_value']:.4f}")
