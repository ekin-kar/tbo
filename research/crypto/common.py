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


TAKER, MAKER, SLIP = 0.0005, 0.0002, 0.0001   # Binance standard fees; slippage on taker fills only


def run(m1, orders, fee=None, funding=None, entry="taker", tp="taker", pad=0.0001, **kw):
    """
    fee: legacy flat per-side cost for every fill (TBO research). If None, the fee model is used:
      entry="taker" (market / stop) -> TAKER + SLIP, entry="maker" (limit) -> MAKER;
      take profit: tp="maker" (resting limit) -> MAKER, else TAKER + SLIP; all other exits TAKER + SLIP.
    pad: a limit order fills only if price trades through it by pad x price (queue pessimism).
    """
    from xengine import _simulate
    funding = FUNDING_8H if funding is None else funding
    n = len(m1["t"])
    bad = (orders.kind != 0) & ~(orders.sl > 0)
    orders.kind[bad] = 0
    res = _simulate(m1["t"], m1["o"], m1["h"], m1["l"], m1["c"],
                    orders.kind, orders.direction, orders.price, orders.sl, np.nan_to_num(orders.tp),
                    orders.expiry, orders.allow_entry, orders.allow_fill, orders.force_exit, orders.exit_long,
                    orders.exit_short, D.day_index(m1["t"]), kw.get("max_trades_day", 0), kw.get("max_bars", 0),
                    np.zeros(n), m1["o"] * pad, kw.get("group_size", 0), kw.get("miss_if_crossed", False),
                    kw.get("be_R", 0.0), kw.get("be_off", 0.0), kw.get("trail_k", 0.0), kw.get("trail_start", 0.0),
                    kw.get("early_bars", 0), kw.get("early_R", 0.0), kw.get("ext_bars", 0), kw.get("ext_R", 0.0),
                    kw.get("trail_after", 0), kw.get("lock_R", 0.0), kw.get("lock_to", 0.0))
    e_idx, x_idx, dirs, e_px, x_px, dist, reason = res
    tr = pd.DataFrame({"entry_time": D.to_datetime(m1["t"][e_idx]), "exit_time": D.to_datetime(m1["t"][x_idx]),
                       "dir": dirs, "entry": e_px, "exit": x_px, "sl_dist": dist,
                       "reason": [E.REASONS[r] for r in reason]})
    if fee is not None:
        f_in = f_out = np.full(len(tr), fee)
    else:
        f_in = np.full(len(tr), MAKER if entry == "maker" else TAKER + SLIP)
        is_tp = tr["reason"].to_numpy() == "TP"
        f_out = np.where(is_tp & (tp == "maker"), MAKER, TAKER + SLIP)
    gross = (tr["exit"] - tr["entry"]) * tr["dir"]
    hours = (tr["exit_time"] - tr["entry_time"]).dt.total_seconds() / 3600
    cost = f_in * tr["entry"] + f_out * tr["exit"] + funding * hours / 8 * tr["entry"]
    tr["R_gross"] = gross / tr["sl_dist"]
    tr["R"] = (gross - cost) / tr["sl_dist"]
    tr["ret"] = tr["R"] * tr["sl_dist"] / tr["entry"]
    tr["hours"] = hours
    return tr


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
