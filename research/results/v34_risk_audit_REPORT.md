# v3.4 joint risk-grid and plateau audit of the complete v3.2.1 system (Nov 2026, data to 2026-11-06)

**System:** TBO v3.2.1 (the v3.1 trade list × the wild-pullback size) + panic v3.0 + 4h VOLC, on one account.

**Code:** `research/crypto/studies/v34_risk_plateau_audit.py` (stages `check stage1 stage2 stage3 stage4b`).

**Read-only on `cryptobot/`:** `portfolio.json`, the configs, `panic.json` and `volc.json` were read, never written. No
page was rebuilt. Branch `v34-research`.

**Files:**

| File | What it holds |
|---|---|
| `v34_stage1_marginal.csv` | 74 one-at-a-time settings |
| `v34_stage1_cap_counts.csv` | Per-coin full / shrunk / skipped counts |
| `v34_stage2_grid.csv.gz` | 54,000 joint settings |
| `v34_stage3_dial.csv` | 806 risk-dial × ladder × cap_min_fraction settings |
| `v34_stage3_baseline_neighbours.csv` | The baseline's 16 one-step neighbours |
| `v34_stage4_options.csv` | The five options |
| `v34_stage_output.txt` | Every printed table |
| `v34_terminal_log.md` | The session transcript with commentary |

## 0. Method: every setting judged jointly, in the exact capped simulator

* **Exact simulator.** Every setting runs through `v31lib._money31`, the function behind every money figure since v3.1.
  * The five coins share the open-risk cap in fill order. BTC is exempt but counted. The cap counts the actual (scaled)
    risk. Panic and VOLC are outside the cap.
  * Each run's events are sorted once, and a parallel numba kernel runs every policy through `_money31`. That makes it
    possible to give every one of 54,000+ settings the full evaluation.
* **Per setting (1,087 runs):**
  * Five windows from $300 (2020, 2022, 2024, Sep 15 2026, Oct 1 2026).
  * 1,000 two-year bootstrap journeys (4-week blocks, the same journeys for every setting).
  * The fixed-size capped account (ret / max DD at the $1,000-10,000 row) in 2020-23 and 2024-26, on the trade list and
    its 40 phase-shifted copies (82 runs).
* **Parity:** the live `portfolio.json` and the grid's base point both reproduce the v3.2.1 reference exactly: 2022
  $2,030,648 / 24.51%, 2024 $74,343 / 26.20%, bootstrap $28,770 / $7,672 / 44.43%.
* **Era-consistency gate** (fixed before the runs, from the brief):
  * A change of the risk STRUCTURE (ETH / BTC, alt / BTC, alt weights, short multiplier, cap / BTC, VOLC share, panic
    units, cap_min_fraction) must raise ret / max DD in 2020-23 AND 2024-26, and do so on ≥ 80% of the 41 trade lists.
  * A pure scale (BTC level with the ratios fixed) or a ladder change leaves that ratio unchanged and is exempt.
* **1-step plateau** (fixed before the option search):
  * The setting's neighbours are ±1 grid step on each of the 8 axes (BTC ± 0.5 points), up to 16 neighbours.
  * A neighbour counts if its 2024 drop and bootstrap dd90 are within the option's limits + 1 point, and its 2024 money
    and bootstrap median are ≥ 90% of the setting's.

## 1. Stage 1: coupled marginal sweeps (each change alone, inside the full portfolio)

`v34_stage1_marginal.csv`; era x = fixed capped account ret / max DD vs v3.2.1 (2020-23 / 2024-26); phase = share of the 41
trade lists with x > 1 in both.

