#!/bin/bash
# V9: Exhaustive random search — NO Optuna, NO SQLite, Parquet output
#
# ⚠️  METHODOLOGY: Random sampling WITHOUT optimizer.
#     DO NOT change this to use NSGA-II/TPE without explicit user confirmation.
#     See DIRECTION.md for full rationale.
#
# Disk: ~50-100 MB per study in Parquet (vs 4.3 GB in SQLite)
# Total: ~1-2 GB for 20 studies (vs 86 GB with SQLite)

set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=.venv/bin/python
OUTDIR=artifacts/exhaustive_v9
TRIALS=300000

export PYTHONPATH=src
export PYTHONWARNINGS="ignore::UserWarning,ignore::RuntimeWarning"

SYMBOLS=(SPY QQQ AAPL NVDA TSLA IWM XLK XLE GLD TLT)
DIRS=(long short)
MAX_CONCURRENT=4

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  V9: Random Search — NO Optuna — Parquet output             ║"
echo "║  10 symbols × 2 directions = 20 studies @ ${TRIALS} trials  ║"
echo "║  Max $MAX_CONCURRENT concurrent processes                   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

mkdir -p "$OUTDIR/parquet"

# ── Check existing progress ──────────────────────────────────────
echo "Checking existing studies..."
PENDING=()
for sym in "${SYMBOLS[@]}"; do
  for dir in "${DIRS[@]}"; do
    sname="${sym}_1h_rich_stock_${dir}"
    count=$($PYTHON -c "
import pandas as pd; from pathlib import Path
files = sorted(Path('$OUTDIR/parquet').glob('${sname}_*.parquet'))
print(sum(len(pd.read_parquet(f, columns=['trial_id'])) for f in files) if files else 0)
" 2>/dev/null || echo "0")
    if [ "$count" -ge "$TRIALS" ]; then
      echo "  ✓ $sym $dir: $count trials (done)"
    else
      echo "  ○ $sym $dir: $count/$TRIALS"
      PENDING+=("$sym:$dir")
    fi
  done
done

if [ ${#PENDING[@]} -eq 0 ]; then
  echo "All 20 studies complete!"
  exit 0
fi

echo ""
echo "${#PENDING[@]} studies pending. Launching in batches of $MAX_CONCURRENT..."
echo ""

# ── Run pending studies ──────────────────────────────────────────
pids=()
batch_num=1

for entry in "${PENDING[@]}"; do
  sym="${entry%%:*}"
  dir="${entry##*:}"

  echo "  Starting $sym $dir..."
  $PYTHON scripts/run_random_v9.py \
    --symbol $sym --direction $dir --timeframe 1h \
    --trials $TRIALS --step-factor 4 \
    --output-dir "$OUTDIR" --seed 42 \
    --months 60 --exchange alpaca --commission 0.0 &
  pids+=($!)

  if [ ${#pids[@]} -ge $MAX_CONCURRENT ]; then
    echo "  [Batch $batch_num: waiting for ${#pids[@]} processes...]"
    wait "${pids[@]}"
    echo "  [Batch $batch_num complete]"
    pids=()
    batch_num=$((batch_num + 1))
  fi
done

if [ ${#pids[@]} -gt 0 ]; then
  echo "  [Batch $batch_num: waiting for ${#pids[@]} processes...]"
  wait "${pids[@]}"
  echo "  [Batch $batch_num complete]"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  V9 complete!                                               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo "Studies: $(ls $OUTDIR/parquet/*.parquet 2>/dev/null | wc -l) parquet files"
echo "Disk: $(du -sh $OUTDIR/parquet | cut -f1)"
