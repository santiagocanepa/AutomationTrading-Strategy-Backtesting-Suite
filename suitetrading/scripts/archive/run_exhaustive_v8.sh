#!/bin/bash
# V8: Refined search with narrowed risk ranges from v7 analysis
#
# Changes from v7:
#   - --risk-space v8: narrowed risk params based on 240K trial analysis
#     stop [0.8, 3.0] (was [2.0, 12.0] → 100% at min)
#     TP [0.10, 0.50] (was [0.25, 1.50] → 95% at min)
#     close_pct [5, 20] (was [10, 45] → 98% at min)
#     pyramid [1, 2] (was [1, 4] → Q4 prefers 1)
#   - step_factor=2 (finer than v7's 4, coarser than v6's 1)
#   - 20K trials (more budget for refined space)
#   - Focus on studies that showed promise in v7 + all longs to retry
#
# v7 results: 8/20 studies produced finalists
#   ⭐ XLK long (PBO=0.049), XLE long (0.187), NVDA short (0.170)
#   ✓  SPY short (0.049), TSLA short (0.238), XLK short (0.202)
#   ✓  IWM short (0.004), XLE short (0.168)
#   All longs except XLK/XLE failed PBO → retry with refined risk

set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=.venv/bin/python
OUTDIR=artifacts/discovery_v8
PYTHONPATH=src
export PYTHONPATH

COMMON="--timeframes 1h --archetypes rich_stock \
  --trials 20000 --top-n 100 \
  --commission 0.0 --exchange alpaca \
  --months 60 --mode fsm --metric sharpe \
  --sampler nsga2 --n-jobs 1 --step-factor 2 \
  --risk-space v8 \
  --pbo-threshold 0.30 --wfo-splits 5 \
  --holdout-months 6 \
  --min-fold-profit 4 --max-degradation 3.0 \
  --seed 42 \
  --output-dir $OUTDIR"

mkdir -p "$OUTDIR"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  V8: Refined Exhaustive — narrowed risk + step_factor=2    ║"
echo "║  10 symbols × 2 directions = 20 studies @ 20K trials each  ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# Batch 1: 5 processes
echo "=== Batch 1/4: SPY QQQ AAPL long+short ==="
for sym in SPY QQQ AAPL; do
  for dir in long short; do
    echo "  Starting $sym $dir..."
    $PYTHON scripts/run_discovery.py --symbols $sym --directions $dir $COMMON \
      > "$OUTDIR/${sym}_${dir}.log" 2>&1 &
  done
done
# Wait but cap at 5 concurrent
wait
echo "=== Batch 1 complete ==="

# Batch 2: 4 processes
echo "=== Batch 2/4: NVDA TSLA long+short ==="
for sym in NVDA TSLA; do
  for dir in long short; do
    echo "  Starting $sym $dir..."
    $PYTHON scripts/run_discovery.py --symbols $sym --directions $dir $COMMON \
      > "$OUTDIR/${sym}_${dir}.log" 2>&1 &
  done
done
wait
echo "=== Batch 2 complete ==="

# Batch 3: 5 processes (IWM + XLK + XLE long, IWM + XLK short)
echo "=== Batch 3/4: IWM XLK XLE ==="
for sym in IWM XLK; do
  for dir in long short; do
    echo "  Starting $sym $dir..."
    $PYTHON scripts/run_discovery.py --symbols $sym --directions $dir $COMMON \
      > "$OUTDIR/${sym}_${dir}.log" 2>&1 &
  done
done
$PYTHON scripts/run_discovery.py --symbols XLE --directions long $COMMON \
  > "$OUTDIR/XLE_long.log" 2>&1 &
wait
$PYTHON scripts/run_discovery.py --symbols XLE --directions short $COMMON \
  > "$OUTDIR/XLE_short.log" 2>&1
echo "=== Batch 3 complete ==="

# Batch 4: 4 processes
echo "=== Batch 4/4: GLD TLT long+short ==="
for sym in GLD TLT; do
  for dir in long short; do
    echo "  Starting $sym $dir..."
    $PYTHON scripts/run_discovery.py --symbols $sym --directions $dir $COMMON \
      > "$OUTDIR/${sym}_${dir}.log" 2>&1 &
  done
done
wait
echo "=== Batch 4 complete ==="

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  V8 complete! Results in $OUTDIR                           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
