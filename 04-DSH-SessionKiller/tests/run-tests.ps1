# 无人值守测试：假档案 + 列表 / 删除 / 恢复 / 无效输入 / 真实 CMD 启动器。
# 用法： powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1

$ErrorActionPreference = 'Stop'

$here     = Split-Path -Parent $MyInvocation.MyCommand.Path
$project  = Split-Path -Parent $here
$toolPs1  = Join-Path $project 'src\DSH-SessionCleanup.ps1'
$dist     = Join-Path $project 'dist'
$toolCmd  = Join-Path $dist 'DSH-SessionKiller.cmd'
$profile_ = Join-Path $here 'profile'
$tmpDir   = Join-Path $here 'tmp'
$failures = New-Object System.Collections.Generic.List[string]

if (Test-Path -LiteralPath $tmpDir) { Remove-Item -LiteralPath $tmpDir -Recurse -Force }
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

$env:DSH_SKIP_APP_CHECK = '1'
$env:DSH_NO_PAUSE = '1'
$env:DSH_PROFILE_ROOT = $profile_

function Invoke-Child {
    param([string]$Exe, [string[]]$Arguments, [string]$InputText, [string]$Name, [string]$WorkingDir)
    $inFile  = Join-Path $tmpDir ($Name + '.in.txt')
    $outFile = Join-Path $tmpDir ($Name + '.out.txt')
    $errFile = Join-Path $tmpDir ($Name + '.err.txt')
    [IO.File]::WriteAllText($inFile, $InputText, (New-Object System.Text.UTF8Encoding($false)))
    $sp = @{
        FilePath               = $Exe
        ArgumentList           = $Arguments
        RedirectStandardInput  = $inFile
        RedirectStandardOutput = $outFile
        RedirectStandardError  = $errFile
        Wait                   = $true
        PassThru               = $true
        NoNewWindow            = $true
    }
    if ($WorkingDir) { $sp['WorkingDirectory'] = $WorkingDir }
    $p = Start-Process @sp
    $out = ''
    $err = ''
    if (Test-Path -LiteralPath $outFile) { $out = [IO.File]::ReadAllText($outFile, [Text.Encoding]::UTF8) }
    if (Test-Path -LiteralPath $errFile) { $err = [IO.File]::ReadAllText($errFile, [Text.Encoding]::UTF8) }
    Write-Host ''
    Write-Host ('---------- [{0}] exit={1} ----------' -f $Name, $p.ExitCode) -ForegroundColor Magenta
    Write-Host $out
    if ($err.Trim()) { Write-Host ('[stderr] ' + $err) -ForegroundColor DarkYellow }
    return [pscustomobject]@{ ExitCode = $p.ExitCode; Out = $out; Err = $err }
}

function Check {
    param([string]$Name, [scriptblock]$Test)
    try {
        if (& $Test) {
            Write-Host ('  PASS  ' + $Name) -ForegroundColor Green
        } else {
            Write-Host ('  FAIL  ' + $Name) -ForegroundColor Red
            $failures.Add($Name) | Out-Null
        }
    } catch {
        Write-Host ('  FAIL  ' + $Name + '  -> ' + $_.Exception.Message) -ForegroundColor Red
        $failures.Add($Name) | Out-Null
    }
}

function Read-Ws {
    $p = Join-Path $profile_ 'storages\workspace.json'
    return ([IO.File]::ReadAllText($p, [Text.Encoding]::UTF8) | ConvertFrom-Json)
}

# ---------------------------------------------------------------- 1. 造档案
$fxOut = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $here 'make-fixture.ps1') -Root $profile_ 2>&1
$fxRc = $LASTEXITCODE
if ($fxRc -ne 0) {
    Write-Host ('fixture 生成失败，exit={0}' -f $fxRc) -ForegroundColor Red
    Write-Host ($fxOut | Out-String)
    throw 'fixture 生成失败'
}

# 让无缓存的会话也有稳定的排序时间，避免依赖工作目录写入时刻
$sessRoot = Join-Path $profile_ 'sessions'
Get-ChildItem $sessRoot -Recurse -Directory | ForEach-Object {
    $_.LastWriteTime = (Get-Date).AddHours(-3)
}
# 单独把“子代理”目录时间设新一点（对应 now-5min）
$orphan = Join-Path $sessRoot '--D-dsh--\ffffffff-5555-5555-5555-555555555555'
if (Test-Path $orphan) { (Get-Item $orphan).LastWriteTime = (Get-Date).AddMinutes(-5) }

