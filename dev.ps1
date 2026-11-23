#!/usr/bin/env pwsh
<#
.SYNOPSIS
本体智能平台的开发入口。代码在本机，容器跑在 Docker 主机（默认 10.16.0.13，上下文 linux013-rootless）。

.DESCRIPTION
用法：./dev.ps1 <命令> [参数]

  up                构建并启动开发栈（postgres、api、web），等待健康后显示访问地址
  down              停止并移除开发栈的容器（保留数据卷）
  status            查看容器状态与访问地址
  logs [服务]       查看最近日志，例如 ./dev.ps1 logs api
  build             只构建 api、web 镜像
  lock [api|web]    在容器里重新生成依赖锁文件（uv.lock / pnpm-lock.yaml）并取回本机
  test-api          后端检查：ruff、mypy、pytest（临时数据库，跑完删除）
  test-web          前端检查：eslint、tsc、vitest
  test              依次运行 test-api、test-web
  gen-api           从后端导出 OpenAPI，并生成前端类型 web/src/api/schema.d.ts
  ci [-Report]      完整门禁：compose 校验、test-api、test-web、构建镜像；-Report 把结果写成提交状态 local-ci
  psql              打开开发库的 psql
  init-env          由 .env.example 生成本机私有配置 .env.local（已存在则不动；由用户本人运行）
  reset             删除开发栈及其数据卷（只能由用户本人运行，会二次确认）

脚本不改变调用方会话的当前目录和环境变量：所有 docker 调用都显式带 --context，所有路径都基于脚本所在目录。
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Command = 'help',
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Rest = @(),
    [switch]$Report
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = $PSScriptRoot
$EnvLocal = Join-Path $Root '.env.local'
$BaseImages = @('python:3.13-slim-trixie', 'node:24-alpine', 'nginxinc/nginx-unprivileged:1.29-alpine', 'pgvector/pgvector:0.8.1-pg18-trixie')

function Write-Step([string]$Text) { Write-Host "==> $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "  OK    $Text" -ForegroundColor Green }
function Write-Bad([string]$Text) { Write-Host "  FAIL  $Text" -ForegroundColor Red }
function Write-Note([string]$Text) { Write-Host "  NOTE  $Text" -ForegroundColor Yellow }
function Stop-Dev([string]$Message, [int]$Code = 1) { Write-Bad $Message; exit $Code }

# 读取设置：环境变量优先，其次仓库根目录的 .env.local（已被 Git 忽略）
function Get-Setting([string]$Name, [string]$Default) {
    $fromEnvironment = [Environment]::GetEnvironmentVariable($Name)
    if ($fromEnvironment) { return $fromEnvironment }
    if (Test-Path -LiteralPath $EnvLocal) {
        $hit = Select-String -LiteralPath $EnvLocal -Pattern "^\s*$Name\s*=\s*(.*)$" | Select-Object -Last 1
        if ($hit) { return $hit.Matches[0].Groups[1].Value.Trim().Trim('"', "'") }
    }
    return $Default
}

$DockerContext = Get-Setting 'OP_DOCKER_CONTEXT' 'linux013-rootless'
$DevHost = Get-Setting 'OP_DEV_HOST' '10.16.0.13'
$WebPort = Get-Setting 'OP_WEB_PORT' '28080'
$DockerExe = (Get-Command docker -CommandType Application | Select-Object -First 1).Source

# 脚本作用域内的 docker 一律带上本项目的上下文，不依赖也不修改调用方的 DOCKER_CONTEXT
function docker {
    # Forward pipeline input (e.g. gen-api pipes OpenAPI JSON into a container) only when there is some,
    # so interactive commands such as psql keep the console as stdin.
    if ($MyInvocation.ExpectingInput) { $input | & $DockerExe --context $DockerContext @args }
    else { & $DockerExe --context $DockerContext @args }
}

function New-TempName([string]$Purpose) { "op-tmp-$Purpose-$([guid]::NewGuid().ToString('N').Substring(0, 8))" }

function Get-ComposeArgs {
    $composeArgs = @('-f', (Join-Path $Root 'compose.yaml'))
    if ((Get-Setting 'OP_MIRROR' 'on') -ne 'off') { $composeArgs += @('--env-file', (Join-Path $Root 'dev/mirrors.cn.env')) }
    if (Test-Path -LiteralPath $EnvLocal) { $composeArgs += @('--env-file', $EnvLocal) }
    return $composeArgs
}

function Invoke-Compose {
    $composeArgs = Get-ComposeArgs
    # 输出直接写到屏幕，避免混进调用方函数的返回值
    docker compose @composeArgs @args | Out-Host
    if ($LASTEXITCODE -ne 0) { Stop-Dev "docker compose $($args -join ' ') 失败，退出码 $LASTEXITCODE" $LASTEXITCODE }
}

# 引擎配置的加速器在 BuildKit 解析基础镜像时可能返回 401，docker pull 正常：构建前先把基础镜像拉到本地。
function Confirm-BaseImages {
    foreach ($image in $BaseImages) {
        docker image inspect $image *> $null
        if ($LASTEXITCODE -eq 0) { continue }
        Write-Step "docker pull $image"
        docker pull --quiet $image | Out-Host
        if ($LASTEXITCODE -ne 0) { Stop-Dev "拉取基础镜像失败：$image" }
    }
}

function Wait-Healthy([string[]]$Services, [int]$TimeoutSeconds = 180) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $composeArgs = Get-ComposeArgs
    $pending = @()
    while ((Get-Date) -lt $deadline) {
        $pending = @()
        foreach ($service in $Services) {
            $id = (docker compose @composeArgs ps -q $service 2>$null | Select-Object -First 1)
            if (-not $id) { $pending += $service; continue }
            $state = docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $id
            if ($state -notmatch '^running (healthy|none)$') { $pending += $service }
        }
        if ($pending.Count -eq 0) { return $true }
        Start-Sleep -Seconds 3
    }
    Write-Bad "等待健康超时：$($pending -join ', ')"
    return $false
}

