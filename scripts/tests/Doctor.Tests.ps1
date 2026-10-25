# 缺失工具的环境阻断应退出2，而不是空命令异常退出1。
param([string]$DoctorScript = (Join-Path $PSScriptRoot '../doctor.ps1'))
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('ontology-doctor-' + [guid]::NewGuid().ToString('N'))
try {
    $realNode = @(Microsoft.PowerShell.Core\Get-Command node -CommandType Application -ErrorAction SilentlyContinue)[0].Source
    New-Item -ItemType Directory -Force -Path (Join-Path $temporary 'pnpm/package/bin') | Out-Null
    [IO.File]::WriteAllText((Join-Path $temporary 'pnpm/package/bin/pnpm.cjs'), "// synthetic fixture`n")
    function Get-Command {
        [CmdletBinding()]
        param([string]$Name)
        return $null
    }
    $messages = @(& $DoctorScript -Root $root -ToolRoot $temporary)
    $code = $LASTEXITCODE
    if ($code -ne 2 -or @($messages | Where-Object { $_ -like 'FAIL:*' }).Count -gt 0) {
        throw "Missing Node must be BLOCKED/2, actual=$code"
    }
    Write-Output 'PASS: Doctor handles existing pnpm without Node as BLOCKED/2.'
    if ($IsMacOS -and [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString() -eq 'Arm64' -and $realNode) {
        # 真实Node入口放入带空格的隔离macOS ARM64目录，隐藏PATH回退以捕获linux-x64硬编码。
        $macTools = Join-Path $temporary 'native tools'
        $nodeDirectory = Join-Path $macTools 'node-v24.22.1-darwin-arm64/bin'
        New-Item -ItemType Directory -Force $nodeDirectory | Out-Null
        New-Item -ItemType SymbolicLink -Path (Join-Path $nodeDirectory 'node') -Target $realNode | Out-Null
        $messages = @(& $DoctorScript -Root $root -ToolRoot $macTools)
        if (@($messages | Where-Object { $_ -like 'PASS: node 24.22.1*' }).Count -ne 1) {
            throw 'Native macOS ARM64 Node in isolated path was not discovered'
        }
        Write-Output 'PASS: Doctor discovers real macOS ARM64 Node from isolated path with spaces.'
    } else { Write-Output 'NOT_RUN: macOS ARM64 native Node case requires that host and Node.' }
} finally {
    $resolved = [IO.Path]::GetFullPath($temporary)
    if ((Split-Path $resolved -Leaf) -notmatch '^ontology-doctor-[a-f0-9]{32}$' -or
        -not $resolved.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing unsafe fixture cleanup'
    }
    if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}
