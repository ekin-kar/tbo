# TBO: BTCUSDT trend-breakout bot (Binance USD-M futures)

## Strategy (v1.0, Oct 2026)

4-hour candles, UTC, Binance last price. Long only by default.

| | |
|---|---|
| Trend filter | Longs only while the last **closed daily** close is above the daily **EMA50** |
| Entry | At every 4h close while flat: a **stop-buy at the highest high of the last 20 closed 4h candles**. It is valid until the next 4h close, then cancelled and re-placed at the new level |
| Stop loss | **1.5 x ATR14 (4h)** from the fill price, server-side (`closePosition` STOP_MARKET) |
| Trailing exit | At a 4h close: exit if close < highest high of the last 12 candles - 2 x ATR14 |
| Time exit | **120 hours (5 days)** after the fill at the latest. No take profit |
| Size | `risk_pct` of account equity is lost if the stop is hit. Notional is capped at `max_leverage` x equity |

Typical stop: 2% of price (0.6-7.5%), so 1% risk is about 0.5x leverage. About 38 trades a year,
average hold 43 h, win rate ~32%. A few winners carry the result: a typical trend-following profile.

## Backtest (fees 0.05% taker + 0.01% slippage per side, funding 0.01%/8h charged)

| Period | Trades | Win % | PF | Net | Max DD |
|---|---|---|---|---|---|
| Dev 2020-03..2023 (tuned here) | 144 | 33 | 1.92 | +80R | 10.5R |
| **Holdout 2024..Sep 2026** (one look) | 108 | 32 | 1.66 | +46R | 11.7R |
| Holdout at 0.10%/side costs | 108 | 30 | 1.55 | +40R | 12.6R |
| ETH, same rules, holdout | 98 | 31 | 1.55 | +35R | 21.8R |

By year (R): 2020 +41, 2021 +11, 2022 -7, 2023 +36, 2024 +28, 2025 +5, 2026 (to Sep) +12.
Compounded 2020-03..2026-09: 1% risk -> CAGR ~19%, max DD ~11%; 2% risk -> CAGR ~37%, max DD ~21%.

Checks: the real entries beat 20 of 20 random-entry runs (same filter and exits) on dev, and 19 of 20 on the
holdout. The 4h / channel 20 / stop 1.5 ATR / EMA50 / 5-day cap area is a broad plateau (74% of 960 nearby
settings pass). Profits are concentrated: without the 10 best trades the 6.5 years are about flat. Expect
long flat or losing stretches (worst run: 9 losses in a row; 2022 and 2025 were weak), and the bot sits
out bear markets (price under the daily EMA50). Shorts (`"sides": "both"`) added nothing net on BTC.
Research code: `research/crypto/` (scans in `research/results/crypto_*`).

## Parity tests

- `python cryptobot/replay.py BTCUSDT` - the live decision code (`strategy.py`, same 1000 x 4h / 500 x 1d
  windows the bot downloads) vs the research engine: 230 / 230 trades, same minute, same prices.
- `python cryptobot/test_bot_sim.py BTCUSDT 2021-01-01 2026-09-30` - **`bot.py` itself** driven by a simulated
  exchange on 1m history: 212 vs 212 trades, 210 on the same minute, entry price within 1 tick, exits within
  1 minute, gross R 104.2 vs 104.6.

## Running it

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

Settings (`config_btc.json`): `risk_pct` (1.0 = 1% of equity per trade), `max_leverage` (notional cap, also
set as the symbol leverage), `poll_s`, and the strategy block (keep the tested values).

### Behaviour notes

- The bot only touches orders whose client id starts with `tbo`; leave the symbol to the bot (no manual
  BTCUSDT trades in the same account; one bot per symbol).
- After an entry fills, the stop loss is placed on the next poll (a few seconds). If price is already past the
  stop, it closes at market.
- Restart-safe: the position comes from Binance; a missing stop loss is re-placed (from the saved stop
  distance, or 1.5 x current ATR if the state file is lost); a 4h close missed while the bot was off is acted
  on when it comes back.
- Conditional orders use Binance's Algo Order API (`/fapi/v1/algoOrder`, required since Dec 2025), triggered
  on the last price (`workingType=CONTRACT_PRICE`), as in the backtest.
- Not yet run against the real API from here (the research machine cannot reach Binance): **run testnet /
  a small live size first** and check the first fills and stop losses on the Binance app.
