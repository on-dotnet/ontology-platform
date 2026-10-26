#Requires -Version 7.4
[CmdletBinding()]
param([string]$RuntimeFile, [switch]$StartRuntime)
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Push-Location $root
try {
    & ./scripts/verify.ps1 -SelfTest
    if ($LASTEXITCODE -ne 0) { throw 'Repository checks failed' }
    dotnet restore backend/OntologyPlatform.slnx --locked-mode
    if ($LASTEXITCODE -ne 0) { throw 'Locked restore failed' }
    & ./scripts/verify-web.ps1 -Restore
    if ($LASTEXITCODE -ne 0) { throw 'Web verification failed' }
    & ./scripts/verify.ps1 -RunNative -RunTests -SkipWeb
    if ($LASTEXITCODE -ne 0) { throw 'Native verification failed' }
    dotnet build backend/OntologyPlatform.slnx --configuration Release --no-restore
    if ($LASTEXITCODE -ne 0) { throw 'Release AppHost build failed' }
    python3 scripts/acceptance/test-governance.py
    if ($LASTEXITCODE -ne 0) { throw 'Real G1 governance integration failed' }
    & ./scripts/acceptance/g2-integration.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Real G2 module integration failed' }
    # 浏览器/LGTM需实际AppHost；新建运行必须显式选择，不能重用历史凭证或环境。
    $arguments = @('scripts/acceptance/g2-acceptance-runtime.py')
    if ($RuntimeFile) { $arguments += @('--runtime-file', $RuntimeFile) }
    if ($StartRuntime) { $arguments += '--start-runtime' }
    if (-not $RuntimeFile -and -not $StartRuntime) { throw 'Specify RuntimeFile for a running G2 profile, or StartRuntime for a new isolated profile' }
    python3 @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Real browser OIDC/LGTM/performance acceptance failed' }
    Write-Output 'PASS: selected local synthetic engineering and tool pipeline. Monaco remains paused; real paid model, Windows/Intel and production are not certified.'
} finally { Pop-Location }
