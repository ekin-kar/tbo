"""Monte Carlo of a $500 account, 24 months: reshuffle whole calendar months of real trades (keeps coins' same-month
correlation). Weights BTC 2x, ETH 1x, DOGE 0.5x, ADA 0.5x (sum 4 = same total as equal weights); shorts at half size.
'risk' = risk per trade of a 1x coin (BTC gets 2x that)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import pickle, sys
import numpy as np, pandas as pd
import common as C

ALL = pickle.load(open(C.D.CACHE / "portfolio_trades.pkl", "rb"))
W = {"BTCUSDT": 2.0, "ETHUSDT": 1.0, "DOGEUSDT": 0.5, "ADAUSDT": 0.5}
X = pd.concat([ALL[(s, 0.0003)].assign(w=w) for s, w in W.items()]).sort_values("exit_time")
X["u"] = X.R * X.w * np.where(X.dir < 0, 0.5, 1.0)                 # return per trade in units of 'risk'
X["m"] = X.exit_time.dt.to_period("M")
rng = np.random.default_rng(7)


def run(start, risk, paths=20000, months=24):
    blocks = [g.u.to_numpy() for _, g in X[X.exit_time >= start].groupby("m")]
    nb = len(blocks)
    res = dict(below100=0, below250=0, hit1k=0)
    dds, t1k, finals = [], [], []
    for _ in range(paths):
        eq = 500.0; pk = 500.0; mdd = 0.0; lo = 500.0; hit = None
        for mi in range(months):
            for u in blocks[rng.integers(nb)]:
                eq *= 1 + risk * u
                pk = max(pk, eq); mdd = max(mdd, 1 - eq / pk); lo = min(lo, eq)
            if hit is None and eq >= 1000:
                hit = mi + 1
        res["below100"] += lo < 100; res["below250"] += lo < 250
        if hit:
            res["hit1k"] += 1; t1k.append(hit)
        dds.append(mdd); finals.append(eq)
    dds = np.array(dds); finals = np.array(finals)
    return (f"risk {risk*100:4.2f}% (BTC {2*risk*100:4.2f}%) | below $100: {res['below100']/paths*100:5.2f}% | below $250: {res['below250']/paths*100:5.1f}% | "
            f"max drop: typical {np.median(dds)*100:4.0f}%, bad case (1 in 20) {np.quantile(dds,.95)*100:4.0f}% | "
            f"$1k reached within 2y: {res['hit1k']/paths*100:4.0f}%, typical {np.median(t1k) if t1k else float('nan'):4.0f} months | "
            f"after 2y: typical ${np.median(finals):,.0f}, bad case (1 in 10) ${np.quantile(finals,.1):,.0f}")


for start, lab in (("2022-01-01", "months from 2022-26 (no 2020-21 boom)"), ("2020-03-01", "months from 2020-26 (all)")):
    print(lab)
    for r in (0.0075, 0.01, 0.0125, 0.015, 0.02, 0.025, 0.03):
        print("  " + run(start, r))
