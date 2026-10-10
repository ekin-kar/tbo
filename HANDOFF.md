# Crypto (Binance futures) - Oct 2026

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
`cryptobot/test_cap_sim.py`: the five bots on one simulated account, each entry checked against the rule.
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
compare fills, fees, funding, slippage. Expectation (research/crypto/three_months.py): typical $257, 1-in-10 bad
$150-170, below $200 in ~1 of 4 windows, worst drop inside 3 months typical 26% / 1-in-10 ~40%, ~58 trades.
Risk ladder (`research/crypto/ladder.py`, bot: portfolio.json "risk_ladder" rows {from_usdt, per-coin %, cap_pct},
now LIVE in portfolio.json): 7.5% <$1k, 5% $1-10k, 2.5% >=$10k (ETH/alts as listed). 2 yrs from
$200: reach $10k 37% (boot) / 41% (real windows) vs flat 5% 29% / 23%; 1-in-4 bad end $1.9k vs $1.5k; drop after
reaching $1k same as flat 5% (41% / 64%). Flat 7.5%: 39% / 48% but drop after $1k 54% / 74%, gave back half of a
$5k+ peak 7%. 10% start: more ruin (5% end < $200). test_cap_sim CAPSIM_PORTFOLIO / CAPSIM_EQ: ladder rows OK.

## v2.5 live settings (Oct 2026): risk ladder
portfolio.json: ladder rows (from $0: BTC 7.5 / ETH 2.5 / alts 0.83, cap 8.25; $1k: 5 / 2.5 / 0.83, cap 5.5; $10k: 2.5 /
1.25 / 0.42, cap 2.75), cap_exempt BTC. config_btc max_leverage 12, exchange_leverage 25 (8x would cut 19% of BTC trades
at 7.5%). bot.py: risk_now / ladder_row / cap_frac(eq); BTC counts in the post-fill trim if it filled in the same minute or
before, re-checked for 2 min after a fill (same-minute races: BTC first; that order is +10% vs BTC-last in 2024-26, drop 42 vs 46% in 2020-23).
`research/crypto/botsim.py` = the bot's sizing (ladder, cap at fill, BTC exempt, same-minute entries BTC, ETH, BNB, SOL,
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
