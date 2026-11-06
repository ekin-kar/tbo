# Context for review

I run a small automated crypto futures bot on Binance (USDT-M perpetuals, started with $300). I ran a research campaign to
test upgrades to it, and the full results are below. Please act as a skeptical senior quant reviewer.

## The system being tested

**TBO v2.8 (main strategy), on BTC, ETH, BNB, SOL, ADA**
- **Entry:** 4h channel breakout. A long is a stop order at the 20-bar high, a short at the 20-bar low. Fills are simulated on 1-minute data.
- **Stop:** 1 ATR(4h) from entry. It moves to breakeven at +1.5R, and is locked to +1.5R once price reaches +5R.
- **Time exit:** 120h.
- **Shorts:** half size (×0.5).
- **Filters:**
  - only trade when open interest fell ≥ 3% over the last 72h;
  - no order while OI sits in the lowest 20% of its 90-day range (the "OI-low" filter, new in v2.8).
- **Risk per trade (% of equity):**

  | equity | BTC | ETH | others |
  |---|---|---|---|
  | < $1k | 6% | 4% | 0.83% |
  | $1k–10k | 5% | 3.3% | 0.83% |
  | > $10k | 2.5% | 1.7% | 0.42% |

- **Total open-risk cap:** 1.1× the BTC risk. BTC itself is exempt from the cap but still counted in it.
- **Costs modelled:** 0.05% taker fee, slippage, and funding.

**Panic Sleeve v2.7 (second strategy), same 5 coins**
- **Trigger:** buys capitulation when, within 4 hours, three things happen together:
  - return z-score ≤ −1.5;
  - open interest drops ≥ 12%;
  - premium-index z-score ≤ −1.
- **Exits:** take profit at 3 ATR, stop at 4 ATR (max −20%), breakeven at +2 ATR, time exit at 12h.
- **Size:** 3 risk units per event, split across the coins that trigger.

## How I validated every idea (gates fixed BEFORE running)
- **Periods:** 2020-23 and 2022-23 are development; 2024-26 is out-of-sample.
- **G1 dev / G2 out-of-sample:** risk-adjusted return (net / max drawdown, fixed-unit R) must beat the base in both.
- **G3 plateau:** at least 60% of neighbouring parameter settings must also beat the base.
- **G4 luck:**
  - the improvement must hold on at least 70% of 40 time-shifted copies of the 4h candles;
  - sizing ideas must also beat 200 random shuffles at the 95th percentile.
- **G5 untouched coins:** must also work on coins never used in development (14 large plus 25 small alts).
- **G6 money:**
  - a compounding simulation from $300 must end higher with drawdown no more than 1 percentage point worse;
  - a 1,000-path block-bootstrapped 2-year simulation must also end higher with no worse tail drawdown.

## What I want from you
1. Look for methodological flaws: look-ahead bias, overfitting, gate design, multiple-testing problems, anything that makes
   the conclusions unreliable. Be specific.
2. Do you agree with each verdict? In particular, say whether rejecting these was right or too strict:
   - U4 (panic on 12 coins: more money, but a weaker 2022-23 and it fails on the untouched coins);
   - U1 (bigger BTC/ETH shorts: more money, but a worse tail drawdown).
3. Was the S3 rejection right? It was profitable, but random entries after the same BTC trigger did as well.
4. What would you test next, ranked by expected value and how cheap it is to test?
5. Anything in the live audit (Part 1) that worries you?

Note: "R" = profit in multiples of the initial risk. "x" = risk-adjusted ratio relative to the base (1.0 = equal, > 1 = better).

---

# v2.9 research campaign — final report (2026-11-06)

Scope: TBO v2.8 + Panic Sleeve v2.7. Data extended to 2026-11-06. Part 1 audits the live account, Part 2 tests the
four upgrades (U1–U4), Part 3 tests four new sleeves (S1–S4). Every test uses the same 6 gates, fixed in advance in the script docstrings.

**Bottom line: nothing passes all 6 gates. Keep v2.8 + v2.7 unchanged.** Three ideas made more money but failed the
robustness gates; they are listed at the end as a watch-list. No live bot file was touched.

