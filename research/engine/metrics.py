"""
Performance metrics. Everything is in R (1R = the amount risked on a trade), so results
compare across symbols and translate directly into account % once risk per trade is chosen.
"""
import numpy as np
import pandas as pd


def max_losing_streak(r):
    best = cur = 0
    for x in r:
        cur = cur + 1 if x <= 0 else 0
        best = max(best, cur)
    return best


def max_drawdown_R(r):
    eq = np.cumsum(np.r_[0.0, r])
    return float((np.maximum.accumulate(eq) - eq).max())


def summary(tr: pd.DataFrame, col="R") -> dict:
    if len(tr) == 0:
        return dict(trades=0)
    r = tr[col].to_numpy()
    wins, losses = r[r > 0], r[r <= 0]
    months = tr["exit_time"].dt.to_period("M")
    span_m = max((tr["exit_time"].max() - tr["entry_time"].min()).days / 30.44, 1e-9)
    by_m = pd.Series(r).groupby(months.to_numpy()).sum()
    return dict(
        trades=len(r),
        per_month=round(len(r) / span_m, 1),
        win_rate=round(len(wins) / len(r) * 100, 1),
        avg_R=round(r.mean(), 3),
        total_R=round(r.sum(), 1),
        PF=round(wins.sum() / -losses.sum(), 2) if losses.sum() < 0 else np.inf,
        maxDD_R=round(max_drawdown_R(r), 1),
        worst_streak=max_losing_streak(r),
        pos_months=f"{(by_m > 0).sum()}/{len(by_m)}",
    )


def monthly(tr: pd.DataFrame, col="R") -> pd.Series:
    return tr.groupby(tr["exit_time"].dt.to_period("M"))[col].sum().round(1)