| Setting | 2024 run $ / drop | Boot median / p10 / dd90 | P(≥ $10k) | era x dev / oos (phase) |
|---|---|---|---|---|
| **v3.2.1 baseline** | **$74.3k / 26.20%** | **$28.8k / $7.67k / 44.43%** | **0.871** | 1.00 / 1.00 |
| BTC ×0.75 / ×1.25 | $48.5k / 23.6% · $123.7k / 30.8% | $19.0k / $4.82k / 41.0% · $42.9k / $11.1k / 49.5% | .761 / .919 | 0.87 / 0.95 · 1.00 / 1.01 |
| ETH ×0 / ×0.75 / ×1.25 | $24.6k / 32.5% · $65.6k / 26.2% · $97.0k / 26.5% | $15.4k / 41.3% · $25.5k / 42.5% · $34.3k / 46.5% | .683 / .834 / .888 | 0.68 / 0.72 · 0.96 / 1.02 · 0.95 / 0.98 |
| BNB ×0 / ×1.5 | $69.4k / 25.4% · $82.6k / 26.9% | $27.1k / 44.0% · $29.8k / 45.0% | .849 / .871 | 1.04 / 0.98 · 0.97 / 1.01 |
| SOL ×0 / ×1.25 | $71.8k / 25.5% · $93.8k / 26.8% | $26.8k / 44.8% · $29.6k / 44.6% | .853 / .874 | 1.00 / 0.99 · 0.97 / 1.00 |
| ADA ×0 / ×1.5 | $81.6k / 25.3% · $76.6k / 26.9% | $28.0k / 43.9% · $29.2k / 45.2% | .847 / .874 | 0.96 / 1.04 · 1.01 / 0.98 |
| short ×0.35 / 0.65 / 1.0 (all) | $71.0k / 26.1% · $93.2k / 26.9% · $112.9k / 30.3% | $23.7k / 42.3% · $34.9k / 47.1% · $45.4k / 52.1% | .822 / .891 / .915 | 0.95 / 1.02 · 0.99 / 0.91 · 0.88 / 0.76 |
| cap 1.00 / 1.20 / 1.35 / 1.50 × BTC | $86.8k / 26.2% · $74.5k / 27.0% · $90.5k / 28.3% · $88.5k / 28.9% | $28.9k / 44.5% · $28.8k / 44.9% · $28.7k / 45.9% · $28.0k / 46.8% | .870 / .862 / .861 / .855 | 0.99 / 0.99 · 0.98 / 0.98 · 0.95 / 0.94 · 0.90 / 0.89 |
| VOLC 0 / 0.30 / 0.40 | $70.5k / 26.4% · $75.0k / 26.2% · $76.4k / 26.2% | $26.9k / 45.3% · $29.8k / 44.4% · $31.3k / 44.1% | .834 / .874 / .883 | 0.98 / 0.95 · 1.00 / 1.01 (59%) · 1.01 / 1.03 (59%) |
| VOLC coin-weighted (TBO ratios / same total) | $71.4k / 26.2% · $72.3k / 26.2% | $27.2k / 44.8% · $28.2k / 44.6% | .841 / .852 | 0.99 / 0.96 · 0.99 / 0.97 |
| panic units 0 / 2.5 / 3.5 / 4.0 | $44.9k / 28.4% · $79.5k / 26.3% · $84.3k / 27.8% · $87.4k / 29.5% | $20.1k / 48.3% · $27.3k / 44.7% · $31.2k / 44.2% · $33.2k / 43.9% | .728 / .848 / .888 / .896 | 0.82 / 0.90 · 0.99 / 0.98 · 1.01 / 1.02 (61%) · 1.02 / 1.03 (51%) |
| panic extra_share 0 / 0.5 / 1.0 | $67.5k · $82.1k · $81.7k | $26.0k / 45.9% · $28.3k / 44.8% · $30.3k / 44.1% | .818 / .856 / .883 | 0.98 / 0.96 · 0.99 / 0.99 · 1.01 / 1.01 (76%) |
| panic max_extra_open 1 / 3 | $77.4k / 26.2% · $85.9k / 30.4% | $29.2k / 44.7% · $28.5k / 44.8% | .865 / .863 | 0.99 / 1.00 · 1.00 / 0.99 |

**Cap interaction** (`v34_stage1_cap_counts.csv`; TBO entries of one $300 account from Jan 2024; full / shrunk / skipped):

| Cap / BTC | BTC | ETH | BNB | SOL | ADA |
|---|---|---|---|---|---|
| 1.10 (live) | 121 / 0 / 0 | 89 / 1 / **15** | 94 / 8 / 7 | 89 / 5 / 5 | 86 / 2 / 4 |
| 1.00 | 121 / 0 / 0 | 87 / 2 / 16 | 94 / 0 / 15 | 89 / 0 / 10 | 86 / 0 / 6 |
| 1.20 | 121 / 0 / 0 | 90 / 11 / 4 | 100 / 0 / 9 | 93 / 1 / 5 | 88 / 0 / 4 |
| 1.35 | 121 / 0 / 0 | 90 / 13 / 2 | 104 / 0 / 5 | 96 / 0 / 3 | 90 / 0 / 2 |
| 1.50 | 121 / 0 / 0 | 90 / 15 / 0 | 104 / 0 / 5 | 96 / 0 / 3 | 90 / 0 / 2 |

