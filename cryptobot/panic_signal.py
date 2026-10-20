"""
Panic-rebound signal (the "panic sleeve"), shared by the live sleeve (panic.py) and the research
(research/crypto/core/panic_sleeve.py), so both compute exactly the same numbers. numpy only.

The idea: when a coin falls hard while open interest collapses, leveraged longs are being force-liquidated. Forced
selling overshoots, and the price tends to rebound. With hourly bars (index t = the hour that just closed):
  * move    rz  = log(close_t / close_t-L) / (sigma_t * sqrt(L)),  sigma_t = std of the last 168 hourly log returns
  * OI drop doi = OI_t / OI_t-L - 1                (open interest value, sampled at the end of each hour)
  * premium pz  = z-score of the futures premium index (close) over the last 720 hours (min 300)
  signal when rz <= -move_k and doi <= -oi_drop and pz <= premium_z
Exits (see panic.py): take-profit +tp_atr x ATR, stop -stop_atr x ATR but never more than stop_max below the entry
(a crash with huge ATR would otherwise put it -50% away), moved to the entry once +be_atr x ATR is reached, otherwise
closed after hold_h hours. ATR = 14-hour exponential average of the true range.
"""
import numpy as np

DEFAULTS = dict(window_h=4, move_k=1.5, oi_drop=0.12, premium_z=-1.0, hold_h=12, tp_atr=3.0, stop_atr=4.0, stop_max=0.20, be_atr=2.0)


def _rolling_mean_std(x, n, min_n):
    """Rolling mean and sample std (ddof 1) over the last n values, ignoring NaN; NaN where fewer than min_n values."""
    x = np.asarray(x, float)
    ok = ~np.isnan(x)
    v = np.where(ok, x, 0.0)
    c1 = np.r_[0.0, np.cumsum(v)]; c2 = np.r_[0.0, np.cumsum(v * v)]; cn = np.r_[0, np.cumsum(ok)]
    i = np.arange(1, len(x) + 1); j = np.maximum(i - n, 0)
    s1, s2, k = c1[i] - c1[j], c2[i] - c2[j], cn[i] - cn[j]
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = s1 / k
        var = (s2 - s1 * s1 / k) / (k - 1)
    var = np.where(var < 0, 0.0, var)
    bad = k < max(min_n, 2)
    return np.where(bad, np.nan, mean), np.where(bad, np.nan, np.sqrt(var))


def atr(h, l, c, n=14):
    """True range averaged with weights (1 - 1/n)^k over all bars so far (the research's pandas ewm(alpha=1/n))."""
    h, l, c = (np.asarray(v, float) for v in (h, l, c))
    pc = np.r_[np.nan, c[:-1]]
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    a = 1.0 - 1.0 / n
    out = np.empty(len(tr)); num = den = 0.0
    for i, x in enumerate(tr):
        num = x + a * num; den = 1.0 + a * den; out[i] = num / den
    return out


def features(h, l, c, oi, prem, window_h=4):
    """Arrays aligned with the hourly bars. oi / prem may contain NaN (missing hours)."""
    c = np.asarray(c, float); oi = np.asarray(oi, float); prem = np.asarray(prem, float)
    L = int(window_h)
    lr = np.r_[np.nan, np.diff(np.log(c))]
    _, sig = _rolling_mean_std(lr, 168, 100)
    cL = np.r_[np.full(L, np.nan), c[:-L]]; oL = np.r_[np.full(L, np.nan), oi[:-L]]
    with np.errstate(invalid="ignore", divide="ignore"):
        rz = np.log(c / cL) / (sig * np.sqrt(L))
        doi = oi / oL - 1.0
    pm, ps = _rolling_mean_std(prem, 720, 300)
    with np.errstate(invalid="ignore", divide="ignore"):
        pz = (prem - pm) / ps
    return dict(rz=rz, doi=doi, pz=pz, atr=atr(h, l, c))


def signal(f, move_k=1.5, oi_drop=0.12, premium_z=-1.0, **_):
    """True at the bars whose close triggers a buy (NaN inputs never trigger)."""
    with np.errstate(invalid="ignore"):
        s = (f["rz"] <= -move_k) & (f["doi"] <= -oi_drop)
        if premium_z is not None:
            s &= f["pz"] <= premium_z
    return np.nan_to_num(s).astype(bool)
