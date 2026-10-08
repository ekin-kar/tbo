"""
Classic short-timeframe (1 / 5 / 15 min) families, written to work on ANY market (no BTC-specific logic).
Fade families use resting LIMIT entries (maker) and LIMIT take profits (maker); stops are taker.
"""
import numpy as np
import pandas as pd
from common import D, E, I, run
from families import resample, _ema_daily_side

MKT, STP, LIM = E.MARKET, E.STOP, E.LIMIT


def _std(x, n):
    return pd.Series(x).rolling(n).std().to_numpy()


def bb_fade(m1, tf=5, n=20, k=2.5, sl_k=1.0, tp="mid", hold_h=4, trend_n=0, entry="maker"):
    """Bollinger fade: limit buy at SMA - k*sd, limit sell at SMA + k*sd (renewed each candle).
    TP at the SMA ('mid') or at the opposite... SL = sl_k * k * sd beyond the entry. trend_n > 0: only fade
    TOWARD the daily trend side (buy dips in uptrends / sell rips in downtrends)."""
    c = resample(m1, tf)
    sma = I.sma(c["c"], n); sd = _std(c["c"], n)
    act = c["act"]
    ok = np.isfinite(sd) & (sd > 0) & (act < len(m1["t"])) & (np.arange(len(act)) > n + 5)
    side = _ema_daily_side(m1, resample(m1, 1440), trend_n, act) if trend_n else np.zeros(len(act))
    o = E.Orders(m1)
    sl = sl_k * k * sd
    tpd = k * sd if tp == "mid" else 0.5 * k * sd
    m = ok & (side >= 0)
    o.place(act[m], LIM, 1, sl[m], tpd[m], price=(sma - k * sd)[m], expiry_min=tf, slot=0)
    m = ok & (side <= 0)
    o.place(act[m], LIM, -1, sl[m], tpd[m], price=(sma + k * sd)[m], expiry_min=tf, slot=1)
    return run(m1, o, max_bars=int(hold_h * 60), entry=entry, tp="maker")


def vwap_rev(m1, tf=5, k=2.0, sl_k=1.0, hold_h=6, atr_n=14):
    """Daily (UTC) VWAP reversion: limit buy at VWAP - k*ATR(tf), sell at VWAP + k*ATR; TP at the VWAP."""
    t = m1["t"]; day = t // 1440
    tp_ = (m1["h"] + m1["l"] + m1["c"]) / 3; v = np.maximum(m1["v"], 1e-9)
    pv = pd.Series(tp_ * v).groupby(day).cumsum().to_numpy(); vv = pd.Series(v).groupby(day).cumsum().to_numpy()
    vwap1 = pv / vv
    c = resample(m1, tf)
    a = I.atr(c["h"], c["l"], c["c"], atr_n)
    act = c["act"]
    last = np.clip(act - 1, 0, len(t) - 1)
    vw = vwap1[last]
    mod = (t[last] % 1440)
    ok = np.isfinite(a) & (act < len(t)) & (mod >= 60) & (np.arange(len(act)) > 50)   # skip the first hour of the day
    o = E.Orders(m1)
    lo = vw - k * a; hi = vw + k * a
    o.place(act[ok], LIM, 1, (sl_k * k * a)[ok], (k * a)[ok], price=lo[ok], expiry_min=tf, slot=0)
    o.place(act[ok], LIM, -1, (sl_k * k * a)[ok], (k * a)[ok], price=hi[ok], expiry_min=tf, slot=1)
    return run(m1, o, max_bars=int(hold_h * 60), entry="maker", tp="maker")


def rsi_fade(m1, tf=5, n=2, lo=5, sl_atr=2.0, tp_atr=1.0, hold_h=2, trend_n=0):
    """RSI(n) extreme -> market order the other way at the next open (taker in, maker TP)."""
    c = resample(m1, tf)
    r = I.rsi_wilder(c["c"], n); a = I.atr(c["h"], c["l"], c["c"], 14)
    act = c["act"]
    ok = np.isfinite(r) & np.isfinite(a) & (act < len(m1["t"])) & (np.arange(len(act)) > 50)
    side = _ema_daily_side(m1, resample(m1, 1440), trend_n, act) if trend_n else np.zeros(len(act))
    o = E.Orders(m1)
    m = ok & (r < lo) & (side >= 0)
    o.place(act[m], MKT, 1, sl_atr * a[m], tp_atr * a[m], slot=0)
    m = ok & (r > 100 - lo) & (side <= 0)
    o.place(act[m], MKT, -1, sl_atr * a[m], tp_atr * a[m], slot=1)
    return run(m1, o, max_bars=int(hold_h * 60), tp="maker")


