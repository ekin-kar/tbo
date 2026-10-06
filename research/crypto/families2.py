"""
Intraday, two-sided BTC families (target: about one trade a day). Same conventions as families.py.
"""
import numpy as np
from common import D, E, I, run
from families import resample, _ema_daily_side

MKT, STP, LIM = E.MARKET, E.STOP, E.LIMIT


def session_breakout(m1, r_start=0, r_end=480, trade_end=1320, sl_mode="range", sl_k=1.0, tp_R=2.0,
                     ema_n=0, min_rng=0.0, max_rng=99.0):
    """Range of [r_start, r_end) minutes UTC; at r_end stop orders at its high and low (both sides),
    valid and flat at trade_end. SL = sl_k x range (sl_mode 'range') or sl_k x ATR14 of 1h (sl_mode 'atr').
    min_rng/max_rng: skip days where range / ATR14(1h) is outside [min_rng, max_rng]."""
    t = m1["t"]
    day = t // 1440
    days = np.unique(day)
    h1 = resample(m1, 60)
    a1 = I.atr(h1["h"], h1["l"], h1["c"], 14)
    o = E.Orders(m1)
    starts = np.searchsorted(t, days * 1440 + r_start)
    ends = np.searchsorted(t, days * 1440 + r_end)
    stop_at = np.searchsorted(t, days * 1440 + trade_end)
    good = (ends > starts) & (ends < len(t))
    hi = np.full(len(days), np.nan); lo = np.full(len(days), np.nan)
    for i in np.flatnonzero(good):
        hi[i] = m1["h"][starts[i]:ends[i]].max(); lo[i] = m1["l"][starts[i]:ends[i]].min()
    k = np.searchsorted(h1["act"], ends, side="right") - 1          # last closed 1h candle at r_end
    atr = a1[np.clip(k, 0, len(a1) - 1)]
    rng = hi - lo
    ok = good & np.isfinite(rng) & np.isfinite(atr) & (rng > 0) & (np.arange(len(days)) > 30)
    ok &= (rng / atr >= min_rng) & (rng / atr <= max_rng)
    sl = sl_k * (rng if sl_mode == "range" else atr)
    tp = tp_R * sl if tp_R > 0 else np.zeros(len(sl))
    side = _ema_daily_side(m1, resample(m1, 1440), ema_n, ends)
    life = (trade_end - r_end) % 1440
    idx = ends
    m = ok & (side >= 0)
    o.place(idx[m], STP, 1, sl[m], tp[m], price=hi[m], expiry_min=life, slot=0)
    m = ok & (side <= 0)
    o.place(idx[m], STP, -1, sl[m], tp[m], price=lo[m], expiry_min=life, slot=1)
    fe = stop_at[(stop_at < len(t))]
    o.force_exit[fe] = True
    return run(m1, o, max_trades_day=1, tp="maker")


def meanrev(m1, tf=60, ema_n=20, k=2.0, sl_atr=1.5, tp_frac=1.0, hold_h=12, atr_n=14, trend_n=0, trend_max=99.0,
            entry="maker"):
    """Fade stretches from the tf EMA: limit buy at EMA - k*ATR, limit sell at EMA + k*ATR (renewed each candle).
    TP = tp_frac * k * ATR back towards the EMA, SL = sl_atr * ATR beyond the entry, time stop hold_h.
    trend_n > 0: only when |close - EMA(trend_n)| / ATR <= trend_max (skip strong trends)."""
    c = resample(m1, tf)
    e = I.ema(c["c"], ema_n); a = I.atr(c["h"], c["l"], c["c"], atr_n)
    act = c["act"]
    ok = (np.arange(len(act)) > 3 * max(ema_n, atr_n, trend_n)) & (act < len(m1["t"])) & np.isfinite(a)
    if trend_n > 0:
        et = I.ema(c["c"], trend_n)
        ok &= np.abs(c["c"] - et) / a <= trend_max
    o = E.Orders(m1)
    sl = sl_atr * a; tp = tp_frac * k * a
    o.place(act[ok], LIM, 1, sl[ok], tp[ok], price=(e - k * a)[ok], expiry_min=tf, slot=0)
    o.place(act[ok], LIM, -1, sl[ok], tp[ok], price=(e + k * a)[ok], expiry_min=tf, slot=1)
    return run(m1, o, max_bars=int(hold_h * 60), entry=entry, tp="maker")


def intraday_channel(m1, tf=60, n=20, sl_atr=1.5, tp_R=0.0, hold_h=24, ema_n=0, flat_min=-1, atr_n=14):
    """Channel breakout on tf candles, both sides, shorter holds; flat_min >= 0 forces flat at that UTC minute."""
    c = resample(m1, tf)
    hi = I.rolling_max(c["h"], n); lo = I.rolling_min(c["l"], n); a = I.atr(c["h"], c["l"], c["c"], atr_n)
    act = c["act"]
    ok = (~np.isnan(hi)) & np.isfinite(a) & (np.arange(len(act)) > max(n, 3 * atr_n)) & (act < len(m1["t"]))
    side = _ema_daily_side(m1, resample(m1, 1440), ema_n, act)
    o = E.Orders(m1)
    sl = sl_atr * a; tp = tp_R * sl if tp_R > 0 else np.zeros(len(a))
    m = ok & (side >= 0)
    o.place(act[m], STP, 1, sl[m], tp[m], price=hi[m], expiry_min=tf, slot=0)
    m = ok & (side <= 0)
    o.place(act[m], STP, -1, sl[m], tp[m], price=lo[m], expiry_min=tf, slot=1)
    if flat_min >= 0:
        o.force_exit[(m1["t"] % 1440) == flat_min] = True
    return run(m1, o, max_bars=int(hold_h * 60), tp="maker")


def pullback(m1, tf=60, ema_n=20, k=1.0, sl_atr=1.5, tp_atr=1.5, hold_h=24, trend_n=50, atr_n=14, entry="maker"):
    """Trade WITH the daily trend (close vs daily EMA trend_n): limit buy at EMA(tf, ema_n) - k*ATR in an
    uptrend, limit sell at EMA + k*ATR in a downtrend. TP tp_atr*ATR (maker), SL sl_atr*ATR, time stop."""
    c = resample(m1, tf)
    e = I.ema(c["c"], ema_n); a = I.atr(c["h"], c["l"], c["c"], atr_n)
    act = c["act"]
    ok = (np.arange(len(act)) > 3 * max(ema_n, atr_n)) & (act < len(m1["t"])) & np.isfinite(a)
    side = _ema_daily_side(m1, resample(m1, 1440), trend_n, act)
    o = E.Orders(m1)
    sl = sl_atr * a; tp = tp_atr * a
    m = ok & (side > 0)
    o.place(act[m], LIM, 1, sl[m], tp[m], price=(e - k * a)[m], expiry_min=tf, slot=0)
    m = ok & (side < 0)
    o.place(act[m], LIM, -1, sl[m], tp[m], price=(e + k * a)[m], expiry_min=tf, slot=1)
    return run(m1, o, max_bars=int(hold_h * 60), entry=entry, tp="maker")
