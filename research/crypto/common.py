"""
Crypto (Binance USD-M futures) research helpers on top of research/engine.

Data: data/<SYM>_1m_2020_2026_part*.parquet (Binance 1m klines, UTC, last price).
Costs (per side, as a fraction of price): taker fee 0.05% + 0.01% slippage = 0.06%
(stop / market orders are taker fills). Stress test: 0.10% per side.
Funding: charged 0.01% per 8 hours held to BOTH longs and shorts (pessimistic: in practice
shorts usually receive it). Binance's API is not reachable from the research box, so the
real funding history is not used.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research"))
from engine import data as D, engine as E, indicators as I, metrics as M  # noqa: E402

FEE_SIDE = 0.0006
FUNDING_8H = 0.0001

DEV = ("2020-03-01", "2024-01-01")      # tuning period (bull 2020-21, bear 2022, recovery 2023)
HOLDOUT = ("2024-01-01", "2026-10-01")  # sealed: looked at once, at the end


def load(sym="BTCUSDT"):
    cache = D.CACHE / f"{sym}_m1.npz"
    if cache.exists():
        z = np.load(cache)
        return {k: z[k] for k in z.files}
    parts = sorted((ROOT / "data").glob(f"{sym}_1m_*_part*.parquet"))
    df = pd.concat([pd.read_parquet(p) for p in parts]).sort_index()
    df = df[~df.index.duplicated()]
    t = (df.index.values.astype("datetime64[m]").astype(np.int64))
    d = dict(t=t, o=df["open"].to_numpy(float), h=df["high"].to_numpy(float),
             l=df["low"].to_numpy(float), c=df["close"].to_numpy(float), v=df["quote_volume"].to_numpy(float))
    np.savez(cache, **d)
    return d


def run(m1, orders, fee=None, funding=None, **kw):
    fee = FEE_SIDE if fee is None else fee                  # read at call time, so a stress test can patch it
    funding = FUNDING_8H if funding is None else funding
    tr = _run(m1, orders, fee, **kw)
    hours = (tr["exit_time"] - tr["entry_time"]).dt.total_seconds() / 3600
    fund = funding * hours / 8 * tr["entry"]
    tr["R"] = tr["R"] - fund / tr["sl_dist"]
    tr["ret"] = tr["R"] * tr["sl_dist"] / tr["entry"]       # return on notional, after costs
    tr["hours"] = hours
    return tr


def _run(m1, orders, fee, **kw):
    D.COMMISSION_PER_SIDE = fee
    D.SPECS.setdefault("CRYPTO", dict(digits=2, spread=dict(typ=0.0)))
    return E.run("CRYPTO", orders, spread=np.zeros(len(m1["t"])), **kw)


def between(tr, a, b):
    return tr[(tr["entry_time"] >= a) & (tr["entry_time"] < b)]


def yearly(tr, col="R"):
    return tr.groupby(tr["entry_time"].dt.year)[col].sum().round(1)


def stats(tr, col="R"):
    s = M.summary(tr, col)
    if len(tr):
        s["avg_hold_h"] = round(tr["hours"].mean(), 1)
        s["long_R"] = round(tr.loc[tr["dir"] == 1, col].sum(), 1)
        s["short_R"] = round(tr.loc[tr["dir"] == -1, col].sum(), 1)
    return s
