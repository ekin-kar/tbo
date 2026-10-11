"""5 more ideas on top of TBO v2.4 (open-interest filter), with Binance data (data/extra):
 1 exit an open trade when open interest falls during it        (OI from 2022)
 2 bigger size when open interest is rising at the breakout      (OI from 2022)
 3 spot-led vs futures-led breakouts (spot share of volume, spot buyers)   (2020+)
 4 futures premium over spot at the breakout (premium index)     (2020+)
 5 top traders vs the crowd (long/short ratios)                  (from 2022)
Account in R as before (BTC 2, ETH 1, alts 0.5, shorts x0.5). Settings / cut-offs are chosen on the first period
(2020-23, or 2022-23 where the data starts in Dec 2021) and judged on 2024-26; random filters give the luck level."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import pickle
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import tradesim as T
import filter_test2 as F2, filter_test3 as F3

EX = C.ROOT / "data" / "extra"
COINS = T.COINS
H4 = 4 * 3600_000


def v24(sym):
    """v2.4 trades with entry price / stop distance (engine, OI filter 'USD 3d <= -3%')."""
    F2.CUR["sym"] = sym
    x = T.base_trades(sym, skip_fn=F3.make("sum_open_interest_value", 72, -0.03))
    return sym, x


# ── data series ──
def metrics(sym):
    g = pd.read_csv(EX / f"{sym}_metrics_1h.csv.gz")
    t = pd.to_datetime(g.create_time).values.astype("datetime64[ms]").astype(np.int64)
    o = np.argsort(t); g = g.iloc[o].reset_index(drop=True); t = t[o]
    num = g.columns[2:]
    g[num] = g[num].where(g[num] > 0).ffill()
    return t, g


def at_before(t, ts):
    """index of the last row with time < ts (or -1)."""
    return np.searchsorted(t, ts, side="left") - 1


def features(X):
    """New measures at the order time (the 4h close before the entry), side-adjusted where directional."""
    out = []
    for sym in COINS:
        x = X[X.sym == sym]
        e_ms = x.entry_time.values.astype("datetime64[ms]").astype(np.int64)
        om = e_ms // H4 * H4                                     # order placed at this 4h close
        sd = x.dir.to_numpy().astype(float)
        f = pd.DataFrame(index=x.index)
        # spot vs futures (4h candles; the last one closed at the order time opened at om - 4h)
        fu = pd.read_csv(EX / f"{sym}_4h.csv.gz"); sp = pd.read_csv(EX / f"{sym}_spot_4h.csv.gz")
        j = fu.merge(sp, on="open_ms", suffixes=("_f", "_s"))
        jt = j.open_ms.to_numpy()
        share = (j.quote_volume_s / (j.quote_volume_s + j.quote_volume_f)).to_numpy()
        sb = (j.taker_buy_quote_s / j.quote_volume_s).to_numpy(); fb = (j.taker_buy_quote_f / j.quote_volume_f).to_numpy()
        r = lambda v, n: pd.Series(v).rolling(n, min_periods=max(2, n // 2)).mean().to_numpy()
        i = np.searchsorted(jt, om - H4)
        ok = (i < len(jt)) & (jt[np.clip(i, 0, len(jt) - 1)] == om - H4)
        i = np.clip(i, 0, len(jt) - 1)
        nan = lambda v: np.where(ok, v, np.nan)
        f["spot_share_last"] = nan(share[i]); f["spot_share_24h"] = nan(r(share, 6)[i])
        f["spot_share_vs_30d"] = nan(r(share, 6)[i] / r(share, 180)[i])
        dirs = lambda v: np.where(sd > 0, v, 1 - v)
        f["spot_buyers_last"] = nan(dirs(sb[i])); f["spot_buyers_24h"] = nan(dirs(r(sb, 6)[i]))
        f["spot_minus_fut_buyers_24h"] = nan(sd * (r(sb, 6)[i] - r(fb, 6)[i]))
        # premium index (1h): perpetual vs spot index, last closed hour before the order
        pr = pd.read_csv(EX / f"{sym}_premium_1h.csv.gz").drop_duplicates("open_ms").sort_values("open_ms")
        pt = pr.open_ms.to_numpy(); pc = pr.c.to_numpy()
        k = np.searchsorted(pt, om - 3600_000)
        okp = (k < len(pt)) & (pt[np.clip(k, 0, len(pt) - 1)] == om - 3600_000)
        k = np.clip(k, 0, len(pt) - 1)
        p24 = pd.Series(pc).rolling(24, min_periods=12).mean().to_numpy(); p30 = pd.Series(pc).rolling(720, min_periods=200).mean().to_numpy()
        pct = pd.Series(pc).rolling(720, min_periods=200).rank(pct=True).to_numpy()
        f["prem_last"] = np.where(okp, sd * pc[k], np.nan); f["prem_24h"] = np.where(okp, sd * p24[k], np.nan)
        f["prem_vs_30d"] = np.where(okp, sd * (p24[k] - p30[k]), np.nan)
        f["prem_pct30d"] = np.where(okp, np.where(sd > 0, pct[k], 1 - pct[k]), np.nan)
        # metrics: OI rising (idea 2) and top traders vs crowd (idea 5)
        mt, g = metrics(sym)
        q = at_before(mt, om)
        okm = (q >= 720) & (om - mt[np.clip(q, 0, None)] < 3 * 3600_000)
        q = np.clip(q, 0, None)
        oi = g.sum_open_interest_value.to_numpy()
        mm = lambda v: np.where(okm, v, np.nan)
        f["oi_chg_3d"] = mm(oi[q] / oi[np.clip(q - 72, 0, None)] - 1); f["oi_chg_7d"] = mm(oi[q] / oi[np.clip(q - 168, 0, None)] - 1)
        f["oi_chg_24h"] = mm(oi[q] / oi[np.clip(q - 24, 0, None)] - 1)
        lt = np.log(g.sum_toptrader_long_short_ratio.to_numpy(float)); la = np.log(g.count_long_short_ratio.to_numpy(float))
        lta = np.log(g.count_toptrader_long_short_ratio.to_numpy(float))
        f["top_pos_ls"] = mm(sd * lt[q]); f["crowd_ls"] = mm(sd * la[q]); f["top_acc_ls"] = mm(sd * lta[q])
        f["top_minus_crowd"] = mm(sd * (lt[q] - la[q]))
        f["top_pos_chg24h"] = mm(sd * (lt[q] - lt[np.clip(q - 24, 0, None)])); f["crowd_chg24h"] = mm(sd * (la[q] - la[np.clip(q - 24, 0, None)]))
        out.append(f)
    return pd.concat(out).loc[X.index]


# ── scoring (weighted R account) ──
def acct(R, w, ext, per):
    o = np.argsort(ext[per], kind="stable")
    p = (R * w)[per][o]; e = np.cumsum(p)
    dd = np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e)
    return e[-1], dd, e[-1] / dd


def oi_exit(args):
    """Idea 1: at each 4h close during a trade, exit at market if OI changed by <= thr over lb hours
    (optionally only once the trade has reached +1R)."""
    sym, X, rules = args
    m = T.data(sym); mt, g = metrics(sym); oi = g.sum_open_interest_value.to_numpy()
    res = {r: [] for r in rules}
    for row in X.itertuples():
        xi, xp, why, b = T.path(sym, row.e, row.dir, row.entry, row.sl_dist)
        R0 = T.R_of(sym, row.dir, row.entry, row.sl_dist, xi, xp, row.e)[0]
        t_e = int(m["t"][row.e]) * 60_000; t_x = int(m["t"][xi]) * 60_000
        closes = np.arange(t_e // H4 * H4 + H4, t_x, H4)
        q = at_before(mt, closes)
        for rule in rules:
            lb, thr, after1R = rule
            R = R0
            if len(closes) and t_e >= mt[0] + lb * 3600_000:
                qq = np.clip(q, lb, None)
                chg = oi[qq] / oi[qq - lb] - 1
                ok = (q >= lb) & (closes - mt[np.clip(q, 0, None)] < 3 * 3600_000) & (chg <= thr)
                if after1R:
                    ci = (closes // 60_000 - m["t"][0]).astype(np.int64)  # minute index of each close
                    ci = np.searchsorted(m["t"], closes // 60_000)
                    fav = np.array([((m["h"][row.e:c].max() - row.entry) if row.dir > 0 else (row.entry - m["l"][row.e:c].min())) if c > row.e else 0
                                    for c in ci])
                    ok &= fav >= row.sl_dist
                hit = np.flatnonzero(ok)
                if len(hit):
                    j = int(np.searchsorted(m["t"], closes[hit[0]] // 60_000))
                    if j < xi:
                        R = T.R_of(sym, row.dir, row.entry, row.sl_dist, j, m["o"][j], row.e)[0]
            res[rule].append(R)
    return sym, res


if __name__ == "__main__":
    with Pool(4) as p:
        base = dict(p.map(v24, COINS))
    X = pd.concat(base.values()).sort_values("entry_time").reset_index(drop=True)
    print("v2.4 trades per coin:", {s[:-4]: len(b) for s, b in base.items()})
    F = features(X)
    pd.to_pickle((X, F), C.D.CACHE / "ideas_v4_features.pkl")
    W = X.sym.map(T.WT).to_numpy() * np.where(X.dir < 0, 0.5, 1)
    R = X.R.to_numpy(); EXT = X.exit_time.values.astype("datetime64[m]").astype(np.int64)
    ET = X.entry_time
    P20, P22, P24, P26 = [(ET >= a).to_numpy() for a in ("2020-03-01", "2022-01-01", "2024-01-01", "2026-10-01")]
    DEV20 = P20 & ~P24; DEV22 = P22 & ~P24; HO = P24 & ~P26
    rng = np.random.default_rng(5)

    def luck(dev, n=300):
        c = 0
        for _ in range(n):
            sh = rng.uniform(.1, .33); msk = rng.random(len(X)) < sh
            c += acct(R, W * ~msk, EXT, dev)[2] / acct(R, W, EXT, dev)[2] > 1.1 and acct(R, W * ~msk, EXT, HO)[2] / acct(R, W, EXT, HO)[2] > 1.1
        return c / n * 100

    def scan(title, feats, dev, mode="skip"):
        bd = acct(R, W, EXT, dev); bh = acct(R, W, EXT, HO)
        rows = []
        for f in feats:
            x = F[f].to_numpy(float); xd = x[dev & ~np.isnan(x)]
            for qq in (0.1, 0.2, 0.33):
                lo, hi = np.quantile(xd, qq), np.quantile(xd, 1 - qq)
                for nm, msk in ((f"{f} <= {lo:.4g} (low {int(qq*100)}%)", x <= lo), (f"{f} >= {hi:.4g} (high {int(qq*100)}%)", x >= hi)):
                    w = W * np.where(msk, 0.0, 1.0) if mode == "skip" else W * np.where(msk, 1.5, 1.0)
                    d = acct(R, w, EXT, dev); h = acct(R, w, EXT, HO)
                    rows.append((nm, msk[dev].mean(), d[2] / bd[2], h[2] / bh[2], d[0] / bd[0], h[0] / bh[0],
                                 np.nanmean(np.clip(R[msk & dev], None, 10)), np.nanmean(np.clip(R[~msk & dev], None, 10)),
                                 np.nanmean(np.clip(R[msk & HO], None, 10)), np.nanmean(np.clip(R[~msk & HO], None, 10))))
        rows.sort(key=lambda r: -min(r[2], r[3]))
        print(f"\n=== {title} ({'skip trades' if mode == 'skip' else 'size x1.5'} where ...); base net/DD first period {bd[2]:.2f}, 2024-26 {bh[2]:.2f} ===")
        print(f"{'condition':46s} share first x  2024-26 x   avg R matched/other first | 2024-26")
        for r in rows[:7]:
            print(f"{r[0][:46]:46s} {r[1]*100:4.0f}%  {r[2]:5.2f}   {r[3]:5.2f}     {r[6]:+.2f}/{r[7]:+.2f} | {r[8]:+.2f}/{r[9]:+.2f}")
        both = sum(1 for r in rows if r[2] > 1.1 and r[3] > 1.1)
        print(f"conditions >10% better in BOTH periods: {both} of {len(rows)} ({both/len(rows)*100:.1f}%)" + (f"; random filters: {luck(dev):.1f}%" if mode == "skip" else ""))
        return rows

    # idea 2: size x1.5 when OI rising (and as a check: skipping)
    scan("2: open interest rising at the breakout", ["oi_chg_24h", "oi_chg_3d", "oi_chg_7d"], DEV22, mode="size")
    # idea 3, 4, 5 as filters
    scan("3: spot-led vs futures-led", [c for c in F.columns if c.startswith("spot")], DEV20)
    scan("4: futures premium", [c for c in F.columns if c.startswith("prem")], DEV20)
    scan("5: top traders vs crowd", ["top_pos_ls", "crowd_ls", "top_acc_ls", "top_minus_crowd", "top_pos_chg24h", "crowd_chg24h"], DEV22)
    scan("3+4+5 as size x1.5 (the good side)", [c for c in F.columns if c.startswith(("spot", "prem"))] +
         ["top_pos_ls", "crowd_ls", "top_minus_crowd"], DEV22, mode="size")

    # idea 1: exit on falling open interest
    rules = [(lb, thr, a) for lb, thrs in ((24, (-0.02, -0.04, -0.06)), (72, (-0.03, -0.06, -0.10))) for thr in thrs for a in (False, True)]
    with Pool(4) as p:
        out = p.map(oi_exit, [(s, base[s], rules) for s in COINS])
    by = {r: np.concatenate([dict(out)[s][r] for s in COINS]) for r in rules}
    order = np.concatenate([np.flatnonzero((X.sym == s).to_numpy()) for s in COINS])
    bd = acct(R, W, EXT, DEV22); bh = acct(R, W, EXT, HO)
    print(f"\n=== 1: exit when open interest falls during the trade (from 2022); base 2022-23 {bd[2]:.2f}, 2024-26 {bh[2]:.2f} ===")
    for r in rules:
        RR = np.empty(len(X)); RR[order] = by[r]
        d = acct(RR, W, EXT, DEV22); h = acct(RR, W, EXT, HO)
        changed = (np.abs(RR - R) > 1e-9)[P22].mean() * 100
        print(f"  OI {r[0]:3d}h <= {r[1]:+.0%}{' after +1R' if r[2] else '          '}: trades changed {changed:4.1f}%  2022-23 x{d[2]/bd[2]:.2f} (net x{d[0]/bd[0]:.2f})  "
              f"2024-26 x{h[2]/bh[2]:.2f} (net x{h[0]/bh[0]:.2f})")
