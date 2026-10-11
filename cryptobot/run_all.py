"""
Runs one bot process per config (default: every config_*.json here) and restarts any that stops.
    python run_all.py                 # live
    python run_all.py --testnet       # Binance futures testnet / demo keys
    python run_all.py --dry-run       # no orders, prints decisions
    python run_all.py config_btc.json config_eth.json   # only these
Stop with Ctrl+C (stops all bots; open positions keep their stop-loss on Binance).
To stop NEW entries but keep managing open trades: create an empty file named PAUSE in this folder.
Telegram (if set in .env): one message when the bots start, one after every 4h check (all coins together); the bots
themselves send their trade events (opened, breakeven, profit lock, closed, cap cuts) and warnings.
"""
import json, subprocess, sys, time, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import notify                                    # noqa: E402

flags = [a for a in sys.argv[1:] if a.startswith("--")]
cfgs = [a for a in sys.argv[1:] if not a.startswith("--")] or sorted(str(p.name) for p in HERE.glob("config_*.json"))
procs, fails, lock = {}, {c: 0 for c in cfgs}, threading.Lock()
notify.load_env(HERE / ".env")
TESTNET, DRY = "--testnet" in flags, "--dry-run" in flags
MODE = " <i>(dry run)</i>" if DRY else " <i>(testnet)</i>" if TESTNET else ""
TF_MS = 4 * 3600_000


def cfg_of(c):
    return json.loads((HERE / c).read_text())


ORDER = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
SYMS = sorted((cfg_of(c)["strategy"]["symbol"] for c in cfgs), key=lambda s: (ORDER.index(s) if s in ORDER else 99, s))
COIN = {s: s[:-4] for s in SYMS}


def pump(cfg, p):
    tag = cfg.replace("config_", "").replace(".json", "").upper()
    for line in p.stdout:
        with lock:
            print(f"{time.strftime('%H:%M:%S')}  {tag:<4s} {line.rstrip()}", flush=True)


def publish(msg):
    """A status message: the console (plain text) and Telegram (formatted)."""
    with lock:
        print("\n" + notify._plain(msg).replace("\n", "\n   ") + "\n", flush=True)
    notify.send(msg)


