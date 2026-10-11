@echo off
rem Day-to-day control of the bot on MY server (watch, status, restart, update, stop / start).
rem The server's IP is kept in my_server.txt next to this file (shared with tbo_install.bat; asked once if missing).
setlocal EnableExtensions EnableDelayedExpansion
title TBO bot on the VDS
cd /d "%~dp0"
set "MINE=%~dp0my_server.txt"
set "MYIP="
if exist "%MINE%" set /p MYIP=<"%MINE%"
if not defined MYIP (
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
echo    5  Update from GitHub + restart
echo    6  Stop the bot
echo    7  Start the bot
echo    8  Open a server terminal
echo    9  Clean up the server  (old logs, caches; also sets up the weekly cleanup)
echo    0  Exit
echo.
set "c="
set /p "c=  Choose: "
if "!c!"=="1" ssh -t !HOST! "journalctl -u tbo -f -o cat _SYSTEMD_INVOCATION_ID=$(systemctl show -p InvocationID --value tbo)"
if "!c!"=="2" ssh -t !HOST! "journalctl -u tbo -o cat --no-pager _SYSTEMD_INVOCATION_ID=$(systemctl show -p InvocationID --value tbo) | tail -200"
if "!c!"=="3" ssh -t !HOST! "systemctl status tbo --no-pager | head -12; echo; free -h; echo; uptime"
if "!c!"=="4" ssh -t !HOST! "systemctl restart tbo && echo Bot restarted."
if "!c!"=="5" ssh -t !HOST! "if [ -d /home/tbo/trade3/.git ]; then su - tbo -c 'cd trade3 && git pull' && systemctl restart tbo && echo Updated and restarted.; else echo This server is updated by the person who installed it, with tbo_install.bat. Nothing to do here.; fi"
if "!c!"=="6" (
  set "y="
  set /p "y=  Stop the bot? No new orders; open trades keep their stop loss on Binance. Type y to confirm: "
  if /i "!y!"=="y" ssh -t !HOST! "systemctl stop tbo && echo Bot stopped."
)
if "!c!"=="7" ssh -t !HOST! "systemctl start tbo && echo Bot started."
if "!c!"=="8" ssh -t !HOST!
if "!c!"=="9" ssh -t !HOST! "sed -i 's/\r$//' /home/tbo/trade3/cryptobot/server_clean.sh; bash /home/tbo/trade3/cryptobot/server_clean.sh --install"
if "!c!"=="0" exit /b
echo.
pause
goto menu
