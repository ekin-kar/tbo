"""
BTC / ETH strategy families for the scans. Each function returns trades (see common.run).
All decisions use CLOSED candles and act at the next 1m bar ('act'); costs in common.
"""
import functools
import numpy as np
from common import D, E, I, run

_resample = D.resample


_M1 = {}


@functools.lru_cache(maxsize=32)
def _rs(key, tf, shift):
    m1 = _M1[key]
    if shift:
        m1 = dict(m1, t=m1["t"] - shift)
    return _resample(m1, tf)


def resample(m1, tf, shift=0):
    """Cached resample; shift (minutes) moves the candle boundaries, e.g. a day starting at 08:00 UTC."""
    key = id(m1["t"])
    _M1[key] = m1            # keeps the array alive, so its id cannot be reused
    return _rs(key, tf, shift)

MKT, STP = E.MARKET, E.STOP


def _ema_daily_side(m1, d, ema_n, at_idx):
    """+1/-1 = last closed daily close above/below its EMA, mapped onto 1m indices at_idx."""
    if ema_n <= 0:
        return np.zeros(len(at_idx))
    e = I.ema(d["c"], ema_n)
    side = np.where(d["c"] > e, 1, -1)
    k = np.searchsorted(d["act"], at_idx, side="right") - 1   # last daily candle already acted on
    out = np.where(k >= ema_n, side[np.clip(k, 0, None)], 0)
    return out


def channel_breakout(m1, tf=240, n=20, sl_atr=2.0, tp_R=0.0, hold_h=48, ema_n=0, atr_n=14, sides="both",
                     trail_m=0, trail_atr=0.0, rand_seed=None):
    """Stop orders at the n-bar high/low of tf candles, renewed each candle; SL k*ATR(tf); exit TP / time.
    trail_m > 0: also exit at a candle close below max(high of the last trail_m candles) - trail_atr * ATR
    (mirror for shorts). rand_seed: benchmark - same exits, but market entries at random candles with the
    same count and side mix (filters kept)."""
    c = resample(m1, tf)
    hi = I.rolling_max(c["h"], n); lo = I.rolling_min(c["l"], n); a = I.atr(c["h"], c["l"], c["c"], atr_n)
    act = c["act"]
    ok = (~np.isnan(hi)) & (~np.isnan(a)) & (np.arange(len(act)) > max(n, 3 * atr_n)) & (act < len(m1["t"]))
    d = resample(m1, 1440)
    tside = _ema_daily_side(m1, d, ema_n, act)
    o = E.Orders(m1)
    sl = sl_atr * a
    tp = tp_R * sl if tp_R > 0 else np.zeros(len(a))
    if trail_m > 0:
        hh = I.rolling_max(c["h"], trail_m); ll = I.rolling_min(c["l"], trail_m)
        xl = c["c"] < hh - trail_atr * a; xs = c["c"] > ll + trail_atr * a
        good = act < len(m1["t"])
        o.exit_long[act[good & xl]] = True
        o.exit_short[act[good & xs]] = True
    if rand_seed is not None:
        real = channel_breakout(m1, tf, n, sl_atr, tp_R, hold_h, ema_n, atr_n, sides, trail_m, trail_atr)
        rng = np.random.default_rng(rand_seed)
        for side, slot in ((1, 0), (-1, 1)):
            k = int((real["dir"] == side).sum())
            cand = np.flatnonzero(ok & (tside * side >= 0))
            if k == 0 or len(cand) == 0:
                continue
            pick = np.sort(rng.choice(cand, size=min(k * 3, len(cand)), replace=False))  # 3x: some fall inside trades
            o.place(act[pick], MKT, side, sl[pick], tp[pick], slot=slot)
        tr = run(m1, o, max_bars=int(hold_h * 60))
        return tr.sample(n=min(len(tr), len(real)), random_state=rand_seed).sort_values("entry_time")
    if sides in ("both", "long"):
        m = ok & (tside >= 0)
        o.place(act[m], STP, 1, sl[m], tp[m], price=hi[m], expiry_min=tf, slot=0)
    if sides in ("both", "short"):
        m = ok & (tside <= 0)
        o.place(act[m], STP, -1, sl[m], tp[m], price=lo[m], expiry_min=tf, slot=1)
    return run(m1, o, max_bars=int(hold_h * 60))


