"""The panic sleeve in the research: hourly data, the live signal (cryptobot/panic_signal.py, same code), the exits on
hourly bars, and the bot + sleeve account in botsim (one balance; the sleeve has its own risk budget outside the cap).

Exits on hourly bars, pessimistic: in each bar the CURRENT stop is checked first, then the take-profit; a breakeven
move applies from the next bar. Costs: taker fee + slippage in and out (as the bot's backtest).
Sizing: `units` per panic EVENT (an hour in which one or more coins trigger), 1 unit = 1/6 of the ladder's BTC risk and
a 5% move = 1 R, split equally over the coins that trigger in the same hour (e.g. 3 units at the $0-1k row, BTC 6% ->
a 5% move costs 3% of the balance).
    from panic_sleeve import events, bot_with
"""
import os, sys
from pathlib import Path
import numpy as np, pandas as pd
import common as C
import botsim as B
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "cryptobot"))
import panic_signal as PS                                          # noqa: E402

EXTRA = ROOT / "data" / "extra"
COINS = B.COINS
P0 = dict(PS.DEFAULTS)
UNITS = 3.0
TAKER = 0.0005
SLIP = {"BTCUSDT": 0.0001, "ETHUSDT": 0.0001}                      # others 0.0003 (as the bot's backtest)
_H = {}


def hourly(sym, extra=EXTRA):
    """Hourly OHLC from the 1m data + open interest value (last 5-minute sample of each hour) + premium index close."""
    key = (sym, str(extra))
    if key in _H:
        return _H[key]
    cache = C.D.CACHE / f"panic_hourly_{sym}.pkl"
    if cache.exists() and str(extra) == str(EXTRA):
        df = pd.read_pickle(cache)
    else:
        m = C.load(sym); t = pd.to_datetime(m["t"], unit="m")
        df = pd.DataFrame({"o": m["o"], "h": m["h"], "l": m["l"], "c": m["c"]}, index=t).resample("1h").agg(
            {"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
        oi = pd.read_csv(Path(extra) / f"{sym}_metrics_1h.csv.gz", usecols=["create_time", "sum_open_interest_value"], parse_dates=["create_time"])
        df["oi"] = oi.set_index(oi.create_time.dt.floor("1h")).sum_open_interest_value.groupby(level=0).last().reindex(df.index)
        pr = pd.read_csv(Path(extra) / f"{sym}_premium_1h.csv.gz"); pr.index = pd.to_datetime(pr.open_ms, unit="ms")
        df["prem"] = pr.c.groupby(level=0).last().reindex(df.index)
        df = df[df.index >= "2021-11-01"]
        if str(extra) == str(EXTRA):
            df.to_pickle(cache)
    _H[key] = df
    return df


def events(coins=COINS, start="2022-01-01", end="2026-10-01", extra=EXTRA, **kw):
    """Every sleeve trade: entry at the open after the signal hour, exits as the live sleeve. One trade per coin at a time."""
    p = dict(P0, **kw); rows = []
    for s in coins:
        df = hourly(s, extra); o, h, l, c = (df[k].values for k in "ohlc")
        f = PS.features(h, l, c, df.oi.values, df.prem.values, p["window_h"])
        sig = PS.signal(f, **p); a_ = f["atr"]; H = int(p["hold_h"])
        cost = 2 * (TAKER + SLIP.get(s, 0.0003)); busy = -1
        for i in np.flatnonzero(sig):
            if i <= busy or i + H + 2 >= len(o):
                continue
            e = o[i + 1]; a = a_[i]; st = max(e - p["stop_atr"] * a, e * (1 - p["stop_max"])); tg = e + p["tp_atr"] * a if p["tp_atr"] > 0 else np.inf; best = e
            px, j, why = o[i + 1 + H], i + 1 + H, "time"
            for jj in range(i + 1, i + 1 + H):
                if l[jj] <= st:
                    px, j, why = st, jj, ("stop" if st < e else "breakeven"); break
                if h[jj] >= tg:
                    px, j, why = tg, jj, "take profit"; break
                best = max(best, h[jj])
                if p["be_atr"] > 0 and best >= e + p["be_atr"] * a:
                    st = max(st, e)
            L = int(p["window_h"])
            rows.append((df.index[i + 1], df.index[j], s, e, px, a, px / e - 1 - cost, why, c[i] / c[i - L] - 1, f["rz"][i], f["doi"][i], f["pz"][i]))
            busy = j
    ev = pd.DataFrame(rows, columns=["t", "t_exit", "sym", "entry", "exit", "atr", "ret", "why", "move", "rz", "doi", "pz"])
    ev = ev[(ev.t >= start) & (ev.t < end)].sort_values(["t", "sym"]).reset_index(drop=True)
    ev["n"] = ev.groupby("t").ret.transform("size")
    return ev


def sleeve_rows(ev):
    """botsim rows (entry, exit, be, dir, R, coin=5): R = return / 5% split over the event's coins; be = entry so the
    sleeve never takes room under the bot's open-risk cap."""
    m = lambda s: s.values.astype("datetime64[m]").astype(np.int64)
    return np.c_[m(ev.t), m(ev.t_exit), m(ev.t), np.ones(len(ev)), ev.ret.values / 0.05 / ev.n.values, np.full(len(ev), 5)]


def policy(units=UNITS, pol=None):
    p = pol or B.bot_policy()
    return dict(p, rows=[(f, rk + [rk[0] * units / 6], cap) for f, rk, cap in p["rows"]], exempt=set(p["exempt"]) | {5})


def combined_TR(ev):
    X = np.r_[B.TR, sleeve_rows(ev)] if len(ev) else B.TR.copy()
    return X[np.lexsort((X[:, 5], X[:, 0]))]


def run(a="2022-01-01", b="2026-10-01", ev=None, units=UNITS, eq0=300.0, keep=None):
    """The bot alone (ev None) or bot + sleeve from eq0 between a and b; botsim result dict."""
    X = combined_TR(ev) if ev is not None else B.TR
    pol = policy(units) if ev is not None else B.bot_policy()
    t0, t1 = pd.Timestamp(a).value // 60_000_000_000, pd.Timestamp(b).value // 60_000_000_000
    x = X[(X[:, 0] >= t0) & (X[:, 0] < t1)].copy(); x[:, :3] -= t0
    return B.run(x, pol, eq0, keep=keep)


if __name__ == "__main__":
    ev = events()
    for a in ("2022-01-01", "2024-01-01"):
        r0, r1 = run(a), run(a, ev=ev)
        print(f"from {a[:4]}: bot ${r0['final']:,.0f} drop {r0['dd']:.1f}% | bot + sleeve ${r1['final']:,.0f} drop {r1['dd']:.1f}%")
    w, lo = ev.ret[ev.ret > 0], ev.ret[ev.ret <= 0]
    print(f"{len(ev)} sleeve trades on {ev.t.nunique()} events: win {len(w)/len(ev)*100:.0f}%, avg win {w.mean()*100:+.2f}%, "
          f"avg loss {lo.mean()*100:+.2f}%, profit factor {w.sum()/-lo.sum():.2f}; exits {ev.why.value_counts().to_dict()}")
