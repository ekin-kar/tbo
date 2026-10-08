"""
Can we tell, BEFORE the 20-candle level breaks, which approaches will break and run?
Moments: 4h closes where TBO's filters allow a trade (daily EMA50 side + 5-day slope, weekday, <= 4 daily ATR from
the EMA) and price closed within d ATR BELOW the 20-candle high (mirror for shorts at the low).
Outcome: did price trade through the level within the next 6 candles (24h)? and the 5-day forward move (in ATR).
Indicators at that close: RSI14, ATR14/ATR100 (squeeze), OBV at its 20-candle high, higher lows, volume build-up.
"""
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V21

COINS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]


def rsi(x, n=14):
    return C.I.rsi_wilder(x, n)


def moments(sym, dmax=1.0):
    m = C.load(sym); c = F.resample(m, 240); d = F.resample(m, 1440)
    h, l, cl, v = c["h"], c["l"], c["c"], c["v"]
    a = C.I.atr(h, l, cl, 14); a100 = C.I.atr(h, l, cl, 100)
    hi = C.I.rolling_max(h, 20); lo = C.I.rolling_min(l, 20)
    r = rsi(cl, 14)
    obv = np.cumsum(np.sign(np.r_[0, np.diff(cl)]) * v)
    obv_hi = C.I.rolling_max(obv, 20); obv_lo = C.I.rolling_min(obv, 20)
    vol_build = pd.Series(v).rolling(3).mean().to_numpy() / pd.Series(v).rolling(20).mean().to_numpy()
    lows_up = (pd.Series(l).rolling(5).min() > pd.Series(l).shift(5).rolling(5).min()).to_numpy()
    highs_dn = (pd.Series(h).rolling(5).max() < pd.Series(h).shift(5).rolling(5).max()).to_numpy()
    # TBO trend side (EMA50 side + 5d slope) and the stretch / weekend filters
    e = C.I.ema(d["c"], 50); ad = C.I.atr(d["h"], d["l"], d["c"], 14)
    kd = np.clip(np.searchsorted(d["act"], c["act"], side="right") - 1, 0, None)
    side = np.where(d["c"][kd] > e[kd], 1, -1)
    slope = np.sign(e[kd] - e[np.clip(kd - 5, 0, None)])
    side = np.where(slope == side, side, 0)
    side = np.where((kd >= 60) & (np.abs(d["c"][kd] - e[kd]) <= 4 * ad[kd]), side, 0)
    wd = ((c["t"] + 240) // 1440 + 3) % 7
    side = np.where(wd < 5, side, 0)
    n = len(cl); rows = []
    fut_hi = np.array([h[i + 1:i + 7].max() if i + 7 <= n else np.nan for i in range(n)])
    fut_lo = np.array([l[i + 1:i + 7].min() if i + 7 <= n else np.nan for i in range(n)])
    fwd30 = np.r_[cl[30:] - cl[:-30], np.full(30, np.nan)]
    for s in (1, -1):
        dist = (hi - cl) / a if s > 0 else (cl - lo) / a
        msk = (side == s) & (dist > 0) & (dist <= dmax) & np.isfinite(a) & (np.arange(n) > 120)
        brk = (fut_hi >= hi) if s > 0 else (fut_lo <= lo)
        rows.append(pd.DataFrame(dict(
            t=pd.to_datetime(c["t"][msk] * 60, unit="s"), sym=sym[:-4], side=s, dist=dist[msk],
            broke=brk[msk], fwd5d=s * fwd30[msk] / a[msk],
            rsi=(r[msk] if s > 0 else 100 - r[msk]), sqz=(a / a100)[msk],
            obv_new_high=((obv >= obv_hi) if s > 0 else (obv <= obv_lo))[msk],
            higher_lows=(lows_up if s > 0 else highs_dn)[msk], vol_build=vol_build[msk])))
    return pd.concat(rows)


if __name__ == "__main__":
    M = pd.concat([moments(s) for s in COINS], ignore_index=True).dropna(subset=["fwd5d"])
    M["period"] = np.where(M.t < "2024-01-01", "2020-23", "2024-26")
    M.to_pickle(C.D.CACHE / "pre_breakout.pkl")
    base = M.groupby("period").agg(n=("broke", "size"), broke=("broke", "mean"), fwd=("fwd5d", "mean"))
    print("BASELINE: price within 1 ATR below the level, trend filter OK")
    print(base.round(3).to_string())
    def show(name, mask):
        g = M[mask].groupby("period").agg(n=("broke", "size"), broke=("broke", "mean"), fwd=("fwd5d", "mean"))
        cells = " | ".join(f"{p}: n={int(g.loc[p,'n']):5d} breaks {g.loc[p,'broke']*100:4.0f}% (base {base.loc[p,'broke']*100:3.0f}%) "
                           f"5-day move {g.loc[p,'fwd']:+.2f} ATR (base {base.loc[p,'fwd']:+.2f})" for p in g.index)
        print(f"  {name:32s} {cells}")
    print("\nconditions (same moments):")
    for d in (0.25, 0.5, 1.0):
        show(f"distance <= {d} ATR", M.dist <= d)
    for r_ in (50, 60, 70):
        show(f"RSI >= {r_}", M.rsi >= r_)
    show("RSI < 50", M.rsi < 50)
    show("squeeze ATR14/ATR100 <= 0.8", M.sqz <= 0.8)
    show("no squeeze (> 1.1)", M.sqz > 1.1)
    show("OBV at 20-candle high", M.obv_new_high)
    show("higher lows (last 5 vs prior 5)", M.higher_lows)
    show("volume build-up (3 vs 20 > 1.3)", M.vol_build > 1.3)
    show("RSI>=60 & dist<=0.5", (M.rsi >= 60) & (M.dist <= 0.5))
    show("RSI>=60 & squeeze<=0.9 & dist<=0.5", (M.rsi >= 60) & (M.sqz <= 0.9) & (M.dist <= 0.5))
    show("OBV high & higher lows & dist<=0.5", M.obv_new_high & M.higher_lows & (M.dist <= 0.5))
