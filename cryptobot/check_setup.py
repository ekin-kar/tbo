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
for c in cfgs:
    p = S.Params(**c["strategy"]); sym = p.symbol; risk = c["risk_pct"] / 100; sm = c.get("short_risk_mult", 1.0)
    total_risk += risk
    print(f" {sym}: risk {c['risk_pct']}% (shorts x{sm}), max leverage {c.get('max_leverage')}")
    try:
        f = x.exchange_info(sym); res(f["status"] == "TRADING", f"{sym} listed and trading")
        k4 = [k for k in x.klines(sym, "4h", 1001) if k[5] < x.now_ms()][-1000:]
        a = S.atr([k[2] for k in k4], [k[3] for k in k4], [k[4] for k in k4], p.atr_n)[-1]; px = k4[-1][4]
        dist = p.sl_atr * a
        for side, m in (("long", 1.0), ("short", sm)):
            qty = bal * risk * m / dist
            qty = min(qty, bal * c.get("max_leverage", 5) / px)
            qr = int(qty / max(f["step"], f["mkt_step"]) + 1e-9) * max(f["step"], f["mkt_step"])
            okq = qr >= f["min_qty"] and qr * px >= f["min_notional"]
            if side == "long":
                total_notional += qr * px / c.get("exchange_leverage", c.get("max_leverage", 5))
            res(okq, f"{side}: stop {dist / px * 100:.2f}% away -> {qr:g} {sym[:-4]} (${qr * px:,.0f} notional, risk ${qr * dist:.2f}; "
                     f"min {f['min_qty']:g} / ${f['min_notional']:g})" + ("" if okq else " -> too small: this trade would be skipped"), warn=not okq)
            if okq and qr * dist < 0.75 * bal * risk * m:
                res(False, f"{side}: rounding cuts the risk to ${qr * dist:.2f} of ${bal * risk * m:.2f} (step {f['step']:g})", warn=True)
        try:
            sc = x.symbol_config(sym); mt = str(sc.get("marginType", "?")).upper()
            res(mt in ("CROSSED", "CROSS"), f"margin type {mt}" + ("" if mt in ("CROSSED", "CROSS") else " (recommended: cross)"), warn=True)
        except Exception:
            pass
        x.open_algo_orders(sym); res(True, f"algo-order endpoint reachable for {sym}")
    except BinanceError as e:
        res(False, f"{sym}: {e}")
print(f" all coins in a trade at once: up to {total_risk * 100:.2f}% of the balance at risk (${bal * total_risk:.2f})")
if bal > 0:
    res(total_notional < 0.8 * bal, f"margin locked if all four are long at today's stops: ${total_notional:.2f} of ${bal:.2f}"
        + ("" if total_notional < 0.8 * bal else " (raise exchange_leverage in the configs)"), warn=True)
print("RESULT:", "ready" if ok_all else "fix the FAIL lines first")
