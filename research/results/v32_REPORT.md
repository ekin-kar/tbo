# v3.2 campaign: crypto market regimes (Nov 2026, data to 2026-11-06)

Code:
* Regime engine: `research/crypto/core/crypto_regimes.py`.
* Engine: `core/xengine32.py` (= v3.1 exactly with its new controls off) and `core/v32lib.py`.
* Campaign: `studies/v32_market_regimes_and_alpha.py` (stages `census s2 s3 s3b2 s4 s5 quintiles`).
* Page: `reports/market_regimes.html` (`pages/make_regimes_html.py`).

Results:
* `research/results/v32_regime_census.csv` (full) and `v32_regime_census_view.csv` (compact).
* `v32_quintiles.json`, `v32_curves.json`.
* `v31_v32_*.csv`: every setting with its gates (named through the v3.1 gate code).
* `v32_S4c_volc_boost_money.csv`.

**Read-only on `cryptobot/`.**

**Base** = v3.1 as deployed: TBO v3.1 (1,355 trades; 41 phase copies) + Panic v3.0 + VOLC 0.25× + ladder ×0.95. From $300:

| | 2022 run | 2024 run | Sep 15 - Nov 6 2026 drop | Bootstrap median / p10 / dd90 |
|---|---|---|---|---|
| v3.1 base | $1.215M | $70.8k, drop 31.5% | 34.4% | $26.4k / $6.63k / 49.5% |

**Gates:** unchanged from v3.1.
* E1: fixed-unit ratio > base in 2020-23 AND 2024-26, with net ≥ 92% of the base.
* E2: ≥ 60% of grid neighbours pass E1.
* E3: x > 1 on ≥ 75% of 40 phase copies; ≥ 95% vs 200 random nulls for sizing rules.
* E4: money and 1,000 two-year journeys vs the base.

The regime classifiers were fitted on 2020-23 only.

## 1. Executive summary

* **1,490 settings over 9 tracks. One family passes all four gates: volatility-regime sizing (Stage 5).**
  * The rule: size each TBO trade by its own coin's daily ATR14 / ATR100 at entry (larger after a quiet spell, smaller
    when volatility has already expanded).
  * The gentlest passing version is **×1.15 when calm (≤ 0.79), ×0.75 above the median (≥ 0.93)**:
    * ratio ×1.14 / ×1.13; plateau 89%; beats 100% of random nulls; phase copies 95% / 82.5%;
    * from $300: 2022 $1.304M, 2024 **$77.3k with drop 29.4%** (31.5%), Sep-Nov 2026 drop 31.1% (34.4%);
    * bootstrap median $26.9k, p10 $6.95k, **dd90 47.3%** (49.5%).
  * 4 of the 44 settings pass everything, 15 pass E1-E3, and the median of the whole grid is ×1.07 / ×1.08.
* **Everything else failed**, mostly decisively:
  * regime-conditional profit locks / take-profits / shorter holds (Stage 2, 341 settings, 0 pass E1; median ×0.74 / ×0.88);
  * regime vetoes / size-downs (Stage 3a, 120: 20 E1, 0 plateau);
  * regime-conditional early cut, both versions (Stage 3b, 504 + 336: 0 and 26 E1, 0 plateau);
  * short-side exit physics (Stage 3c, 99: 0 E1);
  * BTC-chop and breadth risk scaling (Stage 4, 37: 3 E1, 0 plateau);
  * funding-extreme size-downs (9: 0 E1).
* **Why: TBO's edge does not live in a regime.**
  * On the core 5, almost every regime × direction cell is positive in all three periods.
  * The +1.5 … +3R round trips (24.8% of trades) happen at a 20-40% rate in every regime, so locking them early clips the
    runners everywhere.
  * The only feature that orders trade quality the same way in both periods is the coin's volatility ratio.
