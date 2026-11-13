"""v3.3 research simulator: xengine32 + checkpoint rule C (any stage of the trade, also after breakeven):
  39..47  C_T C_G C_CONT C_MLO C_MHI C_THR C_GB C_ACT C_LVL: at the OPEN of a minute j with j - fill >= C_T (minutes) and
          t[j] % C_G == 0 (the 1h / 4h close that just finished): if C_MLO <= MFE < C_MHI (R of the arm risk) and the last
          close is below C_THR R (C_GB = 0) or below MFE x (1 - C_GB) (C_GB > 0: a give-back of that share of the peak):
          C_ACT 1 = limit take-profit at entry + C_LVL R (closed at this open if the price is already beyond it), 2 = closed
          at this open, 3 = stop to entry + C_LVL R (only ever tightened; closed at this open if the price is already past).
          C_CONT 0 = only the first eligible check; 1 = every check until it fires. Fires once per trade; it does not count
          as a "rule" for the post-loss cooldown (RCOOL), the trade's R does.
  All C controls off -> identical to xengine32.sim32.
v3.2 research simulator: xengine31 + regime controls (all off -> identical to xengine31.sim31, checked in v32lib.parity):
  pl2 / ps2, mbl2 / mbs2   a second exit vector and hold limit, used for a trade whose fill minute has emask_l / emask_s True
                           (the regime at entry)
  dyn_l / dyn_s = [DX, DL, DTP] while dmask_l / dmask_s is True at a bar (the regime now): stop to entry + DL x risk once
                           the trade has been DX x risk in favour; take-profit at entry + DTP x risk (0 = off)
  rmaskB                   checkpoint rule B applies only to trades filled where True (rule A keeps rmask)
  exit vector extras: 36 L3 37 L3T (a third lock: at +L3 R the stop to +L3T R), 38 TPR (fixed take-profit at +TPR R, 0 = off)
v3.1 research simulator (Nov 2026): xengine30 (TBO v3.0 rules and fills: stop orders on 1m bars, pessimistic fill-minute
stop, breakeven / locks from the next bar, stale stop, post-loss cooldown, cross-coin masks) plus the v3.1 controls:

  pa (per direction, pl / ps) = exit vector of NP floats:
    0 BE  1 LK  2 LKT  3 L2  4 L2T  5 STB  6 STH  7 STT          as xengine30 (breakeven, lock, 2nd lock, stale stop)
    8 SR_AT  9 SR_TO                                              soft pre-breakeven ratchet: once MFE >= SR_AT (R) the
                                                                  stop moves to entry + SR_TO x risk (SR_TO < 0), from the
                                                                  next bar, while the trade never reached +BE
    10..17 rule A, 18..25 rule B  (T, G, CONT, MLO, MHI, THR, ACT, LVL)   checkpoint rules ("failed breakout" / "dead start"):
        at the OPEN of a minute j with j - fill >= T (minutes) and t[j] % G == 0 (G = 1 / 15 / 60: the 1m / 15m / 1h close
        that just finished), while the trade never reached +BE: if MLO <= MFE < MHI and the last close c[j-1] is below THR
        (R, in the trade's own direction): ACT 1 = take-profit (reduce-only limit) at entry + LVL x risk (if the price is
        already beyond it: closed at this open), ACT 2 = closed at this open, ACT 3 = stop moved to entry + LVL x risk.
        CONT 0 = only the first eligible check is evaluated; 1 = every check from T on until the rule fires.
    26 RA_MODE 27 RA_LO 28 RA_HI 29 RA_ALPHA 30 RA_ANCHOR 31 RA_DEN 32 RA_K 33 RA_MAX 34 RA_MIN   fill-time re-anchor:
        ratio = fa[fill] / den, den = fa[arm] (RA_DEN 0) or arm risk / RA_K (RA_DEN 1, e.g. ATR_1h vs ATR_4h / 2);
        mode 1: ratio < RA_LO -> risk x (alpha + (1 - alpha) ratio) (>= RA_MIN); mode 2: ratio > RA_HI -> the same (<= RA_MAX);
        mode 3 both. Position sized on the new risk (R = P&L / new risk). RA_ANCHOR 1: breakeven / locks / stale / rule
        thresholds stay at multiples of the ARM risk (0: of the new risk).
    35 RCOOL   1 = a trade closed after a checkpoint rule fired starts the cooldown whatever its R.
  optr           per minute: row of the compact order arrays (kind2 ... expiry2, one row per minute with orders) or -1
  rmask          per minute: checkpoint rules A / B apply only to trades whose fill minute is True (regime-conditional rules)
  fa             per-minute fast ATR (value of the last CLOSED fast candle), only read when RA_MODE > 0.

Outputs per trade: entry / exit index, dir, entry / exit price, risk (price distance the trade is sized on), reason,
rf (first minute the stop is at / beyond the entry: the trade stops counting under the open-risk cap; else the exit),
hf (first minute the open risk is <= half the initial one; else the exit), MFE in R, level risk (be / lock unit),
rule (0 none, 1 A, 2 B fired), arm index (minute the filled order was placed).
With all v3.1 controls off the output equals xengine30.sim30 (checked in v31lib.parity)."""
import numpy as np
from numba import njit
from engine.engine import R_SL, R_TP, R_SIGNAL, R_FORCED, R_TIME, R_END, MARKET, STOP

