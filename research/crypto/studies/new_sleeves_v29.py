"""Part 3 of the v2.9 round (Nov 2026): four NEW derivatives-microstructure sleeve families on hourly bars (51 coins,
core/hourly51.py, 2022-01 .. 2026-11-06). DEV12 to select, HOLD39 untouched (HOLD_BIG 14 + HOLD_SMALL 25 shown apart).
Any signal within 12 h of a v2.7 panic trigger on the same coin is dropped (only NEW, non-overlapping alpha is measured).

S1 crowded-long liquidation cascade (SHORT): OI rank 90 d >= q, mean premium z over 24 h >= p, the hourly close breaks
   the prior N-hour low while OI fell over 4 h by <= x (but > -10%: the start, not the exhausted bottom). Stop k ATR(4h),
   BE +1.5R, TP +4R, exit at once if the panic signal fires, max hold H.
S2 trapped-short squeeze breakout (LONG, bear regime): daily close < EMA50(1d), OI rank 90 d >= q, mean premium z over 4 h
   <= p, hourly close above the prior N-hour high, confirmed by spot-led volume (last 4h spot / perp volume > its 7-day
   average) or OI not flushing (4h OI change > -2%). Stop k ATR(4h), BE +1.5R, max hold H.
S3 BTC-ignition relative-strength rotation (both sides, BTC's direction): BTC's TBO v2.8 trade enters / reaches +1R /
   reaches +1.5R -> rank the other coins not extended (|close - EMA50(1d)| <= 2.5 ATR(1d) on the trade side) by residual
   return vs BTC over LB hours (ret - beta x ret_BTC, beta from 30 d hourly), optional 72 h OI change > 0; top K get a stop
   order at the 24 h (6 x 4h) extreme valid 24 h; stop 1 ATR(4h), BE +1.5R, max hold H.
S4 parabolic extension fade (both sides): |close - EMA50(1d)| >= e x ATR(1d), a new 20-candle 4h extreme within the last K
   4h candles, 4h OI change <= x (absorption), hourly close back through the low (high) of the last K closed 4h candles;
   stop at the extreme + 0.25 ATR(4h) (0.3-1.5 ATR(4h) from the entry), TP T R, max hold H.
Fills: signal at an hourly close -> entry at the next open (S3: stop order, fill at max(level, open)); pessimistic bars
(stop first, a gap through the stop fills at the open); costs taker 0.05% + slippage (BTC/ETH 0.01%, others 0.03%) per side
+ funding 0.01% / 8 h charged to both sides. One trade per coin at a time per setting. R = stop distance.
GATES (fixed in advance; periods 2022-23 and 2024-26):
  G1 dev       DEV12 (each trade 1 R unit): avg R > 0 and profit factor >= 1.2 in both periods, >= 30 trades in each
  G2 plateau   >= 60% of the grid neighbours (Chebyshev 1 on the ordinal axes) have avg R > 0 in both periods
  G3 luck      avg R beats >= 95% of 200 random-entry copies (same coin, side and count per period, random hours where the
               family's pre-condition holds, same exits) AND >= 95% of 40 time-shifted copies of the signal (+-6..120 h),
               in both periods
  G4 untouched HOLD39: avg R > 0 and PF > 1 in both periods
  G5 new alpha correlation of monthly R with TBO v2.8's monthly R and its result in TBO's losing months (shown)
  G6 money     bot v2.8 + panic v2.7 + the sleeve on DEV12 (u% of the balance at risk per trade, u = 0.5 / 1 / 2 x the
               ladder's BTC risk / 6) from $300 (starts 2022, 2024): more money and drop at most +1 point for some u, and with
               it 1,000 paired 2-year block-bootstrap journeys: median end higher, 1-in-10 drop at most +1 point
    python new_sleeves_v29.py         -> research/results/v29_S_grid.csv, v29_S_gates.csv (+ printed)"""
import itertools, os, sys
from multiprocessing import Pool
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v28nov")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
import numpy as np, pandas as pd
from numba import njit
import common as C, hourly51 as H
sys.path.insert(0, str(C.ROOT / "cryptobot"))
import panic_signal as PS                                          # noqa: E402

RES = C.ROOT / "research" / "results"
END = "2026-11-07"
PER = {"2022-23": ("2022-01-01", "2024-01-01"), "2024-26": ("2024-01-01", END)}
TAKER, FUND8 = 0.0005, 0.0001


