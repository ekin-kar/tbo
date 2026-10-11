"""Dev-period (2020-03 .. 2023) grid scans of the BTC families. Holdout years are NOT reported."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import itertools, sys, json
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F, families2 as G

SYM = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
FAM = sys.argv[2] if len(sys.argv) > 2 else "chan"
M = None


def init():
    global M
    m = C.load(SYM)
    end = np.searchsorted(m["t"], C.D.minutes(C.DEV[1]))
    M = {k: v[:end] for k, v in m.items()}


GRIDS = {
    "chan": (F.channel_breakout, dict(tf=[60, 240, 1440], n=[10, 20, 40], sl_atr=[1.5, 2.5, 4.0], tp_R=[0, 2, 4],
                                      hold_h=[24, 72, 120], ema_n=[0, 50], sides=["both", "long"])),
    "wvb": (F.vol_breakout, dict(k=[0.3, 0.5, 0.7, 1.0], sl_k=[0.3, 0.5, 1.0], tp_R=[0, 2, 4], hold_h=[12, 24, 48],
                                 ema_n=[0, 50], start_min=[0, 480, 780], sides=["both", "long"])),
    "chan2": (F.channel_breakout, dict(tf=[240], n=[10, 15, 20, 30, 40], sl_atr=[1.0, 1.5, 2.0, 2.5], tp_R=[0],
                                       hold_h=[72, 120, 168], ema_n=[0, 20, 50, 100], sides=["both", "long"],
                                       trail_m=[0, 6], trail_atr=[2.0])),
    "chan3": (F.channel_breakout, dict(tf=[120, 240, 360, 480], n=[20], sl_atr=[1.5], tp_R=[0], hold_h=[120],
                                       ema_n=[50], sides=["both"], trail_m=[0, 3, 6, 12], trail_atr=[1.0, 2.0, 3.0])),
    "sess": (G.session_breakout, dict(r_start=[0], r_end=[240, 480, 720], trade_end=[1200, 1439], sl_mode=["range", "atr"],
                                      sl_k=[0.5, 1.0, 2.0], tp_R=[0, 1.5, 3.0], ema_n=[0, 50], max_rng=[99.0, 3.0])),
    "sess2": (G.session_breakout, dict(r_start=[1200, 1320, 0, 120], r_end=[480], trade_end=[1200, 1439], sl_mode=["range", "atr"],
                                       sl_k=[0.5, 1.0, 2.0], tp_R=[0, 1.5, 3.0], ema_n=[0, 50])),
    "ich": (G.intraday_channel, dict(tf=[60, 120, 240], n=[10, 20, 40], sl_atr=[1.5, 2.5, 4.0], tp_R=[0, 2, 4],
                                     hold_h=[12, 24, 48], ema_n=[0, 50, 100])),
    "mr": (G.meanrev, dict(tf=[15, 60, 240], ema_n=[20, 50], k=[1.5, 2.5, 3.5], sl_atr=[1.0, 2.0], tp_frac=[0.5, 1.0],
                           hold_h=[6, 24], trend_n=[0, 200], trend_max=[3.0])),
    "pb": (G.pullback, dict(tf=[15, 60, 240], ema_n=[20, 50], k=[0.0, 1.0, 2.0], sl_atr=[1.0, 2.0, 3.0],
                            tp_atr=[1.0, 2.0, 4.0], hold_h=[12, 48], trend_n=[20, 50, 100])),
    "volc": (F.volc, dict(tf=[60, 240], ratio=[0.6, 0.8], n=[10, 20], sl_atr=[1.5, 2.5], tp_R=[2.5, 4], hold_h=[20, 72],
                          ema_n=[0, 50])),
}


def one(kw):
    fn = GRIDS[FAM][0]
    tr = C.between(fn(M, **kw), *C.DEV)
    if len(tr) < 30:
        return None
    s = C.stats(tr)
    y = C.yearly(tr)
    row = dict(kw, **{k: s[k] for k in ["trades", "win_rate", "avg_R", "total_R", "PF", "maxDD_R", "avg_hold_h", "long_R", "short_R"]})
    for yr in range(2020, 2024):
        row[f"y{yr}"] = float(y.get(yr, 0))
    row["yrs_pos"] = int(sum(row[f"y{yr}"] > 0 for yr in range(2020, 2024)))
    mo = tr.groupby(tr["exit_time"].dt.to_period("Q"))["R"].sum()
    row["q_pos"] = round(float((mo > 0).mean()), 2)
    row["per_year"] = round(len(tr) / 3.83, 0)
    return row


if __name__ == "__main__":
    fn, grid = GRIDS[FAM]
    combos = [dict(zip(grid, v)) for v in itertools.product(*grid.values())]
    print(len(combos), "combos", flush=True)
    with Pool(4, initializer=init) as p:
        rows = [r for r in p.imap_unordered(one, combos, chunksize=4) if r]
    df = pd.DataFrame(rows)
    out = C.ROOT / "research" / "results" / f"crypto_{SYM}_{FAM}_dev.csv"
    df.to_csv(out, index=False)
    pd.set_option("display.width", 250)
    print(df.sort_values("total_R", ascending=False).head(25).to_string())
    df["both_pos"] = (df.long_R > 0) & (df.short_R > 0)
    print("\nboth sides positive, >=3 yrs, by quarters positive:")
    print(df[df.both_pos & (df.yrs_pos >= 3)].sort_values("q_pos", ascending=False).head(15).to_string())
    print("\nshare with PF>1.15 and >=3 of 4 dev years positive:", ((df.PF > 1.15) & (df.yrs_pos >= 3)).mean().round(3))
