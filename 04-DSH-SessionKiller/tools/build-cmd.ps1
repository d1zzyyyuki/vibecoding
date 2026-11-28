# 把 src\DSH-SessionCleanup.ps1 打包成单文件 CMD 启动器。
# 用法： powershell -NoProfile -ExecutionPolicy Bypass -File tools\build-cmd.ps1
# 产物默认写入 dist\DSH-SessionKiller.cmd。

$ErrorActionPreference = 'Stop'

$here    = $PSScriptRoot
$project = Split-Path -Parent $here
$srcPs1  = Join-Path $project 'src\DSH-SessionCleanup.ps1'
$dist    = Join-Path $project 'dist'
$outCmd  = Join-Path $dist 'DSH-SessionKiller.cmd'
$marker  = '#-DSH-CLEAN-PAYLOAD-#'

if (-not (Test-Path -LiteralPath $srcPs1)) { throw "找不到源脚本：$srcPs1" }
New-Item -ItemType Directory -Force -Path $dist | Out-Null

# ReadAllText + UTF8 会自动剥掉 BOM（如有）
$payload = [System.IO.File]::ReadAllText($srcPs1, [System.Text.Encoding]::UTF8)
$payload = ($payload -replace "`r`n", "`n")

# 批处理头部。marker 那一行在 -Command 里拆成两段拼接，
# 文件里完整 marker 字符串只出现在真正的载荷起始行。
$header = @'
@echo off
setlocal
title DSH Session Killer
rem =====================================================================
rem  DeepSeek Harness conversation cleanup - single-file launcher.
rem
rem  The batch part below only extracts this file's PowerShell payload into
rem  %TEMP% and runs it. All Chinese text lives in the PowerShell part,
rem  which is read as UTF-8, so the CMD code page cannot garble it.
rem
rem  Source: 04-DSH-SessionKiller/src/DSH-SessionCleanup.ps1
rem  Build:  04-DSH-SessionKiller/tools/build-cmd.ps1
rem =====================================================================
set "DSH_TOOL_SELF=%~f0"
set "DSH_TOOL_TMP=%TEMP%\dsh-cleanup-%RANDOM%%RANDOM%.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$m='#-DSH'+'-CLEAN-PAYLOAD-#';$t=[IO.File]::ReadAllText($env:DSH_TOOL_SELF,[System.Text.Encoding]::UTF8);$i=$t.LastIndexOf($m);if($i -lt 0){exit 9};[IO.File]::WriteAllText($env:DSH_TOOL_TMP,$t.Substring($i+$m.Length),[System.Text.Encoding]::UTF8)"
if errorlevel 1 goto :extract_failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%DSH_TOOL_TMP%"
set "DSH_TOOL_RC=%ERRORLEVEL%"
del "%DSH_TOOL_TMP%" >nul 2>nul
exit /b %DSH_TOOL_RC%
:extract_failed
echo.
echo Failed to extract the PowerShell payload from this file.
echo The file may have been edited by another tool. Regenerate it with
echo 04-DSH-SessionKiller\tools\build-cmd.ps1
echo.
pause
exit /b 9
'@

$header = ($header -replace "`r`n", "`n") -replace "`n", "`r`n"
$body   = $marker + "`r`n" + ($payload -replace "`n", "`r`n")
$text   = $header.TrimEnd("`r", "`n") + "`r`n" + $body

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($outCmd, $text, $utf8NoBom)

$bytes = [System.IO.File]::ReadAllBytes($outCmd)
$magic = [System.Text.Encoding]::ASCII.GetString($bytes, 0, [Math]::Min(3, $bytes.Length))
if ($magic -ne '@ec') { throw '生成的 CMD 头无效' }
$hash = (Get-FileHash -LiteralPath $outCmd -Algorithm SHA256).Hash.ToLower()
Write-Host ('已生成：{0}' -f $outCmd) -ForegroundColor Green
Write-Host ('大小：{0:N0} 字节' -f $bytes.Length) -ForegroundColor DarkGray
Write-Host ('SHA256：{0}' -f $hash) -ForegroundColor DarkGray