# ── simulator ───────────────────────────────────────────────────────────────────────────────────────────────────
@njit(cache=True)
def sim(o, h, l, ent_j, ent_px, d, dist, tp_R, be_R, hold, force, cost):
    """Trades in signal order, one at a time. ent_j: entry bar (entry during that bar at ent_px). Returns (k, exit bar, R)."""
    n = len(o); m = len(ent_j)
    ok = np.zeros(m, np.bool_); xj = np.zeros(m, np.int64); R = np.zeros(m)
    busy = -1
    for k in range(m):
        j0 = ent_j[k]
        if j0 <= busy or j0 + hold >= n:
            continue
        e = ent_px[k]; D = dist[k]; dd = d[k]
        s = e - dd * D
        tp = e + dd * tp_R * D if tp_R > 0 else (np.inf if dd > 0 else -np.inf)
        best = 0.0; px = 0.0; jx = -1
        for j in range(j0, j0 + hold):
            if dd > 0:
                if j > j0 and o[j] <= s:
                    px = o[j]; jx = j; break
                if l[j] <= s:
                    px = s; jx = j; break
                if j > j0 and h[j] >= tp:
                    px = max(tp, o[j]) if o[j] > tp else tp; jx = j; break
                best = max(best, h[j] - e)
            else:
                if j > j0 and o[j] >= s:
                    px = o[j]; jx = j; break
                if h[j] >= s:
                    px = s; jx = j; break
                if j > j0 and l[j] <= tp:
                    px = tp; jx = j; break
                best = max(best, e - l[j])
            if be_R > 0 and best >= be_R * D:
                if dd > 0 and s < e:
                    s = e
                elif dd < 0 and s > e:
                    s = e
            if force[j] and j + 1 < n:
                px = o[j + 1]; jx = j + 1; break
        if jx < 0:
            jx = j0 + hold; px = o[jx]
        ok[k] = True; xj[k] = jx
        R[k] = ((px - e) * dd - cost * (e + px) - FUND8 * (jx - j0) / 8.0 * e) / D
        busy = jx
    return ok, xj, R


# ── features ─────────────────────────────────────────────────────────────────────────────────────────────────────
_F = {}


def feats(sym):
    if sym in _F:
        return _F[sym]
    df = H.hourly(sym)
    o, h, l, c = (df[k].to_numpy(float) for k in "ohlc")
    f = PS.features(h, l, c, df.oi.to_numpy(float), df.prem.to_numpy(float), 4)
    t_close = df.index + pd.Timedelta(hours=1)                          # decision time = close of the hour
    q4 = df[["o", "h", "l", "c"]].resample("4h").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    pc = q4.c.shift(1)
    tr4 = np.fmax(q4.h - q4.l, np.fmax((q4.h - pc).abs(), (q4.l - pc).abs()))
    atr4 = tr4.ewm(alpha=1 / 14, adjust=False).mean()
    end4 = q4.index + pd.Timedelta(hours=4)                             # a 4h candle is known from its end
    k4 = np.searchsorted(end4.values, t_close.values, side="right") - 1
    ok4 = k4 >= 20
    kk = np.clip(k4, 0, None)
    A4 = np.where(ok4, atr4.to_numpy()[kk], np.nan)
    hi20_4 = q4.h.rolling(20).max().to_numpy(); lo20_4 = q4.l.rolling(20).min().to_numpy()
    d1 = df[["o", "h", "l", "c"]].resample("1D").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    e50 = d1.c.ewm(span=50, adjust=False).mean(); pcd = d1.c.shift(1)
    atrd = np.fmax(d1.h - d1.l, np.fmax((d1.h - pcd).abs(), (d1.l - pcd).abs())).ewm(alpha=1 / 14, adjust=False).mean()
    endd = d1.index + pd.Timedelta(days=1)
    kd = np.searchsorted(endd.values, t_close.values, side="right") - 1
    okd = kd >= 50; kd2 = np.clip(kd, 0, None)
    ext = np.where(okd, (d1.c.to_numpy() - e50.to_numpy())[kd2] / atrd.to_numpy()[kd2], np.nan)
    below = np.where(okd, d1.c.to_numpy()[kd2] < e50.to_numpy()[kd2], False)
    oi = df.oi.ffill().to_numpy(float)
    rank90 = pd.Series(oi).rolling(90 * 24, min_periods=45 * 24).rank(pct=True).to_numpy()
    def chg(L):
        prev = np.r_[np.full(L, np.nan), oi[:-L]]
        with np.errstate(invalid="ignore", divide="ignore"):
            return oi / prev - 1
    pz = f["pz"]
    sv = df.spot_v4.to_numpy(float); pv = df.perp_v4.to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        sr = sv / pv
    sr_avg = pd.Series(sr).rolling(7 * 24, min_periods=3 * 24).mean().to_numpy()
    panic = PS.signal(f, **PS.DEFAULTS)
    pidx = np.flatnonzero(panic)
    near = np.zeros(len(c), bool)                                       # within 12 h of a panic trigger (either side)
    for i in pidx:
        near[max(0, i - 12):i + 13] = True
    lr = np.r_[np.nan, np.diff(np.log(c))]
    F_ = dict(df=df, o=o, h=h, l=l, c=c, t=df.index, A4=A4, ext=ext, below=below, rank90=rank90, doi4=chg(4), doi72=chg(72),
              pz=pz, pz24=pd.Series(pz).rolling(24, min_periods=12).mean().to_numpy(), pz4=pd.Series(pz).rolling(4, min_periods=2).mean().to_numpy(),
              spot_led=sr > sr_avg, has_spot=~np.isnan(sr), panic=panic, near=near, lr=lr,
              k4=k4, q4h=q4.h.to_numpy(), q4l=q4.l.to_numpy(), hi20_4=hi20_4, lo20_4=lo20_4,
              cost=TAKER + (0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003))
    for N in (10, 12, 20, 24, 30, 36):
        F_[f"hh{N}"] = pd.Series(h).rolling(N).max().shift(1).to_numpy()
        F_[f"ll{N}"] = pd.Series(l).rolling(N).min().shift(1).to_numpy()
    _F[sym] = F_
    return F_


