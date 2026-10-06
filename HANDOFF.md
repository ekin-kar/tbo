# Crypto (Binance futures) - Oct 2026

The prop-firm work below is history. The user now trades **Binance USD-M futures** with their own bots.
Data: `data/BTCUSDT_1m_2020_2026_part*.parquet`, `data/ETHUSDT_...` (Binance 1m, 2020-01 .. 2026-09).
**BTC bot = TBO v2.0** (`cryptobot/`, see `cryptobot/README.md`): 4h 20-candle breakout, long AND short with the
daily EMA50 (side + 5-day slope), no weekend orders, SL 1.0 ATR, breakeven at +1.5R, max hold 120 h, 2% risk
($1k account). Found by walk-forward (`research/crypto/wf_*.py`): 2022-26 out of sample 3.3%/month at 2% risk
vs 2.0% for v1.0; ETH (untouched) +178R vs +88R. User wants ~8-9%/month: told it is not realistic.
(v1.0 = long only, SL 1.5 ATR, trail exit; holdout 2024..2026 PF 1.66.) Research: `research/crypto/` (`common.py` costs/split, `families.py`, `scan1.py` grids,
`bench.py` random entries, `holdout.py`). Dev = 2020-03..2023, holdout = 2024..2026-09 (already used once
for TBO). Tested and rejected on BTC dev: hourly VOLC (-140R), RSI(2) dip-buying (-123R, costs), hourly
seasonality (edges < costs). Williams volatility breakout: long-only works mildly, weaker than TBO.
Round 2 (user wanted daily, two-sided trades): session breakouts, 1h breakouts, mean reversion, pullbacks,
always-in momentum all fail after fees on BTC (`families2.py`, `holdout2.py`). Next: ETH bot (v2 rules +178R on ETH).

---

# Trading handoff (v8, 5 Oct 2026)

Two cTrader bots trade prop-firm accounts: **PDAYT on gold** and **VOLC on USDJPY**. **v7 = v6 + risk scaling below the starting
balance** (new bot versions GoldPDay v1.4 / JpyVolContraction v5.5, settings for every account, plan and statistics pages rebuilt with
it) + the October 2026 research (eight markets and ~5,000 strategy variants tested, nothing new adopted; see section 4).
The trading rules of both bots are **unchanged** from v6: only the position size changes when an account is below its start.
**v8 = v7 + the first live week's fixes and the funded plans** (list below).
Upload this zip plus the data files (section 7) to a new chat and ask Claude to read this file first.

**What changed in v8 (4-5 Oct 2026):**
- **GoldPDay v1.5:** a 2-second reconnect made cTrader reload only recent history (133 days -> 48, in a test 4), so the trend filter
  skipped the day (5 Oct). v1.5 reloads the m1 history at order time when it is short and checks again; the trend filter uses m1
  bars only (h1 fallback removed). Tested live with `extras/HistoryReloadTest.cs` (no orders): 129 -> 4 days after a 47-s drop -> reload -> 129.
  Trades unchanged. JpyVolContraction stays v5.5.
- **Funded settings:** Funding Pips funded 0.5 / 0.6 with the same risk scaling as the challenge (full to -4%, min 0.3x): funded
  accounts lost in year 1 1.4% instead of 8.5% (10y), payouts about the same. FundedHive Low funded = the ladder + risk scaling from
  the start, no manual B-book cuts: lost 2.6% instead of 7.4% (10y funded table), same payouts. The model repays the fee / B-book
  debt at once from any profit above the start (FundedHive: the balance stays at the start until the debt is 0; corrected 5 Oct). Settings files for every level in
  `clibots/funded/` and `cloudbots/*_funded/` (`cloudbots/FUNDED_README.txt`). FundedHive **Moderate dropped**.
- **Launcher (`run-bot.ps1`, `start-bots.bat`):** tidy console (header, time column, settings in two columns, wrapped lines),
  start-up checks (BUILD OK / OLD BUILD for GoldPDay < 1.5 or JpyVolContraction < 5.5, SCALING ON / OFF), repeated lines hidden,
  a cTrader started without internet (endless reconnect spam) is stopped after 30 s and retried, first restart after 5 s, then once
  a minute if it keeps failing; drops while running are left to cTrader ("lost ... restored").
