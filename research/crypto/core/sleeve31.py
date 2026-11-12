"""v3.1 sleeve tools (Part 2): hourly / 4h decision bars for 51 coins, orders executed by the exact 1m engine
(xengine31.sim31: stop / market entries, pessimistic fill minute, fixed take-profit, breakeven, max hold, checkpoint
scratch rule, forced exit minutes) where 1m candles exist (DEV12 from data/, HOLD_BIG after fetch_extend m1big), else an
hourly-bar approximation (sim1h: the bar's path O-H-L-C if the open is nearer the high, else O-L-H-C).

Orders = DataFrame(t_place [minute, real time: the decision bar's close], dir (+1/-1), kind ('stop'/'market'), price (stop
trigger), dist (stop distance, price), tp_R (0 = none), valid_min). One position per coin at a time; the first fill cancels
the coin's other orders (a pending opposite-side order of the same decision is cancelled too).
Costs: entry taker 0.05% + slippage (BTC / ETH 0.01%, others 0.03%), exit the same, take-profit exits maker 0.02%; funding
0.01% / 8 h. R = net P&L / stop distance."""
from pathlib import Path
import numpy as np, pandas as pd
from numba import njit
import common as C
import hourly51 as H
import v29lib as L
import v31lib as W
import xengine31 as X31

EX, EX2 = C.ROOT / "data" / "extra", C.ROOT / "data" / "extra2"
DEV12, HOLD_BIG, HOLD_SMALL, HOLD39 = H.DEV12, H.HOLD_BIG, H.HOLD_SMALL, H.HOLD39
SLIP = {"BTCUSDT": 0.0001, "ETHUSDT": 0.0001}
PER = {"2020-23": ("2020-01-01", "2024-01-01"), "2022-23": ("2022-01-01", "2024-01-01"), "2024-26": ("2024-01-01", W.END)}
MIN = W.MIN
MIN_DIST = 0.001                     # orders with a stop closer than 0.1% of the price are data-gap artefacts (ATR ~ 0): dropped


def has_m1(sym):
    return (C.D.CACHE / f"{sym}_m1.npz").exists() or bool(list((C.ROOT / "data").glob(f"{sym}_1m_*_part*.parquet")))


_HB = {}


def bars(sym):
    """Hourly bars (index = hour open, UTC): o h l c from 1m (if present) else futures 1h klines; oi / prem / fund from
    hourly51 (from 2021-11; NaN before)."""
    if sym in _HB:
        return _HB[sym]
    if has_m1(sym):
        m = L.m1(sym)
        r = C.D.resample(m, 60)
        df = pd.DataFrame({"o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r["v"]}, index=pd.to_datetime(r["t"] * MIN))
    else:
        k = pd.read_csv(EX2 / f"{sym}_1h.csv.gz")
        df = pd.DataFrame({"o": k.o.values, "h": k.h.values, "l": k.l.values, "c": k.c.values, "v": k.quote_volume.values},
                          index=pd.to_datetime(k.open_ms, unit="ms"))
        df = df[~df.index.duplicated()].sort_index()
    df = df.reindex(pd.date_range(df.index[0], df.index[-1], freq="1h"))
    gap = df.c.isna()
    df[["o", "h", "l", "c"]] = df[["o", "h", "l", "c"]].ffill()
    for col in ("o", "h", "l"):
        df.loc[gap, col] = df.loc[gap, "c"]
    df["v"] = df.v.fillna(0.0)
    try:
        hx = H.hourly(sym)
        for col in ("oi", "prem", "fund"):
            df[col] = hx[col].reindex(df.index)
    except Exception:
        df["oi"] = np.nan; df["prem"] = np.nan; df["fund"] = np.nan
    df = df[df.index < pd.Timestamp(W.END)]
    _HB[sym] = df
    return df


def resample_bars(df, tf):
    if tf == 60:
        return df
    g = df.resample(f"{tf}min")
    out = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(), "v": g.v.sum(), "oi": g.oi.last(),
                        "prem": g.prem.last(), "fund": g.fund.last()}).dropna(subset=["c"])
    return out


