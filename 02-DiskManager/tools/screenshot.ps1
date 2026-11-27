param(
    [string]$Out,
    [string]$Select,
    [int]$Width = 0,
    [int]$Height = 0
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root 'dist\DiskManager.exe'
if (-not (Test-Path $exe)) { throw 'dist\DiskManager.exe not found; run tools\build.ps1 first' }
if (-not $Out) { $Out = Join-Path $root 'docs\screenshots\main-1320.png' }

$arguments = @('--screenshot', $Out)
if ($Select) { $arguments += @('--select', $Select) }
if ($Width -gt 0) { $arguments += @('--width', $Width) }
if ($Height -gt 0) { $arguments += @('--height', $Height) }

$process = Start-Process -FilePath $exe -ArgumentList $arguments -Verb RunAs -Wait -PassThru
Write-Host "exit=$($process.ExitCode) screenshot=$Out"
if (-not (Test-Path $Out)) { throw 'screenshot was not written' }
Write-Host "bytes=$((Get-Item $Out).Length)"
