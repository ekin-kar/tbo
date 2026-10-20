"""
Pre-flight check before running live. Places NO orders.
    python check_setup.py            # live keys
    python check_setup.py --testnet  # testnet / demo keys
Checks: keys and permissions (withdrawals must be OFF), position mode, margin mode, balance, clock, the algo-order
endpoint, and for every coin whether the bot's position sizes at your risk settings clear Binance's minimums.
"""
import json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import notify, strategy as S                                    # noqa: E402
from binance_futures import Futures, BinanceError               # noqa: E402

notify.load_env(HERE / ".env")
testnet = "--testnet" in sys.argv
ok_all = True


def res(ok, msg, warn=False):
    global ok_all
    if not ok and not warn:
        ok_all = False
    print(f"  [{'OK  ' if ok else 'WARN' if warn else 'FAIL'}] {msg}")


cfgs = [json.loads(p.read_text()) for p in sorted(HERE.glob("config_*.json"))]
key, sec = os.environ.get("BINANCE_API_KEY", ""), os.environ.get("BINANCE_API_SECRET", "")
print(f"TBO pre-flight check ({'TESTNET' if testnet else 'LIVE'}), configs: {[c['strategy']['symbol'] for c in cfgs]}")
res(bool(key and sec), "API key and secret found (.env or environment)")
base = cfgs[0].get("base_url") if cfgs else None
try:
    x = Futures(key, sec, testnet=testnet, base_url=base)
    res(abs(x.offset) < 1000, f"clock offset vs Binance {x.offset} ms" + ("" if abs(x.offset) < 1000 else " (sync your system clock)"), warn=abs(x.offset) < 5000)
except Exception as e:
    res(False, f"cannot reach Binance futures at {base or ('testnet' if testnet else 'fapi.binance.com')}: {e}"); sys.exit(1)
try:
    acct = x.account(); bal = float(acct["totalMarginBalance"]); res(True, f"futures account reachable, balance {bal:.2f} USDT")
    res(bal >= 100, "balance at least 100 USDT", warn=True)
except BinanceError as e:
    res(False, f"futures account: {e} (key invalid, futures not enabled for the key, or IP not whitelisted)"); sys.exit(1)
if not testnet:
    try:
        r = x.api_restrictions()
        res(not r.get("enableWithdrawals", True), "withdrawals DISABLED on this key" if not r.get("enableWithdrawals") else "withdrawals are ENABLED on this key: disable them!")
        res(bool(r.get("enableFutures")), "futures trading enabled on this key")
        res(bool(r.get("ipRestrict")), "key restricted to your IP address(es)" if r.get("ipRestrict") else "key NOT IP-restricted (recommended: restrict to the bot's IP)", warn=True)
    except Exception as e:
        res(False, f"could not read key permissions: {e}", warn=True)
try:
    res(not x.hedge_mode(), "position mode One-way" if not x.hedge_mode() else "position mode is Hedge: switch to One-way in Binance Futures settings")
except BinanceError as e:
    res(False, f"position mode: {e}")
try:
    res(not x.multi_assets(), "single-asset margin (USDT)" if not x.multi_assets() else "multi-assets mode is ON (fine, but sizing uses total margin balance)", warn=True)
except Exception:
    pass
total_risk = 0.0; total_notional = 0.0
pf_path = Path(__file__).resolve().parent / "portfolio.json"
pf = json.loads(pf_path.read_text()) if pf_path.exists() else {}
# the bot sizes on this account + the panic sleeve's sub-account when its key is set (bot.equity, one pool)
eq, sub_bal = bal, None
if os.environ.get("PANIC_API_KEY") and os.environ.get("PANIC_API_SECRET") and pf.get("pool_panic_balance", True):
    try:
        sub_bal = float(Futures(os.environ["PANIC_API_KEY"], os.environ["PANIC_API_SECRET"], testnet=testnet).account()["totalMarginBalance"])
        eq = bal + sub_bal
        print(f" sizing balance: main ${bal:,.2f} + panic sub-account ${sub_bal:,.2f} = ${eq:,.2f} (the bot sizes on both)")
    except Exception as e:
        res(False, f"panic sub-account balance unreadable ({e}): sizes below use the main balance only", warn=True)
row = None
for r in sorted(pf.get("risk_ladder") or [], key=lambda r: float(r["from_usdt"])):
    if eq >= float(r["from_usdt"]):
        row = r
