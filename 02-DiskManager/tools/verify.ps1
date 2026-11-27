param(
    [string]$Out
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root 'dist\DiskManager.exe'
if (-not (Test-Path $exe)) { throw 'dist\DiskManager.exe not found; run tools\build.ps1 first' }
if (-not $Out) { $Out = Join-Path $root 'out\selftest.json' }
$dir = Split-Path -Parent $Out
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }

Write-Host "running: $exe --selftest --out $Out"
$process = Start-Process -FilePath $exe -ArgumentList @('--selftest', '--out', $Out) -Verb RunAs -Wait -PassThru
Write-Host "exit=$($process.ExitCode)"
if (-not (Test-Path $Out)) { throw 'selftest json was not written' }

$json = [IO.File]::ReadAllText($Out, [Text.Encoding]::UTF8) | ConvertFrom-Json
Write-Host "version=$($json.version) passed=$($json.passed) durationMs=$($json.durationMs) elevated=$($json.elevated)"
foreach ($disk in $json.disks) {
    $speed = if ($disk.speed -and $disk.speed.success) { "$([math]::Round($disk.speed.throughputMBps, 2)) MB/s" } else { 'n/a' }
    Write-Host "disk $($disk.number): $($disk.model) | $($disk.busType) $($disk.pcieLink) | $($disk.mediaKind) | speed=$speed | partitions=$($disk.partitions.Count)"
}
foreach ($check in $json.checks) {
    Write-Host ("{0} {1}: {2}" -f ($(if ($check.passed) { 'PASS' } else { 'FAIL' })), $check.name, $check.detail)
}
Write-Host "json=$Out"
if ($json.passed) { exit 0 } else { exit 1 }
