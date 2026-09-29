# logscan.ps1 - UTF-8-safe substring check for inject.log
# exit 0 = needle NOT found (clean) | exit 1 = needle found | exit 3 = file unreadable
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Need
)
try {
    $t = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
} catch {
    exit 3
}
if ($t.IndexOf($Need, [StringComparison]::Ordinal) -ge 0) { exit 1 }
exit 0
