# 仅测试工程检查器；不会启动应用或安装依赖。
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
. (Join-Path $repoRoot 'scripts/verify.ps1') -Library
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$fixtureRoot = [IO.Path]::GetFullPath((Join-Path $tempBase ('ontology-eng-check-' + [guid]::NewGuid().ToString('N'))))
$testCount = 0
function Assert-Check {
    param([bool]$Condition, [string]$Name)
    if (-not $Condition) { throw "FAIL: $Name" }
    $script:testCount++
    Write-Output "PASS: $Name"
}
try {
    New-Item -ItemType Directory -Path $fixtureRoot | Out-Null
    $paths = @(& git -C $repoRoot ls-files --cached --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot enumerate fixture input' }
    foreach ($path in $paths) {
        $source = Join-Path $repoRoot $path
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { continue }
        $destination = Join-Path $fixtureRoot $path
        New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination
    }
    $checks = @(Test-Repository -RepositoryRoot $fixtureRoot)
    Assert-Check (@($checks | Where-Object Status -eq 'FAIL').Count -eq 0) 'clean baseline accepted'
    $packagePath = Join-Path $fixtureRoot 'package.json'
    $original = [IO.File]::ReadAllText($packagePath)
    [IO.File]::WriteAllText($packagePath, ($original -replace '"ontology-platform"', '"wrong-name"'))
    $checks = @(Test-Repository -RepositoryRoot $fixtureRoot)
    Assert-Check (@($checks | Where-Object { $_.Check -eq 'naming' -and $_.Status -eq 'FAIL' }).Count -gt 0) 'wrong package name rejected'
    [IO.File]::WriteAllText($packagePath, $original)
    $brokenPath = Join-Path $fixtureRoot 'docs/evidence/G1-ENG-001/fixture.md'
    [IO.File]::WriteAllText($brokenPath, "# Fixture`n`n[missing](missing-target.md)`n")
    $checks = @(Test-Repository -RepositoryRoot $fixtureRoot)
    Assert-Check (@($checks | Where-Object { $_.Check -eq 'markdown-links' -and $_.Status -eq 'FAIL' }).Count -gt 0) 'broken relative link rejected'
    [IO.File]::WriteAllText($brokenPath, "# Fixture`n`nSynthetic test value: " + 'gh' + 'p_' + ('A' * 36) + "`n")
    $checks = @(Test-Repository -RepositoryRoot $fixtureRoot)
    Assert-Check (@($checks | Where-Object { $_.Check -eq 'secret-patterns' -and $_.Status -eq 'FAIL' }).Count -gt 0) 'synthetic token rejected without printing value'
    [IO.File]::WriteAllText($brokenPath, "# Fixture`n`nSafe fixture.`n")
    $sourceFixture = Join-Path $fixtureRoot 'synthetic.ts'
    [IO.File]::WriteAllText($sourceFixture, '// Synthetic: ' + 'gh' + 'p_' + ('B' * 36) + "`n")
    $checks = @(Test-Repository -RepositoryRoot $fixtureRoot)
    Assert-Check (@($checks | Where-Object { $_.Check -eq 'secret-patterns' -and $_.Status -eq 'FAIL' }).Count -gt 0) 'synthetic token in TypeScript rejected'
    [IO.File]::WriteAllText($sourceFixture, "// Safe fixture.`n")
    $envFixture = Join-Path $fixtureRoot '.env'
    [IO.File]::WriteAllText($envFixture, 'API_KEY=' + 'synthetic-' + ('C' * 24) + "`n")
    $checks = @(Test-Repository -RepositoryRoot $fixtureRoot)
    Assert-Check (@($checks | Where-Object { $_.Check -eq 'secret-patterns' -and $_.Status -eq 'FAIL' }).Count -gt 0) 'credential assignment in dot-env rejected'
    [IO.File]::WriteAllText($envFixture, "# Safe fixture.`n")
    $workflowPath = Join-Path $fixtureRoot '.github/workflows/ci.yml'
    $workflowOriginal = [IO.File]::ReadAllText($workflowPath)
    [IO.File]::WriteAllText($workflowPath, ($workflowOriginal -replace 'actions/checkout@[a-f0-9]{40}', 'actions/checkout@main'))
    $checks = @(Test-Repository -RepositoryRoot $fixtureRoot)
    Assert-Check (@($checks | Where-Object { $_.Check -eq 'workflow-policy' -and $_.Status -eq 'FAIL' }).Count -gt 0) 'unpinned action rejected'
    [IO.File]::WriteAllText($workflowPath, $workflowOriginal)
    # 隔离假目标只验证调用目录/参数，不调用真实dotnet，不创建业务工程。
    [IO.File]::WriteAllText((Join-Path $fixtureRoot 'backend/Fixture.csproj'), "<Project />`n")
    $nativeCalls = [Collections.Generic.List[object]]::new()
    function dotnet {
        $nativeCalls.Add([pscustomobject]@{ Location = (Get-Location).Path; Arguments = @($args) })
        $global:LASTEXITCODE = 0
    }
    # Windows临时目录可能使用8.3短名，按Provider解析为同一种路径再比较。
    Push-Location $fixtureRoot
    try { $expectedNativeLocation = (Get-Location).Path }
    finally { Pop-Location }
    Push-Location $tempBase
    try { & (Join-Path $repoRoot 'scripts/verify.ps1') -Root $fixtureRoot -RunNative }
    finally { Pop-Location }
    Assert-Check ($nativeCalls.Count -eq 2 -and @($nativeCalls | Where-Object { $_.Location -ne $expectedNativeLocation }).Count -eq 0) 'native commands resolve SDK and config from selected Root'
    Write-Output "Checker tests: $testCount passed; application tests: NOT_RUN."
} finally {
    $resolvedFixture = [IO.Path]::GetFullPath($fixtureRoot)
    if (-not $resolvedFixture.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase) -or
        (Split-Path $resolvedFixture -Leaf) -notmatch '^ontology-eng-check-[a-f0-9]{32}$') {
        throw 'Refusing cleanup outside generated temporary fixture'
    }
    if (Test-Path -LiteralPath $resolvedFixture) { Remove-Item -LiteralPath $resolvedFixture -Recurse -Force }
}
