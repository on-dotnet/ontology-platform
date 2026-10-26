<#
.SYNOPSIS
默认只读的项目资源盘点；不提供Apply或删除入口，不读取环境、凭证或卷内容。
#>
[CmdletBinding()]
param(
    [string]$Root = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),
    [switch]$IncludeDocker
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Root = [IO.Path]::GetFullPath($Root)
$commands = [Collections.Generic.List[object]]::new()
function Read-ResourceCommand {
    param([string]$Executable, [string[]]$Arguments, [string]$Directory = $Root)
    $info = [Diagnostics.ProcessStartInfo]::new($Executable)
    $info.WorkingDirectory = $Directory
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $info
    try {
        $null = $process.Start()
        $outputRead = $process.StandardOutput.ReadToEndAsync()
        $errorRead = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $output = $outputRead.GetAwaiter().GetResult()
        $null = $errorRead.GetAwaiter().GetResult()
        $commands.Add(@{ executable = $Executable; arguments = $Arguments; exitCode = $process.ExitCode })
        return @{ exitCode = $process.ExitCode; text = $output }
    } catch { return @{ exitCode = -1; text = ''; reason = 'Unavailable command or access denied; raw stderr suppressed.' } }
    finally { $process.Dispose() }
}
function Read-ResourceGit {
    param([string[]]$Arguments, [string]$Directory = $Root)
    return Read-ResourceCommand 'git' (@('--no-optional-locks', '-C', $Directory, '-c', 'color.ui=false', '-c', 'core.quotePath=false') + $Arguments) $Directory
}
$mainResult = Read-ResourceGit @('rev-parse', '--verify', 'origin/main')
if ($mainResult.exitCode -ne 0) { throw 'Git origin/main unavailable; no resource changes performed.' }
$main = $mainResult.text.Trim()
$refs = [Collections.Generic.List[object]]::new()
$refResult = Read-ResourceGit @('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads', 'refs/remotes/origin')
if ($refResult.exitCode -ne 0) { throw 'Git refs unavailable; no resource changes performed.' }
foreach ($line in $refResult.text.Split("`n", [StringSplitOptions]::RemoveEmptyEntries)) {
    $ref, $tip = $line.Trim().Split(' ', 2)
    if ($ref -ceq 'refs/remotes/origin/HEAD') { continue }
    $ancestor = Read-ResourceGit @('merge-base', '--is-ancestor', $tip, $main)
    $refs.Add([ordered]@{ ref = $ref; tip = $tip; ancestorExitCode = $ancestor.exitCode; classification = $(if ($ancestor.exitCode -eq 0) { 'KEEP' } else { 'AMBIGUOUS' }); action = 'DEFERRED'; reason = 'Cross-machine/old-chat activity and acceptance must be reviewed; ancestry alone is insufficient.' })
}
$trees = [Collections.Generic.List[object]]::new()
$treeResult = Read-ResourceGit @('worktree', 'list', '--porcelain')
if ($treeResult.exitCode -ne 0) { throw 'Git worktree metadata unavailable; no resource changes performed.' }
foreach ($block in ($treeResult.text.Trim() -split "\r?\n\r?\n")) {
    $record = @{}
    foreach ($line in ($block -split "\r?\n")) {
        $parts = $line.Split(' ', 2)
        $record[$parts[0]] = if ($parts.Count -eq 2) { $parts[1] } else { $true }
    }
    $path = $record.worktree
    $exists = Test-Path -LiteralPath $path -PathType Container
    $state = if ($exists) { Read-ResourceGit @('status', '--porcelain=v1', '-uall') $path } else { @{ exitCode = -1; text = '' } }
    $groups = @{}
    if ($exists) {
        # 仅路径与分类计数，忽略文件字节不读取，链接不递归。
        $ignored = Read-ResourceGit @('ls-files', '--others', '--ignored', '--exclude-standard', '-z') $path
        foreach ($name in $ignored.text.Split([char]0, [StringSplitOptions]::RemoveEmptyEntries)) {
            $top = $name.Split('/')[0]
            if (-not $groups.ContainsKey($top)) { $groups[$top] = 0 }; $groups[$top]++
        }
    }
    $trees.Add([ordered]@{ path = $path; metadata = $record; exists = $exists; statusExitCode = $state.exitCode; statusPaths = @($state.text.Split("`n", [StringSplitOptions]::RemoveEmptyEntries)); ignoredTopCounts = $groups; classification = 'KEEP'; action = 'DEFERRED'; reason = 'No automatic deletion; validate active/locked/ignored private data and external references first.' })
}
$zips = [Collections.Generic.List[object]]::new()
$directory = Join-Path $Root 'artifacts/reviews'
if ((Test-Path -LiteralPath $directory) -and ((Get-Item -LiteralPath $directory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
    foreach ($file in Get-ChildItem -LiteralPath $directory -Filter '*.zip' -File) {
        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
        $zips.Add(@{ name = $file.Name; sizeBytes = $file.Length; sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant(); classification = 'KEEP'; action = 'DEFERRED'; reason = 'Reopen and prove source/unique evidence recoverability before any exact-ID cleanup.' })
    }
}
$docker = [ordered]@{ status = 'NOT_RUN'; reason = 'Use IncludeDocker for read-only allowlisted metadata. No environment or volume contents are read.' }
if ($IncludeDocker) {
    $queries = [ordered]@{
        containers = @('ps', '-a', '--format', '{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Label "com.docker.compose.project"}}')
        volumes = @('volume', 'ls', '--format', '{{.Name}}\t{{.Driver}}\t{{.Label "com.docker.compose.project"}}')
        networks = @('network', 'ls', '--format', '{{.ID}}\t{{.Name}}\t{{.Driver}}\t{{.Label "com.docker.compose.project"}}')
        capacity = @('system', 'df', '--format', '{{json .}}')
        detailedCapacity = @('system', 'df', '-v')
    }
    $docker = [ordered]@{ status = 'OBSERVED'; policy = 'KEEP / DEFERRED: ownership, private data and active references require independent review; reclaimable is not authorization.'; queries = [ordered]@{} }
    foreach ($key in $queries.Keys) {
        $result = Read-ResourceCommand 'docker' $queries[$key]
        $docker.queries[$key] = $result
        if ($result.exitCode -ne 0) { $docker.status = 'BLOCKED'; $docker.reason = 'Docker metadata unavailable or access denied; resources NOT_VERIFIED.' }
    }
}
[ordered]@{
    schemaVersion = 1; mode = 'READ_ONLY'; observedAt = [DateTime]::UtcNow.ToString('o'); originMain = $main
    refs = $refs.ToArray(); worktrees = $trees.ToArray(); reviewPackages = $zips.ToArray(); docker = $docker
    commands = $commands.ToArray(); mutations = @(); reclaimedBytes = 0
    limitations = 'No cleanup executor; no active-chat or cross-machine proof; no ignored file contents; Git paths only outside current tree; no volume contents; no whole-user-directory scan.'
} | ConvertTo-Json -Depth 16
