# 造一个假的 DSH 数据目录，用于测试清理工具（绝不碰真实档案）。
# 用法： powershell -NoProfile -ExecutionPolicy Bypass -File make-fixture.ps1 [-Root D:\dsh\work\dsh-tool-test\profile]

param(
    [string]$Root = (Join-Path $PSScriptRoot 'profile')
)

$ErrorActionPreference = 'Stop'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if (Test-Path -LiteralPath $Root) { Remove-Item -LiteralPath $Root -Recurse -Force }
New-Item -ItemType Directory -Path $Root -Force | Out-Null

$sessionsRoot = Join-Path $Root 'sessions'
$cacheDir     = Join-Path $Root 'storages\session_projcache\sessions'
$wsPath       = Join-Path $Root 'storages\workspace.json'
foreach ($d in @($sessionsRoot, $cacheDir, (Join-Path $Root 'storages'))) {
    if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

$now = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()

function New-SessionFixture {
    param(
        [string]$WorkspaceDirKey,
        [string]$Id,
        [string]$Title,
        [long]$LastPromptAt,
        [int]$PayloadBytes = 4096,
        [switch]$SkipCache,
        [string]$Cwd = 'D:\dsh'
    )
    $dir = Join-Path (Join-Path $sessionsRoot $WorkspaceDirKey) $Id
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $bytes = New-Object byte[] $PayloadBytes
    (New-Object Random 7).NextBytes($bytes)
    [IO.File]::WriteAllBytes((Join-Path $dir 'session.v4.jsonl.zstd'), $bytes)

    if (-not $SkipCache) {
        $rec = [ordered]@{
            version = 7
            record  = [ordered]@{
                identity = [ordered]@{ formatVersion = 4; createdAt = ($LastPromptAt - 60000); cwd = $Cwd; isSeeded = $false; inheritedEventCount = 0 }
                rows     = [ordered]@{
                    title                = [ordered]@{ ver = 1; seq = 50; val = $Title }
                    sessionListMetadata  = [ordered]@{ ver = 1; seq = 50; val = [ordered]@{ blank = $false; lastPromptAt = $LastPromptAt } }
                }
            }
        }
        $json = $rec | ConvertTo-Json -Depth 10
        [IO.File]::WriteAllText((Join-Path $cacheDir ('{0}.json' -f $Id)), $json, $utf8NoBom)
    }
}

$wsA = 'aaaaaaaa-1111-2222-3333-444444444444'
$wsB = 'bbbbbbbb-1111-2222-3333-444444444444'

# s1: 普通对话（最近活动最新）
New-SessionFixture -WorkspaceDirKey '--D-dsh--' -Id 'session-11111111-1111-1111-1111-111111111111' -Title '怎么删掉某个窗口（中文标题测试）' -LastPromptAt ($now - 600000)
# s2: 已归档
New-SessionFixture -WorkspaceDirKey '--D-dsh--' -Id 'session-22222222-2222-2222-2222-222222222222' -Title '归档掉的老对话' -LastPromptAt ($now - 3600000)
# s3: 已置顶
New-SessionFixture -WorkspaceDirKey '--D-dsh--' -Id 'session-33333333-3333-3333-3333-333333333333' -Title '置顶的对话：写脚本' -LastPromptAt ($now - 7200000)
# s4: 另一个工作区
New-SessionFixture -WorkspaceDirKey '--D-work-proj--' -Id 'session-44444444-4444-4444-4444-444444444444' -Title '课程作业：第 3 章习题' -LastPromptAt ($now - 1800000) -Cwd 'D:\work\proj'
# s5: 子代理会话：没有缓存、不在任何工作区
New-SessionFixture -WorkspaceDirKey '--D-dsh--' -Id 'ffffffff-5555-5555-5555-555555555555' -Title 'x' -LastPromptAt ($now - 300000) -SkipCache
# s6: 缓存损坏的会话
New-SessionFixture -WorkspaceDirKey '--D-dsh--' -Id 'session-66666666-6666-6666-6666-666666666666' -Title 'y' -LastPromptAt ($now - 900000)
[IO.File]::WriteAllText((Join-Path $cacheDir 'session-66666666-6666-6666-6666-666666666666.json'), '{ this is not json', $utf8NoBom)

$wsJson = [ordered]@{
    unit   = [ordered]@{ name = 'workspace'; version = 2 }
    global = [ordered]@{
        initialized        = $true
        workspaceIds       = @($wsA, $wsB)
        archivedSessionIds = @('session-22222222-2222-2222-2222-222222222222')
        pinnedSessionIds   = @('session-33333333-3333-3333-3333-333333333333')
        defaultWorkspaceId = $wsA
    }
    tables = [ordered]@{
        workspaces = [ordered]@{
            $wsA = [ordered]@{
                path       = 'D:\dsh'
                title      = 'dsh'
                sessionIds = @(
                    'session-11111111-1111-1111-1111-111111111111',
                    'session-22222222-2222-2222-2222-222222222222',
                    'session-33333333-3333-3333-3333-333333333333',
                    'session-66666666-6666-6666-6666-666666666666',
                    'session-dead-dead-dead-dead-deaddeaddead'
                )
                createdAt  = '2026-11-14T15:37:42.925Z'
                updatedAt  = '2026-11-16T21:21:16.920Z'
            }
            $wsB = [ordered]@{
                path       = 'D:\work\proj'
                title      = '课程作业'
                sessionIds = @('session-44444444-4444-4444-4444-444444444444')
                createdAt  = '2026-11-15T10:00:00.000Z'
                updatedAt  = '2026-11-15T10:00:00.000Z'
            }
        }
    }
}
[IO.File]::WriteAllText($wsPath, ($wsJson | ConvertTo-Json -Depth 20), $utf8NoBom)

Write-Host ('fixture ready: {0}' -f $Root) -ForegroundColor Green
Write-Host ('  sessions dirs: {0}' -f (Get-ChildItem (Join-Path $sessionsRoot '--D-dsh--') -Directory).Count)
Write-Host ('  cache records: {0}' -f (Get-ChildItem $cacheDir -Filter *.json).Count)
