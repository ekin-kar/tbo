"""Trailing-stop variants vs the 5-day time exit (TBO v2.1), BTC + ETH, all data and walk-forward (pooled)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V21, stream, mar, TESTS

VARIANTS = [dict(label="v2.1 (5-day close)")]
VARIANTS += [dict(label=f"5-day->{h}h hold only", hold_h=h) for h in (168, 240, 480)]
for k, st, h in itertools.product((1.0, 2.0, 3.0, 4.0, 6.0, 8.0), (1.5, 3.0, 5.0), (120, 240, 480)):
    VARIANTS.append(dict(label=f"trail {k}R from +{st}R, max {h}h", trail_k=k, trail_start=st, hold_h=h))
for mm, a, h in itertools.product((6, 12, 24), (2.0, 3.0, 4.0), (120, 240)):
    VARIANTS.append(dict(label=f"4h-close trail {mm} candles-{a}ATR, max {h}h", trail_m=mm, trail_atr=a, hold_h=h))
DATA = {}


def one(args):
    sym, i = args
    if sym not in DATA:
        DATA[sym] = C.load(sym)
    kw = {k: v for k, v in VARIANTS[i].items() if k != "label"}
    tr = F.channel_breakout(DATA[sym], **dict(V21, **kw))
    return sym, i, tr[tr.entry_time >= "2020-03-01"][["entry_time", "exit_time", "dir", "R", "hours"]]


if __name__ == "__main__":
    jobs = [(s, i) for s in ("BTCUSDT", "ETHUSDT") for i in range(len(VARIANTS))]
    with Pool(4) as p:
        res = p.map(one, jobs, chunksize=4)
    T = {(s, i): tr for s, i, tr in res}
    yrs = 6.58
    rows = []
    for i, v in enumerate(VARIANTS):
        row = dict(variant=v["label"])
        for s in ("BTCUSDT", "ETHUSDT"):
            x = stream(T[(s, i)], "2020-03-01", "2026-10-01"); r = x.R.to_numpy()
            eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
            e = 1000 * np.cumprod(1 + 0.02 * r); pk = np.maximum.accumulate(e)
            tag = s[:3]
            row[f"{tag}_R"] = round(r.sum()); row[f"{tag}_DD"] = round(dd, 1); row[f"{tag}_MAR"] = round(r.sum() / yrs / dd, 2)
            row[f"{tag}_2%mo"] = round(((e[-1] / 1000) ** (1 / 79) - 1) * 100, 1); row[f"{tag}_2%DD"] = round(((pk - e) / pk).max() * 100)
            row[f"{tag}_hold"] = round(x.hours.mean())
        row["MAR_avg"] = round((row["BTC_MAR"] + row["ETH_MAR"]) / 2, 2)
        rows.append(row)
    df = pd.DataFrame(rows).sort_values("MAR_avg", ascending=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    df.to_csv(C.ROOT / "research" / "results" / "crypto_trail_scan.csv", index=False)
    print(df.head(20).to_string(index=False))
    print("...\nbaseline row:"); print(df[df.variant.str.startswith("v2.1")].to_string(index=False))
    # walk-forward, pooled: each year pick the variant with the best (BTC MAR + ETH MAR) on earlier years
    oos = {s: [] for s in ("BTCUSDT", "ETHUSDT")}; picks = []
    for y in TESTS:
        ty = (pd.Timestamp(f"{y}-01-01") - pd.Timestamp("2020-03-01")).days / 365.25
        sc = [sum(mar(stream(T[(s, i)], "2020-03-01", f"{y}-01-01"), ty) for s in oos) for i in range(len(VARIANTS))]
        b = int(np.argmax(sc)); picks.append(VARIANTS[b]["label"])
        for s in oos:
            oos[s].append(stream(T[(s, b)], f"{y}-01-01", f"{y+1}-01-01"))
    print("\nwalk-forward picks:", dict(zip(TESTS, picks)))
    for s in oos:
        for lab, x in (("walk-forward trail choice", pd.concat(oos[s])),
                       ("v2.1 fixed", pd.concat([stream(T[(s, 0)], f"{y}-01-01", f"{y+1}-01-01") for y in TESTS]))):
            r = x.R.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
            print(f"  {s} {lab:26s} 2022-26: {r.sum()/4.75:5.1f}R/yr DD {dd:4.1f}R")
