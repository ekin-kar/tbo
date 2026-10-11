"""TBO v1.0 vs v2 candidates: BTC (tuned) and ETH (untouched), per year, long/short split, $1k compounding."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import numpy as np, pandas as pd
import common as C, families as F
V1 = dict(tf=240, n=20, sl_atr=1.5, hold_h=120, ema_n=50, sides="long", trail_m=12, trail_atr=2.0)
V2L = dict(V1, sl_atr=1.0, trail_m=0, trail_atr=0.0, slope_d=5, no_weekend=True, be_R=1.5)
V2B = dict(V2L, sides="both")
V2BT = dict(V2B, trail_m=12, trail_atr=2.0)
for sym in ["BTCUSDT", "ETHUSDT"]:
    m = C.load(sym)
    for nm, cfg in [("v1.0", V1), ("v2 long", V2L), ("v2 both", V2B), ("v2 both+trail", V2BT)]:
        x = C.between(F.channel_breakout(m, **cfg), "2020-03-01", "2026-10-01").sort_values("exit_time")
        r = x.R.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
        mo = x.groupby(x.exit_time.dt.to_period("M")).R.sum()
        line = f"{sym} {nm:14s} n={len(r):3d} R={r.sum():6.1f} DD={dd:5.1f}R PF={C.stats(x)['PF']} L={x[x.dir>0].R.sum():.0f} S={x[x.dir<0].R.sum():.0f} mo+={(mo>0).mean()*100:.0f}%"
        for risk in (0.02, 0.03):
            e = 1000 * np.cumprod(1 + risk * r); pk = np.maximum.accumulate(e)
            line += f" | {int(risk*100)}%: {((e[-1]/1000)**(1/(6.58*12))-1)*100:.1f}%/mo DD {((pk-e)/pk).max()*100:.0f}%"
        print(line)
        print("     by year:", C.yearly(x).to_dict(), " shorts by year:", x[x.dir < 0].groupby(x[x.dir < 0].entry_time.dt.year).R.sum().round(1).to_dict())
