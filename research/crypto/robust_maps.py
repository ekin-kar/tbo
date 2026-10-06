"""Sensitivity maps around v2.2 from the wide 4-coin grid (equal weights, shorts half) + 'halve the drawdown' search."""
import pickle, json
import numpy as np, pandas as pd
import common as C
from portfolio_grid import COINS

z = pickle.load(open(C.D.CACHE / "portfolio_grid.pkl", "rb")); cfgs, T = z["cfgs"], z["trades"]
keys = ["n", "sl_atr", "be_R", "hold_h", "ema_n", "slope_d"]
kof = {tuple(c[k] for k in keys): i for i, c in enumerate(cfgs)}
m2 = lambda s: int(pd.Timestamp(s).value // 60_000_000_000)
PER = {"2020-23": (m2("2020-03-01"), m2("2024-01-01")), "2024-26": (m2("2024-01-01"), m2("2026-10-01"))}


def met(i, p):
    ex = np.concatenate([T[(s, i)][0] for s in COINS]); en = np.concatenate([T[(s, i)][1] for s in COINS])
    r = np.concatenate([T[(s, i)][2] * np.where(T[(s, i)][3] < 0, 0.5, 1.0) for s in COINS]).astype(float)
    o = np.argsort(ex); en, r = en[o], r[o]; a, b = PER[p]; k = (en >= a) & (en < b); rr = r[k]
    eq = np.cumsum(rr); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max(); yrs = (b - a) / 525960
    return dict(mar=round(rr.sum() / yrs / dd, 2), ryr=round(rr.sum() / yrs), dd=round(dd, 1))


BASE = dict(n=20, sl_atr=1.0, be_R=1.5, hold_h=120, ema_n=50, slope_d=5)
MAPS = [("n", "hold_h", "Breakout channel (candles) vs max hold"), ("sl_atr", "be_R", "Stop size (ATR) vs breakeven trigger (R)"),
        ("ema_n", "slope_d", "Trend EMA vs slope check (days)")]
GV = dict(n=[15, 20, 30, 40], sl_atr=[0.75, 1.0, 1.25, 1.5], be_R=[0.0, 1.0, 1.5, 2.0], hold_h=[72, 120, 168], ema_n=[30, 50, 100], slope_d=[0, 5, 10])
maps = []
for a, b, title in MAPS:
    cells = []
    for va in GV[a]:
        for vb in GV[b]:
            c = dict(BASE, **{a: va, b: vb}); i = kof[tuple(c[k] for k in keys)]
            cells.append(dict(x=vb, y=va, **{p: met(i, p) for p in PER}))
    maps.append(dict(a=a, b=b, title=title, xs=GV[b], ys=GV[a], cells=cells))
    print(title)
    for p in PER:
        print("  ", p, " ".join(f"{c['y']}/{c['x']}:{c[p]['mar']}" for c in cells))
base_i = kof[tuple(BASE[k] for k in keys)]
bm = {p: met(base_i, p) for p in PER}
allm = [(i, {p: met(i, p) for p in PER}) for i in range(len(cfgs))]
half = [(i, m) for i, m in allm if all(m[p]["dd"] <= 0.6 * bm[p]["dd"] and m[p]["ryr"] >= 0.85 * bm[p]["ryr"] for p in PER)]
better_both = [(i, m) for i, m in allm if all(m[p]["mar"] > bm[p]["mar"] for p in PER)]
print("\nv2.2:", bm)
print(f"settings with drawdown <= 60% of v2.2 AND profit >= 85% of v2.2 in BOTH periods: {len(half)} of {len(cfgs)}")
print(f"settings with better return/DD than v2.2 in BOTH periods: {len(better_both)}")
for i, m in sorted(better_both, key=lambda t: -min(t[1][p]['mar'] for p in PER))[:8]:
    print("   ", {k: cfgs[i][k] for k in keys}, m)
json.dump(dict(maps=maps, base=bm, n_half=len(half), n_cfg=len(cfgs), better=[dict(cfg={k: cfgs[i][k] for k in keys}, m=m) for i, m in better_both]),
          open(C.D.CACHE / "robust_maps.json", "w"))
