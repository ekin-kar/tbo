"""Half size (or skip) on the weak setups found in trade_features.py; 4-coin portfolio in R units.
Note: the bucket table looked at both periods, so 2024-26 is no longer a clean test for these features."""
import numpy as np, pandas as pd
import common as C

D = pd.read_csv(C.ROOT / "research" / "results" / "crypto_trade_features.csv", parse_dates=["entry_time"])
RULES = {
    "v2.1 as is": lambda d: np.ones(len(d)),
    "half size when wild (vol ratio > 0.87)": lambda d: np.where(d.vol_ratio_daily > 0.87, 0.5, 1.0),
    "half size when wild (> 1.0)": lambda d: np.where(d.vol_ratio_daily > 1.0, 0.5, 1.0),
    "skip when wild (> 0.87)": lambda d: np.where(d.vol_ratio_daily > 0.87, 0.0, 1.0),
    "half size when trend steep (> 0.38)": lambda d: np.where(d.ema_slope > 0.38, 0.5, 1.0),
    "half size shorts": lambda d: np.where(d.side < 0, 0.5, 1.0),
    "half when wild OR steep": lambda d: np.where((d.vol_ratio_daily > 0.87) | (d.ema_slope > 0.38), 0.5, 1.0),
    "half wild/steep, 1.5x calm (< 0.46)": lambda d: np.where((d.vol_ratio_daily > 0.87) | (d.ema_slope > 0.38), 0.5,
                                                             np.where(d.vol_ratio_daily < 0.46, 1.5, 1.0)),
}


def st(d):
    d = d.sort_values("entry_time"); r = d.Rs.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    yrs = (d.entry_time.max() - d.entry_time.min()).days / 365.25
    return r.sum() / yrs, dd, r.sum() / yrs / dd


print(f"{'rule':40s} | {'2020-23 R/yr  DD  ret/DD':>24s} | {'2024-26 R/yr  DD  ret/DD':>24s} | per coin ret/DD 2024-26 (BTC ETH DOGE ADA)")
for name, f in RULES.items():
    d = D.copy(); d["Rs"] = d.R * f(d)
    a = st(d[d.period == "2020-23"]); b = st(d[d.period == "2024-26"])
    pc = [st(d[(d.period == "2024-26") & (d.sym == s)])[2] for s in ("BTC", "ETH", "DOGE", "ADA")]
    print(f"{name:40s} | {a[0]:8.0f} {a[1]:6.1f} {a[2]:6.2f} | {b[0]:8.0f} {b[1]:6.1f} {b[2]:6.2f} | " + " ".join(f"{x:5.2f}" for x in pc))
