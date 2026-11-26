#!/usr/bin/env pwsh
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = Split-Path -Parent $PSScriptRoot
$files = @(
    'check/check.py'
    'data/data.ttl'
    'data/invalid-data.ttl'
    'ontology/mappings.sssom.tsv'
    foreach ($module in 'core','steelmaking','rolling','quality','logistics','codes','standards','shapes','steel-industry') {
        "ontology/$module.ttl"
    }
    foreach ($number in 1..14) {
        'cq/cq{0:00}.rq' -f $number
        'cq/cq{0:00}.csv' -f $number
    }
)

# Use archive-relative names on both platforms. Never enumerate the worktree.
$buffer = [IO.MemoryStream]::new()
try {
    $zip = [IO.Compression.ZipArchive]::new($buffer, [IO.Compression.ZipArchiveMode]::Create, $true)
    try {
        foreach ($relative in $files) {
            $path = Join-Path $root $relative
            foreach ($item in (Split-Path -Parent $path), $path) {
                if ((Get-Item -LiteralPath $item).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                    throw "压缩包输入不能指向其他路径 $item"
                }
            }
            [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $path, $relative)
        }
    } finally {
        $zip.Dispose()
    }
    $encoded = [Convert]::ToBase64String($buffer.ToArray())
} finally {
    $buffer.Dispose()
}

$index = $env:OP_MIRROR -eq 'off' ? '' : '--index-url https://mirrors.aliyun.com/pypi/simple/'
$script = @(
    'set -eu'
    'python -c "import base64, io, sys, zipfile; zipfile.ZipFile(io.BytesIO(base64.b64decode(sys.stdin.buffer.read()))).extractall()"'
    "python -m pip install --disable-pip-version-check --no-cache-dir --root-user-action=ignore $index rdflib==7.6.0 pyshacl==0.40.2 </dev/null"
    'exec python -B check/check.py'
) -join "`n"
$name = 'op-tmp-steel-check-' + [guid]::NewGuid().ToString('N').Substring(0, 12)
$encoded | docker --context linux013-rootless run --rm -i --name $name --workdir /w python:3.13-slim-trixie sh -c $script
exit $LASTEXITCODE
