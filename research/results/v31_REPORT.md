# v3.1 campaign: drawdown controls for TBO v3.0 and chop-regime sleeves (Nov 2026)

Data to 2026-11-06. Engine `research/crypto/core/xengine31.py`, library `v31lib.py`, sleeve engine `sleeve31.py`;
campaign `research/crypto/studies/v31_drawdown_and_sleeves.py` (Tracks 1-4, stages `base t1 .. t8`), `v31_sleeves.py`
(Tracks 5-8), `v31_final.py` (`holdbig`, `combo`, `fillsize`, `volc4h`, `cluster_exact`). Every table below is a CSV in
`research/results/v31_*.csv`; `v31_summary_funnels.csv` has the funnel of every track.
**Nothing in `cryptobot/` was changed.**

## 1. Executive summary

* **7,433 configurations** were scored through the full gate funnel (5,705 in Tracks 1-8 + the combination stage, 1,728
  in the 4h VOLC follow-up). All runs used the exact 1-minute numba engine, on 7 CPU workers.
* **Parity.** `sim31` with every new control off reproduces the deployed v3.0 exactly: 1,333 / 1,333 trades, R and
  open-risk release time identical on all 5 coins. The money simulator matches `v30lib.money_nb` to the cent.
* **One new TBO exit rule passes every gate.** The failed-breakout stop tighten (Track 1):
  * The rule: from 8 h after the fill, at each hourly close, if the trade has reached +0.9R but never +1.5R and the
    close is below -0.2R, the stop moves from -1R to -0.5R.
  * Ratio ×1.06 (2020-23) / ×1.08 (2024-26); plateau 72%; phase copies 75% / 92.5%.
  * Untouched HOLD_BIG coins: drawdown lower in every period, and 2024-26 net goes from -8.8 to +6.5 units.
* **One of my own hypotheses passes** (Track 8, H8): the BTC stop-out cascade. When a BTC trade stops out, open ETH /
  alt trades in the same direction that are not yet at breakeven get their stop raised. -0.75R passes everything;
  -0.5R to 0R pass E1 and E4 but miss one phase period.
* **Together they are the v3.1 candidate.** All 10 combinations pass all gates. Recommended centre: rule at -0.2R +
  cascade to -0.25R, from $300:

| | v3.0 base | **v3.1 candidate** (rule -0.2R + cascade -0.25R) | rule -0.2R + cascade 0R |
|---|---|---|---|
| Fixed-unit ratio (2020-23 / 2024-26) | 1 / 1 | **×1.13 / ×1.16** | ×1.13 / ×1.18 |
| Phase copies with x > 1 (2020-23 / 2024-26) | | 82.5% / 85% | 82.5% / 85% |
| 2022 run | $1.125M, DD 26.0% | **$1.587M** | $1.614M |
| 2024 run | $61.0k, DD 34.0% | **$68.4k, DD 33.1%** | $69.2k, DD 33.1% |
| Sep 15 - Nov 6 2026 (from $300, worst drop; see note in section 9) | 40.1% | **37.1%** | 36.4% |
| 2-yr bootstrap median | $23.4k | **$27.2k** | $27.4k |
| 2-yr bootstrap p10 | $4.87k | **$6.43k** | $6.45k |
| 2-yr bootstrap dd90 | 56.7% | **52.5%** | 52.3% |
| TBO losing months 2024-26 (13 months, units) | -236.9 | **-192.8** | |
| HOLD_BIG net / DD 2024-26 (units) | -8.8 / 117.4 | **+20.1 / 99.8** | +12.4 / 98.0 |

  * It meets every E4 target in the brief.
  * The gain is real but modest: a 13-16% better return / drawdown ratio. The big money numbers are compounding.
  * The drawdown cut is 3-4 points, not the 25-33% seen in trade-v5. Crypto stop-outs are fast (median 7 h) and most
    losers never get far enough into profit to be rescued.
