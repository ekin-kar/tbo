"""reports/breakout_support.html: can open interest / positioning data support the 4h breakout? The 51-coin study
(research/crypto/studies/oi_support.py: build, eval, luck must have run) - every idea, the six gates, the one that
passed (OI value low vs its last 90 days -> no order), its plateau, luck test, untouched coins and the money test."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]
import json, pickle
import numpy as np, pandas as pd
import common as C
import oi_support as O
from multiprocessing import Pool

P = [p[0] for p in O.PERIODS]
WIN = dict(fam="C", p=dict(meas="oi", side="low", W=90, p=0.8))
FAMS = {
    "A": "Price moved the trade's way while open interest fell (a move with no new money)",
    "A+": "Coil: price flat while open interest built up",
    "B": "Exit soon after the fill when open interest falls (a short / long squeeze, not new money)",
    "C": "Open interest (or OI vs trading volume) at a high / low for the coin",
    "D": "The coin's open interest vs the whole market's",
    "D+": "The coin's open interest growing faster than the market's",
    "E": "Long/short ratio extremes (all accounts, top-trader accounts, top-trader positions)",
    "F": "A forced-liquidation flush in the last hours",
    "G": "Tired setup: level touched many times, or very quiet candles before the break",
}
MODES = {"skip": "skip the order", "half": "half size", "up": "1.5x size", "exit": "early exit"}


def flagged(R, vid):
    out = {}
    for g in ("DEV12", "OUR5", "BTC", "HOLD_BIG", "HOLD_SMALL"):
        for nm, a, b in O.PERIODS:
            a_, b_ = pd.Timestamp(a).value // 60_000_000_000, pd.Timestamp(b).value // 60_000_000_000
            f, r = [], []
            for s in O.GROUPS[g][0]:
                t = R[s]["base"]; m = (t.e.values >= a_) & (t.e.values < b_)
                f.append(R[s]["flag"][vid][m]); r.append(t.R.values[m])
            f = np.concatenate(f); r = np.concatenate(r)
            out[f"{g}|{nm}"] = dict(share=float(f.mean() * 100), fl=float(r[f].mean()), rest=float(r[~f].mean()), n=int(f.sum()))
    return out


def curve(r, a):
    e = pd.DataFrame(r["events"], columns=["t", "bal", "worst"])
    e["t"] = pd.Timestamp(a) + pd.to_timedelta(e.t, unit="m"); e = e.set_index("t")
    idx = pd.date_range(pd.Timestamp(a), pd.Timestamp("2026-11-06"), freq="D")
    bal = e.bal.resample("D").last().reindex(idx).ffill().fillna(300.0)
    w = e.worst.resample("D").min().reindex(idx).ffill().fillna(300.0)
    dd = (w / np.maximum.accumulate(np.maximum(w.values, 1e-9)) - 1) * 100
    return [float(f"{v:.4g}") for v in bal.values], [round(float(v), 2) for v in dd]


if __name__ == "__main__":
    ev = pd.read_pickle(O.OUT / "eval.pkl"); luck = pickle.load(open(O.OUT / "luck.pkl", "rb"))
    fine = pd.read_pickle(O.OUT / "fine_eval.pkl"); mfine = pickle.load(open(O.OUT / "money_fine.pkl", "rb"))
    money = pickle.load(open(O.OUT / "money.pkl", "rb")); base = pickle.load(open(O.OUT / "base.pkl", "rb"))
    R = O.load_all()
    wrow = ev[(ev.fam == "C") & (ev["mode"] == "skip") & ev.p.apply(lambda p: p == WIN["p"])].iloc[0]; vid = int(wrow.id)
    # G3 and G6 per setting
    real = lambda r: min(r[f"DEV12|{p}|ratiox"] for p in P)
    ev["G3"] = False; ev["luck_pct"] = np.nan
    for i, r in ev[ev.G1 & ev.G2].iterrows():
        k = (int(r.id), r["mode"]) if r["mode"] != "exit" else ("B", str(r.p))
        if k in luck:
            pct = float(np.mean(real(r) > np.array(luck[k])) * 100); ev.loc[i, "luck_pct"] = pct; ev.loc[i, "G3"] = pct >= 95
    mres = {}
    for name, m in money.items():
        ok = all(v[0] > b[0] and v[1] <= b[1] + 1.0 for b, v in m.values())
        mres[name] = dict(ok=ok, **{k: dict(base=b, var=v) for k, (b, v) in m.items()})
    ev["G6"] = ev["name"].map(lambda n: mres.get(n, {}).get("ok", None))
    passed = ev[ev.G1 & ev.G2 & ev.G3 & ev.G4 & ev.G5]
    funnel = [("Settings tested", len(ev)), ("Gate 1: better on the 12 dev coins, both periods", int(ev.G1.sum())),
              ("Gate 2: neighbours agree (plateau)", int((ev.G1 & ev.G2).sum())),
              ("Gate 3: beats 95% of random time-shifts", int((ev.G1 & ev.G2 & ev.G3).sum())),
              ("Gate 4: holds on the 14 untouched big coins", int((ev.G1 & ev.G2 & ev.G3 & ev.G4).sum())),
              ("Gate 5: better on our 5 (bot weights)", int(len(passed))),
              ("Gate 6: more money, drop no deeper (from $300)", int(sum(1 for n in passed["name"] if mres.get(n, {}).get("ok"))))]
    fams = []
    for (fam, mode), s in ev.groupby(["fam", "mode"], sort=False):
        best = s.assign(m=s.apply(real, axis=1)).sort_values("m").iloc[-1]
        fams.append(dict(fam=fam, mode=MODES[mode], idea=FAMS[fam], n=len(s), g1=int(s.G1.sum()), g2=int((s.G1 & s.G2).sum()),
                         g3=int((s.G1 & s.G2 & s.G3).sum()), g45=int((s.G1 & s.G2 & s.G3 & s.G4 & s.G5).sum()),
                         best=best["name"], best_dev=[float(best[f"DEV12|{p}|ratiox"]) for p in P],
                         best_our=[float(best[f"OUR5|{p}|ratiox"]) for p in P], best_hb=[float(best[f"HOLD_BIG|{p}|dnet"]) for p in P]))
    near = []
    for _, r in ev[ev.G1 & ev.G2].iterrows():
        near.append(dict(name=r["name"], dev=[float(r[f"DEV12|{p}|ratiox"]) for p in P], our=[float(r[f"OUR5|{p}|ratiox"]) for p in P],
                         btc=[float(r[f"BTC|{p}|ratiox"]) for p in P], hb=[float(r[f"HOLD_BIG|{p}|dnet"]) for p in P],
                         hs=[float(r[f"HOLD_SMALL|{p}|dnet"]) for p in P], luck=None if np.isnan(r.luck_pct) else float(r.luck_pct),
                         g4=bool(r.G4), g5=bool(r.G5), g6=mres.get(r["name"], {}).get("ok")))
    heat = {}
    for g, m in (("DEV12", "rx"), ("OUR5", "rx"), ("BTC", "rx"), ("HOLD_BIG", "dnet"), ("HOLD_BIG", "ddd"), ("HOLD_SMALL", "dnet"), ("HOLD_SMALL", "ddd")):
        heat[f"{g}|{m}"] = [[[float(r[f"{g}|{p}|{m}"]) for p in P] for _, r in s.sort_values("p").iterrows()] for W, s in fine.groupby("W")]
    Ws = sorted(fine.W.unique().tolist()); ps = sorted(fine.p.unique().tolist())
    # money grid: fine (13 cells) + the 4 W90 cells from the main money run
    mgrid = {}
    for (W, p), m in mfine.items():
        mgrid[f"{W}|{p}"] = [[float(v[0] / b[0]), float(v[1] - b[1])] for b, v in m.values()]
    for pp in (0.7, 0.8, 0.9, 0.95):
        nm = f"C skip: meas oi, side low, W 90, p {pp}"
        if nm in money:
            mgrid[f"90|{pp}"] = [[float(v[0] / b[0]), float(v[1] - b[1])] for b, v in money[nm].values()]
    # equity curves base vs winner
    curves = {}
    full = O.money(dict(WIN), "skip", keep="events")
    for k, (rb, rv) in full.items():
        a = f"{k}-01-01"; b0, d0 = curve(rb, a); b1, d1 = curve(rv, a)
        curves[k] = dict(t0=a, base=dict(final=rb["final"], dd=rb["dd"], bal=b0, ddser=d0), win=dict(final=rv["final"], dd=rv["dd"], bal=b1, ddser=d1))
    # per coin / year on our 5 (R, shorts x0.5)
    coins = []
    yr = lambda e: pd.to_datetime(e * 60_000_000_000).year
    for s in O.OUR5:
        b = R[s]["base"]; v = R[s]["skip"][vid]
        row = dict(coin=s[:-4], n0=len(b), n1=len(v), years=[])
        for y in range(2022, 2027):
            rb = float((b.R.values * np.where(b.d.values < 0, .5, 1))[yr(b.e.values) == y].sum())
            rv = float((v.R.values * np.where(v.d.values < 0, .5, 1))[yr(v.e.values) == y].sum())
            row["years"].append([rb, rv])
        coins.append(row)
    dis = pd.read_pickle(O.OUT / "disguise.pkl") if (O.OUT / "disguise.pkl").exists() else None
    disg = []
    if dis is not None:
        for nm, a, b in O.PERIODS:
            a_, b_ = pd.Timestamp(a).value // 60_000_000_000, pd.Timestamp(b).value // 60_000_000_000
            for grp in ("DEV12", "HOLD39"):
                x = dis[dis.sym.isin(getattr(O, grp)) & (dis.e >= a_) & (dis.e < b_)]
                row = dict(period=nm, grp=grp, n=len(x))
                for col in ("val", "coins", "price"):
                    f = x[col] <= 0.2
                    row[col] = [float(f.mean() * 100), float(x.R[f].mean()), float(x.R[~f].mean())]
                disg.append(row)
    sides = []
    if dis is not None:
        for nm, a, b in O.PERIODS:
            a_, b_ = pd.Timestamp(a).value // 60_000_000_000, pd.Timestamp(b).value // 60_000_000_000
            for grp in ("OUR5", "DEV12", "HOLD39"):
                x = dis[dis.sym.isin(getattr(O, grp)) & (dis.e >= a_) & (dis.e < b_)]; f = (x.val <= 0.2).to_numpy()
                row = dict(period=nm, grp=grp)
                for side, m in (("short", (x.d < 0).to_numpy()), ("long", (x.d > 0).to_numpy())):
                    row[side] = [int(m.sum()), int((f & m).sum()), float(x.R[f & m].mean()) if (f & m).any() else None, float(x.R[~f & m].mean())]
                sides.append(row)
    lk = luck[(vid, "skip")]
    data = dict(funnel=funnel, fams=fams, near=near, heat=heat, Ws=Ws, ps=ps, mgrid=mgrid, curves=curves, coins=coins, disg=disg, sides=sides,
                luck=dict(real=real(wrow), sims=[float(v) for v in lk]), flag=flagged(R, vid), periods=P,
                base={g: {p: list(v) for p, v in d.items()} for g, d in base.items()},
                win=dict(name=wrow["name"], dev=[float(wrow[f"DEV12|{p}|ratiox"]) for p in P], our=[float(wrow[f"OUR5|{p}|ratiox"]) for p in P],
                         btc=[float(wrow[f"BTC|{p}|ratiox"]) for p in P], hb=[float(wrow[f"HOLD_BIG|{p}|dnet"]) for p in P],
                         hs=[float(wrow[f"HOLD_SMALL|{p}|dnet"]) for p in P]),
                ncoins=len(R), ntrades=int(sum(len(r["base"]) for r in R.values())))
    html = (pathlib.Path(__file__).resolve().parent / "breakout_support_template.html").read_text().replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
    (C.ROOT / "reports" / "breakout_support.html").write_text(html)
    print("written", len(html) // 1024, "KB;", [f for f in funnel])
