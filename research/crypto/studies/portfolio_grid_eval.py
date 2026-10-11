"""Evaluate the 4-coin grid: pooled return/DD per period, walk-forward, plateau (neighbour) check, per-coin check."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import itertools, pickle
import numpy as np, pandas as pd
import common as C
from portfolio_grid import GRID, COINS

z = pickle.load(open(C.D.CACHE / "portfolio_grid.pkl", "rb")); cfgs, T = z["cfgs"], z["trades"]
MULTS = (1.0, 0.5, 0.0)
m2 = lambda s: int(pd.Timestamp(s).value // 60_000_000_000)
A, DEV_END, END = m2("2020-03-01"), m2("2024-01-01"), m2("2026-10-01")


def pooled(i, mult, coins=COINS):
    ex = np.concatenate([T[(s, i)][0] for s in coins]); en = np.concatenate([T[(s, i)][1] for s in coins])
    r = np.concatenate([T[(s, i)][2] * np.where(T[(s, i)][3] < 0, mult, 1.0) for s in coins]).astype(float)
    o = np.argsort(ex); return ex[o], en[o], r[o]


def mar(ex, en, r, a, b):
    k = (en >= a) & (en < b)
    if k.sum() < 30:
        return -9, 0, 0
    rr = r[k]; eq = np.cumsum(rr); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    yrs = (b - a) / 525960
    return rr.sum() / yrs / max(dd, 3), rr.sum() / yrs, dd


rows = []
for i, c in enumerate(cfgs):
    for mlt in MULTS:
        ex, en, r = pooled(i, mlt)
        d = mar(ex, en, r, A, DEV_END); h = mar(ex, en, r, DEV_END, END); f = mar(ex, en, r, A, END)
        pc = [mar(*pooled(i, mlt, [s]), DEV_END, END)[0] for s in COINS]
        rows.append(dict(i=i, short=mlt, **c, dev=d[0], new=h[0], full=f[0], full_Ryr=f[1], full_DD=f[2], coin_min_new=min(pc),
                         tr_mo=len(r) / 79))
df = pd.DataFrame(rows)
df["robust"] = df[["dev", "new"]].min(axis=1)
ref = df[(df.n == 20) & (df.sl_atr == 1.0) & (df.be_R == 1.5) & (df.hold_h == 120) & (df.ema_n == 50) & (df.slope_d == 5) & (df.short == 0.5)].iloc[0]
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
cols = ["n", "sl_atr", "be_R", "hold_h", "ema_n", "slope_d", "short", "dev", "new", "full", "full_Ryr", "full_DD", "coin_min_new", "tr_mo"]
print("v2.2 reference:\n", ref[cols].to_frame().T.round(2).to_string(index=False))
print(f"\nv2.2 rank by full-period ret/DD: {(df.full > ref.full).sum() + 1} of {len(df)}; by min(2020-23, 2024-26): {(df.robust > ref.robust).sum() + 1}")
print("\nTOP 15 by min(2020-23 ret/DD, 2024-26 ret/DD):")
print(df.sort_values("robust", ascending=False).head(15)[cols].round(2).to_string(index=False))
# parameter marginals (plateau view), median 'robust' per value
print("\nmedian min(dev, new) per parameter value:")
for k in list(GRID) + ["short"]:
    print(f"  {k:8s}", df.groupby(k).robust.median().round(2).to_dict())
# neighbour plateau for the top 10 robust configs
keys = list(GRID); vals = {k: GRID[k] for k in keys}
idx = {(tuple(getattr(r, k) for k in keys), r.short): r.robust for r in df.itertuples()}
print("\nplateau check (median robust score of all one-step neighbours):")
for r in df.sort_values("robust", ascending=False).head(10).itertuples():
    nb = []
    for k in keys:
        L = vals[k]; j = L.index(getattr(r, k))
        for jj in (j - 1, j + 1):
            if 0 <= jj < len(L):
                key = tuple((L[jj] if kk == k else getattr(r, kk)) for kk in keys)
                nb.append(idx[(key, r.short)])
    print(f"  {dict((k, getattr(r, k)) for k in keys)} short x{r.short}: own {r.robust:.2f}, neighbours median {np.median(nb):.2f}, worst {min(nb):.2f}")
# walk-forward over everything (choose on earlier years, pooled)
oos = []; picks = []
for y in range(2022, 2027):
    a, b = m2(f"{y}-01-01"), m2(f"{y+1}-01-01")
    best, bs = None, -99
    for r in df.itertuples():
        s = mar(*pooled(r.i, r.short), A, a)[0]
        if s > bs:
            bs, best = s, r
    ex, en, rr = pooled(best.i, best.short); k = (en >= a) & (en < b); oos.append(rr[k]); picks.append({kk: getattr(best, kk) for kk in keys + ["short"]})
o = np.concatenate(oos); eq = np.cumsum(o); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
exr, enr, rr = pooled(int(ref.i), 0.5); k = enr >= m2("2022-01-01"); eqr = np.cumsum(rr[k]); ddr = (np.maximum.accumulate(np.r_[0, eqr])[1:] - eqr).max()
print("\nwalk-forward picks:"); [print("  ", y, p) for y, p in zip(range(2022, 2027), picks)]
print(f"walk-forward 2022-26 out of sample: {o.sum()/4.75:.0f}R/yr DD {dd:.1f} ret/DD {o.sum()/4.75/dd:.2f}  |  v2.2 fixed: {rr[k].sum()/4.75:.0f}R/yr DD {ddr:.1f} ret/DD {rr[k].sum()/4.75/ddr:.2f}")
df.to_csv(C.ROOT / "research" / "results" / "crypto_portfolio_grid.csv", index=False)
