"""cryptobot/cap_comparison.html: equity and drawdown of the bot with and without the open-risk cap (and the
'just lower the risk' alternative), from $200, for three start dates and three risk levels. Uses sizing_v3.sim."""
import json
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import sizing_v3 as S

STARTS = {"2020": "2020-03-01", "2022": "2022-01-01", "2024": "2024-01-01"}
END = "2026-10-01"
MULTS = [0.5, 1.0, 1.5]
VARIANTS = [("now", "Now (no cap)", lambda m: dict(mult=m)),
            ("cap11", "Cap 1.1× BTC risk (recommended)", lambda m: dict(mult=m, cap=0.055 * m, cap_mode="shrink")),
            ("low", "Lower risk instead (0.8×)", lambda m: dict(mult=0.8 * m)),
            ("cap10", "Cap 1.0× BTC risk", lambda m: dict(mult=m, cap=0.05 * m, cap_mode="shrink")),
            ("cap13", "Cap 1.3× BTC risk", lambda m: dict(mult=m, cap=0.065 * m, cap_mode="shrink"))]


def job(args):
    sk, m, vk = args
    f = dict((k, fn) for k, _, fn in VARIANTS)[vk]
    st, bal, dd = S.sim(f(m), STARTS[sk], END, curve=True)
    return sk, m, vk, st, bal, dd


if __name__ == "__main__":
    jobs = [(sk, m, vk) for sk in STARTS for m in MULTS for vk, _, _ in VARIANTS]
    with Pool(4) as p:
        res = p.map(job, jobs)
    data = dict(variants=[(k, lab) for k, lab, _ in VARIANTS], mults=MULTS, starts={"2020": "Mar 2020 (full history)", "2022": "2022 (no 2020-21 bull run)", "2024": "2024 (most recent)"},
                risks={k: v * 100 for k, v in S.RISK.items()}, series={})
    for sk, m, vk, st, bal, dd in res:
        key = f"{sk}_{m:g}_{vk}"
        data["series"][key] = dict(t0=bal.index[0].strftime("%Y-%m-%d"), bal=[round(float(v), 2) for v in bal.values], dd=[round(float(v), 2) for v in dd.values],
                                   stats={k: (round(float(v), 3) if isinstance(v, (int, float, np.floating, np.integer)) else v) for k, v in st.items()})
    html = open(C.ROOT / "research" / "crypto" / "cap_template.html").read().replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
    (C.ROOT / "cryptobot" / "cap_comparison.html").write_text(html)
    s = data["series"]
    for k in ("2024_1_now", "2024_1_cap11", "2024_1_low", "2020_1_now", "2020_1_cap11"):
        st = s[k]["stats"]; print(k, round(st["final"]), round(st["pm"], 2), round(st["dd"], 1))
    print("written", len(html) // 1024, "KB")