_DD = {}


def daily(sym):
    """Daily close vs EMA50 side (+1/-1), ER10, |close-EMA50|/ATR14 of the last CLOSED day, as arrays indexed by day open."""
    if sym not in _DD:
        df = bars(sym)
        d = df[["o", "h", "l", "c"]].resample("1D").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
        cc = d.c.to_numpy(); e = C.I.ema(cc, 50); a = C.I.atr(d.h.to_numpy(), d.l.to_numpy(), cc, 14)
        er = np.full(len(cc), np.nan)
        er[10:] = np.abs(cc[10:] - cc[:-10]) / np.maximum(np.convolve(np.abs(np.diff(cc)), np.ones(10), "valid"), 1e-12)
        _DD[sym] = pd.DataFrame({"side": np.where(cc > e, 1, -1), "er": er, "ext": np.abs(cc - e) / a}, index=d.index + pd.Timedelta(days=1))
    return _DD[sym]


def daily_at(sym, tcl):
    """Values of the last day closed at or before the times tcl (DatetimeIndex / array of datetime64)."""
    D = daily(sym)
    k = np.searchsorted(D.index.values, np.asarray(tcl, "datetime64[ns]"), side="right") - 1
    ok = k >= 0
    kk = np.clip(k, 0, None)
    return {c: np.where(ok, D[c].to_numpy()[kk], np.nan) for c in D.columns}


def atr(df, n=14):
    return C.I.atr(df.h.to_numpy(), df.l.to_numpy(), df.c.to_numpy(), n)


# ── execution on 1m ────────────────────────────────────────────────────────────────────────────────────────────────
def run1m(sym, od, hold_h, be_R=0.0, rule=None, exit_at=None, fill_ok=None, start="2020-01-01", end=W.END):
    """Orders -> trades with the exact 1m engine. exit_at: array of minute timestamps where any open position is closed at
    the open (e.g. 20:00 UTC). fill_ok: per-minute bool (False = no fill), e.g. 'TBO flat on this coin'."""
    m = L.m1(sym); t = m["t"]; n = len(t)
    if len(od) == 0:
        return _empty(sym)
    od = od.sort_values("t_place", kind="stable")
    j = np.searchsorted(t, od.t_place.to_numpy(np.int64))
    ref = np.where(od.kind.to_numpy() == "market", m["c"][np.clip(j - 1, 0, n - 1)], od.price.to_numpy(float))
    ok = (j < n) & (od.dist.to_numpy() >= MIN_DIST * ref) & np.isfinite(od.dist.to_numpy())     # (gap artefacts: ATR ~ 0)
    od = od[ok]; j = j[ok]
    uj, inv = np.unique(j, return_inverse=True)
    optr = np.full(n, -1, np.int64); optr[uj] = np.arange(len(uj))
    shape = (len(uj), 2)
    kind = np.zeros(shape, np.int64); dirn = np.zeros(shape, np.int64); price = np.zeros(shape); sl = np.zeros(shape)
    tp = np.zeros(shape); exp = np.zeros(shape, np.int64)
    slot = np.where(od.dir.to_numpy() > 0, 0, 1)
    kd = np.where(od.kind.to_numpy() == "market", C.E.MARKET, C.E.STOP)
    kind[inv, slot] = kd; dirn[inv, slot] = od.dir.to_numpy(np.int64); price[inv, slot] = od.price.to_numpy(float)
    sl[inv, slot] = od.dist.to_numpy(float); tp[inv, slot] = od.tp_R.to_numpy(float) * od.dist.to_numpy(float)
    exp[inv, slot] = od.valid_min.to_numpy(np.int64)
    ones, zeros = np.ones(n, np.bool_), np.zeros(n, np.bool_)
    xl = zeros.copy()
    if exit_at is not None and len(exit_at):
        q = np.searchsorted(t, np.asarray(exit_at, np.int64)); q = q[q < n]; xl[q] = True
    fo = ones if fill_ok is None else fill_ok
    pa = W.exit31(be_R=be_R, lock_R=0.0, lock_to=0.0, lock2_R=0.0, lock2_to=0.0, stale_h=0, A=rule)
    res = X31.sim31(t, m["o"], m["h"], m["l"], m["c"], optr, kind, dirn, price, sl, tp, exp, ones, ones, zeros, xl, xl,
                    np.zeros(n), int(hold_h * 60), int(hold_h * 60), pa, pa, fo, fo, zeros, zeros, 0.0, 0, -0.5, 0, 0.0, np.zeros(n), ones)
    e_idx, x_idx, dirs, e_px, x_px, dist, reason, rf, hf, mfe, ld, rl, arm = res
    tr = pd.DataFrame({"t": pd.to_datetime(t[e_idx] * MIN), "t_exit": pd.to_datetime(t[x_idx] * MIN), "dir": dirs, "entry": e_px,
                       "exit": x_px, "dist": dist, "reason": [C.E.REASONS[r] for r in reason], "mfe": mfe})
    fee = C.TAKER + SLIP.get(sym, 0.0003)
    f_out = np.where(tr.reason.to_numpy() == "TP", C.MAKER, fee)
    hours = (tr.t_exit - tr.t).dt.total_seconds() / 3600
    cost = fee * tr.entry + f_out * tr.exit + C.FUNDING_8H * hours / 8 * tr.entry
    tr["R"] = ((tr.exit - tr.entry) * tr.dir - cost) / tr.dist
    tr["hours"] = hours; tr["sym"] = sym
    tr = tr[(tr.t >= start) & (tr.t < end) & (tr.reason != "END")].reset_index(drop=True)
    return tr


