"""
Runs one bot process per config (default: every config_*.json here) and restarts any that stops.
    python run_all.py                 # live
    python run_all.py --testnet       # Binance futures testnet / demo keys
    python run_all.py --dry-run       # no orders, prints decisions
    python run_all.py config_btc.json config_eth.json   # only these
Stop with Ctrl+C (stops all bots; open positions keep their stop-loss on Binance).
To stop NEW entries but keep managing open trades: create an empty file named PAUSE in this folder.
"""
import subprocess, sys, time, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
flags = [a for a in sys.argv[1:] if a.startswith("--")]
cfgs = [a for a in sys.argv[1:] if not a.startswith("--")] or sorted(str(p.name) for p in HERE.glob("config_*.json"))
procs, fails, lock = {}, {c: 0 for c in cfgs}, threading.Lock()


def pump(cfg, p):
    tag = cfg.replace("config_", "").replace(".json", "").upper()
    for line in p.stdout:
        with lock:
            print(f"{tag:5s} | {line.rstrip()}", flush=True)


def start(cfg):
    p = subprocess.Popen([sys.executable, "-u", str(HERE / "bot.py"), str(HERE / cfg)] + flags, cwd=HERE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    threading.Thread(target=pump, args=(cfg, p), daemon=True).start()
    procs[cfg] = (p, time.time())


print(f"TBO launcher: {', '.join(cfgs)} {' '.join(flags)}", flush=True)
for c in cfgs:
    start(c); time.sleep(2)                      # stagger start-up requests
try:
    while True:
        time.sleep(5)
        for c, (p, t0) in list(procs.items()):
            if p.poll() is not None:
                fails[c] = fails[c] + 1 if time.time() - t0 < 300 else 1
                wait = 5 if fails[c] == 1 else 60
                print(f"{c}: bot stopped (exit code {p.returncode}); restarting in {wait} s", flush=True)
                time.sleep(wait); start(c)
except KeyboardInterrupt:
    print("stopping all bots (stop-losses stay on Binance)", flush=True)
    for p, _ in procs.values():
        p.terminate()
