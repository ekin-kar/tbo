# v3.5 research: more strategies and VOLC on the extra coins, scored against v3.2.1 (O1)

**Result: nothing is adopted. No candidate passes G1 + G2 + G3. `cryptobot/` is untouched and v3.2.1 stays.**

Branch `v35-research` (from `main` at 17a6ce1). Code: `research/crypto/studies/v35_new_strategies_and_volc_extra.py`
(`check t1 t2 t3 t4 t5`). Read-only on `cryptobot/`. Data to 2026-11-06. Eras: dev 2022-23, oos 2024-26 (OI archive starts Dec 2021).

## Method
* **Money.** O1 + the candidate's trades as one extra sleeve class (outside the cap; class 8 = inside the cap for T1), through
  `v31lib._money31` with the v3.4 kernel. Harness check: reproduces O1 exactly (2022 $2,030,648 / 24.51%, 2024 $74,343 /
  26.20%, bootstrap $28,770 / $7,672 / 44.43%); an empty sleeve changes nothing. Run sets as v3.4: 5 windows, 1,000 journeys, fixed
  capped account on 41 trade lists (era x = ret / max DD vs O1).
* **New strategies** run on a new 1m order simulator (stop / market entries, SL, maker TP touch of the full target and 0.01% pad,
  hold, BE, TBO block on the coin and exit on a TBO fill, panic-trade block). Costs as VOLC: taker + slippage, maker TP, funding.
* **Gates.** G1: net > 0 and PF >= 1.25 in both eras, **>= 30 trades per era** (added after a first pass flagged 1-29-trade cells
  of a ~1,000-setting grid; see the log), corr with TBO monthly R <= 0.20, >= 75% positive month-block bootstraps (both eras).
  G2: plateau >= 60% (1-step neighbours that pass G1a) + the same sign out of universe. G3: era x > 1 in both eras on >= 80% of 41
  lists + 2022 / 2024 / bootstrap median / p10 up + 2024 DD <= 26.20 + dd90 <= 44.43.
* **Caveat.** Each grid has hundreds of settings and all are scored on both eras, so a best cell is optimistic by construction;
  that is what the plateau, minimum-n and out-of-universe gates are for.

## Track 1: 4h VOLC on the 7 extra DEV12 coins (live-exact engine) - FAILS
Files: `v35_T1_per_coin_audit.csv`, `v35_T1_extra_pool_grid.csv`, `v35_T1_holdbig_*.csv`.
* **Your v3.3 figures reproduce:** EXTRA7 pooled 89 trades +34.1R dd 5.2R (dev), 95 trades +18.1R dd 6.9R (oos); PF 1.84 / 1.35.
  Core 5 pooled (live list): +21.9R / +9.8R.
* **Per coin it is not uniform.** XRP +16.6R / +8.6R is the only coin strong in both eras. DOGE +7.1 / +0.0, AVAX +9.3 / **-4.1**,
  LTC +3.5 / **-1.9**, LINK -1.5 / +5.1, DOT -0.2 / +9.5, TRX -0.7 / +0.8. Two of seven coins lose in each era.
* **Out of universe (HOLD_BIG 14, one corrupt ICP stop-distance row excluded): +66.6R PF 1.97 in 2022-23, +0.3R PF 1.00 in
  2024-26.** The 2024-26 edge on extra coins does not generalise, which is the G2 check.
