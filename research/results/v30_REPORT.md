# v3.0 deep campaign — final report (2026-11-06)

Script: `research/crypto/studies/v30_deep_campaign.py` (protocol fixed in its docstring before any run). Engine: `core/xengine30.py` +
`core/v30lib.py`. Both are exactly equal to the live v2.8 rules when all switches are off: all 1,403 trades, every breakeven time and the money to the cent (`v30lib.parity`).
Data runs to 2026-11-06. 4,687 configurations were scored on 8 threads (~60 min of engine time). Every table is in `research/results/v30_*.csv`.

## Bottom line

**Four components pass all four gates, and so does their combination.** Live files are untouched; this is for your review.

| | fixed-unit x 2020-23 / 2022-23 / 2024-26 | phase copies | $300→ 2022 (drop) | $300→ 2024 (drop) | bootstrap median | p10 | dd90 |
|---|---|---|---|---|---|---|---|
| **BASE v2.8 + v2.7** | 1 / 1 / 1 | | $689k (26.3%) | $50.3k (36.1%) | $18.95k | $2.92k | 64.6% |
| C1 cooldown 16h after a stop | 1.099 / 1.233 / 1.074 | 98% / 75% | $781k (25.2%) | $50.5k (35.4%) | $20.25k | $3.48k | 60.9% |
| C2 majors' long exits | 1.106 / 1.155 / 1.086 | 80% / 100% | $826k (26.3%) | $60.6k (34.8%) | $20.32k | $3.35k | 62.4% |
| C3 alts' entry geometry | 1.082 / 1.091 / 1.063 | 98% / 93% | $709k (26.8%) | $52.8k (35.9%) | $19.21k | $2.93k | 64.3% |
| C4 panic on 12 coins (hybrid 0.75) | sleeve x 1.344 (22-23) / 1.304 (24-26) | (null 100%) | $944k (26.3%) | $72.8k (36.1%) | $21.90k | $3.96k | 61.9% |
| **v3.0 package C1+C2+C3+C4** | **1.329 / 1.537 / 1.206** | **100% / 100%** | **$1.32M (26.1%)** | **$65.7k (33.6%)** | **$25.73k** | **$5.35k** | **56.2%** |
| package, C2 replaced by the all-coins exit | 1.230 / 1.476 / 1.126 | 100% / 98% | $1.28M (26.7%) | $68.2k (34.9%) | $24.77k | $4.98k | 58.0% |

- All rows pass at **k = 1.00**: none needed its risk cut to match the base drawdown, and every one has a *lower* bootstrap dd90 than the base.
- From a 2020 start (shown, not gated) the package reaches $15.5M vs $10.5M, with a 34.5% vs 35.5% drop. **But C1 alone ends lower from 2020** ($8.8M vs $10.5M), even though its fixed-unit 2020-23 ratio is better. The effect is path-dependent compounding in the 2020-21 run.

**What each component is:**
- **C1 — cooldown.** After any trade closes at a loss worse than −0.5R (in practice, a stop-out), that coin places no new order for 16 hours. It applies to all 5 coins and both directions. The "same direction only" variant and the −0.8R trigger give identical results.
- **C2 — BTC and ETH longs only.** Three exit changes:
  - the profit lock at +5R moves the stop to **+2.0R** instead of +1.5R;
  - a **second lock** moves it to **+3.5R** once the trade reaches +8R;
  - **stale exit:** at exactly 60h, a trade that never reached +1.5R and is above −0.3R gets its stop moved to entry.

  Shorts and the breakeven at +1.5R are unchanged. The tie-break rule declared before the results picked this majors-longs variant over the all-coins/both-sides version (min x 1.086 vs 1.085). The all-coins version has the far wider plateau (94% vs 66%), and the last table row shows the package built with it.
- **C3 — BNB, SOL, ADA.** Long orders use a **30-bar** 4h channel (was 20). Short orders use a **12-bar** channel (was 20) and a **daily EMA40** trend filter (was EMA50). The max extension for shorts makes no difference between 3.5 and 5.
- **C4 — panic sleeve v2.7, same signal and exits, on the 5 coins + XRP, DOGE, AVAX, LINK, DOT, LTC, TRX.**
  - The 5 coins keep their full v2.7 share: 3 units split over the live coins that trigger that hour.
  - The 7 new coins get a separate 0.75 × 3 units, split over the new coins that trigger that hour, so the live coins are never diluted.
  - No cap on open sleeve positions.

