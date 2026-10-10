"""reports/cap_comparison.html: equity and drawdown of the bot with and without the open-risk cap (and the
'just lower the risk' alternative), from $300, for three start dates and risk sets (the bot's ladder first). botsim.py."""
import json
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import botsim as BS

STARTS = {"2020": "2020-03-01", "2022": "2022-01-01", "2024": "2024-01-01"}
END = "2026-10-01"
LAD = [(r[0], r[1][0], r[1][1], r[1][2]) for r in BS.bot_policy()["rows"]]
SETS = [("lad", "Ladder: 7.5% → 5% from $1k → 2.5% from $10k (the bot)", None), ("now", "5% / 2.5% / 0.83%", (5, 2.5, 0.83)),
        ("b75", "7.5% / 2.5% / 0.83%", (7.5, 2.5, 0.83)), ("b75lo", "7.5% / 1.5% / 0.5%", (7.5, 1.5, 0.5))]
VARIANTS = [("now", "No cap", dict(cap_x=0)),
            ("capbtc", "Cap 1.1× BTC risk, BTC never shrunk (the bot)", dict(cap_x=1.1)),
            ("cap11", "Cap 1.1×, all coins", dict(cap_x=1.1, exempt_btc=False)),
            ("low", "Lower risk instead (0.8×, no cap)", dict(cap_x=0, mult=0.8)),
            ("cap10", "Cap 1.0×, all coins", dict(cap_x=1.0, exempt_btc=False)),
            ("cap13", "Cap 1.3×, all coins", dict(cap_x=1.3, exempt_btc=False))]


def policy(m, kw):
    v = dict((k, x) for k, _, x in SETS)[m]
    return BS.ladder_policy(LAD, **kw) if v is None else BS.flat_policy(*v, **kw)


def job(args):
    sk, m, vk = args
    h = BS.history(policy(m, dict((k, kw) for k, _, kw in VARIANTS)[vk]), STARTS[sk], END, 300.0)
    bal, dd, r = h["bal"], h["dd"], h["r"]
    mo = (pd.Timestamp(END) - pd.Timestamp(STARTS[sk])).days / 30.44
    pm = ((r["final"] / 300) ** (1 / mo) - 1) * 100
    hw = bal.cummax(); nh = bal.index[bal >= hw]; flat = int(np.diff(nh.values).astype("timedelta64[D]").astype(int).max())
    mm = bal.resample("ME").last().pct_change().dropna()
    st = dict(final=r["final"], pm=pm, dd=r["dd"], ratio=pm / r["dd"], flat=flat, pos=float((mm > 0).mean() * 100),
              worst_m=float(mm.min() * 100), skipped=r["skipped"])
    return sk, m, vk, st, bal, dd


if __name__ == "__main__":
    jobs = [(sk, m, vk) for sk in STARTS for m, _, _ in SETS for vk, _, _ in VARIANTS]
    with Pool(4) as p:
        res = p.map(job, jobs)
    data = dict(variants=[(k, lab) for k, lab, _ in VARIANTS], sets=[(k, l) for k, l, _ in SETS], starts={"2020": "Mar 2020 (full history)", "2022": "2022 (no 2020-21 bull run)", "2024": "2024 (most recent)"},
                series={})
    for sk, m, vk, st, bal, dd in res:
        key = f"{sk}_{m}_{vk}"
        data["series"][key] = dict(t0=bal.index[0].strftime("%Y-%m-%d"), bal=[float(f"{v:.4g}") for v in bal.values], dd=[round(float(v), 2) for v in dd.values],
                                   stats={k: (round(float(v), 3) if isinstance(v, (int, float, np.floating, np.integer)) else v) for k, v in st.items()})
    html = open(C.ROOT / "research" / "crypto" / "cap_template.html").read().replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
    (C.ROOT / "reports" / "cap_comparison.html").write_text(html)
    s = data["series"]
    for k in ("2024_lad_now", "2024_lad_capbtc", "2024_now_capbtc", "2022_lad_capbtc", "2020_lad_capbtc"):
        st = s[k]["stats"]; print(k, round(st["final"]), round(st["pm"], 2), round(st["dd"], 1))
    print("written", len(html) // 1024, "KB")
