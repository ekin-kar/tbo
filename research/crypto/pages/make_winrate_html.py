"""reports/winrate_rr.html: expectancy heatmap (win rate x reward-to-risk) with the bot's coins plotted on it.
Win = trade closed above 0R; RR = average win / average loss (losses include the small breakeven exits after fees),
so win% x avg win - loss% x avg loss = the real average R per trade."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import json, pickle
import pandas as pd
import common as C

import botsim as _BS
ALL = _BS.ALL
COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
pts = {}
for per, a in (("all", "2020-01-01"), ("2024", "2024-01-01")):
    rows = []
    for s in COINS + ["ALL"]:
        x = pd.concat([ALL[(c, 0.0003)] for c in COINS]) if s == "ALL" else ALL[(s, 0.0003)]
        R = x[x.entry_time >= a].R
        p = float((R > 0).mean()); W = float(R[R > 0].mean()); L = float(-R[R <= 0].mean())
        rows.append(dict(name="All 5 coins" if s == "ALL" else s[:-4], n=int(len(R)), win=p * 100, rr=W / L, avgw=W, avgl=L, e=float(R.mean()),
                         be=float(((R > -0.2) & (R <= 0.2)).mean() * 100)))
    pts[per] = rows
html = open(pathlib.Path(__file__).resolve().parent / "winrate_template.html").read().replace("/*DATA*/null", json.dumps(pts))
(C.ROOT / "reports" / "winrate_rr.html").write_text(html)
print(json.dumps(pts["all"][-1]), "written")
