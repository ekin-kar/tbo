"""Extends the research data to END (Nov 2026 research round, v2.9 studies) from Binance's public archive
(data.binance.vision: monthly files, then daily files) and the REST API for the last, not yet archived day.

  python research/crypto/core/fetch_extend.py dev       # DEV12: 1m candles -> data/<SYM>_1m_2020_2026_part3.parquet
                                                        #        (Oct 2026 .. END), data/extra/ metrics / premium / funding /
                                                        #        4h / spot 4h appended up to END
  python research/crypto/core/fetch_extend.py hold      # HOLD39: 1h candles, metrics (OI), premium 1h, funding, spot 4h
                                                        #        -> data/extra2/ (not in git)
  python research/crypto/core/fetch_extend.py m1big     # HOLD_BIG (14 untouched big coins): 1m candles 2020 .. END
                                                        #        -> cache/<SYM>_m1.npz (the format common.load reads)
Safe to re-run (finished files are skipped; `dev` rewrites part3 and re-appends extra rows idempotently)."""
import csv, gzip, io, os, sys, time, zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import numpy as np, pandas as pd, requests

ROOT = Path(__file__).resolve().parents[3]
DATA, EX, EX2, CACHE = ROOT / "data", ROOT / "data" / "extra", ROOT / "data" / "extra2", ROOT / "cache"
END = os.environ.get("FETCH_END", "2026-11-07")                       # exclusive (data through 2026-11-06)
ARCH = "https://data.binance.vision/data"
FAPI = "https://fapi.binance.com"
OUR5 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
DEV12 = OUR5 + ["XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT"]
HOLD_BIG = ["BCHUSDT", "XLMUSDT", "SUIUSDT", "HBARUSDT", "1000SHIBUSDT", "1000PEPEUSDT", "NEARUSDT", "UNIUSDT", "ETCUSDT",
            "APTUSDT", "AAVEUSDT", "ATOMUSDT", "FILUSDT", "ICPUSDT"]
HOLD_SMALL = ["ALGOUSDT", "ARBUSDT", "AXSUSDT", "CRVUSDT", "ENAUSDT", "EOSUSDT", "FETUSDT", "GRTUSDT", "IMXUSDT", "INJUSDT",
              "LDOUSDT", "MANAUSDT", "OPUSDT", "ORDIUSDT", "RUNEUSDT", "SANDUSDT", "SEIUSDT", "STXUSDT", "THETAUSDT", "TIAUSDT",
              "VETUSDT", "WIFUSDT", "WLDUSDT", "XTZUSDT", "ZECUSDT"]
HOLD39 = HOLD_BIG + HOLD_SMALL
SPOT_NAME = {"1000SHIBUSDT": "SHIBUSDT", "1000PEPEUSDT": "PEPEUSDT"}    # spot has no 1000x contracts
S = requests.Session()
S.mount("https://", requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32))
END_D = date.fromisoformat(END)
END_MS = int(datetime.fromisoformat(END).replace(tzinfo=timezone.utc).timestamp() * 1000)


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


def zrows(r):
    if r is None:
        return []
    z = zipfile.ZipFile(io.BytesIO(r.content))
    return [x for x in csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())) if x and x[0][:1].isdigit()]


def months(a, b):
    """'YYYY-MM' for every calendar month from a's month whose last day is before b (a partial first month is fetched
    whole; rows are de-duplicated later)."""
    d, out = a.replace(day=1), []
    while (d.replace(day=28) + timedelta(days=4)).replace(day=1) <= b:
        out.append(d.strftime("%Y-%m")); d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def days(a, b):
    return [a + timedelta(k) for k in range((b - a).days)]