def _empty(sym):
    return pd.DataFrame(columns=["t", "t_exit", "dir", "entry", "exit", "dist", "reason", "mfe", "R", "hours", "sym"])


# ── execution on hourly bars (coins without 1m) ───────────────────────────────────────────────────────────────────────
@njit(cache=True)
def sim1h(o, h, l, c, oj, odir, okind, oprice, odist, otp, ovalid, hold, be_R, rT, rM, rthr, xbar, fee_in, fee_out, fee_tp):
    """Orders sorted by placement bar oj (active from bar oj on, for ovalid bars). Path heuristic inside a bar."""
    n = len(o); m = len(oj)
    E = np.full(m, -1, np.int64); X = np.zeros(m, np.int64); PX = np.zeros(m); PE = np.zeros(m); R = np.zeros(m); WHY = np.zeros(m, np.int64)
    busy = -1; k = 0
    while k < m:
        j0 = oj[k]
        if j0 <= busy:
            k += 1; continue
        # orders placed at the same bar (two-sided) compete: first fill wins
        k2 = k
        while k2 + 1 < m and oj[k2 + 1] == j0:
            k2 += 1
        filled = -1; fj = -1; fpx = 0.0
        for j in range(j0, min(j0 + ovalid[k], n)):
            best_q = -1; best_d = 1e18
            for q in range(k, k2 + 1):
                if okind[q] == 1:                                   # market at the open of j0
                    if j == j0:
                        best_q = q; best_d = 0.0
                    continue
                if odir[q] > 0 and h[j] >= oprice[q]:
                    d_ = max(oprice[q] - o[j], 0.0)
                    if d_ < best_d:
                        best_d = d_; best_q = q
                elif odir[q] < 0 and l[j] <= oprice[q]:
                    d_ = max(o[j] - oprice[q], 0.0)
                    if d_ < best_d:
                        best_d = d_; best_q = q
            if best_q >= 0:
                filled = best_q; fj = j
                if okind[best_q] == 1:
                    fpx = o[j]
                else:
                    fpx = max(oprice[best_q], o[j]) if odir[best_q] > 0 else min(oprice[best_q], o[j])
                break
        if filled < 0:
            k = k2 + 1; continue
        q = filled; d = odir[q]; e = fpx; D = odist[q]
        sl = e - d * D; tp = e + d * otp[q] * D if otp[q] > 0 else (np.inf if d > 0 else -np.inf)
        best = 0.0; px = 0.0; jx = -1; why = 0
        for j in range(fj, n):
            if j - fj >= hold or xbar[j] and j > fj:
                px = o[j]; jx = j; why = 3; break
            up_first = (h[j] - o[j]) < (o[j] - l[j])                 # open nearer the high: O-H-L-C
            if j > fj:
                if (d > 0 and o[j] <= sl) or (d < 0 and o[j] >= sl):
                    px = o[j]; jx = j; why = 1; break
                if (d > 0 and o[j] >= tp) or (d < 0 and o[j] <= tp):
                    px = o[j]; jx = j; why = 2; break
                hitS = (l[j] <= sl) if d > 0 else (h[j] >= sl)
                hitT = (h[j] >= tp) if d > 0 else (l[j] <= tp)
                fav_first = up_first if d > 0 else not up_first
                if hitS and hitT:
                    if fav_first:
                        px = tp; why = 2
                    else:
                        px = sl; why = 1
                    jx = j; break
                if hitS:
                    px = sl; jx = j; why = 1; break
                if hitT:
                    px = tp; jx = j; why = 2; break
            else:                                                      # fill bar: only the part of the path after the fill
                fav_first = up_first if d > 0 else not up_first
                if fav_first:                                          # fill on the way to the favourable extreme
                    if (d > 0 and h[j] >= tp) or (d < 0 and l[j] <= tp):
                        px = tp; jx = j; why = 2; break
                    if (d > 0 and l[j] <= sl) or (d < 0 and h[j] >= sl):
                        px = sl; jx = j; why = 1; break
                else:                                                  # adverse extreme first, then the fill, then the close
                    if (d > 0 and h[j] >= tp) or (d < 0 and l[j] <= tp):
                        px = tp; jx = j; why = 2; break
                    if (d > 0 and c[j] <= sl) or (d < 0 and c[j] >= sl):
                        px = sl; jx = j; why = 1; break
            fv = (h[j] - e) if d > 0 else (e - l[j])
            if fv > best:
                best = fv
            if be_R > 0 and best >= be_R * D:
                if d > 0 and sl < e:
                    sl = e
                elif d < 0 and sl > e:
                    sl = e
            if rT > 0 and j - fj + 1 >= rT and best < 99 * D:
                cur = ((c[j] - e) if d > 0 else (e - c[j])) / D
                if best >= rM * D and cur < rthr and j + 1 < n:
                    px = o[j + 1]; jx = j + 1; why = 3; break
        if jx < 0:
            k = k2 + 1; continue
        fo = fee_tp if why == 2 else fee_out
        R[q] = ((px - e) * d - fee_in * e - fo * px - 0.0001 * (jx - fj) / 8.0 * e) / D
        E[q] = fj; X[q] = jx; PX[q] = px; PE[q] = e; WHY[q] = why
        busy = jx
        k = k2 + 1
    return E, X, PE, PX, R, WHY


