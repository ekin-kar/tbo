# Crypto (Binance futures) - Oct 2026

**Layout (Oct 2026 cleanup):** research scripts are in `research/crypto/core/` (library), `research/crypto/pages/` (page generators + templates) and `research/crypto/studies/` (experiments); the bot's developer checks in `cryptobot/dev/`. Script names below are unchanged; see the top-level `README.md` for what is where.

**CURRENT LIVE SETTINGS (from 12 Oct 2026, $300 start):** TBO v2.6 (4h n20 breakout, 1 ATR stop, BE +1.5R, lock +5R -> +1.5R, 120 h, OI filter, shorts x0.5) on BTC/ETH/BNB/SOL/ADA; risk ladder in cryptobot/portfolio.json **BTC 6 / ETH 4 / alts 0.83% under $1k, 5 / 3.3 / 0.83% to $10k, 2.5 / 1.7 / 0.42% above**, open-risk cap 1.1x the BTC risk (6.6 / 5.5 / 2.75%), BTC exempt but counted. **v2.8 (Oct 2026): + OI-low filter (no order while OI is in the lowest 20% of its 90 days), see the last entry.** **v2.7 (Oct 2026): + panic sleeve** (`cryptobot/panic.py`, Binance sub-account, see the last section): long after a forced-liquidation flush (4 h: price <= -1.5x normal move, OI <= -12%, premium z <= -1), TP +3 ATR(1h), stop -4 ATR (max -20%) -> entry at +2 ATR, 12 h; 3 units/event; bot and sleeve size on main + sub. Older sections below describe how it got here (their ladder numbers are the old ones).

**Live setup (v2.5 = v2.4 + risk ladder and open-risk cap in portfolio.json, see the v2.5 section at the end; v2.4 = v2.3 + open-interest filter: no new order while OI (USD) is down >= 3% vs 72 h earlier; bot fetches /futures/data/openInterestHist; parity bot vs replay 15 of 16 coin-half-years exact, DOGE 2022H2 differs by the backtest's pessimistic fill-minute stop):** `cryptobot/run_all.py` (all coins, restarts), `check_setup.py` (pre-flight, no orders), `.env`
(keys, optional Telegram), risk from portfolio.json's ladder (configs' risk_pct 5 / 2.5 / 0.83 only a fallback; DOGE dropped, BNB + SOL added Oct 2026 on recent strength; size cap 8x, BTC 12x, leverage 20x, BTC 25x), shorts x0.5; step-by-step
guide in `cryptobot/README.md` ("GO LIVE"). Pages: all in `reports/` (rebuilt by research/crypto/make_*.py from the live settings; robustness page retired).

