"""Optional Telegram alerts and .env loading (no extra packages).
.env next to the configs:  BINANCE_API_KEY=...  BINANCE_API_SECRET=...  TELEGRAM_TOKEN=...  TELEGRAM_CHAT_ID=..."""
import logging
import os
import threading
import time

import requests

KEYS = ("FILLED", "EXIT", "BREAKEVEN", "position closed", "STOP LOSS for", "market entry", "TBO v")


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


def send(text):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", data=dict(chat_id=chat, text=text[:3500]), timeout=10)
    except Exception:
        pass                                                   # alerts must never break trading


class TelegramHandler(logging.Handler):
    """Forwards trade events, warnings and errors (at most one message per 2 s, sent in a background thread)."""

    def __init__(self, tag):
        super().__init__(logging.INFO)
        self.tag, self.last = tag, 0.0

    def emit(self, record):
        msg = record.getMessage()
        if record.levelno < logging.WARNING and not any(k in msg for k in KEYS):
            return
        if time.time() - self.last < 2:
            return
        self.last = time.time()
        icon = "⚠️ " if record.levelno >= logging.WARNING else ""
        threading.Thread(target=send, args=(f"{icon}[{self.tag}] {msg}",), daemon=True).start()
