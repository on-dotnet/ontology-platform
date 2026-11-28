#!/usr/bin/env pwsh
# Keep the blank line below: Get-Help ignores a help block that directly follows a comment.

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
  test-api [参数]   后端检查：ruff、mypy、pytest（8 个进程并行，每个进程一个临时库，跑完删除）；
                    带参数时只运行 pytest <参数>（单进程），如 test-api tests/test_ai_pipeline.py -x
  test-web          前端检查：eslint、tsc、vitest
  test              同时运行 test-api、test-web，日志在 .verification/test/
  e2e               端到端冒烟测试：起一套临时的 postgres、api、worker、web（容器与网络都以 op-tmp-e2e- 开头，
                    库在 tmpfs，不碰开发栈），用 web/e2e/e2e.env 的测试账号跑 Playwright（Chromium），
                    跑完全部删除；失败时截图与 trace 存 .verification/e2e/
  gen-api           从后端导出 OpenAPI，并生成前端类型 web/src/api/schema.d.ts
  fmt <文件...>     用容器里的 ruff 修复并格式化指定的 backend 文件（经标准输入，只改这些文件）
  ai-check          在容器里对 OP_AI_MODEL、OP_AI_REASONING_MODEL 各发一次最小的结构化调用（带识别时用的推理强度），
                    只显示可用与否、模型、强度和错误类型，不显示地址与 Key
  eval [案例|目录] [-Replay] [-Recordings <目录>] [-Sequential] [-Reviewed [-NoMemory]] [-CodeFrom <worktree>]
                    识别 samples/<案例>（默认 steel）并按期望答案打分，结果存 .verification/eval/。
                    也可给一个结构相同的目录（带 / 或 \，如 .verification/private-docs/<名称>），
                    结果与录制以 dir-<目录名> 命名；没有 eval/expected.toml 时只识别、不打分。
                    模型调用按输入录制在 .verification/eval/recordings/<案例>/：输入没变的调用回放录制，
                    只有新的调用付费。-Replay 只回放（有调用没录过就失败，不用模型 Key）；
                    -Recordings 换一个录制目录，例如 worktree 里用主检出目录的录制。
                    跑两个场景（规格 004 第 10 节）：顺序场景每份资料的变更集合并后再识别下一份；同基线场景
                    全部对着起始本体识别完再依次合并。都按合并计划全部接受，并报告跳过的项、重复的类型与关系；
                    -Sequential 只跑顺序场景（例如同基线场景还没有录制时只回放）；
                    -Reviewed 只跑顺序场景，每份资料的变更集按期望答案审核（规格 008 第 10.1 节：
                    不在期望里的拒绝、名称不对的改名），审核结果记入审核记忆，再识别下一份，并报告
                    再提比例、改名沿用率等记忆指标；加 -NoMemory 照样审核，但识别时不用记忆，作对照；
                    -CodeFrom 用本仓库另一个 worktree 的代码构建镜像来评测，模型配置、录制和结果
                    仍用运行脚本的这个目录的，在主检出目录评测分支不必切换分支
  eval-qa [-Replay] [-Recordings <目录>] [-CodeFrom <worktree>]
                    在一次性数据库评测钢铁样例的五条问答与缺口提议。已有录制优先回放，-Replay 只回放。
                    录制默认在 .verification/eval/recordings/qa-steel/；-Recordings、-CodeFrom 与 eval 相同，
                    问题、答案与样例数据仍用运行脚本的这个目录的
  owl-check         Protégé 往返检查：样例与开发栈当前版本经平台导出，由 OWL API（断网）读写后再导回，
                    除已知改写外不得有差异；报告存 .verification/owl-check/
  schema-check      检查 web/src/api/schema.d.ts 与后端当前的 OpenAPI 一致（按 gen-api 的办法生成后比较，
                    换行统一为 LF）；不一致时显示差异开头，退出码 1
  ci [-Report]      完整门禁：compose 校验后，test-api、test-web、构建运行镜像、schema-check 四项同时运行
                    （schema-check 等构建运行镜像完成后开始），日志在 .verification/ci/；
                    -Report 把结果写成提交状态 local-ci
  images            列出本项目的镜像（ontology/*）及其所属工作区
  clean-images      删除已不存在的工作区留下的 ontology/* 镜像标签（只删本项目的，不 prune）
  psql              打开开发库的 psql
  seed-steel        装载冶金样例库：在开发用 postgres 里建库 steel_mes 与只读账号 steel_reader，
                    执行 samples/steel/relational 的两个 SQL 文件（每次重建 mes 模式，不碰平台的库）
  init-env          由 .env.example 生成本机私有配置 .env.local（已存在则不动；由用户本人运行）
  reset             删除开发栈及其数据卷（只能由用户本人运行，会二次确认）

脚本不改变调用方会话的当前目录和环境变量：所有 docker 调用都显式带 --context，所有路径都基于脚本所在目录。

本项目构建的镜像都带工作区标签：主检出目录用 local，其他 git worktree 用"目录名-路径哈希"，
可用 OP_IMAGE_TAG 覆盖。几个工作区同时构建、测试时各用各的镜像，互不覆盖。
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Command = 'help',
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Rest = @(),
    [switch]$Report,
    [switch]$Replay,
    [string]$Recordings = '',
    [switch]$Sequential,
    [switch]$Reviewed,
    [switch]$NoMemory,
    [string]$CodeFrom = ''
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

function Get-NormalizedPath([string]$Path) { [IO.Path]::GetFullPath($Path).TrimEnd('\', '/').ToLowerInvariant() }

# Image tag of a workspace other than the main checkout: "<folder>-<path hash>".
$WorktreeTagPattern = '^[a-z0-9_][a-z0-9_.-]*-[0-9a-f]{8}$'
function Get-WorktreeTag([string]$Path) {
    $hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($Path))).Substring(0, 8).ToLowerInvariant()
    $folder = ((Split-Path -Leaf $Path) -replace '[^a-z0-9_.-]', '-').TrimStart('.', '-')
    if (-not $folder) { $folder = 'wt' }
    return "$($folder.Substring(0, [Math]::Min(40, $folder.Length)))-$hash"
}

# Every git worktree of this repository, main checkout first, with its image tag: "local" for the
# main checkout, Get-WorktreeTag for the others. Empty when git cannot list them.
function Get-Workspaces {
    # git prints paths as UTF-8; decode them as such so non-ASCII folders compare correctly.
    # Hosts without a console may refuse the change; git still runs, and a path that then fails to
    # match only gets its own hash tag (Get-ImageTag), never "local".
    $previousConsole = [Console]::OutputEncoding
    try {
        try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false) } catch { }
        $lines = @(git -C $Root worktree list --porcelain 2>$null)
        $code = $LASTEXITCODE
    } finally {
        try { [Console]::OutputEncoding = $previousConsole } catch { }
    }
    if ($code -ne 0) { return }
    $paths = @($lines | Where-Object { $_ -like 'worktree *' } | ForEach-Object { Get-NormalizedPath $_.Substring(9) })
    for ($i = 0; $i -lt $paths.Count; $i++) {
        [pscustomobject]@{ Path = $paths[$i]; Tag = ($i -eq 0 ? 'local' : (Get-WorktreeTag $paths[$i])) }
    }
}

# "local" only when this is provably the main checkout; anything else gets its own tag, so a
# worktree never falls back to (and overwrites) the main checkout's images.
function Get-ImageTag {
    $configured = Get-Setting 'OP_IMAGE_TAG' ''
    if ($configured) { return $configured }
    $here = Get-NormalizedPath $Root
    $main = Get-Workspaces | Select-Object -First 1
    if ($main -and $main.Path -eq $here) { return 'local' }
    return Get-WorktreeTag $here
}

$ImageTag = Get-ImageTag

function Get-ComposeArgs([string]$CodeRoot = $Root) {
    # Settings always come from this checkout; only the compose file (and so the build context)
    # may be another worktree's.
    $composeArgs = @('-f', (Join-Path $CodeRoot 'compose.yaml'))
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
function Invoke-ToolTest([string]$Service, [string[]]$Command = @()) {
    Confirm-BaseImages
    Write-Step "构建工具镜像 $Service（纳入当前工作区代码）"
    Invoke-Compose --profile tools build $Service
    if ($Service -eq 'test-api') { Invoke-Compose up -d postgres; [void](Wait-Healthy @('postgres') 120) }
    $name = New-TempName $Service
    $composeArgs = Get-ComposeArgs
    Write-Step "运行 $Service（临时容器 $name）"
    try {
        docker compose @composeArgs --profile tools run --rm -T --name $name $Service @Command | Out-Host
        $code = $LASTEXITCODE
    } finally {
        docker rm -f $name *> $null
    }
    if ($code -eq 0) { Write-Ok "$Service 通过" } else { Write-Bad "$Service 失败，退出码 $code" }
    return $code
}

# Polls a probe command inside a container until it succeeds; gives up early if the container stops.
function Wait-Container([string]$Name, [string[]]$Probe, [int]$TimeoutSeconds = 120) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        docker exec $Name @Probe *> $null
        if ($LASTEXITCODE -eq 0) { return $true }
        if ((docker inspect -f '{{.State.Status}}' $Name 2>$null) -ne 'running') { break }
        Start-Sleep -Seconds 2
    }
    Write-Bad "$Name 未就绪，日志末尾："
    docker logs --tail 60 $Name 2>&1 | Out-Host
    return $false
}

# Test values of the throwaway e2e stack (web/e2e/e2e.env); never the dev stack's settings.
function Read-E2eFixture {
    $values = @{}
    foreach ($line in Get-Content -LiteralPath (Join-Path $Root 'web/e2e/e2e.env')) {
        if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') { $values[$Matches[1]] = $Matches[2].Trim() }
    }
    foreach ($name in @('E2E_USERNAME', 'E2E_PASSWORD', 'E2E_POSTGRES_PASSWORD', 'E2E_SECRET_KEY')) {
        if (-not $values[$name]) { Stop-Dev "web/e2e/e2e.env 缺少 $name" }
    }
    return $values
}

# End-to-end smoke tests (web/e2e). Postgres, api, worker and web run as op-tmp-e2e-* containers on a
# network of their own, with the database and documents in tmpfs, so nothing touches the dev stack
# and nothing is left behind. No port is published: the Playwright container joins that network.
function Invoke-E2e {
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $fixture = Read-E2eFixture
    $version = (Get-Content -Raw -LiteralPath (Join-Path $Root 'web/package.json') | ConvertFrom-Json).devDependencies.'@playwright/test'
    if ($version -notmatch '^\d+\.\d+\.\d+$') { Stop-Dev "web/package.json 里 @playwright/test 要写确切版本（与 Playwright 镜像一致），现在是 $version" }
    Confirm-BaseImages
    # Pulled up front for the same reason as Confirm-BaseImages (BuildKit may get 401 from the mirror).
    $playwrightImage = "mcr.microsoft.com/playwright:v$version-noble"
    docker image inspect $playwrightImage *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Step "docker pull $playwrightImage"
        docker pull --quiet $playwrightImage | Out-Host
        if ($LASTEXITCODE -ne 0) { Stop-Dev "拉取基础镜像失败：$playwrightImage" }
    }
    Write-Step '构建 api、web 与 test-e2e 镜像（纳入当前工作区代码）'
    Invoke-Compose build api web
    # package.json is the one source of the version: compose passes it to the e2e stage's FROM.
    $callerPlaywright = $env:OP_PLAYWRIGHT_VERSION
    $env:OP_PLAYWRIGHT_VERSION = $version
    try { Invoke-Compose --profile tools build test-e2e } finally { $env:OP_PLAYWRIGHT_VERSION = $callerPlaywright }

    $prefix = New-TempName 'e2e'
    $db = "$prefix-db"
    $api = "$prefix-api"
    $worker = "$prefix-worker"
    $web = "$prefix-web"
    $runner = "$prefix-run"
    $out = Join-Path $Root '.verification/e2e'
    if (Test-Path -LiteralPath $out) { Remove-Item -LiteralPath $out -Recurse -Force }
    $databaseUrl = "postgresql+psycopg://ontology:$($fixture.E2E_POSTGRES_PASSWORD)@postgres:5432/ontology"
    $code = 1
    $lines = @()
    $previousConsole = [Console]::OutputEncoding
    try {
        try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false) } catch { }
        Write-Step "启动临时环境 $prefix（postgres、api、worker、web；库在 tmpfs，跑完删除）"
        docker network create $prefix | Out-Null
        if ($LASTEXITCODE -ne 0) { Stop-Dev "创建网络 $prefix 失败" }
        docker run -d --name $db --network $prefix --network-alias postgres --tmpfs /var/lib/postgresql `
            -e POSTGRES_DB=ontology -e POSTGRES_USER=ontology -e "POSTGRES_PASSWORD=$($fixture.E2E_POSTGRES_PASSWORD)" `
            'pgvector/pgvector:0.8.1-pg18-trixie' | Out-Null
        # TCP, not the socket: the image's init server listens on the socket only, then restarts.
        if ($LASTEXITCODE -ne 0 -or -not (Wait-Container $db @('pg_isready', '-h', '127.0.0.1', '-U', 'ontology', '-d', 'ontology'))) { Stop-Dev '临时 postgres 未就绪' }
        docker run -d --name $api --network $prefix --network-alias api --tmpfs /data/documents:mode=1777 `
            -e OP_ENV=development -e "OP_DATABASE_URL=$databaseUrl" -e "OP_SECRET_KEY=$($fixture.E2E_SECRET_KEY)" `
            -e "OP_ADMIN_USERNAME=$($fixture.E2E_USERNAME)" -e "OP_ADMIN_PASSWORD=$($fixture.E2E_PASSWORD)" `
            -e OP_DOCUMENTS_DIR=/data/documents -e 'FORWARDED_ALLOW_IPS=*' "ontology/api:$ImageTag" | Out-Null
        $apiProbe = @('python', '-c', "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)")
        if ($LASTEXITCODE -ne 0 -or -not (Wait-Container $api $apiProbe)) { Stop-Dev '临时 api 未就绪' }
        # Jobs such as review.assist only run in the worker; started after the api has migrated the database.
        docker run -d --name $worker --network $prefix --tmpfs /data/documents:mode=1777 `
            -e OP_ENV=development -e "OP_DATABASE_URL=$databaseUrl" -e "OP_SECRET_KEY=$($fixture.E2E_SECRET_KEY)" `
            -e OP_DOCUMENTS_DIR=/data/documents "ontology/api:$ImageTag" python -m ontology_platform.worker | Out-Null
        if ($LASTEXITCODE -ne 0) { Stop-Dev '临时 worker 启动失败' }
        docker run -d --name $web --network $prefix --network-alias web "ontology/web:$ImageTag" | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Wait-Container $web @('wget', '-q', '-O', '/dev/null', 'http://127.0.0.1:8080/healthz') 60)) { Stop-Dev '临时 web 未就绪' }

        Write-Step "运行 Playwright 冒烟测试（临时容器 $runner）"
        # Docker's default 64 MB /dev/shm is tight for Chromium; --init reaps its child processes.
        docker run --name $runner --network $prefix --init --shm-size=1g -e E2E_BASE_URL=http://web:8080 `
            -e "E2E_USERNAME=$($fixture.E2E_USERNAME)" -e "E2E_PASSWORD=$($fixture.E2E_PASSWORD)" `
            "ontology/test-e2e:$ImageTag" 2>&1 | Tee-Object -Variable lines | Out-Host
        $code = $LASTEXITCODE
        if ($code -ne 0) {
            New-Item -ItemType Directory -Force -Path $out | Out-Null
            docker cp "${runner}:/app/test-results/artifacts" (Join-Path $out 'artifacts') *> $null
            docker logs --tail 200 $api *> (Join-Path $out 'api.log')
            docker logs --tail 200 $worker *> (Join-Path $out 'worker.log')
        }
    } finally {
        try { [Console]::OutputEncoding = $previousConsole } catch { }
        # -v: only these containers' anonymous volumes (none while tmpfs covers the image VOLUMEs).
        docker rm -f -v $runner $web $worker $api $db *> $null
        docker network rm $prefix *> $null
    }
    $counts = @($lines | ForEach-Object { "$_".Trim() } | Where-Object { $_ -match '^\d+ (passed|failed|flaky|skipped|did not run|interrupted)\b' })
    $summary = $counts.Count -gt 0 ? ($counts -join '，') : '没有测试结果'
    Write-Host "e2e summary: $summary；总耗时 $([Math]::Round($watch.Elapsed.TotalSeconds)) 秒"
    if ($code -eq 0) { Write-Ok 'e2e 通过' } else { Write-Bad "e2e 失败，退出码 $code（截图、trace 与 api 日志在 $out）" }
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
        $image = "ontology/lock-${t}:$ImageTag"
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

# Builds the api and test-web images from the current code and returns the generated
# web/src/api/schema.d.ts text (LF line endings). gen-api writes it; schema-check compares it.
function Get-GeneratedApiTypes {
    Write-Step '构建 api 与 test-web 镜像'
    Invoke-Compose build api
    Invoke-Compose --profile tools build test-web
    $tmp = New-Item -ItemType Directory -Force -Path (Join-Path $Root '.verification/gen-api')
    $openapi = Join-Path $tmp 'openapi.json'
    # Containers print UTF-8; decode (and pipe) as UTF-8 so non-ASCII API descriptions survive
    # whatever code page the console, or the gate's redirected child process, would use.
    $previousConsole = [Console]::OutputEncoding
    $OutputEncoding = [Text.UTF8Encoding]::new($false)
    try {
        try { [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false) } catch { }
        Write-Step '导出 OpenAPI'
        docker run --rm --name (New-TempName 'openapi') "ontology/api:$ImageTag" python -m ontology_platform.openapi > $openapi
        if ($LASTEXITCODE -ne 0) { Stop-Dev '导出 OpenAPI 失败' }
        Write-Step '生成 web/src/api/schema.d.ts'
        $types = Get-Content -Raw -LiteralPath $openapi | docker run --rm -i --name (New-TempName 'gen-api') "ontology/test-web:$ImageTag" sh -c 'cat > /tmp/openapi.json && pnpm exec openapi-typescript /tmp/openapi.json -o /tmp/schema.d.ts >/dev/null && cat /tmp/schema.d.ts'
        if ($LASTEXITCODE -ne 0) { Stop-Dev '生成前端类型失败' }
    } finally {
        try { [Console]::OutputEncoding = $previousConsole } catch { }
    }
    $header = '// Generated by ./dev.ps1 gen-api from the backend OpenAPI schema. Do not edit by hand.'
    return ((@($header) + @($types)) -join "`n") + "`n"
}

function Invoke-GenApi {
    $text = Get-GeneratedApiTypes
    # Set-Content would otherwise write CRLF on Windows; the text already uses LF.
    Set-Content -LiteralPath (Join-Path $Root 'web/src/api/schema.d.ts') -Encoding utf8NoBOM -NoNewline -Value $text
    Write-Ok '已更新 web/src/api/schema.d.ts'
}

# Gate step: the committed schema.d.ts must equal what gen-api would write from the current code.
# Line endings are compared as LF so a CRLF checkout does not count as a difference.
function Invoke-SchemaCheck {
    # Drop the previous run's comparison files first, so a failed generation leaves no stale diff.
    $dir = Join-Path $Root '.verification/gen-api'
    Remove-Item -LiteralPath (Join-Path $dir 'schema.committed.d.ts'), (Join-Path $dir 'schema.generated.d.ts') -ErrorAction SilentlyContinue
    $expected = Get-GeneratedApiTypes
    $path = Join-Path $Root 'web/src/api/schema.d.ts'
    $actual = if (Test-Path -LiteralPath $path) { [IO.File]::ReadAllText($path) -replace "`r`n", "`n" } else { '' }
    if ($actual -ceq $expected) {
        Write-Host 'schema-check: web/src/api/schema.d.ts 与后端 OpenAPI 一致'
        return 0
    }
    [IO.File]::WriteAllText((Join-Path $dir 'schema.committed.d.ts'), $actual)
    [IO.File]::WriteAllText((Join-Path $dir 'schema.generated.d.ts'), $expected)
    # At most ~20 diff lines, so the gate's 30-line log tail still shows them and the hint below.
    Write-Host '差异开头（--- 仓库里的文件，+++ 由当前代码生成；完整文件在 .verification/gen-api/）：'
    git -C $dir -c core.autocrlf=false diff --no-index --no-color --unified=1 -- schema.committed.d.ts schema.generated.d.ts | Select-Object -Skip 2 -First 22 | ForEach-Object { Write-Host "  $_" }
    Write-Host 'schema-check: web/src/api/schema.d.ts 与后端 OpenAPI 不一致，运行 ./dev.ps1 gen-api 后提交'
    return 1
}

# Runs dev.ps1 commands at the same time, each as its own process writing its own log, then prints
# them in the given order: the summary line of a passing step, the failures and log tail of a
# failing one. $After delays a command until the listed commands have finished (whatever their
# exit codes), e.g. so it reuses the images they built instead of building the same ones at once.
# Returns command -> exit code, in the given order.
function Invoke-Parallel([string[]]$Commands, [string]$LogDir, [hashtable]$After = @{}) {
    foreach ($name in @($After.Keys) + @($After.Values | ForEach-Object { $_ })) {
        if ($Commands -notcontains $name) { Stop-Dev "Invoke-Parallel：等待关系里的命令 $name 不在本次运行的命令里" }
    }
    $logs = New-Item -ItemType Directory -Force -Path $LogDir
    $outcomes = @{}
    $waiting = [Collections.Generic.List[string]]::new([string[]]$Commands)
    $pending = @()
    $order = @($Commands | ForEach-Object { if ($After.ContainsKey($_)) { "$_（等 $(@($After[$_]) -join '、') 完成后开始）" } else { $_ } })
    Write-Step "同时运行 $($order -join '、')（日志在 $logs）"
    try {
        while ($true) {
            foreach ($command in @($waiting)) {
                $blocking = @($After[$command] | Where-Object { $_ -and -not $outcomes.ContainsKey($_) })
                if ($blocking.Count -gt 0) { continue }
                [void]$waiting.Remove($command)
                $log = Join-Path $logs "$command.log"
                $pending += Start-ThreadJob -Name $command -ArgumentList $PSCommandPath, $command, $log -ScriptBlock {
                    param($Script, $Command, $Log)
                    $watch = [Diagnostics.Stopwatch]::StartNew()
                    & pwsh -NoProfile -NonInteractive -File $Script $Command *> $Log
                    [pscustomobject]@{ Code = $LASTEXITCODE; Seconds = [Math]::Round($watch.Elapsed.TotalSeconds) }
                }
            }
            if ($pending.Count -eq 0) {
                # Only a dependency cycle leaves commands waiting with nothing running.
                if ($waiting.Count -gt 0) { Stop-Dev "Invoke-Parallel：$($waiting -join '、') 的等待关系成环，无法开始" }
                break
            }
            $job = Wait-Job -Job $pending -Any
            $outcome = Receive-Job -Job $job -ErrorAction SilentlyContinue | Select-Object -Last 1
            if (-not $outcome -or $null -eq $outcome.Code) { $outcome = [pscustomobject]@{ Code = 1; Seconds = 0 } }
            $outcomes[$job.Name] = $outcome
            Remove-Job -Job $job
            $pending = @($pending | Where-Object { $_.Id -ne $job.Id })
            Write-Host "  完成  $($job.Name)：退出码 $($outcome.Code)，$($outcome.Seconds) 秒"
        }
    } finally {
        # Interrupted (Ctrl+C): in a console the child processes get the same Ctrl+C and clean up
        # their own temporary containers; elsewhere they may still be running.
        if ($pending.Count -gt 0) {
            $pending | Remove-Job -Force -ErrorAction SilentlyContinue
            Write-Note "已中断：$(@($pending.Name) -join '、') 的子进程可能仍在运行（日志在 $logs）；重跑前用 docker ps --filter name=op-tmp- 确认临时容器已退出"
        }
    }
    $codes = [ordered]@{}
    foreach ($command in $Commands) {
        $log = Join-Path $logs "$command.log"
        $code = $outcomes[$command].Code
        $codes[$command] = $code
        $lines = @(if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log } else { '（没有日志）' })
        Write-Host ''
        if ($code -eq 0) {
            Write-Ok "$command（$($outcomes[$command].Seconds) 秒）"
            $lines | Where-Object { $_ -match '^(check\.sh: |test-web summary: |schema-check: )' } | ForEach-Object { Write-Host "        $_" }
        } else {
            Write-Bad "$command（退出码 $code，$($outcomes[$command].Seconds) 秒，完整日志 $log）"
            $lines | Where-Object { $_ -match '^(FAILED|ERROR) |^\s+FAIL\s|^\s*×' } | Select-Object -First 30 | ForEach-Object { Write-Host "        $_" }
            Write-Host '        ---- 日志末尾 ----'
            $lines | Select-Object -Last 30 | ForEach-Object { Write-Host "        $_" }
        }
    }
    return $codes
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
    # Pull missing base images once, before the steps below would each pull them at the same time.
    Confirm-BaseImages
    # schema-check starts once build has built the api image, so the two never build it at the same
    # time. It does not wait for test-web, which takes as long as test-api; it rebuilds the test-web
    # image itself. By then test-web has normally built that image already (build's web runtime
    # chain shares the deps stage and is longer than the test target), so the rebuild is a cache hit;
    # if the two ever overlap, the worst case on this host's overlay2 store is one dangling image.
    $steps = Invoke-Parallel @('test-api', 'test-web', 'build', 'schema-check') (Join-Path $Root '.verification/ci') @{ 'schema-check' = @('build') }
    foreach ($name in $steps.Keys) { $results[($name -eq 'schema-check' ? 'schema' : $name)] = $steps[$name] }

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

# Formats only the named backend files: each file goes through ruff via stdin and is written back.
function Invoke-Fmt([string[]]$Files) {
    if (-not $Files) { Stop-Dev '用法：./dev.ps1 fmt <backend 下的 .py 文件...>' }
    Invoke-Compose --profile tools build test-api
    $backend = Join-Path $Root 'backend'
    # Source files contain Chinese text: pipe UTF-8 both ways regardless of the console code page.
    $previousConsole = [Console]::OutputEncoding
    $OutputEncoding = [Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
    try {
    foreach ($file in $Files) {
        $full = (Resolve-Path -LiteralPath $file).Path
        if (-not $full.StartsWith($backend, [StringComparison]::OrdinalIgnoreCase) -or -not $full.EndsWith('.py')) {
            Stop-Dev "只能格式化 backend 下的 .py 文件：$file"
        }
        $relative = $full.Substring($backend.Length + 1).Replace('\', '/')
        $source = Get-Content -Raw -LiteralPath $full
        $fixed = $source | docker run --rm -i --name (New-TempName 'fmt') "ontology/test-api:$ImageTag" sh -c "ruff check --fix --exit-zero --quiet --stdin-filename '$relative' - | ruff format --quiet --stdin-filename '$relative' -"
        if ($LASTEXITCODE -ne 0) { Stop-Dev "格式化失败：$relative" }
        $text = ($fixed -join "`n") + "`n"
        if ($text -ne $source.Replace("`r`n", "`n")) {
            Set-Content -LiteralPath $full -Encoding utf8NoBOM -NoNewline -Value $text
            Write-Ok "已格式化 $relative"
        }
    }
    } finally {
        [Console]::OutputEncoding = $previousConsole
    }
}

# Reads an eval's JSON Lines as they arrive and saves each recording at once (through a .tmp file),
# so that an interrupted run keeps the calls it paid for. Returns the last result or error line.
function Save-EvalStream([string]$RecordingsDir) {
    begin {
        $last = $null
        $saved = 0
        $warned = $false
    }
    process {
        try { $line = $_ | ConvertFrom-Json -ErrorAction Stop } catch { $line = $null }
        if (-not $line -or -not $line.PSObject.Properties['type']) {
            if (-not $warned) { Write-Note '评测返回了无法解析的输出行，已跳过'; $warned = $true }
        } elseif ($line.type -eq 'file') {
            if ($line.name -cnotmatch '^([0-9a-f]{64}|models)\.json$') { Stop-Dev "评测返回了意外的文件名：$($line.name)" }
            if (-not (Test-Path -LiteralPath $RecordingsDir)) { New-Item -ItemType Directory -Force -Path $RecordingsDir | Out-Null }
            $path = Join-Path $RecordingsDir $line.name
            Set-Content -LiteralPath "$path.tmp" -Encoding utf8NoBOM -NoNewline -Value $line.content
            Move-Item -LiteralPath "$path.tmp" -Destination $path -Force
            if ($line.name -ne 'models.json') { $saved++ }
        } elseif ($line.type -eq 'result' -or $line.type -eq 'error') {
            $last = $line
        } elseif (-not $warned) {
            Write-Note '评测返回了未知类型的输出行，已跳过'
            $warned = $true
        }
    }
    end { [pscustomobject]@{ Last = $last; Saved = $saved } }
}

# The code root and image tag an evaluation builds from: this checkout, or with -CodeFrom another
# worktree of this repository. Only worktrees qualify: the model key must not run code from an
# arbitrary folder. git still lists a worktree whose folder was deleted, so check the folder too.
function Resolve-CodeFrom([string]$CodeFrom) {
    if (-not $CodeFrom) { return $Root, $env:OP_IMAGE_TAG }
    $codeRoot = [IO.Path]::GetFullPath($CodeFrom, (Get-Location).Path).TrimEnd('\', '/')
    $workspace = Get-Workspaces | Where-Object { $_.Path -eq (Get-NormalizedPath $codeRoot) } | Select-Object -First 1
    if (-not $workspace) { Stop-Dev "-CodeFrom 只接受本仓库的 worktree（git worktree list）：$codeRoot" }
    if (-not (Test-Path -LiteralPath (Join-Path $codeRoot 'compose.yaml') -PathType Leaf)) {
        Stop-Dev "-CodeFrom 的 worktree 目录不存在或缺少 compose.yaml：$codeRoot"
    }
    return $codeRoot, $workspace.Tag
}

# Scores extraction on a case pack. Rootless Docker cannot bind-mount local folders, so documents
# and recordings go in as JSON on stdin; results and new recordings return line by line on stdout.
# A case is a name under samples/ or the path of a folder laid out the same way (docs/ and,
# optionally, eval/expected.toml), e.g. .verification/private-docs/<name>/ for documents that
# must not be committed. Results and recordings of a folder case are named "dir-<folder>".
function Invoke-Eval([string]$Case, [bool]$ReplayOnly, [string]$RecordingsDir, [bool]$SequentialOnly, [string]$CodeFrom, [bool]$ReviewedRun, [bool]$NoMemoryRun) {
    if ($NoMemoryRun -and -not $ReviewedRun) { Stop-Dev '-NoMemory 只能和 -Reviewed 一起用' }
    if (-not $Case) { $Case = 'steel' }
    $asPath = [IO.Path]::GetFullPath($Case, (Get-Location).Path).TrimEnd('\', '/')
    $isFolder = $Case -match '[\\/]'
    if ($isFolder) {
        if (-not (Test-Path -LiteralPath (Join-Path $asPath 'docs') -PathType Container)) { Stop-Dev "目录里没有 docs/：$asPath" }
        $caseDir = $asPath
        $Case = 'dir-' + ((Split-Path -Leaf $asPath) -replace '[^\w.-]', '-')
    } else {
        $caseDir = Join-Path $Root "samples/$Case"
        if (-not (Test-Path -LiteralPath (Join-Path $caseDir 'docs') -PathType Container)) { Stop-Dev "找不到 samples/$Case/docs" }
    }
    $answers = Join-Path $caseDir 'eval/expected.toml'
    $hasAnswers = Test-Path -LiteralPath $answers -PathType Leaf
    # A case pack in samples/ is scored against answers written first (samples/README.md).
    if (-not $hasAnswers -and -not $isFolder) { Stop-Dev "找不到 samples/$Case/eval/expected.toml" }
    if (-not $hasAnswers) { Write-Note "没有 eval/expected.toml：只做识别，不打分" }
    $RecordingsDir = $RecordingsDir ? [IO.Path]::GetFullPath($RecordingsDir, (Get-Location).Path) : (Join-Path $Root ".verification/eval/recordings/$Case")
    if ($ReplayOnly -and -not (Test-Path -LiteralPath $RecordingsDir -PathType Container)) { Stop-Dev "只回放需要录制，目录不存在：$RecordingsDir" }
    # -CodeFrom scores another worktree's code with this checkout's model settings, so a branch
    # can be measured before merging without checking it out here.
    $codeRoot, $codeTag = Resolve-CodeFrom $CodeFrom
    Confirm-BaseImages
    # compose.yaml reads the tag from the environment; the main switch restores the caller's value.
    $env:OP_IMAGE_TAG = $codeTag
    $composeArgs = Get-ComposeArgs $codeRoot
    docker compose @composeArgs build api | Out-Host
    if ($LASTEXITCODE -ne 0) { Stop-Dev "构建 $codeRoot 的 api 镜像失败，退出码 $LASTEXITCODE" $LASTEXITCODE }
    $files = @{}
    foreach ($item in Get-ChildItem -LiteralPath (Join-Path $caseDir 'docs') -File) {
        $files["docs/$($item.Name)"] = [Convert]::ToBase64String([IO.File]::ReadAllBytes($item.FullName))
    }
    if ($hasAnswers) { $files['eval/expected.toml'] = [Convert]::ToBase64String([IO.File]::ReadAllBytes($answers)) }
    $recordingTexts = @()
    $manifest = $null
    if (Test-Path -LiteralPath $RecordingsDir -PathType Container) {
        foreach ($item in Get-ChildItem -LiteralPath $RecordingsDir -Filter '*.json' -File) {
            $text = [IO.File]::ReadAllText($item.FullName, [Text.Encoding]::UTF8)
            if ($item.Name -eq 'models.json') { $manifest = $text } else { $recordingTexts += $text }
        }
    }
    $mode = $ReplayOnly ? 'replay' : 'record'
    # A reviewed run is a sequential one (spec 008, 10.1).
    $scenarios = ($SequentialOnly -or $ReviewedRun) ? @('sequential') : @('sequential', 'sameBaseline')
    $bundle = @{ files = $files; recordings = $recordingTexts; manifest = $manifest; mode = $mode; scenarios = $scenarios; reviewed = $ReviewedRun; noMemory = $NoMemoryRun } | ConvertTo-Json -Compress -Depth 4
    $outDir = New-Item -ItemType Directory -Force -Path (Join-Path $Root '.verification/eval')
    $reviewTag = $ReviewedRun ? ($NoMemoryRun ? '-reviewed-nomemory' : '-reviewed') : ''
    $outFile = Join-Path $outDir "$Case$reviewTag$($ReplayOnly ? '-replay' : '')$($CodeFrom ? "-$codeTag" : '')-$(Get-Date -Format 'yyyyMMdd-HHmmss').json"
    # Replay never reaches the model: the container gets no key and no proxy.
    $noModel = $ReplayOnly ? @('-e', 'OP_OPENAI_API_KEY=', '-e', 'OP_AI_PROXY=') : @()
    $previousConsole = [Console]::OutputEncoding
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
    $OutputEncoding = [Text.UTF8Encoding]::new($false)
    $container = New-TempName 'eval'
    try {
        Write-Step "识别 $caseDir（$($ReplayOnly ? '只回放' : '有录制就回放')，录制目录 $RecordingsDir$($CodeFrom ? "，代码取自 $codeRoot" : '')；进度显示在下方）"
        $stream = $bundle | docker compose @composeArgs run --rm -T --no-deps @noModel --name $container api python -m ontology_platform.modules.ai.eval | Save-EvalStream $RecordingsDir
        $code = $LASTEXITCODE
    } finally {
        [Console]::OutputEncoding = $previousConsole
        docker rm -f $container *> $null
    }
    if ($stream.Saved -gt 0) { Write-Ok "新录制 $($stream.Saved) 次模型调用，存到 $RecordingsDir" }
    $reply = $stream.Last
    if (-not $reply) { Stop-Dev "评测没有返回结果，退出码 $code" }
    if ($code -ne 0 -or $reply.type -eq 'error') {
        $detail = $reply.PSObject.Properties['error'] ? $reply.error : "退出码 $code"
        Stop-Dev "评测失败：$detail"
    }
    Set-Content -LiteralPath $outFile -Encoding utf8NoBOM -Value $reply.result
    $result = $reply.result | ConvertFrom-Json
    if (-not $result.scored) { Write-Note '没有答案，未打分；补上 eval/expected.toml 后用 -Replay 重跑即可打分，不再调用模型' }
    Show-EvalScenario ($ReviewedRun ? '顺序场景（按期望审核）' : '顺序场景') $result
    if ($result.PSObject.Properties['memory']) { Show-EvalMemory $result.memory }
    if ($result.PSObject.Properties['sameBaseline']) { Show-EvalScenario '同基线场景' $result.sameBaseline }
    Write-Ok "结果已保存到 $outFile"
}

function Invoke-EvalQa([bool]$ReplayOnly, [string]$RecordingsDir, [string]$CodeFrom) {
    $prefix = New-TempName 'eval-qa'
    $db = "$prefix-db"
    $api = "$prefix-api"
    $outDir = New-Item -ItemType Directory -Force -Path (Join-Path $Root '.verification/eval')
    $recordDir = $RecordingsDir ? [IO.Path]::GetFullPath($RecordingsDir, (Get-Location).Path) : (Join-Path $outDir 'recordings/qa-steel')
    if ($ReplayOnly -and -not (Test-Path -LiteralPath $recordDir -PathType Container)) { Stop-Dev "只回放需要录制，目录不存在：$recordDir" }
    # Questions, answers and sample data stay this checkout's, as in eval: only the code changes.
    $codeRoot, $codeTag = Resolve-CodeFrom $CodeFrom
    $inputs = @('samples/steel/qa/ontology.ttl', 'samples/steel/qa/expected-bindings.toml',
        'samples/steel/qa/metrics.toml', 'samples/steel/qa/questions.toml',
        'backend/tests/fixtures/qa/steel/plans.toml',
        'samples/steel/relational/01-schema.sql', 'samples/steel/relational/02-data.sql')
    $files = @{}
    foreach ($path in $inputs) {
        $files[(Split-Path -Leaf $path)] = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $Root $path)))
    }
    $recordings = @()
    $manifest = $null
    if (Test-Path -LiteralPath $recordDir) {
        foreach ($file in Get-ChildItem -LiteralPath $recordDir -Filter '*.json' -File) {
            $content = [IO.File]::ReadAllText($file.FullName)
            if ($file.Name -eq 'models.json') { $manifest = $content } else { $recordings += $content }
        }
    }
    $mode = $ReplayOnly ? 'replay' : 'record'
    $bundle = @{ mode = $mode; recordings = $recordings; manifest = $manifest; files = $files } | ConvertTo-Json -Depth 4 -Compress
    $noModel = $ReplayOnly ? @('-e', 'OP_OPENAI_API_KEY=', '-e', 'OP_AI_PROXY=') : @()
    Confirm-BaseImages
    # compose.yaml reads the tag from the environment; the main switch restores the caller's value.
    $env:OP_IMAGE_TAG = $codeTag
    $composeArgs = Get-ComposeArgs $codeRoot
    docker compose @composeArgs build api | Out-Host
    if ($LASTEXITCODE -ne 0) { Stop-Dev "构建 $codeRoot 的 api 镜像失败，退出码 $LASTEXITCODE" $LASTEXITCODE }
    $overlay = Join-Path $outDir "$prefix.yaml"
    # Compose merges mounts by target. Cover both image VOLUMEs with tmpfs before starting either service.
    $config = @'
services:
  postgres:
    volumes: [{type: tmpfs, target: /var/lib/postgresql}]
  api:
    volumes: [{type: tmpfs, target: /data/documents}]
  worker:
    volumes: [{type: tmpfs, target: /data/documents}]
volumes: !reset {}
'@
    $argsQa = $composeArgs + @('-f', $overlay, '-p', $prefix)
    $password = [Guid]::NewGuid().ToString('N')
    $adminUrl = "postgresql+psycopg://ontology:${password}@postgres:5432/postgres"
    $previousConsole = [Console]::OutputEncoding
    try {
        [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
        $OutputEncoding = [Text.UTF8Encoding]::new($false)
        Set-Content -LiteralPath $overlay -Value $config -Encoding utf8NoBOM
        Write-Step "启动问答评测临时环境 $prefix（$($ReplayOnly ? '只回放' : '优先回放')，录制目录 $recordDir$($CodeFrom ? "，代码取自 $codeRoot" : '')）"
        docker compose @argsQa run --rm -d --no-deps --use-aliases --name $db -e POSTGRES_DB=postgres -e "POSTGRES_PASSWORD=$password" postgres | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Wait-Container $db @('pg_isready', '-h', '127.0.0.1', '-U', 'ontology', '-d', 'postgres'))) { throw '评测临时数据库未就绪' }
        $stream = $bundle | docker compose @argsQa run --rm -T --no-deps @noModel --name $api -e OP_ENV=development -e "OP_DATABASE_URL=$adminUrl" -e "OP_QA_EVAL_ADMIN_URL=$adminUrl" api python -m ontology_platform.qa_eval | Save-EvalStream $recordDir
        $code = $LASTEXITCODE
    } finally {
        [Console]::OutputEncoding = $previousConsole
        docker rm -f $api $db *> $null
        docker network rm "${prefix}_default" *> $null
        Remove-Item -LiteralPath $overlay -ErrorAction SilentlyContinue
        $left = @(docker ps -aq --filter "name=^/${prefix}-(api|db)$")
        if ($LASTEXITCODE -ne 0 -or $left.Count) { throw "无法确认 $prefix 的容器已清理" }
        Write-Ok "已确认 $prefix 的临时容器无残留"
    }
    if ($stream.Saved -gt 0) { Write-Ok "新录制 $($stream.Saved) 次模型调用，存到 $recordDir" }
    $reply = $stream.Last
    if (-not $reply) { Stop-Dev "评测没有返回结果，退出码 $code" }
    if ($code -ne 0 -or $reply.type -eq 'error') {
        $detail = $reply.PSObject.Properties['error'] ? $reply.error : "退出码 $code"
        Stop-Dev "问答评测失败：$detail" $code
    }
    $outFile = Join-Path $outDir "qa-steel$($ReplayOnly ? '-replay' : '')$($CodeFrom ? "-$codeTag" : '')-$(Get-Date -Format 'yyyyMMdd-HHmmssfff').json"
    Set-Content -LiteralPath $outFile -Encoding utf8NoBOM -Value $reply.result
    $result = $reply.result | ConvertFrom-Json
    $result.questions | ForEach-Object {
        $row = $_
        [pscustomobject]@{
            题号 = $row.case; 状态 = $row.status; 检验 = $row.result; v2达标 = $row.v2Pass
            计划 = $row.planEquivalent ? '等价' : $row.firstMismatch
            调用 = $row.usage.calls; 回放 = $row.usage.replayed; 秒 = $row.elapsedSeconds
            输入泄露 = @($result.promptLeaks | Where-Object { $_.question -eq $row.case }).Count
        }
    } | Format-Table -AutoSize | Out-Host
    Write-Ok "CQ 通过 $($result.summary.passed)/5，符合 v2 预期 $($result.summary.v2Passed)/5，计划等价 $($result.summary.equivalent)/5。结果已保存到 $outFile"
}

# Scores, merge counts and usage of one scenario of an evaluation result.
function Show-EvalScenario([string]$Title, $result) {
    Write-Host "  $Title"
    foreach ($section in 'entityTypes', 'relations', 'properties', 'hierarchy') {
        $numbers = $result.$section
        if (-not $result.scored) {
            Write-Host ("  {0,-12} 识别出 {1,4}" -f $section, $numbers.predicted)
        } elseif ($numbers.PSObject.Properties['precision']) {
            # null: nothing to divide by (no predictions, or no core entries)
            $precision = $null -eq $numbers.precision ? '-' : $numbers.precision
            $recall = $null -eq $numbers.recall ? '-' : $numbers.recall
            Write-Host ("  {0,-12} 预测 {1,4}  准确率 {2}  召回率 {3}" -f $section, $numbers.predicted, $precision, $recall)
        } else {
            Write-Host ("  {0,-12} 预测 {1,4}  （期望答案没有这一段，不计分）" -f $section, $numbers.predicted)
        }
    }
    $merge = $result.merge
    $line = "  合并（全部接受）：跳过 {0} 项，重复关系 {1} 条" -f $merge.skipped, $merge.duplicateRelations
    if ($merge.PSObject.Properties['duplicateTypeGroups']) {
        $groups = $merge.duplicateTypeGroups
        $line += "；重复类型 {0} 组（主名称相同 {1}、有标记 {2}、无标记 {3}）" -f $groups.total, $groups.sameMainName, $groups.marked, $groups.unmarked
    }
    Write-Host $line
    $total = $result.usage.total
    Write-Host ("  证据定位率 {0}；模型调用 {1} 次、回放 {2} 次，输入 {3} / 输出 {4} token，{5} 秒" -f $result.groundedShare, $total.calls, $total.replayed, $total.inputTokens, $total.outputTokens, $total.seconds)
}

# Review-memory metrics of a reviewed run (spec 008, 10.2): each is numerator / denominator.
function Show-EvalMemory($memory) {
    Write-Host ("  审核记忆：{0}，最后有效条目 {1} 条" -f ($memory.enabled ? '开' : '关（对照）'), $memory.entries)
    $names = [ordered]@{
        reproposeModel     = '再提比例（模型层面）'
        reproposeReview    = '再提比例（审核人面前）'
        variantRepropose   = '变体再提比例'
        renameReuse        = '改名沿用率'
        keptApartViolation = '保持分开的违背率'
    }
    foreach ($key in $names.Keys) {
        if (-not $memory.PSObject.Properties[$key]) { continue }
        $m = $memory.$key
        $ratio = $null -eq $m.ratio ? '-' : $m.ratio
        Write-Host ("  {0} {1}（{2} / {3}）" -f $names[$key], $ratio, $m.numerator, $m.denominator)
    }
}

# A value from dev/mirrors.cn.env, unless mirrors are switched off.
function Get-MirrorValue([string]$Name) {
    if ((Get-Setting 'OP_MIRROR' 'on') -eq 'off') { return '' }
    $hit = Select-String -LiteralPath (Join-Path $Root 'dev/mirrors.cn.env') -Pattern "^\s*$Name\s*=\s*(.*)$" | Select-Object -Last 1
    if ($hit) { return $hit.Matches[0].Groups[1].Value.Trim() }
    return ''
}

# Protégé round trip (spec 002, 4.3): platform export -> OWL API, offline -> import again.
function Invoke-OwlCheck {
    Confirm-BaseImages
    Invoke-Compose build api
    foreach ($image in @('maven:3.9-eclipse-temurin-25', 'eclipse-temurin:25-jre')) {
        docker image inspect $image *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Step "docker pull $image"
            docker pull --quiet $image | Out-Host
            if ($LASTEXITCODE -ne 0) { Stop-Dev "拉取基础镜像失败：$image" }
        }
    }
    Write-Step "构建 OWL API 工具镜像 ontology/owlapi:$ImageTag"
    docker build --build-arg "MAVEN_MIRROR=$(Get-MirrorValue 'OP_MAVEN_MIRROR')" -t "ontology/owlapi:$ImageTag" (Join-Path $Root 'dev/owlapi') | Out-Host
    if ($LASTEXITCODE -ne 0) { Stop-Dev '构建 OWL API 工具镜像失败' }

    $work = Join-Path $Root '.verification/owl-check'
    foreach ($name in @('cases', 'export', 'saved')) {
        $path = Join-Path $work $name
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
    }
    $cases = New-Item -ItemType Directory -Force -Path (Join-Path $work 'cases')
    Copy-Item -LiteralPath (Join-Path $Root 'samples/owl-features') -Destination $cases -Recurse
    $steel = New-Item -ItemType Directory -Force -Path (Join-Path $cases 'steel')
    foreach ($name in @('ontology', 'shapes', 'vocabulary')) {
        Copy-Item -LiteralPath (Join-Path $Root "samples/steel/$name.ttl") -Destination $steel
    }
    $composeArgs = Get-ComposeArgs
    $previousConsole = [Console]::OutputEncoding
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
    try {
        $running = docker compose @composeArgs ps -q --status running postgres 2>$null
        if ($running) {
            $extra = New-Item -ItemType Directory -Force -Path (Join-Path $cases 'extra')
            $query = 'select o.key, r.version from ontology.ontologies o join ontology.releases r on r.id = o.active_release_id order by o.key'
            foreach ($row in @(docker compose @composeArgs exec -T postgres psql -U ontology -d ontology -At -F '|' -c $query)) {
                $key, $version = $row.Split('|')
                $turtle = docker compose @composeArgs exec -T postgres psql -U ontology -d ontology -At -c "select r.turtle from ontology.ontologies o join ontology.releases r on r.id = o.active_release_id where o.key = '$key'"
                Set-Content -LiteralPath (Join-Path $extra "$key-v$version.ttl") -Encoding utf8NoBOM -Value ($turtle -join "`n")
                Write-Note "包含开发栈的当前版本：$key v$version"
            }
        } else {
            Write-Note '开发栈未运行，只检查样例'
        }

        $api = New-TempName 'owl-api'
        $java = New-TempName 'owl-java'
        try {
            docker run -d --network none --name $api --entrypoint sleep "ontology/api:$ImageTag" 1800 | Out-Null
            docker run -d --network none --name $java --entrypoint sleep "ontology/owlapi:$ImageTag" 1800 | Out-Null
            Write-Step '平台导出'
            docker cp $cases "${api}:/tmp/cases" | Out-Null
            docker exec $api python -m ontology_platform.modules.ontology.owlcheck export /tmp/cases /tmp/export | Out-Host
            if ($LASTEXITCODE -ne 0) { Stop-Dev '平台导出失败' }
            docker cp "${api}:/tmp/export" (Join-Path $work 'export') | Out-Null
            Write-Step 'OWL API 读入并另存（断网）'
            docker cp (Join-Path $work 'export') "${java}:/work/in" | Out-Null
            $log = docker exec $java java -cp '/opt/owlapi/owl-roundtrip-0.jar:/opt/owlapi/lib/*' RoundTrip /work/in /work/out
            if ($LASTEXITCODE -ne 0) { Stop-Dev 'OWL API 运行失败' }
            Set-Content -LiteralPath (Join-Path $work 'owlapi.log') -Encoding utf8NoBOM -Value ($log -join "`n")
            docker cp "${java}:/work/out" (Join-Path $work 'saved') | Out-Null
            Write-Step '导回平台并比较'
            docker cp (Join-Path $work 'saved') "${api}:/tmp/saved" | Out-Null
            docker cp (Join-Path $work 'owlapi.log') "${api}:/tmp/owlapi.log" | Out-Null
            $report = docker exec $api python -m ontology_platform.modules.ontology.owlcheck compare /tmp/cases /tmp/saved /tmp/owlapi.log
            $code = $LASTEXITCODE
        } finally {
            docker rm -f $api $java *> $null
        }
    } finally {
        [Console]::OutputEncoding = $previousConsole
    }
    Set-Content -LiteralPath (Join-Path $work 'report.txt') -Encoding utf8NoBOM -Value ($report -join "`n")
    $report | Out-Host
    if ($code -ne 0) { Stop-Dev "owl-check 未通过，详见 .verification/owl-check/report.txt" }
    Write-Ok 'owl-check 通过（报告：.verification/owl-check/report.txt）'
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

# Lists this project's images (ontology/*) with the workspace each tag belongs to. With -Clean,
# removes the tags of workspaces that no longer exist. Never prunes and never forces: an image a
# container still uses stays.
function Invoke-Images([switch]$Clean) {
    $workspaces = @(Get-Workspaces)
    if ($workspaces.Count -eq 0) { Stop-Dev 'git worktree list 失败，无法判断哪些工作区还在；未做任何改动' }
    $owners = @{}
    foreach ($workspace in $workspaces) { $owners[$workspace.Tag] = $workspace.Path }
    if (-not $owners.ContainsKey($ImageTag)) { $owners[$ImageTag] = '（当前工作区）' }
    $stale = @()
    foreach ($row in @(docker image ls --filter 'reference=ontology/*' --format '{{.Repository}}:{{.Tag}}|{{.Size}}|{{.CreatedSince}}')) {
        if ($row -notmatch '^(ontology/[^:|]+):([^|]+)\|([^|]*)\|(.*)$') { continue }
        $tag = $Matches[2]
        $name = "$($Matches[1]):$tag"
        $owner = $owners[$tag]
        if (-not $owner) {
            # Only tags in the generated worktree format are ours to clean; "local", tags set with
            # OP_IMAGE_TAG by other sessions and <none> stay.
            if ($tag -cmatch $WorktreeTagPattern) { $stale += $name; $owner = '已不存在的工作区' } else { $owner = '其他标签，不清理' }
        }
        Write-Host ('{0,-58} {1,9}  {2,-20} {3}' -f $name, $Matches[3], $Matches[4], $owner)
    }
    if (-not $Clean) {
        if ($stale.Count -gt 0) { Write-Note "$($stale.Count) 个标签属于已不存在的工作区，./dev.ps1 clean-images 可删除" }
        return
    }
    if ($stale.Count -eq 0) { Write-Ok '没有需要清理的标签'; return }
    foreach ($name in $stale) {
        docker rmi $name *> $null
        if ($LASTEXITCODE -eq 0) { Write-Ok "已删除 $name" } else { Write-Note "未删除 $name（可能仍有容器在用）" }
    }
}

# 冶金样例库（规格 003 第 11 节）：在开发用 postgres 里建库 steel_mes 和只读账号 steel_reader。
# 只动这个库和这个账号，不碰平台自己的库；每次重建 mes 模式，可以重复运行。
$SteelReaderPassword = 'steel-reader-dev-only'
function Invoke-SeedSteel {
    if ((Get-Setting 'OP_ENV' 'development') -eq 'production') { Stop-Dev 'OP_ENV=production 时不装载样例库' }
    $files = @('01-schema.sql', '02-data.sql')
    # The test image only has backend/, so the tests carry byte-identical copies; the binding
    # answers are compared too, or the end-to-end tests could pass against stale answers.
    foreach ($name in $files + 'expected-bindings.toml') {
        $sample = Join-Path $Root "samples/steel/relational/$name"
        $copy = Join-Path $Root "backend/tests/fixtures/connectors/steel/$name"
        if (-not (Test-Path -LiteralPath $sample) -or -not (Test-Path -LiteralPath $copy)) { Stop-Dev "缺少 $name" }
        if ((Get-FileHash -LiteralPath $sample).Hash -ne (Get-FileHash -LiteralPath $copy).Hash) {
            Stop-Dev "samples/steel/relational/$name 与测试副本 backend/tests/fixtures/connectors/steel/$name 不一致"
        }
    }
    $sources = foreach ($name in $files) { [IO.File]::ReadAllText((Join-Path $Root "samples/steel/relational/$name"), [Text.UTF8Encoding]::new($false)) }
    if (-not (Wait-Healthy @('postgres') 15)) { Stop-Dev 'postgres 没有运行，请先运行 ./dev.ps1 up' }

    # CREATE DATABASE cannot run inside a transaction, so the account and the database come first.
    $setup = @"
SELECT 'CREATE ROLE steel_reader' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'steel_reader') \gexec
ALTER ROLE steel_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '$SteelReaderPassword';
ALTER ROLE steel_reader SET default_transaction_read_only = on;
SELECT 'CREATE DATABASE steel_mes' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'steel_mes') \gexec
"@
    # One transaction: a failure leaves the previous mes schema as it was.
    $load = @(
        'DROP SCHEMA IF EXISTS mes CASCADE;'
        $sources
        @'
REVOKE ALL ON DATABASE steel_mes FROM PUBLIC;
GRANT CONNECT ON DATABASE steel_mes TO steel_reader;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA mes FROM PUBLIC;
GRANT USAGE ON SCHEMA mes TO steel_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA mes TO steel_reader;
SELECT c.relname AS "表", c.relkind AS "种类",
       CASE WHEN c.relkind = 'r' THEN (xpath('/row/n/text()', query_to_xml(
           format('SELECT count(*) AS n FROM mes.%I', c.relname), false, true, '')))[1]::text END AS "行数"
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'mes' AND c.relkind IN ('r', 'v') ORDER BY 1;
'@
    ) -join "`n"

    $composeArgs = Get-ComposeArgs
    $previousConsole = [Console]::OutputEncoding
    $OutputEncoding = [Text.UTF8Encoding]::new($false)
    try {
        [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
        Write-Step '建立只读账号 steel_reader 与库 steel_mes'
        $setup | docker compose @composeArgs exec -T postgres psql -U ontology -d postgres -v ON_ERROR_STOP=1 -q | Out-Host
        if ($LASTEXITCODE -ne 0) { Stop-Dev "建立账号与库失败，退出码 $LASTEXITCODE" }
        Write-Step '重建 mes 模式并装入样例数据'
        $load | docker compose @composeArgs exec -T postgres psql -U ontology -d steel_mes -v ON_ERROR_STOP=1 --single-transaction -q | Out-Host
        if ($LASTEXITCODE -ne 0) { Stop-Dev "装载样例数据失败，退出码 $LASTEXITCODE" }
    } finally {
        [Console]::OutputEncoding = $previousConsole
    }
    Write-Ok '样例库已就绪。在界面上新建数据源：主机 postgres，端口 5432，库 steel_mes，用户 steel_reader，口令见 docs/development.md'
}

function Invoke-Reset {
    Write-Note '将删除开发栈的全部容器和数据卷（数据库内容会丢失）。'
    $answer = Read-Host '确认删除请输入 RESET'
    if ($answer -ne 'RESET') { Stop-Dev '已取消' 0 }
    Invoke-Compose --profile tools down -v
    Write-Ok '已删除'
}

# compose.yaml reads the image tag from the environment; restore the caller's value afterwards.
$callerImageTag = $env:OP_IMAGE_TAG
$env:OP_IMAGE_TAG = $ImageTag
try {
    switch ($Command) {
        'up' { Invoke-Up }
        'down' { Invoke-Compose --profile tools down }
        'status' { Show-Status }
        'logs' { Invoke-Compose logs --tail 200 @Rest }
        'build' { Confirm-BaseImages; Invoke-Compose build api web }
        'lock' { Invoke-Lock ($Rest | Select-Object -First 1) }
        'test-api' { exit (Invoke-ToolTest 'test-api' ($Rest.Count -gt 0 ? @('pytest') + $Rest : @())) }
        'test-web' { exit (Invoke-ToolTest 'test-web') }
        'e2e' { exit (Invoke-E2e) }
        'test' {
            Confirm-BaseImages
            $codes = Invoke-Parallel @('test-api', 'test-web') (Join-Path $Root '.verification/test')
            if (@($codes.Values | Where-Object { $_ -ne 0 }).Count -gt 0) { exit 1 }
        }
        'gen-api' { Invoke-GenApi }
        'schema-check' { exit (Invoke-SchemaCheck) }
        'ci' { Invoke-Ci }
        'psql' { Invoke-Compose exec postgres psql -U ontology -d ontology }
        'seed-steel' { Invoke-SeedSteel }
        'fmt' { Invoke-Fmt $Rest }
        'eval' { Invoke-Eval ($Rest | Select-Object -First 1) $Replay.IsPresent $Recordings $Sequential.IsPresent $CodeFrom $Reviewed.IsPresent $NoMemory.IsPresent }
        'eval-qa' { Invoke-EvalQa $Replay.IsPresent $Recordings $CodeFrom }
        'owl-check' { Invoke-OwlCheck }
        'ai-check' {
            Confirm-BaseImages
            Invoke-Compose build api
            $composeArgs = Get-ComposeArgs
            $previousConsole = [Console]::OutputEncoding
            [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
            try {
                docker compose @composeArgs run --rm -T --no-deps --name (New-TempName 'ai-check') api python -m ontology_platform.modules.ai.check | Out-Host
                $code = $LASTEXITCODE
            } finally {
                [Console]::OutputEncoding = $previousConsole
            }
            exit $code
        }
        'images' { Invoke-Images }
        'clean-images' { Invoke-Images -Clean }
        'init-env' { Invoke-InitEnv }
        'reset' { Invoke-Reset }
        default { Get-Help $PSCommandPath -Detailed | Out-Host }
    }
} finally {
    $env:OP_IMAGE_TAG = $callerImageTag
}
