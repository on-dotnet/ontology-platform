#requires -Version 7.0
<#
.SYNOPSIS
按已提交证据和精确 JSON 白名单清理本项目的已关闭合成开发资源。
.DESCRIPTION
默认 DryRun。Apply 必须指定尚不存在的 LogPath，完整预检通过后才创建 JSONL。
Python 入口仅使用标准库，不安装依赖、不读取环境秘密、不执行全局 prune/force。
.PARAMETER Root
当前 Git 工作树的绝对根目录。
.PARAMETER PlanPath
符合 cleanup_resources.py 模块文档的 JSON 白名单路径。
.PARAMETER Apply
显式执行经过全量预检和每步复验的白名单。
.PARAMETER LogPath
Apply 专用的新 JSONL 日志文件；其父目录必须已存在。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$PlanPath,
    [switch]$Apply,
    [string]$LogPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($Apply -and [string]::IsNullOrWhiteSpace($LogPath)) { throw 'Apply requires -LogPath.' }
if (-not $Apply -and -not [string]::IsNullOrWhiteSpace($LogPath)) { throw 'DryRun does not accept -LogPath.' }
$pythonCommand = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $pythonCommand) { $pythonCommand = Get-Command python -ErrorAction SilentlyContinue }
if (-not $pythonCommand) { throw 'Python 3 is required; no dependency will be installed.' }
$enginePath = Join-Path $PSScriptRoot 'cleanup_resources.py'
$engineArguments = @($enginePath, '--root', $Root, '--plan', $PlanPath)
if ($Apply) { $engineArguments += @('--apply', '--log-path', $LogPath) }
& $pythonCommand.Source @engineArguments
exit $LASTEXITCODE