def lastK4(F_, K, side):
    """Per hour: max high (side 1) / min low (side -1) of the last K closed 4h candles."""
    k4 = F_["k4"]; src = F_["q4h"] if side > 0 else F_["q4l"]
    s = pd.Series(src).rolling(K).max() if side > 0 else pd.Series(src).rolling(K).min()
    s = s.to_numpy()
    return np.where(k4 >= K, s[np.clip(k4, 0, None)], np.nan)


# ── families: signal arrays (decision bar i, dir, stop distance) ─────────────────────────────────────────────────────
S1G = dict(q=(0.75, 0.85), p=(0.0, 0.5, 1.0), N=(10, 20, 30), x=(-0.015, -0.025, -0.04), katr=(1.5, 2.5), H=(16, 24, 36, 48))
S2G = dict(q=(0.5, 0.7), p=(-0.75, -1.25, -1.75), N=(12, 24, 36), conf=("spot", "oi"), katr=(1.0, 1.5), H=(18, 36, 60))
S3G = dict(trig=("entry", "1R", "1.5R"), LB=(48, 72), K=(1, 2), oic=("off", "on"), H=(72, 96, 120))
S4G = dict(e=(3.5, 4.0, 5.0), K=(2, 3), x=(0.0, -0.02, -0.04), T=(2.5, 3.5), H=(16, 24, 36))
GRIDS = {"S1": S1G, "S2": S2G, "S3": S3G, "S4": S4G}
ORDINAL = {"S1": ("q", "p", "N", "x", "katr", "H"), "S2": ("q", "p", "N", "katr", "H"), "S3": ("trig", "LB", "K", "H"), "S4": ("e", "K", "x", "T", "H")}
EXIT = {"S1": lambda p: dict(tp_R=4.0, be_R=1.5, hold=p["H"]), "S2": lambda p: dict(tp_R=0.0, be_R=1.5, hold=p["H"]),
        "S3": lambda p: dict(tp_R=0.0, be_R=1.5, hold=p["H"]), "S4": lambda p: dict(tp_R=p["T"], be_R=0.0, hold=p["H"])}


def precond(fam, F_, p):
    """Hours where the family's pre-condition (regime part) holds: the random-entry null draws from these."""
    with np.errstate(invalid="ignore"):
        if fam == "S1":
            return (F_["rank90"] >= p["q"]) & (F_["pz24"] >= p["p"]) & ~F_["near"]
        if fam == "S2":
            return F_["below"] & (F_["rank90"] >= p["q"]) & (F_["pz4"] <= p["p"]) & ~F_["near"]
        if fam == "S4":
            return (np.abs(F_["ext"]) >= p["e"]) & ~F_["near"]
    raise ValueError(fam)


