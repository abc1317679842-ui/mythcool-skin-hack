# ============================================================
#  Myth.Cool Skin Hack - idempotent entry point
#
#  Called by the scheduled task \MythCoolInject (every minute).
#  (Legacy installs registered it as \MythCoolSkinHack - same payload.)
#
#  Logic:
#    find the MythCool MAIN process
#      not running       -> mark state NONE, exit (silent if already NONE)
#      pid == state      -> exit immediately (already patched, ~1 s)
#      pid != state      -> run inject_main.py
#                             rc 0 -> book the pid (done)
#                             rc 2 -> not visible, retry next round
#                             rc 3 -> V8 symbols missing (version skew):
#                                     record SYMFAIL:<pid>, stop retrying.
#                                     Retries automatically ONLY when Myth.Cool
#                                     restarts (new pid = new chance).
#                             else -> FAILED, do NOT book, retry next round
#
#  State is only written on success: if a patch attempt fails (e.g. the
#  skin page is not ready yet) the next round retries automatically. A
#  failed attempt must never look like "done".
#
#  ASCII only on purpose (PowerShell 5.1 reads .ps1 as ANSI without BOM).
# ============================================================
param([switch]$Force, [switch]$Probe)

$ROOT   = $PSScriptRoot
$MAIN   = Join-Path $ROOT 'inject_main.py'
# v22: DO NOT hard-code the private python path.
#   Setup-Runtime.ps1 creates <ROOT>\venv\Scripts\python.exe when it can build a
#   venv, but on machines without a base python on PATH it falls back to an
#   embedded runtime at <ROOT>\python\python.exe. Either one alone breaks the
#   other machine -- resolve at runtime, and fail loudly (with the tried list)
#   if none of them exists. Found for real on 2026-09-30: a hard-coded 'venv'
#   path turned into "FATAL missing python" and killed injection completely.
$PY = ''
$PYCAND = @((Join-Path $ROOT 'venv\Scripts\python.exe'),
            (Join-Path $ROOT 'python\python.exe'),
            (Join-Path $ROOT 'python\Scripts\python.exe'))
foreach ($c in $PYCAND) { if (Test-Path -LiteralPath $c) { $PY = $c; break } }
if (-not $PY) {
    $sys = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($sys) { $PY = $sys.Source }
}
$LOGD   = Join-Path $ROOT 'log'
$STATED = Join-Path $ROOT 'state'
$STATE  = Join-Path $STATED 'last_pid.txt'
$HASHF  = Join-Path $STATED 'last_hash.txt'
$LOG    = Join-Path $LOGD 'inject.log'

foreach ($d in @($LOGD, $STATED)) {
    if (-not (Test-Path -LiteralPath $d)) {
        try { New-Item -ItemType Directory -Force -Path $d | Out-Null } catch {}
    }
}

# keep the log from growing without bound
try {
    if (Test-Path -LiteralPath $LOG) {
        if ((Get-Item -LiteralPath $LOG).Length -gt 524288) {
            Move-Item -LiteralPath $LOG -Destination ($LOG + '.old') -Force
        }
    }
} catch {}

