# FINAL AUDIT BUNDLE: TBO v3.2.1 (O1), pre-install production audit

* Generated 2026-11-14 09:19 (local) from commit `abaf80c` on `main`, by `build_bundle.py` (the script that produced this file reads, it never writes `cryptobot/`).
* Scope: git / process health, the 8 live JSON configs verbatim + checklist, the remaining live modules and install scripts verbatim, the 8 HTML reports (versions, JS syntax, headline numbers vs the simulator), and the live smoke test.
* Everything marked PASS / FAIL below is computed from the files in this checkout; the verdicts are collected in the summary.
* **Summary: 145 of 145 computed checks pass, 0 fail** (see Section 6).

## SECTION 1: git, branch and process health

Captured immediately before the bundle was generated (after `git fetch origin`):

~~~~
$ git status
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean

$ git branch -v
* main         abaf80c market_regimes page: state the live system is v3.2.1 in the page text (data unchanged)
  v31-research 58a24ae TBO v3.1 production build: failed-breakout stop, BTC cascade, VOLC sleeve, ladder x 0.90
  v32-research 946b026 TBO v3.2 production build: wild-pullback x0.25 size, flat first ladder row at k 1.00
  v33-research 80bceaf v3.3 research: VOLC collision diagnosed and guarded, zone-2 failed-extension stop passes, 2,005 settings
  v34-research 17a6ce1 v3.4 wrap-up: O1 (the v3.2.1 settings) kept and verified; pages labelled v3.2.1
  v35-research 614304b v3.5 wrap-up: HANDOFF and bot README note the campaign (0 adopted, v3.2.1 final)

$ git log -n 8 --oneline
abaf80c market_regimes page: state the live system is v3.2.1 in the page text (data unchanged)
133476f winrate_rr page: label TBO v3.2.1 (was v2.8) and quote the current 20.0% win rate and +0.65R per trade; data unchanged
614304b v3.5 wrap-up: HANDOFF and bot README note the campaign (0 adopted, v3.2.1 final)
07dc69d v3.5 research: VOLC on the 7 extra coins and 4 new strategy families scored against v3.2.1 (O1); nothing adopted
17a6ce1 v3.4 wrap-up: O1 (the v3.2.1 settings) kept and verified; pages labelled v3.2.1
a181441 v3.4 research: joint risk-grid and plateau audit of the v3.2.1 system (54,000 joint settings, 5 options)
26f07bf v3.2.1 review fixes: /status vs the VOLC sleeve, own fill price after a hand-over, two-sided VOLC market entry
ec292fd v3.2.1 audit: VOLC hand-over after a take-profit fill, tie-guard cancel race, per-coin isolation

$ git rev-parse main origin/main
abaf80c400af50c3fca8650cb23ff0154f08d31c
abaf80c400af50c3fca8650cb23ff0154f08d31c

$ git rev-list --left-right --count main...origin/main   # ahead behind
0	0
~~~~

~~~~
$ ps aux | grep python    # (the harness shell and this grep itself also match; lines cut to 170 chars)
root         181  0.0  0.1  30140 19776 ?        Ss   07:23   0:00 /usr/bin/python3 /usr/bin/networkd-dispatcher --run-startup-triggers
root         213  0.0  0.1 107196 22144 ?        Ssl  07:23   0:00 /usr/bin/python3 /usr/share/unattended-upgrades/unattended-upgrade-shutdown --wait-for-signal
eko         7262  0.0  0.0   5052  3652 ?        Ss   09:16   0:00 /bin/bash -c source /home/eko/.claude/shell-snapshots/snapshot-bash-1794630460251-a6zdwy.sh 2>/dev/null
eko         7280  0.0  0.0   5052  2320 ?        S    09:16   0:00 /bin/bash -c source /home/eko/.claude/shell-snapshots/snapshot-bash-1794630460251-a6zdwy.sh 2>/dev/null
eko         7282  0.0  0.0 1408488 6612 ?        S    09:16   0:00 ugrep -G --ignore-files --hidden -I --exclude-dir=.git --exclude-dir=.svn --exclude-dir=.hg --exclude-d

$ ps aux | grep '[p]ython'    # same without matching itself
root         181  0.0  0.1  30140 19776 ?        Ss   07:23   0:00 /usr/bin/python3 /usr/bin/networkd-dispatcher --run-startup-triggers
root         213  0.0  0.1 107196 22144 ?        Ssl  07:23   0:00 /usr/bin/python3 /usr/share/unattended-upgrades/unattended-upgrade-shutdown --wait-for-signal
eko         7262  0.0  0.0   5052  3652 ?        Ss   09:16   0:00 /bin/bash -c source /home/eko/.claude/shell-snapshots/snapshot-bash-1794630460251-a6zdwy.sh 2>/dev/null
eko         7284  0.0  0.0   5052  2320 ?        S    09:16   0:00 /bin/bash -c source /home/eko/.claude/shell-snapshots/snapshot-bash-1794630460251-a6zdwy.sh 2>/dev/null
~~~~

* main checked out: PASS; in sync with origin/main: PASS; working tree clean: PASS
* No research / test / bot process left running (only the OS daemons `networkd-dispatcher` and `unattended-upgrade-shutdown`; the `/bin/bash -c` lines are the shell that ran the command): PASS
* The five older `v31-research` .. `v35-research` branches still exist locally (not deleted); `main` is the only branch that matters for the install.
* Note: this snapshot is the state before this bundle file itself was committed; the final state is re-checked after the commit (see the closing note).

## SECTION 2: live JSON configs (verbatim) and checklist

### 2.1 `cryptobot/portfolio.json`
~~~~json
{
  "open_risk_cap_pct": 5.5,
  "cap_exempt": ["BTCUSDT"],
  "cap_min_fraction": 0.25,
  "risk_scale_note": "v3.2 (13 Nov 2026): the v3.0 ladder at k = 1.00 with the first row (< $1,000) at the $1,000-10,000 risks (research/results/v32c_REPORT.md, stage 3)",
  "risk_ladder": [
    {"from_usdt": 0, "BTCUSDT": 5.0, "ETHUSDT": 3.3, "BNBUSDT": 0.83, "SOLUSDT": 0.83, "ADAUSDT": 0.83, "cap_pct": 5.5},
    {"from_usdt": 1000, "BTCUSDT": 5.0, "ETHUSDT": 3.3, "BNBUSDT": 0.83, "SOLUSDT": 0.83, "ADAUSDT": 0.83, "cap_pct": 5.5},
    {"from_usdt": 10000, "BTCUSDT": 2.5, "ETHUSDT": 1.7, "BNBUSDT": 0.42, "SOLUSDT": 0.42, "ADAUSDT": 0.42, "cap_pct": 2.75}
  ]
}
~~~~

### 2.2 `cryptobot/config_btc.json`
~~~~json
{
  "risk_pct": 5.0,
  "short_risk_mult": 0.5,
  "max_leverage": 12,
  "exchange_leverage": 25,
  "poll_s": 5,
  "strategy": {
    "symbol": "BTCUSDT",
    "tf_min": 240,
    "n": 20,
    "atr_n": 14,
    "sl_atr": 1.0,
    "ema_n": 50,
    "trail_m": 0,
    "trail_atr": 0.0,
    "max_hold_h": 120,
    "sides": "both",
    "slope_d": 5,
    "no_weekend": true,
    "be_R": 1.5,
    "be_off": 0.0,
    "lock_R": 5.0,
    "lock_to": 2.0,
    "max_ext": 4.0,
    "oi_lookback_h": 72,
    "oi_min_chg": -0.03,
    "oi_low_days": 90,
    "oi_low_rank": 0.2,
    "lock2_R": 8.0,
    "lock2_to": 3.5,
    "stale_h": 60,
    "stale_thr": -0.3,
    "stale_to": 0.0,
    "cool_h": 16,
    "cool_R": -0.5,
    "fb_h": 8,
    "fb_mfe": 0.9,
    "fb_thr": -0.2,
    "fb_to": -0.5,
    "fb_cool": true,
    "casc_src": "",
    "casc_R": -0.5,
    "casc_to": -0.25,
    "vr_mult": 0.25,
    "vr_min": 0.98,
    "vr_chg5": -0.25
  }
}
~~~~

### 2.3 `cryptobot/config_eth.json`
~~~~json
{
  "risk_pct": 3.3,
  "short_risk_mult": 0.5,
  "max_leverage": 8,
  "exchange_leverage": 20,
  "poll_s": 5,
  "strategy": {
    "symbol": "ETHUSDT",
    "tf_min": 240,
    "n": 20,
    "atr_n": 14,
    "sl_atr": 1.0,
    "ema_n": 50,
    "trail_m": 0,
    "trail_atr": 0.0,
    "max_hold_h": 120,
    "sides": "both",
    "slope_d": 5,
    "no_weekend": true,
    "be_R": 1.5,
    "be_off": 0.0,
    "lock_R": 5.0,
    "lock_to": 2.0,
    "max_ext": 4.0,
    "oi_lookback_h": 72,
    "oi_min_chg": -0.03,
    "oi_low_days": 90,
    "oi_low_rank": 0.2,
    "lock2_R": 8.0,
    "lock2_to": 3.5,
    "stale_h": 60,
    "stale_thr": -0.3,
    "stale_to": 0.0,
    "cool_h": 16,
    "cool_R": -0.5,
    "fb_h": 8,
    "fb_mfe": 0.9,
    "fb_thr": -0.2,
    "fb_to": -0.5,
    "fb_cool": true,
    "casc_src": "BTCUSDT",
    "casc_R": -0.5,
    "casc_to": -0.25,
    "vr_mult": 0.25,
    "vr_min": 0.98,
    "vr_chg5": -0.25
  }
}
~~~~

### 2.4 `cryptobot/config_bnb.json`
~~~~json
{
  "risk_pct": 0.83,
  "short_risk_mult": 0.5,
  "max_leverage": 8,
  "exchange_leverage": 20,
  "poll_s": 5,
  "strategy": {
    "symbol": "BNBUSDT",
    "tf_min": 240,
    "n": 20,
    "atr_n": 14,
    "sl_atr": 1.0,
    "ema_n": 50,
    "trail_m": 0,
    "trail_atr": 0.0,
    "max_hold_h": 120,
    "sides": "both",
    "slope_d": 5,
    "no_weekend": true,
    "be_R": 1.5,
    "be_off": 0.0,
    "lock_R": 5.0,
    "lock_to": 2.0,
    "max_ext": 4.0,
    "oi_lookback_h": 72,
    "oi_min_chg": -0.03,
    "oi_low_days": 90,
    "oi_low_rank": 0.2,
    "lock2_R": 8.0,
    "lock2_to": 3.5,
    "stale_h": 60,
    "stale_thr": -0.3,
    "stale_to": 0.0,
    "cool_h": 16,
    "cool_R": -0.5,
    "fb_h": 8,
    "fb_mfe": 0.9,
    "fb_thr": -0.2,
    "fb_to": -0.5,
    "fb_cool": true,
    "casc_src": "BTCUSDT",
    "casc_R": -0.5,
    "casc_to": -0.25,
    "vr_mult": 0.25,
    "vr_min": 0.98,
    "vr_chg5": -0.25
  }
}
~~~~

### 2.5 `cryptobot/config_sol.json`
~~~~json
{
  "risk_pct": 0.83,
  "short_risk_mult": 0.5,
  "max_leverage": 8,
  "exchange_leverage": 20,
  "poll_s": 5,
  "strategy": {
    "symbol": "SOLUSDT",
    "tf_min": 240,
    "n": 20,
    "atr_n": 14,
    "sl_atr": 1.0,
    "ema_n": 50,
    "trail_m": 0,
    "trail_atr": 0.0,
    "max_hold_h": 120,
    "sides": "both",
    "slope_d": 5,
    "no_weekend": true,
    "be_R": 1.5,
    "be_off": 0.0,
    "lock_R": 5.0,
    "lock_to": 2.0,
    "max_ext": 4.0,
    "oi_lookback_h": 72,
    "oi_min_chg": -0.03,
    "oi_low_days": 90,
    "oi_low_rank": 0.2,
    "lock2_R": 8.0,
    "lock2_to": 3.5,
    "stale_h": 60,
    "stale_thr": -0.3,
    "stale_to": 0.0,
    "cool_h": 16,
    "cool_R": -0.5,
    "fb_h": 8,
    "fb_mfe": 0.9,
    "fb_thr": -0.2,
    "fb_to": -0.5,
    "fb_cool": true,
    "casc_src": "BTCUSDT",
    "casc_R": -0.5,
    "casc_to": -0.25,
    "vr_mult": 0.25,
    "vr_min": 0.98,
    "vr_chg5": -0.25
  }
}
~~~~

### 2.6 `cryptobot/config_ada.json`
~~~~json
{
  "risk_pct": 0.83,
  "short_risk_mult": 0.5,
  "max_leverage": 8,
  "exchange_leverage": 20,
  "poll_s": 5,
  "strategy": {
    "symbol": "ADAUSDT",
    "tf_min": 240,
    "n": 20,
    "atr_n": 14,
    "sl_atr": 1.0,
    "ema_n": 50,
    "trail_m": 0,
    "trail_atr": 0.0,
    "max_hold_h": 120,
    "sides": "both",
    "slope_d": 5,
    "no_weekend": true,
    "be_R": 1.5,
    "be_off": 0.0,
    "lock_R": 5.0,
    "lock_to": 2.0,
    "max_ext": 4.0,
    "oi_lookback_h": 72,
    "oi_min_chg": -0.03,
    "oi_low_days": 90,
    "oi_low_rank": 0.2,
    "lock2_R": 8.0,
    "lock2_to": 3.5,
    "stale_h": 60,
    "stale_thr": -0.3,
    "stale_to": 0.0,
    "cool_h": 16,
    "cool_R": -0.5,
    "fb_h": 8,
    "fb_mfe": 0.9,
    "fb_thr": -0.2,
    "fb_to": -0.5,
    "fb_cool": true,
    "casc_src": "BTCUSDT",
    "casc_R": -0.5,
    "casc_to": -0.25,
    "vr_mult": 0.25,
    "vr_min": 0.98,
    "vr_chg5": -0.25
  }
}
~~~~

### 2.7 `cryptobot/volc.json`
~~~~json
{
  "enabled": true,
  "coins": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"],
  "share": 0.25,
  "signal": {
    "n": 10,
    "sq": 0.6,
    "oi_min": 0.0,
    "ema_n": 50,
    "er_n": 10,
    "er_max": 0.25,
    "mode": "hybrid",
    "sl_atr": 1.0,
    "tp_R": 1.5,
    "hold_h": 36,
    "excl_h": 12
  },
  "max_leverage": 6,
  "poll_s": 5,
  "dry_run_equity": 300
}
~~~~

### 2.8 `cryptobot/panic.json`
~~~~json
{
  "coins": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"],
  "units": 3,
  "extra_coins": ["XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT"],
  "extra_share": 0.75,
  "max_extra_open": 2,
  "signal": {
    "window_h": 4,
    "move_k": 1.5,
    "oi_drop": 0.12,
    "premium_z": -1.0,
    "hold_h": 12,
    "tp_atr": 3.0,
    "stop_atr": 4.0,
    "stop_max": 0.2,
    "be_atr": 2.0
  },
  "max_leverage": 4,
  "exchange_leverage": 5,
  "poll_s": 15,
  "dry_run_equity": 75,
  "dry_run_equity_main": 225
}
~~~~

### 2.9 Checklist (computed)

