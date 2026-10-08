"""Portfolio-level sizing rules on the bot's real trades (TBO v2.4, BTC ETH BNB SOL ADA), compounding account simulation.
 A  open-risk cap (risk not yet at breakeven): skip, or shrink the new trade to fit
 A2 same-direction scaling: k-th position in the same direction (still at risk) trades at a smaller size
 B  shorts: size 0 / 0.25 / 0.5 (now) / 0.75 / 1, or full shorts only in a bear market (BTC below its daily EMA200)
 C  volatility sizing: scale risk by BTC's 30-day volatility vs its own past median, or by the account's own 30-day volatility
 D  drawdown brake: half risk while the account is more than X% below its peak
Base = the bot now: BTC 5%, ETH 2.5%, BNB/SOL/ADA 0.83% (shorts x0.5), $200 start. 2020-23 and 2024-26 run separately."""
import pickle
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C

ALL = pickle.load(open(C.D.CACHE / "portfolio_trades_v24.pkl", "rb"))
COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
RISK = {"BTCUSDT": 0.05, "ETHUSDT": 0.025, "BNBUSDT": 0.0083, "SOLUSDT": 0.0083, "ADAUSDT": 0.0083}
T = pd.concat([ALL[(s, 0.0003)] for s in COINS]).sort_values("entry_time").reset_index(drop=True)
# BTC daily context (known at the previous daily close)
m = C.load("BTCUSDT")
import families as F
d = F.resample(m, 1440)
btc = pd.Series(d["c"], index=pd.to_datetime((d["t"] + 1440) * 60, unit="s"))     # stamped at the close
lr = np.log(btc).diff()
VOL30 = lr.rolling(30).std()
VOL_MED = VOL30.expanding(180).median()                                             # past-only reference level
EMA200 = btc.ewm(span=200, adjust=False).mean()
BEAR = (btc < EMA200) & (EMA200 < EMA200.shift(10))


def at(series, t):
    i = series.index.searchsorted(t, side="right") - 1
    return series.iloc[i] if i >= 0 else np.nan


def sim(rule, start, end, eq0=200.0, curve=False):
    tr = T[(T.entry_time >= start) & (T.entry_time < end)].reset_index(drop=True)
    eps = pd.Timedelta(microseconds=1); ev = []
    for i, r in tr.iterrows():
        ev += [(r.entry_time, 1, i), (max(r.be_time, r.entry_time + eps), 0, i), (max(r.exit_time, r.entry_time + 2 * eps), 2, i)]
    ev.sort(key=lambda z: (z[0], -z[1]))
    eq = eq0; peak = eq0; open_ = {}; curve = []; daily = {}; skipped = 0
    for t, kind, i in ev:
        if kind == 1:
            sym, dr = tr.sym[i], tr.dir[i]
            amt = RISK[sym] * eq * rule.get("mult", 1.0)
            if dr < 0:
                sm = rule.get("short", 0.5)
                if rule.get("bear_shorts") is not None:
                    sm = rule["bear_shorts"] if at(BEAR, t) else rule.get("short_bull", 0.0)
                amt *= sm
            if rule.get("btc_vol"):
                v, md = at(VOL30, t), at(VOL_MED, t)
                if v == v and md == md and v > 0:
                    amt *= float(np.clip(md / v, rule["btc_vol"][0], rule["btc_vol"][1]))
            if rule.get("acct_vol"):
                days = sorted(daily)[-31:]
                if len(days) >= 20:
                    e = np.array([daily[k] for k in days]); r_ = np.diff(np.log(e))
                    s = r_.std() * np.sqrt(365)
                    if s > 0:
                        amt *= float(np.clip(rule["acct_vol"][0] / s, rule["acct_vol"][1], rule["acct_vol"][2]))
            if rule.get("dd_brake"):
                lvl, f = rule["dd_brake"]
                if eq < peak * (1 - lvl):
                    amt *= f
            at_risk = [v for v in open_.values() if not v["be"]]
            if rule.get("same_dir"):
                k = sum(1 for v in at_risk if v["dir"] == dr)
                fs = rule["same_dir"]; amt *= fs[min(k, len(fs) - 1)]
            if rule.get("cap"):
                room = rule["cap"] * eq - sum(v["amt"] for v in at_risk)
                if amt > room:
                    if rule.get("cap_mode") == "shrink" and room > 0.25 * amt:
                        amt = room
                    else:
                        skipped += 1; continue
            if amt <= 0:
                skipped += 1; continue
            open_[i] = dict(amt=amt, be=False, dir=dr)
        elif kind == 0 and i in open_:
            open_[i]["be"] = True
        elif kind == 2 and i in open_:
            eq += open_.pop(i)["amt"] * tr.R[i]; peak = max(peak, eq)
        worst = eq - sum(v["amt"] for v in open_.values() if not v["be"])
        curve.append((t, eq, worst)); daily[t.normalize()] = eq
    cv = pd.DataFrame(curve, columns=["t", "bal", "worst"]).set_index("t")
    pk = cv.worst.cummax(); dd = ((pk - cv.worst) / pk).max() * 100
    mo = (pd.Timestamp(end) - pd.Timestamp(start)).days / 30.44
    pm = ((cv.bal.iloc[-1] / eq0) ** (1 / mo) - 1) * 100
    hw = cv.bal.cummax(); nh = cv.index[cv.bal >= hw]; flat = np.diff(nh.values).astype("timedelta64[D]").astype(int).max()
    mm = cv.bal.resample("ME").last().ffill().pct_change().dropna()
    st = dict(final=cv.bal.iloc[-1], pm=pm, dd=dd, ratio=pm / dd, flat=int(flat), pos=(mm > 0).mean() * 100, worst_m=mm.min() * 100, skipped=skipped)
    if curve:
        idx = pd.date_range(pd.Timestamp(start), pd.Timestamp(end) - pd.Timedelta(days=1), freq="D")
        bal = cv.bal.resample("D").last().reindex(idx).ffill().fillna(eq0)
        wst = cv.worst.resample("D").min().reindex(idx).ffill().fillna(eq0)
        ddd = (wst / np.maximum.accumulate(np.maximum(wst.values, 1e-9)) - 1) * 100
        return st, bal, ddd
    return st


