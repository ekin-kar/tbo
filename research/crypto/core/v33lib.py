"""v3.3 tools: trades33 (xengine33 = v3.2's engine + checkpoint rule C, any stage of the trade), exit33, job33.
With rule C off trades33 = v32lib.trades32 = the v3.1 / v3.2 trade list (checked in v33 setup)."""
import numpy as np, pandas as pd
import common as C, v29lib as L, v31lib as W, xengine33 as X33
import v32lib as V32
from v32lib import FB, CASC_R, CASC_TO, TP_PAD, btc_tight, minute_mask      # noqa: F401


def exit33(Cr=None, **kw):
    """v32lib.exit32 + rule C: Cr = dict(T_h, G (min), cont, mlo, mhi, thr, gb, act, lvl)."""
    v = np.zeros(X33.NP)
    v[:39] = V32.exit32(**kw)
    if Cr:
        v[39:48] = [Cr["T_h"] * 60, Cr.get("G", 60), Cr.get("cont", 1), Cr["mlo"], Cr.get("mhi", 5.0), Cr.get("thr", 99.0),
                    Cr.get("gb", 0.0), Cr["act"], Cr["lvl"]]
    return v


def trades33(sym, shift=0, btc=None, ex=None, exL2=None, exS2=None, hold2=None, emask=None, dmask=None, dyn=None, ruleB=None,
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
    pl, ps = exit33(**eL), exit33(**eS)
    pl2 = exit33(**dict(eL, **(exL2 or {}))) if exL2 is not None else pl
    ps2 = exit33(**dict(eS, **(exS2 or {}))) if exS2 is not None else ps
    mbl = int((holdL or kL["hold_h"]) * 60); mbs = int((holdS or kS["hold_h"]) * 60)
    mbl2 = int((hold2 or holdL or kL["hold_h"]) * 60); mbs2 = int((hold2 or holdS or kS["hold_h"]) * 60)
    em_l, em_s = emask(t) if emask else (zeros, zeros)
    dm_l, dm_s = dmask(t) if dmask else (zeros, zeros)
    dy = dyn or {}
    dyl, dys = np.asarray(dy.get("l", [0, 0, 0]), float), np.asarray(dy.get("s", [0, 0, 0]), float)
    rb = rmaskB(t) if rmaskB else ones
    tl = btc_tight(t, btc) if btc is not None and sym != "BTCUSDT" else {"l": zeros, "s": zeros}
    cl = W.V30_COOL
    res = X33.sim33(mm_t, m["o"], m["h"], m["l"], m["c"], o["optr"], o["kind"], o["direction"], o["price"], o["sl"], o["tp"], o["expiry"],
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



_BT = {}


def job33(args):
    """M.run_jobs worker: (spec, sym, shift) -> trades with spec['kw'] (BTC run first in the worker for the cascade)."""
    import v31_drawdown_and_sleeves as M
    spec, sym, shift = args
    if M._CUR["sym"] != sym:
        L._M.clear(); W._ORD.clear(); W._FA.clear(); _BT.clear()
        import families as F
        F._rs.cache_clear(); F._M1.clear()
        M._CUR["sym"] = sym
    kw = dict(spec.get("kw", {}))
    if sym == "BTCUSDT":
        x = trades33(sym, shift, **kw)
    else:
        key = (spec["id"], shift)
        if key not in _BT:
            _BT.clear(); _BT[key] = trades33("BTCUSDT", shift, **kw)
        x = trades33(sym, shift, btc=_BT[key], **kw)
    return spec["id"], sym, shift, x[[c for c in M.KEEP if c in x]]