def run1h(sym, od, hold_h, be_R=0.0, rule=None, exit_at=None, start="2020-01-01", end=W.END, tf_valid=60):
    df = bars(sym)
    if len(od) == 0:
        return _empty(sym)
    t0 = df.index.values.astype("datetime64[m]").astype(np.int64)
    od = od.sort_values("t_place", kind="stable")
    oj = np.searchsorted(t0, od.t_place.to_numpy(np.int64))
    ref = np.where(od.kind.to_numpy() == "market", df.c.to_numpy()[np.clip(oj - 1, 0, len(t0) - 1)], od.price.to_numpy(float))
    keep = (oj < len(t0)) & (od.dist.to_numpy() >= MIN_DIST * ref) & np.isfinite(od.dist.to_numpy())
    od = od[keep]; oj = oj[keep]
    xbar = np.zeros(len(t0), np.bool_)
    if exit_at is not None and len(exit_at):
        q = np.searchsorted(t0, np.asarray(exit_at, np.int64)); xbar[q[q < len(t0)]] = True
    fee = C.TAKER + SLIP.get(sym, 0.0003)
    rT = int(rule["T_h"]) if rule else 0
    E, X, PE, PX, R, WHY = sim1h(df.o.to_numpy(), df.h.to_numpy(), df.l.to_numpy(), df.c.to_numpy(), oj.astype(np.int64),
                                 od.dir.to_numpy(np.int64), (od.kind.to_numpy() == "market").astype(np.int64), od.price.to_numpy(float),
                                 od.dist.to_numpy(float), od.tp_R.to_numpy(float), np.maximum(od.valid_min.to_numpy() // 60, 1).astype(np.int64),
                                 int(hold_h), float(be_R), rT, float(rule["mlo"]) if rule else 0.0, float(rule["thr"]) if rule else 0.0,
                                 xbar, fee, fee, C.MAKER)
    ok = E >= 0
    tr = pd.DataFrame({"t": df.index[E[ok]], "t_exit": df.index[X[ok]], "dir": od.dir.to_numpy()[ok], "entry": PE[ok], "exit": PX[ok],
                       "dist": od.dist.to_numpy()[ok], "reason": np.array(["", "SL", "TP", "TIME"])[WHY[ok]], "mfe": np.nan, "R": R[ok]})
    tr["hours"] = (tr.t_exit - tr.t).dt.total_seconds() / 3600; tr["sym"] = sym
    return tr[(tr.t >= start) & (tr.t < end)].reset_index(drop=True)


def run(sym, od, hold_h, prefer="1m", **kw):
    if prefer == "1m" and has_m1(sym):
        return run1m(sym, od, hold_h, **kw)
    kw.pop("fill_ok", None)
    return run1h(sym, od, hold_h, **kw)


# ── statistics ───────────────────────────────────────────────────────────────────────────────────────────────────
def stats(T, per=PER):
    out = {}
    for k, (a, b) in per.items():
        g = T[(T.t >= a) & (T.t < b)].sort_values("t_exit")
        if len(g) == 0:
            out[k] = dict(n=0, avg=np.nan, pf=np.nan, net=0.0, dd=np.nan, win=np.nan); continue
        e = np.cumsum(g.R.to_numpy(float)); dd = float(np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e))
        w, lo = g.R[g.R > 0].sum(), -g.R[g.R <= 0].sum()
        out[k] = dict(n=len(g), avg=float(g.R.mean()), pf=float(w / lo) if lo > 0 else np.inf, net=float(e[-1]), dd=dd,
                      win=float((g.R > 0).mean()))
    return out


def monthly(T, col="R", tcol="t_exit"):
    if len(T) == 0:
        return pd.Series(dtype=float)
    return T.groupby(pd.to_datetime(T[tcol]).dt.to_period("M"))[col].sum()


_PAN = {}


def panic_times():
    """Hours (minute timestamps) of every Panic v3.0 trigger (entry hour - 1 h) on DEV12."""
    if "t" not in _PAN:
        import panic_sleeve as PSL
        ev = PSL.events(start="2021-11-01", extra_coins=PSL.EXTRA_COINS, max_extra_open=None)
        _PAN["t"] = np.unique(ev.t.values.astype("datetime64[m]").astype(np.int64) - 60)
    return _PAN["t"]


def near_panic(tmin, hours=12):
    """True where the minute timestamps tmin are within +-hours of a panic trigger."""
    p = panic_times()
    k = np.searchsorted(p, tmin)
    d1 = np.abs(tmin - p[np.clip(k, 0, len(p) - 1)]); d0 = np.abs(tmin - p[np.clip(k - 1, 0, len(p) - 1)])
    return np.minimum(d0, d1) <= hours * 60