function Log([string]$m) {
    $line = ('[{0}][PS] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m)
    try { Add-Content -LiteralPath $LOG -Value $line -Encoding UTF8 } catch {}
}

function ReadState() {
    if (Test-Path -LiteralPath $STATE) {
        try {
            $v = (Get-Content -LiteralPath $STATE -Raw -ErrorAction Stop).Trim()
            if ($v) { return $v }
        } catch {}
    }
    return 'NONE'
}

function ReadHash() {
    if (Test-Path -LiteralPath $HASHF) {
        try {
            $v = (Get-Content -LiteralPath $HASHF -Raw -ErrorAction Stop).Trim()
            if ($v) { return $v }
        } catch {}
    }
    return ''
}

function WriteHash([string]$v) {
    try { Set-Content -LiteralPath $HASHF -Value $v -Encoding ASCII -NoNewline -ErrorAction Stop } catch {}
}

function WriteState([string]$v) {
    try {
        Set-Content -LiteralPath $STATE -Value $v -Encoding ASCII -NoNewline -ErrorAction Stop
    } catch {
        Log ('WARN cannot write state file: ' + $_.Exception.Message)
    }
}

#  v21: the fast path must NOT key on pid alone. If inject_main.py is updated
#  while Myth.Cool keeps the same pid, "pid == state" silently skips forever and
#  the new code never reaches the page (hit for real on 2026-09-30: v21 deployed
#  at 04:50, scheduled task kept exiting at the fast path, page stayed on v20).
#  => also compare a hash of inject_main.py. Do NOT use mtime: Copy-Item can
#     carry the source's timestamp over, making the test a lie.
#
# ---------- 0) sanity ----------
if (-not $PY) {
    Log ('FATAL missing python. tried: ' + ($PYCAND -join ' , ') + ' and PATH python.exe -> run Install.bat first')
    exit 3
}
if (-not (Test-Path -LiteralPath $MAIN)) {
    Log ('FATAL missing injector: ' + $MAIN)
    exit 3
}

$last = ReadState

# ---------- 1) find the MythCool MAIN process ----------
# MythCool spawns several MythCool.exe helpers (--type=gpu-process,
# --type=renderer, ...) and ALL of them share the parent's start time, so
# sorting by StartTime cannot tell them apart. CommandLine would work but is
# unreadable without elevated rights ("access denied").
# => use the parent/child relation: the main process is the only one whose
#    parent is NOT itself a MythCool.exe.
$mainPid  = 0
$rawCount = 0

try {
    $raw = @(Get-CimInstance Win32_Process -Filter "Name='MythCool.exe'" -ErrorAction Stop)
    $rawCount = $raw.Count
    if ($rawCount -gt 0) {
        $ids  = @($raw | ForEach-Object { $_.ProcessId })
        $cand = @($raw | Where-Object { $ids -notcontains $_.ParentProcessId })
        if ($cand.Count -eq 0) { $cand = $raw }
        $mainPid = [int](($cand | Sort-Object CreationDate | Select-Object -First 1).ProcessId)
    }
} catch {
    Log ('WARN WMI query failed: ' + $_.Exception.Message)
}

if ($mainPid -le 0) {
    try {
        $gp = @(Get-Process -Name 'MythCool' -ErrorAction Stop)
        if ($gp.Count -gt 0) {
            $mainPid  = [int](($gp | Sort-Object StartTime | Select-Object -First 1).Id)
            $rawCount = $gp.Count
        }
    } catch {}
}

if ($mainPid -le 0) {
    if ($last -ne 'NONE') {
        Log 'MythCool not running -> state NONE'
        WriteState 'NONE'
    }
    exit 0
}

$cur = [string]$mainPid

# ---------- 1b) probe mode (read-only) ----------
if ($Probe) {
    Write-Host ('probe: mainPid=' + $cur + ' mythCoolProcs=' + $rawCount + ' lastState=' + $last + ' action=' + $(if ($cur -eq $last) { 'skip (already patched)' } else { 'inject' }))
    exit 0
}

# ---------- 2) idempotent fast path ----------
# SYMFAIL:<pid> = last attempt hit missing V8 symbols (version skew). Retry is
# pointless for the SAME pid; a new pid (Myth.Cool restarted) gets one fresh
# attempt automatically. -Force overrides.
# v21: hash of the injector itself -- catches "code updated, pid unchanged".
$hash = ''
try { $hash = (Get-FileHash -LiteralPath $MAIN -Algorithm SHA256 -ErrorAction Stop).Hash } catch { $hash = '' }
$lastHash = ReadHash
$codeChanged = ($hash -ne '') -and ($hash -ne $lastHash)

if ((-not $Force) -and ($last -like 'SYMFAIL:*') -and ($cur -eq ($last -replace '^SYMFAIL:', '')) -and (-not $codeChanged)) { exit 0 }
if ((-not $Force) -and ($cur -eq $last) -and (-not $codeChanged)) { exit 0 }

$started = ''
try { $started = (Get-Process -Id $mainPid -ErrorAction Stop).StartTime.ToString('yyyy-MM-dd HH:mm:ss') } catch {}

if ($last -eq 'NONE') {
    Log ('MythCool started main-pid=' + $cur + ' started=' + $started + ' procs=' + $rawCount + ' -> injecting')
} elseif ($last -like 'SYMFAIL:*') {
    Log ('MythCool restarted after symbol failure (' + $last + ' -> pid=' + $cur + ' started=' + $started + ' procs=' + $rawCount + ') -> one fresh attempt')
} elseif ($last -eq $cur) {
    if ($codeChanged) { Log ('injector code changed (hash ' + $lastHash + ' -> ' + $hash + ') -> re-injecting same pid=' + $cur) }
    else { Log ('same instance pid=' + $cur + ' but -Force given -> re-injecting') }
} else {
    Log ('MythCool restarted ' + $last + ' -> ' + $cur + ' started=' + $started + ' procs=' + $rawCount + ' -> injecting')
}

# ---------- 3) run the injector ----------
# Output goes through a pipe, not a file redirection: a failed redirection
# would abort the whole run, and the injector keeps its own log anyway.
$env:PYTHONIOENCODING = 'utf-8'

$t0 = Get-Date
$rc = 99
try {
    & $PY $MAIN $cur 2>&1 | Out-Null
    $rc = $LASTEXITCODE
    if ($null -eq $rc) { $rc = 0 }
} catch {
    Log ('injector threw: ' + $_.Exception.Message)
    $rc = 99
}
$sec = [int]((Get-Date) - $t0).TotalSeconds

# ---------- 4) record only on success ----------
if ($rc -eq 0) {
    WriteState $cur
    if ($hash -ne '') { WriteHash $hash }
    Log ('inject OK pid=' + $cur + ' in ' + $sec + 's -> booked')
    exit 0
} elseif ($rc -eq 2) {
    Log ('inject skipped: MythCool not visible to frida (rc=2) in ' + $sec + 's -> retry next round')
    exit 0
} elseif ($rc -eq 3) {
    Log ('inject ABORTED rc=3: V8 symbols missing (version skew) -> stopping retries. Run the symbol probe (see SKILL.md version-upgrade self-check). Will retry automatically only after Myth.Cool restarts.')
    WriteState ('SYMFAIL:' + $cur)
    exit 3
} else {
    Log ('inject FAILED rc=' + $rc + ' in ' + $sec + 's -> not booked, retry next round')
    exit 1
}
