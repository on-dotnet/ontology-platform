# 真实解析器正反例，不依赖产品项目或容器。
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('ontology-structured-' + [guid]::NewGuid().ToString('N'))
$previousPythonPath = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
try {
    New-Item -ItemType Directory -Path $temporary | Out-Null
    $env:PYTHONPATH = Join-Path $root '.tools/pythonlibs'
    $python = if ($IsWindows) { (Get-Command python).Source } else { (Get-Command python3).Source }
    $parser = Join-Path $root 'scripts/validate-structured-files.py'
    [IO.File]::WriteAllText((Join-Path $temporary 'valid.yml'), "name: 正例`nitems: [one, two]`n")
    & $python $parser $temporary
    if ($LASTEXITCODE -ne 0) { throw 'Valid YAML rejected' }
    [IO.File]::WriteAllText((Join-Path $temporary 'invalid.yml'), "items: [unterminated`n")
    & $python $parser $temporary
    if ($LASTEXITCODE -ne 1) { throw 'Invalid YAML not rejected' }
    [IO.File]::WriteAllText((Join-Path $temporary 'invalid.yml'), "name: repaired`n")
    [IO.File]::WriteAllText((Join-Path $temporary 'invalid.toml'), "[unterminated`n")
    & $python $parser $temporary
    if ($LASTEXITCODE -ne 1) { throw 'Invalid TOML not rejected' }
    # 在独立作用域仅隐藏解析器，验证普通检查不会静默跳过必要门禁。
    & {
        . (Join-Path $root 'scripts/verify.ps1') -Library
        function Test-Path {
            [CmdletBinding()]
            param([string]$LiteralPath, [string]$Path)
            if ($LiteralPath -like '*validate-structured-files.py') { return $false }
            Microsoft.PowerShell.Management\Test-Path @PSBoundParameters
        }
        $checks = @(Test-Repository -RepositoryRoot $root)
        if (-not @($checks | Where-Object { $_.Check -eq 'structured-syntax' -and $_.Status -eq 'FAIL' }).Count) {
            throw 'Missing structured parser was not rejected'
        }
    }
    Write-Output 'PASS: structured parser 4 real positive/negative cases.'
} finally {
    [Environment]::SetEnvironmentVariable('PYTHONPATH', ($previousPythonPath ?? [NullString]::Value), 'Process')
    if ((Split-Path $temporary -Leaf) -notmatch '^ontology-structured-[a-f0-9]{32}$') { throw 'Unsafe fixture cleanup' }
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
