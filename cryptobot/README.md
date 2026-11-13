# TBO v3.2: trend-breakout bot (BTC, ETH, BNB, SOL, ADA) + panic sleeve on 12 coins + VOLC sleeve (Binance USD-M futures)

## Strategy (v2.0, Oct 2026) - long AND short

4-hour candles, UTC, Binance last price.

| | |
|---|---|
| Trend filter | Long only while the last closed **daily** close is above the daily **EMA50** and the EMA is higher than 5 days ago; short only when below and falling. Otherwise no order |
| Stretch filter (v2.1) | No new order while the daily close is more than **4 daily ATR14** away from the daily EMA50 (do not chase) |
| Coins (Oct 2026) | BTC, ETH, BNB, SOL, ADA, risk per trade by the ladder below (DOGE dropped: weakest coin over the last 12 months; BNB and SOL strongest alts; `research/crypto/studies/all12.py`, `combos22.py`). At $300 SOL's 1-SOL minimum order may skip SOL trades until the account is larger: `check_setup.py` shows it |
| Open-interest filter (v2.4) | No new order while Binance open interest (USD, hourly) is **down 3% or more versus 72 hours earlier** (`oi_lookback_h` / `oi_min_chg`; 0 = off). Data missing -> no filter. Tested 2022-26 (`research/crypto/studies/filter_test3.py`): $200 2024-26 $8.3k -> $14.0k at 2x risk, worst drop 49% -> 44% |
| OI-low filter (v2.8) | No new order while open interest (USD, hourly) is in the **lowest 20% of its last 90 days** (`oi_low_days` / `oi_low_rank`; 0 = off). Nearly always a short after a sell-off: nobody left to force out, the breakdown fizzles. 90 days of history: Binance's public archive (data.binance.vision) + the API, cached in `oi_<SYMBOL>.json`; not enough history -> no filter. See "OI-low filter" below |
| Entry | At every 4h close while flat (**not on Saturday / Sunday UTC**): a stop order at the **highest high (long) / lowest low (short) of the last 20 closed 4h candles**, valid until the next 4h close, then re-placed |
| Stop loss | **1.0 x ATR14 (4h)** from the fill price, server-side (median 1.5% of price) |
| Breakeven | Once price has gone **+1.5R** in favour, the stop moves to the entry price |
| Profit lock (v2.6, v3.0) | Once price has gone **+5R** in favour, the stop moves to **+2R** (v2.6: +1.5R; `lock_R` / `lock_to`), and at **+8R** to **+3.5R** (`lock2_R` / `lock2_to`, v3.0). See "v3.0" below |
| Stale stop (v3.0) | Exactly **60 hours** after the fill, a trade that never reached +1.5R and is above -0.3R gets its stop moved to the **entry** (closed at once if the price is below the entry) (`stale_h` / `stale_thr` / `stale_to`) |
| Cooldown (v3.0) | After a trade on a coin closed below **-0.5R** (a stop-out), that coin takes **no new entry for 16 hours** (`cool_h` / `cool_R`); the 4h order of a close inside the cooldown waits and is placed when it ends (until that candle's order expires; at market if the price is already past the level, as the backtest) |
| Failed-breakout stop (v3.1) | From **8 hours** after the fill, at every hourly close: a trade that has been **+0.9R** in favour but never +1.5R and is now **below -0.2R** gets its stop moved to **-0.5R** (once); the 16 h cooldown follows that trade whatever its result (`fb_h` / `fb_mfe` / `fb_thr` / `fb_to` / `fb_cool`) |
| BTC cascade (v3.1) | When a **BTC** trade closes below **-0.5R** (after costs), every open ETH / BNB / SOL / ADA trade in the **same direction** that filled in that minute or earlier gets its stop raised to **-0.25R** (a trade already at breakeven or locked is untouched); read from BTC's state file within seconds (`casc_src` / `casc_R` / `casc_to`) |
| Wild-pullback size (v3.2) | At the 4h close that arms the entry order: if the coin's last closed **daily** candle has **ATR14 / ATR100 >= 0.98** (volatility already expanded) and the last **5 days moved >= 0.25 ATR14 against the order** (down for a long, up for a short), the order's risk is **x 0.25**. The trade is still taken, so its cooldown, the BTC cascade and the VOLC hand-over work as with a full-size trade. A x0.25 order under Binance's minimum (while the full one would trade) is raised to the minimum order if it fits the cap and leverage (`vr_mult` / `vr_min` / `vr_chg5`; `vr_mult` 1 = off). See "v3.2" below |
| Exit | stop (initial, failed-breakout, cascade, breakeven, lock, stale), or **120 hours (5 days)** after the fill. No take profit |
| Size | `risk_pct` of equity lost if the stop is hit; notional capped at `max_leverage` x equity (5x: at 2% risk the median is 1.4x, max 4.2x) |
| Risk ladder (v3.2) | `portfolio.json`: **BTC 5% / ETH 3.3% / alts 0.83% from $300 to $10,000** (the first row, under $1,000, at the $1,000-10,000 risks), **2.5% / 1.7% / 0.42% above** (= the v3.0 ladder with its first row flattened; v3.1 was v3.0 x 0.95: 5.7 / 3.8 / 0.79% under $1,000). See "v3.2" and "Risk ladder" below |
| Open-risk cap (v2.5) | `portfolio.json`: the risk of all open positions not yet at breakeven may not exceed **1.1 x the BTC risk** of the ladder step (v3.2: 5.5% of equity up to $10,000, 2.75% above; it counts each trade's actual risk, so a x0.25 trade takes a quarter of the room). A new ETH / BNB / SOL / ADA trade that would go over is made smaller to fit, or not taken if less than a quarter fits. **BTC is exempt** (always full size), but its open risk counts for the others. See below |

About 5 trades a month (long and short), median hold 17 h, average 38 h.

## OI-low filter (v2.8, Oct 2026): `oi_history.py`, page `reports/breakout_support.html`

Study `research/crypto/studies/oi_support.py`: 51 coins (our 5 + 7 dev coins to pick ideas; 14 big + 25 small coins
untouched until the end), 9,555 breakout trades 2022-26, today's rules incl. the 72 h OI filter as the base. 7 idea families
(OI vs price over the setup, squeeze exits after the fill, leverage build-up, coin vs market OI, long/short ratios,
liquidation flushes, tired levels) as grids of 430 settings, six gates fixed in advance (dev coins both periods, plateau,
40 time-shifted luck copies, untouched big coins, our 5 with the bot's weights, real money from $300). **One passed**: no
order while OI ranks in the lowest 20% of 90 days. Our 5 ratio (profit / drop) x1.05 / x1.10, BTC x1.05 / x1.05, untouched
big coins +25R / +17R and smaller drops, small coins +24R / +34R, luck test 98%; plateau 45-90 days x lowest 10-30%. It is
about shorts: it flags ~30-40% of short breakouts (avg -0.37R / -0.13R on our 5 vs +0.84R / +0.61R for the other shorts) and
~2% of longs. Not price in disguise (price at a 90-day low: those breakouts did better). Money, bot sizing from $300 (5 coins):
2022 $367.5k / 46.4% -> $461.6k / 39.4%; 2024 $39.1k / 41.8% -> $41.6k / 40.5%.
AVAX was tried as a 6th coin (v2.8 first push) and removed the same day: with the filter, 6 coins 2022 $526.8k / 47.0%
(vs 5 coins $461.6k / 39.4%), 2024 $45.8k / 41.5% (vs $41.6k / 40.5%): more money but a much deeper worst drop in 2022.
Coin sets with the filter (from 2022 / 2024, $300): BTC only $61k / 40.2%, $13.3k / 30.9%; BTC+ETH $296k / 45.7%, $30.6k /
36.5%; BTC+ETH+one alt $304-374k / 45-47%, $35-38k / 35-40%; all 5 the best money per drop in 2022 (39.4%).
Parity (`dev/test_oi_low.py`): live `strategy.oi_rank` vs the research's rank at every 4h close 2022-26 on all 6 coins:
0 of ~62,000 decisions differ; live-logic replay vs research engine with the filter: identical trades on all 6 coins.
`dev/test_bot_sim.py`: BTC / SOL / AVAX 2024-25 every entry on the same minute; `dev/test_cap_sim.py`: 0 off the rule.
The archive files are the same numbers the research used (max difference 2e-16). First start: ~90 files per coin (~30 s).
With the panic sleeve (v2.8 bot + sleeve, from $300): 2022 $826.9k / 28.2% (bot alone $461.6k / 39.4%), 2024 $60.4k / 36.1%
(bot alone $41.6k / 40.5%). All pages in `reports/` are rebuilt on the v2.8 trades (`build_trades.py v28`).

## v3.2.1 (13 Nov 2026): VOLC tie guard

From the v3.3 research (`research/results/v33_REPORT.md`, Track 0; the rest of that 2,005-setting campaign was not
adopted). When the VOLC sleeve's 10-candle stop sits exactly at the trend bot's 20-candle stop (same coin, same side),
both fill in the same minute and the sleeve trades its part straight back at market: a 1-minute round trip that costs two
taker fees. `volc.py` now places no sleeve stop where the trend bot's resting entry order on that side is at the same
level or nearer (buy: trend bot <= sleeve, sell: trend bot >= sleeve). It checks when placing at the 4h close and at
every poll, since the trend bot may place its order a moment later; a tied sleeve order is cancelled. A VOLC level can
never be beyond the trend bot's, so only exact ties are affected.

Parity (`dev/test_v32_sim.py`, 2021-01 .. 2026-11, the real `volc.py`): 23 tied sleeve stops not placed, **0 collision
trades** (were 3), VOLC entries **114 / 115** in the same minute as the research (the last: SOL 2022-12-11, one minute
apart from tick rounding), exits 112 / 115; trend bot unchanged. Logs show `(tie guard)` when it acts.

**Pre-deployment audit (13 Nov 2026), fixed in v3.2.1:**
- **Hand-over after a take-profit fill:** when the trend bot's order filled on a coin the sleeve held, `volc.py` traded the
  sleeve's whole quantity back at market (not reduce-only). If its take-profit limit had filled (in part) in the seconds
  before, that part was gone and the market order would have cut into the trend bot's position. It now cancels the
  take-profit first, reads its `executedQty`, and sends back only what the sleeve still holds.
- **Tie guard cancel race:** a sleeve stop cancelled by the tie guard is forgotten only once Binance reports it
  CANCELED / EXPIRED / REJECTED. If it triggered first, the fill check adopts the position with its stop loss.
- **One coin's error no longer blocks the others:** `volc.py` manages each coin separately. An exchange error on one is
  logged and retried next poll; key / permission errors still stop the sleeve.
- **Stop loss refused 3 polls in a row:** closed at market (never left without a stop). A take-profit error no longer
  aborts the poll.
- **State files on Windows:** the atomic temp-file swap retries for a moment when a reader holds the file open (bot,
  sleeves).
- Checked and fine as they were:
  - Real Binance field names (`clientAlgoId`, `side`, `triggerPrice` as a string, `algoId`), the same keys the cap
    already reads live.
  - The post-only take-profit rejected with -5022, or returned EXPIRED (closed at market / re-placed next poll).
  - Atomic state writes, with every cross-process reader in try / except.
  - The poll check only calls `openAlgoOrders` for coins where the sleeve has waiting entry orders.
- Tests: `dev/test_volc_edges.py` (12 cases on a stub exchange) and the full `dev/test_v32_sim.py` 2021-26 run on the
  final code (unchanged: VOLC 114 / 115 entries and 112 / 115 exits in the same minute, 0 collision trades, the trend bot and its 1,152 size multipliers identical).

**Updating a server:** `tbo_install.bat` -> **1 Update my bot** (`volc.py`, `bot.py`, `panic.py` changed; no setting or key).

## v3.2 (13 Nov 2026): wild-pullback size, flat first ladder row

Research: `research/results/v32_REPORT.md` (regimes: 1,490 settings), `v32b_REPORT.md` (cap counting, 4 follow-ups) and
`v32c_REPORT.md` (the exact-engine re-test that picked this rule, and the ladder). Live twin
`research/crypto/core/v32deploy.py` (`build_trades.py v32`, botsim's default). Adopted (user decision, 13 Nov 2026):
1. **Wild-pullback size** (`strategy.vol_regime` / `size_mult`, `bot.py` `size(mult=...)`): see the table above. Decided once
   at the 4h close that arms the order (kept for a cooldown release and for the per-minute cap resize), from the 1,499 last
   closed daily candles (the bot now fetches Binance's maximum so the daily ATR100 has converged, as in the research). The
   trade is taken at x0.25 instead of skipped: skipping it inside the 1-minute engine let later full-size re-entries in and
   failed the money gate (2024 drop 32.0% vs 31.5%); taking it small keeps every cooldown, cascade and VOLC hand-over of
   v3.1, so the trend bot's trade list is exactly v3.1's (1,355 trades, 116 of them at x0.25).
2. **Ladder** (`portfolio.json`): the v3.0 ladder at k = 1.00 with its first row (under $1,000) at the $1,000-10,000 risks:
   BTC 5 / 5 / 2.5%, ETH 3.3 / 3.3 / 1.7%, alts 0.83 / 0.83 / 0.42%, cap 5.5 / 5.5 / 2.75%. Small accounts no longer take
   the extra 1.2x risk under $1,000 (every $300-start window and every 2-year journey began there); from $1,000 the risks
   are v3.0's (v3.1: x 0.95). The panic and VOLC sleeves follow the ladder's BTC risk.

| From $300 (research account; 1,000 two-year journeys from 2022) | v3.1 (x 0.95) | **v3.2 as deployed** |
|---|---|---|
| 2022 start | $1.215M, drop 23.4% | **$2.031M, drop 24.5%** |
| 2024 start | $70.8k, drop 31.5% | **$74.3k, drop 26.2%** |
| 15 Sep - 6 Nov 2026: from $300 / inside the 2024 run | drop 34.4% / 16.0% | **26.6% / 14.2%** |
| 1 Oct - 6 Nov 2026 from $300 | -26.0% (drop 29.1%) | **-22.0% (drop 24.6%)** |
| Losing months of the 2024 run | 11 of 35 | **11 of 35** |
| P(>= $10,000 after 2 years) | 83.4% | **87.1%** |
| Bootstrap median / 1-in-10 low / 1-in-10 drop | $26.4k / $6.63k / 49.5% | **$28.8k / $7.67k / 44.4%** |

The 2022 drop is 1.1 points higher (from $10,000 the risks are v3.0's, not x 0.95); everything else is better. Inside the
2024 run the autumn-2026 chop cost 14.2% at a ~$67k balance; the 26.6% is a $300 start in the first ladder row. On the 14
coins the bot does not trade the rule helps in 2020-23 and lowers the 2024-26 drop, but its 2024-26 net there is slightly
negative: watch it.

**Updating a server to v3.2:** on this PC run `tbo_install.bat` -> **1 Update my bot** (pulls `main`, sends the bot folder
without keys / state / logs, runs `vds_setup.sh`, restarts the service), then **2 Check my setup**: each coin now shows a
"v3.2 wild-pullback size" line (today's daily ATR14/ATR100, 5-day move, and whether longs / shorts would be armed at x0.25).
No new key or setting is needed. The new `portfolio.json` applies at the next sizing. Open trades carry on unchanged; the
first x0.25 decision is made at the next 4h close. To switch the rule off: `"vr_mult": 1.0` in the `config_*.json` files and
restart.

## v3.1 (13 Nov 2026): failed-breakout stop, BTC cascade, VOLC sleeve, risk x 0.95

Research: `research/results/v31_REPORT.md` (7,433 settings, then the v3.1b follow-up), the live twin
`research/crypto/core/v31deploy.py` (`build_trades.py v31`, botsim's default) and `research/results/v31_deploy_money.csv`.
Adopted (user decision, 13 Nov 2026):
1. **Failed-breakout stop tighten** (`bot.py` `check_fb`, `strategy.fb_fires`): see the table above. Replayed on closed 1m
   candles exactly as the research engine (best excursion from the minute after the fill, the hour's last 1m close).
2. **BTC stop-out cascade** (`bot.py` `record_close` / `check_cascade`): BTC's bot writes every closed trade's R (net of
   fees and funding, `strategy.net_R`) into `state_BTCUSDT.json`; the other bots read it every poll. Oct 12 2026: ETH -1.15R
   -> -0.40R, SOL -1.13R -> -0.60R; Nov 4 2026: SOL -1.11R -> -0.39R, ETH -1.10R -> -0.55R.
3. **VOLC sleeve** (`volc.py`, `volc_signal.py`, `volc.json`; started by `run_all.py`): on BTC ETH BNB SOL ADA, at every
   4h close: when the 4h ATR14 is below 0.6 x ATR100 (a quiet spell) and open interest is higher than 24 h earlier, stop
   orders at the 10-candle 4h high (long) / low (short), in the daily trend's direction (both directions while the daily
   efficiency ratio ER10 < 0.25); stop 1 x ATR14; **take-profit +1.5R as a reduce-only post-only LIMIT 0.01% inside the
   target** (maker fee; a touch of the target fills it); closed after 36 h; no order in the 12 h after a panic-sleeve
   trigger (`panic.py` records its triggers). Size: **0.25 x the ladder's BTC risk** per trade, outside the open-risk cap.
   **Main account, one coin = one position, the trend bot first:** the sleeve arms a coin only while the trend bot has no
   trade on it and cancels its orders when the bot's entry fills. The trend bot never stands aside: it keeps its orders
   while the sleeve holds the coin, and when one fills on top of the sleeve's position, `volc.py` cancels its stop and
   take-profit and trades its own quantity back at market within seconds (also when the bot went the other way); the bot
   then takes over with its own fill price. So the trend bot's trades are exactly the v3.1 research list (1,355 trades,
   none lost to the sleeve). Why the main account: a VOLC position is about 1.4x the whole balance (median; 2.7x at the
   90th percentile, up to 5 open), too big for a sub-account limited to 5x leverage.
4. **Every risk and cap x 0.95** (`portfolio.json`; the panic and VOLC sleeves follow the ladder's BTC risk, so they scale
   too): BTC 5.7 / 4.75 / 2.375%, ETH 3.8 / 3.135 / 1.615%, alts 0.7885 / 0.7885 / 0.399%, cap 6.27 / 5.225 / 2.6125%. Rule
   (user): x 0.90 if it beats v3.0's 2024 money and bootstrap median, else x 0.95. x 0.90 did not (2024 $56.9k).

| From $300 (research account, 1,000 two-year journeys from 2022) | v3.0 | v3.1 x 0.90 | **v3.1 as deployed (x 0.95)** | v3.1 x 1.00 |
|---|---|---|---|---|
| 2022 start | $1.125M, drop 26.0% | $1.033M, drop 22.2% | **$1.215M, drop 23.4%** | $1.588M, drop 24.5% |
| 2024 start | $61.0k, drop 34.0% | $56.9k, drop 30.1% | **$70.8k, drop 31.5%** | $72.2k, drop 32.9% |
| 1 Oct - 6 Nov 2026 (from $300) | -32.6% (drop 33.6%) | -24.7% (27.8%) | **-26.0% (29.1%)** | -27.2% (30.4%) |
| Losing months of the 2024 run (average) | 12 of 35 (-7.3%) | 11 (-5.5%) | **11 (-5.8%)** | 11 (-6.1%) |
| Bootstrap median / 1-in-10 low / 1-in-10 drop | $23.4k / $4.87k / 56.7% | $23.8k / $5.89k / 47.9% | **$26.4k / $6.63k / 49.5%** | $29.4k / $7.49k / 51.2% |

x 0.95 beats v3.0 on every money and every drop figure above. The VOLC sleeve as deployed earns less than in the research
grid: +0.35R / +0.19R per trade in 2022-23 / 2024-26 (PF 1.76 / 1.37, 115 trades, 5 of them handed over to the trend bot)
vs +0.32R / +0.25R in the grid (that grid filled take-profits at a touch with the maker fee, read OI from a different
sample and excluded panic triggers 12 h into the future). A take-profit limit AT the target (filled only when the price
trades through it) did worse than a market take-profit (+0.14R vs +0.17R): the limit sits 0.01% inside the target. It is the
least proven part (found in a follow-up grid, failed its own money gate by a hair): watch it.

**Updating a server to v3.1:** on this PC run `tbo_install.bat` -> **1 Update my bot** (it pulls `main`, sends the bot
folder without keys / state / logs, runs `vds_setup.sh` and restarts the service), then **2 Check my setup**: the new
"VOLC SLEEVE" lines show the sleeve's size per coin against Binance's minimums. No new key is needed (the sleeve uses the
main account's key). Open trades carry on: their stop, breakeven and lock stages are kept, and the failed-breakout check
starts on them from their fill. The sleeve places its first orders at the next 4h close. To run without the sleeve:
`"enabled": false` in `volc.json` and restart. `TBO-VDS.bat` shows the live output: the sleeve's lines are tagged `VLC`,
and /status lists its open trades under 🌀.

## v3.0 (Nov 2026): cooldown, exit curve, panic sleeve on 12 coins

Research: `research/results/v30_REPORT.md` (4,687 settings, protocol fixed in advance: fixed-unit return / drop in the dev
period and 2024-26, neighbour plateau, 40 phase-shifted candle copies + random nulls, drawdown-matched money with 1,000
bootstrap journeys) and `research/crypto/studies/v30_deploy.py` (the adopted combination). Adopted (user decision, Nov 2026):
- **C1** 16 h cooldown after a stop-out (see the table above); **C2** the all-coins exit curve: lock +5R -> +2R, second lock
  +8R -> +3.5R, stale stop at 60 h (breakeven stays at +1.5R). Not adopted: the alts entry geometry (grid edges, +1% money).
- **C4** the panic sleeve also on XRP, DOGE, AVAX, LINK, DOT, LTC, TRX (`extra_coins` in `panic.json`): their own pool of
  **0.75 x 3 = 2.25 units per event**, the 5 core coins keep their full 3 units; at most **2 extra-coin trades open**
  (`max_extra_open`), the largest |open-interest drop| x |premium z| first when more trigger.

| From $300 (botsim page definition: worst drop incl. open sleeve risk) | v2.8 + v2.7 | **v3.0** |
|---|---|---|
| 2020 start | $10.47M, drop 35.5% | $10.51M, drop 34.6% |
| 2022 start | $689k, drop 28.2% | **$1.125M**, drop 29.8% |
| 2024 start | $50.3k, drop 36.1% | **$61.0k**, drop 34.0% |
| 2-yr bootstrap (1,000 journeys from 2022, research account): median / 1-in-10 low / 1-in-10 drop | $18.95k / $2.92k / 64.6% | **$23.4k / $4.87k / 56.7%** |

The bot alone: 2022 $472k / drop 27.1% (v2.8 $384k / 39.4%), 2024 $33.8k / 34.8% (v2.8 $34.6k / 40.5%), 2020 $4.48M (v2.8 $5.86M:
the cooldown costs in the 2020-21 run). Fixed-unit return / drop vs v2.8: x1.25 (2020-23), x1.46 (2022-23), x1.11 (2024-26),
better on 97.5% of the phase-shifted copies in both periods. The 2022-start drop is 1.6 points higher on the page definition
(12 coins = more sleeve risk open in a crash) and 0.3 lower on the research account's. Caveat: no untouched hold-out is
left (2024-26 was a gate); live trading is the out-of-sample test. Trade list: `build_trades.py v30` (botsim's default).

### Your own trades on the same account (Nov 2026)
Open them in **isolated margin** on a coin no bot trades (e.g. TAOUSDT): the bots then leave them out of the balance they size
on (its isolated margin + P&L; back in once it is closed) and out of the open-risk cap, and do not warn about them.
A position on a bot coin always counts (one-way mode merges it with the bot's position anyway); a cross-margin position on
another coin is counted like before. `check_setup.py` lists the trades it leaves out.

## Panic sleeve (v2.7, Oct 2026; v3.0: + 7 extra coins): `panic.py`, `panic_signal.py`, `panic.json`, page `reports/panic.html`

A second, separate strategy that buys **forced-liquidation crashes** and sells the rebound. When a coin falls hard while
**open interest collapses**, leveraged longs are being liquidated: market sells at any price, so the price overshoots
and tends to snap back. (If open interest RISES during the drop, new shorts are opening: real selling, no rebound.)

| | |
|---|---|
| Account | A Binance **sub-account** with its own API key (`PANIC_API_KEY` / `PANIC_API_SECRET` in `.env`): its positions never touch the bot's (in 27% of panic trades the bot is short the same coin) |
| Signal | Checked after every hourly close on BTC, ETH, BNB, SOL, ADA (+ v3.0 extra coins XRP, DOGE, AVAX, LINK, DOT, LTC, TRX): over the last **4 hours** the price fell **>= 1.5x its normal 4-hour move** (std of the last 168 hourly returns x 2), **open interest fell >= 12%**, and the futures **premium is at a discount** (z-score <= -1 over 30 days) |
| Entry | Market buy at once (the next hour's open in the backtest). Long only (short squeezes: rare and losing) |
| Exits | Take-profit **+3 x ATR(1h)**, stop **-4 x ATR(1h), never more than 20% below the entry** (both on Binance; without the limit the FTX crash would have put the stop 68% away), the stop moves to the **entry once the price was +2 ATR** above it, otherwise **closed after 12 hours** |
| Size | **3 units per panic event**: 1 unit = 1/6 of the ladder's BTC risk, a 5% move = 1 unit's risk. At the $0-1k row (BTC 6%) a 5% move against the position costs 3% of the balance (position = 60% of the balance), split equally if several coins trigger in the same hour. Sized on **main + sub-account** (one pool, as in the research); follows the ladder automatically |
| Balance | The bot also sizes on main + sub when the key is set (portfolio.json `"pool_panic_balance": false` = main only). Keep **20-30%** of the money on the sub-account (`check_setup.py` shows it) |
| Frequency | About 1.2 events a month on the 5 coins (86 trades 2022-26), held 10 hours on average (most run the full 12 h) |

Backtest (`research/crypto/core/panic_sleeve.py`, the live signal code; bot's real sizing from $300, open interest data
from Dec 2021): bot alone from 2022 $367.5k, worst drop 46.4% -> bot + sleeve **$652k, 29.2%**; from 2024 $39.1k, 41.8%
-> **$50.7k, 36.1%**. Sleeve trades: 74% win, average win +5.9%, average loss -3.3%, profit factor 5.2. The exact settings
are a good point of a broad plateau: over 81 neighbouring settings (window 3-6 h, OI 10-15%, premium -0.5 to -1.5,
2-4 units) 70% give more money AND a smaller drop in both runs; the typical neighbour adds +5-20% and a few points less
drop. On 41 coins never used to find it the effect holds (2022-23 x1.03-1.13, 2024-26 x1.17-1.21 on the bot's
return / drop) when sized per event. Weak spot: long bear-market cascades (2022: LUNA, FTX). Details: `reports/panic.html`.

Set up: Binance -> Sub-accounts -> create one -> enable Futures -> transfer 20-30% of the balance -> API Management of the
sub-account: create a key (Enable Futures, NO withdrawals, restrict to the server's IP) -> `tbo_install.bat` option 8 (my
server) or 6 -> 9 (someone's server) saves it and restarts; `check_setup.py` checks it. Logs: `logs/PANIC.log`.

## How v2 was found (Oct 2026)

`research/crypto/studies/wf_grid.py` ran 3,000 settings around v1 (timeframe, channel, stop, hold, EMA, long/both,
trail, EMA slope, weekend skip, breakeven); `wf_eval.py` does an **anchored walk-forward**: for each year
2022-2026 the best return/drawdown setting on the years BEFORE it is traded in that year (out of sample).
- v1.0 (fixed) 2022-26: 15.5R/year, DD 11.7R -> 2.0%/month at 2% risk, DD 21%.
- Walk-forward picks 2022-26: 23.6R/year, DD 13.4R -> 3.3%/month at 2% risk, DD 24% (honest estimate).
- Every yearly pick used: weekend skip, breakeven 1.5R, 4h, channel 20-30, EMA50, 5-day hold; the top 25
  settings on all data agree (weekend skip 23/25, breakeven 24/25).
- **ETH (never used for tuning)**, 2020-03..2026-09: v1 +88R DD 21.8R -> v2 +178R DD 17.0R, every year
  positive, shorts +72R.
- Rejected: "halve risk after a -3R/-5R drawdown" (worse than simply a lower risk: losing streaks come right
  before the big trend trades), top-K averaging (small gain, needs several positions), trailing exits on ETH.

## Round 3 tuning (v2.1, Oct 2026): `research/crypto/core/wf2.py`, `ext_check.py`

- Stage A, 2,592 core settings around v2 (channel 15-30, stop 0.75-1.25 ATR, breakeven 1-3R / +0.2R, hold
  72-168 h, EMA 30-75, slope 3-10 days): v2 is the best setting on all data AND the peak of every single
  parameter; re-picking every year on this finer grid did worse out of sample (1.9%/month vs v2's) ->
  finer tuning only fits noise. Core unchanged.
- Stage B, filters on v2: take profit 5R/8R, breakout buffer, 200-day trend, volatility percentile, weekend
  trading all worse; volume filter worse. **Distance from the daily EMA50 <= 4 daily ATR** helps: smooth
  plateau 4-5 ATR, walk-forward picked it 3 of 5 years, and on ETH (untouched) return/DD 1.59 -> 1.85.
  BTC 2020-26: +255R DD 13.1R -> +269R DD 12.2R (2% risk: 5.2 -> 5.6%/month in-sample, DD 24 -> 22%).

## Backtest of v2 (fees: 0.05% taker + 0.01% slippage on stop/market fills, funding 0.01%/8h)

| BTCUSDT 2020-03..2026-09 | Trades | PF | Net | Max DD | Longs / shorts |
|---|---|---|---|---|---|
| v1.0 (long only) | 252 | 1.81 | +126R | 11.7R | +126R / - |
| **v2.0** | 402 | 2.00 | +255R | 13.1R | +217R / +38R |

By year (R): 2020 +75, 2021 +24, 2022 +19, 2023 +53, 2024 +35, 2025 +18, 2026 (to Sep) +31.
$1,000 compounded over the 6.6 years: 2% risk -> 5.2%/month average, max DD 24%; 3% -> 7.0%/month, DD 34%.
**These are in-sample (settings picked on this data): plan on the walk-forward figure, about 3-4% a month
at 2% risk, with drawdowns up to 25-30%, and losing months (about 4 in 10).**

## ETHUSDT (Oct 2026): same settings as BTC, `config_eth.json`

Tuned with the same anchored walk-forward (`research/crypto/core/wf2.py eth|ethf ETHUSDT`, `eth_narrow.py`):
5,184 core settings, a narrow channel/stop search and 256 filter settings. **None beat the BTC v2.1
settings out of sample** (2022-26 at 2% risk: BTC settings 3.2%/month DD 28%; ETH-tuned 2.7%, narrow
3.2% but DD 37%, filters 2.6%), so ETH runs the BTC settings unchanged - never fitted to ETH data.

| ETHUSDT 2020-03..2026-09 (`eth_report.py`) | |
|---|---|
| Trades | 364 (4.6/month), PF 1.87, +191R, max DD 15.7R, worst losing run 17 |
| Longs / shorts | +116R / +75R |
| By year (R) | 2020 +43, 2021 +25, 2022 +24, 2023 +14, 2024 +20, 2025 +14, 2026 (to Sep) +50 |
| Months positive | 43% (best +32R, worst -7R) |
| $1,000 at 1% / 1.5% / 2% risk | 2.1% / 3.0% / 3.7% per month, max DD 15% / 22% / 28% |

BTC for comparison: 1% / 1.5% / 2% -> 3.1% / 4.4% / 5.6% per month, DD 12% / 17% / 22% (in-sample for BTC).
Stop: median 1.8% of ETH's price -> 2% risk is 1.1x leverage (max 4.4x).

**Both bots on one account:** monthly results correlate 0.52 and 65% of BTC trades overlap an ETH trade in
the same direction, so losses often come together. Closed-trade simulation: 1% risk each -> 5.3%/month,
DD 24%; 1.5% each -> 7.5%/month, DD 34% (open-trade drawdowns are deeper than these closed-trade figures).
Use about 1% each when running both.

Parity on ETH: `dev/replay.py ETHUSDT` 337 / 337 trades; `dev/test_bot_sim.py ETHUSDT` 316 of 320 on the same minute,
gross R 181.7 (bot) vs 178.8 (backtest): the differences are fills whose stop the backtest hits inside the
fill minute (pessimistic), while the bot's stop goes on a few seconds later.
Run: `python cryptobot/bot.py cryptobot/config_eth.json` (a second process next to the BTC one).

## Trailing stops vs the 5-day close (Oct 2026, `research/crypto/studies/trail_scan.py`)

Tested on BTC and ETH: intrabar trailing stops 1-8R behind the best price (starting at +1.5/3/5R, max hold
5/10/20 days), 4h-close chandelier trails (6/12/24 candles, 2-4 ATR) and longer holds alone (110 variants).
None beats the 5-day close: tight trails (1-4R) cut the trend trades that dip mid-move; an 8R trail ties
(BTC -9R, ETH +18R); longer holds add drawdown (ETH 28% -> 41% at 2%); the yearly walk-forward choice did
worse than the 5-day close on both coins. Trades that reach the 5-day close keep 71% of their best point
on average (best +10R, exit +7R). Kept: no trailing stop.

## History: earlier research (the live setup is in "Risk ladder", "3-month trial" and "GO LIVE" below)

## More coins (Oct 2026): `research/crypto/portfolio*.py`

TBO v2.1 untouched on 12 coins (alts charged 0.03% slippage per taker fill): all 12 positive in 2020-23, 9 of 12 in
2024-26 (LINK, LTC, DOT negative); trade results correlate only 0.21 between coins on average. But more coins did
NOT give a better return per drawdown: on 2024-26 (coins chosen on 2020-23 only), in R units:

| set | trades/week | return/DD 2024-26 | longest flat |
|---|---|---|---|
| BTC+ETH | 2.1 | 3.13 | 175 d |
| **BTC+ETH+DOGE+ADA** (2020-23 return/DD >= 1) | 4.3 | 2.50 | 122 d |
| top 6 by 2020-23 return/DD | 6.5 | 2.34 | 224 d |
| all 12 | 13.6 | 1.34 | 421 d |

One $1,000 account (risk per trade, 3% open-risk cap, drawdown on 'all open trades stopped' basis):
- 2020-03..2026-09: BTC+ETH 1% each 4.9%/month, DD 25%; BTC+ETH+DOGE+ADA 0.6% each 5.3%/month, DD 25%,
  months positive 59% vs 55%, worst month -12%.
- 2024-01..2026-09 only: BTC+ETH 1% 4.4%/month DD 20%; 4 coins 0.6% 4.0%/month DD 22%, longest flat 156 d vs 296 d.
With 4 coins at 0.5-0.6% the 3% cap never binds, so the bot runs one process per coin with no shared state.
Configs: `config_btc.json`, `config_eth.json`, `config_doge.json`, `config_ada.json` (set the same risk_pct in all four).
Parity: `dev/replay.py DOGEUSDT` 334/335 from 2021 (2020 differences = DOGE's warm-up after listing), ADA 348/348.

## Winners vs losers (Oct 2026): `research/crypto/studies/trade_features.py`, `sizing_rules.py` -> v2.2

1,474 trades of BTC/ETH/DOGE/ADA compared by the conditions when the order was placed (hour, weekday, volatility,
channel width, level age, EMA distance/slope, volume, move into the breakout, previous trade, BTC agreement, side).
Consistent in 2020-23 AND 2024-26 on all 4 coins: shorts earn ~+0.2R vs longs ~+0.8-1.1R; trades in 'wild' weeks
(7d/90d vol >= 0.87) and in very steep trends earn little. Hour, weekday, volume, previous result: noise.
Tested as sizing (4-coin portfolio, return/DD 2020-23 | 2024-26): v2.1 3.15 | 2.60; **shorts at half size
3.58 | 3.20** (the only rule better in both periods); half size when wild 3.00-3.14 | 2.55-2.85; half size when steep
2.97 | 3.10; skip wild 3.14 | 1.71.
**v2.2 = v2.1 + `short_risk_mult` 0.5.** $1,000, 4 coins, 0.75% longs / 0.375% shorts: 2020-26 6.0%/month, DD 27%,
months positive 62%, worst month -11%; 2024-26 alone 4.5%/month, DD 20% (vs 0.6% full-size shorts: 4.0%, DD 22%).
Configs: all four at `risk_pct` 0.75, `short_risk_mult` 0.5. Note: BTCUSDT quantities step 0.001 BTC, so on a
$1k account BTC positions round down (shorts ~20% smaller than intended); DOGE/ADA have fine steps.

## Coin weights and risk for a $500 account (Oct 2026): `research/crypto/studies/weights.py`, `risk_mc.py`

BTC is the steadiest coin in both periods (return/DD 4.83 | 3.78), DOGE/ADA the bumpiest. Weights BTC 2x, ETH 1x,
DOGE 0.5x, ADA 0.5x: 4-coin return/DD 4.31 | 4.44 vs equal weights 3.64 | 3.11 (2020-23 | 2024-26).
Monte Carlo (20,000 two-year paths from reshuffled real months 2022-26, $500 start), base risk = 1x coin:
1.25% (BTC 2.5%): P(hit $100) 0.01%, P(< $250) 2.4%, max drop typical 37% / 1-in-20 58%, $1k typically in 8 months.
1.5%: P(< $250) 5%, 1-in-20 drop 65%. Above 1.5% the bad cases stop improving (volatility drag).
**Configs then (4 coins, before v2.5): BTC 2.5%, ETH 1.25%, DOGE 0.625%, ADA 0.625% (shorts half).** With all four open: up to ~5% of
equity at risk and ~3-4x notional; the bot sets 5x leverage per symbol, so margin use stays below equity.
The simulation reshuffles months independently and uses closed trades: real drawdowns can be deeper.

## Open-risk cap (v2.5, Oct 2026): `research/crypto/studies/sizing_v3.py`, `sizing_v4.py`, page `reports/cap_comparison.html`

Why: the deepest drops come when several coins break out together and all their stops get hit. Capping the risk
that is open at once (only trades not yet at breakeven count: a breakeven stop loses nothing) trims exactly
those moments. BTC is the best coin, so it is never trimmed; its risk still counts, so while BTC is in a fresh
trade the other coins get less room. $200, compounding, worst drop counting open risk as lost:

| BTC 5% / ETH 2.5% / alts 0.83% | 2020-23 %/month, worst drop | 2024-26 $200 -> | worst drop |
|---|---|---|---|
| no cap | 19.1%, 50% | $15.3k | 45% |
| cap 5.5%, all coins | 18.5%, 47% | $14.6k | 38% |
| **cap 5.5%, BTC exempt (v2.5)** | 18.9%, 49% | **$18.2k** | **38%** |

Smooth from 0.9x to 1.1x the BTC risk (1.3x: less gain; 1.5x: no effect). A cap among ETH + alts only (ignoring
BTC's risk) does nothing. If you change the BTC risk, set the ladder row's `cap_pct` (or `open_risk_cap_pct` without a ladder) to about 1.1x it (BTC 6% -> 6.6).

How the bot applies it (the order is sized at the 4h close, before it fills, so it keeps checking):
- At the 4h close: room = cap x equity - risk of the other open positions not at breakeven (read from Binance:
  every position and its stop loss; a position whose stop is not placed yet uses its bot's state file).
- Every minute while the entry order waits: re-sized if the room changed by 5% or more (other coins filled,
  reached breakeven or closed); an order held back for lack of room is placed once room opens, unless the price
  already went through the level.
- Right after a fill: if coins that filled earlier (same minute) left less room, the position is cut to fit.
- Sizing only at the close would keep less of the gain (2024-26 $17.0k, drop 41%); with the re-checks it is
  the same as checking at the fill ($18.2k, 38%).
- Cap set but the account cannot be read: no new ETH / alt order that candle (no risk added blind).
- `portfolio.json` is read every time: an edit applies without a restart. Delete it (or set 0) to turn the cap off.

## Parity tests

**v3.2 (13 Nov 2026): `dev/test_v32_sim.py <start> <end>`** (the v3.1 test plus the wild-pullback size; research twin
`research/crypto/core/v32deploy.py`, `build_trades.py v32`). Run 2021-01 .. 2026-11 in three parts:

| | 2021-22 | 2023-24 | 2025 - 6 Nov 2026 |
|---|---|---|---|
| 4h closes checked (ATR14/ATR100, 5-day move, x0.25 for longs and shorts) | 21,748: 0 differ | 21,930: 6 differ (one SOL day, see below) | 20,220: 0 differ |
| Trades: size multiplier bot = research | 406 of 406 (32 at x0.25) | 442 of 442 (41) | 304 of 304 (28) |
| TBO entry / exit minute | 406 / 402 of 413 | 442 / 430 of 446 | 304 / 303 of 304 |
| VOLC entry / exit minute | 35 / 35 of 36 | 44 / 44 of 44 | 35 / 33 of 35 |
| VOLC with the v3.2.1 tie guard | 35 / 35 of 36, 0 extra | 44 / 44 of 44, 0 extra | 35 / 33 of 35, 0 extra |

- The bot's formula on the research's own daily candles is identical (largest difference 2.4e-12). The simulated
  exchange rounds old prices to today's tick (SOL 0.01, where its 2023 data moved in 0.001 steps), so on 10 Feb 2023 its
  SOL VolReg was 0.97991 vs the research's 0.98042: x0.25 for longs at that day's 6 closes in the research, not in the bots
  (no trade that day). Live, the bot reads the same Binance candles the research is built from.
- Entry / exit differences are v3.1's: one-minute shifts from tick rounding and SOL's minute-data gaps, the backtest's stop
  inside the fill minute. The VOLC trades only in the bots before v3.2.1 (BNB 7 Dec 2022, BTC 10 Apr 2023, BNB 24 Jul 2023)
  were same-minute ties with the trend bot's entry: removed by the tie guard (see v3.2.1).
- `dev/test_cap_sim.py 2022-01-01 2026-11-06` (v3.2 ladder, the x0.25 multiplier and the minimum-order floor in the expected risk): $10,000 886 entries (66 at x0.25), 79 shrunk by the cap, BTC 193/193 full size; $500 834 entries (60 at x0.25, 6 raised to Binance's minimum), 118 shrunk; $300 789 entries (58 at x0.25, 5 raised); **0 entries off the rule** at all three. The test now counts the other positions at the stop in force at the entry (a failed-breakout tighten lowers their risk, as the bot counts it) and calls a quick market close a cap close only when the bot says so.

**v3.1 (13 Nov 2026): `dev/test_v31_sim.py <start> <end>`.** The five coin bots (`bot.py`) and the VOLC sleeve
(`volc.py`) run together on ONE simulated account fed with 1m history (cap off, so every trade the rules allow is taken).
Their trades are compared with the research twin `research/crypto/core/v31deploy.py` (`build_trades.py v31`): the
failed-breakout stop, the BTC cascade through BTC's state file, the cooldown after both, and the VOLC / trend-bot
hand-over on the same coin. Results: same entry minute, then same exit minute.

| Year | TBO trend bots (entry / exit minute) | VOLC sleeve (entry / exit minute) |
|---|---|---|
| 2021 | 255 / 254 of 261 | (no setups) |
| 2022 | 146 / 143 of 147 | 35 / 35 of 36 |
| 2023 | 222 / 214 of 225 | 26 / 26 of 26 |
| 2024 | 215 / 211 of 216 | 18 / 18 of 18 |
| 2025 | 166 / 165 of 166 | 25 / 23 of 25 |
| 2026 to 6 Nov | 138 / 138 of 139 | 10 / 10 of 10 |

Entry prices are within 0.11%. Every difference is in an old category: one-minute entry shifts from tick rounding and
SOL's minute-data gaps (2021: 6, 2023: 3), the backtest's stop inside the fill minute (the bot places its stop seconds
after the fill), take-profit limits rounded to the tick (VOLC 2025: 2), and the trade still open at the end of the data. The
Oct 12 and Nov 4 2026 cascades and the 5 hand-overs of a coin from the VOLC sleeve to the trend bot are identical.

Problems found and fixed by this test:
- **Fill just before a 4h close** (since the "your own trades" change, commit e69da14): an entry that filled in the last
  poll before a 4h close was taken for a manual position, so the bot placed **no stop loss** on it. Live this is rare (the
  window is one 5-second poll) but dangerous. `on_candle_close` now adopts such a fill first.
- **Both orders on a coin trigger in the same minute** (trend bot and VOLC): the trend bot keeps the coin and `volc.py`
  trades its own part back at once.
- **Time exit**: counted from the fill minute (as the research and the stale check), not the fill's millisecond, which made
  the bot leave up to a minute after the backtest.

`dev/test_bot_sim.py` (one bot vs `replay.py`) checks the v3.0 core with the v3.1 rules switched off.
- `dev/test_cap_sim.py 2024-01-01 2026-11-06` with the v3.1 ladder (x 0.95): at $10,000 509 entries, 54 shrunk by the cap,
  BTC 121/121 full size; at `CAPSIM_EQ=500` 466 entries, 64 shrunk, BTC 116/121 full (Binance's 0.001 BTC step); **0 entries
  off the rule** at both balances.
- `dev/test_panic_sim.py` (with the trigger record for VOLC): 0 missed / 0 extra signals in 3,449 hours, trades 208/208,
  207/208 the same result (the known ADA 2024-04-12 take-profit rounding).

**v3.0 (Nov 2026), all re-run on the v3.0 configs:**
- `dev/replay.py <coin> 2020-09-01 2026-11-07` (live decision code with the v3.0 rules) vs `research/crypto/core/v30lib.trades_v30`
  (xengine30): BTC 258/258, ETH 259/260 (the window's first minute), BNB 263/263, SOL 200/219 (19 before the replay's
  1000-candle warm-up), ADA 227/227 on the same entry AND exit minute, same prices.
- `dev/test_bot_sim.py <coin> 2021-03-01 2026-11-06` (bot.py itself on a simulated exchange vs the replay): BTC 234/234,
  ETH 231/231, BNB 233/233, ADA 199/200, SOL 193/200 on the same entry minute. Every difference (`dev/parity_detail.py`)
  is one of the old categories: the backtest's stop inside the fill minute (BNB 5, ADA 3; the bot's stop is placed seconds
  after the fill), 1-minute entry shifts from tick rounding (the simulated exchange serves tick-rounded prices; one SOL
  entry 3 h earlier at the same 49.00 level), SOL's minute-data gaps (bar count vs clock); none is a cooldown, stale or
  lock difference. (Fixed: the simulated OI history ignored bot.py's `budget_s`, so earlier sims ran without the OI-low filter.)
- `dev/test_oi_low.py`: block decisions identical on all five coins (10,623 4h closes each); trades with the v2.8 exits
  identical except SOL 171/172 (minute-data gap).
- `dev/test_panic_sim.py` (12 coins, one chronological run with the real Sleeve.select): signal parity 0 missed / 0 extra
  in 3,449 hours; trades 208/208 (coin, entry hour, units share), 207/208 the same result (ADA 2024-04-12: the take-profit
  order rounded up to the tick sat just above the hour's high). Fixed for v3.0: a coin's new signal counts only after the
  hour in which its last trade closed (the research rule; the live code allowed that same hour).
- `dev/test_cap_sim.py 2024-01-01 2026-11-06` (the five v3.0 bots on one simulated account): at $10,000 507 entries, 62 shrunk
  by the cap, BTC 121/121 full size; at `CAPSIM_EQ=500` 468 entries, 68 shrunk, BTC 118/121 full (Binance's 0.001 BTC step);
  **0 entries off the rule** at both balances.

- `python cryptobot/dev/replay.py BTCUSDT` - the live decision code (`strategy.py`, same 1000 x 4h / 500 x 1d
  windows the bot downloads) vs the research engine: v2.1 347 / 347 trades (2020-09..2026-09), same minute, same prices.
- `python cryptobot/dev/test_bot_sim.py BTCUSDT 2021-01-01 2026-09-30` - **`bot.py` itself** driven by a simulated
  exchange on 1m history (v2.1): 327 vs 328 trades, 326 on the same minute, entry price within 1 tick, gross R
  234.8 vs 235.4. The few exit differences are fills where the backtest assumes the stop is hit inside the fill
  minute (pessimistic); the bot places its stop a few seconds after the fill.
- v2.6 profit lock, `dev/test_bot_sim.py <coin> 2024-01-01 2025-07-01`: BTC 76/76, ETH 63/63, ADA 68/68, SOL 72/73, BNB 74/75
  on the same minute; the few differences are the backtest's pessimistic stop inside the fill minute (none reached
  breakeven or the lock). Live-logic replay vs research engine with the lock: ETH 274/274, BTC 278/278 identical.
- **Full run before going live (v2.6, Oct 2026):** `dev/test_bot_sim.py <coin> 2021-01-01 2026-09-30`: BTC 276/277, ETH
  273/274, BNB 287/289, ADA 260/261, SOL 246 (+14 Jan-Feb 2021 trades before the replay's 1000-candle warm-up) on the
  same entry minute; every difference listed by `dev/parity_detail.py`: the backtest's stop inside the fill minute (and its
  knock-on re-entry), 1-minute entry shifts from tick rounding, and SOL's minute-data gaps (the engine counts bars, the
  bot clock time); none involves the profit lock or the cap. `check_replay_engine.py`: replay = engine on all five coins.
  `dev/test_cap_sim.py 2024-01-01 2026-09-01`: see below (re-run with the current ladder).
- `python cryptobot/dev/test_oi_low.py` - the OI-low filter (v2.8): live rank vs research rank at every 4h close and the
  trades with the filter, every coin (see "OI-low filter").
- `python cryptobot/dev/test_cap_sim.py 2024-01-01 2026-09-01` - the **coin bots together on one simulated account**
  with `portfolio.json`: every entry's risk is checked against the cap rule of the research simulation (BTC
  always full size; the others shrunk to the room left by the coins that filled before them).
  With the current ladder (Oct 2026), 2024-01..2026-09 at `CAPSIM_EQ=500 / 3000 / 10000 / 20000` (the 6/4/.83, 5/3.3/.83
  and 2.5/1.7/.42 steps): 530 / 594 / 594 / 594 entries, 76 / 97 / 82 / 44 shrunk by the cap, 4 cut or closed right
  after a same-minute fill, every BTC entry exempt (at $500, 8 of 130 a little under full size only from Binance's
  0.001 BTC quantity step), **0 off the rule** at every balance.

## Profit lock (v2.6, Oct 2026): `research/crypto/studies/ratchet.py`, `lock_grid.py`, `build_trades.py`

Of the trades that reached +3.5R, about 1 in 3 fell back and closed below +1R (67 in 2020-23, 51 in 2024-26, giving
back ~5R each). Trailing stops cut the big runners (net R -30 to -70%). A one-step lock works: once a trade reaches
+A R, the stop moves once to +L R. Locking early (+3 / +3.5R) hurts; +4.5R to +6R with +0.5R to +2R is better in both
periods (fixed-size R account return/drawdown x1.00-1.15). Chosen: the middle, **+5R -> +1.5R**.

| From $200, ladder + cap, to Sep 2026 | v2.5 | v2.6 (lock) |
|---|---|---|
| from Mar 2020 | $3.12M, worst drop 42.0% | $3.26M, 37.1% |
| from Jan 2022 | $143k, 48.5% | $181k, 44.6% |
| from Jan 2024 | $25.2k, 44.6% | $26.7k, 42.3% |
| runners >= +5R 2024-26 | 55 | 52 |

Event-consistent: the research engine, the live-logic replay and the bot all apply the lock; `build_trades.py v26`
rebuilds the trade list every page uses (1,559 trades from the first one, ETH on 24 Feb 2020, after the indicators' warm-up on
Jan-Feb 2020 data; until Oct 2026 the list started on 1 Mar 2020 and missed that one trade; without the lock it reproduces v2.4).

## Risk ladder (live from Oct 2026): `portfolio.json`

The risk per trade is set by the balance: high while the account is small (money you accepted losing), lower as it
grows (protects what was won). The bot reads `portfolio.json` at every order (an edit applies without a restart) and
`check_setup.py` shows the step that applies now. If the balance falls back under a step, the risk goes back up.

| Balance | BTC | ETH | BNB / SOL / ADA | open-risk cap (BTC exempt) |
|---|---|---|---|---|
| under $1,000 | 6% | 4% | 0.83% | 6.6% |
| $1,000 - 10,000 | 5% | 3.3% | 0.83% | 5.5% |
| from $10,000 | 2.5% | 1.7% | 0.42% | 2.75% |

Shorts at half size. `risk_pct` in the configs is only used if `portfolio.json` has no ladder. BTC's size cap is
12x the balance (`max_leverage`; at 6% risk it limits about 3 in 1,000 BTC trades; ETH's 8x about 3 in 1,000 at 4%) and its Binance
leverage 25x (only sets the margin a position locks; in cross margin it does not move the liquidation point).

2 years from $300 (`research/crypto/core/three_months.py`, same sizing as the bot (`botsim.py`), v2.6 trades; 3,000
reshuffled runs of 2022-26 trades / every real 2-year window of 2022-26):

| v2.6 (with the profit lock) | flat 5% + cap | **ladder (the bot)** | old ladder 7.5/2.5/.83 | flat 7.5% + cap |
|---|---|---|---|---|
| typical end | $7.5k / $8.2k | **$11.0k / $11.1k** | $10.7k / $11.5k | $12.2k / $14.0k |
| 1 in 4 bad end | $2.9k / $4.0k | **$3.6k / $5.0k** | $3.5k / $5.2k | $3.6k / $5.8k |
| reach $10k | 43% / 40% | **53% / 53%** | 52% / 55% | 54% / 60% |
| worst drop (typical / 1 in 10, reshuffled) | 48% / 64% | **51% / 70%** | 52% / 73% | 61% / 77% |
| worst drop once above $1k (typical / 1 in 10) | 42% / 59% | **42% / 62%** | 41% / 61% | 54% / 73% |
| gave back half of a $5k+ peak | 2% | **1%** | 1% | 7% |

Why this ladder (Oct 2026, 62 risk profiles x 1,000 reshuffled 2-yr runs from $300 + real windows + a stress test with
every trade 0.2R worse; then 4 ladders x 9 cap settings): ETH at about 2/3 of the BTC risk is on the best
return-for-drawdown line (ETH's trades are as good as BTC's and often trend at other times); BTC 6% instead of 7.5%
under $1,000 cuts the bad-case drop. Against the old 7.5/2.5/.83 ladder: same or more money, smaller drops, slightly
better in the stress test (runs ending below $300 after 2 years: 2% vs 2% as-is, 12% vs 13% with every trade 0.2R worse). The cap stays
1.1x BTC: looser caps (1.25x-2.5x, none, ETH exempt) give less money AND deeper drops on every ladder (trades let
through while BTC is fresh are the weak, correlated ones); BTC capped too, BTC not counted, or trimming ETH/alts when
BTC joins (BTC joining late averages +1.10R, the best BTC trades) are all worse.

The ladder's extra drops happen while the account is under $1,000; above it, BTC trades like flat 5%. Pages:
all in the top-level `reports/` folder: `trades.html` (equity chart with every trade: click one to see it on its 4h price
chart with entry, stop, breakeven, lock and exit), `tbo_statistics.html` (equity chart, every statistic, random
journeys), `risk_comparison.html`, `plan_ladder_plus50.html`, `monthly_report.html`, `cap_comparison.html`,
`winrate_rr.html`. All are rebuilt from the live settings by the `research/crypto/make_*.py` scripts and size trades
like the bot.

## 3-month trial from $300 (v2.6, Oct 2026)

Settings: the risk ladder above (at $300: BTC 6%, ETH 4%, BNB / SOL / ADA 0.83%, cap 6.6%). Leave them alone
for the 3 months (changing settings mid-way makes the result impossible to judge).

- **Start:** `git pull`, then steps 1-8 below. `python check_setup.py` must say `RESULT: ready`. At $300 SOL trades
  are often too small for Binance's 1-SOL minimum and get skipped (check_setup shows it); that is expected.
- **Every month-end:** `python report.py --days 31` -> `trial_results/report_<date>.md` + two CSV files (Binance keeps
  only a few months of history, so keep each month's files).
- **Every fill** is logged with the level aimed for, the slippage and the risk (`FILLED ... level ..., slippage ...%`).
- **After 3 months:** send the `trial_results/` and `logs/` folders. They are compared with the backtest of the same
  days (same trades? same fills? fees and slippage as assumed?).
- **What 3 months looked like in the past** (`research/crypto/core/three_months.py`, the ladder from $300; every real
  3-month window of 2022-26 and 5,000 reshuffled ones; real results will be somewhat worse):

| After 3 months (v2.6) | real windows | reshuffled |
|---|---|---|
| 1 in 10 bad | $248 | $216 |
| 1 in 4 bad | $280 | $283 |
| typical | $401 | $419 |
| 1 in 4 good | $592 | $677 |
| 1 in 10 good | $986 | $1,170 |
| below $300 / doubled | 31% / 24% | 28% / 30% |
| worst drop inside the 3 months (typical / 1 in 4 / 1 in 10) | 29% / 37% / 46% | 30% / 38% / 46% |

  About 58 trades in 3 months (41-74), most of them small losses or breakeven. A losing 3 months happens about 1
  time in 3 and says little. A drop beyond 60% from the top would be outside the backtest's usual range: stop and
  review then.

## GO LIVE: step by step (v2.6)

**Easiest: `tbo_install.bat` (Windows, in this folder).** Two sections. *My server*: update my bot, check it, or set
it up from scratch (its IP is asked once and kept in `my_server.txt` in the private-files folder, see the top-level README). *Other people's servers*: set up a new person's
server (fresh Ubuntu 22.04/24.04; asks the root password once, then logs in with this PC's SSH key; asks that person's
own Binance key / secret and Telegram token / chat id; installs everything with `vds_setup.sh`; reminds you to add the
server's IP to his API key; runs `check_setup.py`; starts the bot as a service that survives logouts and reboots),
update someone's bot, or manage it (live output, status, restart, stop / start, terminal). *Update ALL bots* does
every server at once. Updates: `git pull` on this PC, then the code is sent to the server (friends' servers never
touch GitHub); a server's `.env`, state files and logs are kept; a server with a git checkout pulls by itself.
The manual steps below do the same by hand.

**Where to run it.** Recommended: a small Linux VPS (~$5/month, e.g. Hetzner in Germany/Finland), **not in the USA**
(Binance.com blocks US IPs). It runs 24/7 without sleep, updates or power cuts. Your Windows PC also works if it
never sleeps. If the bot is offline, open trades stay protected (the stop-loss sits on Binance); you only miss new
entries, breakeven moves and the 5-day exit until it is back.

1. **Binance account (website/app):** open a USD-M Futures account and move the USDT you want to trade into the
   USD-M Futures wallet. Futures settings: **Position Mode = One-way**. Margin mode **Cross** for BTCUSDT, ETHUSDT,
   BNBUSDT, SOLUSDT, ADAUSDT. Do not trade these five coins by hand on this account. Keep some BNB in the USD-M
   Futures wallet with the BNB fee discount on (10% off fees).
2. **API key:** API Management -> create a key (system generated). Tick **Enable Futures**. **Do NOT enable
   withdrawals.** Restrict it to your server's IP address (on a home PC: your home IP, if it is fixed).
3. **Install** (Python 3.10+): `git clone` this repo (branch `main`), then
   `pip install -r cryptobot/requirements.txt`.
4. **Keys:** copy `cryptobot/.env.example` to `.env` in the private-files folder (`TBO_SECRETS_DIR`, default
   `~/tbo-secrets`, on Windows `%USERPROFILE%\tbo-secrets`; see the top-level README) and paste the key and secret. Optional: Telegram
   token + chat id for phone messages (`TELEGRAM_UTC_OFFSET=3` shows times in UTC+3; default: the computer's time zone).
   What arrives (run with `run_all.py`): one short **start-up** message (version and balance);
   **/status** whenever you send it in the chat (or tap it in the bot's / menu), in lines short enough for a phone: every coin as it is now (in a
   trade: R and $ now, entry, price, stop and its stage, time held; an order waiting: its level, how far the price is
   from it, stop loss and risk; or why there is no order: weekend, open-interest filter, no trend, cap full, the
   candle's order already used), then balance, open P&L, open risk and the cap (no message after the 4h checks;
   one bot token per server, or /status answers on only one of them); and per trade: **opened** (entry, slippage, stop loss, the breakeven and profit-lock
   prices, size, risk, opening and time-exit times, the open-risk cap), **stop to breakeven**, **profit locked**,
   **cut by the cap**, **closed** (R, $ after fees and funding, exit reason, hold time, balance). Warnings and
   errors are sent too, each one at most once per 30 minutes.
5. **Risk:** the risk ladder and the open-risk cap in `portfolio.json` (see "Risk ladder"; shorts x0.5 in the
   configs). `risk_pct` in the configs is only the fallback when `portfolio.json` has no ladder.
6. **Check:** `cd cryptobot && python check_setup.py` (places no orders). Every line must be OK (WARN = read it):
   key works, withdrawals OFF, futures ON, One-way, balance, clock, and each coin's long/short size above
   Binance's minimum at your risk.
7. **Try it without risk:**
   - `python run_all.py --dry-run`: real prices, no orders; at every 4-hour close each coin prints its decision.
   - Optional, recommended: Binance futures **testnet / demo** keys in `.env`, then `python check_setup.py --testnet`
     and `python run_all.py --testnet` for a few days. The testnet address is set to `https://demo-fapi.binance.com`;
     if your demo uses another address, add `"base_url": "..."` to the four configs.
8. **Go live:** `python run_all.py` (Windows: double-click `start-bots.bat`). On a Linux VPS make it start on boot:
   copy `tbo.service` to `/etc/systemd/system/`, adjust user/paths, `sudo systemctl enable --now tbo`, watch with
   `journalctl -u tbo -f`.
9. **Day to day:** logs in `cryptobot/logs/<COIN>.log` (+ Telegram). The first log line of each coin shows
   `TBO v2.6`, its risk and settings. Orders appear on Binance as conditional (algo) orders named `tbo_...`.
   - Pause new entries (open trades still managed): create an empty file `cryptobot/PAUSE`; delete it to resume.
   - Stop everything: Ctrl+C / close the window / `sudo systemctl stop tbo`. Stop-losses stay on Binance.
   - Change risk: edit the ladder in `portfolio.json` (read at every order, no restart needed; the configs' `risk_pct` is only the fallback).
   - Restarts are safe: positions are read from Binance, missing stop-losses are re-placed, a missed 4-hour close
     is handled when the bot is back.
10. **Rules for yourself:** judge it after months, not days (about 19 trades a month, most small losses or
    breakeven; ~2 big winners a month pay for it). If the account is down more than 50% from its peak, stop and
    review: that is beyond the backtest's usual range.

**v2.3 changes (before real money):** price checked before every stop order (enters / exits at market if price is
already past the level, instead of relying on error codes); position re-read after cancelling the old entry order
(no double entry if it filled in the same second); a stop-loss that triggered but left the position open is
re-placed after 60 s; tick rounding without floating-point noise; hourly clock re-sync; calm start-up retries;
PAUSE file; Telegram alerts; `run_all.py`, `check_setup.py`. Bot vs backtest on a simulated exchange with tick-exact
prices, H1 2024: BTC 29/29, ETH 24/24, DOGE 35/35, ADA 38/38 entries on the same minute and price.
**Not yet run against the real Binance API** (blocked from the research machine): steps 6-7 are the first real test.

## Running it (older notes)

1. Python 3.10+, `pip install -r cryptobot/requirements.txt`.
2. Binance: Futures account in **One-way** position mode. Create an API key with **Enable Futures** only (no
   withdrawals), IP-restricted to the machine that runs the bot.
3. Set the keys as environment variables (never commit them):
   `set BINANCE_API_KEY=...` / `set BINANCE_API_SECRET=...` (Windows) or `export ...` (Linux).
4. Try it first:
   - `python cryptobot/bot.py cryptobot/config_btc.json --dry-run` - no keys needed: prints the signal and the
     order it would place at each 4h close (sized on `dry_run_equity`, default 1000).
   - `python cryptobot/bot.py cryptobot/config_btc.json --testnet` - Binance futures demo/testnet keys. If your
     demo uses another URL, set `"base_url"` in the config.
5. Live: `python cryptobot/bot.py cryptobot/config_btc.json`. Logs: `cryptobot/logs/BTCUSDT.log`. State:
   `cryptobot/state_BTCUSDT.json` (keep it; it holds the entry time for the 5-day exit).

Settings (`config_btc.json`): `risk_pct` (2.0 = 2% of equity per trade), `max_leverage` (notional cap, also
set as the symbol leverage), `poll_s`, and the strategy block (keep the tested values).

### Behaviour notes

- The bot only touches orders whose client id starts with `tbo`; leave the symbol to the bot (no manual
  BTCUSDT trades in the same account; one bot per symbol).
- After an entry fills, the stop loss is placed on the next poll (a few seconds). If price is already past the
  stop, it closes at market.
- Restart-safe: the position comes from Binance; a missing stop loss is re-placed (from the saved stop
  distance, or 1.5 x current ATR if the state file is lost); a 4h close missed while the bot was off is acted
  on when it comes back.
- Breakeven: the bot reads the last 1m candles every poll; once a candle after the fill has reached +1.5R it
  cancels the stop and places a new one at the entry price (logged as BREAKEVEN).
- Conditional orders use Binance's Algo Order API (`/fapi/v1/algoOrder`, required since Dec 2025), triggered
  on the last price (`workingType=CONTRACT_PRICE`), as in the backtest.
- Not yet run against the real API from here (the research machine cannot reach Binance): **run testnet /
  a small live size first** and check the first fills and stop losses on the Binance app.
