"""One account trading the bot's five coins, sized exactly like cryptobot/bot.py (v2.5): each coin's risk and the
open-risk cap come from portfolio.json's risk ladder row for the current balance (or flat risks), BTC exempt from
the cap but counted, a capped trade shrunk to the room left (skipped if < cap_min_fraction fits), shorts x
short_risk_mult. The cap is checked at the fill (the bot re-sizes its waiting order every minute and trims at the fill;
cryptobot/test_cap_sim.py checks the bot against this rule). Used by every page generator (make_*.py).

Policy = dict(rows=[(from_usdt, [risk % per coin], cap %)], exempt={coin index}, minf, smult, mult)."""
import json, pickle
import numpy as np, pandas as pd
import common as C

COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
CFG = {s: json.load(open(C.ROOT / "cryptobot" / f"config_{s[:-4].lower()}.json")) for s in COINS}
PF = json.load(open(C.ROOT / "cryptobot" / "portfolio.json"))
ALL = pickle.load(open(C.D.CACHE / "portfolio_trades_v24.pkl", "rb"))
T = pd.concat([ALL[(s, 0.0003)] for s in COINS])
T = T.assign(_c=T.sym.map({s: i for i, s in enumerate(COINS)})).sort_values(["entry_time", "_c"], kind="stable").drop(columns="_c").reset_index(drop=True)
# (same-minute entries: coin order BTC, ETH, BNB, SOL, ADA, as the statistics page)
MIN = 60_000_000_000
_m = lambda col: T[col].values.astype("datetime64[m]").astype(np.int64)
TR = np.c_[_m("entry_time"), _m("exit_time"), _m("be_time"), T.dir.values, T.R.values, T.sym.map({s: i for i, s in enumerate(COINS)}).values]
MON = 30.44 * 1440
BLK = 28 * 1440


def bot_policy(pf=None):
    """The live settings: portfolio.json (ladder or flat cap) + the coin configs."""
    pf = pf or PF
    smult = CFG["BTCUSDT"].get("short_risk_mult", 1.0)
    if pf.get("risk_ladder"):
        rows = [(float(r["from_usdt"]), [float(r.get(s, CFG[s]["risk_pct"])) for s in COINS], float(r.get("cap_pct", pf.get("open_risk_cap_pct", 0))))
                for r in sorted(pf["risk_ladder"], key=lambda r: float(r["from_usdt"]))]
    else:
        rows = [(0.0, [CFG[s]["risk_pct"] for s in COINS], float(pf.get("open_risk_cap_pct", 0) or 0))]
    return dict(rows=rows, exempt={COINS.index(s) for s in pf.get("cap_exempt", [])}, minf=float(pf.get("cap_min_fraction", 0.25)),
                smult=smult, mult=1.0)


def flat_policy(btc, eth, alt, cap_x=1.1, exempt_btc=True, mult=1.0):
    """Fixed risks; cap = cap_x x the BTC risk (0 = no cap)."""
    return dict(rows=[(0.0, [btc, eth, alt, alt, alt], cap_x * btc)], exempt={0} if exempt_btc else set(), minf=0.25,
                smult=CFG["BTCUSDT"].get("short_risk_mult", 1.0), mult=mult)


def ladder_policy(rows, cap_x=1.1, exempt_btc=True, mult=1.0):
    """rows: [(from_usdt, btc, eth, alt)], cap = cap_x x that row's BTC risk."""
    return dict(rows=[(f, [b, e, a, a, a], cap_x * b) for f, b, e, a in rows], exempt={0} if exempt_btc else set(), minf=0.25,
                smult=CFG["BTCUSDT"].get("short_risk_mult", 1.0), mult=mult)


def label(pol):
    def one(r):
        return f"{r[1][0]:g} / {r[1][1]:g} / {r[1][2]:g}%"
    if len(pol["rows"]) == 1:
        return one(pol["rows"][0])
    return " → ".join((one(r) if not i else f"{one(r)} from ${r[0]:,.0f}") for i, r in enumerate(pol["rows"]))


def row_at(pol, eq):
    r = pol["rows"][0]
    for rr in pol["rows"]:
        if eq >= rr[0]:
            r = rr
    return r