| Check | Result |
|---|---|
| config_btc.json v3.0 / v3.1 / v3.2 parameters (lock_R 5 -> 2, lock2_R 8 -> 3.5, stale_h 60, cool_h 16, fb_h 8 / fb_mfe 0.9 / fb_thr -0.2 / fb_to -0.5, casc_R -0.5 / casc_to -0.25, vr_mult 0.25 / vr_min 0.98 / vr_chg5 -0.25) | PASS |
| config_btc.json casc_src = '' (BTC is the source) | PASS |
| config_btc.json fallback risk_pct 5.0 = portfolio tier 1 (5.0) | PASS |
| config_btc.json shorts x0.5, OI filters oi_lookback_h 72 / oi_min_chg -0.03 / oi_low_days 90 / oi_low_rank 0.2, be_R 1.5, max_hold_h 120, n 20, sl_atr 1.0 | PASS |
| config_eth.json v3.0 / v3.1 / v3.2 parameters (lock_R 5 -> 2, lock2_R 8 -> 3.5, stale_h 60, cool_h 16, fb_h 8 / fb_mfe 0.9 / fb_thr -0.2 / fb_to -0.5, casc_R -0.5 / casc_to -0.25, vr_mult 0.25 / vr_min 0.98 / vr_chg5 -0.25) | PASS |
| config_eth.json casc_src = 'BTCUSDT' (follows BTC) | PASS |
| config_eth.json fallback risk_pct 3.3 = portfolio tier 1 (3.3) | PASS |
| config_eth.json shorts x0.5, OI filters oi_lookback_h 72 / oi_min_chg -0.03 / oi_low_days 90 / oi_low_rank 0.2, be_R 1.5, max_hold_h 120, n 20, sl_atr 1.0 | PASS |
| config_bnb.json v3.0 / v3.1 / v3.2 parameters (lock_R 5 -> 2, lock2_R 8 -> 3.5, stale_h 60, cool_h 16, fb_h 8 / fb_mfe 0.9 / fb_thr -0.2 / fb_to -0.5, casc_R -0.5 / casc_to -0.25, vr_mult 0.25 / vr_min 0.98 / vr_chg5 -0.25) | PASS |
| config_bnb.json casc_src = 'BTCUSDT' (follows BTC) | PASS |
| config_bnb.json fallback risk_pct 0.83 = portfolio tier 1 (0.83) | PASS |
| config_bnb.json shorts x0.5, OI filters oi_lookback_h 72 / oi_min_chg -0.03 / oi_low_days 90 / oi_low_rank 0.2, be_R 1.5, max_hold_h 120, n 20, sl_atr 1.0 | PASS |
| config_sol.json v3.0 / v3.1 / v3.2 parameters (lock_R 5 -> 2, lock2_R 8 -> 3.5, stale_h 60, cool_h 16, fb_h 8 / fb_mfe 0.9 / fb_thr -0.2 / fb_to -0.5, casc_R -0.5 / casc_to -0.25, vr_mult 0.25 / vr_min 0.98 / vr_chg5 -0.25) | PASS |
| config_sol.json casc_src = 'BTCUSDT' (follows BTC) | PASS |
| config_sol.json fallback risk_pct 0.83 = portfolio tier 1 (0.83) | PASS |
| config_sol.json shorts x0.5, OI filters oi_lookback_h 72 / oi_min_chg -0.03 / oi_low_days 90 / oi_low_rank 0.2, be_R 1.5, max_hold_h 120, n 20, sl_atr 1.0 | PASS |
| config_ada.json v3.0 / v3.1 / v3.2 parameters (lock_R 5 -> 2, lock2_R 8 -> 3.5, stale_h 60, cool_h 16, fb_h 8 / fb_mfe 0.9 / fb_thr -0.2 / fb_to -0.5, casc_R -0.5 / casc_to -0.25, vr_mult 0.25 / vr_min 0.98 / vr_chg5 -0.25) | PASS |
| config_ada.json casc_src = 'BTCUSDT' (follows BTC) | PASS |
| config_ada.json fallback risk_pct 0.83 = portfolio tier 1 (0.83) | PASS |
| config_ada.json shorts x0.5, OI filters oi_lookback_h 72 / oi_min_chg -0.03 / oi_low_days 90 / oi_low_rank 0.2, be_R 1.5, max_hold_h 120, n 20, sl_atr 1.0 | PASS |
| portfolio.json ladder = v3.2 ($0 / $1,000: BTC 5 / ETH 3.3 / alts 0.83, cap 5.5; $10,000: 2.5 / 1.7 / 0.42, cap 2.75) | PASS |
| portfolio.json open_risk_cap_pct 5.5, cap_exempt ['BTCUSDT'], cap_min_fraction 0.25 | PASS |
| volc.json `enabled: true`, `share: 0.25`, coins = the core 5, max_leverage 6 | PASS |
| volc.json `signal` = the v3.1 signal (n 10, sq 0.6, oi_min 0, ema_n 50, er_n 10, er_max 0.25, hybrid, sl_atr 1.0, tp_R 1.5, hold_h 36, excl_h 12) | PASS |
| volc.json `signal` equals `volc_signal.DEFAULTS` (every key; DEFAULTS also holds the internal `warmup` = 122 bars, not a config key) (identical) | PASS |
| volc.json has no `tp_inside` key: **the 0.01% inside take-profit is the code default** `volc.py: cfg.get("tp_inside", 0.0001)` (same value the research uses, `v31deploy.TP_PAD` = 0.0001). Equivalent, but not written in the JSON. | PASS |
| panic.json `units: 3`, `extra_share: 0.75`, `max_extra_open: 2` | PASS |
| panic.json core coins = BTC ETH BNB SOL ADA; extra coins = XRP DOGE AVAX LINK DOT LTC TRX | PASS |
| panic.json `signal` equals `panic_signal.DEFAULTS` (window 4 h, move_k 1.5, oi_drop 0.12, premium_z -1.0, hold 12 h, tp 3 ATR, stop 4 ATR, stop_max 0.20, be 2 ATR) | PASS |

Not live-trading values: `dry_run_equity*` keys in `volc.json` / `panic.json` are only used by the dry-run mode.

## SECTION 3: remaining live modules and install scripts (verbatim)

### 3.1 `cryptobot/panic_signal.py` (70 lines)
~~~~python
"""
Panic-rebound signal (the "panic sleeve"), shared by the live sleeve (panic.py) and the research
(research/crypto/core/panic_sleeve.py), so both compute exactly the same numbers. numpy only.

The idea: when a coin falls hard while open interest collapses, leveraged longs are being force-liquidated. Forced
selling overshoots, and the price tends to rebound. With hourly bars (index t = the hour that just closed):
  * move    rz  = log(close_t / close_t-L) / (sigma_t * sqrt(L)),  sigma_t = std of the last 168 hourly log returns
  * OI drop doi = OI_t / OI_t-L - 1                (open interest value, sampled at the end of each hour)
  * premium pz  = z-score of the futures premium index (close) over the last 720 hours (min 300)
  signal when rz <= -move_k and doi <= -oi_drop and pz <= premium_z
Exits (see panic.py): take-profit +tp_atr x ATR, stop -stop_atr x ATR but never more than stop_max below the entry
(a crash with huge ATR would otherwise put it -50% away), moved to the entry once +be_atr x ATR is reached, otherwise
closed after hold_h hours. ATR = 14-hour exponential average of the true range.
"""
import numpy as np

DEFAULTS = dict(window_h=4, move_k=1.5, oi_drop=0.12, premium_z=-1.0, hold_h=12, tp_atr=3.0, stop_atr=4.0, stop_max=0.20, be_atr=2.0)


def _rolling_mean_std(x, n, min_n):
    """Rolling mean and sample std (ddof 1) over the last n values, ignoring NaN; NaN where fewer than min_n values."""
    x = np.asarray(x, float)
    ok = ~np.isnan(x)
    v = np.where(ok, x, 0.0)
    c1 = np.r_[0.0, np.cumsum(v)]; c2 = np.r_[0.0, np.cumsum(v * v)]; cn = np.r_[0, np.cumsum(ok)]
    i = np.arange(1, len(x) + 1); j = np.maximum(i - n, 0)
    s1, s2, k = c1[i] - c1[j], c2[i] - c2[j], cn[i] - cn[j]
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = s1 / k
        var = (s2 - s1 * s1 / k) / (k - 1)
    var = np.where(var < 0, 0.0, var)
    bad = k < max(min_n, 2)
    return np.where(bad, np.nan, mean), np.where(bad, np.nan, np.sqrt(var))


def atr(h, l, c, n=14):
    """True range averaged with weights (1 - 1/n)^k over all bars so far (the research's pandas ewm(alpha=1/n))."""
    h, l, c = (np.asarray(v, float) for v in (h, l, c))
    pc = np.r_[np.nan, c[:-1]]
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    a = 1.0 - 1.0 / n
    out = np.empty(len(tr)); num = den = 0.0
    for i, x in enumerate(tr):
        num = x + a * num; den = 1.0 + a * den; out[i] = num / den
    return out


def features(h, l, c, oi, prem, window_h=4):
    """Arrays aligned with the hourly bars. oi / prem may contain NaN (missing hours)."""
    c = np.asarray(c, float); oi = np.asarray(oi, float); prem = np.asarray(prem, float)
    L = int(window_h)
    lr = np.r_[np.nan, np.diff(np.log(c))]
    _, sig = _rolling_mean_std(lr, 168, 100)
    cL = np.r_[np.full(L, np.nan), c[:-L]]; oL = np.r_[np.full(L, np.nan), oi[:-L]]
    with np.errstate(invalid="ignore", divide="ignore"):
        rz = np.log(c / cL) / (sig * np.sqrt(L))
        doi = oi / oL - 1.0
    pm, ps = _rolling_mean_std(prem, 720, 300)
    with np.errstate(invalid="ignore", divide="ignore"):
        pz = (prem - pm) / ps
    return dict(rz=rz, doi=doi, pz=pz, atr=atr(h, l, c))


def signal(f, move_k=1.5, oi_drop=0.12, premium_z=-1.0, **_):
    """True at the bars whose close triggers a buy (NaN inputs never trigger)."""
    with np.errstate(invalid="ignore"):
        s = (f["rz"] <= -move_k) & (f["doi"] <= -oi_drop)
        if premium_z is not None:
            s &= f["pz"] <= premium_z
    return np.nan_to_num(s).astype(bool)
~~~~

### 3.2 `cryptobot/oi_history.py` (111 lines)
~~~~python
"""
Hourly open interest (USD value) for the OI-low filter (v2.8), which needs more history than Binance's API keeps
(openInterestHist: the last 30 days, 500 rows per call). The older part comes from Binance's public daily archive
(data.binance.vision, the same numbers the research used); the last ~20 days from the API. One row per hour,
cached in oi_<SYMBOL>.json next to the configs so a restart only fetches what is new.
"""
import csv
import io
import json
import logging
import time
import zipfile
from datetime import datetime, timedelta, timezone

import requests

ARCH = "https://data.binance.vision/data/futures/um/daily/metrics"
HOUR = 3600_000
log = logging.getLogger("tbo")


class OIHistory:
    def __init__(self, x, sym, days, folder, suffix=""):
        self.x, self.sym, self.days = x, sym, int(days)
        self.path = folder / f"oi_{sym}{suffix}.json"
        self.rows, self.done = {}, set()                 # hour start (ms) -> (sample ms, value); archive days fetched
        try:
            c = json.loads(self.path.read_text())
            self.rows = {int(k): tuple(v) for k, v in c.get("rows", {}).items()}
            self.done = set(c.get("days", []))
        except (OSError, ValueError):
            pass
        self.s = requests.Session()

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(rows={str(k): list(v) for k, v in self.rows.items()}, days=sorted(self.done))))
        tmp.replace(self.path)

    def _day(self, day):
        """One archive day: the last 5-minute row of each hour (as research/crypto/core/fetch_binance_extra.py).
        None = not published yet / unreachable; [] = no file for that day (coin not listed yet)."""
        try:
            r = self.s.get(f"{ARCH}/{self.sym}/{self.sym}-metrics-{day}.zip", timeout=20)
        except requests.RequestException:
            return None
        if r.status_code == 404:
            return []
        if r.status_code != 200:
            return None
        z = zipfile.ZipFile(io.BytesIO(r.content))
        rd = list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
        if not rd:
            return []
        col = rd[0].index("sum_open_interest_value")
        keep = {}
        for row in rd[1:]:
            keep[row[0][:13]] = row
        out = []
        for row in keep.values():
            t = int(datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)
            out.append((t, float(row[col] or 0)))
        return out

    def update(self, budget_s=None):
        """Fetch the archive days still missing (oldest first; stops after budget_s seconds, the rest next time) and
        the API's last 500 hours."""
        t_end = None if budget_s is None else time.time() + budget_s
        now = self.x.now_ms()
        today = datetime.fromtimestamp(now / 1000, timezone.utc).date()
        want = [str(today - timedelta(days=d)) for d in range(self.days + 2, 1, -1)]   # up to the day before yesterday
        todo = [d for d in want if d not in self.done]
        api_from = None
        try:
            api = self.x.open_interest_hist(self.sym, period="1h", limit=500)
            api_from = api[0][0] if api else None
        except Exception as e:
            api = []
            log.warning(f"open interest history (API) unavailable: {e}")
        # archive days the API already covers are not needed
        if api_from is not None:
            todo = [d for d in todo if datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000 + 86400_000 <= api_from + HOUR]
        n = 0
        for d in todo:
            if t_end is not None and time.time() > t_end:
                break
            got = self._day(d)
            if got is None:
                continue
            for t, v in got:
                if v > 0:
                    self.rows.setdefault(t - t % HOUR, (t, v))
            self.done.add(d)
            n += 1
        for t, v in api:                                 # the API wins where both have the hour
            if v > 0:
                self.rows[t - t % HOUR] = (t, v)
        old = now - (self.days + 3) * 86400_000
        self.rows = {k: v for k, v in self.rows.items() if k >= old}
        self.done = {d for d in self.done if d >= str(today - timedelta(days=self.days + 3))}
        self.save()
        if n:
            log.debug(f"open interest history: {n} archive day(s) added, {len(self.rows)} hours known")
        return n

    def series(self):
        """[(sample ms, value), ...] oldest first, one row per hour."""
        return [self.rows[k] for k in sorted(self.rows)]

    def hours(self):
        return len(self.rows)
~~~~

### 3.3 `cryptobot/notify.py` (203 lines)
~~~~python
"""Telegram messages and .env loading (no extra packages).
.env in TBO_SECRETS_DIR (outside the repo; default ~/tbo-secrets, on Windows %USERPROFILE%\tbo-secrets), or for
servers set up by vds_setup.sh next to the configs:  BINANCE_API_KEY=...  BINANCE_API_SECRET=...  TELEGRAM_TOKEN=...  TELEGRAM_CHAT_ID=...
Optional: TELEGRAM_UTC_OFFSET=3 shows times in UTC+3 (default: the computer's own time zone).

The bots send their own trade events (opened, breakeven, profit lock, closed, cap cuts) and warnings; run_all.py sends
one start-up message and answers /status (listen()). Messages use Telegram's HTML formatting."""
import html
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


def load_env(path):
    """KEY=VALUE lines; values already set in the environment win."""
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


def secrets_dir():
    """The private-files folder outside the repo: $TBO_SECRETS_DIR, else ~/tbo-secrets (%USERPROFILE%\tbo-secrets)."""
    d = os.environ.get("TBO_SECRETS_DIR")
    return Path(d).expanduser() if d else Path.home() / "tbo-secrets"


def load_secrets_env(bot_dir):
    """Load .env from the secrets folder; a server set up by vds_setup.sh keeps its .env in the bot folder
    (bot_dir), which is used when the secrets folder has none. Returns the file loaded, or None."""
    for p in (secrets_dir() / ".env", Path(bot_dir) / ".env"):
        if p.is_file():
            load_env(p)
            return p
    print(f"WARNING: no .env file found. Looked in {secrets_dir() / '.env'} and {Path(bot_dir) / '.env'}. "
          "Put .env in the secrets folder (or set TBO_SECRETS_DIR); only keys already in the environment are used.",
          file=sys.stderr)
    return None


