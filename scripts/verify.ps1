<#
.SYNOPSIS
运行工程基线检查；不安装依赖、不启动服务。
.DESCRIPTION
退出0仅代表选定工程检查通过；应用缺失时明确NOT_RUN。退出1为检查失败。
SelfTest执行隔离临时目录中的真实正反例；Library只加载检查函数。
#>
[CmdletBinding()]
param(
    [string]$Root = (Split-Path $PSScriptRoot -Parent),
    [switch]$SelfTest,
    [switch]$RunNative,
    [switch]$Library
)
$ErrorActionPreference = 'Stop'

function Get-SourceFiles {
    param([string]$Directory)
    foreach ($entry in Get-ChildItem -LiteralPath $Directory -Force) {
        if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
        if ($entry.PSIsContainer) {
            if ($entry.Name -notin @('.git', 'node_modules', 'bin', 'obj', '.next', '.turbo', '.worktrees', 'artifacts')) {
                Get-SourceFiles -Directory $entry.FullName
            }
        } else { $entry }
    }
}

function Test-Repository {
    param([string]$RepositoryRoot)
    # 每项结果只打印位置和原因，不打印疑似机密内容。
    $results = [Collections.Generic.List[object]]::new()
    function Record {
        param([string]$Check, [string]$Status, [string]$Message)
        $results.Add([pscustomobject]@{ Check = $Check; Status = $Status; Message = $Message })
    }
    $base = [IO.Path]::GetFullPath($RepositoryRoot)
    $files = @(Get-SourceFiles -Directory $base)
    $jsonValues = @{}
    foreach ($file in $files) {
        $relative = [IO.Path]::GetRelativePath($base, $file.FullName).Replace('\', '/')
        if ($file.Extension -notin @('.json', '.xml', '.props', '.targets', '.slnx', '.Config', '.ps1', '.md', '.toml', '.yaml', '.yml', '.example', '.cs', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.css', '.html', '.py', '.txt', '.log', '.csv') -and
            $file.Name -notmatch '^\.env(?:\.|$)' -and
            $file.Name -notin @('.editorconfig', '.node-version', '.gitignore', '.dockerignore', '.gitattributes', 'CODEOWNERS')) { continue }
        $text = [IO.File]::ReadAllText($file.FullName)
        if ($text -match '\r' -or -not $text.EndsWith("`n") -or $text -match '(?m)[\t ]+$') {
            # 历史G0文档保留Markdown有意换行空格；其余文件拒绝尾随空白。
            if ($text -match '\r' -or -not $text.EndsWith("`n") -or ($file.Extension -ne '.md' -and $text -match '(?m)[\t ]+$')) {
                Record 'text-format' 'FAIL' "$relative 需要LF/末尾换行/无尾随空白"
            }
        }
        if ($file.Extension -eq '.json') {
            try { $jsonValues[$relative] = ConvertFrom-Json -InputObject $text -AsHashtable -ErrorAction Stop }
            catch { Record 'json' 'FAIL' "$relative JSON无效" }
        }
        if ($file.Extension -in @('.props', '.targets', '.slnx', '.Config')) {
            try { $null = [xml]$text } catch { Record 'xml' 'FAIL' "$relative XML无效" }
        }
        if ($file.Extension -eq '.ps1') {
            $tokens = $null
            $parseErrors = $null
            $null = [Management.Automation.Language.Parser]::ParseInput($text, [ref]$tokens, [ref]$parseErrors)
            if ($parseErrors.Count -gt 0) { Record 'powershell-syntax' 'FAIL' "$relative 解析失败" }
        }
        # 有限模式扫描：不声称取代完整秘密扫描器或依赖漏洞审计。
        $secretPattern = '(-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{32,})'
        if ($text -match $secretPattern -or $text -match '(?im)^\s*(?:password|client_secret|api_key|access_token)\s*[:=]\s*["'']?[^\s"''#<>]{8,}') {
            Record 'secret-patterns' 'FAIL' "$relative 命中凭证模式，值已隐藏"
        }
        if ($file.Extension -eq '.md') {
            if (([regex]::Matches($text, '(?m)^```').Count % 2) -ne 0) { Record 'markdown-fences' 'FAIL' "$relative 围栏不闭合" }
            # 只检查围栏外链接，避免把文档中的代码示例误当实际导航。
            $prose = [regex]::Replace($text, '(?ms)^```[^\n]*\n.*?^```[^\n]*$', '')
            foreach ($link in [regex]::Matches($prose, '\[[^\]\n]+\]\(([^)\n]+)\)')) {
                $target = $link.Groups[1].Value.Trim('<', '>')
                if ($target -match '^(https://|mailto:)') { continue }
                if ($target -match '^(/|[A-Za-z]:|file:|https?:)') {
                    Record 'markdown-links' 'FAIL' "$relative 本地链接必须相对仓库"; continue
                }
                $parts = $target.Split('#', 2)
                $path = if ($parts[0]) { [IO.Path]::GetFullPath((Join-Path $file.DirectoryName ([uri]::UnescapeDataString($parts[0])))) } else { $file.FullName }
                if (-not $path.StartsWith($base + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
                    -not (Test-Path -LiteralPath $path)) {
                    Record 'markdown-links' 'FAIL' "$relative 存在缺失或越界链接"; continue
                }
                if ($parts.Count -eq 2 -and $parts[1]) {
                    $headings = @(Get-Content -LiteralPath $path | Where-Object { $_ -match '^#{1,6} ' } | ForEach-Object {
                        (($_ -replace '^#{1,6} ', '').ToLower() -replace '[^\p{L}\p{N}_\- ]', '') -replace ' ', '-'
                    })
                    if ([uri]::UnescapeDataString($parts[1]) -notin $headings) { Record 'markdown-links' 'FAIL' "$relative 锚点不存在" }
                }
            }
        }
    }
    $required = @('global.json', 'Directory.Build.props', 'Directory.Packages.props', 'NuGet.Config', '.config/dotnet-tools.json',
        'package.json', 'apps/web/package.json', 'pnpm-workspace.yaml', 'turbo.json', '.node-version',
        'AGENTS.md', 'PLANS.md', 'backend/AGENTS.md', 'apps/web/AGENTS.md', '.editorconfig', '.github/workflows/ci.yml')
    foreach ($path in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $base $path))) { Record 'required-files' 'FAIL' "$path 缺失" }
    }
    if ($jsonValues['package.json'].name -ne 'ontology-platform' -or $jsonValues['apps/web/package.json'].name -ne '@ontology-platform/web') {
        Record 'naming' 'FAIL' '根包或Web包名称不符合冻结命名'
    }
    if ($jsonValues['package.json'].private -ne $true -or $jsonValues['apps/web/package.json'].private -ne $true) { Record 'package-policy' 'FAIL' '工作区必须private' }
    $sdk = $jsonValues['global.json'].sdk
    if ($sdk.version -notmatch '^10\.0\.\d+$' -or $sdk.rollForward -ne 'disable' -or $sdk.allowPrerelease -ne $false) { Record 'sdk-policy' 'FAIL' 'SDK必须精确.NET10、禁预览和隐式滚动' }
    $pm = $jsonValues['package.json'].packageManager
    if ($pm -notmatch '^pnpm@\d+\.\d+\.\d+$') { Record 'package-policy' 'FAIL' '包管理器必须精确版本' }
    $workspacePath = Join-Path $base 'pnpm-workspace.yaml'
    if (Test-Path -LiteralPath $workspacePath) {
        if ([IO.File]::ReadAllText($workspacePath).Trim() -ne "packages:`n  - apps/web") { Record 'workspace-policy' 'FAIL' 'ADR-001只允许apps/web工作区' }
    }
    $workflowPath = Join-Path $base '.github/workflows/ci.yml'
    if (Test-Path -LiteralPath $workflowPath) {
        $workflow = [IO.File]::ReadAllText($workflowPath)
        $uses = [regex]::Matches($workflow, '(?m)^\s*-?\s*uses:\s*(\S+)')
        if ($uses.Count -eq 0 -or @($uses | Where-Object { $_.Groups[1].Value -notmatch '^actions/checkout@[a-f0-9]{40}$' }).Count -gt 0 -or
            $workflow -notmatch '(?m)^permissions:\n  contents: read\s*$' -or $workflow -notmatch 'persist-credentials: false' -or
            $workflow -match '(pull_request_target|write-all|secrets\.|curl |wget |npm install|pnpm install)' -or
            $workflow -notmatch 'runs-on: ubuntu-24.04' -or $workflow -notmatch 'verify.ps1 -SelfTest') {
            Record 'workflow-policy' 'FAIL' 'CI须固定官方checkout SHA、只读权限、受控Runner、静态同一入口'
        }
    }
    if ($results.Count -eq 0) { Record 'repository-static' 'PASS' "检查$($files.Count)个文件：语法/格式/相对链接/有限机密模式/基线策略通过" }
    return $results.ToArray()
}

