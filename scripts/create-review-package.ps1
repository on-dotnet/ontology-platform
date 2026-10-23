<#
.SYNOPSIS
从明确的已提交Base/Head生成并重新打开校验一个审查ZIP。
.DESCRIPTION
退出0代表构包和完整性复检通过，不表示任务、产品、CI或安全审计通过。
秘密检查为有限模式检查，不代替人工审查或完整秘密扫描器。
#>
[CmdletBinding()]
param(
    [string]$Root = (Split-Path $PSScriptRoot -Parent),
    [string]$BaseSha,
    [string]$HeadSha,
    [string]$TaskId,
    [ValidateSet('PASS', 'PARTIAL', 'BLOCKED', 'NOT_RUN')][string]$Status,
    [string]$EvidencePath,
    [string]$CiRunId,
    [string]$CiRunUrl,
    [string]$CiCommit,
    [ValidateSet('success', 'failure', 'cancelled', 'timed_out', 'action_required')][string]$CiConclusion,
    [switch]$VerifyOnly,
    [string]$PackagePath
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$script:commands = [Collections.Generic.List[object]]::new()
$script:utf8 = [Text.UTF8Encoding]::new($false)

function Invoke-ReviewGit {
    param([string]$Repository, [string[]]$Arguments, [switch]$AllowFailure)
    $info = [Diagnostics.ProcessStartInfo]::new('git')
    $info.WorkingDirectory = $Repository
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in @('-c', 'core.autocrlf=false', '-c', 'core.quotePath=false') + $Arguments) { $info.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    $buffer = [IO.MemoryStream]::new()
    try {
        $null = $process.Start()
        $errorRead = $process.StandardError.ReadToEndAsync()
        $process.StandardOutput.BaseStream.CopyTo($buffer)
        $process.WaitForExit()
        $null = $errorRead.GetAwaiter().GetResult()
        $exitCode = $process.ExitCode
        $script:commands.Add([ordered]@{ command = 'git ' + ($Arguments -join ' '); exitCode = $exitCode })
        if ($exitCode -ne 0 -and -not $AllowFailure) { throw "GIT_FAILED: $($Arguments[0]); exit=$exitCode; raw output suppressed" }
        $bytes = $buffer.ToArray()
        return @{ Bytes = $bytes; Text = $script:utf8.GetString($bytes); ExitCode = $exitCode }
    } finally { $buffer.Dispose(); $process.Dispose() }
}

function Assert-ReviewPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path.Contains('\') -or $Path -match '(^/|:|[\x00-\x1f\x7f])' -or
        @($Path.Split('/') | Where-Object { $_ -in @('', '.', '..') -or $_.EndsWith('.') -or $_.EndsWith(' ') }).Count -gt 0) {
        throw 'UNSAFE_PATH: archive path rejected; value suppressed'
    }
    $segments = $Path.Split('/')
    foreach ($segment in $segments) {
        if ($segment -match '^(?i:\.git|\.ssh|auth|node_modules|\.next|\.turbo|bin|obj|\.tools|\.cache|cache|caches|models?|\.aws|\.azure|\.nuget|\.vs|TestResults|coverage|artifacts|\.worktrees)$' -or
            ($segment -match '^(?i:\.env)(?:\.|$)' -and $segment -cne '.env.example') -or
            $segment -match '(?i)\.(pfx|p12|pem|key|db|sqlite|sqlite3|dump|bak|onnx|gguf|safetensors|pt|pth|dll|exe|zip|7z|tar|gz|log)$' -or
            $segment -match '^(?i:id_rsa|id_ed25519|credentials|\.npmrc|\.netrc)$') {
            throw 'FORBIDDEN_PATH: credential, environment, cache, binary, model or database member rejected; value suppressed'
        }
    }
    if ($Path -match '(?i)(^|/)\.codex/auth[^/]*($|/)') { throw 'FORBIDDEN_PATH: authentication material rejected' }
}

