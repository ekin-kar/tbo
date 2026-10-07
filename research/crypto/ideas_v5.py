"""Fakeout detection on top of TBO v2.4 (Oct 2026):
 1 absorption at the level   - first 15/30/60 min after the fill: lots of volume and aggressive orders our way,
                               but price does not get away from the level -> exit early
 2 liquidation spike         - trade-count spike in the trigger minute / open interest dropping in the first hour
                               after the fill -> exit early
 3 market not joining        - other coins (and BTC) far from their own breakout at the order time -> skip
 4 how the level is broken   - rejected pokes at the level before, grinding under it (order time -> skip);
                               gap / spike through it (fill time -> exit early)
 6 RSI / MACD divergence     - momentum lower now than when the level was set -> skip
Order-time measures become skip filters, fill-time measures become early exits (replayed minute by minute).
Choose on 2020-23 (2022-23 for open interest), judge on 2024-26, compare with random skips / random exits."""
import sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
import tradesim as T
from ideas_v4 import v24, metrics, at_before, acct

I = C.I
COINS = T.COINS
TK = {}


def taker(sym):
    if sym not in TK:
        z = np.load(C.D.CACHE / f"{sym}_taker1m.npz")
        TK[sym] = {k: z[k] for k in z.files}
    return TK[sym]


def macd_hist(c):
    m = I.ema(c, 12) - I.ema(c, 26)
    return m - I.ema(m, 9)


def order_features(args):
    """Measures known at the order time (the 4h close before the fill)."""
    sym, X, others = args
    m = T.data(sym); c = F.resample(m, 240); d = F.resample(m, 1440)
    H, L, Cc = c["h"], c["l"], c["c"]
    a = I.atr(H, L, Cc, 14); hi = I.rolling_max(H, 20); lo = I.rolling_min(L, 20)
    r14 = I.rsi_wilder(Cc, 14); mh = macd_hist(Cc)
    dr = I.rsi_wilder(d["c"], 14)
    k = np.searchsorted(c["act"], X.e.to_numpy(), side="right") - 1
    kd = np.searchsorted(d["act"], c["act"][k], side="right") - 1
    s = X.dir.to_numpy().astype(float)
    f = pd.DataFrame(index=X.index)
    lvl = np.where(s > 0, hi[k], lo[k])
    # 6: divergence vs the candle that set the level (negative = momentum weaker now)
    lk = np.array([kk - 19 + (int(np.argmax(H[kk - 19:kk + 1])) if sd > 0 else int(np.argmin(L[kk - 19:kk + 1]))) for kk, sd in zip(k, s)])
    f["rsi_div_4h"] = s * (r14[k] - r14[lk])
    f["rsi_at_level_4h"] = np.where(s > 0, r14[lk], 100 - r14[lk])
    f["macd_div_4h"] = s * (mh[k] - mh[lk]) / a[k]
    f["level_age"] = k - lk
    ld = np.array([kk - 19 + (int(np.argmax(d["h"][kk - 19:kk + 1])) if sd > 0 else int(np.argmin(d["l"][kk - 19:kk + 1]))) for kk, sd in zip(kd, s)])
    f["rsi_div_daily"] = s * (dr[kd] - dr[ld])
    # 4 (order time): rejected pokes at the level and grinding right under it
    rej, grind = [], []
    for kk, sd, lv, aa in zip(k, s, lvl, a[k]):
        Hs, Ls, Cs = H[kk - 19:kk + 1], L[kk - 19:kk + 1], Cc[kk - 19:kk + 1]
        if sd > 0:
            rej.append(int(((Hs >= lv - 0.1 * aa) & (Cs <= lv - 0.5 * aa)).sum()))
            grind.append(int((Cs[-6:] >= lv - 0.5 * aa).sum()))
        else:
            rej.append(int(((Ls <= lv + 0.1 * aa) & (Cs >= lv + 0.5 * aa)).sum()))
            grind.append(int((Cs[-6:] <= lv + 0.5 * aa).sum()))
    f["rejected_pokes"] = rej; f["grind_6"] = grind
    # 3: other coins at the same 4h close
    t_close = c["t"][k] + 240
    pos_all, near, broke = [], [], []
    for o in others:
        mo = T.data(o); co = F.resample(mo, 240)
        hio = I.rolling_max(co["h"], 20); loo = I.rolling_min(co["l"], 20)
        ko = np.searchsorted(co["t"] + 240, t_close, side="right") - 1
        valid = ko >= 30                                  # the other coin was listed long enough
        ko = np.clip(ko, 30, None)
        rng_ = np.maximum(hio[ko] - loo[ko], 1e-12)
        pos = np.where(s > 0, (co["c"][ko] - loo[ko]) / rng_, (hio[ko] - co["c"][ko]) / rng_)
        pos = np.where(valid, pos, np.nan)
        pos_all.append(pos); near.append(np.where(valid, pos >= 0.9, np.nan))
        prev_hi = I.rolling_max(co["h"], 20)[np.clip(ko - 6, 0, None)]; prev_lo = I.rolling_min(co["l"], 20)[np.clip(ko - 6, 0, None)]
        hi6 = np.array([co["h"][j - 5:j + 1].max() for j in ko]); lo6 = np.array([co["l"][j - 5:j + 1].min() for j in ko])
        broke.append(np.where(valid, np.where(s > 0, hi6 > prev_hi, lo6 < prev_lo), np.nan))
        if o == "BTCUSDT":
            f["btc_chanpos"] = pos
    f["others_chanpos"] = np.nanmean(pos_all, axis=0); f["others_near_break"] = np.nansum(near, axis=0)
    f["others_broke_24h"] = np.nansum(broke, axis=0)
    return sym, f


