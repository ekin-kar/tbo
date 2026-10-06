"""Winners vs losers, deep version: ~90 market measurements at the moment each TBO v2.2 order was placed
(the 4h close before the fill), plus a few known only at the fill. 4 coins, 2020-03 .. 2026-09.
Writes cache/loser_features.pkl; the analysis is in loser_eval.py."""
import pickle
import numpy as np, pandas as pd
import common as C, families as F

I = C.I
COINS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]
ALL = pickle.load(open(C.D.CACHE / "portfolio_trades.pkl", "rb"))


def rsi(x, n):
    return I.rsi_wilder(x, n)


def adx(h, l, c, n=14):
    up = np.r_[0, np.diff(h)]; dn = np.r_[0, -np.diff(l)]
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = I.true_range(h, l, c)
    w = lambda x: pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    atr = w(tr); pdi = 100 * w(pdm) / atr; ndi = 100 * w(ndm) / atr
    dx = 100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-12)
    return w(dx), pdi, ndi


def roll(x, n, f):
    return getattr(pd.Series(x).rolling(n, min_periods=n), f)().to_numpy()


def counts(sym):
    """trade count per 4h candle (not in the npz cache)."""
    parts = sorted((C.ROOT / "data").glob(f"{sym}_1m_*_part*.parquet"))
    df = pd.concat([pd.read_parquet(p, columns=["count"]) for p in parts])
    df = df[~df.index.duplicated()]
    t = df.index.values.astype("datetime64[m]").astype(np.int64)
    s = pd.Series(df["count"].to_numpy(float), index=t // 240 * 240)
    return s.groupby(level=0).sum()


def build(sym):
    m = C.load(sym)
    tr = ALL[(sym, 0.0003)].copy().reset_index(drop=True)
    c = F.resample(m, 240); d = F.resample(m, 1440)
    n4 = len(c["c"])
    side = tr.dir.to_numpy().astype(float)
    ei = np.searchsorted(m["t"], tr.entry_time.values.astype("datetime64[m]").astype(np.int64))
    k = np.searchsorted(c["act"], ei, side="right") - 1            # 4h close at which the order was placed
    kd = np.searchsorted(d["act"], c["act"][k], side="right") - 1  # last closed day then
    H, L, Cc, V, O = c["h"], c["l"], c["c"], c["v"], c["o"]
    a = I.atr(H, L, Cc, 14); a100 = I.atr(H, L, Cc, 100)
    hi20 = I.rolling_max(H, 20); lo20 = I.rolling_min(L, 20)
    cnt = counts(sym).reindex(c["t"]).fillna(0).to_numpy()
    f = {}
    s = side
    lvl = np.where(s > 0, hi20[k], lo20[k])
    A = a[k]
    # ── the breakout setup ──
    f["atr_pct"] = A / Cc[k] * 100
    f["atr_expand"] = A / a100[k]
    f["chan_width_atr"] = (hi20[k] - lo20[k]) / A
    f["chan_width_pct"] = (hi20[k] - lo20[k]) / Cc[k] * 100
    f["dist_trigger_atr"] = np.abs(lvl - Cc[k]) / A
    f["close_in_chan"] = np.where(s > 0, (Cc[k] - lo20[k]), (hi20[k] - Cc[k])) / np.maximum(hi20[k] - lo20[k], 1e-12)
    age, touch, touch_t = [], [], []
    for kk, sd, lv, aa in zip(k, s, lvl, A):
        seg = H[kk - 19:kk + 1] if sd > 0 else L[kk - 19:kk + 1]
        ext = seg.max() if sd > 0 else seg.min()
        age.append(19 - int(np.argmax((seg == ext)[::-1])))
        near = (seg >= lv - 0.25 * aa) if sd > 0 else (seg <= lv + 0.25 * aa)
        touch.append(int(near.sum()))
        near2 = (seg >= lv - 0.5 * aa) if sd > 0 else (seg <= lv + 0.5 * aa)
        touch_t.append(int(near2.sum()))
    f["level_age"] = np.array(age); f["touches_025"] = np.array(touch); f["touches_05"] = np.array(touch_t)
    # level vs longer channels: is the 20-candle level also the 60 / 120 candle extreme?
    for nn in (60, 120):
        hx = I.rolling_max(H, nn)[k]; lx = I.rolling_min(L, nn)[k]
        f[f"lvl_vs_{nn}"] = np.where(s > 0, (hx - lvl), (lvl - lx)) / A      # 0 = also the longer extreme
    # compression before the break
    f["range5_atr"] = (I.rolling_max(H, 5)[k] - I.rolling_min(L, 5)[k]) / A
    f["range10_atr"] = (I.rolling_max(H, 10)[k] - I.rolling_min(L, 10)[k]) / A
    f["std10_atr"] = roll(Cc, 10, "std")[k] / A
    bbw = roll(Cc, 20, "std") / roll(Cc, 20, "mean")
    f["bbw_pctile"] = pd.Series(bbw).rolling(200, min_periods=50).rank(pct=True).to_numpy()[k]
    f["atr_pctile"] = pd.Series(a / Cc).rolling(500, min_periods=100).rank(pct=True).to_numpy()[k]
    # path into the level
    x = np.arange(20)
    sl = np.array([np.polyfit(x, Cc[kk - 19:kk + 1], 1)[0] for kk in k])
    f["slope20_atr"] = s * sl * 20 / A
    lows10 = I.rolling_min(L, 10); highs10 = I.rolling_max(H, 10)
    f["higher_lows"] = np.where(s > 0, lows10[k] - lows10[k - 10], highs10[k - 10] - highs10[k]) / A
    f["er20"] = np.abs(Cc[k] - Cc[k - 20]) / np.array([np.abs(np.diff(Cc[kk - 20:kk + 1])).sum() for kk in k])
    f["er6"] = np.abs(Cc[k] - Cc[k - 6]) / np.array([np.abs(np.diff(Cc[kk - 6:kk + 1])).sum() for kk in k])
    for nb, nm in ((1, "4h"), (6, "1d"), (18, "3d"), (42, "7d"), (84, "14d"), (180, "30d")):
        f[f"ret_{nm}_atr"] = s * (Cc[k] - Cc[k - nb]) / A
    f["last_body_atr"] = s * (Cc[k] - O[k]) / A
    f["last_closepos"] = np.where(s > 0, Cc[k] - L[k], H[k] - Cc[k]) / np.maximum(H[k] - L[k], 1e-12)
    f["last_range_atr"] = (H[k] - L[k]) / A
    up = np.sign(np.diff(Cc, prepend=Cc[0]))
    f["dir_candles_6"] = np.array([(up[kk - 5:kk + 1] * sd > 0).sum() for kk, sd in zip(k, s)])
    # oscillators (side adjusted: 70 = strong in the trade direction)
    r14 = rsi(Cc, 14); r2 = rsi(Cc, 2)
    f["rsi14_4h"] = np.where(s > 0, r14[k], 100 - r14[k]); f["rsi2_4h"] = np.where(s > 0, r2[k], 100 - r2[k])
    ad, pdi, ndi = adx(H, L, Cc)
    f["adx_4h"] = ad[k]; f["di_spread_4h"] = s * (pdi[k] - ndi[k])
    e20 = I.ema(Cc, 20); e50 = I.ema(Cc, 50); e200 = I.ema(Cc, 200)
    f["ema20_4h_dist"] = s * (Cc[k] - e20[k]) / A; f["ema50_4h_dist"] = s * (Cc[k] - e50[k]) / A
    f["ema200_4h_dist"] = s * (Cc[k] - e200[k]) / A; f["ema20_50_4h"] = s * (e20[k] - e50[k]) / A
    # volume / activity
    v20 = roll(V, 20, "mean"); v100 = roll(V, 100, "mean")
    f["vol_last"] = V[k] / v20[k]; f["vol_5_vs_100"] = roll(V, 5, "mean")[k] / v100[k]; f["vol_20_vs_100"] = v20[k] / v100[k]
    f["vol_trend"] = np.array([np.polyfit(x, V[kk - 19:kk + 1], 1)[0] for kk in k]) * 20 / v20[k]
    upv = np.where(Cc > O, V, 0); dnv = np.where(Cc < O, V, 0)
    f["vol_dir_share20"] = np.where(s > 0, roll(upv, 20, "sum")[k], roll(dnv, 20, "sum")[k]) / roll(V, 20, "sum")[k]
    f["trades_last"] = cnt[k] / roll(cnt, 20, "mean")[k]
    tsize = V / np.maximum(cnt, 1)
    f["avg_trade_size"] = roll(tsize, 5, "mean")[k] / roll(tsize, 100, "mean")[k]
    # ── daily context ──
    DH, DL, DC, DO, DV = d["h"], d["l"], d["c"], d["o"], d["v"]
    adly = I.atr(DH, DL, DC, 14); de50 = I.ema(DC, 50); de20 = I.ema(DC, 20); de200 = I.ema(DC, 200)
    Ad = adly[kd]
    f["d_ema50_dist"] = s * (DC[kd] - de50[kd]) / Ad
    f["d_ema50_slope5"] = s * (de50[kd] - de50[kd - 5]) / Ad
    f["d_ema20_50"] = s * (de20[kd] - de50[kd]) / Ad
    f["d_ema200_dist"] = s * (DC[kd] - de200[kd]) / Ad
    f["d_atr_pct"] = Ad / DC[kd] * 100
    f["d_atr_vs100"] = Ad / I.atr(DH, DL, DC, 100)[kd]
    lr = np.r_[np.nan, np.diff(np.log(DC))]
    f["d_vol7_90"] = (roll(lr, 7, "std") / roll(lr, 90, "std"))[kd]
    f["d_vol30_365"] = (roll(lr, 30, "std") / roll(lr, 365, "std"))[kd]
    f["d_prev_body"] = s * (DC[kd] - DO[kd]) / Ad
    f["d_prev_range"] = (DH[kd] - DL[kd]) / Ad
    f["d_prev_closepos"] = np.where(s > 0, DC[kd] - DL[kd], DH[kd] - DC[kd]) / np.maximum(DH[kd] - DL[kd], 1e-12)
    f["d_prev2_body"] = s * (DC[kd - 1] - DO[kd - 1]) / Ad
    inside = (DH[1:] <= DH[:-1]) & (DL[1:] >= DL[:-1]); inside = np.r_[False, inside]
    f["d_inside_5"] = roll(inside.astype(float), 5, "sum")[kd]
    f["d_rsi14"] = np.where(s > 0, rsi(DC, 14)[kd], 100 - rsi(DC, 14)[kd])
    dad, dp, dn = adx(DH, DL, DC); f["d_adx"] = dad[kd]; f["d_di_spread"] = s * (dp[kd] - dn[kd])
    for nn in (20, 55, 365):
        f[f"d_to_high{nn}"] = np.where(s > 0, I.rolling_max(DH, nn)[kd] - DC[kd], DC[kd] - I.rolling_min(DL, nn)[kd]) / Ad
    dup = np.sign(np.diff(DC, prepend=DC[0]))
    f["d_dir_days_5"] = np.array([(dup[kk - 4:kk + 1] * sd > 0).sum() for kk, sd in zip(kd, s)])
    f["d_vol_ratio"] = (roll(DV, 5, "mean") / roll(DV, 50, "mean"))[kd]
    # ── timing ──
    f["hour"] = tr.entry_time.dt.hour.to_numpy(); f["weekday"] = tr.entry_time.dt.dayofweek.to_numpy()
    f["order_hour"] = (c["t"][k] + 240) // 60 % 24
    f["month"] = tr.entry_time.dt.month.to_numpy()
    f["side"] = s
    # ── at the fill (known only when the stop triggers) ──
    f["fill_wait_h"] = (ei - c["act"][k]) / 60
    pre = np.array([m["c"][i - 1] - m["c"][max(i - 60, 0)] for i in ei]) * s / A
    f["fill_move_1h_atr"] = pre
    v1 = np.array([m["v"][max(i - 15, 0):i].mean() / max(m["v"][max(i - 1440, 0):i].mean(), 1e-9) for i in ei])
    f["fill_vol_15m"] = v1
    out = pd.DataFrame(f)
    out.insert(0, "sym", sym[:-4]); out.insert(1, "entry_time", tr.entry_time.values); out.insert(2, "exit_time", tr.exit_time.values)
    out.insert(3, "R", tr.R.values); out["k_time"] = c["t"][k]
    return out


if __name__ == "__main__":
    from multiprocessing import Pool
    with Pool(4) as p:
        parts = p.map(build, COINS)
    X = pd.concat(parts).sort_values("entry_time").reset_index(drop=True)
    # ── cross-coin context (only information from before the entry) ──
    btc = parts[0].copy()
    m = C.load("BTCUSDT"); d = F.resample(m, 1440); de = I.ema(d["c"], 50); ad = I.atr(d["h"], d["l"], d["c"], 14)
    t_ent = X.entry_time.values.astype("datetime64[m]").astype(np.int64)
    kd = np.searchsorted(d["t"] + 1440, t_ent, side="right") - 1
    X["btc_side_agree"] = (np.sign(d["c"][kd] - de[kd]) == X.side).astype(int)
    X["btc_ret7d"] = X.side * (d["c"][kd] - d["c"][kd - 7]) / ad[kd]
    X["btc_ema_dist"] = X.side * (d["c"][kd] - de[kd]) / ad[kd]
    et, xt, sd, sy = X.entry_time.values, X.exit_time.values, X.side.values, X.sym.values
    day = np.timedelta64(1, "D")
    X["others_open_same"] = [int(((et < e) & (xt > e) & (sd == s) & (sy != y)).sum()) for e, s, y in zip(et, sd, sy)]
    X["others_open_opp"] = [int(((et < e) & (xt > e) & (sd != s) & (sy != y)).sum()) for e, s, y in zip(et, sd, sy)]
    X["others_entered_24h"] = [int(((et < e) & (et >= e - day) & (sd == s) & (sy != y)).sum()) for e, s, y in zip(et, sd, sy)]
    # own history (only trades closed before this entry)
    prevR, last_win_days, n30, loss_streak = [], [], [], []
    for e, y in zip(et, sy):
        h = X[(X.sym == y) & (X.exit_time < e)]
        prevR.append(h.R.iloc[-1] if len(h) else np.nan)
        w = h[h.R > 0.2]
        last_win_days.append((e - w.exit_time.values[-1]) / day if len(w) else np.nan)
        n30.append(int((h.entry_time.values >= e - 30 * day).sum()))
        kk = 0
        for r in h.R.values[::-1]:
            if r < -0.2: kk += 1
            elif r > 0.2: break
        loss_streak.append(kk)
    X["prev_R"] = prevR; X["days_since_win"] = last_win_days; X["trades_30d"] = n30; X["loss_streak"] = loss_streak
    X.to_pickle(C.D.CACHE / "loser_features.pkl")
    print(X.shape); print(X.describe().T[["mean", "min", "max"]].to_string())
