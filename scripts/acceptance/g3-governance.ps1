#Requires -Version 7.4
[CmdletBinding()]
param([ValidateSet('M1', 'M2')][string]$Milestone = 'M1', [string]$RuntimeFile, [switch]$StartRuntime, [switch]$ModulesOnly)
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$beforeEvidence = [Environment]::GetEnvironmentVariable('PLATFORM_EVIDENCE_DIR', 'Process')
$beforeReaderIdentity = [Environment]::GetEnvironmentVariable('G3_READER_IDENTITY_SHA', 'Process')
$pipeline = $null
function Save-Pipeline {
    $pipeline | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $pipelineRoot 'pipeline.json') -Encoding utf8
}
function Start-PipelineStep([string]$Name) {
    if ($pipeline.currentStep -ge 0) { $pipeline.stages[$pipeline.currentStep].status = 'PASS' }
    $pipeline.currentStep = [Array]::IndexOf($stageNames, $Name)
    if ($pipeline.currentStep -lt 0) { throw 'Unknown fixed M1 stage' }
    $pipeline.stages[$pipeline.currentStep].status = 'RUNNING'
    Save-Pipeline
}
Push-Location $root
try {
    $pipelineId = 'pipeline-' + [Guid]::NewGuid().ToString('N')
    $env:PLATFORM_EVIDENCE_DIR = 'docs/evidence/G3-' + $Milestone + '-001/runtime/' + $pipelineId
    $pipelineRoot = Join-Path $root $env:PLATFORM_EVIDENCE_DIR
    $null = New-Item -ItemType Directory -Path $pipelineRoot
    $stageNames = @('self-test', 'frozen-restore', 'web', 'backpressure', 'native', 'release-build', 'apphost-prefix',
        'prewrite-reader', 'generated-types', 'control-boundaries', 'real-governance', 'real-modules', 'runtime')
    $sourceHead = (git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Committed source identity unavailable' }
    $pipeline = @{ runId = $pipelineId; sourceHead = $sourceHead; milestone = $Milestone; modulesOnly = [bool]$ModulesOnly;
        status = 'RUNNING'; currentStep = -1; startedAtUtc = [DateTimeOffset]::UtcNow.ToString('O');
        stages = @($stageNames | ForEach-Object { @{ name = $_; status = 'NOT_RUN' } }) }
    Start-PipelineStep 'self-test'
    & ./scripts/verify.ps1 -SelfTest
    if ($LASTEXITCODE -ne 0) { throw 'Engineering self-tests failed' }
    Start-PipelineStep 'frozen-restore'
    dotnet restore backend/OntologyPlatform.slnx --locked-mode
    if ($LASTEXITCODE -ne 0) { throw 'Frozen restore failed' }
    Start-PipelineStep 'web'
    & ./scripts/verify-web.ps1 -Restore
    if ($LASTEXITCODE -ne 0) { throw 'Web checks failed' }
    Start-PipelineStep 'backpressure'
    $tools = & ./scripts/bootstrap-web-tools.ps1 | ConvertFrom-Json
    & $tools.nodePath --test scripts/tests/G3ReadBackpressure.Tests.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Read backpressure harness boundaries failed' }
    Start-PipelineStep 'native'
    & ./scripts/verify.ps1 -RunNative -RunTests -SkipWeb
    if ($LASTEXITCODE -ne 0) { throw 'Native checks failed' }
    Start-PipelineStep 'release-build'
    dotnet build backend/OntologyPlatform.slnx --configuration Release --no-restore
    if ($LASTEXITCODE -ne 0) { throw 'Release build failed' }
    Start-PipelineStep 'apphost-prefix'
    python3 scripts/tests/G3AppHost.Tests.py
    if ($LASTEXITCODE -ne 0) { throw 'Actual AppHost prefix boundary failed' }
    Start-PipelineStep 'prewrite-reader'
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
    Start-PipelineStep 'generated-types'
    node apps/web/scripts/generate-types.mjs --check
    if ($LASTEXITCODE -ne 0) { throw 'Generated types drifted' }
    Start-PipelineStep 'control-boundaries'
    python3 scripts/tests/G3Evidence.Tests.py
    if ($LASTEXITCODE -ne 0) { throw 'Evidence boundaries failed' }
    python3 scripts/tests/G3Acceptance.Tests.py
    if ($LASTEXITCODE -ne 0) { throw 'M1 orchestration boundaries failed' }
    Start-PipelineStep 'real-governance'
    python3 scripts/acceptance/test-governance.py
    if ($LASTEXITCODE -ne 0) { throw 'Real governance integration failed' }
    Start-PipelineStep 'real-modules'
    & ./scripts/acceptance/g2-integration.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Real semantic/publication/query/run integration failed' }
    if (-not $ModulesOnly) {
        Start-PipelineStep 'runtime'
        $arguments = @('scripts/acceptance/g3-acceptance-runtime.py', '--milestone', $Milestone)
        if ($RuntimeFile) { $arguments += @('--runtime-file', $RuntimeFile) }
        if ($StartRuntime) { $arguments += '--start-runtime' }
        if (-not $RuntimeFile -and -not $StartRuntime) { throw 'RuntimeFile or StartRuntime required for real browser acceptance' }
        python3 @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Real M1 vertical acceptance failed' }
    }
    $pipeline.stages[$pipeline.currentStep].status = 'PASS'
    $pipeline.status = 'PASS'
    Write-Output "PASS: selected G3-$Milestone checks; ModulesOnly=$ModulesOnly. Monaco/real LLM/Windows/Intel/production not certified."
} finally {
    if ($null -ne $pipeline) {
        if ($pipeline.status -eq 'RUNNING') {
            $pipeline.status = 'FAIL'
            if ($pipeline.currentStep -ge 0) { $pipeline.stages[$pipeline.currentStep].status = 'FAIL' }
        }
        $pipeline.completedAtUtc = [DateTimeOffset]::UtcNow.ToString('O')
        Save-Pipeline
        Write-Output ("M1 evidence: " + $pipelineRoot)
    }
    [Environment]::SetEnvironmentVariable('PLATFORM_EVIDENCE_DIR', $beforeEvidence, 'Process')
    [Environment]::SetEnvironmentVariable('G3_READER_IDENTITY_SHA', $beforeReaderIdentity, 'Process')
    Pop-Location
}
