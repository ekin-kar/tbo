"""Downloads the extra Binance data for ideas 6, 7 and 10 from Binance's public archive data.binance.vision
(standard library + requests).
Run from the repo root:   python research/crypto/fetch_binance_extra.py
Writes data/extra/ (gzipped CSV, about 15 MB in total), then:   git add data/extra && git commit -m "extra data" && git push
  - {SYM}_funding.csv.gz   every funding payment since the coin listed (time, rate)          -> ideas 6 and 10
  - {SYM}_4h.csv.gz        4h candles incl. taker buy volume (aggressive buyers), 2020-01+   -> idea 7
  - {SYM}_metrics_1h.csv.gz open interest, long/short ratios, taker buy/sell ratio, hourly,
                           from Binance's public archive (starts Dec 2021)                    -> idea 6
Safe to re-run: finished files are skipped."""
import csv, gzip, io, os, sys, time, zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import requests

COINS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]
FAPI = "https://fapi.binance.com"
ARCH = "https://data.binance.vision/data/futures/um/daily/metrics"
MONTHLY = "https://data.binance.vision/data/futures/um/monthly"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "data", "extra")
START = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
S = requests.Session()


def get(url, params=None, tries=6):
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=30)
            if r.status_code == 404:
                return None
            if r.status_code in (418, 429) or r.status_code >= 500:
                time.sleep(2 ** i); continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            time.sleep(2 ** i)
    raise RuntimeError(f"failed: {url} {params}")


def write(path, header, rows):
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    os.replace(tmp, path)


def months():
    d = date(2020, 1, 1); out = []
    while d < date.today().replace(day=1):
        out.append(d.strftime("%Y-%m")); d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def monthly_rows(kind, sym, sub=""):
    """All rows of Binance's monthly archive files (data.binance.vision), header lines dropped."""
    def one(mo):
        name = f"{sym}-{sub + '-' if sub else ''}{mo}.zip" if kind.endswith(("klines", "Klines")) else f"{sym}-fundingRate-{mo}.zip"
        url = f"{MONTHLY}/{kind}/{sym}/{sub + '/' if sub else ''}{name}"
        r = get(url)
        if r is None:
            return []
        z = zipfile.ZipFile(io.BytesIO(r.content))
        rows = list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
        return [x for x in rows if x and x[0][:1].isdigit()]
    with ThreadPoolExecutor(8) as ex:
        return [r for part in ex.map(one, months()) for r in part]


def funding(sym):
    path = os.path.join(OUT, f"{sym}_funding.csv.gz")
    if os.path.exists(path):
        return
    rows = [(r[0], r[-1]) for r in monthly_rows("fundingRate", sym)]      # calc_time, ..., last_funding_rate
    write(path, ["time_ms", "rate"], sorted(rows, key=lambda x: int(x[0])))
    print(f"{sym}: {len(rows)} funding payments")


def klines(sym):
    path = os.path.join(OUT, f"{sym}_4h.csv.gz")
    if os.path.exists(path):
        return
    rows = [(k[0], k[1], k[2], k[3], k[4], k[5], k[7], k[8], k[9], k[10]) for k in monthly_rows("klines", sym, "4h")]
    write(path, ["open_ms", "o", "h", "l", "c", "volume", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote"],
          sorted(rows, key=lambda x: int(x[0])))
    print(f"{sym}: {len(rows)} 4h candles")


def metrics_day(sym, day):
    r = get(f"{ARCH}/{sym}/{sym}-metrics-{day.isoformat()}.zip")
    if r is None:
        return []
    z = zipfile.ZipFile(io.BytesIO(r.content))
    txt = z.read(z.namelist()[0]).decode()
    rd = list(csv.reader(io.StringIO(txt)))
    head, body = rd[0], rd[1:]
    keep = {}
    for row in body:                       # 5-minute rows -> the last one of each hour
        keep[row[0][:13]] = row
    return [head] + list(keep.values())


def metrics(sym):
    path = os.path.join(OUT, f"{sym}_metrics_1h.csv.gz")
    if os.path.exists(path):
        return
    days = [date(2021, 12, 1) + timedelta(d) for d in range((date.today() - date(2021, 12, 1)).days)]
    with ThreadPoolExecutor(8) as ex:
        parts = list(ex.map(lambda d: metrics_day(sym, d), days))
    head = next((p[0] for p in parts if p), None)
    rows = [r for p in parts if p for r in p[1:]]
    if head is None:
        print(f"{sym}: no metrics files found"); return
    write(path, head, rows)
    print(f"{sym}: {len(rows)} hourly metrics rows ({sum(1 for p in parts if p)} of {len(days)} days)")


def spot_klines(sym):
    """Spot 4h candles (idea: spot-led vs futures-led breakouts). Spot archive times are in microseconds from 2025."""
    path = os.path.join(OUT, f"{sym}_spot_4h.csv.gz")
    if os.path.exists(path):
        return
    def one(mo):
        r = get(f"https://data.binance.vision/data/spot/monthly/klines/{sym}/4h/{sym}-4h-{mo}.zip")
        if r is None:
            return []
        z = zipfile.ZipFile(io.BytesIO(r.content))
        rows = [x for x in csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())) if x and x[0][:1].isdigit()]
        return [(int(x[0]) // 1000 if int(x[0]) > 10**14 else int(x[0]),) + tuple(x[1:6]) + (x[7], x[8], x[9], x[10]) for x in rows]
    with ThreadPoolExecutor(8) as ex:
        rows = [r for part in ex.map(one, months()) for r in part]
    write(path, ["open_ms", "o", "h", "l", "c", "volume", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote"],
          sorted(rows, key=lambda x: x[0]))
    print(f"{sym}: {len(rows)} spot 4h candles")


def premium(sym):
    """Futures premium index, 1h candles (perpetual price vs the spot index, as used for funding)."""
    path = os.path.join(OUT, f"{sym}_premium_1h.csv.gz")
    if os.path.exists(path):
        return
    rows = [(k[0], k[1], k[2], k[3], k[4]) for k in monthly_rows("premiumIndexKlines", sym, "1h")]
    write(path, ["open_ms", "o", "h", "l", "c"], sorted(rows, key=lambda x: int(x[0])))
    print(f"{sym}: {len(rows)} premium index 1h candles")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for sym in COINS:
        funding(sym); klines(sym); spot_klines(sym); premium(sym)
    for sym in COINS:
        print(f"{sym}: downloading ~{(date.today() - date(2021, 12, 1)).days} daily metrics files ...", flush=True)
        metrics(sym)
    print("done ->", OUT)
