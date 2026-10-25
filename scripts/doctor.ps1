<#
.SYNOPSIS
只读诊断目标工具链，不安装工具或启动服务。
.DESCRIPTION
退出0为必要版本满足；退出2为环境BLOCKED；退出1为诊断异常。
#>
[CmdletBinding()]
param(
    [string]$Root = (Split-Path $PSScriptRoot -Parent),
    [string]$ToolRoot = '',
    [switch]$CheckDocker
)
$ErrorActionPreference = 'Stop'
try {
    # 从项目文件读取目标，避免机器旧版本变成实际标准。
    $sdkTarget = (Get-Content -Raw (Join-Path $Root 'global.json') | ConvertFrom-Json).sdk.version
    $package = Get-Content -Raw (Join-Path $Root 'package.json') | ConvertFrom-Json
    $nodeTarget = (Get-Content -Raw (Join-Path $Root '.node-version')).Trim()
    $pnpmTarget = $package.packageManager.Split('@')[1]
    # 项目并存安装优先；只读选择，不改变用户/机器默认工具或PATH。
    if (-not $ToolRoot) { $ToolRoot = Join-Path $Root '.tools' }
    $dotnetCandidate = Join-Path $ToolRoot $(if ($IsWindows) { 'dotnet/dotnet.exe' } else { 'dotnet/dotnet' })
    # Node发行目录按当前OS和原生架构选择；macOS ARM64不能借用linux-x64路径。
    $nodePlatform = if ($IsWindows) { 'win' } elseif ($IsMacOS) { 'darwin' } else { 'linux' }
    $nodeArchitecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
    $nodeRelativePath = if ($IsWindows) { "node-v$nodeTarget-$nodePlatform-$nodeArchitecture/node.exe" } else { "node-v$nodeTarget-$nodePlatform-$nodeArchitecture/bin/node" }
    $nodeCandidate = Join-Path $ToolRoot $nodeRelativePath
    $pnpmCandidate = Join-Path $ToolRoot 'pnpm/package/bin/pnpm.cjs'
    $dotnetCommand = if (Test-Path -LiteralPath $dotnetCandidate) { $dotnetCandidate } elseif (Get-Command dotnet -ErrorAction SilentlyContinue) { (Get-Command dotnet).Source } else { $null }
    $nodeCommand = if (Test-Path -LiteralPath $nodeCandidate) { $nodeCandidate } elseif (Get-Command node -ErrorAction SilentlyContinue) { (Get-Command node).Source } else { $null }
    $blocked = $false
    Write-Output "PASS: PowerShell $($PSVersionTable.PSVersion)，$([Runtime.InteropServices.RuntimeInformation]::OSDescription)"
    if ($dotnetCommand) {
        $sdks = @(& $dotnetCommand --list-sdks 2>&1)
        if ($LASTEXITCODE -eq 0 -and @($sdks | Where-Object { "$_" -match ('^' + [regex]::Escape($sdkTarget) + ' ') }).Count -gt 0) {
            Write-Output "PASS: SDK $sdkTarget 已安装，入口=$dotnetCommand"
        } else { $blocked = $true; Write-Output "BLOCKED: 目标SDK $sdkTarget 未安装；不执行OS级安装。" }
    } else { $blocked = $true; Write-Output 'BLOCKED: 未找到dotnet' }
    foreach ($tool in @(@('node', $nodeTarget), @('pnpm', $pnpmTarget))) {
        $toolCommand = if ($tool[0] -eq 'node') { $nodeCommand } elseif (Test-Path -LiteralPath $pnpmCandidate) { $pnpmCandidate } elseif (Get-Command pnpm -ErrorAction SilentlyContinue) { (Get-Command pnpm).Source } else { $null }
        if ($toolCommand -eq $pnpmCandidate -and -not $nodeCommand) {
            $blocked = $true
            Write-Output 'BLOCKED: 项目pnpm存在但Node缺失；跳过执行，不安装工具。'
            continue
        }
        if ($toolCommand) {
            $output = if ($toolCommand -eq $pnpmCandidate) { @(& $nodeCommand $pnpmCandidate --version 2>&1) } else { @(& $toolCommand --version 2>&1) }
            $actual = ($output | Select-Object -Last 1).ToString().Trim().TrimStart('v')
            if ($LASTEXITCODE -eq 0 -and $actual -eq $tool[1]) { Write-Output "PASS: $($tool[0]) $actual，入口=$toolCommand" }
            else { $blocked = $true; Write-Output "BLOCKED: $($tool[0])=$actual，目标=$($tool[1])；未升级全局工具。" }
        } else { $blocked = $true; Write-Output "BLOCKED: 未找到$($tool[0])" }
    }
    if (Get-Command codex -ErrorAction SilentlyContinue) {
        $version = @(& codex --version 2>&1) | Where-Object { "$_" -match '^codex-cli ' }
        Write-Output "WARN: $version；仅版本观察，不代表自定义角色加载通过。"
    } else { Write-Output 'WARN: Codex PATH未发现；静态CI不要求安装Codex。' }
    if (Get-Command aspire -ErrorAction SilentlyContinue) { Write-Output 'WARN: Aspire入口存在，服务编排验证归后续任务。' }
    else { Write-Output 'WARN: Aspire PATH未发现；本任务不安装。' }
    if ($CheckDocker) {
        if (Get-Command docker -ErrorAction SilentlyContinue) {
            $dockerVersion = @(& docker info --format '{{json .ServerVersion}}' 2>&1)
            if ($LASTEXITCODE -eq 0) { Write-Output "PASS: Docker daemon $($dockerVersion[-1])" }
            else { $blocked = $true; Write-Output 'BLOCKED: Docker daemon当前不可访问；不安装/启动Docker或修改虚拟化。' }
        } else { $blocked = $true; Write-Output 'BLOCKED: Docker命令未找到。' }
    } else { Write-Output 'NOT_RUN: Docker daemon未探测；基础设施启动前用-CheckDocker复核。' }
    Write-Output 'NOT_RUN: 本命令不恢复局部EF或执行构建/测试/业务PoC；这些状态由对应实际命令记录，不调用全局EF9替代。'
    if ($blocked) { exit 2 }
    exit 0
} catch {
    Write-Output "FAIL: 诊断异常：$($_.Exception.Message)"
    exit 1
}
