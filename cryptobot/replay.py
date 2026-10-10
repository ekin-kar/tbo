"""
Replays history through strategy.decide() exactly as the live bot uses it (trailing windows of
LIVE_4H_CANDLES 4h candles and LIVE_1D_CANDLES daily candles, decision at each 4h close), with the
research engine's fill rules on 1m bars, and compares the trades with research/engine.

    python cryptobot/replay.py [BTCUSDT] [start] [end]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "research" / "crypto"))
import strategy as S                      # noqa: E402
import common as C, families as F         # noqa: E402

LIVE_4H_CANDLES = 1000
LIVE_1D_CANDLES = 500
EXTRA = HERE.parent / "data" / "extra"


def load_oi(sym):
    """Hourly open interest (USD) from Binance's archive (data/extra, fetch_binance_extra.py): (times ms, values);
    the archive has a few zero rows, which carry the previous value."""
    g = pd.read_csv(EXTRA / f"{sym}_metrics_1h.csv.gz", usecols=["create_time", "sum_open_interest_value"])
    t = pd.to_datetime(g.create_time).values.astype("datetime64[ms]").astype(np.int64)
    o = np.argsort(t)
    v = g.sum_open_interest_value.to_numpy(float)[o]
    v = pd.Series(np.where(v > 0, v, np.nan)).ffill().to_numpy()
    return t[o], v


def replay(m, p: S.Params, start, end, fee=C.FEE_SIDE, oi=None):
    """fee: per side, on every fill (float), or (entry, exit) per side."""
    c4 = F.resample(m, p.tf_min)
    if p.oi_lookback_h > 0 and oi is None:
        oi = load_oi(p.symbol)
    d1 = F.resample(m, 1440)
    t0, t1 = C.D.minutes(start), C.D.minutes(end)
    n1 = len(m["t"])
    trades = []
    pos, entry_px, entry_i, sl, dist = 0, 0.0, -1, 0.0, 0.0
    be_i = lock_i = -1
    max_bars = int(p.max_hold_h * 60)
    for k in range(LIVE_4H_CANDLES, len(c4["t"])):
        j0 = c4["act"][k]                                  # first 1m bar after candle k closed
        if c4["t"][k] < t0 or j0 >= n1 or m["t"][j0] >= t1:
            continue
        j1 = c4["act"][k + 1] if k + 1 < len(c4["t"]) else n1
        sl_ = slice(k - LIVE_4H_CANDLES + 1, k + 1)
        nd = np.searchsorted(d1["act"], j0, side="right")  # daily candles closed by now
        wd = int(((c4["t"][k] + p.tf_min) // 1440 + 3) % 7)
        ds = slice(max(0, nd - LIVE_1D_CANDLES), nd)
        dec = S.decide(p, c4["h"][sl_], c4["l"][sl_], c4["c"][sl_], d1["c"][ds], wd, d1["h"][ds], d1["l"][ds])

        def close(j, px, why):
            nonlocal pos
            trades.append(dict(entry_time=m["t"][entry_i], exit_time=m["t"][j], dir=pos, entry=entry_px,
                               exit=px, sl_dist=dist, reason=why, be_time=m["t"][be_i] if be_i >= 0 else m["t"][j],
                               lock_time=m["t"][lock_i] if lock_i >= 0 else m["t"][j]))
            pos = 0

        # at the candle close: trail exit, then (if flat) a new order
        if pos == 1 and dec.exit_long:
            close(j0, m["o"][j0], "SIGNAL")
        elif pos == -1 and dec.exit_short:
            close(j0, m["o"][j0], "SIGNAL")
        order = None
        blocked = False
        if p.oi_lookback_h > 0:
            order_ms = (int(c4["t"][k]) + p.tf_min) * 60_000
            i = int(np.searchsorted(oi[0], order_ms))
            lo_i = max(0, i - p.oi_lookback_h - 12)
            chg = S.oi_change(list(zip(oi[0][lo_i:i], oi[1][lo_i:i])), order_ms, p.oi_lookback_h)
            blocked = S.oi_blocks(p, chg)
        if pos == 0 and not blocked:
            if dec.long_trigger is not None:
                order = (1, dec.long_trigger)
            elif dec.short_trigger is not None:
                order = (-1, dec.short_trigger)
        for j in range(j0, j1):
            o, h, l = m["o"][j], m["h"][j], m["l"][j]
            if pos != 0 and j - entry_i >= max_bars:
                close(j, o, "TIME")
            if pos == 0 and order is not None:
                d, trig = order
                if (d == 1 and h >= trig) or (d == -1 and l <= trig):
                    pos, entry_i, dist = d, j, dec.sl_dist
                    be_i = lock_i = -1
                    entry_px = max(trig, o) if d == 1 else min(trig, o)
                    sl = entry_px - d * dist
                    order = None
                    if (d == 1 and l <= sl) or (d == -1 and h >= sl):
                        close(j, sl, "SL")
                    continue
            if pos == 1:
                if j > entry_i and o <= sl:
                    close(j, o, "SL")
                elif l <= sl:
                    close(j, sl, "SL")
                else:
                    if p.be_R > 0 and h - entry_px >= p.be_R * dist and sl < entry_px + p.be_off * dist:
                        sl = entry_px + p.be_off * dist      # breakeven, from the next bar
                        be_i = j if be_i < 0 else be_i
                    if p.lock_R > 0 and h - entry_px >= p.lock_R * dist and sl < entry_px + p.lock_to * dist:
                        sl = entry_px + p.lock_to * dist     # profit lock, from the next bar
                        lock_i = j
            elif pos == -1:
                if j > entry_i and o >= sl:
                    close(j, o, "SL")
                elif h >= sl:
                    close(j, sl, "SL")
                else:
                    if p.be_R > 0 and entry_px - l >= p.be_R * dist and sl > entry_px - p.be_off * dist:
                        sl = entry_px - p.be_off * dist
                        be_i = j if be_i < 0 else be_i
                    if p.lock_R > 0 and entry_px - l >= p.lock_R * dist and sl > entry_px - p.lock_to * dist:
                        sl = entry_px - p.lock_to * dist
                        lock_i = j
    tr = pd.DataFrame(trades)
    for col in ("entry_time", "exit_time", "be_time", "lock_time"):
        tr[col] = C.D.to_datetime(tr[col])
    gross = (tr["exit"] - tr["entry"]) * tr["dir"]
    hours = (tr["exit_time"] - tr["entry_time"]).dt.total_seconds() / 3600
    f_in, f_out = fee if isinstance(fee, tuple) else (fee, fee)
    tr["R"] = (gross - f_in * tr["entry"] - f_out * tr["exit"] - C.FUNDING_8H * hours / 8 * tr["entry"]) / tr["sl_dist"]
    tr["hours"] = hours
    return tr


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    start = sys.argv[2] if len(sys.argv) > 2 else "2020-09-01"
    end = sys.argv[3] if len(sys.argv) > 3 else "2026-10-01"
    p = S.Params(symbol=sym)
    m = C.load(sym)
    live = replay(m, p, start, end)
    eng = C.between(F.channel_breakout(m, tf=p.tf_min, n=p.n, sl_atr=p.sl_atr, hold_h=p.max_hold_h, ema_n=p.ema_n,
                                       atr_n=p.atr_n, sides=p.sides, trail_m=p.trail_m, trail_atr=p.trail_atr,
                                       slope_d=p.slope_d, no_weekend=p.no_weekend, be_R=p.be_R, be_off=p.be_off,
                                       max_ext=p.max_ext),
                    start, end)
    a = live.set_index("entry_time"); b = eng.set_index("entry_time")
    both = a.join(b, how="inner", lsuffix="_live", rsuffix="_eng")
    print(f"live-logic replay: {len(live)} trades, {live['R'].sum():.1f}R | research engine: {len(eng)} trades, {eng['R'].sum():.1f}R")
    print(f"same entry minute: {len(both)}; same exit minute: {(both.exit_time_live == both.exit_time_eng).sum()}; "
          f"max entry price diff: {np.abs(both.entry_live - both.entry_eng).max():.2f}; "
          f"max SL-distance diff: {(np.abs(both.sl_dist_live - both.sl_dist_eng) / both.sl_dist_eng).max() * 100:.3f}%")
    only_live = a.index.difference(b.index); only_eng = b.index.difference(a.index)
    print("only in live replay:", list(only_live[:10])); print("only in engine:", list(only_eng[:10]))
    print(live.groupby(live.entry_time.dt.year)["R"].sum().round(1).to_dict())
