# 缺失工具的环境阻断应退出2，而不是空命令异常退出1。
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('ontology-doctor-' + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Force -Path (Join-Path $temporary 'pnpm/package/bin') | Out-Null
    [IO.File]::WriteAllText((Join-Path $temporary 'pnpm/package/bin/pnpm.cjs'), "// synthetic fixture`n")
    function Get-Command {
        [CmdletBinding()]
        param([string]$Name)
        return $null
    }
    $messages = @(& (Join-Path $root 'scripts/doctor.ps1') -Root $root -ToolRoot $temporary)
    $code = $LASTEXITCODE
    if ($code -ne 2 -or @($messages | Where-Object { $_ -like 'FAIL:*' }).Count -gt 0) {
        throw "Missing Node must be BLOCKED/2, actual=$code"
    }
    Write-Output 'PASS: Doctor handles existing pnpm without Node as BLOCKED/2.'
} finally {
    $resolved = [IO.Path]::GetFullPath($temporary)
    if ((Split-Path $resolved -Leaf) -notmatch '^ontology-doctor-[a-f0-9]{32}$' -or
        -not $resolved.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing unsafe fixture cleanup'
    }
    if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
}
