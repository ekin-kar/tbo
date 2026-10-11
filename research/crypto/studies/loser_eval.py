"""Can any measurement at order time filter out losers? Uses cache/loser_features.pkl (loser_study.py).
Each filter is chosen on 2020-23 (dev) and judged on 2024-26 (holdout), on the bot's weighted account
(BTC 2, ETH 1, DOGE/ADA 0.5, shorts x0.5, in R): net, max drawdown, net/DD; vs removing the same share at random."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import itertools, sys
import numpy as np, pandas as pd
import common as C

X = pd.read_pickle(C.D.CACHE / "loser_features.pkl")
WT = X.sym.map({"BTC": 2, "ETH": 1, "DOGE": .5, "ADA": .5}).to_numpy() * np.where(X.side < 0, .5, 1)
PR = X.R.to_numpy() * WT
DEV = (X.entry_time < "2024-01-01").to_numpy(); HO = ~DEV
ORD = np.argsort(X.exit_time.values, kind="stable")
META = {"sym", "entry_time", "exit_time", "R", "k_time"}
FEATS = [c for c in X.columns if c not in META]
FILL = {"fill_wait_h", "fill_move_1h_atr", "fill_vol_15m"}       # known only when the stop triggers


def acct(keep, per):
    m = keep & per
    p = np.where(m, PR, 0.0)[ORD][per[ORD]]
    e = np.cumsum(p); dd = np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e)
    return e[-1], dd, e[-1] / dd


BASE = {p: acct(np.ones(len(X), bool), m) for p, m in (("dev", DEV), ("ho", HO))}
rng = np.random.default_rng(0)


def rand_ratio(share, per, n=400):
    out = []
    for _ in range(n):
        keep = rng.random(len(X)) >= share
        out.append(acct(keep, per)[2])
    return np.array(out)


RAND = {}


def rand_pct(share, per_name, val):
    key = (round(share, 2), per_name)
    if key not in RAND:
        RAND[key] = rand_ratio(share, DEV if per_name == "dev" else HO)
    return (RAND[key] < val).mean() * 100


def describe(rm, name):
    rows = []
    for pn, per in (("dev", DEV), ("ho", HO)):
        r = rm & per; k = ~rm & per
        net, dd, ratio = acct(~rm, per)
        Rr = X.R[r]; Rk = X.R[k]
        rows.append(dict(per=pn, removed=r.sum() / per.sum() * 100, rem_win=(Rr > .2).mean() * 100, keep_win=(Rk > .2).mean() * 100,
                         rem_avgR=Rr.clip(upper=10).mean(), keep_avgR=Rk.clip(upper=10).mean(),
                         net=net / BASE[pn][0] * 100, dd=dd / BASE[pn][1] * 100, ratio=ratio, base_ratio=BASE[pn][2],
                         rand_pctile=rand_pct(r.sum() / per.sum(), pn, ratio)))
    return name, rows


def conds():
    """(name, mask) tails on dev quantiles: lowest/highest 10/20/33% of each measurement; categories by value."""
    out = []
    for f in FEATS:
        x = X[f].to_numpy(float); xd = x[DEV & ~np.isnan(x)]
        if len(np.unique(xd)) <= 12:
            for v in np.unique(xd):
                out.append((f"{f} == {v:g}", x == v))
            continue
        for q in (0.1, 0.2, 0.33):
            lo, hi = np.quantile(xd, q), np.quantile(xd, 1 - q)
            out.append((f"{f} <= {lo:.3g} (low {int(q*100)}%)", x <= lo))
            out.append((f"{f} >= {hi:.3g} (high {int(q*100)}%)", x >= hi))
    return out


if __name__ == "__main__":
    print(f"trades: dev {DEV.sum()}, holdout {HO.sum()}; base net/DD dev {BASE['dev'][2]:.2f} holdout {BASE['ho'][2]:.2f}")
    print(f"win rate dev {(X.R[DEV] > .2).mean()*100:.1f}%  holdout {(X.R[HO] > .2).mean()*100:.1f}%")
    CS = conds()
    print(f"{len(CS)} single conditions from {len(FEATS)} measurements")

    # 1) single filters: score on dev, then look at holdout
    res = []
    for name, m in CS:
        sh = m[DEV].mean()
        if sh < 0.05 or sh > 0.45:
            continue
        d = acct(~m, DEV); h = acct(~m, HO)
        res.append((name, sh, d[2] / BASE["dev"][2], h[2] / BASE["ho"][2], d[0] / BASE["dev"][0], h[0] / BASE["ho"][0], m))
    res.sort(key=lambda r: -r[2])
    print("\n=== single filters (remove trades matching), best 25 by 2020-23 net/DD ===")
    print(f"{'condition':52s} {'share':>6s} {'dev ratio':>9s} {'ho ratio':>9s} {'dev net':>8s} {'ho net':>7s}")
    for r in res[:25]:
        print(f"{r[0][:52]:52s} {r[1]*100:5.0f}% {r[2]:9.2f} {r[3]:9.2f} {r[4]*100:7.0f}% {r[5]*100:6.0f}%")
    both = [r for r in res if r[2] > 1.1 and r[3] > 1.1]
    print(f"\nsingle filters improving net/DD by >10% in BOTH periods: {len(both)} of {len(res)}")
    for r in sorted(both, key=lambda r: -min(r[2], r[3]))[:20]:
        print(f"  {r[0][:60]:60s} share {r[1]*100:3.0f}%  dev x{r[2]:.2f}  ho x{r[3]:.2f}  net dev {r[4]*100:.0f}% ho {r[5]*100:.0f}%")
    # what does chance give? fraction of random conditions passing the same bar
    fake = 0
    for _ in range(300):
        sh = rng.uniform(.05, .45); m = rng.random(len(X)) < sh
        if acct(~m, DEV)[2] / BASE["dev"][2] > 1.1 and acct(~m, HO)[2] / BASE["ho"][2] > 1.1:
            fake += 1
    print(f"random filters passing the same bar: {fake/3:.1f}% (real conditions: {len(both)/len(res)*100:.1f}%)")

    # 2) pairs: remove only when BOTH conditions hold; pick on dev, test on holdout
    single = [(n, m) for n, m in CS if 0.1 <= m[DEV].mean() <= 0.5]
    pr = []
    for (n1, m1), (n2, m2) in itertools.combinations(single, 2):
        if n1.split()[0] == n2.split()[0]:
            continue
        m = m1 & m2; sh = m[DEV].mean()
        if sh < 0.05:
            continue
        d = acct(~m, DEV)
        pr.append((d[2] / BASE["dev"][2], n1, n2, m, sh))
    pr.sort(key=lambda r: -r[0])
    print(f"\n=== pairs: {len(pr)} tested; best 15 on 2020-23 and how they did 2024-26 ===")
    hos = []
    for r in pr[:200]:
        h = acct(~r[3], HO); hos.append(h[2] / BASE["ho"][2])
    for r, hv in list(zip(pr, hos))[:15]:
        print(f"  dev x{r[0]:.2f} ho x{hv:.2f} share {r[4]*100:3.0f}%  {r[1][:40]} AND {r[2][:40]}")
    print(f"top 200 dev pairs on holdout: median x{np.median(hos):.2f}, better than base in {np.mean(np.array(hos) > 1)*100:.0f}%")

    # 3) machine learning: trained on one period, tested on the other
    try:
        from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
        from sklearn.metrics import roc_auc_score
        F2 = [f for f in FEATS if f not in FILL]
        Z = X[F2].fillna(X[F2].median()).to_numpy()
        y = (X.R > .2).to_numpy()
        print("\n=== machine learning (gradient boosting, features known at order time) ===")
        for tr_, te_, lab in ((DEV, HO, "train 2020-23 -> test 2024-26"), (HO, DEV, "train 2024-26 -> test 2020-23")):
            for model, kind in ((GradientBoostingClassifier(n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.7, random_state=0), "win?"),
                                (GradientBoostingRegressor(n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.7, random_state=0, loss="huber"), "R")):
                model.fit(Z[tr_], y[tr_] if kind == "win?" else X.R.clip(upper=10).to_numpy()[tr_])
                sc = model.predict_proba(Z[te_])[:, 1] if kind == "win?" else model.predict(Z[te_])
                auc = roc_auc_score(y[te_], sc)
                full = np.full(len(X), np.inf); full[te_] = sc
                out = []
                for q in (0.1, 0.2, 0.3):
                    thr = np.quantile(sc, q); rm = full <= thr
                    rr = acct(~rm, te_); base = acct(np.ones(len(X), bool), te_)
                    out.append(f"drop worst {int(q*100)}%: net/DD x{rr[2]/base[2]:.2f} net {rr[0]/base[0]*100:.0f}% (random pctile {rand_pct(q, 'ho' if te_ is HO else 'dev', rr[2]):.0f})")
                print(f"  {lab} [{kind}] AUC {auc:.3f} | " + " | ".join(out))
    except ImportError:
        print("sklearn missing")
