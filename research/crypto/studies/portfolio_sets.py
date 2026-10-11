"""Coin sets compared in R units (equal risk per trade, no compounding, no caps): which coins actually help?
Selection rules use ONLY 2020-23; 2024-26 is the check."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import pickle
import numpy as np, pandas as pd
import common as C
from portfolio import COINS

ALL = pickle.load(open(C.D.CACHE / "portfolio_trades.pkl", "rb"))
T = {s: ALL[(s, 0.0003)] for s in COINS}


def stats(syms, a, b):
    x = pd.concat([T[s] for s in syms]); x = x[(x.entry_time >= a) & (x.entry_time < b)].sort_values("exit_time")
    r = x.R.to_numpy(); eq = np.cumsum(r); hw = np.maximum.accumulate(np.r_[0, eq])[1:]; dd = (hw - eq).max()
    yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
    t = x.exit_time.to_numpy(); nh = t[np.r_[True, eq[1:] > hw[:-1]]]
    gaps = np.diff(nh).astype("timedelta64[D]").astype(int)
    mo = x.groupby(x.exit_time.dt.to_period("M")).R.sum()
    return r.sum() / yrs, dd, r.sum() / yrs / dd, gaps.max(), (mo > 0).mean(), len(r) / yrs / 52


dev_r = {s: C.between(T[s], *C.DEV).R.sum() / ((pd.Timestamp(C.DEV[1]) - max(pd.Timestamp(C.DEV[0]), T[s].entry_time.min())).days / 365.25)
         for s in COINS}
dev_mar = {}
for s in COINS:
    x = C.between(T[s], *C.DEV).sort_values("exit_time"); r = x.R.to_numpy(); eq = np.cumsum(r)
    dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max(); dev_mar[s] = dev_r[s] / dd
print("2020-23 per coin: R/yr and return/DD:", {s[:-4]: (round(dev_r[s]), round(dev_mar[s], 2)) for s in COINS})
SETS = {
    "BTC+ETH": ["BTCUSDT", "ETHUSDT"],
    "all 12": COINS,
    "dev R/yr >= 15": [s for s in COINS if dev_r[s] >= 15],
    "dev return/DD >= 1.0": [s for s in COINS if dev_mar[s] >= 1.0],
    "dev top 6 by return/DD": sorted(COINS, key=lambda s: -dev_mar[s])[:6],
    "top 5 by liquidity (a priori)": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"],
}
print(f"\n{'set':32s} {'coins':>5s} | {'2020-23: R/yr  DD  ret/DD':>26s} | {'2024-26: R/yr  DD  ret/DD  longest flat  months+  trades/wk':>58s}")
for name, syms in SETS.items():
    d = stats(syms, *C.DEV); h = stats(syms, *C.HOLDOUT)
    print(f"{name:32s} {len(syms):5d} | {d[0]:8.0f} {d[1]:6.1f} {d[2]:6.2f}   | {h[0]:8.0f} {h[1]:6.1f} {h[2]:6.2f} {h[3]:8d}d {h[4]*100:6.0f}% {h[5]:8.1f}"
          f"   {[s[:-4] for s in syms] if len(syms) < 12 else ''}")
