"""
Trend-breakout strategy ("TBO") - the pure decision logic, shared by the live bot and the parity test.

Rules (4-hour candles, UTC, Binance last price), v2 defaults:
  Trend      : last CLOSED daily close vs its EMA(ema_n). Above -> longs allowed, below -> shorts allowed
               (shorts only if sides == "both"). With slope_d > 0 the EMA must also be rising (longs) /
               falling (shorts) versus slope_d days earlier, otherwise no order.
  Weekend    : no_weekend -> no new orders placed on Saturday / Sunday (UTC).
  Stretch    : no new order while the daily close is more than max_ext x daily ATR14 away from the daily EMA.
  Open int.  : oi_lookback_h > 0 -> no new order while Binance open interest (USD value, hourly) is down by
               oi_min_chg or more versus oi_lookback_h hours earlier (positions are being closed, not opened:
               breakouts then follow through less). Missing / stale data -> no filter.
  OI low     : oi_low_days > 0 -> no new order while open interest (USD value, hourly) ranks in the lowest
               oi_low_rank of its last oi_low_days days (v2.8; nearly always a short after a sell-off: nobody
               left to force out, the breakdown fizzles). Fewer than half the window known / stale -> no filter.
  Entry      : at each 4h candle close, while flat: a stop order at the highest high of the last `n`
               closed 4h candles (long) / lowest low (short). The order lives until the next 4h close,
               where it is cancelled and re-placed at the new level.
  Stop loss  : sl_atr x ATR(atr_n) of the 4h candles, measured from the fill price (server-side order).
  Trail exit : at a 4h close, a long is closed if close < highest high of the last trail_m candles
               - trail_atr x ATR (mirror for shorts).
  Breakeven  : once price has gone be_R x the stop distance in favour, the stop moves to entry + be_off x dist.
  Profit lock: once price has gone lock_R x the stop distance in favour, the stop moves to entry + lock_to x dist (v2.6).
  Time exit  : closed max_hold_h hours after the fill. No take profit.

Indicators match research/engine/indicators.py (cTrader style): EMA seeded with the first value,
ATR = exponential smoothing of the true range seeded with the true range of bar 1.
"""
from dataclasses import dataclass, asdict

import numpy as np


@dataclass
class Params:
    symbol: str = "BTCUSDT"
    tf_min: int = 240
    n: int = 20
    atr_n: int = 14
    sl_atr: float = 1.0
    ema_n: int = 50
    trail_m: int = 0
    trail_atr: float = 0.0
    max_hold_h: float = 120.0
    sides: str = "both"          # "long" or "both"
    slope_d: int = 5
    no_weekend: bool = True
    be_R: float = 1.5
    be_off: float = 0.0
    lock_R: float = 0.0          # profit lock: at +lock_R the stop moves to +lock_to (0 = off)
    lock_to: float = 0.0
    max_ext: float = 4.0         # in daily ATR14 from the daily EMA; 99 = off
    oi_lookback_h: int = 0       # open-interest filter: hours back (hourly rows); 0 = off
    oi_min_chg: float = -0.03    # skip new orders when OI changed by this much or less over the lookback
    oi_low_days: int = 0         # OI-low filter: window in days of hourly rows; 0 = off
    oi_low_rank: float = 0.2     # skip new orders while OI ranks below this fraction of its window

    def to_dict(self):
        return asdict(self)


def ema(x, n):
    x = np.asarray(x, float)
    out = np.empty(len(x))
    a = 2.0 / (n + 1.0)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out


def atr(h, l, c, n):
    h, l, c = (np.asarray(v, float) for v in (h, l, c))
    out = np.full(len(h), np.nan)
    if len(h) < 2:
        return out
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    a = 2.0 / (n + 1.0)
    out[1] = tr[0]
    for i in range(2, len(h)):
        out[i] = out[i - 1] + a * (tr[i - 1] - out[i - 1])
    return out


