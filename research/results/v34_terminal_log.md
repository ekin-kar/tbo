# v3.4 risk-grid and plateau audit: session transcript (13 Nov 2026)

This file records the whole session in order: what was run, every printed table (verbatim from
`research/results/v34_stage_output.txt`, which the study appends to on every run), and my commentary at each step. The
quantitative summary and the recommendation are in `v34_risk_audit_REPORT.md`.

* **Branch:** `v34-research` (from `main` at 26f07bf).
* **Study:** `research/crypto/studies/v34_risk_plateau_audit.py`.
* **Environment:** WSL Ubuntu, Python venv `~/.venvs/tbo`, `TRADING_CACHE=~/.cache/tbo`, 8 cores.
* **`cryptobot/`** was only read (`portfolio.json`, `config_*.json`, `panic.json`, `volc.json`). Nothing in it was changed and
  no page was rebuilt.

---

## Step 0: reading the live settings

`cryptobot/portfolio.json`:

| From | BTC / ETH / BNB / SOL / ADA | Cap |
|---|---|---|
| $0 | 5.0 / 3.3 / 0.83 / 0.83 / 0.83 | 5.5 |
| $1,000 | the same | 5.5 |
| $10,000 | 2.5 / 1.7 / 0.42 / 0.42 / 0.42 | 2.75 |

Also live: `cap_exempt` [BTC], `cap_min_fraction` 0.25; `short_risk_mult` 0.5 on every coin; `panic.json` units 3,
extra_share 0.75, max_extra_open 2; `volc.json` share 0.25.

## Step 1: building a joint evaluator (and checking it)

**The brief's key rule:** never size coins in isolation, because the coins share the chronological open-risk cap. So every
setting must run through the exact multi-coin capped simulator: `v31lib._money31`, behind every money figure since v3.1.
It applies the cap in fill order, BTC exempt but counted, the cap counting the actual scaled risk, sleeves outside it.

**Making 54,000+ settings × 1,087 runs feasible:**
* Each run's events (a bootstrap journey, a window, a phase copy) are sorted exactly as `money31` does, once.
* A parallel numba kernel (`prange` over policies) calls `_money31` itself for every policy.
* The policy arrays (ladder rows × 5 coin risks, cap per row, per-coin short multipliers, `cap_min_fraction`, sleeve shares)
  are packed per setting.

**First check.** The live policy reproduced the reference exactly. The grid generator's base point gave 2022 $1,954,483
instead of $2,030,648: the live top row is not a uniform ×0.5 (ETH 1.7 not 1.65, alts 0.42 not 0.415). I made the
generator keep those top-row factors. The second check (below) shows all three identical. Speed: 2,000 policies × 1,000
journeys in 5.2 s.

```
[check] run sets built: windows 5, journeys 1000 [0.7s]
[check] kernel (2 policies x 1005 runs) [3.5s]
[check] portfolio.json exact: 2022 $2,030,648 / 24.51%, 2024 $74,343 / 26.20%, boot $28,770 / $7,672 / 44.43%
[check] grid generator at the base point: 2022 $2,030,648 / 24.51%, 2024 $74,343 / 26.20%, boot $28,770 / $7,672 / 44.43%
[check] reference (v33, money31): 2022 $2,030,648 / 24.51%, 2024 $74,343 / 26.20%, boot $28,770 / $7,672 / 44.43%
[check] speed: 2000 policies x 1000 journeys [5.7s]
```

## Step 2: Stage 1, coupled marginal sweeps

Each component is changed alone, inside the full portfolio (TBO + panic + VOLC, shared cap). For each: the five windows,
the 1,000-journey bootstrap, and the fixed capped account's ret / max DD in 2020-23 and 2024-26 on all 41 trade lists ("era"
columns: x vs v3.2.1; phase = share of the 41 lists with x > 1 in both eras).

* The panic extra-pool / max-extra-open and VOLC coin-weighting variants change the sleeve rows themselves, so they have
  their own run sets.
* The per-coin full / shrunk / skipped counts come from botsim's trade-level output (the same cap rule; botsim and money31
  agree to the dollar).

