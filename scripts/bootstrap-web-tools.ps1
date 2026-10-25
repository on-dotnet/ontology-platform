#Requires -Version 7.4
[CmdletBinding()]
param([string]$Root = (Split-Path $PSScriptRoot -Parent), [switch]$Library)
$ErrorActionPreference = 'Stop'

function Assert-ToolArchive {
    param([string]$Path, [ValidateSet('SHA256', 'SHA512')][string]$Algorithm, [string]$Expected)
    # 校验失败必须发生在提取或执行之前，错误不回显任何文件内容。
    $bytes = [IO.File]::ReadAllBytes($Path)
    $actual = if ($Algorithm -eq 'SHA256') {
        [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
    } else { 'sha512-' + [Convert]::ToBase64String([Security.Cryptography.SHA512]::HashData($bytes)) }
    if ($actual -cne $Expected) { throw 'TOOLCHAIN_HASH_MISMATCH: archive rejected before extraction' }
}

if ($Library) { return }
$ProgressPreference = 'SilentlyContinue'
$manifest = Get-Content -Raw (Join-Path $PSScriptRoot 'toolchain-artifacts.json') | ConvertFrom-Json -AsHashtable
$package = Get-Content -Raw (Join-Path $Root 'package.json') | ConvertFrom-Json
if ($package.packageManager -ne "pnpm@$($manifest.pnpmVersion)" -or
    (Get-Content -Raw (Join-Path $Root '.node-version')).Trim() -ne $manifest.nodeVersion) {
    throw 'TOOLCHAIN_TARGET_MISMATCH: update requires a reviewed artifact manifest'
}
$toolDirectory = Join-Path $Root '.tools'
$downloadDirectory = Join-Path $toolDirectory 'downloads'
New-Item -ItemType Directory -Force $downloadDirectory | Out-Null
$architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
$platform = if ($IsWindows) { 'win' } elseif ($IsMacOS) { 'darwin' } else { 'linux' }
$extension = if ($IsWindows) { 'zip' } elseif ($IsMacOS) { 'tar.gz' } else { 'tar.xz' }
$name = "node-v$($manifest.nodeVersion)-$platform-$architecture"
$archiveName = "$name.$extension"
if (-not $manifest.archives.ContainsKey($archiveName)) { throw 'TOOLCHAIN_PLATFORM_NOT_APPROVED' }
$nodePath = Join-Path $toolDirectory $(if ($IsWindows) { "$name/node.exe" } else { "$name/bin/node" })
if (-not (Test-Path -LiteralPath $nodePath)) {
    # 机器入口只有实际精确匹配才复用，不更改默认Node或用户PATH。
    $installed = Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($installed -and ((& $installed.Source --version).Trim() -eq "v$($manifest.nodeVersion)")) { $nodePath = $installed.Source }
    else {
        $archivePath = Join-Path $downloadDirectory $archiveName
        if (-not (Test-Path -LiteralPath $archivePath)) {
            Invoke-WebRequest "https://nodejs.org/dist/v$($manifest.nodeVersion)/$archiveName" -OutFile $archivePath
        }
        Assert-ToolArchive $archivePath SHA256 $manifest.archives[$archiveName]
        if ($IsWindows) { Expand-Archive -LiteralPath $archivePath -DestinationPath $toolDirectory }
        else { & tar -xf $archivePath -C $toolDirectory; if ($LASTEXITCODE -ne 0) { throw 'Node extraction failed' } }
    }
}
if ((& $nodePath --version).Trim() -ne "v$($manifest.nodeVersion)" -or $LASTEXITCODE -ne 0) { throw 'Node exact version check failed' }
$pnpmPath = Join-Path $toolDirectory 'pnpm/package/bin/pnpm.cjs'
if (-not (Test-Path -LiteralPath $pnpmPath)) {
    $pnpmArchive = Join-Path $downloadDirectory "pnpm-$($manifest.pnpmVersion).tgz"
    if (-not (Test-Path -LiteralPath $pnpmArchive)) { Invoke-WebRequest $manifest.pnpmTarball -OutFile $pnpmArchive }
    Assert-ToolArchive $pnpmArchive SHA512 $manifest.pnpmIntegrity
    $pnpmDirectory = Join-Path $toolDirectory 'pnpm'
    New-Item -ItemType Directory -Force $pnpmDirectory | Out-Null
    & tar -xzf $pnpmArchive -C $pnpmDirectory
    if ($LASTEXITCODE -ne 0) { throw 'pnpm extraction failed' }
}
if ((& $nodePath $pnpmPath --version).Trim() -ne $manifest.pnpmVersion -or $LASTEXITCODE -ne 0) { throw 'pnpm exact version check failed' }
$result = @{ nodePath = [IO.Path]::GetFullPath($nodePath); pnpmPath = [IO.Path]::GetFullPath($pnpmPath); nodeVersion = $manifest.nodeVersion; pnpmVersion = $manifest.pnpmVersion }
$result | ConvertTo-Json -Compress