# ---------------------------------------------------------------- 2. 只列表
$r1 = Invoke-Child -Exe 'powershell.exe' -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $toolPs1) -InputText "q`r`n" -Name 'list-only'
Check '列表退出码为 0' { $r1.ExitCode -eq 0 }
Check '列表包含中文标题' { $r1.Out -like '*中文标题测试*' }
Check '列表显示归档标记' { $r1.Out -like '*归档*' }
Check '列表显示“共 7 个对话”' { $r1.Out -like '*共 7 个对话*' }

# ---------------------------------------------------------------- 2b. dry-run
$env:DSH_DRYRUN = '1'
$rDry = Invoke-Child -Exe 'powershell.exe' -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $toolPs1) -InputText "1`r`ny`r`n" -Name 'dry-run'
$env:DSH_DRYRUN = ''
Check 'dry-run 输出预览' { $rDry.Out -like '*dry-run*' }
Check 'dry-run 不创建回收站' { -not (Test-Path (Join-Path $profile_ 'trash')) }
Check 'dry-run 不移动会话目录' { Test-Path (Join-Path $sessRoot '--D-dsh--\session-11111111-1111-1111-1111-111111111111') }

# ---------------------------------------------------------------- 3. 删除 #2 #5
$r2 = Invoke-Child -Exe 'powershell.exe' -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $toolPs1) -InputText "2 4`r`ny`r`n" -Name 'delete-two'
Check '删除退出码为 0' { $r2.ExitCode -eq 0 }
Check '删除输出“已删除 2 个对话”' { $r2.Out -like '*已删除 2 个对话*' }

$s1 = 'session-11111111-1111-1111-1111-111111111111'
$s2 = 'session-22222222-2222-2222-2222-222222222222'
$s3 = 'session-33333333-3333-3333-3333-333333333333'
$s6 = 'session-66666666-6666-6666-6666-666666666666'
$ghost = 'session-dead-dead-dead-dead-deaddeaddead'

Check 's1 会话目录已移走' { -not (Test-Path (Join-Path $sessRoot "--D-dsh--\$s1")) }
Check 's2 会话目录已移走' { -not (Test-Path (Join-Path $sessRoot "--D-dsh--\$s2")) }
Check 's3 会话目录保留' { Test-Path (Join-Path $sessRoot "--D-dsh--\$s3") }
Check 's6 会话目录保留' { Test-Path (Join-Path $sessRoot "--D-dsh--\$s6") }
Check 's1 缓存记录已移走' { -not (Test-Path (Join-Path $profile_ "storages\session_projcache\sessions\$s1.json")) }
Check 's2 缓存记录已移走' { -not (Test-Path (Join-Path $profile_ "storages\session_projcache\sessions\$s2.json")) }
Check 's3 缓存记录保留' { Test-Path (Join-Path $profile_ "storages\session_projcache\sessions\$s3.json") }

$ws = Read-Ws
$wsA = $ws.tables.workspaces.'aaaaaaaa-1111-2222-3333-444444444444'
Check '工作区索引去掉了 s1' { @($wsA.sessionIds) -notcontains $s1 }
Check '工作区索引去掉了 s2' { @($wsA.sessionIds) -notcontains $s2 }
Check '工作区索引仍保留 s3' { @($wsA.sessionIds) -contains $s3 }
Check '工作区索引仍保留 ghost 登记' { @($wsA.sessionIds) -contains $ghost }
Check '归档列表已清空' { @($ws.global.archivedSessionIds).Count -eq 0 }
Check '置顶列表仍是 s3' { (@($ws.global.pinnedSessionIds) -join ',') -eq $s3 }
Check '第二个工作区未被破坏' { @($ws.tables.workspaces.'bbbbbbbb-1111-2222-3333-444444444444'.sessionIds).Count -eq 1 }