function Assert-ReviewContent {
    param([byte[]]$Bytes, [string]$Location)
    # 同时检查常见UTF8/UTF16表示；有限模式不能识别所有机密或生产数据。
    $patterns = @(
        '-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        'gh[pousr]_[A-Za-z0-9]{30,}',
        'github_pat_[A-Za-z0-9_]{30,}',
        'AKIA[A-Z0-9]{16}',
        'sk-[A-Za-z0-9_-]{32,}',
        '(?im)^[+\- ]?\s*["'']?(?:password|client_secret|api_key|access_token)["'']?\s*[:=]\s*["'']?(?!\$|<|\{|\[|REPLACE|CHANGEME|example|placeholder|set.locally)[A-Za-z0-9_+/=.-]{8,}'
    )
    foreach ($encoding in @($script:utf8, [Text.Encoding]::Unicode, [Text.Encoding]::BigEndianUnicode)) {
        $text = $encoding.GetString($Bytes)
        foreach ($pattern in $patterns) {
            if ($text -match $pattern) { throw "SECRET_PATTERN: $Location; suspected value suppressed; finite scan only" }
        }
    }
}

function Get-ReviewHash {
    param([byte[]]$Bytes)
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()
}

function Get-ReviewSnapshot {
    param([string]$Repository, [string]$Base, [string]$Head)
    foreach ($sha in @($Base, $Head)) {
        if ($sha -notmatch '^[0-9a-f]{40}$') { throw 'COMMIT_REQUIRED: explicit full lowercase 40-character commit SHA required' }
        $resolved = Invoke-ReviewGit $Repository @('rev-parse', '--verify', "$sha^{commit}")
        if ($resolved.Text.Trim() -cne $sha) { throw 'COMMIT_REQUIRED: SHA must identify a commit directly' }
    }
    $ancestry = Invoke-ReviewGit $Repository @('merge-base', '--is-ancestor', $Base, $Head) -AllowFailure
    if ($ancestry.ExitCode -ne 0) { throw 'ANCESTRY: BaseSha is not an ancestor of HeadSha' }
    $state = Invoke-ReviewGit $Repository @('status', '--porcelain=v1', '--untracked-files=all')
    if ($state.Bytes.Length -ne 0) { throw 'DIRTY_TREE: commit tracked/untracked delivery changes before packaging; file contents suppressed' }
    $ignored = Invoke-ReviewGit $Repository @('ls-files', '--others', '--ignored', '--exclude-standard', '-z')
    $ignoredPaths = @($ignored.Text.Split([char]0, [StringSplitOptions]::RemoveEmptyEntries))
    # 忽略项仅报告路径，不读取其内容；它们不是交付输入。
    $changedPaths = Invoke-ReviewGit $Repository @('diff', '--name-only', '-z', '--no-renames', $Base, $Head, '--')
    foreach ($changedPath in $changedPaths.Text.Split([char]0, [StringSplitOptions]::RemoveEmptyEntries)) { Assert-ReviewPath $changedPath }
    $tree = Invoke-ReviewGit $Repository @('ls-tree', '-r', '-z', $Head)
    $blobs = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
    foreach ($item in $tree.Text.Split([char]0, [StringSplitOptions]::RemoveEmptyEntries)) {
        if ($item -notmatch '^(100644|100755) blob ([0-9a-f]{40})\t(.+)$') { throw 'UNSUPPORTED_TREE: symlink/submodule or unsupported Git entry; no silent omission' }
        $path = $Matches[3]
        Assert-ReviewPath $path
        $blobs.Add($path, $Matches[2])
    }
    $archiveResult = Invoke-ReviewGit $Repository @('archive', '--format=zip', $Head)
    $memory = [IO.MemoryStream]::new($archiveResult.Bytes, $false)
    $archive = [IO.Compression.ZipArchive]::new($memory, [IO.Compression.ZipArchiveMode]::Read)
    $members = [Collections.Generic.Dictionary[string,byte[]]]::new([StringComparer]::Ordinal)
    $mapping = [Collections.Generic.List[object]]::new()
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    try {
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName.EndsWith('/')) { continue }
            $path = $entry.FullName
            Assert-ReviewPath $path
            if (-not $blobs.ContainsKey($path) -or -not $seen.Add($path)) { throw 'SNAPSHOT_MISMATCH: extra or case-colliding Git archive member' }
            $stream = $entry.Open()
            $buffer = [IO.MemoryStream]::new()
            try { $stream.CopyTo($buffer); $bytes = $buffer.ToArray() } finally { $stream.Dispose(); $buffer.Dispose() }
            # 比较原始Git blob，拒绝export-ignore/export-subst造成的遗漏或改写。
            $prefix = $script:utf8.GetBytes("blob $($bytes.Length)`0")
            $blobHash = [Convert]::ToHexString([Security.Cryptography.SHA1]::HashData([byte[]]($prefix + $bytes))).ToLowerInvariant()
            if ($blobHash -cne $blobs[$path]) { throw 'SNAPSHOT_MISMATCH: Git archive content differs from committed blob' }
            Assert-ReviewContent $bytes 'committed source'
            # source保留完整仓库相对结构，确保源码中的文档导航可用；顶层docs/evidence是便捷副本。
            $destinations = @('source/' + $path)
            if ($path.StartsWith('docs/evidence/')) { $destinations += 'evidence/' + $path.Substring(14) }
            elseif ($path.StartsWith('docs/')) { $destinations += $path }
            foreach ($destination in $destinations) {
                Assert-ReviewPath $destination
                $members.Add($destination, $bytes)
                $mapping.Add([ordered]@{ gitPath = $path; archivePath = $destination; sha256 = Get-ReviewHash $bytes })
            }
        }
    } finally { $archive.Dispose(); $memory.Dispose() }
    if ($seen.Count -ne $blobs.Count) { throw 'SNAPSHOT_MISMATCH: git archive omitted tracked delivery; check export-ignore attributes' }
    $diff = Invoke-ReviewGit $Repository @('diff', '--binary', '--full-index', '--no-ext-diff', '--no-textconv', '--no-renames', $Base, $Head, '--')
    Assert-ReviewContent $diff.Bytes 'complete patch including removed lines'
    $changed = Invoke-ReviewGit $Repository @('diff', '--name-status', '--no-renames', $Base, $Head, '--')
    $commits = Invoke-ReviewGit $Repository @('log', '--format=fuller', '--no-decorate', "$Base..$Head")
    Assert-ReviewContent $commits.Bytes 'commit messages'
    $check = Invoke-ReviewGit $Repository @('diff', '--check', $Base, $Head, '--') -AllowFailure
    $members.Add('git/diff.patch', $diff.Bytes)
    $members.Add('git/changed-files.txt', $changed.Bytes)
    $members.Add('git/commits.txt', $commits.Bytes)
    $members.Add('git/status.txt', $script:utf8.GetBytes("OBSERVED: clean tracked and untracked delivery at packaging time.`nIgnored paths excluded; see manifest.excludedIgnoredPaths.`n"))
    $members.Add('git/diff-check.txt', $script:utf8.GetBytes("exitCode=$($check.ExitCode)`n" + $check.Text))
    return @{ Members = $members; Mapping = $mapping.ToArray(); Ignored = $ignoredPaths; DiffCheckExit = $check.ExitCode }
}