def enabled():
    return bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _post(text):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    for _ in range(3):
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=10,
                              data=dict(chat_id=chat, text=text[:4000], parse_mode="HTML", disable_web_page_preview="true"))
            if r.status_code == 200:
                return
            if r.status_code == 400:                       # formatting refused: send it as plain text
                requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=10,
                              data=dict(chat_id=chat, text=_plain(text)[:4000]))
                return
        except Exception:
            pass                                           # alerts must never break trading
        time.sleep(2)


def _plain(text):
    for t in ("<b>", "</b>", "<i>", "</i>", "<code>", "</code>"):
        text = text.replace(t, "")
    return html.unescape(text)


def send(text, wait=False):
    """Send in the background (wait=True: before returning, e.g. right before the program exits)."""
    if not enabled():
        return
    if wait:
        _post(text)
    else:
        threading.Thread(target=_post, args=(text,), daemon=True).start()


def listen(commands, log=print):
    """Answer commands typed in the chat (only from TELEGRAM_CHAT_ID), e.g. {"status": ("description", fn)}; fn()
    returns the reply text. Runs forever (long polling); adds the commands to the bot's / menu. One server per bot
    token: a second program polling the same token gets HTTP 409 and the commands go to one of them only."""
    if not enabled():
        return
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), str(os.environ.get("TELEGRAM_CHAT_ID")).strip()
    api = f"https://api.telegram.org/bot{tok}"
    try:
        requests.post(f"{api}/setMyCommands", timeout=10,
                      json=dict(commands=[dict(command=c, description=d) for c, (d, _) in commands.items()]))
    except Exception:
        pass
    offset, warned = None, 0.0
    try:                                                   # skip commands typed while the bot was not running
        old = requests.get(f"{api}/getUpdates", timeout=15, params=dict(offset=-1, timeout=0)).json().get("result", [])
        offset = old[-1]["update_id"] + 1 if old else None
    except Exception:
        pass
    while True:
        try:
            r = requests.get(f"{api}/getUpdates", timeout=60,
                             params=dict(timeout=50, offset=offset, allowed_updates='["message"]'))
            if r.status_code != 200:
                if time.time() - warned > 3600:
                    log(f"Telegram commands unavailable (HTTP {r.status_code}"
                        f"{': is another program using the same bot token?' if r.status_code == 409 else ''})")
                    warned = time.time()
                time.sleep(30)
                continue
            for u in r.json().get("result", []):
                offset = u["update_id"] + 1
                m = u.get("message") or {}
                if str((m.get("chat") or {}).get("id")) != chat:
                    continue
                word = (m.get("text") or "").strip().split(" ")[0].split("@")[0].lstrip("/").lower()
                if word in commands:
                    try:
                        _post(commands[word][1]())
                    except Exception as e:
                        _post(f"❗ /{esc(word)} failed: {esc(e)}")
        except Exception:
            time.sleep(10)


# ── formatting ──
def esc(s):
    return html.escape(str(s), quote=False)


def _tz():
    off = os.environ.get("TELEGRAM_UTC_OFFSET")
    if off not in (None, ""):
        try:
            return timezone(timedelta(hours=float(off)))
        except ValueError:
            pass
    return datetime.now().astimezone().tzinfo


def tz_label():
    d = datetime.now(_tz()).utcoffset() or timedelta(0)
    h = d.total_seconds() / 3600
    return "UTC" if h == 0 else f"UTC{h:+g}"


def when(ms, day=True):
    """'Mon 12 Oct 23:15' in the chosen time zone (day=False: '23:15')."""
    t = datetime.fromtimestamp(ms / 1000, _tz())
    return t.strftime("%a %d %b %H:%M") if day else t.strftime("%H:%M")


def px(x, tick=None):
    """A price with the coin's decimals and thousands separators."""
    if tick:
        dec = max(0, len(f"{tick:.10f}".rstrip("0").split(".")[1])) if tick < 1 else 0
    else:
        dec = 2 if abs(x) >= 100 else 4 if abs(x) >= 1 else 6
    return f"{x:,.{dec}f}"


def usd(x, sign=False):
    s = f"{abs(x):,.2f}"
    return (("+" if x >= 0 else "−") if sign else ("−" if x < 0 else "")) + "$" + s


def num(x, dec=2, sign=False):
    return (f"{x:+.{dec}f}" if sign else f"{x:.{dec}f}").replace("-", "−")


def pct(x, sign=False, dec=2):
    return num(x, dec, sign) + "%"