* **Near-pass sleeve: 4h VOLC + OI build-up** (section 6). Fails only the literal money gate, by 0.01-0.14 points of
  2024 drawdown. On top of the v3.1 package at 0.2 x BTC risk: dd90 52.5 -> 50.8%, p10 $6.4k -> $8.7k. Recommended for
  paper trading, not for money yet.
* **What failed:**
  * The other Part 1 mechanisms: take-profit at entry, market close on failed breakout, early dead-start stale rules,
    fill-time re-anchor, soft ratchet, cross-coin cluster cooldown, staggered release, dynamic cap, closed-loss brake,
    order validity window, chop max-ext, channel-width filters.
  * All Part 2 sleeves: 3,124 configurations, none reaches S2. Session and funding plays are negative after costs on
    every config out of sample. The trap snapback is breakeven at best. 4h VOLC + OI is the only positive family; see
    section 6.
* **A finding that contradicts the brief's premise.** Late fills (180-240 min into the 4h bar) are the *best* TBO trades:
  +1.06R / +1.75R / +1.02R per trade in 2020-23 / 2022-23 / 2024-26, against +0.30 / +0.52 / +0.38R for first-hour
  fills. Cancelling late orders therefore fails, 0 of 15 configs.

## 2. Baseline reproduced (`v31_base.csv`, `money_base.pkl`)

| | Brief | Reproduced (same as `v30_deploy.csv`) |
|---|---|---|
| TBO trades | 1,333 | 1,333 |
| 2022 from $300 | $1.125M / 29.8% DD | $1,124,560 / 25.99% DD |
| 2024 from $300 | $61.0k / 34.0% DD | $60,969 / 34.04% DD |
| Bootstrap median / p10 / dd90 | $23.4k / $5.35k / 56.7% | $23,395 / $4,874 / 56.70% |

The brief's 29.8% (2022 DD) and $5.35k (p10) do not match `v30_deploy.csv`. The reproduced numbers are the reference
everywhere in this report.

The brief's anatomy reproduces exactly (`v31_T1_anatomy.csv`):
* 694 full stop-outs, -756.4R, median hold 7.0 h, p95 36.5 h, 98.7% before 48 h.
* 183 time exits / end-of-data trades, +1,437.6R.

## 3. Protocol (fixed before the runs)

**TBO rules:**
* **E1:** fixed-unit net / max drawdown ratio x > 1 in dev (2020-23; 2022-23 for OI / funding rules) AND out of sample
  (2024-01 .. 2026-11), with net units >= 92% of the base in both.
* **E2:** >= 60% of grid neighbours pass E1.
* **E3:** x > 1 in both periods on >= 75% of 40 phase-shifted copies. Removal / sizing rules must also beat >= 95% of 200
  random nulls.
* **E4:** literal, at the live risk.
  * 2022 and 2024 money >= base, 2024-26 drop < base, Oct-Nov 2026 drop <= base.
  * Bootstrap (1,000 two-year journeys) dd90 < base, p10 > base, median > base.
  * v3.0's drawdown-matched G6 is reported next to it.

**Sleeves:**
* **S1:** avg R > 0, PF >= 1.25, N >= 30 in both periods (DEV12).
* **S2:** 60% plateau.
* **S3:** >= 95% vs 200 random-entry copies.
* **S4:** HOLD39 avg > 0 in both periods.
* **S5:** monthly correlation with TBO <= 0.15 and positive R over TBO's losing months in 2022-23 AND 2024-26. No entry
  within 12 h of a panic trigger.
* **S6:** E4 next to bot + panic at 0.10 / 0.20 / 0.33 x BTC risk per trade.

About 7,400 configurations were scored. Expect some false E1 passes; E2-E4 and HOLD_BIG are there to remove them.

## 4. Part 1: TBO drawdown

### Track 1: failed-breakout scratch / early cut / dead start (1,684 configs)

**Anatomy:**

