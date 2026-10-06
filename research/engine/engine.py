"""
Execution simulator. Runs on 1m BID bars; ask = bid + spread (constant per run).

Strategies hand over ORDERS placed at the OPEN of a 1m bar (normally a candle's 'act'
index), never with knowledge of that bar. Rules, chosen to be honest or pessimistic:

  Market order   fills at the bar open (long at ask, short at bid).
  Stop entry     fills at its price, or at the open if price already gapped past it.
  Limit entry    needs price to trade THROUGH the level by `limit_pad`; fills at the level.
  SL / TP        are set from the actual fill price.
  Long exits     use bid; short exits use ask (bid + spread).
  Gap past SL    exit at the (worse) open price.
  Gap past TP    exit at the TP price (no bonus from the gap).
  SL and TP both touched in one 1m bar  -> counted as SL.
  Bar where a pending order filled      -> only SL can trigger there (worst case).
  Forced exits / exit signals           -> at the bar open.
One position at a time. A new order replaces an unfilled pending one.
"""
import numpy as np
import pandas as pd
from numba import njit

from . import data as D

MARKET, STOP, LIMIT = 1, 2, 3
R_SL, R_TP, R_SIGNAL, R_FORCED, R_TIME, R_END = 1, 2, 3, 4, 5, 6
REASONS = {1: "SL", 2: "TP", 3: "SIGNAL", 4: "FORCED", 5: "TIME", 6: "END"}


