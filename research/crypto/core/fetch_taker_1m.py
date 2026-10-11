"""1-minute futures aggressive-buyer volume (taker buy quote), quote volume and trade count, 2020-01 .. last month,
from data.binance.vision. Saves cache/{SYM}_taker1m.npz (t = minutes since epoch). ~650 MB download, not in git."""
import io, zipfile, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests
import common as C
from fetch_binance_extra import months, get

COINS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]


def one(args):
    sym, mo = args
    r = get(f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/1m/{sym}-1m-{mo}.zip")
    if r is None:
        return None
    z = zipfile.ZipFile(io.BytesIO(r.content))
    d = pd.read_csv(z.open(z.namelist()[0]), header=None, usecols=[0, 7, 8, 10])
    d = d[pd.to_numeric(d[0], errors="coerce").notna()].astype(float)
    return np.c_[(d[0].to_numpy() // 60000), d[7].to_numpy(), d[8].to_numpy(), d[10].to_numpy()]


if __name__ == "__main__":
    for sym in (sys.argv[1:] or COINS):
        out = C.D.CACHE / f"{sym}_taker1m.npz"
        if out.exists():
            continue
        with ThreadPoolExecutor(8) as ex:
            parts = [p for p in ex.map(one, [(sym, mo) for mo in months()]) if p is not None]
        a = np.concatenate(parts); a = a[np.argsort(a[:, 0], kind="stable")]
        _, u = np.unique(a[:, 0], return_index=True); a = a[u]
        np.savez(out, t=a[:, 0].astype(np.int64), qv=a[:, 1].astype(np.float32), n=a[:, 2].astype(np.float32), tbq=a[:, 3].astype(np.float32))
        print(sym, len(a), "minutes", flush=True)