function Get-ReviewEvidence {
    param($Snapshot, [string]$Path, [string]$DeclaredStatus, $RuntimeCi)
    $evidence = @{ checks = @(@{ name = 'task-validation'; command = $null; status = 'NOT_RUN'; exitCode = $null; output = 'No committed evidence input supplied.' }); ci = @{ status = 'NOT_VERIFIED'; runId = $null; url = $null; commit = $null; conclusion = $null } }
    if ($Path) {
        Assert-ReviewPath $Path
        $item = @($Snapshot.Mapping | Where-Object { $_.archivePath -ceq ('source/' + $Path) })
        if ($item.Count -ne 1) { throw 'EVIDENCE_REQUIRED: EvidencePath must be an exact committed Git path in HeadSha' }
        $evidence = $script:utf8.GetString($Snapshot.Members[$item[0].archivePath]) | ConvertFrom-Json -AsHashtable
        if (-not $evidence.ContainsKey('checks') -or -not $evidence.ContainsKey('ci') -or @($evidence.checks).Count -eq 0) { throw 'EVIDENCE_REQUIRED: checks and ci objects required' }
    }
    if ($null -ne $RuntimeCi) { $evidence.ci = $RuntimeCi }
    foreach ($check in $evidence.checks) {
        if ($check.status -notin @('PASS', 'FAIL', 'PARTIAL', 'BLOCKED', 'NOT_RUN', 'NOT_VERIFIED')) { throw 'EVIDENCE_STATUS: invalid check status' }
        if ($check.status -eq 'PASS' -and (-not $check.command -or -not $check.ContainsKey('exitCode') -or $null -eq $check.exitCode -or $check.exitCode -ne 0 -or -not $check.output)) { throw 'EVIDENCE_REQUIRED: PASS requires command, exitCode=0 and actual output summary' }
    }
    if ($evidence.ci.status -notin @('PASS', 'FAIL', 'NOT_VERIFIED', 'NOT_RUN', 'BLOCKED')) { throw 'EVIDENCE_STATUS: invalid CI status' }
    if ($evidence.ci.status -in @('PASS', 'FAIL')) {
        foreach ($field in @('runId', 'url', 'commit', 'conclusion')) { if (-not $evidence.ci.Contains($field) -or -not $evidence.ci[$field]) { throw 'CI_EVIDENCE: runId, url, commit and conclusion required' } }
        if ($evidence.ci.url -notmatch '^https://github.com/on-dotnet/ontology-platform/actions/runs/[0-9]+(?:/.*)?$' -or $evidence.ci.commit -notmatch '^[0-9a-f]{40}$') { throw 'CI_EVIDENCE: explicit repository run URL and commit required' }
        if ($evidence.ci.runId -notmatch '^[0-9]+$' -or $evidence.ci.url -cne ('https://github.com/on-dotnet/ontology-platform/actions/runs/' + $evidence.ci.runId)) { throw 'CI_EVIDENCE: runId must match exact run URL' }
        if (($evidence.ci.status -eq 'PASS') -ne ($evidence.ci.conclusion -eq 'success')) { throw 'CI_EVIDENCE: status and conclusion disagree' }
    }
    if ($DeclaredStatus -eq 'PASS' -and (@($evidence.checks | Where-Object status -NE 'PASS').Count -gt 0 -or $evidence.ci.status -ne 'PASS' -or $Snapshot.DiffCheckExit -ne 0)) { throw ("EVIDENCE_REQUIRED: overall PASS requires all checks, diff-check and observed CI PASS; checkFailures={0}; ci={1}; diffExit={2}" -f @($evidence.checks | Where-Object status -NE 'PASS').Count, $evidence.ci.status, $Snapshot.DiffCheckExit) }
    return $evidence
}

