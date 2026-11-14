# v3.5 research: session log (14 Nov 2026)

Branch `v35-research` from 17a6ce1. Environment: `~/.venvs/tbo`, `TRADING_CACHE=~/.cache/tbo` (the repo's own `cache/` is empty).
`cryptobot/` was only read. Every printed table is in `v35_stage_output.txt` (appended by each run; it contains the first T3 pass, see step 4).

1. **Harness check.** `python v35_new_strategies_and_volc_extra.py check`: O1 reproduced exactly (2022 $2,030,648 / 24.51%, 2024 $74,343 / 26.20%,
   boot $28,770 / $7,672 / 44.43%); an empty extra sleeve leaves the numbers unchanged; the inside-the-cap class path runs.
2. **T1.** First run: VOLC on EXTRA7 reproduced v3.3 (89 / +34.1R, 95 / +18.1R). My first drawdown figures differed (4.2R / 8.8R) because the
   per-era stream was not sorted by exit time; fixed (now 5.2R / 6.9R as v3.3 printed). HOLD_BIG was skipped (the loader read `data/extra` only); fixed
   by pointing the OI loader at `data/extra2`, re-run; one corrupt ICP stop-distance row (R about -1e31) excluded. 0 of 136 pool settings pass.
3. **T2.** 432 settings, none passes G1a (median PF 0.86 / 0.83).
4. **T3, first pass.** Reported "12 of 18 G3 passes" for T3b. Inspection: 1-2 trades per era, money moved by about $10, G1 false, plateau 0.13. Noise in a
   972-setting grid. I added the 30-trades-per-era rule to G1 (and to the fallback ranking) and re-ran T3, T4, T5 under it. T3 now has no candidate.
5. **T4.** First run crashed (a column was both an ordinal and a categorical axis for the plateau); fixed. 4a: 17 settings pass G1a, plateau <= 0.12.
   Checked the low bootstrap share directly: monthly R of the best cell is lumpy (+25R month vs several -10R months), and by year the edge is
   2023 -0.4R, 2026 -35.2R. It is real, not a bug.
6. **T5.** 5a too few trades. 5b passes G3 on 4 settings but not G1 / G2 (see report).

Files: `v35_REPORT.md`, `v35_T*_grid.csv` (standalone grids), `v35_T*_money.csv` (coupled runs), `v35_T1_*` (audits and the extra-pool grid).
