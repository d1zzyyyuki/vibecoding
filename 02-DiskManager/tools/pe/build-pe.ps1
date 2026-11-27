param(
    [string]$AdkRoot = 'C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit',
    [string]$OutputRoot = '',
    [string]$JobPath = ''
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $OutputRoot) { $OutputRoot = Join-Path $repo 'out\pe' }
if (-not $JobPath) { $JobPath = Join-Path $env:ProgramData 'DiskManager\pe\job.json' }
$copype = Join-Path $AdkRoot 'Windows Preinstallation Environment\amd64\copype.cmd'
$makeMedia = Join-Path $AdkRoot 'Windows Preinstallation Environment\amd64\MakeWinPEMedia.cmd'
$dotnet = $env:DOTNET_EXE
if (-not $dotnet) {
    $candidate = 'D:\dsh\work\dotnet\dotnet.exe'
    $dotnet = if (Test-Path $candidate) { $candidate } else { 'dotnet' }
}

if (-not (Test-Path $copype)) {
    throw "Windows ADK WinPE 未安装：缺少 $copype。先安装 Windows ADK + WinPE add-on，再运行本脚本。"
}

$offlineProject = Join-Path $repo 'src\DiskManager.Offline\DiskManager.Offline.csproj'
$publishDir = Join-Path $OutputRoot 'publish'
$mediaDir = Join-Path $OutputRoot 'media'
Remove-Item $OutputRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $publishDir | Out-Null

Write-Host '[1/4] publish offline validator/planner'
& $dotnet publish $offlineProject -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o $publishDir
if ($LASTEXITCODE -ne 0) { throw 'offline publish failed' }

Write-Host '[2/4] create WinPE media'
& $copype amd64 $mediaDir
if ($LASTEXITCODE -ne 0) { throw 'copype failed' }

Write-Host '[3/4] inject DiskManagerOffline'
$mount = Join-Path $OutputRoot 'mount'
New-Item -ItemType Directory -Force -Path $mount | Out-Null
& dism /Mount-Wim /WimFile:(Join-Path $mediaDir 'media\sources\boot.wim') /index:1 /MountDir:$mount
if ($LASTEXITCODE -ne 0) { throw 'dism mount failed' }
try {
    $target = Join-Path $mount 'DiskManager'
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item (Join-Path $publishDir 'DiskManagerOffline.exe') $target -Force
    Copy-Item (Join-Path $PSScriptRoot 'startnet.cmd') $target -Force
    if (Test-Path $JobPath) {
        Copy-Item $JobPath (Join-Path $target 'job.json') -Force
    } else {
        Copy-Item (Join-Path $PSScriptRoot 'job.example.json') $target -Force
    }
    Copy-Item (Join-Path $PSScriptRoot 'startnet.cmd') (Join-Path $mount 'Windows\System32\startnet.cmd') -Force
} finally {
    & dism /Unmount-Wim /MountDir:$mount /Commit
}

Write-Host '[4/4] build ISO'
& $makeMedia /ISO $mediaDir (Join-Path $OutputRoot 'DiskManagerPE.iso')
if ($LASTEXITCODE -ne 0) { throw 'MakeWinPEMedia failed' }
Write-Host "PE ISO: $(Join-Path $OutputRoot 'DiskManagerPE.iso')"
Write-Host '注意：当前离线程序只实现 validate/plan；写入执行引擎接入后再把 startnet.cmd 改为 run。'