def vol_breakout(m1, k=0.5, sl_k=0.5, tp_R=0.0, hold_h=24, ema_n=0, start_min=0, sides="both"):
    """Larry Williams: at the day open (UTC + start_min) stop orders at open +- k * yesterday's range."""
    tf = 1440
    d = resample(m1, tf, start_min)                            # session starting at start_min UTC
    rng = np.r_[np.nan, (d["h"] - d["l"])[:-1]]
    idx = np.searchsorted(m1["t"], d["t"] + start_min)          # first bar of the session
    ok = ~np.isnan(rng) & (idx < len(m1["t"])) & (np.arange(len(idx)) > 60)
    op = m1["o"][np.clip(idx, 0, len(m1["t"]) - 1)]
    tside = _ema_daily_side(m1, resample(m1, 1440), ema_n, idx)
    o = E.Orders(m1)
    sl = sl_k * rng
    tp = tp_R * sl if tp_R > 0 else np.zeros(len(sl))
    if sides in ("both", "long"):
        m = ok & (tside >= 0)
        o.place(idx[m], STP, 1, sl[m], tp[m], price=op[m] + k * rng[m], expiry_min=tf, slot=0)
    if sides in ("both", "short"):
        m = ok & (tside <= 0)
        o.place(idx[m], STP, -1, sl[m], tp[m], price=op[m] - k * rng[m], expiry_min=tf, slot=1)
    return run(m1, o, max_bars=int(hold_h * 60), max_trades_day=1)


def volc(m1, tf=60, ratio=0.8, n=10, sl_atr=1.5, tp_R=2.5, hold_h=20, life_h=24, ema_n=0):
    """USDJPY VOLC idea: ATR14 < ratio*ATR100 -> stop orders at the n-bar high/low."""
    c = resample(m1, tf)
    a14 = I.atr(c["h"], c["l"], c["c"], 14); a100 = I.atr(c["h"], c["l"], c["c"], 100)
    hi = I.rolling_max(c["h"], n); lo = I.rolling_min(c["l"], n)
    act = c["act"]
    ok = (a14 < ratio * a100) & (np.arange(len(act)) > 300) & (act < len(m1["t"]))
    tside = _ema_daily_side(m1, resample(m1, 1440), ema_n, act)
    o = E.Orders(m1)
    sl = sl_atr * a14; tp = tp_R * sl
    m = ok & (tside >= 0)
    o.place(act[m], STP, 1, sl[m], tp[m], price=hi[m], expiry_min=int(life_h * 60), slot=0)
    m = ok & (tside <= 0)
    o.place(act[m], STP, -1, sl[m], tp[m], price=lo[m], expiry_min=int(life_h * 60), slot=1)
    return run(m1, o, max_bars=int(hold_h * 60))


def dip_buy(m1, tf=60, rsi_n=2, rsi_lo=10, ema_n=200, sl_atr=3.0, tp_atr=1.5, hold_h=24, sides="both"):
    """Short-term mean reversion in the direction of the daily trend: RSI(n) extreme on tf candles."""
    c = resample(m1, tf)
    r = I.rsi_wilder(c["c"], rsi_n); a = I.atr(c["h"], c["l"], c["c"], 14)
    act = c["act"]
    ok = (np.arange(len(act)) > 100) & (act < len(m1["t"])) & ~np.isnan(r)
    tside = _ema_daily_side(m1, resample(m1, 1440), ema_n, act)
    o = E.Orders(m1)
    if sides in ("both", "long"):
        m = ok & (r < rsi_lo) & (tside >= 0)
        o.place(act[m], MKT, 1, sl_atr * a[m], tp_atr * a[m], slot=0)
    if sides in ("both", "short"):
        m = ok & (r > 100 - rsi_lo) & (tside <= 0)
        o.place(act[m], MKT, -1, sl_atr * a[m], tp_atr * a[m], slot=1)
    return run(m1, o, max_bars=int(hold_h * 60))
