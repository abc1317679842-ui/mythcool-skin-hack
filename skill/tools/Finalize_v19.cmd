@echo off
setlocal
rem ============================================================
rem  MythCoolInject  v19  FINAL
rem  cleanup + deploy + reinject   --   one shot
rem ------------------------------------------------------------
rem  WHAT CHANGED IN v19
rem   the beat diagnostic was removed completely.
rem   v18 armed a setInterval that ran EVERY 60 SECONDS, read the
rem   page counters and wrote log\last_beat.json, forever.
rem   v19 never starts that timer and never writes that file.
rem   everything else - the display, refresh tick, tune hot-reload -
rem   is byte-for-byte the same as v18.
rem
rem  WHAT IT DOES
rem   1  admin self-check
rem   2  preflight: every input must exist, else abort clean
rem   3  verify the v19 source markers BEFORE touching disk
rem   4  stop the scheduled task, then clean up
rem   5  deploy the final build
rem   6  re-enable the task, re-inject, prove beat is gone
rem
rem  WHAT IT KEEPS ON PURPOSE
rem   inject_main.py.bak_v17.py   the one usable rollback point
rem   Inject.ps1  InjectSilent.vbs  Install.bat  Register-Task.ps1
rem   tune.json   your tuned parameters
rem   python      the bundled runtime
rem
rem  HARD RULES FOR THIS FILE
rem   * pure ASCII + CRLF only. Do not re-save it with an editor
rem     that adds a BOM or converts to LF.
rem   * no parenthesised if-blocks anywhere. cmd counts parens to
rem     find where a block ends, so one stray paren shifts every
rem     later command. All branches below use goto.
rem   * do not verify markers with findstr: it reads through the
rem     console code page and garbles UTF-8 files with CJK text.
rem     verify_markers.ps1 exists for exactly that reason.
rem ============================================================

echo ============================================================
echo   MythCoolInject   v19   FINAL
echo   cleanup + deploy + reinject
echo   per-minute beat logging: REMOVED
echo ============================================================
echo.

rem ------------------------- CONFIG -------------------------
set PD=C:\ProgramData\MythCoolInject
set SRC=C:\ProgramData\MythCoolInject\skill\tools\inject_main_v19_final.py
set VER=19
set VFY=C:\ProgramData\MythCoolInject\skill\tools\verify_markers.ps1
set DST=%PD%\inject_main.py
set BAK=%PD%\inject_main.py.bak_v17.py
set INJ=%PD%\Inject.ps1
set BEAT=%PD%\log\last_beat.json
set SHL=powershell.exe
rem ----------------------------------------------------------

rem -------------------- 1/6  admin --------------------------
net session >nul 2>&1
if errorlevel 1 goto NOADMIN
echo [1/6] admin check ............ OK
goto S2

:NOADMIN
echo [1/6] admin check ............ FAILED
echo.
echo   This script needs an ADMIN terminal. Nothing was changed.
echo.
echo   How to run it:
echo     Start menu -^> type  Terminal  -^> right-click
echo     Windows Terminal  -^>  Run as administrator
echo     then paste the command again.
echo.
pause
exit /b 1

rem -------------------- 2/6  preflight ----------------------
:S2
if not exist "%SRC%" goto PREF
if not exist "%VFY%" goto PREF
goto S3

:PREF
echo [2/6] preflight .............. FAILED
echo.
echo   Missing input - nothing on disk was changed:
if not exist "%SRC%" echo     final source : %SRC%
if not exist "%VFY%" echo     verifier     : %VFY%
echo.
pause
exit /b 1

rem -------------------- 3/6  verify -------------------------
:S3
echo [2/6] preflight .............. OK
echo.
echo [3/6] verify v%VER% source BEFORE touching disk ...
%SHL% -NoProfile -ExecutionPolicy Bypass -File "%VFY%" -Path "%SRC%" -Ver %VER% -Neg
if errorlevel 1 goto MARKF
echo        [OK] markers verified, beat confirmed absent
goto S4

:MARKF
echo.
echo [3/6] verify v%VER% source ...... FAILED
echo.
echo   Marker check failed. NOTHING on disk was changed and the
echo   running Myth.Cool is still on its previous build.
echo.
pause
exit /b 1

