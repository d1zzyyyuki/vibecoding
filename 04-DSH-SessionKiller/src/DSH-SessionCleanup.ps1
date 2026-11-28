# ============================================================
# DeepSeek Harness 会话清理器
#   - 列出全部对话（含侧栏里看不到的子代理会话）
#   - 选择编号后彻底删除：会话日志 + 投影缓存 + 工作区索引登记
#   - 删除前先移入 %USERPROFILE%\.dsh\trash\<时间戳>\ ，可随时恢复
#   - 关闭 DSH：外部没有优雅退出接口（点窗口关闭只会缩到托盘），确认后直接结束进程
#
# 直接运行： powershell -NoProfile -ExecutionPolicy Bypass -File DSH-SessionCleanup.ps1
# 环境变量（一般不用改）：
#   DSH_PROFILE_ROOT     覆盖 DSH 数据目录，默认 %USERPROFILE%\.dsh
#   DSH_SKIP_APP_CHECK=1 跳过"DSH 是否在运行"的检查（自动化测试用）
#   DSH_NO_PAUSE=1       结束后不等待回车
#   DSH_DRYRUN=1         只预览删除项，不关闭 DSH、不改磁盘
# ============================================================

$ErrorActionPreference = 'Stop'

$script:ProfileRoot = $env:DSH_PROFILE_ROOT
if ([string]::IsNullOrWhiteSpace($script:ProfileRoot)) {
    $script:ProfileRoot = Join-Path $env:USERPROFILE '.dsh'
}
$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$script:AppWasRunning = $false
$script:AppExe = ''
$script:AppProcessNames = @('DeepSeek Harness')
# 按名字找不到时，是否再按映像路径兜底扫一遍。生产环境开着（防改名），
# 测试/嵌入场景可关掉，否则杀掉测试进程后会误把真正的 DSH 当成"残留进程"。
$script:AppPathFallback = $true

# ------------------------------------------------------------
# 通用小工具
# ------------------------------------------------------------

# 安全地按路径取嵌套属性，任何一层缺失都返回 $null
function Get-Val {
    param($Object, [string[]]$Path)
    $cur = $Object
    foreach ($key in $Path) {
        if ($null -eq $cur) { return $null }
        $prop = $cur.PSObject.Properties[$key]
        if ($null -eq $prop) { return $null }
        $cur = $prop.Value
    }
    return $cur
}

# 中文字符按 2 列宽计算，用于对齐表格
function Get-DisplayWidth {
    param([string]$Text)
    $w = 0
    if ([string]::IsNullOrEmpty($Text)) { return 0 }
    foreach ($ch in $Text.ToCharArray()) {
        $code = [int]$ch
        if (($code -ge 0x1100 -and $code -le 0x115F) -or
            ($code -ge 0x2E80 -and $code -le 0xA4CF) -or
            ($code -ge 0xAC00 -and $code -le 0xD7A3) -or
            ($code -ge 0xF900 -and $code -le 0xFAFF) -or
            ($code -ge 0xFE30 -and $code -le 0xFE6F) -or
            ($code -ge 0xFF00 -and $code -le 0xFF60) -or
            ($code -ge 0xFFE0 -and $code -le 0xFFE6)) { $w += 2 } else { $w += 1 }
    }
    return $w
}

# 截断并补空格到指定显示宽度
function Format-Cell {
    param([string]$Text, [int]$Width)
    if ($null -eq $Text) { $Text = '' }
    $Text = ($Text -replace '[\r\n\t]+', ' ')
    $sb = New-Object System.Text.StringBuilder
    $w = 0
    foreach ($ch in $Text.ToCharArray()) {
        $cw = Get-DisplayWidth -Text ([string]$ch)
        if ($w + $cw -gt $Width) { break }
        [void]$sb.Append($ch)
        $w += $cw
    }
    return ($sb.ToString() + (' ' * ($Width - $w)))
}

function Format-Size {
    param([double]$Bytes)
    if ($Bytes -le 0) { return '—' }
    if ($Bytes -ge 1MB) { return ('{0:N1} MB' -f ($Bytes / 1MB)) }
    if ($Bytes -ge 1KB) { return ('{0:N0} KB' -f ($Bytes / 1KB)) }
    return ('{0:N0} B' -f $Bytes)
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $raw = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
    return ($raw | ConvertFrom-Json)
}

function Write-JsonFile {
    param([string]$Path, $Value, [int]$Depth = 20)
    $json = $Value | ConvertTo-Json -Depth $Depth
    [System.IO.File]::WriteAllText($Path, $json, $script:Utf8NoBom)
}

function Get-ConsoleWidth {
    try {
        $w = $Host.UI.RawUI.WindowSize.Width
        if ($w -ge 60) { return $w }
    } catch { }
    return 110
}

function Wait-Exit {
    if ($env:DSH_NO_PAUSE -eq '1') { return }
    Write-Host ''
    try { Read-Host '按回车键关闭窗口' | Out-Null } catch { }
}

