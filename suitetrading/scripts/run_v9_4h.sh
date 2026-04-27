#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=.venv/bin/python
OUTDIR=artifacts/exhaustive_v9_4h
TRIALS=100000
MAX_CONCURRENT=4

export PYTHONPATH=src
export PYTHONWARNINGS="ignore::UserWarning,ignore::RuntimeWarning"

SYMBOLS=(SPY QQQ AAPL NVDA TSLA IWM XLK XLE GLD TLT)
DIRS=(long short)

mkdir -p "$OUTDIR/parquet"
pids=()

for sym in "${SYMBOLS[@]}"; do
  for dir in "${DIRS[@]}"; do
    sname="${sym}_4h_rich_stock_${dir}"
    count=$($PYTHON -c "
import pandas as pd; from pathlib import Path
files = sorted(Path('$OUTDIR/parquet').glob('${sname}_*.parquet'))
print(sum(len(pd.read_parquet(f, columns=['trial_id'])) for f in files) if files else 0)
" 2>/dev/null || echo "0")
    if [ "$count" -ge "$TRIALS" ]; then
      continue
    fi
    echo "Starting $sym $dir 4h..."
    $PYTHON scripts/run_random_v9.py \
      --symbol $sym --direction $dir --timeframe 4h \
      --trials $TRIALS --step-factor 4 \
      --output-dir "$OUTDIR" --seed 42 \
      --months 60 --exchange alpaca --commission 0.0 > "$OUTDIR/log_${sname}.log" 2>&1 &
    pids+=($!)
    if [ ${#pids[@]} -ge $MAX_CONCURRENT ]; then
      wait "${pids[@]}"
      pids=()
    fi
  done
done
wait "${pids[@]}"
echo "V9 4h DONE"
