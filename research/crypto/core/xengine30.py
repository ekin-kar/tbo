"""v3.0 research simulator: xengine29's rules and fills (stop orders, 1m bars, pessimistic fill bar, breakeven / lock from the
next bar) restricted to what TBO uses, plus per-direction and cross-coin controls:
  pl / ps        exit parameters for longs / shorts: [be_R, lock_R, lock_to, lock2_R, lock2_to, stale_bars, stale_thr, stale_to]
  mbl / mbs      hold limit (bars) for longs / shorts
  fill_l/fill_s  per-minute masks: a pending long / short order may fill only where True (cross-coin vetoes)
  tight_l/_s     at the open of a minute where True, an open long / short has its stop raised to entry + tight_to x risk
                 (exit_long / exit_short close it at that open instead)
  cool_*         after a trade closes below cool_R (price R), for cool_bars minutes: mode 1 no entries, mode 2 no entries in
                 the same direction, mode 3 same-direction stop orders trigger only beyond the failed trade's best price
                 + cool_clear x its risk
With all controls off and pl = ps = the live exits the output equals xengine29 / xengine (checked in v30lib.parity)."""
import numpy as np
from numba import njit
from engine.engine import R_SL, R_TP, R_SIGNAL, R_FORCED, R_TIME, R_END, MARKET, STOP

BE, LK, LKT, L2, L2T, STB, STH, STT = range(8)


