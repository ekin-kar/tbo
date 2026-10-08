"""cryptobot/risk_comparison.html: $250 over 24 months at different risk levels (and monthly deposits), simulated from
random 4-week blocks of the bot's real v2.4 trades (BTC ETH BNB SOL ADA, shorts x0.5). Same engine as goal_mc.py."""
import json, pickle
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C

ALL = pickle.load(open(C.D.CACHE / "portfolio_trades_v24.pkl", "rb"))
COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
CFG = {s: json.load(open(C.ROOT / "cryptobot" / f"config_{s[:-4].lower()}.json")) for s in COINS}
RISK = np.array([CFG[s]["risk_pct"] for s in COINS]) / 100                 # the bot's current risks = 1x
T = pd.concat([ALL[(s, 0.0003)] for s in COINS]).sort_values("entry_time")
mins = lambda col: T[col].values.astype("datetime64[m]").astype(np.int64)
TR = np.c_[mins("entry_time"), mins("exit_time"), mins("be_time"), T.dir.values, T.R.values, T.sym.map({s: i for i, s in enumerate(COINS)}).values]
BLK = 28 * 1440; MON = 30.44 * 1440
MULTS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
DEPS = [0, 50, 100]
SRCS = {"2022": ("2022-01-01", "2026-10-01"), "2024": ("2024-01-01", "2026-10-01")}
MONTHS, START, N = 24, 250.0, 1000
LEVELS = [1000, 5000, 10000, 20000]


def journey(args):
    seed, src = args
    a, b = SRCS[src]
    r = np.random.default_rng(seed)
    t0, t1 = pd.Timestamp(a).value // 60_000_000_000, pd.Timestamp(b).value // 60_000_000_000
    pool = TR[(TR[:, 0] >= t0) & (TR[:, 0] < t1)]
    rows = []
    for k in range(int(np.ceil(MONTHS * MON / BLK))):
        u = t0 + r.random() * (t1 - BLK - t0)
        sel = pool[(pool[:, 0] >= u) & (pool[:, 0] < u + BLK)].copy(); sel[:, :3] += k * BLK - u
        rows.append(sel)
    x = np.concatenate(rows)
    ev = []
    for i, (e, xx, be, d, R, c) in enumerate(x):
        ev += [(e, 1, i), (max(be, e + 1e-3), 0, i), (max(xx, e + 2e-3), 2, i)]
    ev.sort(key=lambda z: (z[0], -z[1]))
    out = {}
    for mult in MULTS:                       # same market path for every risk level and deposit (fair comparison)
        for dep in DEPS:
            eq = START; opn = {}; pk = START; dd = 0.0; low = START; nxt = MON; m_bal = []; reach = {L: None for L in LEVELS}
            invested = START
            for t, kind, i in ev:
                if t > MONTHS * MON:
                    break
                while t >= nxt and len(m_bal) < MONTHS:
                    m_bal.append(eq)
                    if dep and len(m_bal) < MONTHS:
                        eq += dep; invested += dep; pk += dep
                    nxt += MON
                e, xx, be, d, R, c = x[i]
                if kind == 1:
                    opn[i] = [eq * RISK[int(c)] * mult * (0.5 if d < 0 else 1), False]
                elif kind == 0 and i in opn:
                    opn[i][1] = True
                elif kind == 2 and i in opn:
                    eq += opn.pop(i)[0] * R; low = min(low, eq)
                    for L in LEVELS:
                        if reach[L] is None and eq >= L:
                            reach[L] = t / MON
                w = eq - sum(v[0] for v in opn.values() if not v[1]); pk = max(pk, w); dd = max(dd, 1 - w / pk)
            while len(m_bal) < MONTHS:
                m_bal.append(eq)
            out[(mult, dep)] = dict(bal=[START] + m_bal, dd=dd, low=low, reach=reach, invested=invested)
    return out


def summarize(results):
    S = {}
    for mult in MULTS:
        for dep in DEPS:
            js = [r[(mult, dep)] for r in results]
            bal = np.array([j["bal"] for j in js])                      # N x (MONTHS+1)
            fin = bal[:, -1]; dd = np.array([j["dd"] for j in js]); low = np.array([j["low"] for j in js])
            reach = {L: [sum(1 for j in js if j["reach"][L] is not None and j["reach"][L] <= m) / len(js) * 100 for m in range(MONTHS + 1)]
                     for L in LEVELS}
            S[f"{mult:g}_{dep}"] = dict(
                pct={str(p): [round(float(v), 2) for v in np.percentile(bal, p, axis=0)] for p in (10, 25, 50, 75, 90)},
                ex=[[round(float(v), 2) for v in bal[i]] for i in range(12)],
                reach={str(L): [round(v, 1) for v in reach[L]] for L in LEVELS},
                median=float(np.median(fin)), p10=float(np.percentile(fin, 10)), p90=float(np.percentile(fin, 90)),
                p_up=float((fin > js[0]["invested"]).mean() * 100), p10k=float((fin >= 1e4).mean() * 100), p20k=float((fin >= 2e4).mean() * 100),
                end_lt100=float((fin < 100).mean() * 100), ever_lt100=float((low < 100).mean() * 100), ever_half=float((low < START / 2).mean() * 100),
                dd_med=float(np.median(dd) * 100), dd_p90=float(np.percentile(dd, 90) * 100), invested=js[0]["invested"])
    return S


if __name__ == "__main__":
    data = dict(mults=MULTS, deps=DEPS, levels=LEVELS, months=MONTHS, start=START, n=N,
                risks={s[:-4]: CFG[s]["risk_pct"] for s in COINS}, srcs={"2022": "Trades from 2022 – Sep 2026 (no 2020-21 bull run)", "2024": "Trades from 2024 – Sep 2026"},
                res={})
    for src in SRCS:
        with Pool(4) as p:
            res = p.map(journey, [(s, src) for s in range(N)])
        data["res"][src] = summarize(res)
        s = data["res"][src]["1.5_0"]
        print(src, "1.5x no deposits: median", round(s["median"]), "P10k", round(s["p10k"], 1), "dd", round(s["dd_med"]))
    tpl = open(C.ROOT / "research" / "crypto" / "risk_template.html").read()
    for name, preset in (("risk_comparison.html", None), ("plan_2.5pct_plus50.html", dict(m=MULTS.index(0.5), d=DEPS.index(50)))):
        dd = dict(data, preset=preset) if preset else data
        html = tpl.replace("/*DATA*/null", json.dumps(dd, separators=(",", ":")))
        if preset:
            html = html.replace("<title>TBO Risk Comparison</title>", "<title>TBO Plan: 2.5% + $50/month</title>")
        (C.ROOT / "cryptobot" / name).write_text(html)
        print("written", name, len(html) // 1024, "KB")
