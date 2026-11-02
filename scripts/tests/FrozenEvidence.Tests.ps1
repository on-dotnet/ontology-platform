#Requires -Version 7.4
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../verify.ps1') -Library
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$path = 'docs/evidence/G3-M4-001/mac-master/actual-v2-manifest.json'
$content = [IO.File]::ReadAllBytes((Join-Path $root $path))
if (-not (Test-FrozenEvidenceFormat $path $content)) { throw 'Original immutable evidence was not recognized' }
if (Test-FrozenEvidenceFormat $path ([byte[]]($content + 32))) { throw 'Changed bytes bypassed text format checks' }
if (Test-FrozenEvidenceFormat 'docs/evidence/G3-M5-001/manifest.json' $content) { throw 'New task inherited historical exception' }
if (Test-FrozenEvidenceFormat 'source.json' $content) { throw 'Product source inherited evidence exception' }
if (Test-FrozenEvidenceFormat $path ([byte[]](@(239, 187, 191) + $content))) { throw 'BOM variant bypassed exact raw evidence hash' }
Write-Output 'FrozenEvidence: exact original bytes only, 5 checks PASS; history unchanged.'

# 新例外以独立临时仓库验证真实入口；上面的G3-M4五项断言原样保留。
$jsonlPath = 'docs/evidence/G4-M1-FINAL-GATES-001/host-monitor.json'
$jsonlBytes = [IO.File]::ReadAllBytes((Join-Path $root $jsonlPath))
$fixtureParent = Join-Path $root 'artifacts/g4-m1-verify-recovery-001'
$fixture = Join-Path $fixtureParent ('frozen-jsonl-' + [guid]::NewGuid().ToString('N'))
$jsonlAssertions = 0
function Assert-FrozenJsonl {
    param([bool]$Condition, [string]$Name)
    if (-not $Condition) { throw "FrozenJsonl assertion failed: $Name" }
    $script:jsonlAssertions++
    Write-Output "FrozenJsonl PASS: $Name"
}
function Assert-JsonEntrance {
    param([bool]$Rejected, [string]$Name)
    $checks = @(Test-Repository -RepositoryRoot $fixture)
    $jsonFailures = @($checks | Where-Object { $_.Check -eq 'json' -and $_.Status -eq 'FAIL' })
    $unrelatedFailures = @($checks | Where-Object { $_.Status -eq 'FAIL' -and $_.Check -notin @('json', 'text-format') })
    Assert-FrozenJsonl ($unrelatedFailures.Count -eq 0 -and $jsonFailures.Count -eq [int]$Rejected) "$Name real Test-Repository json rejection=$Rejected"
}
try {
    # 所有夹具从既有配置复制，仅修改本次随机目录；不触碰旧证据。
    foreach ($parent in @($fixtureParent, (Split-Path $fixtureParent -Parent))) {
        if ((Test-Path -LiteralPath $parent) -and ((Get-Item -LiteralPath $parent).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Linked fixture parent refused' }
    }
    New-Item -ItemType Directory -Path $fixture | Out-Null
    $required = @('global.json', 'Directory.Build.props', 'Directory.Packages.props', 'NuGet.Config', '.config/dotnet-tools.json',
        'package.json', 'apps/web/package.json', 'pnpm-workspace.yaml', 'turbo.json', '.node-version',
        '.editorconfig', '.github/workflows/ci.yml', 'scripts/validate-structured-files.py', 'scripts/verification-requirements.txt')
    foreach ($relative in $required) {
        $destination = Join-Path $fixture $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
        Copy-Item -LiteralPath (Join-Path $root $relative) -Destination $destination
    }
    foreach ($relative in @('AGENTS.md', 'PLANS.md', 'backend/AGENTS.md', 'apps/web/AGENTS.md')) {
        $destination = Join-Path $fixture $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
        [IO.File]::WriteAllText($destination, "# Synthetic fixture`n")
    }
    $historicalTarget = Join-Path $fixture $jsonlPath
    New-Item -ItemType Directory -Force -Path (Split-Path $historicalTarget) | Out-Null
    [IO.File]::WriteAllBytes($historicalTarget, $jsonlBytes)
    Assert-FrozenJsonl (Test-FrozenJsonlEvidence $jsonlPath $jsonlBytes) 'exact historical bytes and structure accepted'
    Assert-JsonEntrance $false 'exact historical evidence'
    $originalText = [Text.Encoding]::UTF8.GetString($jsonlBytes)
    $rows = $originalText.TrimEnd("`n").Split("`n")
    $singleByte = [byte[]]$jsonlBytes.Clone()
    $singleByte[0] = 91
    $swapped = [string[]]$rows.Clone()
    ($swapped[0], $swapped[1]) = ($swapped[1], $swapped[0])
    $variants = [ordered]@{
        'single-byte' = $singleByte
        'truncated' = [byte[]]$jsonlBytes[0..($jsonlBytes.Length - 20)]
        'added-row' = [Text.Encoding]::UTF8.GetBytes($originalText + $rows[0] + "`n")
        'deleted-row' = [Text.Encoding]::UTF8.GetBytes(($rows[1..75] -join "`n") + "`n")
        'swapped-rows' = [Text.Encoding]::UTF8.GetBytes(($swapped -join "`n") + "`n")
        'trailing-empty-line' = [byte[]]($jsonlBytes + 10)
        'trailing-space' = [Text.Encoding]::UTF8.GetBytes($originalText.TrimEnd("`n") + " `n")
        'crlf' = [Text.Encoding]::UTF8.GetBytes($originalText.Replace("`n", "`r`n"))
        'bom' = [byte[]](@(239, 187, 191) + $jsonlBytes)
        'missing-final-lf' = [byte[]]$jsonlBytes[0..($jsonlBytes.Length - 2)]
        'invalid-json' = [Text.Encoding]::UTF8.GetBytes('!' + $originalText.Substring(1))
        'wrong-task' = [Text.Encoding]::UTF8.GetBytes($originalText.Replace('G4-M1-FINAL-GATES-001', 'G4-M1-FINAL-GATES-002'))
        'wrong-schema' = [Text.Encoding]::UTF8.GetBytes(($originalText -replace '"schemaVersion": 1', '"schemaVersion": 2'))
        'wrong-sequence' = [Text.Encoding]::UTF8.GetBytes(($originalText -replace '"sequence": 0,', '"sequence": 1,'))
        'noninteger-sequence' = [Text.Encoding]::UTF8.GetBytes(($originalText -replace '"sequence": 0,', '"sequence": 0.5,'))
        'ordinary-json-at-historical-path' = [Text.Encoding]::UTF8.GetBytes("{}`n")
    }
    foreach ($entry in $variants.GetEnumerator()) {
        Assert-FrozenJsonl (-not [Linq.Enumerable]::SequenceEqual[byte]($jsonlBytes, [byte[]]$entry.Value)) ($entry.Key + ' fixture actually changed')
        Assert-FrozenJsonl (-not (Test-FrozenJsonlEvidence $jsonlPath $entry.Value)) ($entry.Key + ' helper refused')
        [IO.File]::WriteAllBytes($historicalTarget, $entry.Value)
        Assert-JsonEntrance $true $entry.Key
    }
    Remove-Item -LiteralPath $historicalTarget
    foreach ($relative in @('source.json', 'other/host-monitor.json', 'docs/evidence/G4-M1-FINAL-GATES-001/prefix-host-monitor.json',
        'docs/evidence/G4-M1-FINAL-GATES-001/host-monitor.json.json', 'docs/evidence/G4-M1-FINAL-GATES-001-extra/host-monitor.json',
        'docs/evidence/G4-M1-FINAL-GATES-001/HOST-MONITOR.json')) {
        Assert-FrozenJsonl (-not (Test-FrozenJsonlEvidence $relative $jsonlBytes)) "$relative helper refused"
        $target = Join-Path $fixture $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        [IO.File]::WriteAllBytes($target, $jsonlBytes)
        Assert-JsonEntrance $true "$relative strict single JSON"
        Remove-Item -LiteralPath $target
    }
    $ordinary = Join-Path $fixture 'ordinary.json'
    [IO.File]::WriteAllText($ordinary, "{`"valid`": true}`n")
    Assert-JsonEntrance $false 'ordinary valid JSON'
    [IO.File]::WriteAllText($ordinary, "{broken`n")
    Assert-JsonEntrance $true 'ordinary malformed JSON'
    Write-Output "FrozenJsonl: $jsonlAssertions assertions PASS; original G3-M4 5 checks retained."
} finally {
    if ((Split-Path $fixture -Parent) -cne $fixtureParent -or (Split-Path $fixture -Leaf) -notmatch '^frozen-jsonl-[a-f0-9]{32}$') { throw 'Unsafe fixture cleanup' }
    if (Test-Path -LiteralPath $fixture) { Remove-Item -LiteralPath $fixture -Recurse -Force }
}