**What Stage 1 says:**
* **The cap hypothesis does not hold.** The brief's arithmetic is right: under 1.10 × BTC, ETH is skipped while a BTC trade
  is open and not yet at breakeven (15 of 105 ETH entries in the 2024 run). Raising the cap lets those trades in (1.20:
  4 skipped, 11 shrunk). But ret / max DD falls in BOTH eras (1.20: ×0.98 / ×0.98; 1.50: ×0.90 / ×0.89). The cascade
  protects an ETH trade only after BTC has already stopped out; the extra ETH risk taken while BTC is open adds more
  drawdown than return.
* **ETH matters, and its current weight is near the best ratio.** Removing ETH costs 30% of the ratio. ×0.75 and ×1.25
  are both ≤ 1.02 in one era and < 1 in the other.
* **Alt differentiation is era-inconsistent; keep alts equal.**
  * BNB ×0: dev ×1.04, oos ×0.98. SOL ×1.25: ×0.97 / ×1.00. ADA ×0: ×0.96 / ×1.04.
  * Each coin "helps" in one era and hurts in the other, which is what curve-fitting to one era looks like.
* **Short multiplier:** more short size adds money and drawdown, and the 2024-26 ratio falls steeply (0.65: ×0.91;
  1.0: ×0.76). Less short size (0.35): dev ×0.95. 0.5 stays.
* **Sleeves:** VOLC share, panic units and the panic extra pool are the only levers that raise the ratio in both eras.
  But they do so on only 51-76% of the trade lists. VOLC coin-weighting is worse than uniform.

## 2. Stage 2: the joint grid (54,000 settings, 1,087 runs each, 173 s)

| Axis | Values |
|---|---|
| BTC | 4.0 / 4.5 / 5.0 / 5.5 / 6.0 |
| ETH / BTC | 0.50 / 0.60 / 0.66 / 0.75 / 0.85 |
| alt / BTC | 0.12 / 0.166 / 0.20 / 0.25 |
| alt pattern (BNB, SOL, ADA × the alt unit) | 1, 1, 1 / 1.25, 1.25, 0.75 / 1.5, 1.5, 0.5 |
| short | 0.40 / 0.50 / 0.65 |
| cap / BTC | 1.10 / 1.15 / 1.22 / 1.30 / 1.40 |
| VOLC share | 0.20 / 0.25 / 0.30 / 0.35 |
| panic units | 2.5 / 3.0 / 3.5 |

The ladder and cap_min_fraction are as live (both tested in Stage 3).

**Era gate: 0 of the 53,995 structural settings pass.**
* 629 raise ret / max DD in both eras on the unshifted trade list.
* None does so on ≥ 80% of the 41 trade lists. The most consistent is VOLC 0.30 + panic 3.5 (×1.014 / ×1.027, 63% of
  the lists).

**One axis at a time from v3.2.1** (era x dev / oos, share of lists):

| Axis | Read |
|---|---|
| ETH / BTC | 0.50: 0.96 / 1.02 · 0.60: 1.01 / 1.01 (7%) · 0.75: 0.98 / 0.99 · 0.85: 0.95 / 0.97 |
| alt / BTC | 0.12: 1.04 / 1.00 (12%) · 0.20: 0.97 / 1.00 · 0.25: 0.93 / 0.99 |
| alt pattern | 1.25 / 1.25 / 0.75: 0.95 / 1.02 · 1.5 / 1.5 / 0.5: 0.91 / 1.03 (dev worse, oos better: era-inconsistent) |
| short | 0.40: 0.97 / 1.03 · 0.65: 0.99 / 0.91 |
| cap / BTC | 1.15: 1.00 / 1.00 · 1.22: 0.97 / 0.98 · 1.30: 0.96 / 0.95 · 1.40: 0.93 / 0.92 |
| VOLC | 0.30: 1.004 / 1.011 (59%) · 0.35: 1.008 / 1.022 (59%) |
| panic units | 3.5: 1.010 / 1.016 (61%) |

**Conclusion of the grid:** the v3.2.1 ratio structure is the era-robust choice.
* ETH 0.66 × BTC, equal alts at 0.166 × BTC, short 0.5, cap 1.10 × BTC, VOLC 0.25 and panic 3 units.
* Nothing in 54,000 joint settings improves both eras robustly. The sleeve increases are the only near-misses (~60%).
* What remains are risk-LEVEL choices: the BTC dial and the ladder. These trade drawdown against money; they do not
  change the edge.

