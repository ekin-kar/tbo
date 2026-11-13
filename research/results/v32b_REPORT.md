# v3.2b: the open-risk cap under size multipliers, and four follow-ups (Nov 2026, data to 2026-11-06)

Code: `research/crypto/studies/v32b_cap_fix_and_wild_regime.py` (stages `t1a t1 t2 t3 t4 final`).
Engine change: `core/v31lib.money31` gains two opt-in options.
* `pol["cap_basis"] = "base"`: the cap counts each trade's un-scaled risk.
* Column 10 = a per-trade risk cap for sleeves, used as a VOLC leverage cap.
* With both off the results are identical to v3.1 / v3.2 (checked: v3.1 base $1,214,774 / $70,818; v3.2 S5a $77,293 / 29.42%).

**Read-only on `cryptobot/`.**

## 1. The cap claim: confirmed mechanism, but not a v3.1 bug

**How the cap counts today.** `_money31` and the live bot count each open TBO trade in the 1.1 × BTC open-risk cap at its
actual (scaled) risk.
* A size-down (e.g. ×0.75 on a wild day) frees cap room that the next coins in a cluster fill.
* A boost on BTC (exempt from the cap) eats the alts' room.
* Under $1,000: BTC 5.7%, ETH 3.8% (not 4.75%), alts 0.79%, cap 6.27%.

**What that means:**
* **Live bot:** not affected. v3.1 has no TBO size multipliers (`bot.py` `open_risk` / `size`). It would only matter if a
  sizing rule were deployed.
* **Gates E1–E3 were not affected.** They score the uncapped fixed-unit stream, so the S3a / S4 / S5a / cluster / brake
  failures at E1 / E2 in v3.1, v3.1b and v3.2 had nothing to do with the cap. Only the money gate (E4) used the cap.
* **What changes with base-risk counting (S5a ×1.15 / ×0.75, from $300):**

  | | 2024 run | Sep-Nov 26 drop | Boot median / p10 / dd90 |
  |---|---|---|---|
  | v3.1 deployed | $70.8k, 31.5% | 34.4% | $26.4k / $6.63k / 49.5% |
  | S5a, live cap | $77.3k, 29.4% | 31.1% | $26.9k / $6.95k / 47.3% |
  | S5a, base cap | $59.8k, 27.9% | 30.1% | $27.1k / $6.99k / 46.6% |

  * Drops fall, as the claim predicted.
  * But the 2024 money falls to $59.8k: the "refill" trades the claim calls harmful made money in 2024.
  * Under base counting, S5a fails the literal E4 (2024 money ≥ base).

**The new capped E1 (capped non-compounding account) fails S5a in both cap modes** (2024-26 ×0.979 live, ×0.968 base).
* The 1.15 calm boost enlarges the worst 2024-26 episode on that account: worst-case drawdown 198k → 206k.
* The capped ratio is decided by one episode. Calm cut-off 0.79: 24% of 3-tier settings pass the capped E1; 0.75 or 0.83:
  96-98%.

T1a: all 44 S5a settings before / after in `v32b_T1a_S5a_cap_before_after.csv`. **No S5a setting passes the v3.2b gates
in either cap mode.**

## 2. Gates (fixed before the runs)

| Gate | Rule |
|---|---|
| E1 | Uncapped fixed-unit x > 1 in 2020-23 and 2024-26, net ≥ 92% of the reference, AND the capped non-compounding account (base cap, TBO only) x > 1 in both periods |
| E2 | Plateau ≥ 60% |
| E3 | ≥ 95% of 200 shuffled nulls (uncapped and capped) and ≥ 75% of 40 phase copies (uncapped and capped, each period) |
| E4 | Money from $300 with the base cap, vs the reference (v3.1 deployed, or the S5a overlay for "on top of" families) |

## 3. Results

| Test | Settings | E1 (uncapped / capped / both) | +E2 | +E3 | PASS |
|---|---|---|---|---|---|
| T1 3-tier VolReg (calm ≤ 0.75/0.79/0.83 × 1.00-1.25; ≥ 0.90/0.93/0.96 × 0.70-0.80; ≥ 1.08-1.25 × 0.35-0.55) | 1,620 | 1,400 / 1,172 / 979 | 37 | 11 | **0** |
| T2 wild VolReg × 5-day move against the trade (or overlap), on v3.1 | 84 | 69 / 40 / 40 | 33 | 22 | **6** |
| T2 the same, on top of S5a | 84 | 36 / 37 / 36 | 33 | 3 | **2** |
| T3a cluster size-down (2 stops in 6/12/24 h → ×0.4-0.65 for 12-24 h), on v3.1 / on S5a | 27 + 27 | 3 / 0 | 0 | 0 | 0 |
| T3b BTC-chop risk, on v3.1 / on S5a | 28 + 28 | 2 / 0 | 0 | 0 | 0 |
| T3c loss brake, on v3.1 / on S5a | 72 + 72 | 3 / 3 | 0 | 0 | 0 |
| T4 VolReg ≥ 1.05/1.12/1.20 lock (2.5→1, 3→1, 3→1.5, 3.5→1.5) or hold 48/72/96 h (engine) | 21 | 3 | 0 | 0 | 0 |

**T1.** The 11 E1-E3 survivors lose 2024 money ($60-66k vs $70.8k).
* The best money rows (calm ≤ 0.75 × 1.25, ≥ 0.90 × 0.70, ≥ 1.18 × 0.35) pass E4 and G6: 2024 $75.3k / 24.1%, boot
  $28.0k / $8.0k / 42.7%.
