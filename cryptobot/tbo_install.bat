@echo off
rem TBO installer (Windows): installs and updates the bot on Ubuntu servers (VDS / VPS) from this PC.
rem   MY SERVER     : your own server (its IP is asked once and kept in my_server.txt)
rem   OTHER PEOPLE  : friends' servers (name + IP kept in servers.txt); each one trades with his OWN Binance keys
rem The first contact with a server asks its root password once; after that this PC logs in with its SSH key.
rem Updates: git pull on this PC, then the code is sent to the server (no GitHub access on friends' servers);
rem the server's .env, state files and logs are never touched. A server that has a git checkout pulls by itself.
setlocal EnableExtensions EnableDelayedExpansion
title TBO installer
cd /d "%~dp0"
set "LIST=%~dp0servers.txt"
set "MINE=%~dp0my_server.txt"
set "KEY=%USERPROFILE%\.ssh\id_ed25519"
set "SSHO=-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15"
rem the SSH key kept in the (private) repo: copied to this PC's .ssh folder (Windows ssh refuses keys with loose file rights)
if exist "%~dp0secrets\tbo_key" (
  if not exist "%USERPROFILE%\.ssh" mkdir "%USERPROFILE%\.ssh"
  copy /y "%~dp0secrets\tbo_key" "%USERPROFILE%\.ssh\tbo_repo_key" >nul
  set "SSHO=%SSHO% -i "%USERPROFILE%\.ssh\tbo_repo_key""
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