$trashDir = Join-Path $profile_ 'trash'
$batches = @()
if (Test-Path $trashDir) { $batches = @(Get-ChildItem $trashDir -Directory) }
Check '回收站有 1 个批次' { $batches.Count -eq 1 }
$batch = $batches[0]
Check '批次里有 manifest.json' { Test-Path (Join-Path $batch.FullName 'manifest.json') }
Check '批次里有 workspace.json 备份' { Test-Path (Join-Path $batch.FullName 'workspace.json.bak') }
Check '批次里有 s1 的日志目录' { Test-Path (Join-Path $batch.FullName "sessions\--D-dsh--\$s1\session.v4.jsonl.zstd") }
Check '批次里有 s2 的缓存记录' { Test-Path (Join-Path $batch.FullName "storages\session_projcache\sessions\$s2.json") }
$mf = [IO.File]::ReadAllText((Join-Path $batch.FullName 'manifest.json'), [Text.Encoding]::UTF8) | ConvertFrom-Json
Check 'manifest 记录 2 条' { @($mf.items).Count -eq 2 }

# ---------------------------------------------------------------- 4. 恢复
$r3 = Invoke-Child -Exe 'powershell.exe' -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $toolPs1) -InputText "r`r`n1`r`n" -Name 'restore'
Check '恢复退出码为 0' { $r3.ExitCode -eq 0 }
Check 's1 目录已恢复' { Test-Path (Join-Path $sessRoot "--D-dsh--\$s1\session.v4.jsonl.zstd") }
Check 's2 目录已恢复' { Test-Path (Join-Path $sessRoot "--D-dsh--\$s2\session.v4.jsonl.zstd") }
Check 's1 缓存已恢复' { Test-Path (Join-Path $profile_ "storages\session_projcache\sessions\$s1.json") }
Check 's2 缓存已恢复' { Test-Path (Join-Path $profile_ "storages\session_projcache\sessions\$s2.json") }
$ws2 = Read-Ws
$wsA2 = $ws2.tables.workspaces.'aaaaaaaa-1111-2222-3333-444444444444'
Check '侧栏登记已恢复 s1' { @($wsA2.sessionIds) -contains $s1 }
Check '侧栏登记已恢复 s2' { @($wsA2.sessionIds) -contains $s2 }
Check '归档状态已恢复 s2' { @($ws2.global.archivedSessionIds) -contains $s2 }

# ---------------------------------------------------------------- 5. 无效输入 + 删除空壳登记
$r4 = Invoke-Child -Exe 'powershell.exe' -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $toolPs1) -InputText "99`r`nq`r`n" -Name 'bad-input'
Check '越界输入被拒绝' { $r4.Out -like '*输入无法识别*' }
Check '越界输入后正常退出' { $r4.ExitCode -eq 0 }

$r5 = Invoke-Child -Exe 'powershell.exe' -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $toolPs1) -InputText "7`r`ny`r`n" -Name 'delete-ghost'
Check '空壳登记删除成功' { $r5.Out -like '*已删除 1 个对话*' }
$ws3 = Read-Ws
Check '空壳 id 已从索引移除' { @($ws3.tables.workspaces.'aaaaaaaa-1111-2222-3333-444444444444'.sessionIds) -notcontains $ghost }

# ---------------------------------------------------------------- 6. 真实 CMD 启动器
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $here 'make-fixture.ps1') -Root $profile_ | Out-Null
$r6 = Invoke-Child -Exe 'cmd.exe' -Arguments @('/c', (Split-Path $toolCmd -Leaf)) -InputText "q`r`n" -Name 'desktop-cmd' -WorkingDir $dist
Check 'CMD 启动器存在' { Test-Path -LiteralPath $toolCmd }
Check 'CMD 启动器退出码为 0' { $r6.ExitCode -eq 0 }
Check 'CMD 启动器成功打印列表' { $r6.Out -like '*共 7 个对话*' }
Check 'CMD 启动器中文未乱码' { $r6.Out -like '*中文标题测试*' }
Check 'CMD 启动器未留下临时脚本' { @(Get-ChildItem $env:TEMP -Filter 'dsh-cleanup-*.ps1' -ErrorAction SilentlyContinue).Count -eq 0 }

Write-Host ''
if ($failures.Count -eq 0) {
    Write-Host 'ALL PASS' -ForegroundColor Green
    exit 0
} else {
    Write-Host ('FAILED: ' + ($failures -join ' | ')) -ForegroundColor Red
    exit 1
}