RULES = {"now (no portfolio rule)": {}}
for cap in (0.06, 0.08):
    for mode in ("skip", "shrink"):
        RULES[f"A open-risk cap {cap:.0%} ({mode})"] = dict(cap=cap, cap_mode=mode)
for fs in ((1, 1, 0.5), (1, 0.75, 0.5), (1, 0.5), (1, 1, 1, 0.5)):
    RULES[f"A2 same-direction sizes {'/'.join(map(str, fs))}"] = dict(same_dir=list(fs))
for sm in (0.0, 0.25, 0.75, 1.0):
    RULES[f"B shorts x{sm}"] = dict(short=sm)
RULES["B shorts x0.5 only in BTC bear market, else 0"] = dict(bear_shorts=0.5, short_bull=0.0)
RULES["B shorts x1 in bear market, x0.25 otherwise"] = dict(bear_shorts=1.0, short_bull=0.25)
for lo, hi in ((0.5, 1.5), (0.5, 1.0), (0.75, 1.25)):
    RULES[f"C BTC-volatility sizing clip {lo}-{hi}"] = dict(btc_vol=(lo, hi))
for tgt in (0.6, 1.0):
    RULES[f"C account-volatility target {tgt:.0%}/yr (0.5-1.5x)"] = dict(acct_vol=(tgt, 0.5, 1.5))
for lvl in (0.2, 0.3, 0.4):
    RULES[f"D drawdown brake: half risk below -{lvl:.0%}"] = dict(dd_brake=(lvl, 0.5))
RULES["(reference: everything at 0.8x risk)"] = dict(mult=0.8)


def run(name):
    rule = RULES[name]
    return name, sim(rule, "2020-03-01", "2024-01-01"), sim(rule, "2024-01-01", "2026-10-01")


if __name__ == "__main__":
    with Pool(4) as p:
        res = p.map(run, list(RULES))
    pickle.dump(res, open(C.D.CACHE / "sizing_v3.pkl", "wb"))
    b = dict((n, (a, h)) for n, a, h in res)["now (no portfolio rule)"]
    print(f"{'rule':48s} | 2020-23: %/mo  worst drop  ratio  (x now) | 2024-26: $200->   %/mo  worst drop  ratio (x now)  flat days  worst month")
    for n, a, h in res:
        print(f"{n:48s} | {a['pm']:6.2f}% {a['dd']:6.1f}% {a['ratio']:6.3f} (x{a['ratio']/b[0]['ratio']:.2f}) | ${h['final']:>8,.0f} {h['pm']:6.2f}% {h['dd']:6.1f}% "
              f"{h['ratio']:6.3f} (x{h['ratio']/b[1]['ratio']:.2f}) {h['flat']:5d} {h['worst_m']:6.1f}%")
