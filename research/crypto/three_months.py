"""What 3 months of the bot can look like from $200 (v2.5: BTC 5 / ETH 2.5 / alts 0.83, cap 5.5% BTC exempt).
(1) every real 3-month window 2022-26 (start each week); (2) 5,000 block-bootstrap journeys (4-week blocks of 2022-26)."""
import numpy as np, pandas as pd
from multiprocessing import Pool
import sizing_v4 as V

R = V.R(5, 2.5, 0.83); CAP = 0.055; M3 = int(3 * 30.44 * 1440)


def window(t0):
    x = V.TR[(V.TR[:, 0] >= t0) & (V.TR[:, 0] < t0 + M3)].copy()
    f, dd, _, _ = V.sim(x, R, CAP, eq0=200.0)
    return f, dd, len(x)


def boot(seed):
    r = np.random.default_rng(seed)
    t0, t1 = pd.Timestamp("2022-01-01").value // V.MIN, pd.Timestamp("2026-10-01").value // V.MIN
    pool = V.TR[(V.TR[:, 0] >= t0) & (V.TR[:, 0] < t1)]; rows = []
    for k in range(4):
        u = t0 + r.integers(0, (t1 - V.BLK - t0) // 240) * 240
        s = pool[(pool[:, 0] >= u) & (pool[:, 0] < u + V.BLK)].copy(); s[:, :3] += k * V.BLK - u; rows.append(s)
    x = np.concatenate(rows); x = x[x[:, 0] < M3]
    f, dd, _, _ = V.sim(x, R, CAP, eq0=200.0, end=M3)
    return f, dd, len(x)


def show(name, z):
    f, dd, n = z[:, 0], z[:, 1], z[:, 2]
    q = lambda a, p: np.percentile(a, p)
    print(f"{name}: end balance  1-in-10 bad ${q(f,10):.0f} | 1-in-4 bad ${q(f,25):.0f} | typical ${q(f,50):.0f} | 1-in-4 good ${q(f,75):.0f} | 1-in-10 good ${q(f,90):.0f}")
    print(f"   below $200 after 3 months: {(f < 200).mean()*100:.0f}% | below $150: {(f < 150).mean()*100:.0f}% | below $100: {(f < 100).mean()*100:.0f}% | doubled: {(f >= 400).mean()*100:.0f}%")
    print(f"   worst drop inside the 3 months: typical {q(dd,50):.0f}%, 1 in 4 {q(dd,75):.0f}%, 1 in 10 {q(dd,90):.0f}% | trades: typical {q(n,50):.0f} ({q(n,10):.0f}-{q(n,90):.0f})")


if __name__ == "__main__":
    starts = np.arange(pd.Timestamp("2022-01-03").value // V.MIN, pd.Timestamp("2026-07-01").value // V.MIN, 7 * 1440)
    with Pool(4) as p:
        w = np.array(p.map(window, starts)); b = np.array(p.map(boot, range(5000), chunksize=100))
    show(f"real 3-month windows 2022-26 (n={len(w)})", w)
    show("bootstrap 3-month journeys (n=5000)", b)