* **Coupled (136 settings: share 0.35 / 0.50 / 0.75 / 1.00 x max_extra_open 1-4 x rank fill / squeeze / OI / squeeze+OI x outside /
  inside the cap):** 0 pass G3. 0 settings have era x > 1 in both eras. Best era phase share 48.8% (gate 80%). Example,
  share 0.35, 2 slots, first-fill: dev x 1.009, oos x 0.981, 2022 $1.96M (**below O1's $2.03M**, DD 25.83%), 2024 $79.6k, boot
  median $30.9k. Bigger shares buy more 2024 money and bootstrap median but raise 2022 DD and drop oos x further (share 1.0: 0.948).
  Ranking does not help (it only reorders a pool whose R is the same); inside vs outside the cap is within 1-2%.
* Read: the standalone Ret/DD of 6.56 / 2.62 is on a 7-coin, ~90-trade stream; added to the account it does not beat the account's own
  ret / DD in 2024-26, and it is not robust outside the 7 coins.

## Track 2: trend-pullback resumption - FAILS (no edge)
432 settings x 12 coins. Median setting: net -23.5R dev / -42.7R oos, PF 0.86 / 0.83. 4 settings are positive in both eras; 0 pass G1a.
Coupled runs of the 3 closest: era x dev 0.73-0.91 (worse than O1). Buying a pullback's resumption high inside the channel loses to costs.

## Track 3: squeeze exhaustion - FAILS (no signal, too few events)
* **3a (short after a spike with falling OI):** 648 settings, median 13 dev / 3 oos trades; the signal almost never fires (oi drops while
  price spikes up are rare), median PF 1.01 / 0.19.
* **3b (euphoria blow-off):** 972 settings, median 10 / 16 trades, PF 0.89 / 0.68.
* A first pass without a minimum trade count reported "12 of 18 G3 passes" for 3b. Those were 1-2-trade cells moving money by ~$10
  (G1 false, plateau 0.13). With >= 30 trades per era there are no candidates; reported, then removed from the gate.

## Track 4: weekend alpha - FAILS
* **4a Monday box:** 972 settings, median PF 1.01 / 0.98. 17 settings pass G1a (all `comp 0.6`, valid 8 h), plateau <= 0.12, bootstrap
  positive 16-28% (gate 75%). Best ("both", ATR stop, 2.5R, 12 h): 223 / 337 trades, +40.5R / +48.2R, PF 1.44 / 1.29, but by year
  2022 +40.9R, 2023 -0.4R, 2024 +17.3R, 2025 +66.0R, 2026 **-35.2R**: lumpy and unstable. Coupled: era x oos 0.82-0.92.
* **4b CME fade:** 54 settings, median PF 1.31 dev, **0.92 oos**; 0 pass G1a (CME-gap fade was already rejected in v2.x).

## Track 5: own hypotheses
* **5a BTC-confirmed laggard catch-up:** 96 settings, median 5.5 / 11 trades (too selective), PF 1.55 / 0.83; 0 pass.
* **5b post-panic secondary continuation (long 12 h after a panic entry if the coin is >= 0.5-1 ATR above the panic entry):**
  the only lead. 10 settings pass G1a; best have 39-58 trades per era, PF 1.3-2.9, corr with TBO -0.12..0.08. Coupled at share 0.40: era x
  1.01 / 1.02, phase 95-100%, 2022 / 2024 / bootstrap up, DD within limits: **it passes G3 on the 4 best settings** (e.g. `pp_dh12_b1.0_
  cont_long_h36_sl2.0_tp2.0`: 2022 $2.18M, 2024 $84.8k, boot median $32.5k). But it **fails G1** (bootstrap positive only 26-31%) and **G2**
  (plateau 0.12-0.28), the sample is ~45 trades per era out of 324 settings, and the gain is +1-2% of the ratio. **Not adoptable;
  watch item only**: re-test on live data after 6-12 months with the setting fixed now.

## Summary
| Candidate | G1 | G2 | G3 |
|---|---|---|---|
| T1 VOLC on EXTRA7 (any pool setting) | passes standalone in both eras | fails out of universe (HOLD_BIG oos +0.3R) | fails (0 of 136; best phase 49%) |
| T2 trend pullback | fails (PF 0.83-0.86) | - | worse than O1 |
| T3a / T3b squeeze exhaustion, euphoria | no signal (n < 30) | - | - |
| T4a Monday box | marginal, unstable by year | plateau <= 0.12 | era x oos < 1 |
| T4b CME fade | fails oos | - | - |
| T5a laggard | n too small | - | - |
| T5b post-panic continuation | bootstrap 26-31% | plateau 0.12-0.28 | passes (era 1.01 / 1.02) |

**Recommendation:** keep v3.2.1 as is. The idle-capital observation is true but the unused hours do not hold a tested edge at these
risk levels: every orthogonal hypothesis tried either has no signal or has an era-unstable one. The two leads (XRP-only VOLC strength;
post-panic continuation) are single-digit-percent effects on small samples.
