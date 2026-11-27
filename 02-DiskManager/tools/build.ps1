param(
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dotnet = $env:DOTNET_EXE
if (-not $dotnet) {
    $bundled = 'D:\dsh\work\dotnet\dotnet.exe'
    if (Test-Path $bundled) { $dotnet = $bundled } else { $dotnet = 'dotnet' }
}
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_NOLOGO = '1'

Write-Host "[1/4] build tests"
& $dotnet build (Join-Path $root 'tests\DiskManager.Tests\DiskManager.Tests.csproj') -c Release -v:minimal
if ($LASTEXITCODE -ne 0) { throw 'test project build failed' }

if (-not $SkipTests) {
    Write-Host "[2/4] run tests"
    & (Join-Path $root 'tests\DiskManager.Tests\bin\Release\net8.0\DiskManager.Tests.exe')
    if ($LASTEXITCODE -ne 0) { throw 'unit tests failed' }
} else {
    Write-Host "[2/4] tests skipped"
}

Write-Host "[3/4] build app"
& $dotnet build (Join-Path $root 'src\DiskManager.App\DiskManager.App.csproj') -c Release -v:minimal
if ($LASTEXITCODE -ne 0) { throw 'app build failed' }

Write-Host "[4/4] build offline validator/executor"
& $dotnet build (Join-Path $root 'src\DiskManager.Offline\DiskManager.Offline.csproj') -c Release -v:minimal
if ($LASTEXITCODE -ne 0) { throw 'offline build failed' }

$dist = Join-Path $root 'dist'
if (Test-Path $dist) { Remove-Item (Join-Path $dist '*') -Force -Recurse -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Force -Path $dist | Out-Null
Copy-Item (Join-Path $root 'src\DiskManager.App\bin\Release\net48\DiskManager.exe') (Join-Path $dist 'DiskManager.exe') -Force

$files = @(Get-ChildItem $dist -File)
if ($files.Count -ne 1 -or $files[0].Name -ne 'DiskManager.exe') {
    throw 'dist must contain exactly one executable'
}

$size = [math]::Round($files[0].Length / 1KB, 1)
Write-Host "BUILD OK: dist\DiskManager.exe (${size} KB)"
