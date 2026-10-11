"""
Copy of engine._simulate where the limit-order pad is an ARRAY (a fraction of price per bar), so a
limit order must trade THROUGH its level by e.g. 0.01% of price at any price level. Rules otherwise as
research/engine/engine.py.
"""
import numpy as np
from numba import njit
from engine.engine import R_SL, R_TP, R_SIGNAL, R_FORCED, R_TIME, R_END, MARKET, STOP, LIMIT


@njit(cache=True)
def _simulate(t, o, h, l, c,
              kind2, direction2, price2, sl_d2, tp_d2, expiry2,
              allow_entry, allow_fill, force_exit, exit_long, exit_short,
              day_id, max_trades_day, max_bars, spread_arr, limit_pad_arr, group_size, miss_if_crossed, be_R=0.0, be_off=0.0,
              trail_k=0.0, trail_start=0.0, early_bars=0, early_R=0.0, ext_bars=0, ext_R=0.0, trail_after=0,
              lock_R=0.0, lock_to=0.0):
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
    best_fav = 0.0
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
            elif early_bars > 0 and j - entry_i == early_bars and best_fav < early_R * dist:
                why = R_TIME                               # 'dead trade': never reached early_R by early_bars
            elif max_bars > 0 and j - entry_i >= max_bars:
                cur = (o[j] - entry_price) if pos == 1 else (entry_price - ask_o)
                if not (ext_bars > max_bars and j - entry_i < ext_bars and cur >= ext_R * dist):
                    why = R_TIME                           # extension: winners above ext_R held up to ext_bars
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
                best_fav = 0.0
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
                if p_dir[q] == 1 and l[j] + spread <= p_price[q] - limit_pad_arr[j]:
                    filled = True; fill = min(p_price[q], ask_o)
                elif p_dir[q] == -1 and h[j] >= p_price[q] + limit_pad_arr[j]:
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
            best_fav = 0.0
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
        if pos == 1 and h[j] - entry_price > best_fav:
            best_fav = h[j] - entry_price
        elif pos == -1 and entry_price - (l[j] + spread) > best_fav:
            best_fav = entry_price - (l[j] + spread)
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
            else:
                if be_R > 0 and h[j] - entry_price >= be_R * dist and sl < entry_price + be_off * dist:
                    sl = entry_price + be_off * dist      # breakeven: effective from the next bar
                if lock_R > 0 and h[j] - entry_price >= lock_R * dist and sl < entry_price + lock_to * dist:
                    sl = entry_price + lock_to * dist     # profit lock (one step), from the next bar
                if trail_k > 0 and h[j] - entry_price >= trail_start * dist and j - entry_i >= trail_after:
                    nsl = h[j] - trail_k * dist           # trailing stop: best price - trail_k x initial risk
                    if nsl > sl:
                        sl = nsl
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
            else:
                if be_R > 0 and entry_price - (l[j] + spread) >= be_R * dist and sl > entry_price - be_off * dist:
                    sl = entry_price - be_off * dist
                if lock_R > 0 and entry_price - (l[j] + spread) >= lock_R * dist and sl > entry_price - lock_to * dist:
                    sl = entry_price - lock_to * dist
                if trail_k > 0 and entry_price - (l[j] + spread) >= trail_start * dist and j - entry_i >= trail_after:
                    nsl = l[j] + spread + trail_k * dist
                    if nsl < sl:
                        sl = nsl

    if pos != 0:
        e_idx[k] = entry_i; x_idx[k] = n - 1; dirs[k] = pos
        e_px[k] = entry_price; x_px[k] = c[n - 1] if pos == 1 else c[n - 1] + spread
        sl_dist[k] = dist; reason[k] = R_END; k += 1

    return e_idx[:k], x_idx[:k], dirs[:k], e_px[:k], x_px[:k], sl_dist[:k], reason[:k]


