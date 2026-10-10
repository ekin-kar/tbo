"""Telegram messages and .env loading (no extra packages).
.env next to the configs:  BINANCE_API_KEY=...  BINANCE_API_SECRET=...  TELEGRAM_TOKEN=...  TELEGRAM_CHAT_ID=...
Optional: TELEGRAM_UTC_OFFSET=3 shows times in UTC+3 (default: the computer's own time zone).

The bots send their own trade events (opened, breakeven, profit lock, closed, cap cuts) and warnings; run_all.py sends
one start-up message and one combined message after every 4h check. Messages use Telegram's HTML formatting."""
import html
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

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
