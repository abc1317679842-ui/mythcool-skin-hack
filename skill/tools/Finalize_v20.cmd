@echo off
setlocal
rem ============================================================
rem  MythCoolInject  v20  FINAL
rem  cleanup + deploy + reinject   --   one shot
rem ------------------------------------------------------------
rem  WHAT CHANGED IN v20
rem   A1  missing V8 symbols are now reported EXPLICITLY:
rem       log line "SYM MISS", last_result.json symMiss=true,
rem       exit code 3. no more silent failure after the vendor
rem       ships a new Electron/V8.
rem   A2  tune logs show BOTH the file value and the effective
rem       value of refresh_ms (the fuse clamps <3500 to 3500).
rem   A3  dead "tick" parameter removed (never worked).
rem   B1  layer host no longer falls back silently to a
rem       non-rotated container - it refuses and warns instead.
rem   B2  pushTune checks window liveness, re-finds if destroyed.
rem
rem  WHAT IT DOES
rem   1  admin self-check
rem   2  preflight: every input must exist, else abort clean
rem   3  verify the v20 source markers BEFORE touching disk
rem   4  stop the scheduled task, then clean up
rem   5  snapshot the running v19 as rollback, deploy v20
rem   6  re-enable the task, re-inject, prove no SYM MISS
rem      and no beat file
rem
rem  WHAT IT KEEPS ON PURPOSE
rem   inject_main.py.bak_v17.py   deep rollback point
rem   inject_main.py.bak_v19.py   previous build (created here)
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
echo   MythCoolInject   v20   FINAL
echo   cleanup + deploy + reinject
echo   A1 sym-miss guard / A2 dual tune logs / B1 B2 hardening
echo ============================================================
echo.

rem ------------------------- CONFIG -------------------------
set PD=C:\ProgramData\MythCoolInject
set SRC=C:\ProgramData\MythCoolInject\skill\tools\inject_main_v22_final.py
set SRC19=C:\ProgramData\MythCoolInject\skill\tools\inject_main_v19_final.py
set VER=20
set VFY=C:\ProgramData\MythCoolInject\skill\tools\verify_markers.ps1
set LG=C:\ProgramData\MythCoolInject\skill\tools\logscan.ps1
set DST=%PD%\inject_main.py
set BAK=%PD%\inject_main.py.bak_v19.py
set SHL=powershell.exe
set INJ=C:\ProgramData\MythCoolInject\Inject.ps1
set BEAT=%PD%\log\last_beat.json
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
if not exist "%SRC%" echo     v20 source    : %SRC%
if not exist "%SRC19%" echo     v19 archive   : %SRC19%
if not exist "%VFY%" echo     verifier      : %VFY%
if not exist "%LG%" echo     log scanner   : %LG%
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
echo [5/6] snapshot rollback + deploy v20 ........
if exist "%BAK%" goto BAKOK
echo        creating rollback point from the v19 archive ...
copy /Y "%SRC19%" "%BAK%" >nul
if errorlevel 1 goto BAKF
goto DPL
:BAKF
echo        [X] could not create a rollback point - aborting.
pause
exit /b 1
:BAKOK
echo        rollback point kept: inject_main.py.bak_v19.py
:DPL
copy /Y "%SRC%" "%DST%" >nul
if errorlevel 1 goto CPF
echo        [OK] deployed  inject_main.py  v%VER%
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
echo        proof 1: no SYM MISS in the log ...
%SHL% -NoProfile -ExecutionPolicy Bypass -File "%LG%" -Path "%PD%\log\inject.log" -Need "SYM MISS"
if errorlevel 3 goto LOGMISS
if errorlevel 1 goto SYMFAIL
echo        [OK] no SYM MISS - all V8 symbols resolved
echo        proof 2: last_beat.json must NOT exist ...
if exist "%BEAT%" goto BEATSTILL
echo        [OK] no last_beat.json - per-minute logging is gone
goto DONE
:LOGMISS
echo        [WARN] inject.log not found - injection may not have
echo               run at all. Check the Inject.ps1 exit code above.
goto BEATCHK
:SYMFAIL
echo        [X] SYM MISS found in the log - the vendor app likely
echo            shipped a new Electron/V8. v20 refused to run rather
echo            than fail silently. See README "version-upgrade
echo            self-check". Deployment itself SUCCEEDED, but the
echo            symbols must be re-dumped before injection works.
echo            last_result.json has symMiss=true for the record.
goto DONE
:BEATCHK
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
echo   Deployed : v%VER%   sym-miss guard + log hardening
echo   File     : %DST%
echo   Rollback : %BAK%   - plus .bak_v17.py as deep rollback
echo   Log      : %PD%\log\inject.log
echo ------------------------------------------------------------
echo   If anything looks wrong, check inject.log for either
echo   "SYM MISS" - symbol problem, or the "OK" success line.
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
