"""
Strategy families. Each has few parameters and a reason to exist.
All of them: no entries 20:30-23:00 UTC (rollover), stops always set, one position at a time.
"""
import numpy as np
from .. import data as D, engine as E, indicators as I

ROLL_START, ROLL_END = 20 * 60 + 30, 23 * 60      # no entries in this UTC window


def _base(m1):
    """No new orders AND no resting orders during the rollover window: spreads spike there,
    which fills stop orders at terrible prices (measured on USDJPY: about -1R per such trade)."""
    od = E.Orders(m1)
    mod = D.minute_of_day(m1["t"])
    roll = (mod >= ROLL_START) & (mod < ROLL_END)
    od.allow_entry[roll] = False
    od.allow_fill[roll] = False
    return od, mod


def session_breakout(m1, box_end=7 * 60, sl_atr=1.5, rr=2.0, buf=0.0, tf=15, atr_n=14,
                     entry_deadline=16 * 60, eod=20 * 60, box_start=0):
    """
    Asian range breakout: build the box from 00:00 UTC to box_end, then place stop orders
    on both sides. First one to trigger wins; flat by end of day.
    """
    b = D.resample(m1, tf)
    a = I.atr(b["h"], b["l"], b["c"], atr_n)
    mod_b = D.minute_of_day(b["t"])
    day = D.day_index(b["t"])
    inbox = (mod_b >= box_start) & (mod_b < box_end)
    # box high/low per day, taken at the candle that closes at box_end
    hi = np.full(len(b["t"]), np.nan); lo = np.full(len(b["t"]), np.nan)
    cur_d, ch, cl = -1, -np.inf, np.inf
    for i in range(len(b["t"])):
        if day[i] != cur_d:
            cur_d, ch, cl = day[i], -np.inf, np.inf
        if inbox[i]:
            ch = max(ch, b["h"][i]); cl = min(cl, b["l"][i])
        hi[i], lo[i] = ch, cl
    k = np.flatnonzero((mod_b >= box_end - tf) & (mod_b < box_end) & np.isfinite(a) & (hi > lo))
    od, mod = _base(m1)
    atrk = a[k]
    exp = entry_deadline - box_end
    od.place(b["act"][k], E.STOP, 1, sl_atr * atrk, sl_atr * rr * atrk,
             price=hi[k] + buf * atrk, expiry_min=exp, slot=0)
    od.place(b["act"][k], E.STOP, -1, sl_atr * atrk, sl_atr * rr * atrk,
             price=lo[k] - buf * atrk, expiry_min=exp, slot=1)
    od.force_exit[eod_mask(m1, eod)] = True
    return od


def trend_pullback(m1, tf=15, sl_atr=2.0, rr=2.0, fast=20, slow=50, trend=200, atr_n=14):
    """Trade with the trend after a pullback: EMA50>EMA200, price dips below EMA20 and closes back above."""
    b = D.resample(m1, tf)
    c = b["c"]
    e_f, e_s, e_t = I.ema(c, fast), I.ema(c, slow), I.ema(c, trend)
    a = I.atr(b["h"], b["l"], b["c"], atr_n)
    up = (e_s > e_t) & (c > e_f) & (np.r_[False, c[:-1] <= e_f[:-1]]) & (np.r_[False, b["l"][:-1] < e_s[:-1]])
    dn = (e_s < e_t) & (c < e_f) & (np.r_[False, c[:-1] >= e_f[:-1]]) & (np.r_[False, b["h"][:-1] > e_s[:-1]])
    k = np.flatnonzero((up | dn) & np.isfinite(a))
    od, mod = _base(m1)
    od.place(b["act"][k], E.MARKET, np.where(up[k], 1, -1), sl_atr * a[k], sl_atr * rr * a[k])
    return od


def mean_reversion(m1, tf=15, k_atr=2.5, sl_atr=2.0, rr=1.0, ref=100, atr_n=14):
    """Fade stretches away from a slow EMA: enter when price closes k ATR beyond it."""
    b = D.resample(m1, tf)
    c = b["c"]
    e = I.ema(c, ref)
    a = I.atr(b["h"], b["l"], b["c"], atr_n)
    long_ = c < e - k_atr * a
    short = c > e + k_atr * a
    # only the first bar of a stretch
    long_ = long_ & ~np.r_[False, long_[:-1]]
    short = short & ~np.r_[False, short[:-1]]
    k = np.flatnonzero((long_ | short) & np.isfinite(a))
    od, mod = _base(m1)
    od.place(b["act"][k], E.MARKET, np.where(long_[k], 1, -1), sl_atr * a[k], sl_atr * rr * a[k])
    return od


