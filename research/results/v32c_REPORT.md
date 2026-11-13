# v3.2c: the v3.2b candidate re-tested exactly, smooth VolReg sizing, and the ladder's first tier (Nov 2026)

Code: `research/crypto/studies/v32c_exact_engine_and_ladder.py` (stages `s1 s2 s3`).
* `core/v32lib.trades32(ofilt=...)` edits the entry orders before the 1-minute run.

**Read-only on `cryptobot/`.**

**Corrects v32b:** the v32b "skip" was tested by zeroing trades on the frozen v3.1 list. Inside the engine it fails the
money gate (below).

## Stage 1: the wild × 5-day-pullback rule, exactly

**How the skip is modelled in the engine.**
* The entry orders the live bot would not arm are dropped. The check runs at each order's own 4h arming close, by side:
  coin VolReg ≥ vr and dir × Chg5 / ATR14 ≤ c, from the last daily close.
* Then everything is re-run: re-entries, cooldowns, BTC first → the cascade on ETH / alts, then VOLC (blocks and
  hand-overs) around the new TBO list.
* Parity: the engine base = the v3.1 package on all 41 phase copies; VOLC rebuilt around the base = `volc_trades_v31`
  exactly.

**Engine skip results (9 settings):** E1 9, E2 9, E3 5, **PASS 0**.