def signals(fam, sym, p):
    """(i, dir, dist) arrays for S1/S2/S4 (entry next open)."""
    F_ = feats(sym); c = F_["c"]; A4 = F_["A4"]
    with np.errstate(invalid="ignore"):
        if fam == "S1":
            m = precond(fam, F_, p) & (c < F_[f"ll{p['N']}"]) & (F_["doi4"] <= p["x"]) & (F_["doi4"] > -0.10)
            i = np.flatnonzero(m & ~np.isnan(A4)); return i, np.full(len(i), -1), p["katr"] * A4[i]
        if fam == "S2":
            cf = (F_["spot_led"] & F_["has_spot"]) if p["conf"] == "spot" else (F_["doi4"] > -0.02)
            m = precond(fam, F_, p) & (c > F_[f"hh{p['N']}"]) & cf
            i = np.flatnonzero(m & ~np.isnan(A4)); return i, np.full(len(i), 1), p["katr"] * A4[i]
        if fam == "S4":
            ext = F_["ext"]; base = precond(fam, F_, p) & (F_["doi4"] <= p["x"]) & ~np.isnan(A4)
            out_i, out_d, out_s = [], [], []
            for side in (1, -1):                                       # side = direction of the extension; trade = -side
                k4 = F_["k4"]; kk = np.clip(k4, 0, None)
                xt = lastK4(F_, p["K"], side)                          # extreme of the last K 4h candles
                ref = (F_["hi20_4"] if side > 0 else F_["lo20_4"])[kk]
                new_ext = (xt >= ref) if side > 0 else (xt <= ref)
                brk = lastK4(F_, p["K"], -side)                        # low (high) of the last K 4h candles
                trig = (c < brk) if side > 0 else (c > brk)
                m = base & (ext * side > 0) & new_ext & trig
                i = np.flatnonzero(m)
                e_next = F_["o"][np.clip(i + 1, 0, len(c) - 1)]
                dist = np.clip((xt[i] + side * 0.25 * A4[i] - e_next) * side, 0.3 * A4[i], 1.5 * A4[i])
                out_i.append(i); out_d.append(np.full(len(i), -side)); out_s.append(dist)
            i = np.concatenate(out_i); o_ = np.argsort(i, kind="stable")
            return i[o_], np.concatenate(out_d)[o_], np.concatenate(out_s)[o_]
    raise ValueError(fam)


def run_sig(sym, i, d, dist, ex, force_panic=False):
    F_ = feats(sym); n = len(F_["o"])
    keep = (i + 1 < n) & (dist > 0) & np.isfinite(dist)
    i, d, dist = i[keep], d[keep], dist[keep]
    ent_j = i + 1; ent_px = F_["o"][np.clip(ent_j, 0, n - 1)]
    force = F_["panic"] if force_panic else np.zeros(n, np.bool_)
    ok, xj, R = sim(F_["o"], F_["h"], F_["l"], ent_j.astype(np.int64), ent_px, d.astype(np.int64), dist.astype(float),
                    float(ex["tp_R"]), float(ex["be_R"]), int(ex["hold"]), force, F_["cost"])
    t = F_["t"]
    return pd.DataFrame(dict(sym=sym, t=t[ent_j[ok]], t_exit=t[np.clip(xj[ok], 0, n - 1)], dir=d[ok], R=R[ok]))


# ── S3 (event-driven, cross-sectional) ───────────────────────────────────────────────────────────────────────────
_PANEL = {}
_S3C = {}


def panel(coins):
    key = tuple(coins)
    if key not in _PANEL:
        _PANEL[key] = pd.DataFrame({s: H.hourly(s).c for s in coins})
    return _PANEL[key]


def btc_triggers():
    """BTC TBO v2.8 trades: (time, dir) at entry, at +1R, at +1.5R (first full minute after the fill), hour-rounded up."""
    import botsim as B, v29lib as L
    P = pd.read_pickle(C.D.CACHE / "trade_prices_v28nov.pkl")
    X = B.ALL[("BTCUSDT", 0.0003)].merge(P, on=["sym", "entry_time"])
    X1 = X.assign(be_time=L.be_times(X, "BTCUSDT", R=1.0))
    out = {"entry": X[["entry_time", "dir"]].rename(columns={"entry_time": "t"}),
           "1R": X1.loc[X1.be_time < X1.exit_time, ["be_time", "dir"]].rename(columns={"be_time": "t"}),
           "1.5R": X.loc[X.be_time < X.exit_time, ["be_time", "dir"]].rename(columns={"be_time": "t"})}
    for k in out:
        out[k] = out[k].assign(t=out[k].t.dt.ceil("1h")).reset_index(drop=True)
    return out