| Stop-outs that first reached | +0.4R | +0.6R | +0.8R | +1.0R | +1.25R |
|---|---|---|---|---|---|
| Share of the 694 | 55.3% | 40.6% | 28.0% | 19.3% | 8.8% |

* Winners >= 2R that dipped below -0.4R after reaching +0.5R: 18.8%. After +1.0R: 4.2%.
* Hence the MFE threshold sweet spot is 0.75-0.9R.

**Grid 1b** (8 T x 6 MFE x 5 thresholds x 4 actions = 960):
* Funnel: 255 E1 -> 79 E2 -> 2 E3 -> 2 E4.
* By action (median x dev / oos):

| Action | x dev | x oos | Configs passing E1 |
|---|---|---|---|
| Stop tighten -0.5R | 1.001 | 1.027 | 39% |
| Stop tighten -0.35R | 1.001 | 1.024 | 32% |
| Take-profit at entry | 1.000 | 0.982 | 19% |
| Market close | 0.999 | 0.989 | 16% |

  * Scratching the trade (take-profit at entry or market close) does not help; tightening the stop does.
  * T 6-8 h and MFE 0.75-0.9R are the best region.
* **Passers:**

| | `fb_T8_M0.9_c-0.2_tight-0.5` | `fb_T8_M0.9_c-0.3_tight-0.5` |
|---|---|---|
| x dev / oos | 1.060 / 1.082 | 1.056 / 1.076 |
| Plateau | 0.72 | 0.80 |
| Phase copies (dev / oos) | 0.75 / 0.925 | 0.85 / 0.925 |
| 2022 money | $1.51M | $1.45M |
| 2024 money / DD | $65.0k / 33.3% | $62.0k / 33.3% |
| Bootstrap dd90 | 53.2% | 53.9% |

  * Neighbours with -0.35R or T 4-6 h have strong x (up to ×1.15 oos) but fail the dev phase copies (12-40%).
* **1c variants (220):** 1m / 15m checks, a single check instead of continuous, take-profit at -0.05R, no cooldown after
  a rule exit. None passes E3; the hourly continuous version is best.
* **1d scope (40):** majors / alts / longs / shorts only. None passes E3; the all-coins version is the robust one.
* **1e early dead-start rule (432):** 0 pass E3. Replacing the 60 h stale stop is worse than adding to it (median x oos
  0.988 vs 1.000).
* **1f scope of 1e (32):** 2 pass E3, 0 pass E4. `stale_T24_N1.5_c0_tp0_add@longs` is dd-matched G6 only.

### Track 2: fill-time re-anchor and soft ratchet (412 configs)

* **2a re-anchor (312):**
  * Funnel: 84 E1 -> 45 E2 -> 4 E3 -> 0 E4 (3 pass G6 only).
  * Medians are flat (x 0.99-1.01). Only `1h / (4h/2)`, tighten-only, anchored to the arm distance shows anything:
    `ra_tight_1h/(4h/2)_lo0.8_a0.25_anc1` has x 1.014 / 1.031 and phase 0.85 / 0.825.
  * But 2024 money $66.7k at a 34.0% drop and bootstrap p10 $5.15k, with dd90 56.6% vs 56.7%: no drawdown benefit.
  * Widening on spike fills: x oos <= 1.004 median; never passes E3.
* **2b soft ratchet (100):** 26 E1 -> 1 E2 -> 0. +0.6R -> stop -0.75R improves DD (2024 31.2%) but cuts 2024 money to
  $56k. Every tighter version (-0.5 / -0.35R) loses winners.

### Track 3: portfolio heat (395 configs)

* **3a cluster cooldown (160) and BTC trap (40):**
  * 77 E1 -> 38 E2 -> 0 E3, and 8 -> 0.
  * The best (block every coin 24 h after 2 losing coins within 4-12 h) beats 98-100% of nulls but only 55-85% of phase
    copies.
  * **Caveat:** these rules feed back on themselves; a block removes a stop-out, which removes a block. The
    fixed-point iteration did not settle for 61% of the rules within 8 passes, so 3a is approximate.
  * An exact time-ordered resolver is in `v31_final.py cluster_exact`. It is correct but needs about 15-30 min per rule
    and phase copy, so it was not run for the whole grid.
  * The cascade (H8) gets most of the useful effect exactly, because BTC itself is never blocked.
