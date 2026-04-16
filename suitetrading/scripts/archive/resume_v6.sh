#!/bin/bash
# Resume v6 random exploration — max 5 concurrent processes
# Usage: ./scripts/resume_v6.sh

set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=.venv/bin/python
OUTDIR=artifacts/exploration_random
COMMON="--timeframes 1h --archetypes rich_stock --trials 200000 --top-n 1000 \
  --commission 0.0 --exchange alpaca --months 60 --mode simple --metric sharpe \
  --sampler random --n-jobs 1 --step-factor 1 --skip-wfo --seed 42 \
  --output-dir $OUTDIR"

echo "=== Batch 1/3: Shorts for SPY QQQ IWM NVDA + continue AAPL ==="
for sym in SPY QQQ IWM NVDA AAPL; do
  echo "Starting $sym short..."
  $PYTHON scripts/run_discovery.py --symbols $sym --directions short --resume $COMMON &
done
wait
echo "=== Batch 1 complete ==="

echo "=== Batch 2/3: TSLA GLD XLK (long + short) ==="
for sym in TSLA GLD XLK; do
  for dir in long short; do
    echo "Starting $sym $dir..."
    $PYTHON scripts/run_discovery.py --symbols $sym --directions $dir $COMMON &
  done
done
wait
echo "=== Batch 2 complete ==="

echo "=== Batch 3/3: XLE TLT (long + short) ==="
for sym in XLE TLT; do
  for dir in long short; do
    echo "Starting $sym $dir..."
    $PYTHON scripts/run_discovery.py --symbols $sym --directions $dir $COMMON &
  done
done
wait
echo "=== All batches complete ==="
echo "Total studies: $(ls $OUTDIR/studies/*.db 2>/dev/null | wc -l)"