def run(x, pol, eq0=200.0, end=None, deposit=0.0, levels=(), keep=None):
    """x: rows (entry, exit, be, dir, R, coin) in minutes, any time origin. deposit: added every MON minutes after the
    first trade's month start (journeys use origin 0). keep: 'events' -> (t, balance, worst) list, 'trades' -> per-trade
    amounts. Returns dict(final, dd (worst-case, %), ddc (closed, %), top, low, invested, reach{level: t}, ...)."""
    ev = []
    for i, (e, xx, be, d, R, c) in enumerate(x):
        ev += [(e, 1, i), (max(be, e + 1e-3), 0, i), (max(xx, e + 2e-3), 2, i)]
    rank = {2: 0, 0: 1, 1: 2}
    ev.sort(key=lambda z: (z[0], rank[z[1]]))
    eq = eq0; opn = {}; pk = eq0; dd = 0.0; pkc = eq0; ddc = 0.0; top = eq0; low = eq0; inv = eq0
    reach = {L: None for L in levels}; out_ev = [] if keep == "events" else None; amts = {} if keep == "trades" else None
    nxt = MON; mbal = [] if deposit or keep == "months" else None; skipped = 0
    for t, kind, i in ev:
        if end is not None and t > end:
            break
        if mbal is not None:
            while t >= nxt:
                mbal.append(eq)
                if deposit:
                    eq += deposit; inv += deposit; pk += deposit; pkc += deposit
                nxt += MON
        e, xx, be, d, R, c = x[i]; c = int(c)
        if kind == 1:
            fr, rk, cap = row_at(pol, eq)
            amt = eq * rk[c] / 100 * pol["mult"] * (pol["smult"] if d < 0 else 1.0)
            if cap > 0 and c not in pol["exempt"]:
                room = cap / 100 * pol["mult"] * eq - sum(v[0] for v in opn.values() if not v[1])
                if amt > room:
                    amt = room if room > pol["minf"] * amt else 0.0
            if amt > 0:
                opn[i] = [amt, False]
            else:
                skipped += 1
        elif kind == 0 and i in opn:
            opn[i][1] = True
        elif kind == 2 and i in opn:
            a = opn.pop(i)[0]; eq += a * R; top = max(top, eq); low = min(low, eq)
            if amts is not None:
                amts[i] = a
            for L in levels:
                if reach[L] is None and eq >= L:
                    reach[L] = t
        w = eq - sum(v[0] for v in opn.values() if not v[1])
        pk = max(pk, w); dd = max(dd, (pk - w) / pk); pkc = max(pkc, eq); ddc = max(ddc, (pkc - eq) / pkc)
        if out_ev is not None:
            out_ev.append((t, eq, w))
    if mbal is not None and end is not None:          # month ends after the last trade (deposits continue)
        while nxt < end - 1:
            mbal.append(eq)
            if deposit:
                eq += deposit; inv += deposit
            nxt += MON
    return dict(final=eq, dd=dd * 100, ddc=ddc * 100, top=top, low=low, invested=inv, reach=reach, events=out_ev, amts=amts,
                months=mbal, skipped=skipped)


def window(a, b):
    t0, t1 = pd.Timestamp(a).value // MIN, pd.Timestamp(b).value // MIN
    return TR[(TR[:, 0] >= t0) & (TR[:, 0] < t1)], t0, t1


def journey_trades(seed, a="2022-01-01", b="2026-10-01", months=24):
    """Random 4-week blocks of the real trades glued into one path starting at t=0 (blocks start on a 4h boundary)."""
    r = np.random.default_rng(seed)
    pool, t0, t1 = window(a, b)
    rows = []
    for k in range(int(np.ceil(months * MON / BLK))):
        u = t0 + r.integers(0, (t1 - BLK - t0) // 240) * 240
        s = pool[(pool[:, 0] >= u) & (pool[:, 0] < u + BLK)].copy(); s[:, :3] += k * BLK - u
        rows.append(s)
    return np.concatenate(rows)


def history(pol, a, b, eq0=200.0):
    """Real history a..b: dict with daily balance / worst-case drawdown series, the taken trades with $ results."""
    x, t0, t1 = window(a, b)
    r = run(x, pol, eq0, keep="events")
    ev = pd.DataFrame(r["events"], columns=["t", "bal", "worst"])
    ev["t"] = pd.to_datetime(ev.t * MIN)
    ev = ev.set_index("t")
    idx = pd.date_range(pd.Timestamp(a), pd.Timestamp(b) - pd.Timedelta(days=1), freq="D")
    bal = ev.bal.resample("D").last().reindex(idx).ffill().fillna(eq0)
    wst = ev.worst.resample("D").min().reindex(idx).ffill().fillna(eq0)
    ddd = (wst / np.maximum.accumulate(np.maximum(wst.values, 1e-9)) - 1) * 100
    r2 = run(x, pol, eq0, keep="trades")
    sel = T[(T.entry_time >= a) & (T.entry_time < b)].reset_index(drop=True)
    tk = sel.loc[sorted(r2["amts"])].copy()
    tk["risk_usd"] = [r2["amts"][i] for i in tk.index]; tk["pnl"] = tk.risk_usd * tk.R
    return dict(r=r, bal=bal, dd=ddd, events=ev, trades=tk)