if pf.get("risk_ladder"):
    print(" risk ladder (portfolio.json), risk % by balance: " + " | ".join(
        f"from ${float(r['from_usdt']):,.0f}: BTC {r.get('BTCUSDT')} ETH {r.get('ETHUSDT')} alts {r.get('ADAUSDT')} cap {r.get('cap_pct')}"
        for r in sorted(pf["risk_ladder"], key=lambda r: float(r["from_usdt"]))))
    print(f" -> at your balance ${eq:,.2f} the row from ${float(row['from_usdt']):,.0f} applies" if row else " -> no row applies: config risk_pct")
for c in cfgs:
    p = S.Params(**c["strategy"]); sym = p.symbol; sm = c.get("short_risk_mult", 1.0)
    c = dict(c, risk_pct=float(row[sym]) if row and sym in row else c["risk_pct"])
    risk = c["risk_pct"] / 100
    total_risk += risk
    print(f" {sym}: risk {c['risk_pct']}% (shorts x{sm}), size cap {c.get('max_leverage')}x balance, Binance leverage {c.get('exchange_leverage', c.get('max_leverage'))}x")
    try:
        f = x.exchange_info(sym); res(f["status"] == "TRADING", f"{sym} listed and trading")
        k4 = [k for k in x.klines(sym, "4h", 1001) if k[5] < x.now_ms()][-1000:]
        a = S.atr([k[2] for k in k4], [k[3] for k in k4], [k[4] for k in k4], p.atr_n)[-1]; px = k4[-1][4]
        dist = p.sl_atr * a
        for side, m in (("long", 1.0), ("short", sm)):
            qty = eq * risk * m / dist
            qty = min(qty, eq * c.get("max_leverage", 5) / px)
            qr = int(qty / max(f["step"], f["mkt_step"]) + 1e-9) * max(f["step"], f["mkt_step"])
            okq = qr >= f["min_qty"] and qr * px >= f["min_notional"]
            if side == "long":
                total_notional += qr * px / c.get("exchange_leverage", c.get("max_leverage", 5))
            res(okq, f"{side}: stop {dist / px * 100:.2f}% away -> {qr:g} {sym[:-4]} (${qr * px:,.0f} notional, risk ${qr * dist:.2f}; "
                     f"min {f['min_qty']:g} / ${f['min_notional']:g})" + ("" if okq else " -> too small: this trade would be skipped"), warn=not okq)
            if okq and qr * dist < 0.75 * eq * risk * m:
                res(False, f"{side}: rounding cuts the risk to ${qr * dist:.2f} of ${eq * risk * m:.2f} (step {f['step']:g})", warn=True)
        try:
            sc = x.symbol_config(sym); mt = str(sc.get("marginType", "?")).upper()
            res(mt in ("CROSSED", "CROSS"), f"margin type {mt}" + ("" if mt in ("CROSSED", "CROSS") else " (recommended: cross)"), warn=True)
        except Exception:
            pass
        x.open_algo_orders(sym); res(True, f"algo-order endpoint reachable for {sym}")
        if p.oi_lookback_h > 0:
            try:
                hist = x.open_interest_hist(sym, limit=p.oi_lookback_h + 12)
                chg = S.oi_change(hist, x.now_ms(), p.oi_lookback_h)
                res(chg is not None, f"open interest data: {len(hist)} hourly rows" + (
                    f", {chg * 100:+.1f}% over {p.oi_lookback_h} h -> " + ("new entries PAUSED by the filter right now" if S.oi_blocks(p, chg)
                                                                          else "entries allowed") if chg is not None else
                    " but not enough recent rows (the filter is skipped until there are)"), warn=chg is None)
            except Exception as e:
                res(False, f"open interest data unavailable ({e}): the bot then trades without the filter", warn=True)
    except BinanceError as e:
        res(False, f"{sym}: {e}")