## 3. Stage 3: the risk dial (BTC 3.5-6.5% by 0.1) × 13 ladders × cap_min_fraction, on the v3.2.1 structure

**Ladders at BTC 5%** (`v34_stage3_dial.csv`):

| Ladder | 2022 run | 2024 run | Boot median / p10 / dd90 | P(≥ $10k) |
|---|---|---|---|---|
| **live: $10k ×0.5** | **$2.03M / 24.5%** | **$74.3k / 26.2%** | **$28.8k / $7.67k / 44.43%** | **0.871** |
| $5k ×0.5 | $1.61M / 24.5% | $53.9k / 26.2% | $22.3k / $7.16k / 42.74% | 0.801 |
| $25k ×0.5 | $3.33M / 25.7% | $117.0k / 26.2% | $41.9k / $7.34k / 45.53% | 0.855 |
| $10k ×0.6 | $4.45M / 24.5% | $100.6k / 26.2% | $32.7k / $7.61k / 44.43% | 0.868 |
| $5k ×0.75, $25k ×0.5 | $2.41M / 24.5% | $87.8k / 26.2% | $33.6k / $7.33k / 43.25% | 0.837 |
| no step-down | $61.0M / 32.8% | $267.0k / 32.8% | $51.1k / $7.34k / 46.07% | 0.855 |

* The ladder is the largest money lever.
  * The 2024 run's worst drop happens below $10k, so it barely moves.
  * Keeping full risk longer ($25k) adds about 45% to the bootstrap median, at +1.1 points of dd90 and a 4% lower p10.
* cap_min_fraction 0.20 vs 0.25: no measurable effect (era x 1.000 / 1.000).

**The BTC dial on the live ladder:**

| BTC | 2024 run | Boot median / p10 / dd90 | P(≥ $10k) |
|---|---|---|---|
| 3.5 | $29.4k / 19.0% | $13.7k / $3.47k / 34.3% | 0.650 |
| 4.0 | $41.2k / 21.5% | $18.0k / $4.59k / 38.0% | 0.754 |
| 4.5 | $57.2k / 23.8% | $23.0k / $5.90k / 41.1% | 0.813 |
| **5.0** | **$74.3k / 26.2%** | **$28.8k / $7.67k / 44.4%** | **0.871** |
| 5.5 | $103.1k / 28.5% | $37.4k / $9.97k / 47.3% | 0.899 |
| 6.0 | $132.5k / 30.8% | $46.1k / $11.9k / 49.9% | 0.924 |

**Plateaus.**
* The 1-step rule is demanding for risk settings by construction:
  * one step down in BTC, short multiplier or panic units costs > 10% of the money (that neighbour always fails);
  * one step up breaks a drawdown ceiling when the setting sits within ~1.5 points of it.
* The reachable maximum is therefore ~87-94%.
* v3.2.1's own plateau: 64% under the "≤ current drawdown" rule (fails: BTC−, BTC+, ETH−, alt−, short−, units−), 93%
  under the high-growth rule.

## 4. The five options (`v34_stage4_options.csv`; full metrics from $300, money31)

