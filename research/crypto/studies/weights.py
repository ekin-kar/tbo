"""Per-coin weights for the 4-coin TBO v2.2 portfolio (R units, shorts at half size). Choose on 2020-23, check 2024-26."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import pickle
import numpy as np, pandas as pd
import common as C

ALL = pickle.load(open(C.D.CACHE / "portfolio_trades.pkl", "rb"))
COINS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]
T = {s: ALL[(s, 0.0003)].assign(Rs=lambda x: x.R * np.where(x.dir < 0, 0.5, 1.0)) for s in COINS}


def met(parts, a, b):
    x = pd.concat(parts); x = x[(x.entry_time >= a) & (x.entry_time < b)].sort_values("exit_time")
    r = x.W.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
    return r.sum() / yrs / dd, r.sum() / yrs, dd


print("per coin ret/DD  2020-23 | 2024-26")
for s in COINS:
    d = met([T[s].assign(W=T[s].Rs)], "2020-03-01", "2024-01-01"); h = met([T[s].assign(W=T[s].Rs)], "2024-01-01", "2026-10-01")
    print(f"  {s[:-4]:5s} {d[0]:5.2f} | {h[0]:5.2f}")
SCHEMES = {"equal 1/1/1/1": (1, 1, 1, 1), "BTC 1.5x": (1.5, 1, 1, 1), "BTC 2x": (2, 1, 1, 1), "BTC 2x, ETH 1.5x": (2, 1.5, 1, 1),
           "BTC 2x, alts 0.5x": (2, 1, 0.5, 0.5), "BTC+ETH only": (1, 1, 0, 0), "BTC only": (1, 0, 0, 0)}
print("\nweights (BTC/ETH/DOGE/ADA), pooled; ret/DD is what matters (risk can be scaled after):")
print(f"  {'scheme':22s} {'2020-23 ret/DD':>15s} {'2024-26 ret/DD':>15s}")
for name, w in SCHEMES.items():
    parts = [T[s].assign(W=T[s].Rs * wi) for s, wi in zip(COINS, w) if wi > 0]
    print(f"  {name:22s} {met(parts, '2020-03-01', '2024-01-01')[0]:15.2f} {met(parts, '2024-01-01', '2026-10-01')[0]:15.2f}")