def held(ms):
    m = int(ms // 60_000); d, m = divmod(m, 1440); h, m = divmod(m, 60)
    return f"{d}d {h}h" if d else f"{h}h {m}m" if h else f"{m}m"


class TelegramHandler(logging.Handler):
    """Forwards only warnings and errors (trade events are sent as their own messages). The same message is not
    repeated within 30 minutes, so a network hiccup does not flood the chat."""

    def __init__(self, tag):
        super().__init__(logging.WARNING)
        self.tag, self.seen = tag, {}

    def emit(self, record):
        msg = record.getMessage()
        key = "".join(ch for ch in msg if not ch.isdigit())[:120]
        now = time.time()
        if now - self.seen.get(key, 0) < 1800:
            return
        self.seen[key] = now
        icon = "❗" if record.levelno >= logging.ERROR else "⚠️"
        send(f"{icon} <b>{esc(self.tag)}</b> · {esc(msg)}")
~~~~

### 3.4 `cryptobot/check_setup.py` (241 lines)
~~~~python
"""
Pre-flight check before running live. Places NO orders.
    python check_setup.py            # live keys
    python check_setup.py --testnet  # testnet / demo keys
Checks: keys and permissions (withdrawals must be OFF), position mode, margin mode, balance, clock, the algo-order
endpoint, and for every coin whether the bot's position sizes at your risk settings clear Binance's minimums.
"""
import json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import notify, strategy as S                                    # noqa: E402
from binance_futures import Futures, BinanceError               # noqa: E402
from oi_history import OIHistory                                # noqa: E402

ENV_FILE = notify.load_secrets_env(HERE)
testnet = "--testnet" in sys.argv
ok_all = True


def res(ok, msg, warn=False):
    global ok_all
    if not ok and not warn:
        ok_all = False
    print(f"  [{'OK  ' if ok else 'WARN' if warn else 'FAIL'}] {msg}")


cfgs = [json.loads(p.read_text()) for p in sorted(HERE.glob("config_*.json"))]
key, sec = os.environ.get("BINANCE_API_KEY", ""), os.environ.get("BINANCE_API_SECRET", "")
print(f"TBO pre-flight check ({'TESTNET' if testnet else 'LIVE'}), configs: {[c['strategy']['symbol'] for c in cfgs]}")
res(bool(key and sec), f"API key and secret found ({ENV_FILE or 'environment only: no .env in ' + str(notify.secrets_dir())})")
base = cfgs[0].get("base_url") if cfgs else None
try:
    x = Futures(key, sec, testnet=testnet, base_url=base)
    res(abs(x.offset) < 1000, f"clock offset vs Binance {x.offset} ms" + ("" if abs(x.offset) < 1000 else " (sync your system clock)"), warn=abs(x.offset) < 5000)
except Exception as e:
    res(False, f"cannot reach Binance futures at {base or ('testnet' if testnet else 'fapi.binance.com')}: {e}"); sys.exit(1)
try:
    acct = x.account(); bal = float(acct["totalMarginBalance"]); res(True, f"futures account reachable, balance {bal:.2f} USDT")
    try:                                                            # the user's own isolated trades on non-bot coins
        bots_ = {json.loads(f.read_text())["strategy"]["symbol"] for f in HERE.glob("config_*.json")}
        man = {k: v for k, v in x.isolated_positions().items() if k not in bots_}
        if man:
            bal -= sum(man.values())
            res(True, f"your own isolated trades {', '.join(k[:-4] for k in man)} (margin + P&L ${sum(man.values()):.2f}) are left out: "
                      f"the bots size on {bal:.2f} USDT and do not count them in the open-risk cap")
    except Exception as e:
        res(False, f"isolated positions unreadable ({e})", warn=True)
    res(bal >= 100, "balance at least 100 USDT", warn=True)
except BinanceError as e:
    res(False, f"futures account: {e} (key invalid, futures not enabled for the key, or IP not whitelisted)"); sys.exit(1)
if not testnet:
    try:
        r = x.api_restrictions()
        res(not r.get("enableWithdrawals", True), "withdrawals DISABLED on this key" if not r.get("enableWithdrawals") else "withdrawals are ENABLED on this key: disable them!")
        res(bool(r.get("enableFutures")), "futures trading enabled on this key")
        res(bool(r.get("ipRestrict")), "key restricted to your IP address(es)" if r.get("ipRestrict") else "key NOT IP-restricted (recommended: restrict to the bot's IP)", warn=True)
    except Exception as e:
        res(False, f"could not read key permissions: {e}", warn=True)
try:
    res(not x.hedge_mode(), "position mode One-way" if not x.hedge_mode() else "position mode is Hedge: switch to One-way in Binance Futures settings")
except BinanceError as e:
    res(False, f"position mode: {e}")
try:
    res(not x.multi_assets(), "single-asset margin (USDT)" if not x.multi_assets() else "multi-assets mode is ON (fine, but sizing uses total margin balance)", warn=True)
except Exception:
    pass
total_risk = 0.0; total_notional = 0.0
pf_path = Path(__file__).resolve().parent / "portfolio.json"
pf = json.loads(pf_path.read_text()) if pf_path.exists() else {}
# the bot sizes on this account + the panic sleeve's sub-account when its key is set (bot.equity, one pool)
eq, sub_bal = bal, None
if os.environ.get("PANIC_API_KEY") and os.environ.get("PANIC_API_SECRET") and pf.get("pool_panic_balance", True):
    try:
        sub_bal = float(Futures(os.environ["PANIC_API_KEY"], os.environ["PANIC_API_SECRET"], testnet=testnet).account()["totalMarginBalance"])
        eq = bal + sub_bal
        print(f" sizing balance: main ${bal:,.2f} + panic sub-account ${sub_bal:,.2f} = ${eq:,.2f} (the bot sizes on both)")
    except Exception as e:
        res(False, f"panic sub-account balance unreadable ({e}): sizes below use the main balance only", warn=True)
row = None
for r in sorted(pf.get("risk_ladder") or [], key=lambda r: float(r["from_usdt"])):
    if eq >= float(r["from_usdt"]):
        row = r
if pf.get("risk_ladder"):
    print(" risk ladder (portfolio.json), risk % by balance: " + " | ".join(
        f"from ${float(r['from_usdt']):,.0f}: BTC {r.get('BTCUSDT')} ETH {r.get('ETHUSDT')} alts {r.get('ADAUSDT')} cap {r.get('cap_pct')}"
        for r in sorted(pf["risk_ladder"], key=lambda r: float(r["from_usdt"]))))
    print(f" -> at your balance ${eq:,.2f} the row from ${float(row['from_usdt']):,.0f} applies" if row else " -> no row applies: config risk_pct")
for c in cfgs:
    p = S.Params(**c["strategy"]); sym = p.symbol; sm = c.get("short_risk_mult", 1.0)
    c = dict(c, risk_pct=float(row[sym]) if row and sym in row else c["risk_pct"])
    risk = c["risk_pct"] / 100
    total_risk += risk
    print(f" {sym}: risk {c['risk_pct']}% (shorts x{sm}), size cap {c.get('max_leverage')}x balance, Binance leverage {c.get('exchange_leverage', c.get('max_leverage'))}x")
    try:
        f = x.exchange_info(sym); res(f["status"] == "TRADING", f"{sym} listed and trading")
        k4 = [k for k in x.klines(sym, "4h", 1001) if k[5] < x.now_ms()][-1000:]
        a = S.atr([k[2] for k in k4], [k[3] for k in k4], [k[4] for k in k4], p.atr_n)[-1]; px = k4[-1][4]
        dist = p.sl_atr * a
        for side, m in (("long", 1.0), ("short", sm)):
            qty = eq * risk * m / dist
            qty = min(qty, eq * c.get("max_leverage", 5) / px)
            qr = int(qty / max(f["step"], f["mkt_step"]) + 1e-9) * max(f["step"], f["mkt_step"])
            okq = qr >= f["min_qty"] and qr * px >= f["min_notional"]
            if side == "long":
                total_notional += qr * px / c.get("exchange_leverage", c.get("max_leverage", 5))
            res(okq, f"{side}: stop {dist / px * 100:.2f}% away -> {qr:g} {sym[:-4]} (${qr * px:,.0f} notional, risk ${qr * dist:.2f}; "
                     f"min {f['min_qty']:g} / ${f['min_notional']:g})" + ("" if okq else " -> too small: this trade would be skipped"), warn=not okq)
            if okq and qr * dist < 0.75 * eq * risk * m:
                res(False, f"{side}: rounding cuts the risk to ${qr * dist:.2f} of ${eq * risk * m:.2f} (step {f['step']:g})", warn=True)
        if p.vr_mult < 1.0:                             # v3.2 wild-pullback size (decided at each 4h arming close)
            k1 = [k for k in x.klines(sym, "1d", 1500) if k[5] < x.now_ms()][-1499:]
            vr, chg5 = S.vol_regime([k[2] for k in k1], [k[3] for k in k1], [k[4] for k in k1])
            if vr is None:
                res(False, f"v3.2 wild-pullback size: only {len(k1)} daily candles (need 101): not applied yet", warn=True)
            else:
                now_ = [sd for sd, s_ in (("longs", 1), ("shorts", -1)) if S.size_mult(p, s_, vr, chg5) < 1.0]
                q_ = max(f["min_qty"], int(f["min_notional"] / px / max(f["step"], f["mkt_step"]) + 1 - 1e-9) * max(f["step"], f["mkt_step"]))
                res(True, f"v3.2 wild-pullback size: daily ATR14/ATR100 {vr:.3f} (>= {p.vr_min:g}?), 5-day move {chg5:+.2f} ATR -> "
                          + (f"{' and '.join(now_)} armed today at x{p.vr_mult:g} risk" if now_ else "full size today")
                          + f"; a x{p.vr_mult:g} order below Binance's minimum is raised to {q_:g} {sym[:-4]} (${q_ * px:,.0f})")
        try:
            sc = x.symbol_config(sym); mt = str(sc.get("marginType", "?")).upper()
            res(mt in ("CROSSED", "CROSS"), f"margin type {mt}" + ("" if mt in ("CROSSED", "CROSS") else " (recommended: cross)"), warn=True)
        except Exception:
            pass
        x.open_algo_orders(sym); res(True, f"algo-order endpoint reachable for {sym}")
        if p.oi_lookback_h > 0:
            try:
                hist = x.open_interest_hist(sym, limit=p.oi_lookback_h + 12)
                chg = S.oi_change(hist, x.now_ms(), p.oi_lookback_h)
                res(chg is not None, f"open interest data: {len(hist)} hourly rows" + (
                    f", {chg * 100:+.1f}% over {p.oi_lookback_h} h -> " + ("new entries PAUSED by the filter right now" if S.oi_blocks(p, chg)
                                                                          else "entries allowed") if chg is not None else
                    " but not enough recent rows (the filter is skipped until there are)"), warn=chg is None)
            except Exception as e:
                res(False, f"open interest data unavailable ({e}): the bot then trades without the filter", warn=True)
        if p.oi_low_days > 0:                           # also fills the bot's cache (oi_<SYMBOL>.json)
            try:
                h = OIHistory(x, sym, p.oi_low_days, HERE, "_testnet" if testnet else "")
                h.update(budget_s=180)
                rank = S.oi_rank(h.series(), x.now_ms(), p.oi_low_days * 24, p.oi_low_days * 12)
                res(rank is not None, f"open interest history: {h.hours()} hours (need {p.oi_low_days * 12} of {p.oi_low_days * 24})" + (
                    f", now at {rank * 100:.0f}% of its {p.oi_low_days}-day range -> " + ("new entries PAUSED by the OI-low filter right now"
                                                                                     if S.oi_low_blocks(p, rank) else "entries allowed")
                    if rank is not None else ": data.binance.vision unreachable? the bot trades without the OI-low filter until it loads"),
                    warn=rank is None)
            except Exception as e:
                res(False, f"open interest history unavailable ({e}): the bot then trades without the OI-low filter", warn=True)
    except BinanceError as e:
        res(False, f"{sym}: {e}")
print(f" all coins in a trade at once: up to {total_risk * 100:.2f}% of the balance at risk (${eq * total_risk:.2f})")
cap = float(row["cap_pct"]) if row and "cap_pct" in row else float(pf.get("open_risk_cap_pct", 0) or 0)
if cap > 0:
    ex = [c["strategy"]["symbol"] for c in cfgs if c["strategy"]["symbol"] in pf.get("cap_exempt", [])]
    rk = lambda c: float(row[c["strategy"]["symbol"]]) if row and c["strategy"]["symbol"] in row else c["risk_pct"]
    capped = [rk(c) for c in cfgs if c["strategy"]["symbol"] not in ex] or [0]
    btc = next((rk(c) for c in cfgs if c["strategy"]["symbol"] == "BTCUSDT"), None)
    print(f" open-risk cap (portfolio.json): {cap:g}% of the balance (${eq * cap / 100:.2f})"
          + (f" = {cap / btc:.2f} x the BTC risk (tested best: about 1.1x)" if btc else "") + f"; never shrunk: {', '.join(ex) or 'none'}")
    res(cap >= max(capped), f"cap {cap:g}% vs the biggest capped coin risk {max(capped):g}%" + ("" if cap >= max(capped) else
        " -> that coin could never trade full size: raise the cap (about 1.1 x the BTC risk)"), warn=cap < max(capped))
    try:
        x.positions(); x.open_algo_orders(); res(True, "all-symbol position / order endpoints reachable (needed by the cap)")
    except BinanceError as e:
        res(False, f"all-symbol position / order endpoints: {e} (the cap then blocks new alt / ETH orders)")
else:
    print(" open-risk cap: off (no portfolio.json or open_risk_cap_pct 0)")
if bal > 0:
    res(total_notional < 0.8 * bal, f"margin locked if all coins are long at today's stops: ${total_notional:.2f} of ${bal:.2f} (main account)"
        + ("" if total_notional < 0.8 * bal else " (raise exchange_leverage in the configs)"), warn=True)
pk, ps = os.environ.get("PANIC_API_KEY", ""), os.environ.get("PANIC_API_SECRET", "")
if pk and ps:
    print("\nPANIC SLEEVE (sub-account, panic.py)")
    try:
        import panic as PN
        pcfg = PN.load_cfg()
        y = Futures(pk, ps, testnet=testnet)
        sub = float(y.account()["totalMarginBalance"]); res(True, f"sub-account reachable, balance {sub:.2f} USDT")
        if not testnet:
            r = y.api_restrictions()
            res(not r.get("enableWithdrawals", True), "withdrawals DISABLED on the sub-account key" if not r.get("enableWithdrawals") else "withdrawals ENABLED on the sub-account key: disable them!")
            res(bool(r.get("enableFutures")), "futures trading enabled on the sub-account key")
            res(bool(r.get("ipRestrict")), "sub-account key restricted to your IP" if r.get("ipRestrict") else "sub-account key NOT IP-restricted (recommended)", warn=True)
        res(not y.hedge_mode(), "sub-account position mode One-way" if not y.hedge_mode() else "sub-account is in Hedge mode: switch it to One-way")
        total = bal + sub
        res(sub >= 0.15 * total, f"sub-account holds {sub / total * 100:.0f}% of main + sub (${total:.2f}); 20-30% recommended"
            + ("" if sub >= 0.15 * total else " -> move more to the sub-account (panic trades are sized on main + sub)"), warn=True)
        btc = PN.ladder_btc_pct(total); units = float(pcfg.get("units", 3))
        risk = total * btc / 100 * units / 6
        print(f" {units:g} units per panic event = {units / 6 * btc:.2f}% of ${total:.2f} = ${risk:.2f} lost on a 5% move; position ${risk / 0.05:.2f}"
              f" (split over the coins that trigger in the same hour)")
        ml = float(pcfg.get("max_leverage", 4))
        res(risk / 0.05 <= sub * ml, f"panic position ${risk / 0.05:.2f} = {risk / 0.05 / max(sub, 1e-9):.1f}x the sub-account (limit {ml:g}x; Binance allows sub-accounts 5x)"
            + ("" if risk / 0.05 <= sub * ml else " -> it will be cut to the limit: move more to the sub-account"), warn=True)
        for sym in pcfg["coins"]:
            f = y.exchange_info(sym)
            for n in (1, 2):
                res(risk / 0.05 / n >= f["min_notional"], f"{sym} panic position with {n} coin(s) in the event: ${risk / 0.05 / n:.2f} vs Binance minimum ${f['min_notional']:g}",
                    warn=True)
        sh = float(pcfg.get("extra_share", 0.75))                  # v3.0 extra coins: their own pool, at most max_extra_open open
        for sym in pcfg.get("extra_coins", []):
            f = y.exchange_info(sym)
            for n in (1, 2):
                res(risk * sh / 0.05 / n >= f["min_notional"], f"{sym} (extra coin, {sh:g}x units) panic position with {n} extra coin(s) in the event: "
                    f"${risk * sh / 0.05 / n:.2f} vs Binance minimum ${f['min_notional']:g}", warn=True)
        try:
            y.open_algo_orders(); x.premium_klines("BTCUSDT", "1h", 5); x.open_interest_hist("BTCUSDT", period="5m", limit=5)
            res(True, "algo orders, premium index and 5-minute open interest reachable")
        except BinanceError as e:
            res(False, f"panic data / orders: {e}")
    except BinanceError as e:
        res(False, f"sub-account: {e} (key invalid, futures not enabled for the key, or IP not whitelisted)")
    except Exception as e:
        res(False, f"panic sleeve check failed: {e}")
else:
    print("\nPANIC SLEEVE: off (no PANIC_API_KEY / PANIC_API_SECRET in .env)")
try:                                                     # v3.1 VOLC sleeve (volc.py) on this main account
    vcfg = json.loads((HERE / "volc.json").read_text())
except (OSError, ValueError):
    vcfg = {}
if vcfg.get("enabled"):
    print("\nVOLC SLEEVE (main account, volc.py)")
    try:
        btc = float(row["BTCUSDT"]) if row and "BTCUSDT" in row else float(json.loads((HERE / "config_btc.json").read_text())["risk_pct"])
        share = float(vcfg.get("share", 0.25)); vrisk = eq * btc / 100 * share
        print(f" risk per VOLC trade: {share:g} x the BTC risk {btc:g}% = {btc * share:.2f}% of ${eq:,.2f} = ${vrisk:.2f}; outside the open-risk cap")
        for sym in vcfg.get("coins", []):
            f = x.exchange_info(sym)
            k4 = x.klines(sym, "4h", 200)
            a = float(S.atr([k[2] for k in k4], [k[3] for k in k4], [k[4] for k in k4], 14)[-1])
            px = k4[-1][4]
            stp = max(f["step"], f["mkt_step"]); qty = round(int(vrisk / a / stp + 1e-9) * stp, 12)
            res(qty >= f["min_qty"] and qty * px >= f["min_notional"], f"{sym} VOLC trade at today's 4h ATR (stop {a / px * 100:.2f}%): {qty:g} "
                f"(${qty * px:,.0f} = {qty * px / max(bal, 1e-9):.1f}x the main balance) vs Binance minimum ${f['min_notional']:g}", warn=True)
    except Exception as e:
        res(False, f"VOLC sleeve check failed: {e}", warn=True)
else:
    print("\nVOLC SLEEVE: off (volc.json missing or \"enabled\": false)")
print("RESULT:", "ready" if ok_all else "fix the FAIL lines first")
~~~~

### 3.5 `cryptobot/vds_setup.sh` (65 lines)
~~~~bash
#!/bin/bash
# TBO server install / update, run as root by tbo_servers.bat (Ubuntu 22.04 / 24.04).
# Safe to run again: keeps .env, the state files and the logs. The bot files come from /root/cryptobot.tgz (sent by
# tbo_install.bat: only the cryptobot folder, never secrets/). A server that was set up as a git clone is switched to
# this once: everything in /home/tbo/trade3 except cryptobot/ (research, data, reports, .git) is removed from it.
# Without a package a git clone still updates itself with git pull.
set -e
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
PKG=/root/cryptobot.tgz
D=/home/tbo/trade3/cryptobot

if ! id tbo >/dev/null 2>&1; then
  echo "== first install: system update and Python (a few minutes)"
  apt-get update -qq
  apt-get -y -qq -o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef upgrade
  apt-get -y -qq install python3 python3-venv
  timedatectl set-ntp true || true
  adduser --disabled-password --gecos "" tbo
fi

mkdir -p /home/tbo/trade3
if [ -f "$PKG" ]; then
  if [ -d /home/tbo/trade3/.git ]; then
    echo "== switching this server from git to package updates: only the bot folder stays on the server"
    find /home/tbo/trade3 -mindepth 1 -maxdepth 1 ! -name cryptobot -exec rm -rf {} +
  fi
  echo "== copying the bot files"
  tar xzf "$PKG" -C /home/tbo/trade3
elif [ -d /home/tbo/trade3/.git ]; then
  echo "== this server uses git: pulling the latest code"
  sudo -u tbo git -C /home/tbo/trade3 pull
fi
rm -f "$PKG"
rm -rf "$D/secrets"                                  # the installers' private files never stay on a server

if [ -f /root/tbo.env ]; then
  mv /root/tbo.env "$D/.env"
fi
chown -R tbo:tbo /home/tbo/trade3
if [ -f "$D/.env" ]; then
  sed -i 's/\r$//' "$D/.env"
  chmod 600 "$D/.env"
fi

cd "$D"
if [ ! -x venv/bin/python ]; then
  echo "== creating the Python environment"
  sudo -u tbo python3 -m venv venv
fi
sudo -u tbo venv/bin/pip install -q --disable-pip-version-check -r requirements.txt

sed -e 's/\r$//' -e 's#/usr/bin/python3#/home/tbo/trade3/cryptobot/venv/bin/python#' tbo.service > /etc/systemd/system/tbo.service
systemctl daemon-reload
ufw allow OpenSSH >/dev/null 2>&1 && ufw --force enable >/dev/null 2>&1 || true

sed -i 's/\r$//' "$D/server_clean.sh" 2>/dev/null || true
bash "$D/server_clean.sh" --install >/dev/null 2>&1 || true
echo "== weekly cleanup installed"

if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes; then
  echo "== clock synchronized"
else
  echo "== clock not synchronized yet (it usually is within a minute)"
fi
echo "== done"
~~~~

### 3.6 `cryptobot/tbo_install.bat` (301 lines)
~~~~bat
@echo off
rem TBO installer (Windows): installs and updates the bot on Ubuntu servers (VDS / VPS) from this PC.
rem   MY SERVER     : your own server (its IP is asked once and kept in my_server.txt in TBO_SECRETS_DIR)
rem   OTHER PEOPLE  : friends' servers (name + IP kept in servers.txt in TBO_SECRETS_DIR); each one trades with his OWN Binance keys
rem The first contact with a server asks its root password once; after that this PC logs in with its SSH key.
rem Updates: git pull on this PC, then the code is sent to the server (no GitHub access on friends' servers);
rem the server's .env, state files and logs are never touched. A server that has a git checkout pulls by itself.
setlocal EnableExtensions EnableDelayedExpansion
title TBO installer
cd /d "%~dp0"
rem Private files live OUTSIDE the repo, in the folder TBO_SECRETS_DIR (default %USERPROFILE%\tbo-secrets):
rem   tbo_key = the servers' SSH private key, my_server.txt = my server's IP, servers.txt = other people's servers
if not defined TBO_SECRETS_DIR set "TBO_SECRETS_DIR=%USERPROFILE%\tbo-secrets"
if not exist "!TBO_SECRETS_DIR!\" (
  echo.
  echo   ERROR: the secrets folder was not found: !TBO_SECRETS_DIR!
  echo   Create it and put tbo_key in it, or set TBO_SECRETS_DIR to the folder that has your private files.
  echo   See "Private files" in README.md.
  echo.
  pause
  exit /b 1
)
set "MINE=!TBO_SECRETS_DIR!\my_server.txt"
set "REPOKEY=!TBO_SECRETS_DIR!\tbo_key"
if not exist "!REPOKEY!" (
  echo.
  echo   ERROR: SSH key not found: !REPOKEY!
  echo   Put the servers' SSH private key there as tbo_key, or set TBO_SECRETS_DIR. See "Private files" in README.md.
  echo.
  pause
  exit /b 1
)
rem the SSH key is copied to this PC's .ssh folder (Windows ssh refuses keys with loose file rights)
if not exist "%USERPROFILE%\.ssh" mkdir "%USERPROFILE%\.ssh"
copy /y "!REPOKEY!" "%USERPROFILE%\.ssh\tbo_repo_key" >nul
set "LIST=!TBO_SECRETS_DIR!\servers.txt"
set "KEY=%USERPROFILE%\.ssh\id_ed25519"
set "SSHO=-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -i "%USERPROFILE%\.ssh\tbo_repo_key""

if /i "%~1"=="update-mine" (
  set "MYIP="
  if exist "%MINE%" set /p MYIP=<"%MINE%"
  call :myip && call :update
  exit /b
)

:main
set "MYIP="
if exist "%MINE%" set /p MYIP=<"%MINE%"
cls
echo.
echo   TBO installer
echo   =============
echo.
if defined MYIP (echo   MY SERVER  ^(!MYIP!^)) else (echo   MY SERVER  ^(not set yet^))
echo    1  Update my bot  ^(latest code^) + restart
echo    2  Check my setup  ^(check_setup.py^)
echo    3  Set up my server from scratch  ^(new or reinstalled server^)
echo    8  Add / change my panic sleeve key  ^(Binance sub-account^)
echo.
echo   OTHER PEOPLE'S SERVERS
echo    4  Set up a new person's server
echo    5  Update someone's bot
echo    6  Manage someone's server  ^(live output, status, restart, stop / start ...^)
echo.
echo    7  Update ALL bots  ^(mine + everyone's^)
echo    0  Exit
echo.
set "c="
set /p "c=  Choose: "
if "!c!"=="1" ( call :myip && call :update )
if "!c!"=="2" ( call :myip && call :check )
if "!c!"=="3" ( call :myip && call :setup )
if "!c!"=="4" ( call :addserver && call :setup )
if "!c!"=="5" ( call :pickserver && call :update )
if "!c!"=="6" ( call :pickserver && goto manage )
if "!c!"=="7" call :updateall
if "!c!"=="8" ( call :myip && call :panickey )
if "!c!"=="0" exit /b
echo.
pause
goto main

rem ── my server's IP (asked once) ──
:myip
if not defined MYIP (
  echo   my_server.txt not found: !MINE!
  echo   Type your server's IP once; it is saved there.
  set /p "MYIP=  Your own server's IP address: "
  if "!MYIP!"=="" exit /b 1
  >"%MINE%" echo !MYIP!
)
set "IP=!MYIP!"
set "NAME=my server"
exit /b 0

rem ── other people's servers ──
:addserver
echo.
set "NAME="
set /p "NAME=  A one-word name for this person (e.g. Ali): "
set "IP="
set /p "IP=  The IP address of his server: "
if "!NAME!"=="" exit /b 1
if "!IP!"=="" exit /b 1
>>"%LIST%" echo !NAME! !IP!
exit /b 0

:pickserver
echo.
set n=0
if exist "%LIST%" for /f "usebackq tokens=1,2" %%a in ("%LIST%") do (
  set /a n+=1
  set "SNAME!n!=%%a"
  set "SIP!n!=%%b"
  echo    !n!  %%a  ^(%%b^)
)
if !n!==0 (
  if not exist "!LIST!" echo   servers.txt not found: !LIST!
  echo   No servers yet: use 4 to set one up.
  exit /b 1
)
set "s="
set /p "s=  Which one: "
if "!s!"=="" exit /b 1
if not defined SIP!s! exit /b 1
set "IP=!SIP%s%!"
set "NAME=!SNAME%s%!"
exit /b 0

:manage
cls
echo.
echo   TBO on !NAME!  (root@!IP!)
echo   ------------------------------------------
echo    1  Live output  (Ctrl+C to come back here)
echo    2  Status + memory
echo    3  Restart the bot
echo    4  Stop the bot
echo    5  Start the bot
echo    6  Check the setup  (check_setup.py)
echo    7  Update the bot  (latest code) + restart
echo    8  Server terminal
echo    9  Add / change the panic sleeve key  ^(Binance sub-account^)
echo    B  Back
echo.
set "c="
set /p "c=  Choose: "
if "!c!"=="1" ssh -t %SSHO% root@!IP! "journalctl -u tbo -f -o cat _SYSTEMD_INVOCATION_ID=$(systemctl show -p InvocationID --value tbo)"
if "!c!"=="2" ssh -t %SSHO% root@!IP! "systemctl status tbo --no-pager | head -12; echo; free -h; echo; uptime"
if "!c!"=="3" ssh -t %SSHO% root@!IP! "systemctl restart tbo && echo Bot restarted."
if "!c!"=="4" call :stop
if "!c!"=="5" ssh -t %SSHO% root@!IP! "systemctl enable --now tbo && echo Bot started."
if "!c!"=="6" call :check
if "!c!"=="7" call :update
if "!c!"=="8" ssh -t %SSHO% root@!IP!
if "!c!"=="9" call :panickey
if /i "!c!"=="B" goto main
echo.
pause
goto manage

rem ── this PC's SSH key on the server (asks the root password only the first time) ──
:ensurekey
if not exist "%KEY%" (
  echo   Creating an SSH key for this PC ^(only once^)...
  if not exist "%USERPROFILE%\.ssh" mkdir "%USERPROFILE%\.ssh"
  ssh-keygen -q -t ed25519 -N "" -f "%KEY%"
)
ssh -o BatchMode=yes %SSHO% root@!IP! "true" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Type the ROOT PASSWORD of !IP! ^(only this once; nothing shows while you type^):
  type "%KEY%.pub" | ssh %SSHO% root@!IP! "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && sort -u -o ~/.ssh/authorized_keys ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
)
ssh -o BatchMode=yes %SSHO% root@!IP! "true" >nul 2>&1
if errorlevel 1 (
  echo   Could not log in to !IP!. Check the IP and the password and try again.
  exit /b 1
)
exit /b 0

rem ── package this PC's bot folder (after git pull), without keys, state files, logs or venv ──
:pkg
if defined PKGDONE exit /b 0
set "ROOT=%~dp0.."
if exist "%ROOT%\.git" (
  echo   Getting the latest code from GitHub on this PC...
  git -C "%ROOT%" pull
)
set "PKG=%TEMP%\cryptobot.tgz"
del "%PKG%" >nul 2>&1
tar -czf "%PKG%" --exclude=venv --exclude=.env --exclude="state_*" --exclude=logs --exclude=__pycache__ --exclude=trial_results --exclude=PAUSE --exclude=servers.txt --exclude=my_server.txt --exclude=secrets --exclude="*.tmp" --exclude=dev -C "%ROOT%" cryptobot
if errorlevel 1 (
  echo   Could not build the package.
  exit /b 1
)
exit /b 0

:setup
call :ensurekey || exit /b
ssh -o BatchMode=yes %SSHO% root@!IP! "test -f /home/tbo/trade3/cryptobot/.env" >nul 2>&1
if not errorlevel 1 (
  echo.
  echo   !NAME! ^(!IP!^) is already set up ^(it has its keys^). For the latest code use Update instead.
  set "y="
  set /p "y=  Replace its Binance / Telegram keys and set it up again anyway? Type y to continue: "
  if /i not "!y!"=="y" exit /b
)
echo.
echo   The keys of the person who trades on this server ^(HIS OWN Binance account^):
set "AK=" & set /p "AK=  Binance API key: "
set "AS=" & set /p "AS=  Binance API secret: "
set "TT=" & set /p "TT=  Telegram bot token (Enter to skip): "
set "TC=" & set /p "TC=  Telegram chat id (Enter to skip): "
echo   Optional: the panic sleeve's Binance SUB-ACCOUNT key ^(Enter to skip; can be added later^)
set "PK=" & set /p "PK=  Sub-account API key: "
set "PS=" & set /p "PS=  Sub-account API secret: "
if "!AK!"=="" ( echo   No API key given: setup cancelled. & exit /b )
set "ENVF=%TEMP%\tbo.env"
> "%ENVF%" (
  echo BINANCE_API_KEY=!AK!
  echo BINANCE_API_SECRET=!AS!
  echo TELEGRAM_TOKEN=!TT!
  echo TELEGRAM_CHAT_ID=!TC!
  echo TELEGRAM_UTC_OFFSET=3
  if not "!PK!"=="" echo PANIC_API_KEY=!PK!
  if not "!PK!"=="" echo PANIC_API_SECRET=!PS!
)
call :pkg || ( del "%ENVF%" >nul 2>&1 & exit /b )
echo   Uploading...
scp %SSHO% "%PKG%" "%~dp0vds_setup.sh" "%ENVF%" root@!IP!:/root/
del "%ENVF%" >nul 2>&1
echo   Installing ^(2-5 minutes on a new server^)...
ssh -t %SSHO% root@!IP! "sed -i 's/\r$//' /root/vds_setup.sh && bash /root/vds_setup.sh"
echo.
echo   ==========================================================================
echo    Now, in Binance: API Management - this API key - Edit restrictions -
echo    "Restrict access to trusted IPs only" - add  !IP!  - Save.
echo   ==========================================================================
pause
call :check
echo.
set "y="
set /p "y=  Did it end with RESULT: ready?  Start the bot now (y/n): "
if /i "!y!"=="y" ssh -t %SSHO% root@!IP! "systemctl enable --now tbo && echo Bot started. Waiting 30 s for its first lines... && sleep 30 && journalctl -u tbo -o cat --no-pager -n 25"
exit /b

:update
call :ensurekey || exit /b
call :pkg || exit /b
echo   Updating !NAME! ^(!IP!^)...
scp %SSHO% "%PKG%" "%~dp0vds_setup.sh" root@!IP!:/root/
ssh -t %SSHO% root@!IP! "sed -i 's/\r$//' /root/vds_setup.sh && bash /root/vds_setup.sh && systemctl restart tbo && echo Bot updated and restarted."
exit /b

:updateall
call :pkg || exit /b
set "PKGDONE=1"
if not exist "!MINE!" echo   my_server.txt not found: !MINE!  ^(skipping my server^)
if not exist "!LIST!" echo   servers.txt not found: !LIST!  ^(skipping other people's servers^)
if exist "%MINE%" (
  set /p MYIP=<"%MINE%"
  set "IP=!MYIP!" & set "NAME=my server"
  echo. & echo   ===== my server ^(!IP!^) =====
  call :update
)
if exist "%LIST%" for /f "usebackq tokens=1,2" %%a in ("%LIST%") do (
  set "NAME=%%a" & set "IP=%%b"
  echo. & echo   ===== %%a ^(%%b^) =====
  call :update
)
set "PKGDONE="
exit /b

:check
ssh -t %SSHO% root@!IP! "cd /home/tbo/trade3/cryptobot && sudo -u tbo venv/bin/python check_setup.py"
exit /b

rem ── the panic sleeve's sub-account key into the server's .env (replaces an old one), then restart ──
:panickey
call :ensurekey || exit /b
echo.
echo   In Binance: create a sub-account, enable Futures on it, move 20-30%% of the balance there, and create an
echo   API key FOR THE SUB-ACCOUNT ^(Enable Futures, NO withdrawals, restricted to !IP!^).
set "PK=" & set /p "PK=  Sub-account API key (Enter = remove the panic sleeve): "
set "PS="
if not "!PK!"=="" set /p "PS=  Sub-account API secret: "
if "!PK!"=="" (
  ssh -t %SSHO% root@!IP! "cd /home/tbo/trade3/cryptobot && sed -i '/^PANIC_API_/d' .env && systemctl restart tbo && echo Panic sleeve removed, bot restarted."
) else (
  ssh -t %SSHO% root@!IP! "cd /home/tbo/trade3/cryptobot && sed -i '/^PANIC_API_/d' .env && echo PANIC_API_KEY=!PK! >> .env && echo PANIC_API_SECRET=!PS! >> .env && chown tbo:tbo .env && chmod 600 .env && systemctl restart tbo && echo Panic sleeve key saved, bot restarted."
  call :check
)
exit /b

:stop
set "y="
set /p "y=  Stop the bot on !NAME!? No new orders; open trades keep their stop loss on Binance. Type y to confirm: "
if /i "!y!"=="y" ssh -t %SSHO% root@!IP! "systemctl stop tbo && echo Bot stopped."
exit /b
~~~~

### 3.7 `cryptobot/TBO-VDS.bat` (78 lines)
~~~~bat
@echo off
rem Day-to-day control of the bot on MY server (watch, status, restart, update, stop / start).
rem The server's IP is kept in my_server.txt in TBO_SECRETS_DIR, outside the repo (shared with tbo_install.bat;
rem asked once if missing). The SSH key tbo_key is read from the same folder.
setlocal EnableExtensions EnableDelayedExpansion
title TBO bot on the VDS
cd /d "%~dp0"
rem Private files live OUTSIDE the repo, in the folder TBO_SECRETS_DIR (default %USERPROFILE%\tbo-secrets):
rem   tbo_key = the servers' SSH private key, my_server.txt = my server's IP, servers.txt = other people's servers
if not defined TBO_SECRETS_DIR set "TBO_SECRETS_DIR=%USERPROFILE%\tbo-secrets"
if not exist "!TBO_SECRETS_DIR!\" (
  echo.
  echo   ERROR: the secrets folder was not found: !TBO_SECRETS_DIR!
  echo   Create it and put tbo_key in it, or set TBO_SECRETS_DIR to the folder that has your private files.
  echo   See "Private files" in README.md.
  echo.
  pause
  exit /b 1
)
set "MINE=!TBO_SECRETS_DIR!\my_server.txt"
set "REPOKEY=!TBO_SECRETS_DIR!\tbo_key"
if not exist "!REPOKEY!" (
  echo.
  echo   ERROR: SSH key not found: !REPOKEY!
  echo   Put the servers' SSH private key there as tbo_key, or set TBO_SECRETS_DIR. See "Private files" in README.md.
  echo.
  pause
  exit /b 1
)
rem the SSH key is copied to this PC's .ssh folder (Windows ssh refuses keys with loose file rights)
if not exist "%USERPROFILE%\.ssh" mkdir "%USERPROFILE%\.ssh"
copy /y "!REPOKEY!" "%USERPROFILE%\.ssh\tbo_repo_key" >nul
set "SSHI=-i "%USERPROFILE%\.ssh\tbo_repo_key""
set "MYIP="
if exist "%MINE%" set /p MYIP=<"%MINE%"
if not defined MYIP (
  echo   my_server.txt not found: !MINE!
  echo   Type your server's IP once; it is saved there.
  set /p "MYIP=  Your server's IP address: "
  if "!MYIP!"=="" exit /b
  >"%MINE%" echo !MYIP!
)
set "HOST=root@!MYIP!"
:menu
cls
echo.
echo   TBO bot on the VDS  (!HOST!)
echo   ------------------------------------------
echo    1  Live output  (Ctrl+C to come back here)
echo    2  Last 200 lines
echo    3  Status + memory
echo    4  Restart the bot
echo    5  Update (latest code from GitHub, sent as the bot folder) + restart
echo    6  Stop the bot
echo    7  Start the bot
echo    8  Open a server terminal
echo    9  Clean up the server  (old logs, caches; also sets up the weekly cleanup)
echo    0  Exit
echo.
set "c="
set /p "c=  Choose: "
if "!c!"=="1" ssh -t !SSHI! !HOST! "journalctl -u tbo -f -o cat _SYSTEMD_INVOCATION_ID=$(systemctl show -p InvocationID --value tbo)"
if "!c!"=="2" ssh -t !SSHI! !HOST! "journalctl -u tbo -o cat --no-pager _SYSTEMD_INVOCATION_ID=$(systemctl show -p InvocationID --value tbo) | tail -200"
if "!c!"=="3" ssh -t !SSHI! !HOST! "systemctl status tbo --no-pager | head -12; echo; free -h; echo; uptime"
if "!c!"=="4" ssh -t !SSHI! !HOST! "systemctl restart tbo && echo Bot restarted."
if "!c!"=="5" call "%~dp0tbo_install.bat" update-mine
if "!c!"=="6" (
  set "y="
  set /p "y=  Stop the bot? No new orders; open trades keep their stop loss on Binance. Type y to confirm: "
  if /i "!y!"=="y" ssh -t !SSHI! !HOST! "systemctl stop tbo && echo Bot stopped."
)
if "!c!"=="7" ssh -t !SSHI! !HOST! "systemctl start tbo && echo Bot started."
if "!c!"=="8" ssh -t !SSHI! !HOST!
if "!c!"=="9" ssh -t !SSHI! !HOST! "sed -i 's/\r$//' /home/tbo/trade3/cryptobot/server_clean.sh; bash /home/tbo/trade3/cryptobot/server_clean.sh --install"
if "!c!"=="0" exit /b
echo.
pause
goto menu
~~~~