---

## 1. Checking the critique that triggered this round

| claim | verdict |
|---|---|
| "U4's G1 summed un-split per-coin returns" | **Not correct.** v2.9 already scored `ret / 5% × w` with `w = units / n` (per-event split). The real issue was different: the sleeve's *standalone* drawdown rose, while inside the portfolio it diversifies. The drawdown-matched portfolio gate (E4) now measures that properly, and C4 passes it. |
| "U4's G5 should use HOLD_BIG, not HOLD_SMALL" | **Fair.** On the 14 HOLD_BIG coins alone, v2.7 earns +1.08% per trade in 2022-23 (ratio 2.35) and +3.65% in 2024-26 (ratio 5.6). It's positive in both periods, though weaker than on the live 5 in 2022-23 (+3.39%, ratio 4.99). |
| "U1 was rejected only for +1.9pp dd90; compare at matched drawdown" | **The money part is right, and the conclusion still holds** (§3.3). At matched drawdown, 32 of 99 bigger-short policies beat the base on money from 2022. But all 99 have a worse fixed-unit ratio in 2020-23 (the 2020-21 squeezes). The bootstrap only samples 2022-26, so it can't see that period. |
| "G5 on HOLD_BIG is meaningless for BTC/ETH rules" | **Fair.** It's dropped as a gate in v3.0, and untouched-coin results are shown where a rule applies to alts. Base TBO itself has ratio 0.01 on HOLD_BIG in 2024-26, so x ratios there are noise (see `v30_T3_universes.csv`). |

## 2. Protocol (fixed before running)

- **E1 fixed-unit:** risk-adjusted ratio (net / max drop) is better than the base in the dev period AND in 2024-01 → 2026-11.
  - Dev is 2020-23 for price-only rules, and 2022-23 for rules that read OI, premium, funding or spot volume.
  - Units: BTC 6, ETH 4, others 0.83, shorts × 0.5.
- **E2 plateau:** at least 60% of the grid neighbours also pass E1.
- **E3 luck:**
  - engine rules must give x > 1 on at least 70% of 40 phase-shifted copies of the 4h/daily candles, in each period;
  - removal and sizing rules must also beat at least 95% of 200 random nulls (same number of trades removed, or multipliers shuffled, per coin and side).
- **E4 money, drawdown-matched:**
  - bot + panic sleeve from $300 (2022 and 2024 starts), plus 1,000 paired 2-year block-bootstrap journeys;
  - the candidate's risks are scaled by k ∈ {1.00, 0.96, 0.93, 0.90}, and the first k with dd90 ≤ the base dd90 is used;
  - it must beat the base on bootstrap median, p10, and 2022 and 2024 money, with window drops at most +1pt.
- **Sleeves (Track 5):** avg R > 0, PF ≥ 1.2 and ≥ 30 trades in each period; plateau; ≥ 95% vs random and shifted copies; HOLD39 avg > 0; correlation with TBO ≤ 0.15 and positive in TBO's losing months; E4.

## 3. Funnel

| track | configs | E1 | +E2 | +E3 | **PASS** | E4 alone |
|---|---|---|---|---|---|---|
| 1a opposite-leader veto | 8 | 8 | 8 | 0 | 0 | 3 |
| 1b opposite-leader active exit | 6 | 4 | 4 | 0 | 0 | 2 |
| 1c breadth sizing | 180 | 0 | 0 | 0 | 0 | 0 |
| **1d same-coin cooldown** | 24 | 8 | 4 | 4 | **4** | 4 |
| 2a entry geometry, all 5 coins | 899 | 27 | 0 | 0 | 0 | 0 |
| 2a entry geometry, majors | 899 | 37 | 0 | 0 | 0 | 0 |
| **2a entry geometry, alts** | 899 | 327 | 299 | 8 | **3** | 3 |
| **2b exits, all coins** | 321 | 108 | 41 | 7 | **6** | 9 |
| **2b exits, majors** | 321 | 96 | 37 | 10 | **8** | 10 |
| **2b exits, alts** | 321 | 90 | 50 | 12 | **11** | 12 |
| 2c short sizing (drawdown-matched) | 99 | 0 | 0 | 0 | 0 | **32** |
| 3 spot / OI / premium / vol filters | 36 | 11 | 6 | 0 | 0 | 3 |
| **4 panic universe / ranking / horizons** | 278 | 54 | 2 | 2 | **1** | 8 |
| 5 new sleeves N1–N3 | 396 | 4 | 3 | 0 | 0 | — |