def s3_trades(p, coins, trig=None, rng=None, shift_h=0):
    """S3 trades on `coins` (BTC excluded). rng: random-entry null (random coins from the eligible set instead of the
    top K). shift_h: trigger times shifted (time-shifted copy)."""
    trig = (trig or btc_triggers())[p["trig"]]
    alts = [s for s in coins if s != "BTCUSDT"]
    Pn = panel(alts + ["BTCUSDT"]); lr = np.log(Pn).diff()
    LB = p["LB"]; rows = []
    for _, tr in trig.iterrows():
        T = tr.t + pd.Timedelta(hours=shift_h); d = int(tr.dir)
        if T not in Pn.index:
            continue
        ti = Pn.index.get_loc(T) - 1                                   # last closed hour before T
        if ti < 720:
            continue
        ck = (tuple(alts), ti, d, LB)
        if ck not in _S3C:
            w = lr.iloc[ti - 719:ti + 1]
            b = w["BTCUSDT"]; vb = b.var()
            beta = w[alts].apply(lambda s: s.cov(b)) / vb
            r_alt = np.log(Pn[alts].iloc[ti] / Pn[alts].iloc[ti - LB]); r_b = np.log(Pn["BTCUSDT"].iloc[ti] / Pn["BTCUSDT"].iloc[ti - LB])
            resid = (r_alt - beta * r_b) * d
            el0 = []
            for s in alts:
                F_ = feats(s); j = np.searchsorted(F_["t"].values, Pn.index[ti].to_datetime64())
                if j >= len(F_["t"]) or F_["t"][j] != Pn.index[ti] or np.isnan(resid[s]) or np.isnan(F_["ext"][j]):
                    continue
                if F_["ext"][j] * d > 2.5 or F_["near"][j]:
                    continue
                el0.append((resid[s], s, j, F_["doi72"][j] > 0))
            _S3C[ck] = el0
        el = [(r_, s, j) for r_, s, j, up in _S3C[ck] if p["oic"] == "off" or up]
        if not el:
            continue
        el.sort(reverse=True)
        pick = el[:p["K"]] if rng is None else [el[q] for q in rng.choice(len(el), min(p["K"], len(el)), replace=False)]
        for _, s, j in pick:
            F_ = feats(s); lvl = (lastK4(F_, 6, d))[j]; A4 = F_["A4"][j]
            if np.isnan(lvl) or np.isnan(A4):
                continue
            for jj in range(j + 1, min(j + 25, len(F_["o"]) - 1)):
                if (d > 0 and F_["h"][jj] >= lvl) or (d < 0 and F_["l"][jj] <= lvl):
                    px = max(lvl, F_["o"][jj]) if d > 0 else min(lvl, F_["o"][jj])
                    rows.append((s, jj, px, d, A4)); break
    out = []
    for s in set(r[0] for r in rows):
        rr = sorted([r for r in rows if r[0] == s], key=lambda r: r[1])
        F_ = feats(s); n = len(F_["o"])
        ej = np.array([r[1] for r in rr], np.int64); ep = np.array([r[2] for r in rr]); dd = np.array([r[3] for r in rr], np.int64)
        ds = np.array([r[4] for r in rr])
        ok, xj, R = sim(F_["o"], F_["h"], F_["l"], ej, ep, dd, ds, 0.0, 1.5, int(p["H"]), np.zeros(n, np.bool_), F_["cost"])
        out.append(pd.DataFrame(dict(sym=s, t=F_["t"][ej[ok]], t_exit=F_["t"][np.clip(xj[ok], 0, n - 1)], dir=dd[ok], R=R[ok])))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["sym", "t", "t_exit", "dir", "R"])


# ── one setting on a universe ────────────────────────────────────────────────────────────────────────────────────
def trades(fam, p, coins, trig=None):
    if fam == "S3":
        return s3_trades(p, coins, trig)
    out = []
    for s in coins:
        i, d, dist = signals(fam, s, p)
        F_ = feats(s); keep = ~F_["near"][i]
        out.append(run_sig(s, i[keep], d[keep], dist[keep], EXIT[fam](p), force_panic=(fam == "S1")))
    return pd.concat(out, ignore_index=True)


def stats(T):
    out = {}
    for k, (a, b) in PER.items():
        g = T[(T.t >= a) & (T.t < b)].sort_values("t_exit")
        if len(g) == 0:
            out[k] = dict(n=0, avg=np.nan, pf=np.nan, net=0.0, dd=np.nan); continue
        e = np.cumsum(g.R.to_numpy()); dd = float(np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e))
        w, lo = g.R[g.R > 0].sum(), -g.R[g.R <= 0].sum()
        out[k] = dict(n=len(g), avg=float(g.R.mean()), pf=float(w / lo) if lo > 0 else np.inf, net=float(e[-1]), dd=dd,
                      win=float((g.R > 0).mean() * 100))
    return out


