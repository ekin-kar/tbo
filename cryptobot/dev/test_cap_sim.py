"""
Open-risk cap test: the five coin bots (bot.py, live configs) run together on ONE simulated account fed with historical
1m bars, with portfolio.json's cap. Every entry is then checked against the rule the research simulation uses
(research/crypto/studies/sizing_v4.py, cap checked at the fill):
  * BTC (exempt) always trades its full size
  * any other coin: risk = its normal risk if it fits under cap x equity together with the risk (not yet at
    breakeven) of the coins that filled before it, otherwise the room left (or no trade if < cap_min_fraction fits)

    python cryptobot/dev/test_cap_sim.py [2024-01-01] [2024-07-01]
    CAPSIM_PORTFOLIO=other.json CAPSIM_EQ=500 python cryptobot/dev/test_cap_sim.py ...   # another portfolio file / balance
"""
import json
import logging
import os
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]            # the cryptobot folder (this file is in cryptobot/dev)
sys.path[:0] = [str(HERE), str(Path(__file__).resolve().parent)]
import bot as B                                      # noqa: E402
import strategy as S                                 # noqa: E402
from replay import C                                 # noqa: E402
from test_bot_sim import FakeFutures                 # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
EQ = float(os.environ.get("CAPSIM_EQ", 10_000))
PF = Path(os.environ.get("CAPSIM_PORTFOLIO", HERE / "portfolio.json"))


def coin_risk(pf, sym, cfg):
    """(risk %, cap %) at the test balance: the ladder row if portfolio.json has one, else the config / cap."""
    rows = [r for r in sorted(pf.get("risk_ladder") or [], key=lambda r: r["from_usdt"]) if EQ >= r["from_usdt"]]
    row = rows[-1] if rows else {}
    return float(row.get(sym, cfg["risk_pct"])), float(row.get("cap_pct", pf.get("open_risk_cap_pct", 0)))


