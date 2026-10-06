"""
Candidate SECOND strategies, meant to earn when TBO (trend breakout) does not.
  failed_breakout : fade a breakout that closed back inside the channel (TBO's typical loser)
  crash_rebound   : buy after a liquidation-style crash candle / short after a spike
"""
import numpy as np
from common import D, E, I, run
from families import resample, _ema_daily_side

MKT = E.MARKET


def failed_breakout(m1, tf=240, n=20, sl_atr=0.5, tp_R=2.0, tp_mid=False, hold_h=48, regime="any", ema_n=50,
                    slope_d=5, atr_n=14, entry="taker"):
    """Candle k pokes above the prior n-candle high but CLOSES back below it -> short at the next open
    (mirror at lows). SL = candle extreme + sl_atr*ATR. TP = tp_R x risk, or the channel middle (tp_mid).
    regime: 'any'; 'notrend' = only when TBO's trend filter is off (EMA side and slope disagree);
            'counter' = only fades AGAINST the daily trend side; 'with' = only fades in the trend's favour."""
    c = resample(m1, tf)
    h, l, cl = c["h"], c["l"], c["c"]
    ph = np.r_[np.nan, I.rolling_max(h, n)[:-1]]          # prior n-candle high (excluding candle k)
    pl = np.r_[np.nan, I.rolling_min(l, n)[:-1]]
    a = I.atr(h, l, cl, atr_n)
    act = c["act"]
    ok = np.isfinite(ph) & np.isfinite(a) & (np.arange(len(act)) > 3 * max(n, atr_n)) & (act < len(m1["t"]))
    short_sig = ok & (h > ph) & (cl < ph)
    long_sig = ok & (l < pl) & (cl > pl)
    d = resample(m1, 1440)
    side = _ema_daily_side(m1, d, ema_n, act)                 # +1 / -1 by EMA side
    if regime != "any":
        k = np.clip(np.searchsorted(d["act"], act, side="right") - 1, 0, None)
        e = I.ema(d["c"], ema_n)
        slope = np.sign(e[k] - e[np.clip(k - slope_d, 0, None)])
        trending = slope == side                               # TBO would trade in direction `side`
        if regime == "notrend":
            short_sig &= ~trending; long_sig &= ~trending
        elif regime == "counter":
            short_sig &= trending & (side > 0); long_sig &= trending & (side < 0)
        elif regime == "with":
            short_sig &= trending & (side < 0); long_sig &= trending & (side > 0)
    o = E.Orders(m1)
    # risk from the next open (~close) to beyond the candle extreme
    sl_s = (h - cl) + sl_atr * a
    sl_l = (cl - l) + sl_atr * a
    tp_s = np.where(tp_mid, cl - (ph + pl) / 2, tp_R * sl_s) if tp_mid else tp_R * sl_s
    tp_l = np.where(tp_mid, (ph + pl) / 2 - cl, tp_R * sl_l) if tp_mid else tp_R * sl_l
    m = short_sig & (sl_s > 0) & (tp_s > 0)
    o.place(act[m], MKT, -1, sl_s[m], tp_s[m], slot=0)
    m = long_sig & (sl_l > 0) & (tp_l > 0)
    o.place(act[m], MKT, 1, sl_l[m], tp_l[m], slot=1)
    return run(m1, o, max_bars=int(hold_h * 60), tp="maker")


def crash_rebound(m1, tf=15, k=2.5, vmult=0.0, sl_atr=2.0, tp_atr=2.0, hold_h=12, sides="both", atr_n=48):
    """A tf candle moving more than k x ATR (and volume > vmult x its 96-candle mean) -> fade it at the next open."""
    c = resample(m1, tf)
    a = I.atr(c["h"], c["l"], c["c"], atr_n)
    ret = c["c"] - c["o"]
    act = c["act"]
    ok = np.isfinite(a) & (np.arange(len(act)) > 200) & (act < len(m1["t"]))
    if vmult > 0:
        import pandas as pd
        va = pd.Series(c["v"]).rolling(96).mean().shift(1).to_numpy()
        ok &= c["v"] > vmult * va
    o = E.Orders(m1)
    if sides in ("both", "long"):
        m = ok & (ret < -k * a)
        o.place(act[m], MKT, 1, sl_atr * a[m], tp_atr * a[m], slot=0)
    if sides in ("both", "short"):
        m = ok & (ret > k * a)
        o.place(act[m], MKT, -1, sl_atr * a[m], tp_atr * a[m], slot=1)
    return run(m1, o, max_bars=int(hold_h * 60), tp="maker")


def weekend_momo(m1, th=0.5, hold_h=24, sl_k=1.0, tp_k=0.0, entry="cme", lookback_d=20):
    """Weekend continuation: move from the CME Friday close (16:00 Chicago) to the CME Sunday open (17:00
    Chicago) of at least th x the daily return st.dev (last lookback_d days) -> trade in its direction at the
    Sunday open. entry='cme' (Sunday 17:00 Chicago) or 'mon' (Monday 00:00 UTC).
    SL = sl_k x daily st.dev x price; TP = tp_k x the same (0 = none); time exit hold_h."""
    import pandas as pd
    t = m1["t"]
    o = E.Orders(m1)
    d = resample(m1, 1440)
    lr = np.r_[np.nan, np.diff(np.log(d["c"]))]
    sd = pd.Series(lr).rolling(lookback_d).std().to_numpy()
    fris = pd.date_range(pd.Timestamp(int(t[0]) * 60, unit="s").normalize() + pd.Timedelta(days=7),
                         pd.Timestamp(int(t[-1]) * 60, unit="s") - pd.Timedelta(days=3), freq="W-FRI")
    idx, dirs, sl, tp = [], [], [], []
    for f in fris:
        fc = pd.Timestamp(f.date()).tz_localize("America/Chicago") + pd.Timedelta(hours=16)
        so = fc + pd.Timedelta(days=2, hours=1)
        tf_ = int(fc.tz_convert("UTC").tz_localize(None).value // 60_000_000_000)
        ts_ = int(so.tz_convert("UTC").tz_localize(None).value // 60_000_000_000)
        if entry == "mon":
            ts_ = int((pd.Timestamp(f.date()) + pd.Timedelta(days=3)).value // 60_000_000_000)
        i0 = np.searchsorted(t, tf_); i1 = np.searchsorted(t, ts_)
        if i1 >= len(t) - 1:
            break
        k = np.searchsorted(d["t"], tf_ // 1440 * 1440) - 1          # last daily candle closed before Friday's day
        if k < lookback_d or not np.isfinite(sd[k]):
            continue
        gap = np.log(m1["o"][i1] / m1["o"][i0])
        if abs(gap) < th * sd[k]:
            continue
        px = m1["o"][i1]
        idx.append(i1); dirs.append(int(np.sign(gap))); sl.append(sl_k * sd[k] * px)
        tp.append(tp_k * sd[k] * px if tp_k > 0 else 0.0)
    if idx:
        o.place(np.array(idx), MKT, np.array(dirs), np.array(sl), np.array(tp), slot=0)
    return run(m1, o, max_bars=int(hold_h * 60), tp="maker")
