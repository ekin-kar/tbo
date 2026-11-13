"""v3.2 tools: trades32 (xengine32: v3.1 + regime-conditional exits / rules) and daily-regime -> per-minute masks.
Base = v3.1 TBO (v31deploy: failed-breakout rule, BTC cascade); with every v3.2 control off trades32 = the v3.1 list."""
import numpy as np, pandas as pd
import common as C, v29lib as L, v31lib as W, xengine32 as X32
import crypto_regimes as R

FB = dict(T_h=8, G=60, cont=1, mlo=0.9, mhi=99.0, thr=-0.2, act=3, lvl=-0.5)
CASC_R, CASC_TO = -0.5, -0.25
TP_PAD = 0.0001                                   # take-profit limit 0.01% inside the target (as the VOLC sleeve)


def exit32(L3=0.0, L3T=0.0, TPR=0.0, **kw):
    kw = dict(dict(A=FB, rcool=1), **kw)
    v = np.zeros(X32.NP)
    v[:36] = W.exit31(**dict(W.V30_EXIT, **kw))
    v[X32.L3], v[X32.L3T], v[X32.TPR] = L3, L3T, TPR
    return v


def minute_mask(sym, t, cond):
    """cond: boolean Series indexed by daily close times (crypto_regimes.regimes index) -> per-minute mask (value of the
    last daily close at or before each minute)."""
    idx = cond.index.values.astype("datetime64[m]").astype(np.int64)
    k = np.searchsorted(idx, t, side="right") - 1
    v = cond.to_numpy(bool)
    return np.where(k >= 0, v[np.clip(k, 0, None)], False)


def btc_tight(t, btc):
    """The v3.1 cascade masks for a non-BTC coin from BTC's trades."""
    b = btc[btc.R < CASC_R]; out = {}
    for d, nm in ((1, "l"), (-1, "s")):
        j = np.searchsorted(t, b[b.dir == d].exit_time.values.astype("datetime64[m]").astype(np.int64)) + 1
        m = np.zeros(len(t), np.bool_); m[j[j < len(t)]] = True
        out[nm] = m
    return out


