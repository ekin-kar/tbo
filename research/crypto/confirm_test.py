"""Pause from the moment a breakout is CONFIRMED (Oct 2026). Instead of waiting for a big winner to close, a trade counts
as confirmed once it has reached +k R (k = 1.5 / 2 / 3 / 5) or has been open H hours and is in profit. While / after another
trade is confirmed, new trades are skipped or halved (for its remaining life, or for D days from confirmation).
(1) How long do winners take to show? (2) How do trades entered while another is confirmed do? (3) Rules, scored per
period on the fixed-size R account and on the bot (ladder + cap) from $200. Live v2.6 trades (botsim); the +k R times
come from the 1m prices (tradepath, exact vs the engine)."""
import pickle, sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import botsim as BS
import tradepath as TP

X = BS.TR; N = len(X); D = 1440
P = pd.read_pickle(C.D.CACHE / f"trade_prices_{BS.TAG}.pkl")
TT = BS.T.merge(P, on=["sym", "entry_time"], how="left")
KS = (1.5, 2.0, 3.0, 5.0)
MF = C.D.CACHE / f"confirm_marks_{BS.TAG}.pkl"


def build_marks():
    out = np.full((N, len(KS)), np.inf)
    for i in range(N):
        r = TP.run(int(X[i, 5]), int(X[i, 3]), int(X[i, 0]), float(TT.entry[i]), float(TT.sl_dist[i]), marks=KS)
        for j, k in enumerate(KS):
            mt = r["marks"].get(k)
            if mt is not None and mt < X[i, 1]:
                out[i, j] = mt
    pickle.dump(out, open(MF, "wb"))
    return out


try:
    MK = pickle.load(open(MF, "rb"))
except FileNotFoundError:
    MK = None


def diagnose():
    R = X[:, 4]; e = X[:, 0]
    print("How long winners take to show (hours from entry, median / 75%):")
    for j, k in enumerate(KS):
        hit = np.isfinite(MK[:, j]); h = (MK[hit, j] - e[hit]) / 60
        fin = R[hit]
        print(f"  reached +{k}R: {hit.mean()*100:4.1f}% of trades, after {np.median(h):5.1f} / {np.percentile(h, 75):5.1f} h; "
              f"those end avg {fin.mean():+.2f}R, {np.mean(fin >= 5)*100:3.0f}% end >= +5R")
    print("Trades entered while ANOTHER coin's trade is open and already confirmed (+k R), avg R (n):")
    for pp, a, b in (("2020-23", "2020-03-01", "2024-01-01"), ("2024-26", "2024-01-01", "2026-10-01")):
        t0, t1 = pd.Timestamp(a).value // BS.MIN, pd.Timestamp(b).value // BS.MIN
        idx = np.nonzero((e >= t0) & (e < t1))[0]
        for j, k in enumerate(KS):
            for same in (True, False):
                flag = np.array([np.any((X[:, 5] != X[i, 5]) & (MK[:, j] <= e[i]) & (X[:, 1] > e[i]) &
                                        ((X[:, 3] == X[i, 3]) if same else True)) for i in idx])
                print(f"  {pp} +{k}R {'same dir' if same else 'any dir '}: with {R[idx][flag].mean():+.2f} ({flag.sum():3d}) | "
                      f"without {R[idx][~flag].mean():+.2f} ({(~flag).sum():3d})")


