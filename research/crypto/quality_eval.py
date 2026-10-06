"""Pick a 'fewer, better trades' setting on 2020-23 only (neighbourhood-smoothed), then test it:
2024-26 on the 4 coins, the 8 other coins (never used to choose), leave-one-coin-out, and dollars at matched drawdown."""
import pickle, itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
from portfolio_grid import GRIDS, COINS
from wf2 import V21

G = GRIDS["quality"]; keys = list(G)
z = pickle.load(open(C.D.CACHE / "portfolio_grid_quality.pkl", "rb")); cfgs, T = z["cfgs"], z["trades"]
m2 = lambda s: int(pd.Timestamp(s).value // 60_000_000_000)
A, D1, E = m2("2020-03-01"), m2("2024-01-01"), m2("2026-10-01")
SHORT = 0.5


def pooled(i, coins):
    ex = np.concatenate([T[(s, i)][0] for s in coins]); en = np.concatenate([T[(s, i)][1] for s in coins])
    r = np.concatenate([T[(s, i)][2] * np.where(T[(s, i)][3] < 0, SHORT, 1.0) for s in coins]).astype(float)
    o = np.argsort(ex); return en[o], r[o]


def met(en, r, a, b):
    k = (en >= a) & (en < b); rr = r[k]
    if len(rr) < 20:
        return dict(mar=-9, ryr=0, dd=0, tpm=0)
    eq = np.cumsum(rr); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max(); yrs = (b - a) / 525960
    return dict(mar=rr.sum() / yrs / max(dd, 3), ryr=rr.sum() / yrs, dd=dd, tpm=len(rr) / yrs / 12)


key_of = {tuple(c[k] for k in keys): i for i, c in enumerate(cfgs)}


def neighbours(i):
    c = cfgs[i]; out = []
    for k in keys:
        L = G[k]; j = L.index(c[k])
        for jj in (j - 1, j + 1):
            if 0 <= jj < len(L):
                out.append(key_of[tuple((L[jj] if kk == k else c[kk]) for kk in keys)])
    return out


def choose(coins, min_tpm):
    dev = {i: met(*pooled(i, coins), A, D1) for i in range(len(cfgs))}
    smooth = {i: np.mean([dev[i]["mar"]] + [dev[j]["mar"] for j in neighbours(i)]) for i in dev}
    ok = [i for i in dev if dev[i]["tpm"] >= min_tpm]
    return max(ok, key=lambda i: smooth[i]), dev, smooth


if __name__ == "__main__":
    best, dev, smooth = choose(COINS, 6.0)
    ref = key_of[(20, 1.0, 1.5, 120, 50, 5)]
    print("chosen on 2020-23 only (smoothed with neighbours, >= 6 trades/month):", cfgs[best])
    print("top 8 by smoothed 2020-23 score:")
    for i in sorted([i for i in dev if dev[i]["tpm"] >= 6], key=lambda i: -smooth[i])[:8]:
        print(f"   {cfgs[i]}  smoothed {smooth[i]:.2f}  own {dev[i]['mar']:.2f}  trades/mo {dev[i]['tpm']:.1f}")
    print("\n4 coins pooled          |  2020-23: ret/DD  R/yr   DD  tr/mo | 2024-26: ret/DD  R/yr   DD  tr/mo")
    for lab, i in (("v2.2", ref), ("chosen", best)):
        a = met(*pooled(i, COINS), A, D1); b = met(*pooled(i, COINS), D1, E)
        print(f"   {lab:20s} | {a['mar']:12.2f} {a['ryr']:5.0f} {a['dd']:5.1f} {a['tpm']:5.1f} | {b['mar']:12.2f} {b['ryr']:5.0f} {b['dd']:5.1f} {b['tpm']:5.1f}")
    # leave-one-coin-out
    print("\nleave-one-coin-out (choose on 3 coins' 2020-23, test the 4th, full 2020-26):")
    for s in COINS:
        rest = [c for c in COINS if c != s]
        b3, _, _ = choose(rest, 4.5)
        x = met(*pooled(b3, [s]), A, E); y = met(*pooled(ref, [s]), A, E)
        print(f"   held out {s[:-4]:5s}: chosen {cfgs[b3]} -> ret/DD {x['mar']:.2f} ({x['ryr']:.0f}R/yr)   v2.2 {y['mar']:.2f} ({y['ryr']:.0f}R/yr)")
    pickle.dump(dict(best=cfgs[best]), open(C.D.CACHE / "quality_choice.pkl", "wb"))