- **Pages** rebuilt (funded numbers, Low only, v1.5). Research: dropped-market scripts and data removed (git history); tests of the
  daily stop (1.5% kept; 1.6% optional), loss-count rules (rejected), the user's cat3 bot (curve-fitted) are in the git history only.
- **Restart caveat (not fixed, by choice):** a bot restarted during the day rebuilds the day's start from closed trades, so open profit
  at the reset (USDJPY held over 21:00 UTC) is missing from its daily-stop level; check the firm dashboard after such a restart.

---

## 1. The bots (live)

| | Gold: `cloudbots/GoldPDay.cs` (PDAYT, **v1.5**: v1.4 + reloads its m1 history at order time if a reconnect shortened it; trend filter from m1 only) | USDJPY: `cloudbots/JpyVolContraction.cs` (VOLC, **v5.5**) |
|---|---|---|
| Idea | Breakout of the previous day's high/low, only in the direction of the daily trend | Breakout after volatility contracts |
| Entry | **01:15 UTC** (04:15 Turkey): one stop order at yesterday's high (buy) or low (sell), valid until 20:00 UTC | Each hour: if ATR14(h1) < 0.8 x ATR100 -> stop orders at the 10-candle high and low, valid 24h |
| Trend filter | Only the side agreeing with yesterday's close vs the **daily EMA40** | - |
| Stop / target | 2.0 x ATR14 (15-min, exponential) / **2R** | 1.5 x ATR14 (1-hour) / **2.5R** |
| Exit | stop, target, or flat 20:00 UTC (23:00 Turkey); max 1 trade/day; never overnight | stop, target, **closed after 20 hours**, or flat Friday 20:00 UTC (23:00 Turkey) |
| Other | Warm-up 120 days; "Max actual risk %" 0.9 (skips a day when even the minimum lot would risk more) | No orders 20:30-23:00 UTC; one position at a time; cancels resting orders while a position is open; hourly status line |
| **New in v7** | **Risk scaling** (group "Risk scaling", off by default), v1.4 | **Risk scaling** (same), v5.5 |

**Risk scaling (v1.4 / v5.5).** Four parameters: `StartBalance` (0 = off), `FloorPercent` (the firm's fail level as % of the start:
88 = 12% max loss, 95 = 5%, 94 = 6%), `ShrinkFromPercent` and `MinScale`. Full risk while the balance is at or above the shrink level
= `StartBalance x (1 - ShrinkFromPercent/100)`. Below it the risk is multiplied by `max(MinScale, (balance - floor) / (level - floor))`,
so it shrinks with the room left to the firm's static floor. Funding Pips 10k (floor 8,800, shrink from 4%, MinScale 0.3):
9,600 or more -> 1.0x, 9,400 -> 0.75x, 9,200 -> 0.5x, 9,040 or less -> 0.3x. FundedHive (shrink from 0%, floor 95%, MinScale 0.3):
200k: 198k -> 0.8x, 196k -> 0.6x, 193k or less -> 0.3x. (v1.3 / v5.4 = the same without `ShrinkFromPercent`.) Each bot sizes
from the same account balance, so both scale together. The bots print the scaling status at start and a line whenever a trade is
sized down. **There is no step-up above the start** (tested, not worth it: section 4).

Both bots run on **UTC** (Server.Time = UTC), so summer/winter time never moves their schedule; Turkey is UTC+3 all year.
Server-side SL/TP, restart-safe, account-wide daily loss stop: **1.5%**.

**Performance** (backtest at current costs, 2016 - 18 Sep 2026, USDJPY with the 20-hour max hold; interactive version in
`stats/fundingpips_statistics.html` / `stats/fundedhive_statistics.html`):

