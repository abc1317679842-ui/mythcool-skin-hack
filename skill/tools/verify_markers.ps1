<#
  MythCoolInject - source marker verification (UTF-8 safe).

  WHY THIS EXISTS INSTEAD OF findstr IN THE .CMD

    1) findstr reads files through the console code page. Its matching
       behaviour on UTF-8 files that contain CJK text is not dependable.
    2) Putting an "echo" line that contains bare parentheses inside an
       "if errorlevel 1 (...)" block is a classic cmd.exe parsing trap:
       cmd counts parentheses to find the end of the block, so a stray
       ")" inside the block can terminate it early and shift every
       following command.

    This script sidesteps both. PowerShell reads the file as real UTF-8
    and does plain substring matching, so the result does not depend on
    the code page at all; and the caller uses "goto" labels instead of a
    parenthesised block.

  USAGE
    powershell -NoProfile -ExecutionPolicy Bypass ^
      -File verify_markers.ps1 -Path <inject_main.py> -Ver 19 [-Neg]

    -Path   file to check                     (required)
    -Ver    expected RES.ver value            (default 19)
    -Neg    also run the negative asserts     (default off)

  EXIT CODES
    0  all good
    1  one or more required markers missing
    2  a forbidden marker is present
    3  file not found
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$Ver = '19',
    [switch]$Neg
)

if (-not (Test-Path -LiteralPath $Path)) {
    Write-Host "  [X] file not found: $Path"
    exit 3
}

$fi = Get-Item -LiteralPath $Path
$s = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)

Write-Host ("  file : {0}" -f $fi.FullName)
Write-Host ("  size : {0} bytes" -f $fi.Length)

$must = @(
    ('RES.ver = ' + $Ver),
    'ensureLayer',
    'mainpage_jx',
    'cleanJson',
    'MTC_GUARD',
    'var STALE',
    'function refresh'
)

$never = @(
    '_beatMax',
    'window.__MTC_BEAT',
    'BEATTIMER',
    'RINGMAX',
    '_beatDump',
    'last_beat',
    'setInterval(_beatDump',
    "__mtc_layer', '__mtc_v10css",
    "__mtc_v12css', '__mtc_v13css"
)

$miss = @()
foreach ($x in $must) {
    if ($s.IndexOf($x) -lt 0) { $miss += $x }
}

$hit = @()
if ($Neg) {
    foreach ($x in $never) {
        if ($s.IndexOf($x) -ge 0) { $hit += $x }
    }
}

if ($miss.Count -gt 0) {
    Write-Host '  [X] required marker MISSING:'
    foreach ($x in $miss) { Write-Host ('        {0}' -f $x) }
}
if ($hit.Count -gt 0) {
    Write-Host '  [X] forbidden marker PRESENT:'
    foreach ($x in $hit) { Write-Host ('        {0}' -f $x) }
}

if ($miss.Count -gt 0) { exit 1 }
if ($hit.Count -gt 0) { exit 2 }

if ($Neg) {
    Write-Host ('  [OK] {0} required present, {1} forbidden absent' -f $must.Count, $never.Count)
} else {
    Write-Host ('  [OK] {0} required present' -f $must.Count)
}
exit 0