function Show-Status {
    Invoke-Compose ps -a --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'
    Write-Host ''
    Write-Host "平台地址   http://${DevHost}:$WebPort"
    Write-Host "开发账号   $(Get-Setting 'OP_ADMIN_USERNAME' 'admin') / 见 docs/development.md"
}

function Invoke-Up {
    Confirm-BaseImages
    Write-Step '构建镜像'
    Invoke-Compose build api web
    Write-Step '启动开发栈'
    Invoke-Compose up -d postgres api worker web
    if (-not (Wait-Healthy @('postgres', 'api', 'worker', 'web'))) {
        Invoke-Compose logs --tail 80 api worker web
        Stop-Dev '开发栈未就绪，见上方日志'
    }
    Write-Ok '开发栈已就绪'
    Show-Status
}

# 在工具容器里运行检查。输出照常显示；返回退出码。
function Invoke-ToolTest([string]$Service) {
    Confirm-BaseImages
    Write-Step "构建工具镜像 $Service（纳入当前工作区代码）"
    Invoke-Compose --profile tools build $Service
    if ($Service -eq 'test-api') { Invoke-Compose up -d postgres; [void](Wait-Healthy @('postgres') 120) }
    $name = New-TempName $Service
    $composeArgs = Get-ComposeArgs
    Write-Step "运行 $Service（临时容器 $name）"
    try {
        docker compose @composeArgs --profile tools run --rm -T --name $name $Service | Out-Host
        $code = $LASTEXITCODE
    } finally {
        docker rm -f $name *> $null
    }
    if ($code -eq 0) { Write-Ok "$Service 通过" } else { Write-Bad "$Service 失败，退出码 $code" }
    return $code
}

# 在容器里生成锁文件后用 docker cp 取回（Docker 主机无法挂载本机目录）。
function Invoke-Lock([string]$Target) {
    Confirm-BaseImages
    $targets = if ($Target) { @($Target) } else { @('api', 'web') }
    $composeArgs = Get-ComposeArgs
    foreach ($t in $targets) {
        $spec = switch ($t) {
            'api' { @{ Dir = 'backend'; File = 'uv.lock' } }
            'web' { @{ Dir = 'web'; File = 'pnpm-lock.yaml' } }
            default { Stop-Dev "未知的 lock 目标：$t（可选 api、web）" }
        }
        $buildArgs = @()
        foreach ($line in (docker compose @composeArgs config --format json | ConvertFrom-Json).services.api.build.args.PSObject.Properties) {
            $buildArgs += @('--build-arg', "$($line.Name)=$($line.Value)")
        }
        $image = "ontology/lock-${t}:local"
        $dir = Join-Path $Root $spec.Dir
        Write-Step "生成 $($spec.Dir)/$($spec.File)"
        docker build --target lock @buildArgs -t $image $dir | Out-Host
        if ($LASTEXITCODE -ne 0) { Stop-Dev "生成锁文件失败（$t）" }
        $name = New-TempName "lock-$t"
        docker create --name $name $image | Out-Null
        try {
            docker cp "${name}:/app/$($spec.File)" (Join-Path $dir $spec.File)
            if ($LASTEXITCODE -ne 0) { Stop-Dev "取回锁文件失败（$t）" }
        } finally {
            docker rm -f $name *> $null
        }
        Write-Ok "已更新 $($spec.Dir)/$($spec.File)"
    }
}