def eod_mask(m1, eod):
    """First bar at or after `eod` each day - robust when the exact minute has no data."""
    t = m1["t"]
    mod = D.minute_of_day(t)
    day = D.day_index(t)
    idx = np.flatnonzero(mod >= eod)
    if len(idx) == 0:
        return np.zeros(len(t), np.bool_)
    first = idx[np.r_[True, day[idx][1:] != day[idx][:-1]]]
    m = np.zeros(len(t), np.bool_)
    m[first] = True
    return m


def _day_starts(t):
    d = D.day_index(t)
    return np.flatnonzero(np.r_[True, d[1:] != d[:-1]]), d


def opening_range(m1, session=7 * 60, or_min=30, sl_atr=1.5, rr=2.0, tf=15, atr_n=14,
                  hold_min=8 * 60, eod=20 * 60):
    """Opening-range breakout: range of the first or_min minutes after a session open."""
    t = m1["t"]
    mod = D.minute_of_day(t)
    day = D.day_index(t)
    inor = (mod >= session) & (mod < session + or_min)
    hi = np.where(inor, m1["h"], -np.inf)
    lo = np.where(inor, m1["l"], np.inf)
    starts, _ = _day_starts(t)
    dhi = np.maximum.reduceat(hi, starts)
    dlo = np.minimum.reduceat(lo, starts)
    b = D.resample(m1, tf)
    a = I.atr(b["h"], b["l"], b["c"], atr_n)
    atr_at = np.interp(t, b["t"] + tf, np.nan_to_num(a))   # last closed HTF ATR at each minute
    k = np.flatnonzero((mod == session + or_min) & np.isfinite(dhi[np.searchsorted(starts, np.arange(len(t)), "right") - 1]))
    didx = np.searchsorted(starts, k, "right") - 1
    ok = np.isfinite(dhi[didx]) & np.isfinite(dlo[didx]) & (atr_at[k] > 0)
    k, didx = k[ok], didx[ok]
    od, mod_ = _base(m1)
    A = atr_at[k]
    od.place(k, E.STOP, 1, sl_atr * A, sl_atr * rr * A, price=dhi[didx], expiry_min=hold_min, slot=0)
    od.place(k, E.STOP, -1, sl_atr * A, sl_atr * rr * A, price=dlo[didx], expiry_min=hold_min, slot=1)
    od.force_exit[eod_mask(m1, eod)] = True
    return od


def donchian(m1, tf=60, lookback=20, sl_atr=2.0, rr=2.0, atr_n=14, trend=0):
    """Classic channel breakout on closed candles; optional EMA200 trend filter."""
    b = D.resample(m1, tf)
    a = I.atr(b["h"], b["l"], b["c"], atr_n)
    hh = I.rolling_max(b["h"], lookback)
    ll = I.rolling_min(b["l"], lookback)
    c = b["c"]
    e = I.ema(c, 200)
    up = (c > np.r_[np.nan, hh[:-1]]) & (np.isfinite(a))
    dn = (c < np.r_[np.nan, ll[:-1]]) & (np.isfinite(a))
    if trend:
        up &= c > e
        dn &= c < e
    k = np.flatnonzero(up | dn)
    od, _ = _base(m1)
    od.place(b["act"][k], E.MARKET, np.where(up[k], 1, -1), sl_atr * a[k], sl_atr * rr * a[k])
    return od


def vol_contraction(m1, tf=60, ratio=0.7, lookback=10, sl_atr=1.5, rr=2.0, atr_n=14, hold_min=24 * 60):
    """After a quiet stretch (ATR14 well below ATR100), trade the break of the recent range."""
    b = D.resample(m1, tf)
    a = I.atr(b["h"], b["l"], b["c"], atr_n)
    slow = I.atr(b["h"], b["l"], b["c"], 100)
    quiet = a < ratio * slow
    hh = I.rolling_max(b["h"], lookback)
    ll = I.rolling_min(b["l"], lookback)
    k = np.flatnonzero(quiet & np.isfinite(a) & np.isfinite(hh) & np.isfinite(ll))
    od, _ = _base(m1)
    od.place(b["act"][k], E.STOP, 1, sl_atr * a[k], sl_atr * rr * a[k], price=hh[k], expiry_min=hold_min, slot=0)
    od.place(b["act"][k], E.STOP, -1, sl_atr * a[k], sl_atr * rr * a[k], price=ll[k], expiry_min=hold_min, slot=1)
    return od