def params(fam):
    G = GRIDS[fam]
    return [dict(zip(G, v)) for v in itertools.product(*G.values())]


def job(args):
    fam, k = args
    p = params(fam)[k]
    trig = btc_triggers() if fam == "S3" else None
    rows = []
    for univ, coins in (("DEV12", H.DEV12), ("HOLD_BIG", H.HOLD_BIG), ("HOLD_SMALL", H.HOLD_SMALL)):
        T = trades(fam, p, coins if fam != "S3" else (coins if univ == "DEV12" else ["BTCUSDT"] + coins), trig)
        s = stats(T)
        rows.append(dict(fam=fam, k=k, univ=univ, **p, **{f"{a}_{m}": v for a, d in s.items() for m, v in d.items()}))
    return rows


def null_test(fam, p, T, trig=None, n=200, seed=0):
    """Percentile of the setting's avg R among n random-entry copies and 40 time-shifted copies, per period."""
    rng = np.random.default_rng(seed)
    real = stats(T)
    rand, shif = {k: [] for k in PER}, {k: [] for k in PER}
    if fam == "S3":
        for q in range(n):
            s = stats(s3_trades(p, H.DEV12, trig, rng=rng))
            for k in PER: rand[k].append(s[k]["avg"])
        for sh in rng.choice(np.r_[-120:-5, 6:121], 40, replace=False):
            s = stats(s3_trades(p, H.DEV12, trig, shift_h=int(sh)))
            for k in PER: shif[k].append(s[k]["avg"])
    else:
        sig = {s: signals(fam, s, p) for s in H.DEV12}
        for s in H.DEV12:                                              # drop near-panic signals as in the real run
            F_ = feats(s); i, d, dist = sig[s]; keep = ~F_["near"][i]; sig[s] = (i[keep], d[keep], dist[keep])
        elig = {s: np.flatnonzero(precond(fam, feats(s), p) & ~np.isnan(feats(s)["A4"])) for s in H.DEV12}
        draws = {k: [] for k in PER}
        for q in range(n):
            out = []
            for s in H.DEV12:
                i, d, dist = sig[s]
                if len(i) == 0 or len(elig[s]) == 0:
                    continue
                F_ = feats(s); A4 = F_["A4"]
                ri = np.sort(rng.choice(elig[s], len(i), replace=len(elig[s]) < len(i)))
                rd = rng.permutation(d)
                rdist = dist / A4[i] * A4[ri]                          # same stop in ATR units
                out.append(run_sig(s, ri, rd, rdist, EXIT[fam](p), force_panic=(fam == "S1")))
            st = stats(pd.concat(out)) if out else None
            for k in PER: rand[k].append(st[k]["avg"] if st else np.nan)
        for sh in rng.choice(np.r_[-120:-5, 6:121], 40, replace=False):
            out = []
            for s in H.DEV12:
                i, d, dist = sig[s]; F_ = feats(s); n_ = len(F_["o"])
                ii = i + int(sh); m = (ii > 0) & (ii < n_ - 2); ii = ii[m]
                A4 = F_["A4"]; dd2 = dist[m] / A4[i[m]] * A4[ii]
                m2 = np.isfinite(dd2)
                out.append(run_sig(s, ii[m2], d[m][m2], dd2[m2], EXIT[fam](p), force_panic=(fam == "S1")))
            st = stats(pd.concat(out))
            for k in PER: shif[k].append(st[k]["avg"])
    return {k: (float(np.nanmean(np.array(rand[k]) < real[k]["avg"])), float(np.nanmean(np.array(shif[k]) < real[k]["avg"]))) for k in PER}


def monthly(T):
    return T.groupby(T.t_exit.dt.to_period("M")).R.sum()


