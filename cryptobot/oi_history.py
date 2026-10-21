"""
Hourly open interest (USD value) for the OI-low filter (v2.8), which needs more history than Binance's API keeps
(openInterestHist: the last 30 days, 500 rows per call). The older part comes from Binance's public daily archive
(data.binance.vision, the same numbers the research used); the last ~20 days from the API. One row per hour,
cached in oi_<SYMBOL>.json next to the configs so a restart only fetches what is new.
"""
import csv
import io
import json
import logging
import time
import zipfile
from datetime import datetime, timedelta, timezone

import requests

ARCH = "https://data.binance.vision/data/futures/um/daily/metrics"
HOUR = 3600_000
log = logging.getLogger("tbo")


class OIHistory:
    def __init__(self, x, sym, days, folder, suffix=""):
        self.x, self.sym, self.days = x, sym, int(days)
        self.path = folder / f"oi_{sym}{suffix}.json"
        self.rows, self.done = {}, set()                 # hour start (ms) -> (sample ms, value); archive days fetched
        try:
            c = json.loads(self.path.read_text())
            self.rows = {int(k): tuple(v) for k, v in c.get("rows", {}).items()}
            self.done = set(c.get("days", []))
        except (OSError, ValueError):
            pass
        self.s = requests.Session()

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(rows={str(k): list(v) for k, v in self.rows.items()}, days=sorted(self.done))))
        tmp.replace(self.path)

    def _day(self, day):
        """One archive day: the last 5-minute row of each hour (as research/crypto/core/fetch_binance_extra.py).
        None = not published yet / unreachable; [] = no file for that day (coin not listed yet)."""
        try:
            r = self.s.get(f"{ARCH}/{self.sym}/{self.sym}-metrics-{day}.zip", timeout=20)
        except requests.RequestException:
            return None
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            return None
        z = zipfile.ZipFile(io.BytesIO(r.content))
        rd = list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
        if not rd:
            return []
        col = rd[0].index("sum_open_interest_value")
        keep = {}
        for row in rd[1:]:
            keep[row[0][:13]] = row
        out = []
        for row in keep.values():
            t = int(datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)
            out.append((t, float(row[col] or 0)))
        return out

    def update(self, budget_s=None):
        """Fetch the archive days still missing (oldest first; stops after budget_s seconds, the rest next time) and
        the API's last 500 hours."""
        t_end = None if budget_s is None else time.time() + budget_s
        now = self.x.now_ms()
        today = datetime.fromtimestamp(now / 1000, timezone.utc).date()
        want = [str(today - timedelta(days=d)) for d in range(self.days + 2, 1, -1)]   # up to the day before yesterday
        todo = [d for d in want if d not in self.done]
        api_from = None
        try:
            api = self.x.open_interest_hist(self.sym, period="1h", limit=500)
            api_from = api[0][0] if api else None
        except Exception as e:
            api = []
            log.warning(f"open interest history (API) unavailable: {e}")
        # archive days the API already covers are not needed
        if api_from is not None:
            todo = [d for d in todo if datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000 + 86400_000 <= api_from + HOUR]
        n = 0
        for d in todo:
            if t_end is not None and time.time() > t_end:
                break
            got = self._day(d)
            if got is None:
                continue
            for t, v in got:
                if v > 0:
                    self.rows.setdefault(t - t % HOUR, (t, v))
            self.done.add(d)
            n += 1
        for t, v in api:                                 # the API wins where both have the hour
            if v > 0:
                self.rows[t - t % HOUR] = (t, v)
        old = now - (self.days + 3) * 86400_000
        self.rows = {k: v for k, v in self.rows.items() if k >= old}
        self.done = {d for d in self.done if d >= str(today - timedelta(days=self.days + 3))}
        self.save()
        if n:
            log.debug(f"open interest history: {n} archive day(s) added, {len(self.rows)} hours known")
        return n

    def series(self):
        """[(sample ms, value), ...] oldest first, one row per hour."""
        return [self.rows[k] for k in sorted(self.rows)]

    def hours(self):
        return len(self.rows)
