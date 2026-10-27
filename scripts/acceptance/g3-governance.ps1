#Requires -Version 7.4
[CmdletBinding()]
param([ValidateSet('M1')][string]$Milestone = 'M1', [string]$RuntimeFile, [switch]$StartRuntime, [switch]$ModulesOnly)
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$beforeEvidence = [Environment]::GetEnvironmentVariable('PLATFORM_EVIDENCE_DIR', 'Process')
$beforeReaderIdentity = [Environment]::GetEnvironmentVariable('G3_READER_IDENTITY_SHA', 'Process')
Push-Location $root
try {
    $env:PLATFORM_EVIDENCE_DIR = 'docs/evidence/G3-M1-001/runtime'
    & ./scripts/verify.ps1 -SelfTest
    if ($LASTEXITCODE -ne 0) { throw 'Engineering self-tests failed' }
    dotnet restore backend/OntologyPlatform.slnx --locked-mode
    if ($LASTEXITCODE -ne 0) { throw 'Frozen restore failed' }
    & ./scripts/verify-web.ps1 -Restore
    if ($LASTEXITCODE -ne 0) { throw 'Web checks failed' }
    $tools = & ./scripts/bootstrap-web-tools.ps1 | ConvertFrom-Json
    & $tools.nodePath --test scripts/tests/G3ReadBackpressure.Tests.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Read backpressure harness boundaries failed' }
    & ./scripts/verify.ps1 -RunNative -RunTests -SkipWeb
    if ($LASTEXITCODE -ne 0) { throw 'Native checks failed' }
    dotnet build backend/OntologyPlatform.slnx --configuration Release --no-restore
    if ($LASTEXITCODE -ne 0) { throw 'Release build failed' }
    python3 scripts/tests/G3AppHost.Tests.py
    if ($LASTEXITCODE -ne 0) { throw 'Actual AppHost prefix boundary failed' }
    # 正式栈写V2前先运行兼容reader，再保留独立二进制供真实制品后验读取。
    dotnet test --project backend/tests/OntologyPlatform.G2ContractTests --filter 'FullyQualifiedName~G3ManifestContractTests.V2RoundtripRetainsExactAssessmentBinding' --output Detailed
    if ($LASTEXITCODE -ne 0) { throw 'Pre-write V2 compatible binary failed' }
    $reader = Join-Path $root 'artifacts/g3-m1/fallback-reader-v4'
    if (-not (Test-Path -LiteralPath $reader)) {
        $null = New-Item -ItemType Directory -Path $reader -Force
        Copy-Item -Path (Join-Path $root 'backend/tests/OntologyPlatform.G2ContractTests/bin/Debug/net10.0/*') -Destination $reader -Recurse
    }
    $freeze = python3 scripts/acceptance/g3-compatibility.py --freeze | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $freeze.status -ne 'PASS') { throw 'Retained fallback reader failed before V2 writes' }
    $env:G3_READER_IDENTITY_SHA = $freeze.freezeSha256
    node apps/web/scripts/generate-types.mjs --check
    if ($LASTEXITCODE -ne 0) { throw 'Generated types drifted' }
    python3 scripts/tests/G3Evidence.Tests.py
    if ($LASTEXITCODE -ne 0) { throw 'Evidence boundaries failed' }
    python3 scripts/tests/G3Acceptance.Tests.py
    if ($LASTEXITCODE -ne 0) { throw 'M1 orchestration boundaries failed' }
    python3 scripts/acceptance/test-governance.py
    if ($LASTEXITCODE -ne 0) { throw 'Real governance integration failed' }
    & ./scripts/acceptance/g2-integration.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Real semantic/publication/query/run integration failed' }
    if (-not $ModulesOnly) {
        $arguments = @('scripts/acceptance/g3-acceptance-runtime.py')
        if ($RuntimeFile) { $arguments += @('--runtime-file', $RuntimeFile) }
        if ($StartRuntime) { $arguments += '--start-runtime' }
        if (-not $RuntimeFile -and -not $StartRuntime) { throw 'RuntimeFile or StartRuntime required for real browser acceptance' }
        python3 @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Real M1 vertical acceptance failed' }
    }
    Write-Output "PASS: selected G3-$Milestone checks; ModulesOnly=$ModulesOnly. Monaco/real LLM/Windows/Intel/production not certified."
} finally {
    [Environment]::SetEnvironmentVariable('PLATFORM_EVIDENCE_DIR', $beforeEvidence, 'Process')
    [Environment]::SetEnvironmentVariable('G3_READER_IDENTITY_SHA', $beforeReaderIdentity, 'Process')
    Pop-Location
}
