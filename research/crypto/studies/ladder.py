"""Risk ladders (Oct 2026): risk set by the account balance, high while the account is small, lower as it grows.
Ladder = [(balance from, BTC risk %), ...]; ETH = min(2.5, BTC/2), alts = min(0.83, BTC/6) (above 5% only BTC rises:
lowering ETH/alts with BTC 7.5 cost a lot for little, sizing_v4); cap 1.1 x BTC risk, BTC exempt; shorts half.
2-year journeys from $200: (1) 5,000 block-bootstrap runs (4-week blocks of 2022-26 trades), (2) every real 2-year
window of 2020-26 (start each month). Worst drop counts open risk not at breakeven as lost (as everywhere)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import numpy as np, pandas as pd
from multiprocessing import Pool
import sizing_v4 as V

M24 = int(24 * 30.44 * 1440)
LADDERS = {
    "flat 5% (now)": [(0, 5)],
    "flat 7.5%": [(0, 7.5)],
    "flat 6%": [(0, 6)],
    "5% -> 2.5% from $10k": [(0, 5), (10_000, 2.5)],
    "5% -> 3.5% from $3k -> 2.5% from $10k": [(0, 5), (3_000, 3.5), (10_000, 2.5)],
    "7.5% -> 5% from $1k": [(0, 7.5), (1_000, 5)],
    "7.5% -> 5% from $1k -> 2.5% from $10k": [(0, 7.5), (1_000, 5), (10_000, 2.5)],
    "7.5% -> 5% from $2k -> 2.5% from $10k": [(0, 7.5), (2_000, 5), (10_000, 2.5)],
    "7.5% -> 5% from $5k -> 2.5% from $15k": [(0, 7.5), (5_000, 5), (15_000, 2.5)],
    "10% -> 7.5% from $500 -> 5% from $2k -> 2.5% from $10k": [(0, 10), (500, 7.5), (2_000, 5), (10_000, 2.5)],
}


def risk_at(lad, eq):
    b = [r for th, r in lad if eq >= th][-1]
    return b, np.array([b, min(2.5, b / 2), min(0.83, b / 6), min(0.83, b / 6), min(0.83, b / 6)]) / 100


def sim(x, lad, eq0=200.0, end=None):
    ev = []
    for i, (e, xx, be, d, R, c) in enumerate(x):
        ev += [(e, 1, i), (max(be, e + 1e-3), 0, i), (max(xx, e + 2e-3), 2, i)]
    rank = {2: 0, 0: 1, 1: 2}
    ev.sort(key=lambda z: (z[0], rank[z[1]]))
    eq = eq0; opn = {}; pk = eq0; dd = 0.0; top = eq0; pk1 = 0.0; dd1 = 0.0
    for t, kind, i in ev:
        if end is not None and t > end:
            break
        e, xx, be, d, R, c = x[i]; c = int(c)
        if kind == 1:
            b, rk = risk_at(lad, eq)
            amt = eq * rk[c] * (0.5 if d < 0 else 1.0)
            if c != 0:
                room = 0.011 * b * eq - sum(v[0] for v in opn.values() if not v[1])
                if amt > room:
                    amt = room if room > 0.25 * amt else 0.0
            if amt > 0:
                opn[i] = [amt, False]
        elif kind == 0 and i in opn:
            opn[i][1] = True
        elif kind == 2 and i in opn:
            eq += opn.pop(i)[0] * R; top = max(top, eq)
        w = eq - sum(v[0] for v in opn.values() if not v[1])
        pk = max(pk, w); dd = max(dd, (pk - w) / pk)
        if pk >= 1000:                                          # drops once the account has reached $1k
            pk1 = max(pk1, w); dd1 = max(dd1, (pk1 - w) / pk1)
    return eq, dd * 100, top, dd1 * 100


def boot(args):
    seed, name = args
    r = np.random.default_rng(seed)
    t0, t1 = pd.Timestamp("2022-01-01").value // V.MIN, pd.Timestamp("2026-10-01").value // V.MIN
    pool = V.TR[(V.TR[:, 0] >= t0) & (V.TR[:, 0] < t1)]; rows = []
    for k in range(int(np.ceil(M24 / V.BLK))):
        u = t0 + r.integers(0, (t1 - V.BLK - t0) // 240) * 240
        s = pool[(pool[:, 0] >= u) & (pool[:, 0] < u + V.BLK)].copy(); s[:, :3] += k * V.BLK - u; rows.append(s)
    return sim(np.concatenate(rows), LADDERS[name], end=M24)


def window(args):
    t0, name = args
    return sim(V.TR[(V.TR[:, 0] >= t0) & (V.TR[:, 0] < t0 + M24)], LADDERS[name])


def line(z):
    f, dd, top, d1 = z[:, 0], z[:, 1], z[:, 2], z[:, 3]
    q = lambda a, p: np.percentile(a, p)
    return (f"{q(f,50):>8,.0f} {q(f,25):>7,.0f} {(f>=1e4).mean()*100:5.0f}% {(f>=2e4).mean()*100:5.0f}% {(f<200).mean()*100:5.0f}% {(f<100).mean()*100:5.0f}% "
            f"{((top>=5e3)&(f<0.5*top)).mean()*100:6.0f}% | {q(dd,50):4.0f}% {q(dd,90):4.0f}% | {q(d1,50):4.0f}% {q(d1,90):4.0f}%")


if __name__ == "__main__":
    starts = np.arange(pd.Timestamp("2020-03-01").value // V.MIN, pd.Timestamp("2024-10-01").value // V.MIN, int(30.44 * 1440))
    hdr = f"{'':54s} | {'median':>8s} {'1in4bad':>7s} {'>=10k':>6s} {'>=20k':>6s} {'<$200':>6s} {'<$100':>6s} {'gaveback':>7s} |  drop: typ 1in10 | after $1k: typ 1in10"
    with Pool(4) as p:
        res = {n: np.array(p.map(boot, [(s, n) for s in range(4000)], chunksize=100)) for n in LADDERS}
        win = {n: np.array(p.map(window, [(t, n) for t in starts])) for n in LADDERS}
    print("=== 2 years from $200, 4,000 reshuffled runs (2022-26 trades) ===  gaveback = reached $5k+ but ended below half the top")
    print(hdr)
    for n in LADDERS:
        print(f"{n:54s} | {line(res[n])}")
    print(f"\n=== every real 2-year window 2020-26 (n={len(starts)}, start each month; 2020-21 bull run included) ===")
    print(hdr)
    for n in LADDERS:
        print(f"{n:54s} | {line(win[n])}")
