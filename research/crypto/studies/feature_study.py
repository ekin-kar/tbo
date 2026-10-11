"""
What predicts BTC / ETH over the next 1 and 3 days? Daily decision at 00:00 UTC (features from closed daily
candles only). Forward returns are vol-normalised (divided by the 20-day st.dev) and DE-MEANED per coin and
period, so a bull market does not make every 'long' bucket look good.
A feature counts as robust only if its top-vs-bottom quintile spread has the SAME sign on BTC and ETH in
BOTH dev halves (2020-03..2021, 2022..2023). 2024-26 is not looked at here.
"""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
from pathlib import Path
import numpy as np, pandas as pd
import common as C

ROOT = Path(__file__).resolve().parents[3]


def daily(sym):
    parts = sorted((ROOT / "data").glob(f"{sym}_1m_*_part*.parquet"))
    df = pd.concat([pd.read_parquet(p) for p in parts]).sort_index()
    df = df[~df.index.duplicated()]
    d = df.resample("1D").agg(dict(open="first", high="max", low="min", close="last", volume="sum",
                                   quote_volume="sum", count="sum"))
    return d.dropna()


def features(d):
    f = pd.DataFrame(index=d.index)
    c, h, l, o = d.close, d.high, d.low, d.open
    lr = np.log(c).diff()
    sd20 = lr.rolling(20).std()
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()
    for n in (1, 3, 7, 14, 30, 90):
        f[f"ret_{n}d"] = np.log(c / c.shift(n)) / (sd20 * np.sqrt(n))
    for n in (20, 50, 200):
        e = c.ewm(span=n, adjust=False).mean()
        f[f"dist_ema{n}"] = (c - e) / atr
    e50 = c.ewm(span=50, adjust=False).mean()
    f["slope_ema50"] = (e50 - e50.shift(5)) / atr
    f["vol_ratio_7_90"] = lr.rolling(7).std() / lr.rolling(90).std()
    f["vol_level_90d_pct"] = sd20.rolling(365, min_periods=120).rank(pct=True)
    f["range_pos_20d"] = (c - l.rolling(20).min()) / (h.rolling(20).max() - l.rolling(20).min())
    f["dd_from_90d_high"] = c / h.rolling(90).max() - 1
    f["dd_from_365d_high"] = c / h.rolling(365, min_periods=120).max() - 1
    f["volume_3_30"] = d.quote_volume.rolling(3).mean() / d.quote_volume.rolling(30).mean()
    f["trades_3_30"] = d["count"].rolling(3).mean() / d["count"].rolling(30).mean()
    ats = d.quote_volume / d["count"]                       # average trade size in USDT (whales vs retail)
    f["avg_trade_size_7_60"] = ats.rolling(7).mean() / ats.rolling(60).mean()
    f["close_loc_1d"] = (c - l) / (h - l)                   # 1 = closed at the high
    f["upper_wick_1d"] = (h - np.maximum(o, c)) / (h - l)
    f["lower_wick_1d"] = (np.minimum(o, c) - l) / (h - l)
    up = (c > o).astype(int)
    streak = up.groupby((up != up.shift()).cumsum()).cumcount() + 1
    f["streak_signed"] = np.where(up == 1, streak, -streak)
    f["range_1d_vs_atr"] = (h - l) / atr
    f["weekday"] = d.index.dayofweek                        # of the candle that just closed
    # forward returns from the decision moment (= this candle's close)
    out = {}
    for H in (1, 3):
        out[f"fwd{H}"] = np.log(c.shift(-H) / c) / (sd20 * np.sqrt(H))
    return f, pd.DataFrame(out, index=d.index), sd20


PERIODS = {"A 2020-21": ("2020-03-01", "2022-01-01"), "B 2022-23": ("2022-01-01", "2024-01-01")}

if __name__ == "__main__":
    res = []
    data = {}
    for sym in ("BTCUSDT", "ETHUSDT"):
        d = daily(sym); f, y, sd = features(d); data[sym] = (d, f, y)
    for feat in data["BTCUSDT"][1].columns:
        row = dict(feature=feat)
        for H in (1, 3):
            spreads = []
            for sym, (d, f, y) in data.items():
                dev = f.loc[C.DEV[0]:C.DEV[1]][feat]
                if feat == "weekday":
                    edges = None
                else:
                    edges = dev.quantile([0, .2, .4, .6, .8, 1]).to_numpy().copy(); edges[0], edges[-1] = -np.inf, np.inf
                for pn, (a, b) in PERIODS.items():
                    x = f.loc[a:b, feat]; t = y.loc[a:b, f"fwd{H}"]; t = t - t.mean()
                    if edges is None:
                        g = t.groupby(x).mean(); sp = g.loc[[5, 6]].mean() - g.loc[[0, 1, 2, 3, 4]].mean()
                    else:
                        q = pd.cut(x, edges, labels=False)
                        g = t.groupby(q).mean(); sp = g.get(4, np.nan) - g.get(0, np.nan)
                    spreads.append(sp)
                    row[f"{sym[:3]} {pn} H{H}"] = round(sp, 3)
            spreads = list(np.nan_to_num(spreads)); s = np.sign(spreads)
            row[f"H{H}_agree"] = int(abs(s.sum()))           # 4 = same sign everywhere
            row[f"H{H}_min_abs"] = round(np.min(np.abs(spreads)) * np.sign(np.sum(spreads)), 3)
        res.append(row)
    df = pd.DataFrame(res)
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 30)
    df.to_csv(ROOT / "research" / "results" / "crypto_feature_study_dev.csv", index=False)
    cols = ["feature"] + [c for c in df.columns if "H1" in c and "agree" not in c and "min" not in c] + ["H1_agree", "H1_min_abs"]
    print("TOP-minus-BOTTOM quintile, next-1-day return in daily st.devs (de-meaned). agree=4 -> same sign on BTC+ETH in both halves")
    print(df[cols].sort_values("H1_min_abs", key=abs, ascending=False).to_string(index=False))
    cols3 = ["feature"] + [c for c in df.columns if "H3" in c and "agree" not in c and "min" not in c] + ["H3_agree", "H3_min_abs"]
    print("\nsame for the next 3 days:")
    print(df[cols3].sort_values("H3_min_abs", key=abs, ascending=False).to_string(index=False))
