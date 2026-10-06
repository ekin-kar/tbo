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
                     trail_m=0, trail_atr=0.0, rand_seed=None, buffer_atr=0.0, be_R=0.0, be_off=0.0,
                     vol_lo=0.0, vol_hi=1.0, slope_d=0, ema2_n=0, no_weekend=False, max_ext=99.0, vratio=0.0, trail_k=0.0, trail_start=0.0, vr_max=99.0,
                     early_h=0, early_R=0.0, ext_h=0, ext_R=0.0, confirm_tf=0, sl_mode="atr", swing_k=6,
                     er_n=0, er_min=0.0, co_m1=None, entry_mask=None, atr_tf=0, retest_h=0, retest_off=0.0):
    """Stop orders at the n-bar high/low of tf candles, renewed each candle; SL k*ATR(tf); exit TP / time.
    trail_m > 0: also exit at a candle close below max(high of the last trail_m candles) - trail_atr * ATR
    (mirror for shorts). rand_seed: benchmark - same exits, but market entries at random candles with the
    same count and side mix (filters kept)."""
    c = resample(m1, tf)
    hi = I.rolling_max(c["h"], n); lo = I.rolling_min(c["l"], n); a = I.atr(c["h"], c["l"], c["c"], atr_n)
    if atr_tf and atr_tf != tf:                        # stop sized from ATR of atr_tf candles (last closed one)
        ca = resample(m1, atr_tf); aa = I.atr(ca["h"], ca["l"], ca["c"], atr_n)
        ka = np.searchsorted(ca["act"], c["act"], side="right") - 1
        a = np.where(ka >= 0, aa[np.clip(ka, 0, None)], np.nan)
    act = c["act"]
    ok = (~np.isnan(hi)) & (~np.isnan(a)) & (np.arange(len(act)) > max(n, 3 * atr_n)) & (act < len(m1["t"]))
    d = resample(m1, 1440)
    tside = _ema_daily_side(m1, d, ema_n, act)
    # ── optional entry filters (all known at the candle close) ──
    if vol_lo > 0 or vol_hi < 1:                       # ATR/price percentile over the last 500 candles
        rel = a / c["c"]
        import pandas as pd
        pct = pd.Series(rel).rolling(500, min_periods=200).rank(pct=True).to_numpy()
        ok &= (pct >= vol_lo) & (pct <= vol_hi)
    if slope_d > 0 or ema2_n > 0 or max_ext < 99:
        d = resample(m1, 1440)
        k = np.searchsorted(d["act"], act, side="right") - 1
        kk = np.clip(k, 0, None)
        if slope_d > 0:                                # daily EMA rising (long) / falling (short) over slope_d days
            e = I.ema(d["c"], ema_n)
            sl_sign = np.sign(e[kk] - e[np.clip(kk - slope_d, 0, None)])
            tside = np.where(sl_sign == tside, tside, 0)
        if ema2_n > 0:                                 # second, slower daily trend filter must agree
            s2 = np.where(d["c"] > I.ema(d["c"], ema2_n), 1, -1)[kk]
            tside = np.where(s2 == tside, tside, 0)
        if max_ext < 99:                               # skip when price is too far above / below the daily EMA
            e = I.ema(d["c"], ema_n); ad = I.atr(d["h"], d["l"], d["c"], 14)
            ext = np.abs(d["c"][kk] - e[kk]) / ad[kk]
            ok &= ext <= max_ext
        tside = np.where(tside == 0, 2, tside)         # 2 = blocked (neither >=0 for shorts nor <=0 for longs)
        tside = np.where(tside == 2, np.nan, tside)
    if er_n > 0:                                       # daily Kaufman efficiency ratio (trend cleanliness)
        d_ = resample(m1, 1440)
        cc = d_["c"]
        er = np.full(len(cc), np.nan)
        num = np.abs(cc[er_n:] - cc[:-er_n])
        den = np.convolve(np.abs(np.diff(cc)), np.ones(er_n), "valid")
        er[er_n:] = num / np.maximum(den, 1e-12)
        kd = np.clip(np.searchsorted(d_["act"], act, side="right") - 1, 0, None)
        ok &= er[kd] >= er_min
    if co_m1 is not None:                              # the other coin's trend (side + slope) must agree
        dc = resample(co_m1, 1440)
        ec = I.ema(dc["c"], ema_n)
        sc = np.where(dc["c"] > ec, 1, -1)
        if slope_d > 0:
            slc = np.sign(ec - np.r_[np.full(slope_d, np.nan), ec[:-slope_d]])
            sc = np.where(slc == sc, sc, 0)
        when = m1["t"][np.clip(act, 0, len(m1["t"]) - 1)]
        kc = np.searchsorted(dc["t"] + 1440, when, side="right") - 1    # last co-coin daily candle closed by then
        co_side = np.where(kc >= ema_n, sc[np.clip(kc, 0, None)], 0)
        tside = np.where(co_side == tside, tside, np.nan)
    if vr_max < 99:                                    # 7-day vs 90-day daily-return volatility (study: wild = worse)
        import pandas as pd
        d_ = resample(m1, 1440)
        lr = pd.Series(np.r_[np.nan, np.diff(np.log(d_["c"]))])
        vr = (lr.rolling(7).std() / lr.rolling(90).std()).to_numpy()
        kd = np.clip(np.searchsorted(d_["act"], act, side="right") - 1, 0, None)
        ok &= ~(vr[kd] > vr_max)
    if vratio > 0:                                     # last closed candle's volume vs its 20-candle average
        import pandas as pd
        va = pd.Series(c["v"]).rolling(20).mean().to_numpy()
        ok &= c["v"] >= vratio * va
    if no_weekend:
        wd = ((c["t"] + tf) // 1440 + 3) % 7           # weekday of the moment the order is placed
        ok &= wd < 5
    o = E.Orders(m1)
    if entry_mask is not None:                         # entries / fills only where the mask is True
        o.allow_entry[:] = entry_mask; o.allow_fill[:] = entry_mask
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
    buf = buffer_atr * a
    sl_l = sl_s = sl
    if sl_mode == "swing":                             # stop beyond the recent swing, 0.5-2.5 ATR from the level
        sw_lo = I.rolling_min(c["l"], swing_k); sw_hi = I.rolling_max(c["h"], swing_k)
        sl_l = np.clip(hi + buf - sw_lo + 0.1 * a, 0.5 * a, 2.5 * a)
        sl_s = np.clip(sw_hi - (lo - buf) + 0.1 * a, 0.5 * a, 2.5 * a)
    tp_l = tp_R * sl_l if tp_R > 0 else np.zeros(len(a)); tp_s = tp_R * sl_s if tp_R > 0 else np.zeros(len(a))
    if retest_h > 0:                                   # breakout happened in candle k -> limit back at the broken level
        prev_hi = np.r_[np.nan, hi[:-1]]; prev_lo = np.r_[np.nan, lo[:-1]]
        bl = ok & (tside >= 0) & (c["h"] > prev_hi) & (c["c"] > prev_hi) if sides in ("both", "long") else np.zeros(len(a), bool)
        bs = ok & (tside <= 0) & (c["l"] < prev_lo) & (c["c"] < prev_lo) if sides in ("both", "short") else np.zeros(len(a), bool)
        o.place(act[bl], E.LIMIT, 1, sl_l[bl], tp_l[bl], price=(prev_hi + retest_off * a)[bl], expiry_min=int(retest_h * 60), slot=0)
        o.place(act[bs], E.LIMIT, -1, sl_s[bs], tp_s[bs], price=(prev_lo - retest_off * a)[bs], expiry_min=int(retest_h * 60), slot=1)
        return run(m1, o, max_bars=int(hold_h * 60), be_R=be_R, be_off=be_off, tp="maker", entry="maker",
                   early_bars=int(early_h * 60), early_R=early_R, ext_bars=int(ext_h * 60), ext_R=ext_R)
    if confirm_tf > 0:                                 # enter at market after a confirm_tf candle CLOSES beyond the level
        cf = resample(m1, confirm_tf)
        k4 = np.searchsorted(act, cf["act"], side="right") - 1       # governing 4h decision for each small candle
        valid = (k4 >= 0) & (cf["act"] < len(m1["t"]))
        k4c = np.clip(k4, 0, None)
        gl = ok[k4c] & valid & (tside[k4c] >= 0) & (cf["c"] > (hi + buf)[k4c]) if sides in ("both", "long") else np.zeros(len(k4), bool)
        gs = ok[k4c] & valid & (tside[k4c] <= 0) & (cf["c"] < (lo - buf)[k4c]) if sides in ("both", "short") else np.zeros(len(k4), bool)
        o.place(cf["act"][gl], MKT, 1, sl_l[k4c][gl], tp_l[k4c][gl], slot=0)
        o.place(cf["act"][gs], MKT, -1, sl_s[k4c][gs], tp_s[k4c][gs], slot=1)
    else:
        if sides in ("both", "long"):
            m = ok & (tside >= 0)
            o.place(act[m], STP, 1, sl_l[m], tp_l[m], price=(hi + buf)[m], expiry_min=tf, slot=0)
        if sides in ("both", "short"):
            m = ok & (tside <= 0)
            o.place(act[m], STP, -1, sl_s[m], tp_s[m], price=(lo - buf)[m], expiry_min=tf, slot=1)
    return run(m1, o, max_bars=int(hold_h * 60), be_R=be_R, be_off=be_off, tp="maker",
               trail_k=trail_k, trail_start=trail_start, early_bars=int(early_h * 60), early_R=early_R,
               ext_bars=int(ext_h * 60), ext_R=ext_R)


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