```
=== STAGE 1: coupled marginal sweeps (each change alone, inside the joint capped portfolio) ===
[stage1] 67 settings [13s]
                        setting     m_2022 dd_2022  m_2024 dd_2024 dd_sep26 dd_oct26 boot_med boot_p10 boot_dd90 p_10k era_x_dev era_x_oos era_phase
                baseline v3.2.1  2,030,648   24.51  74,343   26.20    26.58    24.63   28,770    7,672     44.43 0.871      1.00      1.00     0.000
                BTC weight x0.0     19,471   24.10   5,426   25.48    14.27    10.89    1,861      631     37.98 0.054      0.43      0.58     0.000
                BTC weight x0.5    248,631   23.44  28,549   19.86    20.58    16.88   11,790    2,664     37.96 0.557      0.74      0.86     0.146
               BTC weight x0.75    701,186   21.37  48,487   23.60    23.17    19.78   18,950    4,821     41.03 0.761      0.87      0.95     0.317
               BTC weight x1.25  4,637,001   27.64 123,690   30.84    30.09    29.24   42,872   11,118     49.54 0.919      1.00      1.01     0.000
                BTC weight x1.5 11,708,776   30.34 167,028   35.29    33.88    33.63   60,468   13,379     53.97 0.941      0.94      0.99     0.000
                BTC weight x2.0 58,083,417   35.94 353,046   43.11    41.77    41.77  112,689   19,384     62.96 0.961      0.88      0.92     0.000
                ETH weight x0.0    378,576   17.44  24,631   32.51    21.88    21.88   15,354    3,391     41.30 0.683      0.68      0.72     0.000
                ETH weight x0.5    837,542   18.01  46,487   26.61    23.70    23.10   21,706    5,597     41.13 0.790      0.84      0.95     0.000
               ETH weight x0.75  1,325,084   21.32  65,644   26.20    25.15    23.87   25,467    6,588     42.50 0.834      0.96      1.02     0.024
               ETH weight x1.25  2,607,433   27.58  96,977   26.53    28.00    25.39   34,317    8,888     46.51 0.888      0.95      0.98     0.244
                ETH weight x1.5  3,296,476   30.06 118,998   26.90    29.39    26.14   37,338    9,592     48.31 0.898      0.90      0.96     0.171
                ETH weight x2.0  4,395,851   32.81 133,657   27.04    30.83    27.18   42,444   10,089     50.86 0.902      0.88      0.95     0.098
                BNB weight x0.0  1,607,251   26.81  69,423   25.38    25.99    24.24   27,095    7,294     44.00 0.849      1.04      0.98     0.000
                BNB weight x0.5  1,813,411   25.62  80,479   25.79    26.33    24.43   28,254    7,474     43.94 0.862      1.03      0.99     0.049
               BNB weight x0.75  1,913,882   25.05  86,266   26.00    26.46    24.53   28,605    7,445     44.09 0.871      1.02      1.00     0.049
               BNB weight x1.25  2,213,099   23.98  78,442   26.53    26.71    24.73   28,963    7,587     44.75 0.868      0.98      1.00     0.244
                BNB weight x1.5  2,369,861   23.49  82,611   26.88    26.83    24.82   29,837    7,580     45.03 0.871      0.97      1.01     0.195
                BNB weight x2.0  2,112,083   24.71  90,868   27.57    27.07    25.02   31,034    8,088     45.97 0.872      0.93      1.02     0.049
                SOL weight x0.0  1,604,089   23.16  71,758   25.48    26.88    25.07   26,762    6,693     44.81 0.853      1.00      0.99     0.000
                SOL weight x0.5  1,777,794   23.83  72,497   25.83    26.73    24.85   27,800    7,140     44.64 0.859      1.02      0.99     0.000
               SOL weight x0.75  1,892,930   24.17  73,441   26.00    26.66    24.74   28,413    7,312     44.45 0.866      1.03      1.00     0.000
               SOL weight x1.25  2,235,949   24.84  93,818   26.75    26.51    24.52   29,555    7,906     44.58 0.874      0.97      1.00     0.780
                SOL weight x1.5  1,985,373   25.18  93,681   27.30    26.44    24.41   30,559    8,377     44.74 0.878      0.95      1.01     0.659
                SOL weight x2.0  2,199,941   25.84  94,663   28.40    26.30    24.19   32,132    8,918     44.98 0.888      0.90      1.01     0.610
                ADA weight x0.0  1,740,553   26.36  81,583   25.27    25.48    24.63   27,996    6,790     43.87 0.847      0.96      1.04     0.098
                ADA weight x0.5  1,881,390   25.42  87,376   25.72    26.03    24.63   28,332    7,333     43.88 0.860      0.98      1.02     0.146
               ADA weight x0.75  1,948,380   24.96  90,715   25.95    26.31    24.63   28,834    7,614     44.08 0.866      0.99      1.01     0.244
               ADA weight x1.25  2,169,243   24.06  75,659   26.55    26.86    24.63   29,372    7,619     44.93 0.872      1.01      0.99     0.024
                ADA weight x1.5  2,273,203   23.61  76,649   26.90    27.13    24.63   29,229    7,878     45.17 0.874      1.01      0.98     0.024
                ADA weight x2.0  1,959,033   24.54  78,655   27.60    27.68    24.63   30,351    8,255     45.70 0.883      1.00      0.96     0.049
          short mult 0.35 (all)  1,148,209   23.28  71,037   26.09    24.78    22.78   23,720    6,190     42.30 0.822      0.95      1.02     0.220
          short mult 0.65 (all)  2,498,590   24.97  93,218   26.93    28.36    26.45   34,935    9,172     47.07 0.891      0.99      0.91     0.000
           short mult 0.8 (all)  3,208,991   24.85  95,189   27.67    30.12    28.26   40,185   10,311     48.89 0.907      0.96      0.84     0.000
           short mult 1.0 (all)  4,884,840   27.05 112,877   30.28    32.22    30.42   45,378   11,022     52.08 0.915      0.88      0.76     0.000
 short mult 0.35 (BTC/ETH only)  1,185,337   23.45  70,071   26.20    24.70    22.70   24,058    6,180     42.85 0.819      0.95      1.01     0.122
 short mult 0.65 (BTC/ETH only)  2,475,202   24.99  93,492   26.71    28.44    26.53   35,191    9,442     46.23 0.892      0.99      0.92     0.024
  short mult 0.8 (BTC/ETH only)  3,198,123   25.01  99,171   27.24    30.26    28.41   39,654   10,460     48.09 0.907      0.99      0.85     0.000
  short mult 1.0 (BTC/ETH only)  4,359,158   25.35 118,133   28.58    32.66    30.86   44,467   11,534     50.07 0.914      0.97      0.77     0.000
    short mult 0.35 (alts only)  1,937,252   24.33  75,340   26.09    26.66    24.71   28,929    7,668     44.11 0.872      0.99      1.01     0.171
    short mult 0.65 (alts only)  1,803,206   24.70  91,564   26.40    26.51    24.55   29,120    7,652     44.81 0.865      1.01      0.99     0.024
     short mult 0.8 (alts only)  1,866,193   25.26  89,219   26.62    26.43    24.47   29,364    7,727     45.56 0.865      1.01      0.99     0.024
     short mult 1.0 (alts only)  1,923,253   26.78  85,844   26.91    26.33    24.37   29,236    7,746     46.21 0.867      0.99      0.98     0.000
                 cap 1.00 x BTC  2,014,799   24.51  86,753   26.20    26.15    24.63   28,893    7,629     44.51 0.870      0.99      0.99     0.122
                 cap 1.15 x BTC  2,025,502   24.51  75,424   26.20    26.80    24.63   28,938    7,637     44.62 0.870      1.00      1.00     0.171
                 cap 1.20 x BTC  1,947,395   24.51  74,467   27.02    27.01    24.63   28,820    7,328     44.92 0.862      0.98      0.98     0.000
                 cap 1.25 x BTC  1,947,823   24.51  74,135   27.57    27.20    24.63   28,786    7,297     45.22 0.864      0.97      0.97     0.000
                 cap 1.35 x BTC  1,912,254   24.51  90,478   28.31    27.20    24.63   28,717    7,224     45.85 0.861      0.95      0.94     0.000
                 cap 1.50 x BTC  1,855,631   24.51  88,548   28.92    28.23    24.63   28,026    6,913     46.76 0.855      0.90      0.89     0.024
                 VOLC share 0.0  1,509,712   24.85  70,459   26.36    27.77    24.63   26,860    6,687     45.31 0.834      0.98      0.95     0.000
                VOLC share 0.15  1,800,434   24.37  72,862   26.25    27.06    24.63   28,296    7,105     44.90 0.853      0.99      0.98     0.000
                 VOLC share 0.2  1,906,234   24.43  73,615   26.22    26.82    24.63   28,642    7,365     44.72 0.867      1.00      0.99     0.000
                 VOLC share 0.3  1,837,079   24.59  75,045   26.20    26.35    24.63   29,840    7,879     44.42 0.874      1.00      1.01     0.585
                VOLC share 0.35  1,924,791   24.67  75,720   26.20    26.11    24.63   30,591    8,033     44.42 0.878      1.01      1.02     0.585
                 VOLC share 0.4  2,027,973   24.77  76,367   26.20    25.87    24.63   31,250    8,185     44.11 0.883      1.01      1.03     0.585
                panic units 0.0    788,641   19.16  44,926   28.35    29.36    25.55   20,146    3,693     48.27 0.728      0.82      0.90     0.000
                panic units 2.0  1,432,461   21.52  69,730   26.36    27.51    24.63   26,007    6,097     45.01 0.824      0.98      0.97     0.000
                panic units 2.5  1,704,053   22.78  79,456   26.27    27.05    24.63   27,316    6,739     44.71 0.848      0.99      0.98     0.000
                panic units 3.5  2,035,174   26.23  84,295   27.83    26.12    24.63   31,193    8,731     44.16 0.888      1.01      1.02     0.610
                panic units 4.0  2,382,929   27.94  87,374   29.45    25.66    24.63   33,184    9,754     43.92 0.896      1.02      1.03     0.512
          panic extra_share 0.0  1,512,048   24.90  67,549   26.18    29.36    25.55   26,016    6,159     45.87 0.818      0.98      0.96     0.000
          panic extra_share 0.5  1,838,178   24.62  82,088   26.18    27.51    24.63   28,336    6,941     44.82 0.856      0.99      0.99     0.000
          panic extra_share 1.0  2,296,937   24.40  81,685   26.42    25.66    24.63   30,265    8,468     44.05 0.883      1.01      1.01     0.756
         panic max_extra_open 1  1,962,424   26.92  77,422   26.20    27.78    24.63   29,241    7,403     44.66 0.865      0.99      1.00     0.000
         panic max_extra_open 3  1,913,936   24.92  85,943   30.42    26.58    24.63   28,462    7,314     44.76 0.863      1.00      0.99     0.000
VOLC coin-weighted (TBO ratios)  1,603,368   26.38  71,419   26.20    26.58    24.63   27,192    6,684     44.79 0.841      0.99      0.96     0.000
 VOLC coin-weighted, same total  1,719,271   29.16  72,285   26.20    25.06    24.63   28,195    6,789     44.60 0.852      0.99      0.97     0.000

[stage1] per-coin TBO entries, one $300 account from Jan 2024 (full size / shrunk by the cap / skipped by the cap):
         setting start  SOL_full  SOL_shrunk  SOL_skipped  BNB_full  BNB_shrunk  BNB_skipped  BTC_full  BTC_shrunk  BTC_skipped  ADA_full  ADA_shrunk  ADA_skipped  ETH_full  ETH_shrunk  ETH_skipped
 baseline v3.2.1  2022       150           8            6       175           9            7       193           0            0       153           2            4       172           2           18
 baseline v3.2.1  2024        89           5            5        94           8            7       121           0            0        86           2            4        89           1           15
  cap 1.00 x BTC  2022       150           0           14       174           1           16       193           0            0       151           1            7       167           5           20
  cap 1.00 x BTC  2024        89           0           10        94           0           15       121           0            0        86           0            6        87           2           16
  cap 1.20 x BTC  2022       157           1            6       182           0            9       193           0            0       155           0            4       173          15            4
  cap 1.20 x BTC  2024        93           1            5       100           0            9       121           0            0        88           0            4        90          11            4
  cap 1.35 x BTC  2022       160           0            4       186           0            5       193           0            0       157           0            2       174          16            2
  cap 1.35 x BTC  2024        96           0            3       104           0            5       121           0            0        90           0            2        90          13            2
  cap 1.50 x BTC  2022       160           0            4       186           0            5       193           0            0       157           0            2       174          18            0
  cap 1.50 x BTC  2024        96           0            3       104           0            5       121           0            0        90           0            2        90          15            0
ETH weight x0.75  2022       151           7            6       175           9            7       193           0            0       153           2            4       172           2           18
ETH weight x0.75  2024        89           5            5        94           8            7       121           0            0        86           2            4        89           1           15
ETH weight x1.25  2022       148           9            7       173          11            7       193           0            0       152           3            4       167           7           18
ETH weight x1.25  2024        88           6            5        93           9            7       121           0            0        85           3            4        87           3           15
```

**Commentary on Stage 1:**
* **The brief's arithmetic is right.** Under cap = 1.10 × BTC, ETH is skipped whenever a BTC trade is open and not yet at
  breakeven: 15 of 105 ETH entries in the 2024 run, 18 of 192 in the 2022 run. Raising the cap lets them in (1.20: 4
  skipped, 11 shrunk).
