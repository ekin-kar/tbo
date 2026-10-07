# TBO v2.2: trend-breakout bot (BTC, ETH, DOGE, ADA) (Binance USD-M futures)

## Strategy (v2.0, Oct 2026) - long AND short

4-hour candles, UTC, Binance last price.

| | |
|---|---|
| Trend filter | Long only while the last closed **daily** close is above the daily **EMA50** and the EMA is higher than 5 days ago; short only when below and falling. Otherwise no order |
| Stretch filter (v2.1) | No new order while the daily close is more than **4 daily ATR14** away from the daily EMA50 (do not chase) |
| Coins (Oct 2026) | BTC 5%, ETH 2.5%, BNB / SOL / ADA 0.83% each (DOGE dropped: weakest coin over the last 12 months; BNB and SOL strongest alts; `research/crypto/all12.py`, `combos22.py`). At $200 SOL's 1-SOL minimum order may skip SOL trades until the account is larger: `check_setup.py` shows it |
| Open-interest filter (v2.4) | No new order while Binance open interest (USD, hourly) is **down 3% or more versus 72 hours earlier** (`oi_lookback_h` / `oi_min_chg`; 0 = off). Data missing -> no filter. Tested 2022-26 (`research/crypto/filter_test3.py`): $200 2024-26 $8.3k -> $14.0k at 2x risk, worst drop 49% -> 44% |
| Entry | At every 4h close while flat (**not on Saturday / Sunday UTC**): a stop order at the **highest high (long) / lowest low (short) of the last 20 closed 4h candles**, valid until the next 4h close, then re-placed |
| Stop loss | **1.0 x ATR14 (4h)** from the fill price, server-side (median 1.5% of price) |
| Breakeven | Once price has gone **+1.5R** in favour, the stop moves to the entry price |
| Exit | stop, breakeven stop, or **120 hours (5 days)** after the fill. No take profit |
| Size | `risk_pct` of equity lost if the stop is hit; notional capped at `max_leverage` x equity (5x: at 2% risk the median is 1.4x, max 4.2x) |

About 5 trades a month (long and short), median hold 17 h, average 38 h.

## How v2 was found (Oct 2026)

