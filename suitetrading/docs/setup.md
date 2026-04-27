# Setup — SuiteTrading v2

## Requirements

- **Python 3.11+** (tested 3.11–3.14)
- **TA-Lib C library**
  ```bash
  # macOS
  brew install ta-lib
  # Ubuntu
  sudo apt-get install libta-lib-dev
  ```

## Installation

```bash
cd suitetrading
python -m venv .venv
source .venv/bin/activate

# Core + dev + data + optimization
pip install -e ".[dev,data,optimization]"

# Missing from pyproject.toml (manual install required)
pip install yfinance fredapi
```

## Verify

```bash
# Tests (1,468 passed in ~25 s)
pytest -x -q

# Registry check
PYTHONPATH=src python -c "
from suitetrading.indicators.registry import INDICATOR_REGISTRY
from suitetrading.risk.archetypes import ARCHETYPE_REGISTRY
print(f'Indicators: {len(INDICATOR_REGISTRY)}')   # 38
print(f'Archetypes: {len(ARCHETYPE_REGISTRY)}')    # 164
"
```

## Environment variables

```bash
# Required for Alpaca data download + paper trading
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...

# Optional (for FRED macro data)
FRED_API_KEY=...
```

See `.env.example` for template.

## First run

```bash
# 1. Download stock data (Alpaca, ~5 years 1m bars)
python scripts/download_data.py \
    --symbols SPY QQQ IWM AAPL NVDA TSLA GLD XLK XLE TLT \
    --timeframes 1m --exchange alpaca

# 2. Validate data integrity
python scripts/audit_raw_data.py

# 3. Smoke test v9 runner (30 trials, ~10 sec)
PYTHONPATH=src python scripts/run_random_v9.py \
    --symbol SPY --direction long --timeframe 1h \
    --trials 30 --step-factor 4 \
    --output-dir /tmp/v9_smoke --seed 42 \
    --months 60 --exchange alpaca --commission 0.0

# 4. Inspect Parquet output (verify MDD is non-zero)
PYTHONPATH=src python -c "
import pandas as pd; from pathlib import Path
files = sorted(Path('/tmp/v9_smoke/parquet').glob('*.parquet'))
df = pd.concat([pd.read_parquet(f) for f in files])
print(df[['sharpe','max_drawdown_pct','total_trades']].describe())
"
```

## Hardware

- **M4 Pro 48GB** — empirically saturates at ~8 parallel `run_random_v9.py` processes (I/O-bound on 1-minute Parquet reads)
- ~5–10 K trials/hour/study (TF-dependent: 4h faster, 15m slower due to bar-count differential)
- Full multi-TF discovery (15m + 1h + 4h × 20 studies × 100 K trials) writes ~7 GB of Parquet (zstd-compressed)

## Known issues

- `yfinance` and `fredapi` not in `pyproject.toml` — must install manually
- Claude Code sandbox: background processes need `</dev/null` stdin redirect + `disown`
- Bash subshell `$(python -c "...")` can hang in orchestrator check loops