def run(x, ids, pol, g, compound=True, eq0=200.0):
    ev = []
    for n, i in enumerate(ids):
        e, xx, be, d, R, c = x[n]
        ev += [(e, 1, n), (max(be, e + 1e-3), 0, n), (max(xx, e + 2e-3), 2, n)]
    rank = {2: 0, 0: 1, 1: 2}
    ev.sort(key=lambda z: (z[0], rank[z[1]]))
    eq = eq0; opn = {}; pk = eq0; dd = 0.0
    pause = []                                         # (confirm time, until, dir) of confirmed trades (D-day windows)
    trades_open = {}                                   # n -> (coin, dir, confirm time)
    for t, kind, n in ev:
        e, xx, be, d, R, c = x[n]; c = int(c); i = ids[n]
        if kind == 1:
            m = 1.0
            if g:
                k = g["k"]; j = KS.index(k) if k in KS else None
                hit = False
                for nn, (cc, dd_, ct) in trades_open.items():          # still open and confirmed now
                    if cc != c and ct <= t and (not g.get("same") or dd_ == d):
                        hit = True
                if g.get("days"):                                      # or confirmed within the last D days (even if closed)
                    hit = hit or any(ct <= t < ct + g["days"] * D and (not g.get("same") or pd_ == d) and cc != c
                                     for ct, cc, pd_ in pause)
                    if g.get("only_window"):
                        hit = any(ct <= t < ct + g["days"] * D and (not g.get("same") or pd_ == d) and cc != c
                                  for ct, cc, pd_ in pause)
                if hit:
                    m = g["m"]
            trades_open[n] = (c, d, MK[i, KS.index(g["k"])] if g else np.inf)
            if g and g.get("days") and np.isfinite(trades_open[n][2]):
                pause.append((trades_open[n][2], c, d))
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
                opn[n] = [amt, False]
        elif kind == 0 and n in opn:
            opn[n][1] = True
        elif kind == 2:
            trades_open.pop(n, None)
            if n in opn:
                eq += opn.pop(n)[0] * R
        w = eq - sum(v[0] for v in opn.values() if not v[1])
        pk = max(pk, w); dd = max(dd, (pk - w) / pk)
    return eq, dd * 100


VARS = {"bot now": None}
for k in KS:
    for same in (True, False):
        tag = "same dir" if same else "any dir"
        for m in (0.0, 0.5):
            VARS[f"while another trade is >= +{k}R ({tag}): x{m}"] = dict(k=k, same=same, m=m)
        for days in (2, 4, 7):
            VARS[f"+{k}R confirmed -> x0.5 for {days}d from then ({tag})"] = dict(k=k, same=same, m=0.5, days=days, only_window=True)
            VARS[f"+{k}R confirmed -> skip for {days}d from then ({tag})"] = dict(k=k, same=same, m=0.0, days=days, only_window=True)


def job(name):
    g = VARS[name]; out = []
    for a, b in (("2020-03-01", "2024-01-01"), ("2024-01-01", "2026-10-01")):
        t0, t1 = pd.Timestamp(a).value // BS.MIN, pd.Timestamp(b).value // BS.MIN
        ids = np.nonzero((X[:, 0] >= t0) & (X[:, 0] < t1))[0]; xs = X[ids]
        f, dd = run(xs, ids, BS.flat_policy(2, 1, 1 / 3, cap_x=0), g, compound=False, eq0=100.0)
        lad = run(xs, ids, BS.bot_policy(), g)
        out.append((f - 100.0, dd, lad))
    return name, out


if __name__ == "__main__":
    if MK is None:
        MK = build_marks()
    diagnose()
    with Pool(3) as p:
        res = p.map(job, list(VARS))
    pickle.dump(res, open(C.D.CACHE / "confirm_test.pkl", "wb"))
    b = res[0][1]; r_ = lambda o: o[0] / o[1]
    print(f"\n{'rule':58s} | fixed R account net/drop 2020-23 | 2024-26          | bot ladder $200: 2020-23 | 2024-26")
    for n, o in sorted(res, key=lambda z: -min(r_(z[1][0]) / r_(b[0]), r_(z[1][1]) / r_(b[1]))):
        print(f"{n[:58]:58s} | {o[0][0]:5.0f} {o[0][1]:4.1f}% x{r_(o[0])/r_(b[0]):.2f} | {o[1][0]:5.0f} {o[1][1]:4.1f}% x{r_(o[1])/r_(b[1]):.2f} | "
              f"${o[0][2][0]:>9,.0f} {o[0][2][1]:4.1f}% | ${o[1][2][0]:>7,.0f} {o[1][2][1]:4.1f}%", flush=True)
