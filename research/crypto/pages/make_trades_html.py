"""reports/trades.html: every trade of the bot on one $300 account (sized like the bot: risk ladder + open-risk cap,
botsim.py), with the equity chart and each trade's 4h price chart (entry, stop, breakeven, exit). Click a trade in the
table or a dot on the equity chart to see it. Prices from trade_prices.py (same engine, matched trade for trade)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import json
import numpy as np, pandas as pd
import common as C, families as F
import botsim as BS

START_BAL = 300.0
RUNS = {"2020": ("2020-01-01", "Feb 2020 – Sep 2026 (every trade since the first)"), "2022": ("2022-01-01", "Jan 2022 – Sep 2026 (no 2020-21 boom)"),
        "2024": ("2024-01-01", "Jan 2024 – Sep 2026 (most recent)")}
END = "2026-10-01"
r5 = lambda v: float(f"{v:.6g}")


def main():
    P = pd.read_pickle(C.D.CACHE / f"trade_prices_{BS.TAG}.pkl")
    T = BS.T.merge(P, on=["sym", "entry_time"], how="left")
    assert T.entry.notna().all() and len(T) == len(BS.T)
    mins = lambda s: (s.values.astype("datetime64[m]").astype(np.int64))
    ci = T.sym.map({s: i for i, s in enumerate(BS.COINS)}).to_numpy()
    e, x, b = mins(T.entry_time), mins(T.exit_time), mins(T.be_time)
    trades = []
    for k in range(len(T)):
        be = int(b[k]) if b[k] < x[k] else 0                 # breakeven reached before the exit
        trades.append([int(ci[k]), int(T.dir[k]), int(e[k]), int(x[k]), be, r5(T.entry[k]), r5(T.exit[k]), r5(T.sl_dist[k]),
                       0 if T.reason[k] == "SL" else 1, round(float(T.R[k]), 3)])
    pol = BS.bot_policy()
    runs = {}
    for key, (a, lab) in RUNS.items():
        x_, t0, t1 = BS.window(a, END)
        first = int(np.searchsorted(BS.TR[:, 0], t0))        # x_ rows are BS.TR[first:first+len]
        r = BS.run(x_, pol, START_BAL, keep="trades")
        rows = []
        for i in range(len(x_)):
            full, bal0 = r["full"][i]
            amt = r["amts"].get(i, 0.0)
            rows.append([first + i, round(full, 2), round(amt, 2), round(bal0, 2), round(r["bal_after"].get(i, 0.0), 2)])
        runs[key] = dict(label=lab, t0=int(t0), t1=int(t1), rows=rows, final=round(r["final"], 2), dd=round(r["dd"], 1))
        print(key, lab, "trades", len(rows), "taken", len(r["amts"]), "final", round(r["final"]), "worst drop", round(r["dd"], 1))
    candles = {}
    for s in BS.COINS:
        c = F.resample(C.load(s), 240)
        keep = (c["t"] >= pd.Timestamp("2020-01-01").value // BS.MIN) & (c["t"] < pd.Timestamp(END).value // BS.MIN)
        t = c["t"][keep].astype(np.int64); t0 = int(t[0])
        candles[s[:-4]] = dict(t0=t0, k=((t - t0) // 240).astype(int).tolist(),
                               o=[r5(v) for v in c["o"][keep]], h=[r5(v) for v in c["h"][keep]], l=[r5(v) for v in c["l"][keep]], c=[r5(v) for v in c["c"][keep]])
    data = dict(coins=[s[:-4] for s in BS.COINS], trades=trades, runs=runs, order=list(RUNS), candles=candles, start=START_BAL,
                ladder=[[f, r, cp] for f, r, cp in pol["rows"]], smult=pol["smult"], beR=1.5)
    lad = "; ".join((f"under ${pol['rows'][1][0]:,.0f}: " if i == 0 else f"from ${r[0]:,.0f}: ") + f"BTC {r[1][0]:g}% / ETH {r[1][1]:g}% / each alt {r[1][2]:g}%"
                    for i, r in enumerate(pol["rows"]))
    html = (open(pathlib.Path(__file__).resolve().parent / "trades_template.html").read().replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
            .replace("/*LADDER*/", lad))
    (C.ROOT / "reports" / "trades.html").write_text(html)
    print("written trades.html", len(html) // 1024, "KB")


if __name__ == "__main__":
    main()
