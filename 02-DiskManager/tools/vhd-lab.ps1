param(
    [ValidateSet('Create', 'Attach', 'Detach', 'Delete')]
    [string]$Action = 'Create'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$lab = Join-Path $root 'out\vhd'
New-Item -ItemType Directory -Force -Path $lab | Out-Null
$tail = Join-Path $lab 'tail.vhdx'
$notail = Join-Path $lab 'notail.vhdx'

function Write-Ascii([string]$path, [string[]]$lines) {
    [IO.File]::WriteAllText($path, (($lines -join "`r`n") + "`r`n"), [Text.Encoding]::ASCII)
}

function Run-DiskPart([string]$name, [string[]]$lines) {
    $script = Join-Path $lab ($name + '.txt')
    $log = Join-Path $lab ($name + '.log')
    Write-Ascii $script $lines
    $process = Start-Process -FilePath 'diskpart.exe' -ArgumentList @('/s', $script) -NoNewWindow -Wait -PassThru -RedirectStandardOutput $log
    $text = [IO.File]::ReadAllText($log, [Text.Encoding]::Default)
    Write-Host $text
    if ($process.ExitCode -ne 0) { throw "diskpart $name failed with $($process.ExitCode)" }
}

$detachLines = @()
foreach ($file in @($tail, $notail)) {
    if (Test-Path $file) {
        $detachLines += "select vdisk file=`"$file`""
        $detachLines += "detach vdisk noerr"
    }
}

switch ($Action) {
    'Detach' {
        if ($detachLines.Count -gt 0) {
            $detachLines += 'exit'
            Run-DiskPart 'detach' $detachLines
        }
        break
    }
    'Delete' {
        $lines = @()
        if ($detachLines.Count -gt 0) { $lines += $detachLines }
        $lines += 'exit'
        if ($lines.Count -gt 1) { Run-DiskPart 'delete-detach' $lines }
        foreach ($file in @($tail, $notail)) {
            if (Test-Path $file) { Remove-Item $file -Force }
        }
        Write-Host 'VHD lab deleted'
        break
    }
    'Create' {
        if ($detachLines.Count -gt 0) {
            $lines = @()
            $lines += $detachLines
            $lines += 'exit'
            Run-DiskPart 'create-detach' $lines
        }
        foreach ($file in @($tail, $notail)) {
            if (Test-Path $file) { Remove-Item $file -Force }
        }

        Run-DiskPart 'create-tail' @(
            "create vdisk file=`"$tail`" maximum=9216 type=expandable",
            "select vdisk file=`"$tail`"",
            'attach vdisk',
            'convert gpt',
            'create partition primary size=3072',
            'format fs=ntfs quick label=CFAKE',
            'assign letter=V',
            'create partition primary size=4096',
            'format fs=ntfs quick label=DFAKE',
            'assign letter=W',
            'exit'
        )

        Run-DiskPart 'create-notail' @(
            "create vdisk file=`"$notail`" maximum=8192 type=expandable",
            "select vdisk file=`"$notail`"",
            'attach vdisk',
            'convert gpt',
            'create partition primary size=2048',
            'format fs=ntfs quick label=CFAKE2',
            'assign letter=X',
            'create partition primary size=6000',
            'format fs=ntfs quick label=DFAKE2',
            'assign letter=Y',
            'exit'
        )
        break
    }
    'Attach' {
        if (-not (Test-Path $tail) -or -not (Test-Path $notail)) { throw 'VHD files missing; run Create first' }
        Run-DiskPart 'attach' @(
            "select vdisk file=`"$tail`"",
            'attach vdisk',
            "select vdisk file=`"$notail`"",
            'attach vdisk',
            'exit'
        )
        break
    }
}

Get-Disk | Where-Object { $_.FriendlyName -like '*Virtual*' } |
    Select-Object Number, FriendlyName, PartitionStyle, @{n='SizeGB';e={[math]::Round($_.Size/1GB,2)}} |
    Format-Table -AutoSize
Get-Volume | Where-Object { $_.DriveLetter -in 'V','W','X','Y' } |
    Select-Object DriveLetter, FileSystemLabel, @{n='SizeGB';e={[math]::Round($_.Size/1GB,2)}}, @{n='FreeGB';e={[math]::Round($_.SizeRemaining/1GB,2)}} |
    Format-Table -AutoSize
