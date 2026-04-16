# Sprint 2 Go/No-Go Checklist

Generated: 2026-03-11

## Verdict

GO

Sprint 1 no longer has blocking gaps for the data layer. The raw store incident was repaired, native validation is green, and the project is ready to start indicator expansion in Sprint 2.

## Gates

| Gate | Status | Evidence |
|------|--------|----------|
| Raw parquet store free of corrupt future-year partitions | PASS | `docs/raw_data_integrity_report.md` + quarantine/rebuild run completed |
| Missing 1m partitions for BTCUSDT/ETHUSDT/SOLUSDT regenerated | PASS | `scripts/download_data.py --symbols BTCUSDT ETHUSDT SOLUSDT --timeframe 1m` after parser fix |
| Native 1m→1h validation against exchange candles | PASS | `docs/cross_validation_report.md` |
| Native 1m→1d validation against exchange candles | PASS | `docs/cross_validation_report.md` |
| Downloader hardened against Binance Vision timestamp-unit changes | PASS | `src/suitetrading/data/downloader.py` |
| Concurrent download runs prevented | PASS | `scripts/download_data.py` lock file guard |
| VS Code workspace aligned to project virtualenv | PASS | `.vscode/settings.json` |
| Automated validation suite green | PASS | `256 passed` via `cd suitetrading && .venv/bin/pytest -q` |

## Remaining Non-Blockers

- Sprint 2 still needs to implement the planned standard-indicator layer and broader Pine/TradingView parity work.
- Risk management and backtesting modules remain outside Sprint 1 scope and are still mostly scaffolding.

## Recommendation

Proceed to Sprint 2, but keep the raw-data audit script in the operational playbook whenever historical archives are refreshed or backfilled.