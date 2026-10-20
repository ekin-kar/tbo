# TBO v2.7: trend-breakout bot (BTC, ETH, BNB, SOL, ADA) + panic sleeve (Binance USD-M futures)

## Strategy (v2.0, Oct 2026) - long AND short

4-hour candles, UTC, Binance last price.

| | |
|---|---|
| Trend filter | Long only while the last closed **daily** close is above the daily **EMA50** and the EMA is higher than 5 days ago; short only when below and falling. Otherwise no order |
| Stretch filter (v2.1) | No new order while the daily close is more than **4 daily ATR14** away from the daily EMA50 (do not chase) |
| Coins (Oct 2026) | BTC, ETH, BNB, SOL, ADA, risk per trade by the ladder below (DOGE dropped: weakest coin over the last 12 months; BNB and SOL strongest alts; `research/crypto/studies/all12.py`, `combos22.py`). At $300 SOL's 1-SOL minimum order may skip SOL trades until the account is larger: `check_setup.py` shows it |
| Open-interest filter (v2.4) | No new order while Binance open interest (USD, hourly) is **down 3% or more versus 72 hours earlier** (`oi_lookback_h` / `oi_min_chg`; 0 = off). Data missing -> no filter. Tested 2022-26 (`research/crypto/studies/filter_test3.py`): $200 2024-26 $8.3k -> $14.0k at 2x risk, worst drop 49% -> 44% |
| Entry | At every 4h close while flat (**not on Saturday / Sunday UTC**): a stop order at the **highest high (long) / lowest low (short) of the last 20 closed 4h candles**, valid until the next 4h close, then re-placed |
| Stop loss | **1.0 x ATR14 (4h)** from the fill price, server-side (median 1.5% of price) |
| Breakeven | Once price has gone **+1.5R** in favour, the stop moves to the entry price |
| Profit lock (v2.6) | Once price has gone **+5R** in favour, the stop moves to **+1.5R** (`lock_R` / `lock_to` in the configs). See "Profit lock" below |
| Exit | stop, breakeven stop, or **120 hours (5 days)** after the fill. No take profit |
| Size | `risk_pct` of equity lost if the stop is hit; notional capped at `max_leverage` x equity (5x: at 2% risk the median is 1.4x, max 4.2x) |
| Risk ladder (Oct 2026) | `portfolio.json`: BTC 6% / ETH 4% / alts 0.83% under $1,000; 5% / 3.3% / 0.83% to $10,000; 2.5% / 1.7% / 0.42% above. See "Risk ladder" below |
| Open-risk cap (v2.5) | `portfolio.json`: the risk of all open positions not yet at breakeven may not exceed **1.1 x the BTC risk** of the ladder step (6.6% of equity under $1,000, 5.5% to $10,000, 2.75% above). A new ETH / BNB / SOL / ADA trade that would go over is made smaller to fit, or not taken if less than a quarter fits. **BTC is exempt** (always full size), but its open risk counts for the others. See below |

About 5 trades a month (long and short), median hold 17 h, average 38 h.

## Panic sleeve (v2.7, Oct 2026): `panic.py`, `panic_signal.py`, `panic.json`, page `reports/panic.html`

A second, separate strategy that buys **forced-liquidation crashes** and sells the rebound. When a coin falls hard while
**open interest collapses**, leveraged longs are being liquidated: market sells at any price, so the price overshoots
and tends to snap back. (If open interest RISES during the drop, new shorts are opening: real selling, no rebound.)

| | |
|---|---|
| Account | A Binance **sub-account** with its own API key (`PANIC_API_KEY` / `PANIC_API_SECRET` in `.env`): its positions never touch the bot's (in 27% of panic trades the bot is short the same coin) |
| Signal | Checked after every hourly close on BTC, ETH, BNB, SOL, ADA: over the last **4 hours** the price fell **>= 1.5x its normal 4-hour move** (std of the last 168 hourly returns x 2), **open interest fell >= 12%**, and the futures **premium is at a discount** (z-score <= -1 over 30 days) |
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
- `python cryptobot/dev/test_cap_sim.py 2024-01-01 2026-09-01` - the **five bots together on one simulated account**
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
it up from scratch (its IP is asked once and kept in `my_server.txt`). *Other people's servers*: set up a new person's
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
3. **Install** (Python 3.10+): `git clone` this repo (branch `claude/sweet-meitner-lubkf9`), then
   `pip install -r cryptobot/requirements.txt`.
4. **Keys:** copy `cryptobot/.env.example` to `cryptobot/.env` and paste the key and secret. Optional: Telegram
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