* **But the fixed-account ret / max DD falls in both eras as the cap rises** (1.20: 0.98 / 0.98; 1.35: 0.95 / 0.94; 1.50:
  0.90 / 0.89). The BTC cascade only acts after BTC has stopped out. The ETH risk added while BTC is open costs more
  drawdown than it earns. The 2024-run money for the cap variants jumps around ($74k-$91k) because single-path sequencing
  is noisy; the bootstrap median stays flat ($28.0-28.9k).
* **Alt weights:** BNB ×0 is 1.04 in 2020-23 and 0.98 in 2024-26; ADA ×0 is 0.96 and 1.04; SOL ×1.25 is 0.97 / 1.00. Each
  coin helps in one era and hurts in the other. Keep the alts equal.
* **ETH:** removing it costs ~30% of the ratio; ×0.75 / ×1.25 are below 1 in one era each.
* **Short multiplier:** 0.65 / 0.8 / 1.0 drop the 2024-26 ratio to 0.91 / 0.84 / 0.76.
* **Sleeves:** the only components that raise the ratio in both eras (VOLC 0.30-0.40, panic units 3.5-4, panic extra_share
  1.0), but on just 51-76% of the 41 trade lists. VOLC coin-weighting is worse than uniform.

## Step 3: Stage 2, the joint grid

The grid is BTC 5 × ETH/BTC 5 × alt/BTC 4 × alt pattern 3 × short 3 × cap/BTC 5 × VOLC 4 × panic units 3 = 54,000 settings,
each with 1,087 runs (173 s). The full grid is in `v34_stage2_grid.csv.gz`, with the era columns and the four plateau
columns.

```
=== STAGE 2: joint grid btc 5 x eth_r 5 x alt_r 4 x altpat 3 x short 3 x cap_r 5 x volc 4 x units 3 = 54,000 settings (ladder and cap_min_fraction as live) ===
[stage2] evaluated 54,000 settings x 1087 runs [173s]
[stage2] baseline point in the grid: m_2022 2.031e+06, dd_2022 24.51, m_2024 7.434e+04, dd_2024 26.2, dd_sep26 26.58, dd_oct26 24.63, boot_med 2.877e+04, boot_p10 7672, boot_dd90 44.43, p_10k 0.871 | plateaus plateau_O2 0.64, plateau_O3 0.00, plateau_O4 0.00, plateau_O5 0.93
[stage2] era gate: 53,995 structural settings, 0 improve ret / max DD in 2020-23 AND 2024-26 with >= 80% of the 41 trade lists
[stage2] era read, eth_r alone: 0.5: x 0.958 / 1.022 (2%); 0.6: x 1.014 / 1.008 (7%); 0.66: x 1.000 / 1.000 (0%); 0.75: x 0.976 / 0.988 (34%); 0.85: x 0.948 / 0.974 (24%)
[stage2] era read, alt_r alone: 0.12: x 1.037 / 1.003 (12%); 0.166: x 1.000 / 1.000 (0%); 0.2: x 0.970 / 0.998 (27%); 0.25: x 0.927 / 0.992 (24%)
[stage2] era read, altpat alone: 0: x 1.000 / 1.000 (0%); 1: x 0.950 / 1.018 (41%); 2: x 0.905 / 1.033 (29%)
[stage2] era read, short alone: 0.4: x 0.966 / 1.030 (24%); 0.5: x 1.000 / 1.000 (0%); 0.65: x 0.990 / 0.914 (0%)
[stage2] era read, cap_r alone: 1.1: x 1.000 / 1.000 (0%); 1.15: x 1.000 / 1.003 (17%); 1.22: x 0.974 / 0.975 (5%); 1.3: x 0.964 / 0.951 (0%); 1.4: x 0.930 / 0.921 (2%)
[stage2] era read, volc alone: 0.2: x 0.996 / 0.989 (0%); 0.25: x 1.000 / 1.000 (0%); 0.3: x 1.004 / 1.011 (59%); 0.35: x 1.008 / 1.022 (59%)
[stage2] era read, units alone: 2.5: x 0.990 / 0.984 (0%); 3: x 1.000 / 1.000 (0%); 3.5: x 1.010 / 1.016 (61%)

[stage2] O2 max profit at <= current drawdown: 2 settings in the band (era-ok), 0 on a >= 80% plateau; best 8:
   (none)

[stage2] O3 balanced sweet spot: 0 settings in the band (era-ok), 0 on a >= 80% plateau; best 8:
   (none)

[stage2] O4 low-drawdown shield: 1 settings in the band (era-ok), 0 on a >= 80% plateau; best 8:
   (none)

[stage2] O5 high-growth compounder: 1 settings in the band (era-ok), 0 on a >= 80% plateau; best 8:
   (none)
```

**Commentary on Stage 2:**
* **The era gate passes no structural setting** (0 of 53,995). 629 settings improve both eras on the unshifted trade list,
  but the most consistent (VOLC 0.30 + panic 3.5) holds on only 63% of the 41 lists.
* **The one-axis reads match Stage 1:** every structural axis either trades one era for the other (ETH 0.50, alt patterns,
  short 0.40) or is a sleeve near-miss.
* **So the option bands came out almost empty.** Only the 5 pure-scale settings pass the era gate, and the grid's 0.5-point
  BTC step is too coarse for 1.5-point drawdown bands.
