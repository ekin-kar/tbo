"""Channel breakout vs random entries with identical exits / filters (dev period only)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import sys
import numpy as np
import common as C, families as F

m = C.load(sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT")
end = np.searchsorted(m["t"], C.D.minutes(C.DEV[1]))
m = {k: v[:end] for k, v in m.items()}
cfgs = [dict(tf=240, n=20, sl_atr=1.5, hold_h=120, ema_n=50, sides="both"),
        dict(tf=240, n=20, sl_atr=1.5, hold_h=120, ema_n=50, sides="both", trail_m=12, trail_atr=2.0),
        dict(tf=240, n=20, sl_atr=1.5, hold_h=120, ema_n=0, sides="both"),
        dict(tf=240, n=20, sl_atr=1.5, hold_h=120, ema_n=50, sides="long")]
for cfg in cfgs:
    real = C.between(F.channel_breakout(m, **cfg), *C.DEV)
    rnd = [C.between(F.channel_breakout(m, rand_seed=s, **cfg), *C.DEV) for s in range(20)]
    rr = np.array([x["R"].sum() for x in rnd])
    print(cfg)
    print(f"  real {real['R'].sum():7.1f}R  PF {C.stats(real)['PF']}  n={len(real)} | random mean {rr.mean():6.1f}R "
          f"sd {rr.std():5.1f}  max {rr.max():6.1f}  -> real beats {np.mean(rr < real['R'].sum())*100:.0f}% of random")
