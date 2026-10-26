<#
.SYNOPSIS
在隔离Git仓库中运行审查包真实正反例；无需Pester或项目依赖。
#>
[CmdletBinding()]
param([string]$PackageScript = (Join-Path $PSScriptRoot '../create-review-package.ps1'), [string]$CaseFilter = '*')
$ErrorActionPreference = 'Stop'
$PackageScript = [IO.Path]::GetFullPath($PackageScript)
$fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('ontology-review-tests-' + [guid]::NewGuid().ToString('N'))
$results = [Collections.Generic.List[object]]::new()
$script:gitExecutable = @(Get-Command git -CommandType Application)[0].Source
function Git {
    param([string[]]$Arguments)
    $output = & $script:gitExecutable -C $script:repo -c core.autocrlf=false @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "fixture git failed: $($Arguments[0])" }
    return ($output -join "`n").Trim()
}
function Write-Fixture {
    param([string]$Path, [string]$Text)
    $destination = Join-Path $script:repo $Path
    $null = New-Item -ItemType Directory -Force (Split-Path $destination -Parent)
    [IO.File]::WriteAllText($destination, $Text.Replace("`r`n", "`n"), [Text.UTF8Encoding]::new($false))
}
function Commit-Fixture {
    $null = Git @('add', '--all')
    $null = Git @('commit', '-qm', 'fixture change')
    return (Git @('rev-parse', 'HEAD'))
}
function New-Fixture {
    $script:repo = Join-Path $fixtureRoot ([guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Force $script:repo
    $null = Git @('init', '-q', '--initial-branch=master')
    $null = Git @('config', 'user.email', 'fixture@example.invalid')
    $null = Git @('config', 'user.name', 'Review fixture')
    Write-Fixture '.gitignore' "artifacts/`n"
    Write-Fixture 'app.txt' "base`n"
    $script:base = Commit-Fixture
    Write-Fixture 'app.txt' "当前源码`n"
    Write-Fixture 'docs/tasks/TEST-001.md' "# 测试任务`n"
    Write-Fixture 'docs/evidence/TEST-001/result.txt' "NOT_RUN: product tests`n"
    Write-Fixture '.env.example' "CLIENT_SECRET=<set-locally>`n"
    $script:head = Commit-Fixture
}
function Invoke-Package {
    param([string[]]$Extra = @(), [switch]$Verify, [switch]$Compact, [string]$DeclaredStatus = 'PARTIAL')
    $arguments = @('-NoProfile', '-File', $PackageScript, '-Root', $script:repo)
    if (-not $Verify -and -not $Compact) { $arguments += @('-SchemaVersion', '1') }
    if (-not $Verify) { $arguments += @('-BaseSha', $script:base, '-HeadSha', $script:head, '-TaskId', 'TEST-001', '-Status', $DeclaredStatus) }
    $output = & pwsh @arguments @Extra 2>&1
    return [pscustomobject]@{ Exit = $LASTEXITCODE; Output = ($output -join "`n") }
}
function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}
function Expect-Rejected {
    param([string]$Reason)
    $actual = Invoke-Package
    Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains($Reason)) "Expected rejection $Reason; got $($actual.Output)"
    Assert-True (@(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip' -ErrorAction SilentlyContinue).Count -eq 0) 'Rejected input left a delivery ZIP'
}
function Case {
    param([string]$Name, [scriptblock]$Action)
    if ($Name -notlike $CaseFilter) { return }
    try { New-Fixture; & $Action; $results.Add([pscustomobject]@{ Name = $Name; Status = 'PASS' }); Write-Output "PASS: $Name" }
    catch { $results.Add([pscustomobject]@{ Name = $Name; Status = 'FAIL' }); Write-Output "FAIL: $Name -- $($_.Exception.Message)" }
}
try {
    $null = New-Item -ItemType Directory -Force $fixtureRoot
    function Read-ZipText($Archive, [string]$Name) {
        $reader = [IO.StreamReader]::new($Archive.GetEntry($Name).Open())
        try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
    }
    function Open-Compact {
        $actual = Invoke-Package -Compact
        Assert-True ($actual.Exit -eq 0) "Compact creation failed: $($actual.Output)"
        return @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
    }
    Case 'compact default is V2 with complete source and historical evidence index' {
        $path = Open-Compact
        $archive = [IO.Compression.ZipFile]::OpenRead($path)
        try {
            $manifest = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json
            $index = @(Read-ZipText $archive 'evidence-index.json' | ConvertFrom-Json)
            Assert-True ($manifest.schemaVersion -eq 2) 'Default must be compact schema2'
            foreach ($name in @('source/app.txt', 'source/docs/tasks/TEST-001.md', 'git/diff-text.patch', 'git/changed-files.json', 'git/ci.json', 'review-evidence/TEST-001/result.txt')) {
                Assert-True ($null -ne $archive.GetEntry($name)) "Missing compact member $name"
            }
            Assert-True ($null -eq $archive.GetEntry('source/docs/evidence/TEST-001/result.txt')) 'Evidence copied twice'
            Assert-True ($index.Count -eq 1 -and $index[0].gitPath -eq 'docs/evidence/TEST-001/result.txt' -and $index[0].commit -eq $script:head -and $index[0].sha256.Length -eq 64 -and $index[0].blobOid.Length -eq 40 -and $index[0].sizeBytes -gt 0 -and $index[0].testScope -and $index[0].recovery -and $index[0].retention) 'Evidence index lacks provenance'
        } finally { $archive.Dispose() }
        $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
        Assert-True ($verified.Exit -eq 0) "Compact reopen failed: $($verified.Output)"
    }
    Case 'compact binary add modify delete rename and historical screenshot reduction' {
        $random = [Random]::new(42)
        $bytes = [byte[]]::new(32768); $random.NextBytes($bytes); $bytes[0] = 0
        Write-Fixture 'docs/evidence/OLD-001/samples/one.png' ''
        [IO.File]::WriteAllBytes((Join-Path $script:repo 'docs/evidence/OLD-001/samples/one.png'), $bytes)
        [IO.File]::WriteAllBytes((Join-Path $script:repo 'remove.png'), $bytes)
        Write-Fixture 'rename.txt' "rename source with sufficient unchanged text for Git detection`n"
        $script:base = Commit-Fixture
        $bytes[10] = $bytes[10] -bxor 1
        [IO.File]::WriteAllBytes((Join-Path $script:repo 'docs/evidence/OLD-001/samples/one.png'), $bytes)
        for ($i = 0; $i -lt 24; $i++) {
            $bytes = [byte[]]::new(32768); $random.NextBytes($bytes); $bytes[0] = 0
            [IO.File]::WriteAllBytes((Join-Path $script:repo "docs/evidence/OLD-001/samples/new-$i.png"), $bytes)
        }
        $null = Git @('rm', 'remove.png'); $null = Git @('mv', 'rename.txt', 'renamed.txt')
        Write-Fixture 'new.txt' "new text`n"
        $script:head = Commit-Fixture
        $path = Open-Compact
        $archive = [IO.Compression.ZipFile]::OpenRead($path)
        try {
            $diff = Read-ZipText $archive 'git/diff-text.patch'
            $changed = @(Read-ZipText $archive 'git/changed-files.json' | ConvertFrom-Json)
            $index = @(Read-ZipText $archive 'evidence-index.json' | ConvertFrom-Json)
            Assert-True (-not $diff.Contains('GIT binary patch') -and $diff.Contains('new text')) 'Binary encoded patch or missing text diff'
            Assert-True (@($changed | Where-Object isBinary).Count -eq 26) 'Binary changes missing'
            Assert-True (@($changed | Where-Object { $_.changeType -like 'R*' }).Count -eq 1) 'Rename missing'
            $deleted = @($changed | Where-Object path -EQ 'remove.png')[0]
            Assert-True ($deleted.base.blobOid.Length -eq 40 -and $deleted.base.sha256.Length -eq 64 -and $deleted.base.sizeBytes -eq 32768 -and $null -eq $deleted.head) 'Deleted binary recovery metadata missing'
            Assert-True (@($index | Where-Object { $_.gitPath -like 'docs/evidence/OLD-001/*' -and $null -eq $_.archivePath }).Count -eq 25) 'Historical evidence not fully indexed/omitted'
            Assert-True (@($archive.Entries | Where-Object FullName -Like '*OLD-001/samples/*').Count -eq 0) 'Historical screenshots copied'
        } finally { $archive.Dispose() }
        # 同一个已提交Head显式生成V1比较实际压缩大小，旧包先改名保留，不覆盖。
        $compactSize = (Get-Item $path).Length
        Move-Item -LiteralPath $path -Destination ($path + '.compact')
        $legacy = Invoke-Package
        Assert-True ($legacy.Exit -eq 0) "Legacy comparison failed: $($legacy.Output)"
        $legacySize = (Get-Item $path).Length
        Assert-True ($compactSize -lt ($legacySize / 3)) "Compact did not shrink: compact=$compactSize legacy=$legacySize"
        Write-Output "OBSERVED compactBytes=$compactSize legacyBytes=$legacySize"
        $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', ($path + '.compact'))
        Assert-True ($verified.Exit -eq 0) "Binary compact reopen failed: $($verified.Output)"
    }
    Case 'compact text diff cannot be hidden by committed attributes' {
        Write-Fixture '.gitattributes' "app.txt -diff`n"
        $script:base = Commit-Fixture
        Write-Fixture 'app.txt' "critical changed text`n"
        $script:head = Commit-Fixture
        $path = Open-Compact
        $archive = [IO.Compression.ZipFile]::OpenRead($path)
        try {
            $patch = Read-ZipText $archive 'git/diff-text.patch'
            Assert-True ($patch.Contains('-当前源码') -and $patch.Contains('+critical changed text')) 'Text diff hidden by attributes'
        } finally { $archive.Dispose() }
        $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
        Assert-True ($verified.Exit -eq 0) 'Attribute-independent text diff reopen failed'
    }
    Case 'compact duplicate payload maps to one physical member' {
        Write-Fixture 'duplicate.txt' "当前源码`n"
        Write-Fixture 'docs/evidence/TEST-001/duplicate.txt' "当前源码`n"
        $script:head = Commit-Fixture
        $path = Open-Compact
        $archive = [IO.Compression.ZipFile]::OpenRead($path)
        try {
            $manifest = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json
            $mappings = @($manifest.sourceMembers | Where-Object gitPath -In @('app.txt', 'duplicate.txt', 'docs/evidence/TEST-001/duplicate.txt'))
            Assert-True ($mappings.Count -eq 3 -and @($mappings.archivePath | Select-Object -Unique).Count -eq 1) 'Duplicate content retained'
        } finally { $archive.Dispose() }
    }
    Case 'compact index tamper with rewritten checksum is rejected' {
        $path = Open-Compact
        $archive = [IO.Compression.ZipFile]::Open($path, [IO.Compression.ZipArchiveMode]::Update)
        try {
            $index = @(Read-ZipText $archive 'evidence-index.json' | ConvertFrom-Json)
            $index[0].sha256 = '0' * 64
            $bytes = [Text.Encoding]::UTF8.GetBytes(($index | ConvertTo-Json -AsArray -Depth 12))
            $archive.GetEntry('evidence-index.json').Delete()
            $stream = $archive.CreateEntry('evidence-index.json').Open()
            try { $stream.Write($bytes) } finally { $stream.Dispose() }
            $sums = Read-ZipText $archive 'SHA256SUMS.txt'
            $hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
            $sums = $sums -replace '(?m)^[a-f0-9]{64}  evidence-index.json$', ($hash + '  evidence-index.json')
            $archive.GetEntry('SHA256SUMS.txt').Delete()
            $writer = [IO.StreamWriter]::new($archive.CreateEntry('SHA256SUMS.txt').Open())
            try { $writer.Write($sums) } finally { $writer.Dispose() }
        } finally { $archive.Dispose() }
        $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
        Assert-True ($verified.Exit -ne 0 -and $verified.Output.Contains('HEAD_MISMATCH')) 'Forged index accepted'
    }
    Case 'compact rejects CI success from different Head even with PARTIAL task' {
        $actual = Invoke-Package -Compact -Extra @('-CiRunId', '123', '-CiRunUrl', 'https://github.com/on-dotnet/ontology-platform/actions/runs/123', '-CiCommit', $script:base, '-CiConclusion', 'success')
        Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('CI_EVIDENCE')) 'Old CI success reused'
    }
    Case 'compact rejects case-colliding committed paths' {
        $blob = Git @('hash-object', 'app.txt')
        $null = Git @('update-index', '--add', '--cacheinfo', "100644,$blob,APP.txt")
        $null = Git @('commit', '-qm', 'case collision')
        $script:head = Git @('rev-parse', 'HEAD')
        $null = Git @('checkout', '-q', $script:base)
        $actual = Invoke-Package -Compact
        Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('SNAPSHOT_MISMATCH')) 'Case collision accepted'
    }
    foreach ($negative in @('dirty', 'untracked', 'forbidden', 'removed-secret', 'symlink', 'path-traversal', 'case-member', 'duplicate-member', 'linked-member', 'hash-forgery')) {
        $scenario = $negative
        Case "compact safety $scenario" {
            switch ($scenario) {
                'dirty' { Write-Fixture 'app.txt' "dirty`n" }
                'untracked' { Write-Fixture 'untracked.txt' "pending`n" }
                'forbidden' { Write-Fixture '.env' "synthetic safe placeholder`n"; $script:head = Commit-Fixture }
                'removed-secret' {
                    Write-Fixture 'removed.txt' (('gh' + 'p_' + ('Z' * 36)) + "`n"); $script:base = Commit-Fixture
                    $null = Git @('rm', 'removed.txt'); $script:head = Commit-Fixture
                }
                'symlink' {
                    $blob = Git @('hash-object', 'app.txt')
                    $null = Git @('update-index', '--add', '--cacheinfo', "120000,$blob,linked")
                    $null = Git @('commit', '-qm', 'synthetic symlink'); $script:head = Git @('rev-parse', 'HEAD')
                    $null = Git @('checkout', '-q', $script:base)
                }
                default {
                    $path = Open-Compact
                    $archive = [IO.Compression.ZipFile]::Open($path, [IO.Compression.ZipArchiveMode]::Update)
                    try {
                        $name = switch ($scenario) { 'path-traversal' { '../escape.txt' }; 'case-member' { 'source/APP.txt' }; default { 'source/app.txt' } }
                        if ($scenario -eq 'hash-forgery') {
                            $sums = (Read-ZipText $archive 'SHA256SUMS.txt') -replace '(?m)^[a-f0-9]{64}  source/app.txt$', (('0' * 64) + '  source/app.txt')
                            $archive.GetEntry('SHA256SUMS.txt').Delete(); $entry = $archive.CreateEntry('SHA256SUMS.txt')
                            $writer = [IO.StreamWriter]::new($entry.Open()); try { $writer.Write($sums) } finally { $writer.Dispose() }
                        } else {
                            $entry = $archive.CreateEntry($name)
                            if ($scenario -eq 'linked-member') { $entry.ExternalAttributes = [int](0xA000 -shl 16) }
                            $writer = [IO.StreamWriter]::new($entry.Open()); try { $writer.Write('synthetic tamper') } finally { $writer.Dispose() }
                        }
                    } finally { $archive.Dispose() }
                    $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
                    Assert-True ($verified.Exit -ne 0) "Compact accepted unsafe archive $scenario"
                    return
                }
            }
            $actual = Invoke-Package -Compact
            Assert-True ($actual.Exit -ne 0) "Compact accepted unsafe Git input $scenario"
        }
    }
    Case 'compact committed validation kept once with runtime CI recorded separately' {
        Write-Fixture 'docs/evidence/TEST-001/validation.json' (@{ checks = @(@{ name = 'fixture'; command = 'fixture'; status = 'PASS'; exitCode = 0; output = 'isolated fixture only' }); ci = @{ status = 'NOT_VERIFIED' } } | ConvertTo-Json -Depth 6)
        $script:head = Commit-Fixture
        $actual = Invoke-Package -Compact -Extra @('-EvidencePath', 'docs/evidence/TEST-001/validation.json', '-CiRunId', '123', '-CiRunUrl', 'https://github.com/on-dotnet/ontology-platform/actions/runs/123', '-CiCommit', $script:head, '-CiConclusion', 'success')
        Assert-True ($actual.Exit -eq 0) "Validation compact failed: $($actual.Output)"
        $path = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
        $archive = [IO.Compression.ZipFile]::OpenRead($path)
        try {
            $raw = Read-ZipText $archive 'review-evidence/TEST-001/validation.json' | ConvertFrom-Json
            $ci = Read-ZipText $archive 'git/ci.json' | ConvertFrom-Json
            Assert-True ($raw.ci.status -eq 'NOT_VERIFIED' -and $ci.status -eq 'PASS' -and $ci.commit -eq $script:head -and $null -eq $archive.GetEntry('review-evidence/validation.json')) 'Raw validation duplicated or rewritten'
        } finally { $archive.Dispose() }
        $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
        Assert-True ($verified.Exit -eq 0) "Raw validation reopen failed: $($verified.Output)"
    }
    Case 'resource inspector is read only and default Docker NOT_RUN' {
        $null = Git @('update-ref', 'refs/remotes/origin/main', $script:head)
        Write-Fixture 'untracked.txt' "pending untouched`n"
        $before = Git @('status', '--porcelain=v1', '-uall')
        $beforeRefs = Git @('show-ref')
        $inspector = Join-Path (Split-Path $PackageScript -Parent) 'maintenance/inspect-resources.ps1'
        $indexPath = Join-Path $script:repo '.git/index'
        (Get-Item (Join-Path $script:repo 'app.txt')).LastWriteTimeUtc = [DateTime]::UtcNow.AddSeconds(-60)
        $indexBefore = (Get-FileHash -LiteralPath $indexPath -Algorithm SHA256).Hash
        $output = & pwsh -NoProfile -File $inspector -Root $script:repo 2>&1
        Assert-True ($LASTEXITCODE -eq 0) "Inspector failed: $($output -join ' ')"
        Assert-True ((Get-FileHash -LiteralPath $indexPath -Algorithm SHA256).Hash -ceq $indexBefore) 'Read-only inspector rewrote index cache'
        $inventory = ($output -join "`n") | ConvertFrom-Json
        Assert-True ($inventory.mode -eq 'READ_ONLY' -and $inventory.docker.status -eq 'NOT_RUN' -and @($inventory.mutations).Count -eq 0 -and (Git @('status', '--porcelain=v1', '-uall')) -eq $before -and (Git @('show-ref')) -eq $beforeRefs) 'Inspector changed files or refs'
    }
    Case 'committed snapshot, Unicode, full diff and reopened ZIP' {
        $actual = Invoke-Package
        Assert-True ($actual.Exit -eq 0) "Positive fixture failed: $($actual.Output)"
        $zip = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')
        Assert-True ($zip.Count -eq 1) 'Expected exactly one delivery ZIP'
        $archive = [IO.Compression.ZipFile]::OpenRead($zip[0].FullName)
        try {
            foreach ($name in @('REVIEW_SUMMARY.md', 'manifest.json', 'git/diff.patch', 'git/status.txt', 'git/commits.txt', 'git/changed-files.txt', 'git/diff-check.txt', 'source/app.txt', 'docs/tasks/TEST-001.md', 'evidence/TEST-001/result.txt', 'SHA256SUMS.txt')) {
                Assert-True ($null -ne $archive.GetEntry($name)) "Missing $name"
            }
            $reader = [IO.StreamReader]::new($archive.GetEntry('manifest.json').Open())
            try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
            Assert-True ($manifest.baseSha -eq $script:base -and $manifest.headSha -eq $script:head) 'Manifest commits differ'
            Assert-True ($manifest.ci.status -eq 'NOT_VERIFIED') 'Unknown CI was promoted'
            Assert-True ($manifest.checks[0].status -eq 'NOT_RUN') 'Absent evidence was promoted'
        } finally { $archive.Dispose() }
        $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $zip[0].FullName)
        Assert-True ($verified.Exit -eq 0) "External reopen failed: $($verified.Output)"
    }
    Case 'color.ui always cannot contaminate machine-readable patch' {
        # 真实仓库局部配置，模拟用户always彩色偏好；不修改用户或机器配置。
        $null = Git @('config', 'color.ui', 'always')
        $actual = Invoke-Package
        Assert-True ($actual.Exit -eq 0) "Color fixture generation failed: $($actual.Output)"
        $zip = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0]
        $patchPath = Join-Path $script:repo 'artifacts/reviews/extracted.patch'
        $archive = [IO.Compression.ZipFile]::OpenRead($zip.FullName)
        try {
            $buffer = [IO.MemoryStream]::new()
            $stream = $archive.GetEntry('git/diff.patch').Open()
            try { $stream.CopyTo($buffer); $patchBytes = $buffer.ToArray() } finally { $stream.Dispose(); $buffer.Dispose() }
        } finally { $archive.Dispose() }
        [IO.File]::WriteAllBytes($patchPath, $patchBytes)
        $numstat = & $script:gitExecutable -C $script:repo apply --numstat $patchPath 2>&1
        $applyExit = $LASTEXITCODE
        $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $zip.FullName)
        $escapeCount = @($patchBytes | Where-Object { $_ -eq 27 }).Count
        Assert-True ($escapeCount -eq 0 -and $applyExit -eq 0 -and $verified.Exit -eq 0) "Color contamination: ANSI=$escapeCount; git apply --numstat exit=$applyExit; VerifyOnly exit=$($verified.Exit)"
        Assert-True (($numstat -join "`n").Contains('app.txt')) 'Patch parser did not observe expected source change'
    }
    Case 'PASS requires real command evidence' {
        $actual = Invoke-Package -DeclaredStatus PASS
        Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('EVIDENCE_REQUIRED')) 'PASS accepted without command evidence'
    }
    Case 'non-ancestor commits' {
        $null = Git @('checkout', '--orphan', 'unrelated')
        $null = Git @('rm', '-rf', '.')
        Write-Fixture '.gitignore' "artifacts/`n"
        Write-Fixture 'other.txt' "unrelated`n"
        $script:base = Commit-Fixture
        $null = Git @('checkout', '-q', 'master')
        Expect-Rejected 'ANCESTRY'
    }
    Case 'dirty tracked delivery' { Write-Fixture 'app.txt' "dirty`n"; Expect-Rejected 'DIRTY_TREE' }
    Case 'untracked delivery' { Write-Fixture 'pending.md' "untracked`n"; Expect-Rejected 'DIRTY_TREE' }
    foreach ($forbidden in @('.env', '.env.production', '.ssh/id', '.codex/auth.json', 'auth/config.json', 'cert.pem', 'nested/bin/output', '.tools/sdk/file', 'models/weights.dat', 'state.db', '.cache/item', 'node_modules/item')) {
        $path = $forbidden
        Case "forbidden committed member $path" {
            Write-Fixture $path "simulated forbidden material`n"
            $script:head = Commit-Fixture
            Expect-Rejected 'FORBIDDEN_PATH'
        }
    }
    Case 'synthetic token in source' {
        Write-Fixture 'settings.txt' (('gh' + 'p_' + ('A' * 36)) + "`n")
        $script:head = Commit-Fixture
        Expect-Rejected 'SECRET_PATTERN'
    }
    Case 'removed synthetic token retained in patch' {
        Write-Fixture 'settings.txt' (('gh' + 'p_' + ('B' * 36)) + "`n")
        $script:base = Commit-Fixture
        Write-Fixture 'settings.txt' "redacted`n"
        $script:head = Commit-Fixture
        Expect-Rejected 'SECRET_PATTERN'
    }
    foreach ($injection in @('.git/config', '.env', '../escape.txt', 'source/app.txt')) {
        $member = $injection
        Case "reopened archive rejects injected or changed member $member" {
            $actual = Invoke-Package
            Assert-True ($actual.Exit -eq 0) "Fixture generation failed: $($actual.Output)"
            $zip = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0]
            $archive = [IO.Compression.ZipFile]::Open($zip.FullName, [IO.Compression.ZipArchiveMode]::Update)
            try {
                if ($member -eq 'source/app.txt') { $archive.GetEntry($member).Delete() }
                $entry = $archive.CreateEntry($member)
                $writer = [IO.StreamWriter]::new($entry.Open())
                try { $writer.Write('simulated tamper') } finally { $writer.Dispose() }
            } finally { $archive.Dispose() }
            $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $zip.FullName)
            Assert-True ($verified.Exit -ne 0) 'Tampered archive accepted'
        }
    }
    Case 'git archive export-ignore cannot omit committed source' {
        Write-Fixture '.gitattributes' "app.txt export-ignore`n"
        $script:head = Commit-Fixture
        Expect-Rejected 'SNAPSHOT_MISMATCH'
    }
    Case 'git archive export-subst cannot rewrite committed source' {
        Write-Fixture '.gitattributes' "app.txt export-subst`n"
        Write-Fixture 'app.txt' ('$Format:%H$' + "`n")
        $script:head = Commit-Fixture
        Expect-Rejected 'SNAPSHOT_MISMATCH'
    }
    Case 'git symlink blob cannot silently become source' {
        $blob = Git @('hash-object', 'app.txt')
        $null = Git @('update-index', '--add', '--cacheinfo', "120000,$blob,linked-file")
        $null = Git @('commit', '-qm', 'simulated symlink')
        $script:head = Git @('rev-parse', 'HEAD')
        # 将工作树切换到另一个干净提交；快照仍明确指向含链接的提交。
        $null = Git @('checkout', '-q', $script:base)
        Expect-Rejected 'UNSUPPORTED_TREE'
    }
    Case 'committed submodule cannot be omitted by git archive' {
        $null = Git @('update-index', '--add', '--cacheinfo', "160000,$script:head,vendor-module")
        $null = Git @('commit', '-qm', 'simulated submodule')
        $script:head = Git @('rev-parse', 'HEAD')
        $null = Git @('checkout', '-q', $script:base)
        Expect-Rejected 'UNSUPPORTED_TREE'
    }
    Case 'complete patch rejects removed forbidden environment member' {
        Write-Fixture '.env' "simulation only`n"
        $script:base = Commit-Fixture
        $null = Git @('rm', '.env')
        $script:head = Commit-Fixture
        Expect-Rejected 'FORBIDDEN_PATH'
    }
    Case 'reopened archive rejects payload tamper even after checksum rewrite' {
        $actual = Invoke-Package
        Assert-True ($actual.Exit -eq 0) "Fixture generation failed: $($actual.Output)"
        $zip = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0]
        $archive = [IO.Compression.ZipFile]::Open($zip.FullName, [IO.Compression.ZipArchiveMode]::Update)
        try {
            $replacement = [Text.Encoding]::UTF8.GetBytes('tamper with recomputed hash')
            $archive.GetEntry('source/app.txt').Delete()
            $entry = $archive.CreateEntry('source/app.txt')
            $stream = $entry.Open()
            try { $stream.Write($replacement) } finally { $stream.Dispose() }
            $reader = [IO.StreamReader]::new($archive.GetEntry('SHA256SUMS.txt').Open())
            try { $sums = $reader.ReadToEnd() } finally { $reader.Dispose() }
            $hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($replacement)).ToLowerInvariant()
            $sums = $sums -replace '(?m)^[a-f0-9]{64}  source/app.txt$', ($hash + '  source/app.txt')
            $archive.GetEntry('SHA256SUMS.txt').Delete()
            $writer = [IO.StreamWriter]::new($archive.CreateEntry('SHA256SUMS.txt').Open())
            try { $writer.Write($sums) } finally { $writer.Dispose() }
        } finally { $archive.Dispose() }
        $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $zip.FullName)
        Assert-True ($verified.Exit -ne 0 -and $verified.Output.Contains('HEAD_MISMATCH')) 'Rehashed payload escaped committed-head comparison'
    }
    Case 'missing checksum/member is rejected on reopen' {
        $actual = Invoke-Package
        Assert-True ($actual.Exit -eq 0) "Fixture generation failed: $($actual.Output)"
        $zip = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0]
        $archive = [IO.Compression.ZipFile]::Open($zip.FullName, [IO.Compression.ZipArchiveMode]::Update)
        try { $archive.GetEntry('source/app.txt').Delete() } finally { $archive.Dispose() }
        $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $zip.FullName)
        Assert-True ($verified.Exit -ne 0) 'Missing member accepted'
    }
    Case 'CI PASS cannot be inferred without run metadata' {
        Write-Fixture 'docs/evidence/TEST-001/checks.json' (@{ checks = @(@{ name = 'fixture'; command = 'fixture'; status = 'PASS'; exitCode = 0; output = 'actual simulated fixture result' }); ci = @{ status = 'PASS' } } | ConvertTo-Json -Depth 6)
        $script:head = Commit-Fixture
        $actual = Invoke-Package -Extra @('-EvidencePath', 'docs/evidence/TEST-001/checks.json')
        Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('CI_EVIDENCE')) 'CI PASS accepted without run metadata'
    }
    Case 'explicit CI metadata avoids self-referential commit evidence' {
        Write-Fixture 'docs/evidence/TEST-001/checks.json' (@{ checks = @(@{ name = 'fixture'; command = 'fixture'; status = 'PASS'; exitCode = 0; output = 'isolated fixture only, no real remote CI claim' }); ci = @{ status = 'NOT_VERIFIED' } } | ConvertTo-Json -Depth 6)
        $script:head = Commit-Fixture
        $actual = Invoke-Package -DeclaredStatus PASS -Extra @('-EvidencePath', 'docs/evidence/TEST-001/checks.json', '-CiRunId', '123', '-CiRunUrl', 'https://github.com/on-dotnet/ontology-platform/actions/runs/123', '-CiCommit', $script:head, '-CiConclusion', 'success')
        Assert-True ($actual.Exit -eq 0) "Explicit CI fixture rejected: $($actual.Output)"
    }
    Case 'existing delivery ZIP is preserved' {
        $actual = Invoke-Package
        Assert-True ($actual.Exit -eq 0) "Fixture generation failed: $($actual.Output)"
        $zip = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0]
        $before = (Get-FileHash $zip.FullName).Hash
        $again = Invoke-Package
        Assert-True ($again.Exit -ne 0 -and $again.Output.Contains('OUTPUT_EXISTS')) 'Existing ZIP was overwritten'
        Assert-True ((Get-FileHash $zip.FullName).Hash -ceq $before) 'Existing delivery bytes changed'
    }
    Case 'valid committed evidence preserves command and status' {
        Write-Fixture 'docs/evidence/TEST-001/checks.json' (@{ checks = @(@{ name = 'fixture'; command = 'pwsh fixture.ps1'; status = 'PASS'; exitCode = 0; output = '1 assertion passed' }); ci = @{ status = 'NOT_VERIFIED' } } | ConvertTo-Json -Depth 6)
        $script:head = Commit-Fixture
        $actual = Invoke-Package -Extra @('-EvidencePath', 'docs/evidence/TEST-001/checks.json')
        Assert-True ($actual.Exit -eq 0) "Evidence fixture failed: $($actual.Output)"
    }
} finally {
    # 仅清理本测试创建的系统临时目录；先确认绝对路径边界。
    $resolved = [IO.Path]::GetFullPath($fixtureRoot)
    $temporary = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolved.StartsWith($temporary, [StringComparison]::OrdinalIgnoreCase) -and (Split-Path $resolved -Leaf) -like 'ontology-review-tests-*') {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
    }
}
if ($results.Count -eq 0) { throw 'No matching review-package tests ran' }
$failed = @($results | Where-Object Status -eq 'FAIL').Count
Write-Output "ReviewPackage: $($results.Count) tests, $failed failures; product/container tests NOT_RUN."
if ($failed -gt 0) { throw 'Review package self-tests failed' }
