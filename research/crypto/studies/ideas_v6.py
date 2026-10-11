"""Coins together (Oct 2026), on top of TBO v2.4:
 A per-coin win rate / R
 B BTC confirms the alts: BTC in a trade the same way / BTC entered within 24-48 h / BTC near its own breakout level /
   BTC 4h trend; as skip filters for ETH, DOGE, ADA trades (BTC trades unchanged) and as size x1.5
 C BTC dominance proxy: BTC vs an equal-weight index of 11 alts (ETH BNB SOL XRP DOGE ADA LINK AVAX LTC TRX DOT)
 D USDT dominance proxy: trend of a 12-coin market index (USDT dominance rises when the market falls)
Choose on 2020-23, judge on 2024-26, random skips as the luck level."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
import tradesim as T
from ideas_v4 import v24, acct

I = C.I
ALL12 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT", "TRXUSDT", "DOTUSDT"]


def daily(sym):
    m = C.load(sym); d = F.resample(m, 1440)
    return sym, pd.Series(d["c"], index=pd.to_datetime(d["t"] * 60, unit="s"))


def btc4h():
    m = C.load("BTCUSDT"); c = F.resample(m, 240)
    a = I.atr(c["h"], c["l"], c["c"], 14)
    return dict(t=c["t"], c=c["c"], hi=I.rolling_max(c["h"], 20), lo=I.rolling_min(c["l"], 20), a=a, e50=I.ema(c["c"], 50))


if __name__ == "__main__":
    with Pool(4) as p:
        base = dict(p.map(v24, T.COINS))
        dly = dict(p.map(daily, ALL12))
    X = pd.concat(base.values()).sort_values("entry_time").reset_index(drop=True)
    R = X.R.to_numpy(); W = X.sym.map(T.WT).to_numpy() * np.where(X.dir < 0, 0.5, 1)
    EXT = X.exit_time.values.astype("datetime64[m]").astype(np.int64)
    ET = X.entry_time; s = X.dir.to_numpy()
    DEV = ((ET >= "2020-03-01") & (ET < "2024-01-01")).to_numpy(); HO = (ET >= "2024-01-01").to_numpy()
    alt = (X.sym != "BTCUSDT").to_numpy()

    print("=== A: per coin (v2.4, 2020-26) ===")
    for sym in T.COINS:
        x = X[X.sym == sym]
        print(f"  {sym[:-4]:5s} trades {len(x):4d}  win (>+0.2R) {(x.R > .2).mean()*100:4.1f}%  avg R {x.R.mean():+.3f}  "
              f"2020-23 {x[x.entry_time < '2024'].R.mean():+.3f}  2024-26 {x[x.entry_time >= '2024'].R.mean():+.3f}  biggest {x.R.max():.1f}R")

    # ── B: BTC confirmation features for every trade (only used on alt trades) ──
    bt = X[X.sym == "BTCUSDT"]
    be, bx, bd = bt.entry_time.values, bt.exit_time.values, bt.dir.values
    e = X.entry_time.values
    btc_open_same = np.array([((be < t) & (bx > t) & (bd == d)).any() for t, d in zip(e, s)])
    btc_open_opp = np.array([((be < t) & (bx > t) & (bd != d)).any() for t, d in zip(e, s)])
    h24, h48 = np.timedelta64(24, "h"), np.timedelta64(48, "h")
    btc_in24 = np.array([((be < t) & (be >= t - h24) & (bd == d)).any() for t, d in zip(e, s)])
    btc_in48 = np.array([((be < t) & (be >= t - h48) & (bd == d)).any() for t, d in zip(e, s)])
    b4 = btc4h()
    om = (X.entry_time.values.astype("datetime64[m]").astype(np.int64) // 240) * 240      # order time (4h close), minutes
    kb = np.searchsorted(b4["t"] + 240, om, side="right") - 1
    btc_dist = np.where(s > 0, b4["hi"][kb] - b4["c"][kb], b4["c"][kb] - b4["lo"][kb]) / b4["a"][kb]   # ATRs to BTC's level
    btc_4h_trend = np.sign(b4["c"][kb] - b4["e50"][kb]) == s

    # ── C/D: dominance proxies from daily closes ──
    px = pd.DataFrame(dly).sort_index()
    lr = np.log(px).diff()
    alt_idx = lr.drop(columns="BTCUSDT").mean(axis=1, skipna=True).cumsum()          # equal-weight alt index (log)
    mkt_idx = lr.mean(axis=1, skipna=True).cumsum()                                  # 12-coin market index (log)
    dom = np.log(px.BTCUSDT) - alt_idx                                               # log BTC / alts
    mkt_ema = pd.Series(I.ema(np.exp(mkt_idx.fillna(0).to_numpy()), 50), index=mkt_idx.index)
    day = pd.to_datetime(om * 60, unit="s").floor("D") - pd.Timedelta(days=1)        # last closed day
    g = lambda ser, lag=0: ser.shift(lag).reindex(day).to_numpy()
    dom7 = g(dom) - g(dom, 7); dom30 = g(dom) - g(dom, 30)
    mkt_up = np.exp(g(mkt_idx)) > g(mkt_ema)
    mkt_rising = g(mkt_ema) > g(mkt_ema, 5)
    mkt_side = np.where(mkt_up & mkt_rising, 1, np.where(~mkt_up & ~mkt_rising, -1, 0))
    mkt7 = g(mkt_idx) - g(mkt_idx, 7)

    bd_ = acct(R, W, EXT, DEV)[2]; bh_ = acct(R, W, EXT, HO)[2]
    rng = np.random.default_rng(21)

    def show(title, rules, mode="skip"):
        print(f"\n=== {title} ({'skip where' if mode == 'skip' else 'size x1.5 where'}); base net/DD 2020-23 {bd_:.2f}, 2024-26 {bh_:.2f} ===")
        res = []
        for nm, msk in rules:
            msk = np.asarray(msk, bool)
            w = W * np.where(msk, 0.0 if mode == "skip" else 1.5, 1.0)
            d = acct(R, w, EXT, DEV)[2] / bd_; h = acct(R, w, EXT, HO)[2] / bh_
            sh = msk[DEV].mean()
            lk = []
            for _ in range(150):
                rm = rng.random(len(X)) < sh
                w2 = W * np.where(rm, 0.0 if mode == "skip" else 1.5, 1.0)
                lk.append((acct(R, w2, EXT, DEV)[2] / bd_, acct(R, w2, EXT, HO)[2] / bh_))
            lk = np.array(lk)
            res.append((nm, sh, d, h, np.percentile(lk[:, 0], 90), np.percentile(lk[:, 1], 90),
                        np.mean(np.clip(R[msk], None, 10)), np.mean(np.clip(R[~msk & (alt if 'alt' in nm else True)], None, 10))))
        for r in res:
            flag = "  <-- beats random in both" if r[2] > max(1.05, r[4]) and r[3] > max(1.05, r[5]) else ""
            print(f"  {r[0][:58]:58s} share {r[1]*100:3.0f}%  2020-23 x{r[2]:.2f} (rnd90 x{r[4]:.2f})  2024-26 x{r[3]:.2f} (rnd90 x{r[5]:.2f})  avg R matched {r[6]:+.2f}{flag}")

    show("B: BTC confirms the alts", [
        ("alt trade while BTC NOT in a same-direction trade", alt & ~btc_open_same),
        ("alt trade while BTC in an opposite trade", alt & btc_open_opp),
        ("alt trade, BTC did not enter same way within 24h", alt & ~btc_in24),
        ("alt trade, BTC did not enter same way within 48h", alt & ~btc_in48),
        ("alt trade, BTC > 1 ATR from its own level", alt & (btc_dist > 1.0) & ~btc_open_same),
        ("alt trade, BTC > 2 ATR from its own level", alt & (btc_dist > 2.0) & ~btc_open_same),
        ("alt trade, BTC 4h trend against", alt & ~btc_4h_trend),
    ])
    show("B: BTC confirms the alts", [
        ("alt trade while BTC in a same-direction trade", alt & btc_open_same),
        ("alt trade, BTC entered same way within 24h", alt & btc_in24),
        ("alt trade, BTC within 1 ATR of its level or beyond", alt & ((btc_dist <= 1.0) | btc_open_same)),
    ], mode="size")
    q = lambda v, p: np.nanquantile(v[DEV], p)
    show("C: BTC dominance proxy (BTC vs 11 alts)", [
        ("alt long while BTC dominance rose >q67 over 30d", alt & (s > 0) & (dom30 >= q(dom30, .67))),
        ("alt long while BTC dominance rose >q67 over 7d", alt & (s > 0) & (dom7 >= q(dom7, .67))),
        ("alt short while BTC dominance fell <q33 over 30d", alt & (s < 0) & (dom30 <= q(dom30, .33))),
        ("BTC long while dominance fell <q33 over 30d", ~alt & (s > 0) & (dom30 <= q(dom30, .33))),
        ("alt trade whenever dominance 30d against the alt side", alt & (s * -dom30 < 0)),
        ("BTC trade whenever dominance 30d against BTC side", ~alt & (s * dom30 < 0)),
    ])
    show("D: USDT dominance proxy (12-coin market trend)", [
        ("long while the market index trend is not up", (s > 0) & (mkt_side != 1)),
        ("short while the market index trend is not down", (s < 0) & (mkt_side != -1)),
        ("any trade against the market index trend", s * mkt_side < 0),
        ("long while market fell >q33 last 7d", (s > 0) & (mkt7 <= q(mkt7, .33))),
        ("short while market rose >q67 last 7d", (s < 0) & (mkt7 >= q(mkt7, .67))),
    ])