def trades32(sym, shift=0, btc=None, ex=None, exL2=None, exS2=None, hold2=None, emask=None, dmask=None, dyn=None, ruleB=None,
             rmaskB=None, exL=None, exS=None, holdL=None, holdS=None, start="2020-01-01", end=W.END, ofilt=None):
    """v3.1 TBO trades of one coin with v3.2 controls.
    ex / exL / exS: exit32 kwargs for both / long / short (over v3.0 + the failed-breakout rule A);
    exL2 / exS2 + hold2 (h) + emask (fn(t) -> (mask_l, mask_s)): the second exit set for trades filled where the mask is True;
    dmask (fn(t) -> (mask_l, mask_s)) + dyn = {'l': [DX, DL, DTP], 's': [...]}: regime-now locks / take-profit;
    ruleB (dict for rule slot B) + rmaskB (fn(t) -> mask): an extra checkpoint rule for trades filled where the mask is True;
    holdL / holdS: hold limits (h). btc: BTC's v3.2 trades at this shift for the cascade (None for BTC itself).
    ofilt(o, t, shift) -> o': edits the entry orders before the run (v3.2c: entry filters inside the engine; the cached
    arrays must be copied, never modified)."""
    m = L.m1(sym)
    C.SLIP = W.SLIPS.get(sym, 0.0003)
    o, kL, kS = W.orders(sym, shift)
    n = len(m["t"]); t = m["t"]
    if ofilt is not None:
        o = ofilt(dict(o), t, shift)
    mm_t = t + shift if shift else t
    ones, zeros = np.ones(n, np.bool_), np.zeros(n, np.bool_)
    dflt = lambda nm, d: o[nm] if o[nm] is not None else d
    eL = dict(ex or {}, **(exL or {})); eS = dict(ex or {}, **(exS or {}))
    if ruleB:
        eL = dict(eL, B=ruleB); eS = dict(eS, B=ruleB)
    pl, ps = exit32(**eL), exit32(**eS)
    pl2 = exit32(**dict(eL, **(exL2 or {}))) if exL2 is not None else pl
    ps2 = exit32(**dict(eS, **(exS2 or {}))) if exS2 is not None else ps
    mbl = int((holdL or kL["hold_h"]) * 60); mbs = int((holdS or kS["hold_h"]) * 60)
    mbl2 = int((hold2 or holdL or kL["hold_h"]) * 60); mbs2 = int((hold2 or holdS or kS["hold_h"]) * 60)
    em_l, em_s = emask(t) if emask else (zeros, zeros)
    dm_l, dm_s = dmask(t) if dmask else (zeros, zeros)
    dy = dyn or {}
    dyl, dys = np.asarray(dy.get("l", [0, 0, 0]), float), np.asarray(dy.get("s", [0, 0, 0]), float)
    rb = rmaskB(t) if rmaskB else ones
    tl = btc_tight(t, btc) if btc is not None and sym != "BTCUSDT" else {"l": zeros, "s": zeros}
    cl = W.V30_COOL
    res = X32.sim32(mm_t, m["o"], m["h"], m["l"], m["c"], o["optr"], o["kind"], o["direction"], o["price"], o["sl"], o["tp"], o["expiry"],
                    dflt("allow_entry", ones), dflt("allow_fill", ones), dflt("force_exit", zeros), dflt("exit_long", zeros),
                    dflt("exit_short", zeros), np.zeros(n), mbl, mbs, pl, ps, ones, ones, tl["l"], tl["s"],
                    CASC_TO if btc is not None and sym != "BTCUSDT" else 0.0, int(cl[0]), float(cl[1]), int(cl[2]), float(cl[3]),
                    np.zeros(n), ones, pl2, ps2, mbl2, mbs2, em_l, em_s, dm_l, dm_s, dyl, dys, rb)
    e_idx, x_idx, dirs, e_px, x_px, dist, reason, rf, hf, mfe, ld, rule, arm = res
    tr = pd.DataFrame({"entry_time": C.D.to_datetime(t[e_idx]), "exit_time": C.D.to_datetime(t[x_idx]), "dir": dirs, "entry": e_px,
                       "exit": x_px, "sl_dist": dist, "reason": [C.E.REASONS[r] for r in reason]})
    tpm = tr.reason.to_numpy() == "TP"                       # take-profit limit 0.01% inside the target, maker fee
    tr.loc[tpm, "exit"] = tr.exit[tpm] - tr.dir[tpm] * TP_PAD * tr.entry[tpm]
    fee = C.TAKER + C.SLIP
    f_out = np.where(tpm, C.MAKER, fee)
    gross = (tr["exit"] - tr["entry"]) * tr["dir"]
    hours = (tr["exit_time"] - tr["entry_time"]).dt.total_seconds() / 3600
    tr["R"] = (gross - fee * tr["entry"] - f_out * tr["exit"] - C.FUNDING_8H * hours / 8 * tr["entry"]) / tr["sl_dist"]
    tr["hours"] = hours; tr["be_time"] = C.D.to_datetime(t[rf]); tr["half_time"] = C.D.to_datetime(t[hf])
    tr["mfe"] = mfe; tr["ldist"] = ld; tr["rule"] = rule; tr["arm_time"] = C.D.to_datetime(t[np.clip(arm, 0, n - 1)])
    tr = C.between(tr, start, end).reset_index(drop=True)
    tr["sym"] = sym
    return tr


def all32(shift=0, **kw):
    """The five coins (BTC first: its trades drive the cascade)."""
    btc = trades32("BTCUSDT", shift, **{k: (v("BTCUSDT") if callable(v) and k.endswith("_fn") else v) for k, v in kw.items()})
    return pd.concat([btc] + [trades32(s, shift, btc=btc, **kw) for s in W.COINS[1:]], ignore_index=True)


def parity():
    P = pd.read_pickle(W.CACHE / "pkg" / "base_s0.pkl")
    X = all32()
    k = lambda Z: sorted(zip(Z.sym, Z.entry_time, Z.exit_time, Z.R.round(9)))
    return len(X), len(P), k(X) == k(P), bool((X.sort_values(["sym", "entry_time"]).be_time.values == P.sort_values(["sym", "entry_time"]).be_time.values).all())
