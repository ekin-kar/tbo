"""Open-risk cap study on the live v2.6 trades (Oct 2026). (1) What the cap blocks: per coin with / without the cap,
and the trades it skips or shrinks split by BTC's state at that moment (BTC in a fresh trade same / opposite direction,
how far BTC's trade is in profit, BTC's 7-day move). (2) Cap variants. Scored per period (2020-23, 2024-26) on a
fixed-size account (no compounding: BTC 2, ETH 1, alts 1/3 units, shorts x0.5, cap in the same units) and on the bot
(ladder from $200)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import botsim as BS
import tradepath as TP

X = BS.TR
P = pd.read_pickle(C.D.CACHE / f"trade_prices_{BS.TAG}.pkl")
TT = BS.T.merge(P, on=["sym", "entry_time"], how="left")
EP, DIST = TT.entry.to_numpy(), TT.sl_dist.to_numpy()
D = 1440


def btc_mom(t, days=7):
    return TP.price(0, t) / TP.price(0, t - days * D) - 1


def run(x, ids, pol, g, compound=True, eq0=200.0, log=None):
    ev = []
    for n in range(len(x)):
        e, xx, be, d, R, c = x[n]
        ev += [(e, 1, n), (max(be, e + 1e-3), 0, n), (max(xx, e + 2e-3), 2, n)]
    rank = {2: 0, 0: 1, 1: 2}
    ev.sort(key=lambda z: (z[0], rank[z[1]]))
    eq = eq0; opn = {}; pk = eq0; dd = 0.0
    for t, kind, n in ev:
        e, xx, be, d, R, c = x[n]; c = int(c); i = ids[n]
        if kind == 1:
            base = eq if compound else eq0
            fr, rk, cap = BS.row_at(pol, base)
            full = base * rk[c] / 100 * (pol["smult"] if d < 0 else 1.0)
            amt = full; cap = cap * g.get("cap_x", 1.0)
            exempt = c in pol["exempt"] or c in g.get("exempt_more", ())
            if g.get("off_mom") and abs(btc_mom(t)) >= g["off_mom"] and np.sign(btc_mom(t)) == d:
                exempt = True                                            # BTC moving strongly in this direction: no cap
            if cap > 0 and not exempt and not g.get("nocap"):
                used = 0.0
                for v in opn.values():
                    if v["be"]:
                        continue
                    if g.get("same_dir") and v["d"] != d:
                        continue
                    if g.get("btc_free_at") is not None and v["c"] == 0:   # BTC's risk stops counting once it is +k R
                        prog = v["d"] * (TP.price(0, t) - v["ep"]) / v["dist"]
                        if prog >= g["btc_free_at"]:
                            continue
                    used += v["amt"]
                room = cap / 100 * base - used
                if amt > room:
                    amt = room if room > g.get("minf", pol["minf"]) * amt else 0.0
            if log is not None and c != 0:
                st = "none"; prog = np.nan
                for v in opn.values():
                    if v["c"] == 0 and not v["be"]:
                        st = "same" if v["d"] == d else "opp"; prog = v["d"] * (TP.price(0, t) - v["ep"]) / v["dist"]
                log.append((i, c, d, R, full, amt, st, prog, btc_mom(t)))
            if amt > 0:
                opn[n] = dict(amt=amt, be=False, d=d, c=c, ep=EP[i], dist=DIST[i])
        elif kind == 0 and n in opn:
            opn[n]["be"] = True
        elif kind == 2 and n in opn:
            eq += opn.pop(n)["amt"] * R
        w = eq - sum(v["amt"] for v in opn.values() if not v["be"])
        pk = max(pk, w); dd = max(dd, (pk - w) / pk)
    return eq, dd * 100


FIX = BS.ladder_policy([(0, 2, 1, 1 / 3)], cap_x=1.1)                     # fixed account: BTC 2 units, cap 2.2 units


def window(a, b):
    t0, t1 = pd.Timestamp(a).value // BS.MIN, pd.Timestamp(b).value // BS.MIN
    ids = np.nonzero((X[:, 0] >= t0) & (X[:, 0] < t1))[0]
    return X[ids], ids


def diagnose():
    for pp, a, b in (("2020-23", "2020-03-01", "2024-01-01"), ("2024-26", "2024-01-01", "2026-10-01")):
        xs, ids = window(a, b); log = []
        run(xs, ids, FIX, {}, compound=False, eq0=100.0, log=log)
        L = pd.DataFrame(log, columns=["i", "c", "d", "R", "full", "amt", "btc", "prog", "mom"])
        L["w"] = np.where(L.d < 0, 0.5, 1.0); L["kind"] = np.where(L.amt <= 0, "skipped", np.where(L.amt < L.full * 0.995, "cut", "full"))
        print(f"\n=== {pp}: ETH / alt trades by what the cap did (R per trade, n) ===")
        print(L.groupby("kind").R.agg(n="size", avgR="mean", sumR="sum", big=lambda r: (r >= 5).sum()).round(2).to_string())
        print("   lost R from cap (units, fixed account): skipped trades "
              f"{(L[L.kind=='skipped'].R * L[L.kind=='skipped'].full).sum():+.1f}, cut part {((L.full - L.amt) * L.R)[L.kind=='cut'].sum():+.1f}")
        print("   by coin, units with cap vs without cap:")
        for c in range(1, 5):
            s = L[L.c == c]
            print(f"     {BS.COINS[c][:-4]}: with cap {(s.amt * s.R).sum():+6.1f}, without {(s.full * s.R).sum():+6.1f} ({len(s)} trades)")
        blk = L[L.kind != "full"]
        print("   skipped / cut trades by BTC state at that moment (avg R, n):")
        for st in ("same", "opp"):
            s = blk[blk.btc == st]
            print(f"     BTC fresh trade {st:4s}: {s.R.mean():+.2f} ({len(s)})")
        s = blk[blk.btc == "same"]
        for lo, hi in ((-9, 0), (0, 0.5), (0.5, 1.0), (1.0, 9)):
            q = s[(s.prog >= lo) & (s.prog < hi)]
            print(f"     BTC same dir, BTC trade at {lo:+.1f}..{hi:+.1f}R: {q.R.mean():+.2f} ({len(q)})")
        mm = blk.mom * blk.d
        for lo, hi in ((-9, 0), (0, 0.05), (0.05, 0.10), (0.10, 9)):
            q = blk[(mm >= lo) & (mm < hi)]
            print(f"     BTC 7d move in trade direction {lo*100:+.0f}..{hi*100:+.0f}%: {q.R.mean():+.2f} ({len(q)})")
        free = L[(L.btc == "same") & (L.kind == "full")]
        print(f"   for comparison, full-size trades while BTC fresh same dir: {free.R.mean():+.2f} ({len(free)}); "
              f"no BTC fresh trade: {L[L.btc=='none'].R.mean():+.2f} ({(L.btc=='none').sum()})")


VARS = {"bot now (cap 1.1x BTC, BTC exempt)": {}, "no cap": dict(nocap=True)}
for cx in (0.8, 0.9, 1.0, 1.2, 1.3, 1.5):
    VARS[f"cap {cx}x"] = dict(cap_x=cx / 1.1)
VARS["ETH exempt too"] = dict(exempt_more=(1,))
VARS["only same-direction risk counts"] = dict(same_dir=True)
for k in (0.5, 1.0):
    VARS[f"BTC risk stops counting at BTC +{k}R"] = dict(btc_free_at=k)
for mm in (0.05, 0.08, 0.12):
    VARS[f"no cap if BTC 7d move >= {mm*100:.0f}% in trade dir"] = dict(off_mom=mm)
for mf in (0.0, 0.5, 0.99):
    VARS[f"min fraction to trade {mf}"] = dict(minf=mf)
VARS["same-dir only + BTC free at +1R"] = dict(same_dir=True, btc_free_at=1.0)


def job(name):
    g = VARS[name]; out = []
    for a, b in (("2020-03-01", "2024-01-01"), ("2024-01-01", "2026-10-01")):
        xs, ids = window(a, b)
        f, dd = run(xs, ids, FIX, g, compound=False, eq0=100.0)
        L_ = run(xs, ids, BS.bot_policy(), g)
        out.append((f - 100.0, dd, L_))
    xs, ids = window("2020-03-01", "2026-10-01")
    return name, out, run(xs, ids, BS.bot_policy(), g)


if __name__ == "__main__":
    diagnose()
    with Pool(3) as p:
        res = p.map(job, list(VARS))
    b = res[0][1]; r_ = lambda o: o[0] / o[1]
    print(f"\n{'variant':46s} | fixed acct 2020-23: net, drop, ret/drop (x now) | 2024-26          | ladder $200 2020-23 | 2024-26 | 2020-now")
    for n, o, full in res:
        print(f"{n:46s} | {o[0][0]:6.0f} {o[0][1]:4.1f}% x{r_(o[0])/r_(b[0]):.2f} | {o[1][0]:6.0f} {o[1][1]:4.1f}% x{r_(o[1])/r_(b[1]):.2f} | "
              f"${o[0][2][0]:>9,.0f} {o[0][2][1]:4.1f}% | ${o[1][2][0]:>7,.0f} {o[1][2][1]:4.1f}% | ${full[0]:>10,.0f} {full[1]:4.1f}%", flush=True)