| | Trades | Win rate | Profit factor | Net | Max DD |
|---|---|---|---|---|---|
| Gold, full history | 1,488 | 41.1% | 1.25 | +228R | 35R |
| USDJPY, full history | 1,617 | 36.7% | 1.22 | +224R | 22R |
| Combined, full history | 3,105 | 38.8% | 1.24 | +452R | 31R |
| Combined, last 3 years | 932 | 40.9% | 1.32 | +176R | 13R |

Live check (Funding Pips cTrader tick backtest, Feb 2024 - Sep 2026, gold): 377 of 380 engine trades on the same day, 375 same
direction, 95% same outcome; cTrader about 14% below the engine. Entry slippage median $0.12.

## 2. Accounts and settings (agreed 4 Oct 2026)

| Account | Firm rules | Gold | USDJPY | Risk scaling (cbotset) | Daily stop / reset | Expected (live-equity simulator) |
|---|---|---|---|---|---|---|
| **Funding Pips 1-Step Flex 10k** (#***REMOVED***, cTrader CLI, Swing add-on), challenge | +12% target, **12% static** floor (8,800), 2% daily from max(bal, eq) at 21:00 UTC, no per-trade limit | **0.7%** | **0.9%** | StartBalance 10000, FloorPercent 88, ShrinkFromPercent **4**, MinScale **0.3** | 1.5% / **21** | fail 1.3 / 1.5 / 5.7 / 2.4% (2y / 3y / 10y / real order), median 2.4 / 2.9 / 3.2 / 3.3 months |
| Funding Pips, **once funded** | same floor/daily; bi-weekly payouts 80% | 0.5% | 0.6% | StartBalance 10000, FloorPercent 88, ShrinkFromPercent **4**, MinScale **0.3** (as in the challenge; decided 5 Oct 2026) | 1.5% / 21 | keep **$100** (1%) in the account: request a payout at $10,200+, withdraw above $10,100 (decided 5 Oct 2026: with a 12% floor a bigger buffer only cost money; `plans/fundingpips_plan.html`) |
| **FundedHive 200k 1-step Low** (~208k, +4%), evaluation | 1%/trade, 2% daily, **5% static** max loss (190k), +10% target | **0.4%** (lowered from 0.5) | **0.5%** (lowered from 0.6) | StartBalance 200000, FloorPercent 95, ShrinkFromPercent 0, MinScale **0.3** | 1.5% / 0 | from +4%: fail 0.2 / 0.2 / 2.5%, median 1.9 / 2.1 / 2.5 months |
| **FundedHive 10k Low** | as 200k Low | 0.4% | 0.5% | StartBalance 10000, FloorPercent 95, ShrinkFromPercent 0, MinScale 0.3 | 1.5% / 0 | |
| FundedHive Low, **new** account (any size) | as 200k Low | 0.4% | 0.5% | StartBalance = size, FloorPercent 95, ShrinkFromPercent 0, MinScale 0.3 | 1.5% / 0 | fail 2.0 / 1.8 / 9.6%, median 3.7 / 4.2 / 5.1 months (fixed 0.4/0.5: fail 12.7 / 11.4 / 21.4%) |
| FundedHive Low, **funded** | + fee (1%) from profits, B book below 99% (flat 1% debt) | ladder | ladder | StartBalance = funded size, FloorPercent 95, ShrinkFromPercent 0, MinScale 0.3 (decided 5 Oct 2026); **no manual B-book cuts** | 1.5% / 0 | ladder by buffer (debt repaid first): 0.25/0.35, from +1% 0.30/0.40, +2% 0.40/0.50, +4% 0.50/0.60 (`plans/fundedhive_plan.html`): same payouts as the ladder alone, funded accounts lost 2.6% instead of 7.4% (10y) |

Settings files: `clibots/` = Funding Pips 10k (CLI); `cloudbots/FundedHive_200k_Low/`, `cloudbots/FundedHive_10k_Low/`.
Funded settings files (5 Oct 2026): `clibots/funded/` (Funding Pips, copy over the challenge files when funded); `cloudbots/FundedHive_200k_Low_funded/` and `cloudbots/FundedHive_10k_Low_funded/`, one sub-folder per ladder level (`1_start`, `2_buffer_1pct`, `3_buffer_2pct`, `4_buffer_4pct`), explained in `cloudbots/FUNDED_README.txt`.
**After passing a challenge, set `StartBalance` to 0** (scaling was only tested for challenges/evaluations).
FundedHive only allows the same trade on one funded account at a time, so FundedHive stays at the one 200k account; growth goes
through Funding Pips (up to $400k allocation). Several Funding Pips accounts with the same bots fail or pass together: start
challenges a few weeks apart instead of buying several at once.

**Documents:** `plans/fundingpips_plan.html` (Funding Pips 10k: pass dates, equity paths, payouts, challenge and funded risk options
incl. the scaling rows) and `plans/fundedhive_plan.html` (FundedHive Low (Moderate dropped 5 Oct 2026): pass dates, payouts, risk options incl. scaling,
already-in-profit table, funded ladders, B book). Both use the live-equity simulators with the risk scaling built in.

**Open checks:** (1) ask Funding Pips whether the daily reset moves to 22:00 UTC in winter (if yes: `DailyResetHourUtc` 22 in both
cbotsets on the weekend of 24-25 Oct 2026, back to 21 on 27-28 Mar 2027); (2) confirm FundedHive's rules: static (not trailing)
5% max loss, reset 00:00 UTC, B-book mechanics.

## 3. How the settings were found

- **Method:** fixed data split (tuning on 2019-2022 only, one-shot tests on 2016-18, 2023-24, 2025-26), plateau centres rather than
  best cells, comparison with random entries, long/short and year-by-year checks, costs at the broker's real level (plus a 2x stress
  test). The engine was verified against a cTrader tick backtest (226 of 226 trades matched on day and direction).