rem -------------------- 4/6  stop + cleanup ----------------
:S4
echo.
echo [4/6] stop scheduled task + cleanup ...
schtasks /Change /TN "MythCoolInject" /DISABLE >nul 2>&1
echo        task disabled if it existed
echo        runtime logs, including last_beat.json
del /F /Q "%PD%\log\*.*" >nul 2>&1
echo        scratch files
del /F /Q "%PD%\_chk1.txt" >nul 2>&1
del /F /Q "%PD%\_chk2.txt" >nul 2>&1
del /F /Q "%PD%\_chk3.txt" >nul 2>&1
del /F /Q "%PD%\_chk4.txt" >nul 2>&1
del /F /Q "%PD%\_chk5.txt" >nul 2>&1
del /F /Q "%PD%\_wtest.tmp" >nul 2>&1
del /F /Q "%PD%\_probe_nonelev.py" >nul 2>&1
rmdir /S /Q "%PD%\__pycache__" >nul 2>&1
echo        old build backups, v17 rollback point is kept
del /F /Q "%PD%\inject_main.py.bak_v13_20260929_120258" >nul 2>&1
del /F /Q "%PD%\inject_main.py.bak_v14_20260929_121640" >nul 2>&1
del /F /Q "%PD%\inject_main.py.bak_v151.py" >nul 2>&1
del /F /Q "%PD%\inject_main.py.bak_v15old.py" >nul 2>&1
del /F /Q "%PD%\inject_main.py.bak_v16.py" >nul 2>&1
del /F /Q "%PD%\inject_main.py.bak_v16_before_v17.py" >nul 2>&1
del /F /Q "%PD%\inject_main.py.bak_v16_pre_v17.py" >nul 2>&1
del /F /Q "%PD%\tune.json.bak_20260929_120258" >nul 2>&1
echo        stale state
del /F /Q "%PD%\state\last_pid.txt" >nul 2>&1
echo        cleanup done
goto S5

rem -------------------- 5/6  deploy -------------------------
:S5
echo.
echo [5/6] deploy final build ........
if exist "%BAK%" goto BAKOK
echo        [WARN] rollback point missing, creating one first
copy /Y "%DST%" "%BAK%" >nul
if errorlevel 1 goto BAKF
goto DPL
:BAKF
echo        [X] could not create a rollback point - aborting.
pause
exit /b 1
:BAKOK
echo        rollback point kept: inject_main.py.bak_v17.py
:DPL
copy /Y "%SRC%" "%DST%" >nul
if errorlevel 1 goto CPF
echo        [OK] deployed  inject_main.py
goto S6
:CPF
echo        [X] copy failed - restoring the previous build
copy /Y "%BAK%" "%DST%" >nul
pause
exit /b 1

rem -------------------- 6/6  reinject -----------------------
:S6
echo.
echo [6/6] restore task + re-inject ...
schtasks /Query /TN "MythCoolInject" >nul 2>&1
if errorlevel 1 goto NOTASK
schtasks /Change /TN "MythCoolInject" /ENABLE >nul 2>&1
echo        scheduled task re-enabled
goto DOINJ
:NOTASK
echo        [WARN] task MythCoolInject not found - auto-inject
echo               at logon will not happen. To register it, run
echo               Register-Task.ps1 as administrator.
:DOINJ
echo        forcing re-inject now ...
%SHL% -NoProfile -ExecutionPolicy Bypass -File "%INJ%" -Force
echo        Inject.ps1 exit code = %ERRORLEVEL%
echo.
echo        waiting 15s for the runtime dump ...
ping -n 16 127.0.0.1 >nul
echo.
echo        proof: last_beat.json must NOT exist ...
if exist "%BEAT%" goto BEATSTILL
echo        [OK] no last_beat.json - per-minute logging is gone
goto DONE
:BEATSTILL
echo        [X] last_beat.json EXISTS - the beat was NOT removed.
echo            Something re-created it. Do not ignore this.

:DONE
echo.
echo ============================================================
echo   FINISHED
echo ------------------------------------------------------------
echo   Deployed : v%VER%   beat logging removed
echo   File     : %DST%
echo   Rollback : %BAK%
echo   Log      : %PD%\log\inject.log
echo ------------------------------------------------------------
echo   log\inject.log is written ONCE per injection, not per minute.
echo   last_beat.json will never come back on this build.
echo ------------------------------------------------------------
echo   Want the ORIGINAL skin back, no injection at all?
echo     1. disable the task:
echo          schtasks /Change /TN "MythCoolInject" /DISABLE
echo     2. restart Myth.Cool
echo   The injected CSS and DOM live only inside the running
echo   page, so a restart wipes them completely.
echo ============================================================
endlocal
pause
