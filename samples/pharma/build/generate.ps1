#!/usr/bin/env pwsh
# Keep the blank line below: Get-Help ignores a help block that directly follows a comment.

<#
.SYNOPSIS
重新生成 samples/pharma/docs/ 下的 PDF、Word、Excel 资料。

.DESCRIPTION
在 Docker 主机上起一个临时容器（op-tmp-pharma-docs-*，用完即删），装中文字体（fonts-wqy-microhei）和
reportlab、python-docx、openpyxl，运行 build.py。这些工具不进项目依赖。rootless Docker 不能绑定挂载，
所以 build/ 目录以 base64 编码的 zip 经标准输入传入，生成的文件同样经标准输出取回（zip 的文件名用 UTF-8）。
Docker 上下文取环境变量 OP_DOCKER_CONTEXT，默认 linux013-rootless；OP_MIRROR=off 时不用国内源。
#>
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$build = $PSScriptRoot
$docs = Join-Path (Split-Path -Parent $build) 'docs'
$context = $env:OP_DOCKER_CONTEXT ? $env:OP_DOCKER_CONTEXT : 'linux013-rootless'
$mirror = $env:OP_MIRROR -ne 'off'
$apt = $mirror ? "sed -i 's#http://deb.debian.org#https://mirrors.aliyun.com#g' /etc/apt/sources.list.d/debian.sources && " : ''
$pip = $mirror ? '-i https://mirrors.aliyun.com/pypi/simple/' : ''
$script = @(
    'set -e'
    # stdin first: apt and debconf would otherwise read from it. -i skips the CR PowerShell adds.
    'mkdir -p /w/out && base64 -di > /w/build.zip'
    "export DEBIAN_FRONTEND=noninteractive; ${apt}apt-get update -qq >/dev/null </dev/null && apt-get install -y -qq --no-install-recommends fonts-wqy-microhei >/dev/null </dev/null"
    "pip install -q --disable-pip-version-check --root-user-action=ignore $pip reportlab==5.1.0 python-docx==1.2.0 openpyxl==3.1.5 >&2 </dev/null"
    "python -c `"import zipfile; zipfile.ZipFile('/w/build.zip').extractall('/w/build')`""
    'python /w/build/build.py --out /w/out >&2'
    "cd /w/out && python -c `"import os, zipfile; z = zipfile.ZipFile('/w/docs.zip', 'w'); [z.write(n) for n in sorted(os.listdir('.'))]; z.close()`""
    'base64 -w0 /w/docs.zip'
) -join "`n"

Add-Type -AssemblyName System.IO.Compression.FileSystem
$scratch = Join-Path ([IO.Path]::GetTempPath()) "pharma-docs-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
New-Item -ItemType Directory -Path (Join-Path $scratch 'build') -Force | Out-Null
try {
    Copy-Item -Recurse -Path (Join-Path $build '*') -Destination (Join-Path $scratch 'build') -Exclude 'generate.ps1', '__pycache__'
    $archive = Join-Path $scratch 'build.zip'
    [IO.Compression.ZipFile]::CreateFromDirectory((Join-Path $scratch 'build'), $archive)
    $name = "op-tmp-pharma-docs-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
    $encoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes($archive))
    $output = $encoded | docker --context $context run --rm -i --name $name python:3.13-slim-trixie sh -c $script
    if ($LASTEXITCODE -ne 0) { throw "生成失败，退出码 $LASTEXITCODE" }
    $result = Join-Path $scratch 'docs.zip'
    [IO.File]::WriteAllBytes($result, [Convert]::FromBase64String(($output -join '').Trim()))
    # Unpack first, replace the old documents only once that worked.
    $fresh = Join-Path $scratch 'docs'
    [IO.Compression.ZipFile]::ExtractToDirectory($result, $fresh)
    New-Item -ItemType Directory -Force -Path $docs | Out-Null
    Get-ChildItem -LiteralPath $docs -File | Remove-Item
    Get-ChildItem -LiteralPath $fresh -File | Move-Item -Destination $docs
    Get-ChildItem -LiteralPath $docs -File | ForEach-Object { '{0,8:N0} 字节  {1}' -f $_.Length, $_.Name }
} finally {
    Remove-Item -Recurse -Force -LiteralPath $scratch
}
