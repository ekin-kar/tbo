"""ONE-SHOT holdout (2024-01 .. 2026-09) of the configs chosen on dev. Do not tune on this output."""
import numpy as np, common as C, families as F
A = dict(tf=240, n=20, sl_atr=1.5, hold_h=120, ema_n=50, sides="both", trail_m=12, trail_atr=2.0)
B = dict(A, sides="long")
for sym in ["BTCUSDT", "ETHUSDT"]:
    m = C.load(sym)
    for nm, cfg in [("A both", A), ("B long", B)]:
        for fee in [0.0006, 0.0010]:
            C.FEE_SIDE = fee
            tr = C.between(F.channel_breakout(m, **cfg), *C.HOLDOUT)
            s = C.stats(tr)
            print(sym, nm, f"fee {fee*100:.2f}%", {k: s[k] for k in ['trades','win_rate','total_R','PF','maxDD_R','avg_hold_h','long_R','short_R','pos_months']}, C.yearly(tr).to_dict())
        C.FEE_SIDE = 0.0006
        real = C.between(F.channel_breakout(m, **cfg), *C.HOLDOUT)["R"].sum()
        rr = np.array([C.between(F.channel_breakout(m, rand_seed=s, **cfg), *C.HOLDOUT)["R"].sum() for s in range(20)])
        print(f"   random entries: mean {rr.mean():.1f}R sd {rr.std():.1f} max {rr.max():.1f}; real {real:.1f}R beats {np.mean(rr<real)*100:.0f}%")
