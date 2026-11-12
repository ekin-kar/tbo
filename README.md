# TBO: trend-breakout bot for Binance USD-M futures

A 4-hour channel-breakout strategy (long and short) on BTC, ETH, BNB, SOL and ADA, plus a **panic sleeve** that buys
forced-liquidation crashes on a Binance sub-account, with the research that built them.
**Live settings, how they were chosen and how to run the bot: [`cryptobot/README.md`](cryptobot/README.md).**
The full research log (every idea tested, what worked and what did not): [`HANDOFF.md`](HANDOFF.md).

## What is where

| Folder | What it is |
|---|---|
| `cryptobot/` | **The live bot.** `bot.py` (one coin), `run_all.py` (all coins + the panic sleeve + Telegram), `strategy.py`, `binance_futures.py`, `notify.py`; settings in `config_*.json` and `portfolio.json` (risk ladder, open-risk cap); **panic sleeve** `panic.py` + `panic_signal.py` (signal maths shared with the research), settings `panic.json`, sub-account key `PANIC_API_KEY` in `.env`; `check_setup.py` (pre-flight check), `report.py` (monthly results) |
| `cryptobot/` (Windows tools) | `TBO-VDS.bat` (watch / control my server), `tbo_install.bat` (set up and update servers: mine and other people's), `start-bots.bat` (run on this PC) |
| `cryptobot/` (server side) | `vds_setup.sh` (installs / updates the bot on an Ubuntu server), `server_clean.sh` (weekly cleanup of old logs and caches), `tbo.service` (keeps the bot running) |
| `cryptobot/dev/` | Developer checks, not needed to trade: the bot on a simulated exchange vs the backtest (`test_bot_sim.py`, `test_cap_sim.py`, `parity_detail.py`), the panic sleeve on a simulated exchange vs the research (`test_panic_sim.py`), the live-logic replay (`replay.py`), a one-order live test (`live_test.py`) |
| `reports/` | The HTML pages (open in a browser): every trade (`trades.html`), statistics, monthly results, risk and cap comparisons (the trend bot), the panic sleeve (`panic.html`: bot alone vs bot + sleeve, its trades, every setting's plateau), and the breakout support study (`breakout_support.html`: what open interest can and cannot tell about a breakout, the OI-low filter of v2.8). Rebuilt by `research/crypto/pages/` |
| `research/engine/` | The backtest engine (orders, fills, costs, indicators) |
| `research/crypto/core/` | The research library everything uses: data and costs (`common.py`), the strategy in the engine (`families.py`, `xengine.py`), live settings (`wf2.py`, `grid_v25.py`), the bot's sizing (`botsim.py`), the panic sleeve (`panic_sleeve.py`), the trade list (`build_trades.py`, `trade_prices.py`), 1-minute trade simulators (`tradepath.py`, `tradesim.py`), expectations (`three_months.py`), data downloads, engine-vs-replay check |
| `research/crypto/pages/` | The page generators (`make_*.py`) and their HTML templates |
| `research/crypto/studies/` | Every experiment (filters, exits, sizing, other strategies, ...), kept for the record; results in `HANDOFF.md` |
| `research/results/` | Output tables some studies write (CSV), kept for reference |
| `data/` | Binance 1-minute candles 2020-2026 (parquet) and extra Binance data (`data/extra/`: open interest, funding, ...) |
| `cache/` | Rebuilt automatically (not in git) |

## Private files (outside the repo)

Keys and server details are never stored in this repo. The scripts read them from the folder named by the environment
variable `TBO_SECRETS_DIR`, by default `%USERPROFILE%\tbo-secrets` on Windows and `~/tbo-secrets` on Linux:

| File | Used by |
|---|---|
| `tbo_key` | `tbo_install.bat`, `TBO-VDS.bat` (SSH private key for the servers; required) |
| `my_server.txt` | `tbo_install.bat`, `TBO-VDS.bat` (asked once and saved here if missing) |
| `servers.txt` | `tbo_install.bat` (other people's servers; created when you add one) |
| `.env` | the bot and its tools (`run_all.py`, `bot.py`, `panic.py`, `check_setup.py`, `report.py`); template: `cryptobot/.env.example` |

On a server set up by `vds_setup.sh` the bot keeps its own `.env` in its bot folder; it is used when the secrets folder has none.

## Common commands (from the repo root)

```
python research/crypto/core/build_trades.py v30         # rebuild the trade list every page uses (v3.0 rules, botsim's default)
python research/crypto/pages/make_trades_html.py        # rebuild a page (any make_*.py)
python research/crypto/core/three_months.py             # what 3 months / 2 years can look like
python cryptobot/dev/test_bot_sim.py BTCUSDT 2024-01-01 2025-01-01   # the bot vs the backtest on a simulated exchange
python cryptobot/dev/test_panic_sim.py                  # the panic sleeve vs the research on a simulated exchange
python research/crypto/pages/make_panic_html.py         # reports/panic.html
python cryptobot/check_setup.py                         # before going live: keys, account, sizes, cap
```
Research needs `pip install -r research/requirements.txt`; the bot only `cryptobot/requirements.txt`.