### 3.1 Track 1 — cross-coin interaction
- **Premise confirmed:** alt/ETH entries taken *opposite an open BTC trade* went 11 for 11 losers, −10.98R in total. Of those, 5 came after BTC had passed +1.5R (−5.42R).
- **The veto** blocks those 11 entries. It passes E1 and E2 everywhere, but the gain is tiny (x 1.003–1.006), and the best version beats only 94.5% of random 11-trade removals (needs 95%). That's not distinguishable from luck. Three versions pass the money gate on their own.
- **Active exit** (cut or tighten the follower when BTC/ETH enters the other way): effects of ±0.1%, and nulls at 57–64%. **Rejected.**
- **Breadth sizing:** 0/180 pass E1. The statistics-page numbers include entries that happen *after* the trade. Counted only with what is known at the fill, the 2024-26 gap shrinks from +1.12R vs +0.34R to +0.85R vs +0.56R. Co-entries also lose together, so boosting them raises drawdown as much as return.
- **Cooldown → C1.**
  - 16h is a real local optimum. 12h passes E1 but fails the phase test (55% oos). 20h passes E1–E3 but not E4. 24h, 32h and 48h are worse on every measure.
  - It removes 84 re-entries (1,403 → 1,319 trades).

### 3.2 Track 2 — majors vs alts, longs vs shorts
- **Entry geometry:**
  - For all 5 coins, or for BTC/ETH, the 27–37 settings that beat the base are isolated peaks (plateau ≤ 16%). **Rejected.**
  - For the alts, a whole region works (299 settings on a plateau). Its best phase-robust corner is long n30 / short n12 / short EMA40 → **C3**.
  - Caveat: n_long 30 and n_short 12 are grid edges.
- **Exits:** the passers in every group share one recipe: lock to +2R, second lock 8R→3.5R, stale stop at 60h. That's **C2**.
  - In v2.9 the 2nd lock and the stale exit were tested *separately*, and both failed; together, with the higher first lock, they pass.
  - On alts the effect is only about +0.7%.

### 3.3 Short sizing at matched drawdown (your U1 point)
- **Money:** e.g. BTC ×0.75 / ETH ×0.75 / alts ×0.5, run at k = 0.93: 2022 $822k vs $689k, 2024 $53.5k vs $50.3k, bootstrap median $20.8k vs $18.95k, dd90 64.0% vs 64.6%. The money gate passes.
- **Fixed-unit:** every one of the 99 policies has x below 1 in 2020-23 (0.86–0.97). 98 of 99 are above 1 in 2024-26.
- **Verdict:** bigger shorts pay in the 2022-26 regime and cost in a 2021-style bull run. The bootstrap only covers 2022-26, so it can't price that risk. **Fails E1.** If you deliberately judge 2020-21 irrelevant, this is the next candidate; but that would be a discretionary call, not a gate result.

### 3.4 Track 3 — microstructure filters (2022-23 dev)
None pass.
- **Closest:** skip longs when spot/perp volume is in the bottom 20% of 30 days and premium z > 1. It gains +0.7–0.9%, with a 100% plateau and 100% null, but holds on only 27.5% of the 2024-26 phase copies (needs 70%).
- **Crowded-long half-size:** 1.066 in dev but 1.001 out of sample, with a 0% plateau.
- **Squeeze-short skip:** no effect.
- **Vol-ratio rules:** worse out of sample. Note that ATR14/ATR100 above 2.0 is a 0.1% tail, and only 30 TBO trades since 2022 even exceed 1.5. A 1.3 threshold was added before the run; it also fails.

### 3.5 Track 4 — panic sleeve
- **Universe:** the uncapped hybrid (5 coins full + 7 at share 0.75) passes everything → **C4**.
  - It adds +94 trades in 2022-23 and +88 in 2024-26; the 7 extra coins each average +0.4% to +5.3% per trade.
  - 2022-23 is the weak part: about +1.1% per trade on the extra coins, against 3.4% on the live 5.
  - Shares 0.5 (x 1.23 / 1.22) and 1.0 (1.13 / 1.37) also pass E1.
  - Equal-share DEV12, with no protected share for the live 5, fails 2022-23 at every cap (x 0.71–0.84).
