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
