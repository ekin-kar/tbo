"""The panic sleeve in the research: hourly data, the live signal (cryptobot/panic_signal.py, same code), the exits on
hourly bars, and the bot + sleeve account in botsim (one balance; the sleeve has its own risk budget outside the cap).

Exits on hourly bars, pessimistic: in each bar the CURRENT stop is checked first, then the take-profit; a breakeven
move applies from the next bar. Costs: taker fee + slippage in and out (as the bot's backtest).
Sizing: `units` per panic EVENT (an hour in which one or more coins trigger), 1 unit = 1/6 of the ladder's BTC risk and
a 5% move = 1 R, split equally over the coins that trigger in the same hour (e.g. 3 units at the $0-1k row, BTC 6% ->
a 5% move costs 3% of the balance).
v3.0 (C4): the same signal and exits also on EXTRA_COINS (7 more DEV12 coins) with their own pool of extra_share x units
per event, split over the extra coins entered that hour (the 5 core coins keep their full units), and at most
max_extra_open extra-coin positions at a time; when more extra coins trigger than free slots, the largest |doi| x |pz|
first (panic.py does the same).
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
EXTRA_COINS = ["XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT"]
EXTRA_SHARE, MAX_EXTRA_OPEN = 0.75, 2                              # v3.0 live settings (cryptobot/panic.json)
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


def candidates(sym, extra=EXTRA, **kw):
    """Every signal hour of one coin with the trade it would give (no one-trade-at-a-time rule yet): bar indices i
    (signal hour), j (exit bar) and the trade fields."""
    p = dict(P0, **kw); rows = []
    df = hourly(sym, extra); o, h, l, c = (df[k].values for k in "ohlc")
    f = PS.features(h, l, c, df.oi.values, df.prem.values, p["window_h"])
    sig = PS.signal(f, **p); a_ = f["atr"]; H = int(p["hold_h"])
    cost = 2 * (TAKER + SLIP.get(sym, 0.0003)); L = int(p["window_h"])
    for i in np.flatnonzero(sig):
        if i + H + 2 >= len(o):
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
        rows.append((i, j, df.index[i + 1], df.index[j], sym, e, px, a, px / e - 1 - cost, why, c[i] / c[i - L] - 1, f["rz"][i], f["doi"][i], f["pz"][i]))
    return pd.DataFrame(rows, columns=["i", "j", "t", "t_exit", "sym", "entry", "exit", "atr", "ret", "why", "move", "rz", "doi", "pz"])


def events(coins=COINS, start="2022-01-01", end="2026-11-07", extra=EXTRA, extra_coins=EXTRA_COINS, extra_share=EXTRA_SHARE,
           max_extra_open=MAX_EXTRA_OPEN, **kw):
    """Every sleeve trade: entry at the open after the signal hour, exits as the live sleeve. One trade per coin at a time
    (a new signal counts only after the previous trade's exit bar). Core coins (`coins`) always enter; extra coins
    (`extra_coins`, v3.0 live default; () = the v2.7 sleeve) only into free slots (max_extra_open, None = no limit), ranked
    by |doi| x |pz|.
    Column w = this trade's share of `units`: 1 / (core coins entered that hour) or extra_share / (extra coins entered)."""
    cd = pd.concat([candidates(s, extra, **kw) for s in list(coins) + list(extra_coins)], ignore_index=True)
    if cd.empty:
        return cd.assign(n=[], w=[], pool=[])
    xs = set(extra_coins); busy = {}; open_x = []; out = []
    for t, g in cd.sort_values(["t", "sym"]).groupby("t", sort=True):
        open_x = [x for x in open_x if x >= t]                     # extra trades still open at this entry
        g = g[[r.i > busy.get(r.sym, -1) for r in g.itertuples()]]
        if g.empty:
            continue
        core, ext = g[~g.sym.isin(xs)], g[g.sym.isin(xs)]
        if len(ext) and max_extra_open is not None:
            free = max_extra_open - len(open_x)
            ext = ext.iloc[0:0] if free <= 0 else ext.assign(_s=-(ext.doi.abs() * ext.pz.abs())).sort_values("_s", kind="stable").head(free).drop(columns="_s")
        for part, share, pool in ((core, 1.0, "core"), (ext, extra_share, "extra")):
            if part.empty:
                continue
            for r in part.itertuples():
                busy[r.sym] = r.j
                if pool == "extra":
                    open_x.append(r.t_exit)
            out.append(part.assign(n=len(part), w=share / len(part), pool=pool))
    ev = pd.concat(out, ignore_index=True).drop(columns=["i", "j"])
    ev = ev[(ev.t >= start) & (ev.t < end)].sort_values(["t", "sym"]).reset_index(drop=True)
    return ev


def sleeve_rows(ev):
    """botsim rows (entry, exit, be, dir, R, coin=5): R = return / 5% split over the event's coins; be = entry so the
    sleeve never takes room under the bot's open-risk cap."""
    m = lambda s: s.values.astype("datetime64[m]").astype(np.int64)
    w = ev.w.values if "w" in ev else 1.0 / ev.n.values
    return np.c_[m(ev.t), m(ev.t_exit), m(ev.t), np.ones(len(ev)), ev.ret.values / 0.05 * w, np.full(len(ev), 5)]


def policy(units=UNITS, pol=None):
    """The bot's policy + this sleeve (coin 5) + the v3.1 VOLC sleeve (coin 6, botsim.VOLC_SHARE x the BTC risk)."""
    p = pol or B.bot_policy()
    return dict(p, rows=[(f, list(rk[:5]) + [rk[0] * units / 6, rk[0] * B.VOLC_SHARE], cap) for f, rk, cap in p["rows"]],
                exempt=set(p["exempt"]) | {5, 6})


def volc_rows():
    """v3.1: the VOLC sleeve's rows (coin 6) from botsim, part of 'the bot' on the panic page."""
    S = B.sleeve_rows()
    return S[S[:, 5] == 6]


def combined_TR(ev):
    X = np.r_[B.TR, volc_rows()] if ev is None or not len(ev) else np.r_[B.TR, volc_rows(), sleeve_rows(ev)]
    return X[np.lexsort((X[:, 5], X[:, 0]))]


def run(a="2022-01-01", b="2026-11-07", ev=None, units=UNITS, eq0=300.0, keep=None):
    """The bot alone (ev None) or bot + sleeve from eq0 between a and b; botsim result dict."""
    X = combined_TR(ev)                                            # v3.1: 'the bot' = TBO + the VOLC sleeve
    pol = policy(units)
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
