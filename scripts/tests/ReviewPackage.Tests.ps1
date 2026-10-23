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
    param([string[]]$Extra = @(), [switch]$Verify, [string]$DeclaredStatus = 'PARTIAL')
    $arguments = @('-NoProfile', '-File', $PackageScript, '-Root', $script:repo)
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