* **3b staggered release (36):** ETH / alts blocked or sized x0.5-0.65 while BTC cools. 0 pass E2.
* **3c dynamic cap (11):**
  * BTC counted x1.25-1.5 while underwater almost never binds; money is identical to the base.
  * Freeing 50% of the cap at a soft ratchet lowers money. 0 pass E4.
* **3d closed-loss brake (72):** 21 E1 -> 17 E2 -> 0 E3. Best `brake_D7_X3.5_m0.5` reaches the 92nd percentile vs
  nulls (needs 95). Same verdict as `btc_streak.py`: like lowering risk.

### Track 4: entry microstructure (129 configs)

* **Fill minute (`v31_T4_fill_minute.csv`):** later fills are better in every period, the opposite of the premise.
* 4a validity window (15): 0 E1. 4b chop max-ext (60): 1 -> 0. 4c wide-box skip (18): 2 -> 0. 4d wide-box size
  (36): 4 -> 2 -> 0.
* A median 20-candle box is about 6-7 ATR. Wide boxes are not worse breakouts.

## 5. Track 8: own hypotheses (493 configs + 36)

| | Hypothesis | Configs | Result |
|---|---|---|---|
| H1 | Mini-panic tier: OI drop 6-10%, outside the panic tier, optional chop regime | 240 | 10 pass S1 on 11-70 trades per period, plateau 0: too few events |
| H2 | Post-flush block of TBO shorts (6-72 h after a panic trigger) | 20 | Nearly no effect: v2.8's OI-low filter already skips those shorts |
| H3 | Partial failed-breakout scratch (close 1/3-2/3 at the Track 1 trigger) | 96 | 60 -> 51 -> 3 -> **1 PASS**: `partial_f0.33_T8_M0.75_c-0.2`, x 1.03 / 1.02, a weaker sibling of the Track 1 rule (2024 $63.1k, dd90 55.4%). Not adopted: the stop tighten is better and simpler |
| H4 | Track 1 rule only in a choppy regime (BTC or own ER10 < 0.2-0.4) | 50 | 41 E1 -> 39 E2 -> 0 E3; high x oos (up to 1.10) but dev phase copies 25-35% |
| H5 | Chop-regime ETH / alt sizing | 24 | 0 E1 |
| H6 | Unconfirmed-crowd sizing | 12 | 2 -> 0 (joint breakouts are the runs, as in v2.x) |
| H7 | Weekend stop tighten / close (Fri 20:00 / Sat 00:00) | 10 | -0.25R x 1.004 / 1.021 but 0 E2; closing for the weekend halves the edge |
| **H8** | **BTC stop-out cascade** (ETH / alts' stop to -0.75 .. 0R, or close) | 5 | 4 E1 -> 4 E2 -> **1 PASS** at -0.75R; -0.5 / -0.25 / 0R pass E4 with phase 35-80% / 60-85% |
| H9 | Size first-60-min fills smaller (from the Track 4 table; data-suggested, so the null test carries the weight) | 36 | 15 -> 9 -> 0 E3 |

## 6. Part 2: sleeves (3,124 configs + 1,728 follow-up)

| Family | Configs | S1 | Best config out of sample |
|---|---|---|---|
| T5 VOLC (1h / 4h, ATR or BB squeeze, trend / range / hybrid) | 900 | 0 | 4h ATR14/ATR100 < 0.65, N 8, TP 3R, 36 h: +0.157R, PF 1.22 (dev +0.171R, PF 1.25). Hourly versions lose after costs |
| T5b + OI build-up / scratch | 150 | 3 | 4h, OI 24h >= 0: +0.154R, PF 1.28 (2022-23: +0.163R, PF 1.30); 97% of this grid positive oos; plateau undefined (built around 10 different starting configs) |
| **T5c 4h VOLC + OI, regular grid** | 1,728 | *see below* | |
| T6 trap snapback (+ OI) | 648 + 324 | 0 | Breakeven at best (+0.05 / +0.00R); only 2-4% of configs positive oos. Confirms the Oct 2026 failed-breakout-fade result |
| T7a Asia-box breakout (+ OI) | 108 + 108 | 0 | -0.05R per trade; 0% positive oos |
| T7b Judas sweep fade (+ premium) | 64 + 64 | 0 | -0.15R per trade; 0% positive oos |
| T7c funding-settlement snapback | 288 | 0 | -0.06R per trade; 0% positive oos |

T5c_RESULT

## 7. Recommendation

1. **Adopt the Track 1 rule.** Failed-breakout stop tighten: T 8 h, hourly closes, MFE >= 0.9R, close < -0.2R, never at
   +1.5R, stop to -0.5R, and a cooldown after a rule exit. It passes every gate, holds on 14 untouched coins, and is a
   one-coin rule.
   * Bot work: an hourly check in `bot.check_position` and a `stop_level` stage in `strategy.py`.
   * Parity tests: `test_bot_sim.py` must be extended first.
2. **Adopt the BTC cascade next to it** (stop to -0.25R; -0.75R if you want the setting that passed alone).
   * It needs cross-coin state: the BTC bot's stop-out must reach the other bots within a minute (`run_all.py` shared
     state).
   * `test_cap_sim.py` will need a cascade check.
   * Alone it is borderline (1 of 5 settings passes everything). Its value is in the combination: 10 / 10 pass.