- **Capped hybrids:** many pass E1, some with higher out-of-sample x (cap 2, rank C, share 0.75: 1.25 / 1.74), but they sit on thin plateaus (25–60%). Ranking still beats random selection when capped.
- **Multi-horizon (2h / 8h / 12h windows added to the 4h one):** higher raw numbers. For example, 2+4+8h at share 1.0 gives $1.12M from 2022 and x 1.38 / 1.43. But these are isolated (plateau 14–40%), so they fail E2. Worth re-testing with a coarser grid once live data accumulates.

### 3.6 Track 5 — counter-cyclical sleeves
None pass.
- **N1, post-panic V-reversal runner:** the best setting has 29 / 34 trades (needs 30), avg +0.22 / +0.14R, and is negative on HOLD39 in 2022-23.
- **N2, funding-squeeze breakout:**
  - It is truly orthogonal: correlation with TBO is 0.06, and it earned +46R in TBO's losing months.
  - The edge is thin: PF 1.19 / 1.13 (needs 1.2), random-entry percentiles 99.5% / 88.5%, and negative on HOLD39 in 2024-26.
- **N3, chop-regime wick fade:** negative everywhere (median −0.10 / −0.15R).

## 4. Caveats — read before deploying
1. **Selection bias.** About 4,700 configurations were scored, and the package is built from the best passer of each family. The plateau and phase gates guard against single-point luck, but the 2024-26 period was used as a gate, so **no untouched hold-out remains**. The only real out-of-sample test left is live trading from here on.
2. **C2 and C3 sit near grid edges.** The C1 edge was checked and is a genuine peak.
3. **C1 lowers the 2020-start compounding result on its own.** It only helps in combination, and from 2022.
4. **C4 adds 7 symbols to the live sleeve.** That means:
   - order handling for 12 coins;
   - lower-liquidity coins (slippage modelled at 0.03% per side);
   - more simultaneous positions in a crash.

   The sleeve's peak open risk on a market-wide flush rises by up to 75%. The bootstrap includes those events, but a 2020-style crash on 12 coins at once is beyond the sample.
5. **Engine simplifications:** cross-coin rules used the leaders' *base* trades (exact for followers, one-step for BTC). Breakeven / lock "from the next bar" is as in v2.8.

**Suggested rollout (your call):** start with C1 + C2. They're two small rule changes in `strategy.py` with no new symbols, and their combination alone scores 1.26 / 1.45 / 1.16 with a bootstrap median of $22.1k. Then C3, then C4 after a dry-run period.

## 5. Housekeeping done
- **CSV:** `Binance-Futures-Trade-History-…csv` is untracked with `git rm --cached` (the deletion is staged and the file kept on disk; `.git/info/exclude` covers it). It disappears from the repo with your next commit, but stays in history (commit 14f8f74).
- **Pages:** 8 of 9 rebuilt with data to 6 Nov 2026 (1,403 trades): tbo_statistics, trades, monthly_report, cap_comparison,
  risk_comparison, plan_ladder_plus50, panic, winrate_rr.
- **breakout_support.html:** kept as its October snapshot (data to Sep 2026).
  - Its study (`oi_support.py`) was re-run to 6 Nov on all 51 coins: `eval.pkl` and `luck.pkl`.
  - The 25 small coins' 1m candles were downloaded again with the new `fetch_extend.py m1small` mode.
  - Result: 52 rules pass G1, 31 pass G1+G2, 0 pass all of that study's gates. Same verdict as October.
  - The page also needs `fine_eval.pkl`, `money_fine.pkl` and `money.pkl`. Those came from uncommitted October scratch scripts,
    so the page itself was not regenerated.
- **Date and default changes:**
  - page generators, templates, `panic_sleeve.py` and `oi_support.py`: end date 2026-10-01 → 2026-11-07
    (`oi_support.py` also uses Pool(6) instead of 4);
  - `botsim.py`: default trade list `v28` → `v28nov` (identical before Oct 1, plus Oct–Nov).
- **New files:**
  - `core/xengine30.py`, `core/v30lib.py`
  - `studies/v30_deep_campaign.py`
  - `results/v30_*.csv`, this report
- **Not touched:** `cryptobot/*.py`, `portfolio.json`. Nothing committed.