def ema_cross(m1, tf=5, fast=9, slow=21, sl_atr=2.0, tp_R=2.0, hold_h=8, trend_n=0):
    """Momentum: fast EMA crosses slow EMA at a candle close -> market entry; SL ATR, TP R, time exit."""
    c = resample(m1, tf)
    ef = I.ema(c["c"], fast); es = I.ema(c["c"], slow); a = I.atr(c["h"], c["l"], c["c"], 14)
    up = (ef > es) & (np.r_[False, ef[:-1] <= es[:-1]]); dn = (ef < es) & (np.r_[False, ef[:-1] >= es[:-1]])
    act = c["act"]
    ok = np.isfinite(a) & (act < len(m1["t"])) & (np.arange(len(act)) > 3 * slow)
    side = _ema_daily_side(m1, resample(m1, 1440), trend_n, act) if trend_n else np.zeros(len(act))
    o = E.Orders(m1)
    sl = sl_atr * a; tp = tp_R * sl if tp_R > 0 else np.zeros(len(a))
    m = ok & up & (side >= 0); o.place(act[m], MKT, 1, sl[m], tp[m], slot=0)
    m = ok & dn & (side <= 0); o.place(act[m], MKT, -1, sl[m], tp[m], slot=1)
    o.exit_long[act[ok & dn]] = True; o.exit_short[act[ok & up]] = True
    return run(m1, o, max_bars=int(hold_h * 60), tp="maker")


def squeeze(m1, tf=15, n=20, bb_k=2.0, kc_k=1.5, brk=20, sl_atr=1.5, tp_R=2.0, hold_h=12, trend_n=0):
    """TTM-style squeeze: Bollinger bands inside Keltner channels (quiet) -> stop orders at the brk-candle
    high / low, valid one candle."""
    c = resample(m1, tf)
    sma = I.sma(c["c"], n); sd = _std(c["c"], n); a = I.atr(c["h"], c["l"], c["c"], n)
    sq = (bb_k * sd) < (kc_k * a)
    hi = I.rolling_max(c["h"], brk); lo = I.rolling_min(c["l"], brk)
    act = c["act"]
    ok = sq & np.isfinite(hi) & np.isfinite(a) & (act < len(m1["t"])) & (np.arange(len(act)) > 3 * n)
    side = _ema_daily_side(m1, resample(m1, 1440), trend_n, act) if trend_n else np.zeros(len(act))
    o = E.Orders(m1)
    sl = sl_atr * a; tp = tp_R * sl
    m = ok & (side >= 0); o.place(act[m], STP, 1, sl[m], tp[m], price=hi[m], expiry_min=tf, slot=0)
    m = ok & (side <= 0); o.place(act[m], STP, -1, sl[m], tp[m], price=lo[m], expiry_min=tf, slot=1)
    return run(m1, o, max_bars=int(hold_h * 60), tp="maker")


def ema_retest(m1, tf=5, fast=9, slow=21, htf=60, htf_ema=50, htf_slope=3, sl_atr=1.0, stop_tf=60, tp_R=2.0,
               hold_h=12, retest="slow", exit_cross=True, hours=None, offset_atr=0.0):
    """Intraday trend pullback ('EMA retest'):
       trend  : htf candles - close above EMA(htf_ema) AND that EMA rising over htf_slope candles -> longs only
                (mirror for shorts); otherwise no orders.
       setup  : on tf candles EMA(fast) > EMA(slow) (long) / < (short).
       entry  : resting LIMIT at the slow (or fast) EMA - offset_atr*ATR(stop_tf), re-placed every tf candle (maker).
       stop   : sl_atr x ATR14 of stop_tf candles; TP = tp_R x stop (maker); exit at a tf close if the EMAs cross back.
       hours  : optional (start, end) UTC hours in which orders may be placed."""
    c = resample(m1, tf)
    ef = I.ema(c["c"], fast); es = I.ema(c["c"], slow)
    act = c["act"]; n1 = len(m1["t"])
    H = resample(m1, htf)
    he = I.ema(H["c"], htf_ema)
    hside = np.where((H["c"] > he) & (he > np.r_[np.full(htf_slope, np.nan), he[:-htf_slope]]), 1,
                     np.where((H["c"] < he) & (he < np.r_[np.full(htf_slope, np.nan), he[:-htf_slope]]), -1, 0))
    kh = np.searchsorted(H["act"], act, side="right") - 1
    side = np.where(kh >= 3 * htf_ema, hside[np.clip(kh, 0, None)], 0)
    S = resample(m1, stop_tf)
    sa = I.atr(S["h"], S["l"], S["c"], 14)
    ks = np.clip(np.searchsorted(S["act"], act, side="right") - 1, 0, None)
    a = sa[ks]
    ok = np.isfinite(a) & (a > 0) & (act < n1) & (np.arange(len(act)) > 3 * slow)
    if hours is not None:
        hr = ((c["t"] + tf) % 1440) // 60
        ok &= (hr >= hours[0]) & (hr < hours[1])
    lvl = es if retest == "slow" else ef
    o = E.Orders(m1)
    sl = sl_atr * a; tp = tp_R * sl
    m = ok & (side > 0) & (ef > es) & (c["c"] > lvl)          # limit below the market
    o.place(act[m], LIM, 1, sl[m], tp[m], price=(lvl - offset_atr * a)[m], expiry_min=tf, slot=0)
    m = ok & (side < 0) & (ef < es) & (c["c"] < lvl)
    o.place(act[m], LIM, -1, sl[m], tp[m], price=(lvl + offset_atr * a)[m], expiry_min=tf, slot=1)
    if exit_cross:
        good = act < n1
        o.exit_long[act[good & (ef < es)]] = True
        o.exit_short[act[good & (ef > es)]] = True
    return run(m1, o, max_bars=int(hold_h * 60), entry="maker", tp="maker")
