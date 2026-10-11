"""Bleeds after big profits (Oct 2026). (1) Is the period after a big win worse than any other period? (2) Rules that
cut / pause new trades after a big profit or once a bleed starts, using only what the bot knows at entry time.
Live v2.6 trades (botsim). Scored per period (2020-23, 2024-26) on a fixed-size R account (BTC 2, ETH 1, alts 1/3,
shorts x0.5; no cap) and on the bot itself (ladder + cap) from $200."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import botsim as BS
import tradepath as TP

WT = np.array([2, 1, 1 / 3, 1 / 3, 1 / 3])
D = 1440
X = BS.TR


def diagnose():
    x = X; ex = x[:, 1]; R = x[:, 4]; w = WT[x[:, 5].astype(int)] * np.where(x[:, 3] < 0, 0.5, 1); u = R * w
    print("Units of R (fixed account) from trades ENTERED in the next N days:")
    for pp, a, b in (("2020-23", "2020-03-01", "2024-01-01"), ("2024-26", "2024-01-01", "2026-10-01")):
        t0, t1 = pd.Timestamp(a).value // BS.MIN, pd.Timestamp(b).value // BS.MIN
        s = (x[:, 0] >= t0) & (x[:, 0] < t1)
        for thr in (5, 10):
            big = np.nonzero(s & (R >= thr))[0]
            for days in (7, 14):
                after = [u[(x[:, 0] >= ex[k]) & (x[:, 0] < ex[k] + days * D)].sum() for k in big]
                rng = np.random.default_rng(1); anyw = []
                for t in rng.integers(t0, t1 - days * D, 3000):
                    anyw.append(u[(x[:, 0] >= t) & (x[:, 0] < t + days * D)].sum())
                after, anyw = np.array(after), np.array(anyw)
                print(f"  {pp} after a >= +{thr}R winner closes ({len(big)} cases), next {days:2d} d: avg {after.mean():+5.2f}, losing {np.mean(after < 0)*100:3.0f}% "
                      f"| any {days:2d} d window: avg {anyw.mean():+5.2f}, losing {np.mean(anyw < 0)*100:3.0f}%")


def run(x, pol, rule, compound=True, eq0=200.0):
    """botsim.run with a size multiplier from `rule` at each entry (0 = skip)."""
    ev = []
    for i, (e, xx, be, d, R, c) in enumerate(x):
        ev += [(e, 1, i), (max(be, e + 1e-3), 0, i), (max(xx, e + 2e-3), 2, i)]
    rank = {2: 0, 0: 1, 1: 2}
    ev.sort(key=lambda z: (z[0], rank[z[1]]))
    eq = eq0; opn = {}; pk = eq0; dd = 0.0
    closed = []                                     # (exit time, R, coin, equity after)
    st = dict(until=-1, mult=1.0)
    for t, kind, i in ev:
        e, xx, be, d, R, c = x[i]; c = int(c)
        if kind == 1:
            m = rule(t, c, closed, eq, st) if rule else 1.0
            if m <= 0:
                continue
            base = eq if compound else eq0
            fr, rk, cap = BS.row_at(pol, base)
            amt = base * rk[c] / 100 * (pol["smult"] if d < 0 else 1.0) * m
            if cap > 0 and c not in pol["exempt"]:
                room = cap / 100 * base - sum(v[0] for v in opn.values() if not v[1])
                if amt > room:
                    amt = room if room > pol["minf"] * amt else 0.0
            if amt > 0:
                opn[i] = [amt, False]
        elif kind == 0 and i in opn:
            opn[i][1] = True
        elif kind == 2 and i in opn:
            a = opn.pop(i)[0]; eq += a * R
            closed.append((t, R, c, eq))
        w = eq - sum(v[0] for v in opn.values() if not v[1])
        pk = max(pk, w); dd = max(dd, (pk - w) / pk)
    return eq, dd * 100


# ── rules: f(t, coin, closed, equity, state) -> size multiplier ──
def after_big(thr, days, m, same_coin=False):
    def f(t, c, closed, eq, st):
        for xt, R, cc, _ in reversed(closed):
            if t - xt > days * D:
                break
            if R >= thr and (not same_coin or cc == c):
                return m
        return 1.0
    return f


def equity_jump(pct, look, days, m):
    def f(t, c, closed, eq, st):
        if t < st["until"]:
            return m
        past = [e for xt, _, _, e in closed if xt <= t - look * D]
        ref = past[-1] if past else None
        if ref and eq >= ref * (1 + pct / 100):
            st["until"] = t + days * D; return m
        return 1.0
    return f


def below_ma(n, m):
    def f(t, c, closed, eq, st):
        if len(closed) < n:
            return 1.0
        ma = np.mean([e for *_, e in closed[-n:]])
        return m if eq < ma else 1.0
    return f


def bleed_started(lossR, days, m):
    def f(t, c, closed, eq, st):
        s = sum(R for xt, R, _, _ in closed if t - xt <= days * D)
        return m if s <= -lossR else 1.0
    return f


def after_big_then_losses(thr, days, k, m):
    """after a >= thr winner closed in the last `days`, once k losses closed since it: x m"""
    def f(t, c, closed, eq, st):
        n = 0
        for xt, R, cc, _ in reversed(closed):
            if t - xt > days * D:
                break
            if R >= thr:
                return m if n >= k else 1.0
            if R < -0.5:
                n += 1
        return 1.0
    return f


def btc_move(pct, look, m):
    def f(t, c, closed, eq, st):
        r = TP.price(0, t) / TP.price(0, t - look * D) - 1
        return m if abs(r) >= pct / 100 else 1.0
    return f


RULES = {"bot now": None}
for thr in (5, 10):
    for days in (3, 7, 14):
        for m in (0.0, 0.5):
            RULES[f"after a +{thr}R win: x{m} for {days}d (all coins)"] = after_big(thr, days, m)
    RULES[f"after a +{thr}R win: that coin x0 for 7d"] = after_big(thr, 7, 0.0, same_coin=True)
for pct, look in ((30, 14), (50, 14), (100, 30)):
    for days in (7, 14):
        RULES[f"account +{pct}% in {look}d: x0.5 for {days}d"] = equity_jump(pct, look, days, 0.5)
for n in (10, 20, 50):
    RULES[f"account below avg of last {n} trades: x0.5"] = below_ma(n, 0.5)
    RULES[f"account below avg of last {n} trades: skip"] = below_ma(n, 0.0)
for lr, days in ((3, 7), (5, 7), (5, 14)):
    RULES[f"bleed: last {days}d <= -{lr}R closed: x0.5"] = bleed_started(lr, days, 0.5)
for k in (2, 3):
    RULES[f"after +5R win then {k} losses (14d): pause"] = after_big_then_losses(5, 14, k, 0.0)
for pct, look in ((20, 14), (30, 14)):
    RULES[f"BTC moved > {pct}% in {look}d: x0.5"] = btc_move(pct, look, 0.5)


def job(name):
    rule = RULES[name]; out = []
    for a, b in (("2020-03-01", "2024-01-01"), ("2024-01-01", "2026-10-01")):
        t0, t1 = pd.Timestamp(a).value // BS.MIN, pd.Timestamp(b).value // BS.MIN
        xs = X[(X[:, 0] >= t0) & (X[:, 0] < t1)]
        f, dd = run(xs, BS.flat_policy(2, 1, 1 / 3, cap_x=0), rule, compound=False, eq0=100.0)   # fixed R account (1 unit = 1%)
        lad = run(xs, BS.bot_policy(), rule)
        out.append((f - 100.0, dd, lad))
    lad20 = run(X[X[:, 0] >= pd.Timestamp("2020-03-01").value // BS.MIN], BS.bot_policy(), rule)
    return name, out, lad20


if __name__ == "__main__":
    diagnose()
    with Pool(3) as p:
        res = p.map(job, list(RULES))
    b = res[0][1]
    r_ = lambda o: o[0] / o[1]
    print(f"\n{'rule':46s} | fixed R account net/drop 2020-23 | 2024-26        | bot ladder $200: 2020-23 final, drop | 2024-26 final, drop | from 2020 to now")
    for n, o, l20 in res:
        print(f"{n:46s} | {o[0][0]:6.0f} {o[0][1]:4.1f}% x{r_(o[0])/r_(b[0]):.2f} | {o[1][0]:6.0f} {o[1][1]:4.1f}% x{r_(o[1])/r_(b[1]):.2f} | "
              f"${o[0][2][0]:>9,.0f} {o[0][2][1]:4.1f}% | ${o[1][2][0]:>7,.0f} {o[1][2][1]:4.1f}% | ${l20[0]:>10,.0f} {l20[1]:4.1f}%", flush=True)