@njit(cache=True)
def _simulate(t, o, h, l, c,
              kind2, direction2, price2, sl_d2, tp_d2, expiry2,
              allow_entry, allow_fill, force_exit, exit_long, exit_short,
              day_id, max_trades_day, max_bars, spread_arr, limit_pad, group_size, miss_if_crossed, be_R=0.0, be_off=0.0):
    n = len(t)
    nslot = kind2.shape[1]
    cap = int((kind2 != 0).sum()) + 1
    e_idx = np.empty(cap, np.int64)
    x_idx = np.empty(cap, np.int64)
    dirs = np.empty(cap, np.int64)
    e_px = np.empty(cap)
    x_px = np.empty(cap)
    sl_dist = np.empty(cap)
    reason = np.empty(cap, np.int64)
    k = 0

    pos = 0
    entry_i = -1
    entry_price = 0.0
    sl = 0.0
    tp = 0.0
    dist = 0.0

    p_kind = np.zeros(nslot, np.int64)
    p_dir = np.zeros(nslot, np.int64)
    p_price = np.zeros(nslot)
    p_sl = np.zeros(nslot)
    p_tp = np.zeros(nslot)
    p_exp = np.zeros(nslot, np.int64)

    cur_day = -1
    trades_today = 0

    for j in range(n):
        if day_id[j] != cur_day:
            cur_day = day_id[j]
            trades_today = 0

        spread = spread_arr[j]
        ask_o = o[j] + spread

        # ── 1. at the open: forced / signal / time exits ──
        if pos != 0:
            why = 0
            if force_exit[j]:
                why = R_FORCED
            elif (pos == 1 and exit_long[j]) or (pos == -1 and exit_short[j]):
                why = R_SIGNAL
            elif max_bars > 0 and j - entry_i >= max_bars:
                why = R_TIME
            if why != 0:
                e_idx[k] = entry_i; x_idx[k] = j; dirs[k] = pos
                e_px[k] = entry_price; x_px[k] = o[j] if pos == 1 else ask_o
                sl_dist[k] = dist; reason[k] = why; k += 1
                pos = 0

        for q in range(nslot):
            if p_kind[q] != 0 and (force_exit[j] or not allow_fill[j] or t[j] >= p_exp[q]):
                p_kind[q] = 0

        # ── 2. new orders placed at this open ──
        opened_at_open = False
        for q in range(nslot):
            if kind2[j, q] == 0:
                continue
            if pos != 0 or not allow_entry[j] or force_exit[j]:
                continue
            if max_trades_day > 0 and trades_today >= max_trades_day:
                continue
            if kind2[j, q] == MARKET:
                pos = direction2[j, q]
                entry_price = ask_o if pos == 1 else o[j]
                dist = sl_d2[j, q]
                sl = entry_price - pos * dist
                tp = entry_price + pos * tp_d2[j, q] if tp_d2[j, q] > 0 else (np.inf if pos == 1 else -np.inf)
                entry_i = j
                trades_today += 1
                opened_at_open = True
                for r in range(nslot):
                    p_kind[r] = 0
            else:
                p_kind[q] = kind2[j, q]; p_dir[q] = direction2[j, q]; p_price[q] = price2[j, q]
                p_sl[q] = sl_d2[j, q]; p_tp[q] = tp_d2[j, q]; p_exp[q] = t[j] + expiry2[j, q]

        # ── 2b. optional: orders waiting behind an open position are dropped if their level trades ──
        if miss_if_crossed and pos != 0:
            for q in range(nslot):
                if p_kind[q] == 0:
                    continue
                if p_kind[q] == STOP and ((p_dir[q] == 1 and h[j] + spread >= p_price[q]) or
                                          (p_dir[q] == -1 and l[j] <= p_price[q])):
                    p_kind[q] = 0

        # ── 3. pending order fills inside this bar (first fill cancels the others) ──
        filled_here = False
        for q in range(nslot):
            if p_kind[q] == 0 or pos != 0:
                continue
            filled = False
            fill = 0.0
            if p_kind[q] == STOP:
                if p_dir[q] == 1 and h[j] + spread >= p_price[q]:
                    filled = True; fill = max(p_price[q], ask_o)
                elif p_dir[q] == -1 and l[j] <= p_price[q]:
                    filled = True; fill = min(p_price[q], o[j])
            else:
                if p_dir[q] == 1 and l[j] + spread <= p_price[q] - limit_pad:
                    filled = True; fill = min(p_price[q], ask_o)
                elif p_dir[q] == -1 and h[j] >= p_price[q] + limit_pad:
                    filled = True; fill = max(p_price[q], o[j])
            if not filled:
                continue
            if max_trades_day > 0 and trades_today >= max_trades_day:
                p_kind[q] = 0
                continue
            pos = p_dir[q]; entry_price = fill; dist = p_sl[q]
            sl = fill - pos * dist
            tp = fill + pos * p_tp[q] if p_tp[q] > 0 else (np.inf if pos == 1 else -np.inf)
            entry_i = j; trades_today += 1
            filled_here = True
            if group_size <= 0:
                for r in range(nslot):
                    p_kind[r] = 0
            else:
                g0 = (q // group_size) * group_size
                for r in range(g0, g0 + group_size):
                    p_kind[r] = 0
            # worst case on the fill bar: only the stop can be hit
            if (pos == 1 and l[j] <= sl) or (pos == -1 and h[j] + spread >= sl):
                e_idx[k] = entry_i; x_idx[k] = j; dirs[k] = pos
                e_px[k] = entry_price; x_px[k] = sl
                sl_dist[k] = dist; reason[k] = R_SL; k += 1
                pos = 0
            break

        # ── 4. manage an open position through this bar ──
        if filled_here:
            continue
        if pos == 1:
            px = 0.0; why = 0
            if o[j] <= sl and not opened_at_open:
                px = o[j]; why = R_SL
            elif o[j] >= tp and not opened_at_open:
                px = tp; why = R_TP
            elif l[j] <= sl:
                px = sl; why = R_SL
            elif h[j] >= tp:
                px = tp; why = R_TP
            if why != 0:
                e_idx[k] = entry_i; x_idx[k] = j; dirs[k] = 1
                e_px[k] = entry_price; x_px[k] = px
                sl_dist[k] = dist; reason[k] = why; k += 1
                pos = 0
            elif be_R > 0 and h[j] - entry_price >= be_R * dist and sl < entry_price + be_off * dist:
                sl = entry_price + be_off * dist          # breakeven: effective from the next bar
        elif pos == -1:
            px = 0.0; why = 0
            if ask_o >= sl and not opened_at_open:
                px = ask_o; why = R_SL
            elif ask_o <= tp and not opened_at_open:
                px = tp; why = R_TP
            elif h[j] + spread >= sl:
                px = sl; why = R_SL
            elif l[j] + spread <= tp:
                px = tp; why = R_TP
            if why != 0:
                e_idx[k] = entry_i; x_idx[k] = j; dirs[k] = -1
                e_px[k] = entry_price; x_px[k] = px
                sl_dist[k] = dist; reason[k] = why; k += 1
                pos = 0
            elif be_R > 0 and entry_price - (l[j] + spread) >= be_R * dist and sl > entry_price - be_off * dist:
                sl = entry_price - be_off * dist

    if pos != 0:
        e_idx[k] = entry_i; x_idx[k] = n - 1; dirs[k] = pos
        e_px[k] = entry_price; x_px[k] = c[n - 1] if pos == 1 else c[n - 1] + spread
        sl_dist[k] = dist; reason[k] = R_END; k += 1

    return e_idx[:k], x_idx[:k], dirs[:k], e_px[:k], x_px[:k], sl_dist[:k], reason[:k]


class Orders:
    """Order book in 1m-bar coordinates. Two slots per bar, so a breakout can place both sides."""

    SLOTS = 2

    def __init__(self, m1):
        n = len(m1["t"])
        self.m1 = m1
        z = lambda dt: np.zeros((n, self.SLOTS), dt)
        self.kind = z(np.int64)
        self.direction = z(np.int64)
        self.price = z(float)
        self.sl = z(float)
        self.tp = z(float)
        self.expiry = z(np.int64)
        self.allow_entry = np.ones(n, np.bool_)
        self.allow_fill = np.ones(n, np.bool_)   # resting orders are cancelled where this is False
        self.force_exit = np.zeros(n, np.bool_)
        self.exit_long = np.zeros(n, np.bool_)
        self.exit_short = np.zeros(n, np.bool_)

    def place(self, idx, kind, direction, sl_dist, tp_dist, price=None, expiry_min=0, slot=0):
        """Vectorised: idx = 1m indices (e.g. candle 'act'); other args scalars or arrays."""
        idx = np.asarray(idx)
        ok = idx < len(self.kind)
        idx = idx[ok]

        def pick(v):
            v = np.asarray(v)
            return v[ok] if v.ndim else np.full(len(idx), v)

        self.kind[idx, slot] = kind
        self.direction[idx, slot] = pick(direction)
        self.sl[idx, slot] = pick(sl_dist)
        self.tp[idx, slot] = pick(tp_dist)
        if price is not None:
            self.price[idx, slot] = pick(price)
        self.expiry[idx, slot] = pick(expiry_min)


def run(sym, orders: Orders, spread="typ", max_trades_day=0, max_bars=0, limit_pad=0.0, group_size=0,
        miss_if_crossed=False, be_R=0.0, be_off=0.0):
    m1 = orders.m1
    n = len(m1["t"])
    if isinstance(spread, str) and spread == "real":
        sp = D.load_spread(sym, m1)
        if sp is None:
            raise FileNotFoundError(f"no measured spread file for {sym}")
    elif isinstance(spread, np.ndarray):
        sp = spread
    else:
        val = D.SPECS[sym]["spread"][spread] if isinstance(spread, str) else float(spread)
        sp = np.full(n, val)
    # an order with no valid stop is dropped (guards against NaN indicators during warm-up)
    bad = (orders.kind != 0) & ~(orders.sl > 0)
    orders.kind[bad] = 0
    res = _simulate(m1["t"], m1["o"], m1["h"], m1["l"], m1["c"],
                    orders.kind, orders.direction, orders.price, orders.sl, np.nan_to_num(orders.tp),
                    orders.expiry, orders.allow_entry, orders.allow_fill, orders.force_exit, orders.exit_long, orders.exit_short,
                    D.day_index(m1["t"]), max_trades_day, max_bars, sp, limit_pad, group_size, miss_if_crossed, be_R, be_off)
    e_idx, x_idx, dirs, e_px, x_px, dist, reason = res
    gross = (x_px - e_px) * dirs
    comm = D.COMMISSION_PER_SIDE * (e_px + x_px)
    tr = pd.DataFrame({
        "entry_time": D.to_datetime(m1["t"][e_idx]),
        "exit_time": D.to_datetime(m1["t"][x_idx]),
        "dir": dirs, "entry": e_px, "exit": x_px, "sl_dist": dist,
        "reason": [REASONS[r] for r in reason],
        "R_gross": gross / dist,
        "R": (gross - comm) / dist,
    })
    tr.attrs.update(symbol=sym, spread=float(np.mean(sp)))
    return tr