### 3.8 `cryptobot/tbo.service` (16 lines)
~~~~ini
# Linux (systemd): copy to /etc/systemd/system/tbo.service, adjust User and paths, then:
#   sudo systemctl daemon-reload && sudo systemctl enable --now tbo && journalctl -u tbo -f
[Unit]
Description=TBO crypto bots (Binance USD-M futures)
After=network-online.target
Wants=network-online.target

[Service]
User=tbo
WorkingDirectory=/home/tbo/trade3/cryptobot
ExecStart=/usr/bin/python3 /home/tbo/trade3/cryptobot/run_all.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
~~~~

### 3.9 Install-script checks (computed from the files above)

* `tbo_install.bat` packages `cryptobot/` with: `--exclude=venv --exclude=.env --exclude=state_* --exclude=logs --exclude=__pycache__ --exclude=trial_results --exclude=PAUSE --exclude=servers.txt --exclude=my_server.txt --exclude=secrets --exclude=*.tmp --exclude=dev`. Applying those patterns to the 39 tracked files of `cryptobot/` ships **29** of them.
* Required runtime files all in the package (volc.py, volc_signal.py, volc.json, panic*, portfolio.json, config_*.json, bot / strategy / run_all, notify, check_setup, requirements...): PASS
* `.env` excluded from the package: PASS; `state_*` (state_*.json, e.g. `state_volc.json`) excluded: PASS; logs, venv, secrets, PAUSE excluded: PASS; `dev` (tests) not shipped: PASS
* On the server `vds_setup.sh` extracts with `tar xzf "$PKG" -C /home/tbo/trade3` (adds / overwrites package files only; it cannot touch `.env` or `state_*` because they are not in the package): PASS
* `.env` is only written from `/root/tbo.env`, which `tbo_install.bat` uploads only in the Setup path (new server, or after the user typed `y` to replace the keys); the Update paths upload the package only: PASS
* The only deletion of existing server files is `find /home/tbo/trade3 -mindepth 1 -maxdepth 1 ! -name cryptobot -exec rm -rf {} +`, guarded by `[ -d /home/tbo/trade3/.git ]` (a git-checkout server switching to package updates): it removes everything **except** the `cryptobot/` folder, so `.env` and `state_*.json` inside `cryptobot/` survive: PASS
* `vds_setup.sh` removes `$D/secrets` (installer-private files never stay on the server) and only `chmod 600`s `.env`: PASS
* `tbo.service` runs `run_all.py` (which starts the coin bots, panic and the VOLC sleeve when `volc.json` says enabled): PASS
* Behaviour to know (not a bug): an Update **overwrites the server's** `portfolio.json`, `config_*.json`, `volc.json`, `panic.json` with this checkout's versions, because they are in the package. Any hand edit made directly on the server is lost at the next Update; edit them here instead.
* `tbo_install.bat` runs `git pull` on this PC before packaging when `.git` exists: the package is built from this PC's working tree after the pull.

