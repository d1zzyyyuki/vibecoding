$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$extension = Join-Path $root 'extension'
$dist = Join-Path $root 'dist'
$keys = Join-Path $root 'keys'
$key = Join-Path $keys 'hltv-adblocker.pem'
$profile = Join-Path $env:TEMP ('hltv-adblocker-build-' + [guid]::NewGuid().ToString('N'))

$edgeCandidates = @(
    'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    'C:\Program Files\Microsoft\Edge\Application\msedge.exe'
)
$edge = $edgeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) {
    throw 'Microsoft Edge not found. Install Edge or pass a Chromium-based Edge build.'
}

New-Item -ItemType Directory -Force -Path $dist, $keys | Out-Null
Remove-Item (Join-Path $root 'extension.crx'), (Join-Path $root 'extension.pem') -Force -ErrorAction SilentlyContinue

$arguments = @(
    "--user-data-dir=$profile",
    '--no-first-run',
    '--no-default-browser-check',
    "--pack-extension=$extension",
    '--no-message-box'
)
if (Test-Path $key) {
    $arguments += "--pack-extension-key=$key"
}

Write-Host 'Packing extension with Edge...'
& $edge @arguments
$generatedCrx = Join-Path $root 'extension.crx'
for ($i = 0; $i -lt 50 -and -not (Test-Path $generatedCrx); $i++) {
    Start-Sleep -Milliseconds 200
}
if (-not (Test-Path $generatedCrx)) {
    throw 'Edge did not create extension.crx'
}

$generatedKey = Join-Path $root 'extension.pem'
if ((-not (Test-Path $key)) -and (Test-Path $generatedKey)) {
    Move-Item $generatedKey $key -Force
}

$out = Join-Path $dist 'HLTV-AdBlocker.crx'
Copy-Item (Join-Path $root 'extension.crx') $out -Force
Remove-Item (Join-Path $root 'extension.crx') -Force -ErrorAction SilentlyContinue
Remove-Item $profile -Recurse -Force -ErrorAction SilentlyContinue

$bytes = [IO.File]::ReadAllBytes($out)
$magic = [Text.Encoding]::ASCII.GetString($bytes, 0, 4)
if ($magic -ne 'Cr24') {
    throw "invalid CRX header: $magic"
}

$size = [math]::Round((Get-Item $out).Length / 1KB, 1)
Write-Host "BUILD OK: $out (${size} KB)"
