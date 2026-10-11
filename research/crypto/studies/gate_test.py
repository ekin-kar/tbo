"""Gated / staggered entries and second chances (Oct 2026).
Gate: a new trade is held back while another coin's trade in the SAME direction is still "fresh" (not yet de-risked).
Variants: what counts as de-risked (breakeven at +1.5R, +1R / +0.5R reached, currently in profit), BTC exempt or not,
how many fresh trades are allowed, only recent blockers, market-wide bypasses (BTC bull regime, BTC momentum, gate only
in chop). Second chance for a held-back trade, checked whenever the gate may have opened (another trade de-risked or
closed), until W hours after the signal: enter at market if price is still near the breakout level; or (retest) a limit
order back at the breakout level if it ran away. Re-entries are managed like any bot trade (tradepath.py, 1m prices).
Sizing as the bot (botsim.py: ladder + open-risk cap, BTC exempt); also a fixed-size (non-compounding) R account."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import heapq, pickle, sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
import botsim as BS
import tradepath as TP

MIN = BS.MIN
P = pd.read_pickle(C.D.CACHE / "trade_prices_v24.pkl")
T = BS.T.merge(P, on=["sym", "entry_time"], how="left")
_m = lambda s: s.values.astype("datetime64[m]").astype(np.int64)
E, X, BE = _m(T.entry_time), _m(T.exit_time), _m(T.be_time)
CI = T.sym.map({s: i for i, s in enumerate(BS.COINS)}).to_numpy(); DIR = T.dir.to_numpy().astype(int)
EP, DIST, R0 = T.entry.to_numpy(), T.sl_dist.to_numpy(), T.R.to_numpy()
N = len(T)
NEXT_SAME = np.full(N, 10**12, dtype=np.int64)                      # entry minute of the coin's next own trade
for c in range(5):
    ids = np.nonzero(CI == c)[0]
    NEXT_SAME[ids[:-1]] = E[ids[1:]]

MARKS_F = C.D.CACHE / "gate_marks.pkl"
try:
    MARKS = pickle.load(open(MARKS_F, "rb"))
except FileNotFoundError:
    MARKS = None


def build_marks():
    out = []
    for k in range(N):
        r = TP.run(int(CI[k]), int(DIR[k]), int(E[k]), float(EP[k]), float(DIST[k]), marks=(0.5, 1.0))
        out.append(r["marks"])
    pickle.dump(out, open(MARKS_F, "wb"))
    return out


# ── market context (known at the time: previous daily close / last 1m close) ──
_btc = C.load("BTCUSDT"); _d = F.resample(_btc, 1440)
DT = (_d["t"] + 1440).astype(np.int64)                               # daily close stamp (minutes)
DC = pd.Series(_d["c"])
EMA200 = DC.ewm(span=200, adjust=False).mean().to_numpy(); EMA50 = DC.ewm(span=50, adjust=False).mean().to_numpy()
BULL = (DC.to_numpy() > EMA200) & (EMA200 > np.r_[EMA200[:10], EMA200[:-10]])
BEAR = (DC.to_numpy() < EMA200) & (EMA200 < np.r_[EMA200[:10], EMA200[:-10]])
_c4 = F.resample(_btc, 240)
_h, _l, _cc = _c4["h"], _c4["l"], _c4["c"]
up = np.r_[0, np.diff(_h)]; dn = np.r_[0, -np.diff(_l)]
pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
tr4 = np.maximum(_h - _l, np.maximum(np.abs(_h - np.r_[_cc[0], _cc[:-1]]), np.abs(_l - np.r_[_cc[0], _cc[:-1]])))
w = lambda a: pd.Series(a).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
_atr = w(tr4); _pdi = 100 * w(pdm) / _atr; _ndi = 100 * w(ndm) / _atr
ADX4 = w(100 * np.abs(_pdi - _ndi) / np.maximum(_pdi + _ndi, 1e-12)); T4 = (_c4["t"] + 240).astype(np.int64)


def daily(arr, t):
    j = int(np.searchsorted(DT, t, side="right")) - 1
    return arr[j] if j >= 0 else False


def btc_mom(t, days=7):
    return TP.price(0, t) / TP.price(0, t - days * 1440) - 1


def adx(t):
    j = int(np.searchsorted(T4, t, side="right")) - 1
    return ADX4[j] if j >= 0 else 0


# ── portfolio simulation ──
def sim(a, b, g, pol, eq0=200.0, compound=True):
    """g: gate / second-chance settings (dict). Returns stats and per-trade records."""
    ids = np.nonzero((E >= pd.Timestamp(a).value // MIN) & (E < pd.Timestamp(b).value // MIN))[0]
    hp = []; seq = 0
    def push(t, kind, ref):
        nonlocal seq; heapq.heappush(hp, (t, {"x": 0, "be": 1, "mk": 1, "en": 2, "sc": 2}[kind], seq, kind, ref)); seq += 1
    for i in ids:
        push(int(E[i]), "en", int(i))
    eq = eq0; pk = eq0; dd = 0.0; pkc = eq0; ddc = 0.0
    opn = {}                                   # pid -> position dict
    pend = {}                                  # original id -> dict(expiry, retest)
    busy = {}                                  # coin -> pid of its open position
    recs = []; pid_n = 0
    stats = dict(blocked=0, sc_near=0, sc_retest=0, skipped_cap=0, skipped_busy=0)

    def unlocked(p, t):
        u = g.get("unlock", "be")
        if p["be_t"] is not None and t >= p["be_t"]:
            return True
        if isinstance(u, float):
            mt = p["marks"].get(u)
            return mt is not None and t >= mt
        if u == "profit":
            px = TP.price(p["ci"], t)
            return p["d"] * (px - p["ep"]) >= g.get("profit_R", 0.0) * p["dist"]
        return False

    def gated(ci, d, t):
        if not g.get("gate"):
            return False
        if g.get("exempt_btc") and ci == 0:
            return False
        byp = g.get("bypass")
        if byp == "btc_regime" and daily(BULL if d > 0 else BEAR, t):
            return False
        if byp == "btc_mom" and d * btc_mom(t) > g.get("mom", 0.08):
            return False
        if byp == "chop_only" and adx(t) >= g.get("adx", 20):
            return False
        n = 0
        for p in opn.values():
            if p["d"] != d or p["ci"] == ci:
                continue
            if g.get("blockers") == "btc" and p["ci"] != 0:
                continue
            if g.get("blockers") == "nonbtc" and p["ci"] == 0:
                continue
            if g.get("window_h") and t - p["t"] > g["window_h"] * 60:
                continue
            if not unlocked(p, t):
                n += 1
        return n >= g.get("max_fresh", 1)

    def open_pos(ci, d, t, ep, dist, res, src, oid):
        nonlocal pid_n
        fr, rk, cap = BS.row_at(pol, eq if compound else eq0)
        base = eq if compound else eq0
        amt = base * rk[ci] / 100 * (pol["smult"] if d < 0 else 1.0)
        if cap > 0 and ci not in pol["exempt"]:
            room = cap / 100 * base - sum(p["amt"] for p in opn.values() if not p["be"])
            if amt > room:
                amt = room if room > pol["minf"] * amt else 0.0
        if amt <= 0:
            stats["skipped_cap"] += 1; return
        pid_n += 1; pid = pid_n
        p = dict(ci=ci, d=d, t=t, ep=ep, dist=dist, R=res["R"], x=res["exit_t"], be_t=res["be_t"], marks=res["marks"], amt=amt,
                 be=False, src=src, oid=oid)
        opn[pid] = p; busy[ci] = pid
        push(max(res["exit_t"], t + 1e-3), "x", pid)
        if res["be_t"] is not None and res["be_t"] < res["exit_t"]:
            push(res["be_t"], "be", pid)
        for q, mt in res["marks"].items():
            if mt is not None and mt < res["exit_t"]:
                push(mt, "mk", pid)

    def try_pending(t):
        for oid in list(pend):
            pdx = pend[oid]; ci, d = int(CI[oid]), int(DIR[oid])
            if t > pdx["exp"] or t >= NEXT_SAME[oid]:
                pend.pop(oid); continue
            if ci in busy or gated(ci, d, t):
                continue
            px = TP.price(ci, t); lvl = EP[oid]; dist = DIST[oid]
            run_away = d * (px - lvl) / dist
            if d * (px - (lvl - d * dist)) <= 0.25 * dist:              # back near / through the stop: the breakout failed
                pend.pop(oid); continue
            mode = g.get("sc")
            if mode in ("near", "both") and run_away <= g.get("near_k", 0.5):
                res = TP.run(ci, d, int(t), px, dist, end_min=int(NEXT_SAME[oid]))
                open_pos(ci, d, int(t), px, dist, res, "near", oid); stats["sc_near"] += 1; pend.pop(oid); continue
            if mode in ("retest", "both") and run_away > g.get("near_k", 0.5):
                m = TP.m1(ci); j0 = int(np.searchsorted(m["t"], t)); j1 = int(np.searchsorted(m["t"], pdx["exp"]))
                L = lvl + d * g.get("retest_at", 0.0) * dist
                touch = np.nonzero((m["l"][j0:j1] <= L) if d > 0 else (m["h"][j0:j1] >= L))[0]
                pend.pop(oid)
                if len(touch):
                    push(int(m["t"][j0 + touch[0]]), "sc", (oid, float(L)))
                continue

    for_events = 0
    while hp:
        t, _, _, kind, ref = heapq.heappop(hp); for_events += 1
        if kind == "en":
            i = ref; ci, d = int(CI[i]), int(DIR[i])
            if ci in busy:
                stats["skipped_busy"] += 1
            elif gated(ci, d, t):
                stats["blocked"] += 1; recs.append(("blocked", i))
                if g.get("sc"):
                    pend[i] = dict(exp=t + g.get("W", 24) * 60)
            else:
                res = dict(R=R0[i], exit_t=int(X[i]), be_t=int(BE[i]) if BE[i] < X[i] else None, marks=MARKS[i])
                open_pos(ci, d, t, EP[i], DIST[i], res, "orig", i)
        elif kind == "sc":
            oid, L = ref; ci, d = int(CI[oid]), int(DIR[oid])
            if ci not in busy and t < NEXT_SAME[oid]:
                res = TP.run(ci, d, int(t), L, DIST[oid], entry_fee=C.MAKER, end_min=int(NEXT_SAME[oid]))
                open_pos(ci, d, int(t), L, DIST[oid], res, "retest", oid); stats["sc_retest"] += 1
        elif kind == "be":
            if ref in opn:
                opn[ref]["be"] = True
        elif kind == "x":
            p = opn.pop(ref, None)
            if p is not None:
                busy.pop(p["ci"], None)
                pnl = p["amt"] * p["R"]; eq += pnl
                recs.append(("trade", p["oid"], p["src"], p["R"], pnl, p["amt"]))
        if kind in ("be", "mk", "x") and pend:
            try_pending(t)
        wv = eq - sum(p["amt"] for p in opn.values() if not p["be"])
        pk = max(pk, wv); dd = max(dd, (pk - wv) / pk); pkc = max(pkc, eq); ddc = max(ddc, (pkc - eq) / pkc)
    mo = (pd.Timestamp(b) - pd.Timestamp(a)).days / 30.44
    tr = [r for r in recs if r[0] == "trade"]
    big = [r for r in tr if r[3] >= 5]
    out = dict(final=eq, pm=((eq / eq0) ** (1 / mo) - 1) * 100 if compound else (eq - eq0) / eq0 * 100 / mo, dd=dd * 100,
               ddc=ddc * 100, n=len(tr), big=len(big), bigR=sum(r[3] for r in big),
               sc_R=float(np.mean([r[3] for r in tr if r[2] != "orig"])) if any(r[2] != "orig" for r in tr) else np.nan,
               blockedR=float(np.mean([R0[r[1]] for r in recs if r[0] == "blocked"])) if stats["blocked"] else np.nan, **stats)
    out["ratio"] = out["pm"] / out["dd"] if out["dd"] else np.nan
    return out


WINDOWS = [("2020-03-01", "2024-01-01"), ("2024-01-01", "2026-10-01"), ("2022-01-01", "2026-10-01")]
FLAT = BS.flat_policy(5, 2.5, 0.83)                                  # fixed-size R account: units of 1% = 1


def job(args):
    name, g = args
    lad = BS.bot_policy()
    res = [sim(a, b, g, lad) for a, b in WINDOWS]
    fx = [sim(a, b, g, FLAT, eq0=100.0, compound=False) for a, b in WINDOWS[:2]]
    return name, res, fx


def variants(part):
    V = {"baseline (bot now: ladder + cap)": {}}
    if part in ("all", "gate"):
        for ex in (False, True):
            tag = ", BTC exempt" if ex else ""
            V[f"gate: same dir until breakeven{tag}"] = dict(gate=1, exempt_btc=ex)
            for u in (1.0, 0.5):
                V[f"gate: until +{u}R reached{tag}"] = dict(gate=1, unlock=u, exempt_btc=ex)
            for pr in (0.0, 0.5):
                V[f"gate: until in profit >= {pr}R now{tag}"] = dict(gate=1, unlock="profit", profit_R=pr, exempt_btc=ex)
            V[f"gate: max 2 fresh same dir{tag}"] = dict(gate=1, max_fresh=2, exempt_btc=ex)
            for wh in (4, 12, 24):
                V[f"gate: only blockers < {wh}h old{tag}"] = dict(gate=1, window_h=wh, exempt_btc=ex)
        V["gate: only fresh BTC blocks (alts wait for BTC)"] = dict(gate=1, blockers="btc", exempt_btc=True)
        V["gate: only fresh non-BTC trades block"] = dict(gate=1, blockers="nonbtc", exempt_btc=True)
        V["gate, bypass in BTC bull/bear regime"] = dict(gate=1, bypass="btc_regime")
        V["gate, bypass if BTC 7d move > 8%"] = dict(gate=1, bypass="btc_mom", mom=0.08)
        V["gate, bypass if BTC 7d move > 4%"] = dict(gate=1, bypass="btc_mom", mom=0.04)
        V["gate only in chop (BTC 4h ADX < 20)"] = dict(gate=1, bypass="chop_only", adx=20)
        V["gate only in chop (BTC 4h ADX < 25)"] = dict(gate=1, bypass="chop_only", adx=25)
    if part in ("all", "sc"):
        for gname, gg in (("gate BE", dict(gate=1)), ("gate BE, BTC exempt", dict(gate=1, exempt_btc=True)),
                          ("gate +1R", dict(gate=1, unlock=1.0)), ("gate +0.5R, BTC exempt", dict(gate=1, unlock=0.5, exempt_btc=True))):
            for W in (12, 24, 48):
                for k in (0.25, 0.5, 1.0):
                    V[f"{gname} + 2nd chance near (<= {k}R away, {W}h)"] = dict(gg, sc="near", near_k=k, W=W)
                V[f"{gname} + 2nd chance retest at level ({W}h)"] = dict(gg, sc="retest", near_k=0.0, W=W)
                V[f"{gname} + near 0.5R or retest ({W}h)"] = dict(gg, sc="both", near_k=0.5, W=W)
                V[f"{gname} + near 0.5R or retest at +0.5R ({W}h)"] = dict(gg, sc="both", near_k=0.5, retest_at=0.5, W=W)
    return V


if __name__ == "__main__":
    if MARKS is None:
        MARKS = build_marks()
    part = sys.argv[1] if len(sys.argv) > 1 else "all"
    V = variants(part)
    with Pool(3, maxtasksperchild=8) as p:
        res = p.map(job, list(V.items()), chunksize=1)
    pickle.dump(res, open(C.D.CACHE / f"gate_test_{part}.pkl", "wb"))
    b = dict((n, (r, f)) for n, r, f in res)["baseline (bot now: ladder + cap)"]
    print(f"{'':58s} | 2020-23 $200 ladder: %/mo drop ratio | 2024-26: $200->  %/mo drop ratio | 2022-26 %/mo drop | fixed R acct 20-23 / 24-26 ret/dd | trades blocked 2nd-chance(near/retest) | big runners(R>=5) 24-26 | blocked avgR / 2nd-ch avgR")
    for n, r, f in res:
        a_, h, w_ = r
        fr = [x["pm"] / x["dd"] for x in f]
        print(f"{n[:58]:58s} | {a_['pm']:6.2f} {a_['dd']:5.1f} {a_['ratio']:.3f}(x{a_['ratio']/b[0][0]['ratio']:.2f}) | ${h['final']:>7,.0f} {h['pm']:6.2f} {h['dd']:5.1f} {h['ratio']:.3f}(x{h['ratio']/b[0][1]['ratio']:.2f}) | "
              f"{w_['pm']:6.2f} {w_['dd']:5.1f} | x{fr[0]/(b[1][0]['pm']/b[1][0]['dd']):.2f} x{fr[1]/(b[1][1]['pm']/b[1][1]['dd']):.2f} | "
              f"{h['n']:4d} {h['blocked']:4d} {h['sc_near']:3d}/{h['sc_retest']:3d} | {h['big']:3d} ({h['bigR']:5.0f}R) | {h['blockedR']:6.2f} / {h['sc_R']:6.2f}", flush=True)