BE, LK, LKT, L2, L2T, STB, STH, STT = range(8)
SR_AT, SR_TO = 8, 9
RA_, RB_ = 10, 18
T_, G_, CONT_, MLO_, MHI_, THR_, ACT_, LVL_ = range(8)
RA_MODE, RA_LO, RA_HI, RA_ALPHA, RA_ANCHOR, RA_DEN, RA_K, RA_MAX, RA_MIN = range(26, 35)
RCOOL = 35
L3, L3T, TPR = 36, 37, 38
C_T, C_G, C_CONT, C_MLO, C_MHI, C_THR, C_GB, C_ACT, C_LVL = range(39, 48)
NP = 48


@njit(cache=True)
def sim33(t, o, h, l, c, optr, kind2, direction2, price2, sl_d2, tp_d2, expiry2, allow_entry, allow_fill, force_exit,
          exit_long, exit_short, spread_arr, mbl, mbs, pl, ps, fill_l, fill_s, tight_l, tight_s, tight_to,
          cool_bars, cool_R, cool_mode, cool_clear, fa, rmask,
          pl2, ps2, mbl2, mbs2, emask_l, emask_s, dmask_l, dmask_s, dyn_l, dyn_s, rmaskB):
    n = len(t)
    nslot = kind2.shape[1]
    cap = int((kind2 != 0).sum()) + 1
    e_idx = np.empty(cap, np.int64); x_idx = np.empty(cap, np.int64); dirs = np.empty(cap, np.int64)
    e_px = np.empty(cap); x_px = np.empty(cap); sl_dist = np.empty(cap); reason = np.empty(cap, np.int64)
    rf_o = np.empty(cap, np.int64); hf_o = np.empty(cap, np.int64); mfe_o = np.empty(cap); ld_o = np.empty(cap)
    rule_o = np.empty(cap, np.int64); arm_o = np.empty(cap, np.int64)
    k = 0
    pos = 0; best_fav = 0.0; entry_i = -1; entry_price = 0.0; sl = 0.0; tp = 0.0; dist = 0.0; ldist = 0.0; be_hit = False
    rf = -1; hf = -1; rule_fired = 0; chkA = False; chkB = False; arm_i = -1; chkC = False; cfired = False
    pa = pl.copy()
    mb = mbl
    cool_until = -1; cool_dir = 0; cool_lvl = 0.0
    p_kind = np.zeros(nslot, np.int64); p_dir = np.zeros(nslot, np.int64); p_price = np.zeros(nslot)
    p_sl = np.zeros(nslot); p_tp = np.zeros(nslot); p_exp = np.zeros(nslot, np.int64); p_arm = np.zeros(nslot, np.int64)

    for j in range(n):
        spread = spread_arr[j]
        ask_o = o[j] + spread
        closed = False
        # ── 1. at the open: forced / signal / time exits, stale stop, cross-coin tightening, checkpoint rules ──
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
                if cur > pa[STH] * ldist:
                    if pos == 1 and sl < entry_price + pa[STT] * ldist:
                        sl = entry_price + pa[STT] * ldist
                    elif pos == -1 and sl > entry_price - pa[STT] * ldist:
                        sl = entry_price - pa[STT] * ldist
            if why == 0:
                if pos == 1 and tight_l[j] and sl < entry_price + tight_to * dist:
                    sl = entry_price + tight_to * dist
                elif pos == -1 and tight_s[j] and sl > entry_price - tight_to * dist:
                    sl = entry_price - tight_to * dist
            # checkpoint rules A / B
            if why == 0 and not be_hit and j > entry_i:
                for rr in range(2):
                    base = RA_ if rr == 0 else RB_
                    if pa[base + T_] <= 0:
                        continue
                    if rule_fired != 0:
                        break
                    if (rr == 0 and not rmask[entry_i]) or (rr == 1 and not rmaskB[entry_i]):
                        continue
                    if rr == 0 and chkA and pa[base + CONT_] == 0:
                        continue
                    if rr == 1 and chkB and pa[base + CONT_] == 0:
                        continue
                    if j - entry_i < pa[base + T_]:
                        continue
                    g = int(pa[base + G_])
                    if g > 1 and t[j] % g != 0:
                        continue
                    if rr == 0:
                        chkA = True
                    else:
                        chkB = True
                    mfe = best_fav / ldist
                    cur = ((c[j - 1] - entry_price) if pos == 1 else (entry_price - (c[j - 1] + spread))) / ldist
                    if mfe >= pa[base + MLO_] and mfe < pa[base + MHI_] and cur < pa[base + THR_]:
                        act = int(pa[base + ACT_]); lv = pa[base + LVL_]
                        rule_fired = rr + 1
                        if act == 2:
                            why = R_SIGNAL
                        elif act == 1:
                            lvl_px = entry_price + pos * lv * dist
                            if (pos == 1 and o[j] >= lvl_px) or (pos == -1 and ask_o <= lvl_px):
                                why = R_SIGNAL                       # already beyond the level: the limit fills at once
                            elif pos == 1 and lvl_px < tp:
                                tp = lvl_px
                            elif pos == -1 and lvl_px > tp:
                                tp = lvl_px
                        elif act == 3:
                            lvl_px = entry_price + pos * lv * dist
                            if pos == 1 and sl < lvl_px:
                                sl = lvl_px
                            elif pos == -1 and sl > lvl_px:
                                sl = lvl_px
            # v3.3 checkpoint rule C (any stage of the trade)
            if why == 0 and pa[C_T] > 0 and not cfired and j > entry_i and not (chkC and pa[C_CONT] == 0) and j - entry_i >= pa[C_T]:
                gc_ = int(pa[C_G])
                if gc_ <= 1 or t[j] % gc_ == 0:
                    chkC = True
                    mfe = best_fav / ldist
                    cur = ((c[j - 1] - entry_price) if pos == 1 else (entry_price - (c[j - 1] + spread))) / ldist
                    if pa[C_GB] > 0:
                        trig_c = cur < mfe * (1.0 - pa[C_GB])
                    else:
                        trig_c = cur < pa[C_THR]
                    if mfe >= pa[C_MLO] and mfe < pa[C_MHI] and trig_c:
                        cfired = True
                        act = int(pa[C_ACT]); lv = pa[C_LVL]
                        lvl_px = entry_price + pos * lv * ldist
                        if act == 2:
                            why = R_SIGNAL
                        elif act == 1:
                            if (pos == 1 and o[j] >= lvl_px) or (pos == -1 and ask_o <= lvl_px):
                                why = R_SIGNAL
                            elif pos == 1 and lvl_px < tp:
                                tp = lvl_px
                            elif pos == -1 and lvl_px > tp:
                                tp = lvl_px
                        elif act == 3:
                            if pos == 1 and sl < lvl_px:
                                sl = lvl_px
                            elif pos == -1 and sl > lvl_px:
                                sl = lvl_px
            if why != 0:
                e_idx[k] = entry_i; x_idx[k] = j; dirs[k] = pos
                e_px[k] = entry_price; x_px[k] = o[j] if pos == 1 else ask_o
                sl_dist[k] = dist; reason[k] = why
                rf_o[k] = rf if rf >= 0 else j; hf_o[k] = hf if hf >= 0 else j; mfe_o[k] = best_fav / dist; ld_o[k] = ldist
                rule_o[k] = rule_fired; arm_o[k] = arm_i; k += 1
                closed = True

        if closed:
            if cool_bars > 0 and ((x_px[k - 1] - e_px[k - 1]) * pos / dist < cool_R or (rule_fired != 0 and pa[RCOOL] > 0)):
                cool_until = j + cool_bars; cool_dir = pos
                cool_lvl = entry_price + pos * (best_fav + cool_clear * dist)
            pos = 0
            closed = False

        for q in range(nslot):
            if p_kind[q] != 0 and (force_exit[j] or not allow_fill[j] or t[j] >= p_exp[q]):
                p_kind[q] = 0

        # ── 2. new orders placed at this open ──
        opened_at_open = False
        jr = optr[j]
        for q in range(nslot):
            if jr < 0 or kind2[jr, q] == 0:
                continue
            if pos != 0 or not allow_entry[j] or force_exit[j]:
                continue
            if kind2[jr, q] == MARKET:
                d0 = direction2[jr, q]
                if (d0 == 1 and not fill_l[j]) or (d0 == -1 and not fill_s[j]):
                    continue
                if j < cool_until and (cool_mode == 1 or (cool_mode >= 2 and d0 == cool_dir)):
                    continue
                pos = d0
                entry_price = ask_o if pos == 1 else o[j]
                dist = sl_d2[jr, q]; ldist = dist
                sl = entry_price - pos * dist
                tp = entry_price + pos * tp_d2[jr, q] if tp_d2[jr, q] > 0 else (np.inf if pos == 1 else -np.inf)
                entry_i = j; best_fav = 0.0; be_hit = False
                rf = -1; hf = -1; rule_fired = 0; chkA = False; chkB = False; chkC = False; cfired = False; arm_i = j
                if pos == 1:
                    pa = pl2.copy() if emask_l[j] else pl.copy(); mb = mbl2 if emask_l[j] else mbl
                else:
                    pa = ps2.copy() if emask_s[j] else ps.copy(); mb = mbs2 if emask_s[j] else mbs
                if pa[TPR] > 0:
                    tp = entry_price + pos * pa[TPR] * dist
                opened_at_open = True
                for r in range(nslot):
                    p_kind[r] = 0
            else:
                p_kind[q] = kind2[jr, q]; p_dir[q] = direction2[jr, q]; p_price[q] = price2[jr, q]
                p_sl[q] = sl_d2[jr, q]; p_tp[q] = tp_d2[jr, q]; p_exp[q] = t[j] + expiry2[jr, q]; p_arm[q] = j

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
            pos = dq; entry_price = fill
            if pos == 1:
                pa = pl2.copy() if emask_l[j] else pl.copy()
            else:
                pa = ps2.copy() if emask_s[j] else ps.copy()
            dist = p_sl[q]; ldist = dist
            arm_i = p_arm[q]
            mode = int(pa[RA_MODE])
            if mode > 0:
                den = fa[arm_i] if pa[RA_DEN] == 0 else dist / pa[RA_K]
                if den > 0 and fa[j] > 0:
                    ratio = fa[j] / den
                    f = 1.0
                    if (mode == 1 or mode == 3) and ratio < pa[RA_LO]:
                        f = pa[RA_ALPHA] + (1.0 - pa[RA_ALPHA]) * ratio
                        if f < pa[RA_MIN]:
                            f = pa[RA_MIN]
                    elif (mode == 2 or mode == 3) and ratio > pa[RA_HI]:
                        f = pa[RA_ALPHA] + (1.0 - pa[RA_ALPHA]) * ratio
                        if f > pa[RA_MAX]:
                            f = pa[RA_MAX]
                    dist = dist * f
                    ldist = p_sl[q] if pa[RA_ANCHOR] == 1 else dist
            sl = fill - pos * dist
            tp = fill + pos * p_tp[q] if p_tp[q] > 0 else (np.inf if pos == 1 else -np.inf)
            entry_i = j; best_fav = 0.0; be_hit = False
            rf = -1; hf = -1; rule_fired = 0; chkA = False; chkB = False; chkC = False; cfired = False
            if pos == 1:
                mb = mbl2 if emask_l[j] else mbl
            else:
                mb = mbs2 if emask_s[j] else mbs
            if pa[TPR] > 0:
                tp = fill + pos * pa[TPR] * dist
            filled_here = True
            for r in range(nslot):
                p_kind[r] = 0
            if (pos == 1 and l[j] <= sl) or (pos == -1 and h[j] + spread >= sl):
                e_idx[k] = entry_i; x_idx[k] = j; dirs[k] = pos
                e_px[k] = entry_price; x_px[k] = sl
                sl_dist[k] = dist; reason[k] = R_SL
                rf_o[k] = j; hf_o[k] = j; mfe_o[k] = 0.0; ld_o[k] = ldist; rule_o[k] = 0; arm_o[k] = arm_i; k += 1
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
                sl_dist[k] = dist; reason[k] = why
                rf_o[k] = rf if rf >= 0 else j; hf_o[k] = hf if hf >= 0 else j; mfe_o[k] = best_fav / dist; ld_o[k] = ldist
                rule_o[k] = rule_fired; arm_o[k] = arm_i; k += 1
                if cool_bars > 0 and ((px - entry_price) / dist < cool_R or (rule_fired != 0 and pa[RCOOL] > 0)):
                    cool_until = j + cool_bars; cool_dir = 1
                    cool_lvl = entry_price + (best_fav + cool_clear * dist)
                pos = 0
            else:
                fav = h[j] - entry_price
                if pa[BE] > 0 and fav >= pa[BE] * ldist and sl < entry_price:
                    sl = entry_price
                if pa[LK] > 0 and fav >= pa[LK] * ldist and sl < entry_price + pa[LKT] * ldist:
                    sl = entry_price + pa[LKT] * ldist
                if pa[BE] > 0 and fav >= pa[BE] * ldist:
                    be_hit = True
                if pa[L2] > 0 and fav >= pa[L2] * ldist and sl < entry_price + pa[L2T] * ldist:
                    sl = entry_price + pa[L2T] * ldist
                if pa[SR_AT] > 0 and not be_hit and fav >= pa[SR_AT] * ldist and sl < entry_price + pa[SR_TO] * dist:
                    sl = entry_price + pa[SR_TO] * dist
                if pa[L3] > 0 and fav >= pa[L3] * ldist and sl < entry_price + pa[L3T] * ldist:
                    sl = entry_price + pa[L3T] * ldist
                if dmask_l[j]:
                    if dyn_l[0] > 0 and fav >= dyn_l[0] * ldist and sl < entry_price + dyn_l[1] * ldist:
                        sl = entry_price + dyn_l[1] * ldist
                    if dyn_l[2] > 0 and entry_price + dyn_l[2] * dist < tp:
                        tp = entry_price + dyn_l[2] * dist
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
                sl_dist[k] = dist; reason[k] = why
                rf_o[k] = rf if rf >= 0 else j; hf_o[k] = hf if hf >= 0 else j; mfe_o[k] = best_fav / dist; ld_o[k] = ldist
                rule_o[k] = rule_fired; arm_o[k] = arm_i; k += 1
                if cool_bars > 0 and ((entry_price - px) / dist < cool_R or (rule_fired != 0 and pa[RCOOL] > 0)):
                    cool_until = j + cool_bars; cool_dir = -1
                    cool_lvl = entry_price - (best_fav + cool_clear * dist)
                pos = 0
            else:
                fav = entry_price - (l[j] + spread)
                if pa[BE] > 0 and fav >= pa[BE] * ldist and sl > entry_price:
                    sl = entry_price
                if pa[LK] > 0 and fav >= pa[LK] * ldist and sl > entry_price - pa[LKT] * ldist:
                    sl = entry_price - pa[LKT] * ldist
                if pa[BE] > 0 and fav >= pa[BE] * ldist:
                    be_hit = True
                if pa[L2] > 0 and fav >= pa[L2] * ldist and sl > entry_price - pa[L2T] * ldist:
                    sl = entry_price - pa[L2T] * ldist
                if pa[SR_AT] > 0 and not be_hit and fav >= pa[SR_AT] * ldist and sl > entry_price - pa[SR_TO] * dist:
                    sl = entry_price - pa[SR_TO] * dist
                if pa[L3] > 0 and fav >= pa[L3] * ldist and sl > entry_price - pa[L3T] * ldist:
                    sl = entry_price - pa[L3T] * ldist
                if dmask_s[j]:
                    if dyn_s[0] > 0 and fav >= dyn_s[0] * ldist and sl > entry_price - dyn_s[1] * ldist:
                        sl = entry_price - dyn_s[1] * ldist
                    if dyn_s[2] > 0 and entry_price - dyn_s[2] * dist > tp:
                        tp = entry_price - dyn_s[2] * dist
        if pos != 0:                                                   # open-risk bookkeeping (cap) at the end of the bar
            frac = (entry_price - sl) * pos / dist
            if rf < 0 and frac <= 1e-12:
                rf = j
            if hf < 0 and frac <= 0.5 + 1e-9:
                hf = j

    if pos != 0:
        e_idx[k] = entry_i; x_idx[k] = n - 1; dirs[k] = pos
        e_px[k] = entry_price; x_px[k] = c[n - 1] if pos == 1 else c[n - 1] + spread
        sl_dist[k] = dist; reason[k] = R_END
        rf_o[k] = rf if rf >= 0 else n - 1; hf_o[k] = hf if hf >= 0 else n - 1; mfe_o[k] = best_fav / dist; ld_o[k] = ldist
        rule_o[k] = rule_fired; arm_o[k] = arm_i; k += 1
    return (e_idx[:k], x_idx[:k], dirs[:k], e_px[:k], x_px[:k], sl_dist[:k], reason[:k], rf_o[:k], hf_o[:k], mfe_o[:k],
            ld_o[:k], rule_o[:k], arm_o[:k])