@njit(cache=True)
def sim30(t, o, h, l, c, kind2, direction2, price2, sl_d2, tp_d2, expiry2, allow_entry, allow_fill, force_exit,
          exit_long, exit_short, spread_arr, mbl, mbs, pl, ps, fill_l, fill_s, tight_l, tight_s, tight_to,
          cool_bars, cool_R, cool_mode, cool_clear):
    n = len(t)
    nslot = kind2.shape[1]
    cap = int((kind2 != 0).sum()) + 1
    e_idx = np.empty(cap, np.int64); x_idx = np.empty(cap, np.int64); dirs = np.empty(cap, np.int64)
    e_px = np.empty(cap); x_px = np.empty(cap); sl_dist = np.empty(cap); reason = np.empty(cap, np.int64)
    k = 0
    pos = 0; best_fav = 0.0; entry_i = -1; entry_price = 0.0; sl = 0.0; tp = 0.0; dist = 0.0; be_hit = False
    pa = pl.copy()
    mb = mbl
    cool_until = -1; cool_dir = 0; cool_lvl = 0.0
    p_kind = np.zeros(nslot, np.int64); p_dir = np.zeros(nslot, np.int64); p_price = np.zeros(nslot)
    p_sl = np.zeros(nslot); p_tp = np.zeros(nslot); p_exp = np.zeros(nslot, np.int64)

    for j in range(n):
        spread = spread_arr[j]
        ask_o = o[j] + spread
        closed = False
        # ── 1. at the open: forced / signal / time exits, stale stop, cross-coin tightening ──
        if pos != 0:
            why = 0
            if force_exit[j]:
                why = R_FORCED
            elif (pos == 1 and exit_long[j]) or (pos == -1 and exit_short[j]):
                why = R_SIGNAL
            elif mb > 0 and j - entry_i >= mb:
                why = R_TIME
            stb = int(pa[STB])
            if why == 0 and stb > 0 and j - entry_i == stb and not be_hit:
                cur = (o[j] - entry_price) if pos == 1 else (entry_price - ask_o)
                if cur > pa[STH] * dist:
                    if pos == 1 and sl < entry_price + pa[STT] * dist:
                        sl = entry_price + pa[STT] * dist
                    elif pos == -1 and sl > entry_price - pa[STT] * dist:
                        sl = entry_price - pa[STT] * dist
            if why == 0:
                if pos == 1 and tight_l[j] and sl < entry_price + tight_to * dist:
                    sl = entry_price + tight_to * dist
                elif pos == -1 and tight_s[j] and sl > entry_price - tight_to * dist:
                    sl = entry_price - tight_to * dist
            if why != 0:
                e_idx[k] = entry_i; x_idx[k] = j; dirs[k] = pos
                e_px[k] = entry_price; x_px[k] = o[j] if pos == 1 else ask_o
                sl_dist[k] = dist; reason[k] = why; k += 1
                closed = True

        if closed:
            if cool_bars > 0 and (x_px[k - 1] - e_px[k - 1]) * pos / dist < cool_R:
                cool_until = j + cool_bars; cool_dir = pos
                cool_lvl = entry_price + pos * (best_fav + cool_clear * dist)
            pos = 0
            closed = False

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
            if kind2[j, q] == MARKET:
                d0 = direction2[j, q]
                if (d0 == 1 and not fill_l[j]) or (d0 == -1 and not fill_s[j]):
                    continue
                if j < cool_until and (cool_mode == 1 or (cool_mode >= 2 and d0 == cool_dir)):
                    continue
                pos = d0
                entry_price = ask_o if pos == 1 else o[j]
                dist = sl_d2[j, q]
                sl = entry_price - pos * dist
                tp = entry_price + pos * tp_d2[j, q] if tp_d2[j, q] > 0 else (np.inf if pos == 1 else -np.inf)
                entry_i = j; best_fav = 0.0; be_hit = False
                pa = pl.copy() if pos == 1 else ps.copy()
                mb = mbl if pos == 1 else mbs
                opened_at_open = True
                for r in range(nslot):
                    p_kind[r] = 0
            else:
                p_kind[q] = kind2[j, q]; p_dir[q] = direction2[j, q]; p_price[q] = price2[j, q]
                p_sl[q] = sl_d2[j, q]; p_tp[q] = tp_d2[j, q]; p_exp[q] = t[j] + expiry2[j, q]

        # ── 3. pending order fills inside this bar (first fill cancels the others) ──
        filled_here = False
        for q in range(nslot):
            if p_kind[q] == 0 or pos != 0:
                continue
            dq = p_dir[q]
            if (dq == 1 and not fill_l[j]) or (dq == -1 and not fill_s[j]):
                continue
            px_trig = p_price[q]
            if j < cool_until and (cool_mode == 1 or (cool_mode == 2 and dq == cool_dir)):
                continue
            if j < cool_until and cool_mode == 3 and dq == cool_dir:
                if dq == 1 and cool_lvl > px_trig:
                    px_trig = cool_lvl
                elif dq == -1 and cool_lvl < px_trig:
                    px_trig = cool_lvl
            filled = False
            fill = 0.0
            if p_kind[q] == STOP:
                if dq == 1 and h[j] + spread >= px_trig:
                    filled = True; fill = max(px_trig, ask_o)
                elif dq == -1 and l[j] <= px_trig:
                    filled = True; fill = min(px_trig, o[j])
            if not filled:
                continue
            pos = dq; entry_price = fill; dist = p_sl[q]
            sl = fill - pos * dist
            tp = fill + pos * p_tp[q] if p_tp[q] > 0 else (np.inf if pos == 1 else -np.inf)
            entry_i = j; best_fav = 0.0; be_hit = False
            pa = pl.copy() if pos == 1 else ps.copy()
            mb = mbl if pos == 1 else mbs
            filled_here = True
            for r in range(nslot):
                p_kind[r] = 0
            if (pos == 1 and l[j] <= sl) or (pos == -1 and h[j] + spread >= sl):
                e_idx[k] = entry_i; x_idx[k] = j; dirs[k] = pos
                e_px[k] = entry_price; x_px[k] = sl
                sl_dist[k] = dist; reason[k] = R_SL; k += 1
                if cool_bars > 0 and (x_px[k - 1] - e_px[k - 1]) * pos / dist < cool_R:
                    cool_until = j + cool_bars; cool_dir = pos
                    cool_lvl = entry_price + pos * (best_fav + cool_clear * dist)
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
                if cool_bars > 0 and (px - entry_price) / dist < cool_R:
                    cool_until = j + cool_bars; cool_dir = 1
                    cool_lvl = entry_price + (best_fav + cool_clear * dist)
                pos = 0
            else:
                fav = h[j] - entry_price
                if pa[BE] > 0 and fav >= pa[BE] * dist and sl < entry_price:
                    sl = entry_price
                if pa[LK] > 0 and fav >= pa[LK] * dist and sl < entry_price + pa[LKT] * dist:
                    sl = entry_price + pa[LKT] * dist
                if pa[BE] > 0 and fav >= pa[BE] * dist:
                    be_hit = True
                if pa[L2] > 0 and fav >= pa[L2] * dist and sl < entry_price + pa[L2T] * dist:
                    sl = entry_price + pa[L2T] * dist
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
                if cool_bars > 0 and (entry_price - px) / dist < cool_R:
                    cool_until = j + cool_bars; cool_dir = -1
                    cool_lvl = entry_price - (best_fav + cool_clear * dist)
                pos = 0
            else:
                fav = entry_price - (l[j] + spread)
                if pa[BE] > 0 and fav >= pa[BE] * dist and sl > entry_price:
                    sl = entry_price
                if pa[LK] > 0 and fav >= pa[LK] * dist and sl > entry_price - pa[LKT] * dist:
                    sl = entry_price - pa[LKT] * dist
                if pa[BE] > 0 and fav >= pa[BE] * dist:
                    be_hit = True
                if pa[L2] > 0 and fav >= pa[L2] * dist and sl > entry_price - pa[L2T] * dist:
                    sl = entry_price - pa[L2T] * dist

    if pos != 0:
        e_idx[k] = entry_i; x_idx[k] = n - 1; dirs[k] = pos
        e_px[k] = entry_price; x_px[k] = c[n - 1] if pos == 1 else c[n - 1] + spread
        sl_dist[k] = dist; reason[k] = R_END; k += 1
    return e_idx[:k], x_idx[:k], dirs[:k], e_px[:k], x_px[:k], sl_dist[:k], reason[:k]
