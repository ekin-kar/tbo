"""
The 10 TBO improvement ideas (Oct 2026), each with a small set of variants, on BTC and ETH, 2020-03..2026-09.
Judged by an anchored walk-forward 2022..2026 (each year: best variant on earlier years, BTC+ETH pooled) vs v2.1.
"""
import itertools, pickle, sys
from multiprocessing import Pool
import numpy as np, pandas as pd
from numba import njit
import common as C, families as F
from wf2 import V21, stream, mar, TESTS

SYMS = ("BTCUSDT", "ETHUSDT")
A, B = "2020-03-01", "2026-10-01"
DATA = {}


def M(sym):
    if sym not in DATA:
        DATA[sym] = C.load(sym)
    return DATA[sym]


@njit(cache=True)
def first_reach(h, l, e_idx, x_idx, dirs, entry, dist, level):
    """First 1m index after the fill bar where the trade was `level` x dist in profit (-1 = never)."""
    out = np.full(len(e_idx), -1, np.int64)
    for k in range(len(e_idx)):
        tgt = entry[k] + dirs[k] * level * dist[k]
        for j in range(e_idx[k] + 1, x_idx[k] + 1):
            if (dirs[k] == 1 and h[j] >= tgt) or (dirs[k] == -1 and l[j] <= tgt):
                out[k] = j
                break
    return out


def idx(m, times):
    return np.searchsorted(m["t"], (times.values.astype("datetime64[m]").astype(np.int64)))


def base(sym, **kw):
    return C.between(F.channel_breakout(M(sym), **dict(V21, **kw)), A, B)


# ── variant builders: each returns a trades DataFrame with entry_time, exit_time, dir, R ──
def v_base(sym):
    return base(sym)


def v_pyramid(sym, add_risk):
    m = M(sym); b = base(sym)
    e = idx(m, b.entry_time); x = idx(m, b.exit_time)
    be = first_reach(m["h"], m["l"], e, x, b.dir.to_numpy(), b.entry.to_numpy(), b.sl_dist.to_numpy(), V21["be_R"])
    mask = np.zeros(len(m["t"]), np.bool_)
    for s_, x_ in zip(be, x):
        if s_ >= 0:
            mask[s_ + 1:x_] = True
    add = C.between(F.channel_breakout(m, **dict(V21, entry_mask=mask)), A, B)
    add = add.copy(); add["R"] *= add_risk
    return pd.concat([b, add])


def v_partial(sym, x_R, frac):
    m = M(sym); b = base(sym).copy()
    e = idx(m, b.entry_time); x = idx(m, b.exit_time)
    hit = first_reach(m["h"], m["l"], e, x, b.dir.to_numpy(), b.entry.to_numpy(), b.sl_dist.to_numpy(), x_R) >= 0
    leg = x_R - (C.TAKER + C.SLIP + C.MAKER) * b.entry / b.sl_dist
    b["R"] = np.where(hit, frac * leg + (1 - frac) * b.R, b.R)
    return b


def v_tilt(sym, feat):
    """1.5x risk on the best third of setups, 0.5x on the worst third (thresholds from EARLIER trades only)."""
    m = M(sym); b = base(sym).copy().sort_values("entry_time")
    d = F.resample(m, 1440); cc = d["c"]
    kd = np.searchsorted(d["act"], idx(m, b.entry_time), side="right") - 1
    if feat == "er":
        num = np.abs(cc[20:] - cc[:-20]); den = np.convolve(np.abs(np.diff(cc)), np.ones(20), "valid")
        v = np.r_[np.full(20, np.nan), num / den]; good_high = True
    elif feat == "volratio":
        lr = pd.Series(np.r_[np.nan, np.diff(np.log(cc))]); v = (lr.rolling(7).std() / lr.rolling(90).std()).to_numpy(); good_high = False
    else:  # slope strength of the daily EMA50 in daily ATR
        e = C.I.ema(cc, 50); a = C.I.atr(d["h"], d["l"], cc, 14); v = np.abs(e - np.r_[np.full(5, np.nan), e[:-5]]) / a; good_high = True
    f = pd.Series(v[np.clip(kd, 0, None)], index=b.index)
    lo = f.expanding(30).quantile(1 / 3).shift(1); hi = f.expanding(30).quantile(2 / 3).shift(1)
    top = (f >= hi) if good_high else (f <= lo)
    bot = (f <= lo) if good_high else (f >= hi)
    mult = np.where(top, 1.5, np.where(bot, 0.5, 1.0))
    b["R"] = b.R * mult
    return b


def v_shorts(sym, hold_h, be_R, tp_R):
    L = base(sym, sides="long")
    S = base(sym, sides="short", hold_h=hold_h, be_R=be_R, tp_R=tp_R)
    return pd.concat([L, S])