@njit(cache=True)
def path_stats(t, h, l, c, ei, xi, d, e, dist, marks):
    """Per trade, from the 1m path after the fill bar: MFE / MAE (R) and, for each R mark in `marks`, the first minute
    (offset from the fill) the favourable excursion reached it (-1 = never); plus MAE after first reaching each mark."""
    n = len(ei); nm = len(marks)
    mfe = np.zeros(n); mae = np.zeros(n); first = np.full((n, nm), -1, np.int64); mae_after = np.zeros((n, nm))
    for k in range(n):
        bf = 0.0; ba = 0.0
        for j in range(ei[k] + 1, xi[k] + 1):
            fv = (h[j] - e[k]) / dist[k] if d[k] > 0 else (e[k] - l[j]) / dist[k]
            av = (l[j] - e[k]) / dist[k] if d[k] > 0 else (e[k] - h[j]) / dist[k]
            for q in range(nm):
                if first[k, q] >= 0 and av < mae_after[k, q]:
                    mae_after[k, q] = av
            if fv > bf:
                bf = fv
                for q in range(nm):
                    if first[k, q] < 0 and bf >= marks[q]:
                        first[k, q] = j - ei[k]
            if av < ba:
                ba = av
        mfe[k] = bf; mae[k] = ba
    return mfe, mae, first, mae_after
