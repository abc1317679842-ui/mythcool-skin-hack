<#
  MythCoolInject - beat ring format check (v18 and later).

  WHY A SEPARATE FILE

    The task "is last_beat.json a v18 array?" used to be a single
    powershell -Command one-liner inside Install_v<VER>.cmd. That line
    carried nested parentheses and a .StartsWith(...) call, which is a
    cmd.exe parsing hazard the moment it ever lands inside a
    parenthesised block. Keeping it out of the .cmd means the installer
    stays a dumb sequence of "run file, test errorlevel" steps.

  WHAT IT CHECKS

    v17 and earlier wrote a single JSON OBJECT (overwritten every cycle).
    v18 writes a JSON ARRAY (ring buffer, last 60 samples). So:

      * file exists
      * first non-space char is "["          -> array, not object
      * parses as valid JSON
      * reports how many rows the ring holds and prints the last sample

  USAGE
    powershell -NoProfile -ExecutionPolicy Bypass ^
      -File check_beat.ps1 -Path <last_beat.json>

  EXIT CODES
    0  v18+ array format confirmed
    1  missing / not an array / unparsable
#>
[CmdletBinding()]
param(
    [string]$Path = 'C:\ProgramData\MythCoolInject\log\last_beat.json'
)

if (-not (Test-Path -LiteralPath $Path)) {
    Write-Host "  [X] beat file missing: $Path"
    Write-Host '      the injector either did not run or died before the first sample'
    exit 1
}

$t = [IO.File]::ReadAllText($Path).TrimStart()

if (-not $t.StartsWith('[')) {
    Write-Host '  [X] last_beat.json is NOT the v18 array format'
    $head = $t
    if ($head.Length -gt 80) { $head = $head.Substring(0, 80) + '...' }
    Write-Host ('      head: ' + $head)
    Write-Host '      => the running build still writes the v17 object format'
    exit 1
}

$rows = $null
try { $rows = $t | ConvertFrom-Json } catch { $rows = $null }

if ($null -eq $rows) {
    Write-Host '  [X] array brackets present but the body is not valid JSON'
    exit 1
}

$n = @($rows).Count
Write-Host ('  [OK] beat ring v18 array format confirmed - rows: {0}' -f $n)

if ($n -gt 0) {
    $lastOne = @($rows)[$n - 1]
    try {
        Write-Host ('       last sample: ' + ($lastOne | ConvertTo-Json -Compress))
    } catch {
        Write-Host '       last sample: unprintable'
    }
    if ($n -gt 1) {
        Write-Host '       (rows x 60s = span covered; 60 rows = the full 1h window)'
    } else {
        Write-Host '       (only 1 row so far - a fresh inject always starts empty)'
    }
}

exit 0