def main():
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 200)
    for s in H.ALL51:                                                  # warm the hourly caches in this process
        H.hourly(s)
    jobs = [(f, k) for f in GRIDS for k in range(len(params(f)))]
    print(f"{len(jobs)} settings x 3 universes", flush=True)
    with Pool(int(os.environ.get("V29_PROCS", 6))) as pool:
        rows = [r for rr in pool.imap_unordered(job, jobs, chunksize=4) for r in rr]
    G = pd.DataFrame(rows).sort_values(["fam", "k", "univ"])
    G.to_csv(RES / "v29_S_grid.csv", index=False)
    dev = G[G.univ == "DEV12"].set_index(["fam", "k"]); hold = G[G.univ != "DEV12"]
    hb = G[G.univ == "HOLD_BIG"].set_index(["fam", "k"]); hs = G[G.univ == "HOLD_SMALL"].set_index(["fam", "k"])
    g1 = (dev["2022-23_avg"] > 0) & (dev["2024-26_avg"] > 0) & (dev["2022-23_pf"] >= 1.2) & (dev["2024-26_pf"] >= 1.2) & \
         (dev["2022-23_n"] >= 30) & (dev["2024-26_n"] >= 30)
    pos = (dev["2022-23_avg"] > 0) & (dev["2024-26_avg"] > 0)
    gates = []
    for fam in GRIDS:
        P = params(fam); ords = ORDINAL[fam]; G_ = GRIDS[fam]
        cats = [a for a in G_ if a not in ords]
        for k, p in enumerate(P):
            nb = [kk for kk, q in enumerate(P) if kk != k and all(q[a] == p[a] for a in cats) and
                  max(abs(G_[a].index(q[a]) - G_[a].index(p[a])) for a in ords) <= 1]
            pl = float(np.mean([pos.loc[(fam, kk)] for kk in nb])) if nb else np.nan
            r = dev.loc[(fam, k)]
            # HOLD39 pooled = trade-weighted from the two halves
            def pooled(per):
                nb_, nsm = hb.loc[(fam, k), f"{per}_n"], hs.loc[(fam, k), f"{per}_n"]
                if nb_ + nsm == 0:
                    return np.nan
                return (np.nan_to_num(hb.loc[(fam, k), f"{per}_avg"]) * nb_ + np.nan_to_num(hs.loc[(fam, k), f"{per}_avg"]) * nsm) / (nb_ + nsm)
            gates.append(dict(fam=fam, k=k, **p, n22=r["2022-23_n"], avg22=r["2022-23_avg"], pf22=r["2022-23_pf"], n24=r["2024-26_n"],
                              avg24=r["2024-26_avg"], pf24=r["2024-26_pf"], plateau=pl, G1=bool(g1.loc[(fam, k)]), G2=bool(pl >= 0.6),
                              hold39_avg22=pooled("2022-23"), hold39_avg24=pooled("2024-26"),
                              hb_avg22=hb.loc[(fam, k), "2022-23_avg"], hb_avg24=hb.loc[(fam, k), "2024-26_avg"],
                              hs_avg22=hs.loc[(fam, k), "2022-23_avg"], hs_avg24=hs.loc[(fam, k), "2024-26_avg"]))
    Q = pd.DataFrame(gates)
    Q["G4"] = (Q.hold39_avg22 > 0) & (Q.hold39_avg24 > 0)
    # G3 for G1+G2 passers (and each family's best by min avg, for the record)
    Q["minavg"] = Q[["avg22", "avg24"]].min(axis=1)
    todo = set(Q[Q.G1 & Q.G2].index) | set(Q.loc[Q.groupby("fam").minavg.idxmax()].index)
    trig = btc_triggers()
    for ix in sorted(todo):
        r = Q.loc[ix]; p = params(r.fam)[int(r.k)]
        T = trades(r.fam, p, H.DEV12, trig)
        nt = null_test(r.fam, p, T, trig, n=200 if r.fam != "S3" else 100, seed=int(ix))
        Q.loc[ix, ["rand22", "shift22", "rand24", "shift24"]] = [nt["2022-23"][0], nt["2022-23"][1], nt["2024-26"][0], nt["2024-26"][1]]
    Q["G3"] = (Q.rand22 >= 0.95) & (Q.shift22 >= 0.95) & (Q.rand24 >= 0.95) & (Q.shift24 >= 0.95)
    Q.to_csv(RES / "v29_S_gates.csv", index=False)
    show = [c for c in Q.columns if c not in ("minavg",)]
    print("\nfunnel per family (settings): all -> G1 dev -> +G2 plateau -> +G3 luck -> +G4 HOLD39")
    for fam in GRIDS:
        q = Q[Q.fam == fam]
        print(f"  {fam}: {len(q)} -> {int(q.G1.sum())} -> {int((q.G1 & q.G2).sum())} -> {int((q.G1 & q.G2 & q.G3).sum())} -> "
              f"{int((q.G1 & q.G2 & q.G3 & q.G4).sum())};  dev avg R median {q.avg22.median():+.3f} / {q.avg24.median():+.3f}, "
              f"share avg>0 both {((q.avg22 > 0) & (q.avg24 > 0)).mean():.0%}")
    print("\nbest per family by min(avg R 2022-23, 2024-26) on DEV12, and every G1+G2 passer:")
    print(Q.loc[sorted(todo)][show].round(3).to_string(index=False))


