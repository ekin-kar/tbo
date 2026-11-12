"""
VOLC sleeve signal (v3.1), shared by the live sleeve (volc.py) and the research (research/crypto/core/v31deploy.py), so
both compute exactly the same numbers. numpy only (+ strategy.py's indicators).

The idea: after a long quiet spell (4h ATR14 well below ATR100) a breakout of the recent 4h range tends to run a short
way. At each 4h close (UTC), on CLOSED candles:
  quiet      ATR14 / ATR100 of the 4h candles < sq
  building   open interest (USD value, the last 5-minute sample of the 4h candle's last hour) is higher than 24 h earlier
             (change > oi_min)
  direction  'hybrid': the daily trend side (last closed daily close vs its EMA(ema_n)), and both sides while the market
             is choppy (daily efficiency ratio ER(er_n) < er_max)
  orders     stop orders at the n-candle 4h high (long) / low (short), valid for one 4h candle; stop sl_atr x ATR14,
             take-profit tp_R x the stop distance, closed after hold_h hours
  not near   no order within excl_h hours after a panic-sleeve trigger (a forced-liquidation flush)
"""
import numpy as np

from strategy import atr, ema

DEFAULTS = dict(n=10, sq=0.6, oi_min=0.0, ema_n=50, er_n=10, er_max=0.25, mode="hybrid", sl_atr=1.0, tp_R=1.5, hold_h=36,
                excl_h=12, warmup=122)


def er(close, n):
    """Kaufman efficiency ratio of the last n daily moves (net move / sum of absolute moves), NaN if too short."""
    c = np.asarray(close, float)
    if len(c) <= n:
        return float("nan")
    den = float(np.sum(np.abs(np.diff(c[-n - 1:]))))
    return abs(c[-1] - c[-1 - n]) / max(den, 1e-12)


def decide(h4, l4, c4, daily_close, oi_now, oi_prev, p=None):
    """h4, l4, c4: CLOSED 4h candles, oldest first (the last one has just closed); daily_close: CLOSED daily closes.
    oi_now / oi_prev: open interest at the end of the last candle / 24 h earlier (NaN = unknown -> no order).
    Returns dict(long, short, dist, tp_R, info): stop levels (None = no order) and the stop distance."""
    p = dict(DEFAULTS, **(p or {}))
    h4, l4, c4 = (np.asarray(v, float) for v in (h4, l4, c4))
    out = dict(long=None, short=None, dist=0.0, tp_R=float(p["tp_R"]), info={})
    if len(c4) < int(p["warmup"]):
        return out
    a = atr(h4, l4, c4, 14)
    a14, a100 = float(a[-1]), float(atr(h4, l4, c4, 100)[-1])
    dc = np.asarray(daily_close, float)
    side = 0
    if len(dc) > 1:
        side = 1 if dc[-1] > ema(dc, int(p["ema_n"]))[-1] else -1
    e = er(dc, int(p["er_n"]))
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = a14 / a100 if a100 > 0 else float("nan")
        doi = oi_now / oi_prev - 1 if (oi_prev and np.isfinite(oi_prev) and np.isfinite(oi_now)) else float("nan")
    out["info"] = dict(atr14=a14, atr100=a100, ratio=ratio, doi=doi, side=side, er=e)
    if not (np.isfinite(a14) and a14 > 0 and np.isfinite(ratio) and ratio < p["sq"] and np.isfinite(doi) and doi > p["oi_min"]):
        return out
    rng = bool(np.isfinite(e) and e < p["er_max"])
    if p["mode"] == "trend":
        ok_l, ok_s = side > 0, side < 0
    elif p["mode"] == "range2":
        ok_l = ok_s = rng
    else:                                               # hybrid
        ok_l, ok_s = side > 0 or rng, side < 0 or rng
    n = int(p["n"])
    out["dist"] = float(p["sl_atr"]) * a14
    if ok_l:
        out["long"] = float(h4[-n:].max())
    if ok_s:
        out["short"] = float(l4[-n:].min())
    return out


def near_panic(t_ms, triggers, excl_h):
    """True if a panic trigger (its signal hour's close, ms) happened in the excl_h hours before t_ms (strictly before)."""
    return any(t_ms - excl_h * 3_600_000 <= tr < t_ms for tr in triggers)