* **What this means:** the remaining choices are about risk LEVEL, not structure. So I added Stage 3: a fine BTC dial on the
  era-robust structure, crossed with the ladder shapes and cap_min_fraction (the brief's Stage 2b axes), with explicit
  1-step plateaus.
* The stage-2b function in the script (ladders on stage-2 seeds) was not needed: Stage 3 covers ladders and cap_min_fraction
  on the full dial.

## Step 4: Stage 3, the risk dial, ladders, explicit plateaus

806 settings: BTC 3.5-6.5% by 0.1 × 13 ladders × cap_min_fraction 0.20 / 0.25. The structure is fixed at v3.2.1's, which
passes the era gate by construction; cap_min_fraction 0.20 would need the gate and shows x = 1.000 / 1.000. For each option
band, every candidate's 16 one-step neighbours (the Stage 2 steps) were evaluated explicitly.

**First Stage 3 run (superseded).** It had two flaws, both fixed before the second run:
* O2's band used ≤ 26.2% while v3.2.1 itself is 26.2015%. Now: ≤ 26.2015% / 44.43%.
* Only the 25 best candidates by median were scored. Now every in-band candidate is scored; if none reaches 80%, the
  highest-plateau one is shown and flagged.

```
=== STAGE 3: risk dial (BTC 3.5-6.5% by 0.1, the era-robust v3.2.1 structure) x 13 ladders x cap_min_fraction 0.20 / 0.25 ===
[stage3] 806 dial settings [6s]; cap_min_fraction 0.20 era read at BTC 5%, live ladder: [{'era_x_dev': 1.0, 'era_x_oos': 1.0, 'era_phase': 0.0}]

[stage3] ladders at BTC 5%, cap_min_fraction 0.25:
             ladder     m_2022 dd_2022  m_2024 dd_2024 dd_sep26 dd_oct26 boot_med boot_p10 boot_dd90 p_10k
     live: 10k x0.5  2,030,648   24.51  74,343   26.20    26.58    24.63   28,770    7,672     44.43 0.871
            5k x0.5  1,613,836   24.51  53,916   26.20    26.58    24.63   22,335    7,163     42.74 0.801
           25k x0.5  3,326,273   25.72 116,963   26.20    26.58    24.63   41,871    7,342     45.53 0.855
            1k x0.5    734,414   18.08  30,750   26.18    26.58    24.63   11,391    3,674     38.78 0.544
          10k x0.45  1,343,857   24.51  63,356   26.20    26.58    24.63   26,878    7,721     44.43 0.873
           10k x0.6  4,448,688   24.51 100,563   26.20    26.58    24.63   32,695    7,607     44.43 0.868
            5k x0.6  3,715,505   24.51  78,056   26.20    26.58    24.63   27,118    7,186     42.76 0.822
          25k x0.45  2,352,557   25.72 105,253   26.20    26.58    24.63   40,801    7,342     45.53 0.855
           25k x0.6  6,016,191   25.72 142,513   26.20    26.58    24.63   44,880    7,342     45.56 0.855
 5k x0.75, 25k x0.5  2,406,770   24.51  87,826   26.20    26.58    24.63   33,615    7,334     43.25 0.837
 5k x0.75, 10k x0.5  1,813,503   24.51  70,765   26.20    26.58    24.63   26,505    7,437     43.19 0.843
10k x0.6, 25k x0.45  1,610,631   24.51  78,767   26.20    26.58    24.63   32,202    7,607     44.43 0.868
       no step-down 60,996,039   32.76 267,033   32.76    26.58    24.63   51,073    7,342     46.07 0.855

[stage3] the BTC dial on the live ladder (cap_min_fraction 0.25):
 btc     m_2022 dd_2022  m_2024 dd_2024 dd_sep26 dd_oct26 boot_med boot_p10 boot_dd90 p_10k
 3.5    292,776   18.70  29,356   18.99    19.29    17.82   13,665    3,472     34.27 0.650
 4.0    557,728   19.87  41,197   21.45    21.78    20.14   17,984    4,586     37.98 0.754
 4.3    874,330   21.28  51,147   22.89    23.25    21.51   20,650    5,349     39.85 0.787
 4.5  1,010,131   22.21  57,234   23.84    24.21    22.41   23,009    5,899     41.07 0.813
 4.7  1,328,053   23.13  69,130   24.79    25.17    23.30   25,400    6,505     42.37 0.833
 5.0  2,030,648   24.51  74,343   26.20    26.58    24.63   28,770    7,672     44.43 0.871
 5.3  2,635,217   25.87  97,705   27.59    27.98    25.93   34,370    8,838     46.23 0.892
 5.5  3,121,160   26.77 103,051   28.51    28.89    26.79   37,377    9,968     47.31 0.899
 6.0  5,888,403   29.00 132,539   30.77    31.14    28.91   46,123   11,899     49.87 0.924
 6.5 10,853,394   31.19 177,766   32.98    33.34    30.98   56,096   13,754     52.32 0.941

[stage3] O2 max profit at <= current drawdown: 182 dial settings in the band
   BTC 4.8 25k x0.6             minf 0.25: 2024 $118,069 / 25.26%, boot $39,465 / $6,819 / 44.15%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 4.8 25k x0.5             minf 0.25: 2024 $97,314 / 25.26%, boot $38,289 / $6,819 / 44.15%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 4.8 25k x0.45            minf 0.25: 2024 $87,788 / 25.26%, boot $37,769 / $6,819 / 44.15%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 4.7 25k x0.6             minf 0.25: 2024 $116,452 / 24.79%, boot $37,073 / $6,505 / 43.43%  plateau 57% (fails: btc- btc+ eth_r- short- short+ units-)
   BTC 4.7 25k x0.5             minf 0.25: 2024 $98,540 / 24.79%, boot $36,111 / $6,505 / 43.43%  plateau 57% (fails: btc- btc+ eth_r- short- short+ units-)
   BTC 4.7 25k x0.45            minf 0.25: 2024 $90,121 / 24.79%, boot $35,741 / $6,505 / 43.43%  plateau 57% (fails: btc- btc+ eth_r- short- short+ units-)
   BTC 4.6 25k x0.6             minf 0.25: 2024 $105,631 / 24.32%, boot $35,417 / $6,198 / 42.75%  plateau 79% (fails: btc- btc+ short-)
   BTC 4.6 25k x0.5             minf 0.25: 2024 $89,549 / 24.32%, boot $35,221 / $6,198 / 42.71%  plateau 79% (fails: btc- btc+ short-)
   BTC 4.6 25k x0.45            minf 0.25: 2024 $81,987 / 24.32%, boot $34,486 / $6,198 / 42.71%  plateau 71% (fails: btc- btc+ eth_r- short-)
   BTC 4.5 25k x0.6             minf 0.25: 2024 $95,724 / 23.84%, boot $33,977 / $5,899 / 42.03%  plateau 79% (fails: btc- btc+ short-)
   BTC 4.5 25k x0.5             minf 0.25: 2024 $81,305 / 23.84%, boot $33,488 / $5,899 / 42.03%  plateau 79% (fails: btc- btc+ short-)
   BTC 4.5 25k x0.45            minf 0.25: 2024 $74,522 / 23.84%, boot $33,058 / $5,899 / 42.03%  plateau 79% (fails: btc- btc+ short-)
   BTC 4.4 25k x0.6             minf 0.25: 2024 $89,389 / 23.37%, boot $32,350 / $5,613 / 41.30%  plateau 79% (fails: btc- eth_r- short-)
   BTC 4.9 5k x0.75, 25k x0.5   minf 0.25: 2024 $86,750 / 25.73%, boot $31,995 / $7,075 / 42.77%  plateau 50% (fails: btc- btc+ eth_r- alt_r- short- units- units+)
   BTC 4.4 25k x0.5             minf 0.25: 2024 $77,457 / 23.37%, boot $31,916 / $5,613 / 41.30%  plateau 79% (fails: btc- eth_r- short-)
   BTC 4.4 25k x0.45            minf 0.25: 2024 $71,447 / 23.37%, boot $31,603 / $5,613 / 41.30%  plateau 79% (fails: btc- eth_r- short-)
   BTC 4.9 10k x0.6             minf 0.25: 2024 $106,714 / 25.73%, boot $31,243 / $7,084 / 43.74%  plateau 43% (fails: btc- btc+ eth_r- alt_r- short- short+ units- units+)
   BTC 4.9 10k x0.6, 25k x0.45  minf 0.25: 2024 $82,117 / 25.73%, boot $30,824 / $7,084 / 43.74%  plateau 57% (fails: btc- btc+ short- short+ units- units+)
   BTC 4.8 5k x0.75, 25k x0.5   minf 0.25: 2024 $76,794 / 25.26%, boot $30,744 / $6,830 / 42.56%  plateau 79% (fails: btc- btc+ short-)
   BTC 4.3 25k x0.6             minf 0.25: 2024 $81,527 / 22.89%, boot $30,228 / $5,349 / 40.56%  plateau 86% (fails: btc- short-)
   BTC 4.3 25k x0.5             minf 0.25: 2024 $70,285 / 22.89%, boot $30,017 / $5,349 / 40.56%  plateau 86% (fails: btc- short-)
   BTC 4.3 25k x0.45            minf 0.25: 2024 $64,935 / 22.89%, boot $29,955 / $5,349 / 40.56%  plateau 86% (fails: btc- short-)
   BTC 4.8 10k x0.6             minf 0.25: 2024 $97,323 / 25.26%, boot $29,917 / $6,830 / 43.12%  plateau 57% (fails: btc- btc+ eth_r- short- short+ units-)
   BTC 4.8 10k x0.6, 25k x0.45  minf 0.25: 2024 $76,596 / 25.26%, boot $29,748 / $6,830 / 43.12%  plateau 57% (fails: btc- btc+ eth_r- short- short+ units-)
   BTC 4.7 5k x0.75, 25k x0.5   minf 0.25: 2024 $72,815 / 24.79%, boot $29,375 / $6,572 / 41.86%  plateau 86% (fails: btc- short-)

[stage3] O3 balanced sweet spot: 2 dial settings in the band
   BTC 4.4 25k x0.6             minf 0.25: 2024 $89,389 / 23.37%, boot $32,350 / $5,613 / 41.30%  plateau 64% (fails: btc- btc+ eth_r- short- short+)
   BTC 4.4 25k x0.5             minf 0.25: 2024 $77,457 / 23.37%, boot $31,916 / $5,613 / 41.30%  plateau 64% (fails: btc- btc+ eth_r- short- short+)
[stage3] O3 balanced sweet spot: no candidate on a >= 80% plateau among the 25 best

[stage3] O4 low-drawdown shield: 48 dial settings in the band
   BTC 4.1 25k x0.45            minf 0.25: 2024 $58,469 / 21.93%, boot $26,842 / $4,830 / 39.05%  plateau 64% (fails: btc- btc+ short- short+ units+)
   BTC 4.1 25k x0.5             minf 0.25: 2024 $62,594 / 21.93%, boot $26,710 / $4,830 / 39.05%  plateau 64% (fails: btc- btc+ short- short+ units+)
   BTC 4.1 25k x0.6             minf 0.25: 2024 $71,076 / 21.93%, boot $26,644 / $4,830 / 39.05%  plateau 64% (fails: btc- btc+ short- short+ units+)
   BTC 4.0 25k x0.45            minf 0.25: 2024 $55,789 / 21.45%, boot $24,916 / $4,586 / 38.32%  plateau 64% (fails: btc- btc+ alt_r- short- units-)
   BTC 4.0 25k x0.5             minf 0.25: 2024 $59,465 / 21.45%, boot $24,709 / $4,586 / 38.32%  plateau 64% (fails: btc- btc+ alt_r- short- units-)
   BTC 4.0 25k x0.6             minf 0.25: 2024 $67,045 / 21.45%, boot $24,583 / $4,586 / 38.32%  plateau 64% (fails: btc- btc+ alt_r- short- units-)
   BTC 3.9 25k x0.45            minf 0.25: 2024 $55,103 / 20.96%, boot $22,256 / $4,351 / 37.55%  plateau 71% (fails: btc- btc+ short- units-)
   BTC 3.9 25k x0.5             minf 0.25: 2024 $58,015 / 20.96%, boot $22,252 / $4,351 / 37.55%  plateau 79% (fails: btc- btc+ short-)
   BTC 3.9 25k x0.6             minf 0.25: 2024 $63,797 / 20.96%, boot $22,166 / $4,351 / 37.55%  plateau 79% (fails: btc- btc+ short-)
   BTC 4.1 10k x0.6             minf 0.25: 2024 $55,327 / 21.93%, boot $20,258 / $4,830 / 38.74%  plateau 57% (fails: btc- btc+ eth_r- short- units- units+)
   BTC 4.1 10k x0.6, 25k x0.45  minf 0.25: 2024 $49,173 / 21.93%, boot $20,258 / $4,830 / 38.74%  plateau 71% (fails: btc- btc+ short- units+)
   BTC 3.8 25k x0.6             minf 0.25: 2024 $61,321 / 20.47%, boot $20,239 / $4,117 / 36.78%  plateau 64% (fails: btc- eth_r- alt_r- short- units-)
   BTC 3.8 25k x0.5             minf 0.25: 2024 $54,063 / 20.47%, boot $20,239 / $4,117 / 36.78%  plateau 64% (fails: btc- eth_r- alt_r- short- units-)
   BTC 3.8 25k x0.45            minf 0.25: 2024 $51,585 / 20.47%, boot $20,239 / $4,117 / 36.78%  plateau 64% (fails: btc- eth_r- alt_r- short- units-)
   BTC 4.1 5k x0.75, 25k x0.5   minf 0.25: 2024 $62,981 / 21.93%, boot $19,863 / $4,951 / 38.05%  plateau 29% (fails: btc- btc+ alt_r- alt_r+ altpat+ short- cap_r+ volc+ units- units+)
   BTC 4.0 10k x0.6             minf 0.25: 2024 $50,024 / 21.45%, boot $19,312 / $4,586 / 38.03%  plateau 64% (fails: btc- btc+ eth_r- short- units-)
   BTC 4.0 10k x0.6, 25k x0.45  minf 0.25: 2024 $49,898 / 21.45%, boot $19,312 / $4,586 / 38.03%  plateau 57% (fails: btc- btc+ eth_r- alt_r- short- units-)
   BTC 4.1 live: 10k x0.5       minf 0.25: 2024 $45,428 / 21.93%, boot $18,893 / $4,830 / 38.74%  plateau 57% (fails: btc- btc+ eth_r- short- units- units+)
   BTC 4.0 5k x0.75, 25k x0.5   minf 0.25: 2024 $57,648 / 21.45%, boot $18,327 / $4,641 / 37.23%  plateau 50% (fails: btc- btc+ eth_r- alt_r- short- units- units+)
   BTC 3.9 10k x0.6             minf 0.25: 2024 $44,671 / 20.96%, boot $18,090 / $4,351 / 37.28%  plateau 71% (fails: btc- btc+ eth_r- short-)
   BTC 3.9 10k x0.6, 25k x0.45  minf 0.25: 2024 $43,640 / 20.96%, boot $18,090 / $4,351 / 37.28%  plateau 71% (fails: btc- btc+ eth_r- short-)
   BTC 4.1 10k x0.45            minf 0.25: 2024 $40,943 / 21.93%, boot $18,025 / $4,830 / 38.74%  plateau 57% (fails: btc- btc+ eth_r- short- units- units+)
   BTC 4.0 live: 10k x0.5       minf 0.25: 2024 $41,197 / 21.45%, boot $17,984 / $4,586 / 37.98%  plateau 64% (fails: btc- btc+ eth_r- short- units-)
   BTC 4.0 10k x0.45            minf 0.25: 2024 $37,192 / 21.45%, boot $17,259 / $4,586 / 37.98%  plateau 64% (fails: btc- btc+ eth_r- short- units-)
   BTC 4.1 5k x0.75, 10k x0.5   minf 0.25: 2024 $37,849 / 21.93%, boot $17,219 / $4,951 / 37.93%  plateau 71% (fails: btc- btc+ short- units+)
[stage3] O4 low-drawdown shield: no candidate on a >= 80% plateau among the 25 best

[stage3] O5 high-growth compounder: 25 dial settings in the band
   BTC 5.7 5k x0.75, 25k x0.5   minf 0.25: 2024 $135,477 / 29.42%, boot $46,502 / $9,598 / 47.57%  plateau 64% (fails: btc- btc+ short- short+ units+)
   BTC 5.6 10k x0.6             minf 0.25: 2024 $157,267 / 28.97%, boot $46,156 / $10,305 / 47.89%  plateau 50% (fails: btc- btc+ eth_r- eth_r+ alt_r- short- short+)
   BTC 5.6 5k x0.75, 25k x0.5   minf 0.25: 2024 $135,894 / 28.97%, boot $44,672 / $9,211 / 46.96%  plateau 50% (fails: btc- btc+ eth_r- alt_r- short- short+ units-)
   BTC 5.5 10k x0.6             minf 0.25: 2024 $144,609 / 28.51%, boot $43,661 / $9,792 / 47.51%  plateau 57% (fails: btc- btc+ eth_r- alt_r- short- short+)
   BTC 5.5 5k x0.75, 25k x0.5   minf 0.25: 2024 $121,522 / 28.51%, boot $42,543 / $8,916 / 46.30%  plateau 79% (fails: btc- btc+ short-)
   BTC 5.6 10k x0.6, 25k x0.45  minf 0.25: 2024 $114,022 / 28.97%, boot $42,404 / $10,305 / 47.89%  plateau 57% (fails: btc- btc+ eth_r- eth_r+ short- short+)
   BTC 5.4 10k x0.6             minf 0.25: 2024 $133,877 / 28.05%, boot $41,477 / $9,421 / 46.87%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 5.8 5k x0.6              minf 0.25: 2024 $148,946 / 29.87%, boot $40,623 / $9,104 / 47.71%  plateau 43% (fails: btc- btc+ eth_r- alt_r- short- short+ units- units+)
   BTC 5.5 10k x0.6, 25k x0.45  minf 0.25: 2024 $105,151 / 28.51%, boot $40,513 / $9,792 / 47.51%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 5.7 5k x0.6              minf 0.25: 2024 $137,271 / 29.42%, boot $38,900 / $8,957 / 47.12%  plateau 43% (fails: btc- btc+ eth_r- alt_r- short- short+ units- units+)
   BTC 5.8 5k x0.75, 10k x0.5   minf 0.25: 2024 $114,478 / 29.87%, boot $38,895 / $10,077 / 47.91%  plateau 43% (fails: btc- btc+ eth_r- eth_r+ alt_r- short- short+ units+)
   BTC 5.6 live: 10k x0.5       minf 0.25: 2024 $111,682 / 28.97%, boot $38,847 / $10,437 / 47.87%  plateau 50% (fails: btc- btc+ eth_r- eth_r+ alt_r- short- short+)
   BTC 5.4 10k x0.6, 25k x0.45  minf 0.25: 2024 $97,638 / 28.05%, boot $38,614 / $9,421 / 46.87%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 5.5 live: 10k x0.5       minf 0.25: 2024 $103,051 / 28.51%, boot $37,377 / $9,968 / 47.31%  plateau 57% (fails: btc- btc+ eth_r- alt_r- short- short+)
   BTC 5.6 5k x0.6              minf 0.25: 2024 $128,497 / 28.97%, boot $36,876 / $8,653 / 46.52%  plateau 57% (fails: btc- btc+ eth_r- alt_r- short- units-)
   BTC 5.7 5k x0.75, 10k x0.5   minf 0.25: 2024 $105,816 / 29.42%, boot $36,735 / $9,836 / 47.43%  plateau 64% (fails: btc- btc+ short- short+ units+)
   BTC 5.4 live: 10k x0.5       minf 0.25: 2024 $95,023 / 28.05%, boot $35,697 / $9,446 / 46.82%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 5.6 10k x0.45            minf 0.25: 2024 $93,118 / 28.97%, boot $35,576 / $10,558 / 47.87%  plateau 50% (fails: btc- btc+ eth_r- eth_r+ alt_r- short- short+)
   BTC 5.6 5k x0.75, 10k x0.5   minf 0.25: 2024 $106,220 / 28.97%, boot $34,767 / $9,673 / 46.86%  plateau 57% (fails: btc- btc+ eth_r- alt_r- short- units-)
   BTC 5.5 10k x0.45            minf 0.25: 2024 $86,093 / 28.51%, boot $34,383 / $10,041 / 47.31%  plateau 64% (fails: btc- btc+ eth_r- short- short+)
   BTC 5.5 5k x0.75, 10k x0.5   minf 0.25: 2024 $92,995 / 28.51%, boot $33,257 / $9,172 / 46.20%  plateau 71% (fails: btc- eth_r- alt_r- short-)
   BTC 5.4 10k x0.45            minf 0.25: 2024 $79,547 / 28.05%, boot $33,053 / $9,446 / 46.67%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 5.8 5k x0.5              minf 0.25: 2024 $98,919 / 29.87%, boot $31,617 / $8,473 / 47.65%  plateau 50% (fails: btc- btc+ eth_r- alt_r- short- short+ units+)
   BTC 5.7 5k x0.5              minf 0.25: 2024 $91,504 / 29.42%, boot $30,714 / $8,463 / 47.07%  plateau 57% (fails: btc- btc+ short- short+ units- units+)
   BTC 5.6 5k x0.5              minf 0.25: 2024 $86,333 / 28.97%, boot $29,118 / $8,304 / 46.46%  plateau 57% (fails: btc- btc+ eth_r- alt_r- short- units-)
[stage3] O5 high-growth compounder: no candidate on a >= 80% plateau among the 25 best
[stage3] baseline plateau under the O2 rule: 64%
[stage3] baseline plateau under the O3 rule: 0%
[stage3] baseline plateau under the O4 rule: 0%
[stage3] baseline plateau under the O5 rule: 93%

[stage3] the baseline's 16 one-step neighbours:
 btc  eth_r  alt_r  altpat  short  cap_r  volc  units    m_2022 dd_2022  m_2024 dd_2024 dd_sep26 dd_oct26 boot_med boot_p10 boot_dd90 p_10k
 4.5   0.66  0.166       0   0.50   1.10  0.25    3.0 1,010,131   22.21  57,234   23.84    24.21    22.41   23,009    5,899     41.07 0.813
 5.5   0.66  0.166       0   0.50   1.10  0.25    3.0 3,121,160   26.77 103,051   28.51    28.89    26.79   37,377    9,968     47.31 0.899
 5.0   0.60  0.166       0   0.50   1.10  0.25    3.0 1,732,201   23.36  80,594   26.20    26.06    24.35   27,899    7,125     43.71 0.860
 5.0   0.75  0.166       0   0.50   1.10  0.25    3.0 2,145,558   26.20  86,377   26.37    27.36    25.04   31,464    8,291     45.63 0.880
 5.0   0.66  0.120       0   0.50   1.10  0.25    3.0 1,713,402   25.25  82,460   25.34    26.22    24.64   27,905    7,188     43.96 0.855
 5.0   0.66  0.200       0   0.50   1.10  0.25    3.0 1,972,473   23.98  79,609   27.11    26.85    24.62   30,036    8,157     45.21 0.876
 5.0   0.66  0.166       1   0.50   1.10  0.25    3.0 2,273,097   24.77  77,691   26.61    26.36    24.62   29,553    8,067     44.63 0.874
 5.0   0.66  0.166       0   0.40   1.10  0.25    3.0 1,365,560   23.68  77,175   26.13    25.38    23.40   26,060    6,735     42.94 0.840
 5.0   0.66  0.166       0   0.65   1.10  0.25    3.0 2,498,590   24.97  93,218   26.93    28.36    26.45   34,935    9,172     47.07 0.891
 5.0   0.66  0.166       0   0.50   1.15  0.25    3.0 2,025,502   24.51  75,424   26.20    26.80    24.63   28,938    7,637     44.62 0.870
 5.0   0.66  0.166       0   0.50   1.10  0.20    3.0 1,906,234   24.43  73,615   26.22    26.82    24.63   28,642    7,365     44.72 0.867
 5.0   0.66  0.166       0   0.50   1.10  0.30    3.0 1,837,079   24.59  75,045   26.20    26.35    24.63   29,840    7,879     44.42 0.874
 5.0   0.66  0.166       0   0.50   1.10  0.25    2.5 1,704,053   22.78  79,456   26.27    27.05    24.63   27,316    6,739     44.71 0.848
 5.0   0.66  0.166       0   0.50   1.10  0.25    3.5 2,035,174   26.23  84,295   27.83    26.12    24.63   31,193    8,731     44.16 0.888
```

**Second (final) Stage 3 run:**

```
=== STAGE 3: risk dial (BTC 3.5-6.5% by 0.1, the era-robust v3.2.1 structure) x 13 ladders x cap_min_fraction 0.20 / 0.25 ===
[stage3] 806 dial settings [6s]; cap_min_fraction 0.20 era read at BTC 5%, live ladder: [{'era_x_dev': 1.0, 'era_x_oos': 1.0, 'era_phase': 0.0}]

[stage3] ladders at BTC 5%, cap_min_fraction 0.25:
             ladder     m_2022 dd_2022  m_2024 dd_2024 dd_sep26 dd_oct26 boot_med boot_p10 boot_dd90 p_10k
     live: 10k x0.5  2,030,648   24.51  74,343   26.20    26.58    24.63   28,770    7,672     44.43 0.871
            5k x0.5  1,613,836   24.51  53,916   26.20    26.58    24.63   22,335    7,163     42.74 0.801
           25k x0.5  3,326,273   25.72 116,963   26.20    26.58    24.63   41,871    7,342     45.53 0.855
            1k x0.5    734,414   18.08  30,750   26.18    26.58    24.63   11,391    3,674     38.78 0.544
          10k x0.45  1,343,857   24.51  63,356   26.20    26.58    24.63   26,878    7,721     44.43 0.873
           10k x0.6  4,448,688   24.51 100,563   26.20    26.58    24.63   32,695    7,607     44.43 0.868
            5k x0.6  3,715,505   24.51  78,056   26.20    26.58    24.63   27,118    7,186     42.76 0.822
          25k x0.45  2,352,557   25.72 105,253   26.20    26.58    24.63   40,801    7,342     45.53 0.855
           25k x0.6  6,016,191   25.72 142,513   26.20    26.58    24.63   44,880    7,342     45.56 0.855
 5k x0.75, 25k x0.5  2,406,770   24.51  87,826   26.20    26.58    24.63   33,615    7,334     43.25 0.837
 5k x0.75, 10k x0.5  1,813,503   24.51  70,765   26.20    26.58    24.63   26,505    7,437     43.19 0.843
10k x0.6, 25k x0.45  1,610,631   24.51  78,767   26.20    26.58    24.63   32,202    7,607     44.43 0.868
       no step-down 60,996,039   32.76 267,033   32.76    26.58    24.63   51,073    7,342     46.07 0.855

[stage3] the BTC dial on the live ladder (cap_min_fraction 0.25):
 btc     m_2022 dd_2022  m_2024 dd_2024 dd_sep26 dd_oct26 boot_med boot_p10 boot_dd90 p_10k
 3.5    292,776   18.70  29,356   18.99    19.29    17.82   13,665    3,472     34.27 0.650
 4.0    557,728   19.87  41,197   21.45    21.78    20.14   17,984    4,586     37.98 0.754
 4.3    874,330   21.28  51,147   22.89    23.25    21.51   20,650    5,349     39.85 0.787
 4.5  1,010,131   22.21  57,234   23.84    24.21    22.41   23,009    5,899     41.07 0.813
 4.7  1,328,053   23.13  69,130   24.79    25.17    23.30   25,400    6,505     42.37 0.833
 5.0  2,030,648   24.51  74,343   26.20    26.58    24.63   28,770    7,672     44.43 0.871
 5.3  2,635,217   25.87  97,705   27.59    27.98    25.93   34,370    8,838     46.23 0.892
 5.5  3,121,160   26.77 103,051   28.51    28.89    26.79   37,377    9,968     47.31 0.899
 6.0  5,888,403   29.00 132,539   30.77    31.14    28.91   46,123   11,899     49.87 0.924
 6.5 10,853,394   31.19 177,766   32.98    33.34    30.98   56,096   13,754     52.32 0.941

[stage3] O2 max profit at <= current drawdown: 190 dial settings in the band (all scored; the 12 best by bootstrap median shown, then the pick)
   BTC 4.8 25k x0.6             minf 0.25: 2024 $118,069 / 25.26%, boot $39,465 / $6,819 / 44.15%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 4.8 25k x0.5             minf 0.25: 2024 $97,314 / 25.26%, boot $38,289 / $6,819 / 44.15%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 4.8 25k x0.45            minf 0.25: 2024 $87,788 / 25.26%, boot $37,769 / $6,819 / 44.15%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 4.7 25k x0.6             minf 0.25: 2024 $116,452 / 24.79%, boot $37,073 / $6,505 / 43.43%  plateau 57% (fails: btc- btc+ eth_r- short- short+ units-)
   BTC 4.7 25k x0.5             minf 0.25: 2024 $98,540 / 24.79%, boot $36,111 / $6,505 / 43.43%  plateau 57% (fails: btc- btc+ eth_r- short- short+ units-)
   BTC 4.7 25k x0.45            minf 0.25: 2024 $90,121 / 24.79%, boot $35,741 / $6,505 / 43.43%  plateau 57% (fails: btc- btc+ eth_r- short- short+ units-)
   BTC 4.6 25k x0.6             minf 0.25: 2024 $105,631 / 24.32%, boot $35,417 / $6,198 / 42.75%  plateau 79% (fails: btc- btc+ short-)
   BTC 4.6 25k x0.5             minf 0.25: 2024 $89,549 / 24.32%, boot $35,221 / $6,198 / 42.71%  plateau 79% (fails: btc- btc+ short-)
   BTC 4.6 25k x0.45            minf 0.25: 2024 $81,987 / 24.32%, boot $34,486 / $6,198 / 42.71%  plateau 71% (fails: btc- btc+ eth_r- short-)
   BTC 4.5 25k x0.6             minf 0.25: 2024 $95,724 / 23.84%, boot $33,977 / $5,899 / 42.03%  plateau 79% (fails: btc- btc+ short-)
   BTC 5.0 5k x0.75, 25k x0.5   minf 0.25: 2024 $87,826 / 26.20%, boot $33,615 / $7,334 / 43.25%  plateau 64% (fails: btc- btc+ short- short+ units+)
   BTC 4.5 25k x0.5             minf 0.25: 2024 $81,305 / 23.84%, boot $33,488 / $5,899 / 42.03%  plateau 79% (fails: btc- btc+ short-)
   PICK (best bootstrap median on a >= 80% plateau): BTC 4.3 25k x0.6             minf 0.25: 2024 $81,527 / 22.89%, boot $30,228 / $5,349 / 40.56%  plateau 86% (fails: btc- short-)

[stage3] O3 balanced sweet spot: 2 dial settings in the band (all scored; the 12 best by bootstrap median shown, then the pick)
   BTC 4.4 25k x0.6             minf 0.25: 2024 $89,389 / 23.37%, boot $32,350 / $5,613 / 41.30%  plateau 64% (fails: btc- btc+ eth_r- short- short+)
   BTC 4.4 25k x0.5             minf 0.25: 2024 $77,457 / 23.37%, boot $31,916 / $5,613 / 41.30%  plateau 64% (fails: btc- btc+ eth_r- short- short+)
   PICK (none >= 80%: the highest plateau in the band): BTC 4.4 25k x0.6             minf 0.25: 2024 $89,389 / 23.37%, boot $32,350 / $5,613 / 41.30%  plateau 64% (fails: btc- btc+ eth_r- short- short+)

[stage3] O4 low-drawdown shield: 48 dial settings in the band (all scored; the 12 best by bootstrap median shown, then the pick)
   BTC 4.1 25k x0.45            minf 0.25: 2024 $58,469 / 21.93%, boot $26,842 / $4,830 / 39.05%  plateau 64% (fails: btc- btc+ short- short+ units+)
   BTC 4.1 25k x0.5             minf 0.25: 2024 $62,594 / 21.93%, boot $26,710 / $4,830 / 39.05%  plateau 64% (fails: btc- btc+ short- short+ units+)
   BTC 4.1 25k x0.6             minf 0.25: 2024 $71,076 / 21.93%, boot $26,644 / $4,830 / 39.05%  plateau 64% (fails: btc- btc+ short- short+ units+)
   BTC 4.0 25k x0.45            minf 0.25: 2024 $55,789 / 21.45%, boot $24,916 / $4,586 / 38.32%  plateau 64% (fails: btc- btc+ alt_r- short- units-)
   BTC 4.0 25k x0.5             minf 0.25: 2024 $59,465 / 21.45%, boot $24,709 / $4,586 / 38.32%  plateau 64% (fails: btc- btc+ alt_r- short- units-)
   BTC 4.0 25k x0.6             minf 0.25: 2024 $67,045 / 21.45%, boot $24,583 / $4,586 / 38.32%  plateau 64% (fails: btc- btc+ alt_r- short- units-)
   BTC 3.9 25k x0.45            minf 0.25: 2024 $55,103 / 20.96%, boot $22,256 / $4,351 / 37.55%  plateau 71% (fails: btc- btc+ short- units-)
   BTC 3.9 25k x0.5             minf 0.25: 2024 $58,015 / 20.96%, boot $22,252 / $4,351 / 37.55%  plateau 79% (fails: btc- btc+ short-)
   BTC 3.9 25k x0.6             minf 0.25: 2024 $63,797 / 20.96%, boot $22,166 / $4,351 / 37.55%  plateau 79% (fails: btc- btc+ short-)
   BTC 4.1 10k x0.6             minf 0.25: 2024 $55,327 / 21.93%, boot $20,258 / $4,830 / 38.74%  plateau 57% (fails: btc- btc+ eth_r- short- units- units+)
   BTC 4.1 10k x0.6, 25k x0.45  minf 0.25: 2024 $49,173 / 21.93%, boot $20,258 / $4,830 / 38.74%  plateau 71% (fails: btc- btc+ short- units+)
   BTC 3.8 25k x0.6             minf 0.25: 2024 $61,321 / 20.47%, boot $20,239 / $4,117 / 36.78%  plateau 64% (fails: btc- eth_r- alt_r- short- units-)
   PICK (best bootstrap median on a >= 80% plateau): BTC 3.8 10k x0.6             minf 0.25: 2024 $40,032 / 20.47%, boot $17,063 / $4,117 / 36.61%  plateau 93% (fails: btc-)

[stage3] O5 high-growth compounder: 25 dial settings in the band (all scored; the 12 best by bootstrap median shown, then the pick)
   BTC 5.7 5k x0.75, 25k x0.5   minf 0.25: 2024 $135,477 / 29.42%, boot $46,502 / $9,598 / 47.57%  plateau 64% (fails: btc- btc+ short- short+ units+)
   BTC 5.6 10k x0.6             minf 0.25: 2024 $157,267 / 28.97%, boot $46,156 / $10,305 / 47.89%  plateau 50% (fails: btc- btc+ eth_r- eth_r+ alt_r- short- short+)
   BTC 5.6 5k x0.75, 25k x0.5   minf 0.25: 2024 $135,894 / 28.97%, boot $44,672 / $9,211 / 46.96%  plateau 50% (fails: btc- btc+ eth_r- alt_r- short- short+ units-)
   BTC 5.5 10k x0.6             minf 0.25: 2024 $144,609 / 28.51%, boot $43,661 / $9,792 / 47.51%  plateau 57% (fails: btc- btc+ eth_r- alt_r- short- short+)
   BTC 5.5 5k x0.75, 25k x0.5   minf 0.25: 2024 $121,522 / 28.51%, boot $42,543 / $8,916 / 46.30%  plateau 79% (fails: btc- btc+ short-)
   BTC 5.6 10k x0.6, 25k x0.45  minf 0.25: 2024 $114,022 / 28.97%, boot $42,404 / $10,305 / 47.89%  plateau 57% (fails: btc- btc+ eth_r- eth_r+ short- short+)
   BTC 5.4 10k x0.6             minf 0.25: 2024 $133,877 / 28.05%, boot $41,477 / $9,421 / 46.87%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 5.8 5k x0.6              minf 0.25: 2024 $148,946 / 29.87%, boot $40,623 / $9,104 / 47.71%  plateau 43% (fails: btc- btc+ eth_r- alt_r- short- short+ units- units+)
   BTC 5.5 10k x0.6, 25k x0.45  minf 0.25: 2024 $105,151 / 28.51%, boot $40,513 / $9,792 / 47.51%  plateau 71% (fails: btc- btc+ short- short+)
   BTC 5.7 5k x0.6              minf 0.25: 2024 $137,271 / 29.42%, boot $38,900 / $8,957 / 47.12%  plateau 43% (fails: btc- btc+ eth_r- alt_r- short- short+ units- units+)
   BTC 5.8 5k x0.75, 10k x0.5   minf 0.25: 2024 $114,478 / 29.87%, boot $38,895 / $10,077 / 47.91%  plateau 43% (fails: btc- btc+ eth_r- eth_r+ alt_r- short- short+ units+)
   BTC 5.6 live: 10k x0.5       minf 0.25: 2024 $111,682 / 28.97%, boot $38,847 / $10,437 / 47.87%  plateau 50% (fails: btc- btc+ eth_r- eth_r+ alt_r- short- short+)
   PICK (none >= 80%: the highest plateau in the band): BTC 5.5 5k x0.75, 25k x0.5   minf 0.25: 2024 $121,522 / 28.51%, boot $42,543 / $8,916 / 46.30%  plateau 79% (fails: btc- btc+ short-)
[stage3] baseline plateau under the O2 rule: 64%
[stage3] baseline plateau under the O3 rule: 0%
[stage3] baseline plateau under the O4 rule: 0%
[stage3] baseline plateau under the O5 rule: 93%

[stage3] the baseline's 16 one-step neighbours:
 btc  eth_r  alt_r  altpat  short  cap_r  volc  units    m_2022 dd_2022  m_2024 dd_2024 dd_sep26 dd_oct26 boot_med boot_p10 boot_dd90 p_10k
 4.5   0.66  0.166       0   0.50   1.10  0.25    3.0 1,010,131   22.21  57,234   23.84    24.21    22.41   23,009    5,899     41.07 0.813
 5.5   0.66  0.166       0   0.50   1.10  0.25    3.0 3,121,160   26.77 103,051   28.51    28.89    26.79   37,377    9,968     47.31 0.899
 5.0   0.60  0.166       0   0.50   1.10  0.25    3.0 1,732,201   23.36  80,594   26.20    26.06    24.35   27,899    7,125     43.71 0.860
 5.0   0.75  0.166       0   0.50   1.10  0.25    3.0 2,145,558   26.20  86,377   26.37    27.36    25.04   31,464    8,291     45.63 0.880
 5.0   0.66  0.120       0   0.50   1.10  0.25    3.0 1,713,402   25.25  82,460   25.34    26.22    24.64   27,905    7,188     43.96 0.855
 5.0   0.66  0.200       0   0.50   1.10  0.25    3.0 1,972,473   23.98  79,609   27.11    26.85    24.62   30,036    8,157     45.21 0.876
 5.0   0.66  0.166       1   0.50   1.10  0.25    3.0 2,273,097   24.77  77,691   26.61    26.36    24.62   29,553    8,067     44.63 0.874
 5.0   0.66  0.166       0   0.40   1.10  0.25    3.0 1,365,560   23.68  77,175   26.13    25.38    23.40   26,060    6,735     42.94 0.840
 5.0   0.66  0.166       0   0.65   1.10  0.25    3.0 2,498,590   24.97  93,218   26.93    28.36    26.45   34,935    9,172     47.07 0.891
 5.0   0.66  0.166       0   0.50   1.15  0.25    3.0 2,025,502   24.51  75,424   26.20    26.80    24.63   28,938    7,637     44.62 0.870
 5.0   0.66  0.166       0   0.50   1.10  0.20    3.0 1,906,234   24.43  73,615   26.22    26.82    24.63   28,642    7,365     44.72 0.867
 5.0   0.66  0.166       0   0.50   1.10  0.30    3.0 1,837,079   24.59  75,045   26.20    26.35    24.63   29,840    7,879     44.42 0.874
 5.0   0.66  0.166       0   0.50   1.10  0.25    2.5 1,704,053   22.78  79,456   26.27    27.05    24.63   27,316    6,739     44.71 0.848
 5.0   0.66  0.166       0   0.50   1.10  0.25    3.5 2,035,174   26.23  84,295   27.83    26.12    24.63   31,193    8,731     44.16 0.888
```

**Commentary on Stage 3:**
* **The ladder's shape is the biggest money lever.** Full risk to $25k instead of $10k lifts the bootstrap median from
  $28.8k to $41.9k. The 2024-run drop is unchanged, because its worst drop happens below $10k. The cost is +1.1 points of
  dd90 and 4% less p10.
* **The plateau rule is hard for risk settings by construction.** One step down in BTC, short or panic units costs > 10%
  of the money, so that neighbour always fails. One step up breaks the ceiling near a band's top. The reachable maximum is
  ~87-94%.
* **Results by option:**
  * O2: a ≥ 80% pick (86%).
  * O4: a ≥ 80% pick (93%).
  * O3: only 2 settings in its band (64%, flagged).
  * O5: best is 79%, flagged.
  * The baseline: 64% under its own rule, 93% under the high-growth rule.

## Step 5: Stage 4, the five options with full metrics

```
=== STAGE 4: the five options, full metrics ===
option                  O1 current v3.2.1 (26f07bf) O2 max profit at <= current drawdown O3 balanced sweet spot O4 low-drawdown shield O5 high-growth compounder
ladder                               live: 10k x0.5                             25k x0.6               25k x0.6               10k x0.6        5k x0.75, 25k x0.5
minf                                           0.25                                 0.25                   0.25                   0.25                      0.25
short                                           0.5                                  0.5                    0.5                    0.5                       0.5
volc                                           0.25                                 0.25                   0.25                   0.25                      0.25
panic_units                                     3.0                                  3.0                    3.0                    3.0                       3.0
plateau                                         NaN                             0.857143               0.642857               0.928571                  0.785714
r0_from                                         0.0                                  0.0                    0.0                    0.0                       0.0
r0_BTC                                          5.0                                  4.3                    4.4                    3.8                       5.5
r0_ETH                                          3.3                                2.838                  2.904                  2.508                      3.63
r0_BNB                                         0.83                               0.7138                 0.7304                 0.6308                     0.913
r0_SOL                                         0.83                               0.7138                 0.7304                 0.6308                     0.913
r0_ADA                                         0.83                               0.7138                 0.7304                 0.6308                     0.913
r0_cap                                          5.5                                 4.73                   4.84                   4.18                      6.05
r1_from                                      1000.0                              25000.0                25000.0                10000.0                    5000.0
r1_BTC                                          5.0                                 2.58                   2.64                   2.28                     4.125
r1_ETH                                          3.3                               1.7544                 1.7952                 1.5504                     2.805
r1_BNB                                         0.83                               0.4334                 0.4435                  0.383                     0.693
r1_SOL                                         0.83                               0.4334                 0.4435                  0.383                     0.693
r1_ADA                                         0.83                               0.4334                 0.4435                  0.383                     0.693
r1_cap                                          5.5                                2.838                  2.904                  2.508                    4.5375
r2_from                                     10000.0                                  NaN                    NaN                    NaN                   25000.0
r2_BTC                                          2.5                                  NaN                    NaN                    NaN                      2.75
r2_ETH                                          1.7                                  NaN                    NaN                    NaN                      1.87
r2_BNB                                         0.42                                  NaN                    NaN                    NaN                     0.462
r2_SOL                                         0.42                                  NaN                    NaN                    NaN                     0.462
r2_ADA                                         0.42                                  NaN                    NaN                    NaN                     0.462
r2_cap                                         2.75                                  NaN                    NaN                    NaN                     3.025
m_2022                               2030647.516775                         2172819.2234         2549564.154364          928132.052736            4512063.507008
dd_2022                                    24.50648                            22.605764              23.083822              20.150561                 26.770194
m_2024                                 74343.331265                         81526.948615           89389.262549           40031.676853             121521.753363
dd_2024                                   26.201465                            22.892811              23.369356              20.473878                 28.512443
dd_sep26_inrun                              14.2232                            14.649804              14.968636              13.041187                 15.550672
bal_sep26_inrun                        67127.476966                         73449.639728            80401.11766           36379.289969             108983.360162
dd_sep26_inrun_from_ath                     14.2232                            14.649804              14.968636              13.041187                 15.550672
m_sep26                                  348.594961                           345.509979             346.015444             342.646744                350.172744
dd_sep26                                  26.583131                            23.249213              23.732784              20.794305                 28.892549
m_oct26                                  234.223361                           242.731131             241.502175             248.944279                228.280939
dd_oct26                                   24.62857                            21.509668               21.96145              19.219185                 26.794917
boot_med                               28770.119234                         30228.086893           32349.876701            17063.39163              42542.776257
boot_p10                                7672.122818                          5349.255115            5613.157067            4116.826397               8916.342261
boot_dd90                                 44.429475                            40.560437              41.304902              36.612147                 46.304282
p_10k                                         0.871                                0.778                  0.789                   0.71                     0.886
p_loss                                          0.0                                  0.0                    0.0                    0.0                       0.0
losing_months                                    11                                   11                     10                     11                        11
months                                           35                                   35                     35                     35                        35
```

**Commentary on Stage 4:**
* **O2 gives up the small-account tail** (p10 -30%, P(≥ $10k) 77.8% vs 87.1%) for a higher median and lower drawdown. It
  sizes smaller below $10k and larger between $10k and $25k.
* **O5 improves every money and tail figure** (p10 $8.92k, P(≥ $10k) 88.6%) at +2.3 points of 2024 drop and +1.9 of dd90.
* **O4 halves the bootstrap outcomes.**
* **Recommendation (see the report): keep O1.** O5 is the alternative if about 2 more points of drawdown are acceptable.

## Files written

| File | What it holds |
|---|---|
| `v34_stage1_marginal.csv` | Stage 1: 74 settings |
| `v34_stage1_cap_counts.csv` | Per-coin full / shrunk / skipped counts |
| `v34_stage2_grid.csv.gz` | Stage 2: 54,000 settings, all metrics, era columns, plateau columns |
| `v34_stage3_dial.csv` | Stage 3: 806 settings |
| `v34_stage3_baseline_neighbours.csv` | The baseline's 16 one-step neighbours |
| `v34_stage4_options.csv` | The five options: ladder rows per coin, caps, all metrics |
| `v34_stage_output.txt` | The raw stage log (what this transcript quotes) |
| `v34_risk_audit_REPORT.md` | The report |