3. **Do not add a sleeve with money yet.** The 4h VOLC + OI sleeve (section 6) is the one to paper-trade and re-test.
4. **Expectation:** about 3-4 points less 2-year dd90 and ~15% better return / drawdown. Most of Oct-Nov 2026's
   -33% would still have happened: the package saves 3.1R of the 18.7R lost.
   * Oct 12: ETH -1.15 -> -0.40R, SOL -1.13 -> -0.60R.
   * Nov 4: SOL -1.11 -> -0.39R, ETH -1.10 -> -0.55R.
   * The BTC trades themselves are still full stops.

## 8. Caveats

* About 7,400 configs scored. The passing rule's dev phase share (75%) is exactly at the threshold; its -0.3R neighbour
  has 85%.
* The combination grid is small (2 x 5), so its plateau is weak evidence. The component rules carry the robustness.
* The cluster-cooldown iteration is approximate (section 4, Track 3).
* Sleeve sizing assumes no cap on concurrent sleeve trades. HOLD_SMALL used an hourly-bar approximation (no 1m data);
  DEV12 and HOLD_BIG used the 1m engine.
* Stop fills are modelled as in v3.0 (pessimistic fill minute). The live slippage on the tightened stops is unknown.


## 9. v3.1b follow-up (`studies/v31b_surgical_followup.py`, results `v31b_*.csv` and `v31_v31b_*.csv`)

**Correction to the sections above.** The "Oct-Nov 2026 drop" in the E4 money columns (`dd_fall26`: 40.1% base, 37.1%
package) is computed from **Sep 15** to Nov 6, 2026, not Oct 1. From Oct 1, the v3.0 base falls 32.6% (worst drop
33.6%); the risk table below uses Oct 1.

Rules marked "on PKG" are scored against the v3.1 package (its own 41 phase copies and money base).
PKG = 1,355 trades; 2024 $68,400 / 33.1%; bootstrap median $27,182, p10 $6,434, dd90 52.5%.

