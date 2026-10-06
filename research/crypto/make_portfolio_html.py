"""Builds cryptobot/equity_portfolio.html: one $1,000 account trading BTC+ETH+DOGE+ADA (TBO v2.1), vs BTC+ETH."""
import json, pickle
import numpy as np, pandas as pd
import common as C
from portfolio import simulate

ALL = pickle.load(open(C.D.CACHE / "portfolio_trades.pkl", "rb"))
P4 = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]
T4 = pd.concat([ALL[(s, 0.0003)] for s in P4]); T2 = pd.concat([ALL[(s, 0.0003)] for s in P4[:2]])
series, coins = {}, {}
for (key, T, risk), start in [(k, st) for k in [("P4_0.5", T4, 0.005), ("P4_0.6", T4, 0.006), ("P4_0.75", T4, 0.0075), ("P2_1", T2, 0.01)]
                              for st in ("2020-03-01", "2024-01-01")]:
    cv, tk = simulate(T, risk=risk, cap=0.03, start=start)
    key = f"{key}|{start[:4]}"
    d = cv.resample("1D").last().ffill()
    pk = d.worst.cummax(); dd = (d.worst / pk - 1) * 100
    series[key] = [[int(t.value // 10**6), round(float(e), 2), round(float(x), 2)] for t, e, x in zip(d.index, d.equity, dd)]
    if key.startswith("P4") and key.endswith("2020"):
        coins[key.split("|")[0]] = {s[:-4]: [int(len(tk[tk.sym == s])), round(float(tk[tk.sym == s].R.sum()), 1)] for s in P4}
html = open("equity_portfolio_template.html").read().replace("/*DATA*/null", json.dumps(dict(series=series, coins=coins)))
(C.ROOT / "cryptobot" / "equity_portfolio.html").write_text(html)
print("ok", {k: len(v) for k, v in series.items()}, {k: v[-1][1] for k, v in series.items()})
