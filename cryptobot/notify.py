"""Telegram messages and .env loading (no extra packages).
.env in TBO_SECRETS_DIR (outside the repo; default ~/tbo-secrets, on Windows %USERPROFILE%\tbo-secrets), or for
servers set up by vds_setup.sh next to the configs:  BINANCE_API_KEY=...  BINANCE_API_SECRET=...  TELEGRAM_TOKEN=...  TELEGRAM_CHAT_ID=...
Optional: TELEGRAM_UTC_OFFSET=3 shows times in UTC+3 (default: the computer's own time zone).

The bots send their own trade events (opened, breakeven, profit lock, closed, cap cuts) and warnings; run_all.py sends
one start-up message and answers /status (listen()). Messages use Telegram's HTML formatting."""
import html
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


def load_env(path):
    """KEY=VALUE lines; values already set in the environment win."""
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


def secrets_dir():
    """The private-files folder outside the repo: $TBO_SECRETS_DIR, else ~/tbo-secrets (%USERPROFILE%\tbo-secrets)."""
    d = os.environ.get("TBO_SECRETS_DIR")
    return Path(d).expanduser() if d else Path.home() / "tbo-secrets"


def load_secrets_env(bot_dir):
    """Load .env from the secrets folder; a server set up by vds_setup.sh keeps its .env in the bot folder
    (bot_dir), which is used when the secrets folder has none. Returns the file loaded, or None."""
    for p in (secrets_dir() / ".env", Path(bot_dir) / ".env"):
        if p.is_file():
            load_env(p)
            return p
    print(f"WARNING: no .env file found. Looked in {secrets_dir() / '.env'} and {Path(bot_dir) / '.env'}. "
          "Put .env in the secrets folder (or set TBO_SECRETS_DIR); only keys already in the environment are used.",
          file=sys.stderr)
    return None


def enabled():
    return bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _post(text):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    for _ in range(3):
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=10,
                              data=dict(chat_id=chat, text=text[:4000], parse_mode="HTML", disable_web_page_preview="true"))
            if r.status_code == 200:
                return
            if r.status_code == 400:                       # formatting refused: send it as plain text
                requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=10,
                              data=dict(chat_id=chat, text=_plain(text)[:4000]))
                return
        except Exception:
            pass                                           # alerts must never break trading
        time.sleep(2)


def _plain(text):
    for t in ("<b>", "</b>", "<i>", "</i>", "<code>", "</code>"):
        text = text.replace(t, "")
    return html.unescape(text)


def send(text, wait=False):
    """Send in the background (wait=True: before returning, e.g. right before the program exits)."""
    if not enabled():
        return
    if wait:
        _post(text)
    else:
        threading.Thread(target=_post, args=(text,), daemon=True).start()


def listen(commands, log=print):
    """Answer commands typed in the chat (only from TELEGRAM_CHAT_ID), e.g. {"status": ("description", fn)}; fn()
    returns the reply text. Runs forever (long polling); adds the commands to the bot's / menu. One server per bot
    token: a second program polling the same token gets HTTP 409 and the commands go to one of them only."""
    if not enabled():
        return
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), str(os.environ.get("TELEGRAM_CHAT_ID")).strip()
    api = f"https://api.telegram.org/bot{tok}"
    try:
        requests.post(f"{api}/setMyCommands", timeout=10,
                      json=dict(commands=[dict(command=c, description=d) for c, (d, _) in commands.items()]))
    except Exception:
        pass
    offset, warned = None, 0.0
    try:                                                   # skip commands typed while the bot was not running
        old = requests.get(f"{api}/getUpdates", timeout=15, params=dict(offset=-1, timeout=0)).json().get("result", [])
        offset = old[-1]["update_id"] + 1 if old else None
    except Exception:
        pass
    while True:
        try:
            r = requests.get(f"{api}/getUpdates", timeout=60,
                             params=dict(timeout=50, offset=offset, allowed_updates='["message"]'))
            if r.status_code != 200:
                if time.time() - warned > 3600:
                    log(f"Telegram commands unavailable (HTTP {r.status_code}"
                        f"{': is another program using the same bot token?' if r.status_code == 409 else ''})")
                    warned = time.time()
                time.sleep(30)
                continue
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                m = u.get("message") or {}
                if str((m.get("chat") or {}).get("id")) != chat:
                    continue
                word = (m.get("text") or "").strip().split(" ")[0].split("@")[0].lstrip("/").lower()
                if word in commands:
                    try:
                        _post(commands[word][1]())
                    except Exception as e:
                        _post(f"❗ /{esc(word)} failed: {esc(e)}")
        except Exception:
            time.sleep(10)


# ── formatting ──
def esc(s):
    return html.escape(str(s), quote=False)


def _tz():
    off = os.environ.get("TELEGRAM_UTC_OFFSET")
    if off not in (None, ""):
        try:
            return timezone(timedelta(hours=float(off)))
        except ValueError:
            pass
    return datetime.now().astimezone().tzinfo


def tz_label():
    d = datetime.now(_tz()).utcoffset() or timedelta(0)
    h = d.total_seconds() / 3600
    return "UTC" if h == 0 else f"UTC{h:+g}"


def when(ms, day=True):
    """'Mon 12 Oct 23:15' in the chosen time zone (day=False: '23:15')."""
    t = datetime.fromtimestamp(ms / 1000, _tz())
    return t.strftime("%a %d %b %H:%M") if day else t.strftime("%H:%M")


def px(x, tick=None):
    """A price with the coin's decimals and thousands separators."""
    if tick:
        dec = max(0, len(f"{tick:.10f}".rstrip("0").split(".")[1])) if tick < 1 else 0
    else:
        dec = 2 if abs(x) >= 100 else 4 if abs(x) >= 1 else 6
    return f"{x:,.{dec}f}"


def usd(x, sign=False):
    s = f"{abs(x):,.2f}"
    return (("+" if x >= 0 else "−") if sign else ("−" if x < 0 else "")) + "$" + s


def num(x, dec=2, sign=False):
    return (f"{x:+.{dec}f}" if sign else f"{x:.{dec}f}").replace("-", "−")


def pct(x, sign=False, dec=2):
    return num(x, dec, sign) + "%"


def held(ms):
    m = int(ms // 60_000); d, m = divmod(m, 1440); h, m = divmod(m, 60)
    return f"{d}d {h}h" if d else f"{h}h {m}m" if h else f"{m}m"


class TelegramHandler(logging.Handler):
    """Forwards only warnings and errors (trade events are sent as their own messages). The same message is not
    repeated within 30 minutes, so a network hiccup does not flood the chat."""

    def __init__(self, tag):
        super().__init__(logging.WARNING)
        self.tag, self.seen = tag, {}

    def emit(self, record):
        msg = record.getMessage()
        key = "".join(ch for ch in msg if not ch.isdigit())[:120]
        now = time.time()
        if now - self.seen.get(key, 0) < 1800:
            return
        self.seen[key] = now
        icon = "❗" if record.levelno >= logging.ERROR else "⚠️"
        send(f"{icon} <b>{esc(self.tag)}</b> · {esc(msg)}")
