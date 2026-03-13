"""Check what keys are actually stored in Optuna trial metrics."""
import optuna
import ast
from pathlib import Path

optuna.logging.set_verbosity(optuna.logging.WARNING)

# Pick one study
db = next(Path("artifacts/discovery/studies").glob("*momentum*.db"))
study = optuna.load_study(study_name=db.stem, storage=f"sqlite:///{db}")

# Look at best completed trial with most trades
trials = [t for t in study.trials if t.state.name == "COMPLETE"]

# Find trial with best value (highest Sharpe among non-penalty)
best = None
for t in trials:
    if t.value > -5:  # skip penalty trials
        if best is None or t.value > best.value:
            best = t

if best:
    print(f"Trial {best.number}, value={best.value:.4f}")
    print(f"\nAll user_attrs keys: {list(best.user_attrs.keys())}")
    met = best.user_attrs.get("metrics", {})
    if isinstance(met, str):
        met = ast.literal_eval(met)
    print(f"\nMetrics dict keys: {list(met.keys())}")
    print(f"\nFull metrics:")
    for k, v in sorted(met.items()):
        print(f"  {k}: {v}")
    
    print(f"\nAll params:")
    for k, v in sorted(best.params.items()):
        print(f"  {k}: {v}")