def run(start, end):
    pf = json.loads(PF.read_text())
    tmp = Path(f"/tmp/claude_tbo_capsim_{os.getpid()}"); shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
    (tmp / "portfolio.json").write_text(json.dumps(pf))
    fxs, bots = [], []
    for sym in COINS:
        cfg = json.loads((HERE / f"config_{sym[:-4].lower()}.json").read_text())
        m = C.load(sym)
        fx = FakeFutures(m, tick=FakeFutures.exchange_info(None, sym)["tick"], sym=sym)
        b = B.Bot.__new__(B.Bot)
        b.cfg, b.dry, b.p, b.sym = cfg, False, S.Params(**cfg["strategy"]), sym
        b.risk, b.short_mult = cfg["risk_pct"] / 100, cfg.get("short_risk_mult", 1.0)
        b.max_lev, b.poll, b.dir, b.suffix = cfg["max_leverage"], 0, tmp, ""
        b.state_path = tmp / f"state_{sym}.json"; b.x = fx; b.f = fx.exchange_info(sym)
        b.st = dict(last_candle=0, entry_id=None, entry_side=0, sl_dist=0.0, sl_id=None, entry_ms=0)
        fxs.append(fx); bots.append(b)
    for fx in fxs:
        fx.group = fxs
        fx.account = lambda: {"totalMarginBalance": str(EQ)}
    t0, t1 = C.D.minutes(start), C.D.minutes(end)
    clock = fxs[0].m["t"]; clock = clock[(clock >= t0) & (clock < t1)]
    idx = [np.searchsorted(fx.m["t"], clock) for fx in fxs]
    tf_ms = 240 * 60_000
    for k, t in enumerate(clock):
        live = []
        for i, (fx, b) in enumerate(zip(fxs, bots)):
            j = idx[i][k]
            if j >= len(fx.m["t"]) or fx.m["t"][j] != t:
                continue                                   # no bar for this coin this minute
            fx.j = j; live.append(i)
            now = fx.now_ms(); last_open = (now // tf_ms) * tf_ms - tf_ms
            if b.st["last_candle"] < last_open:
                b.on_candle_close(last_open)
            b.check_position()
        for i in live:
            fxs[i].process_bar()
    return fxs, pf


def trades_of(fx):
    """Round trips with every fill: entry time/price/qty, cuts, exit time; stops from the stop-loss log."""
    out, cur = [], None
    for t, d, q, px, kind in fx.fills:
        if cur is None:
            cur = dict(sym=fx.sym, t=t, dir=d, entry=px, qty=q, cut=0.0, exit=None)
        elif d == cur["dir"]:
            cur["qty"] += q
        elif kind == "market" and round(q, 9) < round(cur["qty"] - cur["cut"], 9):
            cur["cut"] += q; cur["cut_t"] = t
        else:
            cur.update(exit=t, how=kind); out.append(cur); cur = None
    if cur:
        cur.update(exit=10 ** 12, how=None); out.append(cur)
    for tr in out:                                         # first stop = risk at entry; a later stop at entry = breakeven
        sls = [(t, trig) for t, trig in fx.sl_log if tr["t"] <= t <= tr["exit"]]
        tr["stop"] = sls[0][1] if sls else np.nan
        be = [t for t, trig in sls[1:] if abs(trig - tr["entry"]) <= 0.002 * tr["entry"]]
        tr["be"] = be[0] if be else tr["exit"]
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    seen = {"held back (no room)": "no entry order for now", "order resized": "CAP: entry order", "breakout while full": "breakout happened while",
            "cut after the fill": "CAP after the fill", "account unreadable": "open risk unavailable"}
    counts = dict.fromkeys(seen, 0)

    class Count(logging.Handler):
        def emit(self, r):
            for k, v in seen.items():
                counts[k] += v in r.getMessage()
    lg = logging.getLogger("tbo"); lg.setLevel(logging.INFO); lg.propagate = False; lg.addHandler(Count())
    start = sys.argv[1] if len(sys.argv) > 1 else "2024-01-01"
    end = sys.argv[2] if len(sys.argv) > 2 else "2024-07-01"
    fxs, pf = run(start, end)
    print(f"balance {EQ:,.0f}, portfolio {PF.name}: " + ", ".join(f"{s[:-4]} {coin_risk(pf, s, json.loads((HERE / f'config_{s[:-4].lower()}.json').read_text()))[0]:g}%" for s in COINS)
          + f", cap {coin_risk(pf, 'ETHUSDT', {'risk_pct': 0})[1]:g}%")
    ex, mf = set(pf["cap_exempt"]), pf.get("cap_min_fraction", 0.25)
    cfg = {s: json.loads((HERE / f"config_{s[:-4].lower()}.json").read_text()) for s in COINS}
    T = sorted([tr for fx in fxs for tr in trades_of(fx)], key=lambda r: r["t"])
    bad, n_short, n_full = [], 0, 0
    for i, tr in enumerate(T):
        dist = abs(tr["entry"] - tr["stop"])
        c = cfg[tr["sym"]]
        rp, cp = coin_risk(pf, tr["sym"], c); cap = cp / 100
        want = EQ * rp / 100 * (c.get("short_risk_mult", 1) if tr["dir"] < 0 else 1)
        lev_cap = EQ * c["max_leverage"] / tr["entry"] * dist                     # risk at the leverage size cap
        have = (tr["qty"] - tr["cut"]) * dist
        if tr["how"] == "market" and tr["exit"] - tr["t"] <= 2 and not np.isnan(tr["stop"]):
            have = 0.0; tr["closed_at_once"] = True     # closed right after the fill (the cap had no room)
        others = sum(abs(o["entry"] - o["stop"]) * (o["qty"] - o["cut"]) for o in T[:i]
                     if o["sym"] != tr["sym"] and o["exit"] > tr["t"] and o["be"] > tr["t"])
        exp = want
        if tr["sym"] not in ex:
            room = cap * EQ - others
            exp = want if want <= room else (room if room > mf * want else 0.0)
        exp = min(exp, lev_cap)
        step = max(FakeFutures.exchange_info(None, tr["sym"])["step"], 1e-12) * dist
        ok = (abs(have - exp) <= 0.06 * exp + 2 * step) if exp > 0 else have <= 2 * step
        n_short += have < 0.94 * min(want, lev_cap); n_full += not (have < 0.94 * min(want, lev_cap))
        if not ok:
            bad.append((tr["sym"], C.D.to_datetime([tr["t"]])[0], round(want, 1), round(others, 1), round(exp, 1), round(have, 1)))
    print(f"{len(T)} entries on one account {start}..{end}: {n_full} full size, {n_short} shrunk by the cap; "
          f"cut after the fill: {sum(1 for tr in T if tr['cut'] > 0)}, closed at once after the fill: {sum(1 for tr in T if tr.get('closed_at_once'))}")
    btc = [tr for tr in T if tr["sym"] == "BTCUSDT"]
    cb = cfg["BTCUSDT"]
    full = [(tr["qty"] - tr["cut"]) * abs(tr["entry"] - tr["stop"]) >= 0.94 * min(EQ * coin_risk(pf, "BTCUSDT", cb)[0] / 100 * (cb["short_risk_mult"] if tr["dir"] < 0 else 1),
                                                                          EQ * cb["max_leverage"] / tr["entry"] * abs(tr["entry"] - tr["stop"])) for tr in btc]
    print(f"BTC entries: {len(btc)}, full size: {sum(full)} (exempt from the cap)")
    print("cap actions:", counts)
    print(f"entries off the rule (> 6% from the expected risk): {len(bad)}")
    for b in bad[:20]:
        print("  ", b)