* **Caveat for the winner.** On the 14 untouched coins (HOLD_BIG):
  * 2020-23: clearly better (ratio 2.09 → 2.69; drop 74 → 60 units).
  * 2024-26: drop lower (108 → 96) but net slightly negative (+6.5 → −1.9 units, base near breakeven there).
  * Partial support, not a full confirmation.
* **Optional:** a VOLC share of 0.40 instead of 0.25 adds a little everywhere (median $27.7k, dd90 49.0%; with the volatility
  sizing $28.3k / 47.4%). Each VOLC position grows to about 2.2× the balance, and VOLC is the least proven part.

## 2. Stage 1: the regime engine and census

**Features** (daily, per coin, known at the day's close):
* Dir20, Er20, R2s60 (signed R² of a 60-day log regression), VolReg (ATR14/ATR100), Ovl10 (10-day bar overlap), Bofu /
  Bofd (20-day up / down follow-through);
* Chg5, distance from EMA50 / EMA200;
* Bo4u / Bo4d: 45-day share of 4h 20-candle breakouts still beyond the level 24 h later.

**Market:** DEV12 breadth (share above EMA50), net 4h breakout highs − lows, dispersion, 7-day correlation with BTC.

**Derivatives:** OI 90-day rank, 3 / 7-day OI change, funding 90-day rank, premium z.

**Classifiers** (fitted on 2020-23 DEV12 pooled, frozen):

| Classifier | States |
|---|---|
| RB (readable) | UpClean, UpChop, FlatCalm, FlatWild, DownChop, DownClean. Dir20 terciles −1.05 / +1.34 ATR; clean = Er20 ≥ 0.207 and Ovl10 ≤ 0.451; calm = VolReg ≤ 0.908 |
| TS (two-speed) | 20-day trend × 5-day swing × volatility: 12 states |
| HM | 6 k-means clusters of the 7 z-scored features, assigned by nearest centre |

The state mixes are stable between 2020-23 and 2024-26.

**Census (core 5, avg R per trade 2020-21 / 2022-23 / 2024-26)** — `v32_regime_census_view.csv`:
* Positive almost everywhere.
* Consistently negative: only shorts in an up-ish 20-day state (HM H3 short −0.69 / – / −0.65 on 9 / 0 / 10 trades; HOLD_BIG
  −0.34 on 59) and RB UpClean shorts (2 + 2 trades).
* Weakest long cell: longs while BTC is in UpChop (+0.38 / +0.16 / +0.18; HOLD_BIG −0.27).

**Round-trip leak** (v3.1 list):
* 607 of 1,355 trades reached +1.5R; 336 of them (24.8% of all) closed below +0.1R (−34.6R in final R).
* By MFE band, the share that closed below +0.1R:

  | MFE | +1.5-2R | 2-3R | 3-4R | 4-5R | ≥ +5R |
  |---|---|---|---|---|---|
  | Closed below +0.1R | 125 of 126 | 125 of 129 | 56 of 75 | 30 of 51 | 0 of 226 |

**Feature quintiles** (avg R, calm / low → high; `v32_quintiles.json`). Only the coin's VolReg is monotonic in both periods:

| VolReg quintile | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|---|---|---|---|---|
| 2020-23 | +1.25 | +0.66 | +0.40 | +0.71 | +0.33 |
| 2024-26 | +1.91 | +0.60 | +0.42 | +0.35 | +0.01 |

Overlap, follow-through, efficiency, breadth, correlation, funding and OI change order between periods.

**Worst drawdown windows, in R:**
* Dec 2024 - Jan 2025: −15.2R (longs −12.7R; BTC FlatWild days −10.4R).
* Oct - Nov 2026: −15.6R (spread over every state).
* Jan 2021, summer 2023 and Feb - Apr 2025 were positive in R. Their money drops were sequencing (sizing / timing), not a
  losing regime.

## 3. Stages 2-5 (funnels: settings → E1 → E2 → E3 → PASS; median x 2020-23 / 2024-26)

| Track | Settings | E1 | E2 | E3 | PASS | Median x |
|---|---|---|---|---|---|---|
| S2 regime-conditional locks +0.75..1.5R at +2..3.5R / TP 2.5-4R / hold 48-72h; 9 regimes; at entry or while in the regime | 341 | 0 | 0 | 0 | 0 | 0.74 / 0.88 |
| S3a veto / ×0.5 by RB, HM, TS and BTC-RB state × side | 120 | 20 | 0 | 0 | 0 | 0.99 / 1.00 |
| S3b early cut (2-6 h, never +0.3R, below -0.4..-0.6R: close or stop -0.6R), 7 regimes | 504 | 0 | 0 | 0 | 0 | 1.00 / 0.95 |
| S3b2 the same, applied to one side only (bug fix: S3b applied the rule to both sides) | 336 | 26 | 0 | 0 | 0 | 1.00 / 0.98 |
| S3c own short exits (hold 36-120 h, lock, TP 3.5-6R) | 99 | 0 | 0 | 0 | 0 | 0.91 / 0.92 |
| S4 risk x0.5-0.75 in BTC chop states (+1.1 in clean trends) | 28 | 3 | 0 | 0 | 0 | 0.93 / 1.05 |
| S4b breadth extremes | 9 | 0 | 0 | 0 | 0 | 1.00 / 1.00 |
| **S5a volatility-regime sizing (own coin / BTC)** | 44 | 31 | 28 | 15 | **4** | **1.07 / 1.08** |
| S5b funding extremes | 9 | 0 | 0 | 0 | 0 | 0.91 / 1.00 |

**S3a's E1 passers are all "wild" states** (for example TS Up/dn/wild longs ×0 → ×1.04 / ×1.25): the same volatility
signal, which S5a tests as an ordinal grid.

**S5a passers**, from $300:

| Calm boost / wild cut | x | 2024 run | Sep-Nov 26 drop | Boot median / p10 / dd90 |
|---|---|---|---|---|
| ×1.15 / ×0.75 above the median | 1.14 / 1.13 | $77.3k, 29.4% | 31.1% | $26.9k / $6.95k / 47.3% |
| ×1.3 / ×0.75 above the median | 1.21 / 1.13 | $72.4k, 29.5% | 31.1% | $29.8k / $7.74k / 48.1% |
| ×1.3 / ×0.65 above the top tercile | 1.13 / 1.11 | $83.0k, 30.2% | 33.9% | $32.4k / $8.51k / 49.2% |
| ×1.3 / ×0.5 above the top tercile | 1.11 / 1.11 | $77.6k, 28.3% | 33.6% | $32.7k / $8.87k / 49.6% |

* BTC's VolReg instead of the coin's own: no pass.
* The ×1.3 boosts add risk on calm entries: BTC at 5.7% × 1.3 = 7.4% of the balance on one trade under $1,000.

## 4. Recommendation

* **v3.2 candidate:** TBO risk × 1.15 when the coin's daily ATR14 / ATR100 ≤ 0.79 at entry, × 0.75 when ≥ 0.93 (both read
  from the last daily close; the thresholds are the 2020-23 terciles / median, frozen).
  * It is a sizing rule only: the bot's orders and exits stay as they are, so it needs no new parity test of the exits.
  * Live it needs the daily ATR100 (the bot already downloads 500 daily candles) and a multiplier in `bot.size()` (and the
    cap check).
  * Expected effect, from $300: 2024 run drop 31.5% → 29.4%; bootstrap dd90 49.5% → 47.3%; median and p10 slightly higher.
  * Two warnings: on untouched coins in 2024-26 it cut drops but not losses, and the improvement is modest, about two
    drawdown points.
* **Do not adopt** any regime exit, veto, early cut or regime risk switch; the census shows TBO's edge is not regime-bound.
* The regime engine and page stay as a monitoring tool: `reports/market_regimes.html`.
