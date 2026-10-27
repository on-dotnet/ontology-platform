#Requires -Version 7.4
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$originalPath = [Environment]::GetEnvironmentVariable('PATH', 'Process')
Push-Location $root
try {
    # 唯一批准Dockerfile使用原有固定JRE/Jena摘要；不安装系统软件。
    $fuseki = python3 scripts/maintenance/canonical_fuseki.py --task-id G2-INTEGRATION --run-id ('ci-' + [Guid]::NewGuid().ToString('N')) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Jena fixture image build failed' }
    # AI Schema验证仅复用冻结锁中的既有Ajv传递依赖，精确Node只作用当前进程。
    $tools = & ./scripts/bootstrap-web-tools.ps1 | ConvertFrom-Json
    $env:PATH = (Split-Path $tools.nodePath -Parent) + [IO.Path]::PathSeparator + $originalPath
    & $tools.nodePath $tools.pnpmPath install --frozen-lockfile --store-dir (Join-Path $root '.tools/pnpm-store')
    if ($LASTEXITCODE -ne 0) { throw 'Frozen web dependency restore failed' }
    $env:G2_TEST_JENA_IMAGE = $fuseki.image
    python3 scripts/acceptance/semantic-roundtrip.py --postgres --label ci-semantic
    if ($LASTEXITCODE -ne 0) { throw 'Real semantic integration failed' }
    foreach ($entry in @('release-faults', 'query-plan', 'mcp-agent')) {
        python3 (Join-Path $root "scripts/acceptance/$entry.py") --label "ci-$entry"
        if ($LASTEXITCODE -ne 0) { throw "Real $entry integration failed" }
    }
    Write-Output 'PASS: real PG/Jena/RustFS semantic, release faults, gateway, MCP/MAF and native SSE suites. Browser OIDC and LGTM are separate local acceptance.'
} finally {
    [Environment]::SetEnvironmentVariable('PATH', ($originalPath ?? [NullString]::Value), 'Process')
    Pop-Location
}