`research/crypto/wf_grid.py` ran 3,000 settings around v1 (timeframe, channel, stop, hold, EMA, long/both,
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

## Round 3 tuning (v2.1, Oct 2026): `research/crypto/wf2.py`, `ext_check.py`

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

Tuned with the same anchored walk-forward (`research/crypto/wf2.py eth|ethf ETHUSDT`, `eth_narrow.py`):
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

Parity on ETH: `replay.py ETHUSDT` 337 / 337 trades; `test_bot_sim.py ETHUSDT` 316 of 320 on the same minute,
gross R 181.7 (bot) vs 178.8 (backtest): the differences are fills whose stop the backtest hits inside the
fill minute (pessimistic), while the bot's stop goes on a few seconds later.
Run: `python cryptobot/bot.py cryptobot/config_eth.json` (a second process next to the BTC one).

## Trailing stops vs the 5-day close (Oct 2026, `research/crypto/trail_scan.py`)

Tested on BTC and ETH: intrabar trailing stops 1-8R behind the best price (starting at +1.5/3/5R, max hold
5/10/20 days), 4h-close chandelier trails (6/12/24 candles, 2-4 ATR) and longer holds alone (110 variants).
None beats the 5-day close: tight trails (1-4R) cut the trend trades that dip mid-move; an 8R trail ties
(BTC -9R, ETH +18R); longer holds add drawdown (ETH 28% -> 41% at 2%); the yearly walk-forward choice did
worse than the 5-day close on both coins. Trades that reach the 5-day close keep 71% of their best point
on average (best +10R, exit +7R). Kept: no trailing stop.

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
Parity: `replay.py DOGEUSDT` 334/335 from 2021 (2020 differences = DOGE's warm-up after listing), ADA 348/348.

## Winners vs losers (Oct 2026): `research/crypto/trade_features.py`, `sizing_rules.py` -> v2.2

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

## Coin weights and risk for a $500 account (Oct 2026): `research/crypto/weights.py`, `risk_mc.py`

BTC is the steadiest coin in both periods (return/DD 4.83 | 3.78), DOGE/ADA the bumpiest. Weights BTC 2x, ETH 1x,
DOGE 0.5x, ADA 0.5x: 4-coin return/DD 4.31 | 4.44 vs equal weights 3.64 | 3.11 (2020-23 | 2024-26).
Monte Carlo (20,000 two-year paths from reshuffled real months 2022-26, $500 start), base risk = 1x coin:
1.25% (BTC 2.5%): P(hit $100) 0.01%, P(< $250) 2.4%, max drop typical 37% / 1-in-20 58%, $1k typically in 8 months.
1.5%: P(< $250) 5%, 1-in-20 drop 65%. Above 1.5% the bad cases stop improving (volatility drag).
**Configs now: BTC 2.5%, ETH 1.25%, DOGE 0.625%, ADA 0.625% (shorts half).** With all four open: up to ~5% of
equity at risk and ~3-4x notional; the bot sets 5x leverage per symbol, so margin use stays below equity.
The simulation reshuffles months independently and uses closed trades: real drawdowns can be deeper.

## Parity tests

- `python cryptobot/replay.py BTCUSDT` - the live decision code (`strategy.py`, same 1000 x 4h / 500 x 1d
  windows the bot downloads) vs the research engine: v2.1 347 / 347 trades (2020-09..2026-09), same minute, same prices.
- `python cryptobot/test_bot_sim.py BTCUSDT 2021-01-01 2026-09-30` - **`bot.py` itself** driven by a simulated
  exchange on 1m history (v2.1): 327 vs 328 trades, 326 on the same minute, entry price within 1 tick, gross R
  234.8 vs 235.4. The few exit differences are fills where the backtest assumes the stop is hit inside the fill
  minute (pessimistic); the bot places its stop a few seconds after the fill.

## GO LIVE: step by step (v2.3)

**Where to run it.** Recommended: a small Linux VPS (~$5/month, e.g. Hetzner in Germany/Finland), **not in the USA**
(Binance.com blocks US IPs). It runs 24/7 without sleep, updates or power cuts. Your Windows PC also works if it
never sleeps. If the bot is offline, open trades stay protected (the stop-loss sits on Binance); you only miss new
entries, breakeven moves and the 5-day exit until it is back.

1. **Binance account (website/app):** open a USD-M Futures account and move the USDT you want to trade into the
   USD-M Futures wallet. Futures settings: **Position Mode = One-way**. Margin mode **Cross** for BTCUSDT, ETHUSDT,
   DOGEUSDT, ADAUSDT. Do not trade these four coins by hand on this account.
2. **API key:** API Management -> create a key (system generated). Tick **Enable Futures**. **Do NOT enable
   withdrawals.** Restrict it to your server's IP address (on a home PC: your home IP, if it is fixed).
3. **Install** (Python 3.10+): `git clone` this repo (branch `claude/sweet-meitner-lubkf9`), then
   `pip install -r cryptobot/requirements.txt`.
4. **Keys:** copy `cryptobot/.env.example` to `cryptobot/.env` and paste the key and secret. Optional: Telegram
   token + chat id for phone alerts (fills, stops, breakeven, exits, warnings).
5. **Risk:** set in `config_btc.json` / `config_eth.json` / `config_doge.json` / `config_ada.json` (`risk_pct`; now
   2.5 / 1.25 / 0.625 / 0.625, shorts x0.5). Lower them for your first weeks if you like.
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
   `TBO v2.3`, its risk and settings. Orders appear on Binance as conditional (algo) orders named `tbo_...`.
   - Pause new entries (open trades still managed): create an empty file `cryptobot/PAUSE`; delete it to resume.
   - Stop everything: Ctrl+C / close the window / `sudo systemctl stop tbo`. Stop-losses stay on Binance.
   - Change risk: edit the config, then restart.
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