# ------------------------------------------------------------
# DSH 进程处理
# ------------------------------------------------------------
# 为什么不能"温和关闭"：DSH 桌面端在 Electron 主进程里把窗口 close 事件拦掉了
# （window.on('close') -> event.preventDefault() -> 隐藏到托盘），所以从外部发
# WM_CLOSE（Process.CloseMainWindow、点窗口的 X）永远只是把窗口缩到托盘，进程照旧跑。
# 官方能让进程退出的入口只有托盘菜单的"退出"（还要过一道确认框），外部没有 IPC 或
# 命令行退出开关。因此本工具在用户确认后直接结束进程（等同任务管理器"结束任务"）。

function Find-DshAppExe {
    # 不写死用户名/安装路径；先看当前进程的映像路径，再查常见安装位置。
    foreach ($p in @(Get-DshProcesses)) {
        try {
            if ($p.Path) { return $p.Path }
        } catch { }
    }
    $candidates = @()
    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA 'Programs\DeepSeek Harness\DeepSeek Harness.exe')
    }
    if ($env:ProgramFiles) {
        $candidates += (Join-Path $env:ProgramFiles 'DeepSeek Harness\DeepSeek Harness.exe')
    }
    if (${env:ProgramFiles(x86)}) {
        $candidates += (Join-Path ${env:ProgramFiles(x86)} 'DeepSeek Harness\DeepSeek Harness.exe')
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return ''
}