1. **H3 partial scratch and T2a re-anchors on PKG.**
   * The H3 passer is already listed in section 5 (not adopted). On PKG, 0 of 24 partial-scratch configs pass E1: it
     fires on the same trades as the stop tighten.
   * The 8 best T2a re-anchors on PKG all pass E1 / E2: x 1.02-1.04, 2024 $73-74k, median $28.5-29k, p10 $6.5-6.9k.
     They fail E3 (dev phase copies 48-58%) and E4: the 2024 drop stays 33.1% and dd90 52.2-52.8%. They add return, not
     drawdown protection.
2. **Non-cycling cluster size-down / cap-tighten** (exact in one pass: the trade list never changes).
   * Size-down, 180 configs per base: v3.0 18 E1 -> 0 E2; PKG 3 -> 0.
   * Best: after 2 coins stop out within 24 h, size x0.35-0.65 for 16 h. On v3.0: dd90 56.7 -> 54.7%, Sep-Nov 2026
     40.1 -> 37.6%. On PKG: dd90 52.5 -> 50.9%, 37.1 -> 34.6%. But the 2024 drop is unchanged, 5-7% of dev net is lost,
     and there is no plateau.
   * Cap-tighten (x0.65 / 0.75, 120 configs): the cap rarely binds (BTC is exempt and causes most clusters): x =
     1.000 +- 0.003, 0 E1 on v3.0, 6 -> 0 on PKG. Harder squeezes lose money (x0.3: 2024 $42.9k, drop 36.6%).
3. **Fast-fakeout defence** (T 1-4 h, 15m / 1h checks, never reached +0.2-0.4R, close < -0.45 .. -0.75R -> stop
   -0.65 / -0.75 / -0.8R or take-profit at entry; 384 configs per base).
   * v3.0: 37 E1 -> 0 E2. PKG: 17 -> 0. Out-of-sample medians are below 1 for every action and every T.
   * Why (`v31b_3_fast_anatomy.csv`): 20% of the eventual >= 2R winners have not reached +0.25R after 1 h (31% not
     +0.4R); slow starters look like fakeouts, dip, and the tightened stop cuts them.
   * Oct 1 - Nov 6 2026 had 18 full stop-outs, 11 under 8 h and 7 under 4 h (October alone: 13, 6 under 8 h).
4. **4h VOLC + OI on the core 5 vs DEV12** (`v31b_4_volc_stats.csv`, `v31b_4_volc_money.csv`).

   | N10, 36 h | 2022-23 n / avg R / PF | 2024-26 n / avg R / PF |
   |---|---|---|
   | Core 5 | 60 / +0.32 / 1.67 | 56 / +0.25 / 1.49 |
   | DEV12 | 157 / +0.31 / 1.64 | 155 / +0.20 / 1.37 |

   * On PKG, 62% of the 192 sleeve variants pass E4 against v3.0.
   * Against PKG itself, only **core 5 at 0.25 x BTC risk** passes (uncapped or capped): 2022 $1.61M, 2024 $74.1k with
     the drop at 32.9% (PKG 33.1%), Sep-Nov 2026 35.8%, median $29.3k, p10 $7.59k, dd90 51.2%.
   * DEV12 variants give more money and lower dd90 (50.1% with the 0.5 x cap gate) but a 2024 drop of 33.17-33.20%:
     0.05-0.08 points above PKG.
   * Counting VOLC inside the open-risk cap, or arming it only while open TBO risk < 0.5 x cap, changes little; the
     gate gives the lowest dd90.
5. **Iso-return / risk-scaled table** (`v31b_5_risk_table.csv` = VOLC DEV12 0.2 x; `v31b_5_risk_table_core5.csv` =
   core 5 0.25 x). k scales every risk; "smooth" = BTC 5 / 4.2 / 2.2% (ETH 2/3 of BTC, alts as live), cap 1.0 x BTC.
   Oct-Nov here = Oct 1 - Nov 6 2026 from $300.

