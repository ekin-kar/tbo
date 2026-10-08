"""Builds cryptobot/tbo_statistics.html (TBO v2.5, BTC/ETH/BNB/SOL/ADA; sizing = the bot's risk ladder + open-risk cap, as
botsim.py) and Python reference results (botsim) for checking the page's math (check_tbo_stats.py).
Trades: TBO v2.4 rules (v2.2 + open-interest filter from 2022, filter_test3.py 'USD 3d <= -3%'; shorts sized at short_risk_mult), BTC/ETH slippage 0.01%, alts 0.03%."""
import json, pickle
import numpy as np, pandas as pd
import common as C
import botsim as BS

ROOT = C.ROOT
ALL = pickle.load(open(C.D.CACHE / "portfolio_trades_v24.pkl", "rb"))
COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
cfg = {c: json.load(open(ROOT / "cryptobot" / f"config_{c[:-4].lower()}.json")) for c in COINS}
ms = lambda s: (s.values.astype("datetime64[ms]").astype(np.int64))
rows = []
for ci, s in enumerate(COINS):
    x = ALL[(s, 0.0003)]
    for e, xx, b, d, r, h in zip(ms(x.entry_time), ms(x.exit_time), ms(x.be_time), x.dir, x.R, x.hours):
        rows.append([ci, int(e), int(xx), int(b), int(d), round(float(r), 6), round(float(h), 2)])
rows.sort(key=lambda r: (r[1], r[0]))


def ref_sim(on, risks, smult, start_bal, t0, t1):
    """Python reference of the page's simulation (same event order, no cap)."""
    tr = [r for r in rows if on[r[0]] and t0 <= r[1] < t1]
    ev = []
    for i, r in enumerate(tr):
        ev += [(r[1], 1, i), (max(r[3], r[1] + 1), 0, i), (max(r[2], r[1] + 2), 2, i)]
    ev.sort(key=lambda z: (z[0], -z[1]))
    eq = start_bal; opn = {}; pk_w = start_bal; ddw = 0; pk_c = start_bal; ddc = 0
    for t, k, i in ev:
        r = tr[i]
        if k == 1:
            opn[i] = [risks[r[0]] / 100 * (smult if r[4] < 0 else 1) * eq, False]
        elif k == 0 and i in opn:
            opn[i][1] = True
        elif k == 2 and i in opn:
            eq += opn.pop(i)[0] * r[5]
        w = eq - sum(a for a, be in opn.values() if not be)
        pk_w = max(pk_w, w); ddw = max(ddw, 1 - w / pk_w); pk_c = max(pk_c, eq); ddc = max(ddc, 1 - eq / pk_c)
    return dict(final=round(eq, 2), ddw=round(ddw * 100, 2), ddc=round(ddc * 100, 2), trades=len(tr))


if __name__ == "__main__":
    pol = BS.bot_policy()
    data = dict(trades=rows, coins=[s[:-4] for s in COINS], ladder=[[f, r, c] for f, r, c in pol["rows"]], exempt=sorted(pol["exempt"]), minf=pol["minf"],
                risk=[cfg[s]["risk_pct"] for s in COINS], smult=cfg["BTCUSDT"]["short_risk_mult"],
                strat=cfg["BTCUSDT"]["strategy"], maxlev=cfg["BTCUSDT"]["max_leverage"], exlev=cfg["BTCUSDT"].get("exchange_leverage", cfg["BTCUSDT"]["max_leverage"]))
    html = open(ROOT / "research" / "crypto" / "tbo_stats_template.html").read().replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
    (ROOT / "cryptobot" / "tbo_statistics.html").write_text(html)
    (ROOT / "stats" / "tbo_crypto_statistics.html").write_text(html)
    T0, T1 = int(pd.Timestamp("2020-03-01").value // 10**6), int(pd.Timestamp("2026-10-01").value // 10**6)
    T24 = int(pd.Timestamp("2024-01-01").value // 10**6)
    cases = {"all5": ([1, 1, 1, 1, 1], T0), "btc": ([1, 0, 0, 0, 0], T0), "btc_eth": ([1, 1, 0, 0, 0], T0), "alts_2024": ([0, 0, 1, 1, 1], T24),
             "all5_2024": ([1, 1, 1, 1, 1], T24)}
    def ref_bot(on, t0):
        x = BS.TR[(BS.TR[:, 0] >= t0 // 60000) & (BS.TR[:, 0] < T1 // 60000) & np.isin(BS.TR[:, 5], [i for i, o in enumerate(on) if o])]
        r = BS.run(x, pol, 500.0)
        return dict(final=round(r["final"], 2), ddw=round(r["dd"], 2), ddc=round(r["ddc"], 2), trades=len(x))
    ref = {k: ref_bot(on, t0) for k, (on, t0) in cases.items()}
    json.dump(dict(cases={k: dict(on=v[0], t0=v[1], t1=T1) for k, v in cases.items()}, ref=ref), open(C.D.CACHE / "tbo_stats_ref.json", "w"))
    print(len(rows), "trades;", ref)