- **Gold:** a daily trend filter (EMA40) halved the drawdown of the original 07:00 breakout; a scan of every order time 00:00-08:00
  found a broad strong area at 01:00-01:45 UTC (Asian-session breakouts), 01:15 is its centre. Stop 2.0 ATR / target 2R re-checked.
- **USDJPY:** VOLC's parameters form a broad plateau; "Close before weekend" after a weekend gap cost -8R in 2017; v5.3 max hold 20h
  (12-24h tested, 20h best: drawdown 27R -> 22R, +30R).
- **Simulators:** `research/fundingpips_sim.py` (and the scripts built on it) is minute-level on live equity: every open trade's
  floating P&L, the daily baseline max(balance, equity) at the firm's reset, the static floor, the bots' daily stop. Paths are random
  4-week blocks of the real trades (2y / 3y / 10y windows) plus a fresh account started every week 2016-2024 on the real order.
  **v7:** `fundingpips_sim.sim` (+ `boot` / `rolling`), `fundingpips_report.phase`, `fundedhive_sim.evaluate` take `minm` (risk-scaling
  minimum) and `dz` (shrink from, fraction); `fundedhive_report.phase` takes `minm`.
- **Risk scaling (Oct 2026):** a per-bot "trade smaller after a losing streak" filter does NOT work (streak lengths are random; USDJPY's
  bad stretches are followed by BETTER trades). Account-level scaling by the room left to the static floor does: it cuts failures by
  more than half. Grids (live equity) over base risk x minimum (0.3-0.75) per firm; judge speed on 2-3 years, safety on 10 years.
  Shrinking alone trades a little time for far fewer failed (paid) attempts; starting slightly higher with shrinking (Funding Pips
  0.7/0.9) is both safer and about as fast as the old fixed setting. With a tight floor (5-6%) a low minimum (0.3x) is best.
  Shape (`research/scans/shape_grid.py`): on Funding Pips (12% room) waiting until -4% and then shrinking harder (min 0.3x) beats
  shrinking from the start (min 0.6x): fail 1.3 / 1.5 / 5.7 / 2.4% vs 1.8 / 1.9 / 6.4 / 0.7%, median 2.4 / 2.9 / 3.2 / 3.3 vs 2.6 / 3.1 /
  3.5 / 3.9 months, and it keeps more profit after a dip (last 6 months +9.5% vs +5.8%, no scaling +13.6%). On FundedHive (5% room)
  a delayed start adds failures: shrink from the start. A "curve" (room squared) shrinks more everywhere: fewest failures, slowest.
  Step-up above the start (single jump 1.25x/1.5x at +1/2/4/6%, or a ladder to 1.25x/1.5x by +4/6/8%) gains ~0.3 months on the median
  for 1-2 points more failures in a bad year: not adopted.

