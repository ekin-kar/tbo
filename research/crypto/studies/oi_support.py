"""Breakout support study (Oct 2026): can open interest / positioning data tell real 4h breakouts from false ones?

Base = the live v2.6 rules (4h n20, 1 ATR stop, BE 1.5R, lock +5R -> +1.5R, 120 h) WITH the live OI filter, on 51 coins
(1m candles cache/<SYM>_m1.npz, Binance metrics 1h data/extra + EXTRA2; the 39 extra coins' candles and metrics come from
data.binance.vision as fetch_binance_extra.py does, not kept in git). Trades from 2022 (OI data starts Dec 2021).
Families (all known at the 4h close that places the order, except B):
  A  price move with no new money: price moved >= y ATR in the trade's direction over L h while OI fell <= x  -> skip
     A+ coil: price within +-y ATR over L h while OI rose >= x                                               -> size x1.5
  B  after the fill: OI change from before the fill to +h hours <= x (positions closing = squeeze), optionally only
     when the trade is >= k R in profit then                                                                 -> exit at market
  C  leverage built up: OI value rank over W days (or OI / 30-day average daily volume, rank over W days) >= p (high)
     or <= 1 - p (low)                                                                                         -> skip
  D  coin OI vs the market (sum of the 12 dev coins' OI): change over L h minus the market's <= x -> skip; >= x -> x1.5
  E  long/short ratio extreme (global accounts / top-trader accounts / top-trader positions), rank over W days:
     contra = the crowd already leans the trade's way (long: rank >= p), follow = it leans against it      -> skip
  F  forced-liquidation flush in the last H hours (4h move >= 1.5 sigma and OI <= -x): same direction as the
     trade (a squeeze-driven move) or the opposite one                                                         -> skip
  G  tired setup: level touched >= n times (within tol ATR) in the 20 candles, or very quiet last 10 closes
     (std <= q ATR)                                                                                            -> skip
Modes: skip = the order is not placed (engine re-run: a later candle can fill instead), half = flagged trades x0.5,
up = flagged trades x1.5, exit = B.

Coins: OUR5 (BTC ETH BNB SOL ADA), DEV_OTHER (XRP DOGE AVAX LINK DOT LTC TRX) -> DEV12 = selection set;
HOLD39 untouched until the end, split into HOLD_BIG and HOLD_SMALL.

Gates, fixed before any result was seen (ratio = net R / max drawdown R; x = variant / base; periods 2022-23, 2024-26):
  G1 DEV12 (each coin weight 1, shorts x0.5): ratio x >= 1.05 in both periods and net x >= 0.90 in both
  G2 plateau: >= 60% of the setting's grid neighbours have ratio x > 1 in both periods on DEV12
  G3 luck: min(period ratio x) beats >= 95% of 40 time-shifted copies of the same mask (B: random exits, same count)
  G4 HOLD_BIG: ratio x > 1 in both periods (HOLD_SMALL shown, not a gate)
  G5 OUR5 with the bot's weights (BTC 6, ETH 4, alts 0.83): ratio x > 1 in both periods (BTC alone shown)
  G6 money (botsim, bot sizing from $300, starts 2022 and 2024): more money and the drop at most 1 point deeper
    python oi_support.py build        # all coins -> cache/oi_support/<SYM>.pkl
    python oi_support.py eval         # G1, G2, G4, G5 tables -> cache/oi_support/eval.pkl
    python oi_support.py luck         # G3 for the G1+G2 passers
"""
import itertools, os, pickle, sys
from multiprocessing import Pool
from pathlib import Path
import numpy as np, pandas as pd
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]
import common as C, families as F
from wf2 import V21
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "cryptobot"))
import panic_signal as PS                                          # noqa: E402

EX = ROOT / "data" / "extra"
EXTRA2 = Path(os.environ.get("EXTRA2", ROOT / "data" / "extra2"))      # metrics of the 39 extra coins (data.binance.vision, not in git)
OUT = C.D.CACHE / "oi_support"
OUR5 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
DEV_OTHER = ["XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT"]
DEV12 = OUR5 + DEV_OTHER
HOLD_BIG = ["BCHUSDT", "XLMUSDT", "SUIUSDT", "HBARUSDT", "1000SHIBUSDT", "1000PEPEUSDT", "NEARUSDT", "UNIUSDT", "ETCUSDT",
            "APTUSDT", "AAVEUSDT", "ATOMUSDT", "FILUSDT", "ICPUSDT"]