| Setting | Trades removed (R) | New trades (R) | x 2020-23 / 2024-26 | 2024 run engine (frozen list) | Boot median / dd90 engine (frozen) |
|---|---|---|---|---|---|
| vr 0.98, c −0.25 | 122 (−17.7) | 40 (+8.9) | 1.059 / 1.248 | $77.6k, 32.0% ($77.2k, 27.6%) | $29.5k / 45.3% ($29.5k / 44.6%) |
| vr 1.05, c −0.25 (v32b's pick) | 98 (−22.8) | 32 (0.0) | 1.050 / 1.084 | **$67.3k, 32.0%** ($76.3k, 27.6%) | $29.3k / 46.2% ($30.6k / 45.6%) |
| vr 1.12, c −0.25 | 89 (−25.5) | 30 (+1.2) | 1.043 / 1.069 | $77.3k, 32.0% ($72.1k, 27.6%) | $28.4k / 47.9% ($29.8k / 46.6%) |

* **The suspicion was right.** Skipping leaves the coin flat, and 23-61 new trades appear (re-entries, other cooldown /
  cascade paths).
* Every skip setting has a 2024 drop of 30.8-32.0% (v3.1 31.5%), so they all fail the literal E4.
* **VOLC is unchanged** (115 trades). None of the VOLC orders blocked in v3.1 (14 / 10 / 2 / 28 / 17 per coin) falls in
  the time a skipped trade freed.
* **HOLD_BIG** (14 untouched coins), 2024-26 net: v3.1 +5.4 units; skip 1.05 / −0.25 −4.7; most other settings are
  negative.

**The non-skip size-down** (the trade is taken at ×m, so the engine path is v3.1's exactly):

| Cap counting | Settings | E1 | E2 | E3 | PASS |
|---|---|---|---|---|---|
| Live (the bot's) | 27 | 27 | 27 | 17 | **3** |
| Base | 27 | 27 | 27 | 20 | **4** |

* **Best, live cap: ×0.25 when VolReg ≥ 0.98 and dir × Chg5 ≤ −0.25 ATR14** (`size_vr0.98_c-0.25_m0.25`):
  * x 1.054 / 1.204; capped 1.038 / 1.056; plateau 100%; nulls 98% / 99%; phase copies 100% / 92.5% / 100% / 100%.
  * From $300: 2022 $1.498M; 2024 $73.5k with drop 28.8%; Sep-Nov 26 drop 29.6%; boot $28.4k / $8.24k / 45.7%.
* **HOLD_BIG for the size-down:**

  | | 2020-23 ratio | 2024-26 net | 2024-26 drop |
  |---|---|---|---|
  | v3.1 | 2.09 | +5.4 units | 90 units |
  | Size-down ×0.25 | 2.53 | −16.7 units | 80 units |

  Partial support: better in 2020-23, a lower drop in 2024-26, but negative net there (`v32c_S1_holdbig_sizedown.csv`).

## Stage 2: smooth VolReg sizing and the 0.79 cliff

**Piecewise-linear ramp** (216 settings; w_calm 1.05-1.15 at ≤ v_lo → 1 at v_mid → w_wild 0.5-0.75 at ≥ v_hi):

| Cap | E1 | E2 | E3 | PASS |
|---|---|---|---|---|
| Live | 205 | 205 | 0 | 0 |
| Base | 150 | 129 | 0 | 0 |

* The uncapped gain is robust (phase copies 80-100%).
* The capped-account gain in 2024-26 is ×1.01-1.02 and holds on only 45-70% of phase copies. No pass.

**The 0.79 cliff is a cluster, not one trade.**
* The capped account's worst 2024-26 episode is Jun 25 - Aug 19 2026. It holds 8 losing trades with VolReg 0.754-0.770
  (BTC shorts Jul 13 / 28 / 31, ETH longs Jul 20 ×2 / Jul 27 / Aug 5, BNB long Aug 4; about −5.8R).
* At q_lo 0.79 and at 0.83 all eight are boosted ×1.15, and the drawdown is the same (205.7k).
* 0.83 "passes" only because the 0.79-0.83 band adds net, not because its drawdown is smaller. At 0.75 they are not
  boosted (194.0k).

**T1 q_lo = 0.75 sub-grid:** 540 settings, 86% E1. Within the sub-grid the plateau is 1.0 for the top rows.
* The best row (×1.25 ≤ 0.75, ×0.70 ≥ 0.90, ×0.35 ≥ 1.18): 2024 $75.3k / 24.1%, boot $28.0k / 42.7%.
* It passes E1, E3 and E4, but its full-grid plateau is 49.5%: its q_lo 0.79 neighbours fail.
* Choosing the sub-grid after seeing the result is the forking path the plateau gate exists to stop, so it is not a pass.
  0.90 is also the edge of the q_med grid.

## Stage 3: the ladder's first tier

* `portfolio.json` puts tier 0 (< $1,000) at BTC 5.7% / cap 6.27%, against tier 1's 4.75% / 5.23%.
* Every $300-start window and every bootstrap journey begins in tier 0. Inside the 2024 run, Sep-Nov 2026 is traded at
  a $53-77k balance (tier 2).
* **Sep-Nov 2026 drop inside the 2024 run: 13.6-16.8% for every candidate**, against 29-35% when the window starts at
  $300.

**Full table** (`v32c_S3_ladder_comparison.csv`), from $300, k = v3.0 ladder × k (portfolio.json = 0.95);
"tier0=tier1" = the < $1,000 row at the $1,000-10,000 risks:

| Candidate | Ladder | k | 2022 run | 2024 run | Sep-Nov 26 from $300 / in the 2024 run | Oct-Nov 26 from $300 | P(≥ $10k in 2 y) | Boot median / p10 / dd90 |
|---|---|---|---|---|---|---|---|---|
| v3.1 (deployed) | portfolio | 0.95 | $1.215M, 23.4% | $70.8k, 31.5% | 34.4% / 16.0% | 29.1% | 83.4% | $26.4k / $6.63k / 49.5% |
| v3.1 | tier0=tier1 | 0.95 | $1.199M, 23.4% | $57.4k, 27.4% | 29.6% / 16.0% | 24.8% | 80.4% | $23.9k / $5.43k / 46.4% |
| v3.1 | tier0=tier1 | 1.00 | $1.695M, 24.5% | $70.8k, 28.6% | 30.9% / 16.8% | 25.9% | 82.6% | $26.6k / $6.07k / 48.2% |
| **v3.1 + size-down (live cap)** | portfolio | 0.95 | $1.498M, 23.4% | $73.5k, 28.8% | 29.6% / 13.6% | 27.7% | 87.7% | $28.4k / $8.24k / 45.7% |
| **v3.1 + size-down (live cap)** | portfolio | 1.00 | $1.982M, 24.5% | $84.1k, 30.1% | 31.0% / 14.2% | 29.0% | 89.7% | $32.5k / $9.69k / 47.2% |
| **v3.1 + size-down (live cap)** | tier0=tier1 | 0.95 | $1.425M, 23.4% | $72.3k, 25.0% | 25.4% / 13.6% | 23.5% | 83.9% | $26.2k / $6.66k / 42.8% |
| **v3.1 + size-down (live cap)** | tier0=tier1 | 1.00 | $2.031M, 24.5% | $74.3k, 26.2% | 26.6% / 14.2% | 24.6% | 87.1% | $28.8k / $7.67k / 44.4% |
| v3.1 + size-down 1.05 (base cap) | portfolio | 0.95 | $1.573M, 23.4% | $71.6k, 28.1% | 33.3% / 15.4% | 28.0% | 88.5% | $29.7k / $8.64k / 46.3% |
| v3.1 + engine skip 1.05 (no PASS) | portfolio | 0.95 | $1.525M, 23.4% | $67.3k, 32.0% | 33.2% / 15.4% | 27.6% | 88.1% | $29.3k / $8.29k / 46.2% |

* **Flattening tier 0** costs the bootstrap median about 10% and P(≥ $10k) about 3 points at the same k. It cuts
  every $300-start drop by about 4-5 points and dd90 by about 3. The 2022 drop is unchanged: that run's worst drop
  comes later, at a high balance.
* **tier0=tier1 at k 1.00** = BTC 5.0% below $10,000 (instead of 5.7% / 4.75%). For v3.1 it keeps the median ($26.6k vs
  $26.4k) and lowers every drop, at a lower p10 ($6.07k vs $6.63k).

## Recommendation

**Candidate v3.2c = v3.1 + the size-down, under the live cap counting (no change to the bot's cap).**
* The rule: TBO risk × 0.25 when the coin's VolReg ≥ 0.98 and dir × Chg5 ≤ −0.25 ATR14 at the order's arming close.
* The trade is still taken, so cooldowns, the cascade and VOLC are exactly v3.1's.
* It passes all gates on the bot's own cap rule. HOLD_BIG gives partial support.

**Ladder: two good choices** (instead of portfolio × 0.95):

| Ladder | Bootstrap vs v3.1 | Drops |
|---|---|---|
| (a) tier0=tier1 at k 1.00 (BTC 5.0% / 5.0% / 2.5%) | more money: median $28.8k, p10 $7.67k, P(≥ $10k) 87.1% | $300 Sep-Nov 26.6%, 2024 run 26.2%, dd90 44.4% |
| (b) tier0=tier1 at k 0.95 | same median and p10 as v3.1 | the lowest: 25.0% / 25.4% / dd90 42.8% |

**Not adopted:** the engine skip (fails E4 once re-entries are simulated), the smooth ramp (fails E3 on the capped
account), the 3-tier VolReg (plateau), and S5a.
