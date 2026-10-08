"""ONE-SHOT holdout of the faster two-sided breakout candidates chosen on dev (Oct 2026, round 2)."""
import numpy as np, common as C, families2 as G
cands = {"B 4h n40 sl2.5 tp4R hold24 ema100": dict(tf=240, n=40, sl_atr=2.5, tp_R=4, hold_h=24, ema_n=100),
         "B2 2h n40 sl2.5 hold48 ema100": dict(tf=120, n=40, sl_atr=2.5, tp_R=0, hold_h=48, ema_n=100)}
m = C.load("BTCUSDT")
for nm, cfg in cands.items():
    tr = G.intraday_channel(m, **cfg)
    for per, (a, b) in {"dev": C.DEV, "holdout": C.HOLDOUT}.items():
        x = C.between(tr, a, b); s = C.stats(x)
        mo = x.groupby(x.exit_time.dt.to_period("M")).R.sum()
        yrs = (np.datetime64(b) - np.datetime64(a)).astype(int) / 365.25
        print(nm, per, {k: s[k] for k in ['trades', 'win_rate', 'total_R', 'PF', 'maxDD_R', 'avg_hold_h', 'long_R', 'short_R']},
              f"trades/yr {len(x)/yrs:.0f}, months positive {(mo>0).mean()*100:.0f}%", C.yearly(x).to_dict())
        if per == "holdout":
            for risk in (0.02, 0.03):
                eq = 1000 * np.cumprod(1 + risk * x.R.to_numpy()); pk = np.maximum.accumulate(eq)
                print(f"   $1000 at {risk*100:.0f}% risk -> ${eq[-1]:.0f} after {yrs:.1f}y, max DD {((pk-eq)/pk).max()*100:.0f}%")