HOLD_SMALL = ["ALGOUSDT", "ARBUSDT", "AXSUSDT", "CRVUSDT", "ENAUSDT", "EOSUSDT", "FETUSDT", "GRTUSDT", "IMXUSDT", "INJUSDT",
              "LDOUSDT", "MANAUSDT", "OPUSDT", "ORDIUSDT", "RUNEUSDT", "SANDUSDT", "SEIUSDT", "STXUSDT", "THETAUSDT", "TIAUSDT",
              "VETUSDT", "WIFUSDT", "WLDUSDT", "XTZUSDT", "ZECUSDT"]
HOLD39 = HOLD_BIG + HOLD_SMALL
ALL = DEV12 + HOLD39
BOT_W = {"BTCUSDT": 6.0, "ETHUSDT": 4.0, "BNBUSDT": 0.83, "SOLUSDT": 0.83, "ADAUSDT": 0.83}
PERIODS = (("2022-23", "2022-01-01", "2024-01-01"), ("2024-26", "2024-01-01", "2026-11-07"))
BASE_KW = dict(V21, tf=240, n=20, be_R=1.5, hold_h=120, sl_mode="atr", sl_atr=1.0, lock_R=5.0, lock_to=1.5)
TF = 240


# ── variants ────────────────────────────────────────────────────────────────────────────────────────────────────
def _grid(fam, modes, cats, axes):
    """One variant per categorical combination x ordinal-axis combination; 'ax' keeps the ordinal positions (G2)."""
    out = []
    names = list(axes)
    for cat in itertools.product(*cats.values()) if cats else [()]:
        for pos in itertools.product(*[range(len(axes[k])) for k in names]):
            p = dict(zip(cats, cat)); p.update({k: axes[k][i] for k, i in zip(names, pos)})
            out.append(dict(fam=fam, modes=modes, p=p, cat=cat, ax=pos))
    return out


CONDS = (_grid("A", ("skip", "half"), {}, dict(L=(24, 48, 72, 120), y=(0.5, 1.0, 2.0, 3.0), x=(0.0, -0.02, -0.05)))
         + _grid("A+", ("up",), {}, dict(L=(48, 120), y=(1.0, 2.0, 3.0), x=(0.03, 0.05, 0.10)))
         + _grid("C", ("skip", "half"), dict(meas=("oi", "lev"), side=("high", "low")), dict(W=(7, 30, 90), p=(0.7, 0.8, 0.9, 0.95)))
         + _grid("D", ("skip", "half"), {}, dict(L=(24, 72, 168), x=(-0.10, -0.05, -0.02, 0.0)))
         + _grid("D+", ("up",), {}, dict(L=(24, 72, 168), x=(0.02, 0.05, 0.10, 0.20)))
         + _grid("E", ("skip", "half"), dict(meas=("acc", "top_acc", "top_pos"), how=("contra", "follow")), dict(W=(7, 30), p=(0.8, 0.9, 0.95)))
         + _grid("F", ("skip", "half"), dict(rel=("same", "opposite")), dict(H=(12, 24, 48), x=(0.05, 0.08, 0.12)))
         + _grid("G", ("skip", "half"), dict(kind=("touch",)), dict(tol=(0.1, 0.25, 0.5), n=(4, 5, 6, 7, 8)))
         + _grid("G", ("skip", "half"), dict(kind=("quiet",)), dict(q=(0.25, 0.3, 0.37, 0.45, 0.55))))
for i, v in enumerate(CONDS):
    v["id"] = i
EXITS = _grid("B", ("exit",), {}, dict(h=(1, 2, 4), x=(-0.01, -0.02, -0.03, -0.05), k=(None, 0.0, 0.5)))


def vname(v, mode=None):
    p = ", ".join(f"{k} {'any' if val is None else val}" for k, val in v["p"].items())
    return f"{v['fam']} {mode or v['modes'][0]}: {p}"


