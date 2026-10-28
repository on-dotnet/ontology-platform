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
    [ValidateSet('LOCAL', 'GITHUB')][string]$ValidationSource = 'LOCAL',
    [string]$CiRunId,
    [string]$CiRunUrl,
    [string]$CiCommit,
    [ValidateSet('success', 'failure', 'cancelled', 'timed_out', 'action_required')][string]$CiConclusion,
    [ValidateSet(1, 2, 3)][int]$SchemaVersion = 3,
    [switch]$Library,
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
    foreach ($argument in @('--no-optional-locks', '-c', 'core.autocrlf=false', '-c', 'core.quotePath=false', '-c', 'color.ui=false') + $Arguments) { $info.ArgumentList.Add($argument) }
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

function Get-ReviewObservedCi {
    param([string]$Repository, [string]$RunId, [string]$Head)
    if ($RunId -notmatch '^[0-9]+$') { throw 'CI_EVIDENCE: V3 requires an actual GitHub run ID' }
    $info = [Diagnostics.ProcessStartInfo]::new('gh')
    $info.WorkingDirectory = $Repository
    $info.UseShellExecute = $false
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in @('run', 'view', $RunId, '--repo', 'on-dotnet/ontology-platform', '--json', 'databaseId,headSha,url,status,conclusion,jobs')) { $info.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $info
    try {
        $null = $process.Start()
        $output = $process.StandardOutput.ReadToEndAsync(); $errorOutput = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(120000)) { $process.Kill($true); throw 'CI_EVIDENCE: GitHub query timed out' }
        $null = $errorOutput.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw 'CI_EVIDENCE: actual GitHub run/jobs unavailable; raw stderr suppressed' }
        $run = $output.GetAwaiter().GetResult() | ConvertFrom-Json -AsHashtable
    } catch { throw "CI_EVIDENCE: GitHub query failed; $($_.Exception.Message)" } finally { $process.Dispose() }
    $url = 'https://github.com/on-dotnet/ontology-platform/actions/runs/' + $RunId
    if ([string]$run.databaseId -cne $RunId -or $run.headSha -cne $Head -or $run.url -cne $url -or $run.status -cne 'completed') { throw 'CI_EVIDENCE: actual GitHub run identity, Head or completed status mismatch' }
    $jobs = @()
    foreach ($name in @('engineering', 'governance-integration')) {
        $jobMatches = @($run.jobs | Where-Object { $_.name -ceq $name })
        if ($jobMatches.Count -ne 1 -or $jobMatches[0].status -cne 'completed' -or -not $jobMatches[0].databaseId -or
            $jobMatches[0].url -notmatch ('^' + [regex]::Escape($url) + '/job/[0-9]+$')) { throw 'CI_EVIDENCE: exact required job missing or incomplete' }
        $job = $jobMatches[0]
        $jobs += [ordered]@{ id = [string]$job.databaseId; name = $name; url = $job.url; status = $job.status; conclusion = $job.conclusion }
    }
    $passed = $run.conclusion -ceq 'success' -and @($jobs | Where-Object conclusion -CNE 'success').Count -eq 0
    if ($run.conclusion -ceq 'success' -and -not $passed) { throw 'CI_EVIDENCE: run success disagrees with required jobs' }
    return [ordered]@{ status = $(if ($passed) { 'PASS' } else { 'FAIL' }); runId = $RunId; url = $url; commit = $Head; conclusion = $run.conclusion; verification = 'GITHUB_QUERIED'; jobs = $jobs }
}