| Package | Ladder | k | 2022 | 2024 (DD) | Oct-Nov 26 (DD) | Losing months 2024 run (avg) | Boot median | p10 | dd90 |
|---|---|---|---|---|---|---|---|---|---|
| v3.0 | live | 1.00 | $1.125M | $61.0k (34.0%) | -32.6% (33.6%) | 12 / 35 (-7.3%) | $23.4k | $4.87k | 56.7% |
| v3.0 | live | 0.80 | $381k | $30.1k (28.1%) | -26.8% (27.7%) | 12 (-5.8%) | $15.4k | $3.37k | 49.3% |
| v3.1 PKG | live | 1.00 | $1.587M | $68.4k (33.1%) | -28.6% (30.4%) | 11 (-6.1%) | $27.2k | $6.43k | 52.5% |
| v3.1 PKG | live | 0.90 | $784k | $54.1k (30.3%) | -26.1% (27.8%) | 11 (-5.5%) | $21.4k | $5.23k | 49.1% |
| **v3.1b (VOLC DEV12 0.2)** | live | 1.00 | $2.005M | $83.6k (33.2%) | -26.0% (31.3%) | 10 (-6.7%) | $32.9k | $8.72k | 50.8% |
| **v3.1b (VOLC DEV12 0.2)** | live | 0.95 | $1.420M | $66.7k (31.8%) | -24.8% (30.0%) | 10 (-6.4%) | $28.8k | $7.49k | 48.9% |
| **v3.1b (VOLC DEV12 0.2)** | **live** | **0.90** | **$1.068M** | **$64.3k (30.3%)** | **-23.6% (28.6%)** | **10 (-6.1%)** | **$25.8k** | **$6.78k** | **47.1%** |
| v3.1b (VOLC DEV12 0.2) | live | 0.85 | $919k | $51.0k (28.9%) | -22.4% (27.2%) | 10 (-5.7%) | $22.4k | $5.97k | 45.6% |
| v3.1b (VOLC DEV12 0.2) | live | 0.80 | $621k | $41.7k (27.4%) | -21.2% (25.8%) | 10 (-5.4%) | $20.2k | $5.32k | 43.8% |
| v3.1b (VOLC DEV12 0.2) | smooth | 1.00 | $1.029M | $47.6k (28.9%) | -21.8% (26.8%) | 10 (-5.8%) | $22.8k | $5.83k | 45.5% |
| v3.1b (VOLC DEV12 0.2) | smooth | 0.90 | $590k | $36.0k (26.3%) | -19.8% (24.4%) | 10 (-5.3%) | $18.3k | $4.75k | 42.3% |
| v3.1b (VOLC core5 0.25) | live | 0.95 | $1.227M | $72.6k (31.5%) | -25.9% (29.1%) | 11 (-5.6%) | $26.5k | $6.88k | 49.6% |
| v3.1b (VOLC core5 0.25) | live | 0.90 | $1.043M | $58.2k (30.1%) | -24.7% (27.8%) | 11 (-5.3%) | $23.5k | $6.07k | 48.0% |

* **Iso-return point.** v3.1b at k = 0.90 on the live ladder still beats v3.0 on 2022 / 2024 money, bootstrap median
  and p10, with the 2024 drop at 30.3% (v3.0 34.0%) and dd90 at 47.1% (v3.0 56.7%).
* **The brief's drawdown target** (2024 DD < 25-28%, dd90 < 42-45%) needs k = 0.80 on the live ladder or the smooth
  ladder at k = 0.90-1.00.
  * Wealth there is about 70-80% of v3.0 in 2024 and 78-98% of its bootstrap median: it does **not** fully match v3.0.
  * At the same scaling, v3.0 itself is far worse (k = 0.80: $30.1k, median $15.4k, dd90 49.3%).
* **Status of the VOLC sleeve.** It is in the iso-return package on the strength of section 6 and item 4 above. Its
  own gate status is unchanged (near-pass: S6 missed by < 0.1 point of 2024 drawdown; found in a follow-up grid). The
  same table without it is the v3.1 PKG rows.
