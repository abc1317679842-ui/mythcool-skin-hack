# ============================================================
#  Myth.Cool Skin Hack - runtime setup
#
#  Copies the tool files into a stable location and prepares a
#  private Python environment with frida in it.
#
#  Called by Install.bat. Needs no admin rights itself, but it is
#  run elevated there anyway (the scheduled task registration does).
#
#  Layout produced:
#    <Dest>\inject_main.py, Inject.ps1, InjectSilent.vbs, ...
#    <Dest>\venv\           private Python env containing frida
#    <Dest>\log\  state\    runtime artefacts
#
#  ASCII only on purpose: PowerShell 5.1 reads .ps1 as ANSI unless the
#  file carries a UTF-8 BOM, so non-ASCII here would come out garbled.
# ============================================================
param(
    [string]$Dest = (Join-Path $env:ProgramData 'MythCoolInject')
)

$ErrorActionPreference = 'Stop'
$SRC = $PSScriptRoot

Write-Host ('  source : ' + $SRC)
Write-Host ('  target : ' + $Dest)

# ---------- 1) directories ----------
foreach ($d in @($Dest, (Join-Path $Dest 'log'), (Join-Path $Dest 'state'))) {
    if (-not (Test-Path -LiteralPath $d)) {
        New-Item -ItemType Directory -Force -Path $d | Out-Null
    }
}

# ---------- 2) copy tool files ----------
$files = @('inject_main.py', 'Inject.ps1', 'InjectSilent.vbs', 'Register-Task.ps1',
           'tune.json', 'Collect-Env.ps1')
foreach ($f in $files) {
    $s = Join-Path $SRC $f
    if (Test-Path -LiteralPath $s) {
        Copy-Item -LiteralPath $s -Destination (Join-Path $Dest $f) -Force
        Write-Host ('  copied : ' + $f)
    } else {
        Write-Host ('  MISSING: ' + $f)
    }
}

# ---------- 3) python + venv + frida ----------
$venvDir = Join-Path $Dest 'venv'
$venvPy  = Join-Path $venvDir 'Scripts\python.exe'

$needVenv = $true
if (Test-Path -LiteralPath $venvPy) {
    & $venvPy -c "import frida" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $needVenv = $false
        Write-Host '  venv   : already present and working'
    }
}

if ($needVenv) {
    $base = $null
    $baseArgs = @()

    $g = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($g) { $base = $g.Source; $baseArgs = @() }
    if (-not $base) {
        $g2 = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($g2) { $base = $g2.Source; $baseArgs = @('-3') }
    }

    if (-not $base) {
        Write-Host ''
        Write-Host '  [ERROR] No Python found in PATH.'
        Write-Host '          Install Python 3.9+ from https://www.python.org/downloads/'
        Write-Host '          (tick "Add python.exe to PATH" during setup), then re-run Install.bat.'
        Write-Host ''
        exit 1
    }
    Write-Host ('  python : ' + $base)

    if (-not (Test-Path -LiteralPath $venvPy)) {
        Write-Host '  creating private venv ...'
        & $base @($baseArgs + @('-m', 'venv', $venvDir))
        if ($LASTEXITCODE -ne 0) { Write-Host '  [ERROR] venv creation failed'; exit 1 }
    }

    Write-Host '  installing frida (downloads ~20 MB, please wait) ...'
    & $venvPy -m pip install --disable-pip-version-check --quiet --upgrade pip
    & $venvPy -m pip install --disable-pip-version-check --quiet frida
    if ($LASTEXITCODE -ne 0) {
        Write-Host '  [ERROR] "pip install frida" failed - check your network / proxy.'
        exit 1
    }
}

# ---------- 4) verify ----------
$ver = (& $venvPy -c "import frida;print(frida.__version__)" 2>&1 | Out-String).Trim()
Write-Host ('  frida  : ' + $ver)
if ($LASTEXITCODE -ne 0) { Write-Host '  [ERROR] frida is not importable'; exit 1 }

exit 0
