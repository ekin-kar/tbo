"""Entry ideas for TBO v2.1: shorter channel, finer timeframe (same window, 4h stop), scale-in, breakout retest.
Same walk-forward test as ideas10.py (BTC+ETH pooled, 2022-26)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
import ideas10 as X
from wf2 import V21, stream, mar, TESTS

A, B = X.A, X.B


def scale_in(sym, n1):
    a = X.base(sym, n=n1).copy(); b = X.base(sym).copy()
    a["R"] *= 0.5; b["R"] *= 0.5
    return pd.concat([a, b])


IDEAS = {
    "1 shorter channel": [(f"n={n}", X.base, dict(n=n)) for n in (5, 10, 15)],
    "2 finer timeframe, same window, 4h stop": [(f"{tf}m n={n}", X.base, dict(tf=tf, n=n, atr_tf=240))
                                               for tf, n in ((60, 80), (120, 40), (60, 40), (120, 20))],
    "3 scale in (half at n, half at 20)": [(f"half at n={n}", scale_in, dict(n1=n)) for n in (5, 10, 15)],
    "4 buy the retest (limit at broken level)": [(f"valid {h}h off {o}ATR", X.base, dict(retest_h=h, retest_off=o))
                                                for h in (4, 12, 24) for o in (0.0, 0.25)],
}
X.IDEAS = IDEAS

if __name__ == "__main__":
    jobs = [("base", 0, s) for s in X.SYMS] + [(k, i, s) for k in IDEAS for i in range(len(IDEAS[k])) for s in X.SYMS]
    with Pool(4) as p:
        res = p.map(X.job, jobs, chunksize=1)
    T = {(a, i, s): tr for a, i, s, tr in res}
    yrs = 6.58

    def line(lbl, key):
        out = f"{lbl:36s}"
        for s in X.SYMS:
            x = T[key + (s,)]; r, dd, mr = X.summ(x, yrs); out += f" {r:6.0f}R DD{dd:5.1f} MAR {mr:4.2f} n/wk {len(x)/343:3.1f} |"
        return out
    print(f"{'':36s} {'BTC':^34s}| {'ETH':^34s}")
    print(line("v2.1 baseline", ("base", 0)))
    for idea, vs in IDEAS.items():
        print(f"\n{idea}")
        for i, (lbl, _, _) in enumerate(vs):
            print(line("   " + lbl, (idea, i)))
        cands = [("base", 0)] + [(idea, i) for i in range(len(vs))]
        oos = {s: [] for s in X.SYMS}; picks = []
        for y in TESTS:
            ty = (pd.Timestamp(f"{y}-01-01") - pd.Timestamp(A)).days / 365.25
            sc = [sum(mar(stream(T[c + (s,)], A, f"{y}-01-01"), ty) for s in X.SYMS) for c in cands]
            best = cands[int(np.argmax(sc))]; picks.append("base" if best[0] == "base" else vs[best[1]][0])
            for s in X.SYMS:
                oos[s].append(stream(T[best + (s,)], f"{y}-01-01", f"{y+1}-01-01"))
        print(f"   walk-forward picks {dict(zip(TESTS, picks))}")
        for s in X.SYMS:
            r_w, dd_w, m_w = X.summ(pd.concat(oos[s]), 4.75)
            r_b, dd_b, m_b = X.summ(pd.concat([stream(T[("base", 0, s)], f"{y}-01-01", f"{y+1}-01-01") for y in TESTS]), 4.75)
            print(f"   {s} 2022-26 out of sample: {r_w:6.1f}R DD {dd_w:4.1f} MAR {m_w:4.2f}  vs v2.1 {r_b:6.1f}R DD {dd_b:4.1f} MAR {m_b:4.2f}")
