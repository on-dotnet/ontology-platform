#!/usr/bin/env pwsh
[CmdletBinding()]
param([switch]$Build, [string]$Root = (Split-Path -Parent $PSScriptRoot))

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$utf8 = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding = $utf8
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$Root = (Resolve-Path -LiteralPath $Root).Path
if (-not (Test-Path -LiteralPath (Join-Path $Root 'check/check.py') -PathType Leaf)) {
    throw "所选目录不是钢铁本体包 $Root"
}

# Only release inputs go over stdin. In particular, the checker in a fixture
# copy is data under test, not an executable that needs to run on the host.
$zipBytes = [IO.MemoryStream]::new()
try {
    $zip = [IO.Compression.ZipArchive]::new($zipBytes, 'Create', $true)
    try {
        $patterns = @('check/check.py', 'check/qudt-units.txt', 'cq/*/*.rq', 'cq/*/*.csv', 'mappings/*.sssom.tsv')
        foreach ($file in Get-ChildItem -LiteralPath $Root -Recurse -File -Filter '*.ttl') {
            $relative = [IO.Path]::GetRelativePath($Root, $file.FullName).Replace('\', '/')
            if ($relative -notmatch '^(steel\.ttl|dist/steel\.ttl|(core|process|plain|special|examples)/[\w-]+\.ttl)$') {
                throw "Turtle 文件位于模块布局之外 $relative"
            }
            $patterns += $relative
        }
        foreach ($pattern in $patterns) {
            foreach ($file in (Get-ChildItem -Path (Join-Path $Root $pattern) -File -ErrorAction SilentlyContinue)) {
                for ($item = $file; $item.FullName -ne $Root; $item = Get-Item -LiteralPath (Split-Path $item.FullName)) {
                    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                        throw "打包路径中有符号链接 $($item.FullName)"
                    }
                }
                $name = [IO.Path]::GetRelativePath($Root, $file.FullName).Replace('\', '/')
                [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, "steel/$name")
            }
        }
        # Read the baseline from the main ref even in a detached worktree or a fixture copy.
        $baseline = 'samples/steel-industry/ontology'
        $paths = @(git -C $repo ls-tree -r --name-only main -- $baseline)
        if ($LASTEXITCODE -ne 0) { throw '无法读取 main 上的 #67 基线' }
        foreach ($path in ($paths -like '*.ttl')) {
            $lines = @(git -C $repo show "main:$path")
            if ($LASTEXITCODE -ne 0) { throw "读取 main:$path 失败" }
            $entry = $zip.CreateEntry($path).Open()
            try {
                $bytes = $utf8.GetBytes(($lines -join [char]10) + [char]10)
                $entry.Write($bytes, 0, $bytes.Length)
            } finally { $entry.Dispose() }
        }
    } finally { $zip.Dispose() }
    $encoded = [Convert]::ToBase64String($zipBytes.ToArray())
} finally { $zipBytes.Dispose() }

$index = $env:OP_MIRROR -eq 'off' ? '' : '--index-url https://mirrors.aliyun.com/pypi/simple/'
$script = @(
    'set -eu'
    'python -c "import base64, io, sys, zipfile; zipfile.ZipFile(io.BytesIO(base64.b64decode(sys.stdin.buffer.read()))).extractall()"'
    "python -m pip install --disable-pip-version-check --no-cache-dir --root-user-action=ignore $index rdflib==7.6.0 pyshacl==0.40.2 </dev/null >&2"
    'cd steel'
    if ($Build) {
        'mkdir -p dist'
        'python -B check/check.py build >dist/steel.ttl'
        'python -B check/check.py >&2'
        'cat dist/steel.ttl'
    } else {
        'exec python -B check/check.py'
    }
) -join [char]10
$name = 'op-tmp-steel-' + [guid]::NewGuid().ToString('N')
$arguments = @('--context','linux013-rootless','run','--rm','-i','--name',$name,
    '--workdir','/w','python:3.13-slim-trixie','sh','-c',$script)
if ($Build) {
    $turtle = @($encoded | docker @arguments)
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $dist = [IO.Directory]::CreateDirectory((Join-Path $Root 'dist')).FullName
    $temp = Join-Path $dist "$name.tmp"
    try {
        [IO.File]::WriteAllText($temp, ($turtle -join [char]10) + [char]10, $utf8)
        [IO.File]::Move($temp, (Join-Path $dist 'steel.ttl'), $true)
    } finally {
        if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) }
    }
    'steel check: ok'
} else {
    $encoded | docker @arguments
    exit $LASTEXITCODE
}
