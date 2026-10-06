"""
Trend-breakout strategy ("TBO") - the pure decision logic, shared by the live bot and the parity test.

Rules (4-hour candles, UTC, Binance last price), v2 defaults:
  Trend      : last CLOSED daily close vs its EMA(ema_n). Above -> longs allowed, below -> shorts allowed
               (shorts only if sides == "both"). With slope_d > 0 the EMA must also be rising (longs) /
               falling (shorts) versus slope_d days earlier, otherwise no order.
  Weekend    : no_weekend -> no new orders placed on Saturday / Sunday (UTC).
  Stretch    : no new order while the daily close is more than max_ext x daily ATR14 away from the daily EMA.
  Entry      : at each 4h candle close, while flat: a stop order at the highest high of the last `n`
               closed 4h candles (long) / lowest low (short). The order lives until the next 4h close,
               where it is cancelled and re-placed at the new level.
  Stop loss  : sl_atr x ATR(atr_n) of the 4h candles, measured from the fill price (server-side order).
  Trail exit : at a 4h close, a long is closed if close < highest high of the last trail_m candles
               - trail_atr x ATR (mirror for shorts).
  Breakeven  : once price has gone be_R x the stop distance in favour, the stop moves to entry + be_off x dist.
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
    max_ext: float = 4.0         # in daily ATR14 from the daily EMA; 99 = off

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
