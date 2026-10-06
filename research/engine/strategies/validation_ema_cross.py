"""
Validation strategy (NOT meant to be profitable). Mirrors ValidationEmaCross.cs exactly:
  5m candles. EMA(fast) crosses EMA(slow) on the last closed candle -> market order at the next
  bar, SL = sl_atr * ATR(14), TP = tp_atr * ATR(14). No new entries 20:45-22:15 UTC.
  One position at a time; crosses during an open position are ignored.
"""
import numpy as np
from .. import data as D, engine as E, indicators as I


def orders(sym, fast=10, slow=50, atr_n=14, sl_atr=2.0, tp_atr=3.0, tf=5,
           no_entry=(20 * 60 + 45, 22 * 60 + 15)):
    m1 = D.load_m1(sym)
    b = D.resample(m1, tf)
    ef, es = I.ema(b["c"], fast), I.ema(b["c"], slow)
    a = I.atr(b["h"], b["l"], b["c"], atr_n)
    up = (ef > es) & (np.r_[False, ef[:-1] <= es[:-1]])
    dn = (ef < es) & (np.r_[False, ef[:-1] >= es[:-1]])
    k = np.flatnonzero(up | dn)
    od = E.Orders(m1)
    od.place(b["act"][k], E.MARKET, np.where(up[k], 1, -1), sl_atr * a[k], tp_atr * a[k])
    mod = D.minute_of_day(m1["t"])
    od.allow_entry[(mod >= no_entry[0]) & (mod < no_entry[1])] = False
    return od
