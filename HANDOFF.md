# Crypto (Binance futures) - Oct 2026

**Live setup (v2.4 = v2.3 + open-interest filter: no new order while OI (USD) is down >= 3% vs 72 h earlier; bot fetches /futures/data/openInterestHist; parity bot vs replay 15 of 16 coin-half-years exact, DOGE 2022H2 differs by the backtest's pessimistic fill-minute stop):** `cryptobot/run_all.py` (all coins, restarts), `check_setup.py` (pre-flight, no orders), `.env`
(keys, optional Telegram), configs BTC 5% / ETH 2.5% / BNB 0.83% / SOL 0.83% / ADA 0.83% risk (DOGE dropped, BNB + SOL added Oct 2026 on recent strength; user chose 2x for a $200 account; size cap 8x, leverage 20x), shorts x0.5; step-by-step
guide in `cryptobot/README.md` ("GO LIVE"). Pages: `stats/tbo_crypto_statistics.html`, `cryptobot/robustness.html`,
`cryptobot/monthly_report.html`.

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
2022-26 x1.05; binds on 13% of entries (8% shrunk to ~72%, 5% skipped). Not yet in the bot.
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
