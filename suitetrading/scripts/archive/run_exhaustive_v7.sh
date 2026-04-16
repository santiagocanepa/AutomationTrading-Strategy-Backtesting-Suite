#!/bin/bash
# V7: Structured exhaustive search per asset × direction
#
# Based on v6 analysis (1.27M trials) + v4 lessons:
#   - NSGA-II multi-objective (Sharpe + trades) — avoids penalty -10 discontinuity
#   - step_factor=4 — acts as implicit regularization (v4's winning formula)
#   - FSM mode — full risk management (TP1, BE, trailing, pyramiding)
#   - num_optional_required capped at 3 (v6: viable mean=1.46, penalized mean=2.89)
#   - 10 symbols × 2 directions = 20 studies
#   - 15K trials per study (50% more than v4's 10K, informed by v6 viability rate)
#   - WFO + PBO validation (not skipped like v6)
#   - 6-month holdout for true OOS validation
#
# Expected runtime: ~20-30h on M4 Pro with batches of 5 processes
# Expected output: artifacts/discovery_v7/
#
# KEY DIFFERENCES from v6:
#   - FSM mode (not simple) — full risk management
#   - step_factor=4 (not 1) — regularization
#   - NSGA-II (not random) — directed search
#   - WFO + PBO enabled — proper validation
#   - Holdout split — true OOS check

set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=.venv/bin/python
OUTDIR=artifacts/discovery_v7

COMMON="--timeframes 1h --archetypes rich_stock \
  --trials 15000 --top-n 100 \
  --commission 0.0 --exchange alpaca \
  --months 60 --mode fsm --metric sharpe \
  --sampler nsga2 --n-jobs 1 --step-factor 4 \
  --pbo-threshold 0.30 --wfo-splits 5 \
  --holdout-months 6 \
  --min-fold-profit 4 --max-degradation 3.0 \
  --seed 42 \
  --output-dir $OUTDIR"

mkdir -p "$OUTDIR"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  V7: Structured Exhaustive Search — NSGA-II + FSM + WFO    ║"
echo "║  10 symbols × 2 directions = 20 studies @ 15K trials each  ║"
echo "║  step_factor=4, holdout=6mo, PBO<0.30                      ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# Batch 1: Large-cap (SPY, QQQ, AAPL) — most liquid, best data quality
echo ""
echo "=== Batch 1/4: SPY QQQ AAPL (long + short) ==="
for sym in SPY QQQ AAPL; do
  for dir in long short; do
    echo "  Starting $sym $dir..."
    $PYTHON scripts/run_discovery.py --symbols $sym --directions $dir $COMMON &
  done
done
wait
echo "=== Batch 1 complete ==="

# Batch 2: Tech + momentum (NVDA, TSLA)
echo ""
echo "=== Batch 2/4: NVDA TSLA (long + short) ==="
for sym in NVDA TSLA; do
  for dir in long short; do
    echo "  Starting $sym $dir..."
    $PYTHON scripts/run_discovery.py --symbols $sym --directions $dir $COMMON &
  done
done
wait
echo "=== Batch 2 complete ==="

# Batch 3: Small-cap + sectors (IWM, XLK, XLE)
echo ""
echo "=== Batch 3/4: IWM XLK XLE (long + short) ==="
# Only 5 processes at a time (SQLite contention)
for sym in IWM XLK; do
  for dir in long short; do
    echo "  Starting $sym $dir..."
    $PYTHON scripts/run_discovery.py --symbols $sym --directions $dir $COMMON &
  done
done
# XLE long as 5th process
echo "  Starting XLE long..."
$PYTHON scripts/run_discovery.py --symbols XLE --directions long $COMMON &
wait

# XLE short separate
echo "  Starting XLE short..."
$PYTHON scripts/run_discovery.py --symbols XLE --directions short $COMMON
echo "=== Batch 3 complete ==="

# Batch 4: Safe-haven (GLD, TLT)
echo ""
echo "=== Batch 4/4: GLD TLT (long + short) ==="
for sym in GLD TLT; do
  for dir in long short; do
    echo "  Starting $sym $dir..."
    $PYTHON scripts/run_discovery.py --symbols $sym --directions $dir $COMMON &
  done
done
wait
echo "=== Batch 4 complete ==="

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  V7 complete! Results in $OUTDIR                           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo "Studies: $(ls $OUTDIR/studies/*.db 2>/dev/null | wc -l)"
echo "Finalists: $(wc -l < $OUTDIR/results/finalists.csv 2>/dev/null || echo 0)"