## SECTION 4: the 8 HTML reports

### 4.1 File, JS and version audit

`node` is **not installed on this machine**, so `node --check` could not be run; every inline `<script>` was parsed with the pure-Python `esprima` JavaScript parser instead (ES2017; a syntax error would be reported). None of the pages loads an external script.

| Page | Size | Last modified | Inline scripts parse (esprima) | External scripts |
|---|---|---|---|---|
| `trades.html` | 2,730,476 B | 2026-11-13 20:08 | 1 script(s): ok PASS | none |
| `panic.html` | 788,677 B | 2026-11-13 20:08 | 1 script(s): ok PASS | none |
| `risk_comparison.html` | 172,156 B | 2026-11-13 20:08 | 1 script(s): ok PASS | none |
| `cap_comparison.html` | 1,855,623 B | 2026-11-13 20:08 | 1 script(s): ok PASS | none |
| `monthly_report.html` | 134,292 B | 2026-11-13 20:08 | 1 script(s): ok PASS | none |
| `tbo_statistics.html` | 135,670 B | 2026-11-13 20:08 | 1 script(s): ok PASS | none |
| `winrate_rr.html` | 15,244 B | 2026-11-14 09:09 | 1 script(s): ok PASS | none |
| `market_regimes.html` | 333,589 B | 2026-11-14 09:15 | 1 script(s): ok PASS | none |

Every version string in each page's visible text, with context (`v3.2.1` = the live system; older numbers are rule-introduction labels or the history a research page is about):

**`trades.html`**: {'v3.2.1': 1}
* ladder text: ...count , sized exactly like the bot: the risk ladder (under $1,000: BTC 5% / ETH 3.3% / each alt 0.83%; from $1,000: BTC 5% / ETH 3.3% / each alt 0.83%; from $10,000: BTC 2.5% / ETH 1.7% / each alt 0.42%) with the open-risk cap (BTC never shrunk), shorts at half size, fees, slippag...

**`panic.html`**: {'v3.2.1': 2}
* ladder text: ...e" is the whole v3.2.1 system, with its ladder.) A second strategy next to the trend bot: it buys forced-liquidation crashes and sells the rebound . When a coin falls hard while open interest collapses , leveraged longs are being liquidated: Binance sells their positions at a...

