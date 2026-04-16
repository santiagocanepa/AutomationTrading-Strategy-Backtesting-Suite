#!/bin/bash
# V9 resume: skip check loop, launch only pending studies directly.
# Use when: SPY+QQQ long/short already done, 16 studies remain.

set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=.venv/bin/python
OUTDIR=artifacts/exhaustive_v9
TRIALS=300000

export PYTHONPATH=src
export PYTHONWARNINGS="ignore::UserWarning,ignore::RuntimeWarning"

PENDING=(
  "AAPL:long" "AAPL:short"
  "NVDA:long" "NVDA:short"
  "TSLA:long" "TSLA:short"
  "IWM:long"  "IWM:short"
  "XLK:long"  "XLK:short"
  "XLE:long"  "XLE:short"
  "GLD:long"  "GLD:short"
  "TLT:long"  "TLT:short"
)
MAX_CONCURRENT=4

echo "V9 RESUME — 16 pending studies (batches of $MAX_CONCURRENT)"
mkdir -p "$OUTDIR/parquet"

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

echo "V9 resume complete!"
