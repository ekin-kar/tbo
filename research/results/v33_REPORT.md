# v3.3 campaign: structural frontiers on top of TBO v3.2 (Nov 2026, data to 2026-11-06)

Code: `research/crypto/studies/v33_structural_frontiers.py` (stages `base t1a t1b t2 t3v t3p final`) and
`v33_t0_volc_collision.py` (Track 0).

Engine: `core/xengine33.py` = xengine32 + checkpoint rule C, which also acts after breakeven. With C off it gives the
v3.1 / v3.2 list exactly: 1,355 / 1,355 trades, the same R.

**Read-only on `cryptobot/`.** Branch `v33-research`.

**Base** = v3.2 as deployed (946b026):
* The v3.1 trade list × the wild-pullback size.
* The v3.2 ladder, live cap counting.
* Panic v3.0 + VOLC 0.25.
* Reproduced exactly, from $300: 2022 $2,030,648 / 24.5%, 2024 $74,343 / 26.2%, bootstrap $28,770 / $7,672 / 44.4%.

**Gates** (v3.2c's, fixed before the runs):

| Gate | TBO rules | Sleeve rules (VOLC, panic) |
|---|---|---|
| E1 | Uncapped x > 1 in 2020-23 and 2024-26 with net ≥ 92%, AND the capped account x > 1 in both | The sleeve's own R stream (2022-23 / 2024-26), x > 1 with net ≥ 92% |
| E2 | Plateau 60% | Plateau 60% |
| E3 | Engine rules: ≥ 75% of 40 phase copies (uncapped and capped). Sizing rules: also ≥ 95% of 200 nulls. HOLD_BIG shown | ≥ 75% of 200 paired month-block bootstraps; VOLC also x > 1 on its 7 out-of-universe coins |
| E4 | Money and 1,000 two-year journeys vs v3.2 | Whole-system money vs v3.2 |

## Funnel (2,005 settings)

| Track | Settings | E1 | +E2 | +E3 | PASS (G6) |
|---|---|---|---|---|---|
| 1A late-life lock (T 48-96 h, MFE ≥ 2-3.5R, stop +0.5-1.5R, at T or at a close below +X R) | 380 | 56 | 28 | 4 | **0** (0) |
| 1B zone-2 failed extension (MFE ≥ 2-3.5R, from 16-48 h, 1h / 4h close below +thr R or a 60-80% give-back -> stop +0.25-0.75R or limit TP +1-1.5R) | 1,344 | 325 | 125 | 20 | **6** (10) |
| 2A FlatWild cut (coin / BTC VolReg ≥ v, \|Dir20\| ≤ d, x0.25-0.5) | 72 | 0 | 0 | 0 | 0 |
| 2B Q5 climax cut (VolReg ≥ 1.12-1.25, any or after a 5-day run ≥ 1.25-2.25 ATR) | 36 | 0 | 0 | 0 | 0 |
| 2C counter-macro short cut (short while Dir20 ≥ 0.5-1.25 ATR) | 12 | 0 | 0 | 0 | 0 |
| 3Va VOLC failed-breakout tighten (T 4-12 h, MFE ≥ 0.4-0.8R, close < 0 / -0.15 / -0.25R -> stop -0.35 / -0.5R or close) | 108 | 18 | 0 | 0 | 0 |
| 3Vb VOLC lock (+0.85 / 1.0 / 1.15R -> -0.2 / 0 / +0.25R) | 9 | 1 | 0 | 0 | 0 |
| 3Pa panic failed-bounce tighten | 36 | 0 | 0 | 0 | 0 |
| 3Pb panic same-coin repeat-flush block / half size | 8 | 0 | 0 | 0 | 0 |

CSVs: `research/results/v33_*.csv` (one per track), `v33_final_comparison.csv`.

## Track 0: the 2 extra VOLC trades (solved)

**Cause** (exact logs):
* BTC 2023-04-10: at the 12:00 4h close both the trend bot and `volc.py` armed a BUY stop at 28,539.1.
* VOLC's 10-candle high was also TBO's 20-candle high, so both triggered in the 15:41 minute.
* `volc.py` sold its 0.289 BTC back at market at 15:42: two taker fees and slippage for a 1-minute trade.
* BNB 2023-07-24: the same, SELL at 240.18.
* The research twin blocks VOLC fills from a TBO fill's minute on, so it never had them.

**The guard.** VOLC's long level (10-candle high) can never be above TBO's (20-candle high), and vice versa for shorts. So
the guard "no VOLC stop when the trend bot's resting entry on that side is at a level reached first or at the same time
(buy: tbo ≤ volc, sell: tbo ≥ volc)" removes exact ties only.

**Result.** Tested as a test-time patch of the simulated client (`v33_t0_volc_collision.py`, the full 2021-26 v3.2
parity run):
* 23 VOLC stop orders not placed (all exact ties).
* VOLC: 0 trades only in the bots (was 3: BTC 2023-04-10, BNB 2023-07-24 and a third, BNB 2022-12-07).
* 114 / 115 entries in the same minute; the last (SOL 2022-12-11) is the known 1-minute tick-rounding shift.
* Exits 112 / 115 in the same minute: 1 in 2021-22, 2 in 2025-26 (take-profit limits rounded to the tick).
* TBO parity unchanged.

**Live implementation (when you decide):**
* `volc.py` runs in its own process and may arm before the trend bot at the same close. It should check the exchange's
  open `tbo_..._in_` orders when it places a stop, and again at each poll: cancel its stop if a trend-bot entry on that
  side sits at a tie level.
* This removes a costly, harmless-looking glitch (each collision is a round trip at a loss of fees).

## Track 1: the +1.5 ... +4.8R round-trip leak

**1A late-life lock** (380 settings): no pass.
* The E1-E3 survivors (T 96 h, MFE ≥ 3.5R, stop +0.5R) barely fire: ×1.002 / ×1.001.
* The stronger family (T 96 h, MFE ≥ 2R, stop +0.75R): ×1.009 / ×1.009, capped ×1.010 / ×1.073, and it passes the money
  gates. But it holds on only 52.5% of the 2024-26 phase copies.

**1B zone-2 failed extension** (1,344 settings): 6 pass all four gates.
* Every passer is at the lowest MFE floor tested (+2.0R, the grid edge) with a stop (not a take-profit: 41% vs 7% E1).
* Best: **from 48 h, at each hourly close, a trade that has reached ≥ +2R (never +5R) and closes back below +0.75R gets its
  stop at +0.25R** (`t1b_m2.0_T48_thr0.75_stop0.25_G60`).
  * Ratio ×1.008 / ×1.018; capped ×1.008 / ×1.031; plateau 67%.
  * Phase copies 92.5% / 100% (uncapped and capped).

**Final comparison** (from $300; whole system):

| | 2022 run | 2024 run | Sep-Nov 26 from $300 / in the 2024 run | Oct-Nov 26 | P(≥ $10k) | Bootstrap median / p10 / dd90 |
|---|---|---|---|---|---|---|
| v3.2 deployed | $2.031M, 24.5% | $74.3k, 26.20% | 26.6% / 14.2% | 24.6% | 87.1% | $28.8k / $7.67k / 44.4% |
| + 1B best (T48, 1h, < +0.75R -> +0.25R) | $2.275M, 23.2% | $78.2k, 26.20% | 26.4% / 14.1% | 24.6% | 87.6% | $29.4k / $8.09k / 44.0% |
| + 1B (T36, 4h, < +0.75R -> +0.25R) | $2.101M, 24.2% | $76.6k, 26.20% | 26.6% / 14.2% | 24.6% | 87.4% | $29.4k / $7.98k / 44.3% |
| + 1B (T48, 4h, < +0.75R -> +0.25R) | $2.101M, 24.3% | $77.1k, 26.20% | 26.6% / 14.2% | 24.6% | 87.4% | $29.5k / $7.93k / 44.2% |

**Caveats:**
* The gain is small: about +2% on the bootstrap median, +5% on p10, -0.4 points of dd90.
* The 2024 drop is unchanged (26.2015% vs 26.20146%). The rule never touches that episode's trades, and E4's
  "strictly lower" holds only by rounding noise.
* **HOLD_BIG contradicts it.** On the 14 coins the bot does not trade, 2024-26 net falls from +5.4 to between -7.7 and
  -19.1 units for every passer. For the best one, 2020-23 also goes the wrong way (×0.93).
* Gates are pre-registered, so these count as passes. The out-of-universe evidence says the gain may be specific to the
  core 5.

## Track 2: cut-only regime sizing (no pass)

On top of v3.2 every cut loses net in at least one period (x 0.96-1.04).
* **FlatWild:** the Dec 2024 BTC FlatWild losses (-10.4R) do not generalise. FlatWild cuts also cut the range breakouts
  that later trend.
* **Q5 climax:** the cut is close to neutral (×0.99-1.00).
* **Counter-macro shorts:** too few trades to matter (×0.999 / ×1.006 at d 1.25).
* v3.2's wild-pullback rule already takes the volatility-regime signal that sorts trade quality. Nothing orthogonal is
  left in these features.

## Track 3: sleeve protection (no pass)

**VOLC failed-breakout tighten:**
* 18 E1 passers (best ×1.20 / ×1.22 at T 12 h, MFE 0.8R, close < 0 -> close), all in islands (plateau ≤ 0.56).
* Bootstraps 35-49%; mixed on the 7 out-of-universe coins.
* VOLC has 115 trades; the stream is too short to separate a rule from noise.

**VOLC lock:** one isolated E1 (+1.15R -> 0R), plateau 0.

**Panic failed-bounce:** fires on 2 of 208 trades (both 2022-23), and both would have exited at about the same price at the
12 h time exit. x = 1.000 in 2024-26.

**Panic repeat-flush block / half:** hurts in both periods (×0.79-0.93). A coin flushed again soon after a stop-out is a
GOOD panic trade.

## Recommendation

* **Track 0: fix it.** Implement the tie guard in `volc.py` (place-time check plus a per-poll re-check of the trend bot's
  resting entry order), with a parity run. It removes 3 losing round trips in 2021-26 and brings VOLC to research parity.
* **Track 1B: a low-confidence candidate.** It passes the gates and adds a little money with lower dd90. But the 2024 drop
  does not move and the untouched coins say no.
  * If adopted, take the best version (from 48 h, hourly closes, MFE ≥ +2R, close < +0.75R -> stop +0.25R).
  * It would be a new stop stage in `strategy.stop_level` / `bot.py`, with a parity test.
  * My advice: watch it rather than deploy now, or deploy only together with Track 0's fix and a forward check.
* **Not adopted:** late locks (1A), regime cuts (2A-2C), VOLC tighten / lock, panic tighten / repeat-flush.

Engineering note: the post-processing pools (HOLD_BIG, VOLC rebuilds, money) now use the `spawn` start method. A `fork`
after the engine pools deadlocked once (futex waits), and the run was restarted.