# ── data ────────────────────────────────────────────────────────────────────────────────────────────────────────
def metrics(sym):
    f = EX / f"{sym}_metrics_1h.csv.gz"
    if not f.exists():
        f = EXTRA2 / f"{sym}_metrics_1h.csv.gz"
    g = pd.read_csv(f, usecols=["create_time", "sum_open_interest_value", "count_toptrader_long_short_ratio",
                                 "sum_toptrader_long_short_ratio", "count_long_short_ratio"])
    t = pd.to_datetime(g.create_time).values.astype("datetime64[m]").astype(np.int64)
    o = np.argsort(t, kind="stable"); g = g.iloc[o]; t = t[o]
    keep = np.r_[t[1:] != t[:-1], True]; g = g[keep]; t = t[keep]
    pos = lambda s: pd.Series(np.where(s.to_numpy() > 0, s.to_numpy(), np.nan)).ffill().to_numpy()
    return dict(t=t, oi=pos(g.sum_open_interest_value), acc=pos(g.count_long_short_ratio),
                top_acc=pos(g.count_toptrader_long_short_ratio), top_pos=pos(g.sum_toptrader_long_short_ratio))


def rank(x, n, min_n):
    """Percentile of each value among the last n samples (1 = highest)."""
    return pd.Series(x).rolling(n, min_periods=min_n).rank(pct=True).to_numpy()


def market_oi():
    """Sum of the DEV12 coins' OI value on an hourly grid (only where all 12 are known)."""
    f = OUT / "market_oi.pkl"
    if f.exists():
        return pd.read_pickle(f)
    s = []
    for sym in DEV12:
        m = metrics(sym)
        s.append(pd.Series(m["oi"], index=m["t"] - m["t"] % 60).groupby(level=0).last())
    df = pd.concat(s, axis=1)
    idx = np.arange(df.index.min(), df.index.max() + 60, 60)
    tot = df.reindex(idx).ffill(limit=3).sum(axis=1, min_count=12)
    OUT.mkdir(parents=True, exist_ok=True); tot.to_pickle(f)
    return tot


