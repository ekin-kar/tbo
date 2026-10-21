@echo off
rem Windows: runs all six TBO bots (BTC, ETH, BNB, SOL, ADA, AVAX) (restarts them if they stop). Close this window or Ctrl+C to stop.
cd /d %~dp0
python run_all.py
pause
