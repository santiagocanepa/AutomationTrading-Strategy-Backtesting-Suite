"""Verify commission tracking is working end-to-end."""
from pathlib import Path
import pandas as pd
import numpy as np
from suitetrading.data.storage import ParquetStore
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.backtesting._internal.schemas import BacktestDataset
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.optimization._internal.objective import BacktestObjective

store = ParquetStore(base_dir=Path("data/raw"))
df_1m = store.read("binance", "BTCUSDT", "1m")
resampler = OHLCVResampler()
df_1h = resampler.resample(df_1m, "1h")
cutoff = df_1h.index.max() - pd.DateOffset(months=36)
df_1h = df_1h.loc[df_1h.index >= cutoff]
print(f"bars={len(df_1h)}")

ds = BacktestDataset(ohlcv=df_1h, symbol="BTCUSDT", base_timeframe="1h", exchange="binance")

# MR best trial params
params = {
    "wavetrend_reversal__channel_len": 25,
    "wavetrend_reversal__average_len": 36,
    "wavetrend_reversal__ma_len": 5,
    "wavetrend_reversal__ob_level": 40.9,
    "wavetrend_reversal__os_level": -96.1,
    "wavetrend_reversal__hold_bars": 17,
    "stop__atr_multiple": 3.5,
    "sizing__risk_pct": 0.5,
}

obj = BacktestObjective(dataset=ds, archetype="mean_reversion", mode="fsm")
result = obj.run_single(params)
trades_df = result["trades"]
metrics = result["metrics"]

print(f"\ntrades: {len(trades_df)}")
print(f"columns: {list(trades_df.columns)}")

if "commission" in trades_df.columns:
    total_comm = trades_df["commission"].sum()
    total_gross = trades_df["pnl"].sum()
    total_net_trade = (trades_df["pnl"] - trades_df["commission"]).sum()
    print(f"\ncommission sum  = {total_comm:.4f}")
    print(f"gross pnl sum   = {total_gross:+.4f}")
    print(f"net trade sum   = {total_net_trade:+.4f}")
    print(f"\nFirst 5 trades:")
    for i in range(min(5, len(trades_df))):
        row = trades_df.iloc[i]
        print(f"  #{i}: pnl={row.pnl:+.4f}  comm={row.commission:.4f}  net={row.pnl - row.commission:+.4f}")
else:
    print("\n*** NO commission column! ***")

eq = result["equity_curve"]
eq_net = float(eq[-1] - 10000.0)
print(f"\nequity net_profit = {eq_net:+.4f}")
print(f"\nMetrics:")
print(f"  Sharpe    = {metrics['sharpe']:.4f}")
print(f"  PF        = {metrics['profit_factor']:.4f}")
print(f"  WR        = {metrics['win_rate']:.2f}")
print(f"  AvgTrade  = {metrics['average_trade']:.4f}")
print(f"  NetProfit = {metrics['net_profit']:.4f}")
print(f"  Trades    = {metrics['total_trades']}")