class Coin:
    """One coin's candles, base trades and every feature at each 4h decision close."""

    def __init__(self, sym):
        self.sym = sym
        C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
        self.m = C.load(sym)
        self.c = F.resample(self.m, TF)
        self.M = metrics(sym)
        c = self.c
        self.a = C.I.atr(c["h"], c["l"], c["c"], 14)
        self.T = c["t"] + TF                                       # decision times (minutes)
        mt = self.M["t"]

        def at(T, lag_h=0):                                        # index of the last sample before T - lag
            tt = T - lag_h * 60
            q = np.searchsorted(mt, tt, side="left") - 1
            ok = (q >= 0) & (tt - mt[np.clip(q, 0, None)] < 180)
            return np.where(ok, q, -1)
        self.at = at
        q0 = at(self.T)
        self.q0 = q0
        v = lambda arr, q: np.where(q >= 0, arr[np.clip(q, 0, None)], np.nan)
        self.v = v
        # the live OI filter (grid_v25.oi_skip: 72 samples back)
        oi = self.M["oi"]
        okq = (q0 >= 72)
        chg72 = np.where(okq, oi[np.clip(q0, 0, None)] / oi[np.clip(q0 - 72, 0, None)] - 1, np.nan)
        self.oi_block = chg72 <= -0.03
        self._ranks = {}

    # time-based changes
    def doi(self, L):
        return self.v(self.M["oi"], self.q0) / self.v(self.M["oi"], self.at(self.T, L)) - 1

    def dprice(self, L):
        k = L // 4; cc = self.c["c"]
        prev = np.r_[np.full(k, np.nan), cc[:-k]]
        return (cc - prev) / self.a

    def mrank(self, key, W):
        if (key, W) not in self._ranks:
            if key == "lev":                                       # OI / average daily quote volume (30 d)
                vol = pd.Series(self.m["v"], index=self.m["t"] // 60).groupby(level=0).sum()
                hv = vol.reindex(np.arange(vol.index.min(), vol.index.max() + 1)).fillna(0.0)
                d30 = hv.rolling(720, min_periods=480).sum() / 30
                hidx = self.M["t"] // 60
                x = self.M["oi"] / d30.reindex(hidx).to_numpy()
            else:
                x = self.M[key]
            self._ranks[(key, W)] = rank(x, W * 24, W * 12)
        return self.v(self._ranks[(key, W)], self.q0)

    def flushes(self):
        """Hourly forced-flush flags (down: price <= -1.5 sigma over 4 h, up: >= +1.5 sigma) and the 4 h OI change."""
        if not hasattr(self, "_fl"):
            h1 = F.resample(self.m, 60)
            mt = self.M["t"]
            q = np.searchsorted(mt, h1["t"] + 60, side="left") - 1
            ok = (q >= 0) & (h1["t"] + 60 - mt[np.clip(q, 0, None)] < 120)
            oi = np.where(ok, self.M["oi"][np.clip(q, 0, None)], np.nan)
            f = PS.features(h1["h"], h1["l"], h1["c"], oi, np.zeros(len(oi)), 4)
            self._fl = (h1["t"] + 60, f["rz"], f["doi"])
        return self._fl

    def cond(self, v, shift=0):
        """(long mask, short mask) over the 4h candles: True = the condition holds at that close."""
        P = v["p"]; fam = v["fam"]; n = len(self.T)
        if fam in ("A", "A+"):
            dp = self.dprice(P["L"]); do = self.doi(P["L"])
            if fam == "A":
                L_, S_ = (dp >= P["y"]) & (do <= P["x"]), (-dp >= P["y"]) & (do <= P["x"])
            else:
                L_ = S_ = (np.abs(dp) <= P["y"]) & (do >= P["x"])
        elif fam == "C":
            r = self.mrank(P["meas"], P["W"])
            L_ = S_ = (r >= P["p"]) if P["side"] == "high" else (r <= 1 - P["p"])
        elif fam in ("D", "D+"):
            mk = market_oi()
            mt = self.T - self.T % 60
            def mv(T):                                             # market OI at the last full hour before T
                hh = (T - T % 60) - 60
                return mk.reindex(hh).to_numpy()
            dm = mv(self.T) / mv(self.T - P["L"] * 60) - 1
            rel = self.doi(P["L"]) - dm
            L_ = S_ = (rel <= P["x"]) if fam == "D" else (rel >= P["x"])
        elif fam == "E":
            r = self.mrank(P["meas"], P["W"])
            hi, lo = r >= P["p"], r <= 1 - P["p"]
            L_, S_ = (hi, lo) if P["how"] == "contra" else (lo, hi)
        elif fam == "F":
            th, rz, do = self.flushes()
            up = np.nan_to_num((rz >= 1.5) & (do <= -P["x"])).astype(int)
            dn = np.nan_to_num((rz <= -1.5) & (do <= -P["x"])).astype(int)
            cu, cd = np.r_[0, np.cumsum(up)], np.r_[0, np.cumsum(dn)]
            j1 = np.searchsorted(th, self.T, side="right"); j0 = np.searchsorted(th, self.T - P["H"] * 60, side="right")
            nu, nd = cu[j1] - cu[j0], cd[j1] - cd[j0]
            L_, S_ = ((nu > 0), (nd > 0)) if P["rel"] == "same" else ((nd > 0), (nu > 0))
        elif fam == "G":
            H, Lw, cc, a = self.c["h"], self.c["l"], self.c["c"], self.a
            if P["kind"] == "touch":
                hi20 = C.I.rolling_max(H, 20); lo20 = C.I.rolling_min(Lw, 20)
                win = np.lib.stride_tricks.sliding_window_view
                Hw = np.full((n, 20), np.nan); Lw2 = np.full((n, 20), np.nan)
                Hw[19:] = win(H, 20); Lw2[19:] = win(Lw, 20)
                L_ = ((Hw >= (hi20 - P["tol"] * a)[:, None]).sum(1) >= P["n"])
                S_ = ((Lw2 <= (lo20 + P["tol"] * a)[:, None]).sum(1) >= P["n"])
            else:
                sd = pd.Series(cc).rolling(10).std().to_numpy() / a
                L_ = S_ = sd <= P["q"]
        else:
            raise ValueError(fam)
        L_ = np.nan_to_num(L_).astype(bool); S_ = np.nan_to_num(S_).astype(bool)
        if shift:
            L_, S_ = np.roll(L_, shift), np.roll(S_, shift)
        return L_, S_

    def run(self, extra_l=None, extra_s=None):
        """Engine trades from 2022 with the OI filter (+ extra skip masks)."""
        bl = self.oi_block | (extra_l if extra_l is not None else False)
        bs = self.oi_block | (extra_s if extra_s is not None else False)
        def skip(c, a, hi, lo, s):
            assert len(c["t"]) == len(bl)
            return bl if s > 0 else bs
        x = C.between(F.channel_breakout(self.m, **dict(BASE_KW, skip_fn=skip)), "2022-01-01", "2026-11-07").reset_index(drop=True)
        mn = lambda col: x[col].values.astype("datetime64[m]").astype(np.int64)
        return pd.DataFrame(dict(e=mn("entry_time"), x=mn("exit_time"), d=x.dir.values.astype(int), R=x.R.values,
                                 entry=x.entry.values, exit=x.exit.values, sl=x.sl_dist.values))

    def k_of(self, tr):
        """4h decision candle of each trade (the close that placed the filled order)."""
        ei = np.searchsorted(self.m["t"], tr.e.values)
        return np.searchsorted(self.c["act"], ei, side="right") - 1

    def flags(self, tr, v, shift=0):
        L_, S_ = self.cond(v, shift)
        k = self.k_of(tr)
        return np.where(tr.d.values > 0, L_[k], S_[k])

    def exit_paths(self, tr):
        """For B: per trade and h, the R if closed at market +h hours after the fill (NaN if already closed), the R
        then before costs, and the OI change from before the fill to then."""
        out = {}
        mt, oi = self.M["t"], self.M["oi"]
        q0 = np.searchsorted(mt, tr.e.values, side="left") - 1
        ok0 = (q0 >= 0) & (tr.e.values - mt[np.clip(q0, 0, None)] < 180)
        cost_in = C.TAKER + C.SLIP
        for h in (1, 2, 4):
            Th = tr.e.values + h * 60
            open_ = tr.x.values > Th
            j = np.searchsorted(self.m["t"], Th, side="left") - 1          # the minute ending at Th
            px = self.m["c"][np.clip(j, 0, None)]
            q1 = np.searchsorted(mt, Th, side="right") - 1
            doi = np.where(ok0 & (q1 > q0), oi[np.clip(q1, 0, None)] / oi[np.clip(q0, 0, None)] - 1, np.nan)
            gross = tr.d.values * (px - tr.entry.values)
            cost = cost_in * tr.entry.values + cost_in * px + C.FUNDING_8H * h / 8 * tr.entry.values
            out[h] = dict(R=np.where(open_, (gross - cost) / tr.sl.values, np.nan), Rnow=gross / tr.sl.values, doi=doi)
        return out


def build_one(sym):
    f = OUT / f"{sym}.pkl"
    if f.exists():
        return sym, "cached"
    X = Coin(sym)
    base = X.run()
    res = dict(base=base, skip={}, flag={}, paths=X.exit_paths(base))
    for v in CONDS:
        L_, S_ = X.cond(v)
        res["flag"][v["id"]] = X.flags(base, v)
        if "skip" in v["modes"]:
            t = X.run(L_, S_)
            res["skip"][v["id"]] = t[["e", "x", "d", "R"]]
    pickle.dump(res, open(f, "wb"))
    return sym, f"{len(base)} base trades"


# ── evaluation ──────────────────────────────────────────────────────────────────────────────────────────────────
def load_all(syms=ALL):
    return {s: pickle.load(open(OUT / f"{s}.pkl", "rb")) for s in syms if (OUT / f"{s}.pkl").exists()}


def score(parts):
    """parts: list of (e, x, R, weight) arrays -> {period: (net, dd, n)}."""
    if not parts:
        return {nm: (0.0, np.nan, 0) for nm, *_ in PERIODS}
    e = np.concatenate([p[0] for p in parts]); x = np.concatenate([p[1] for p in parts])
    pr = np.concatenate([p[2] * p[3] for p in parts])
    out = {}
    for nm, a, b in PERIODS:
        a_, b_ = pd.Timestamp(a).value // 60_000_000_000, pd.Timestamp(b).value // 60_000_000_000
        m = (e >= a_) & (e < b_)
        o = np.argsort(x[m], kind="stable"); cum = np.cumsum(pr[m][o])
        dd = float(np.max(np.maximum.accumulate(np.r_[0, cum])[1:] - cum)) if m.any() else np.nan
        out[nm] = (float(cum[-1]) if m.any() else 0.0, dd, int(m.sum()))
    return out


def coin_w(sym, bot):
    return BOT_W.get(sym, 0.83) if bot else 1.0


def parts_of(R, syms, kind, vid=None, mode=None, bot=False, flags=None, exitR=None):
    """Trades of a variant for a coin group as score() parts."""
    parts = []
    for s in syms:
        if s not in R:
            continue
        r = R[s]; cw = coin_w(s, bot)
        if kind == "skip":
            t = r["skip"][vid]; parts.append((t.e.values, t.x.values, t.R.values, cw * np.where(t.d.values < 0, 0.5, 1.0)))
            continue
        t = r["base"]; w = cw * np.where(t.d.values < 0, 0.5, 1.0); RR = t.R.values
        if kind in ("half", "up"):
            fl = r["flag"][vid] if flags is None else flags[s]
            w = w * np.where(fl, 0.5 if kind == "half" else 1.5, 1.0)
        elif kind == "exit":
            RR = exitR[s]
        parts.append((t.e.values, t.x.values, RR, w))
    return parts


def exit_R(R, v, rng=None):
    """B variant R per coin; rng = random exits of the same number of trades (luck test)."""
    out = {}
    for s, r in R.items():
        p = r["paths"][v["p"]["h"]]; Rb = r["base"].R.values
        cond = (p["doi"] <= v["p"]["x"]) & ~np.isnan(p["R"])
        if v["p"]["k"] is not None:
            cond &= p["Rnow"] >= v["p"]["k"]
        if rng is not None:
            elig = np.flatnonzero(~np.isnan(p["R"]))
            pick = rng.choice(elig, size=min(int(cond.sum()), len(elig)), replace=False) if len(elig) else []
            cond = np.zeros(len(Rb), bool); cond[pick] = True
        out[s] = np.where(cond, p["R"], Rb)
    return out


GROUPS = dict(DEV12=(DEV12, False), OUR5=(OUR5, True), BTC=(["BTCUSDT"], True), DEV_OTHER=(DEV_OTHER, False),
              HOLD_BIG=(HOLD_BIG, False), HOLD_SMALL=(HOLD_SMALL, False), HOLD39=(HOLD39, False))


def variants():
    for v in CONDS:
        for mode in v["modes"]:
            yield v, mode
    for v in EXITS:
        yield v, "exit"


def evaluate():
    R = load_all()
    print(len(R), "coins loaded", flush=True)
    base = {g: score(parts_of(R, syms, "base", bot=bot)) for g, (syms, bot) in GROUPS.items()}
    rows = []
    for v, mode in variants():
        ex = exit_R(R, v) if mode == "exit" else None
        row = dict(fam=v["fam"], mode=mode, name=vname(v, mode), p=v["p"], cats=str(v["cat"]), ax=v["ax"], id=v.get("id"))
        for g, (syms, bot) in GROUPS.items():
            sc = score(parts_of(R, syms, mode, v.get("id"), bot=bot, exitR=ex))
            for nm, *_ in PERIODS:
                n1, d1, k1 = sc[nm]; n0, d0, k0 = base[g][nm]
                row[f"{g}|{nm}|net"] = n1; row[f"{g}|{nm}|dd"] = d1; row[f"{g}|{nm}|n"] = k1
                row[f"{g}|{nm}|netx"] = n1 / n0 if n0 > 0 else np.nan
                row[f"{g}|{nm}|ratiox"] = (n1 / d1) / (n0 / d0) if n0 > 0 and d1 > 0 and d0 > 0 else np.nan
                row[f"{g}|{nm}|dnet"] = n1 - n0
        rows.append(row)
    df = pd.DataFrame(rows)
    P = [nm for nm, *_ in PERIODS]
    rx = lambda g: np.minimum(df[f"{g}|{P[0]}|ratiox"], df[f"{g}|{P[1]}|ratiox"])
    df["G1"] = (rx("DEV12") >= 1.05) & (np.minimum(df[f"DEV12|{P[0]}|netx"], df[f"DEV12|{P[1]}|netx"]) >= 0.90)
    good = rx("DEV12") > 1.0
    G2 = np.zeros(len(df), bool)
    for _, grp in df.groupby(["fam", "mode", "cats"]):
        ax = np.array(grp.ax.tolist()); ix = grp.index.to_numpy()
        for a, i in zip(ax, ix):
            nb = ix[np.abs(ax - a).sum(1) == 1]
            G2[i] = len(nb) > 0 and good[nb].mean() >= 0.60
    df["G2"] = G2
    df["G4"] = rx("HOLD_BIG") > 1.0
    df["G5"] = rx("OUR5") > 1.0
    df.to_pickle(OUT / "eval.pkl")
    pickle.dump(base, open(OUT / "base.pkl", "wb"))
    return df, base


def _luck_one(args):
    sym, items, nshift = args
    X = Coin(sym); r = pickle.load(open(OUT / f"{sym}.pkl", "rb")); base = r["base"]
    n = len(X.T); rng = np.random.default_rng(abs(hash(sym)) % 2**32)
    shifts = rng.integers(180, n - 180, size=nshift)
    out = {}
    for vid, mode in items:
        v = CONDS[vid]
        for si, sh in enumerate(shifts):
            if mode == "skip":
                L_, S_ = X.cond(v, int(sh)); t = X.run(L_, S_)
                out[(vid, mode, si)] = t[["e", "x", "d", "R"]]
            else:
                out[(vid, mode, si)] = X.flags(base, v, int(sh))
    return sym, out


def luck(nshift=40):
    df = pd.read_pickle(OUT / "eval.pkl")
    sel = df[df.G1 & df.G2]
    items = [(int(r.id), r["mode"]) for _, r in sel.iterrows() if r["mode"] != "exit"]
    R = load_all(DEV12)
    P = [nm for nm, *_ in PERIODS]
    base = score(parts_of(R, DEV12, "base"))
    def rmin(sc):
        return min((sc[p][0] / sc[p][1]) / (base[p][0] / base[p][1]) for p in P)
    res = {}
    if items:
        with Pool(6) as pool:
            got = dict(pool.map(_luck_one, [(s, items, nshift) for s in DEV12]))
        for vid, mode in items:
            sims = []
            for si in range(nshift):
                if mode == "skip":
                    RR = {s: dict(R[s], skip={vid: got[s][(vid, mode, si)]}) for s in DEV12}
                    sims.append(rmin(score(parts_of(RR, DEV12, "skip", vid))))
                else:
                    sims.append(rmin(score(parts_of(R, DEV12, mode, vid, flags={s: got[s][(vid, mode, si)] for s in DEV12}))))
            res[(vid, mode)] = sims
    for _, r in sel[sel["mode"] == "exit"].iterrows():
        v = dict(fam="B", p=r.p)
        rng = np.random.default_rng(7)
        res[("B", str(r.p))] = [rmin(score(parts_of(R, DEV12, "exit", exitR=exit_R(R, v, rng)))) for _ in range(nshift)]
    pickle.dump(res, open(OUT / "luck.pkl", "wb"))
    for _, r in sel.iterrows():
        k = (int(r.id), r["mode"]) if r["mode"] != "exit" else ("B", str(r.p))
        real = min(r[f"DEV12|{p}|ratiox"] for p in P); sims = np.array(res[k])
        print(f"{r['name']:<60} real {real:.3f}  luck p95 {np.percentile(sims, 95):.3f}  beats {np.mean(real > sims) * 100:.0f}%")


def _bot_rows(sym, vid, mode, pex=None):
    """botsim rows (entry, exit, be, dir, R, coin) of a variant on one of OUR5 or AVAX (be = first minute at +1.5R)."""
    X = Coin(sym); ci = (OUR5 + ["AVAXUSDT"]).index(sym)          # AVAX = coin 5 (the 6-coin test)
    v = CONDS[vid] if isinstance(vid, int) else vid
    if mode == "skip":
        L_, S_ = X.cond(v); t = X.run(L_, S_)
    else:
        t = X.run()
    t = t.copy(); mult = np.ones(len(t))
    if mode in ("half", "up"):
        mult = np.where(X.flags(t, v), 0.5 if mode == "half" else 1.5, 1.0)
    elif mode == "exit":
        p = X.exit_paths(t)[pex["h"]]
        cond = (p["doi"] <= pex["x"]) & ~np.isnan(p["R"])
        if pex["k"] is not None:
            cond &= p["Rnow"] >= pex["k"]
        t.loc[cond, "R"] = p["R"][cond]; t.loc[cond, "x"] = t.e.values[cond] + pex["h"] * 60
    mt = X.m["t"]; be = []
    for e, x, d, en, sl in zip(t.e.values, t.x.values, t.d.values, t.entry.values, t.sl.values):
        j0, j1 = int(np.searchsorted(mt, e)), int(np.searchsorted(mt, x))
        lvl = en + d * 1.5 * sl
        seg = X.m["h"][j0 + 1:j1 + 1] >= lvl if d > 0 else X.m["l"][j0 + 1:j1 + 1] <= lvl
        hit = np.nonzero(seg)[0]
        be.append(mt[j0 + 1 + hit[0]] if len(hit) else x)
    return np.c_[t.e.values, t.x.values, np.array(be), t.d.values, t.R.values * mult, np.full(len(t), ci)]


def money(vid, mode, pex=None, keep=None):
    """Bot sizing from $300 (botsim, the live ladder + cap), starts 2022 and 2024: base vs variant (vid = CONDS index
    or a condition dict)."""
    import botsim as B
    T0 = pd.concat([pickle.load(open(C.D.CACHE / "portfolio_trades_v26.pkl", "rb"))[(s, 0.0003)] for s in OUR5])
    T0 = T0.assign(_c=T0.sym.map(OUR5.index)).sort_values(["entry_time", "_c"], kind="stable")
    mn = lambda col: T0[col].values.astype("datetime64[m]").astype(np.int64)
    TR0 = np.c_[mn("entry_time"), mn("exit_time"), mn("be_time"), T0.dir.values, T0.R.values, T0._c.values]   # the base: v2.6, no OI-low filter
    with Pool(6) as p:
        rows = p.starmap(_bot_rows, [(s, vid, mode, pex) for s in OUR5])
    X = np.concatenate(rows); X = X[np.lexsort((X[:, 5], X[:, 0]))]
    out = {}
    for a in ("2022-01-01", "2024-01-01"):
        t0 = pd.Timestamp(a).value // 60_000_000_000; t1 = pd.Timestamp("2026-11-07").value // 60_000_000_000
        res = []
        for TR in (TR0, X):
            x = TR[(TR[:, 0] >= t0) & (TR[:, 0] < t1)].copy(); x[:, :3] -= t0
            r = B.run(x, B.bot_policy(), 300.0, keep=keep); res.append((r["final"], r["dd"]) if keep is None else r)
        out[a[:4]] = res
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    OUT.mkdir(parents=True, exist_ok=True)
    if cmd == "build":
        market_oi()
        syms = sys.argv[2].split(",") if len(sys.argv) > 2 else ALL
        print(len(CONDS), "conditions,", sum("skip" in v["modes"] for v in CONDS), "skip runs per coin,", len(EXITS), "exits", flush=True)
        with Pool(6) as p:
            for s, msg in p.imap_unordered(build_one, syms):
                print(s, msg, flush=True)
    elif cmd == "eval":
        df, base = evaluate()
        print(df.G1.sum(), "pass G1;", (df.G1 & df.G2).sum(), "G1+G2;", (df.G1 & df.G2 & df.G4 & df.G5).sum(), "G1+G2+G4+G5")
    elif cmd == "luck":
        luck()
