"""cryptobot/cap_comparison.html: equity and drawdown of the bot with and without the open-risk cap (and the
'just lower the risk' alternative; recommended: BTC never shrunk, its risk still counts against the cap for the others), from $200, for three start dates and three risk levels. Uses sizing_v3.sim."""
import json
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import sizing_v3 as S

STARTS = {"2020": "2020-03-01", "2022": "2022-01-01", "2024": "2024-01-01"}
END = "2026-10-01"
SETS = [("now", "5% / 2.5% / 0.83% (now)", (5, 2.5, 0.83)), ("b6", "6% / 2.5% / 0.83%", (6, 2.5, 0.83)),
        ("b75", "7.5% / 2.5% / 0.83%", (7.5, 2.5, 0.83)), ("b75lo", "7.5% / 1.5% / 0.5%", (7.5, 1.5, 0.5))]


def risk(b, e, a):
    return {"BTCUSDT": b / 100, "ETHUSDT": e / 100, "BNBUSDT": a / 100, "SOLUSDT": a / 100, "ADAUSDT": a / 100}


VARIANTS = [("now", "No cap", lambda r, b: dict(risk=r)),
            ("capbtc", "Cap 1.1× BTC risk, BTC never shrunk (recommended)", lambda r, b: dict(risk=r, cap=0.011 * b, cap_mode="shrink", exempt=("BTCUSDT",))),
            ("cap11", "Cap 1.1×, all coins", lambda r, b: dict(risk=r, cap=0.011 * b, cap_mode="shrink")),
            ("low", "Lower risk instead (0.8×)", lambda r, b: dict(risk=r, mult=0.8)),
            ("cap10", "Cap 1.0×, all coins", lambda r, b: dict(risk=r, cap=0.010 * b, cap_mode="shrink")),
            ("cap13", "Cap 1.3×, all coins", lambda r, b: dict(risk=r, cap=0.013 * b, cap_mode="shrink"))]


def job(args):
    sk, m, vk = args
    f = dict((k, fn) for k, _, fn in VARIANTS)[vk]
    b, e, a = dict((k, v) for k, _, v in SETS)[m]
    st, bal, dd = S.sim(f(risk(b, e, a), b), STARTS[sk], END, want_curve=True)
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
    (C.ROOT / "cryptobot" / "cap_comparison.html").write_text(html)
    s = data["series"]
    for k in ("2024_now_now", "2024_now_capbtc", "2024_b75_capbtc", "2020_b75_capbtc", "2024_b75lo_capbtc"):
        st = s[k]["stats"]; print(k, round(st["final"]), round(st["pm"], 2), round(st["dd"], 1))
    print("written", len(html) // 1024, "KB")
