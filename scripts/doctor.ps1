<#
.SYNOPSIS
只读诊断目标工具链，不安装工具或启动服务。
.DESCRIPTION
退出0为必要版本满足；退出2为环境BLOCKED；退出1为诊断异常。
#>
[CmdletBinding()]
param([string]$Root = (Split-Path $PSScriptRoot -Parent))
$ErrorActionPreference = 'Stop'
try {
    # 从项目文件读取目标，避免机器旧版本变成实际标准。
    $sdkTarget = (Get-Content -Raw (Join-Path $Root 'global.json') | ConvertFrom-Json).sdk.version
    $package = Get-Content -Raw (Join-Path $Root 'package.json') | ConvertFrom-Json
    $nodeTarget = (Get-Content -Raw (Join-Path $Root '.node-version')).Trim()
    $pnpmTarget = $package.packageManager.Split('@')[1]
    $blocked = $false
    Write-Output "PASS: PowerShell $($PSVersionTable.PSVersion)，$([Runtime.InteropServices.RuntimeInformation]::OSDescription)"
    if (Get-Command dotnet -ErrorAction SilentlyContinue) {
        $sdks = @(& dotnet --list-sdks 2>&1)
        if ($LASTEXITCODE -eq 0 -and @($sdks | Where-Object { "$_" -match ('^' + [regex]::Escape($sdkTarget) + ' ') }).Count -gt 0) {
            Write-Output "PASS: SDK $sdkTarget 已安装"
        } else { $blocked = $true; Write-Output "BLOCKED: 目标SDK $sdkTarget 未安装；不执行OS级安装。" }
    } else { $blocked = $true; Write-Output 'BLOCKED: 未找到dotnet' }
    foreach ($tool in @(@('node', $nodeTarget), @('pnpm', $pnpmTarget))) {
        if (Get-Command $tool[0] -ErrorAction SilentlyContinue) {
            $output = @(& $tool[0] --version 2>&1)
            $actual = ($output | Select-Object -Last 1).ToString().Trim().TrimStart('v')
            if ($LASTEXITCODE -eq 0 -and $actual -eq $tool[1]) { Write-Output "PASS: $($tool[0]) $actual" }
            else { $blocked = $true; Write-Output "BLOCKED: $($tool[0])=$actual，目标=$($tool[1])；未升级全局工具。" }
        } else { $blocked = $true; Write-Output "BLOCKED: 未找到$($tool[0])" }
    }
    if (Get-Command codex -ErrorAction SilentlyContinue) {
        $version = @(& codex --version 2>&1) | Where-Object { "$_" -match '^codex-cli ' }
        Write-Output "WARN: $version；仅版本观察，不代表自定义角色加载通过。"
    } else { Write-Output 'WARN: Codex PATH未发现；静态CI不要求安装Codex。' }
    if (Get-Command aspire -ErrorAction SilentlyContinue) { Write-Output 'WARN: Aspire入口存在，服务编排验证归后续任务。' }
    else { Write-Output 'WARN: Aspire PATH未发现；本任务不安装。' }
    Write-Output 'NOT_RUN: 局部dotnet-ef恢复、MSTest/MTP、Kiota/Hey API、Docker daemon及应用链路；不调用全局EF9替代局部EF10。'
    if ($blocked) { exit 2 }
    exit 0
} catch {
    Write-Output "FAIL: 诊断异常：$($_.Exception.Message)"
    exit 1
}
