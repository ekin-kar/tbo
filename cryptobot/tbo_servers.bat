@echo off
rem TBO server manager (Windows): set up, update and watch the bot on one or more Ubuntu servers (VDS / VPS).
rem Servers are remembered in servers.txt next to this file (name and IP, one per line; not uploaded to GitHub).
rem First contact with a server asks its root password once; after that this PC logs in with its SSH key.
setlocal EnableExtensions EnableDelayedExpansion
title TBO server manager
cd /d "%~dp0"
set "LIST=%~dp0servers.txt"
set "KEY=%USERPROFILE%\.ssh\id_ed25519"
set "SSHO=-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15"

:pick
cls
echo.
echo   TBO server manager
echo   ==================
echo.
set n=0
if exist "%LIST%" for /f "usebackq tokens=1,2" %%a in ("%LIST%") do (
  set /a n+=1
  set "NAME!n!=%%a"
  set "IP!n!=%%b"
  echo    !n!  %%a  ^(%%b^)
)
if !n!==0 echo    ^(no servers yet^)
echo.
echo    A  Add a server
echo    0  Exit
echo.
set "c="
set /p "c=  Choose: "
if /i "!c!"=="A" goto add
if "!c!"=="0" exit /b
if "!c!"=="" goto pick
if not defined IP!c! goto pick
set "IP=!IP%c%!"
set "NAME=!NAME%c%!"
goto menu

:add
echo.
set "NAME="
set /p "NAME=  A one-word name for this server (e.g. Ali): "
set "IP="
set /p "IP=  Its IP address: "
if "!NAME!"=="" goto pick
if "!IP!"=="" goto pick
>>"%LIST%" echo !NAME! !IP!
goto menu

:menu
cls
echo.
echo   TBO on !NAME!  (root@!IP!)
echo   ------------------------------------------
echo    1  First-time setup  (installs everything, asks the Binance / Telegram keys)
echo    2  Update the bot  (latest code) + restart
echo    3  Live output  (Ctrl+C to come back here)
echo    4  Status + memory
echo    5  Restart the bot
echo    6  Stop the bot
echo    7  Start the bot
echo    8  Check the setup  (check_setup.py)
echo    9  Server terminal
echo    B  Back to the server list
echo.
set "c="
set /p "c=  Choose: "
if "!c!"=="1" call :setup
if "!c!"=="2" call :update
if "!c!"=="3" ssh -t %SSHO% root@!IP! "journalctl -u tbo -f -o cat _SYSTEMD_INVOCATION_ID=$(systemctl show -p InvocationID --value tbo)"
if "!c!"=="4" ssh -t %SSHO% root@!IP! "systemctl status tbo --no-pager | head -12; echo; free -h; echo; uptime"
if "!c!"=="5" ssh -t %SSHO% root@!IP! "systemctl restart tbo && echo Bot restarted."
if "!c!"=="6" call :stop
if "!c!"=="7" ssh -t %SSHO% root@!IP! "systemctl enable --now tbo && echo Bot started."
if "!c!"=="8" ssh -t %SSHO% root@!IP! "cd /home/tbo/trade3/cryptobot && sudo -u tbo venv/bin/python check_setup.py"
if "!c!"=="9" ssh -t %SSHO% root@!IP!
if /i "!c!"=="B" goto pick
echo.
pause
goto menu

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
  echo   Type the server's ROOT PASSWORD ^(only this once; nothing shows while you type^):
  type "%KEY%.pub" | ssh %SSHO% root@!IP! "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && sort -u -o ~/.ssh/authorized_keys ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
)
ssh -o BatchMode=yes %SSHO% root@!IP! "true" >nul 2>&1
if errorlevel 1 (
  echo   Could not log in to !IP! with the key. Check the IP and the password and try again.
  exit /b 1
)
exit /b 0

rem ── package this PC's bot folder (after git pull), without keys, state files, logs or venv ──
:pkg
set "ROOT=%~dp0.."
if exist "%ROOT%\.git" (
  echo   Getting the latest code from GitHub on this PC...
  git -C "%ROOT%" pull
)
set "PKG=%TEMP%\cryptobot.tgz"
del "%PKG%" >nul 2>&1
tar -czf "%PKG%" --exclude=venv --exclude=.env --exclude="state_*" --exclude=logs --exclude=__pycache__ --exclude=trial_results --exclude=PAUSE --exclude=servers.txt --exclude="*.tmp" -C "%ROOT%" cryptobot
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
  echo   This server is already set up ^(it has its keys^). To get the latest code use 2 - Update.
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
if "!AK!"=="" ( echo   No API key given: setup cancelled. & exit /b )
set "ENVF=%TEMP%\tbo.env"
> "%ENVF%" (
  echo BINANCE_API_KEY=!AK!
  echo BINANCE_API_SECRET=!AS!
  echo TELEGRAM_TOKEN=!TT!
  echo TELEGRAM_CHAT_ID=!TC!
  echo TELEGRAM_UTC_OFFSET=3
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
ssh -t %SSHO% root@!IP! "cd /home/tbo/trade3/cryptobot && sudo -u tbo venv/bin/python check_setup.py"
echo.
set "y="
set /p "y=  Did it end with RESULT: ready?  Start the bot now (y/n): "
if /i "!y!"=="y" ssh -t %SSHO% root@!IP! "systemctl enable --now tbo && echo Bot started. Waiting 30 s for its first lines... && sleep 30 && journalctl -u tbo -o cat --no-pager -n 25"
exit /b

:update
call :ensurekey || exit /b
call :pkg || exit /b
echo   Uploading...
scp %SSHO% "%PKG%" "%~dp0vds_setup.sh" root@!IP!:/root/
ssh -t %SSHO% root@!IP! "sed -i 's/\r$//' /root/vds_setup.sh && bash /root/vds_setup.sh && systemctl restart tbo && echo Bot updated and restarted."
exit /b

:stop
set "y="
set /p "y=  Stop the bot? No new orders; open trades keep their stop loss on Binance. Type y to confirm: "
if /i "!y!"=="y" ssh -t %SSHO% root@!IP! "systemctl stop tbo && echo Bot stopped."
exit /b