def start(cfg):
    p = subprocess.Popen([sys.executable, "-u", str(HERE / "bot.py"), str(HERE / cfg)] + flags, cwd=HERE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    threading.Thread(target=pump, args=(cfg, p), daemon=True).start()
    procs[cfg] = (p, time.time())


# ── Telegram ──
def account():
    """(balance, exchange clock ms) or (None, local ms)."""
    try:
        import os
        from binance_futures import Futures
        if DRY:
            return float(cfg_of(cfgs[0]).get("dry_run_equity", 1000)), int(time.time() * 1000)
        x = Futures(os.environ.get("BINANCE_API_KEY", ""), os.environ.get("BINANCE_API_SECRET", ""), testnet=TESTNET)
        return float(x.account()["totalMarginBalance"]), x.now_ms()
    except Exception:
        return None, int(time.time() * 1000)


def portfolio():
    try:
        return json.loads((HERE / "portfolio.json").read_text())
    except (OSError, ValueError):
        return {}


def ladder_row(eq):
    row = None
    for r in sorted(portfolio().get("risk_ladder") or [], key=lambda r: float(r["from_usdt"])):
        if eq is not None and eq >= float(r["from_usdt"]):
            row = r
    return row


def risk_text(eq):
    row = ladder_row(eq)
    if row:
        alts = [s for s in SYMS if s not in ("BTCUSDT", "ETHUSDT")]
        parts = [f"{COIN[s]} {row[s]:g}%" for s in SYMS if s in ("BTCUSDT", "ETHUSDT") and s in row]
        if alts:
            parts.append(f"{'/'.join(COIN[s] for s in alts)} {row.get(alts[0], 0):g}% each")
        return " · ".join(parts), float(row.get("cap_pct", 0))
    parts = [f"{COIN[s]} {cfg_of(c)['risk_pct']:g}%" for c, s in zip(cfgs, SYMS)]
    return " · ".join(parts), float(portfolio().get("open_risk_cap_pct", 0) or 0)


def state(sym):
    try:
        return json.loads((HERE / f"state_{sym}{'_testnet' if TESTNET else ''}.json").read_text())
    except (OSError, ValueError):
        return {}


def coin_lines(t_close):
    """One line per coin (one line for all when they all say the same, e.g. the weekend)."""
    texts, risk = {}, 0.0
    for s in SYMS:
        ck = state(s).get("check") or {}
        if ck.get("t") == t_close:
            texts[s] = notify.esc(ck.get("line", ""))
            risk += float(ck.get("risk", 0) or 0)
        else:
            texts[s] = "<i>no report yet</i>"
    if len(SYMS) > 1 and len(set(texts.values())) == 1:
        return [f"<b>All coins</b> {texts[SYMS[0]]}"], risk
    return [f"<b>{COIN[s]}</b> {texts[s]}" for s in SYMS], risk


def wait_reports(t_close, max_s):
    t0 = time.time()
    while time.time() - t0 < max_s:
        if all((state(s).get("check") or {}).get("t") == t_close for s in SYMS):
            return
        time.sleep(5)


def startup_message():
    eq, now = account()
    last = now // TF_MS * TF_MS
    wait_reports(last, 120)                       # the bots act on the last 4h close right after starting
    rtext, cap = risk_text(eq)
    st0 = json.loads((HERE / cfgs[0]).read_text())["strategy"]
    rows = [f"🟢 <b>TBO v{bot_version()} online</b>{MODE}",
            f"Balance <b>{notify.usd(eq)}</b>" if eq is not None else "Balance: not readable right now",
            f"Coins {' · '.join(COIN[s] for s in SYMS)}",
            f"Risk per trade {rtext} (shorts half)",
            f"Open-risk cap {cap:g}% of the balance (BTC exempt)" if cap else "Open-risk cap off",
            f"Exits: stop 1 ATR · breakeven at +{st0.get('be_R', 1.5):g}R · +{st0.get('lock_R', 5):g}R locks "
            f"+{st0.get('lock_to', 1.5):g}R · time exit after {st0.get('max_hold_h', 120) / 24:g} days",
            "", f"<b>Status</b> at the last 4h check ({notify.when(last)}, {notify.tz_label()})"]
    lines, _ = coin_lines(last)
    rows += lines
    rows += ["", f"Next check {notify.when(last + TF_MS, day=False)}"]
    publish("\n".join(rows))


def bot_version():
    for line in (HERE / "bot.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("VERSION"):
            return line.split("=")[1].strip().strip('"')
    return "?"


def check_message(nxt):
    eq, _ = account()
    lines, risk = coin_lines(nxt)
    _, cap = risk_text(eq)
    foot = f"Balance {notify.usd(eq)}" if eq is not None else "Balance not readable"
    if eq:
        foot += f" · open risk {notify.usd(risk)} ({risk / eq * 100:.1f}%)" + (f" · cap {cap:g}%" if cap else "")
    return "\n".join([f"🕓 <b>4h check</b> · {notify.when(nxt)} ({notify.tz_label()}){MODE}"] + lines
                     + ["", foot, f"Next check {notify.when(nxt + TF_MS, day=False)}"])


def check_loop():
    """After every 4h close: one message with every coin's status."""
    while True:
        now = int(time.time() * 1000)
        nxt = now // TF_MS * TF_MS + TF_MS
        time.sleep(max(1.0, (nxt - now) / 1000 + 20))
        wait_reports(nxt, 240)
        publish(check_message(nxt))


def main():
    mode = "dry run" if DRY else "testnet" if TESTNET else "live"
    print(f"TBO launcher · {mode} · {' '.join(COIN[s] for s in SYMS)}"
          f" · Telegram {'on' if notify.enabled() else 'off'}", flush=True)
    by_sym = {cfg_of(c)["strategy"]["symbol"]: c for c in cfgs}
    for s_ in SYMS:                                  # BTC first, then ETH, BNB, SOL, ADA
        start(by_sym[s_]); time.sleep(2)             # stagger start-up requests
    threading.Thread(target=startup_message, daemon=True).start()
    threading.Thread(target=check_loop, daemon=True).start()
    try:
        while True:
            time.sleep(5)
            for c, (p, t0) in list(procs.items()):
                if p.poll() is not None:
                    fails[c] = fails[c] + 1 if time.time() - t0 < 300 else 1
                    wait = 5 if fails[c] == 1 else 60
                    print(f"{time.strftime('%H:%M:%S')}  {c}: bot stopped (exit code {p.returncode}); restarting in {wait} s", flush=True)
                    notify.send(f"♻️ <b>{COIN.get(cfg_of(c)['strategy']['symbol'], c)}</b> bot stopped (exit code {p.returncode}) · "
                                f"restarting in {wait} s")
                    time.sleep(wait); start(c)
    except KeyboardInterrupt:
        print("stopping all bots (stop-losses stay on Binance)", flush=True)
        notify.send("🔴 <b>TBO stopped</b>\nOpen trades keep their stop loss on Binance; no new orders until it runs again.", wait=True)
        for p, _ in procs.values():
            p.terminate()


if __name__ == "__main__":
    main()
