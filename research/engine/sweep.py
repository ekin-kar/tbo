"""Parameter sweeps on the development period only (2026 stays sealed)."""
import itertools
import numpy as np
import pandas as pd
from . import data as D, engine as E, metrics as M

DEV_START = "2024-05-15"   # after indicator warm-up
DEV_END = D.HOLDOUT_START   # 2026-01-01


def restrict(od, m1, start=DEV_START, end=DEV_END):
    t = m1["t"]
    od.allow_entry[(t < D.minutes(start)) | (t >= D.minutes(end))] = False
    return od


def sweep(sym, build, grid: dict, spread="typ", period=(DEV_START, DEV_END), **run_kw):
    m1 = D.load_m1(sym)
    keys = list(grid)
    rows = []
    for vals in itertools.product(*[grid[k] for k in keys]):
        p = dict(zip(keys, vals))
        od = restrict(build(m1, **p), m1, *period)
        tr = E.run(sym, od, spread=spread, **run_kw)
        rows.append({**p, **M.summary(tr)})
    return pd.DataFrame(rows).sort_values("total_R", ascending=False)
