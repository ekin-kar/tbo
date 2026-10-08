"""Winners vs losers: market conditions at the moment each TBO v2.1 order was placed (4 coins).
A condition is interesting only if its bad bucket is bad in 2020-23 AND 2024-26 and on most coins."""
import numpy as np, pandas as pd
import common as C, families as F
import ideas10 as X
from wf2 import V21

COINS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]


def feats(sym, btc_side=None):
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    m = C.load(sym)
    tr = C.between(F.channel_breakout(m, **V21), "2020-03-01", "2026-10-01").copy().reset_index(drop=True)
    c = F.resample(m, 240); d = F.resample(m, 1440)
    a = C.I.atr(c["h"], c["l"], c["c"], 14); a100 = C.I.atr(c["h"], c["l"], c["c"], 100)
    hi = C.I.rolling_max(c["h"], 20); lo = C.I.rolling_min(c["l"], 20)
    ei = X.idx(m, tr.entry_time)
    k = np.searchsorted(c["act"], ei, side="right") - 1            # the 4h close at which the order was placed
    kd = np.searchsorted(d["act"], c["act"][k], side="right") - 1  # last closed daily candle then
    e50 = C.I.ema(d["c"], 50); ad = C.I.atr(d["h"], d["l"], d["c"], 14)
    lr = pd.Series(np.r_[np.nan, np.diff(np.log(d["c"]))]); vr = (lr.rolling(7).std() / lr.rolling(90).std()).to_numpy()
    v20 = pd.Series(c["v"]).rolling(20).mean().to_numpy()
    side = tr.dir.to_numpy()
    lvl = np.where(side > 0, hi[k], lo[k])
    # candles since the breakout level was set (fresh level = recent high)
    age = np.array([20 - 1 - int(np.argmax(c["h"][kk - 19:kk + 1][::-1] == c["h"][kk - 19:kk + 1].max())) if s > 0 else
                    20 - 1 - int(np.argmax(c["l"][kk - 19:kk + 1][::-1] == c["l"][kk - 19:kk + 1].min())) for kk, s in zip(k, side)])
    f = pd.DataFrame(dict(
        hour=tr.entry_time.dt.hour, weekday=tr.entry_time.dt.dayofweek,
        atr_pct=a[k] / c["c"][k] * 100, atr_expand=a[k] / a100[k], chan_width=(hi[k] - lo[k]) / a[k],
        dist_trigger=np.abs(lvl - c["c"][k]) / a[k], level_age=age,
        ema_dist=side * (d["c"][kd] - e50[kd]) / ad[kd], ema_slope=side * (e50[kd] - e50[kd - 5]) / ad[kd],
        vol_ratio_daily=vr[kd], volume_4h=c["v"][k] / v20[k],
        move_24h=side * (c["c"][k] - c["c"][k - 6]) / a[k],
        prev_R=np.r_[np.nan, tr.R.to_numpy()[:-1]], side=side))
    if btc_side is not None:
        f["btc_agree"] = (btc_side(c["act"][k], m) == side).astype(int)
    out = pd.concat([tr[["entry_time", "R"]], f], axis=1); out["sym"] = sym[:-4]
    return out


def btc_trend_fn():
    mb = C.load("BTCUSDT"); db = F.resample(mb, 1440); e = C.I.ema(db["c"], 50)
    s = np.where((db["c"] > e) & (e > np.r_[np.full(5, np.nan), e[:-5]]), 1, np.where((db["c"] < e) & (e < np.r_[np.full(5, np.nan), e[:-5]]), -1, 0))
    tb = db["t"] + 1440
    def f(act_idx, m):
        when = m["t"][np.clip(act_idx, 0, len(m["t"]) - 1)]
        kk = np.searchsorted(tb, when, side="right") - 1
        return s[np.clip(kk, 0, None)]
    return f


if __name__ == "__main__":
    bt = btc_trend_fn()
    D = pd.concat([feats(s, bt) for s in COINS], ignore_index=True)
    D["period"] = np.where(D.entry_time < "2024-01-01", "2020-23", "2024-26")
    D.to_csv(C.ROOT / "research" / "results" / "crypto_trade_features.csv", index=False)
    print(f"{len(D)} trades; winners (R>0) {(D.R > 0).mean()*100:.0f}%; average R {D.R.mean():.2f}\n")
    print("Average R per trade by bucket (buckets from 2020-23 quintiles). 'bad' = bucket's avg R in each period, and coins where it is below that coin's average")
    res = []
    for col in [c for c in D.columns if c not in ("entry_time", "R", "sym", "period")]:
        x = D[col]
        if x.nunique() <= 7:
            q = x
        else:
            edges = D.loc[D.period == "2020-23", col].quantile([0, .2, .4, .6, .8, 1]).to_numpy().copy(); edges[0], edges[-1] = -np.inf, np.inf
            q = pd.cut(x, np.unique(edges), labels=False)
        D["_b"] = q
        tab = D.pivot_table(index="_b", columns="period", values="R", aggfunc=["mean", "count"])
        coin_avg = D.groupby("sym").R.mean()
        lines = []
        for b in tab.index:
            m0, m1 = tab[("mean", "2020-23")].get(b, np.nan), tab[("mean", "2024-26")].get(b, np.nan)
            sub = D[D._b == b]
            worse = sum(sub[sub.sym == s].R.mean() < coin_avg[s] for s in coin_avg.index)
            rng = f"{x[q == b].min():.2f}..{x[q == b].max():.2f}" if x.nunique() > 7 else str(b)
            lines.append((b, rng, m0, m1, int(tab[('count', '2020-23')].get(b, 0)), int(tab[('count', '2024-26')].get(b, 0)), worse))
            res.append(dict(feature=col, bucket=rng, R_2020_23=m0, R_2024_26=m1, coins_worse=worse))
        print(f"\n{col}:")
        for b, rng, m0, m1, n0, n1, w in lines:
            flag = "  <-- BAD in both periods" if (m0 < 0.2 and m1 < 0.2 and w >= 3) else ""
            print(f"   {rng:>16s}  2020-23 {m0:+.2f}R (n={n0:3d})   2024-26 {m1:+.2f}R (n={n1:3d})   worse on {w}/4 coins{flag}")
    pd.DataFrame(res).to_csv(C.ROOT / "research" / "results" / "crypto_trade_feature_buckets.csv", index=False)
