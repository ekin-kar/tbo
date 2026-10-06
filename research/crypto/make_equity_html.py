"""Builds cryptobot/equity.html: TBO v2.1 equity curves (BTC, ETH, both) from the backtest trades."""
import json
import numpy as np
import common as C, families as F
from wf2 import V21

data = {}
for sym in ("BTCUSDT", "ETHUSDT"):
    x = C.between(F.channel_breakout(C.load(sym), **V21), "2020-03-01", "2026-10-01").sort_values("exit_time")
    data[sym[:3]] = [[int(t.value // 10**6), round(float(r), 4), int(d)] for t, r, d in zip(x.exit_time, x.R, x.dir)]
html = open(C.ROOT / "research" / "crypto" / "equity_template.html").read().replace("/*DATA*/null", json.dumps(data))
out = C.ROOT / "cryptobot" / "equity.html"
out.write_text(html)
print("wrote", out, {k: len(v) for k, v in data.items()})