def momentum_close(m1, tf=60, pct=0.75, sl_atr=2.0, rr=2.0, atr_n=14, trend=200):
    """Continuation: a candle closing near its extreme, in the direction of the trend."""
    b = D.resample(m1, tf)
    a = I.atr(b["h"], b["l"], b["c"], atr_n)
    rng = b["h"] - b["l"]
    pos = np.divide(b["c"] - b["l"], np.where(rng > 0, rng, np.nan))
    e = I.ema(b["c"], trend)
    up = (pos > pct) & (b["c"] > e) & np.isfinite(a)
    dn = (pos < 1 - pct) & (b["c"] < e) & np.isfinite(a)
    k = np.flatnonzero(up | dn)
    od, _ = _base(m1)
    od.place(b["act"][k], E.MARKET, np.where(up[k], 1, -1), sl_atr * a[k], sl_atr * rr * a[k])
    return od


def prev_day_level(m1, sl_atr=1.5, rr=2.0, tf=15, atr_n=14, start=7 * 60, eod=20 * 60, mode="break",
                   min_bars=0):
    """
    Prior day's high/low: trade the break of it, or fade the first touch.
    min_bars > 0: "prior day" = the most recent day with at least min_bars 1m bars, so Sunday's
    2-hour stub session (and holiday stubs) are skipped and Monday uses Friday.
    """
    t = m1["t"]
    mod = D.minute_of_day(t)
    starts, day = _day_starts(t)
    dhi = np.maximum.reduceat(m1["h"], starts)
    dlo = np.minimum.reduceat(m1["l"], starts)
    nbars = np.diff(np.r_[starts, len(t)])
    didx = np.searchsorted(starts, np.arange(len(t)), "right") - 1
    if min_bars > 0:
        full = nbars >= min_bars
        prev_full = np.full(len(starts), -1)
        last = -1
        for i in range(len(starts)):
            prev_full[i] = last
            if full[i]:
                last = i
        pf = prev_full[didx]
        phi = np.where(pf >= 0, dhi[np.maximum(pf, 0)], np.nan)
        plo = np.where(pf >= 0, dlo[np.maximum(pf, 0)], np.nan)
    else:
        phi = np.r_[np.nan, dhi[:-1]][didx]
        plo = np.r_[np.nan, dlo[:-1]][didx]
    b = D.resample(m1, tf)
    a = I.atr(b["h"], b["l"], b["c"], atr_n)
    atr_at = np.interp(t, b["t"] + tf, np.nan_to_num(a))
    k = np.flatnonzero((mod == start) & np.isfinite(phi) & np.isfinite(plo) & (atr_at > 0))
    od, mod_ = _base(m1)
    A = atr_at[k]
    if mode == "break":
        od.place(k, E.STOP, 1, sl_atr * A, sl_atr * rr * A, price=phi[k], expiry_min=eod - start, slot=0)
        od.place(k, E.STOP, -1, sl_atr * A, sl_atr * rr * A, price=plo[k], expiry_min=eod - start, slot=1)
    else:  # fade the touch
        od.place(k, E.LIMIT, -1, sl_atr * A, sl_atr * rr * A, price=phi[k], expiry_min=eod - start, slot=0)
        od.place(k, E.LIMIT, 1, sl_atr * A, sl_atr * rr * A, price=plo[k], expiry_min=eod - start, slot=1)
    od.force_exit[eod_mask(m1, eod)] = True
    return od


def vwap_reversion(m1, tf=15, k_atr=1.5, sl_atr=1.5, rr=1.0, atr_n=14, start=7 * 60, eod=20 * 60):
    """Fade a stretch away from the session VWAP (built from 00:00 UTC), flat by end of day."""
    t = m1["t"]
    starts, _ = _day_starts(t)
    tp = (m1["h"] + m1["l"] + m1["c"]) / 3.0
    v = np.maximum(m1["v"], 1)
    cpv = np.cumsum(tp * v)
    cv = np.cumsum(v)
    base_pv = np.repeat(np.r_[0.0, cpv[starts[1:] - 1]], np.diff(np.r_[starts, len(t)]))
    base_v = np.repeat(np.r_[0.0, cv[starts[1:] - 1]], np.diff(np.r_[starts, len(t)]))
    vwap = (cpv - base_pv) / np.maximum(cv - base_v, 1)
    b = D.resample(m1, tf)
    a = I.atr(b["h"], b["l"], b["c"], atr_n)
    ends = np.clip(b["act"] - 1, 0, len(t) - 1)
    c, vw, A = b["c"], vwap[ends], a
    mod_b = D.minute_of_day(b["t"])
    act_ok = (mod_b >= start) & (mod_b < eod - 60)
    long_ = (c < vw - k_atr * A) & act_ok & np.isfinite(A)
    short = (c > vw + k_atr * A) & act_ok & np.isfinite(A)
    long_ &= ~np.r_[False, long_[:-1]]
    short &= ~np.r_[False, short[:-1]]
    k = np.flatnonzero(long_ | short)
    od, mod_ = _base(m1)
    od.place(b["act"][k], E.MARKET, np.where(long_[k], 1, -1), sl_atr * A[k], sl_atr * rr * A[k])
    od.force_exit[eod_mask(m1, eod)] = True
    return od