def kl_archive(market, sym, iv, a, b, kind="klines"):
    """Kline rows (raw strings) from monthly files for the full months in [a, b) and daily files after, before b."""
    full = months(a, b)
    last_full = (datetime.strptime(full[-1], "%Y-%m").date().replace(day=28) + timedelta(days=4)).replace(day=1) if full else a
    mpath = f"{ARCH}/{market}/monthly/{kind}/{sym}/{iv}/{sym}-{iv}-"
    dpath = f"{ARCH}/{market}/daily/{kind}/{sym}/{iv}/{sym}-{iv}-"
    jobs = [mpath + m + ".zip" for m in full] + [dpath + d.isoformat() + ".zip" for d in days(max(a, last_full), b)]

    with ThreadPoolExecutor(8) as ex:
        parts = list(ex.map(lambda u: zrows(get(u)), jobs))
    rows = [r for p in parts for r in p]
    for r in rows:                                                    # spot archive: microseconds from 2025
        if int(r[0]) > 10 ** 14:
            r[0] = str(int(r[0]) // 1000)
    return rows


def kl_api(path, sym, iv, start_ms, end_ms, extra=None):
    """REST klines from start_ms (incl.) to end_ms (excl.), 1500 per request."""
    out, t = [], start_ms
    while t < end_ms:
        r = get(FAPI + path, dict(symbol=sym, pair=sym, interval=iv, startTime=t, endTime=end_ms - 1, limit=1500, **(extra or {})))
        js = r.json() if r is not None else []
        if not js:
            break
        out += [[str(v) for v in k] for k in js]
        t = int(js[-1][0]) + 1
    return out


def last_archived_day():
    """The newest day whose daily archive file exists (checked on BTCUSDT 1m)."""
    d = END_D - timedelta(1)
    while get(f"{ARCH}/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-{d.isoformat()}.zip") is None:
        d -= timedelta(1)
    return d


def klines(market, sym, iv, a, kind="klines"):
    """Archive up to the last archived day, the REST API for the rest (futures only); de-duplicated, sorted."""
    la = last_archived_day.cache if hasattr(last_archived_day, "cache") else None
    if la is None:
        la = last_archived_day.cache = last_archived_day()
    rows = kl_archive(market, sym, iv, a, la + timedelta(1), kind)
    if market == "futures/um":
        st = int(datetime.combine(la + timedelta(1), datetime.min.time(), timezone.utc).timestamp() * 1000)
        path = {"klines": "/fapi/v1/klines", "premiumIndexKlines": "/fapi/v1/premiumIndexKlines"}[kind]
        rows += kl_api(path, sym, iv, st, END_MS)
    elif market == "spot":
        st = int(datetime.combine(la + timedelta(1), datetime.min.time(), timezone.utc).timestamp() * 1000)
        t = st
        while t < END_MS:
            r = get("https://api.binance.com/api/v3/klines", dict(symbol=sym, interval=iv, startTime=t, endTime=END_MS - 1, limit=1000))
            js = r.json() if r is not None else []
            if not js:
                break
            rows += [[str(v) for v in k] for k in js]; t = int(js[-1][0]) + 1
    d = {}
    for r in rows:
        if int(r[0]) < END_MS:
            d[int(r[0])] = r
    step = {"1m": 60_000, "1h": 3_600_000, "4h": 14_400_000}[iv]
    ks = np.array(sorted(d), dtype=np.int64)
    holes = np.flatnonzero(np.diff(ks) > step) if len(ks) > 1 else []
    for h in holes:                                                   # a day missing in a monthly file: daily file, then API
        a_ms, b_ms = int(ks[h]) + step, int(ks[h + 1])
        for day in sorted({datetime.fromtimestamp(x / 1000, timezone.utc).date() for x in range(a_ms, b_ms, 3_600_000)}):
            for r in zrows(get(f"{ARCH}/{market}/daily/{kind}/{sym}/{iv}/{sym}-{iv}-{day.isoformat()}.zip")):
                r[0] = str(int(r[0]) // 1000) if int(r[0]) > 10 ** 14 else r[0]
                d.setdefault(int(r[0]), r)
        if market == "futures/um" and not any(a_ms <= k < b_ms for k in d):
            path = {"klines": "/fapi/v1/klines", "premiumIndexKlines": "/fapi/v1/premiumIndexKlines"}[kind]
            for r in kl_api(path, sym, iv, a_ms, b_ms):
                d.setdefault(int(r[0]), r)
        n_new = sum(1 for k in d if a_ms <= k < b_ms)
        print(f"{sym} {iv} {kind}: hole {pd.to_datetime(a_ms, unit='ms')} .. {pd.to_datetime(b_ms, unit='ms')} -> {n_new} rows filled", flush=True)
    return [d[k] for k in sorted(d)]


# ── 1m candles ──────────────────────────────────────────────────────────────────────────────────────────────────
def m1_frame(rows):
    a = np.array([[float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[7]), float(r[8])] for r in rows])
    idx = pd.to_datetime(np.array([int(r[0]) for r in rows]), unit="ms").astype("datetime64[ms]")
    df = pd.DataFrame(a[:, :6].astype(np.float32), index=pd.DatetimeIndex(idx, name="open_time"),
                      columns=["open", "high", "low", "close", "volume", "quote_volume"])
    df["count"] = a[:, 6].astype(np.int32)
    return df


def dev_m1(sym):
    old = pd.read_parquet(DATA / f"{sym}_1m_2020_2026_part2.parquet")
    start = (old.index[-1] + pd.Timedelta(minutes=1)).date()
    df = m1_frame(klines("futures/um", sym, "1m", start))
    df = df[df.index > old.index[-1]]
    df.to_parquet(DATA / f"{sym}_1m_2020_2026_part3.parquet", compression="snappy")
    (CACHE / f"{sym}_m1.npz").unlink(missing_ok=True)                 # common.load rebuilds its cache
    print(f"{sym}: 1m {df.index[0]} .. {df.index[-1]} ({len(df):,} rows)", flush=True)


def big_m1(sym, since=date(2020, 1, 1)):
    out = CACHE / f"{sym}_m1.npz"
    if out.exists():
        return
    df = m1_frame(klines("futures/um", sym, "1m", since))
    t = df.index.values.astype("datetime64[m]").astype(np.int64)
    tmp = CACHE / f"{sym}_m1.tmp.npz"
    np.savez(tmp, t=t, o=df.open.to_numpy(float), h=df.high.to_numpy(float), l=df.low.to_numpy(float),
             c=df.close.to_numpy(float), v=df.quote_volume.to_numpy(float))
    os.replace(tmp, out)
    print(f"{sym}: 1m {df.index[0]} .. {df.index[-1]} ({len(df):,} rows)", flush=True)


# ── extra data ──────────────────────────────────────────────────────────────────────────────────────────────────
def write(path, header, rows):
    tmp = str(path) + ".tmp"
    with gzip.open(tmp, "wt", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    os.replace(tmp, path)


def metrics_day(sym, day):
    rd = zrows(get(f"{ARCH}/futures/um/daily/metrics/{sym}/{sym}-metrics-{day.isoformat()}.zip"))
    keep = {}
    for row in rd:                                                    # 5-minute rows -> the last one of each hour
        keep[row[0][:13]] = row
    return list(keep.values())


def metrics_api(sym, start_ms):
    """Hourly OI from /futures/data/openInterestHist (last 30 days) for hours the archive does not have yet."""
    r = get(FAPI + "/futures/data/openInterestHist", dict(symbol=sym, period="1h", startTime=start_ms, limit=500))
    js = r.json() if r is not None else []
    return [[datetime.fromtimestamp(int(k["timestamp"]) / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), sym,
             k["sumOpenInterest"], k["sumOpenInterestValue"], "", "", "", ""] for k in js if int(k["timestamp"]) < END_MS]


HEAD_M = ["create_time", "symbol", "sum_open_interest", "sum_open_interest_value", "count_toptrader_long_short_ratio",
          "sum_toptrader_long_short_ratio", "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]


def metrics(sym, path, start=date(2021, 12, 1)):
    old = pd.read_csv(path, dtype=str) if path.exists() else None
    if old is not None:
        start = (pd.Timestamp(old.create_time.max()).date())
    la = last_archived_day.cache if hasattr(last_archived_day, "cache") else last_archived_day()
    last_archived_day.cache = la
    with ThreadPoolExecutor(16) as ex:
        parts = list(ex.map(lambda d: metrics_day(sym, d), days(start, la + timedelta(1))))
    rows = [r for p in parts for r in p]
    st = int(datetime.combine(la + timedelta(1), datetime.min.time(), timezone.utc).timestamp() * 1000)
    rows += metrics_api(sym, st)
    new = pd.DataFrame(rows, columns=HEAD_M) if rows else pd.DataFrame(columns=HEAD_M)
    allr = pd.concat([old, new]) if old is not None else new
    allr = allr.assign(_h=allr.create_time.str[:13]).drop_duplicates("_h", keep="last").drop(columns="_h").sort_values("create_time")
    write(path, list(allr.columns), allr.values.tolist())
    print(f"{sym}: metrics to {allr.create_time.max()} ({len(allr):,} rows)", flush=True)


def funding(sym, path):
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["time_ms", "rate"])
    st = int(old.time_ms.max()) + 1 if len(old) else int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    rows, t = [], st
    if not len(old):                                                  # archive (monthly) for a new coin
        for m in months(date(2020, 1, 1), END_D):
            rows += [(int(r[0]), float(r[-1])) for r in zrows(get(f"{ARCH}/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{m}.zip"))]
        t = max([r[0] for r in rows], default=st) + 1
    while t < END_MS:
        r = get(FAPI + "/fapi/v1/fundingRate", dict(symbol=sym, startTime=t, endTime=END_MS - 1, limit=1000))
        js = r.json() if r is not None else []
        if not js:
            break
        rows += [(int(k["fundingTime"]), float(k["fundingRate"])) for k in js]; t = int(js[-1]["fundingTime"]) + 1
    allr = pd.concat([old, pd.DataFrame(rows, columns=["time_ms", "rate"])]).drop_duplicates("time_ms").sort_values("time_ms")
    write(path, ["time_ms", "rate"], allr.values.tolist())


def kl_file(path, market, sym, iv, cols, kind="klines", start=date(2020, 1, 1)):
    """Append (or create) a gzipped kline CSV: futures 4h / spot 4h (10 columns) or premium 1h / 1h candles (5+)."""
    old = pd.read_csv(path) if path.exists() else None
    if old is not None:
        start = pd.to_datetime(int(old.open_ms.max()), unit="ms").date()
    rows = klines(market, sym, iv, start, kind)
    pick = {10: lambda k: (int(k[0]), k[1], k[2], k[3], k[4], k[5], k[7], k[8], k[9], k[10]),
            5: lambda k: (int(k[0]), k[1], k[2], k[3], k[4])}[len(cols)]
    new = pd.DataFrame([pick(k) for k in rows], columns=cols)
    allr = pd.concat([old, new]) if old is not None else new
    allr["open_ms"] = allr.open_ms.astype(np.int64)
    allr = allr.drop_duplicates("open_ms", keep="last").sort_values("open_ms")
    write(path, cols, allr.values.tolist())
    return len(allr)


K10 = ["open_ms", "o", "h", "l", "c", "volume", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote"]
K5 = ["open_ms", "o", "h", "l", "c"]


def dev_extra(sym):
    metrics(sym, EX / f"{sym}_metrics_1h.csv.gz")
    funding(sym, EX / f"{sym}_funding.csv.gz")
    kl_file(EX / f"{sym}_premium_1h.csv.gz", "futures/um", sym, "1h", K5, "premiumIndexKlines")
    kl_file(EX / f"{sym}_4h.csv.gz", "futures/um", sym, "4h", K10)
    kl_file(EX / f"{sym}_spot_4h.csv.gz", "spot", SPOT_NAME.get(sym, sym), "4h", K10)
    print(f"{sym}: extra done", flush=True)


def hold_extra(sym):
    EX2.mkdir(exist_ok=True)
    kl_file(EX2 / f"{sym}_1h.csv.gz", "futures/um", sym, "1h", K10)
    kl_file(EX2 / f"{sym}_premium_1h.csv.gz", "futures/um", sym, "1h", K5, "premiumIndexKlines")
    funding(sym, EX2 / f"{sym}_funding.csv.gz")
    try:
        kl_file(EX2 / f"{sym}_spot_4h.csv.gz", "spot", SPOT_NAME.get(sym, sym), "4h", K10)
    except Exception as e:                                            # a coin without a spot market
        print(f"{sym}: no spot ({e})")
    metrics(sym, EX2 / f"{sym}_metrics_1h.csv.gz")
    print(f"{sym}: hold data done", flush=True)


def dev_1h(sym):
    """1h futures candles for DEV12 too (the sleeve studies read one format for all 51 coins)."""
    EX2.mkdir(exist_ok=True)
    kl_file(EX2 / f"{sym}_1h.csv.gz", "futures/um", sym, "1h", K10)


if __name__ == "__main__":
    what = sys.argv[1]
    CACHE.mkdir(exist_ok=True)
    last_archived_day.cache = last_archived_day()
    print("last archived day", last_archived_day.cache, "END", END, flush=True)
    if what == "dev":
        with ThreadPoolExecutor(3) as ex:
            list(ex.map(dev_m1, DEV12))
        with ThreadPoolExecutor(3) as ex:
            list(ex.map(dev_extra, DEV12)); list(ex.map(dev_1h, DEV12))
        # spot 4h for the DEV coins that had none
    elif what == "hold":
        with ThreadPoolExecutor(3) as ex:
            list(ex.map(hold_extra, HOLD39))
    elif what == "m1big":
        with ThreadPoolExecutor(2) as ex:
            list(ex.map(big_m1, HOLD_BIG))
    elif what == "m1small":                                            # HOLD_SMALL: from mid-2021 (the OI study needs 2022+)
        with ThreadPoolExecutor(4) as ex:
            list(ex.map(lambda s: big_m1(s, date(2021, 6, 1)), HOLD_SMALL))
    print("done", what, flush=True)


# ── repair: holes in the archive (e.g. 2026-10-28 is missing from the Oct 2026 monthly files) ──────────────────────
def repair_kl(path, market, sym, iv, cols, kind="klines", since="2025-01-01"):
    """Fill holes (missing candles after `since`) of a gzipped kline CSV from the REST API."""
    if not path.exists():
        return
    old = pd.read_csv(path); old["open_ms"] = old.open_ms.astype(np.int64)
    step = {"1h": 3_600_000, "4h": 14_400_000}[iv]
    t = old.open_ms.to_numpy(); t0 = int(pd.Timestamp(since).value // 1_000_000)
    holes = [(int(t[i]) + step, int(t[i + 1])) for i in np.flatnonzero(np.diff(t) > step) if t[i] >= t0]
    add = []
    for a_ms, b_ms in holes:
        if market == "spot":
            r = get("https://api.binance.com/api/v3/klines", dict(symbol=sym, interval=iv, startTime=a_ms, endTime=b_ms - 1, limit=1000))
            add += [[str(v) for v in k] for k in (r.json() if r is not None else [])]
        else:
            add += kl_api({"klines": "/fapi/v1/klines", "premiumIndexKlines": "/fapi/v1/premiumIndexKlines"}[kind], sym, iv, a_ms, b_ms)
    if not add:
        return
    pick = {10: lambda k: (int(k[0]), k[1], k[2], k[3], k[4], k[5], k[7], k[8], k[9], k[10]), 5: lambda k: (int(k[0]), k[1], k[2], k[3], k[4])}[len(cols)]
    allr = pd.concat([old, pd.DataFrame([pick(k) for k in add], columns=cols)])
    allr["open_ms"] = allr.open_ms.astype(np.int64)
    allr = allr.drop_duplicates("open_ms", keep="first").sort_values("open_ms")
    write(path, cols, allr.values.tolist())
    print(f"{path.name}: {len(holes)} holes, {len(add)} rows added", flush=True)


def repair_m1(sym, since="2025-01-01"):
    f = CACHE / f"{sym}_m1.npz"
    if not f.exists():
        return
    z = dict(np.load(f)); t = z["t"]; t0 = pd.Timestamp(since).value // 60_000_000_000
    holes = [(int(t[i]) + 1, int(t[i + 1])) for i in np.flatnonzero(np.diff(t) > 1) if t[i] >= t0]
    rows = []
    for a, b in holes:
        rows += kl_api("/fapi/v1/klines", sym, "1m", a * 60_000, b * 60_000)
    if not rows:
        return
    df = m1_frame(rows); tn = df.index.values.astype("datetime64[m]").astype(np.int64)
    new = dict(t=tn, o=df.open.to_numpy(float), h=df.high.to_numpy(float), l=df.low.to_numpy(float), c=df.close.to_numpy(float), v=df.quote_volume.to_numpy(float))
    allt = np.r_[t, tn]; o = np.argsort(allt, kind="stable"); allt = allt[o]; keep = np.r_[True, allt[1:] != allt[:-1]]
    out = {k: np.r_[z[k], new[k]][o][keep] for k in z}
    np.savez(f, **out)
    print(f"{sym}: m1 {len(holes)} holes, {len(rows)} rows added", flush=True)


def repair(coins, ex):
    for sym in coins:
        for nm, mk, iv, cols, kind in (("premium_1h", "futures/um", "1h", K5, "premiumIndexKlines"), ("4h", "futures/um", "4h", K10, "klines"),
                                       ("1h", "futures/um", "1h", K10, "klines"), ("spot_4h", "spot", "4h", K10, "klines")):
            for d in ((ex, EX2) if nm == "1h" else (ex,)):
                repair_kl(d / f"{sym}_{nm}.csv.gz", mk, SPOT_NAME.get(sym, sym) if mk == "spot" else sym, iv, cols, kind)


if __name__ == "__main__" and sys.argv[1] == "repair":
    repair(DEV12, EX); repair(HOLD39, EX2)
    for s in HOLD_BIG:
        repair_m1(s)
    print("repair done", flush=True)
