"""Market-neutral cross-sectional strategies on 12 Binance USD-M coins (Oct 2026).
Every H days at 00:00 UTC rank the coins on a signal; long the top N, short the bottom N, equal weights,
long leg = short leg = 0.5 x capital (gross 1x). Daily P&L = price returns, funding (longs pay / shorts receive
positive funding), taker fee 0.05% + slippage (0.01% BTC/ETH, 0.03% others) on every change of weight.
Signals are chosen on 2020-23 (open interest: 2022-23), judged on 2024-26."""
import itertools
import numpy as np, pandas as pd
import common as C

EX = C.ROOT / "data" / "extra"
SYMS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT", "TRXUSDT", "DOTUSDT"]
COST = pd.Series({s: 0.0005 + (0.0001 if s in ("BTCUSDT", "ETHUSDT") else 0.0003) for s in SYMS})


def panel():
    close, qv, tb, fund, prem, oi = {}, {}, {}, {}, {}, {}
    for s in SYMS:
        k = pd.read_csv(EX / f"{s}_4h.csv.gz"); k.index = pd.to_datetime(k.open_ms, unit="ms")
        d = k.resample("1D").agg(dict(c="last", quote_volume="sum", taker_buy_quote="sum"))
        close[s] = d.c; qv[s] = d.quote_volume; tb[s] = d.taker_buy_quote / d.quote_volume
        f = pd.read_csv(EX / f"{s}_funding.csv.gz"); f.index = pd.to_datetime(f.time_ms, unit="ms")
        fund[s] = f.rate.resample("1D").sum()
        p = pd.read_csv(EX / f"{s}_premium_1h.csv.gz").drop_duplicates("open_ms"); p.index = pd.to_datetime(p.open_ms, unit="ms")
        prem[s] = p.c.resample("1D").mean()
        g = pd.read_csv(EX / f"{s}_metrics_1h.csv.gz", usecols=["create_time", "sum_open_interest_value"])
        g.index = pd.to_datetime(g.create_time); v = g.sum_open_interest_value.where(g.sum_open_interest_value > 0)
        oi[s] = v.resample("1D").last().ffill()
    D = {n: pd.DataFrame(x).sort_index().loc["2020-01-01":"2026-09-30"] for n, x in
         dict(close=close, qv=qv, tb=tb, fund=fund, prem=prem, oi=oi).items()}
    D["fund"] = D["fund"].reindex(D["close"].index).fillna(0.0)
    return D


def signals(D):
    c = D["close"]; r = np.log(c).diff()
    S = {}
    for L in (3, 7, 14, 30, 60, 90):
        S[f"mom{L}"] = np.log(c / c.shift(L))
        S[f"mom{L}skip1"] = np.log(c.shift(1) / c.shift(L))
    S["rev1"] = -r; S["rev3"] = -np.log(c / c.shift(3))
    for L in (3, 7, 14):
        S[f"carry{L}"] = -D["fund"].rolling(L).mean()               # long low / negative funding, short high funding
    S["lowvol30"] = -r.rolling(30).std(); S["lowvol90"] = -r.rolling(90).std()
    S["prem3"] = -D["prem"].rolling(3).mean()
    S["oi7_up"] = D["oi"] / D["oi"].shift(7) - 1; S["oi7_down"] = -S["oi7_up"]
    S["taker7"] = D["tb"].rolling(7).mean()
    S["mom30_volnorm"] = S["mom30"] / r.rolling(30).std()
    return S, r


def backtest(sig, r, fund, n=3, hold=1, gross=1.0, start="2020-04-01", end="2026-10-01"):
    """sig, r, fund: date x coin. Weights decided with data up to day t, earn day t+1."""
    rk = sig.rank(axis=1, ascending=False)
    cnt = sig.notna().sum(axis=1)
    w = pd.DataFrame(0.0, index=sig.index, columns=sig.columns)
    long_ = rk.le(n); short_ = rk.gt(cnt.values[:, None] - n) & sig.notna()
    w[long_] = 0.5 * gross / n; w[short_] = -0.5 * gross / n
    w[cnt < 2 * n + 1] = 0.0                                    # not enough coins listed
    if hold > 1:                                                # rebalance only every `hold` days
        keep = np.arange(len(w)) % hold == 0
        w = w.where(pd.Series(keep, index=w.index), np.nan).ffill().fillna(0.0)
    wy = w.shift(1).fillna(0.0)                                 # held during the next day
    ret = (wy * (np.exp(r.fillna(0.0)) - 1)).sum(axis=1)
    fpay = (wy * fund).sum(axis=1)                              # positive funding: longs pay, shorts receive
    turn = (w - w.shift(1).fillna(0.0)).abs().mul(COST, axis=1).sum(axis=1).shift(1).fillna(0.0)
    pnl = (ret - fpay - turn).loc[start:end]
    return pnl, (ret - fpay).loc[start:end], wy.loc[start:end]


def stats(p):
    if len(p) < 30 or p.std() == 0:
        return dict(ann=np.nan, sharpe=np.nan, dd=np.nan, pos_m=np.nan)
    eq = (1 + p).cumprod(); dd = (1 - eq / eq.cummax()).max()
    m = (1 + p).resample("ME").prod() - 1
    return dict(ann=(eq.iloc[-1] ** (365 / len(p)) - 1) * 100, sharpe=p.mean() / p.std() * np.sqrt(365), dd=dd * 100, pos_m=(m > 0).mean() * 100)


if __name__ == "__main__":
    D = panel(); S, r = signals(D)
    rows = []
    for name, sig in S.items():
        dev_start = "2022-02-01" if name.startswith("oi") else "2020-04-01"
        for n, hold in itertools.product((2, 3, 4), (1, 3, 7)):
            p, pg, _ = backtest(sig, r, D["fund"], n=n, hold=hold)
            d = stats(p.loc[dev_start:"2023-12-31"]); h = stats(p.loc["2024-01-01":])
            rows.append(dict(signal=name, n=n, hold=hold, dev_sh=d["sharpe"], dev_ann=d["ann"], dev_dd=d["dd"],
                             ho_sh=h["sharpe"], ho_ann=h["ann"], ho_dd=h["dd"], ho_pos=h["pos_m"],
                             gross_ho_sh=stats(pg.loc["2024-01-01":])["sharpe"]))
    R = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print("=== per signal: setting with the best 2020-23 Sharpe, and how it did 2024-26 (gross 1x: 50% long, 50% short) ===")
    best = R.loc[R.groupby("signal").dev_sh.idxmax()].sort_values("dev_sh", ascending=False)
    print(best.round(2).to_string(index=False))
    print("\nmedian over all 9 settings per signal (less cherry-picked):")
    print(R.groupby("signal")[["dev_sh", "ho_sh"]].median().sort_values("dev_sh", ascending=False).round(2).T.to_string())
    R.to_pickle(C.D.CACHE / "mn_study.pkl")
