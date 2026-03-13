"""Analyze risk lab results for report generation."""
import pandas as pd

df = pd.read_csv("artifacts/risk_lab/BTCUSDT_ETHUSDT_SOLUSDT_15m_1h_4h_1d_20260312_133450/risk_lab_results.csv")
print("Shape:", df.shape)
print()

print("=== By strategy_family ===")
for fam, g in df.groupby("strategy_family"):
    print(f"  {fam}: mean_sharpe={g['sharpe'].mean():.3f}, mean_return={g['total_return_pct'].mean():.2f}%, mean_dd={g['max_drawdown_pct'].mean():.2f}%, trades={g['total_trades'].sum()}")
print()

print("=== By symbol ===")
for sym, g in df.groupby("symbol"):
    print(f"  {sym}: mean_sharpe={g['sharpe'].mean():.3f}, mean_return={g['total_return_pct'].mean():.2f}%, trades={g['total_trades'].sum()}")
print()

print("=== By timeframe ===")
for tf, g in df.groupby("timeframe"):
    print(f"  {tf}: mean_sharpe={g['sharpe'].mean():.3f}, mean_return={g['total_return_pct'].mean():.2f}%, trades={g['total_trades'].sum()}")
print()

print("=== By risk_profile (trend) ===")
trend = df[df["strategy_family"] == "trend"]
for rp, g in trend.groupby("risk_profile"):
    print(f"  {rp}: mean_sharpe={g['sharpe'].mean():.3f}, mean_return={g['total_return_pct'].mean():.2f}%")
print()

print("=== By risk_profile (mean_reversion) ===")
mr = df[df["strategy_family"] == "mean_reversion"]
for rp, g in mr.groupby("risk_profile"):
    print(f"  {rp}: mean_sharpe={g['sharpe'].mean():.3f}, mean_return={g['total_return_pct'].mean():.2f}%")
print()

print("=== Top 10 positive sharpe ===")
pos = df[df["sharpe"] > 0].sort_values("sharpe", ascending=False).head(10)
for _, r in pos.iterrows():
    print(f"  {r['run_label']}: sharpe={r['sharpe']:.3f}, ret={r['total_return_pct']:.2f}%, dd={r['max_drawdown_pct']:.2f}%")
print()

print(f"Positive sharpe campaigns: {len(df[df['sharpe'] > 0])}/{len(df)}")
print(f"Campaigns with >0% return: {len(df[df['total_return_pct'] > 0])}/{len(df)}")
