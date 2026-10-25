#Requires -Version 7.4
[CmdletBinding()]
param([string]$Root = (Split-Path $PSScriptRoot -Parent), [switch]$Restore)
$ErrorActionPreference = 'Stop'
$previousPath = [Environment]::GetEnvironmentVariable('PATH', 'Process')
try {
    $tools = & (Join-Path $PSScriptRoot 'bootstrap-web-tools.ps1') -Root $Root | ConvertFrom-Json
    if (-not $tools.nodePath -or -not $tools.pnpmPath) { throw 'Isolated web tools unavailable' }
    # 仅给本次验证子进程提供精确Node路径，结束后恢复原进程状态。
    $env:PATH = (Split-Path $tools.nodePath -Parent) + [IO.Path]::PathSeparator + $previousPath
    Push-Location $Root
    try {
        if ($Restore) {
            & $tools.nodePath $tools.pnpmPath install --frozen-lockfile
            if ($LASTEXITCODE -ne 0) { throw 'Frozen Web restore failed' }
        }
        foreach ($task in @('lint', 'typecheck', 'test', 'build')) {
            & $tools.nodePath $tools.pnpmPath --dir apps/web run $task
            if ($LASTEXITCODE -ne 0) { throw "Web $task failed" }
        }
    } finally { Pop-Location }
    Write-Output 'PASS: exact Node/pnpm; separate Web lint/typecheck/test/build. Real OIDC/E2E is a separate acceptance.'
} finally { [Environment]::SetEnvironmentVariable('PATH', ($previousPath ?? [NullString]::Value), 'Process') }
