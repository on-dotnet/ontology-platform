# 校验真实下载归档字节，不能用版本输出代替完整性，也不能提取损坏归档。
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
. (Join-Path $root 'scripts/bootstrap-web-tools.ps1') -Library
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('ontology-toolchain-' + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory $temporary | Out-Null
    $path = Join-Path $temporary 'synthetic-archive.bin'
    $bytes = [Text.Encoding]::UTF8.GetBytes('synthetic approved bytes')
    [IO.File]::WriteAllBytes($path, $bytes)
    $sha256 = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
    $sha512 = 'sha512-' + [Convert]::ToBase64String([Security.Cryptography.SHA512]::HashData($bytes))
    Assert-ToolArchive $path SHA256 $sha256
    Assert-ToolArchive $path SHA512 $sha512
    [IO.File]::AppendAllText($path, 'tampered')
    foreach ($check in @(@('SHA256', $sha256), @('SHA512', $sha512))) {
        $rejected = $false
        try { Assert-ToolArchive $path $check[0] $check[1] } catch { $rejected = $_.Exception.Message -like 'TOOLCHAIN_HASH_MISMATCH*' }
        if (-not $rejected) { throw 'Corrupt tool archive was not rejected before extraction' }
    }
    Write-Output 'PASS: toolchain archives accept two exact digests and reject two tampered byte cases.'
} finally {
    if ((Split-Path $temporary -Leaf) -notmatch '^ontology-toolchain-[a-f0-9]{32}$') { throw 'Unsafe fixture cleanup' }
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
