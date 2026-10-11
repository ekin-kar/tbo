"""Minute-level replay of one TBO trade with modified exits (partial take-profit, failed-breakout exit,
re-entry, adding to winners). Base rules: stop 1R, breakeven at +1.5R, time exit after 120 h.
validate() checks the replay against the engine's own trades."""
import pickle
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V21

COINS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]
HOLD = int(V21["hold_h"] * 60)
BE_R = V21["be_R"]
WT = {"BTCUSDT": 2.0, "ETHUSDT": 1.0, "DOGEUSDT": 0.5, "ADAUSDT": 0.5}
_DATA = {}


def slip(sym):
    return 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003


def data(sym):
    if sym not in _DATA:
        _DATA[sym] = C.load(sym)
    return _DATA[sym]


def base_trades(sym, **kw):
    C.SLIP = slip(sym)
    m = data(sym)
    x = C.between(F.channel_breakout(m, **dict(V21, **kw)), "2020-03-01", "2026-10-01").copy().reset_index(drop=True)
    x["sym"] = sym
    x["e"] = np.searchsorted(m["t"], x.entry_time.values.astype("datetime64[m]").astype(np.int64))
    return x


def costs(sym, entry_px, exit_px, hours, taker_exit=True):
    s = C.TAKER + slip(sym)
    return s * entry_px + (s if taker_exit else C.MAKER) * exit_px + C.FUNDING_8H * hours / 8 * entry_px


def first(mask):
    i = np.flatnonzero(mask)
    return i[0] if len(i) else -1


def path(sym, e, side, P, D, be_R=BE_R, be_off=0.0, hold=HOLD, stop0=None, start_be=False):
    """Base exit for a position entered at minute e: returns (exit index, exit price, reason, be index).
    The fill minute can already hit the stop (as in the engine)."""
    m = data(sym)
    n = len(m["t"])
    j1 = min(e + hold, n - 1)
    H, L = m["h"][e:j1], m["l"][e:j1]          # the time exit happens at the open of minute e + hold
    stop = P - side * D if stop0 is None else stop0
    hit = (L <= stop) if side > 0 else (H >= stop)
    if start_be:
        b = 0
    else:
        fav = (H - P) * side if side > 0 else (P - L)
        b = first(fav >= be_R * D)
    s1 = first(hit)
    if b < 0 or (s1 >= 0 and s1 <= b):
        if s1 >= 0:
            return e + s1, stop, "SL", -1
        return j1, m["o"][j1], "TIME", -1
    stop2 = P + side * be_off * D
    hit2 = (L[b + 1:] <= stop2) if side > 0 else (H[b + 1:] >= stop2)
    s2 = first(hit2)
    if s2 >= 0:
        return e + b + 1 + s2, stop2, "BE", e + b
    return j1, m["o"][j1], "TIME", e + b


def R_of(sym, side, P, D, x_idx, x_px, e, taker_exit=True):
    m = data(sym)
    hours = (m["t"][x_idx] - m["t"][e]) / 60
    return ((x_px - P) * side - costs(sym, P, x_px, hours, taker_exit)) / D, hours


def validate(sym):
    x = base_trades(sym)
    ok = 0
    for r in x.itertuples():
        xi, xp, why, _ = path(sym, r.e, r.dir, r.entry, r.sl_dist)
        R, _ = R_of(sym, r.dir, r.entry, r.sl_dist, xi, xp, r.e)
        ok += abs(R - r.R) < 0.02
    return sym, len(x), ok


if __name__ == "__main__":
    from multiprocessing import Pool
    with Pool(4) as p:
        for sym, n, ok in p.map(validate, COINS):
            print(f"{sym}: {ok}/{n} trades replayed within 0.02R")
