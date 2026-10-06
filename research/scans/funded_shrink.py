"""Funding Pips funded account (12 months, payouts every 14 days, $300 kept, 1.5% bot daily stop) with and without the
bots' risk scaling: none / shrink from the start / full to -4% then shrink (as in the challenge), min 0.3x. Same model as
fundingpips_funded.py with the scaling line of fundingpips_sim.py added. Also: losses before vs after the first payout."""
import sys, pathlib, inspect; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, numba as nb, pandas as pd
import fundingpips_funded as FF, fundingpips_sim as F
src = inspect.getsource(FF.fund.py_func).replace('@nb.njit(cache=True)\n', '')
src = src.replace('daily=0.02, floor=0.88, split=0.8):', 'daily=0.02, floor=0.88, split=0.8, minm=1.0, dz=0.0):')
a = '                op[no] = j; sz[no] = (rg if sym[j] == 0 else rv) * bal; no += 1'
assert a in src
src = src.replace(a, '''                w = (rg if sym[j] == 0 else rv) * bal
                if minm < 1.0 and bal < 1.0 - dz: w *= max(minm, (bal - floor) / ((1.0 - dz) - floor))
                op[no] = j; sz[no] = w; no += 1''')
ns = vars(FF).copy(); exec(src, ns); fund = nb.njit(ns['fund'])
D = F.load(); ent, ext, sym, Rr, off, fc, fw = D
def boot(rg, rv, keep, a, b, minm, dz, N=4000, blocks=13, seed=11):
    rng = np.random.default_rng(seed); W = F.WEEK
    starts = np.arange(F.sat(a), F.sat(b) - 4 * W, W); lo = np.searchsorted(ent, starts); hi = np.searchsorted(ent, starts + 4 * W)
    out = np.empty((N, 3))
    for p in range(N):
        pick = rng.integers(0, len(starts), blocks); idx = np.concatenate([np.arange(lo[q], hi[q]) for q in pick])
        shift = np.repeat(np.arange(blocks) * 4 * W - starts[pick] + starts[0], hi[pick] - lo[pick])
        out[p] = fund(ent[idx] + shift, ext[idx] + shift, sym[idx], Rr[idx], off[idx], fc, fw, rg, rv, 0.015, 0.0005,
                      blocks * 28 * 1440, keep, 0.02, 0.88, 0.8, minm, dz)
    return out
WIN = {"2y": ("2024-09-21", "2026-09-19"), "3y": ("2023-09-23", "2026-09-19"), "10y": ("2016-01-09", "2026-09-19")}
rows = []
for rg, rv in ((0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.8)):
    for lab, minm, dz in (("no shrink", 1.0, 0.0), ("shrink from start", 0.3, 0.0), ("full to -4%, then shrink", 0.3, 0.04)):
        r = dict(risk=f"{rg}/{rv}", shrink=lab)
        for w, (a, b) in WIN.items():
            o = boot(rg / 100, rv / 100, 0.03, a, b, minm, dz)
            pay = o[:, 1] * 10000; lost = o[:, 0] == 1
            r[f"{w} lost%"] = round(100 * lost.mean(), 1)
            r[f"{w} paid med"] = int(round(np.median(pay)))
            r[f"{w} bad yr p25"] = int(round(np.percentile(pay, 25)))
            if w == "10y":
                r["10y lost before 1st payout%"] = round(100 * (lost & (o[:, 2] < 0)).mean(), 1)
                fp = o[o[:, 2] >= 0, 2] / 1440; r["10y 1st payout days"] = int(round(np.median(fp)))
        rows.append(r); print(r, flush=True)
pd.DataFrame(rows).to_csv(pathlib.Path(__file__).resolve().parent.parent / "results" / "funded_shrink.csv", index=False)
