"""1/5/15-minute families on BTC AND ETH, dev period 2020-03..2023 only (2024-26 stays unseen)."""
import itertools, sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families2 as G2, families4 as G4

FAM = sys.argv[1]
GRIDS = {
    "bb": (G4.bb_fade, dict(tf=[1, 5, 15], n=[20, 50], k=[2.0, 3.0, 4.0], sl_k=[0.5, 1.0], tp=["mid", "half"],
                            hold_h=[1, 4], trend_n=[0, 50])),
    "vwap": (G4.vwap_rev, dict(tf=[1, 5, 15], k=[1.5, 2.5, 4.0, 6.0], sl_k=[0.5, 1.0], hold_h=[2, 8])),
    "rsi": (G4.rsi_fade, dict(tf=[1, 5, 15], n=[2, 6], lo=[3, 10], sl_atr=[1.0, 2.0], tp_atr=[0.5, 1.0, 2.0],
                              hold_h=[1, 4], trend_n=[0, 50])),
    "ema": (G4.ema_cross, dict(tf=[1, 5, 15], fast=[9, 20], slow=[50, 100], sl_atr=[1.5, 3.0], tp_R=[0, 2, 4],
                               hold_h=[4, 24], trend_n=[0, 50])),
    "sq": (G4.squeeze, dict(tf=[5, 15], n=[20], bb_k=[2.0], kc_k=[1.5, 2.0], brk=[10, 20], sl_atr=[1.0, 2.0],
                            tp_R=[1.5, 3.0], hold_h=[4, 24], trend_n=[0, 50])),
    "chan": (G2.intraday_channel, dict(tf=[5, 15], n=[20, 50, 100], sl_atr=[1.5, 3.0], tp_R=[0, 2, 4], hold_h=[4, 24],
                                       ema_n=[0, 50])),
}
DATA = {}


def one(args):
    sym, kw = args
    if sym not in DATA:
        m = C.load(sym); end = np.searchsorted(m["t"], C.D.minutes(C.DEV[1]))
        DATA[sym] = {k: v[:end] for k, v in m.items()}
    tr = C.between(GRIDS[FAM][0](DATA[sym], **kw), *C.DEV)
    if len(tr) < 50:
        return dict(sym=sym, **kw, trades=len(tr), R=np.nan, gross=np.nan, MAR=np.nan, yrs=0)
    r = tr.R.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    y = tr.groupby(tr.entry_time.dt.year).R.sum()
    return dict(sym=sym, **kw, trades=len(tr), per_day=round(len(tr) / 1400, 2), win=round((r > 0).mean() * 100),
                R=round(r.sum(), 1), gross=round(tr.R_gross.sum(), 1), avgR=round(r.mean(), 3),
                MAR=round(r.sum() / 3.83 / max(dd, 3), 2), yrs=int((y > 0).sum()))


if __name__ == "__main__":
    fn, grid = GRIDS[FAM]
    combos = [dict(zip(grid, v)) for v in itertools.product(*grid.values())]
    jobs = [(s, c) for s in ("BTCUSDT", "ETHUSDT") for c in combos]
    with Pool(4) as p:
        df = pd.DataFrame(p.map(one, jobs, chunksize=4))
    df.to_csv(C.ROOT / "research" / "results" / f"crypto_scalp_{FAM}_dev.csv", index=False)
    keys = list(grid)
    w = df.pivot_table(index=keys, columns="sym", values=["MAR", "R", "gross", "trades", "yrs"]).reset_index()
    w.columns = ["_".join(map(str, c)).strip("_") for c in w.columns]
    w["both"] = w[["MAR_BTCUSDT", "MAR_ETHUSDT"]].min(axis=1)
    good = w[(w.both > 0.5) & (w.yrs_BTCUSDT >= 3) & (w.yrs_ETHUSDT >= 3)]
    print(f"{FAM}: {len(combos)} settings x 2 coins | profitable on BOTH after fees: {(w.both > 0).sum()} | "
          f"robust (MAR>0.5 both, >=3/4 years both): {len(good)} | profitable BEFORE fees on both: "
          f"{((w.gross_BTCUSDT > 0) & (w.gross_ETHUSDT > 0)).sum()}")
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)
    print(w.sort_values("both", ascending=False).head(6).to_string(index=False))