function Test-ReviewArchive {
    param([string]$Path, [string]$Repository)
    $archive = [IO.Compression.ZipFile]::OpenRead($Path)
    $actual = [Collections.Generic.Dictionary[string,byte[]]]::new([StringComparer]::Ordinal)
    $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    try {
        foreach ($entry in $archive.Entries) {
            Assert-ReviewPath $entry.FullName
            if (-not $names.Add($entry.FullName)) { throw 'ARCHIVE_DUPLICATE: duplicate/case-colliding entry' }
            if (($entry.ExternalAttributes -shr 16 -band 0xF000) -eq 0xA000) { throw 'UNSAFE_PATH: archive symlink rejected' }
            $stream = $entry.Open()
            $buffer = [IO.MemoryStream]::new()
            try { $stream.CopyTo($buffer); $bytes = $buffer.ToArray() } finally { $stream.Dispose(); $buffer.Dispose() }
            Assert-ReviewContent $bytes 'reopened archive member'
            $actual.Add($entry.FullName, $bytes)
        }
    } finally { $archive.Dispose() }
    foreach ($required in @('manifest.json', 'SHA256SUMS.txt', 'REVIEW_SUMMARY.md', 'evidence/validation.json')) {
        if (-not $actual.ContainsKey($required)) { throw 'ARCHIVE_MISSING: required metadata absent' }
    }
    $manifest = $script:utf8.GetString($actual['manifest.json']) | ConvertFrom-Json -AsHashtable
    if ($manifest.schemaVersion -ne 1 -or $manifest.taskId -notmatch '^[A-Z0-9][A-Z0-9-]{0,79}$' -or $manifest.status -notin @('PASS', 'PARTIAL', 'BLOCKED', 'NOT_RUN')) { throw 'MANIFEST_INVALID: invalid identity/status' }
    $snapshot = Get-ReviewSnapshot $Repository $manifest.baseSha $manifest.headSha
    $evidence = Get-ReviewEvidence $snapshot $manifest.evidencePath $manifest.status $manifest.runtimeCi
    if ($manifest.status -eq 'PASS' -and $evidence.ci.commit -cne $manifest.headSha) { throw 'CI_EVIDENCE: PASS CI commit must equal HeadSha' }
    # 比较语义JSON，避免字典键序差异；包内状态必须来自已提交证据或显式CI参数。
    $recordedEvidence = $script:utf8.GetString($actual['evidence/validation.json'])
    $expectedEvidence = $evidence | ConvertTo-Json -Depth 16 -Compress
    $recordedManifestEvidence = @{ checks = $manifest.checks; ci = $manifest.ci } | ConvertTo-Json -Depth 16 -Compress
    $expectedNode = [Text.Json.Nodes.JsonNode]::Parse($expectedEvidence)
    if (-not [Text.Json.Nodes.JsonNode]::DeepEquals([Text.Json.Nodes.JsonNode]::Parse($recordedEvidence), $expectedNode) -or
        -not [Text.Json.Nodes.JsonNode]::DeepEquals([Text.Json.Nodes.JsonNode]::Parse($recordedManifestEvidence), $expectedNode)) { throw 'EVIDENCE_MISMATCH: recorded statuses differ from evidence input' }
    if ($manifest.diffCheck.exitCode -ne $snapshot.DiffCheckExit -or $manifest.diffCheck.status -ne $(if ($snapshot.DiffCheckExit -eq 0) { 'PASS' } else { 'FAIL' })) { throw 'EVIDENCE_MISMATCH: diff-check status differs from Git result' }
    $expectedPaths = @($snapshot.Members.Keys) + @('manifest.json', 'SHA256SUMS.txt', 'REVIEW_SUMMARY.md', 'evidence/validation.json')
    if ($actual.Count -ne $expectedPaths.Count) { throw 'ARCHIVE_MEMBERS: unexpected or missing archive member' }
    foreach ($name in $expectedPaths) { if (-not $actual.ContainsKey($name)) { throw 'ARCHIVE_MEMBERS: unexpected or missing archive member' } }
    foreach ($name in $snapshot.Members.Keys) {
        if ((Get-ReviewHash $actual[$name]) -cne (Get-ReviewHash $snapshot.Members[$name])) { throw 'HEAD_MISMATCH: source or full diff does not match committed HeadSha/BaseSha' }
    }
    $checksums = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
    foreach ($line in $script:utf8.GetString($actual['SHA256SUMS.txt']).Split("`n", [StringSplitOptions]::RemoveEmptyEntries)) {
        if ($line -notmatch '^([a-f0-9]{64})  (.+)$') { throw 'HASH_INVALID: checksum line invalid' }
        $checksum = $Matches[1]
        $name = $Matches[2]
        Assert-ReviewPath $name
        if ($name -ceq 'SHA256SUMS.txt' -or $checksums.ContainsKey($name) -or -not $actual.ContainsKey($name) -or (Get-ReviewHash $actual[$name]) -cne $checksum) { throw 'HASH_MISMATCH: member checksum differs' }
        $checksums.Add($name, $checksum)
    }
    if ($checksums.Count -ne $actual.Count - 1) { throw 'HASH_MISSING: every non-checksum member must have a SHA256 entry' }
    if (($manifest.sourceMembers | ConvertTo-Json -Depth 8 -Compress) -cne ($snapshot.Mapping | ConvertTo-Json -Depth 8 -Compress)) { throw 'MANIFEST_INVALID: committed source mapping differs' }
    return [ordered]@{ status = 'PASS'; checks = @('reopen', 'paths', 'forbidden-members', 'finite-secret-patterns', 'complete-member-set', 'member-sha256', 'source-blob-and-head', 'full-base-head-diff'); memberCount = $actual.Count }
}

