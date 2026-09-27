# ============================================================
#  Myth.Cool Skin Hack - environment collector
#
#  Read-only. Produces one text file with everything needed to
#  diagnose a problem. Nothing is modified, nothing is injected.
#
#  Usage (no admin needed):
#      powershell -NoProfile -ExecutionPolicy Bypass -File Collect-Env.ps1
#
#  Output: env-report.txt in the current directory.
#  Paste that file when reporting an issue.
# ============================================================
$ErrorActionPreference = 'Continue'

$ROOT = $PSScriptRoot
$OUT  = Join-Path (Get-Location) 'env-report.txt'
$lines = New-Object System.Collections.ArrayList

function Add-Line($s) { [void]$lines.Add([string]$s) }
function Add-Section($title) { Add-Line ''; Add-Line ('===== ' + $title + ' =====') }

Add-Line ('Myth.Cool Skin Hack - environment report')
Add-Line ('generated : ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Add-Line ('install   : ' + $ROOT)

# ---------- OS ----------
Add-Section 'OS'
try {
    $os = Get-CimInstance Win32_OperatingSystem
    Add-Line ('  caption : ' + $os.Caption)
    Add-Line ('  version : ' + $os.Version + '  build ' + $os.BuildNumber)
    Add-Line ('  arch    : ' + $os.OSArchitecture)
} catch { Add-Line ('  ERR ' + $_.Exception.Message) }

Add-Section 'PowerShell'
Add-Line ('  version : ' + $PSVersionTable.PSVersion)

# ---------- privilege ----------
Add-Section 'Privilege'
try {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    Add-Line ('  user    : ' + $id.Name)
    Add-Line ('  admin   : ' + $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))
} catch { Add-Line ('  ERR ' + $_.Exception.Message) }

# ---------- MythCool processes ----------
Add-Section 'MythCool processes'
try {
    $raw = @(Get-CimInstance Win32_Process -Filter "Name='MythCool.exe'" -ErrorAction Stop)
    Add-Line ('  count   : ' + $raw.Count)
    $ids = @($raw | ForEach-Object { $_.ProcessId })
    foreach ($p in $raw) {
        $isChild = $ids -contains $p.ParentProcessId
        $cl = $p.CommandLine
        if (-not $cl) { $cl = '<null / access denied>' }
        Add-Line ('  pid=' + $p.ProcessId + ' ppid=' + $p.ParentProcessId + ' child=' + $isChild)
        Add-Line ('      created : ' + $p.CreationDate)
        Add-Line ('      cmd     : ' + $cl)
    }
    Add-Line '  (the MAIN process is the one with child=False)'
} catch { Add-Line ('  ERR ' + $_.Exception.Message) }

# ---------- install dir ----------
Add-Section 'Install directory'
foreach ($f in @('inject_main.py','Inject.ps1','InjectSilent.vbs','Register-Task.ps1','tune.json','venv\Scripts\python.exe','state\last_pid.txt')) {
    $p = Join-Path $ROOT $f
    if (Test-Path -LiteralPath $p) {
        $sz = (Get-Item -LiteralPath $p).Length
        $extra = ''
        if ($f -eq 'state\last_pid.txt') { $extra = '  content=[' + ((Get-Content -LiteralPath $p -Raw).Trim()) + ']' }
        Add-Line ('  OK      ' + $f + '  (' + $sz + ' B)' + $extra)
    } else {
        Add-Line ('  MISSING ' + $f)
    }
}

# ---------- frida ----------
Add-Section 'frida'
$venvPy = Join-Path $ROOT 'venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPy) {
    $v = (& $venvPy -c "import frida;print(frida.__version__)" 2>&1 | Out-String).Trim()
    Add-Line ('  version : ' + $v)
    try {
        $paths = (& $venvPy -c "import frida,sys;print(sys.executable);print(frida.__file__)" 2>&1 | Out-String).Trim()
        foreach ($l in ($paths -split "`r?`n")) { Add-Line ('  ' + $l) }
    } catch {}
} else {
    Add-Line '  no venv found - run Install.bat first'
}

# ---------- scheduled task ----------
Add-Section 'Scheduled task \MythCoolSkinHack'
try {
    $t = Get-ScheduledTask -TaskName 'MythCoolSkinHack' -ErrorAction Stop
    Add-Line ('  state    : ' + $t.State)
    Add-Line ('  user     : ' + $t.Principal.UserId + ' / ' + $t.Principal.LogonType + ' / ' + $t.Principal.RunLevel)
    foreach ($a in $t.Actions) {
        Add-Line ('  action   : ' + $a.Execute + ' ' + $a.Arguments)
    }
    $i = 0
    foreach ($tr in $t.Triggers) {
        $i++
        $rep = ''
        if ($tr.Repetition -and $tr.Repetition.Interval) {
            $rep = ' interval=' + $tr.Repetition.Interval + ' duration=' + $tr.Repetition.Duration
        }
        Add-Line ('  trigger' + $i + ' : ' + $tr.CimClass.CimClassName + $rep)
    }
    $info = Get-ScheduledTaskInfo -TaskName 'MythCoolSkinHack' -ErrorAction SilentlyContinue
    if ($info) {
        Add-Line ('  last run : ' + $info.LastRunTime + '   result=' + $info.LastTaskResult)
        Add-Line ('  next run : ' + $info.NextRunTime)
        Add-Line ('  missed   : ' + $info.NumberOfMissedRuns)
    }
} catch {
    Add-Line '  not registered'
}

# ---------- log tail ----------
Add-Section 'inject.log (last 40 lines)'
$log = Join-Path $ROOT 'log\inject.log'
if (Test-Path -LiteralPath $log) {
    try {
        Get-Content -LiteralPath $log -Tail 40 | ForEach-Object { Add-Line ('  ' + $_) }
    } catch { Add-Line ('  ERR ' + $_.Exception.Message) }
} else {
    Add-Line '  no log yet'
}

# ---------- write ----------
$lines | Out-File -FilePath $OUT -Encoding utf8
Write-Host ('report written to: ' + $OUT)
