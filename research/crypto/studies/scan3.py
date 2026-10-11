"""Dev-period (2020-03..2023) scans of the second-strategy candidates; also correlation with TBO by month."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import itertools, sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F, families3 as G3
from wf2 import V21

FAM = sys.argv[1]
SYM = sys.argv[2] if len(sys.argv) > 2 else "BTCUSDT"
GRIDS = {
    "fb": (G3.failed_breakout, dict(tf=[60, 240], n=[10, 20, 40], sl_atr=[0.25, 0.5, 1.0], tp_R=[1.0, 2.0, 3.0],
                                    tp_mid=[False, True], hold_h=[24, 72], regime=["any", "notrend", "counter", "with"])),
    "crash": (G3.crash_rebound, dict(tf=[5, 15, 60], k=[2.0, 3.0, 4.0], vmult=[0.0, 3.0], sl_atr=[1.5, 3.0],
                                     tp_atr=[1.0, 2.0, 4.0], hold_h=[4, 24], sides=["both", "long"])),
}
M = None


def init():
    global M
    m = C.load(SYM); end = np.searchsorted(m["t"], C.D.minutes(C.DEV[1]))
    M = {k: v[:end] for k, v in m.items()}


def one(kw):
    tr = C.between(GRIDS[FAM][0](M, **kw), *C.DEV)
    if len(tr) < 40:
        return None
    s = C.stats(tr); y = C.yearly(tr)
    mo = tr.groupby(tr.exit_time.dt.to_period("M")).R.sum()
    row = dict(kw, trades=len(tr), win=s["win_rate"], R=s["total_R"], PF=s["PF"], DD=s["maxDD_R"], hold=s["avg_hold_h"],
               L=s["long_R"], S=s["short_R"], mpos=round((mo > 0).mean(), 2))
    for yr in range(2020, 2024):
        row[f"y{yr}"] = float(y.get(yr, 0))
    row["yrs_pos"] = sum(row[f"y{yr}"] > 0 for yr in range(2020, 2024))
    row["MAR"] = round(row["R"] / 3.83 / max(row["DD"], 3), 2)
    return row


if __name__ == "__main__":
    fn, grid = GRIDS[FAM]
    combos = [dict(zip(grid, v)) for v in itertools.product(*grid.values())]
    with Pool(4, initializer=init) as p:
        rows = [r for r in p.imap_unordered(one, combos, chunksize=4) if r]
    df = pd.DataFrame(rows); df.to_csv(C.ROOT / "research" / "results" / f"crypto_{SYM}_{FAM}_dev.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)
    print(len(combos), "combos;", f"share PF>1.2 & 4/4 years positive: {((df.PF > 1.2) & (df.yrs_pos == 4)).mean():.3f}")
    print(df[df.yrs_pos >= 3].sort_values("MAR", ascending=False).head(15).to_string(index=False))
    keys = list(grid)
    for k in keys:
        print(f"  {k:8s}", df.groupby(k).MAR.median().round(2).to_dict())