def fill_measures(args):
    """Per trade: base R and the early-exit R for each fill-time rule (idea 1, 2, 4)."""
    sym, X = args
    m = T.data(sym); tk = taker(sym)
    ti = np.searchsorted(tk["t"], m["t"])                      # taker row of each 1m bar
    ok_tk = (ti < len(tk["t"])) & (tk["t"][np.clip(ti, 0, len(tk["t"]) - 1)] == m["t"])
    qv = np.where(ok_tk, tk["qv"][np.clip(ti, 0, len(tk["t"]) - 1)], np.nan)
    tb = np.where(ok_tk, tk["tbq"][np.clip(ti, 0, len(tk["t"]) - 1)], np.nan)
    nt = np.where(ok_tk, tk["n"][np.clip(ti, 0, len(tk["t"]) - 1)], np.nan)
    c4 = F.resample(m, 240); a4 = I.atr(c4["h"], c4["l"], c4["c"], 14)
    mt, g = metrics(sym); oi = g.sum_open_interest_value.to_numpy()
    rows = []
    for r in X.itertuples():
        e, s, P, D = r.e, r.dir, r.entry, r.sl_dist
        xi, xp, why, b = T.path(sym, e, s, P, D)
        R0 = T.R_of(sym, s, P, D, xi, xp, e)[0]
        k = np.searchsorted(c4["act"], e, side="right") - 1
        day = slice(max(0, e - 1440), e)
        vavg = np.nanmean(qv[day]); navg = np.nanmean(nt[day])
        row = dict(R0=R0, xi=xi, trig_range_atr=(m["h"][e] - m["l"][e]) / a4[k], trig_vol=qv[e] / vavg, trig_count=nt[e] / navg)
        for W in (15, 30, 60):
            j = e + W
            if j >= xi:                                         # already out before the check
                row.update({f"prog{W}": np.nan, f"vol{W}": np.nan, f"flow{W}": np.nan, f"Rx{W}": R0})
                continue
            prog = s * (m["c"][j - 1] - P) / D
            vw = np.nansum(qv[e:j]); fw = s * (2 * np.nansum(tb[e:j]) - vw) / max(vw, 1e-9)
            row.update({f"prog{W}": prog, f"vol{W}": vw / (vavg * W), f"flow{W}": fw,
                        f"Rx{W}": T.R_of(sym, s, P, D, j, m["o"][j], e)[0]})
        # open interest: first hourly print after the fill vs the last one before it
        t_e = int(m["t"][e]) * 60_000
        q0 = at_before(mt, t_e); q1 = q0 + 1
        if 0 <= q0 and q1 < len(mt) and mt[q1] - t_e < 2 * 3600_000 and t_e - mt[q0] < 2 * 3600_000:
            j = int(np.searchsorted(m["t"], mt[q1] // 60_000 + 1))
            row["oi_after"] = oi[q1] / oi[q0] - 1
            row["Rx_oi"] = T.R_of(sym, s, P, D, j, m["o"][j], e)[0] if j < xi else R0
        else:
            row["oi_after"] = np.nan; row["Rx_oi"] = R0
        rows.append(row)
    return sym, pd.DataFrame(rows, index=X.index)


if __name__ == "__main__":
    with Pool(4) as p:
        base = dict(p.map(v24, COINS))
        off = 0
        for s_ in COINS:                                  # unique row ids across coins
            base[s_].index = range(off, off + len(base[s_])); off += len(base[s_])
        of = dict(p.map(order_features, [(s, base[s], [o for o in COINS if o != s]) for s in COINS]))
        fm = dict(p.map(fill_measures, [(s, base[s]) for s in COINS]))
    X = pd.concat(base.values()); O = pd.concat(of.values()).loc[X.index]; M = pd.concat(fm.values()).loc[X.index]
    X = X.sort_values("entry_time"); O = O.loc[X.index]; M = M.loc[X.index]
    X = X.reset_index(drop=True); O = O.reset_index(drop=True); M = M.reset_index(drop=True)
    pd.to_pickle((X, O, M), C.D.CACHE / "ideas_v5.pkl")
    W = X.sym.map(T.WT).to_numpy() * np.where(X.dir < 0, 0.5, 1)
    R = M.R0.to_numpy(); EXT = X.exit_time.values.astype("datetime64[m]").astype(np.int64)
    print("replayed R vs engine R, max diff:", np.abs(R - X.R.to_numpy()).max().round(3))
    ET = X.entry_time
    DEV20 = ((ET >= "2020-03-01") & (ET < "2024-01-01")).to_numpy(); DEV22 = ((ET >= "2022-01-01") & (ET < "2024-01-01")).to_numpy()
    HO = (ET >= "2024-01-01").to_numpy()
    rng = np.random.default_rng(11)

    def ratio(Rv, w, per):
        return acct(Rv, w, EXT, per)[2]

    b20, b22, bho = ratio(R, W, DEV20), ratio(R, W, DEV22), ratio(R, W, HO)

    def scan_skip(title, feats, dev, bd):
        rows = []
        for f in feats:
            x = O[f].to_numpy(float); xd = x[dev & ~np.isnan(x)]
            cands = []
            if len(np.unique(xd)) <= 8:
                for v in np.unique(xd):
                    cands += [(f"{f} == {v:g}", x == v), (f"{f} >= {v:g}", x >= v), (f"{f} <= {v:g}", x <= v)]
            else:
                for qq in (0.1, 0.2, 0.33):
                    lo, hi = np.quantile(xd, qq), np.quantile(xd, 1 - qq)
                    cands += [(f"{f} <= {lo:.3g} (low {int(qq*100)}%)", x <= lo), (f"{f} >= {hi:.3g} (high {int(qq*100)}%)", x >= hi)]
            for nm, msk in cands:
                sh = msk[dev].mean()
                if not 0.04 <= sh <= 0.5:
                    continue
                w = W * ~msk
                rows.append((nm, sh, ratio(R, w, dev) / bd, ratio(R, w, HO) / bho,
                             np.mean(np.clip(R[msk & dev], None, 10)), np.mean(np.clip(R[~msk & dev], None, 10)),
                             np.mean(np.clip(R[msk & HO], None, 10)), np.mean(np.clip(R[~msk & HO], None, 10))))
        rows.sort(key=lambda r: -min(r[2], r[3]))
        print(f"\n=== {title}: skip the order when ... (base net/DD first period {bd:.2f}, 2024-26 {bho:.2f}) ===")
        for r in rows[:6]:
            print(f"  {r[0][:44]:44s} share {r[1]*100:3.0f}%  first x{r[2]:.2f}  2024-26 x{r[3]:.2f}   avg R skipped/kept {r[4]:+.2f}/{r[5]:+.2f} | {r[6]:+.2f}/{r[7]:+.2f}")
        both = sum(1 for r in rows if r[2] > 1.1 and r[3] > 1.1)
        luck = np.mean([(ratio(R, W * ~(mk := rng.random(len(X)) < rng.uniform(.05, .4)), dev) / bd > 1.1) and
                        (ratio(R, W * ~mk, HO) / bho > 1.1) for _ in range(300)]) * 100
        print(f"  >10% better in both periods: {both} of {len(rows)} ({both/max(len(rows),1)*100:.1f}%); random skips: {luck:.1f}%")

    scan_skip("6: RSI / MACD divergence", ["rsi_div_4h", "rsi_at_level_4h", "macd_div_4h", "rsi_div_daily"], DEV20, b20)
    scan_skip("3: market not joining", ["others_chanpos", "others_near_break", "others_broke_24h", "btc_chanpos"], DEV20, b20)
    scan_skip("4: how the level was approached", ["rejected_pokes", "grind_6", "level_age"], DEV20, b20)

    def scan_exit(title, rules, dev, bd):
        print(f"\n=== {title}: exit early when ... (base first period {bd:.2f}, 2024-26 {bho:.2f}) ===")
        res = []
        for nm, msk, col in rules:
            Rv = np.where(msk, M[col].to_numpy(), R)
            sh = msk[dev].mean()
            # luck: exit the same share of trades at the same moment, chosen at random
            lk = []
            for _ in range(200):
                rm = rng.random(len(X)) < sh
                lk.append((ratio(np.where(rm, M[col].to_numpy(), R), W, dev) / bd, ratio(np.where(rm, M[col].to_numpy(), R), W, HO) / bho))
            lk = np.array(lk)
            res.append((nm, sh, ratio(Rv, W, dev) / bd, ratio(Rv, W, HO) / bho, np.percentile(lk[:, 0], 90), np.percentile(lk[:, 1], 90),
                        np.mean(M[col][msk & dev] - R[msk & dev]), np.mean(M[col][msk & HO] - R[msk & HO])))
        res.sort(key=lambda r: -min(r[2] - r[4], r[3] - r[5]))
        for r in res[:8]:
            print(f"  {r[0][:52]:52s} share {r[1]*100:3.0f}%  first x{r[2]:.2f} (random 90th x{r[4]:.2f})  2024-26 x{r[3]:.2f} (x{r[5]:.2f})  "
                  f"R gained per exited trade {r[6]:+.2f} | {r[7]:+.2f}")
        good = sum(1 for r in res if r[2] > max(1.05, r[4]) and r[3] > max(1.05, r[5]))
        print(f"  rules better than base AND than random exits in both periods: {good} of {len(res)}")

    rules1, rules2, rules4 = [], [], []
    for Wn in (15, 30, 60):
        prog, vol, flow = M[f"prog{Wn}"].to_numpy(), M[f"vol{Wn}"].to_numpy(), M[f"flow{Wn}"].to_numpy()
        for pq in (0.0, 0.25):
            base_m = prog <= pq
            rules1.append((f"{Wn}min: progress <= {pq}R (no volume check)", base_m, f"Rx{Wn}"))
            for vq in (0.5, 0.67, 0.8):
                vt = np.nanquantile(vol[DEV20], vq)
                rules1.append((f"{Wn}min: progress <= {pq}R & volume >= {vq:.0%}ile", base_m & (vol >= vt), f"Rx{Wn}"))
                rules1.append((f"{Wn}min: progress <= {pq}R & volume >= {vq:.0%}ile & our side aggressive", base_m & (vol >= vt) & (flow > 0), f"Rx{Wn}"))
        for cq in (0.67, 0.8, 0.9):
            ct = np.nanquantile(M.trig_count.to_numpy()[DEV20], cq)
            rules2.append((f"{Wn}min: trigger-minute trades >= {cq:.0%}ile & progress <= 0", (M.trig_count.to_numpy() >= ct) & (prog <= 0), f"Rx{Wn}"))
            rt = np.nanquantile(M.trig_range_atr.to_numpy()[DEV20], cq)
            rules4.append((f"{Wn}min: trigger-minute range >= {cq:.0%}ile & progress <= 0", (M.trig_range_atr.to_numpy() >= rt) & (prog <= 0), f"Rx{Wn}"))
            vt = np.nanquantile(M.trig_vol.to_numpy()[DEV20], cq)
            rules4.append((f"{Wn}min: trigger-minute volume >= {cq:.0%}ile & progress <= 0", (M.trig_vol.to_numpy() >= vt) & (prog <= 0), f"Rx{Wn}"))
    for thr in (-0.005, -0.01, -0.02):
        rules2.append((f"OI first hour after fill <= {thr:.1%}", (M.oi_after.to_numpy() <= thr), "Rx_oi"))
    scan_exit("1: absorption", rules1, DEV20, b20)
    scan_exit("2: liquidation spike", rules2, DEV20, b20)
    scan_exit("4: how the level was broken (fill)", rules4, DEV20, b20)