IDEAS = {
    "1 add to winners": [("risk 0.5", v_pyramid, dict(add_risk=0.5)), ("risk 1.0", v_pyramid, dict(add_risk=1.0))],
    "2 partial take-profit": [(f"{f:.0%} at {x}R", v_partial, dict(x_R=x, frac=f)) for x, f in itertools.product((2, 3, 4), (0.3, 0.5))],
    "3 hold winners longer": [(f">{r}R to {h}h", base, dict(ext_h=h, ext_R=r)) for h, r in itertools.product((168, 240), (3, 4, 6))],
    "4 close dead trades": [(f"<{r}R by {h}h", base, dict(early_h=h, early_R=r)) for h, r in itertools.product((12, 24, 48), (0.3, 0.5, 1.0))],
    "5 close-confirmed entry": [(f"{t}m close", base, dict(confirm_tf=t)) for t in (5, 15, 60)],
    "6 swing stop": [(f"swing {k}", base, dict(sl_mode="swing", swing_k=k)) for k in (3, 6, 12)],
    "7 trend quality (ER)": [(f"ER{n}>={e}", base, dict(er_n=n, er_min=e)) for n, e in itertools.product((10, 20), (0.1, 0.2, 0.3))],
    "8 bigger size on best": [(f"tilt {f}", v_tilt, dict(feat=f)) for f in ("er", "volratio", "slope")],
    "9 BTC/ETH confirm": [("other coin agrees", "co", {})],
    "10 own rules for shorts": [(f"S hold{h} be{b} tp{t}", v_shorts, dict(hold_h=h, be_R=b, tp_R=t))
                                for h, b, t in itertools.product((24, 48, 120), (1.0, 1.5), (0, 3, 5))],
}


def job(args):
    idea, i, sym = args
    if idea == "base":
        return idea, i, sym, v_base(sym)[["entry_time", "exit_time", "dir", "R"]]
    label, fn, kw = IDEAS[idea][i]
    if fn == "co":
        other = "ETHUSDT" if sym == "BTCUSDT" else "BTCUSDT"
        tr = base(sym, co_m1=M(other))
    else:
        tr = fn(sym, **kw)
    return idea, i, sym, tr[["entry_time", "exit_time", "dir", "R"]]


def summ(x, yrs):
    x = x.sort_values("exit_time"); r = x.R.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    return r.sum(), dd, r.sum() / yrs / max(dd, 3)


if __name__ == "__main__":
    jobs = [("base", 0, s) for s in SYMS] + [(k, i, s) for k in IDEAS for i in range(len(IDEAS[k])) for s in SYMS]
    with Pool(4) as p:
        res = p.map(job, jobs, chunksize=1)
    T = {(a, i, s): tr for a, i, s, tr in res}
    pickle.dump(T, open(C.D.CACHE / "ideas10.pkl", "wb"))
    yrs = 6.58
    print(f"{'':34s} {'BTC R':>7s} {'DD':>5s} {'MAR':>5s} | {'ETH R':>7s} {'DD':>5s} {'MAR':>5s}")
    def line(lbl, key):
        out = f"{lbl:34s}"
        for s in SYMS:
            r, dd, mr = summ(T[key + (s,)], yrs); out += f" {r:7.0f} {dd:5.1f} {mr:5.2f} |"
        return out
    print(line("v2.1 baseline", ("base", 0)))
    verdict = {}
    for idea, vs in IDEAS.items():
        print(f"\n{idea}")
        for i, (lbl, _, _) in enumerate(vs):
            print(line("   " + lbl, (idea, i)))
        # walk-forward: candidates = baseline + this idea's variants; pick on pooled MAR of earlier years
        cands = [("base", 0)] + [(idea, i) for i in range(len(vs))]
        oos = {s: [] for s in SYMS}; picks = []
        for y in TESTS:
            ty = (pd.Timestamp(f"{y}-01-01") - pd.Timestamp(A)).days / 365.25
            sc = [sum(mar(stream(T[c + (s,)], A, f"{y}-01-01"), ty) for s in SYMS) for c in cands]
            best = cands[int(np.argmax(sc))]; picks.append("base" if best[0] == "base" else vs[best[1]][0])
            for s in SYMS:
                oos[s].append(stream(T[best + (s,)], f"{y}-01-01", f"{y+1}-01-01"))
        wf = []
        for s in SYMS:
            r_w, dd_w, m_w = summ(pd.concat(oos[s]), 4.75)
            r_b, dd_b, m_b = summ(pd.concat([stream(T[("base", 0, s)], f"{y}-01-01", f"{y+1}-01-01") for y in TESTS]), 4.75)
            wf.append((s, r_w, dd_w, m_w, r_b, dd_b, m_b))
        better = all(w[3] > w[6] + 0.05 for w in wf)
        verdict[idea] = better
        print(f"   walk-forward picks {dict(zip(TESTS, picks))}")
        for s, r_w, dd_w, m_w, r_b, dd_b, m_b in wf:
            print(f"   {s} 2022-26 out of sample: {r_w:6.1f}R DD {dd_w:4.1f} MAR {m_w:4.2f}  vs v2.1 {r_b:6.1f}R DD {dd_b:4.1f} MAR {m_b:4.2f}")
        print(f"   -> {'BETTER on both coins' if better else 'not better on both coins'}")
    print("\nSUMMARY:", {k: ("PASS" if v else "fail") for k, v in verdict.items()})