function Get-SafeChildPath {
    # 只允许把操作限制在 Root 下面；拒绝 .. 或绝对路径逃逸。
    param([string]$Root, [string]$Relative)
    if ([string]::IsNullOrWhiteSpace($Relative)) { throw '空路径' }
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $candidate = [IO.Path]::GetFullPath((Join-Path $rootFull $Relative))
    if (-not ($candidate -eq $rootFull -or
              $candidate.StartsWith($rootFull + '\', [StringComparison]::OrdinalIgnoreCase))) {
        throw ('路径越界：' + $Relative)
    }
    return $candidate
}

function Get-DshProcesses {
    # 按进程名取 + 按映像路径兜底：DSH 主进程和它的 Electron 子进程同名，
    # 将来若改名，路径匹配还能找到。任何异常都当"没找到"，不打断主流程。
    $found = @{}
    try {
        foreach ($procName in $script:AppProcessNames) {
            foreach ($p in @(Get-Process -Name $procName -ErrorAction SilentlyContinue)) {
                $found[$p.Id] = $p
            }
        }
    } catch { }
    if ($script:AppPathFallback -and $found.Count -eq 0) {
        try {
            foreach ($p in @(Get-Process -ErrorAction SilentlyContinue)) {
                try {
                    $path = $p.Path
                    if ($path -and ($path -eq $script:AppExe -or $path -like '*\DeepSeek Harness*.exe')) { $found[$p.Id] = $p }
                } catch { }
            }
        } catch { }
    }
    return @($found.Values)
}

function Write-CloseLog {
    param([string]$Text)
    if (-not $script:CloseLogPath) { return }
    try {
        [System.IO.File]::AppendAllText($script:CloseLogPath,
            ('[{0}] {1}' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss.fff'), $Text) + "`n",
            $script:Utf8NoBom)
    } catch { }
}

# Get-Process 会把"正在退出"的进程也列出来，所以连续两次都为空才认为真的退干净
function Wait-DshProcessesGone {
    param([int]$TimeoutSeconds = 20)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $emptySeen = 0
    while ((Get-Date) -lt $deadline) {
        if ((Get-DshProcesses).Count -eq 0) {
            $emptySeen++
            if ($emptySeen -ge 2) { return $true }
        } else {
            $emptySeen = 0
        }
        Start-Sleep -Milliseconds 250
    }
    return ((Get-DshProcesses).Count -eq 0)
}

# 结束 DSH 全部进程：只对枚举到的精确 PID 用 Stop-Process -Force，
# 不杀"进程树"（taskkill /T），避免误伤 DSH 自己的子进程和正在运行本工具的宿主进程。
function Stop-DshProcesses {
    param($Procs, [switch]$DryRun)

    $script:CloseLogPath = Join-Path $env:TEMP 'dsh-cleanup-closeapp.log'
    $dry = $DryRun -or ($env:DSH_APP_CLOSE_DRYRUN -eq '1')
    $ids = @($Procs | ForEach-Object { $_.Id })
    Write-CloseLog (('需要结束 DSH，PID：' + ($ids -join ', ')) + $(if ($dry) { '（dry-run）' } else { '' }))

    if ($dry) {
        Write-Host ''
        Write-Host ('  [dry-run] 将结束这些 PID（未实际执行）：{0}' -f ($ids -join ', ')) -ForegroundColor Yellow
        return $true
    }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    Write-Host ''
    Write-Host ('  正在结束 DSH 进程（{0} 个）：{1}' -f $Procs.Count, ($ids -join ', ')) -ForegroundColor Gray

    for ($round = 1; $round -le 3; $round++) {
        # 先杀有窗口的主进程（Electron 主进程），它会带走自己的子进程；
        # 反过来先杀宿主会让桌面壳以为后端挂了而尝试重启。
        $alive = @(Get-DshProcesses | Sort-Object @{ Expression = { if ($_.MainWindowHandle -ne 0) { 0 } else { 1 } } })
        if ($alive.Count -eq 0) { break }

        foreach ($p in $alive) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch { }
        }
        Write-CloseLog ('第 {0} 轮 Stop-Process，目标 {1} 个进程' -f $round, $alive.Count)
        if (Wait-DshProcessesGone -TimeoutSeconds 5) {
            Write-Host ('  已结束 DSH（用时 {0:N1} 秒）。' -f $sw.Elapsed.TotalSeconds) -ForegroundColor Green
            Write-CloseLog ('Stop-Process 成功，用时 {0:N1}s' -f $sw.Elapsed.TotalSeconds)
            return $true
        }

        # 兜底：taskkill /F /PID（刻意不带 /T，只结束这一个进程）
        foreach ($p in @(Get-DshProcesses)) {
            try { & cmd.exe /c "taskkill /F /PID $($p.Id) >nul 2>&1" | Out-Null } catch { }
        }
        Write-CloseLog ('第 {0} 轮 taskkill 兜底' -f $round)
        if (Wait-DshProcessesGone -TimeoutSeconds 4) {
            Write-Host ('  已结束 DSH（用时 {0:N1} 秒）。' -f $sw.Elapsed.TotalSeconds) -ForegroundColor Green
            Write-CloseLog ('taskkill 成功，用时 {0:N1}s' -f $sw.Elapsed.TotalSeconds)
            return $true
        }
    }

    $left = @(Get-DshProcesses)
    if ($left.Count -eq 0) {
        Write-Host ('  已结束 DSH（用时 {0:N1} 秒）。' -f $sw.Elapsed.TotalSeconds) -ForegroundColor Green
        return $true
    }

    Write-Host ('  仍有 {0} 个进程没退出：{1}' -f $left.Count, (($left | ForEach-Object { $_.Id }) -join ', ')) -ForegroundColor Red
    Write-CloseLog ('失败，剩余 PID：' + (($left | ForEach-Object { $_.Id }) -join ', '))
    if ($script:CloseLogPath) {
        Write-Host ('  详细日志：{0}' -f $script:CloseLogPath) -ForegroundColor DarkGray
    }
    return $false
}

# 走第二方案：用户自己在托盘里点"退出"，工具等它退干净
function Wait-DshManualExit {
    Write-Host ''
    Write-Host '  请右键任务栏托盘里的 DSH 图标 → 退出（如果弹确认框，点"退出"）。' -ForegroundColor Cyan
    Write-Host '  工具在等它退出，最多 90 秒（可随时 Ctrl+C 放弃）。' -ForegroundColor DarkGray
    $deadline = (Get-Date).AddSeconds(90)
    $lastNote = -1
    while ((Get-Date) -lt $deadline) {
        if ((Get-DshProcesses).Count -eq 0) {
            Write-Host '  DSH 已退出。' -ForegroundColor Green
            return $true
        }
        $leftSec = [int]($deadline - (Get-Date)).TotalSeconds
        if ($lastNote -lt 0 -or ($lastNote - $leftSec) -ge 10) {
            Write-Host ('    等待中… 还剩 {0} 秒' -f $leftSec) -ForegroundColor DarkGray
            $lastNote = $leftSec
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Host '  等待超时，DSH 仍在运行。' -ForegroundColor Red
    return $false
}

# 数据文件能否独占打开：能打开说明 DSH 不再占着它
function Test-DataUnlocked {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    try {
        $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
        $fs.Close()
        return $true
    } catch {
        return $false
    }
}

# 返回 $true 表示可以安全修改磁盘数据
function Confirm-AppClosed {
    if ($env:DSH_SKIP_APP_CHECK -eq '1') { return $true }

    $procs = @(Get-DshProcesses)
    if ($procs.Count -eq 0) { return $true }

    $script:AppWasRunning = $true
    foreach ($p in $procs) {
        try {
            if ($p.Path) { $script:AppExe = $p.Path; break }
        } catch { }
    }
    if (-not $script:AppExe) { $script:AppExe = Find-DshAppExe }

    Write-Host ''
    Write-Host ('  注意：DeepSeek Harness 正在运行（{0} 个进程，PID: {1}）。' -f $procs.Count, (($procs | ForEach-Object { $_.Id }) -join ', ')) -ForegroundColor Yellow
    Write-Host '  它的窗口点"关闭"只是缩到托盘，进程不会退出，所以本工具要让它彻底结束。' -ForegroundColor Yellow
    Write-Host '  正在生成的回答会丢失 —— 请先等本轮跑完再用本工具。' -ForegroundColor DarkYellow
    Write-Host ''
    $ans = Read-Host '  y = 由本工具结束 DSH 进程并继续（推荐）    m = 我自己从托盘退出（工具等你）    其他键 = 退出本工具'

    $closed = $false
    if ($ans -match '^\s*[yY]') {
        $closed = Stop-DshProcesses -Procs $procs
        if (-not $closed) {
            Write-Host ''
            Write-Host '  自动结束没成功，你可以从托盘手动退出 DSH 后重跑本工具。' -ForegroundColor Red
            return $false
        }
    } elseif ($ans -match '^\s*[mM]') {
        $closed = Wait-DshManualExit
        if (-not $closed) { return $false }
    } else {
        return $false
    }

    # 进程退出后还要确认它没被自动拉起、数据文件也没被占着
    Start-Sleep -Milliseconds 600
    $again = @(Get-DshProcesses)
    if ($again.Count -gt 0) {
        Write-Host ('  警告：DSH 又启动了（PID: {0}），已中止操作，磁盘没有被改动。' -f (($again | ForEach-Object { $_.Id }) -join ', ')) -ForegroundColor Red
        return $false
    }
    $wsPath = Join-Path $script:ProfileRoot 'storages\workspace.json'
    $wait = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $wait -and -not (Test-DataUnlocked -Path $wsPath)) {
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-DataUnlocked -Path $wsPath)) {
        Write-Host '  警告：workspace.json 仍被占用，已中止操作，磁盘没有被改动。' -ForegroundColor Red
        return $false
    }

    Write-Host '  DSH 已完全退出，可以安全修改数据。' -ForegroundColor Green
    return $true
}

# ------------------------------------------------------------
# 会话目录扫描
# ------------------------------------------------------------
function New-SessionRow {
    param([string]$Id)
    return [pscustomobject]@{
        Id           = $Id
        Title        = ''
        WorkspaceIds = New-Object System.Collections.ArrayList
        Workspace    = ''
        Dir          = ''
        RelDir       = ''
        CacheFile    = ''
        RelCache     = ''
        SizeBytes    = [double]0
        LastAt       = $null
        Archived     = $false
        Pinned       = $false
        InWorkspace  = $false
    }
}

function Get-SessionCatalog {
    param([string]$Root, $WorkspaceState)

    $sessionRoot = Join-Path $Root 'sessions'
    $cacheDir    = Join-Path $Root 'storages\session_projcache\sessions'
    $catalog     = @{}
    $wsByKey     = @{}

    if ($WorkspaceState) {
        foreach ($wpProp in $WorkspaceState.tables.workspaces.PSObject.Properties) {
            $wsByKey[$wpProp.Name] = $wpProp.Value
            $ids = @(Get-Val $wpProp.Value @('sessionIds'))
            foreach ($sid in $ids) {
                if ([string]::IsNullOrWhiteSpace($sid)) { continue }
                if (-not $catalog.ContainsKey($sid)) { $catalog[$sid] = New-SessionRow -Id $sid }
                [void]$catalog[$sid].WorkspaceIds.Add($wpProp.Name)
            }
        }
    }

    if (Test-Path -LiteralPath $sessionRoot) {
        foreach ($wsDir in Get-ChildItem -LiteralPath $sessionRoot -Directory -ErrorAction SilentlyContinue) {
            foreach ($sDir in Get-ChildItem -LiteralPath $wsDir.FullName -Directory -ErrorAction SilentlyContinue) {
                $sid = $sDir.Name
                if (-not $catalog.ContainsKey($sid)) { $catalog[$sid] = New-SessionRow -Id $sid }
                $catalog[$sid].Dir = $sDir.FullName
                $catalog[$sid].RelDir = 'sessions\' + $wsDir.Name + '\' + $sid
            }
        }
    }

    if (Test-Path -LiteralPath $cacheDir) {
        foreach ($f in Get-ChildItem -LiteralPath $cacheDir -Filter '*.json' -File -ErrorAction SilentlyContinue) {
            $sid = [System.IO.Path]::GetFileNameWithoutExtension($f.Name)
            if (-not $catalog.ContainsKey($sid)) { $catalog[$sid] = New-SessionRow -Id $sid }
            $catalog[$sid].CacheFile = $f.FullName
            $catalog[$sid].RelCache = 'storages\session_projcache\sessions\' + $f.Name
        }
    }

    $archived = @()
    $pinned   = @()
    if ($WorkspaceState) {
        $archived = @(Get-Val $WorkspaceState @('global', 'archivedSessionIds'))
        $pinned   = @(Get-Val $WorkspaceState @('global', 'pinnedSessionIds'))
    }

    foreach ($row in $catalog.Values) {
        $row.InWorkspace = ($row.WorkspaceIds.Count -gt 0)
        $row.Archived = ($archived -contains $row.Id)
        $row.Pinned   = ($pinned -contains $row.Id)

        if ($row.CacheFile) {
            $rec = $null
            try { $rec = Read-JsonFile -Path $row.CacheFile } catch { $rec = $null }
            if ($rec) {
                $title = Get-Val $rec @('record', 'rows', 'title', 'val')
                if (-not $title) {
                    $turns = @(Get-Val $rec @('record', 'rows', 'turnOutline', 'val', 'turns'))
                    if ($turns.Count -gt 0) { $title = $turns[0].prompt }
                }
                if ($title) { $row.Title = (([string]$title) -replace '\s+', ' ').Trim() }

                $lastMs = Get-Val $rec @('record', 'rows', 'sessionListMetadata', 'val', 'lastPromptAt')
                if (-not $lastMs) { $lastMs = Get-Val $rec @('record', 'identity', 'createdAt') }
                if ($lastMs) {
                    try {
                        # 统一存成本地 DateTime，避免 DateTimeOffset 与 DateTime 混排时比较报错
                        $row.LastAt = [DateTimeOffset]::FromUnixTimeMilliseconds([int64]$lastMs).LocalDateTime
                    } catch { }
                }
            }
        }

        if ($row.Dir -and (Test-Path -LiteralPath $row.Dir)) {
            $sum = Get-ChildItem -LiteralPath $row.Dir -Recurse -File -ErrorAction SilentlyContinue |
                Measure-Object -Property Length -Sum
            if ($sum.Sum) { $row.SizeBytes = [double]$sum.Sum }
            if (-not $row.LastAt) {
                try { $row.LastAt = (Get-Item -LiteralPath $row.Dir).LastWriteTime } catch { }
            }
        }

        if ($row.WorkspaceIds.Count -gt 0) {
            $names = @()
            foreach ($wid in $row.WorkspaceIds) {
                $wt = Get-Val $wsByKey[$wid] @('title')
                $wp = Get-Val $wsByKey[$wid] @('path')
                if ($wt) { $names += [string]$wt }
                elseif ($wp) { $names += [string]$wp }
                else { $names += '工作区' }
            }
            $row.Workspace = ($names -join '+')
        }

        if (-not $row.Title) {
            if (-not $row.Dir -and -not $row.CacheFile) { $row.Title = '(空壳登记，无数据文件)' }
            else { $row.Title = '(无标题对话)' }
        }
    }

    $list = @($catalog.Values)
    $sorted = $list | Sort-Object -Property @{
        Expression = { if ($_.LastAt) { $_.LastAt } else { [datetime]::MinValue } }
        Descending = $true
    }, @{ Expression = { $_.Title }; Descending = $false }
    return @($sorted)
}

function Get-RowStatus {
    param($Row)
    $tags = @()
    if ($Row.Archived) { $tags += '归档' }
    if ($Row.Pinned) { $tags += '置顶' }
    if (-not $Row.InWorkspace) { $tags += '隐藏' }
    return ($tags -join '/')
}

function Show-SessionCatalog {
    param($Rows, [int]$TotalWidth)

    $idxW = 4; $timeW = 15; $sizeW = 8; $wsW = 13; $stW = 7; $gap = 1
    $titleW = $TotalWidth - ($idxW + $timeW + $sizeW + $wsW + $stW + 6 + ($gap * 5))
    if ($titleW -lt 20) { $titleW = 20 }

    $sep = ' ' * $gap
    $head = ('{0}{1}{2}{3}{4}{5}{6}{7}{8}{9}{10}' -f
        (Format-Cell '编号' $idxW), $sep,
        (Format-Cell '最近活动' $timeW), $sep,
        (Format-Cell '大小' $sizeW), $sep,
        (Format-Cell '工作区' $wsW), $sep,
        (Format-Cell '状态' $stW), $sep,
        (Format-Cell '对话标题' $titleW))
    Write-Host '  ' -NoNewline
    Write-Host $head -ForegroundColor Cyan
    Write-Host ('  ' + ('-' * ($TotalWidth - 2))) -ForegroundColor DarkGray

    $i = 0
    foreach ($row in $Rows) {
        $i++
        $when = '—'
        if ($row.LastAt) {
            $lt = $row.LastAt
            if ($lt -is [System.DateTimeOffset]) { $lt = $lt.LocalDateTime }
            if ($lt.Year -eq (Get-Date).Year) { $when = $lt.ToString('MM-dd HH:mm') }
            else { $when = $lt.ToString('yyyy-MM-dd') }
        }
        $line = '{0}{1}{2}{3}{4}{5}{6}{7}{8}{9}{10}' -f
            (Format-Cell ($i.ToString().PadLeft($idxW - 2)) $idxW), $sep,
            (Format-Cell $when $timeW), $sep,
            (Format-Cell (Format-Size $row.SizeBytes) $sizeW), $sep,
            (Format-Cell $row.Workspace $wsW), $sep,
            (Format-Cell (Get-RowStatus $row) $stW), $sep,
            (Format-Cell $row.Title $titleW)
        Write-Host '  ' -NoNewline
        if ($row.Archived) { Write-Host $line -ForegroundColor DarkGray }
        elseif (-not $row.InWorkspace) { Write-Host $line -ForegroundColor DarkGray }
        else { Write-Host $line }
    }
}

# ------------------------------------------------------------
# 选择解析
# ------------------------------------------------------------
function ConvertTo-Selection {
    param([string]$Text, [int]$Max)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    $norm = $Text -replace '，', ',' -replace '、', ',' -replace '；', ',' -replace ';', ','
    $norm = $norm -replace '\s+', ','
    $picked = New-Object System.Collections.Generic.List[int]
    foreach ($tok in $norm.Split(',', [System.StringSplitOptions]::RemoveEmptyEntries)) {
        if ($tok -match '^(\d+)-(\d+)$') {
            $a = [int]$Matches[1]; $b = [int]$Matches[2]
            if ($a -gt $b) { $t = $a; $a = $b; $b = $t }
            if ($a -lt 1 -or $b -gt $Max) { return $null }
            for ($k = $a; $k -le $b; $k++) { if (-not $picked.Contains($k)) { $picked.Add($k) } }
        } elseif ($tok -match '^\d+$') {
            $n = [int]$tok
            if ($n -lt 1 -or $n -gt $Max) { return $null }
            if (-not $picked.Contains($n)) { $picked.Add($n) }
        } else {
            return $null
        }
    }
    if ($picked.Count -eq 0) { return $null }
    return @($picked | Sort-Object)
}

# ------------------------------------------------------------
# 删除（移入回收站 + 清理索引）
# ------------------------------------------------------------
function Invoke-DeleteSessions {
    param([string]$Root, $Rows, $PickedRows, [switch]$DryRun)

    if ($DryRun) {
        Write-Host ''
        Write-Host '  [dry-run] 以下对话将被移入回收站（磁盘不会改动）：' -ForegroundColor Yellow
        foreach ($row in $PickedRows) {
            Write-Host ('    - [{0}] {1}' -f $row.Id, $row.Title) -ForegroundColor Yellow
        }
        return
    }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $trashRoot = Join-Path $Root ('trash\' + $stamp)
    # 即使只删“空壳登记”（没有文件要搬），也要先建出批次目录，好放索引备份
    if (-not (Test-Path -LiteralPath $trashRoot)) { New-Item -ItemType Directory -Path $trashRoot -Force | Out-Null }
    $moved = 0
    $manifestItems = @()

    foreach ($row in $PickedRows) {
        $item = [ordered]@{
            sessionId    = $row.Id
            title        = $row.Title
            relDir       = $row.RelDir
            relCache     = $row.RelCache
            workspaceIds = @($row.WorkspaceIds)
            archived     = [bool]$row.Archived
            pinned       = [bool]$row.Pinned
        }
        $manifestItems += $item

        if ($row.RelDir) {
            $src = Get-SafeChildPath -Root $Root -Relative $row.RelDir
            if (Test-Path -LiteralPath $src) {
                $dst = Get-SafeChildPath -Root $trashRoot -Relative $row.RelDir
                $parent = Split-Path -Parent $dst
                if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
                Move-Item -LiteralPath $src -Destination $dst -Force
                $moved++
            }
        }
        if ($row.RelCache) {
            $src = Get-SafeChildPath -Root $Root -Relative $row.RelCache
            if (Test-Path -LiteralPath $src) {
                $dst = Get-SafeChildPath -Root $trashRoot -Relative $row.RelCache
                $parent = Split-Path -Parent $dst
                if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
                Move-Item -LiteralPath $src -Destination $dst -Force
                $moved++
            }
        }
    }

    # 清理工作区索引
    $wsPath = Join-Path $Root 'storages\workspace.json'
    $indexChanged = $false
    if (Test-Path -LiteralPath $wsPath) {
        Copy-Item -LiteralPath $wsPath -Destination (Join-Path $trashRoot 'workspace.json.bak') -Force
        $ws = Read-JsonFile -Path $wsPath
        if ($ws) {
            $ids = @($PickedRows | ForEach-Object { $_.Id })
            foreach ($wpProp in $ws.tables.workspaces.PSObject.Properties) {
                $cur = @(Get-Val $wpProp.Value @('sessionIds'))
                $kept = @($cur | Where-Object { $ids -notcontains $_ })
                if ($kept.Count -ne $cur.Count) {
                    $wpProp.Value.sessionIds = $kept
                    $indexChanged = $true
                }
            }
            foreach ($propName in @('archivedSessionIds', 'pinnedSessionIds')) {
                $cur = @(Get-Val $ws.global @($propName))
                $kept = @($cur | Where-Object { $ids -notcontains $_ })
                if ($kept.Count -ne $cur.Count) {
                    $ws.global.$propName = $kept
                    $indexChanged = $true
                }
            }
            if ($indexChanged) {
                $tmp = $wsPath + '.tmp'
                Write-JsonFile -Path $tmp -Value $ws -Depth 20
                $check = Read-JsonFile -Path $tmp
                if (-not $check) { throw '工作区索引写回校验失败，已中止（原文件未改动）' }
                Move-Item -LiteralPath $tmp -Destination $wsPath -Force
            }
        }
    }

    $manifest = [ordered]@{
        createdAt   = (Get-Date).ToString('o')
        profileRoot = $Root
        items       = $manifestItems
    }
    Write-JsonFile -Path (Join-Path $trashRoot 'manifest.json') -Value $manifest -Depth 8

    Write-Host ''
    Write-Host ('  已删除 {0} 个对话（移动了 {1} 项数据）。' -f $PickedRows.Count, $moved) -ForegroundColor Green
    Write-Host ('  回收站目录：{0}' -f $trashRoot) -ForegroundColor DarkGray
    Write-Host '  后悔药：重新打开本工具选 r，可把这一批原样恢复（含侧栏登记）。' -ForegroundColor DarkGray
}

# ------------------------------------------------------------
# 从回收站恢复
# ------------------------------------------------------------
function Invoke-RestoreSessions {
    param([string]$Root)

    $trashDir = Join-Path $Root 'trash'
    if (-not (Test-Path -LiteralPath $trashDir)) {
        Write-Host '  回收站是空的，没有可恢复的批次。' -ForegroundColor Yellow
        return
    }
    $batches = @(Get-ChildItem -LiteralPath $trashDir -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
    if ($batches.Count -eq 0) {
        Write-Host '  回收站是空的，没有可恢复的批次。' -ForegroundColor Yellow
        return
    }

    Write-Host ''
    Write-Host '  回收站里的删除批次（新 → 旧）：' -ForegroundColor Cyan
    $i = 0
    $info = @()
    foreach ($b in $batches) {
        $i++
        $m = $null
        try { $m = Read-JsonFile -Path (Join-Path $b.FullName 'manifest.json') } catch { $m = $null }
        $count = 0
        $titles = @()
        if ($m -and $m.items) { $items = @($m.items); $count = $items.Count; foreach ($it in $items) { $titles += [string]$it.title } }
        $info += [pscustomobject]@{ Index = $i; Dir = $b.FullName; Count = $count; Titles = $titles }
        $short = ($titles | Select-Object -First 3) -join '、'
        if ($titles.Count -gt 3) { $short += ' …' }
        Write-Host ('   {0,2}) {1}  {2} 个对话  {3}' -f $i, $b.Name, $count, $short)
    }

    $pick = Read-Host '  输入要恢复的批次编号（直接回车取消）'
    if ([string]::IsNullOrWhiteSpace($pick)) { return }
    if ($pick -notmatch '^\s*\d+\s*$') { Write-Host '  输入无效。' -ForegroundColor Yellow; return }
    $n = [int]$pick
    if ($n -lt 1 -or $n -gt $info.Count) { Write-Host '  编号超出范围。' -ForegroundColor Yellow; return }
    $chosen = $info[$n - 1]

    $m = Read-JsonFile -Path (Join-Path $chosen.Dir 'manifest.json')
    if (-not $m -or -not $m.items) { Write-Host '  这个批次缺少清单文件，无法恢复。' -ForegroundColor Red; return }
    $items = @($m.items)

    if (-not (Confirm-AppClosed)) { return }

    $restored = 0
    $ids = @()
    foreach ($it in $items) {
        $ids += [string]$it.sessionId
        if ($it.relDir) {
            $src = Get-SafeChildPath -Root $chosen.Dir -Relative $it.relDir
            $dst = Get-SafeChildPath -Root $Root -Relative $it.relDir
            if (Test-Path -LiteralPath $src) {
                if (Test-Path -LiteralPath $dst) {
                    Write-Host ('  跳过（目标已存在）：{0}' -f $it.relDir) -ForegroundColor DarkYellow
                } else {
                    $parent = Split-Path -Parent $dst
                    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
                    Move-Item -LiteralPath $src -Destination $dst -Force
                    $restored++
                }
            }
        }
        if ($it.relCache) {
            $src = Get-SafeChildPath -Root $chosen.Dir -Relative $it.relCache
            $dst = Get-SafeChildPath -Root $Root -Relative $it.relCache
            if (Test-Path -LiteralPath $src) {
                if (Test-Path -LiteralPath $dst) {
                    Write-Host ('  跳过（目标已存在）：{0}' -f $it.relCache) -ForegroundColor DarkYellow
                } else {
                    $parent = Split-Path -Parent $dst
                    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
                    Move-Item -LiteralPath $src -Destination $dst -Force
                    $restored++
                }
            }
        }
    }

    # 恢复侧栏登记
    $wsPath = Join-Path $Root 'storages\workspace.json'
    if (Test-Path -LiteralPath $wsPath) {
        $ws = Read-JsonFile -Path $wsPath
        if ($ws) {
            $changed = $false
            foreach ($it in $items) {
                $sid = [string]$it.sessionId
                foreach ($wid in @($it.workspaceIds)) {
                    $wp = Get-Val $ws.tables.workspaces @([string]$wid)
                    if (-not $wp) { continue }
                    $cur = @(Get-Val $wp @('sessionIds'))
                    if ($cur -notcontains $sid) {
                        $wp.sessionIds = @($cur + $sid)
                        $changed = $true
                    }
                }
                if ($it.archived) {
                    $cur = @(Get-Val $ws.global @('archivedSessionIds'))
                    if ($cur -notcontains $sid) { $ws.global.archivedSessionIds = @($cur + $sid); $changed = $true }
                }
                if ($it.pinned) {
                    $cur = @(Get-Val $ws.global @('pinnedSessionIds'))
                    if ($cur -notcontains $sid) { $ws.global.pinnedSessionIds = @($cur + $sid); $changed = $true }
                }
            }
            if ($changed) {
                $tmp = $wsPath + '.tmp'
                Write-JsonFile -Path $tmp -Value $ws -Depth 20
                $check = Read-JsonFile -Path $tmp
                if (-not $check) { throw '工作区索引写回校验失败，已中止（原文件未改动）' }
                Move-Item -LiteralPath $tmp -Destination $wsPath -Force
            }
        }
    }

    Write-Host ''
    Write-Host ('  已从批次 {0} 恢复 {1} 个对话（移动了 {2} 项数据）。' -f $chosen.Dir.Split('\')[-1], $items.Count, $restored) -ForegroundColor Green
    Write-Host '  重新打开 DSH 后它们会回到侧栏。' -ForegroundColor DarkGray
}

# ------------------------------------------------------------
# 主流程
# ------------------------------------------------------------
function Start-CleanupTool {
    $root = $script:ProfileRoot
    $dryRun = ($env:DSH_DRYRUN -eq '1')
    try { Clear-Host } catch { }

    Write-Host ''
    Write-Host '  ============================================================' -ForegroundColor DarkCyan
    Write-Host '   DeepSeek Harness 会话清理器' -ForegroundColor Cyan
    Write-Host ('   数据目录：{0}' -f $root) -ForegroundColor DarkGray
    if ($dryRun) {
        Write-Host '   模式：dry-run（只预览，不会关闭 DSH，也不会改动磁盘）' -ForegroundColor Yellow
    }
    Write-Host '  ============================================================' -ForegroundColor DarkCyan

    if (-not (Test-Path -LiteralPath $root)) {
        Write-Host ''
        Write-Host ('  找不到 DSH 数据目录：{0}' -f $root) -ForegroundColor Red
        Write-Host '  请确认 DeepSeek Harness 已至少启动过一次。' -ForegroundColor Yellow
        Wait-Exit
        return
    }
    if (-not $script:AppExe) { $script:AppExe = Find-DshAppExe }

    while ($true) {
        $wsPath = Join-Path $root 'storages\workspace.json'
        $wsState = $null
        if (Test-Path -LiteralPath $wsPath) {
            try { $wsState = Read-JsonFile -Path $wsPath } catch { $wsState = $null }
        }

        $rows = @(Get-SessionCatalog -Root $root -WorkspaceState $wsState)
        if ($rows.Count -eq 0) {
            Write-Host ''
            Write-Host '  没有找到任何对话，没什么可删的。' -ForegroundColor Yellow
            Wait-Exit
            return
        }

        $totalBytes = [double]0
        foreach ($r in $rows) { $totalBytes += $r.SizeBytes }

        Write-Host ''
        Write-Host ('  共 {0} 个对话，占用 {1}。' -f $rows.Count, (Format-Size $totalBytes)) -ForegroundColor Gray
        Write-Host ''

        $width = Get-ConsoleWidth
        if ($width -gt 130) { $width = 130 }
        Show-SessionCatalog -Rows $rows -TotalWidth $width

        Write-Host ''
        Write-Host '  状态：归档 = 侧栏已隐藏但文件仍在磁盘；置顶 = 顶栏固定；隐藏 = 不在任何工作区（多为子代理会话，侧栏看不到）' -ForegroundColor DarkGray
        Write-Host '  多选写法：1 3 5   或   1-3   或   1,3,5' -ForegroundColor DarkGray
        Write-Host '  q = 退出    r = 从回收站恢复    0 = 刷新列表' -ForegroundColor DarkGray
        Write-Host ''

        $answer = Read-Host '  请输入要删除的对话编号'
        if ($null -eq $answer) { return }
        $answer = $answer.Trim()
        if ($answer -eq '') { continue }
        if ($answer -match '^[qQ]') { return }
        if ($answer -match '^[rR]') {
            if ($dryRun) { Write-Host '  dry-run 模式只预览删除，不执行恢复。' -ForegroundColor Yellow; continue }
            if (Confirm-AppClosed) { Invoke-RestoreSessions -Root $root }
            continue
        }
        if ($answer -eq '0') { continue }

        $picked = ConvertTo-Selection -Text $answer -Max $rows.Count
        if ($null -eq $picked) {
            Write-Host '  输入无法识别，请按上面的格式重输。' -ForegroundColor Yellow
            Start-Sleep -Milliseconds 600
            continue
        }

        $pickedRows = @()
        foreach ($n in $picked) { $pickedRows += $rows[$n - 1] }

        Write-Host ''
        Write-Host '  将要彻底删除以下对话：' -ForegroundColor Yellow
        foreach ($r in $pickedRows) {
            Write-Host ('    - [{0}] {1}' -f $r.Id, $r.Title) -ForegroundColor Yellow
        }
        Write-Host ('  会移入 {0}\trash ，删除后可用 r 恢复。' -f $root) -ForegroundColor DarkGray
        $ok = Read-Host '  确认删除？输入 y 确认，其他键取消'
        if ($ok -notmatch '^\s*[yY]') {
            Write-Host '  已取消。' -ForegroundColor DarkGray
            Start-Sleep -Milliseconds 500
            continue
        }

        if (-not $dryRun) {
            if (-not (Confirm-AppClosed)) { return }
        }
        Invoke-DeleteSessions -Root $root -Rows $rows -PickedRows $pickedRows -DryRun:$dryRun
        break
    }

    if ($script:AppWasRunning -and -not $dryRun) {
        $ans = Read-Host '  是否重新打开 DeepSeek Harness？(y/n)'
        if ($ans -match '^\s*[yY]') {
            try {
                if (Test-Path -LiteralPath $script:AppExe) {
                    Start-Process -FilePath $script:AppExe
                    Write-Host '  已启动 DSH。' -ForegroundColor Green
                } else {
                    Write-Host '  找不到 DSH 可执行文件，请手动从桌面图标打开。' -ForegroundColor Yellow
                }
            } catch {
                Write-Host '  启动失败，请手动从桌面图标打开。' -ForegroundColor Yellow
            }
        }
    }

    Wait-Exit
}

# 测试/库模式：只加载函数，不启动交互界面（app-close-test.ps1 用）
if ($env:DSH_TOOL_LIB_ONLY -eq '1') { return }

try {
    Start-CleanupTool
} catch {
    Write-Host ''
    Write-Host ('  出错：{0}' -f $_.Exception.Message) -ForegroundColor Red
    Write-Host ('  位置：{0}' -f $_.InvocationInfo.ScriptName) -ForegroundColor DarkGray
    Write-Host ('  行号：{0}' -f $_.InvocationInfo.ScriptLineNumber) -ForegroundColor DarkGray
    Wait-Exit
    exit 1
}