## 4. Known not to work (do not redo without a new idea)

From v6:
- **Gold, quiet markets:** mean reversion, fading previous-day levels or failed breaks, London-fix fade, London false breakouts,
  momentum continuation. **Gold variations:** several trades per day, intraday trend / volatility / NR-day filters, London-range
  breakout into New York. **USDJPY:** re-tuned VOLC, breakeven stops, trend filter, blocking US-data hours; Gotobi Tokyo-fix (watchlist).
- **Other markets (v6):** EURUSD/GBPUSD failed their holdout; Nasdaq, S&P, EURJPY, XAGUSD nothing robust; BTC 14 ideas, nothing survived.

October 2026 (scripts in `research/scans/`, raw numbers in `research/results/`):
- **Gold + USDJPY new strategies** (`oct2026_b*.py`): USDJPY previous-day breakout + EMA40 at 00:00-07:00 (2023-26 negative); VOLC on
  gold and VOLC h4/m30 (flat); daily channel trend-following (gold: ~6 trades/year, nearly all from 2025); previous-week breakouts.
- **Gold exits / variants** (`improve_*.py`, exact exit simulator `improve_lab.py`): flat 17-19 UTC, breakeven 1.0/1.5R, TP 2.5/3R,
  scale-out 50% at 1-1.5R, time-decay exit, breakout buffer 0.1-0.3 ATR, m15 close confirmation, weekly trend, order cancel time
  09:00-16:00 (cancelling at 11:00-12:30 halves the drawdown but lowers profit by as much: same speed/safety line in the pass sims).
  Far-away orders (`gold_far.py`): on 44% of days PDAYT does not trade; far orders fill rarely but are the BEST trades (never cancel
  them); add-on trades on those days and risk tilts by distance: no gain.
- **Gold session scan** (`gold_sessions.py`, 582 configs): liquidity sweeps (0 of 198 robust), Asia-range breakouts in London/NY,
  session direction: not robust. Only Asian-session breakouts of earlier levels hold -> **ASIAB** (stop orders at yesterday's Asia
  00:00-07:00 high/low placed 00:00 UTC, SL 2 ATR, TP 3R, flat 20:00): +147R, PF 1.33, robust, daily corr 0.16 with PDAYT. But on a
  NETTING account (one gold position) merged with PDAYT it adds no pass speed, and replacing PDAYT with it is slower (`gold_netting*.py`,
  `asiab_replace.py`). Not adopted.
- **USDJPY variants**: scale-out, time-decay exit, buffers: worse; order life 6/12h: same. Same-dollar exposure halving (gold long +
  USDJPY short open together, 9% of trades): portfolio DD 22% -> 17% but slower passing: optional only.
- **EURUSD / EURJPY** (scripts and data removed from the repo; in the git history): every intraday idea loses, mostly before costs;
  3,492-combination window scan: 3 survivors, checkerboard on London/NY time -> chance. VOLC on 4-hour candles: small (+4R/year).
- **AUDUSD** (removed, in the git history): breakouts, Tokyo box, VOLC, trend, mean reversion, fades: all negative.
- **Nasdaq / S&P** (removed, in the git history): the user's **NasTrend** (first-hour trend, 10:30 NY entry, BE 1R, exit 15:30): PF 1.41,
  +275R, but the top 2% of trades make +229R (without them +37R; negative since Apr 2025) and the Funding Pips tick test was flat from
  Sep 2024 -> not adopted. Last-30-minute momentum and overnight long: no.
