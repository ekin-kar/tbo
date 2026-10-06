@echo off
rem Windows: runs all four TBO bots (restarts them if they stop). Close this window or Ctrl+C to stop.
cd /d %~dp0
python run_all.py
pause
