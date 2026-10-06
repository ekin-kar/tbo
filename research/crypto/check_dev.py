import numpy as np, common as C, families as F
A = dict(tf=240, n=20, sl_atr=1.5, hold_h=120, ema_n=50, sides="both", trail_m=12, trail_atr=2.0)
B = dict(A, sides="long")
for sym in ["BTCUSDT", "ETHUSDT"]:
    m = C.load(sym); end = np.searchsorted(m["t"], C.D.minutes(C.DEV[1])); m = {k: v[:end] for k, v in m.items()}
    for nm, cfg in [("A both", A), ("B long", B)]:
        for fee in [0.0006, 0.0010]:
            C.FEE_SIDE = fee
            tr = C.between(F.channel_breakout(m, **cfg), *C.DEV)
            s = C.stats(tr)
            print(sym, nm, f"fee {fee*100:.2f}%", {k: s[k] for k in ['trades','win_rate','total_R','PF','maxDD_R','avg_hold_h','long_R','short_R']}, C.yearly(tr).to_dict())
    C.FEE_SIDE = 0.0006
