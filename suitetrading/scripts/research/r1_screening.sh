#!/bin/bash
# R1-A: Risk Space Screening — FULL 8-param risk space, 500 trials per study
# Launches 9 parallel processes (one per symbol) to maximize M4 Pro utilization.
#
# Usage: bash scripts/research/r1_screening.sh
#
# Total: 9 symbols × 2 TFs × 5 archetypes × 2 directions = 180 studies

set -euo pipefail
cd "$(dirname "$0")/../.."

ARCHETYPES="roc_fullrisk_pyr divergence_fullrisk_pyr macd_regime_fullrisk_pyr roc_regime_fullrisk_pyr ssl_fullrisk_pyr"
OUTPUT_DIR="artifacts/research/r1_screening"
TRIALS=500
MONTHS=66
HOLDOUT=6
LOG_DIR="/tmp/r1_screening"
mkdir -p "$LOG_DIR"

echo "=== R1-A: Risk Space Screening ==="
echo "FULL risk space (8 params for _fullrisk_pyr archetypes)"
echo "500 trials × 180 studies = 90,000 backtests"
echo "Launching 9 parallel processes..."
echo ""

PIDS=()

# Stocks (6 symbols, exchange=alpaca, commission=0.0)
for SYM in SPY QQQ TLT XLE GLD IWM; do
    echo "Launching $SYM (alpaca)..."
    FRED_API_KEY=fc3107c52733b4427e3fb370390b9e43 \
    nohup python scripts/run_discovery.py \
        --symbols "$SYM" \
        --timeframes 4h 1h \
        --archetypes $ARCHETYPES \
        --directions long short \
        --trials $TRIALS --top-n 30 \
        --months $MONTHS --holdout-months $HOLDOUT \
        --commission 0.0 \
        --exchange alpaca \
        --wfo-splits 5 --min-fold-profit 2 \
        --pbo-threshold 0.50 \
        --macro-enrich \
        --output-dir "$OUTPUT_DIR" \
        --seed 42 > "$LOG_DIR/${SYM}.log" 2>&1 &
    PIDS+=($!)
done

# Crypto (3 symbols, exchange=binance, commission=0.04)
for SYM in BTCUSDT ETHUSDT SOLUSDT; do
    echo "Launching $SYM (binance)..."
    nohup python scripts/run_discovery.py \
        --symbols "$SYM" \
        --timeframes 4h 1h \
        --archetypes $ARCHETYPES \
        --directions long short \
        --trials $TRIALS --top-n 30 \
        --months $MONTHS --holdout-months $HOLDOUT \
        --commission 0.04 \
        --exchange binance \
        --wfo-splits 5 --min-fold-profit 2 \
        --pbo-threshold 0.50 \
        --output-dir "$OUTPUT_DIR" \
        --seed 42 > "$LOG_DIR/${SYM}.log" 2>&1 &
    PIDS+=($!)
done

echo ""
echo "All 9 processes launched. PIDs: ${PIDS[*]}"
echo "Logs in: $LOG_DIR/"
echo ""
echo "Monitor progress:"
echo "  watch 'ls $OUTPUT_DIR/results/wfo_*.json 2>/dev/null | wc -l'"
echo ""

# Wait for all
for pid in "${PIDS[@]}"; do
    wait "$pid" || echo "Process $pid exited with error"
done

DONE=$(ls "$OUTPUT_DIR/results/wfo_"*.json 2>/dev/null | wc -l)
echo ""
echo "=== R1-A COMPLETE: $DONE/180 studies ==="