function Get-ReviewIgnoredInventory {
    param([string]$Repository, [string[]]$Paths)
    $groups = @{}
    $directorySafety = [Collections.Generic.Dictionary[string,bool]]::new([StringComparer]::Ordinal)
    foreach ($path in $Paths) {
        # 仅读取非链接文件的长度元数据；不读ignored内容，也不跟随私有目录链接。
        $parts = $path.Split('/')
        $directory = if ($parts.Count -eq 1) { '<root>' } elseif ($parts[0] -in @('.tools', 'apps', 'backend', 'artifacts', '.runtime', 'node_modules', '.superpowers', '.worktrees', '.agents', '.codex')) { $parts[0] } else { '<other>' }
        $category = if ($path -match '(^|/)(node_modules|\.tools|\.nuget|\.pnpm|pnpm-store)(/|$)') { 'dependency-cache' } elseif ($path -match '(^|/)(obj|bin|\.next|coverage|TestResults)(/|$)') { 'build-output' } elseif ($directory -eq 'artifacts') { 'local-artifact' } elseif ($path -match '(^|/)(\.env[^/]*|[^/]*\.(pfx|pem|key))$') { 'private-configuration' } else { 'other-ignored' }
        $key = "$directory|$category"
        if (-not $groups.ContainsKey($key)) { $groups[$key] = [ordered]@{ directory = $directory; category = $category; count = 0; estimatedBytes = [long]0; unknownSizeCount = 0; examples = @() } }
        $group = $groups[$key]; $group.count++
        if ($group.examples.Count -lt 2) { $group.examples += $path }
        $cursor = $Repository; $safe = $true
        for ($i = 0; $i -lt $parts.Count; $i++) {
            $part = $parts[$i]
            if ($part -in @('', '.', '..') -or $part.Contains('\')) { $safe = $false; break }
            $cursor = [IO.Path]::Combine($cursor, $part)
            if ($i -lt $parts.Count - 1) {
                if (-not $directorySafety.ContainsKey($cursor)) {
                    $dir = [IO.DirectoryInfo]::new($cursor)
                    $directorySafety[$cursor] = $dir.Exists -and ($dir.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0
                }
                if (-not $directorySafety[$cursor]) { $safe = $false; break }
            }
        }
        $item = if ($safe) { [IO.FileInfo]::new($cursor) } else { $null }
        if ($null -ne $item -and $item.Exists -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) { $group.estimatedBytes += $item.Length } else { $group.unknownSizeCount++ }
    }
    $orderedGroups = @($groups.Keys | Sort-Object -CaseSensitive | ForEach-Object { $groups[$_] })
    $totalEstimated = [long]0
    foreach ($group in $orderedGroups) { $totalEstimated += $group.estimatedBytes }
    $listBytes = $script:utf8.GetBytes(($Paths -join "`0") + $(if ($Paths.Count) { "`0" } else { '' }))
    return [ordered]@{ count = $Paths.Count; estimatedBytes = $totalEstimated; listSha256 = Get-ReviewHash $listBytes; scannedAt = [DateTime]::UtcNow.ToString('o'); sizeMethod = 'File length metadata only; no content reads or symlink traversal; unavailable lengths counted separately.'; groups = $orderedGroups }
}

function Assert-ReviewIgnoredInventory {
    param($Inventory)
    $expectedFields = @('count', 'estimatedBytes', 'listSha256', 'scannedAt', 'sizeMethod', 'groups')
    if ($Inventory -isnot [Collections.IDictionary] -or $Inventory.get_Count() -ne $expectedFields.Count -or @($Inventory.Keys | Where-Object { $_ -cnotin $expectedFields }).Count) { throw 'MANIFEST_INVALID: ignored inventory fields invalid' }
    foreach ($field in @('count', 'estimatedBytes')) {
        if (($Inventory[$field] -isnot [int] -and $Inventory[$field] -isnot [long]) -or $Inventory[$field] -lt 0) { throw 'MANIFEST_INVALID: ignored inventory nonnegative integers required' }
    }
    $time = [DateTimeOffset]::MinValue
    # ConvertFrom-Json在部分PowerShell版本自动将ISO UTC字符串解析为DateTime。
    $validTime = if ($Inventory.scannedAt -is [string]) { $Inventory.scannedAt -match '(Z|[+-][0-9]{2}:[0-9]{2})$' -and [DateTimeOffset]::TryParse($Inventory.scannedAt, [ref]$time) } elseif ($Inventory.scannedAt -is [DateTime]) { $Inventory.scannedAt.Kind -eq [DateTimeKind]::Utc } else { $Inventory.scannedAt -is [DateTimeOffset] }
    if ($Inventory.listSha256 -isnot [string] -or $Inventory.listSha256 -cnotmatch '^[a-f0-9]{64}$' -or -not $validTime -or
        $Inventory.sizeMethod -cne 'File length metadata only; no content reads or symlink traversal; unavailable lengths counted separately.' -or $Inventory.groups -isnot [array] -or $Inventory.groups.Count -gt 60) { throw 'MANIFEST_INVALID: bounded ignored metadata schema invalid' }
    $keys = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $count = [decimal]0; $size = [decimal]0
    foreach ($group in $Inventory.groups) {
        $fields = @('directory', 'category', 'count', 'estimatedBytes', 'unknownSizeCount', 'examples')
        if ($group -isnot [Collections.IDictionary] -or $group.get_Count() -ne $fields.Count -or @($group.Keys | Where-Object { $_ -cnotin $fields }).Count -or
            $group.directory -cnotin @('<root>', '<other>', '.tools', 'apps', 'backend', 'artifacts', '.runtime', 'node_modules', '.superpowers', '.worktrees', '.agents', '.codex') -or
            $group.category -cnotin @('dependency-cache', 'build-output', 'local-artifact', 'private-configuration', 'other-ignored') -or
            -not $keys.Add(($group.directory + '|' + $group.category))) { throw 'MANIFEST_INVALID: ignored group fields, directory/category or uniqueness invalid' }
        foreach ($field in @('count', 'estimatedBytes', 'unknownSizeCount')) {
            if (($group[$field] -isnot [int] -and $group[$field] -isnot [long]) -or $group[$field] -lt 0) { throw 'MANIFEST_INVALID: ignored group nonnegative integers required' }
        }
        if ($group.count -eq 0 -or $group.unknownSizeCount -gt $group.count -or $group.examples -isnot [array] -or $group.examples.Count -gt [Math]::Min(2, $group.count)) { throw 'MANIFEST_INVALID: ignored group counts/examples inconsistent' }
        foreach ($example in $group.examples) {
            if ($example -isnot [string] -or $example.Length -eq 0 -or $example.Length -gt 4096 -or $example -match '(^/|[\x00-\x1f\x7f])') { throw 'MANIFEST_INVALID: ignored example must be a bounded relative path' }
        }
        $count += $group.count; $size += $group.estimatedBytes
    }
    if ($count -ne $Inventory.count -or $size -ne $Inventory.estimatedBytes) { throw 'MANIFEST_INVALID: ignored inventory totals differ from groups' }
}

function Get-ReviewDeflatedSize {
    param([byte[]]$Bytes)
    $buffer = [IO.MemoryStream]::new()
    $compressor = [IO.Compression.DeflateStream]::new($buffer, [IO.Compression.CompressionLevel]::Optimal, $true)
    try { $compressor.Write($Bytes, 0, $Bytes.Length) } finally { $compressor.Dispose() }
    try { return $buffer.Length } finally { $buffer.Dispose() }
}

function Get-ReviewSizeReport {
    param([string]$Path)
    $archive = [IO.Compression.ZipFile]::OpenRead($Path)
    $categories = @{}
    try {
        foreach ($entry in $archive.Entries) {
            $category = if ($entry.FullName.StartsWith('source/')) { 'source' } elseif ($entry.FullName.StartsWith('review-evidence/')) { 'review-evidence' } elseif ($entry.FullName.StartsWith('git/')) { 'git' } else { 'metadata-and-index' }
            if (-not $categories.ContainsKey($category)) { $categories[$category] = [ordered]@{ category = $category; members = 0; uncompressedBytes = [long]0; compressedBytes = [long]0 } }
            $categories[$category].members++; $categories[$category].uncompressedBytes += $entry.Length; $categories[$category].compressedBytes += $entry.CompressedLength
        }
    } finally { $archive.Dispose() }
    $size = (Get-Item -LiteralPath $Path).Length
    $payloadSize = [long]0
    foreach ($category in $categories.Values) { $payloadSize += $category.compressedBytes }
    return [ordered]@{ sizeBytes = $size; softTargetBytes = 10MB; hardLimitBytes = 15MB; aboveSoftTarget = ($size -gt 10MB); categories = @($categories.Keys | Sort-Object | ForEach-Object { $categories[$_] }); zipOverheadBytes = $size - $payloadSize }
}

function Get-ReviewSnapshot {
    param([string]$Repository, [string]$Base, [string]$Head, [int]$Version = 1, [string]$WorkItem = '')
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
    $changedPaths = Invoke-ReviewGit $Repository @('diff', '--no-color', '--name-only', '-z', '--no-renames', $Base, $Head, '--')
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
    $payloads = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
    $evidenceIndex = [Collections.Generic.List[object]]::new()
    $gitBytes = [Collections.Generic.Dictionary[string,byte[]]]::new([StringComparer]::Ordinal)
    $selectedScreenshots = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $screenshotSelection = "docs/evidence/$WorkItem/review-screenshots.json"
    if ($Version -eq 3 -and $blobs.ContainsKey($screenshotSelection)) {
        $selection = (Invoke-ReviewGit $Repository @('cat-file', 'blob', $blobs[$screenshotSelection])).Text | ConvertFrom-Json -AsHashtable
        $keys = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        if ($selection.schemaVersion -ne 1 -or @($selection.screenshots).Count -gt 12) { throw 'SCREENSHOT_SELECTION: schema1, at most 12 stable screenshots required' }
        foreach ($shot in $selection.screenshots) {
            Assert-ReviewPath $shot.path
            if (-not $shot.path.StartsWith('docs/evidence/', [StringComparison]::Ordinal) -or -not $shot.path.EndsWith('.png', [StringComparison]::OrdinalIgnoreCase) -or -not $blobs.ContainsKey($shot.path) -or $shot.stable -isnot [bool] -or $shot.stable -ne $true -or $shot.page -isnot [string] -or -not $shot.page -or $shot.theme -isnot [string] -or -not $shot.theme -or $shot.viewport -isnot [string] -or -not $shot.viewport -or
                -not $selectedScreenshots.Add($shot.path) -or -not $keys.Add((ConvertTo-Json -InputObject @($shot.page, $shot.theme, $shot.viewport) -Compress))) { throw 'SCREENSHOT_SELECTION: stable unique page/theme/viewport and committed PNG required' }
        }
    }
    $screenshotCompressedBytes = [long]0
    $screenshotPayloads = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
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
            $gitBytes.Add($path, $bytes)
            $hash = Get-ReviewHash $bytes
            if ($Version -eq 1) {
                $destinations = @('source/' + $path)
                if ($path.StartsWith('docs/evidence/')) { $destinations += 'evidence/' + $path.Substring(14) }
                elseif ($path.StartsWith('docs/')) { $destinations += $path }
                foreach ($destination in $destinations) {
                    Assert-ReviewPath $destination
                    $members.Add($destination, $bytes)
                    $mapping.Add([ordered]@{ gitPath = $path; archivePath = $destination; sha256 = $hash })
                }
            } else {
                $isEvidence = $path.StartsWith('docs/evidence/', [StringComparison]::Ordinal)
                $include = -not $isEvidence -or $path.StartsWith("docs/evidence/$WorkItem/", [StringComparison]::Ordinal)
                if ($Version -eq 3 -and $isEvidence -and $path.EndsWith('.png', [StringComparison]::OrdinalIgnoreCase)) {
                    $include = $selectedScreenshots.Contains($path)
                    if ($include -and $screenshotPayloads.Add($hash)) {
                        $screenshotCompressedBytes += Get-ReviewDeflatedSize $bytes
                        if ($screenshotCompressedBytes -gt 3MB) { throw 'SCREENSHOT_BUDGET: stable PNG compressed payload exceeds 3 MiB; select representative evidence' }
                    }
                }
                $destination = $null
                if ($include) {
                    $destination = if ($isEvidence) { 'review-evidence/' + $path.Substring(14) } else { 'source/' + $path }
                    if ($payloads.ContainsKey($hash)) { $destination = $payloads[$hash] }
                    else { $payloads.Add($hash, $destination); $members.Add($destination, $bytes) }
                    $mapping.Add([ordered]@{ gitPath = $path; archivePath = $destination; blobOid = $blobs[$path]; sha256 = $hash; sizeBytes = $bytes.Length })
                }
                if ($isEvidence) {
                    $evidenceIndex.Add([ordered]@{
                        gitPath = $path; commit = $Head; blobOid = $blobs[$path]; sha256 = $hash; sizeBytes = $bytes.Length
                        archivePath = $destination; testScope = $path.Substring(14).Split('/')[0]
                        recovery = "git show ${Head}:$path (raw Git blob); https://github.com/on-dotnet/ontology-platform/blob/$Head/$([uri]::EscapeDataString($path).Replace('%2F', '/'))"
                        retention = $(if ($include) { 'Included once in this package and retained in Git.' } else { 'Historical evidence retained in Git; requires access to this repository at the explicit commit. Not a standalone offline audit archive.' })
                    })
                }
            }
        }
    } finally { $archive.Dispose(); $memory.Dispose() }
    if ($seen.Count -ne $blobs.Count) { throw 'SNAPSHOT_MISMATCH: git archive omitted tracked delivery; check export-ignore attributes' }
    $diffOptions = @('diff', '--no-color', '--full-index', '--no-ext-diff', '--no-textconv', '--no-renames')
    if ($Version -eq 1) { $diffOptions += '--binary' }
    $diff = if ($Version -eq 1) { Invoke-ReviewGit $Repository ($diffOptions + @($Base, $Head, '--')) } else { @{ Bytes = [byte[]]::new(0) } }
    Assert-ReviewContent $diff.Bytes 'complete text patch including removed lines'
    if ($Version -ge 2) {
        # 对所有变更的两侧原始blob做路径/秘密检查；二进制省略不能绕过已删除内容检查。
        $raw = Invoke-ReviewGit $Repository @('diff', '--raw', '-z', '--no-color', '--no-ext-diff', '--no-textconv', '--find-renames', '--abbrev=40', $Base, $Head, '--')
        $parts = $raw.Text.Split([char]0, [StringSplitOptions]::RemoveEmptyEntries)
        $changes = [Collections.Generic.List[object]]::new()
        for ($i = 0; $i -lt $parts.Count; $i++) {
            if ($parts[$i] -notmatch '^:([0-7]{6}) ([0-7]{6}) ([0-9a-f]{40}) ([0-9a-f]{40}) ([A-Z][0-9]*)$') { throw 'DIFF_INVALID: unexpected raw diff record' }
            $oldMode = $Matches[1]; $newMode = $Matches[2]; $oldOid = $Matches[3]; $newOid = $Matches[4]; $kind = $Matches[5]
            $i++; $oldPath = $parts[$i]; $newPath = $oldPath
            if ($kind.StartsWith('R') -or $kind.StartsWith('C')) { $i++; $newPath = $parts[$i] }
            Assert-ReviewPath $oldPath; Assert-ReviewPath $newPath
            $sides = @{}; $binary = $false
            foreach ($side in @('base', 'head')) {
                $oid = if ($side -eq 'base') { $oldOid } else { $newOid }
                $mode = if ($side -eq 'base') { $oldMode } else { $newMode }
                $sidePath = if ($side -eq 'base') { $oldPath } else { $newPath }
                if ($oid -eq ('0' * 40)) { $sides[$side] = $null; continue }
                if ($mode -notin @('100644', '100755')) { throw 'UNSUPPORTED_TREE: changed symlink/submodule rejected' }
                $data = (Invoke-ReviewGit $Repository @('cat-file', 'blob', $oid)).Bytes
                Assert-ReviewContent $data 'changed Base/Head blob'
                if ([Array]::IndexOf($data, [byte]0, 0, [Math]::Min(8000, $data.Length)) -ge 0) { $binary = $true }
                $sides[$side] = [ordered]@{ path = $sidePath; blobOid = $oid; sha256 = Get-ReviewHash $data; sizeBytes = $data.Length; mode = $mode }
            }
            $changes.Add([ordered]@{ path = $newPath; previousPath = $(if ($oldPath -cne $newPath) { $oldPath } else { $null }); changeType = $kind; isBinary = $binary; base = $sides.base; head = $sides.head; recovery = 'git cat-file blob <base.blobOid or head.blobOid>; requires controlled repository access.' })
        }
        # 文本集合由原始blob判定，强制--text，避免已提交或本地attributes把文本差异隐藏成binary。
        $textPaths = @($changes | Where-Object { -not $_.isBinary } | ForEach-Object { $_.path; if ($_.previousPath) { $_.previousPath } } | Sort-Object -Unique -CaseSensitive | ForEach-Object { ':(literal)' + $_ })
        if ($textPaths.Count -gt 0) { $diff = Invoke-ReviewGit $Repository ($diffOptions + @('--text', $Base, $Head, '--') + $textPaths) }
        Assert-ReviewContent $diff.Bytes 'complete text patch including removed lines'
        $members.Add('git/changed-files.json', $script:utf8.GetBytes((ConvertTo-Json -InputObject $changes.ToArray() -Depth 12) + "`n"))
        $members.Add('evidence-index.json', $script:utf8.GetBytes((ConvertTo-Json -InputObject $evidenceIndex.ToArray() -Depth 12) + "`n"))
    }
    $changed = Invoke-ReviewGit $Repository @('diff', '--no-color', '--name-status', '--no-renames', $Base, $Head, '--')
    $commits = Invoke-ReviewGit $Repository @('log', '--no-color', '--format=fuller', '--no-decorate', "$Base..$Head")
    Assert-ReviewContent $commits.Bytes 'commit messages'
    $check = Invoke-ReviewGit $Repository @('diff', '--no-color', '--check', $Base, $Head, '--') -AllowFailure
    if ($Version -eq 1) {
        $members.Add('git/diff.patch', $diff.Bytes)
        $members.Add('git/changed-files.txt', $changed.Bytes)
    } else { $members.Add('git/diff-text.patch', $diff.Bytes) }
    $members.Add('git/commits.txt', $commits.Bytes)
    $members.Add('git/status.txt', $script:utf8.GetBytes("OBSERVED: clean tracked and untracked delivery at packaging time.`nIgnored paths excluded; see manifest.$(if ($Version -eq 3) { 'ignoredInventory' } else { 'excludedIgnoredPaths' }).`n"))
    $members.Add('git/diff-check.txt', $script:utf8.GetBytes("exitCode=$($check.ExitCode)`n" + $check.Text))
    return @{ Members = $members; Mapping = $mapping.ToArray(); Ignored = $ignoredPaths; ScreenshotCount = $selectedScreenshots.Count; ScreenshotCompressedBytes = $screenshotCompressedBytes; DiffCheckExit = $check.ExitCode; GitBytes = $gitBytes }
}

function Read-ReviewEvidenceSchema {
    param([byte[]]$Bytes, [string]$ExpectedHead = '')
    $value = $script:utf8.GetString($Bytes) | ConvertFrom-Json -AsHashtable -Depth 32
    if ($value -isnot [Collections.IDictionary] -or -not $value.ContainsKey('checks') -or -not $value.ContainsKey('ci')) { throw 'EVIDENCE_SCHEMA: checks and ci required' }
    if ($value.ContainsKey('evidenceSchemaVersion')) {
        $allowed = @('evidenceSchemaVersion', 'checks', 'ci', 'metadata')
        if ($value.evidenceSchemaVersion -ceq 2) { $allowed += @('validationSource', 'testedCommit') }
        if ($value.evidenceSchemaVersion -cnotin @(1, 2) -or @($value.Keys | Where-Object { $_ -cnotin $allowed }).Count) { throw 'EVIDENCE_SCHEMA: unsupported version or extra authoritative fields' }
        if ($Bytes.Length -eq 0 -or $Bytes[-1] -ne 10 -or ($Bytes.Length -gt 1 -and $Bytes[-2] -eq 10) -or $script:utf8.GetString($Bytes).Contains("`r")) { throw 'EVIDENCE_EOF: standard evidence requires one final LF and no CR' }
        if ($value.checks -isnot [array] -or $value.checks.Count -eq 0) { throw 'EVIDENCE_SCHEMA: nonempty checks array required' }
        $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        foreach ($check in $value.checks) {
            $fields = @('name', 'command', 'status', 'exitCode', 'output')
            if ($check -isnot [Collections.IDictionary] -or $check.get_Count() -ne $fields.Count -or @($check.Keys | Where-Object { $_ -cnotin $fields }).Count) { throw 'EVIDENCE_SCHEMA: exact check fields required' }
            if ($check.name -isnot [string] -or $check.name -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$' -or -not $names.Add($check.name) -or $check.output -isnot [string] -or -not $check.output -or ($null -ne $check.command -and $check.command -isnot [string])) { throw 'EVIDENCE_SCHEMA: controlled unique name, command and output required' }
            if ($null -ne $check.exitCode -and $check.exitCode -isnot [int] -and $check.exitCode -isnot [long]) { throw 'EVIDENCE_SCHEMA: integer or null exit required' }
            if ($check.status -cnotin @('PASS', 'FAIL', 'PARTIAL', 'BLOCKED', 'NOT_RUN', 'NOT_VERIFIED') -or ($check.status -ceq 'PASS' -and ($null -eq $check.exitCode -or $check.exitCode -ne 0 -or -not $check.command)) -or ($check.status -ceq 'FAIL' -and $check.exitCode -eq 0 -and $null -ne $check.exitCode) -or ($check.status -ceq 'NOT_RUN' -and $null -ne $check.exitCode)) { throw 'EVIDENCE_SCHEMA: status and actual exit disagree' }
        }
        $fields = @('status', 'runId', 'url', 'commit', 'conclusion')
        if ($value.ci -isnot [Collections.IDictionary] -or $value.ci.get_Count() -ne $fields.Count -or @($value.ci.Keys | Where-Object { $_ -cnotin $fields }).Count) { throw 'EVIDENCE_SCHEMA: exact CI fields required' }
        if ($value.ContainsKey('metadata') -and $value.metadata -isnot [Collections.IDictionary]) { throw 'EVIDENCE_SCHEMA: metadata must be an object' }
    }
    if ($value.ContainsKey('evidenceSchemaVersion') -and $value.evidenceSchemaVersion -ceq 2 -and ($value.validationSource -cne 'LOCAL' -or $value.testedCommit -cnotmatch '^[0-9a-f]{40}$' -or $value.ci.status -cnotin @('NOT_RUN', 'NOT_VERIFIED', 'BLOCKED'))) { throw 'LOCAL_EVIDENCE: schema2 requires LOCAL and exact testedCommit' }
    if ($ExpectedHead -and $value.ci.status -in @('PASS', 'FAIL') -and $value.ci.commit -cne $ExpectedHead) { throw 'CI_EVIDENCE: evidence commit differs from expected Head' }
    return $value
}

function Get-ReviewLocalBinding {
    param([string]$Repository, $Snapshot, [string]$Path, [string]$Head)
    if (-not $Path -or -not $Snapshot.GitBytes.ContainsKey($Path)) { throw 'LOCAL_EVIDENCE: committed local evidence required' }
    $value = Read-ReviewEvidenceSchema $Snapshot.GitBytes[$Path]
    if (-not $value.ContainsKey('evidenceSchemaVersion') -or $value.evidenceSchemaVersion -cne 2 -or $value.validationSource -cne 'LOCAL') { throw 'LOCAL_EVIDENCE: source must be authorized by committed schema2 evidence' }
    $tested = $value.testedCommit
    if ((Invoke-ReviewGit $Repository @('rev-parse', '--verify', ($tested + '^{commit}'))).Text.Trim() -cne $tested) { throw 'LOCAL_EVIDENCE: exact tested commit required' }
    if ((Invoke-ReviewGit $Repository @('merge-base', '--is-ancestor', $tested, $Head) -AllowFailure).ExitCode -ne 0) { throw 'LOCAL_EVIDENCE: tested commit must be an ancestor of delivery Head' }
    $identities = @()
    foreach ($commit in @($tested, $Head)) {
        # 仅任务/效率说明和证据可增量；合同、bootstrap及所有源码/脚本/锁/构建输入都参与身份。
        $rows = (Invoke-ReviewGit $Repository @('ls-tree', '-r', '--full-tree', $commit)).Text.Split("`n", [StringSplitOptions]::RemoveEmptyEntries)
        $inputs = @($rows | Where-Object { ($_ -split "`t", 2)[1] -cnotmatch '^(docs/(evidence|tasks|development)/|AGENTS\.md$|PLANS\.md$)' })
        $identities += Get-ReviewHash $script:utf8.GetBytes(($inputs -join "`n") + "`n")
    }
    if ($identities[0] -cne $identities[1]) { throw 'LOCAL_EVIDENCE: tested source/build/runtime input identity differs from delivery Head' }
    return [ordered]@{ testedCommit = $tested; deliveryCommit = $Head; inputSha256 = $identities[0]; evidenceSha256 = Get-ReviewHash $Snapshot.GitBytes[$Path]; verification = 'COMMITTED_LOCAL_EVIDENCE'; scope = 'All tracked inputs except docs/evidence, docs/tasks, docs/development, root AGENTS.md and PLANS.md; contracts/bootstrap included. Assertions are observed evidence, not reexecuted by packaging.' }
}

function Get-ReviewEvidence {
    param($Snapshot, [string]$Path, [string]$DeclaredStatus, $RuntimeCi, [bool]$Local = $false)
    $evidence = @{ checks = @(@{ name = 'task-validation'; command = $null; status = 'NOT_RUN'; exitCode = $null; output = 'No committed evidence input supplied.' }); ci = @{ status = 'NOT_VERIFIED'; runId = $null; url = $null; commit = $null; conclusion = $null } }
    if ($Path) {
        Assert-ReviewPath $Path
        $item = @($Snapshot.Mapping | Where-Object { $_.gitPath -ceq $Path })
        if (-not $Snapshot.GitBytes.ContainsKey($Path)) { throw 'EVIDENCE_REQUIRED: EvidencePath must be an exact committed Git path in HeadSha' }
        $evidence = Read-ReviewEvidenceSchema $Snapshot.GitBytes[$Path]
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
    if ($Local -and (-not $Path -or $null -ne $RuntimeCi -or $evidence.ci.status -notin @('NOT_RUN', 'NOT_VERIFIED', 'BLOCKED') -or @($evidence.checks | Where-Object status -EQ 'PASS').Count -eq 0)) { throw 'LOCAL_EVIDENCE: committed local checks and separate unknown/unrun CI required; use GITHUB to certify CI facts' }
    if ($DeclaredStatus -eq 'PASS' -and (@($evidence.checks | Where-Object status -NE 'PASS').Count -gt 0 -or (-not $Local -and $evidence.ci.status -ne 'PASS') -or $Snapshot.DiffCheckExit -ne 0)) { throw ("EVIDENCE_REQUIRED: overall PASS requires all checks, diff-check and observed CI PASS; checkFailures={0}; ci={1}; diffExit={2}" -f @($evidence.checks | Where-Object status -NE 'PASS').Count, $evidence.ci.status, $Snapshot.DiffCheckExit) }
    # 仅checks/ci是规范化状态；note/context等附加字段只在原始Git/ZIP证据保留，不参与状态比较。
    return @{ checks = $evidence.checks; ci = $evidence.ci }
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
    foreach ($required in @('manifest.json', 'SHA256SUMS.txt', 'REVIEW_SUMMARY.md')) {
        if (-not $actual.ContainsKey($required)) { throw 'ARCHIVE_MISSING: required metadata absent' }
    }
    $manifest = $script:utf8.GetString($actual['manifest.json']) | ConvertFrom-Json -AsHashtable
    if ($manifest.schemaVersion -notin @(1, 2, 3) -or $manifest.taskId -notmatch '^[A-Z0-9][A-Z0-9-]{0,79}$' -or $manifest.status -notin @('PASS', 'PARTIAL', 'BLOCKED', 'NOT_RUN')) { throw 'MANIFEST_INVALID: invalid identity/status' }
    $snapshot = Get-ReviewSnapshot $Repository $manifest.baseSha $manifest.headSha $manifest.schemaVersion $manifest.taskId
    $observedCi = $manifest.runtimeCi
    # 旧V3没有来源字段，继续按原GitHub合同重开；V1/V2保持原行为。
    $localValidation = $manifest.schemaVersion -eq 3 -and $manifest.ContainsKey('validationSource') -and $manifest.validationSource -ceq 'LOCAL'
    if ($manifest.ContainsKey('validationSource') -and $manifest.validationSource -cnotin @('LOCAL', 'GITHUB')) { throw 'LOCAL_EVIDENCE: invalid validation source' }
    if ($manifest.schemaVersion -eq 3) {
        if ((Get-Item -LiteralPath $Path).Length -gt 15MB) { throw 'PACKAGE_SIZE: V3 exceeds 15 MiB delivery limit' }
        if (-not $localValidation) { $observedCi = Get-ReviewObservedCi $Repository $manifest.ci.runId $manifest.headSha }
        if (-not [Text.Json.Nodes.JsonNode]::DeepEquals([Text.Json.Nodes.JsonNode]::Parse(($manifest.runtimeCi | ConvertTo-Json -Depth 12)), [Text.Json.Nodes.JsonNode]::Parse(($observedCi | ConvertTo-Json -Depth 12)))) { throw 'CI_EVIDENCE: recorded CI differs from actual GitHub run/jobs' }
        if ($snapshot.DiffCheckExit -ne 0) { throw 'DIFF_CHECK: V3 refuses a failing full Base/Head diff-check' }
        if (-not $manifest.ContainsKey('ignoredInventory') -or $manifest.ContainsKey('excludedIgnoredPaths')) { throw 'MANIFEST_INVALID: bounded ignored inventory required' }
        Assert-ReviewIgnoredInventory $manifest.ignoredInventory
        if ($manifest.screenshotPolicy.selectedCount -ne $snapshot.ScreenshotCount -or $manifest.screenshotPolicy.compressedBytes -ne $snapshot.ScreenshotCompressedBytes -or $manifest.screenshotPolicy.maxCount -ne 12 -or $manifest.screenshotPolicy.maxCompressedBytes -ne 3MB) { throw 'MANIFEST_INVALID: screenshot policy differs from committed selection' }
    }
    if ($localValidation) {
        $binding = Get-ReviewLocalBinding $Repository $snapshot $manifest.evidencePath $manifest.headSha
        if (-not [Text.Json.Nodes.JsonNode]::DeepEquals([Text.Json.Nodes.JsonNode]::Parse(($binding | ConvertTo-Json -Depth 8)), [Text.Json.Nodes.JsonNode]::Parse(($manifest.localValidation | ConvertTo-Json -Depth 8)))) { throw 'LOCAL_EVIDENCE: recorded input binding differs from committed source' }
    } elseif ($manifest.schemaVersion -eq 3 -and $manifest.evidencePath -and $snapshot.GitBytes.ContainsKey($manifest.evidencePath)) {
        $original = Read-ReviewEvidenceSchema $snapshot.GitBytes[$manifest.evidencePath]
        if ($original.ContainsKey('validationSource') -and $original.validationSource -ceq 'LOCAL') { throw 'LOCAL_EVIDENCE: committed LOCAL evidence cannot be relabeled' }
    }
    $evidence = Get-ReviewEvidence $snapshot $manifest.evidencePath $manifest.status $observedCi $localValidation
    if ((($manifest.status -eq 'PASS' -and -not $localValidation) -or ($manifest.schemaVersion -ge 2 -and $evidence.ci.status -in @('PASS', 'FAIL'))) -and $evidence.ci.commit -cne $manifest.headSha) { throw 'CI_EVIDENCE: PASS CI commit must equal HeadSha' }
    # 证据与CI从提交/显式输入重算；V2原始validation仅存在映射的一个位置。
    $expectedEvidence = $evidence | ConvertTo-Json -Depth 16 -Compress
    $recordedManifestEvidence = @{ checks = $manifest.checks; ci = $manifest.ci } | ConvertTo-Json -Depth 16 -Compress
    $expectedNode = [Text.Json.Nodes.JsonNode]::Parse($expectedEvidence)
    if (-not [Text.Json.Nodes.JsonNode]::DeepEquals([Text.Json.Nodes.JsonNode]::Parse($recordedManifestEvidence), $expectedNode)) { throw 'EVIDENCE_MISMATCH: recorded statuses differ from evidence input' }
    $metadataNames = @('manifest.json', 'SHA256SUMS.txt', 'REVIEW_SUMMARY.md')
    if ($manifest.schemaVersion -eq 1) {
        $metadataNames += 'evidence/validation.json'
        if (-not $actual.ContainsKey('evidence/validation.json') -or -not [Text.Json.Nodes.JsonNode]::DeepEquals([Text.Json.Nodes.JsonNode]::Parse($script:utf8.GetString($actual['evidence/validation.json'])), $expectedNode)) { throw 'EVIDENCE_MISMATCH: normalized evidence differs' }
    } else {
        if ($manifest.evidencePath -and -not $manifest.evidencePath.StartsWith("docs/evidence/$($manifest.taskId)/", [StringComparison]::Ordinal)) { throw 'EVIDENCE_REQUIRED: compact evidence must belong to current task' }
        $metadataNames += 'git/ci.json'
        if (-not $actual.ContainsKey('git/ci.json') -or -not [Text.Json.Nodes.JsonNode]::DeepEquals([Text.Json.Nodes.JsonNode]::Parse($script:utf8.GetString($actual['git/ci.json'])), [Text.Json.Nodes.JsonNode]::Parse(($evidence.ci | ConvertTo-Json -Depth 12)))) { throw 'CI_EVIDENCE: CI metadata mismatch' }
        if (-not $manifest.evidencePath) {
            $metadataNames += 'review-evidence/validation.json'
            if (-not $actual.ContainsKey('review-evidence/validation.json') -or -not [Text.Json.Nodes.JsonNode]::DeepEquals([Text.Json.Nodes.JsonNode]::Parse($script:utf8.GetString($actual['review-evidence/validation.json'])), $expectedNode)) { throw 'EVIDENCE_MISMATCH: absent evidence status differs' }
        }
    }
    if ($manifest.diffCheck.exitCode -ne $snapshot.DiffCheckExit -or $manifest.diffCheck.status -ne $(if ($snapshot.DiffCheckExit -eq 0) { 'PASS' } else { 'FAIL' })) { throw 'EVIDENCE_MISMATCH: diff-check status differs from Git result' }
    $expectedPaths = @($snapshot.Members.Keys) + $metadataNames
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

if ($Library) { return }

try {
    $Root = [IO.Path]::GetFullPath($Root)
    if ($VerifyOnly) {
        if (-not $PackagePath) { throw 'PACKAGE_REQUIRED: VerifyOnly requires PackagePath' }
        $result = Test-ReviewArchive ([IO.Path]::GetFullPath($PackagePath)) $Root
        Write-Output ($result | ConvertTo-Json -Depth 8 -Compress)
        exit 0
    }
    if (-not $Status -or $TaskId -notmatch '^[A-Z0-9][A-Z0-9-]{0,79}$') { throw 'PARAMETERS_REQUIRED: explicit TaskId and Status required' }
    $snapshot = Get-ReviewSnapshot $Root $BaseSha $HeadSha $SchemaVersion $TaskId
    $localValidation = $SchemaVersion -eq 3 -and $ValidationSource -ceq 'LOCAL'
    if ($localValidation -and ($CiRunId -or $CiRunUrl -or $CiCommit -or $CiConclusion -or -not $EvidencePath)) { throw 'LOCAL_EVIDENCE: local V3 requires committed EvidencePath and no remote CI override' }
    $runtimeCi = $null
    if ($CiRunId -or $CiRunUrl -or $CiCommit -or $CiConclusion) {
        if (-not $CiRunId -or -not $CiRunUrl -or -not $CiCommit -or -not $CiConclusion) { throw 'CI_EVIDENCE: all four explicit CI parameters required together' }
        $runtimeCi = [ordered]@{ status = $(if ($CiConclusion -eq 'success') { 'PASS' } else { 'FAIL' }); runId = $CiRunId; url = $CiRunUrl; commit = $CiCommit; conclusion = $CiConclusion }
    }
    if ($SchemaVersion -eq 3) {
        if (-not $localValidation) {
        $declaredCi = $runtimeCi
        if (-not $CiRunId -and $EvidencePath -and $snapshot.GitBytes.ContainsKey($EvidencePath)) { $CiRunId = (($script:utf8.GetString($snapshot.GitBytes[$EvidencePath]) | ConvertFrom-Json -AsHashtable).ci.runId) }
        $runtimeCi = Get-ReviewObservedCi $Root $CiRunId $HeadSha
        if ($null -ne $declaredCi -and ($declaredCi.commit -cne $runtimeCi.commit -or $declaredCi.url -cne $runtimeCi.url -or $declaredCi.conclusion -cne $runtimeCi.conclusion)) { throw 'CI_EVIDENCE: supplied CI differs from actual GitHub run/jobs' }
        }
        if ($snapshot.DiffCheckExit -ne 0) { throw 'DIFF_CHECK: V3 refuses a failing full Base/Head diff-check' }
    }
    $localBinding = if ($localValidation) { Get-ReviewLocalBinding $Root $snapshot $EvidencePath $HeadSha } else { $null }
    $evidence = Get-ReviewEvidence $snapshot $EvidencePath $Status $runtimeCi $localValidation
    if ((($Status -eq 'PASS' -and -not $localValidation) -or ($SchemaVersion -ge 2 -and $evidence.ci.status -in @('PASS', 'FAIL'))) -and $evidence.ci.commit -cne $HeadSha) { throw 'CI_EVIDENCE: PASS CI commit must equal HeadSha' }
    $branch = (Invoke-ReviewGit $Root @('rev-parse', '--abbrev-ref', 'HEAD')).Text.Trim()
    $gitVersion = (Invoke-ReviewGit $Root @('--version')).Text.Trim()
    $manifest = [ordered]@{
        schemaVersion = $SchemaVersion; taskId = $TaskId; baseSha = $BaseSha; headSha = $HeadSha; branch = $branch
        date = [DateTime]::UtcNow.ToString('o'); status = $Status; evidencePath = $EvidencePath; runtimeCi = $runtimeCi
        checks = $evidence.checks; ci = $evidence.ci; commands = $script:commands.ToArray()
        environment = @{ powershell = $PSVersionTable.PSVersion.ToString(); git = $gitVersion; os = [Runtime.InteropServices.RuntimeInformation]::OSDescription }
        diffCheck = @{ status = $(if ($snapshot.DiffCheckExit -eq 0) { 'PASS' } else { 'FAIL' }); exitCode = $snapshot.DiffCheckExit }
        sourceMembers = $snapshot.Mapping; excludedIgnoredPaths = $snapshot.Ignored
        snapshotPolicy = $(if ($SchemaVersion -eq 1) { 'Full repository under source, git archive checked against ls-tree and blob hashes; docs and evidence are additional convenience copies.' } else { 'All current non-evidence sources and current-task evidence, each payload once; historical evidence indexed against Head blobs; full text diff and Base/Head binary metadata; repository access required for omitted bytes.' })
        security = @{ status = 'PARTIAL'; scope = 'Finite path and UTF8/UTF16 pattern checks of committed source, complete patch, commit messages and reopened members. No guarantee of absence of secrets or private/production data; independent human review required.' }
        archiveVerification = @{ status = 'NOT_VERIFIED'; reason = 'Cannot embed its own post-close result; successful CLI JSON reports actual post-close verification.' }
    }
    if ($SchemaVersion -eq 3) {
        $manifest.validationSource = $ValidationSource
        if ($localValidation) { $manifest.localValidation = $localBinding }
        $manifest.Remove('excludedIgnoredPaths')
        $manifest.ignoredInventory = Get-ReviewIgnoredInventory $Root $snapshot.Ignored
        Assert-ReviewIgnoredInventory $manifest.ignoredInventory
        $manifest.screenshotPolicy = [ordered]@{ selectionPath = "docs/evidence/$TaskId/review-screenshots.json"; maxCount = 12; maxCompressedBytes = 3MB; selectedCount = $snapshot.ScreenshotCount; compressedBytes = $snapshot.ScreenshotCompressedBytes; default = 'Only explicitly selected stable representative PNG evidence; all omitted evidence remains recoverable from indexed Git blobs.' }
    }
    $members = $snapshot.Members
    $members.Add('manifest.json', $script:utf8.GetBytes(($manifest | ConvertTo-Json -Depth 16) + "`n"))
    if ($SchemaVersion -eq 1) { $members.Add('evidence/validation.json', $script:utf8.GetBytes(($evidence | ConvertTo-Json -Depth 12) + "`n")) }
    else {
        if ($EvidencePath -and -not $EvidencePath.StartsWith("docs/evidence/$TaskId/", [StringComparison]::Ordinal)) { throw 'EVIDENCE_REQUIRED: compact evidence must belong to current task' }
        $members.Add('git/ci.json', $script:utf8.GetBytes(($evidence.ci | ConvertTo-Json -Depth 12) + "`n"))
        if (-not $EvidencePath) { $members.Add('review-evidence/validation.json', $script:utf8.GetBytes(($evidence | ConvertTo-Json -Depth 12) + "`n")) }
    }
    $summary = "# $TaskId 审查摘要`n`n状态：$Status。BaseSha：$BaseSha；HeadSha：$HeadSha；分支：$branch。`n`n范围：Head中完整已提交常规文件和Base至Head完整差异；不使用origin/main..HEAD。source保留完整仓库相对结构；顶层docs/evidence提供文档和证据副本。`n`n验证：逐项命令/退出码见manifest.json与evidence/validation.json；CI为$($evidence.ci.status)。空证据不是PASS。静态构包成功不表示产品或整个阶段通过。`n`n阻断与未运行项：以checks/ci和任务证据为准；未提供真实运行证据的项目保持NOT_RUN/NOT_VERIFIED。忽略文件不读取、不交付，路径排除清单在manifest。`n`n安全限制：有限模式检查不能证明全面防泄露，独立审查仍需检查私有数据和未知秘密。发现可疑值时停止且不输出原值。`n`n后续：独立Reviewer审查并由Master处理集成；到当前关口停止，不自动进入下一阶段。`n"
    if ($SchemaVersion -ge 2) {
        $summary = "# $TaskId 审查摘要`n`n状态：$Status。BaseSha：$BaseSha；HeadSha：$HeadSha；分支：$branch。`n`n范围：source为全部现行非证据源码/配置/测试/合同/ADR；review-evidence为本任务已提交证据。相同内容只保留一个payload，映射见manifest.sourceMembers。原始validation见映射，实际CI见git/ci.json与manifest。`n`n差异：git/diff-text.patch保留全部文本差异；git/changed-files.json记录每项变更的Base/Head原始blob OID、SHA256、大小、路径、类型；二进制不内嵌补丁。evidence-index.json完整列出历史证据与恢复方式。省略字节需要访问受控Git仓库，不能把此包声称为完整离线审计归档。`n`n验证：逐项命令/退出码见manifest与任务validation；CI为$($evidence.ci.status)，CI成功/失败元数据均要求同Head。空证据不是PASS；构包/重开仅证明有限完整性检查。`n`n安全与限制：已提交源、变更两侧原blob、文本补丁和成员做有限凭证检查；不包含ignored私有配置/凭证/缓存/数据库。不代替完整安全审计。被保留资源、未运行平台及实际回收量见本任务delivery-report。`n`n后续：停在当前关口，等待复审，不自动开始G3或下一阶段。`n"
    }
    if ($SchemaVersion -eq 3) { $summary += "`nV3：验证来源=$ValidationSource。LOCAL从已提交checks和源码blob重算并独立重开，不调用GitHub；GITHUB实际查询同Head run及两个job，历史无来源字段V3维持原规则。PNG仅保留已提交选择清单中的最终稳定代表，最多12张/压缩3MiB。ignored仅聚合元数据，完整路径清单只存本地artifact。软目标10MiB、硬上限15MiB；Slim不等于独立离线审计包。`n" }
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
    $localIgnored = $null
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
        $sizeReport = Get-ReviewSizeReport $temporaryPath
        if ($SchemaVersion -eq 3 -and $sizeReport.sizeBytes -gt 15MB) { throw 'PACKAGE_SIZE: V3 exceeds 15 MiB delivery limit; no default delivery permitted' }
        $verification = Test-ReviewArchive $temporaryPath $Root
        if ($SchemaVersion -eq 3) {
            # 完整ignored清单只写本地artifact；从不放入ZIP或覆盖既有有效包。
            $localIgnored = Join-Path $outputDirectory ("ignored-$TaskId-$($HeadSha.Substring(0, 12))-$([guid]::NewGuid().ToString('N')).paths.txt")
            $ignoredBytes = $script:utf8.GetBytes(($snapshot.Ignored -join "`0") + $(if ($snapshot.Ignored.Count) { "`0" } else { '' }))
            $ignoredFile = [IO.File]::Open($localIgnored, [IO.FileMode]::CreateNew)
            try { $ignoredFile.Write($ignoredBytes, 0, $ignoredBytes.Length) } finally { $ignoredFile.Dispose() }
        }
        [IO.File]::Move($temporaryPath, $finalPath)
    } finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
            if ($localIgnored -and (Test-Path -LiteralPath $localIgnored)) { Remove-Item -LiteralPath $localIgnored -Force }
        }
    }
    Write-Output ([ordered]@{ sizeReport = $sizeReport; packagePath = $finalPath; sizeBytes = (Get-Item -LiteralPath $finalPath).Length; sha256 = (Get-FileHash -LiteralPath $finalPath -Algorithm SHA256).Hash.ToLowerInvariant(); taskStatus = $Status; verification = $verification } | ConvertTo-Json -Depth 8 -Compress)
    exit 0
} catch {
    Write-Output "FAIL: $($_.Exception.Message)"
    exit 1
}
