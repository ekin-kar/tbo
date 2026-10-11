"""Open-risk cap as the bot can run it, and BTC 7.5% risk sets (Oct 2026).
The bot sizes its stop-entry order at the 4h close BEFORE it fills, so the cap is checked against the trades open (and
not yet at breakeven) at that close, not at the fill as in sizing_v3. Timing modes:
  fill        cap checked at the fill (sizing_v3, ideal)
  place       cap checked when the order is placed at the 4h close (what the bot does)
  place_trim  as place, and at the fill any excess over the cap is closed at market (skip if < 25% would remain)
Then risk sets with BTC at 7.5%: worst drop on history (2020-23, 2024-26, 2022-26) and in 2,000 block-bootstrap
2-year journeys from $250 (random 4-week blocks of real trades, 2022-26)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import pickle, sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C

ALL = pickle.load(open(C.D.CACHE / "portfolio_trades_v24.pkl", "rb"))
COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
T = pd.concat([ALL[(s, 0.0003)] for s in COINS]).sort_values("entry_time").reset_index(drop=True)
MIN = 60_000_000_000
m_ = lambda col: T[col].values.astype("datetime64[m]").astype(np.int64)
TR = np.c_[m_("entry_time"), m_("exit_time"), m_("be_time"), T.dir.values, T.R.values, T.sym.map({s: i for i, s in enumerate(COINS)}).values]
FEE = 0.0005 + 0.0003           # taker fee + slippage on a trimmed part (fraction of its notional)


def sim(x, risk, cap=0.0, exempt=(0,), mode="fill", eq0=200.0, end=None, minf=0.25):
    """x: rows (entry, exit, be, dir, R, coin) in minutes. risk: per-coin fraction. cap: fraction of equity (0 = off).
    Returns final, worst drop % (open risk not at breakeven counted as lost), time series (t, balance, worst)."""
    ev = []
    for i, (e, xx, be, d, R, c) in enumerate(x):
        p = e - e % 240                                          # the 4h close where the bot placed the order
        ev += [(p, 3, i), (e, 1, i), (max(be, e + 1e-3), 0, i), (max(xx, e + 2e-3), 2, i)]
    rank = {2: 0, 0: 1, 3: 2, 1: 3}                               # same minute: exits, breakevens, placements, fills
    ev.sort(key=lambda z: (z[0], rank[z[1]]))
    eq = eq0; opn = {}; pend = {}; pk = eq0; dd = 0.0; trims = skips = 0
    for t, kind, i in ev:
        if end is not None and t > end:
            break
        e, xx, be, d, R, c = x[i]; c = int(c)
        if kind == 3 or (kind == 1 and mode == "fill"):
            amt = eq * risk[c] * (0.5 if d < 0 else 1.0)
            if cap and c not in exempt:
                room = cap * eq - sum(v[0] for v in opn.values() if not v[1])
                if amt > room:
                    if room > minf * amt:
                        amt = room
                    else:
                        amt = 0.0
            if kind == 3:
                pend[i] = amt
                continue
        elif kind == 1:
            amt = pend.pop(i, 0.0)
            if amt > 0 and mode == "place_trim" and cap and c not in exempt:
                room = cap * eq - sum(v[0] for v in opn.values() if not v[1])
                if amt > room:
                    cut = amt - room if room > minf * amt else amt
                    eq -= cut * 2 * FEE / 0.02             # fees in and out on the trimmed part (stop ~2% away)
                    amt -= cut; trims += 1
        if kind == 1:
            if amt <= 0:
                skips += 1; continue
            opn[i] = [amt, False]
        elif kind == 0 and i in opn:
            opn[i][1] = True
        elif kind == 2 and i in opn:
            eq += opn.pop(i)[0] * R
        if kind != 3:
            w = eq - sum(v[0] for v in opn.values() if not v[1])
            pk = max(pk, w); dd = max(dd, (pk - w) / pk)
    return eq, dd * 100, trims, skips


def hist(args):
    name, risk, cap, mode = args
    out = [name]
    for a, b in (("2020-03-01", "2024-01-01"), ("2024-01-01", "2026-10-01"), ("2022-01-01", "2026-10-01")):
        t0, t1 = pd.Timestamp(a).value // MIN, pd.Timestamp(b).value // MIN
        x = TR[(TR[:, 0] >= t0) & (TR[:, 0] < t1)]
        f, dd, tr_, sk = sim(x, risk, cap, mode=mode)
        mo = (t1 - t0) / 1440 / 30.44
        out.append((f, ((f / 200) ** (1 / mo) - 1) * 100, dd))
    return out


def hist_kw(kw, risk=None):
    """(final, %/month, worst drop) for 2020-23, 2024-26, 2022-26 with sim keyword arguments kw (fill-time rule)."""
    out = []
    for a, b in (("2020-03-01", "2024-01-01"), ("2024-01-01", "2026-10-01"), ("2022-01-01", "2026-10-01")):
        t0, t1 = pd.Timestamp(a).value // MIN, pd.Timestamp(b).value // MIN
        f, dd, _, _ = sim(TR[(TR[:, 0] >= t0) & (TR[:, 0] < t1)], R(5, 2.5, 0.83) if risk is None else risk, **kw)
        out.append((f, ((f / 200) ** (1 / ((t1 - t0) / 1440 / 30.44)) - 1) * 100, dd))
    return out


BLK = 28 * 1440


def journey(args):
    seed, risk, cap, mode = args
    r = np.random.default_rng(seed)
    t0, t1 = pd.Timestamp("2022-01-01").value // MIN, pd.Timestamp("2026-10-01").value // MIN
    pool = TR[(TR[:, 0] >= t0) & (TR[:, 0] < t1)]
    rows = []
    for k in range(int(np.ceil(24 * 30.44 * 1440 / BLK))):
        u = t0 + r.integers(0, (t1 - BLK - t0) // 240) * 240      # block starts on a 4h boundary (keeps placement times)
        s = pool[(pool[:, 0] >= u) & (pool[:, 0] < u + BLK)].copy()
        s[:, :3] += k * BLK - u
        rows.append(s)
    f, dd, _, _ = sim(np.concatenate(rows), risk, cap, mode=mode, eq0=250.0, end=24 * 30.44 * 1440)
    return f, dd


def R(btc, eth, alt):
    return np.array([btc, eth, alt, alt, alt]) / 100


if __name__ == "__main__":
    part = sys.argv[1] if len(sys.argv) > 1 else "all"
    NOW = R(5, 2.5, 0.83)
    with Pool(4) as p:
        if part in ("all", "timing"):
            jobs = [("no cap", NOW, 0, "fill")]
            for cap in (0.045, 0.055, 0.065):
                for mode in ("fill", "place", "place_trim"):
                    jobs.append((f"cap {cap*100:.1f}% BTC exempt, {mode}", NOW, cap, mode))
            jobs.append(("cap 5.5% ALL coins, place", NOW, 0.055, "place"))
            print("=== timing: current risk (BTC 5 / ETH 2.5 / alts 0.83), $200 ===")
            print(f"{'':42s} | 2020-23 %/mo drop | 2024-26 $200->  %/mo  drop | 2022-26 %/mo drop")
            for n, a, h, w in p.map(hist, [(n, r, c, m) for n, r, c, m in jobs]):
                print(f"{n:42s} | {a[1]:6.2f} {a[2]:5.1f}% | ${h[0]:>8,.0f} {h[1]:6.2f} {h[2]:5.1f}% | {w[1]:6.2f} {w[2]:5.1f}%", flush=True)
        if part in ("all", "btc75"):
            sets = {"now 5 / 2.5 / 0.83": R(5, 2.5, 0.83), "7.5 / 2.5 / 0.83": R(7.5, 2.5, 0.83),
                    "7.5 / 1.5 / 0.5": R(7.5, 1.5, 0.5), "7.5 / 1.25 / 0.42": R(7.5, 1.25, 0.42),
                    "7.5 / 3.75 / 1.25 (all x1.5)": R(7.5, 3.75, 1.25)}
            jobs = []
            for sn, r in sets.items():
                jobs.append((f"{sn}, no cap", r, 0, "place"))
                for cap in (0.055, 0.075, 0.0825):
                    jobs.append((f"{sn}, cap {cap*100:.2f}% (BTC exempt)", r, cap, "place"))
            print("\n=== BTC 7.5% risk sets (cap checked at order placement, as the bot), $200 ===")
            print(f"{'':52s} | 2020-23 %/mo drop | 2024-26 $200->  %/mo  drop | 2022-26 %/mo drop")
            res = p.map(hist, jobs)
            for n, a, h, w in res:
                print(f"{n:52s} | {a[1]:6.2f} {a[2]:5.1f}% | ${h[0]:>8,.0f} {h[1]:6.2f} {h[2]:5.1f}% | {w[1]:6.2f} {w[2]:5.1f}%", flush=True)
            pickle.dump(res, open(C.D.CACHE / "sizing_v4_hist.pkl", "wb"))
        if part in ("all", "mc"):
            picks = [("now 5/2.5/0.83 + cap 5.5%", R(5, 2.5, 0.83), 0.055), ("7.5/2.5/0.83 + cap 8.25%", R(7.5, 2.5, 0.83), 0.0825),
                     ("7.5/2.5/0.83 + cap 7.5%", R(7.5, 2.5, 0.83), 0.075), ("7.5/1.5/0.5 + cap 8.25%", R(7.5, 1.5, 0.5), 0.0825),
                     ("7.5/3.75/1.25 + cap 8.25%", R(7.5, 3.75, 1.25), 0.0825), ("7.5/2.5/0.83 no cap", R(7.5, 2.5, 0.83), 0)]
            print("\n=== 2,000 two-year journeys from $250 (4-week blocks of 2022-26 trades), cap at placement ===")
            print(f"{'':30s} | worst drop: median  1 in 4  1 in 10  1 in 20 | end: median  P(>=10k) P(>=20k) P(<$100)")
            mc = {}
            for n, r, cap in picks:
                z = np.array(p.map(journey, [(s, r, cap, "place") for s in range(2000)], chunksize=50))
                mc[n] = z; f, dd = z[:, 0], z[:, 1]
                print(f"{n:30s} | {np.median(dd):10.0f}% {np.percentile(dd, 75):6.0f}% {np.percentile(dd, 90):7.0f}% {np.percentile(dd, 95):7.0f}%"
                      f" | ${np.median(f):>9,.0f} {(f >= 1e4).mean()*100:6.0f}% {(f >= 2e4).mean()*100:6.0f}% {(f < 100).mean()*100:6.0f}%", flush=True)
            pickle.dump(mc, open(C.D.CACHE / "sizing_v4_mc.pkl", "wb"))