- **XAGUSD:** broker spreads (FundedHive $0.03-0.04, Funding Pips $0.10) cost 0.1-0.45R per trade vs 0.006R on gold -> untradeable.
- **Account choice / risk** (`acct_speed.py`, `fp_highrisk.py`, `scaling_grid.py`, `fp3_grid.py`): closed-trade sims overstate high-risk
  pass rates by 15-25 points (the 2% daily rule on live equity); the Funding Pips 3% daily option is faster at the same risk
  (1.0/1.25, stop 2.5%: 2.4 months, fail 15%) - not bought to keep one account type.
- **USDJPY losing-streak rule** ("after N losses in a row, x risk until a win", on top of the risk scaling; `research/scans/streak_rule.py`
  -> `results/streak_rule.csv`, live equity). Closed trades looked promising (USDJPY trades after 3-5 losses in a row earn ~0R; after 4
  losses -> 0.5x: same R, DD 21.9R -> 16.8R; gold: no pattern). With equity and the scaling already on, it sits on the same speed/safety
  line as simply lowering risk: Funding Pips after 4 -> 0.5x: fail 1.1 / 1.5 / 5.9 / 2.4% -> 0.7 / 0.8 / 4.6 / 0.9% (2y / 3y / 10y / real),
  median +0.15-0.25 months, expected months incl. retries slightly longer; FundedHive Low: 2.0 / 1.8 / 9.6 / 4.0% -> 1.4 / 1.0 / 7.5 /
  2.9%, median +0.1-0.3 months. Not adopted (no free gain, extra bot state).
- **Position sizing by conditions** (`research/scans/size_features.py`): USDJPY by entry hour, weekday, quietness (ATR14/ATR100),
  volatility regime, distance from the daily EMA40, tick volume before entry; gold by volatility regime, EMA40 distance, tick volume
  before entry, weekday, fill hour. No condition ranks trades the same way in all four periods; the one bucket that looked consistent
  (USDJPY 25-50% volatility percentile) disappears with other bucket edges -> curve fitting, nothing adopted. (Gold fills 12-16 UTC
  are weak in every period, as found before; cancelling those orders did not speed up passing.)
- **Parked:** skipping gold days with low pre-session tick volume (chosen on already-used data).

## 5. Open items

1. **Build GoldPDay v1.5 / JpyVolContraction v5.5** in the cTrader app from `cloudbots/*.cs` (both compile with 0 errors / 0 warnings
   against cTrader.Automate) and copy the `.algo` files to `C:\bots`. A FundedHive cTrader backtest (Nov 2024 - Oct 2026) matched the
   research engine: 94% / 90% of trades identical, 98% same outcome.
2. Ask Funding Pips (weekend of 24-25 Oct) whether the daily reset moves to 22:00 UTC in winter (then `DailyResetHourUtc` 22).
3. After passing a challenge: load the funded settings files (`clibots/funded/`, `cloudbots/*_funded/1_start/`), not StartBalance 0.
4. If the bots were off over 20:00 UTC and a gold trade is still open next morning, close it by hand before 01:15 UTC.
5. Possible next research: JP225 (the last Asian-session market with a reason; log its spread first).

## 6. Running the bots live (cTrader CLI, Windows)

- Folder `C:\bots`: `GoldPDay.algo`, `JpyVolContraction.algo` (built from `cloudbots/`), the two cbotsets from `clibots/`,
  `pw.pwd` (cTrader ID password only), `start-bots.bat` and `run-bot.ps1` from `clibots/`.
- Cloud / app accounts (FundedHive): the same `.cs` files, settings from `cloudbots/FundedHive_200k_Low/` or `FundedHive_10k_Low/`.
- `start-bots.bat` opens one Windows Terminal window, gold left / USDJPY right; `run-bot.ps1` colours the log, writes
  `C:\bots\logs\<BOT>_<date>.log` and restarts a bot 5 s after it exits (then once a minute if it keeps failing). Account and cTrader ID are parameters at the top of
  `run-bot.ps1` (default account ***REMOVED***). First log lines must show `v1.5` / `v5.5` and `Risk scaling below start balance: start
  10000, floor 88%, shrink from 4% below start, min 0.3x, now 1.00x` (or less if the account is below 9,600).