---

## 0. Data

| item | status |
|---|---|
| Binance 1m, DEV12 (12 coins) | extended 2026-10-01 → 2026-11-06 (`data/<SYM>_1m_2020_2026_part3.parquet`) |
| OI/metrics, funding, premium 1h, perp 4h, spot 4h | extended for DEV12 (data/extra) and HOLD39 (data/extra2) |
| 1m for the 14 HOLD_BIG coins | `cache/<SYM>_m1.npz`, holes repaired since 2020 |
| Holes | The Oct 2026 monthly archive is missing **Oct 28 entirely** (the daily file also 404s); filled from the REST API. |
| Real gaps | ICP: a 26-day gap in 2022-09. EOS: delisted, ends 2025-05-21. |
| Trade lists | `portfolio_trades_v28nov.pkl` has 1403 trades; it is identical to v28 before Oct 1. v26nov has 1593. |
| Engine parity | The new xengine29 / v29lib reproduces v28 exactly: same trades on all 5 coins, same BE times, money equal to the cent. |

Base v2.8 money from $300 (bot only): 2020→ $5.86M (dd 35.5%), 2022→ $384k (dd 39.4%), 2024→ $34.6k (dd 40.5%).
With panic v2.7: 2022→ $689k (dd 26.3%), 2024→ $50.3k (dd 36.1%).

---

## 1. Live audit (17 closed positions, Oct 12 → Nov 4 2026)

Files: `live_audit_nov.csv`, `live_audit_nov_counterfactual.csv`.

**The engine reproduces 16/17 live positions to the minute.** R is measured against the engine's stop distance.

| # | coin | side | opened (UTC) | exit | ver. live | slip in (bps) | live R gross | fee R | live R net | engine R |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ETH | L | 10-12 02:17 | stop | v2.6 | +0.0 | −0.977 | 0.108 | −1.086 | −1.151 |
| 2 | SOL | L | 10-12 04:43 | stop | v2.6 | +0.9 | −1.007 | 0.069 | −1.076 | −1.128 |
| 3 | BTC | L | 10-12 05:04 | stop | v2.6 | 0.0 | −1.031 | **0.143** | −1.174 | −1.197 |
| 4 | ETH | S | 10-14 20:45 | BE | v2.6 | +8.3 | −0.025 | 0.049 | −0.074 | −0.078 |
| 5 | BTC | L | 10-19 07:32 | stop | v2.6 | +2.8 | −1.004 | 0.103 | −1.107 | −1.127 |
| 6 | BTC | L | 10-20 14:12 | stop | v2.6 | +3.0 | −1.003 | 0.115 | −1.118 | −1.139 |
| 7 | BTC | L | 10-21 08:49 | BE | v2.6 | +1.8 | −0.007 | 0.107 | −0.114 | −0.152 |
| 8 | ETH | S | 10-22 16:47 | stop | v2.8 | +1.0 | −1.003 | 0.066 | −1.069 | −1.086 |
| 9 | ETH | S | 10-23 22:53 | BE | v2.8 | +4.2 | −0.030 | 0.074 | −0.105 | −0.112 |
| 10 | BNB | L | 10-27 15:21 | stop (diverged) | v2.8 | **+17.1** | −1.002 | 0.092 | −1.095 | −0.184 (BE) |
| 11 | BNB | L | 10-28 09:49 | BE | — (no engine trade) | | | | −$1.83 | — |
| 12 | SOL | S | 10-29 20:04 | 120h time | v2.8 | +1.0 | +2.855 | 0.047 | **+2.808** | +2.716 |
| 13 | ETH | S | 10-29 20:34 | BE | v2.8 | +0.9 | −0.013 | 0.057 | −0.070 | −0.068 |
| 14 | BTC | S | 11-03 06:07 | stop | v2.8 | 0.0 | −1.000 | 0.107* | −1.108 | −1.135 |
| 15 | BTC | S | 11-04 02:59 | stop | v2.8 | +0.2 | −1.003 | 0.108* | −1.110 | −1.131 |
| 16 | SOL | S | 11-04 02:59 | stop | v2.8 | +1.1 | −1.004 | 0.065* | −1.070 | −1.106 |
| 17 | ETH | S | 11-04 03:01 | stop | v2.8 | +0.1 | −1.002 | 0.082* | −1.085 | −1.100 |

