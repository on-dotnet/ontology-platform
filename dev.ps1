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
  test-api [参数]   后端检查：ruff、mypy、pytest（临时数据库，跑完删除）；
                    带参数时只运行 pytest <参数>，如 test-api tests/test_ai_pipeline.py -x
  test-web          前端检查：eslint、tsc、vitest
  test              依次运行 test-api、test-web
  gen-api           从后端导出 OpenAPI，并生成前端类型 web/src/api/schema.d.ts
  fmt <文件...>     用容器里的 ruff 修复并格式化指定的 backend 文件（经标准输入，只改这些文件）
  ai-check          在容器里实际调用一次模型，只显示能否连通，不显示地址与 Key
  eval [案例]       用真实模型识别 samples/<案例>（默认 steel）并按期望答案打分，结果存 .verification/eval/（会产生模型费用）
  owl-check         Protégé 往返检查：样例与开发栈当前版本经平台导出，由 OWL API（断网）读写后再导回，
                    除已知改写外不得有差异；报告存 .verification/owl-check/
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
        $fixed = $source | docker run --rm -i --name (New-TempName 'fmt') ontology/test-api:local sh -c "ruff check --fix --exit-zero --quiet --stdin-filename '$relative' - | ruff format --quiet --stdin-filename '$relative' -"
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

# Scores extraction on a case pack with the real model. Files travel as base64 JSON on stdin.
function Invoke-Eval([string]$Case) {
    if (-not $Case) { $Case = 'steel' }
    $caseDir = Join-Path $Root "samples/$Case"
    if (-not (Test-Path -LiteralPath (Join-Path $caseDir 'eval/expected.toml'))) { Stop-Dev "找不到 samples/$Case/eval/expected.toml" }
    Confirm-BaseImages
    Invoke-Compose build api
    $files = @{}
    foreach ($item in Get-ChildItem -LiteralPath (Join-Path $caseDir 'docs') -File) {
        $files["docs/$($item.Name)"] = [Convert]::ToBase64String([IO.File]::ReadAllBytes($item.FullName))
    }
    $files['eval/expected.toml'] = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $caseDir 'eval/expected.toml')))
    $bundle = @{ files = $files } | ConvertTo-Json -Compress
    $outDir = New-Item -ItemType Directory -Force -Path (Join-Path $Root '.verification/eval')
    $outFile = Join-Path $outDir "$Case-$(Get-Date -Format 'yyyyMMdd-HHmmss').json"
    $composeArgs = Get-ComposeArgs
    $previousConsole = [Console]::OutputEncoding
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
    try {
        Write-Step "识别 samples/$Case（进度显示在下方）"
        $result = $bundle | docker compose @composeArgs run --rm -T --no-deps --name (New-TempName 'eval') api python -m ontology_platform.modules.ai.eval
        $code = $LASTEXITCODE
    } finally {
        [Console]::OutputEncoding = $previousConsole
    }
    if ($code -ne 0) { Stop-Dev "评测失败，退出码 $code" }
    Set-Content -LiteralPath $outFile -Encoding utf8NoBOM -Value ($result -join "`n")
    $result | Out-Host
    Write-Ok "结果已保存到 $outFile"
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
    Write-Step '构建 OWL API 工具镜像 ontology/owlapi:local'
    docker build --build-arg "MAVEN_MIRROR=$(Get-MirrorValue 'OP_MAVEN_MIRROR')" -t ontology/owlapi:local (Join-Path $Root 'dev/owlapi') | Out-Host
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
            docker run -d --network none --name $api --entrypoint sleep ontology/api:local 1800 | Out-Null
            docker run -d --network none --name $java --entrypoint sleep ontology/owlapi:local 1800 | Out-Null
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
    'test-api' { exit (Invoke-ToolTest 'test-api' ($Rest.Count -gt 0 ? @('pytest') + $Rest : @())) }
    'test-web' { exit (Invoke-ToolTest 'test-web') }
    'test' { $a = Invoke-ToolTest 'test-api'; $w = Invoke-ToolTest 'test-web'; if ($a -ne 0 -or $w -ne 0) { exit 1 } }
    'gen-api' { Invoke-GenApi }
    'ci' { Invoke-Ci }
    'psql' { Invoke-Compose exec postgres psql -U ontology -d ontology }
    'fmt' { Invoke-Fmt $Rest }
    'eval' { Invoke-Eval ($Rest | Select-Object -First 1) }
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
    'init-env' { Invoke-InitEnv }
    'reset' { Invoke-Reset }
    default { Get-Help $PSCommandPath -Detailed | Out-Host }
}
