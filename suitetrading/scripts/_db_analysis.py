"""Analyze Optuna study databases for trade counts and Sharpe."""
import optuna
import ast
from pathlib import Path

optuna.logging.set_verbosity(optuna.logging.WARNING)

studies_dir = Path("artifacts/discovery/studies")
for db in sorted(studies_dir.glob("*.db")):
    sname = db.stem
    storage = f"sqlite:///{db}"
    study = optuna.load_study(study_name=sname, storage=storage)

    print(f"\n=== {sname} ===")
    trials = [t for t in study.trials if t.state.name == "COMPLETE"]

    trades_list = []
    sharpe_list = []
    winrate_list = []
    for t in trials:
        met = t.user_attrs.get("metrics", {})
        if isinstance(met, str):
            met = ast.literal_eval(met)
        tc = met.get("total_trades", 0)
        sh = met.get("sharpe", 0)
        wr = met.get("win_rate", 0)
        trades_list.append(tc)
        sharpe_list.append(sh)
        winrate_list.append(wr)

    if not trades_list:
        print("  No completed trials!")
        continue

    above30 = sum(1 for t in trades_list if t >= 30)
    zero_trades = sum(1 for t in trades_list if t == 0)
    print(f"  Total trials: {len(trials)}")
    print(f"  Trades: min={min(trades_list)} max={max(trades_list)} mean={sum(trades_list)/len(trades_list):.0f}")
    print(f"  Zero trades: {zero_trades}/{len(trials)}")
    print(f"  >= 30 trades: {above30}/{len(trials)}")

    # Among those with >=30 trades
    valid = [(s, t, w) for s, t, w in zip(sharpe_list, trades_list, winrate_list) if t >= 30]
    if valid:
        vs = [v[0] for v in valid]
        vt = [v[1] for v in valid]
        vw = [v[2] for v in valid]
        print(f"  Valid (>=30): Sharpe min={min(vs):.3f} max={max(vs):.3f} mean={sum(vs)/len(vs):.3f}")
        print(f"  Valid trades: min={min(vt)} max={max(vt)} mean={sum(vt)/len(vt):.0f}")
        print(f"  Valid winrate: min={min(vw):.3f} max={max(vw):.3f} mean={sum(vw)/len(vw):.3f}")
    else:
        print("  No trials with >= 30 trades!")

    # Show top 5 by Sharpe (non-penalty)
    non_penalty = [(sh, tc, wr, i) for i, (sh, tc, wr) in enumerate(zip(sharpe_list, trades_list, winrate_list)) if tc >= 30]
    non_penalty.sort(key=lambda x: x[0], reverse=True)
    if non_penalty:
        print(f"  Top 5 by Sharpe (>=30 trades):")
        for sh, tc, wr, idx in non_penalty[:5]:
            t = trials[idx]
            met = t.user_attrs.get("metrics", {})
            if isinstance(met, str):
                met = ast.literal_eval(met)
            ret = met.get("total_return", 0)
            mdd = met.get("max_drawdown", 0)
            print(f"    Trial {t.number}: Sharpe={sh:.3f} trades={tc} winrate={wr:.3f} return={ret:.4f} mdd={mdd:.4f}")
