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
function Write-LocalFixture {
    param([string]$Path, [string]$Text)
    Write-Fixture $Path ($Text.Replace("`r`n", "`n").Replace("`r", "`n").TrimEnd("`n") + "`n")
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
    param([string[]]$Extra = @(), [switch]$Verify, [switch]$Compact, [switch]$V3, [switch]$Local, [string]$DeclaredStatus = 'PARTIAL')
    $arguments = @('-NoProfile', '-File', $PackageScript, '-Root', $script:repo)
    if (-not $Verify -and -not $Compact -and -not $V3 -and -not $Local) { $arguments += @('-SchemaVersion', '1') }
    if ($Compact) { $arguments += @('-SchemaVersion', '2') }
    if (-not $Verify) { $arguments += @('-BaseSha', $script:base, '-HeadSha', $script:head, '-TaskId', 'TEST-001', '-Status', $DeclaredStatus) }
    $savedPath = $env:PATH
    $savedHead = $env:REVIEW_FIXTURE_CI_HEAD
    try {
        $env:PATH = $script:fakeGhDirectory + [IO.Path]::PathSeparator + $savedPath
        $env:REVIEW_FIXTURE_CI_HEAD = $script:head
        if ($Local) { $arguments += @('-ValidationSource', 'LOCAL') }
        if ($V3) { $arguments += @('-ValidationSource', 'GITHUB', '-CiRunId', '123', '-CiRunUrl', 'https://github.com/on-dotnet/ontology-platform/actions/runs/123', '-CiCommit', $script:head, '-CiConclusion', 'success') }
        $output = & pwsh @arguments @Extra 2>&1
        $code = $LASTEXITCODE
    } finally { $env:PATH = $savedPath; $env:REVIEW_FIXTURE_CI_HEAD = $savedHead }

    return [pscustomobject]@{ Exit = $code; Output = ($output -join "`n") }
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
    catch {
        $status = if ($_.Exception.Message.StartsWith('TEST_NOT_RUN:')) { 'NOT_RUN' } else { 'FAIL' }
        $results.Add([pscustomobject]@{ Name = $Name; Status = $status }); Write-Output "${status}: $Name -- $($_.Exception.Message)"
    }
}
try {
    $null = New-Item -ItemType Directory -Force $fixtureRoot
    $script:fakeGhDirectory = Join-Path $fixtureRoot 'toolbin'
    $null = New-Item -ItemType Directory -Force $script:fakeGhDirectory
    $fake = @'
#!/usr/bin/env python3
import json,os,sys
h=os.environ['REVIEW_FIXTURE_CI_HEAD']; mode=os.environ.get('REVIEW_FIXTURE_CI_MODE','')
if mode=='unavailable': sys.exit(9)
if mode=='wrong-head': h='f'*40
jobs=[dict(databaseId=i+1,name=n,status='completed',conclusion='success',url='https://github.com/on-dotnet/ontology-platform/actions/runs/123/job/'+str(i+1)) for i,n in enumerate(['engineering','governance-integration'])]
if mode=='missing-job': jobs.pop()
if mode=='failed-job': jobs[0]['conclusion']='failure'
print(json.dumps(dict(databaseId=123,headSha=h,url='https://github.com/on-dotnet/ontology-platform/actions/runs/123',status='completed',conclusion='success',jobs=jobs)))
'@
    [IO.File]::WriteAllText((Join-Path $script:fakeGhDirectory 'gh'), $fake + "`n", [Text.UTF8Encoding]::new($false))
    if (-not $IsWindows) { & chmod +x (Join-Path $script:fakeGhDirectory 'gh') }
    function Read-ZipText($Archive, [string]$Name) {
        $reader = [IO.StreamReader]::new($Archive.GetEntry($Name).Open())
        try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
    }
    function Open-Compact {
        $actual = Invoke-Package -Compact
        Assert-True ($actual.Exit -eq 0) "Compact creation failed: $($actual.Output)"
        return @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
    }
    function Open-V3 {
        $actual = Invoke-Package -V3
        Assert-True ($actual.Exit -eq 0) "V3 creation failed: $($actual.Output)"
        return @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
    }
    function Replace-ZipMember($Archive, [string]$Name, [byte[]]$Bytes) {
        if ($null -ne $Archive.GetEntry($Name)) { $Archive.GetEntry($Name).Delete() }
        $stream = $Archive.CreateEntry($Name).Open()
        try { $stream.Write($Bytes) } finally { $stream.Dispose() }
        $sums = Read-ZipText $Archive 'SHA256SUMS.txt'
        $hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()
        $sums = [regex]::Replace($sums, '(?m)^[a-f0-9]{64}  ' + [regex]::Escape($Name) + '$', $hash + '  ' + $Name)
        $Archive.GetEntry('SHA256SUMS.txt').Delete()
        $writer = [IO.StreamWriter]::new($Archive.CreateEntry('SHA256SUMS.txt').Open())
        try { $writer.Write($sums) } finally { $writer.Dispose() }
    }
    foreach ($version in @(1, 2, 3)) {
        $schema = $version
        Case "validation metadata V$schema raw bytes remain recoverable with normalized checks and ci" {
            $evidencePath = 'docs/evidence/TEST-001/metadata-validation.json'
            $rawText = @'
{
 "checks": [{"name":"actual-check","command":"fixture actual command","status":"PASS","exitCode":0,"output":"one actual assertion passed"}],
 "ci": {"status":"NOT_VERIFIED"},
 "note": "non-authoritative source metadata must remain unchanged",
 "context": {"owner":"fixture", "nested":{"status":"UNKNOWN","checks":["context only"]}}
}
'@
            Write-Fixture $evidencePath ($rawText + "`n"); $script:head = Commit-Fixture
            $options = @{}
            if ($schema -eq 2) { $options.Compact = $true }
            if ($schema -eq 3) { $options.V3 = $true }
            $actual = Invoke-Package @options -Extra @('-EvidencePath', $evidencePath)
            Assert-True ($actual.Exit -eq 0) "Metadata V$schema creation failed: $($actual.Output)"
            $path = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
            $archive = [IO.Compression.ZipFile]::OpenRead($path)
            try {
                $m = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json -AsHashtable
                Assert-True (-not $m.ContainsKey('note') -and -not $m.ContainsKey('context') -and $m.checks[0].status -eq 'PASS') 'Non-authoritative metadata entered normalized statuses'
                $mapping = @($m.sourceMembers | Where-Object { $_.gitPath -ceq $evidencePath })
                Assert-True ($mapping.Count -gt 0) 'Raw validation missing from source mapping'
                $rawBytes = [IO.File]::ReadAllBytes((Join-Path $script:repo $evidencePath))
                $hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($rawBytes)).ToLowerInvariant()
                $entry = $archive.GetEntry($mapping[0].archivePath)
                $buffer = [IO.MemoryStream]::new(); $stream = $entry.Open()
                try { $stream.CopyTo($buffer); $stored = $buffer.ToArray() } finally { $stream.Dispose(); $buffer.Dispose() }
                Assert-True ([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($stored)).ToLowerInvariant() -eq $hash -and $stored.Length -eq $rawBytes.Length) 'Original metadata validation bytes were rewritten'
                $raw = [Text.Encoding]::UTF8.GetString($stored) | ConvertFrom-Json -AsHashtable
                Assert-True ($raw.note -eq 'non-authoritative source metadata must remain unchanged' -and $raw.context.nested.status -eq 'UNKNOWN' -and $raw.ci.status -eq 'NOT_VERIFIED') 'Original note/context/CI metadata lost'
                $oid = Git @('rev-parse', ($script:head + ':' + $evidencePath))
                if ($schema -ge 2) {
                    Assert-True ($mapping.Count -eq 1 -and $mapping[0].blobOid -eq $oid) 'Raw metadata duplicated or Git recovery OID differs'
                    $sameSize = @($archive.Entries | Where-Object { $_.Length -eq $rawBytes.Length })
                    $copies = 0
                    foreach ($candidate in $sameSize) {
                        $stream = $candidate.Open(); $sha = [Security.Cryptography.SHA256]::Create()
                        try { if ([Convert]::ToHexString($sha.ComputeHash($stream)).ToLowerInvariant() -eq $hash) { $copies++ } } finally { $sha.Dispose(); $stream.Dispose() }
                    }
                    Assert-True ($copies -eq 1) 'Raw validation payload must appear once in compact schemas'
                } else {
                    $normalized = Read-ZipText $archive 'evidence/validation.json' | ConvertFrom-Json -AsHashtable
                    Assert-True ($normalized.get_Count() -eq 2 -and $normalized.ContainsKey('checks') -and $normalized.ContainsKey('ci')) 'V1 normalized validation included non-authoritative metadata'
                }
            } finally { $archive.Dispose() }
            $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
            Assert-True ($verified.Exit -eq 0) "Metadata V$schema independent reopen failed: $($verified.Output)"
        }
        Case "validation metadata V$schema cannot mask FAIL checks or allow overall PASS" {
            $evidencePath = 'docs/evidence/TEST-001/failed-validation.json'
            Write-Fixture $evidencePath (@{ checks = @(@{ name = 'actual-failure'; command = 'fixture fails'; status = 'FAIL'; exitCode = 1; output = 'actual failure is retained' }); ci = @{ status = 'NOT_VERIFIED' }; note = 'PASS is merely text here'; context = @{ status = 'PASS'; checks = @(@{ status = 'PASS' }) } } | ConvertTo-Json -Depth 8)
            $script:head = Commit-Fixture
            $options = @{}
            if ($schema -eq 2) { $options.Compact = $true }
            if ($schema -eq 3) { $options.V3 = $true }
            $actual = Invoke-Package @options -Extra @('-EvidencePath', $evidencePath)
            Assert-True ($actual.Exit -eq 0) "FAIL metadata V$schema PARTIAL creation failed: $($actual.Output)"
            $path = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
            $before = (Get-FileHash $path -Algorithm SHA256).Hash
            $archive = [IO.Compression.ZipFile]::OpenRead($path)
            try {
                $m = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json
                Assert-True ($m.checks[0].status -eq 'FAIL' -and $m.checks[0].exitCode -eq 1 -and $m.checks[0].output -eq 'actual failure is retained') 'FAIL check changed by extra metadata'
            } finally { $archive.Dispose() }
            $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
            Assert-True ($verified.Exit -eq 0) "FAIL metadata V$schema reopen failed: $($verified.Output)"
            $rejected = Invoke-Package @options -DeclaredStatus PASS -Extra @('-EvidencePath', $evidencePath)
            Assert-True ($rejected.Exit -ne 0 -and $rejected.Output.Contains('EVIDENCE_REQUIRED')) 'Extra metadata allowed overall PASS despite FAIL check'
            Assert-True ((Get-FileHash $path -Algorithm SHA256).Hash -eq $before) 'Rejected PASS changed valid PARTIAL archive'
        }
    }
    Case 'V3 53 PNG and 55256 ignored paths compact fixture with recoverable index' {
        # 标准库生成53张真实可解码、不同像素的PNG，而非扩展名伪装或随机尾随字节。
        $pngProgram = @'
import pathlib,random,struct,sys,zlib
root=pathlib.Path(sys.argv[1]); folder=root/'docs/evidence/TEST-001/screenshots'; folder.mkdir(parents=True)
rng=random.Random(53055256)
def chunk(kind,data):
    return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
for i in range(53):
    raw=b''.join(b'\x00'+rng.randbytes(256*3) for row in range(800))
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',256,800,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
    (folder/('shot-%d.png'%i)).write_bytes(png)
'@
        & python3 -c $pngProgram $script:repo
        Assert-True ($LASTEXITCODE -eq 0) 'PNG fixture generation failed'
        $shots = @()
        for ($i = 0; $i -lt 4; $i++) {
            $shots += @{ path = "docs/evidence/TEST-001/screenshots/shot-$i.png"; page = "page-$i"; theme = 'light'; viewport = '256x800'; stable = $true }
        }
        Write-Fixture 'docs/evidence/TEST-001/review-screenshots.json' (@{ schemaVersion = 1; screenshots = $shots } | ConvertTo-Json -Depth 6)
        Write-Fixture '.gitignore' "artifacts/`nignored-fixture/`n"
        $script:head = Commit-Fixture
        $ignoredDirectory = Join-Path $script:repo 'ignored-fixture'
        $null = [IO.Directory]::CreateDirectory($ignoredDirectory)
        for ($i = 0; $i -lt 55256; $i++) { [IO.File]::WriteAllText((Join-Path $ignoredDirectory "item-$i.txt"), '123') }
        $path = Open-V3
        $compactSize = (Get-Item $path).Length
        $archive = [IO.Compression.ZipFile]::OpenRead($path)
        try {
            $m = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json
            $index = @(Read-ZipText $archive 'evidence-index.json' | ConvertFrom-Json)
            $png = @($archive.Entries | Where-Object FullName -Like '*.png')
            Assert-True ($png.Count -eq 4 -and $m.screenshotPolicy.compressedBytes -le 3MB) 'Stable representative screenshot budget not enforced'
            Assert-True ($m.ignoredInventory.count -eq 55256 -and $m.ignoredInventory.estimatedBytes -eq 165768 -and $m.ignoredInventory.groups.Count -eq 1 -and $m.ignoredInventory.groups[0].examples.Count -le 2) 'Ignored aggregation lost count/size or expanded unbounded'
            Assert-True ($null -eq $m.PSObject.Properties['excludedIgnoredPaths']) 'Full ignored path array retained'
            $pngIndex = @($index | Where-Object gitPath -Like '*.png')
            Assert-True ($pngIndex.Count -eq 53 -and @($pngIndex | Where-Object { $null -eq $_.archivePath }).Count -eq 49) 'All omitted screenshots must be indexed'
            foreach ($item in $pngIndex) {
                $blob = Git @('rev-parse', ($item.commit + ':' + $item.gitPath))
                $fileBytes = [IO.File]::ReadAllBytes((Join-Path $script:repo $item.gitPath))
                $hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($fileBytes)).ToLowerInvariant()
                Assert-True ($blob -eq $item.blobOid -and $hash -eq $item.sha256 -and $fileBytes.Length -eq $item.sizeBytes) 'Screenshot recovery OID/hash/size mismatch'
            }
            $payloadHashes = @($m.sourceMembers | Select-Object -ExpandProperty archivePath -Unique)
            Assert-True (@($archive.Entries | Where-Object { $_.FullName.StartsWith('source/') -or $_.FullName.StartsWith('review-evidence/TEST-001/') }).Count -eq $payloadHashes.Count) 'Unmapped or duplicated payload exists'
        } finally { $archive.Dispose() }
        $localList = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.paths.txt')[0]
        Assert-True ((Get-FileHash $localList.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -eq $m.ignoredInventory.listSha256) 'Local-only ignored inventory SHA does not match'
        $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
        Assert-True ($verified.Exit -eq 0) "Large fixture V3 reopen failed: $($verified.Output)"
        Move-Item -LiteralPath $path -Destination ($path + '.v3')
        $legacy = Invoke-Package -Compact
        Assert-True ($legacy.Exit -eq 0) "V2 comparison failed: $($legacy.Output)"
        $legacySize = (Get-Item $path).Length
        Assert-True ($compactSize -lt 4MB -and $compactSize -lt ($legacySize / 5)) "V3 size regression compact=$compactSize V2=$legacySize"
        Write-Output "OBSERVED V3 fixture: 53PNG, 55256ignored; V3=$compactSize V2=$legacySize bytes"
    }
    foreach ($mode in @('wrong-head', 'missing-job', 'failed-job')) {
        $scenario = $mode
        Case "V3 refuses actual GitHub $scenario" {
            $previous = $env:REVIEW_FIXTURE_CI_MODE
            try {
                $env:REVIEW_FIXTURE_CI_MODE = $scenario
                $actual = Invoke-Package -V3
                Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('CI_EVIDENCE')) 'Forged or incomplete CI accepted'
            } finally { $env:REVIEW_FIXTURE_CI_MODE = $previous }
        }
    }
    foreach ($negative in @('dirty', 'untracked', 'non-ancestor', 'case-collision', 'forbidden', 'secret', 'symlink', 'diff-check')) {
        $scenario = $negative
        Case "V3 refuses Git input $scenario" {
            switch ($scenario) {
                'dirty' { Write-Fixture 'app.txt' "dirty`n" }
                'untracked' { Write-Fixture 'pending.txt' "pending`n" }
                'non-ancestor' {
                    $null = Git @('checkout', '--orphan', 'other'); $null = Git @('rm', '-rf', '.')
                    Write-Fixture '.gitignore' "artifacts/`n"; Write-Fixture 'other.txt' "other`n"; $script:base = Commit-Fixture
                    $null = Git @('checkout', '-q', 'master')
                }
                'case-collision' {
                    $blob = Git @('hash-object', 'app.txt'); $null = Git @('update-index', '--add', '--cacheinfo', "100644,$blob,APP.txt")
                    $null = Git @('commit', '-qm', 'case collision'); $script:head = Git @('rev-parse', 'HEAD'); $null = Git @('checkout', '-q', $script:base)
                }
                'forbidden' { Write-Fixture '.env' "simulation`n"; $script:head = Commit-Fixture }
                'secret' { Write-Fixture 'config.txt' (('gh' + 'p_' + ('Q' * 36)) + "`n"); $script:head = Commit-Fixture }
                'symlink' {
                    $blob = Git @('hash-object', 'app.txt'); $null = Git @('update-index', '--add', '--cacheinfo', "120000,$blob,linked")
                    $null = Git @('commit', '-qm', 'synthetic symlink'); $script:head = Git @('rev-parse', 'HEAD'); $null = Git @('checkout', '-q', $script:base)
                }
                'diff-check' { Write-Fixture 'app.txt' "trailing  `n"; $script:head = Commit-Fixture }
            }
            $actual = Invoke-Package -V3
            Assert-True ($actual.Exit -ne 0) "V3 accepted invalid $scenario"
            Assert-True (@(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip' -ErrorAction SilentlyContinue).Count -eq 0) 'Rejected input published a ZIP'
        }
    }
    foreach ($negative in @('missing-index', 'forged-index', 'forged-ci', 'hash', 'path-traversal', 'duplicate', 'case-member', 'symlink-member', 'forged-text-diff')) {
        $scenario = $negative
        Case "V3 reopen rejects $scenario" {
            $path = Open-V3
            $archive = [IO.Compression.ZipFile]::Open($path, [IO.Compression.ZipArchiveMode]::Update)
            try {
                switch ($scenario) {
                    'missing-index' { $archive.GetEntry('evidence-index.json').Delete() }
                    'forged-index' {
                        $index = @(Read-ZipText $archive 'evidence-index.json' | ConvertFrom-Json); $index[0].blobOid = '0' * 40
                        Replace-ZipMember $archive 'evidence-index.json' ([Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $index -Depth 12)))
                    }
                    'forged-ci' {
                        $m = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json -AsHashtable
                        $m.runtimeCi.jobs[0].id = '999'; $m.ci.jobs[0].id = '999'
                        Replace-ZipMember $archive 'manifest.json' ([Text.Encoding]::UTF8.GetBytes(($m | ConvertTo-Json -Depth 16)))
                    }
                    'hash' { Replace-ZipMember $archive 'source/app.txt' ([Text.Encoding]::UTF8.GetBytes('rehashed malicious replacement')) }
                    'forged-text-diff' { Replace-ZipMember $archive 'git/diff-text.patch' ([Text.Encoding]::UTF8.GetBytes('truncated text diff')) }
                    default {
                        $name = switch ($scenario) { 'path-traversal' { '../escape.txt' }; 'case-member' { 'source/APP.txt' }; default { 'source/app.txt' } }
                        $entry = $archive.CreateEntry($name)
                        if ($scenario -eq 'symlink-member') { $entry.ExternalAttributes = [int](0xA000 -shl 16) }
                        $writer = [IO.StreamWriter]::new($entry.Open()); try { $writer.Write('synthetic') } finally { $writer.Dispose() }
                    }
                }
            } finally { $archive.Dispose() }
            $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
            Assert-True ($verified.Exit -ne 0) "V3 accepted archive $scenario"
        }
    }
    foreach ($negative in @('count', 'size', 'unknown-count', 'duplicate-group', 'too-many-examples', 'scan-time', 'extra-field', 'wrong-type')) {
        $scenario = $negative
        Case "V3 ignored inventory rehashed forgery rejects $scenario" {
            Write-Fixture '.gitignore' "artifacts/`nignored/`n"; $script:head = Commit-Fixture
            Write-Fixture 'ignored/one.txt' 'metadata-only'
            $path = Open-V3
            $archive = [IO.Compression.ZipFile]::Open($path, [IO.Compression.ZipArchiveMode]::Update)
            try {
                $m = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json -AsHashtable
                switch ($scenario) {
                    'count' { $m.ignoredInventory.count++ }
                    'size' { $m.ignoredInventory.estimatedBytes++ }
                    'unknown-count' { $m.ignoredInventory.groups[0].unknownSizeCount = 2 }
                    'duplicate-group' { $m.ignoredInventory.groups += $m.ignoredInventory.groups[0] }
                    'too-many-examples' { $m.ignoredInventory.groups[0].examples = @('one', 'two', 'three') }
                    'scan-time' { $m.ignoredInventory.scannedAt = 'not a date' }
                    'extra-field' { $m.ignoredInventory.fullPaths = @('unbounded', 'list') }
                    'wrong-type' { $m.ignoredInventory.count = '1' }
                }
                Replace-ZipMember $archive 'manifest.json' ([Text.Encoding]::UTF8.GetBytes(($m | ConvertTo-Json -Depth 16)))
            } finally { $archive.Dispose() }
            $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
            Assert-True ($verified.Exit -ne 0 -and $verified.Output.Contains('MANIFEST_INVALID')) "Rehashed ignored inventory forgery $scenario accepted: $($verified.Output)"
        }
    }
    foreach ($negative in @('over-count', 'duplicate-view', 'over-png-budget')) {
        $scenario = $negative
        Case "V3 screenshot selection refuses $scenario" {
            $random = [Random]::new(12); $shots = @()
            $count = if ($scenario -eq 'over-count') { 13 } elseif ($scenario -eq 'duplicate-view') { 2 } else { 1 }
            for ($i = 0; $i -lt $count; $i++) {
                $path = "docs/evidence/TEST-001/shot-$i.png"
                $bytes = [byte[]]::new($(if ($scenario -eq 'over-png-budget') { 4MB } else { 1024 })); $random.NextBytes($bytes); $bytes[0] = 0
                Write-Fixture $path ''; [IO.File]::WriteAllBytes((Join-Path $script:repo $path), $bytes)
                $shots += @{ path = $path; page = $(if ($scenario -eq 'duplicate-view') { 'same' } else { "page-$i" }); theme = 'dark'; viewport = '1440'; stable = $true }
            }
            Write-Fixture 'docs/evidence/TEST-001/review-screenshots.json' (@{ schemaVersion = 1; screenshots = $shots } | ConvertTo-Json -Depth 6)
            $script:head = Commit-Fixture
            $actual = Invoke-Package -V3
            Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('SCREENSHOT_')) "Screenshot limit $scenario not enforced"
        }
    }
    Case 'V3 size over 15MiB refuses atomic publication and preserves previous valid package' {
        $random = [Random]::new(16); $bytes = [byte[]]::new(16MB); $random.NextBytes($bytes); $bytes[0] = 0
        $oldPath = Open-V3; $oldHash = (Get-FileHash $oldPath -Algorithm SHA256).Hash
        Write-Fixture 'large.dat' ''; [IO.File]::WriteAllBytes((Join-Path $script:repo 'large.dat'), $bytes); $script:head = Commit-Fixture
        $actual = Invoke-Package -V3
        Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('PACKAGE_SIZE')) 'Oversized V3 published'
        Assert-True ((Get-FileHash $oldPath -Algorithm SHA256).Hash -eq $oldHash -and @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.partial').Count -eq 0) 'Failure changed previous ZIP or left partial'
    }
    Case 'V3 size over 10MiB emits exact category report without weakening 15MiB gate' {
        $random = [Random]::new(11); $bytes = [byte[]]::new(11MB); $random.NextBytes($bytes); $bytes[0] = 0
        Write-Fixture 'large.dat' ''; [IO.File]::WriteAllBytes((Join-Path $script:repo 'large.dat'), $bytes); $script:head = Commit-Fixture
        $actual = Invoke-Package -V3
        Assert-True ($actual.Exit -eq 0) "Soft target incorrectly blocked: $($actual.Output)"
        $r = $actual.Output | ConvertFrom-Json
        Assert-True ($r.sizeReport.aboveSoftTarget -and $r.sizeReport.sizeBytes -gt 10MB -and @($r.sizeReport.categories | Where-Object category -EQ 'source')[0].compressedBytes -gt 10MB) 'Exact compressed category report missing'
    }
    Case 'local V3 passes and independently reopens without GitHub or a cloud PASS' {
        Write-LocalFixture 'docs/evidence/TEST-001/local.json' (@{ checks = @(@{ name = 'real-local'; command = 'fixture-local-test'; status = 'PASS'; exitCode = 0; output = 'isolated fixture only; no product claim' }); ci = @{ status = 'NOT_RUN'; runId = $null; url = $null; commit = $null; conclusion = $null }; evidenceSchemaVersion = 2; validationSource = 'LOCAL'; testedCommit = $script:head } | ConvertTo-Json -Depth 6)
        $script:head = Commit-Fixture
        $saved = $env:REVIEW_FIXTURE_CI_MODE
        try {
            $env:REVIEW_FIXTURE_CI_MODE = 'unavailable'
            $actual = Invoke-Package -Local -DeclaredStatus PASS -Extra @('-EvidencePath', 'docs/evidence/TEST-001/local.json')
            Assert-True ($actual.Exit -eq 0) "Local delivery blocked: $($actual.Output)"
            $path = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
            $archive = [IO.Compression.ZipFile]::OpenRead($path)
            try {
                $m = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json
                Assert-True ($m.validationSource -ceq 'LOCAL' -and $m.ci.status -ceq 'NOT_RUN' -and $null -eq $m.runtimeCi) 'Local PASS fabricated cloud CI'
            } finally { $archive.Dispose() }
            $reopen = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
            Assert-True ($reopen.Exit -eq 0) "Local reopen required GitHub: $($reopen.Output)"
            $archive = [IO.Compression.ZipFile]::Open($path, [IO.Compression.ZipArchiveMode]::Update)
            try {
                $m.validationSource = 'GITHUB'
                Replace-ZipMember $archive 'manifest.json' ([Text.Encoding]::UTF8.GetBytes(($m | ConvertTo-Json -Depth 20)))
            } finally { $archive.Dispose() }
            $bad = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
            Assert-True ($bad.Exit -ne 0) 'Local package relabeled as GitHub evidence'
        } finally { $env:REVIEW_FIXTURE_CI_MODE = $saved }
    }
    foreach ($inputPath in @('app.txt', 'scripts/runtime.py', 'docs/contracts/runtime.md')) {
        Case "local V3 refuses changed tested input $inputPath" {
            Write-LocalFixture 'docs/evidence/TEST-001/local.json' (@{ evidenceSchemaVersion = 2; validationSource = 'LOCAL'; testedCommit = $script:head; checks = @(@{ name = 'local'; command = 'fixture'; status = 'PASS'; exitCode = 0; output = 'fixture only' }); ci = @{ status = 'NOT_RUN'; runId = $null; url = $null; commit = $null; conclusion = $null } } | ConvertTo-Json -Depth 6)
            Write-Fixture $inputPath "changed after test`n"
            $script:head = Commit-Fixture
            $actual = Invoke-Package -Local -Extra @('-EvidencePath', 'docs/evidence/TEST-001/local.json')
            Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('LOCAL_EVIDENCE')) 'Changed tested input accepted'
        }
    }
    Case 'local V3 refuses invented tested commit' {
        Write-LocalFixture 'docs/evidence/TEST-001/local.json' (@{ evidenceSchemaVersion = 2; validationSource = 'LOCAL'; testedCommit = ('f' * 40); checks = @(@{ name = 'local'; command = 'fixture'; status = 'PASS'; exitCode = 0; output = 'fixture only' }); ci = @{ status = 'NOT_RUN'; runId = $null; url = $null; commit = $null; conclusion = $null } } | ConvertTo-Json -Depth 6)
        $script:head = Commit-Fixture
        $actual = Invoke-Package -Local -Extra @('-EvidencePath', 'docs/evidence/TEST-001/local.json')
        Assert-True ($actual.Exit -ne 0) 'Invented tested commit accepted'
    }
    Case 'local V3 refuses missing committed local evidence' {
        $actual = Invoke-Package -Local
        Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('LOCAL_EVIDENCE')) 'Missing local evidence accepted'
    }
    Case 'local V3 refuses cloud PASS instead of silently bypassing verification' {
        Write-LocalFixture 'docs/evidence/TEST-001/local.json' (@{ checks = @(@{ name = 'local'; command = 'fixture'; status = 'PASS'; exitCode = 0; output = 'fixture' }); evidenceSchemaVersion = 2; validationSource = 'LOCAL'; testedCommit = $script:head; ci = @{ status = 'PASS'; runId = '123'; url = 'https://github.com/on-dotnet/ontology-platform/actions/runs/123'; commit = $script:head; conclusion = 'success' } } | ConvertTo-Json -Depth 6)
        $script:head = Commit-Fixture
        $actual = Invoke-Package -Local -Extra @('-EvidencePath', 'docs/evidence/TEST-001/local.json')
        Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('LOCAL_EVIDENCE')) 'Local mode accepted unqueried CI claim'
    }
    Case 'V3 default with independently queried same Head CI and legacy V2 reopen' {
        $actual = Invoke-Package -V3
        Assert-True ($actual.Exit -eq 0) "V3 creation failed: $($actual.Output)"
        $path = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
        $archive = [IO.Compression.ZipFile]::OpenRead($path)
        try {
            $m = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json
            Assert-True ($m.schemaVersion -eq 3) 'Default must be schema3'
            Assert-True ($m.ci.commit -eq $script:head -and $m.ci.jobs.Count -eq 2 -and $m.ci.verification -eq 'GITHUB_QUERIED') 'CI was not independently queried'
            Assert-True ($null -eq $m.PSObject.Properties['excludedIgnoredPaths']) 'Ignored paths leaked instead of aggregation'
        } finally { $archive.Dispose() }
        $verified = Invoke-Package -Verify -Extra @('-VerifyOnly', '-PackagePath', $path)
        Assert-True ($verified.Exit -eq 0) "V3 reopen failed: $($verified.Output)"
    }
    Case 'compact explicit V2 with complete source and historical evidence index' {
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
    Case 'V3 binary add modify delete rename and historical screenshot reduction' {
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
        $path = Open-V3
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
    Case 'argv bounded diff preserves literal text and binary classification' {
        . $PackageScript -Library
        if ($IsWindows) {
            $rejected = $false
            try { $null = Test-ReviewGitArgvBudget @('diff') } catch { $rejected = $_.Exception.Message.Contains('ARGV_PLATFORM_UNVERIFIED') }
            Assert-True $rejected 'Unverified Windows renderer accepted'
            return
        }
        $names = @('中文 空格.txt', 'Case.txt', 'case-other.txt', 'literal[abc].txt', ':magic.txt')
        foreach ($name in $names) { Write-Fixture $name "text`n" }
        Write-Fixture '.gitattributes' "*.txt -diff`n"
        [IO.File]::WriteAllBytes((Join-Path $script:repo 'image.bin'), [byte[]]@(0, 1, 2, 3))
        $script:head = Commit-Fixture
        $paths = @((Invoke-ReviewGit $script:repo @('diff', '--name-only', '-z', '--no-renames', $script:base, $script:head)).Text.Split([char]0, [StringSplitOptions]::RemoveEmptyEntries))
        $changes = @($paths | ForEach-Object { @{ path = $_; previousPath = $null; isBinary = ($_ -ceq 'image.bin') } })
        $options = @('diff', '--no-color', '--full-index', '--no-ext-diff', '--no-textconv', '--no-renames')
        $expected = Invoke-ReviewGit $script:repo ($options + @('--text', $script:base, $script:head, '--') + @($paths | Where-Object { $_ -cne 'image.bin' } | ForEach-Object { ':(literal)' + $_ }))
        $actual = Get-ReviewBoundedTextDiff $script:repo $script:base $script:head $changes $options
        Assert-True ((Get-ReviewHash $actual.Bytes) -ceq (Get-ReviewHash $expected.Bytes)) 'Bounded diff changed literal/attributes text bytes'
        Assert-True (-not (Test-ReviewGitArgvBudget @('diff', ('中' * 3000)))) 'UTF8 byte budget ignored'
        Assert-True (-not (Test-ReviewGitArgvBudget (@('diff') + @(1..260 | ForEach-Object { 'x' })))) 'Argument count budget ignored'
        $prefix = @(@(Get-Command git -CommandType Application)[0].Source, '--no-optional-locks', '-c', 'core.autocrlf=false', '-c', 'core.quotePath=false', '-c', 'color.ui=false')
        $prefixBytes = 1
        foreach ($item in $prefix) { $prefixBytes += [Text.Encoding]::UTF8.GetByteCount($item) + 1 }
        Assert-True (Test-ReviewGitArgvBudget @(('a' * (8192 - $prefixBytes)))) '8192-byte boundary rejected'
        Assert-True (-not (Test-ReviewGitArgvBudget @(('a' * (8193 - $prefixBytes))))) '8193-byte boundary accepted'
        Assert-True (Test-ReviewGitArgvBudget @(1..(256 - $prefix.Count) | ForEach-Object { 'x' })) '256-argument boundary rejected'
        Assert-True (-not (Test-ReviewGitArgvBudget @(1..(257 - $prefix.Count) | ForEach-Object { 'x' }))) '257-argument boundary accepted'
    }
    Case 'argv large text set uses exact complement and rejects omissions' {
        . $PackageScript -Library
        if ($IsWindows) {
            $rejected = $false
            try { $null = Test-ReviewGitArgvBudget @('diff') } catch { $rejected = $_.Exception.Message.Contains('ARGV_PLATFORM_UNVERIFIED') }
            Assert-True $rejected 'Unverified Windows renderer accepted'
            return
        }
        Write-Fixture 'old name.txt' "rename content`n"
        $script:base = Commit-Fixture
        $null = Git @('mv', 'old name.txt', '新 name.txt')
        Remove-Item -LiteralPath (Join-Path $script:repo 'app.txt')
        foreach ($name in @('中文 空格.txt', 'Case.txt', 'case-other.txt', 'literal[abc].txt', ':magic.txt')) { Write-Fixture $name "literal text`n" }
        foreach ($i in 1..300) { Write-Fixture ('many/{0:D4}.txt' -f $i) "value $i`n" }
        Write-Fixture '.gitattributes' "*.txt diff=argvprobe`n"
        [IO.File]::WriteAllBytes((Join-Path $script:repo 'image.bin'), [byte[]]@(0, 5, 8))
        $script:head = Commit-Fixture
        $null = Git @('config', 'diff.external', 'false')
        $external = Invoke-ReviewGit $script:repo @('diff', $script:base, $script:head) -AllowFailure
        Assert-True ($external.ExitCode -ne 0) 'External diff fault was not exercised'
        $null = Git @('config', '--unset', 'diff.external')
        $null = Git @('config', 'diff.argvprobe.textconv', 'false')
        $textconv = Invoke-ReviewGit $script:repo @('diff', '--no-ext-diff', $script:base, $script:head) -AllowFailure
        Assert-True ($textconv.ExitCode -ne 0) 'Textconv fault was not exercised'
        $null = Git @('config', 'diff.external', 'false')
        $paths = @((Invoke-ReviewGit $script:repo @('diff', '--name-only', '-z', '--no-renames', $script:base, $script:head)).Text.Split([char]0, [StringSplitOptions]::RemoveEmptyEntries))
        $changes = @($paths | ForEach-Object { @{ path = $_; previousPath = $null; isBinary = ($_ -ceq 'image.bin') } })
        $options = @('diff', '--no-color', '--full-index', '--no-ext-diff', '--no-textconv', '--no-renames')
        $expected = Invoke-ReviewGit $script:repo ($options + @('--text', $script:base, $script:head, '--') + @($paths | Where-Object { $_ -cne 'image.bin' } | ForEach-Object { ':(literal)' + $_ }))
        $actual = Get-ReviewBoundedTextDiff $script:repo $script:base $script:head $changes $options
        Assert-True ((Get-ReviewHash $actual.Bytes) -ceq (Get-ReviewHash $expected.Bytes)) 'Complement diff changed bytes'
        $bad = @($changes | Where-Object path -cne 'many/0001.txt')
        $rejected = $false
        try { $null = Get-ReviewBoundedTextDiff $script:repo $script:base $script:head $bad $options } catch { $rejected = $_.Exception.Message.Contains('ARGV_PATH_SET') }
        Assert-True $rejected 'Missing text path accepted'
        $rejected = $false
        try { $null = Get-ReviewBoundedTextDiff $script:repo $script:base $script:head ($changes + @(@{path='image.bin';previousPath=$null;isBinary=$false})) $options } catch { $rejected = $_.Exception.Message.Contains('ARGV_PATH_OVERLAP') }
        Assert-True $rejected 'Binary/text overlap accepted'
        $manyBinary = @(1..300 | ForEach-Object { @{path=('binary/{0}.bin' -f $_);previousPath=$null;isBinary=$true} })
        $rejected = $false
        try { $null = Get-ReviewBoundedTextDiff $script:repo $script:base $script:head ($changes + $manyBinary) $options } catch { $rejected = $_.Exception.Message.Contains('ARGV_BUDGET') }
        Assert-True $rejected 'Both oversized vectors accepted'
        Assert-True (-not (Test-ReviewArgvApproval $script:repo $script:base $script:head 3 'TEST-001')) 'Foreign task granted exception'
        Assert-True (-not (Test-ReviewArgvApproval $script:repo $script:base $script:head 2 'G4-M1-MAIN-INTEGRATION-001')) 'V2 granted exception'
    }
    Case 'argv approval binds exact committed record version task base and ancestry' {
        # 仅在隔离工具副本替换fixture提交身份；生产入口没有fixture或环境旁路。
        $copy = Join-Path $fixtureRoot 'argv-fixture-tool.ps1'
        $source = [IO.File]::ReadAllText($PackageScript).Replace('d1a61daffe844475b07705797e3ad325cc3f2945', $script:base).Replace('03ce658c04fc810e7a10dc14eea1d64124ddbf12', $script:base)
        [IO.File]::WriteAllText($copy, $source)
        . $copy -Library
        $task = 'G4-M1-MAIN-INTEGRATION-001'
        Assert-True (-not (Test-ReviewArgvApproval $script:repo $script:base $script:head 3 $task)) 'Missing approval granted permission'
        $approvalPath = 'docs/tasks/G4-M1-MAIN-INTEGRATION-001/ARGV-APPROVAL.md'
        $actualApproval = Join-Path (Split-Path (Split-Path $PackageScript -Parent) -Parent) $approvalPath
        Write-Fixture $approvalPath ([IO.File]::ReadAllText($actualApproval))
        $script:head = Commit-Fixture
        Assert-True (Test-ReviewArgvApproval $script:repo $script:base $script:head 3 $task) 'Exact approval rejected'
        foreach ($version in @(1, 2)) { Assert-True (-not (Test-ReviewArgvApproval $script:repo $script:base $script:head $version $task)) 'Historical version granted permission' }
        Assert-True (-not (Test-ReviewArgvApproval $script:repo $script:base $script:head 3 'OTHER')) 'Foreign task granted permission'
        Assert-True (-not (Test-ReviewArgvApproval $script:repo ('f' * 40) $script:head 3 $task)) 'Wrong base granted permission'
        # 独立使用不存在的祖先，批准原文仍准确。
        $wrongAncestor = $source.Replace("'--is-ancestor', '$($script:base)'", "'--is-ancestor', '$('f' * 40)'")
        [IO.File]::WriteAllText($copy, $wrongAncestor)
        . $copy -Library
        $rejected = $false
        try { $null = Test-ReviewArgvApproval $script:repo $script:base $script:head 3 $task } catch { $rejected = $_.Exception.Message.Contains('ARGV_APPROVAL') }
        Assert-True $rejected 'Unknown ancestor accepted'
        [IO.File]::WriteAllText($copy, $source)
        . $copy -Library
        Write-Fixture $approvalPath "tampered approval`n"
        $script:head = Commit-Fixture
        $rejected = $false
        try { $null = Test-ReviewArgvApproval $script:repo $script:base $script:head 3 $task } catch { $rejected = $_.Exception.Message.Contains('ARGV_APPROVAL') }
        Assert-True $rejected 'Tampered approval accepted'
    }
    Case 'argv bounded diff preserves delete rename and binary-only result' {
        . $PackageScript -Library
        if ($IsWindows) {
            $rejected = $false
            try { $null = Test-ReviewGitArgvBudget @('diff') } catch { $rejected = $_.Exception.Message.Contains('ARGV_PLATFORM_UNVERIFIED') }
            Assert-True $rejected 'Unverified Windows renderer accepted'
            return
        }
        Write-Fixture 'old name.txt' "renamed content`n"
        $before = Commit-Fixture
        $null = Git @('mv', 'old name.txt', '新 name.txt')
        Remove-Item -LiteralPath (Join-Path $script:repo 'app.txt')
        $after = Commit-Fixture
        $changes = @(@{path='新 name.txt';previousPath='old name.txt';isBinary=$false}, @{path='app.txt';previousPath=$null;isBinary=$false})
        $options = @('diff', '--no-color', '--full-index', '--no-ext-diff', '--no-textconv', '--no-renames')
        $expected = Invoke-ReviewGit $script:repo ($options + @('--text', $before, $after, '--'))
        $actual = Get-ReviewBoundedTextDiff $script:repo $before $after $changes $options
        Assert-True ((Get-ReviewHash $actual.Bytes) -ceq (Get-ReviewHash $expected.Bytes)) 'Rename/delete bytes differ'
        [IO.File]::WriteAllBytes((Join-Path $script:repo 'only.bin'), [byte[]]@(0, 1, 4))
        $binaryHead = Commit-Fixture
        $actual = Get-ReviewBoundedTextDiff $script:repo $after $binaryHead @(@{path='only.bin';previousPath=$null;isBinary=$true}) $options
        Assert-True ($actual.Bytes.Length -eq 0 -and $actual.ExitCode -eq 0) 'Binary-only diff emitted text'
    }
    function Assert-ReductionWindowsRefusal {
        . $PackageScript -Library
        $rejected = $false
        try { $null = Test-ReviewGitArgvBudget @('diff') } catch { $rejected = $_.Exception.Message.Contains('ARGV_PLATFORM_UNVERIFIED') }
        Assert-True $rejected 'Unverified Windows renderer accepted'
        throw 'TEST_NOT_RUN: Windows refusal verified; approved Unix reduction scenario not run on this platform'
    }
    function New-ReductionFixture {
        $script:reductionTask = 'G4-M1-MAIN-INTEGRATION-001'
        $script:reductionRoot = "docs/evidence/$script:reductionTask/"
        $script:reductionRun = 'b-continue-20261106-35'
        $script:reductionValidation = $script:reductionRoot + $script:reductionRun + '/validation.json'
        $script:reductionSelectionPath = $script:reductionRoot + 'review-evidence-selection.json'
        $script:reductionRequired = @(
            'b-continue-20261104-32/gate-I06.json',
            'b-continue-20261104-33/gate-I07.json',
            'b-continue-20261104-23/archive-migration-applied.json',
            'packaging-a-20261106-01/PACKAGING-SIZE-ANALYSIS.md',
            'packaging-reduction-20261106-01/IMPLEMENTATION-PLAN.md'
        ) | ForEach-Object { $script:reductionRoot + $_ }
        foreach ($path in $script:reductionRequired) { Write-Fixture $path "FAIL: original historical fixture witness $path`n" }
        Write-Fixture ($script:reductionRoot + 'old/omitted.txt') "old diagnostic bytes preserved`n"
        Write-Fixture ($script:reductionRoot + $script:reductionRun + '/gate-I01.json') "fixture full run member`n"
        foreach ($record in @('ARGV-APPROVAL.md', 'REDUCTION-APPROVAL.md')) {
            $path = "docs/tasks/$script:reductionTask/$record"
            Write-Fixture $path ([IO.File]::ReadAllText((Join-Path (Split-Path (Split-Path $PackageScript -Parent) -Parent) $path)))
        }
        $script:reductionTested = Commit-Fixture
        Write-LocalFixture $script:reductionValidation (@{ evidenceSchemaVersion = 2; validationSource = 'LOCAL'; testedCommit = $script:reductionTested; checks = @(@{ name = 'fixture-local'; command = 'fixture only'; status = 'PASS'; exitCode = 0; output = 'not a product claim' }); ci = @{ status = 'NOT_RUN'; runId = $null; url = $null; commit = $null; conclusion = $null } } | ConvertTo-Json -Depth 6)
        $script:reductionSelection = @{ schemaVersion = 1; finalRun = $script:reductionRun; validationPath = $script:reductionValidation; retainedPaths = @($script:reductionRequired) }
        Write-Fixture $script:reductionSelectionPath ($script:reductionSelection | ConvertTo-Json -Depth 6)
        $script:head = Commit-Fixture
        $script:reductionTool = Join-Path $fixtureRoot ([guid]::NewGuid().ToString('N') + '.ps1')
        # 仅隔离副本替换实际提交身份，生产入口没有fixture旁路。
        $source = [IO.File]::ReadAllText($PackageScript).Replace('d1a61daffe844475b07705797e3ad325cc3f2945', $script:base).Replace('03ce658c04fc810e7a10dc14eea1d64124ddbf12', $script:base).Replace('9ed3b9283acc81805737fb19efd3123281010103', $script:base)
        [IO.File]::WriteAllText($script:reductionTool, $source)
    }
    function Invoke-ReductionPackage {
        param([string]$VerifyPath = '', [string]$Evidence = $script:reductionValidation)
        $arguments = @('-NoProfile', '-File', $script:reductionTool, '-Root', $script:repo)
        if ($VerifyPath) { $arguments += @('-VerifyOnly', '-PackagePath', $VerifyPath) }
        else { $arguments += @('-BaseSha', $script:base, '-HeadSha', $script:head, '-TaskId', $script:reductionTask, '-Status', 'PARTIAL', '-ValidationSource', 'LOCAL', '-EvidencePath', $Evidence) }
        $output = & pwsh @arguments 2>&1
        return @{ Exit = $LASTEXITCODE; Output = ($output -join "`n") }
    }
    Case 'reduction retains early schema consumer without optional policy fields' {
        . $PackageScript -Library
        $path = 'docs/evidence/PREFLIGHT/validation.json'
        $bytes = [Text.Encoding]::UTF8.GetBytes((@{ checks = @(@{name='fixture';command='synthetic';status='PASS';exitCode=0;output='one fixture check'});ci=@{status='NOT_VERIFIED'} } | ConvertTo-Json -Depth 8) + "`n")
        $snapshot = @{ GitBytes = @{ $path = $bytes }; Mapping = @(); DiffCheckExit = 0 }
        $value = Get-ReviewEvidence $snapshot $path 'PARTIAL' $null
        Assert-True ($value.checks.Count -eq 1 -and $value.checks[0].status -ceq 'PASS') 'Early schema-only consumer changed'
    }
    Case 'reduction V3 includes complete final run and failures with exact omitted recovery' {
        if ($IsWindows) { Assert-ReductionWindowsRefusal }
        New-ReductionFixture
        $actual = Invoke-ReductionPackage
        Assert-True ($actual.Exit -eq 0) "Reduction creation failed: $($actual.Output)"
        $zip = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
        $archive = [IO.Compression.ZipFile]::OpenRead($zip)
        try {
            $manifest = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json -AsHashtable
            Assert-True ($manifest.evidenceReduction.policyId -ceq 'G4-M1-15M-EVIDENCE-1') 'Trusted reduction policy absent'
            $paths = @($manifest.sourceMembers.gitPath)
            foreach ($path in @($script:reductionValidation, $script:reductionSelectionPath, ($script:reductionRoot + $script:reductionRun + '/gate-I01.json')) + $script:reductionRequired) { Assert-True ($paths -ccontains $path) 'Required witness not included' }
            Assert-True ($paths -cnotcontains ($script:reductionRoot + 'old/omitted.txt')) 'Historical payload still duplicated'
            $index = Read-ZipText $archive 'evidence-index.json' | ConvertFrom-Json
            $omitted = @($index | Where-Object gitPath -CEQ ($script:reductionRoot + 'old/omitted.txt'))[0]
            Assert-True ($null -eq $omitted.archivePath -and $omitted.commit -ceq $script:head) 'Omitted evidence lacks exact commit'
            $blob = Git @('rev-parse', ($script:head + ':' + $omitted.gitPath))
            Assert-True ($blob -ceq $omitted.blobOid -and $omitted.sha256.Length -eq 64 -and $omitted.sizeBytes -gt 0 -and $omitted.recovery) 'Omitted evidence lacks exact recovery'
            $patch = Read-ZipText $archive 'git/diff-text.patch'
            Assert-True ($patch.Contains('app.txt') -and -not $patch.Contains('old diagnostic bytes preserved') -and -not $patch.Contains('fixture full run member')) 'Source patch incomplete or evidence duplicated'
            $changes = Read-ZipText $archive 'git/changed-files.json' | ConvertFrom-Json
            $change = @($changes | Where-Object path -CEQ $omitted.gitPath)[0]
            Assert-True ($change.patchDisposition -ceq 'evidence-index-only' -and -not $change.isBinary -and $change.head.commit -ceq $script:head -and $change.head.blobOid -ceq $blob) 'Evidence misclassified or change recovery incomplete'
            $failure = @($manifest.sourceMembers | Where-Object gitPath -CEQ $script:reductionRequired[0])[0]
            Assert-True ((Read-ZipText $archive $failure.archivePath).StartsWith('FAIL:')) 'Historical failure rewritten'
        } finally { $archive.Dispose() }
        $reopen = Invoke-ReductionPackage -VerifyPath $zip
        Assert-True ($reopen.Exit -eq 0) "Reduction independent reopen failed: $($reopen.Output)"
    }
    Case 'reduction policy binds exact approval task base version and ancestry' {
        New-ReductionFixture
        . $script:reductionTool -Library
        $policy = Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask
        Assert-True ($policy.policyId -ceq 'G4-M1-15M-EVIDENCE-1') 'Approved policy not enabled'
        foreach ($version in @(1, 2)) { Assert-True ($null -eq (Get-ReviewReductionPolicy $script:repo $script:base $script:head $version $script:reductionTask)) 'Old version changed' }
        Assert-True ($null -eq (Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 'OTHER')) 'Foreign task granted policy'
        Assert-True ($null -eq (Get-ReviewReductionPolicy $script:repo ('f' * 40) $script:head 3 $script:reductionTask)) 'Foreign base granted policy'
        $source = [IO.File]::ReadAllText($script:reductionTool)
        $mutated = $source.Replace("`$approvalAncestor = '$script:base'", "`$approvalAncestor = '$('f' * 40)'")
        Assert-True ($mutated -cne $source) 'Ancestor negative fixture failed to mutate the actual guard'
        [IO.File]::WriteAllText($script:reductionTool, $mutated)
        . $script:reductionTool -Library
        $rejected = $false
        try { $null = Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask } catch { $rejected = $_.Exception.Message.Contains('REDUCTION_APPROVAL') }
        Assert-True $rejected 'Approved blob with unknown reduction ancestor accepted'
        [IO.File]::WriteAllText($script:reductionTool, $source)
        . $script:reductionTool -Library
        $record = "docs/tasks/$script:reductionTask/REDUCTION-APPROVAL.md"
        Write-Fixture $record "tampered`n"
        $script:head = Commit-Fixture
        $rejected = $false
        try { $null = Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask } catch { $rejected = $_.Exception.Message.Contains('REDUCTION_APPROVAL') }
        Assert-True $rejected 'Tampered approval granted policy'
        Remove-Item (Join-Path $script:repo $record)
        $script:head = Commit-Fixture
        Assert-True ($null -eq (Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask)) 'Missing approval granted policy'
    }
    foreach ($badSelection in @('missing', 'extra-field', 'wrong-run', 'foreign-path', 'duplicate', 'absent-path', 'missing-critical', 'outside-validation', 'png')) {
        Case "reduction selection rejects $badSelection" {
            New-ReductionFixture
            switch ($badSelection) {
                'missing' { Remove-Item (Join-Path $script:repo $script:reductionSelectionPath) }
                'extra-field' { $script:reductionSelection.allowOmission = $true }
                'wrong-run' { $script:reductionSelection.finalRun = '../other' }
                'foreign-path' { $script:reductionSelection.retainedPaths += 'docs/evidence/TEST-001/result.txt' }
                'duplicate' { $script:reductionSelection.retainedPaths += $script:reductionRequired[0] }
                'absent-path' { $script:reductionSelection.retainedPaths += $script:reductionRoot + 'absent.txt' }
                'missing-critical' { $script:reductionSelection.retainedPaths = @($script:reductionRequired | Select-Object -Skip 1) }
                'outside-validation' { $script:reductionSelection.validationPath = $script:reductionRequired[0] }
                'png' { Write-Fixture ($script:reductionRoot + 'fake.png') 'not an image'; $script:reductionSelection.retainedPaths += $script:reductionRoot + 'fake.png' }
            }
            if ($badSelection -ne 'missing') { Write-Fixture $script:reductionSelectionPath ($script:reductionSelection | ConvertTo-Json -Depth 6) }
            $script:head = Commit-Fixture
            $actual = Invoke-ReductionPackage
            Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('REDUCTION_SELECTION')) "Invalid selection accepted or unrelated failure: $($actual.Output)"
        }
    }
    Case 'reduction refuses validation outside the committed selected path' {
        if ($IsWindows) { Assert-ReductionWindowsRefusal }
        New-ReductionFixture
        $other = $script:reductionRoot + 'unselected-validation.json'
        Write-Fixture $other ([IO.File]::ReadAllText((Join-Path $script:repo $script:reductionValidation)))
        $script:head = Commit-Fixture
        $actual = Invoke-ReductionPackage -Evidence $other
        Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('REDUCTION_EVIDENCE')) "Unselected validation accepted: $($actual.Output)"
    }
    Case 'reduction preserves both cross-boundary rename directions and deleted evidence recovery' {
        if ($IsWindows) { Assert-ReductionWindowsRefusal }
        New-ReductionFixture
        Write-Fixture ($script:reductionRoot + 'out.txt') "unique outward rename bytes`n"
        Write-Fixture 'incoming.txt' "unique inward rename bytes`n"
        Write-Fixture ($script:reductionRoot + 'deleted.txt') "original deleted evidence`n"
        [IO.File]::WriteAllBytes((Join-Path $script:repo 'binary.dat'), [byte[]]@(0, 3, 4))
        $before = Commit-Fixture
        $null = Git @('mv', ($script:reductionRoot + 'out.txt'), 'outgoing.txt')
        $null = Git @('mv', 'incoming.txt', ($script:reductionRoot + 'in.txt'))
        Remove-Item (Join-Path $script:repo ($script:reductionRoot + 'deleted.txt'))
        [IO.File]::WriteAllBytes((Join-Path $script:repo 'binary.dat'), [byte[]]@(0, 3, 5))
        $after = Commit-Fixture
        [IO.File]::WriteAllText($script:reductionTool, [IO.File]::ReadAllText($script:reductionTool).Replace($script:base, $before))
        . $script:reductionTool -Library
        $snapshot = Get-ReviewSnapshot $script:repo $before $after 3 $script:reductionTask
        $changes = [Text.Encoding]::UTF8.GetString($snapshot.Members['git/changed-files.json']) | ConvertFrom-Json
        $renames = @($changes | Where-Object changeType -Like 'R*')
        Assert-True ($renames.Count -eq 2 -and @($renames | Where-Object patchDisposition -CNE 'full-text').Count -eq 0) 'Cross-boundary rename omitted'
        $options = @('diff', '--no-color', '--full-index', '--no-ext-diff', '--no-textconv', '--no-renames', '--text', $before, $after, '--', ':(literal)outgoing.txt', (':(literal)' + $script:reductionRoot + 'out.txt'), ':(literal)incoming.txt', (':(literal)' + $script:reductionRoot + 'in.txt'))
        $expected = Invoke-ReviewGit $script:repo $options
        Assert-True ((Get-ReviewHash $expected.Bytes) -ceq (Get-ReviewHash $snapshot.Members['git/diff-text.patch'])) 'Cross-boundary patch differs from full literal patch'
        $deleted = @($changes | Where-Object path -CEQ ($script:reductionRoot + 'deleted.txt'))[0]
        Assert-True ($null -eq $deleted.head -and $deleted.base.commit -ceq $before -and $deleted.patchDisposition -ceq 'evidence-index-only') 'Deleted evidence recovery missing'
        $bytes = (Invoke-ReviewGit $script:repo @('cat-file', 'blob', $deleted.base.blobOid)).Bytes
        Assert-True ((Get-ReviewHash $bytes) -ceq $deleted.base.sha256 -and $bytes.Length -eq $deleted.base.sizeBytes) 'Deleted evidence does not recover exactly'
        Assert-True (@($changes | Where-Object patchDisposition -CEQ 'binary-index-only').Count -eq 1) 'Binary classification changed'
    }
    Case 'reduction bounded directory exclusion is exact and ambiguous paths fail closed' {
        if ($IsWindows) { Assert-ReductionWindowsRefusal }
        . $PackageScript -Library
        $changes = @()
        foreach ($i in 1..270) {
            $sourcePath = "source-$i.txt"; $evidencePath = "docs/evidence/TEST-001/old-$i.txt"
            Write-Fixture $sourcePath "source $i`n"; Write-Fixture $evidencePath "evidence $i`n"
            $changes += @{path=$sourcePath;previousPath=$null;isBinary=$false;patchDisposition='full-text'}, @{path=$evidencePath;previousPath=$null;isBinary=$false;patchDisposition='evidence-index-only'}
        }
        $after = Commit-Fixture
        $options = @('diff', '--no-color', '--full-index', '--no-ext-diff', '--no-textconv', '--no-renames')
        $expected = Invoke-ReviewGit $script:repo ($options + @('--text', $script:head, $after, '--') + @(1..270 | ForEach-Object { ":(literal)source-$_.txt" }))
        $actual = Get-ReviewBoundedTextDiff $script:repo $script:head $after $changes $options -EvidenceIndexOnly
        Assert-True ((Get-ReviewHash $expected.Bytes) -ceq (Get-ReviewHash $actual.Bytes)) 'Directory compression changed source patch'
        $changes += @{path='source-1.txt';previousPath=$null;isBinary=$false;patchDisposition='evidence-index-only'}
        $rejected = $false
        try { $null = Get-ReviewBoundedTextDiff $script:repo $script:head $after $changes $options -EvidenceIndexOnly } catch { $rejected = $_.Exception.Message.Contains('ARGV_PATH_OVERLAP') }
        Assert-True $rejected 'Same path included and excluded silently'
    }
    Case 'reduction scans removed index-only evidence for finite secrets' {
        if ($IsWindows) { Assert-ReductionWindowsRefusal }
        New-ReductionFixture
        $path = $script:reductionRoot + 'deleted-secret.txt'
        Write-Fixture $path (('gh' + 'p_') + ('A' * 36) + "`n")
        $before = Commit-Fixture
        Remove-Item (Join-Path $script:repo $path)
        $after = Commit-Fixture
        [IO.File]::WriteAllText($script:reductionTool, [IO.File]::ReadAllText($script:reductionTool).Replace($script:base, $before))
        . $script:reductionTool -Library
        $rejected = $false
        try { $null = Get-ReviewSnapshot $script:repo $before $after 3 $script:reductionTask } catch { $rejected = $_.Exception.Message.Contains('SECRET_PATTERN') }
        Assert-True $rejected 'Index-only deletion bypassed secret scan'
    }
    Case 'reduction retains 15MiB creation and reopen hard limit' {
        if ($IsWindows) { Assert-ReductionWindowsRefusal }
        New-ReductionFixture
        $actual = Invoke-ReductionPackage
        Assert-True ($actual.Exit -eq 0) "Fixture creation failed: $($actual.Output)"
        $zip = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
        $bytes = [byte[]]::new(16MB); [Random]::new(1615).NextBytes($bytes); $bytes[0] = 0
        $archive = [IO.Compression.ZipFile]::Open($zip, [IO.Compression.ZipArchiveMode]::Update)
        try {
            $stream = $archive.CreateEntry('oversize.dat', [IO.Compression.CompressionLevel]::NoCompression).Open()
            try { $stream.Write($bytes) } finally { $stream.Dispose() }
        } finally { $archive.Dispose() }
        $bad = Invoke-ReductionPackage -VerifyPath $zip
        Assert-True ($bad.Exit -ne 0 -and $bad.Output.Contains('PACKAGE_SIZE')) "Reopen size limit weakened: $($bad.Output)"
        [IO.File]::WriteAllBytes((Join-Path $script:repo ($script:reductionRoot + $script:reductionRun + '/large.dat')), $bytes)
        $script:head = Commit-Fixture
        $actual = Invoke-ReductionPackage
        Assert-True ($actual.Exit -ne 0 -and $actual.Output.Contains('PACKAGE_SIZE')) "Creation size limit weakened: $($actual.Output)"
        Assert-True (@(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip').Count -eq 1 -and @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.partial').Count -eq 0) 'Oversized creation published or left partial'
    }
    foreach ($tamper in @('policy', 'missing-policy', 'index', 'diff', 'changes')) {
        Case "reduction VerifyOnly rejects rehashed $tamper" {
            if ($IsWindows) { Assert-ReductionWindowsRefusal }
            New-ReductionFixture
            $actual = Invoke-ReductionPackage
            Assert-True ($actual.Exit -eq 0) "Fixture creation failed: $($actual.Output)"
            $zip = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
            $archive = [IO.Compression.ZipFile]::Open($zip, [IO.Compression.ZipArchiveMode]::Update)
            try {
                if ($tamper -in @('policy', 'missing-policy')) {
                    $m = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json -AsHashtable
                    if ($tamper -eq 'policy') { $m.evidenceReduction.finalRun = 'b-continue-20261106-99' } else { $m.Remove('evidenceReduction') }
                    Replace-ZipMember $archive 'manifest.json' ([Text.Encoding]::UTF8.GetBytes(($m | ConvertTo-Json -Depth 20)))
                } else {
                    $name = switch ($tamper) { 'index' { 'evidence-index.json' }; 'diff' { 'git/diff-text.patch' }; 'changes' { 'git/changed-files.json' } }
                    Replace-ZipMember $archive $name ([Text.Encoding]::UTF8.GetBytes("[]`n"))
                }
            } finally { $archive.Dispose() }
            $bad = Invoke-ReductionPackage -VerifyPath $zip
            Assert-True ($bad.Exit -ne 0 -and ($bad.Output.Contains('REDUCTION_POLICY') -or $bad.Output.Contains('HEAD_MISMATCH'))) "Rehashed mutation accepted or unrelated failure: $($bad.Output)"
        }
    }
    function New-M4ReductionFixture {
        $script:reductionTask = 'G4-M4-QUERY-001'
        $script:reductionRoot = "docs/evidence/$script:reductionTask/"
        $script:reductionRun = 'review-fix-01'
        $script:reductionValidation = $script:reductionRoot + $script:reductionRun + '/validation.json'
        $script:reductionSelectionPath = $script:reductionRoot + 'review-evidence-selection.json'
        $script:reductionRequired = @(
            'contract-admission-request.md',
            'aba-fix-01/historical-qualifications.json',
            'aba-fix-01/originals-index.json',
            'aba-fix-01/scope-and-preservation.json',
            'aba-fix-01/fixture-root-cause.json',
            'aba-fix-01/review.md',
            'format-fix-01/root-cause-and-preserved-originals.json',
            'query-impl-01/final-failures-raw-index.json',
            'query-impl-01/test-database-isolation-raw-index.json',
            'query-impl-01/isolation-lifecycle-tests-raw-index.json',
            'query-impl-01/isolation-current-connection-raw-index.json',
            'query-impl-01/qualification-s3-6f01c276c3934421b25f77da76296014.json',
            'query-impl-01/qualification-s2-runtime-7bf2cec470aa477d8e0e5b6ff90c6bac.json',
            'query-impl-01/qualification-web-lint-50607e23aef748b4bc4b55a97dafeb34.json',
            'query-impl-01/qualification-security-unit-c22b4cac86d54f5db217b091db33fdb5.json',
            'query-impl-01/qualification-web-typecheck-8d02c72de4cb4f4bae9d28ffc65f6edd.json'
        ) | ForEach-Object { $script:reductionRoot + $_ }
        foreach ($path in $script:reductionRequired) { Write-Fixture $path "[]`n" }
        Write-Fixture ($script:reductionRoot + 'review-fix-01/causal-original.txt') "current exact causal fixture`n"
        Write-Fixture ($script:reductionRoot + 'old/shared.txt') "exact referenced historical original`n"
        Write-Fixture ($script:reductionRoot + 'old/omitted.txt') "unrelated history stays in Git`n"
        Write-Fixture ($script:reductionRoot + 'review-fix-01/originals-index.json') (@(@{path=($script:reductionRoot + 'old/shared.txt')}) | ConvertTo-Json -AsArray)
        $script:reductionRequired += $script:reductionRoot + 'old/shared.txt'
        $approval = $script:reductionRoot + 'review-fix-01/authorization-original.md'
        Write-Fixture $approval ([IO.File]::ReadAllText((Join-Path (Split-Path (Split-Path $PackageScript -Parent) -Parent) $approval)))
        $script:reductionTested = Commit-Fixture
        Write-LocalFixture $script:reductionValidation (@{ evidenceSchemaVersion = 2; validationSource = 'LOCAL'; testedCommit = $script:reductionTested; checks = @(@{ name = 'fixture-local'; command = 'fixture only'; status = 'PASS'; exitCode = 0; output = 'not a product claim' }); ci = @{ status = 'NOT_RUN'; runId = $null; url = $null; commit = $null; conclusion = $null } } | ConvertTo-Json -Depth 6)
        $script:reductionSelection = @{ schemaVersion = 1; finalRun = $script:reductionRun; validationPath = $script:reductionValidation; retainedPaths = @($script:reductionRequired) }
        Write-Fixture $script:reductionSelectionPath ($script:reductionSelection | ConvertTo-Json -Depth 6)
        $script:head = Commit-Fixture
        $script:reductionTool = Join-Path $fixtureRoot ([guid]::NewGuid().ToString('N') + '.ps1')
        # 只改隔离fixture的准确提交身份；生产入口不存在参数化批准旁路。
        $source = [IO.File]::ReadAllText($PackageScript).Replace('f0afb730ce92ecbd3a5947d9c6f58faedc8b2138', $script:base).Replace('116469305cb89c3e3bc3f5dfcfb177a502a5ad2d', $script:base)
        [IO.File]::WriteAllText($script:reductionTool, $source)
    }
    Case 'm4 reduction binds approval and restores full current original closure' {
        if ($IsWindows) { Assert-ReductionWindowsRefusal }
        New-M4ReductionFixture
        . $script:reductionTool -Library
        $policy = Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask
        Assert-True ($null -ne $policy -and $policy.policyId -ceq 'G4-M4-REVIEW-FIX-EVIDENCE-1') 'M4 exact approved policy absent'
        foreach ($wrong in @(@{base=('f'*40);task=$script:reductionTask;version=3},@{base=$script:base;task='OTHER';version=3},@{base=$script:base;task=$script:reductionTask;version=2})) {
            Assert-True ($null -eq (Get-ReviewReductionPolicy $script:repo $wrong.base $script:head $wrong.version $wrong.task)) 'M4 policy escaped identity'
        }
        $badAncestorTool = Join-Path $fixtureRoot ([guid]::NewGuid().ToString('N') + '.ps1')
        $wrongAncestor = 'f' * 40
        [IO.File]::WriteAllText($badAncestorTool, [IO.File]::ReadAllText($script:reductionTool).Replace("`$approvalAncestor = '$script:base'", "`$approvalAncestor = '$wrongAncestor'"))
        . $badAncestorTool -Library
        $rejected = $false
        try { $null = Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask } catch { $rejected = $_.Exception.Message.Contains('REDUCTION_APPROVAL') }
        Assert-True $rejected 'M4 wrong ancestor accepted'
        . $script:reductionTool -Library
        $memberPlan = Get-ReviewMemberPlan (Get-ReviewSnapshot $script:repo $script:base $script:head 3 $script:reductionTask $true)
        $actual = Invoke-ReductionPackage
        Assert-True ($actual.Exit -eq 0) "M4 create failed: $($actual.Output)"
        $zip = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
        $archive = [IO.Compression.ZipFile]::OpenRead($zip)
        try {
            $manifest = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json
            Assert-True ($manifest.evidenceReduction.policyId -ceq 'G4-M4-REVIEW-FIX-EVIDENCE-1') 'M4 binding absent'
            foreach ($member in $memberPlan.members) { Assert-True ($null -ne $archive.GetEntry($member.path)) 'M4 precheck member differs from final package' }
            $paths = @($manifest.sourceMembers.gitPath)
            foreach ($path in $script:reductionRequired + @($script:reductionValidation,($script:reductionRoot+'review-fix-01/originals-index.json'),($script:reductionRoot+'review-fix-01/causal-original.txt'))) { Assert-True ($paths -ccontains $path) 'Current closure omitted' }
            Assert-True ($paths -cnotcontains ($script:reductionRoot+'old/omitted.txt')) 'Historical payload duplicated'
            $index = Read-ZipText $archive 'evidence-index.json' | ConvertFrom-Json
            Assert-True (@($index | Where-Object gitPath -CEQ ($script:reductionRoot+'old/omitted.txt'))[0].commit -ceq $script:head) 'Exact historical recovery absent'
        } finally { $archive.Dispose() }
        $verified = Invoke-ReductionPackage -VerifyPath $zip
        Assert-True ($verified.Exit -eq 0) "M4 reopen failed: $($verified.Output)"
        foreach ($missing in @($script:reductionRequired[1],$script:reductionRequired[-1])) {
            $saved = $script:reductionSelection.retainedPaths
            $script:reductionSelection.retainedPaths = @($saved | Where-Object { $_ -cne $missing })
            Write-Fixture $script:reductionSelectionPath ($script:reductionSelection | ConvertTo-Json -Depth 6); $script:head = Commit-Fixture
            $rejected = $false
            try { $null = Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask } catch { $rejected = $true }
            Assert-True $rejected 'Missing historical index or original closure accepted'
            $script:reductionSelection.retainedPaths = $saved
        }
        Write-Fixture $script:reductionSelectionPath ($script:reductionSelection | ConvertTo-Json -Depth 6)
        Write-Fixture ($script:reductionRoot+'review-fix-01/authorization-original.md') "forged approval`n"; $script:head = Commit-Fixture
        $rejected = $false
        try { $null = Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask } catch { $rejected = $_.Exception.Message.Contains('REDUCTION_APPROVAL') }
        Assert-True $rejected 'M4 wrong approval accepted'
    }
    Case 'm5 reduction preserves current evidence and rejects identity or closure drift' {
        if ($IsWindows) { Assert-ReductionWindowsRefusal }
        $script:reductionTask = 'G4-M5-INTEGRATION-001'
        $script:reductionRoot = "docs/evidence/$script:reductionTask/"
        $script:reductionRun = 'package-final-01'
        $script:reductionValidation = $script:reductionRoot + $script:reductionRun + '/validation.json'
        $script:reductionSelectionPath = $script:reductionRoot + 'review-evidence-selection.json'
        $required = @('authorization.md', 'acceptance.json', 'additional-authorization.json', 'independent-expectations.json', 'non-author-final-source-review.json', 'validation.json', 'integration-01/originals-index.json', 'integration-01/originals/integration-01/counterexample-closeout.json', 'integration-01/originals/integration-01/resource-closeout.json', 'integration-01/originals/integration-01/prerequisite-standard-907aa290-8f3c-4e9b-b1cf-89e8d6051803.json')
        foreach ($path in $required) { Write-Fixture ($script:reductionRoot + $path) "[]`n" }
        $approval = $script:reductionRoot + 'authorization.md'
        Write-Fixture $approval ([IO.File]::ReadAllText((Join-Path (Split-Path (Split-Path $PackageScript -Parent) -Parent) $approval)))
        $current = $script:reductionRoot + 'integration-01/originals/current-failure.txt'
        $checkpoint = $script:reductionRoot + 'integration-01/originals/integration-01/prerequisite-safety-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.json'
        Write-Fixture $current "original current failure remains included`n"
        Write-Fixture $checkpoint "historical cumulative state; exact Git recovery`n"
        $supersededName = 'qualification-security-unit-9895c18f7dae4ddcb2a7840aac2b3e09.json'
        $superseded = $script:reductionRoot + 'integration-01/originals/integration-01/' + $supersededName
        $supersededBytes = '{"taskId":"G4-M5-INTEGRATION-001","runId":"integration-01","status":"PASS","exitCode":0,"inputsUnchanged":true}' + "`n"
        Write-Fixture $superseded $supersededBytes
        $supersededHash = (Get-FileHash -LiteralPath (Join-Path $script:repo $superseded) -Algorithm SHA256).Hash.ToLowerInvariant()
        $closurePath = $script:reductionRoot + 'package-final-01/final-impact-originals/integration-01/product-qualification-after-package-admission.json'
        $closure = @{ taskId = $script:reductionTask; status = 'PASS'; results = @(@{ originals = @(@{ path = 'current-qualification.json' }) }) }
        Write-Fixture $closurePath ($closure | ConvertTo-Json -Depth 8)
        $tested = Commit-Fixture
        Write-LocalFixture $script:reductionValidation (@{ evidenceSchemaVersion = 2; validationSource = 'LOCAL'; testedCommit = $tested; checks = @(@{ name = 'fixture-local'; command = 'fixture only'; status = 'PASS'; exitCode = 0; output = 'not a product claim' }); ci = @{ status = 'NOT_RUN'; runId = $null; url = $null; commit = $null; conclusion = $null } } | ConvertTo-Json -Depth 6)
        $kept = @($required | ForEach-Object { $script:reductionRoot + $_ }) + @($current)
        $selection = @{ schemaVersion = 1; finalRun = $script:reductionRun; validationPath = $script:reductionValidation; retainedPaths = $kept }
        Write-Fixture $script:reductionSelectionPath ($selection | ConvertTo-Json -Depth 6)
        $script:head = Commit-Fixture
        $script:reductionTool = Join-Path $fixtureRoot ([guid]::NewGuid().ToString('N') + '.ps1')
        # 仅隔离Git夹具替换准确提交；生产入口没有批准参数旁路。
        $source = [IO.File]::ReadAllText($PackageScript).Replace('a6716b11c3795e5670c07f1ca37057e5649bed89', $script:base).Replace('237c831166783deb3f3c68ec11e79824cd485540', $script:base).Replace('a14bfc634d1245f5f84a3bd44c72fcdc2d7971c0a7d5f129909f4d36bf4b15c0', $supersededHash)
        [IO.File]::WriteAllText($script:reductionTool, $source)
        . $script:reductionTool -Library
        $policy = Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask
        Assert-True ($null -ne $policy -and $policy.policyId -ceq 'G4-M5-PG-INTEGRATION-EVIDENCE-1') 'M5 approved consumer absent'
        foreach ($wrong in @(@{base=('f'*40);task=$script:reductionTask;version=3},@{base=$script:base;task='OTHER';version=3},@{base=$script:base;task=$script:reductionTask;version=2})) {
            Assert-True ($null -eq (Get-ReviewReductionPolicy $script:repo $wrong.base $script:head $wrong.version $wrong.task)) 'M5 policy escaped identity'
        }
        $actual = Invoke-ReductionPackage
        Assert-True ($actual.Exit -eq 0) "M5 create failed: $($actual.Output)"
        $zip = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0].FullName
        $archive = [IO.Compression.ZipFile]::OpenRead($zip)
        try {
            $manifest = Read-ZipText $archive 'manifest.json' | ConvertFrom-Json
            Assert-True (@($manifest.sourceMembers.gitPath) -ccontains $current) 'Current failure omitted'
            Assert-True (@($manifest.sourceMembers.gitPath) -cnotcontains $checkpoint) 'Intermediate checkpoint duplicated'
            $index = Read-ZipText $archive 'evidence-index.json' | ConvertFrom-Json
            Assert-True (@($index | Where-Object gitPath -CEQ $checkpoint)[0].commit -ceq $script:head) 'Checkpoint Git recovery missing'
        } finally { $archive.Dispose() }
        $verified = Invoke-ReductionPackage -VerifyPath $zip
        Assert-True ($verified.Exit -eq 0) "M5 reopen failed: $($verified.Output)"
        foreach ($missing in @($current, ($script:reductionRoot + $required[-1]))) {
            $selection.retainedPaths = @($kept | Where-Object { $_ -cne $missing })
            Write-Fixture $script:reductionSelectionPath ($selection | ConvertTo-Json -Depth 6); $script:head = Commit-Fixture
            $rejected = $false
            try { $null = Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask } catch { $rejected = $_.Exception.Message.Contains('REDUCTION_') }
            Assert-True $rejected 'Required current or referenced checkpoint evidence omitted'
        }
        $selection.retainedPaths = $kept
        Write-Fixture $script:reductionSelectionPath ($selection | ConvertTo-Json -Depth 6)
        foreach ($mutation in @('current-reference', 'changed-bytes')) {
            if ($mutation -ceq 'current-reference') { $closure.results[0].originals[0].path = $supersededName; Write-Fixture $closurePath ($closure | ConvertTo-Json -Depth 8) }
            else { Write-Fixture $superseded "changed historical qualification`n" }
            $script:head = Commit-Fixture
            $rejected = $false
            try { $null = Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask } catch { $rejected = $_.Exception.Message.Contains('REDUCTION_REFERENCE') }
            Assert-True $rejected 'Current referenced or changed qualification silently omitted'
            $closure.results[0].originals[0].path = 'current-qualification.json'; Write-Fixture $closurePath ($closure | ConvertTo-Json -Depth 8)
            Write-Fixture $superseded $supersededBytes
        }
        Write-Fixture $approval "forged approval`n"; $script:head = Commit-Fixture
        $rejected = $false
        try { $null = Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask } catch { $rejected = $_.Exception.Message.Contains('REDUCTION_APPROVAL') }
        Assert-True $rejected 'M5 forged approval accepted'
        $badAncestorTool = Join-Path $fixtureRoot ([guid]::NewGuid().ToString('N') + '.ps1')
        [IO.File]::WriteAllText($badAncestorTool, $source.Replace("`$approvalAncestor = '$script:base'", "`$approvalAncestor = '$('f'*40)'"))
        . $badAncestorTool -Library
        Write-Fixture $approval ([IO.File]::ReadAllText((Join-Path (Split-Path (Split-Path $PackageScript -Parent) -Parent) $approval))); $script:head = Commit-Fixture
        $rejected = $false
        try { $null = Get-ReviewReductionPolicy $script:repo $script:base $script:head 3 $script:reductionTask } catch { $rejected = $_.Exception.Message.Contains('REDUCTION_APPROVAL') }
        Assert-True $rejected 'M5 wrong ancestor accepted'
    }
    Case 'early committed representative evidence measures without final PASS or ZIP' {
        Write-Fixture 'docs/evidence/TEST-001/representative.json' '{"taskId":"TEST-001","status":"NOT_RUN","observations":["first real output shape"]}'
        $script:head = Commit-Fixture
        $actual = Invoke-Package -Local -DeclaredStatus NOT_RUN -Extra @('-MeasureOnly')
        Assert-True ($actual.Exit -eq 0) "Early measurement rejected: $($actual.Output)"
        $measured = $actual.Output | ConvertFrom-Json -AsHashtable
        Assert-True ($measured.status -ceq 'MEASURED_NOT_READY_FOR_ACCEPTANCE') 'Early size became acceptance'
        Assert-True ($measured.members -ccontains 'review-evidence/TEST-001/representative.json') 'New representative absent from measured candidate'
        Assert-True ($measured.headSha -ceq $script:head) 'Measurement candidate changed'
        Assert-True (-not (Test-Path (Join-Path $script:repo 'artifacts/reviews'))) 'Early measurement published ZIP'
    }
    Case 'early measurement exposes production logical mapping and actual shared payload' {
        $bytes = '{"synthetic":"EF-01","status":"NOT_RUN"}'
        Write-Fixture 'a-shared.json' $bytes
        Write-Fixture 'docs/evidence/TEST-001/reports/a.json' $bytes
        Write-Fixture 'docs/evidence/TEST-001/reports/b.json' $bytes
        $script:head = Commit-Fixture
        $paths = @('docs/evidence/TEST-001/reports/a.json', 'docs/evidence/TEST-001/reports/b.json')
        $actual = Invoke-Package -Local -DeclaredStatus NOT_RUN -Extra @('-MeasureOnly', '-MeasurementPathsJson', (ConvertTo-Json -InputObject $paths -Compress))
        Assert-True ($actual.Exit -eq 0) "Mapped early measurement rejected: $($actual.Output)"
        $measured = $actual.Output | ConvertFrom-Json -AsHashtable
        $description = $measured.representativeEvidence
        Assert-True ($description.protocolVersion -eq 1 -and $description.taskId -ceq 'TEST-001' -and $description.headSha -ceq $script:head -and $description.baseSha -ceq $script:base) 'Description identity differs'
        Assert-True ($description.sourceMembers.Count -eq 2 -and $description.payloads.Count -eq 1) 'Logical paths or payload dedup lost'
        . $PackageScript -Library
        $snapshot = Get-ReviewSnapshot $script:repo $script:base $script:head 3 'TEST-001' $true
        foreach ($path in $paths) {
            $mapped = @($description.sourceMembers | Where-Object gitPath -CEQ $path)
            $expected = @($snapshot.Mapping | Where-Object gitPath -CEQ $path)
            Assert-True ($mapped.Count -eq 1 -and ($mapped | ConvertTo-Json -Compress) -ceq ($expected | ConvertTo-Json -Compress)) 'Output must use production logical mapping'
            Assert-True ($mapped[0].archivePath -ceq 'source/a-shared.json') 'Legal source payload sharing rejected'
        }
        $payload = $description.payloads[0]
        Assert-True ($payload.sha256 -ceq (Get-ReviewHash $snapshot.Members[$payload.archivePath]) -and $payload.sizeBytes -eq $snapshot.Members[$payload.archivePath].Length) 'Payload metadata must reflect actual bytes'
        Assert-True ($measured.members -ccontains $payload.archivePath) 'Payload not in measured members'
        Assert-True (-not (Test-Path (Join-Path $script:repo 'artifacts/reviews'))) 'Pure measurement published ZIP'
        $duplicate = ConvertTo-Json -InputObject @($paths[0], $paths[0]) -Compress
        $bad = Invoke-Package -Local -DeclaredStatus NOT_RUN -Extra @('-MeasureOnly', '-MeasurementPathsJson', $duplicate)
        Assert-True ($bad.Exit -ne 0 -and $bad.Output.Contains('MEASUREMENT_REQUEST')) 'Duplicate request accepted'
        $bad = Invoke-Package -Local -Extra @('-MeasurementPathsJson', (ConvertTo-Json -InputObject $paths -Compress))
        Assert-True ($bad.Exit -ne 0 -and $bad.Output.Contains('MEASUREMENT_REQUEST')) 'Description request altered formal package path'
    }
    Case 'member plan and exact candidate share production V3 bytes without publishing ZIP' {
        Write-LocalFixture 'docs/evidence/TEST-001/local.json' (@{ evidenceSchemaVersion = 2; validationSource = 'LOCAL'; testedCommit = $script:head; checks = @(@{ name = 'fixture'; command = 'fixture only'; status = 'PASS'; exitCode = 0; output = 'not product evidence' }); ci = @{ status = 'NOT_RUN'; runId = $null; url = $null; commit = $null; conclusion = $null } } | ConvertTo-Json -Depth 6)
        $script:head = Commit-Fixture
        $plan = Invoke-Package -Local -Extra @('-MemberPlan')
        Assert-True ($plan.Exit -eq 0) "Plan rejected: $($plan.Output)"
        $p = $plan.Output | ConvertFrom-Json -AsHashtable
        Assert-True ($p.measurement -ceq 'ESTIMATE_SELECTED_MEMBERS' -and $p.metadataReserveBytes -eq 1MB) 'Estimate not distinguished'
        $measured = Invoke-Package -Local -DeclaredStatus PASS -Extra @('-EvidencePath', 'docs/evidence/TEST-001/local.json', '-MeasureOnly')
        Assert-True ($measured.Exit -eq 0) "Measurement rejected: $($measured.Output)"
        $m = $measured.Output | ConvertFrom-Json -AsHashtable
        Assert-True (-not (Test-Path (Join-Path $script:repo 'artifacts/reviews'))) 'Precheck published output'
        $built = Invoke-Package -Local -DeclaredStatus PASS -Extra @('-EvidencePath', 'docs/evidence/TEST-001/local.json')
        Assert-True ($built.Exit -eq 0) "Build rejected: $($built.Output)"
        $zip = @(Get-ChildItem (Join-Path $script:repo 'artifacts/reviews') -Filter '*.zip')[0]
        Assert-True ([Math]::Abs($zip.Length - $m.sizeBytes) -lt 4096 -and $m.limitation.Contains('timestamps')) 'Candidate metadata variance unexplained'
        $archive = [IO.Compression.ZipFile]::OpenRead($zip.FullName)
        try {
            foreach ($row in $p.members) {
                $entry = $archive.GetEntry($row.path)
                Assert-True ($null -ne $entry -and $entry.Length -eq $row.sizeBytes) 'Plan member missing or different'
            }
            Assert-True ($archive.Entries.Count -eq $m.members.Count) 'Final member set differs'
        } finally { $archive.Dispose() }
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
$notRun = @($results | Where-Object Status -eq 'NOT_RUN').Count
Write-Output "ReviewPackage: $($results.Count) tests, $failed failures, $notRun platform cases NOT_RUN; product/container tests NOT_RUN."
if ($failed -gt 0) { throw 'Review package self-tests failed' }
