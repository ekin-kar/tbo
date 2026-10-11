"""Exit ratchet test (Oct 2026): how many trades reached +3.5R or more but closed below +1R, and what a profit lock /
trailing stop once a trade is far in profit would do. Same 1m engine and costs as tradepath.py (validated exact).
Lock rules (on top of the bot's stop / breakeven / 120 h exit; the stop only ever moves up):
  trail T after +A: once the best price has reached +A R, stop = best - T R (best of the minutes before)
  lock L after +A: once +A R reached, stop = entry + L R (one step)"""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import pickle, sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import botsim as BS
import tradepath as TP
from gate_test import E, X, BE, CI, DIR, EP, DIST, R0, N

MIN = BS.MIN


def run(k, rule):
    ci, d, t_e, p_e, dist = int(CI[k]), int(DIR[k]), int(E[k]), float(EP[k]), float(DIST[k])
    m = TP.m1(ci); j0 = int(np.searchsorted(m["t"], t_e)); j1 = min(len(m["t"]), j0 + 7200 + 1)
    o, h, l, c, t = m["o"][j0:j1], m["h"][j0:j1], m["l"][j0:j1], m["c"][j0:j1], m["t"][j0:j1]
    fav = (h if d > 0 else -l).astype(float); adv = (l if d > 0 else -h).astype(float); op = (o if d > 0 else -o).astype(float)
    ep = d * p_e
    stop = np.full(len(t), ep - dist)                                  # sign-adjusted stop in force during each minute
    fb = fav.copy(); fb[0] = -np.inf                                 # the fill minute does not count (as the engine)
    best_prev = np.maximum.accumulate(np.r_[-np.inf, fb[:-1]])        # best price of the minutes BEFORE each minute
    be_on = best_prev[1:] >= ep + 1.5 * dist
    stop[1:] = np.where(be_on, np.maximum(stop[1:], ep), stop[1:])
    if rule:
        kind, A, v = rule
        on = best_prev >= ep + A * dist
        lvl = best_prev - v * dist if kind == "trail" else np.full(len(t), ep + v * dist)
        stop = np.where(on, np.maximum(stop, lvl), stop)
    hit = np.nonzero(adv <= stop)[0]
    if len(hit):
        k_x = hit[0]; xp = d * min(stop[k_x], op[k_x]) if k_x > 0 else d * stop[k_x]
    else:
        k_x = len(t) - 1; xp = float(o[k_x])
    sl = TP.SLIP[BS.COINS[ci]]
    cost = (C.TAKER + sl) * p_e + (C.TAKER + sl) * xp + C.FUNDING_8H * (int(t[k_x]) - t_e) / 60 / 8 * p_e
    mfe = (fav[:k_x + 1].max() - ep) / dist
    return float(((xp - p_e) * d - cost) / dist), int(t[k_x]), float(mfe)


RULES = {"none (bot now)": None}
for A in (3.5, 4.0, 5.0):
    for T in (1.0, 1.5, 2.0, 3.0):
        if T < A:
            RULES[f"trail {T}R after +{A}R"] = ("trail", A, T)
for A, L in ((3.5, 1.5), (4.0, 2.0), (4.0, 1.0), (5.0, 3.0)):
    RULES[f"lock +{L}R after +{A}R"] = ("lock", A, L)


def job(name):
    rule = RULES[name]
    return name, [run(k, rule) for k in range(N)]


def account(out):
    """botsim with each trade's new R / exit time; ladder from $200 (2020 and 2024 runs) and a fixed-size account."""
    x = BS.TR.copy()
    x[:, 4] = [o[0] for o in out]; x[:, 1] = [o[1] for o in out]
    res = {}
    for key, a in (("2020", "2020-03-01"), ("2024", "2024-01-01")):
        t0 = pd.Timestamp(a).value // MIN
        xs = x[x[:, 0] >= t0]
        r = BS.run(xs, BS.bot_policy(), 200.0)
        f = BS.run(xs, BS.flat_policy(5, 2.5, 0.83), 100.0)            # (compounding flat 5% for a second view)
        res[key] = (r["final"], r["dd"], f["final"], f["dd"])
    return res


if __name__ == "__main__":
    with Pool(3) as p:
        res = dict(p.map(job, list(RULES)))
    pickle.dump(res, open(C.D.CACHE / "ratchet.pkl", "wb"))
    base = res["none (bot now)"]
    check = np.abs(np.array([o[0] for o in base]) - R0)
    print(f"engine check: |R - backtest R| max {check.max():.4f} over {N} trades")
    mfe = np.array([o[2] for o in base]); R = R0
    per = np.where(E < pd.Timestamp("2024-01-01").value // MIN, "2020-23", "2024-26")
    for pp in ("2020-23", "2024-26"):
        s = per == pp
        g = s & (mfe >= 3.5)
        print(f"{pp}: {s.sum()} trades, {g.sum()} reached +3.5R; of those {(g & (R < 1)).sum()} closed below +1R "
              f"(avg exit {R[g & (R < 1)].mean():+.2f}R, gave back avg {(mfe - R)[g & (R < 1)].mean():.1f}R), "
              f"{(g & (R >= 3)).sum()} closed >= +3R; trades >= +5R: {(s & (R >= 5)).sum()} (sum {R[s & (R >= 5)].sum():.0f}R)")
    print(f"\n{'rule':26s} | net R 2020-23 / 2024-26 | >=5R runners 24-26 | ladder $200 from 2020: final, worst drop | from 2024: final, drop | flat 5% from 2024: final, drop")
    for name, out in res.items():
        Rn = np.array([o[0] for o in out]); acc = account(out)
        print(f"{name:26s} | {Rn[per=='2020-23'].sum():7.0f} {Rn[per=='2024-26'].sum():7.0f} | {(Rn[per=='2024-26'] >= 5).sum():3d} "
              f"| ${acc['2020'][0]:>11,.0f} {acc['2020'][1]:5.1f}% | ${acc['2024'][0]:>8,.0f} {acc['2024'][1]:5.1f}% | ${acc['2024'][2]:>8,.0f} {acc['2024'][3]:5.1f}%", flush=True)