try {
    $Root = [IO.Path]::GetFullPath($Root)
    if ($VerifyOnly) {
        if (-not $PackagePath) { throw 'PACKAGE_REQUIRED: VerifyOnly requires PackagePath' }
        $result = Test-ReviewArchive ([IO.Path]::GetFullPath($PackagePath)) $Root
        Write-Output ($result | ConvertTo-Json -Depth 8 -Compress)
        exit 0
    }
    if (-not $Status -or $TaskId -notmatch '^[A-Z0-9][A-Z0-9-]{0,79}$') { throw 'PARAMETERS_REQUIRED: explicit TaskId and Status required' }
    $snapshot = Get-ReviewSnapshot $Root $BaseSha $HeadSha
    $runtimeCi = $null
    if ($CiRunId -or $CiRunUrl -or $CiCommit -or $CiConclusion) {
        if (-not $CiRunId -or -not $CiRunUrl -or -not $CiCommit -or -not $CiConclusion) { throw 'CI_EVIDENCE: all four explicit CI parameters required together' }
        $runtimeCi = [ordered]@{ status = $(if ($CiConclusion -eq 'success') { 'PASS' } else { 'FAIL' }); runId = $CiRunId; url = $CiRunUrl; commit = $CiCommit; conclusion = $CiConclusion }
    }
    $evidence = Get-ReviewEvidence $snapshot $EvidencePath $Status $runtimeCi
    if ($Status -eq 'PASS' -and $evidence.ci.commit -cne $HeadSha) { throw 'CI_EVIDENCE: PASS CI commit must equal HeadSha' }
    $branch = (Invoke-ReviewGit $Root @('rev-parse', '--abbrev-ref', 'HEAD')).Text.Trim()
    $gitVersion = (Invoke-ReviewGit $Root @('--version')).Text.Trim()
    $manifest = [ordered]@{
        schemaVersion = 1; taskId = $TaskId; baseSha = $BaseSha; headSha = $HeadSha; branch = $branch
        date = [DateTime]::UtcNow.ToString('o'); status = $Status; evidencePath = $EvidencePath; runtimeCi = $runtimeCi
        checks = $evidence.checks; ci = $evidence.ci; commands = $script:commands.ToArray()
        environment = @{ powershell = $PSVersionTable.PSVersion.ToString(); git = $gitVersion; os = [Runtime.InteropServices.RuntimeInformation]::OSDescription }
        diffCheck = @{ status = $(if ($snapshot.DiffCheckExit -eq 0) { 'PASS' } else { 'FAIL' }); exitCode = $snapshot.DiffCheckExit }
        sourceMembers = $snapshot.Mapping; excludedIgnoredPaths = $snapshot.Ignored
        snapshotPolicy = 'Full repository under source, git archive checked against ls-tree and blob hashes; docs and evidence are additional convenience copies.'
        security = @{ status = 'PARTIAL'; scope = 'Finite path and UTF8/UTF16 pattern checks of committed source, complete patch, commit messages and reopened members. No guarantee of absence of secrets or private/production data; independent human review required.' }
        archiveVerification = @{ status = 'NOT_VERIFIED'; reason = 'Cannot embed its own post-close result; successful CLI JSON reports actual post-close verification.' }
    }
    $members = $snapshot.Members
    $members.Add('manifest.json', $script:utf8.GetBytes(($manifest | ConvertTo-Json -Depth 16) + "`n"))
    $members.Add('evidence/validation.json', $script:utf8.GetBytes(($evidence | ConvertTo-Json -Depth 12) + "`n"))
    $summary = "# $TaskId 审查摘要`n`n状态：$Status。BaseSha：$BaseSha；HeadSha：$HeadSha；分支：$branch。`n`n范围：Head中完整已提交常规文件和Base至Head完整差异；不使用origin/main..HEAD。source保留完整仓库相对结构；顶层docs/evidence提供文档和证据副本。`n`n验证：逐项命令/退出码见manifest.json与evidence/validation.json；CI为$($evidence.ci.status)。空证据不是PASS。静态构包成功不表示产品或整个阶段通过。`n`n阻断与未运行项：以checks/ci和任务证据为准；未提供真实运行证据的项目保持NOT_RUN/NOT_VERIFIED。忽略文件不读取、不交付，路径排除清单在manifest。`n`n安全限制：有限模式检查不能证明全面防泄露，独立审查仍需检查私有数据和未知秘密。发现可疑值时停止且不输出原值。`n`n后续：独立Reviewer审查并由Master处理集成；到当前关口停止，不自动进入下一阶段。`n"
    $members.Add('REVIEW_SUMMARY.md', $script:utf8.GetBytes($summary))
    $lines = foreach ($name in @($members.Keys | Sort-Object -CaseSensitive)) { Assert-ReviewPath $name; Assert-ReviewContent $members[$name] 'generated member'; (Get-ReviewHash $members[$name]) + '  ' + $name }
    $members.Add('SHA256SUMS.txt', $script:utf8.GetBytes(($lines -join "`n") + "`n"))
    $outputDirectory = Join-Path $Root 'artifacts/reviews'
    foreach ($candidate in @((Join-Path $Root 'artifacts'), $outputDirectory)) {
        if ((Test-Path -LiteralPath $candidate) -and ((Get-Item -LiteralPath $candidate -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'UNSAFE_OUTPUT: linked output directory rejected before creating children' }
    }
    $null = New-Item -ItemType Directory -Force $outputDirectory
    $ignoredOutput = Invoke-ReviewGit $Root @('check-ignore', '--no-index', 'artifacts/reviews/probe.zip') -AllowFailure
    if ($ignoredOutput.ExitCode -ne 0) { throw 'OUTPUT_NOT_IGNORED: artifacts/reviews must be ignored by Git' }
    # 输出目录及其祖先不得为链接，避免借ignored目录写出工作树。
    $cursor = Get-Item -LiteralPath $outputDirectory
    while ($null -ne $cursor -and $cursor.FullName -ne $Root) {
        if (($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'UNSAFE_OUTPUT: linked output directory rejected' }
        $cursor = $cursor.Parent
    }
    $finalPath = Join-Path $outputDirectory ("OntologyPlatform-Review-$TaskId-$($HeadSha.Substring(0, 12)).zip")
    if (Test-Path -LiteralPath $finalPath) { throw 'OUTPUT_EXISTS: preserve existing package; choose a new committed HeadSha or explicitly archive old delivery' }
    $temporaryPath = Join-Path $outputDirectory ([guid]::NewGuid().ToString('N') + '.partial')
    try {
        $file = [IO.File]::Open($temporaryPath, [IO.FileMode]::CreateNew)
        $archive = [IO.Compression.ZipArchive]::new($file, [IO.Compression.ZipArchiveMode]::Create)
        try {
            foreach ($name in @($members.Keys | Sort-Object -CaseSensitive)) {
                $entry = $archive.CreateEntry($name, [IO.Compression.CompressionLevel]::Optimal)
                $entry.LastWriteTime = [DateTimeOffset]::new(2000, 1, 1, 0, 0, 0, [TimeSpan]::Zero)
                $stream = $entry.Open()
                try { $stream.Write($members[$name], 0, $members[$name].Length) } finally { $stream.Dispose() }
            }
        } finally { $archive.Dispose(); $file.Dispose() }
        $verification = Test-ReviewArchive $temporaryPath $Root
        [IO.File]::Move($temporaryPath, $finalPath)
    } finally {
        if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Force }
    }
    Write-Output ([ordered]@{ packagePath = $finalPath; sizeBytes = (Get-Item -LiteralPath $finalPath).Length; sha256 = (Get-FileHash -LiteralPath $finalPath -Algorithm SHA256).Hash.ToLowerInvariant(); taskStatus = $Status; verification = $verification } | ConvertTo-Json -Depth 8 -Compress)
    exit 0
} catch {
    Write-Output "FAIL: $($_.Exception.Message)"
    exit 1
}