**`risk_comparison.html`**: {'v3.2.1': 2, 'v3.1': 1, 'v3.2': 2}
* `v3.1`: ... and +8R → +3.5R, stale stop at 60 h, 16 h cooldown after a stop-out; v3.1: failed-breakout stop (from 8 h: was +0.9R, hourly close below −0.2R ...
* `v3.2`: ... BTC stop-out moves the other coins' same-direction stops to −0.25R); v3.2: a trade armed in a wild pullback (the coin's daily ATR14 / ATR100 ≥ ...
* `v3.2`: ...ized as live) could do with $300 over 24 months with its risk ladder (v3.2 ladder: BTC 5% / ETH 3.3% / alts 0.83% of the balance up to $10,000 (...
* ladder text: ...ld do with $300 over 24 months with its risk ladder (v3.2 ladder: BTC 5% / ETH 3.3% / alts 0.83% of the balance up to $10,000 (the same from $300), 2.5% / 1.7% / 0.42% above) and with flat risk levels. Each level was run on the same simulated 2-year market paths, built from random...
* ladder text: ...sk per trade (BTC / ETH / each alt; the ladder changes with the balance) Add money every month Trades taken from Median path Middle 50% Middle 80% $10k / $20k Money put in Chance of having reached each level by month Share of paths whose balance touched the level at least onc...

**`cap_comparison.html`**: {'v3.2.1': 1, 'v3.1': 1, 'v3.2': 2}
* `v3.1`: ... and +8R → +3.5R, stale stop at 60 h, 16 h cooldown after a stop-out; v3.1: failed-breakout stop (from 8 h: was +0.9R, hourly close below −0.2R ...
* `v3.2`: ... BTC stop-out moves the other coins' same-direction stops to −0.25R); v3.2: a trade armed in a wild pullback (the coin's daily ATR14 / ATR100 ≥ ...
* `v3.2`: ...t relative to the BTC risk: 1.1× means 5.5% of the account at BTC 5% (v3.2 ladder, from $300 to $10,000); with the ladder it follows the step (5...
* ladder text: ...ans 5.5% of the account at BTC 5% (v3.2 ladder, from $300 to $10,000); with the ladder it follows the step (5.5% → 2.75% from $10,000). BTC never shrunk (recommended): BTC trades always open at full size, but their risk still counts, so when BTC is in a fresh trade the other...
* ladder text: ...at 0.8× risk, no cap. The bot runs the ladder with the cap, BTC never shrunk . Start Risk level (BTC / ETH / each alt) Lines shown Drop from the highest balance so far, counting every open trade not yet at breakeven as if it hit its stop at that moment (worst case). Side by...

**`monthly_report.html`**: {'v3.2.1': 1}

**`tbo_statistics.html`**: {'v3.2.1': 1, 'v3.2': 1, 'v2.5': 1, 'v2.4': 1, 'v2.8': 1}
* `v3.2`: ...elected coins together, sized the way the bot sizes: the risk ladder (v3.2 ladder: BTC 5% / ETH 3.3% / alts 0.83% of the balance up to $10,000 (...
* `v2.5`: ...and percent figures run one account through time, sized like the bot (v2.5): each trade risks its coin's % from the ladder row for the balance a...
* `v2.4`: ...(the stop was moved to the entry at +1.5R). The open-interest filter (v2.4) only acts from 2022 (Binance's open-interest history starts in Dec 2...
* `v2.8`: ...ing of the same number of orders never matched it. The OI-low filter (v2.8: no order while open interest is in the lowest 20% of its last 90 day...
* ladder text: ...ether, sized the way the bot sizes: the risk ladder (v3.2 ladder: BTC 5% / ETH 3.3% / alts 0.83% of the balance up to $10,000 (the same from $300), 2.5% / 1.7% / 0.42% above) with the open-risk cap (BTC never shrunk), shorts at half size. Pick coins, period and starting balance, o...
* ladder text: ...each trade risks its coin's % from the ladder row for the balance at entry (× the short-size factor for shorts); an ETH / BNB / SOL / ADA trade is shrunk so the risk of all open trades not yet at breakeven stays within the cap (1.1× that row's BTC risk), or skipped if less t...

**`winrate_rr.html`**: {'v3.2.1': 1}

**`market_regimes.html`**: {'v3.2': 5, 'v3.1': 2, 'v3.2.1': 2}
* `v3.2`: ...ever sees the state of the day before it. Then the question: does TBO v3.2 do better or worse in some regimes, and does any regime rule beat v3....
* `v3.1`: ...3.2 do better or worse in some regimes, and does any regime rule beat v3.1 out of sample? Live system: v3.2.1 (its trend-bot trades are v3.2's; ...
* `v3.2`: ...eat v3.1 out of sample? Live system: v3.2.1 (its trend-bot trades are v3.2's; v3.2.1 only adds the VOLC tie guard), so "TBO v3.2" below is the l...
* `v3.2`: ...-bot trades are v3.2's; v3.2.1 only adds the VOLC tie guard), so "TBO v3.2" below is the live trend bot. Coin Method Period TBO v3.2 trades by r...
* `v3.2`: ...d), so "TBO v3.2" below is the live trend bot. Coin Method Period TBO v3.2 trades by regime at entry Average R per trade of the five coins' trad...
* `v3.1`: ...The coin's own volatility ratio (ATR14 / ATR100) is the clearest one. v3.1 vs TBO v3.2 as deployed, from $300 (2024 start) ...
* `v3.2`: ...wn volatility ratio (ATR14 / ATR100) is the clearest one. v3.1 vs TBO v3.2 as deployed, from $300 (2024 start) ...

* All 8 pages carry the label `v3.2.1`: PASS
* Findings and fixes: `winrate_rr.html` said **"TBO v2.8"** and had no v3.2.1 label, and its prose quoted "17% (this bot) ... 4.9" and "+0.5-0.6R per trade" although the page's own data say 20.0% and +0.65R. Fixed in `research/crypto/pages/winrate_template.html` and rebuilt with `make_winrate_html.py` (commit `133476f`); the embedded data were verified byte-identical before and after.
* The remaining older numbers are correct as written: `v3.1` / `v3.2` in `risk_comparison`, `cap_comparison`, `tbo_statistics` name the release that introduced a rule (failed-breakout stop, BTC cascade, wild-pullback size, ladder), and `v2.4` / `v2.5` / `v2.8` in `tbo_statistics` name the OI filter / sizing / OI-low filter releases. `market_regimes.html` is the v3.2 research page: it asks whether regime rules beat v3.1 and compares v3.1 with TBO v3.2 as deployed; v3.2.1 has the same TBO trade list (its change is the VOLC tie guard), so this stays accurate. `panic.html`'s `v3.0` is the panic sleeve's own version.

### 4.2 Headline numbers vs the simulator

**Reference values, recomputed in this audit from the trade lists** (`v31lib._money31` through the v3.4 kernel, O1 policy = `portfolio.json`):

| Run from $300 | Whole system (TBO + panic + VOLC) final / max DD | TBO only final / max DD |
|---|---|---|
| 2020-01-01 | $20,984,045.66 / 29.03% | $7,380,035.36 / 29.03% |
| 2022-01-01 | $2,030,647.52 / 24.51% | $663,690.12 / 28.87% |
| 2024-01-01 | $74,343.33 / 26.20% | $42,552.32 / 26.90% |

Trade counts from the source lists: TBO **1,355** (v3.2.1 list), Panic **208** (v3.0 with the extra pool), VOLC **115** (core 5, live-exact), trades sized x0.25 by the wild-pullback rule **116**.
Claimed reference: 2022 $2,030,648 / 24.5%, 2024 $74,343 / 26.2% -> PASS; counts TBO 1,355 / Panic 208 / VOLC 115 / wild x0.25 116 -> PASS

**What each page embeds and whether it agrees** (a page value is compared with the reference it is supposed to show: *whole system* or *TBO only*; tolerance $0.01 / 0.05 points on balances and drawdowns, which are stored rounded):

| Page | Quantity | Page value | Reference | Result |
|---|---|---|---|---|
| `trades` | 2020 run final (TBO only) | 7,380,035.36 | 7,380,035.36 | PASS |
| `trades` | 2020 run max DD % (TBO only) | 29.00 | 29.03 | PASS |
| `trades` | 2022 run final (TBO only) | 663,690.12 | 663,690.12 | PASS |
| `trades` | 2022 run max DD % (TBO only) | 28.90 | 28.87 | PASS |
| `trades` | 2024 run final (TBO only) | 42,552.32 | 42,552.32 | PASS |
| `trades` | 2024 run max DD % (TBO only) | 26.90 | 26.90 | PASS |
| `trades` | number of trades listed | 1,355 | 1,355 | PASS |
| `panic` | 2022 run final, bot + sleeve (whole system) | 2,030,647.52 | 2,030,647.52 | PASS |
| `panic` | 2022 run max DD %, bot + sleeve | 24.51 | 24.51 | PASS |
| `panic` | 2024 run final, bot + sleeve (whole system) | 74,343.33 | 74,343.33 | PASS |
| `panic` | 2024 run max DD %, bot + sleeve | 26.20 | 26.20 | PASS |
| `panic` | panic trades listed | 208 | 208 | PASS |
| `panic` | panic trades, sum of the yearly counts | 208 | 208 | PASS |
| `monthly_report` | 2024 view final (whole system) | 74,343.33 | 74,343.33 | PASS |
| `monthly_report` | 2024 view max DD % (whole system) | 26.20 | 26.20 | PASS |
| `monthly_report` | 2020 view final (whole system) | 20,984,045.66 | 20,984,045.66 | PASS |
| `monthly_report` | 2020 view max DD % | 29.00 | 29.03 | PASS |
| `monthly_report` | 2020 view TBO trades taken (= 1,355 listed minus 62 skipped by the open-risk cap in that run) | 1,293 | 1,293 | PASS |
| `monthly_report` | 2024 view TBO trades taken (= 527 listed from 2024 minus 31 cap-skipped) | 496 | 496 | PASS |
| `tbo_statistics` | number of trades embedded | 1,355 | 1,355 | PASS |
| `winrate_rr` | trades, sum over the 5 coins (all-time) | 1,355 | 1,355 | PASS |
| `winrate_rr` | trades, 'All 5 coins' row | 1,355 | 1,355 | PASS |
| `market_regimes` | v3.1 vs v3.2 deployed run, last balance (the 2024-start run) | 74,343.33 | 74,343.33 | PASS |

**`cap_comparison.html`**: the page's 'the bot' variant is `capbtc` (cap 1.1x BTC risk, BTC never shrunk) of the `lad` ladder set (variant `now` is the no-cap line). It is a TBO-only account (no sleeves), so it is compared with the TBO-only reference:

| Page | Quantity | Page value | Reference | Result |
|---|---|---|---|---|
| `cap_comparison` | 2020 'the bot' final (TBO only) | 7,380,035.36 | 7,380,035.36 | PASS |
| `cap_comparison` | 2020 'the bot' max DD % | 29.03 | 29.03 | PASS |
| `cap_comparison` | 2022 'the bot' final (TBO only) | 663,690.12 | 663,690.12 | PASS |
| `cap_comparison` | 2022 'the bot' max DD % | 28.87 | 28.87 | PASS |
| `cap_comparison` | 2024 'the bot' final (TBO only) | 42,552.32 | 42,552.32 | PASS |
| `cap_comparison` | 2024 'the bot' max DD % | 26.90 | 26.90 | PASS |

**`risk_comparison.html`**: 1,000 random-block 2-year journeys per source period from $300 (the live ladder, no deposits, the whole system). Independently re-simulated here with `botsim.journey_trades` / `botsim.run` (same seeds 0-999, same policy) and compared with the page's embedded median / p10 / p90 / drop:

| Page | Source period | Quantity | Page value | Re-simulated | Result |
|---|---|---|---|---|---|
| `risk_comparison` | trades from 2022 | median final $ | 24,235.60 | 24,235.60 | PASS |
| `risk_comparison` | trades from 2022 | p10 final $ | 6,429.23 | 6,429.23 | PASS |
| `risk_comparison` | trades from 2022 | p90 final $ | 96,851.61 | 96,851.61 | PASS |
| `risk_comparison` | trades from 2022 | median max drop % | 32.52 | 32.52 | PASS |
| `risk_comparison` | trades from 2022 | p90 max drop % | 44.91 | 44.91 | PASS |
| `risk_comparison` | trades from 2024 | median final $ | 22,369.68 | 22,369.68 | PASS |
| `risk_comparison` | trades from 2024 | p10 final $ | 5,299.74 | 5,299.74 | PASS |
| `risk_comparison` | trades from 2024 | p90 final $ | 87,070.02 | 87,070.02 | PASS |
| `risk_comparison` | trades from 2024 | median max drop % | 32.76 | 32.76 | PASS |
| `risk_comparison` | trades from 2024 | p90 max drop % | 45.09 | 45.09 | PASS |

(The v3.4 bootstrap quoted in this audit, median $28,770 / p10 $7,672 / dd90 44.43%, draws its blocks from the whole 2020-2026 history, so it is a different distribution from the page's 2022- and 2024-sourced ones; both are produced by the same sizing code.)

Notes on scope: `trades.html`, `tbo_statistics.html` and `winrate_rr.html` are **TBO-only** pages (the page text says the panic and VOLC sleeves are not in the list), so their balances are compared with the TBO-only reference; `panic.html`, `monthly_report.html`, `risk_comparison.html`, `cap_comparison.html` and `market_regimes.html` run the whole system. The VOLC count (115) and the wild-pullback count (116) are not printed as numbers on any page; they are verified here from the source lists and are what the whole-system runs above are built from.

## SECTION 5: pre-flight smoke test

### 5.1 `python cryptobot/dev/test_volc_edges.py`

Run on a scratch copy of `cryptobot/` (so nothing is written into the repo); the `ERROR:volc` lines are faults the test injects on purpose.

~~~~
  [OK  ] hand-over after a partial take-profit fill sends only the rest [('BTCUSDT', 'SELL', 0.6, False)]
  [OK  ] hand-over after a full take-profit fill sends nothing []
  [OK  ] hand-over without a fill sends the sleeve's quantity [('BTCUSDT', 'SELL', 1.0, False)]
  [OK  ] hand-over with the fill unreadable sends the last known quantity [('BTCUSDT', 'SELL', 1.0, False)]
  [OK  ] tie on a poll: sleeve stop cancelled and forgotten {}
  [OK  ] tie, but the sleeve stop triggered first: kept for the fill check {'BTCUSDT': {'long': 'v1'}}
  [OK  ] trend bot one tick further is not a tie 
  [OK  ] trend bot at the same level is a tie 
  [OK  ] opposite side is never a tie 
  [OK  ] stop loss refused 3 polls: closed at market [('BTCUSDT', 'SELL', 1.0, True)]
  [OK  ] take-profit refused: no exception, stop loss in place {'entry_ms': 0, 'entry': 100.0, 'qty': 1.0, 'side': 1, 'dist': 1.0, 'stop': 99.0, 'tp': 101.5, 'sl_id': 'sl0', 'tp_oid': None, 'tp_q': 1.0, 'sl_fail': 0}
  [OK  ] one coin's error does not stop the others ['BTCUSDT', 'ETHUSDT']
  [OK  ] two-sided arm, short at market: the placed long stop is cancelled first (['sl0'], ['sl0'], {'BTCUSDT': {'mk': None}}, [('BTCUSDT', 'SELL', 125.0, False)])
  [OK  ] /status: a VOLC-only position is not a trend-bot trade 
  [OK  ] /status: the sleeve's vc_in_ order is not a trend-bot order 
  [OK  ] /status: second profit lock named 
  [OK  ] /status: the VOLC position's stop is not in the trend bot's open risk  0.0% of 2.75% cap · $0.00
  [OK  ] /status stage names: stale / cascade / failed breakout 
  [OK  ] bot open_risk after a hand-over uses the bot's own fill price risk 2.0 (blended entry would give 4.0)
RESULT: all passed
ERROR:volc:BTC: VOLC stop loss not placed (HTTP 400 code -4045: refused), attempt 1
ERROR:volc:BTC: VOLC stop loss not placed (HTTP 400 code -4045: refused), attempt 2
ERROR:volc:BTC: VOLC stop loss not placed (HTTP 400 code -4045: refused), attempt 3
ERROR:volc:BTC: Binance: HTTP 503 code -1001: internal error (retried next poll)
WARNING: no .env file found. Looked in /home/eko/tbo-secrets/.env and /tmp/claude-1000/-mnt-c-Users-Eko-Desktop-tbo/35ca25c5-01af-4e33-9b47-a8768447d5e9/scratchpad/cbaudit__cby28r0/cryptobot/.env. Put .env in the secrets folder (or set TBO_SECRETS_DIR); only keys already in the environment are used.
~~~~

* checks passed: **19**, failed: **0**, exit code 0, result line `RESULT: all passed` (stdout first, then the injected-fault log lines and the missing-.env warning from stderr): PASS

### 5.2 Syntax and import check of every `.py` in `cryptobot/`

Syntax = `py_compile`; import = `python -c "import <module>"` in the scratch copy (no `.env`, no network call at import). Modules that run work at import (no `if __name__` guard and top-level code) are compiled but not imported: `check_setup.py` is the pre-flight script (it contacts Binance when run).

| File | Syntax | Import | Note |
|---|---|---|---|
| `binance_futures.py` | ok | ok |  |
| `bot.py` | ok | ok |  |
| `check_setup.py` | ok | skipped | pre-flight script, runs checks at import |
| `dev/live_test.py` | ok | n/a (dev test / tool: compiled only) |  |
| `dev/parity_detail.py` | ok | n/a (dev test / tool: compiled only) |  |
| `dev/replay.py` | ok | n/a (dev test / tool: compiled only) |  |
| `dev/test_bot_sim.py` | ok | n/a (dev test / tool: compiled only) |  |
| `dev/test_cap_sim.py` | ok | n/a (dev test / tool: compiled only) |  |
| `dev/test_oi_low.py` | ok | n/a (dev test / tool: compiled only) |  |
| `dev/test_panic_sim.py` | ok | n/a (dev test / tool: compiled only) |  |
| `dev/test_v31_sim.py` | ok | n/a (dev test / tool: compiled only) |  |
| `dev/test_v32_sim.py` | ok | n/a (dev test / tool: compiled only) |  |
| `dev/test_volc_edges.py` | ok | ran in 5.1 |  |
| `notify.py` | ok | ok |  |
| `oi_history.py` | ok | ok |  |
| `panic.py` | ok | ok |  |
| `panic_signal.py` | ok | ok |  |
| `report.py` | ok | ok |  |
| `run_all.py` | ok | ok |  |
| `strategy.py` | ok | ok |  |
| `volc.py` | ok | ok |  |
| `volc_signal.py` | ok | ok |  |

### 5.3 Documentation sections v3.1 to v3.5

#### `HANDOFF.md`: header paragraphs (v3.2 / v3.1 current-settings notes), lines 1-12
~~~~markdown
# Crypto (Binance futures) - Oct 2026

**Layout (Oct 2026 cleanup):** research scripts are in `research/crypto/core/` (library), `research/crypto/pages/` (page generators + templates) and `research/crypto/studies/` (experiments); the bot's developer checks in `cryptobot/dev/`. Script names below are unchanged; see the top-level `README.md` for what is where.

**v3.2 (13 Nov 2026, live): v3.1 + wild-pullback size (x0.25 when, at the order's 4h arming close, the coin's last closed
daily candle has ATR14 / ATR100 >= 0.98 and the last 5 days moved >= 0.25 ATR14 against the order; the trade is still taken)
+ ladder = v3.0's at k 1.00 with its first row (< $1,000) at the $1,000-10,000 risks (BTC 5 / 5 / 2.5%, ETH 3.3 / 3.3 / 1.7%,
alts 0.83 / 0.83 / 0.42%, cap 5.5 / 5.5 / 2.75%). See the last section and `research/results/v32c_REPORT.md`.**

**v3.1 (13 Nov 2026, live): v3.0 + failed-breakout stop tighten (from 8 h, hourly closes: was +0.9R, never +1.5R, now < -0.2R
-> stop -0.5R, cooldown after it) + BTC stop-out cascade (BTC trade closed < -0.5R net -> ETH / alts' same-direction stops to
-0.25R) + VOLC sleeve on the core 5 (main account, 0.25 x BTC risk, outside the cap; one coin = one position with the trend
~~~~

#### `HANDOFF.md`: from `## v3.1 round and deployment` to the end of the file (v3.1, v3.2, v3.3 + v3.2.1, v3.4, v3.5), lines 394-580
~~~~markdown
## v3.1 round and deployment (Nov 2026, data to 2026-11-06)
- **Research** (`research/results/v31_REPORT.md`; engine `core/xengine31.py` = v3.0 exactly with its new controls off; campaign
  `studies/v31_drawdown_and_sleeves.py`, `v31_sleeves.py`, `v31_final.py`, follow-up `v31b_surgical_followup.py`): 7,433 settings
  in 8 tracks + the v3.1b follow-up, gates E1-E4 (sleeves S1-S6) fixed in advance.
  - Passed: failed-breakout stop tighten (T 8 h, MFE 0.9R, close < -0.2R -> stop -0.5R) and the BTC cascade; together all 10
    combinations pass.
  - Near-pass: 4h VOLC + OI sleeve (fails its money gate by < 0.1 point of 2024 drop; found in a follow-up grid).
  - Failed: take-profit-at-entry / market-close scratches, early dead-start stale rules, fill-time stop re-anchor, soft
    ratchet, cluster cooldown (hard skip: not exact; non-cycling size-down: no plateau), dynamic cap, closed-loss brake,
    order validity window (late fills are the BEST trades), chop max-ext, channel width, fast-fakeout defence (slow-start
    winners look like fakeouts), every session / funding / trap-snapback sleeve, mini-panic tier.
- **Deployed (user decision 13 Nov 2026; revised the same day):** TBO v3.1 (both rules) + Panic v3.0 + VOLC on BTC ETH BNB SOL
  ADA at 0.25 x the BTC risk + every ladder risk and cap x 0.95 (x 0.90 was the first choice; the rule "x 0.90 only if it beats
  v3.0's 2024 money and bootstrap median" picked x 0.95).
  - Live code: `strategy.py` (fb_* / casc_* settings, `fb_fires`, `net_R`, stop stages); `bot.py` v3.1 (`check_fb` replays
    closed 1m candles like the engine; `record_close` / `check_cascade` through `state_BTCUSDT.json`; `volc_owner`: a VOLC
    position on the coin is not adopted or capped and the bot carries on as if flat; after a hand-over it uses its own fill
    price); `volc.py` + `volc_signal.py` + `volc.json` (take-profit = reduce-only post-only LIMIT 0.01% inside the target;
    `hand_over` gives the coin to the trend bot when its order fills); `binance_futures.py` limit-order helpers; `panic.py`
    records its triggers; `run_all.py` starts / restarts `volc.py` and lists its trades in /status; `check_setup.py`.
  - Research twin: `core/v31deploy.py` (TBO + cascade first, then VOLC around it: no fills while TBO holds the coin,
    closed at the next minute's open when a TBO order fills) -> `build_trades.py v31` (botsim's default `v31`; also
    `cache/volc_trades_v31.pkl`). botsim `full_policy` / `window_full` / `history(full=True)` / `journey_trades(full=True)`:
    the whole system (TBO + panic + VOLC) for the monthly, risk and panic pages.
  - VOLC as deployed: +0.35R / +0.19R per trade 2022-23 / 2024-26 (PF 1.76 / 1.37, 115 trades) vs +0.32R / +0.25R in the
    grid (touch fills at the maker fee, another OI sample, a look-ahead panic exclusion). A limit AT the target that needs
    the price to trade through: +0.14R; a market take-profit: +0.17R; the deployed limit 0.01% inside: +0.19R.
  - Money (`research/results/v31_deploy_money.csv`), from $300:

    | | 2022 | 2024 | Oct-Nov 2026 | Bootstrap median / p10 / dd90 |
    |---|---|---|---|---|
    | v3.0 | $1.125M / 26.0% | $61.0k / 34.0% | -32.6% | $23.4k / $4.87k / 56.7% |
    | v3.1 x 0.90 | $1.033M / 22.2% | $56.9k / 30.1% | -24.7% | $23.8k / $5.89k / 47.9% |
    | **v3.1 x 0.95 (deployed)** | $1.215M / 23.4% | $70.8k / 31.5% | -26.0% | $26.4k / $6.63k / 49.5% |
- **Bug fixed** (since commit e69da14, "leave the user's own positions alone"): an entry that filled in the last seconds
  before a 4h close was taken for a manual position (no stop loss) because `on_candle_close` cleared the entry order before
  `check_position` saw the fill. `on_candle_close` now adopts such a fill first.
- **Parity:** `cryptobot/dev/test_v31_sim.py` (5 bots + `volc.py` on one simulated account vs `v31deploy`): see `cryptobot/README.md`.
- `botsim.py` default trade list is now `v31`. The trades / statistics / monthly / win-rate / cap / risk / panic pages are
  rebuilt with the x 0.95 ladder: trades / statistics / win-rate / cap show the trend bot alone; monthly report, risk
  comparison and panic page the whole system (TBO + panic + VOLC; the panic page's "bot" = TBO + VOLC). `breakout_support.html` is unchanged:
  a v2.8 study page that needs that study's outputs.

## v3.2 round and deployment (Nov 2026, data to 2026-11-06)
- **Research:** `research/results/v32_REPORT.md` (regime engine `core/crypto_regimes.py`, census, 1,490 regime settings: only
  volatility-regime sizing passed), `v32b_REPORT.md` (open-risk cap under size multipliers: opt-in `cap_basis="base"` in
  `v31lib.money31`; 4 follow-ups) and `v32c_REPORT.md` (exact-engine re-test, smooth ramp, the ladder's first row).
  - The v32b "skip" (VolReg >= 1.05 and a 5-day pullback) was tested on the frozen trade list. Inside the 1-minute engine
    (`v32lib.trades32(ofilt=...)`: orders dropped at their arming close, then re-entries, cooldowns, the cascade and VOLC
    re-run; engine base = the v3.1 package on all 41 phase copies) it lets 23-61 later trades in and fails E4 (2024 drop
    30.8-32.0%). Taking the trade at x0.25 instead keeps the engine path = v3.1's and passes all gates on the bot's own cap
    rule (plateau 100%, nulls 98% / 99%, phase copies 92.5-100%); HOLD_BIG: better 2020-23 and a lower 2024-26 drop, net
    there -16.7 units (+5.4 for v3.1).
  - Failed: S5a 2-tier / 3-tier / smooth VolReg sizing (capped account; plateau), cluster size-down, BTC-regime risk, loss
    brake, VolReg-conditioned lock / hold, larger VOLC with a leverage cap. The S5a "0.79 cliff" = 8 losers of Jul-Aug 2026
    with VolReg 0.754-0.770 inside the capped account's worst episode.
  - The ladder: every $300-start window and bootstrap journey began in the old first row (BTC 5.7%); inside the 2024 run the
    Sep-Nov 2026 drop is 13.6-16.8% for every candidate.
- **Deployed (user decision 13 Nov 2026):** v3.1 + the x0.25 size-down (live cap counting: the cap counts actual, scaled
  risk) + the flat-first-row ladder at k 1.00.
  - Live code: `strategy.py` (`vol_regime`, `size_mult`, `vr_mult` / `vr_min` / `vr_chg5`, configs 0.25 / 0.98 / -0.25);
    `bot.py` v3.2 (1,499 daily candles; the multiplier decided at the arming close and kept in `state` for a cooldown
    release and the per-minute cap resize; `size(mult=...)`: a x0.25 order below Binance's minimum while the full one would
    trade is raised to the minimum order if it fits the cap and leverage; Telegram / 4h-check lines show the x0.25);
    `portfolio.json`; configs' fallback risks 5 / 3.3 / 0.83; `check_setup.py` shows each coin's ATR14/ATR100 and 5-day move.
  - Research twin: `core/v32deploy.py` (v31deploy's lists + `size_mult` at the arming close) -> `build_trades.py v32`
    (botsim's default; `portfolio_trades_v32.pkl` with `size_mult` / `vr` / `chg5`, 116 of 1,355 trades at x0.25). botsim:
    TR column 6 = the size multiplier, applied before the cap.
  - **botsim fix:** a sleeve trade (panic / VOLC) was counted in the worst-case balance for the instant of its entry (its
    breakeven event follows 0.001 min later), inflating page drawdowns (v3.1's 2022 run showed 28.8% instead of 23.4%);
    finals were unaffected. Sleeves are now outside the worst case and the cap room from their entry, as in `money31`.
  - Money, from $300 (botsim = money31 to the dollar):

    | | 2022 | 2024 | Sep-Nov 2026 from $300 / in the 2024 run | Oct-Nov 2026 | P(>= $10k, 2 y) | Bootstrap median / p10 / dd90 |
    |---|---|---|---|---|---|---|
    | v3.1 (x 0.95) | $1.215M / 23.4% | $70.8k / 31.5% | 34.4% / 16.0% | -26.0% | 83.4% | $26.4k / $6.63k / 49.5% |
    | **v3.2 (deployed)** | $2.031M / 24.5% | $74.3k / 26.2% | 26.6% / 14.2% | -22.0% | 87.1% | $28.8k / $7.67k / 44.4% |
- **Parity** (`cryptobot/dev/test_v32_sim.py`, 5 bots + VOLC on one simulated account, 2021-01 .. 2026-11 in three runs):
  - x0.25 decision at every 4h close: 63,898 closes; 0 differences except one SOL day (2023-02-10, longs: VolReg 0.97991 vs
    0.98042) because the simulated exchange rounds SOL's 2023 prices to today's 0.01 tick; no trade that day. The formula on
    the research's own candles: identical (max difference 2.4e-12).
  - Size multiplier per trade, bot vs research: 1,152 matched trades (101 at x0.25), **0 differences**.
  - Entries / exits: 2021-22 406 / 402 of 413, 2023-24 442 / 430 of 446, 2025-26 304 / 303 of 304 (v3.1's categories: tick
    rounding and SOL minute gaps move an entry by a minute, the backtest's stop inside the fill minute). VOLC 35 / 44 / 35 of
    36 / 44 / 35; 2 extra VOLC trades in the bots in 2023 (BTC 2023-04-10, BNB 2023-07-24) appear the same under
    `test_v31_sim.py`: a v3.1 difference, not looked into yet.
  - `dev/test_cap_sim.py 2022-01-01 2026-11-06` (v3.2 ladder, the x0.25 multiplier and the minimum-order floor in the expected risk): $10,000 886 entries (66 at x0.25), 79 shrunk by the cap, BTC 193/193 full size; $500 834 entries (60 at x0.25, 6 raised to Binance's minimum), 118 shrunk; $300 789 entries (58 at x0.25, 5 raised); **0 entries off the rule** at all three. The test now counts the other positions at the stop in force at the entry (a failed-breakout tighten lowers their risk, as the bot counts it) and calls a quick market close a cap close only when the bot says so.
- Pages: every page rebuilt with v3.2 (`market_regimes.html` now plots v3.1 vs v3.2 as deployed from $300, 2024 start).

## v3.3 round (Nov 2026) and v3.2.1 (VOLC tie guard, live)
- **Research** (`research/results/v33_REPORT.md`, `studies/v33_structural_frontiers.py`, engine `core/xengine33.py` = xengine32
  + checkpoint rule C that also acts after breakeven, parity 1,355 / 1,355): 2,005 settings on top of v3.2.
  - Track 1A late-life lock (380): 0 pass.
  - Track 1B zone-2 failed-extension stop (1,344): 6 pass the gates (MFE >= +2R, from 36-48 h, close < +0.75R -> stop
    +0.25R) but **rejected (user decision)**: the 2024 drop is unchanged (26.2015%), the passers sit on the +2.0R grid
    edge, and on the 14 untouched coins 2024-26 net turns negative (+5.4 -> -7.7 .. -19.1 units).
  - Track 2 cut-only regime sizing (FlatWild, Q5 climax, counter-macro shorts; 120): 0 pass.
  - Track 3 VOLC failed-breakout tighten / lock (117) and panic failed-bounce / repeat-flush (44): 0 pass.
- **Track 0, deployed as v3.2.1 (13 Nov 2026):** the 2 "extra" live VOLC trades of the parity test (BTC 2023-04-10,
  BNB 2023-07-24, plus BNB 2022-12-07) were exact ties. VOLC's 10-candle stop sat at the trend bot's 20-candle stop, both
  filled in the same minute, and `volc.py` traded its part back at market (two taker fees for a 1-minute round trip).
  - `volc.py` tie guard (`tbo_tie`, `drop_ties`): no sleeve stop where the trend bot's resting entry order on the same coin
    and side is at the same level or nearer (buy: tbo <= volc, sell: tbo >= volc). Checked when placing at the 4h close
    and at every poll, because `bot.py` may place its order a moment later.
  - Parity (`cryptobot/dev/test_v32_sim.py` against the real `volc.py`, 2021-01 .. 2026-11): 23 tied sleeve stops not
    placed, 4 earlier-candle sleeve orders cancelled at a re-armed tie, **0 collision trades**, VOLC entries **114 / 115**
    in the same minute (the last: SOL 2022-12-11, the known one-minute tick shift), exits 112 / 115. The trend bot's
    trades and x0.25 sizes are unchanged (1,152 / 1,152 multipliers).

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
- **Second review (user), fixed:**
  - `run_all.py` /status showed a position held only by the VOLC sleeve as a trend-bot trade (and counted its stop in the
    open risk), took the sleeve's waiting `vc_in_` order for a trend-bot order, and named only the BE / first-lock
    stages. Every stage is now named from the coin's config, incl. +3.5R, stale, cascade and failed breakout.
  - `bot.py` after a VOLC hand-over: the cap trim and the cascade re-read Binance's blended entry price. They now use the
    bot's own fill price (`own_position`), as does `open_risk` for the other coins.
  - `volc.py` with both sides armed: if the long stop was placed and the short went in at market, the long stop was left
    on Binance untracked. It is now cancelled first.
- Tests: `dev/test_volc_edges.py` (19 cases on a stub exchange) and the full `dev/test_v32_sim.py` 2021-26 run on the
  final code (unchanged: VOLC 114 / 115 entries and 112 / 115 exits in the same minute, 0 collision trades, the trend bot and its 1,152 size multipliers identical).

## v3.4 joint risk-grid and plateau audit (Nov 2026): the v3.2.1 settings confirmed (O1)
- **Research:** `research/results/v34_risk_audit_REPORT.md`, transcript `v34_terminal_log.md`, study
  `studies/v34_risk_plateau_audit.py`. Read-only on `cryptobot/`.
- **Method:** every setting judged jointly in the exact chronological capped simulator (`v31lib._money31` through a parallel
  numba kernel: the 5 coins share the cap in fill order, BTC exempt but counted, panic + VOLC outside). Live settings
  reproduced exactly. Per setting: 1,000 two-year journeys, the windows from $300, and the fixed-size capped account's
  ret / max DD in 2020-23 and 2024-26 on 41 trade lists.
- **Stage 1** (one change at a time, inside the full portfolio):
  - Raising the cap (1.20-1.50 × BTC) lets ETH trade alongside an open BTC trade (2024 run: 15 ETH entries skipped at
    1.10, 4 at 1.20) but lowers ret / max DD in both eras (×0.98 to ×0.90).
  - Differentiated alt weights help one era and hurt the other: alts stay equal.
  - More short size hurts 2024-26 (0.65: ×0.91).
  - VOLC / panic increases are the only near-misses (both eras, but 51-76% of the trade lists).
- **Stage 2:** 54,000 joint settings (BTC × ETH/BTC × alt/BTC × alt pattern × short × cap/BTC × VOLC × panic units). 0 of
  53,995 structural changes improve both eras on >= 80% of the 41 lists, so the v3.2.1 ratio structure is the era-robust
  choice.
- **Stage 3:** BTC dial 3.5-6.5% × 13 ladders × cap_min_fraction. Only risk LEVEL and ladder shape remain, trading drawdown
  against money. Full risk to $25k instead of $10k: bootstrap median $28.8k -> $41.9k, at +1.1 points of dd90 and a lower
  p10.
- **Stage 4:** five options (current; max profit at <= current drawdown; balanced; low drawdown; high growth).
- **Decision (user, 13 Nov 2026):** keep **O1 = the v3.2.1 settings**: the best small-account tail (p10 $7.67k, P(>= $10k)
  87.1%) for its drawdown (2024 run 26.2%, dd90 44.4%). The alternative is O5 (BTC 5.5% with a 3-rung ladder: more money
  and tail, +2 points of drawdown).
- **Final verification on O1:** all on the final code (26f07bf + docs):
  - `dev/test_volc_edges.py`: 19 / 19 pass.
  - `dev/test_v32_sim.py` 2021-01 .. 2026-11 (5 bots + VOLC with the tie guard): size multiplier 1,152 / 1,152; TBO 1,152
    of 1,163 same entry minute (v3.1's known categories); VOLC 114 / 115 entries and 112 / 115 exits, 0 collision trades;
    x0.25 decisions identical except one tick-rounded SOL day without a trade.
  - `dev/test_cap_sim.py` 2022-01 .. 2026-11: 0 entries off the rule at $300 (789 entries), $500 (834) and $10,000 (886).
  - `dev/test_panic_sim.py`: 0 missed / 0 extra signals in 3,449 hours, trades 208 / 208, 207 the same result (the known ADA
    2024-04-12 take-profit).
  - Pages: all 8 rebuilt, labelled v3.2.1, numbers unchanged (whole system from $300: 2022 $2,030,648 / 24.5%, 2024 $74,343 /
    26.2%).
  - `risk_comparison.html`'s O1 row (2022 source) shows median $24.2k / p10 $6.43k / dd90 44.9% / P(>= $10k) 82.9%, against
    the research bootstrap's $28.8k / $7.67k / 44.4% / 87.1%. Same idea, different horizon: the page cuts each journey at
    24 calendar months (730.6 days); the research bootstrap (`v30lib.boot_paths`, used for every money comparison since
    v3.0) runs all 27 four-week blocks (756 days). At ~20% median growth a month the extra 25 days are about +16%.

## v3.5 research campaign (14 Nov 2026): nothing adopted, v3.2.1 (O1, commit 17a6ce1) stays final

Branch `v35-research` (merged to main as docs and research only; `cryptobot/` and `reports/` unchanged). Study:
`research/crypto/studies/v35_new_strategies_and_volc_extra.py`; results `research/results/v35_REPORT.md`, `v35_terminal_log.md`, `v35_*.csv`.
3,634 settings scored against O1 in the exact capped simulator (parity: 2022 $2,030,648 / 24.51%, 2024 $74,343 / 26.20%, boot
$28,770 / $7,672 / 44.43%): 136 VOLC extra-pool settings (7 extra coins x share x max_extra_open x ranking x inside/outside the cap) +
3,498 settings of 7 new archetypes (trend-pullback, squeeze exhaustion, euphoria blow-off, Monday box, CME fade, laggard catch-up,
post-panic continuation). **0 pass G1 + G2 + G3.** VOLC on the extra coins: era ratio never > 1 in both eras (best phase share 49%),
and out of universe (HOLD_BIG 14) it earns +0.3R, PF 1.00 in 2024-26. Only lead: post-panic continuation (passes G3, fails G1 / G2,
~45 trades per era): re-test on live data in 6-12 months. Gate note: G1 needs >= 30 trades per era (a first pass flagged 1-2-trade cells).
~~~~

#### `cryptobot/README.md`: `## v3.4` through `## v3.1` (lines 53-205)
~~~~markdown
## v3.4 (13 Nov 2026): joint risk and plateau audit, the current settings kept

`research/results/v34_risk_audit_REPORT.md` tested the risk settings jointly, never coin by coin. 54,000 settings of BTC
risk, ETH / BTC, alt / BTC, alt weights, short multiplier, cap / BTC, VOLC share and panic units went through the exact
capped simulator. Each got 1,000 two-year journeys and an era check: better ret / max DD in 2020-23 AND 2024-26 on >= 80%
of 41 trade lists.
- No change to the ratios survives the era check:
  - a bigger cap lets ETH trade next to BTC but lowers ret / max DD in both eras;
  - different alt weights help one era and hurt the other;
  - more short size hurts 2024-26.
- What remains (the BTC risk level, the ladder's shape) only trades drawdown against money.
- **Kept (user decision): the current `portfolio.json` and configs (O1)**:
  - BTC 5% / ETH 3.3% / alts 0.83% / cap 5.5% below $10,000;
  - 2.5% / 1.7% / 0.42% / 2.75% from $10,000;
  - shorts × 0.5, VOLC 0.25 × the BTC risk, panic 3 units (extra pool 0.75, max 2 open).
- From $300: 2022 run $2.03M (drop 24.5%), 2024 run $74.3k (26.2%), bootstrap median $28.8k / bad 1-in-10 $7.67k / 1-in-10
  drop 44.4%, P(>= $10k in 2 years) 87.1%.
- No bot change.

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
- **Second review (user), fixed:**
  - `run_all.py` /status showed a position held only by the VOLC sleeve as a trend-bot trade (and counted its stop in the
    open risk), took the sleeve's waiting `vc_in_` order for a trend-bot order, and named only the BE / first-lock
    stages. Every stage is now named from the coin's config, incl. +3.5R, stale, cascade and failed breakout.
  - `bot.py` after a VOLC hand-over: the cap trim and the cascade re-read Binance's blended entry price. They now use the
    bot's own fill price (`own_position`), as does `open_risk` for the other coins.
  - `volc.py` with both sides armed: if the long stop was placed and the short went in at market, the long stop was left
    on Binance untracked. It is now cancelled first.
- Tests: `dev/test_volc_edges.py` (19 cases on a stub exchange) and the full `dev/test_v32_sim.py` 2021-26 run on the
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
~~~~

#### `cryptobot/README.md`: `## v3.5` (lines 711-715)
~~~~markdown
## v3.5 research (14 Nov 2026): no change to the bot

A further 3,634-setting campaign (VOLC on the 7 extra DEV12 coins with a slot-capped pool, plus 7 new strategy archetypes) found nothing
that passes the standalone, plateau / out-of-universe and coupled-portfolio gates against v3.2.1. Nothing in `cryptobot/` changed; the live
settings stay v3.2.1 (VOLC on the core 5 only). Details: `research/results/v35_REPORT.md`.
~~~~

## SECTION 6: verdict

**145 of 145 computed checks pass; 0 fail.**

No computed check failed.

### Limits of this audit (what was NOT verified)

* `node --check` was not run (Node.js is not installed here); the JS check is a pure-Python ES2017 parse. A page is not rendered in a browser here.
* Only `dev/test_volc_edges.py` was run. The other `cryptobot/dev` tests need the research caches / long replays and were compiled, not run. Parity between the live code and the research replay was established in earlier sessions (v3.1-v3.2.1), not re-run here.
* Nothing talks to Binance: no keys, no order, no `check_setup.py` run (it needs the server's `.env`). Run it on the server as `tbo_install.bat` does (`RESULT: ready`) before starting the bot.
* The install scripts were read and their package filter was applied to the tracked file list; `tbo_install.bat` itself (Windows / ssh / scp) was not executed.
* Page checks compare embedded numbers with the simulator; they do not judge the page layout. The `risk_comparison` page was re-simulated for its live-ladder row only (not the flat-risk rows or deposits).

Closing note: the git state in Section 1 was captured just before this file was written; after committing this file `main` is one commit ahead of `origin/main` until it is pushed (re-checked in the session reply).
