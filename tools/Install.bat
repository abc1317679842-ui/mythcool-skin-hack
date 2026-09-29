@echo off
REM ============================================================
REM  Myth.Cool Skin Hack - one time installer
REM
REM  1. prepares the runtime (copies files, builds a private
REM     Python venv, installs frida)
REM  2. verifies the silent launcher
REM  3. registers the scheduled task \MythCoolInject
REM  4. applies the patch once, right now
REM  5. reports the result
REM
REM  Needs admin: the scheduled task runs HighestAvailable so frida can
REM  attach to the Myth.Cool main process, which does the same.
REM
REM  Written WITHOUT goto / labels / multi-line if-blocks on purpose so it
REM  also works if the file ends up with LF-only line endings.
REM  ASCII only.
REM ============================================================

setlocal
set "SRC=%~dp0"
set "DEST=%ProgramData%\MythCoolInject"

net session >nul 2>&1
set "ELEV=%errorlevel%"

if not "%ELEV%"=="0" powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
if not "%ELEV%"=="0" exit /b

echo ============================================================
echo  Myth.Cool Skin Hack - installer   (running as admin)
echo ============================================================
echo.

echo [1/5] preparing runtime (copy files + python venv + frida)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%Setup-Runtime.ps1" -Dest "%DEST%"
if errorlevel 1 echo   [ERROR] runtime setup failed - aborting.
if errorlevel 1 timeout /t 120 >nul
if errorlevel 1 exit /b 1
echo.

echo [2/5] verifying the silent launcher (must return 0)...
cscript //nologo "%DEST%\InjectSilent.vbs"
set "LRC=%errorlevel%"
echo   launcher exit code = %LRC%
if not "%LRC%"=="0" echo   [ERROR] launcher failed - the task would never inject. Aborting.
if not "%LRC%"=="0" timeout /t 120 >nul
if not "%LRC%"=="0" exit /b 1
echo.

echo [3/5] registering scheduled task...
powershell -NoProfile -ExecutionPolicy Bypass -File "%DEST%\Register-Task.ps1"
if errorlevel 1 echo   [ERROR] task registration failed - aborting.
if errorlevel 1 timeout /t 120 >nul
if errorlevel 1 exit /b 1
echo.

echo [4/5] applying the patch now (about 20-40 seconds)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%DEST%\Inject.ps1" -Force
echo.

echo [5/5] result
if exist "%DEST%\state\last_pid.txt" echo   [OK] patch applied, booked pid:
if exist "%DEST%\state\last_pid.txt" type "%DEST%\state\last_pid.txt"
if not exist "%DEST%\state\last_pid.txt" echo   [WARN] no state file - is Myth.Cool running? see the log below.
echo.
echo   install : %DEST%
echo   log     : %DEST%\log\inject.log
echo   config  : %DEST%\tune.json   (edit + save = takes effect live, no restart)
echo.
echo   task    : MythCoolInject  (at logon + every 1 minute)
echo             remove with:  schtasks /Delete /TN MythCoolInject /F
echo.
echo Done. This window closes in 120 seconds.
timeout /t 120 >nul
exit /b
