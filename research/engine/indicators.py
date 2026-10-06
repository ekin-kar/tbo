"""
Indicators computed on CLOSED candles, matching cTrader exactly (verified on XAUUSD 5m:
max difference 0.000005 over 165k bars).

Value at index k = indicator as of the close of candle k. A strategy acting on it
must enter at candle k's 'act' index (next 1m bar after the close), never earlier.
"""
import numpy as np
from numba import njit


@njit(cache=True)
def ema(x, n):
    """cTrader EMA: seeded with the first value, alpha = 2/(n+1)."""
    out = np.empty(len(x))
    if len(x) == 0:
        return out
    a = 2.0 / (n + 1.0)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out


@njit(cache=True)
def true_range(h, l, c):
    tr = np.full(len(h), np.nan)
    for i in range(1, len(h)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return tr


@njit(cache=True)
def atr(h, l, c, n):
    """cTrader ATR (Exponential smoothing): seeded with the true range of bar 1."""
    tr = true_range(h, l, c)
    out = np.full(len(h), np.nan)
    if len(h) < 2:
        return out
    a = 2.0 / (n + 1.0)
    out[1] = tr[1]
    for i in range(2, len(h)):
        out[i] = out[i - 1] + a * (tr[i] - out[i - 1])
    return out


@njit(cache=True)
def sma(x, n):
    out = np.full(len(x), np.nan)
    s = 0.0
    for i in range(len(x)):
        s += x[i]
        if i >= n:
            s -= x[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


@njit(cache=True)
def rolling_max(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        m = x[i]
        for j in range(i - n + 1, i):
            if x[j] > m:
                m = x[j]
        out[i] = m
    return out


@njit(cache=True)
def rolling_min(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        m = x[i]
        for j in range(i - n + 1, i):
            if x[j] < m:
                m = x[j]
        out[i] = m
    return out


@njit(cache=True)
def rsi_wilder(x, n):
    """Classic Wilder RSI (to be verified against cTrader before any strategy relies on it)."""
    out = np.full(len(x), np.nan)
    if len(x) <= n:
        return out
    g = 0.0
    lo = 0.0
    for i in range(1, n + 1):
        d = x[i] - x[i - 1]
        if d > 0:
            g += d
        else:
            lo -= d
    g /= n
    lo /= n
    out[n] = 100.0 if lo == 0 else 100.0 - 100.0 / (1.0 + g / lo)
    for i in range(n + 1, len(x)):
        d = x[i] - x[i - 1]
        gi = d if d > 0 else 0.0
        li = -d if d < 0 else 0.0
        g = (g * (n - 1) + gi) / n
        lo = (lo * (n - 1) + li) / n
        out[i] = 100.0 if lo == 0 else 100.0 - 100.0 / (1.0 + g / lo)
    return out
