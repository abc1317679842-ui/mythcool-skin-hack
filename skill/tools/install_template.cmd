@echo off
rem ============================================================
rem  MythCoolInject  install template   (v18 schema)
rem  --------------------------------
rem  BEFORE USE, edit the CONFIG block below:
rem    SRC  = the inject_main source file (absolute path)
rem    VER  = expected version number (grep "RES.ver = " in SRC)
rem    TAG  = backup suffix, e.g. v17 -> inject_main.py.bak_v17.py
rem    VFY  = verify_markers.ps1  (UTF-8 safe marker checker)
rem    CHK  = check_beat.ps1      (beat ring format checker)
rem
rem  Hard rules (learned the hard way, 2026-09-29):
rem    * keep this file PURE ASCII + CRLF -- cmd garbles non-ASCII
rem    * NO parenthesised if-blocks anywhere in this file. cmd counts
rem      parens to find where a block ends, so a single stray paren
rem      inside one terminates the block early and shifts every later
rem      command. A marker-check echo that mentioned a CSS transform
rem      was exactly that trap, and it aborted a perfectly good
rem      install. => every failure branch below uses "goto".
rem    * do NOT verify markers with findstr. findstr reads files
rem      through the console code page and misbehaves on UTF-8 files
rem      that contain CJK text. Use verify_markers.ps1 instead.
rem    * do NOT put PowerShell logic in a -Command one-liner here.
rem      A long command line with nested parens is a parsing hazard.
rem      Put the logic in a .ps1 and call it with -File.
rem    * NOTHING on disk is modified until the source has been
rem      verified. A failed check must leave the previous build
rem      untouched and the app still running it.
rem    * NEVER overwrite an existing rollback point. If the backup
rem      file already exists, keep it. Re-running the installer must
rem      not turn a genuine older build into a copy of the new one.
rem ============================================================
setlocal

rem ------------------- CONFIG -------------------
set SRC=C:\ProgramData\MythCoolInject\workspace\inject_main_v16_src.py
set VER=18
set TAG=v17
set VFY=C:\ProgramData\MythCoolInject\skill\tools\verify_markers.ps1
set CHK=C:\ProgramData\MythCoolInject\skill\tools\check_beat.ps1
rem ----------------------------------------------

set DST=C:\ProgramData\MythCoolInject\inject_main.py
set BAK=C:\ProgramData\MythCoolInject\inject_main.py.bak_%TAG%.py
set INJ=C:\ProgramData\MythCoolInject\Inject.ps1
set BEAT=C:\ProgramData\MythCoolInject\log\last_beat.json
set SHL=powershell.exe

echo ============================================================
echo   MythCoolInject  install  - expected version: v%VER%
echo ============================================================

rem  ---- preflight: touch nothing until every input exists ----
if not exist "%SRC%" goto PREFAIL
if not exist "%VFY%" goto PREFAIL
if not exist "%CHK%" goto PREFAIL
goto PREOK

:PREFAIL
echo.
echo   [X] PREFLIGHT FAILED - nothing was changed.
if not exist "%SRC%" echo       source missing       : %SRC%
if not exist "%VFY%" echo       verifier missing     : %VFY%
if not exist "%CHK%" echo       beat checker missing : %CHK%
pause
exit /b 1

:PREOK

echo.
echo [1/6] Verify SOURCE markers BEFORE touching anything ...
%SHL% -NoProfile -ExecutionPolicy Bypass -File "%VFY%" -Path "%SRC%" -Ver %VER% -Neg
if errorlevel 1 goto MARKFAIL
echo   [OK] source verified - safe to install
goto MARKOK

:MARKFAIL
echo.
echo   [X] SOURCE MARKER CHECK FAILED - nothing was changed on disk.
echo       The failing marker is listed above.
echo       The running Myth.Cool is still on the previous build.
pause
exit /b 1

:MARKOK

echo.
echo [2/6] Prepare rollback point ...
if exist "%BAK%" goto BAKKEEP
copy /Y "%DST%" "%BAK%" >nul
if errorlevel 1 goto BAKFAIL
echo   OK  -^> %BAK%
echo       snapshot of the build being replaced
goto BAKOK

:BAKKEEP
echo   [KEEP] rollback point already exists, NOT overwriting it:
echo          %BAK%
%SHL% -NoProfile -ExecutionPolicy Bypass -File "%VFY%" -Path "%BAK%" -Ver %VER% >nul 2>&1
if errorlevel 1 goto BAKOLD
echo   [WARN] that file already carries v%VER% markers, so it is NOT a usable
echo          rollback point. Delete it and re-run for a fresh snapshot.
goto BAKOK

:BAKOLD
echo   [OK]   it is a genuine older build - rollback point is usable
goto BAKOK

:BAKFAIL
echo   [X] BACKUP FAILED - aborting before overwrite.
pause
exit /b 1

:BAKOK

echo.
echo [3/6] Copy new source ...
copy /Y "%SRC%" "%DST%" >nul
if errorlevel 1 goto COPYFAIL
goto COPYOK

:COPYFAIL
echo   [X] COPY FAILED - restoring previous build from backup.
copy /Y "%BAK%" "%DST%" >nul
pause
exit /b 1

:COPYOK

echo.
echo [4/6] Force re-inject into running Myth.Cool ...
%SHL% -NoProfile -ExecutionPolicy Bypass -File "%INJ%" -Force
echo   exit code = %ERRORLEVEL%

echo.
echo [4b/6] Clean up stale beat log files ...
if exist "C:\ProgramData\MythCoolInject\log\_v5.txt" del /F /Q "C:\ProgramData\MythCoolInject\log\_v5.txt" >nul 2>&1
if exist "C:\ProgramData\MythCoolInject\log\_v6.txt" del /F /Q "C:\ProgramData\MythCoolInject\log\_v6.txt" >nul 2>&1
echo   OK

echo.
echo [5/6] Waiting 15s for runtime dump ...
ping -n 16 127.0.0.1 >nul

echo.
echo [6/6] Verify beat ring format ...
%SHL% -NoProfile -ExecutionPolicy Bypass -File "%CHK%" -Path "%BEAT%"
if errorlevel 1 goto BEATFAIL
goto BEATOK

:BEATFAIL
echo   [WARN] beat file not in v18 array format yet.
echo          This does NOT affect the display - beat is diagnostics only.

:BEATOK

echo.
echo ============================================================
echo   Done.
echo   Log     : C:\ProgramData\MythCoolInject\log\inject.log
echo   Runtime : C:\ProgramData\MythCoolInject\log\last_result.json
echo   Beat    : C:\ProgramData\MythCoolInject\log\last_beat.json
echo.
echo   Rollback if needed:
echo     copy /Y "%BAK%" "%DST%"
echo     powershell -NoProfile -ExecutionPolicy Bypass -File "%INJ%" -Force
echo ============================================================
endlocal
