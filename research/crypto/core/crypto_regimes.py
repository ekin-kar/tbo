"""Crypto market regime engine (v3.2, Nov 2026). Strictly causal: every value is indexed by the moment it becomes known
(the CLOSE of the daily candle it describes), and a trade / order uses the last value known before it.

Per coin, daily (UTC) candles from the 1m data:
  Dir20   (C - C[-20]) / ATR14                         signed 20-day move in ATR
  Er20    |C - C[-20]| / sum |C[k] - C[k-1]|           efficiency ratio
  R2s60   sign(slope) x R^2 of a 60-day regression of log close
  VolReg  ATR14 / ATR100
  Ovl10   mean over 10 days of the overlap of consecutive candles ((min H - max L) / (max H - min L); < 0 = a gap)
  Bofu    20-day share of up-pokes that closed above the previous high (follow-through), Bofd the same down
  Chg5    5-day move / ATR14;  dE50, dE200: distance from the EMA50 / EMA200 in ATR
  Bo4u / Bo4d   share of 4h 20-candle breakouts of the last 45 days whose close 24 h later was still beyond the level
Market (DEV12): breadth50 (share above their daily EMA50), nethi (share of coins that broke a 4h 20-candle high that day minus
  lows), disp (cross-coin std of daily returns), corr7 (mean 7-day correlation with BTC).
Derivatives (from Dec 2021): oi_rank90, doi3d, doi7d, fund_rank90 (of the 8h settlements), pz (premium z, 30 days).
Classifiers, fitted on 2020-01 .. 2023-12 ONLY (DEV12 pooled), frozen in FIT (thresholds / centroids):
  RB   readable: trend side (Dir20 terciles) x quality (Clean: Er20 >= median and Ovl10 <= median; else Choppy), and for
       flat markets Calm / Wild (VolReg median): UpClean UpChop DownClean DownChop FlatCalm FlatWild
  TS   two-speed: macro (Dir20 terciles: Up / Flat / Down) x swing (Chg5 sign) x fast vol (VolReg median): 12 states
  HM   6-state nearest-centroid on the z-scored 7 core features (k-means on dev; H0..H5 ordered by mean Dir20)"""
import json
from pathlib import Path
import numpy as np, pandas as pd
import common as C
import v29lib as L
import hourly51 as H

DEV12, HOLD_BIG, HOLD39 = H.DEV12, H.HOLD_BIG, H.HOLD39
CORE7 = ["Dir20", "Er20", "R2s60", "VolReg", "Ovl10", "Bofu", "Bofd"]
DEV_END = "2024-01-01"
CACHE = C.D.CACHE / "v32"
_D = {}


def _atr(h, l, c, n):
    return C.I.atr(h, l, c, n)


def _ema(x, n):
    return C.I.ema(x, n)


def daily(sym):
    """Daily candles of a coin + its features, index = the day's CLOSE time (known from then on)."""
    if sym in _D:
        return _D[sym]
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"daily_{sym}.pkl"
    if f.exists():
        _D[sym] = pd.read_pickle(f); return _D[sym]
    m = L.m1(sym)
    d = C.D.resample(m, 1440)
    o, h, l, c = (np.asarray(d[k], float) for k in ("o", "h", "l", "c"))
    a14 = _atr(h, l, c, 14); a100 = _atr(h, l, c, 100)
    n = len(c); s = pd.Series(c)
    out = pd.DataFrame(index=pd.to_datetime((np.asarray(d["t"], np.int64) + 1440) * 60_000_000_000))
    out["o"], out["h"], out["l"], out["c"], out["atr"] = o, h, l, c, a14
    with np.errstate(invalid="ignore", divide="ignore"):
        out["Dir20"] = (s - s.shift(20)).to_numpy() / a14
        out["Er20"] = (s - s.shift(20)).abs().to_numpy() / s.diff().abs().rolling(20).sum().to_numpy()
        lc = np.log(c); x = np.arange(n, dtype=float)
        lcs, xs = pd.Series(lc), pd.Series(x)
        cov = lcs.rolling(60).cov(xs); vx = xs.rolling(60).var(); vy = lcs.rolling(60).var()
        r2 = (cov ** 2 / (vx * vy)).to_numpy()
        out["R2s60"] = np.sign(cov.to_numpy()) * r2
        out["VolReg"] = a14 / a100
        hp, lp = np.r_[np.nan, h[:-1]], np.r_[np.nan, l[:-1]]
        ov = (np.minimum(h, hp) - np.maximum(l, lp)) / (np.maximum(h, hp) - np.minimum(l, lp))
        out["Ovl10"] = pd.Series(ov).rolling(10).mean().to_numpy()
        up = h > hp; dn = l < lp
        out["Bofu"] = pd.Series((up & (c > hp)).astype(float)).rolling(20).sum().to_numpy() / pd.Series(up.astype(float)).rolling(20).sum().to_numpy()
        out["Bofd"] = pd.Series((dn & (c < lp)).astype(float)).rolling(20).sum().to_numpy() / pd.Series(dn.astype(float)).rolling(20).sum().to_numpy()
        out["Chg5"] = (s - s.shift(5)).to_numpy() / a14
        out["dE50"] = (c - _ema(c, 50)) / a14
        out["dE200"] = (c - _ema(c, 200)) / a14
        out["ret"] = s.pct_change().to_numpy()
    out.loc[out.index < out.index[0] + pd.Timedelta(days=100), ["VolReg"]] = np.nan          # ATR100 warm-up
    bo = bo4(sym)
    out = out.join(bo.reindex(out.index, method="ffill"))
    out.to_pickle(f)
    _D[sym] = out
    return out


