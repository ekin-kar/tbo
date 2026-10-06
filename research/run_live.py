"""Backtest the two live bots with the research engine and print their statistics.

Usage (from the folder that contains this file):
    python run_live.py
Data files must be in ./data (or set TRADING_DATA): XAUUSD_M1.m1pack, USDJPY_M1.m1pack,
XAUUSD_DUKA_BID.m1pack, XAUUSD_DUKA_ASK.m1pack, USDJPY_DUKA_BID.m1pack, USDJPY_DUKA_ASK.m1pack,
XAUUSD_SPREAD.csv, USDJPY_SPREAD.csv. The first run builds ./cache (a few minutes); later runs take seconds.
"""
import sys, pathlib, runpy
ROOT = pathlib.Path(__file__).resolve().parent
if ROOT.name == "research": ROOT = ROOT.parent   # works from the repo root or from research/
sys.path[:0] = [str(ROOT), str(ROOT / "research")]
import numpy as np, pandas as pd
import R, ideas as X

for sym in ("XAUUSD", "USDJPY"):
    if not (R.C / f"{sym}_duka.npz").exists():
        print("First run: preparing the Dukascopy files (one-off)...")
        runpy.run_path(str(ROOT / "research" / "prep.py"))
        break

def clean(sym, tr, adj):
    """Drop trades that span whole missing data days; deduct the measured live-execution gap per trade."""
    t = R.get(sym)["t"]; gap = np.r_[0, np.diff(t)]
    holes = pd.to_datetime(t[np.flatnonzero(gap > 120)] * 60, unit="s").values.astype("datetime64[m]")
    a = tr.entry_time.values.astype("datetime64[m]"); b = tr.exit_time.values.astype("datetime64[m]")
    bad = np.zeros(len(tr), bool)
    for x in holes: bad |= (a < x) & (b >= x)
    tr = tr[~bad].copy(); tr["R"] = tr.R - adj; return tr

print("Running gold (PDAYT, 01:15 UTC, EMA40) ...")
gold = clean("XAUUSD", R.run("XAUUSD", X.pday_trend(R.get("XAUUSD")), "main"), 0.02)
print("Running USDJPY (VOLC, Friday close) ...")
volc = clean("USDJPY", R.run("USDJPY", X.volc_f(R.get("USDJPY")), "main"), 0.002)

def stats(tr):
    tr = tr.sort_values("exit_time"); c = np.cumsum(tr.R.values)
    dd = (np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]).max()
    pos, neg = tr.R[tr.R > 0].sum(), -tr.R[tr.R <= 0].sum()
    return f"{len(tr):5d} trades | win {100*(tr.R>0).mean():5.1f}% | PF {pos/neg:4.2f} | net {tr.R.sum():+7.1f}R | max DD {dd:5.1f}R"

both = pd.concat([gold, volc])
for lab, start in [("Full history", "2016-01-01"), ("Last 5 years", "2021-09-19"), ("Last 3 years", "2023-09-19"), ("Last year", "2025-09-19")]:
    print(f"\n{lab}")
    for name, tr in [("Gold  ", gold), ("USDJPY", volc), ("Both  ", both)]:
        print("  ", name, stats(tr[tr.entry_time >= start]))
yr = pd.DataFrame({"Gold": gold.groupby(gold.entry_time.dt.year).R.sum(), "USDJPY": volc.groupby(volc.entry_time.dt.year).R.sum()}).fillna(0)
yr["Both"] = yr.sum(axis=1)
print("\nNet R per year:"); print(yr.round(1).to_string())
gold.to_csv(ROOT / "gold_trades.csv", index=False); volc.to_csv(ROOT / "usdjpy_trades.csv", index=False)
print("\nTrade lists written to gold_trades.csv and usdjpy_trades.csv")