\* The trade-history export ends 2026-10-30 00:18 (UTC+3), so these 5 positions use an estimated 0.05% USDT taker fee.

| metric | live | engine | comment |
|---|---|---|---|
| stop-loss R, n = 10 | **−1.100** (gross −1.004, fee 0.097) | −1.130 | Expected −1.07R. Live is better than the engine because the engine books a pessimistic stop fill. |
| breakeven exit R | −0.091 | −0.103 | A BE exit costs about 0.1R, almost all of it fees. |
| entry slippage | mean +2.6 bps (+0.023R), median +1.0 bps | — | The BNB Oct 27 fill (17 bps) is the outlier. |
| exit slippage | −0.6 bps | — | |
| fee drag | BNB-paid: 0.095R (9.3 bps round trip, 7 pos.) · USDT-paid: 0.087R (9.9 bps, 14 pos.) | | |
| BNB balance | ran out first at the ETH close, 10-12 12:35 UTC; mostly USDT fees from 10-19 on | | Top up BNB to get the 10% discount. |
| tight-stop fee | BTC 10-12: stop 0.628% → fee 0.143R | | This was the U3 premise; U3 failed (see below). |

**The one divergence (BNB, Oct 27–28).** The live long filled 17 bps worse than the engine (+0.167R), so the live stop
sat 1.28 higher. Price hit it at 742.71, while the engine trade survived and later went to BE (−0.18R). Live then
re-entered on Oct 28 at 09:49 (a position the engine never had) and closed it at BE. The two live BNB positions cost −$3.67 together.

**Versions.** Positions 1–7 opened before v2.8 went live (2026-10-21 17:00 UTC, commit 2d08a33). All 7 are identical under v2.8; the OI-low filter would not have removed any of them.

**Balance and counterfactual from $300 on Oct 12.**

| | final | max drop |
|---|---|---|
| live (realized, excl. funding) | **$200.87** (gross −87.02, fees 12.11, net −99.13) | |
| engine, pure v2.8 + v2.7 panic | $199.79 | 33.6% |
| engine, v2.6 | $196.05 | 34.9% |

- The engine figure includes the open SOL short (mark-to-market) and a BNB short on Nov 3 06:13 (−1.15R) that live never took. The cause of the missing BNB short is unknown; check the bot log for that hour.
- The v2.6 figure includes 6 ADA shorts, ≈ −4.3R, that the v2.8 OI-low filter removes.
- Panic: 0 triggers in the window.

**Conclusion:** execution is fine. Live was $1 *better* than the engine. The −33% is the strategy's own losing streak
(10 stops, 1 winner), not a bot bug.

Premise checks done for Part 2:
- Short avg R by period (2020-21 / 2022-23 / 2024-26):
  - BTC 0.28 / 1.38 / 0.80
  - ETH 0.37 / 1.38 / 1.41 (your brief said 1.72; the data says 1.41)
  - SOL 0.50 / 0.24 / −0.01
  - ADA 0.10 / 0.43 / 0.07
  - BNB −0.10 / 0.66 / 0.18
- TIME exits are 15.8% of trades but 179% of net R (avg +7.6R).

---

## 2. The 6 gates (fixed before running)

