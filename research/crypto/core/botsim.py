"""One account trading the bot's five coins, sized exactly like cryptobot/bot.py (v2.5): each coin's risk and the
open-risk cap come from portfolio.json's risk ladder row for the current balance (or flat risks), BTC exempt from
the cap but counted, a capped trade shrunk to the room left (skipped if < cap_min_fraction fits), shorts x
short_risk_mult. The cap is checked at the fill (the bot re-sizes its waiting order every minute and trims at the fill;
cryptobot/dev/test_cap_sim.py checks the bot against this rule). Used by every page generator (make_*.py).

Policy = dict(rows=[(from_usdt, [risk % per coin], cap %)], exempt={coin index}, minf, smult, mult)."""
import json, pickle
import numpy as np, pandas as pd
import common as C

COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
CFG = {s: json.load(open(C.ROOT / "cryptobot" / f"config_{s[:-4].lower()}.json")) for s in COINS}
PF = json.load(open(C.ROOT / "cryptobot" / "portfolio.json"))
import os
TAG = os.environ.get("BOT_TRADES", "v32")            # v32 = live rules from 13 Nov 2026 (build_trades.py v32: v3.1 + the wild-pullback
                                                     # size, column size_mult = TR column 6); v31 = 13 Nov 2026 (v3.1) (build_trades.py v31); v30 = 6-12 Nov 2026;
                                                     # v28nov = v2.8 to 2026-11-06
ALL = pickle.load(open(C.D.CACHE / f"portfolio_trades_{TAG}.pkl", "rb"))
T = pd.concat([ALL[(s, 0.0003)] for s in COINS])
T = T.assign(_c=T.sym.map({s: i for i, s in enumerate(COINS)})).sort_values(["entry_time", "_c"], kind="stable").drop(columns="_c").reset_index(drop=True)
# (same-minute entries: coin order BTC, ETH, BNB, SOL, ADA, as the statistics page)
MIN = 60_000_000_000
_m = lambda col: T[col].values.astype("datetime64[m]").astype(np.int64)
TR = np.c_[_m("entry_time"), _m("exit_time"), _m("be_time"), T.dir.values, T.R.values, T.sym.map({s: i for i, s in enumerate(COINS)}).values,
           T.size_mult.values if "size_mult" in T else np.ones(len(T))]   # col 6: v3.2 size multiplier (1 = full size)


def cols7(a):
    """Rows with the size column (6-column sleeve rows get x 1)."""
    a = np.asarray(a, float)
    return a if a.shape[1] >= 7 else np.c_[a, np.ones(len(a))]
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
    """x: rows (entry, exit, be, dir, R, coin[, size mult]) in minutes, any time origin. The size multiplier (v3.2) scales
    the trade's risk before the open-risk cap, so the cap counts the actual risk (as bot.py). deposit: added every MON minutes after the
    first trade's month start (journeys use origin 0). keep: 'events' -> (t, balance, worst) list, 'trades' -> per-trade
    amounts. Returns dict(final, dd (worst-case, %), ddc (closed, %), top, low, invested, reach{level: t}, ...)."""
    ev = []
    for i, row in enumerate(x):
        e, xx, be = row[0], row[1], row[2]
        ev += [(e, 1, i), (max(be, e + 1e-3), 0, i), (max(xx, e + 2e-3), 2, i)]
    rank = {2: 0, 0: 1, 1: 2}
    ev.sort(key=lambda z: (z[0], rank[z[1]]))
    eq = eq0; opn = {}; pk = eq0; dd = 0.0; pkc = eq0; ddc = 0.0; top = eq0; low = eq0; inv = eq0
    reach = {L: None for L in levels}; out_ev = [] if keep == "events" else None; amts = {} if keep == "trades" else None
    full = {} if keep == "trades" else None; bal_at = {} if keep == "trades" else None
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
        e, xx, be, d, R, c = x[i][:6]; c = int(c); sm = x[i][6] if len(x[i]) > 6 else 1.0
        if kind == 1:
            fr, rk, cap = row_at(pol, eq)
            amt = eq * rk[c] / 100 * pol["mult"] * (pol["smult"] if d < 0 and c < 5 else 1.0) * sm   # (sleeves: no short factor)
            if full is not None:
                full[i] = (amt, eq)
            if cap > 0 and c not in pol["exempt"]:
                room = cap / 100 * pol["mult"] * eq - sum(v[0] for v in opn.values() if not v[1])
                if amt > room:
                    amt = room if room > pol["minf"] * amt else 0.0
            if amt > 0:
                opn[i] = [amt, c >= 5]                    # sleeves (coin 5 / 6): never in the cap room or the worst case
                                                          # (v3.2 fix: they were counted for the instant of their entry)
            else:
                skipped += 1
        elif kind == 0 and i in opn:
            opn[i][1] = True
        elif kind == 2 and i in opn:
            a = opn.pop(i)[0]; eq += a * R; top = max(top, eq); low = min(low, eq)
            if amts is not None:
                amts[i] = a; bal_at[i] = eq
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
    return dict(final=eq, dd=dd * 100, ddc=ddc * 100, top=top, low=low, invested=inv, reach=reach, events=out_ev, amts=amts, full=full, bal_after=bal_at,
                months=mbal, skipped=skipped)


