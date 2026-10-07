"""Ideas 6 (positioning: funding, open interest, long/short ratios) and 7 (aggressive buyers vs sellers) as filters on the
TBO trades. Data: data/extra (fetch_binance_extra.py). Everything is read strictly before the order time (the 4h close).
Funding and taker volume exist from 2020 (dev 2020-23); open interest / ratios from Dec 2021 (dev 2022-23)."""
import numpy as np, pandas as pd
import common as C
import loser_eval as L

EX = C.ROOT / "data" / "extra"


def extra_features(X):
    t_order = (X.k_time.to_numpy() + 240).astype(np.int64)        # minutes since epoch, the 4h close
    s = X.side.to_numpy()
    out = pd.DataFrame(index=X.index)
    for sym in X.sym.unique():
        m = (X.sym == sym).to_numpy(); S = sym + "USDT"; to = t_order[m]; sd = s[m]
        # ── 7: taker buy share from 4h candles ──
        k = pd.read_csv(EX / f"{S}_4h.csv.gz")
        kt = (k.open_ms // 60000).to_numpy()
        share = (k.taker_buy_quote / k.quote_volume).to_numpy()
        delta = (2 * k.taker_buy_quote - k.quote_volume).to_numpy()
        qv = k.quote_volume.to_numpy()
        i = np.searchsorted(kt + 240, to, side="right") - 1          # last candle closed by the order time
        r = lambda x, n: pd.Series(x).rolling(n).mean().to_numpy()
        sh_s = lambda v: np.where(sd > 0, v, 1 - v)                    # share of aggressive orders in our direction
        out.loc[m, "tb_last"] = sh_s(share[i]); out.loc[m, "tb_6"] = sh_s(r(share, 6)[i]); out.loc[m, "tb_20"] = sh_s(r(share, 20)[i])
        out.loc[m, "tb_last_vs_20"] = out.loc[m, "tb_last"].to_numpy() - out.loc[m, "tb_20"].to_numpy()
        cd20 = pd.Series(delta).rolling(20).sum().to_numpy() / pd.Series(qv).rolling(20).sum().to_numpy()
        cd6 = pd.Series(delta).rolling(6).sum().to_numpy() / pd.Series(qv).rolling(6).sum().to_numpy()
        out.loc[m, "cvd_20"] = sd * cd20[i]; out.loc[m, "cvd_6"] = sd * cd6[i]
        # price up but buyers not pushing = divergence
        ret6 = sd * (k.c.to_numpy()[i] / k.c.to_numpy()[i - 6] - 1)
        out.loc[m, "cvd6_minus_ret"] = sd * cd6[i] - np.sign(ret6) * 0.01
        # ── 6a: funding (paid every 8h; positive = longs pay) ──
        f = pd.read_csv(EX / f"{S}_funding.csv.gz"); ft = (f.time_ms // 60000).to_numpy(); fr = f.rate.to_numpy()
        j = np.searchsorted(ft, to, side="right") - 1
        out.loc[m, "fund_last"] = sd * fr[j]                           # + = traders on our side are paying (crowded)
        out.loc[m, "fund_3d"] = sd * r(fr, 9)[j]; out.loc[m, "fund_7d"] = sd * r(fr, 21)[j]
        out.loc[m, "fund_pct90"] = pd.Series(fr * 1).rolling(270, min_periods=90).rank(pct=True).to_numpy()[j]
        out.loc[m, "fund_pct90"] = np.where(sd > 0, out.loc[m, "fund_pct90"], 1 - out.loc[m, "fund_pct90"])
        # ── 6b: open interest and long/short ratios (hourly) ──
        g = pd.read_csv(EX / f"{S}_metrics_1h.csv.gz")
        gt = (pd.to_datetime(g.create_time).values.astype("datetime64[m]").astype(np.int64))
        o = np.argsort(gt); gt = gt[o]; g = g.iloc[o].reset_index(drop=True)
        num = g.columns[2:]
        g[num] = g[num].where(g[num] > 0).ffill()                       # a few rows are 0 (missing): carry the last value
        q = np.searchsorted(gt, to, side="left") - 1
        ok = (q >= 24 * 30) & (to - gt[np.clip(q, 0, None)] < 180)
        oi = g.sum_open_interest_value.to_numpy()
        def lag(h):
            return oi[np.clip(q - h, 0, None)]
        v = lambda x: np.where(ok, x, np.nan)
        out.loc[m, "oi_chg_4h"] = v(oi[q] / lag(4) - 1); out.loc[m, "oi_chg_24h"] = v(oi[q] / lag(24) - 1)
        out.loc[m, "oi_chg_7d"] = v(oi[q] / lag(168) - 1)
        out.loc[m, "oi_vs_30d"] = v(oi[q] / pd.Series(oi).rolling(720).mean().to_numpy()[q])
        for col, nm in (("count_toptrader_long_short_ratio", "top_accounts_ls"), ("sum_toptrader_long_short_ratio", "top_positions_ls"),
                        ("count_long_short_ratio", "all_accounts_ls"), ("sum_taker_long_short_vol_ratio", "taker_ls_5m")):
            x = np.log(g[col].to_numpy().astype(float))
            out.loc[m, nm] = v(sd * x[q])                             # + = crowd leaning our way
            out.loc[m, nm + "_chg24h"] = v(sd * (x[q] - x[np.clip(q - 24, 0, None)]))
    return out


if __name__ == "__main__":
    X = L.X
    E = extra_features(X)
    for c in E.columns:
        L.X[c] = E[c].to_numpy()
    print(E.describe().T[["count", "mean", "min", "max"]].round(4).to_string())
    BASE = L.BASE
    rng = np.random.default_rng(3)
    for group, feats, dev_from in (("7: aggressive buyers/sellers (2020-26)", [c for c in E.columns if c.startswith(("tb_", "cvd"))], "2020-03-01"),
                                   ("6a: funding (2020-26)", [c for c in E.columns if c.startswith("fund")], "2020-03-01"),
                                   ("6b: open interest + long/short ratios (2022-26)", [c for c in E.columns if c.startswith(("oi_", "top_", "all_", "taker_"))], "2022-01-01")):
        dev = L.DEV & (X.entry_time >= dev_from).to_numpy()
        bd = L.acct(np.ones(len(X), bool), dev); bh = BASE["ho"]
        print(f"\n=== {group}: base net/DD dev {bd[2]:.2f} holdout {bh[2]:.2f} ===")
        rows = []
        for f in feats:
            x = X[f].to_numpy(float); xd = x[dev & ~np.isnan(x)]
            for qq in (0.1, 0.2, 0.33):
                lo, hi = np.quantile(xd, qq), np.quantile(xd, 1 - qq)
                for nm, msk in ((f"{f} <= {lo:.4g} (low {int(qq*100)}%)", x <= lo), (f"{f} >= {hi:.4g} (high {int(qq*100)}%)", x >= hi)):
                    d = L.acct(~msk, dev); h = L.acct(~msk, L.HO)
                    rows.append((nm, msk[dev].mean(), d[2] / bd[2], h[2] / bh[2], d[0] / bd[0], h[0] / bh[0],
                                 X.R[msk & dev].clip(upper=10).mean(), X.R[~msk & dev].clip(upper=10).mean(),
                                 X.R[msk & L.HO].clip(upper=10).mean(), X.R[~msk & L.HO].clip(upper=10).mean()))
        rows.sort(key=lambda r: -min(r[2], r[3]))
        print(f"{'skip trades where':44s} share  dev x  ho x   avg R skipped/kept dev | ho")
        for r in rows[:8]:
            print(f"{r[0][:44]:44s} {r[1]*100:4.0f}% {r[2]:5.2f} {r[3]:5.2f}   {r[6]:+.2f}/{r[7]:+.2f} | {r[8]:+.2f}/{r[9]:+.2f}")
        both = sum(1 for r in rows if r[2] > 1.1 and r[3] > 1.1)
        fake = 0
        for _ in range(400):
            sh = rng.uniform(.1, .33); msk = rng.random(len(X)) < sh
            fake += (L.acct(~msk, dev)[2] / bd[2] > 1.1) and (L.acct(~msk, L.HO)[2] / bh[2] > 1.1)
        print(f"filters >10% better in BOTH periods: {both} of {len(rows)} ({both/len(rows)*100:.1f}%); random filters: {fake/4:.1f}%")
    X.to_pickle(C.D.CACHE / "loser_features_extra.pkl")