def money_stage(ids=None):
    """G5 + G6 for the G1-G4 passers (or `ids` = rows of v29_S_gates.csv): sleeve on DEV12 next to bot v2.8 + panic v2.7."""
    import botsim as B, panic_sleeve as PSL, v29lib as L
    Q = pd.read_csv(RES / "v29_S_gates.csv")
    if ids is None:
        ids = list(Q[Q.G1 & Q.G2 & Q.G3 & Q.G4].index)
        if not ids:                                                    # nothing passed: the best of each family, for the record
            ids = list(Q.loc[Q.assign(m=Q[["avg22", "avg24"]].min(axis=1)).groupby("fam").m.idxmax()].index)
    ev = PSL.events(start="2022-01-01", end=END, extra_coins=())
    A0 = np.r_[B.TR, PSL.sleeve_rows(ev)]; A0 = A0[np.lexsort((A0[:, 5], A0[:, 0]))]
    base_pol = L.policy(extra_risk=[(5, 0.5)])
    Tb = B.T.assign(u=L.units(B.T.assign(R=B.T.R)))
    tbo_m = Tb.groupby(Tb.exit_time.dt.to_period("M")).u.sum()
    trig = btc_triggers(); out = []
    for ix in ids:
        r = Q.loc[ix]; p = {k: (type(v)(r[k]) if not isinstance(v, str) else str(r[k])) for k, v in params(r.fam)[int(r.k)].items()}
        T = trades(r.fam, p, H.DEV12, trig)
        sm = monthly(T).reindex(tbo_m.index).fillna(0.0); sm = sm[sm.index >= pd.Period("2022-01")]; tm = tbo_m[tbo_m.index >= pd.Period("2022-01")]
        corr = float(np.corrcoef(sm.values, tm.values)[0, 1])
        bad = tm < 0
        m = lambda c: T[c].values.astype("datetime64[m]").astype(np.int64)
        S = np.c_[m("t"), m("t_exit"), m("t"), np.ones(len(T)), T.R.to_numpy(), np.full(len(T), 6)]
        A = np.r_[A0, S]; A = A[np.lexsort((A[:, 5], A[:, 0]))]
        row = dict(id=int(ix), fam=r.fam, k=int(r.k), params=str(p), corr_tbo=corr, R_in_tbo_losing_months=float(sm[bad].sum()),
                   R_in_tbo_winning_months=float(sm[~bad].sum()), n_tbo_losing=int(bad.sum()))
        for a in ("2022-01-01", "2024-01-01"):
            b0 = L.money_window(A0, a, END, base_pol); row[f"base_m{a[:4]}"] = b0["final"]; row[f"base_dd{a[:4]}"] = b0["dd"]
        best = None
        for u in (0.5, 1.0, 2.0):
            pol = L.policy(extra_risk=[(5, 0.5), (6, u / 6)])
            for a in ("2022-01-01", "2024-01-01"):
                x = L.money_window(A, a, END, pol); row[f"u{u:g}_m{a[:4]}"] = x["final"]; row[f"u{u:g}_dd{a[:4]}"] = x["dd"]
            okk = all(row[f"u{u:g}_m{y}"] > row[f"base_m{y}"] and row[f"u{u:g}_dd{y}"] <= row[f"base_dd{y}"] + 1 for y in ("2022", "2024"))
            if okk and (best is None or row[f"u{u:g}_m2024"] > row[f"u{best:g}_m2024"]):
                best = u
        uu = best or 0.5
        bt = L.boot_money([A0, A], [base_pol, L.policy(extra_risk=[(5, 0.5), (6, uu / 6)])], n=int(os.environ.get("V29_BOOT", 1000)))
        row.update(u_boot=uu, boot_base_med=bt[0]["med"], boot_med=bt[1]["med"], boot_base_dd90=bt[0]["dd90"], boot_dd90=bt[1]["dd90"])
        row["G6"] = best is not None and bt[1]["med"] > bt[0]["med"] and bt[1]["dd90"] <= bt[0]["dd90"] + 1
        out.append(row); print(pd.Series(row).to_string(), flush=True)
    M = pd.DataFrame(out); M.to_csv(RES / "v29_S_money.csv", index=False)
    return M


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "money":
        money_stage([int(a) for a in sys.argv[2:]] or None)
    else:
        main()