if ($Library) { return }
try {
    $checks = @(Test-Repository -RepositoryRoot $Root)
    $checks | Format-Table -AutoSize | Out-Host
    if (@($checks | Where-Object Status -eq 'FAIL').Count -gt 0) { exit 1 }
    if ($SelfTest) {
        & (Join-Path $PSScriptRoot '../docs/evidence/G1-ENG-001/verify.tests.ps1')
        if (-not $?) { exit 1 }
    }
    # 只有显式获准RunNative时才运行真实项目命令，不执行安装或恢复。
    $nativeSolution = [IO.Path]::GetFullPath((Join-Path $Root 'backend/OntologyPlatform.slnx'))
    $projects = @(Get-ChildItem -LiteralPath (Join-Path $Root 'backend') -Recurse -Filter '*.csproj' -File)
    if ($projects.Count -eq 0) { Write-Output 'NOT_RUN: .NET build/test/format：无项目，空solution不作为通过。' }
    elseif ($RunNative) {
        # dotnet按cwd解析global.json；绝对solution路径本身不足以锁定SDK。
        Push-Location $Root
        try {
            foreach ($arguments in @(
                @('build', $nativeSolution, '--no-restore'),
                @('format', $nativeSolution, '--verify-no-changes', '--no-restore')
            )) {
                & dotnet @arguments
                if ($LASTEXITCODE -ne 0) { exit 1 }
            }
        } finally { Pop-Location }
        Write-Output 'NOT_RUN: .NET test：测试runner及测试项目须按ADR-005验证后单独接入。'
    } else { Write-Output 'NOT_RUN: .NET原生检查需显式-RunNative及对应任务授权。' }
    $web = Get-Content -Raw (Join-Path $Root 'apps/web/package.json') | ConvertFrom-Json -AsHashtable
    foreach ($task in @('lint', 'typecheck', 'build', 'test', 'test:e2e')) {
        if (-not $web.scripts -or -not $web.scripts.ContainsKey($task)) { Write-Output "NOT_RUN: Web $task：未建立实际目标。" }
        elseif ($RunNative) {
            & pnpm --dir (Join-Path $Root 'apps/web') run $task
            if ($LASTEXITCODE -ne 0) { exit 1 }
        } else { Write-Output "NOT_RUN: Web $task：需要显式-RunNative及对应授权。" }
    }
    Write-Output 'PASS: 工程静态门禁；不是产品构建/测试或整个G1通过。'
    exit 0
} catch {
    Write-Output "FAIL: 工程检查异常：$($_.Exception.Message)"
    exit 1
}
