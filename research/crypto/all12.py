"""TBO v2.4 (incl. the open-interest filter) on all 12 coins with data, each alone at 1% risk (shorts x0.5) from $200.
Slippage 0.01% BTC/ETH, 0.03% the rest. Coins listed after March 2020 start when their data starts."""
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import filter_test as FT, filter_test2 as F2, filter_test3 as F3
from portfolio import simulate

ALL12 = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT", "TRXUSDT", "DOTUSDT"]


def job(sym):
    F2.CUR["sym"] = sym
    FT.FILTERS["v24"] = F3.make("sum_open_interest_value", 72, -0.03)
    return sym, FT.job((sym, "v24"))[2]


def acct(x, a, b):
    x = x[(x.entry_time >= a) & (x.entry_time < b)]
    if len(x) < 5:
        return None
    cv, tk = simulate(x, risk=0.01, cap=99, short_mult=0.5, start=a, end=b, eq0=200.0)
    pk = cv.worst.cummax(); start = max(pd.Timestamp(a), x.entry_time.min())
    mo = (pd.Timestamp(b) - start).days / 30.44
    return cv.equity.iloc[-1], ((cv.equity.iloc[-1] / 200) ** (1 / mo) - 1) * 100, ((pk - cv.worst) / pk).max() * 100, start


if __name__ == "__main__":
    with Pool(4) as p:
        res = dict(p.map(job, ALL12))
    pd.to_pickle(res, C.D.CACHE / "all12_v24.pkl")
    rows = []
    for sym in ALL12:
        x = res[sym]
        full = acct(x, "2020-03-01", "2026-10-01"); ho = acct(x, "2024-01-01", "2026-10-01"); dv = acct(x, "2020-03-01", "2024-01-01")
        r = x.R.to_numpy(); e = np.cumsum(x.sort_values("exit_time").R.to_numpy()); ddR = np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e)
        rows.append(dict(coin=sym[:-4], since=full[3].strftime("%Y-%m"), trades=len(x), win=(r > .2).mean() * 100, avgR=r.mean(),
                         netR_20_23=x[x.entry_time < "2024"].R.sum(), netR_24_26=x[x.entry_time >= "2024"].R.sum(), ddR=ddR,
                         usd_full=full[0], mo_full=full[1], dd_full=full[2], usd_dev=dv[0] if dv else np.nan, mo_dev=dv[1] if dv else np.nan,
                         usd_ho=ho[0], mo_ho=ho[1], dd_ho=ho[2]))
    D = pd.DataFrame(rows).sort_values("mo_ho", ascending=False)
    pd.set_option("display.width", 250)
    print(D.round(2).to_string(index=False))
