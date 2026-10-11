"""Random-skip benchmark for filter_test.py: skip ~the same share of 4h orders at random, 40 seeds."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
from multiprocessing import Pool
import numpy as np, pandas as pd
import filter_test as FT
from portfolio import simulate


def mk(seed, share):
    def f(c, a, hi, lo, s):
        r = np.random.default_rng(seed * 2 + (s > 0)).random(len(a))
        return r < share
    return f


def job(args):
    sym, seed, share = args
    FT.FILTERS["rnd"] = mk(seed, share)
    return seed, share, FT.job((sym, "rnd"))[2]


if __name__ == "__main__":
    out = {}
    for share in (0.12, 0.25):
        with Pool(4) as p:
            res = p.map(job, chunksize=30, iterable= [(s, sd, share) for s in FT.COINS for sd in range(30)])
        by = {}
        for sd, sh, x in res:
            by.setdefault(sd, []).append(x)
        rows = []
        for sd, xs in by.items():
            TT = pd.concat(xs); r = []
            for a, b, mo in (("2020-03-01", "2024-01-01", 46), ("2024-01-01", "2026-10-01", 33)):
                cv, tk = simulate(TT, risk=0.05, cap=99, short_mult=0.5, start=a, end=b, eq0=200.0, weights=FT.W)
                pk = cv.worst.cummax(); r += [((cv.equity.iloc[-1] / 200) ** (1 / mo) - 1) * 100, ((pk - cv.worst) / pk).max() * 100, len(tk), cv.equity.iloc[-1]]
            rows.append(r)
        R = np.array(rows)
        print(f"random skip of {share*100:.0f}% of order candles: trades dev {R[:,2].mean():.0f} ho {R[:,6].mean():.0f}")
        for i, nm in ((0, "dev %/mo"), (1, "dev DD"), (4, "ho %/mo"), (5, "ho DD"), (7, "ho $200->")):
            print(f"   {nm:10s} 10th {np.percentile(R[:,i],10):9.2f}  median {np.median(R[:,i]):9.2f}  90th {np.percentile(R[:,i],90):9.2f}")