# ── the full v3.1 system: TBO + panic sleeve (coin 5) + VOLC sleeve (coin 6), as live ─────────────────────────────
VOLC_SHARE, PANIC_UNITS = 0.25, 3.0
_SL = {}


def sleeve_rows():
    """Panic v3.0 (5 core + 7 extra coins, max 2 extra open) and the VOLC sleeve's trades (cache/volc_trades_<TAG>.pkl, from
    build_trades.py v31) as rows (entry, exit, be = entry, dir, R, coin 5 / 6): sized outside the open-risk cap."""
    if "r" not in _SL:
        import panic_sleeve as PSL
        rows = [PSL.sleeve_rows(PSL.events())]
        f = C.D.CACHE / f"volc_trades_{TAG}.pkl"
        if f.exists():
            V = pd.read_pickle(f)
            m = lambda col: V[col].values.astype("datetime64[m]").astype(np.int64)
            rows.append(np.c_[m("entry_time"), m("exit_time"), m("entry_time"), V.dir.values, V.R.values, np.full(len(V), 6)])
        _SL["r"] = np.concatenate(rows).astype(float)
    return _SL["r"]


def full_policy(pol):
    """pol + the panic sleeve (PANIC_UNITS / 6 of the row's BTC risk per 5% move) and VOLC (VOLC_SHARE x the BTC risk)."""
    return dict(pol, rows=[(f, list(rk[:5]) + [rk[0] * PANIC_UNITS / 6, rk[0] * VOLC_SHARE], cap) for f, rk, cap in pol["rows"]],
                exempt=set(pol["exempt"]) | {5, 6})


def window_full(a, b):
    """TBO rows of the window first (same order as window(), so history()'s trade table still lines up), sleeves after."""
    xb, t0, t1 = window(a, b)
    S = sleeve_rows()
    return np.r_[cols7(xb), cols7(S[(S[:, 0] >= t0) & (S[:, 0] < t1)])], t0, t1, len(xb)


def window(a, b):
    t0, t1 = pd.Timestamp(a).value // MIN, pd.Timestamp(b).value // MIN
    return TR[(TR[:, 0] >= t0) & (TR[:, 0] < t1)], t0, t1


def journey_trades(seed, a="2022-01-01", b="2026-11-07", months=24, full=False):
    """Random 4-week blocks of the real trades glued into one path starting at t=0 (blocks start on a 4h boundary)."""
    r = np.random.default_rng(seed)
    pool, t0, t1 = window_full(a, b)[:3] if full else window(a, b)
    rows = []
    for k in range(int(np.ceil(months * MON / BLK))):
        u = t0 + r.integers(0, (t1 - BLK - t0) // 240) * 240
        s = pool[(pool[:, 0] >= u) & (pool[:, 0] < u + BLK)].copy(); s[:, :3] += k * BLK - u
        rows.append(s)
    return np.concatenate(rows)


def history(pol, a, b, eq0=200.0, full=False):
    """Real history a..b: dict with daily balance / worst-case drawdown series, the taken trades with $ results.
    full: the whole v3.1 system (pol = the bot's policy; the panic and VOLC sleeves are added, their trades are not listed)."""
    if full:
        x, t0, t1, nb = window_full(a, b); pol = full_policy(pol)
    else:
        x, t0, t1 = window(a, b); nb = len(x)
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
    tk = sel.loc[sorted(i for i in r2["amts"] if i < nb)].copy()
    tk["risk_usd"] = [r2["amts"][i] for i in tk.index]; tk["pnl"] = tk.risk_usd * tk.R
    return dict(r=r, bal=bal, dd=ddd, events=ev, trades=tk)