* They miss E2 at 49.5%, because their 0.79 neighbours fail the capped E1 (the knife edge above).
* q_med = 0.90 (the grid edge) dominates the top rows.

**T3 / T4.** With the cap counting corrected, the cluster size-down, the BTC-regime risk and the loss brake still fail.
They pass E1 only in islands (plateau ≤ 0.17), as before. The VolReg-conditioned lock / hold has no plateau (≤ 0.40).

**T2, the finding: skip a TBO entry when the coin's VolReg ≥ 1.05 AND the 5-day move is ≥ 0.25 ATR14 against the trade**
(`pull_vr1.05_c-0.25_m0.0`).
* For a long, the coin fell ≥ 0.25 ATR in the last 5 days; for a short, it rose. Both values are read at the last daily
  close at or before the entry.
* 6.9% of trades are skipped.
* Gates: ratio ×1.075 / ×1.110; capped ×1.064 / ×1.059; plateau 100%; nulls 98% / 98%; phase copies 100% in all four
  reads.
* A skip is size 0 or 1, so the result does not depend on how the cap counts.
* Neighbours that also pass: VolReg ≥ 0.98 / ≥ 1.12 at −0.25, and ≥ 0.98 at −0.5. Size ×0.35 / ×0.5 instead of a skip
  passes E1-E3 but not E4.

## 4. Final comparison (from $300; k = v3.0 ladder × k, deployed 0.95; Oct = Oct 1 - Nov 6 2026; losing months = 2024 run, of 35)

| | k | 2022 run | 2024 run | Sep-Nov 26 drop | Oct-Nov 26 drop | Losing months | Boot median / p10 / dd90 |
|---|---|---|---|---|---|---|---|
| v3.1 deployed | 0.95 | $1.215M, 23.4% | $70.8k, 31.5% | 34.4% | 29.1% | 11 | $26.4k / $6.63k / 49.5% |
| v3.1 | 0.90 | $1.033M, 22.2% | $56.9k, 30.1% | 32.8% | 27.8% | 11 | $23.8k / $5.89k / 47.9% |
| v3.1 | 1.00 | $1.588M, 24.5% | $72.2k, 32.9% | 35.8% | 30.4% | 11 | $29.4k / $7.49k / 51.2% |
| **A: skip rule** | 0.85 | $0.947M, 21.0% | $57.4k, 25.0% | 30.0% | 25.0% | 10 | $23.2k / $6.87k / 42.1% |
| **A: skip rule** | 0.90 | $1.381M, 22.2% | $74.4k, 26.3% | 31.5% | 26.3% | 10 | $26.8k / $7.80k / 44.0% |
| **A: skip rule** | **0.95** | **$1.651M, 23.4%** | **$76.3k, 27.6%** | **33.0%** | **27.6%** | **10** | **$30.6k / $8.95k / 45.6%** |
| **A: skip rule** | 1.00 | $2.194M, 24.5% | $87.5k, 28.9% | 34.4% | 28.9% | 10 | $34.2k / $10.19k / 47.2% |
| B: S5a + skip (≥ 1.12) | 0.95 | $1.571M, 22.0% | $69.8k, 24.9% | 30.1% | 27.1% | 11 | $29.8k / $8.47k / 44.9% |
| B: S5a + skip (≥ 1.12) | 1.00 | $2.224M, 23.1% | $78.6k, 26.1% | 31.4% | 28.4% | 11 | $33.3k / $10.07k / 46.5% |

**VOLC** (finalist A, k 0.95):

| Setting | 2024 run | Boot median / p10 / dd90 |
|---|---|---|
| 0.25 (deployed) | $76.3k, 27.6% | $30.6k / $8.95k / 45.6% |
| 0.35, no cap | $80.6k, 27.5% | $31.6k / $9.50k / 45.5% |
| 0.35, 1.5× leverage cap | $76.8k, 27.7% | $31.0k / $9.52k / 45.8% |
| 0.35, 1.8× leverage cap | $77.2k, 27.7% | $31.2k / $9.47k / 45.8% |

* The leverage cap removes most of 0.35's money gain and does not lower the drops. The 0.25 share at the live
  `max_leverage` 6 stays the simpler choice.
* Full grid: `v32b_final_comparison.csv` (46 rows).

## 5. Recommendation

* **Candidate v3.2b = v3.1 + the skip rule (A), ladder unchanged (k 0.95).**
  * It is better than v3.1 on every line of the table: money, drops, bootstrap, and losing months 10 vs 11.
  * It is a pure entry filter, so it needs no change to how the cap counts.
  * Live it needs the daily ATR14 / ATR100 and the 5-day close change from the 500 daily candles the bot already
    downloads. Check it when the 4h signal arms an order.
* **Optional: k 1.00 with the rule.** Bootstrap dd90 47.2% (still below v3.1's 49.5%), median $34.2k, p10 $10.2k; the
  2024 drop is 28.9% vs 31.5%.
* **Do not deploy the S5a sizing or base-risk cap counting.**
  * S5a fails the capped E1 in both cap modes.
  * Under base counting it gives up 2024 money.
  * B (S5a + skip) has the lowest drops but less money and depends on S5a.
* **Not adopted:** cluster size-down, BTC-regime risk, loss brake, the VolReg-conditioned lock / hold, and a larger VOLC
  with a leverage cap.
