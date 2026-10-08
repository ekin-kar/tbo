import numpy as np, pandas as pd
import common as C, families as F, ideas10 as X
from portfolio import simulate, report
from wf2 import V21
COINS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]
def trades(kw):
    out = []
    for sym in COINS:
        C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
        m = C.load(sym); x = C.between(F.channel_breakout(m, **dict(V21, **kw)), "2020-03-01", "2026-10-01").copy()
        e = X.idx(m, x.entry_time); xi = X.idx(m, x.exit_time)
        be = X.first_reach(m["h"], m["l"], e, xi, x.dir.to_numpy(), x.entry.to_numpy(), x.sl_dist.to_numpy(), dict(V21, **kw)["be_R"] or 99)
        x["be_time"] = pd.to_datetime(np.where(be >= 0, m["t"][np.clip(be, 0, None)], m["t"][xi]) * 60, unit="s"); x["sym"] = sym
        out.append(x[["sym", "entry_time", "exit_time", "be_time", "dir", "R", "hours"]])
    return pd.concat(out)
V = trades({}); N = trades(dict(n=40, sl_atr=1.25, ema_n=100))
for lab, start, months in (("Full 2020-03..2026-09", "2020-03-01", 79), ("2024-01..2026-09 only", "2024-01-01", 33)):
    print(lab)
    report(*simulate(V, risk=0.0075, cap=0.03, short_mult=0.5, start=start), "v2.2 0.75%", months)
    for r in (0.0125, 0.015):
        report(*simulate(N, risk=r, cap=0.05, short_mult=0.5, start=start), f"n40/1.25ATR/EMA100 {r*100:.2g}%", months)