The repo is crypto only (the old prop-firm gold/USDJPY work was removed Oct 2026). The user trades **Binance USD-M futures** with their own bots.
Data: `data/BTCUSDT_1m_2020_2026_part*.parquet`, `data/ETHUSDT_...` (Binance 1m, 2020-01 .. 2026-09).
**BTC bot = TBO v2.1** (v2.0 + no new order when the daily close is > 4 daily ATR from the daily EMA50) (`cryptobot/`, see `cryptobot/README.md`): 4h 20-candle breakout, long AND short with the
daily EMA50 (side + 5-day slope), no weekend orders, SL 1.0 ATR, breakeven at +1.5R, max hold 120 h, 2% risk
($1k account). Found by walk-forward (`research/crypto/wf_*.py`): 2022-26 out of sample 3.3%/month at 2% risk
vs 2.0% for v1.0; ETH (untouched) +178R vs +88R. User wants ~8-9%/month: told it is not realistic. Round 3 (`wf2.py`): finer core tuning = noise, v2 core kept.
(v1.0 = long only, SL 1.5 ATR, trail exit; holdout 2024..2026 PF 1.66.) Research: `research/crypto/` (`common.py` costs/split, `families.py`, `scan1.py` grids,
`bench.py` random entries, `holdout.py`). Dev = 2020-03..2023, holdout = 2024..2026-09 (already used once
for TBO). Tested and rejected on BTC dev: hourly VOLC (-140R), RSI(2) dip-buying (-123R, costs), hourly
seasonality (edges < costs). Williams volatility breakout: long-only works mildly, weaker than TBO.
Second-strategy search (Oct 2026, user wants a smoother equity curve; `families3.py`, `pairs.py`, `weekend_scan.py`,
`gold_tbo.py`): failed-breakout fade (864 settings, none pass), crash/spike fade (432, all negative), ETH/BTC ratio
mean reversion (384, all negative: the ratio trends), daily reversal (noise), "CME gap fill" (gaps fill LESS than a
same-distance baseline; weekend moves CONTINUE: strong 2020-23, gone 2024-26 -> rejected), TBO on gold with
Binance XAUUSDT fees (stop 0.4% of price, fees 0.3R/trade: -81R 2020-24). Nothing adopted.
1/5/15-minute scalping (`families4.py`, `scan4.py`, BTC+ETH dev, maker/taker fees): Bollinger fade, VWAP reversion
(both lose even BEFORE fees), RSI(2/6) fade, EMA cross, squeeze breakout, 5/15m channel: momentum families are
profitable before fees on both coins (EMA 199/288, squeeze 96/128, channel 130/144) but 0 survive fees except 3
weak 15m channel settings (= TBO's idea on a smaller timeframe, weaker). Nothing adopted.
Feature study (`feature_study.py`, daily, 24 conditions, robust = same sign BTC+ETH in 2020-21 AND 2022-23):
1-30 day momentum, 20-day range position / EMA20 distance (continuation) and 7d/90d volatility ratio (calm ->
better, wild -> worse) are the only consistent ones; weekday, volume, trade count, average trade size, wicks,
streaks, long-term highs/EMA200 are not. Daily score strategy from them (`score_strat.py`): MAR ~0.5-0.65 on dev,
long side only -> rejected (holdout not used). Vol-ratio filter on TBO (`vr_max`): within noise -> not adopted.
EMA 9/21 retest (`families4.ema_retest`, 5/15m setup, 1h/4h trend, maker limit at the EMA, 1h-ATR stop, maker TP;
768 settings): before fees +100R BTC / +140R ETH per ~2,000 trades (0.05R/trade), after fees 0 settings profitable
on both coins (fees ~0.07R/trade). TBO waiting time: one coin median 35 d to a new equity high, BTC+ETH 15 d.
10 TBO improvement ideas (`ideas10.py`, BTC+ETH, walk-forward 2022-26 pooled): add to winners, partial TP, hold
>xR winners longer, close dead trades, close-confirmed entry, swing stop, efficiency-ratio filter, size tilt, BTC/ETH
confirmation, own rules for shorts -> none beats v2.1 out of sample on both coins. Closest: hold winners above +6R
at day 5 up to 10 days (picked every year; BTC MAR 2.90 -> 3.14, ETH 1.65 -> 1.66): marginal, not adopted yet.
Entry ideas (`ideas_entry.py`): channel 5/10/15 (DD 12 -> 18-30R), same 80h window on 1h/2h candles with the
4h stop (~same, slightly worse), scale-in half at n=5/10/15 (worse), limit retest of the broken level (the best
breakouts never come back: 57-115R vs 269R). None picked by the walk-forward in any year.
12 coins (Oct 2026, `portfolio.py`, `portfolio_sim.py`, `portfolio_sets.py`): TBO v2.1 untouched; more coins = more
trades but not better return/DD (crypto drawdowns coincide; alts weaker). Chosen set BTC+ETH+DOGE+ADA (2020-23
return/DD >= 1), 0.5-0.6% risk each: same return/DD as BTC+ETH at 1%, 2x trades, shorter flat periods.
Winners vs losers (`trade_features.py`, `sizing_rules.py`): only shorts-at-half-size improves both periods ->
TBO v2.2 (`short_risk_mult` 0.5); configs 4 coins at 0.75% (shorts 0.375%): 2020-26 6.0%/mo DD 27%, 2024-26 4.5%/mo DD 20%.
Deep winners-vs-losers study (Oct 2026, `loser_study.py` 85 measurements per trade, `loser_eval.py`, `filter_test.py`,
`filter_rand.py`): single conditions pass both periods at about chance rate (2.3% vs 2.0% random); the best 2020-23 pairs
fail 2024-26 (median x0.72); gradient boosting AUC 0.49-0.53 (= coin flip). Some 'tired setup' conditions are consistent
across sub-periods and coins (8/8 for 7.6% of conditions vs 2.6% random): level touched 6+ times, very quiet last 10
candles (std10 <= 0.37 ATR). Inside the engine (skip the order) they remove only ~5-9% of trades (the breakout fills a
candle later) and add ~+0.6%/month with ~4 points less DD at 2x risk, above the random-skip 90th percentile, but they were
picked using all years -> not adopted; re-check on live/new data after 6-12 months.
10 ideas, round 3 (Oct 2026; `tradesim.py` minute replay = engine on 1472/1474 trades, `ideas_v3.py`, `ideas_v3b.py`):
partial take-profit (1/3 at +1R) is the only near-neutral one: 2024-26 net/DD x0.99 (2020-23 x0.83), trades in profit 46%
vs 16%, longest full-loss streak 8 vs 12; at 1.3x risk about the same money and DD as now ($8.2k vs $8.7k from $200
2024-26). Rejected: earlier breakeven (all worse out of sample), failed-breakout exit (x0.37-1.0), re-entry (x0.43-0.66),
adding at +1R/+2R (2024-26 x0.49-0.61), trend-strength sizing (none beats random sizing in both periods), several channel
lengths (2020-23 better, 2024-26 x0.80-0.84). Ideas 6, 7, 10 need Binance data the cloud cannot reach:
`fetch_binance_extra.py` (run on the user's PC, push data/extra/).
Ideas 6, 7, 10 (data/extra from data.binance.vision; `ideas_v3c.py`, `filter_test2.py`, `filter_test3.py`, `carry.py`):
**open-interest filter works**: skip the order when OI (USD value, Binance metrics) fell over the last 3 days by >= 3%:
2022-23 7.8 -> 10.8%/mo (DD 64 -> 58%), 2024-26 12.0 -> 13.8%/mo (DD 49 -> 44%), $200 2024-26 $8.3k -> $14.0k at 2x risk;
24 of 32 lookback/threshold/measure settings beat the bot in both periods; random skipping (25 seeds) never got there
(90th pct 9.7 / 12.3%/mo). Trades -22%, win rate barely changes (15.5 -> 16.6%), avg R per trade +0.35 -> +0.50.
OI data only from Dec 2021 (2020-21 untested). Taker buy share: weaker, near chance. Funding filter: nothing.
Funding carry: ~0.4%/month 2024-26 on capital, 1-3%/yr in 2025-26 -> not worth it at $200.
5 more Binance-data ideas on top of v2.4 (Oct 2026, `ideas_v4.py`; spot 4h + premium index 1h added to data/extra):
OI-falling exit during a trade (x0.06-1.06, worse or flat), bigger size when OI rises (0 of 18 settings >10% better in
both periods), spot-led vs futures-led (0 of 36; luck 1.3%), futures premium (0 of 24), top traders vs crowd (0 of 36),
any of them as size x1.5 (0 of 78). Nothing adopted; v2.4 stays.
Fakeout detection on v2.4 (Oct 2026, `ideas_v5.py`, 1m taker volume via `fetch_taker_1m.py` into cache/, not in git):
RSI/MACD divergence vs the level candle (0 of 24 filters), other coins not joining (0 of 23; "one other coin near its
break" x1.40 / x1.09 but not monotonic: 0/1/2/3 coins = +0.48/+0.07/+0.28/-0.64R 2020-23), rejected pokes / grinding
under the level (0 of 14), early exits on absorption (0 of 42), trigger-minute trade spike / OI drop after the fill
(0 of 12), gap / spike through the level (0 of 18): none beats base and random exits in both periods. Early exits lose
because most breakouts that stall in the first hour still end as winners. Order book: no history; untestable.
Coins together (Oct 2026, `ideas_v6.py`): per-coin win rate BTC 20.4% (avg +0.92R), ADA 18.3%, ETH 16.7%, DOGE 13.3%.
BTC confirming alt trades (BTC in a trade / entered within 24-48 h / near its own level / 4h trend; skip or size x1.5),
BTC dominance proxy (BTC vs 11-alt index, 7d/30d) and USDT dominance proxy (12-coin market trend): none beats random skips in
both periods. Alt trades with BTC already in the same direction average +0.38R vs +0.20R without, but skipping the others
loses in 2024-26 (x0.87). External dominance data (CoinGecko) is blocked from the cloud.
All 12 coins on v2.4 at 1% risk each from $200 (Oct 2026, `all12.py`, OI metrics downloaded for all 12):
2024-26 %/month BTC 2.47, ETH 1.97, BNB 1.72, TRX 1.39, DOGE 1.08, AVAX 0.94, SOL 0.93, ADA 0.86, XRP 0.69, LINK 0.11,
DOT -0.19, LTC -0.69 (2020-23: BTC 3.56, DOGE 2.98, ADA 2.11, SOL 1.84, ETH 1.82, BNB 1.29 ...). Adding BNB at 1.25% raises
money and drawdown in proportion (return/drop 0.358 -> 0.361, 0.312 -> 0.314) = like more risk, not a better edge;
+BNB+SOL better 2020-23, worse 2024-26. Kept BTC/ETH/DOGE/ADA.
Hedge idea (Oct 2026, `hedge_test.py`): half-size opposite trade opened with every entry (or after -0.5/-0.8R), kept after
a stop-out until its TP (1-3R; stop at its entry), closed when the main trade is +0.5..1.5R: all 20 variants worse than
no hedge (net/drop 2020-23 10.5-20.0 vs 21.5; 2024-26 5.0-13.5 vs 13.6), profit -5..-30%, drops not smaller. Not adopted
(and it would need Binance hedge mode).
Market-neutral cross-sectional study (Oct 2026, `mn_study.py`, `mn_carry.py`; funding/premium/4h taker data for all 12
coins): long top-N / short bottom-N, gross 1x, fees + slippage + funding. Momentum (3-90 d) Sharpe 1.4-1.7 in 2020-23 but
negative 2024-26 -> dead. Reversal, low-vol, OI, taker: no. Funding carry (long low / short high funding, 12 coins):
Sharpe > 0 in both periods for 92% of 140 settings, median 0.69 / 0.75, ~10-16%/yr at 1x, losing years 2020/2022/2025,
corr with TBO 0.02; TBO+carry 1-2x: Sharpe 1.58 -> 1.64-1.68, drawdown not lower. On the 7 coins TBO does not trade
(needed in one-way mode) carry fails (median Sharpe ~0, 2022 -48%). TBO's own daily Sharpe ~1.6 beats every
market-neutral factor; its drawdown is the chosen risk (BTC 2.5% -> worst drop ~25-28%).
Big grid (Oct 2026, `grid_v25.py` 4,320 structures x 5 coins with OI filter; `grid_v25_eval.py`; `grid_v25b.py` 30 filters
x 5 structures): live (4h, n20, ATR 1.0 stop, BE 1.5R, 120 h) ranks 41/4320 on a neighbourhood-smoothed min(dev, holdout)
score; only 4 configs beat it in both periods, none by >10%. 1h/2h/1d clearly worse; 8h (n15-30, ATR 0.75) a sibling plateau,
better 2020-23 (x1.2-1.5) but equal/worse 2024-26 (x0.8-1.05). ATR stops beat %-of-price, channel-width and swing stops;
120 h beats 72/240 h; BE 1-1.5R beats 2R/none. Filters: every RSI/ADX/volume/EMA-length/slope variant is worse on average
(median across structures x0.11-0.97 in 2024-26); OI 168 h -3% helps the live structure (x1.17/x1.18) but hurts the others
(median x0.91/x0.88) -> noise. 4h+8h half/half: x1.16/x1.04 but 83% of 8h trades duplicate 4h ones. No change adopted.
Portfolio sizing rules (Oct 2026, `sizing_v3.py`, compounding account sim, BTC 5% settings, $200): shorts x0.5 stays best
(0/0.25/0.75/1/bear-only all worse in a period); BTC-volatility and account-volatility sizing, drawdown brakes,
same-direction scaling: no better than simply lower risk. **Open-risk cap with shrink** (risk of trades not yet at
breakeven <= cap x equity; a new trade is shrunk to fit, skipped if < 25% would fit) is a smooth plateau 4.5-6.5%, better in
both periods; 5.5% (= 1.1 x BTC risk): 2020-23 x1.03, 2024-26 x1.17 (worst drop 44.8 -> 38.0%, $15.3k -> $14.6k),
2022-26 x1.05; binds on 13% of entries (8% shrunk to ~72%, 5% skipped). **Better: BTC exempt** (BTC trades never shrunk or
skipped, but their open risk still counts against the cap for ETH/alts): 1.1x -> 2020-23 x1.03, 2024-26 x1.23 ($18.0k,
drop 38.0%), 2022-26 x1.08; plateau 0.9-1.1x (x1.22-1.23), fades at 1.3x (x1.07) / 1.5x (x0.99). A cap among ETH+alts
only (BTC risk not counted, 0.4-0.8x) does nothing (x0.97-1.02). Page: reports/cap_comparison.html. **In the bot as v2.5** (`portfolio.json`
open_risk_cap_pct 5.5, cap_exempt BTCUSDT; bot.py size/capped/open_risk/resize_entry/trim_to_cap). Timing
(`sizing_v4.py`): sizing only at the 4h close loses part of it (2024-26 $17.0k, drop 41%); the bot therefore re-sizes
a waiting entry order every minute and trims at the fill -> equals the fill-time rule ($18.2k, 38%).
`cryptobot/dev/test_cap_sim.py`: the five bots on one simulated account, each entry checked against the rule.
BTC 7.5% (Oct 2026, fill-time cap 1.1x BTC, $200): 7.5/2.5/0.83 -> 2020-23 22.5%/mo drop 61%, 2024-26 $31.8k drop
48%; 2-yr bootstrap from $250 (2022-26 blocks): drop median 64% / 1-in-10 80%, P(>=$10k) 45%, P(>=$20k) 33%
(5% + cap: 51% / 68%, 35%, 22%). Lowering ETH/alts with BTC 7.5 (1.5/0.5) cuts profit a lot ($20.5k) for little
drop (58% / 46%, MC 61%): BTC drives the drops. 6/2.5/0.83: $24.3k, 54% / 42%, MC 56%.
ETH under the cap (`sizing_v5.py`): ETH trades starting while BTC is in a fresh same-direction trade average 0.33R
(win 12.5%, n=72) vs 0.79R otherwise (both periods: 0.19 vs 0.71, 0.54 vs 0.93); alts 0.31 vs 0.51R. Letting ETH
trade anyway hurts: ETH exempt too -> 2024-26 $15.0k drop 43%; cap 7.5% -> $15.4k 44.8%; ETH taking the 0.5% crumb
-> $17.4k 38.7%; never-shrink -> $17.4k. Current rule (skip if < 25% fits) best with min fraction 0.25-0.5.
Pre-breakout (`pre_breakout.py`, `antic_test.py`, `rsi_size.py`): near the level, RSI>=70 / OBV high + higher lows /
volume build-up raise the break rate (67-72% -> 76-87%) and the 5-day move, in both periods; but entering early
(market, 0.25-1 ATR before the level, on top of TBO or alone) never beats v2.1 (best: 3.24|2.53 vs 3.21|2.50;
walk-forward 1.43 vs 1.80). As sizing at the breakout: RSI>=70 n=50/45 (noise), OBV already leading -> WORSE
breakouts on 7 of 8 coin-periods but half/skip size is mixed (2.95|3.33). Nothing adopted.
4-coin grid (`portfolio_grid.py`, `portfolio_grid_eval.py`, `pgrid_dollars.py`; 1,728 settings x short size 0/0.5/1):
v2.2 ranks 21/5,184 on min(2020-23, 2024-26) return/DD. Higher: channel 40 + 1.25 ATR + EMA100 (3.75|3.91 vs
3.64|3.11) but half the trades (8.7 vs 18.7/month), neighbours median 2.92 (a peak), walk-forward re-picking 1.25 vs
v2.2 fixed 1.87. At matched drawdown (1.25-1.5% risk): 2024-26 5.5-6.4%/mo vs 4.5%, but months positive 49% vs 62%
and longest flat 450-498 d vs 318 d over 2020-26. Not adopted; offered to the user as an option.
'Quality' search (`portfolio_grid.py` PGRID=quality, `quality_eval.py`, `quality_other.py`; 1,512 settings, chosen on
2020-23 with neighbour smoothing, >= 6 trades/month): channel 40 (rest = v2.2). 2020-23 8.64 vs 3.64 (selection
period), but 2024-26 4 coins 2.65 vs 3.11 (worse); 8 other coins 1.15 vs 0.88 (better, DD 62R vs 90R, 5 of 8);
leave-one-coin-out better 3 of 4 (not BTC); 20+40 half each 2.98 in 2024-26. Not adopted (v2.2 kept).
Round 2 (user wanted daily, two-sided trades): session breakouts, 1h breakouts, mean reversion, pullbacks,
always-in momentum all fail after fees on BTC (`families2.py`, `holdout2.py`). ETH (Oct 2026): ETH-specific tuning lost to the BTC v2.1 settings out of sample -> ETH runs BTC settings
(`config_eth.json`): +191R 2020-26, DD 15.7R, 3.7%/month at 2% (DD 28%). Both bots: ~1% risk each.

## Live trial (from Oct 2026)
User runs v2.5 for 3 months from $200 (BTC 5 / ETH 2.5 / alts 0.83, cap 5.5% BTC exempt), then sends
cryptobot/reports/ (report.py, run monthly: summary + trades/income CSV from Binance) and cryptobot/logs/ (FILLED lines
carry level + slippage). To do then: backtest the same days (replay / sizing_v4 with the live equity), match trades,
compare fills, fees, funding, slippage. Expectation (research/crypto/core/three_months.py): typical $257, 1-in-10 bad
$150-170, below $200 in ~1 of 4 windows, worst drop inside 3 months typical 26% / 1-in-10 ~40%, ~58 trades.
Risk ladder (`research/crypto/studies/ladder.py`, bot: portfolio.json "risk_ladder" rows {from_usdt, per-coin %, cap_pct},
now LIVE in portfolio.json): 7.5% <$1k, 5% $1-10k, 2.5% >=$10k (ETH/alts as listed). 2 yrs from
$200: reach $10k 37% (boot) / 41% (real windows) vs flat 5% 29% / 23%; 1-in-4 bad end $1.9k vs $1.5k; drop after
reaching $1k same as flat 5% (41% / 64%). Flat 7.5%: 39% / 48% but drop after $1k 54% / 74%, gave back half of a
$5k+ peak 7%. 10% start: more ruin (5% end < $200). test_cap_sim CAPSIM_PORTFOLIO / CAPSIM_EQ: ladder rows OK.

## v2.5 live settings (Oct 2026): risk ladder
portfolio.json: ladder rows (from $0: BTC 7.5 / ETH 2.5 / alts 0.83, cap 8.25; $1k: 5 / 2.5 / 0.83, cap 5.5; $10k: 2.5 /
1.25 / 0.42, cap 2.75), cap_exempt BTC. config_btc max_leverage 12, exchange_leverage 25 (8x would cut 19% of BTC trades
at 7.5%). bot.py: risk_now / ladder_row / cap_frac(eq); BTC counts in the post-fill trim if it filled in the same minute or
before, re-checked for 2 min after a fill (same-minute races: BTC first; that order is +10% vs BTC-last in 2024-26, drop 42 vs 46% in 2020-23).
`research/crypto/core/botsim.py` = the bot's sizing (ladder, cap at fill, BTC exempt, same-minute entries BTC, ETH, BNB, SOL,
ADA); every page generator uses it (make_monthly_report, make_risk_html -> risk_comparison + plan_ladder_plus50,
make_cap_html, make_tbo_stats; the statistics page JS matches botsim to the cent, check in make_tbo_stats ref).
Ladder from $200, 2 yrs (three_months.py): typical $5.8k / $5.6k (boot / real 2022-26 windows), P($10k) 39% / 29%,
drop after $1k 40% / 63% (typ / 1-in-10). 3 months: typical $259-272, below $200 30%, drop typ 33%, 1-in-10 51%.
Trade explorer `reports/trades.html` (`make_trades_html.py` + `trades_template.html`): every trade from $200 (start 2024 /
2022 / 2020) sized by botsim, equity chart with a dot per trade, 4h price chart per trade (entry, stop, breakeven, exit),
filters, cap cut / skip marked. Prices from `trade_prices.py` (rebuilds the v2.4 trades with prices: 1551 / 1551 match).

Gate / second-chance study (Oct 2026, `gate_test.py`, `tradepath.py` = validated 1m trade simulator, 300/300 exact):
holding a new trade while another coin's same-direction trade is fresh. Premise check: trades entering with 1 other
fresh same-dir trade avg +0.74R / +0.73R (2020-23 / 2024-26) vs solo +0.69 / +0.44 -> joint breakouts are the runs,
not the chop; worst drops 2020 and 2024 were BTC losing streaks (BTC -$422 of -$432, -$64 of -$77). Results vs the bot
(ladder + cap, $200): strict gate 2024-26 $2.5k vs $25.2k (blocked trades avg +0.68R); best variants: max 2 fresh
same-dir (drop 42->38 / 44.6->39.6 but $14.7k, ret/DD x1.14 / x0.99 = same as lowering risk), max 2 fresh BTC exempt
$21.9k x1.00 / x0.98, only-fresh-BTC-blocks $19.0k; chop-only ADX<20 x1.30 in 2020-23 but x0.60 in 2024-26. Second
chance (near level 0.25-1R, retest at level / +0.5R, 12-48h) recovers part (best $16.8k) but re-entries avg 0.2-0.9R
and retests often negative; none beats the bot in 2024-26. Nothing adopted; the open-risk cap already does the useful
part (alts held while BTC is fresh).
BTC losing-streak brake (Oct 2026, `btc_streak.py`): BTC x0.5 after 2 BTC stops until a BTC trade hits +1.5R: ladder
from 2020 worst drop 42.0 -> 47.0% ($3.12M -> $1.19M), from 2024 44.6 -> 43.3% ($25.2k -> $16.2k); 3 stops / x0.33 /
reset on a winner / all coins: drops -3 to +7 points, profit -25 to -90%. Not adopted (the recovery trade is half size).
Exit ratchet (`ratchet.py`, `lock_grid.py`, engine exact on 1551 trades): trades reaching +3.5R but closing < +1R:
67 (2020-23) / 51 (2024-26), avg exit -0.07R, gave back ~5.4R. Trailing stops after +3.5..5R (1-3R): bad (net R -30 to
-70%, runners >= 5R 55 -> 10-42). One-step profit lock (+A R reached -> stop to +L R): A 3-3.5R worse; plateau A 4.5-6R,
L 0.5-2R better in both periods on a fixed R account (net/DD x1.00-1.15), ladder worst drop 42 -> 33-40% (2020 run),
44.6 -> 41.5-43% (2024 run), same profit, runners kept 48-55/55. Centre: +5R -> +1.5R (x1.11 / x1.02; drop 34.9% /
42.3%; $3.41M / $26.7k). Not in the bot yet.
v2.6 LIVE (Oct 2026): profit lock +5R -> stop +1.5R in strategy.Params (lock_R / lock_to, configs), bot.check_breakeven
(lock_done state, PROFIT LOCK log/Telegram), replay.py, xengine/common/families (lock_R, lock_to). build_trades.py
rebuilds the trade list (check: identical to v24 without the lock; v26: 1558 trades) -> cache/portfolio_trades_v26.pkl
+ trade_prices_v26.pkl; botsim.TAG = v26 (env BOT_TRADES=v24 for the old list); all pages regenerated. Parity: bot vs
replay BTC 76/76, ETH 63/63, ADA 68/68, SOL 72/73, BNB 74/75 (fill-minute stop cases only); replay vs engine ETH/BTC
2021-26 identical. Ladder from $200: 2020 $3.26M drop 37.1%, 2022 $181k 44.6%, 2024 $26.7k 42.3%. With v26 the cap's
profit effect is mixed (2024: no cap $29.7k 45.9% vs cap $26.7k 42.3%; 2022: $150k vs $181k) but it lowers drops: kept.

Universe expansion (Oct 2026, `universe.py`, v2.4 trades of 12 coins, bot sizing ladder + cap, $200): 12 coins with extra
alts at 0.83%: 2020-23 ret/drop x1.35 but 2024-26 x1.01 (drop 47.3 vs 44.6%), fixed R account x0.90 / x0.92; alts
0.42%: x1.24 / x1.01, fixed x0.90 / x1.00; same alt budget spread over 10 alts: x1.07 / x0.95; 5 + DOGE: x1.07 / x0.99;
5 + DOGE/XRP/LINK/AVAX at 0.5%: x1.24 / x1.04, fixed x1.04 / x1.08 (best, modest). 2020-23 gains = the 2021 alt boom;
2024-26 no clear gain (alts move with BTC). Not adopted at $200 (extra alt risk ~$1 -> many orders below Binance minimums);
revisit the 9-coin set at a few $k.
Breakeven offset / tighter stop (Oct 2026, `be_stop_test.py`, v2.6 rules, results in R of 1 ATR): breakeven at +0.05 /
+0.1 / +0.2R: BE exits -0.10 -> 0 / +0.10R but more trades knocked out at the higher stop: fixed R net/DD x0.91 / x0.91 /
x0.88 (2020-23), x0.99 / x0.97 / x0.81 (2024-26); ladder from 2020 drop 37.1 -> 42-45%, $3.26M -> $1.2-2.1M. Stop 0.9 ATR
sized on 1 ATR: stops cost -0.99R instead of -1.09R but 73 more stop-outs (906 vs 833): x0.95 / x1.01, ladder 2020 drop
50.6%; 0.8 ATR: x0.84 / x1.12 (inconsistent), 2020 drop 53%; stop 0.9 + BE +0.1R: x0.89 / x0.96, 2020 drop 56%. Not adopted.
Short size with v2.6 (Oct 2026, `short_size.py`): fixed R account net/DD vs no shorts: x0.25 1.09/1.18, x0.5 1.12/1.22 (best both periods), x0.75 1.05/1.16, x1 0.99/1.12; bigger shorts = more money and deeper drops (like more risk). Kept 0.5.
Smoother ladders (Oct 2026, `ladder2.py`, v2.6, $200): live 3-step vs 7 steps (7.5/6.5/5.5/5/4/3/2.5 at 0/500/1k/2.5k/
5k/10k/20k) vs log-linear glides: all within noise. 7 steps: history drops 36.3/42.3/42.3% vs 37.1/44.6/42.3% (2020/22/24
runs), 2-yr bootstrap typical $7.0k vs $6.9k, P($10k) 40% vs 42%, drop after $1k same. Glides cut the 2022-run drop
(35-39%) but lower P($10k) (real windows 29-42% vs 43%). Kept the live 3-step ladder.
Post-profit bleed filters (Oct 2026, `bleed_test.py`, v2.6): fixed R units from trades entered in the 7 d after a >= +5R
winner closed: +0.69 (2020-23) / +1.16 (2024-26) vs +2.60 / +2.15 for any 7 d window, but losing as often (52-62% vs
56-64%); 14 d after: +1.55 / +4.67 vs +5.31 / +4.42 -> weak, not consistent. 34 rules (pause / half size 3-14 d after a
+5R / +10R win, per coin, after +30-100% equity jumps, below the equity average of 10/20/50 trades, after -3/-5R in 7-14
d, after a big win + 2-3 losses, after big BTC moves): none better in both periods on the fixed R account (best x1.00-1.05 /
x0.95-1.00); equity-average filters cut drops (to 28-33%) but lose 25-35% of the edge (x0.64-0.75); skipping kills it.
Ladder-only gains (e.g. x0.5 for 3 d after +5R: 2024-26 $34k) are compounding path luck (fixed account x1.00 / x0.98).
Nothing adopted.
Pause from breakout confirmation (Oct 2026, `confirm_test.py`, v2.6): +1.5 / 2 / 3 / 5R reached by 46 / 36 / 26 / 17% of
trades after a median 6 / 10 / 16 / 30 h (those end avg +2.5 / 3.3 / 4.5 / 6.7R). Trades entered while another coin's
trade is confirmed: 2020-23 BETTER (+0.82..+1.28R vs +0.49R); 2024-26 better at +1.5R (+0.67 vs +0.49), worse at +3/+5R
(+0.31 vs +0.60). 64 rules (skip / x0.5 while confirmed or 2-7 d from confirmation, same / any direction): every one worse
in 2020-23 on the fixed R account (x0.11-0.93); some better in 2024-26 (skip 7 d after +5R x1.42) but they cost 35%+ in
2020-23 -> regime-dependent, not adopted.
Range reading on v2.6 (Oct 2026, `range_test.py`; fixed R account net/DD vs bot 2020-23 / 2024-26): ATR buffer 0.1 / 0.25 /
0.5 x0.87/0.78, x0.63/0.73, x0.59/0.61; skip ranges wider than 6 ATR x1.02/0.83, wider than 8 x1.00/0.98, tighter than 3
x0.86/1.12, tighter than 4 x0.62/0.63; RSI(14) zones x0.66-0.99 / 0.79-0.95; entry after a 1h / 2h close beyond the
level (after the engine fix below) 1h x0.73/0.48, 2h x0.69/0.45, 4h x0.47/0.22 (4h from $200 2024-26: $579, drop 79%); efficiency ratio >= 0.2 / 0.3 x0.32/0.49, x0.29/0.59. None better in both periods. (The
engine's confirm-close path now also applies skip_fn / the OI filter.)
Engine fix (Oct 2026, families.channel_breakout confirm_tf): the governing level for a close-confirmed entry was taken
from the decision at the confirm candle's own close (channel incl. the same bars), so a confirm candle ending on a 4h
close could never break it: 4h confirm gave 0 trades, 1h/2h missed the last 1-2 h of every 4h block. Now: the last tf
candle closed when the confirm candle opened (checked: 40/40 4h-confirm entries = next 4h open after a close beyond the
previous 20-candle level). Earlier close-confirm results (v2 research) were biased low, but the fixed ones are still far
worse than the stop order.

Cap study (Oct 2026, `cap_study.py`, v2.6; fixed account in units, cap in the same units): trades the cap skips avg
+0.30R (2020-23) / -0.04R (2024-26) vs +0.50 for full-size alt trades; trimmed ones +0.92 / +0.78 (kept, smaller).
Cost of the cap in units: skipped +14.9 / -3.7, trimmed part +2.9 / +2.5. Per coin with / without cap 2020-23 | 2024-26:
ETH 80/95 | 76/71, BNB 13/14 | 17/22, SOL 26/25 | 15/13, ADA 32/34 | 11/12. No cap: ret/drop x0.89 / x0.93 (drop 11.0 vs
9.5%, 15.3 vs 14.3%). Blocked trades by BTC state (BTC trade progress, BTC 7d move) flip sign between periods (n 5-33):
noise. Opposite-direction case never occurs (alts only trade with BTC's trend when BTC is fresh). Variants (ret/drop x
now, 2020-23 / 2024-26): cap 0.8-1.0x 1.03-1.06 / 0.98-0.99, 1.2x 1.00 / 0.97, 1.3-1.5x 0.92-0.95 / 0.92-0.96, ETH exempt
0.94 / 0.92, BTC risk free at +0.5/+1R 0.93-0.94 / 0.98-0.99, no cap on strong BTC 7d move 0.87-0.91 / 0.99-1.00, min
fraction 0 / 0.5 / 0.99 1.01-1.03 / 0.98-1.00. None better in both; 1.1x stays (middle of the plateau).

Live start changed to **$300** (Oct 2026, user's choice): START in make_trades_html / make_monthly_report / make_risk_html /
make_cap_html / three_months, page templates and the tbo_statistics default; all pages rebuilt; cryptobot/README trial
tables re-run from $300 (3 months: typical $403 / $420, below $300 29%, worst drop typ 30%; 2 yrs ladder typical $10.7k /
$11.5k, P($10k) 52% / 55%). Older research tables that say "$200" were computed from $200 and are left as they were.
Last research round before going live (Oct 2026, scratchpad scripts, not in git; nothing adopted): BVOL implied vol, order
book depth, metrics ratios, aggTrades whale flow, time of day / same-coin streaks / losing-streak and after-win / near-
equity-high pauses, close-based stops and breakeven, 4h/6h/8h/12h/n30/n40/phase-shifted ensembles, partial take-profit,
trailing winners past 120 h: none beats the bot beyond the noise floor (shifting the 4h candles by 1-3 h alone moves
net/DD by x0.78-1.13). Stress test: every 0.1R/trade of live shortfall roughly halves 5-yr growth -> after ~50/100/200
live trades compare with the same-days backtest; edge alarm: running avg < -0.17R (50) / -0.04R (100) / +0.13R (200).
BNB fee discount (taker 0.045%): 2024-26 $26.7k -> $29.9k from $200, same drop.

Ladder change (Oct 2026, before going live; scratchpad riskgrid/capgrid/capbtc scripts, botsim sizing): 62 profiles x 1,000
reshuffled 2-yr runs from $300 + real windows + every trade 0.2R worse: ETH at ~2/3 of BTC's risk is on the best
return/drawdown line; alts are the first to fail under the stress. Chosen ladder 6/4/.83 -> 5/3.3/.83 @1k -> 2.5/1.7/.42 @10k
vs old 7.5/2.5/.83: 2-yr typical $11.0k vs $10.7k (reshuffled), 1-in-10 drop 70% vs 73%, stress P(<$300) 12% vs 13%; from
$300 since 2022 $368k vs $274k, since 2024 $39.1k vs $36.4k (same drops). Cap grid (0.9-2.5x, none, ETH exempt) on 4 ladders:
1.1x best everywhere (looser = less money AND deeper drops; 13% of ETH trades skipped while BTC is fresh, they are the weak
ones). BTC capped too / BTC not counted / trim ETH+alts when BTC joins: all worse (BTC joining a move late averages +1.10R
vs +0.83R). portfolio.json + config_eth risk_pct 3.3 (fallback = the $1k row) updated; README tables re-run (three_months.py
now also shows the old ladder). Real funding (data/extra) instead of the flat 0.01%/8h: +2R of 911R, no change.
Trade list from the FIRST trade: build_trades / trade_prices now keep trades from 2020-01-01 (indicator warm-up on Jan-Feb
2020 data); adds one ETH trade on 2020-02-24 (-1.06R) -> 1,559 trades (other 1,558 identical). Pages' "2020" runs start
there (trades.html opens on it by default: from $300 -> $4.89M, worst drop 35.5%; 2022 run $368k / 46.4%; 2024 run
$39.1k / 41.8%). All pages rebuilt and checked in headless Chromium (no JS errors, numbers match botsim).

Research round after going live (Oct 2026; exploratory scripts in the scratchpad, not kept; the final sleeve is reproduced
by `research/crypto/core/panic_sleeve.py`, `pages/make_panic_html.py`, `cryptobot/dev/test_panic_sim.py`):
- Rejected (v2.6 engine, both periods + random skips + 4h phase shifts): exit on daily trend flip (never triggers: the 1-ATR
  / breakeven stop always closes first), late trailing stops (+8/10R, 3-5R behind: x0.75-0.97), dead-trade exits (cut 20-60
  future big winners), ATR length 10/20/28, minimum stop %, alts only when stronger than BTC (14/30d x1.18/1.08 but no
  better than random skips in 2024-26; ETH-only version zig-zags with the lookback), alts only with BTC's daily trend
  (opposite-trend alt trades were the BEST in 2020-23), weekly coin rotation from 52 coins (fixed BTC+ETH-led set beats ~97%
  of random sets; rotating the alt slots by 30d efficiency x1.10/1.02 but 60/90d worse = noise), partial take-profit (win
  rate 21% -> 46% but money -30 to -70%), adding at +2.5-5R (bootstrap 2022-26 looked good, 8 phase x era runs at matched drop
  x0.86-1.22 -> not robust).
- Chop study: 36 daily features + a model: AUC within luck bounds (0.57-0.62 vs null 0.58-0.64), model out of sample 0.51-
  0.57. Breakout outcomes on 52 coins are independent of the coin's previous FINISHED breakouts (42.8/42.9/41.6/42.2%; the
  apparent clustering was look-ahead). Drawdown depth = random reorderings of the same trades. Losses cluster in the same
  moment (other coin's trade within 24 h won -> 39% win, lost -> 13%), not in a detectable state: nothing to filter.
- **Panic sleeve (adopted, v2.7):** 3 h move vs OI change: OI rising -> continuation (fade -0.3/-0.75%), OI <= -6% ->
  rebound, monotonic in the OI fall. Premium discount (z <= -1..-5) the same effect. As a sleeve next to the bot (sized per
  event, own budget outside the cap) it beats random long trades at the same times in 99-100% of 200 draws. Grids 15,120 +
  9,072 combinations on 10 dev coins + 41 new coins (OI + premium downloaded from data.binance.vision): 66% of the focused
  grid beat the bot in all 4 tests; OI fall is the dominant setting (monotonic), window 3-6 h, price-move size barely
  matters, hold 6-18 h, no tight stop. Picking on the 10 coins does NOT carry to the 41 (top picks x0.82), picking on the 41
  carries to the 10 (100% > 1): trust the plateau. Frozen rule on the 41 coins (per-event sizing): x1.03-1.13 / x1.17-1.21.
  Exits: 12 h best (18-24 h raise 2024-26 drop to 44-46%), TP 2.5-3.5 ATR plateau, breakeven after +2 ATR neutral (safer),
  trailing 1 ATR / stop-to-entry after 4-6 h worse; stop cap -20% (FTX: 4 ATR = -68%) costs nothing. Neighbours (81: window
  3/4/6, OI 10/12/15%, premium -0.5/-1/-1.5, 2-4 units): 70% more money AND less drop in both runs, typical +5-20% / a few
  points; the chosen point is one of the better ones (expect the typical neighbour). Short squeezes: rare, losing. Waiting
  for a green hour: worse. In 27% of sleeve trades the bot is short the same coin -> separate sub-account (one-way mode).
  Final (bot real sizing from $300): 2022 $367.5k/46.4% -> $652k/29.2%; 2024 $39.1k/41.8% -> $50.7k/36.1%; 86 trades, 74% win,
  +5.9% / -3.3%, PF 5.2. Live parity (`test_panic_sim.py`): signals 0 missed / 0 extra over 3,115 hours, trades 85/86 same.
- **Breakout support study -> OI-low filter + AVAX (adopted, v2.8):** `research/crypto/studies/oi_support.py` (build / eval /
  luck), page `reports/breakout_support.html` (`pages/make_breakout_support_html.py`). 51 coins (12 dev = our 5 + XRP DOGE
  AVAX LINK DOT LTC TRX; 14 big + 25 small untouched), base = v2.6 + 72 h OI filter, 9,555 trades 2022-26. Families as grids
  (430 settings): A price moved with OI falling (skip / half), A+ coil (x1.5), B OI drop after the fill -> exit, C OI level
  or OI / 30-day volume at a high / low (7/30/90 d), D coin vs market OI, E long/short ratio extremes (3 measures), F flush
  in the last 12-48 h, G touches / quiet. Six gates fixed in advance; funnel 430 -> 44 (dev) -> 26 (plateau) -> 16 (40
  time-shifted copies, 95%) -> 4 (untouched big) -> 4 (our 5) -> 1 (money): **skip while OI (USD) ranks in its lowest 20% of
  90 days**. Our 5 ratio x1.05 / x1.10, BTC x1.05 / x1.05; untouched big +25R / +17R with drops 20-37R smaller; small +24R /
  +34R; fine grid 45-180 d x 10-30%: dev better in 24/25 (22-23) and 21/25 (24-26), untouched-big drop smaller in 25/25;
  money 45-90 d better, 120 d neutral, 180 d worse. It is a short filter (flags 29-43% of shorts, ~2% of longs; flagged
  shorts -0.37/-0.13R vs +0.84/+0.61R on our 5; same sign on every group). OI in coins (no price) low: same effect in
  2022-23; price at a 90-day low: the opposite (those breakouts better) -> not price in disguise. Near misses: leverage
  (OI / volume) low x1.2-1.3 on our 5 but small coins -58R in 2024-26 and x0.99 money from 2024; tired levels (6-8 touches)
  beat luck but lose on untouched big coins 2022-23; long/short ratios, flushes, coils, coin-vs-market OI, squeeze exits:
  nothing. Money from $300 (5 coins): 2022 $367.5k/46.4% -> $461.6k/39.4%; 2024 $39.1k/41.8% -> $41.6k/40.5%. Side finding:
  today's rules on other coins ~breakeven (14 big +6R / +22R on 2,765 trades); per coin per 100 trades BTC 78R, ETH 47R, SOL
  40R, AVAX 29R, BNB 27R, ADA 26R; only 13 of 51 coins positive in both periods. AVAX tried as a 6th coin and removed: with
  the filter 2022 $526.8k / 47.0% vs 5 coins $461.6k / 39.4%; 2024 $45.8k / 41.5% vs $41.6k / 40.5%. Coin sets (filter, from
  2022 / 2024): BTC only $61k / 40.2%, $13.3k / 30.9%; ETH only $4.7k / 37.4%, $2.5k / 31.2%; BTC+ETH $296k / 45.7%, $30.6k /
  36.5%; BTC+ETH+1 alt $304-374k / 45-47%, $35-38k / 35-40%; all 5 best money per drop from 2022. Live: `cryptobot/oi_history.py` (archive data.binance.vision + API,
  cache `oi_<SYM>.json`), `strategy.oi_rank` (= pandas rolling rank pct); `dev/test_oi_low.py` 0 / ~62k decisions differ,
  trades identical on 6 coins (incl. AVAX); `test_cap_sim.py` 0 off the rule.
- **Second event sleeve search (rejected, Oct 2026; script `research/crypto/studies/sleeve2.py`, kept out of git):** 7 event
  families on hourly bars, 249 settings, 51 coins (DEV12 to pick, HOLD39 untouched), panic-sleeve exits (TP 3 / SL 4 ATR
  max -20%, BE +2 ATR, 12 h, next-hour entry; simulator = panic research 10/10 on BTC). Gates fixed in advance (dev avg > 0
  and PF >= 1.2 both periods, plateau 60%, 200 random-entry copies 95%, HOLD39 > 0, money with bot + panic). Failed S1:
  euphoria fade (short: pump + OI up + premium), new-money follow (move + OI up, best +0.09/+0.17%), squeeze fade (short:
  pump + OI down), wick reversal (too few), crowd extreme (long/short ratio z, -0.06/-0.09%). Passed S1-S4: flash flush
  (1 h fall >= 4-6 sigma, OI down >= 3-6% -> long; monotonic, dev k5 x6% +0.51/+1.29%, untouched big +0.93/+1.69%) and
  premium extreme (z <= -4 -> long, +0.57/+0.42%), all beat 100% of random entries. Failed S5: their edge IS the panic
  sleeve's events (trades overlapping a panic trade +1..+7%; the rest ~0 / negative 2024-26: flash flush our 5 -0.25..-0.78%,
  premium -0.06..-0.38%). Bot + panic + either: 2022 $672-785k / 30.6-34.8% vs $827k / 28.2%. Bot + flash flush instead of
  panic: worse than panic. Panic rule on more coins (avg +2.5-2.8% per trade elsewhere) but no limit on open sleeve trades:
  12 dev coins 2022 $885k / 30.4%, 2024 $67k / 36.1%, reshuffled 1-in-10 drop 62% (= now); 26 coins drops 55-59% (1-in-10
  71%); 51 coins > 90%. Untested: panic on 12 coins with a cap on open sleeve trades; macro dates (FOMC / CPI calendars not
  reachable from the cloud); funding extremes (funding only for 12 coins). User: no more research for now, the bot runs.
- **Stress tests (Oct 2026, v2.8 live settings, scratchpad scripts):** 2-yr block-reshuffled paths (2022-26 blocks): bot drop
  typical 48% / 1-in-10 66% / 1-in-20 71% (end typ $13.7k); bot + panic 45% / 62% / 67% ($19.0k) -> the history's 39% is a lucky
  path. BTC risk 2-8% (others fixed): growth keeps rising (typ $3.5k -> $20.2k), 1-in-10 drop 58 -> 75%; all risks x0.5: 43%.
  Stops filled at the worst price of the exit minute: -0.16R per stop, 2022 $462k / 39% -> $147k / 59%, 2024 $41.6k / 41% ->
  $30.7k / 46% (5 min: -0.27R, $81k / 66%) -> live stop fills are the key unknown (expected -1.05..-1.10R incl. fees).
  Without the best 10 trades: 2024 run $6.4k vs $41.6k (trend following: uptime matters). Panic without its best 3 events: 2022
  $631k / 38.7% (FTX + Luna carry 2022), 2024 without its best 5: $53.6k / 38.8% (still > bot $41.6k / 40.5%); Oct 2025 crash:
  5 sleeve trades, +1.0% avg. Total notional at entries: median 1.2-1.4x, 90% 3.6-5.4x, max 11-12x; a total-notional cap 4-10x
  costs a lot (6x: 2-yr typ end $8.1k vs $14.5k) for 1-4 points of drop: not adopted. Binance BTCUSDT min notional is $50
  (not $100). Deribit DVOL / federalreserve.gov blocked from the cloud; BVOL (same idea) was rejected earlier.