def trend_side(daily_close, ema_n, slope_d=0):
    """+1 / -1 from the CLOSED daily candles (oldest first); 0 = no trade (not enough history, or the EMA
    slope over slope_d days disagrees)."""
    if len(daily_close) <= max(ema_n, slope_d):
        return 0
    e = ema(daily_close, ema_n)
    side = 1 if daily_close[-1] > e[-1] else -1
    if slope_d > 0 and np.sign(e[-1] - e[-1 - slope_d]) != side:
        return 0
    return side


def oi_change(hist, order_ms, lookback_h):
    """hist: [(timestamp_ms, open interest USD value), ...] hourly, oldest first. Change from lookback_h rows
    before the last row strictly before order_ms to that row; None when the data is missing or stale (>= 3 h old)."""
    ts = [t for t, _ in hist]
    i = int(np.searchsorted(ts, order_ms, side="left")) - 1
    if i < lookback_h or order_ms - ts[i] >= 3 * 3600_000:
        return None
    v0, v1 = hist[i - lookback_h][1], hist[i][1]
    if not (v0 > 0 and v1 > 0):
        return None
    return v1 / v0 - 1


def oi_blocks(p: "Params", chg):
    return p.oi_lookback_h > 0 and chg is not None and chg <= p.oi_min_chg


def oi_rank(hist, order_ms, window_rows, min_rows):
    """hist: [(timestamp_ms, open interest USD value), ...] hourly, oldest first. Percentile (0-1] of the last row
    strictly before order_ms among the last window_rows rows up to it, ties averaged (pandas rank(pct=True), as the
    research); None when fewer than min_rows usable rows or the last row is stale (>= 3 h old)."""
    ts = [t for t, _ in hist]
    i = int(np.searchsorted(ts, order_ms, side="left")) - 1
    if i < 0 or order_ms - ts[i] >= 3 * 3600_000:
        return None
    w = np.array([v for _, v in hist[max(0, i - window_rows + 1):i + 1]], float)
    w = w[np.isfinite(w) & (w > 0)]
    if len(w) < min_rows or not (hist[i][1] > 0):
        return None
    x = hist[i][1]
    return (np.sum(w < x) + (np.sum(w == x) + 1) / 2) / len(w)


def oi_low_blocks(p: "Params", rank):
    return p.oi_low_days > 0 and rank is not None and rank < p.oi_low_rank


@dataclass
class Decision:
    atr: float
    long_trigger: float | None      # stop-buy level, None = no long order
    short_trigger: float | None
    sl_dist: float
    exit_long: bool                 # trail exit for an open long
    exit_short: bool
    trend: int


def decide(p: Params, h, l, c, daily_close, weekday=0, daily_high=None, daily_low=None) -> Decision:
    """h, l, c: CLOSED 4h candles, oldest first (the last one has just closed).
    daily_*: CLOSED daily candles. weekday: UTC weekday (Mon=0) of the moment the order is placed."""
    h, l, c = (np.asarray(v, float) for v in (h, l, c))
    a = atr(h, l, c, p.atr_n)[-1]
    hi = h[-p.n:].max()
    lo = l[-p.n:].min()
    side = trend_side(daily_close, p.ema_n, p.slope_d)
    ok = len(c) > max(p.n, 3 * p.atr_n) and np.isfinite(a) and a > 0 and not (p.no_weekend and weekday >= 5)
    if ok and p.max_ext < 99 and daily_high is not None and len(daily_close) > p.ema_n:
        dc = np.asarray(daily_close, float)
        ad = atr(daily_high, daily_low, dc, 14)[-1]
        ok = bool(abs(dc[-1] - ema(dc, p.ema_n)[-1]) <= p.max_ext * ad)
    long_t = hi if ok and side >= 0 and side != 0 else None
    short_t = lo if ok and side <= 0 and side != 0 and p.sides == "both" else None
    hh = h[-p.trail_m:].max() if p.trail_m > 0 else np.inf
    ll = l[-p.trail_m:].min() if p.trail_m > 0 else -np.inf
    return Decision(atr=float(a), long_trigger=long_t, short_trigger=short_t, sl_dist=float(p.sl_atr * a),
                    exit_long=bool(p.trail_m > 0 and c[-1] < hh - p.trail_atr * a),
                    exit_short=bool(p.trail_m > 0 and c[-1] > ll + p.trail_atr * a), trend=side)