x = (net / max drawdown) relative to base, in fixed-unit R (BTC 6, ETH 4, other coins 0.83, as in the bot's ladder).

| gate | test |
|---|---|
| G1 dev | x2022-23 ≥ 1.05 and x2020-23 ≥ 1, net x ≥ 0.9 |
| G2 OOS | x2024-26 > 1, net x ≥ 0.9 |
| G3 plateau | ≥ 60% of the neighbouring grid points have x > 1 in both 2022-23 and 2024-26 |
| G4 luck | x > 1 on ≥ 70% of 40 phase-shifted 4h copies in both periods; sizing ideas also need ≥ 95% vs 200 random nulls |
| G5 untouched | x > 1 on the 14 HOLD_BIG coins (U1–U3), or on 25 HOLD_SMALL (U4), or on HOLD39 (S1–S4) |
| G6 money | from $300, 2020/2022/2024 money higher with dd ≤ +1pp, and the 1,000-journey 2-year bootstrap median higher with dd90 ≤ +1pp |

---

## 3. Part 2 — upgrades U1–U4

### U1 short multipliers per tier (`v29_U1.csv`, `v29_U1_money.csv`)
Live is btc 0.5 / eth 0.5 / alt 0.5. Grid: btc {0.5, 0.75, 1} × eth {0.5, 0.75, 1} × alt {0, 0.25, 0.5}.

| config | x2020 | x2022 | x2024 | plateau | phase win 22/24 | null | G1–G5 | $300→ 2022 | 2024 | boot med | boot dd90 | G6 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **base** 0.5/0.5/0.5 | 1 | 1 | 1 | | | | | $384k | $34.6k | $14.3k | 67.6% | |
| btc1 eth0.5 alt0.5 | 0.947 | 1.027 | 1.071 | 43% | 63% / 98% | 0.80 | G2 only | $771k | $44.9k | $18.7k | 71.0% | ✗ |
| btc1 eth0.75 alt0.5 | 0.913 | 1.019 | 1.104 | 36% | 65% / 98% | 0.54 | G2 only | $820k | $53.9k | $20.1k | 71.8% | ✗ |
| btc1 eth1 alt0.5 | 0.884 | 1.012 | 1.136 | 29% | 65% / 100% | 0.54 | G2 only | $1.08M | $64.3k | $21.1k | 72.6% | ✗ |
| btc0.75 eth0.5 alt0.5 | 0.972 | 1.014 | 1.049 | 27% | 65% / 100% | 0.76 | G2 only | $602k | $40.9k | $16.8k | 69.5% | ✗ |
| alt 0 (any btc/eth) | 0.83–0.92 | 0.90–0.94 | 1.00–1.15 | 0% | | | G2 only | | | | | |

- **Fails.** Bigger BTC/ETH shorts help 2022–26 but hurt 2020–23 (2021-style squeezes). They fail the phase test in 2022 (63% < 70%), fail the plateau, and the null shuffle (80% < 95%).
- The large money gain is mostly more leverage: the bootstrap dd90 rises by 3–5pp, which fails G6.
- Removing alt shorts (alt 0) hurts everywhere, so alt shorts do earn their keep.
- **Directional open-risk cap on shorts: no effect** at btc1 (identical numbers); slightly worse elsewhere.
- **ETH exempt from the cap on shorts:** mixed results; it never improves both money and drawdown.
- Note: G5 shows True for the alt 0.5 rows only because HOLD_BIG has no BTC/ETH, so nothing changes there. It is not real evidence.

### U2 asymmetric hold / locks / runner / stale decay (`v29_U2_U3floor.csv`)

| family | best variant | x2020 | x2022 | x2024 | plateau | phase 22/24 | HOLD_BIG x22/x24 | gates passed | money vs base |
|---|---|---|---|---|---|---|---|---|---|
| longer holds (15 combos L120–192 / S60–120) | L168 S120 | 0.82 | 0.78 | 0.98 | 0% | 35% / 55% | 1.31 / −16 | none | worse |
| 2nd lock +8R→+3.5R | lock2 (8,3.5) | 1.094 | **1.151** | 1.006 | 25% | 90% / 58% | 0.52 / −0.75 | G1 G2 | 2020 $4.36M (−26%) · 2022 $442k (+15%) · 2024 $35.1k (+1%) → ✗ |
| 2nd + 3rd lock | (8,3.5)+(12,7) | 0.92 | 1.05 | 1.00 | 14% | | | G2 | |
| runner past 120h (chandelier k2/k3, EMA10) | run_R6_k2 | 0.98 | 0.98 | 0.98 | 0% | 20% / 75% | | none | 2022 $337k, 2024 $37.2k → ✗ |
| stale-trade decay | stale 60h → 0 | 1.012 | 1.020 | 1.053 | **100%** | **100%** / 58% | 1.12 / 9.5 | G2 G3 G5 | 2020 +1% · 2022 −1.3% · 2024 −1.7% → ✗ |
| | stale 48h → 0 | 0.997 | 1.018 | 1.074 | 100% | 85% / 78% | 0.85 / −0.4 | G2 G3 G4 | |
| | stale 36h → −0.5R | 1.004 | 1.006 | 1.039 | 100% | 83% / 95% | 0.93 / 3.0 | G2 G3 G4 | |

- **Fails.**
- Longer holds and runners hurt. The 120h time exit is already where the money is: TIME exits carry 179% of net R, and runners give back the open profit.
- The 2nd lock helps 2022-23 but isolated (25% plateau). It also hurts HOLD_BIG and 2020-21, and loses 26% of the 2020 money.
- Stale decay is the most robust idea in Part 2: 100% plateau and stable on phase copies. But the effect is only +0–7%, below G1's +5% bar for 2022, and money is flat. It is real but too small to deploy.

### U3 fee-aware sizing and min stop floor (`v29_U3fee.csv`, `v29_U2_U3floor.csv`)

| variant | stop-loss R | x2020 | x2022 | x2024 | $300→ 2022 | 2024 | boot med | gates |
|---|---|---|---|---|---|---|---|---|
| base | −1.07 (engine) | 1 | 1 | 1 | $384k | $34.6k | $14.3k | |
| fee-aware c 0.5 | −1.047 | 0.998 | 0.988 | 0.976 | $287k | $32.4k | $13.1k | none |
| fee-aware c 1 | −1.007 | 0.998 | 0.979 | 0.955 | $251k | $29.7k | $11.6k | none |
| fee-aware c 2 | −0.938 | 1.001 | 0.967 | 0.922 | $157k | $25.1k | $9.2k | none |
| stop floor 0.6% | | 0.984 | 0.978 | 0.990 | $398k | $33.8k | $14.0k | none |
| stop floor 0.8% | | 0.998 | 0.965 | 0.954 | | | | none |
| stop floor 1.0% | | 0.887 | 0.845 | 0.880 | | | | none |

- **Fails.** Fee-aware sizing does what it promises: the stop loss improves from −1.05R to −0.94R. But it shrinks positions exactly on the tight-stop trades, which are profitable, so returns fall 5–60%.
- A stop floor widens tight stops and makes everything worse.
- The live −0.14R fee on a 0.63% stop is real, but cutting size there costs more than it saves.

### U4 panic on more coins, max_open cap, ranking, runner (`v29_U4.csv`, `v29_U4_money.csv`, `v29_U4_runner.csv`)

Parity: v2.7 on OUR5 here gives 86 trades vs `panic_sleeve.events` 86, same (hour, coin), avg 3.51%. This is the base (x = 1).

| universe / cap / rank / units | n 22-23 | avg 22-23 | n 24-26 | avg 24-26 | x2022 | x2024 | rank vs random | HOLD_SMALL avg 22/24 |
|---|---|---|---|---|---|---|---|---|
| **OUR5 v2.7 (live)** | 40 | 3.39% | 46 | 3.62% | 1 | 1 | | |
| DEV12 uncapped | 134 | 1.78% | 134 | 3.85% | 0.72 | **1.67** | | 0.67% / 4.15% |
| DEV12 cap 2, rank C (composite) | 83 | 1.81% | 63 | 2.95% | 0.84 | 1.41 | **99.5%** | 0.10 / 0.74 |
| DEV12 cap 2, rank B (premium z) | 83 | 1.74% | 63 | 2.78% | 0.80 | 1.33 | **98.5%** | 0.06 / 0.78 |
| DEV12 cap 5, rank B | 121 | 1.91% | 98 | 3.57% | 0.73 | 0.78 | 99.5% | |
| LIQ26 (DEV12 + HOLD_BIG) uncapped | 350 | 1.35% | 332 | 3.73% | 0.26 | 0.78 | | |
| HOLD_SMALL alone uncapped | 287 | 0.67% | 356 | 4.15% | 0.10 | 0.80 | | |

Money (bot v2.8 + sleeve, from $300):

| | $300→ 2022 | dd | $300→ 2024 | dd | boot med | boot dd90 | money gate |
|---|---|---|---|---|---|---|---|
| **v2.7 OUR5 (live)** | $689k | 26.3% | $50.3k | 36.1% | $18.95k | 64.6% | |
| DEV12 uncapped, 3 units | $756k | 24.7% | $57.5k | 36.1% | $19.75k | 62.8% | ✓ |
| DEV12 cap 2 C, 4 units | $802k | 25.8% | $55.4k | 35.9% | $20.65k | 62.1% | ✓ |
| DEV12 cap 2 C, 3 units | $647k | 24.1% | $62.8k | 36.1% | $18.6k | 63.1% | ✗ |
| LIQ26 uncapped, 3 units | $805k | 40.8% | $63.0k | 35.8% | $19.9k | 63.2% | ✗ (dd) |

- **Fails, but this is the closest call of the campaign.**
- Panic on DEV12 makes more money in the bot portfolio, with similar or lower drawdown. But:
  - **G1 fails:** in 2022-23 the extra 7 coins dilute the avg trade from 3.4% to 1.8%, and the sleeve's own return/dd ratio drops to 0.72×.
  - **G5 fails:** on the 25 untouched small coins, 2022-23 is near zero (0.67%/trade, ratio 0.10×).
  - The good result rests on 2024-26 alone.
- **Ranking is a real signal:** when there are more triggers than slots, picking by premium z (B) or the composite (C) beats random picks at 98.5–99.5%. But capping still loses to uncapped on DEV12, so there is nothing to deploy yet.
- **Runner tranche** (half at TP 3 ATR, half runs to 4–6 ATR or 12–24h): worse in every one of 27 settings (x 0.60–0.99).

---

## 4. Part 3 — new sleeves S1–S4 (`v29_S_grid.csv`, `v29_S_gates.csv`, `v29_S_money.csv`)

828 settings, run on DEV12 / HOLD_BIG / HOLD_SMALL. Trades within 12h of a panic trigger on the same coin are excluded.
G3 here = ≥ 95th percentile vs 200 random-entry draws (100 for S3) and vs 40 time-shifted copies, in both periods.

**Funnel (settings):**

| family | all | G1 dev | +G2 plateau | +G3 luck | +G4 HOLD39 | median avg R 22-23 / 24-26 |
|---|---|---|---|---|---|---|
| S1 crowded-long cascade short | 432 | 0 | 0 | 0 | 0 | −0.14 / −0.11 |
| S2 trapped-short squeeze long | 216 | 11 | 8 | 0 | 0 | +0.26 / −0.02 |
| S3 BTC-ignition RS rotation | 72 | **44** | **44** | **0** | (38 pass G4 on their own) | +0.34 / +0.36 |
| S4 parabolic extension fade | 108 | 0 | 0 | 0 | 0 | −0.05 / −0.22 |

**Best settings, money stage (bot v2.8 + panic v2.7 + sleeve as a 6th "coin"):**

| id | family | params | n 22/24 | avg R 22/24 | rank vs random 22/24 | corr w/ TBO months | R in TBO losing months | boot med vs $18.95k | dd90 vs 64.6% | G6 |
|---|---|---|---|---|---|---|---|---|---|---|
| 719 | S3 | trig 1.5R, LB 72, top 2, OI conf on, H 120 | 48 / 95 | 0.79 / 0.79 | 40% / 64% | **+0.42** | **−23.9** | $20.0k | 65.4% | ✓ |
| 692 | S3 | trig 1R, LB 72, top 2, H 120 | 68 / 122 | 0.66 / 0.44 | 51% / 65% | +0.46 | −48.5 | $19.5k | 65.8% | ✗ |
| 601 | S2 | q .7, p −1.25, N 36, spot conf | **7 / 9** | 0.83 / 0.84 | 99% / 93% | −0.18 | +10.3 | $19.8k | 62.8% | ✓ |
| 794 | S4 | e 5, K 2, T 2.5, H 36 | **8 / 29** | 0.20 / 0.22 | 73% / 99% | +0.27 | +0.2 | $19.7k | 64.1% | ✓ |
| 347 | S1 | best S1 | 45 / 129 | −0.00 / −0.02 | | −0.09 | −2.3 | $19.0k | 64.7% | ✗ |

**No new sleeve passes.**
- **S3 is the trap:** it is profitable and stable across the grid and on HOLD39. But random alt longs taken after the same
  BTC-breakout triggers do as well (40–65th percentile, not 95th). The edge is "long alts when BTC breaks out", which TBO
  already holds. It is +0.42 correlated with TBO, and it loses 24–49R in exactly the months TBO loses, so it adds to TBO's risk instead of diversifying it.
- **S2 #601 and S4 #794 pass the money gate on 7–29 trades.** They fail G1 (n < 30) and the plateau (S4 16%). That is noise.

**Portfolio improvement from Part 3: none.**

---

## 5. Verdict

| idea | all 6 gates | closest result | action |
|---|---|---|---|
| U1 short tiers / cap / ETH-exempt | ✗ | btc1: +100% 2022 money, but dd90 +3.4pp, fails 2020-21 and the luck test | keep 0.5 / 0.5 / 0.5 |
| U2 hold / locks / runner / stale | ✗ | stale decay: robust but ~+2% | keep 120h + BE + lock 5→1.5 |
| U3 fee-aware / stop floor | ✗ | none | keep; top up BNB instead |
| U4 panic universe / ranking / runner | ✗ | DEV12 panic: money ✓, dev period and HOLD_SMALL ✗ | keep OUR5 v2.7; **watch-list** |
| S1–S4 new sleeves | ✗ | S3 = TBO beta | reject |

**Watch-list (re-test once 2026-27 data accumulates, do not deploy):**
1. Panic v2.7 on DEV12 with B/C ranking. Money-positive, and the ranking signal is significant, but it rests on 2024-26 alone.
2. BTC short ×1.0. Strong 2022-26, but it hurts 2020-21 and worsens the bootstrap tail.
3. Stale-trade exit at 48–60h. Robust, but the effect is negligible.

**Practical items from the audit:**
- **BNB balance:** keep BNB topped up. USDT fees ran from Oct 19 on.
- **Missing BNB short (Nov 3 06:13):** the engine took it, live didn't. Check the bot log for that hour.
- **Diverged stop:** a 17 bps worse fill moves the stop with it. This is a one-off, not systematic (median slippage is 1 bp).

---

## 6. Housekeeping
- **CSV exclusion:** `.git/info/exclude` now has `Binance-Futures-*.csv`, which keeps the Position History CSV untracked.
  The **Trade History CSV was already committed by you in 14f8f74 ("added trades")**, and an exclude rule cannot untrack a committed file.
  To untrack it you'd run `git rm --cached "Binance-Futures-Trade-History-202611061046(UTC+3)-part1-of1.csv"` and commit.
  Not done; that's your call. It also stays in git history.
- **Line endings:** all the " M" files in `git status` are CRLF line-ending noise (`git diff --ignore-cr-at-eol` is empty).
- **Research code changed (not committed):**
  - `core/build_trades.py`: `TBO_END` env var, `low = tag.startswith("v28")`.
  - `core/grid_v25.py`: falls back to data/extra2 for HOLD-coin OI.
- **Research code new:**
  - `core/fetch_extend.py`, `core/xengine29.py`, `core/v29lib.py`, `core/hourly51.py`
  - `studies/live_audit_nov.py`, `studies/quant_upgrades_v29.py`, `studies/panic_rank_v29.py`, `studies/new_sleeves_v29.py`
- **Live bot:** `cryptobot/*.py` and `portfolio.json` untouched.
