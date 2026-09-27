# ============================================================
#  Myth.Cool Skin Hack - register the scheduled task
#  REQUIRES ADMIN. Install.bat calls this elevated for you.
#
#  Triggers
#    1) At logon                -> covers boot / sign-in
#    2) Every 1 minute, forever -> covers wake-from-sleep, manual
#                                  restarts and crashes: the task just
#                                  re-injects as soon as the pid changes
#
#  Action     wscript.exe //B //NoLogo "<dir>\InjectSilent.vbs"
#             (a VBS launcher, NOT powershell.exe directly: a task action
#              of "powershell.exe -WindowStyle Hidden" still flashes a
#              console window, because Windows allocates the console
#              before PowerShell can hide it)
#  Principal  current user / Interactive / HighestAvailable
#             MUST have the same privilege level as Myth.Cool itself,
#             otherwise frida cannot attach to its main process.
#  Settings   IgnoreNew (never overlap), StartWhenAvailable (catch up
#             after sleep/hibernate), 5 minute execution limit.
#
#  Safe to re-run: any previous registration is removed first.
#  ASCII only (PowerShell 5.1 reads .ps1 as ANSI without a BOM).
# ============================================================
$ErrorActionPreference = 'Stop'

$TASK     = 'MythCoolSkinHack'
$ROOT     = $PSScriptRoot
$ENTRY    = Join-Path $ROOT 'Inject.ps1'
$LAUNCHER = Join-Path $ROOT 'InjectSilent.vbs'

if (-not (Test-Path -LiteralPath $ENTRY))    { Write-Host ('MISSING: ' + $ENTRY);    exit 1 }
if (-not (Test-Path -LiteralPath $LAUNCHER)) { Write-Host ('MISSING: ' + $LAUNCHER); exit 1 }

# ---------- remove any previous registration ----------
try {
    $null = Get-ScheduledTask -TaskName $TASK -ErrorAction Stop
    Unregister-ScheduledTask -TaskName $TASK -Confirm:$false -ErrorAction Stop
    Write-Host 'removed previous task registration'
} catch {
    Write-Host 'no previous task (first install)'
}

# ---------- action ----------
$vbsExe = Join-Path $env:SystemRoot 'System32\wscript.exe'
if (-not (Test-Path -LiteralPath $vbsExe)) { $vbsExe = 'wscript.exe' }
$psExe  = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

$argLine = '//B //NoLogo "{0}"' -f $LAUNCHER
$action  = New-ScheduledTaskAction -Execute $vbsExe -Argument $argLine

# ---------- triggers ----------
$tLogon = New-ScheduledTaskTrigger -AtLogOn
$tEvery = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) `
            -RepetitionInterval (New-TimeSpan -Minutes 1)

# ---------- settings ----------
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

# ---------- principal (same level as Myth.Cool so frida can attach) ----------
$sid = ([Security.Principal.WindowsIdentity]::GetCurrent()).User.Value
$principal = New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Highest

# ---------- register ----------
Register-ScheduledTask -TaskName $TASK `
    -Action $action `
    -Trigger @($tLogon, $tEvery) `
    -Settings $settings `
    -Principal $principal `
    -Description 'Re-applies the Myth.Cool skin patch whenever MythCool.exe (re)starts.' `
    -Force | Out-Null

Write-Host ('registered: ' + $TASK)
Write-Host ('  action   : ' + $vbsExe)
Write-Host ('  argument : ' + $argLine)
Write-Host ('  payload  : ' + $psExe + '  (started hidden by the launcher)')
Write-Host ('  injector : ' + $ENTRY)
Write-Host ('  user     : ' + $sid + '  (Interactive, HighestAvailable)')

# ---------- readback ----------
try {
    $t = Get-ScheduledTask -TaskName $TASK
    Write-Host ('  state    : ' + $t.State)
    $i = 0
    foreach ($tr in $t.Triggers) {
        $i++
        $rep = ''
        if ($tr.Repetition -and $tr.Repetition.Interval) {
            $rep = ' interval=' + $tr.Repetition.Interval + ' duration=' + $tr.Repetition.Duration
        }
        Write-Host ('  trigger' + $i + ' : ' + $tr.CimClass.CimClassName + $rep)
    }
    Write-Host ('  multiple : ' + $t.Settings.MultipleInstances + ' | startWhenAvailable=' + $t.Settings.StartWhenAvailable)
} catch {
    Write-Host ('readback failed: ' + $_.Exception.Message)
}