| | O1 current v3.2.1 | O2 max profit at ≤ current drawdown | O3 balanced (band: 2024 23-24.5%, dd90 40-42%) | O4 low-drawdown shield | O5 high-growth compounder |
|---|---|---|---|---|---|
| Ladder rows: BTC / ETH / each alt / cap | < $10k: 5.0 / 3.3 / 0.83 / 5.5; ≥ $10k: 2.5 / 1.7 / 0.42 / 2.75 | < $25k: 4.3 / 2.84 / 0.71 / 4.73; ≥ $25k: 2.58 / 1.75 / 0.43 / 2.84 | < $25k: 4.4 / 2.90 / 0.73 / 4.84; ≥ $25k: 2.64 / 1.80 / 0.44 / 2.90 | < $10k: 3.8 / 2.51 / 0.63 / 4.18; ≥ $10k: 2.28 / 1.55 / 0.38 / 2.51 | < $5k: 5.5 / 3.63 / 0.91 / 6.05; $5-25k: 4.13 / 2.81 / 0.69 / 4.54; ≥ $25k: 2.75 / 1.87 / 0.46 / 3.03 |
| Short mult / VOLC / panic units (extra share, max open) | 0.5 / 0.25 / 3 (0.75, 2) | same | same | same | same |
| cap_min_fraction | 0.25 | 0.25 | 0.25 | 0.25 | 0.25 |
| **Plateau** (its own rule) | 64% (93% under O5's) | **86%** | 64% (**below 80%**: only 2 settings fall in this band) | **93%** | 79% (**just below 80%**) |
| 2022 run | $2.03M / 24.5% | $2.17M / 22.6% | $2.55M / 23.1% | $0.93M / 20.2% | $4.51M / 26.8% |
| 2024 run | $74.3k / 26.2% | $81.5k / 22.9% | $89.4k / 23.4% | $40.0k / 20.5% | $121.5k / 28.5% |
| Sep 15 - Nov 6 2026: from $300 / in the 2024 run | 26.6% / 14.2% | 23.2% / 14.6% | 23.7% / 15.0% | 20.8% / 13.0% | 28.9% / 15.6% |
| Oct 1 - Nov 6 2026 drop | 24.6% | 21.5% | 22.0% | 19.2% | 26.8% |
| Losing months (2024 run, of 35) | 11 | 11 | 10 | 11 | 11 |
| P(≥ $10k in 2 years) | 87.1% | 77.8% | 78.9% | 71.0% | 88.6% |
| Bootstrap median / p10 / dd90 | $28.8k / $7.67k / 44.4% | $30.2k / $5.35k / 40.6% | $32.3k / $5.61k / 41.3% | $17.1k / $4.12k / 36.6% | $42.5k / $8.92k / 46.3% |

**Reading the options:**
* **O2** gets more median, 2024 money and 2022 money with LESS drawdown than O1 (2024 -3.3 points, dd90 -3.9 points).
  The price is the small-account tail:
  * p10 -30% ($5.35k vs $7.67k);
  * P(≥ $10k) 77.8% vs 87.1%.
  * It takes less risk below $10k (4.3% vs 5.0%) and more between $10k and $25k (4.3% vs 2.5%).
  * Its 2024 drop (22.9%) is 0.1 point below O3's band, so it is also the best robust "balanced" setting.
* **O3** proper (the band and money floors as specified) has only 2 settings in the whole dial. Neither sits on an 80%
  plateau; shown at 64% and flagged.
* **O4** is a robust low-drawdown point (93%), but it halves the bootstrap outcomes ($17.1k / $4.12k).
* **O5** has the best money everywhere and a better tail than O1 (p10 $8.92k, P(≥ $10k) 88.6%). It costs +2.3 points of
  2024 drop and +1.9 of dd90. Plateau 79%: it fails BTC−, BTC+ and short−.

## 5. What worked and what did not

**Did not work:**
* Raising the cap so ETH can trade alongside BTC.
* Differentiated alt weights (each helps one era and hurts the other).
* A larger or smaller ETH weight or alt weight.
* More short size.
* VOLC coin-weighting.
* cap_min_fraction 0.20.

**Near-miss, not robust:**
* VOLC 0.30-0.40, panic 3.5-4 units and a full panic extra pool raise ret / max DD in both eras on the unshifted list.
* But only on 51-76% of the 41 lists (gate: 80%).

**What moves the outcome:** only the risk level (the BTC dial) and the ladder's shape. Neither changes the edge; both
trade drawdown against money, and the ladder trades small-account outcomes against large-account ones.

## 6. Recommendation (mine)

**Keep the v3.2.1 settings (O1) for the live account and the final simulation.**
* **The structure is right.** In 54,000 joint settings no change to ratios, cap, shorts or sleeves improves ret / max DD
  in both eras robustly.
* **Every option buys its gains with something else.** O2 / O3 pay with the small-account tail (p10 -27 to -30%,
  P(≥ $10k) -8 to -9 points). O4 halves the money. O5 adds drawdown.
* **O1 has the best tail-to-drawdown balance.**
  * With O1's 2024 drop, only O5 has a higher p10, and O5 has more drawdown.
  * For a $300 start, P(≥ $10k) and p10 are the numbers that matter most.

**If you want more growth and accept about 2 more points of drawdown, O5** (3 rungs: 5.5% / 4.125% from $5k / 2.75% from
$25k):
* It improves every money and tail figure.
* Its plateau (79%) misses the bar by one neighbour.

**If the account grows past $10k and you want a larger median**, consider moving the step-down to $25k at that time. That
is a large-account preference, not an edge.

**Not recommended:** O2 / O3 / O4 for a $300 account (the 2-year p10 falls to $4-5.6k).
