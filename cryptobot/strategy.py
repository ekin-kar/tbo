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
  Profit lock: once price has gone lock_R x the stop distance in favour, the stop moves to entry + lock_to x dist (v2.6;
               v3.0: +5R -> +2R), and a second step at lock2_R -> lock2_to (v3.0: +8R -> +3.5R).
  Stale stop : (v3.0) exactly stale_h hours after the fill, a trade that never reached +be_R and is above stale_thr R
               (at that minute's price) gets its stop moved to entry + stale_to x dist (0 = the entry; if the price is
               below the entry the trade is closed at once).
  Cooldown   : (v3.0) after a trade on this coin closed below cool_R (price R: (exit - entry) x side / dist, i.e. a
               stop-out), no entry fills for cool_h hours from the exit minute; an order of a 4h close inside the
               cooldown waits and is placed when the cooldown ends (until that candle's order expires).
  Failed     : (v3.1) from fb_h hours after the fill, at each hourly close (the open of a minute on the hour), while the
  breakout     trade has never reached +be_R: if it has been +fb_mfe R in favour (1m highs / lows after the fill minute) and
               the last 1m close is below fb_thr R, the stop moves to entry + fb_to x dist (once). A trade closed after
               that starts the cooldown whatever its result (fb_cool).
  Cascade    : (v3.1) when the casc_src coin's (BTC's) trade closes below casc_R (R net of fees and funding, as the research),
               an open trade of this coin in the same direction that filled in that minute or earlier gets its stop
               raised to entry + casc_to x dist (the most favourable stage still wins, so a trade at breakeven is untouched).
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
    lock2_R: float = 0.0         # v3.0 second profit lock: at +lock2_R the stop moves to +lock2_to (0 = off)
    lock2_to: float = 0.0
    stale_h: float = 0.0         # v3.0 stale stop: hours after the fill (0 = off)
    stale_thr: float = -0.3      # ... applied if the trade is above this R then (and never reached +be_R)
    stale_to: float = 0.0        # ... stop moves to entry + stale_to x dist
    cool_h: float = 0.0          # v3.0 cooldown: hours without entry fills after a loss below cool_R (0 = off)
    cool_R: float = -0.5
    fb_h: float = 0.0            # v3.1 failed-breakout stop tighten: first check fb_h hours after the fill (0 = off)
    fb_mfe: float = 0.9          # ... the trade has been at least +fb_mfe R in favour
    fb_thr: float = -0.2         # ... and the last 1m close (on the hour) is below fb_thr R
    fb_to: float = -0.5          # ... stop to entry + fb_to x dist
    fb_cool: bool = True         # ... a trade closed after the tighten starts the cooldown whatever its result
    casc_src: str = ""           # v3.1 cascade: the coin whose stop-outs tighten this coin's open trades ("" = off)
    casc_R: float = -0.5         # ... when its trade closed below this R (net of costs)
    casc_to: float = -0.25       # ... stop to entry + casc_to x dist

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


def stop_level(p: "Params", side, entry, dist, be_done=False, lock_done=False, lock2_done=False, stale_done=False,
               fb_done=False, casc_done=False):
    """The stop price for the stages reached so far (the most favourable of them; the initial stop if none)."""
    lv = [entry - side * dist]
    if fb_done:
        lv.append(entry + side * p.fb_to * dist)
    if casc_done:
        lv.append(entry + side * p.casc_to * dist)
    if be_done:
        lv.append(entry + side * p.be_off * dist)
    if stale_done:
        lv.append(entry + side * p.stale_to * dist)
    if lock_done:
        lv.append(entry + side * p.lock_to * dist)
    if lock2_done:
        lv.append(entry + side * p.lock2_to * dist)
    return max(lv) if side == 1 else min(lv)


def stale_moves(p: "Params", side, entry, dist, price, be_done):
    """At the stale moment: True if the stop moves to entry + stale_to x dist (never reached +be_R, above stale_thr R)."""
    return p.stale_h > 0 and dist > 0 and not be_done and side * (price - entry) > p.stale_thr * dist


def cooldown_after(p: "Params", side, entry, exit_px, dist, fb_done=False):
    """True if a trade that closed at exit_px starts the cooldown (price R below cool_R; v3.1: or the failed-breakout
    tighten fired during the trade and fb_cool is on)."""
    if p.cool_h <= 0 or dist <= 0:
        return False
    return side * (exit_px - entry) / dist < p.cool_R or bool(fb_done and p.fb_cool and p.fb_h > 0)


def fb_fires(p: "Params", side, entry, dist, best, last_close):
    """v3.1 failed breakout, at one hourly check: best = the most favourable 1m high (long) / low (short) since the
    minute after the fill, last_close = the close of the 1m candle just before the hour."""
    if p.fb_h <= 0 or dist <= 0:
        return False
    return side * (best - entry) >= p.fb_mfe * dist and side * (last_close - entry) < p.fb_thr * dist


def net_R(side, entry, exit_px, dist, hours, fee=0.0006, funding_8h=0.0001):
    """A trade's R after fees (per side, on entry and exit) and funding, as the research's trade lists."""
    if dist <= 0:
        return 0.0
    return (side * (exit_px - entry) - fee * (entry + exit_px) - funding_8h * hours / 8 * entry) / dist


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