def bo4(sym, N=20, look=6, days=45):
    """4h 20-candle breakout follow-through: each 4h candle that breaks the previous N-candle high (low) is an event,
    resolved `look` candles later (close still beyond the level = success); daily share over the last `days` days of
    events RESOLVED by the day's close."""
    m = L.m1(sym)
    q = C.D.resample(m, 240)
    h, l, c = (np.asarray(q[k], float) for k in ("h", "l", "c"))
    hi = pd.Series(h).rolling(N).max().shift(1).to_numpy(); lo = pd.Series(l).rolling(N).min().shift(1).to_numpy()
    tclose = q["t"] + 240
    n = len(c); res_t = np.r_[tclose[look:], np.full(look, np.iinfo(np.int64).max // 2)]   # resolution time
    cl = np.r_[c[look:], np.full(look, np.nan)]
    up = h > hi; dn = l < lo
    ev = []
    for mask, okc, nm in ((up, cl > hi, "u"), (dn, cl < lo, "d")):
        e = pd.DataFrame({"t": res_t[mask], "ok": okc[mask].astype(float)})
        e = e[e.t < np.iinfo(np.int64).max // 4]
        e.index = pd.to_datetime(e.t * 60_000_000_000)
        r = e.ok.rolling(f"{days}D").mean()
        cnt = e.ok.rolling(f"{days}D").count()
        ev.append(pd.DataFrame({f"Bo4{nm}": r.where(cnt >= 3), f"nbo4{nm}": cnt}).groupby(level=0).last())
    out = ev[0].join(ev[1], how="outer").sort_index().ffill()
    # daily breakout flags for breadth (any 4h break of the 20-candle high / low during the day)
    dd = pd.DataFrame({"hi": up.astype(float), "lo": dn.astype(float)}, index=pd.to_datetime(tclose * 60_000_000_000))
    dday = dd.resample("1D", label="right", closed="right").max()
    out = out.resample("1D", label="right", closed="right").last().ffill().join(dday.rename(columns={"hi": "brk_hi", "lo": "brk_lo"}), how="outer")
    return out


def deriv(sym):
    """OI / funding / premium features (daily, at the day's close), from hourly51 (Dec 2021 on)."""
    try:
        df = H.hourly(sym)
    except Exception:
        return pd.DataFrame()
    oi = df.oi.ffill(); pr = df.prem; fu = df.fund
    end = df.index + pd.Timedelta(hours=1)
    x = pd.DataFrame({"oi": oi.to_numpy(), "prem": pr.to_numpy(), "fund": fu.to_numpy()}, index=end)
    out = pd.DataFrame(index=x.index)
    out["oi_rank90"] = x.oi.rolling(2160, min_periods=1080).rank(pct=True)
    out["doi3d"] = x.oi / x.oi.shift(72) - 1
    out["doi7d"] = x.oi / x.oi.shift(168) - 1
    st = x.fund[x.index.hour % 8 == 1]                               # (the hour after each settlement)
    out["fund_rank90"] = st.rolling(270, min_periods=135).rank(pct=True).reindex(out.index).ffill()
    out["pz"] = (x.prem - x.prem.rolling(720, min_periods=300).mean()) / x.prem.rolling(720, min_periods=300).std()
    return out.resample("1D", label="right", closed="right").last()


_MK = {}


def market():
    """DEV12 breadth / dispersion / correlation, daily at the close."""
    if "m" in _MK:
        return _MK["m"]
    f = CACHE / "market.pkl"
    if f.exists():
        _MK["m"] = pd.read_pickle(f); return _MK["m"]
    D = {s: daily(s) for s in DEV12}
    idx = D["BTCUSDT"].index
    above = pd.DataFrame({s: (d.dE50 > 0).astype(float).where(d.dE50.notna()) for s, d in D.items()}).reindex(idx)
    bh = pd.DataFrame({s: d.brk_hi for s, d in D.items()}).reindex(idx); bl = pd.DataFrame({s: d.brk_lo for s, d in D.items()}).reindex(idx)
    rets = pd.DataFrame({s: d.ret for s, d in D.items()}).reindex(idx)
    out = pd.DataFrame(index=idx)
    out["breadth50"] = above.mean(axis=1)
    out["nethi"] = bh.mean(axis=1) - bl.mean(axis=1)
    out["disp"] = rets.std(axis=1)
    cr = [rets[s].rolling(7).corr(rets["BTCUSDT"]) for s in DEV12 if s != "BTCUSDT"]
    out["corr7"] = pd.concat(cr, axis=1).mean(axis=1)
    out.to_pickle(f)
    _MK["m"] = out
    return out


# ── classifiers (fitted on dev, frozen) ─────────────────────────────────────────────────────────────────────────
FIT_FILE = CACHE / "fit.json"


def fit():
    """Thresholds (RB, TS) and centroids (HM) from 2020-23 daily features of the DEV12 coins pooled."""
    rows = pd.concat([daily(s)[CORE7 + ["Chg5"]].assign(sym=s) for s in DEV12])
    dev = rows[rows.index < DEV_END].dropna()
    q = lambda col, p: float(dev[col].quantile(p))
    F = dict(dir_lo=q("Dir20", 1 / 3), dir_hi=q("Dir20", 2 / 3), er_med=q("Er20", 0.5), ovl_med=q("Ovl10", 0.5), vol_med=q("VolReg", 0.5),
             mu={c: float(dev[c].mean()) for c in CORE7}, sd={c: float(dev[c].std()) for c in CORE7})
    Z = ((dev[CORE7] - pd.Series(F["mu"])) / pd.Series(F["sd"])).to_numpy()
    rng = np.random.default_rng(0)
    best = None
    for _ in range(20):                                              # k-means (k = 6), best of 20 starts
        cen = Z[rng.choice(len(Z), 6, replace=False)]
        for _ in range(200):
            lab = np.argmin(((Z[:, None, :] - cen[None]) ** 2).sum(-1), axis=1)
            new = np.array([Z[lab == k].mean(0) if (lab == k).any() else cen[k] for k in range(6)])
            if np.allclose(new, cen):
                break
            cen = new
        inertia = ((Z - cen[lab]) ** 2).sum()
        if best is None or inertia < best[0]:
            best = (inertia, cen)
    cen = best[1]
    order = np.argsort(cen[:, 0])                                     # H0 = most negative Dir20 ... H5 = most positive
    F["centroids"] = cen[order].tolist()
    CACHE.mkdir(parents=True, exist_ok=True)
    FIT_FILE.write_text(json.dumps(F, indent=1))
    return F


def frozen():
    return json.loads(FIT_FILE.read_text()) if FIT_FILE.exists() else fit()


RB_STATES = ["UpClean", "UpChop", "FlatCalm", "FlatWild", "DownChop", "DownClean"]


def classify(d, F=None):
    """RB / TS / HM labels for a daily feature frame (NaN features -> 'na')."""
    F = F or frozen()
    out = pd.DataFrame(index=d.index)
    side = np.where(d.Dir20 >= F["dir_hi"], 1, np.where(d.Dir20 <= F["dir_lo"], -1, 0))
    clean = (d.Er20 >= F["er_med"]) & (d.Ovl10 <= F["ovl_med"])
    calm = d.VolReg <= F["vol_med"]
    rb = np.where(side > 0, np.where(clean, "UpClean", "UpChop"), np.where(side < 0, np.where(clean, "DownClean", "DownChop"),
                  np.where(calm, "FlatCalm", "FlatWild")))
    ok = d[CORE7].notna().all(axis=1).to_numpy()
    out["RB"] = np.where(ok, rb, "na")
    mac = np.where(side > 0, "Up", np.where(side < 0, "Dn", "Flat"))
    sw = np.where(d.Chg5 >= 0, "up", "dn")
    out["TS"] = np.where(ok, pd.Series(mac).str.cat([pd.Series(sw), pd.Series(np.where(calm, "calm", "wild"))], sep="/").to_numpy(), "na")
    Z = ((d[CORE7] - pd.Series(F["mu"])) / pd.Series(F["sd"])).to_numpy()
    cen = np.array(F["centroids"])
    lab = np.argmin(((np.nan_to_num(Z)[:, None, :] - cen[None]) ** 2).sum(-1), axis=1)
    out["HM"] = np.where(ok, np.char.add("H", lab.astype(str)), "na")
    return out


_R = {}


def regimes(sym):
    """Features + labels of a coin, daily at the close, joined with the market and derivatives features."""
    if sym in _R:
        return _R[sym]
    d = daily(sym)
    r = d.join(classify(d)).join(market(), rsuffix="_m").join(deriv(sym), how="left")
    _R[sym] = r
    return r


def at(sym, times, cols=None):
    """Regime values known at the given times (the last daily close at or before each time)."""
    r = regimes(sym)
    t = pd.to_datetime(times).values
    k = np.searchsorted(r.index.values, t, side="right") - 1
    ok = k >= 0
    kk = np.clip(k, 0, None)
    cols = cols or list(r.columns)
    out = r.iloc[kk][cols].reset_index(drop=True)
    out.loc[~ok, :] = np.nan
    return out