def cat2_199(m1, box_start=0, box_end=90, delay=15, fast=100, slow=200, slope_lb=2, atr_n=30,
             sl_mult=4.4, tp_mult=5.4, long_buf=0.0, short_buf=0.2, pull=0.45, eod=20 * 60, tf=5,
             keep_2355=False):
    """
    Faithful rebuild of the user's old Cat2_199-RR1_23 bot (m5 chart):
    box of m5 candles 00:00-01:30 UTC; from 01:45, a close breaking the box (plus buffer) with
    EMA100/200 trend + slope agreement places a LIMIT at close -/+ 0.45 ATR30, valid one candle.
    SL 4.4 ATR, TP 5.4 ATR, flat 20:00. Daily caps (2 trades, stop after a loss) are applied
    afterwards in the runner, since trades never overlap.
    """
    b = D.resample(m1, tf)
    c = b["c"]
    ef, es = I.ema(c, fast), I.ema(c, slow)
    a = I.atr(b["h"], b["l"], b["c"], atr_n)
    mod_close = (D.minute_of_day(b["t"]) + tf) % 1440      # candle close time = when OnBar sees it
    day = D.day_index(b["t"] + tf)                           # the UTC day in which OnBar sees the candle
    n = len(c)
    hi = np.full(n, np.nan); lo = np.full(n, np.nan)
    cur, h0, l0 = -1, np.nan, np.nan
    for i in range(n):
        if day[i] != cur:
            cur, h0, l0 = day[i], np.nan, np.nan
        # the bot adds the candle that just CLOSED when OnBar fires at a minute in [box_start, box_end)
        in_box = box_start <= mod_close[i] < box_end
        if mod_close[i] == 0 and not keep_2355:
            in_box = False      # OnBar at 00:00 adds the 23:55 candle, then OnTick's midnight reset wipes it
        if in_box:
            h0 = b["h"][i] if np.isnan(h0) else max(h0, b["h"][i])
            l0 = b["l"][i] if np.isnan(l0) else min(l0, b["l"][i])
        hi[i], lo[i] = h0, l0
    slope = es - np.r_[np.full(slope_lb, np.nan), es[:-slope_lb]]
    c2 = np.r_[np.nan, c[:-1]]
    trig_h = hi + long_buf * a
    trig_l = lo - short_buf * a
    hunt = (mod_close >= box_end + delay) & (mod_close < eod) & np.isfinite(hi) & np.isfinite(a)
    up = hunt & (c > trig_h) & (c2 <= trig_h) & (ef > es) & (c > es) & (slope > 0)
    dn = hunt & (c < trig_l) & (c2 >= trig_l) & (ef < es) & (c < es) & (slope < 0)
    k = np.flatnonzero(up | dn)
    od, _ = _base(m1)
    direction = np.where(up[k], 1, -1)
    price = c[k] - direction * pull * a[k]
    od.place(b["act"][k], E.LIMIT, direction, sl_mult * a[k], tp_mult * a[k], price=price, expiry_min=tf)
    od.force_exit[eod_mask(m1, eod)] = True
    return od


def apply_daily_caps(tr, max_trades=2, loss_r=-0.1):
    """Old-bot rules: max 2 trades a day; after a losing trade (net loss beyond the friction filter) stop for the day."""
    tr = tr.sort_values("entry_time").copy()
    keep = []
    for _, g in tr.groupby(tr.entry_time.dt.date):
        n = 0
        for idx, row in g.iterrows():
            if n >= max_trades:
                break
            keep.append(idx)
            n += 1
            if row.R <= loss_r:
                break
    return tr.loc[keep]
