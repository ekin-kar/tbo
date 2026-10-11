"""Real TBO v2.2 entries vs RANDOM entries with identical coins, trend filter, stop, breakeven, 5-day exit, weights.
200 random runs. If the real result is not far above all of them, the edge is luck."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import pickle
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V21

W = {"BTCUSDT": 2.0, "ETHUSDT": 1.0, "DOGEUSDT": 0.5, "ADAUSDT": 0.5}
N = 200
DATA = {}


def run(sym, seed):
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    if sym not in DATA:
        DATA[sym] = C.load(sym)
    kw = dict(V21) if seed < 0 else dict(V21, rand_p=0.06, rand_seed2=seed)
    x = C.between(F.channel_breakout(DATA[sym], **kw), "2020-03-01", "2026-10-01")
    return x.assign(u=x.R * W[sym] * np.where(x.dir < 0, 0.5, 1.0))[["entry_time", "exit_time", "u"]]


def job(a):
    sym, seed = a
    return sym, seed, run(sym, seed)


def stats(x):
    out = {}
    for p, (a, b) in {"2020-23": ("2020-03-01", "2024-01-01"), "2024-26": ("2024-01-01", "2026-10-01")}.items():
        z = x[(x.entry_time >= a) & (x.entry_time < b)].sort_values("exit_time"); r = z.u.to_numpy()
        eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
        out[p] = (r.mean(), r.sum() / dd if dd > 0 else 0, len(r))
    return out


if __name__ == "__main__":
    with Pool(4) as p:
        res = p.map(job, [(s, k) for s in W for k in [-1] + list(range(N))], chunksize=N + 1)
    by = {}
    for s, k, x in res:
        by.setdefault(k, []).append(x)
    real = stats(pd.concat(by[-1]))
    rnd = [stats(pd.concat(by[k])) for k in range(N)]
    out = {}
    for p in ("2020-23", "2024-26"):
        avg = np.array([r[p][0] for r in rnd]); n = np.array([r[p][2] for r in rnd])
        beat = (avg < real[p][0]).mean() * 100
        print(f"{p}: real avg {real[p][0]:+.3f} R/trade ({real[p][2]} trades) | random: mean {avg.mean():+.3f}, best of 200 {avg.max():+.3f} "
              f"({n.mean():.0f} trades avg) | real beats {beat:.1f}% of random runs | real is {(real[p][0]-avg.mean())/avg.std():.1f} st.dev above")
        out[p] = dict(real=real[p][0], rand=avg.tolist(), real_n=real[p][2], rand_n=float(n.mean()))
    pickle.dump(out, open(C.D.CACHE / "random_bench.pkl", "wb"))
