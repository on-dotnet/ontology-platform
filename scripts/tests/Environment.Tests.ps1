# 环境恢复必须保留未设置、空字符串及非空字符串，防止同进程原生构建被污染。
[CmdletBinding()]
param([string]$VerifyScript = (Join-Path $PSScriptRoot '../verify.ps1'))
$ErrorActionPreference = 'Stop'
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$temporaryTools = Join-Path ([IO.Path]::GetTempPath()) ('ontology-env-' + [guid]::NewGuid().ToString('N'))
$environmentNames = @('PYTHONPATH', 'DOTNET_ROOT', 'DOTNET_CLI_HOME', 'NUGET_PACKAGES', 'DOTNET_CLI_TELEMETRY_OPTOUT')
$originalValues = @{}
foreach ($environmentName in $environmentNames) { $originalValues[$environmentName] = [Environment]::GetEnvironmentVariable($environmentName, 'Process') }
try {
    New-Item -ItemType Directory -Path $temporaryTools | Out-Null
    # 拦截原生调用，仅检查入口的进程环境恢复，不把桩调用冒充真实构建。
    function dotnet {
        $nativeCalls.Add('observed')
        $global:LASTEXITCODE = 0
    }
    foreach ($state in @('unset', 'empty', 'value')) {
        foreach ($environmentName in $environmentNames) {
            $value = if ($state -eq 'unset') { [NullString]::Value } elseif ($state -eq 'empty') { '' } else { 'm0-synthetic-environment' }
            [Environment]::SetEnvironmentVariable($environmentName, $value, 'Process')
        }
        $expectedValues = @{}
        foreach ($environmentName in $environmentNames) { $expectedValues[$environmentName] = [Environment]::GetEnvironmentVariable($environmentName, 'Process') }
        $nativeCalls = [Collections.Generic.List[string]]::new()
        $messages = @(& $VerifyScript -Root $repositoryRoot -ToolRoot $temporaryTools -RunNative -SkipWeb)
        if ($LASTEXITCODE -ne 0 -or $nativeCalls.Count -ne 2) { throw "Environment fixture failed to exercise two native calls ($state)" }
        foreach ($environmentName in $environmentNames) {
            $actualValue = [Environment]::GetEnvironmentVariable($environmentName, 'Process')
            if (($null -eq $expectedValues[$environmentName]) -ne ($null -eq $actualValue) -or
                ($null -ne $actualValue -and $expectedValues[$environmentName] -cne $actualValue)) {
                throw "Environment state changed: $environmentName ($state); values hidden"
            }
        }
        Write-Output "PASS: verification preserves $state environment state for five process variables."
    }
    # 结构化负例脚本也独立恢复PYTHONPATH，覆盖其自身finally，避免只修主入口。
    [Environment]::SetEnvironmentVariable('PYTHONPATH', [NullString]::Value, 'Process')
    $messages = @(& (Join-Path $PSScriptRoot 'StructuredFiles.Tests.ps1'))
    if ($null -ne [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')) { throw 'Structured tests changed unset PYTHONPATH; value hidden' }
    Write-Output 'Environment regression: 3 state groups and structured-suite cleanup passed; native calls are synthetic, product tests NOT_RUN.'
} finally {
    foreach ($environmentName in $environmentNames) {
        $originalValue = $originalValues[$environmentName]
        if ($null -eq $originalValue) { $originalValue = [NullString]::Value }
        [Environment]::SetEnvironmentVariable($environmentName, $originalValue, 'Process')
    }
    if ((Split-Path $temporaryTools -Leaf) -notmatch '^ontology-env-[a-f0-9]{32}$') { throw 'Unsafe fixture cleanup' }
    if (Test-Path -LiteralPath $temporaryTools) { Remove-Item -LiteralPath $temporaryTools -Recurse -Force }
}