function Invoke-GenApi {
    Write-Step '构建 api 与 test-web 镜像'
    Invoke-Compose build api
    Invoke-Compose --profile tools build test-web
    $tmp = New-Item -ItemType Directory -Force -Path (Join-Path $Root '.verification/gen-api')
    $openapi = Join-Path $tmp 'openapi.json'
    Write-Step '导出 OpenAPI'
    docker run --rm --name (New-TempName 'openapi') ontology/api:local python -m ontology_platform.openapi > $openapi
    if ($LASTEXITCODE -ne 0) { Stop-Dev '导出 OpenAPI 失败' }
    Write-Step '生成 web/src/api/schema.d.ts'
    $types = Get-Content -Raw -LiteralPath $openapi | docker run --rm -i --name (New-TempName 'gen-api') ontology/test-web:local sh -c 'cat > /tmp/openapi.json && pnpm exec openapi-typescript /tmp/openapi.json -o /tmp/schema.d.ts >/dev/null && cat /tmp/schema.d.ts'
    if ($LASTEXITCODE -ne 0) { Stop-Dev '生成前端类型失败' }
    $header = '// Generated by ./dev.ps1 gen-api from the backend OpenAPI schema. Do not edit by hand.'
    # Join with LF explicitly; Set-Content would otherwise write CRLF on Windows.
    $text = ((@($header) + @($types)) -join "`n") + "`n"
    Set-Content -LiteralPath (Join-Path $Root 'web/src/api/schema.d.ts') -Encoding utf8NoBOM -NoNewline -Value $text
    Write-Ok '已更新 web/src/api/schema.d.ts'
}

function Invoke-Ci {
    $sha = (git -C $Root rev-parse HEAD).Trim()
    if ($Report) {
        if (git -C $Root status --porcelain) { Stop-Dev '工作区有未提交的改动；-Report 只能对已提交的 HEAD 运行' }
        git -C $Root fetch --quiet origin
        if (-not (git -C $Root branch -r --contains $sha 2>$null)) { Stop-Dev "提交 $sha 还没有推送到 origin，先 git push" }
    }
    $results = [ordered]@{}
    Write-Step '校验 compose 配置'
    $composeArgs = Get-ComposeArgs
    docker compose @composeArgs config -q
    $results['compose'] = $LASTEXITCODE
    $results['test-api'] = Invoke-ToolTest 'test-api'
    $results['test-web'] = Invoke-ToolTest 'test-web'
    Write-Step '构建运行镜像'
    docker compose @composeArgs build api web | Out-Host
    $results['build'] = $LASTEXITCODE

    Write-Host ''
    $failed = @($results.Keys | Where-Object { $results[$_] -ne 0 })
    foreach ($k in $results.Keys) { if ($results[$k] -eq 0) { Write-Ok $k } else { Write-Bad "$k（退出码 $($results[$k])）" } }
    $summary = ($results.Keys | ForEach-Object { "$_=$(if ($results[$_] -eq 0) { 'ok' } else { 'fail' })" }) -join ' '
    Write-Host "ci summary: $sha $summary"
    if ($Report) {
        $state = if ($failed.Count -eq 0) { 'success' } else { 'failure' }
        Push-Location -LiteralPath $Root
        try {
            gh api "repos/{owner}/{repo}/statuses/$sha" -f "state=$state" -f 'context=local-ci' -f "description=$summary" --silent
            if ($LASTEXITCODE -eq 0) { Write-Ok "已写提交状态 local-ci=$state（$sha）" } else { Write-Bad '写提交状态失败' }
        } finally {
            Pop-Location
        }
    }
    if ($failed.Count -gt 0) { exit 1 }
}

# Creates the private settings file from the template; never prints its content.
function Invoke-InitEnv {
    if (Test-Path -LiteralPath $EnvLocal) {
        Write-Note "已存在 $EnvLocal，未做改动"
        return
    }
    Copy-Item -LiteralPath (Join-Path $Root '.env.example') -Destination $EnvLocal
    Write-Ok "已生成 $EnvLocal"
    Write-Host '请用编辑器打开它，填写 OP_OPENAI_API_KEY 和 OP_AI_PROXY（例如 http://ontology:口令@10.16.0.157:7897），保存后运行 ./dev.ps1 up'
}

function Invoke-Reset {
    Write-Note '将删除开发栈的全部容器和数据卷（数据库内容会丢失）。'
    $answer = Read-Host '确认删除请输入 RESET'
    if ($answer -ne 'RESET') { Stop-Dev '已取消' 0 }
    Invoke-Compose --profile tools down -v
    Write-Ok '已删除'
}

switch ($Command) {
    'up' { Invoke-Up }
    'down' { Invoke-Compose --profile tools down }
    'status' { Show-Status }
    'logs' { Invoke-Compose logs --tail 200 @Rest }
    'build' { Confirm-BaseImages; Invoke-Compose build api web }
    'lock' { Invoke-Lock ($Rest | Select-Object -First 1) }
    'test-api' { exit (Invoke-ToolTest 'test-api') }
    'test-web' { exit (Invoke-ToolTest 'test-web') }
    'test' { $a = Invoke-ToolTest 'test-api'; $w = Invoke-ToolTest 'test-web'; if ($a -ne 0 -or $w -ne 0) { exit 1 } }
    'gen-api' { Invoke-GenApi }
    'ci' { Invoke-Ci }
    'psql' { Invoke-Compose exec postgres psql -U ontology -d ontology }
    'init-env' { Invoke-InitEnv }
    'reset' { Invoke-Reset }
    default { Get-Help $PSCommandPath -Detailed | Out-Host }
}