print(f" all coins in a trade at once: up to {total_risk * 100:.2f}% of the balance at risk (${eq * total_risk:.2f})")
cap = float(row["cap_pct"]) if row and "cap_pct" in row else float(pf.get("open_risk_cap_pct", 0) or 0)
if cap > 0:
    ex = [c["strategy"]["symbol"] for c in cfgs if c["strategy"]["symbol"] in pf.get("cap_exempt", [])]
    rk = lambda c: float(row[c["strategy"]["symbol"]]) if row and c["strategy"]["symbol"] in row else c["risk_pct"]
    capped = [rk(c) for c in cfgs if c["strategy"]["symbol"] not in ex] or [0]
    btc = next((rk(c) for c in cfgs if c["strategy"]["symbol"] == "BTCUSDT"), None)
    print(f" open-risk cap (portfolio.json): {cap:g}% of the balance (${eq * cap / 100:.2f})"
          + (f" = {cap / btc:.2f} x the BTC risk (tested best: about 1.1x)" if btc else "") + f"; never shrunk: {', '.join(ex) or 'none'}")
    res(cap >= max(capped), f"cap {cap:g}% vs the biggest capped coin risk {max(capped):g}%" + ("" if cap >= max(capped) else
        " -> that coin could never trade full size: raise the cap (about 1.1 x the BTC risk)"), warn=cap < max(capped))
    try:
        x.positions(); x.open_algo_orders(); res(True, "all-symbol position / order endpoints reachable (needed by the cap)")
    except BinanceError as e:
        res(False, f"all-symbol position / order endpoints: {e} (the cap then blocks new alt / ETH orders)")
else:
    print(" open-risk cap: off (no portfolio.json or open_risk_cap_pct 0)")
if bal > 0:
    res(total_notional < 0.8 * bal, f"margin locked if all coins are long at today's stops: ${total_notional:.2f} of ${bal:.2f} (main account)"
        + ("" if total_notional < 0.8 * bal else " (raise exchange_leverage in the configs)"), warn=True)
pk, ps = os.environ.get("PANIC_API_KEY", ""), os.environ.get("PANIC_API_SECRET", "")
if pk and ps:
    print("\nPANIC SLEEVE (sub-account, panic.py)")
    try:
        import panic as PN
        pcfg = PN.load_cfg()
        y = Futures(pk, ps, testnet=testnet)
        sub = float(y.account()["totalMarginBalance"]); res(True, f"sub-account reachable, balance {sub:.2f} USDT")
        if not testnet:
            r = y.api_restrictions()
            res(not r.get("enableWithdrawals", True), "withdrawals DISABLED on the sub-account key" if not r.get("enableWithdrawals") else "withdrawals ENABLED on the sub-account key: disable them!")
            res(bool(r.get("enableFutures")), "futures trading enabled on the sub-account key")
            res(bool(r.get("ipRestrict")), "sub-account key restricted to your IP" if r.get("ipRestrict") else "sub-account key NOT IP-restricted (recommended)", warn=True)
        res(not y.hedge_mode(), "sub-account position mode One-way" if not y.hedge_mode() else "sub-account is in Hedge mode: switch it to One-way")
        total = bal + sub
        res(sub >= 0.15 * total, f"sub-account holds {sub / total * 100:.0f}% of main + sub (${total:.2f}); 20-30% recommended"
            + ("" if sub >= 0.15 * total else " -> move more to the sub-account (panic trades are sized on main + sub)"), warn=True)
        btc = PN.ladder_btc_pct(total); units = float(pcfg.get("units", 3))
        risk = total * btc / 100 * units / 6
        print(f" {units:g} units per panic event = {units / 6 * btc:.2f}% of ${total:.2f} = ${risk:.2f} lost on a 5% move; position ${risk / 0.05:.2f}"
              f" (split over the coins that trigger in the same hour)")
        for sym in pcfg["coins"]:
            f = y.exchange_info(sym)
            for n in (1, 2):
                res(risk / 0.05 / n >= f["min_notional"], f"{sym} panic position with {n} coin(s) in the event: ${risk / 0.05 / n:.2f} vs Binance minimum ${f['min_notional']:g}",
                    warn=True)
        try:
            y.open_algo_orders(); x.premium_klines("BTCUSDT", "1h", 5); x.open_interest_hist("BTCUSDT", period="5m", limit=5)
            res(True, "algo orders, premium index and 5-minute open interest reachable")
        except BinanceError as e:
            res(False, f"panic data / orders: {e}")
    except BinanceError as e:
        res(False, f"sub-account: {e} (key invalid, futures not enabled for the key, or IP not whitelisted)")
    except Exception as e:
        res(False, f"panic sleeve check failed: {e}")
else:
    print("\nPANIC SLEEVE: off (no PANIC_API_KEY / PANIC_API_SECRET in .env)")
print("RESULT:", "ready" if ok_all else "fix the FAIL lines first")