- Before a new account: run `extras/LiveSafetyTest.cs` once per symbol via the CLI (13/13 PASS on Funding Pips).
- PC: never sleep, no automatic Windows Update restarts, auto-login + startup shortcut to `start-bots.bat`.
  Avoid restarting (Turkey time): 04:00-04:30, 23:00-23:45, Friday 22:45-23:15, and the :00 minute.

## 7. Research environment

1. Python 3.10+, `pip install -r research/requirements.txt` (numpy, pandas, numba).
2. Data in a `data` folder next to `research/` (or `TRADING_DATA`): `XAUUSD_M1.m1pack`, `USDJPY_M1.m1pack`,
   `XAUUSD_DUKA_BID/ASK.m1pack`, `USDJPY_DUKA_BID/ASK.m1pack`, `XAUUSD_SPREAD.csv`, `USDJPY_SPREAD.csv`, all in `data/` on the
   GitHub repo (`ekin-kar/trade2`). The EURUSD / EURJPY / AUDUSD / Nasdaq / S&P data used in October 2026 were removed (git history).
3. Pack new CSVs with `extras/pack_dukascopy.py` (dukascopy-node bid/ask CSVs in `./download` and cTrader DataExporter
   `*_M1*.csv` on the Desktop -> `claude_upload_duka/*.m1pack`, each verified).
4. `python research/run_live.py` backtests both bots (first run builds `cache/`); `python -m engine.test_engine` (from `research/`).
5. Pages: `fundingpips_sim.py` (risk table) + `fundingpips_report.py` + `make_plan_html.py` -> `plans/fundingpips_plan.html`;
   `fundedhive_sim.py` (risk tables) + `fh_report_parallel.py` (or `fundedhive_report.py`) + `make_fundedhive_html.py` ->
   `plans/fundedhive_plan.html`; `make_stats_html.py` -> `stats/*.html`. Raw results in `research/results/`.
6. `research/scans/` = the October 2026 research scripts (run from the repo root, e.g. `python research/scans/gold_sessions.py`).
   Note: the grid scripts that patch the simulators (`scaling_grid.py`, `ladder_grid.py`, ...) were written against the v6 simulator
   source; the v7 simulators have the scaling built in (`minm`), so use those for new runs.

## 8. Files

- `cloudbots/` - **the live bots** `GoldPDay.cs` (v1.5), `JpyVolContraction.cs` (v5.5); evaluation settings `FundedHive_200k_Low/`,
  `FundedHive_10k_Low/`; funded settings `FundedHive_200k_Low_funded/`, `FundedHive_10k_Low_funded/` (one folder per ladder level,
  see `FUNDED_README.txt`).
- `clibots/` - Funding Pips 10k (CLI): the two challenge cbotsets, `funded/` (funded cbotsets + README), `start-bots.bat`,
  `run-bot.ps1`, `pw.pwd`. Build the `.algo` files yourself (or use the ones added to the zip by the user).
- `extras/` - `pack_dukascopy.py` (data packer), `LiveSafetyTest.cs`, `HistoryReloadTest.cs` (+ cbotset, `test-history.bat`: no-order
  test of the v1.5 history reload), `SpreadLogger.cs`, `ApexDataExporterV2.cs`, SignalRelay (Telegram, unused).
- `plans/` - `fundingpips_plan.html`, `fundedhive_plan.html` (rebuilt for v8: funded with risk scaling, Low only).
  `accounts_outlook.html` (5 Oct 2026): FundedHive 200k / 10k and Funding Pips 10k / 50k started fresh on the same simulated market:
  pass, fail, first payout, payout per month, an 18-month chart (`research/scans/income_plan.py` + `research/make_outlook_html.py`).
- `stats/` - `fundingpips_statistics.html`, `fundedhive_statistics.html` (v8: "Shrink from (% below start)" and "Shrink: min
  risk x" boxes run the bots' risk scaling in every percent figure and in the prop account check; min 1 = off).
- `research/` - engine, simulators, page builders, `scans/` (Oct 2026), `results/`.
