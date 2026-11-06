"""reports/risk_comparison.html (+ plan_ladder_plus50.html preset): $300 over 24 months with different risk profiles
(the bot's risk ladder and flat risks, all with the open-risk cap, BTC exempt) and monthly deposits, simulated from random
4-week blocks of the bot's real v2.4 trades (BTC ETH BNB SOL ADA, shorts x0.5). Sizing: botsim.py (= the bot)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import json
from multiprocessing import Pool
import numpy as np
import common as C
import botsim as BS

PROFILES = [("lad", BS.bot_policy(), 12), ("f25", BS.flat_policy(2.5, 1.25, 0.42), 8), ("f5", BS.flat_policy(5, 2.5, 0.83), 8),
            ("f6", BS.flat_policy(6, 2.5, 0.83), 10), ("f75", BS.flat_policy(7.5, 2.5, 0.83), 12), ("f10", BS.flat_policy(10, 2.5, 0.83), 16)]
DEPS = [0, 50, 100]
SRCS = {"2022": ("2022-01-01", "2026-11-07"), "2024": ("2024-01-01", "2026-11-07")}
MONTHS, START, N = 24, 300.0, 1000
LEVELS = [1000, 5000, 10000, 20000]
MON = BS.MON


def journey(args):
    seed, src = args
    x = BS.journey_trades(seed, *SRCS[src], months=MONTHS)
    out = {}
    for key, pol, _ in PROFILES:                 # same market path for every profile and deposit (fair comparison)
        for dep in DEPS:
            r = BS.run(x, pol, START, end=MONTHS * MON, deposit=dep, levels=LEVELS, keep="months")
            mb = (r["months"] + [r["final"]] * MONTHS)[:MONTHS - 1] + [r["final"]]
            out[(key, dep)] = dict(bal=[START] + mb, dd=r["dd"] / 100, low=r["low"], invested=r["invested"],
                                   reach={L: (None if r["reach"][L] is None else r["reach"][L] / MON) for L in LEVELS})
    return out


def summarize(results):
    S = {}
    for key, _, _ in PROFILES:
        for dep in DEPS:
            js = [r[(key, dep)] for r in results]
            bal = np.array([j["bal"] for j in js])                      # N x (MONTHS+1)
            fin = bal[:, -1]; dd = np.array([j["dd"] for j in js]); low = np.array([j["low"] for j in js])
            reach = {L: [sum(1 for j in js if j["reach"][L] is not None and j["reach"][L] <= m) / len(js) * 100 for m in range(MONTHS + 1)]
                     for L in LEVELS}
            S[f"{key}_{dep}"] = dict(
                pct={str(p): [round(float(v), 2) for v in np.percentile(bal, p, axis=0)] for p in (10, 25, 50, 75, 90)},
                ex=[[round(float(v), 2) for v in bal[i]] for i in range(12)],
                reach={str(L): [round(v, 1) for v in reach[L]] for L in LEVELS},
                median=float(np.median(fin)), p10=float(np.percentile(fin, 10)), p90=float(np.percentile(fin, 90)),
                p_up=float((fin > js[0]["invested"]).mean() * 100), p10k=float((fin >= 1e4).mean() * 100), p20k=float((fin >= 2e4).mean() * 100),
                end_lt100=float((fin < 100).mean() * 100), ever_lt100=float((low < 100).mean() * 100), ever_half=float((low < START / 2).mean() * 100),
                dd_med=float(np.median(dd) * 100), dd_p90=float(np.percentile(dd, 90) * 100), invested=js[0]["invested"])
    return S


if __name__ == "__main__":
    data = dict(profiles=[(k, BS.label(p), lev) for k, p, lev in PROFILES], deps=DEPS, levels=LEVELS, months=MONTHS, start=START, n=N,
                srcs={"2022": "Trades from 2022 – 6 Nov 2026 (no 2020-21 bull run)", "2024": "Trades from 2024 – 6 Nov 2026"}, res={})
    for src in SRCS:
        with Pool(4) as p:
            res = p.map(journey, [(s, src) for s in range(N)], chunksize=20)
        data["res"][src] = summarize(res)
        for k in ("lad", "f5", "f75"):
            q = data["res"][src][f"{k}_0"]
            print(src, k, "median", round(q["median"]), "P10k", round(q["p10k"], 1), "dd", round(q["dd_med"]), round(q["dd_p90"]))
    tpl = open(pathlib.Path(__file__).resolve().parent / "risk_template.html").read()
    for name, preset in (("risk_comparison.html", None), ("plan_ladder_plus50.html", dict(m=0, d=DEPS.index(50)))):
        dd = dict(data, preset=preset) if preset else data
        html = tpl.replace("/*DATA*/null", json.dumps(dd, separators=(",", ":")))
        if preset:
            html = html.replace("<title>TBO Risk Comparison</title>", "<title>TBO Plan: Ladder + $50/month</title>")
        (C.ROOT / "reports" / name).write_text(html)
        print("written", name, len(html) // 1024, "KB")
