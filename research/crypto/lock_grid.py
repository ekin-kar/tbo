"""Profit-lock neighbourhood (follow-up of ratchet.py): once a trade reaches +A R, its stop moves to +L R (one step).
Scored on a fixed-size R account (BTC 2, ETH 1, alts 1/3, shorts x0.5): net R and max drawdown in R per period, so the
result does not depend on compounding luck; plus the ladder from $200 (2020 and 2024 runs)."""
import pickle
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import botsim as BS
import ratchet as Rt

GRID = [(A, L) for A in (3.0, 3.5, 4.0, 4.5, 5.0, 6.0) for L in (0.5, 1.0, 1.5, 2.0, 3.0) if L <= A - 1.0]
WT = np.array([2, 1, 1 / 3, 1 / 3, 1 / 3])


def rstats(R, xt, mask):
    w = WT[Rt.CI[mask]] * np.where(Rt.DIR[mask] < 0, 0.5, 1.0)
    o = np.argsort(xt[mask]); e = np.cumsum((R[mask] * w)[o])
    dd = (np.maximum.accumulate(np.r_[0, e])[1:] - e).max()
    return e[-1], dd


def job(r):
    out = [Rt.run(k, ("lock",) + r if r else None) for k in range(Rt.N)]
    R = np.array([o[0] for o in out]); xt = np.array([o[1] for o in out])
    per = Rt.E < pd.Timestamp("2024-01-01").value // Rt.MIN
    s = [rstats(R, xt, per), rstats(R, xt, ~per)]
    acc = Rt.account(out)
    return r, s, acc, int((R[~per] >= 5).sum())


if __name__ == "__main__":
    with Pool(3) as p:
        res = p.map(job, [None] + GRID)
    pickle.dump(res, open(C.D.CACHE / "lock_grid.pkl", "wb"))
    b = res[0]
    print(f"{'lock':14s} | fixed R account 2020-23: net, maxDD, net/DD (x bot) | 2024-26: net, maxDD, net/DD (x bot) | >=5R 24-26 | ladder from 2020: final, drop | from 2024: final, drop")
    for r, s, acc, big in res:
        nm = "bot now" if r is None else f"+{r[0]}R -> +{r[1]}R"
        print(f"{nm:14s} | {s[0][0]:6.0f} {s[0][1]:5.1f} {s[0][0]/s[0][1]:5.2f} (x{s[0][0]/s[0][1]/(b[1][0][0]/b[1][0][1]):.2f}) | "
              f"{s[1][0]:6.0f} {s[1][1]:5.1f} {s[1][0]/s[1][1]:5.2f} (x{s[1][0]/s[1][1]/(b[1][1][0]/b[1][1][1]):.2f}) | {big:3d} | "
              f"${acc['2020'][0]:>11,.0f} {acc['2020'][1]:5.1f}% | ${acc['2024'][0]:>8,.0f} {acc['2024'][1]:5.1f}%", flush=True)
