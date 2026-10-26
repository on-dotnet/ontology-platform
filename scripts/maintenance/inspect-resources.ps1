<#
.SYNOPSIS
默认只读资源盘点；按已提交精确审批清单与实际身份分类，不执行删除。
#>
[CmdletBinding()]
param(
    [string]$Root = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),
    [switch]$IncludeDocker,
    [string]$ApprovalPath
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
$topLevel = Read-ResourceGit @('rev-parse', '--show-toplevel')
if ($topLevel.exitCode -ne 0) { throw 'Actual Git root unavailable; no resource changes performed.' }
$Root = $topLevel.text.Trim()
$approval = $null
if (-not $ApprovalPath) { $ApprovalPath = Join-Path $Root 'docs/evidence/PRE-G3-CLEANUP-FIX-002/approved-candidates.json' }
if (Test-Path -LiteralPath $ApprovalPath -PathType Leaf) {
    $approval = Get-Content -LiteralPath $ApprovalPath -Raw | ConvertFrom-Json -AsHashtable
    if ($approval.project -cne 'on-dotnet/ontology-platform' -or $approval.schemaVersion -ne 1) { throw 'Invalid resource approval registry identity.' }
}
function Find-Approval {
    param([string]$Kind, [string]$Target)
    if ($null -eq $approval) { return $null }
    return @($approval.operations | Where-Object { $_.type -ceq $Kind -and $_.target -ceq $Target }) | Select-Object -First 1
}
function Test-Overlap {
    param([string]$Left, [string]$Right)
    $leftPath = [IO.Path]::GetFullPath($Left).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $rightPath = [IO.Path]::GetFullPath($Right).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $comparison = if ($IsWindows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
    return $leftPath.Equals($rightPath, $comparison) -or $leftPath.StartsWith($rightPath + [IO.Path]::DirectorySeparatorChar, $comparison) -or $rightPath.StartsWith($leftPath + [IO.Path]::DirectorySeparatorChar, $comparison)
}
function Protect-Path {
    param([string]$Path)
    $paths = @($Root, $primaryRoot)
    if ($null -ne $approval) { $paths += @($approval.protectedWorktrees) + @($approval.keep | Where-Object { [IO.Path]::IsPathRooted($_) }) }
    foreach ($protected in $paths) { if (Test-Overlap $Path $protected) { return $true } }
    return $false
}
function Read-DockerApproval {
    param([string]$Kind, [string]$Target, $Expected)
    # 使用同一个只读白名单metadata API，省略环境、BuildArgs及卷内容；Python无第三方依赖。
    $python = if ($IsWindows) { 'python' } else { 'python3' }
    $module = Join-Path $PSScriptRoot 'cleanup_resources.py'
    $program = @'
import importlib.util,json,sys
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('cleanup_readonly',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
kind,target=sys.argv[2:4];e=json.loads(sys.argv[4]);a=m.safe_docker_snapshot(kind,target)
if kind=='docker-container': ok=a==dict(Id=target,Name=e['expectedName'],Image=e['expectedImage'],State=e['expectedState'],Mounts=e['expectedMounts'])
elif kind=='docker-volume': ok=a==dict(Name=target,Driver=e['expectedDriver'],CreatedAt=e['expectedCreatedAt'])
elif kind=='docker-image': ok=a==dict(Id=target,RepoTags=sorted(e['expectedTags']))
else: ok=a==e['historySnapshot']
print(json.dumps({'matches':ok,'snapshot':a}))
'@
    $result = Read-ResourceCommand $python @('-c', $program, $module, $Kind, $Target, ($Expected | ConvertTo-Json -Depth 12 -Compress))
    if ($result.exitCode -ne 0) { return @{ matches = $false; reason = 'Exact metadata could not be read; no deletion eligibility.' } }
    return $result.text | ConvertFrom-Json -AsHashtable
}
$mainResult = Read-ResourceGit @('rev-parse', '--verify', 'origin/main')
if ($mainResult.exitCode -ne 0) { throw 'Git origin/main unavailable; no resource changes performed.' }
$main = $mainResult.text.Trim()
$currentBranch = (Read-ResourceGit @('rev-parse', '--abbrev-ref', 'HEAD')).text.Trim()
$commonResult = Read-ResourceGit @('rev-parse', '--path-format=absolute', '--git-common-dir')
if ($commonResult.exitCode -ne 0) { throw 'Git common metadata unavailable.' }
$common = $commonResult.text.Trim()
$primaryRoot = Split-Path $common -Parent
$treeResult = Read-ResourceGit @('worktree', 'list', '--porcelain')
if ($treeResult.exitCode -ne 0) { throw 'Git worktree metadata unavailable; no resource changes performed.' }
$trees = [Collections.Generic.List[object]]::new()
foreach ($block in ($treeResult.text.Trim() -split "\r?\n\r?\n")) {
    $record = @{}
    foreach ($line in ($block -split "\r?\n")) {
        $parts = $line.Split(' ', 2)
        $record[$parts[0]] = if ($parts.Count -eq 2) { $parts[1] } else { $true }
    }
    $path = $record.worktree
    $exists = Test-Path -LiteralPath $path -PathType Container
    $state = if ($exists) { Read-ResourceGit @('status', '--porcelain=v1', '-uall') $path } else { @{ exitCode = -1; text = '' } }
    $ignoredExit = -1
    $groups = @{}; $ignoredPaths = @(); $privatePaths = @(); $uncovered = @()
    if ($exists) {
        $ignored = Read-ResourceGit @('ls-files', '--others', '--ignored', '--exclude-standard', '-z') $path
        $ignoredExit = $ignored.exitCode
        $ignoredPaths = @($ignored.text.Split([char]0, [StringSplitOptions]::RemoveEmptyEntries))
        foreach ($name in $ignoredPaths) {
            $top = $name.Split('/')[0]
            if (-not $groups.ContainsKey($top)) { $groups[$top] = 0 }; $groups[$top]++
            $publicAsset = $name -ceq 'node_modules/.pnpm/language-subtag-registry@0.3.23/node_modules/language-subtag-registry/data/json/private-use.json'
            if (-not $publicAsset -and ($name -match '(?i)(^|/)(\.env(?:\.|$)|(?:private|secrets?|credentials?)(?:[._-]|$)|\.(?:runtime|ssh|aws)(?:/|$)|auth\.json$)' -or $name -match '(?i)\.(pfx|p12|pem|key|crt|dump|db|sqlite3?)$' -or $name -match '^\.tools/security/')) { $privatePaths += $name }
            $covered = $false
            if ($null -ne $approval) {
                foreach ($cache in @($approval.operations | Where-Object { $_.type -ceq 'cache' -and $_.treeRoot -ceq $path -and $_.expectedTip -ceq $record.HEAD })) {
                    $file = [IO.Path]::GetFullPath((Join-Path $path $name))
                    $cachePath = [IO.Path]::GetFullPath($cache.target)
                    if ($file -ceq $cachePath -or $file.StartsWith($cachePath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::Ordinal)) { $covered = $true; break }
                }
            }
            if (-not $covered) { $uncovered += $name }
        }
    }
    $approved = Find-Approval 'worktree' $path
    $classification = 'KEEP'; $reason = 'Exact retained private-data/current-task/unintegrated source boundary; see resource-specific approval and Git classification.'
    if ($null -ne $approved -and -not (Protect-Path $path)) {
        $sameCommon = if ($exists) { (Read-ResourceGit @('rev-parse', '--path-format=absolute', '--git-common-dir') $path).text.Trim() -ceq $common } else { $false }
        if ($exists -and $sameCommon -and $ignoredExit -eq 0 -and $state.exitCode -eq 0 -and -not $state.text -and -not $record.ContainsKey('locked') -and -not $record.ContainsKey('prunable') -and $approved.expectedTip -ceq $record.HEAD -and ('refs/heads/' + $approved.expectedBranch) -ceq $record.branch -and $privatePaths.Count -eq 0 -and $uncovered.Count -eq 0) { $classification = 'SAFE_CANDIDATE'; $reason = 'Closed task, exact clean reviewed Head and every ignored path covered by precise approved regenerable cache; Apply revalidates identities and fingerprints.' }
        else { $classification = 'AMBIGUOUS'; $reason = 'Actual missing/changed/dirty/locked/cross-project tree or private/unapproved ignored paths prevent safe classification.' }
    }
    $trees.Add([ordered]@{ path = $path; metadata = $record; exists = $exists; statusExitCode = $state.exitCode; ignoredExitCode = $ignoredExit; statusPaths = @($state.text.Split("`n", [StringSplitOptions]::RemoveEmptyEntries)); ignoredTopCounts = $groups; blockedPrivateIgnoredPaths = $privatePaths; uncoveredIgnoredCount = $uncovered.Count; classification = $classification; action = $(if ($classification -ceq 'SAFE_CANDIDATE') { 'REVALIDATE_APPROVED_CACHE_THEN_APPLY' } else { 'RETAIN' }); reason = $reason })
}
$refs = [Collections.Generic.List[object]]::new()
$refResult = Read-ResourceGit @('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads', 'refs/remotes/origin')
if ($refResult.exitCode -ne 0) { throw 'Git refs unavailable; no resource changes performed.' }
foreach ($line in $refResult.text.Split("`n", [StringSplitOptions]::RemoveEmptyEntries)) {
    $ref, $tip = $line.Trim().Split(' ', 2)
    if ($ref -ceq 'refs/remotes/origin/HEAD') { continue }
    $ancestor = Read-ResourceGit @('merge-base', '--is-ancestor', $tip, $main)
    $name = if ($ref.StartsWith('refs/heads/')) { $ref.Substring(11) } else { $ref.Substring(20) }
    $kind = if ($ref.StartsWith('refs/heads/')) { 'git-local-branch' } else { 'git-remote-branch' }
    $approved = Find-Approval $kind $name
    $attached = @($trees | Where-Object { $_.metadata.ContainsKey('branch') -and $_.metadata.branch -ceq ('refs/heads/' + $name) })
    $attachedUnsafe = @($attached | Where-Object { $_.classification -cne 'SAFE_CANDIDATE' }).Count -gt 0
    $classification = if ($ancestor.exitCode -eq 0) { 'KEEP' } else { 'AMBIGUOUS' }
    $reason = 'Exact ref lacks a reviewed closed-resource ancestor approval; nonancestor refs require explicit patch/recovery review, no force deletion.'
    if ($name -ceq 'main' -or $name -ceq $currentBranch -or ($null -ne $approval -and $name -cin $approval.keep) -or $attachedUnsafe) { $classification = 'KEEP'; $reason = 'Current/main/keep ref or associated protected/locked/private/changed worktree; removal protection propagates to local and remote ref.' }
    elseif ($null -ne $approved) {
        if ($ancestor.exitCode -eq 0 -and $approved.expectedTip -ceq $tip) { $classification = 'SAFE_CANDIDATE'; $reason = 'Closed task, exact reviewed tip, actual ancestry and eligible attached-tree state match; Apply must recheck PRs and live tip with atomic delete lease.' }
        else { $classification = 'AMBIGUOUS'; $reason = 'Reviewed ref tip/ancestry changed; regenerate exact reviewed whitelist.' }
    }
    $refs.Add([ordered]@{ ref = $ref; tip = $tip; ancestorExitCode = $ancestor.exitCode; classification = $classification; action = $(if ($classification -ceq 'SAFE_CANDIDATE') { 'REVALIDATE_APPLY' } else { 'RETAIN' }); reason = $reason })
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
        containers = @('ps', '-a', '--no-trunc', '--format', '{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Label "com.docker.compose.project"}}')
        volumes = @('volume', 'ls', '--format', '{{.Name}}\t{{.Driver}}\t{{.Label "com.docker.compose.project"}}')
        images = @('image', 'ls', '--no-trunc', '--format', '{{.ID}}\t{{.Repository}}:{{.Tag}}')
        history = @('buildx', 'history', 'ls', '--builder', 'desktop-linux', '--format', '{{.Ref}}')
        networks = @('network', 'ls', '--format', '{{.ID}}\t{{.Name}}\t{{.Driver}}\t{{.Label "com.docker.compose.project"}}')
        capacity = @('system', 'df', '--format', '{{json .}}')
        detailedCapacity = @('system', 'df', '-v')
    }
    $docker = [ordered]@{ status = 'OBSERVED'; policy = 'Classify exact reviewed identities below; safe candidates require guarded Apply, retained resources have concrete private/recovery/shared ownership facts. Reclaimable alone is not authority.'; queries = [ordered]@{} }
    foreach ($key in $queries.Keys) {
        $result = Read-ResourceCommand 'docker' $queries[$key]
        $docker.queries[$key] = $result
        if ($result.exitCode -ne 0) { $docker.status = 'BLOCKED'; $docker.reason = 'Docker metadata unavailable or access denied; resources NOT_VERIFIED.' }
    }
    $decisions = [Collections.Generic.List[object]]::new()
    foreach ($pair in @(@('containers','docker-container'),@('volumes','docker-volume'),@('images','docker-image'),@('history','docker-history'))) {
        $seenTargets = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        foreach ($line in $docker.queries[$pair[0]].text.Split("`n", [StringSplitOptions]::RemoveEmptyEntries)) {
            $target = ($line -split "`t")[0]
            if ($pair[1] -ceq 'docker-history') { $target = $target.Split('/')[-1] }
            if (-not $seenTargets.Add($target)) { continue }
            $approved = Find-Approval $pair[1] $target
            $classification = 'KEEP'; $reason = 'Exact G2 private runtime/PFX recovery binding, pinned dependency, or resource not in project-reviewed deletion whitelist.'
            if ($null -ne $approved -and ($null -eq $approval -or $target -cnotin $approval.keep)) {
                $actual = Read-DockerApproval $pair[1] $target $approved
                if ($actual.matches) { $classification = 'SAFE_CANDIDATE'; $reason = 'Actual identity/version equals exact closed synthetic project resource approval; guarded Apply still verifies no active references.' }
                else { $classification = 'AMBIGUOUS'; $reason = 'Actual approved metadata changed or could not be verified; no Apply permitted.' }
            }
            $decisions.Add(@{ type = $pair[1]; target = $target; classification = $classification; reason = $reason })
        }
    }
    $docker.decisions = $decisions.ToArray()

}
[ordered]@{
    schemaVersion = 1; mode = 'READ_ONLY'; observedAt = [DateTime]::UtcNow.ToString('o'); originMain = $main
    refs = $refs.ToArray(); worktrees = $trees.ToArray(); reviewPackages = $zips.ToArray(); docker = $docker
    commands = $commands.ToArray(); mutations = @(); reclaimedBytes = 0
    approvalRegistry = $(if ($null -ne $approval) { $ApprovalPath } else { $null })
    limitations = 'Read-only classification is a recommendation; separate cleanup-resources Apply must validate committed evidence, identities, expiry, protected data, PRs and references. Ignored/private bytes and volumes not read; no whole-user-directory scan.'
} | ConvertTo-Json -Depth 16
