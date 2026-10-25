# macOS 开发与 Windows/Linux 回退

适用于 M0 工程接管，不授权 Wave 2。实际验收见 [M0 任务卡](../tasks/M0-MAC-PORTABILITY-001.md) 与 [总报告](../evidence/M0-MAC-PORTABILITY-001/delivery-report.md)。不要从 Windows 拷贝 .git、凭证、工具缓存、秘密、数据库卷或 Codex 私有会话。

## 固定工具与平台

本机 macOS27.0.1/arm64、.NET SDK10.0.402（osx-arm64）、Node24.22.1、PowerShell7.6.8、Python3.13.17、Docker Engine29.9.2 linux/aarch64、Codex CLI0.164.0-alpha.11.1、gh2.103.2。SDK由 global.json 禁止滚动；已有安装优先，不自动改机器 PATH/默认SDK/全局EF。安装系统组件和管理员改动需人类另行处理。

AppHost锁按实际 SDK RID 选择：win-x64、linux-x64、osx-arm64。Intel Mac osx-x64 本轮 NOT_RUN，不能套用 arm64 锁。Windows ARM、Linux ARM 开发宿主亦未声明通过；Docker Linux ARM64 容器不是 Linux ARM64 .NET 开发宿主验收。

## 项目隔离 pnpm11.28.8

全局pnpm12.15.0保留。直接使用项目Node运行 .tools/pnpm/package/bin/pnpm.cjs，不执行全局 self-update/corepack enable。复现隔离下载可用以下PowerShell，所有写入限当前仓库忽略目录：

```powershell
New-Item -ItemType Directory -Force .tools/pnpm | Out-Null
$metadata = Invoke-RestMethod https://registry.npmjs.org/pnpm/11.28.8
if ($metadata.version -ne '11.28.8') { throw 'Unexpected pnpm version' }
Invoke-WebRequest $metadata.dist.tarball -OutFile .tools/pnpm-11.28.8.tgz
$bytes = [IO.File]::ReadAllBytes((Join-Path $PWD '.tools/pnpm-11.28.8.tgz'))
$integrity = 'sha512-' + [Convert]::ToBase64String([Security.Cryptography.SHA512]::HashData($bytes))
$expected = 'sha512-9piKMgRrmj9419fuB0eSa76QX/nf9zvxmruHvX0ZBqKskNk/c74ytfnhTCiZVpvLDJxeyKGeCD9dcburbdnguA=='
if ($integrity -ne $expected -or $integrity -ne $metadata.dist.integrity) { throw 'pnpm integrity mismatch' }
tar -xzf .tools/pnpm-11.28.8.tgz -C .tools/pnpm
if ($LASTEXITCODE -ne 0) { throw 'pnpm extraction failed' }
node .tools/pnpm/package/bin/pnpm.cjs --version
```

当前前端只有工作区清单，没有产品构建目标，不生成假 pnpm-lock.yaml 或运行未授权 Web Shell。未来 FE 获批后再执行实际 frozen-lockfile 安装。Worktree 可各自准备 .tools，或以 doctor -ToolRoot 指向已校验共享目录；只读复用不代表必须迁移工具缓存。

## 诊断、恢复和真实测试

在仓库根执行，macOS/Linux用python3，Windows用python（固定批准版本）：

```powershell
python3 -m pip install --index-url https://pypi.org/simple --only-binary=:all: --no-deps --require-hashes --disable-pip-version-check --target .tools/pythonlibs -r scripts/verification-requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Parser restore failed' }
pwsh -NoProfile -File scripts/doctor.ps1 -CheckDocker
dotnet restore backend/OntologyPlatform.slnx --locked-mode
if ($LASTEXITCODE -ne 0) { throw 'Locked restore failed' }
pwsh -NoProfile -File scripts/verify.ps1 -SelfTest -RunNative -RunTests
```

每条命令必须检查退出码。doctor exit2 表示版本/可访问环境阻断，exit1诊断异常；verify exit1为检查失败。doctor不是安装器；真实应用测试与容器测试另计，不将静态配置、空solution或零测试视作产品通过。PowerShell -ToolRoot 参数语义不同：doctor 指 .tools 目录本身，verify 指包含 .tools 的仓库/工具根；未传参使用当前树默认。

新增Mac解析器wheel只批准CPython3.13 arm64，保持Windows CPython3.13 x64、Ubuntu CPython3.12 x64哈希。其他Python/RID组合恢复失败时停止，不关闭 --require-hashes 或改用未登记源码包。NuGet新RID锁必须来自官方真实restore并审查；生成文件末尾LF可规范，不能编辑依赖关系冒充恢复成功。

## 容器、监听和数据

四资源及完整命令见 [基础设施手册](local-infrastructure.md)。AppHost为唯一资源模型，使用固定摘要和专用开发命名卷，不启用 --platform linux/amd64 模拟来宣称原生兼容。通过当前进程环境注入新随机秘密，禁止写仓库、终端记录、URL或证据。不要打印 Dashboard 登录token、docker inspect 的完整 Env 或用户秘密内容；只查询容器平台、卷名、端口等必要字段。

Windows卷不迁移，本机初始化测试数据；保留真实数据时须另行备份恢复，不将本轮随机开发探针当生产恢复证明。先核实固定端口可用，所有外部监听只在127.0.0.1/::1；启动健康不等于资源Ready。重启测试使用本任务卷前缀，不删除现有卷，不执行volume prune。

## 故障与回退

- .NET缺精确SDK：停止恢复，安装由人类按官方支持矩阵处理；不放宽global.json。
- pnpm显示12或长时间DNS重试：用明确Node+项目cjs入口，检查官方源网络；不改锁定目标或全局配置。
- Docker socket在Codex沙箱被拒：按客户端正常权限流程运行同一命令；不能据此判daemon故障或改socket权限。
- AppHost ASPIRE010：当前官方NuGet Dashboard/DCP回退路径，警告保留；CLI bundle特有能力未验，不抑制警告冒充通过。
- 镜像没有原生ARM64或固定校验失败：BLOCKED，停止该资源并提交具体架构/摘要事实，换图须独立批准。
- macOS默认大小写不敏感不等于Linux路径通过；继续以真实Linux CI为门禁。
- Windows回退：在原Windows开发目录fetch新main，保留自己的秘密和卷，使用win-x64 SDK/原锁、Python3.13 x64和相同PowerShell入口；先doctor再locked restore/verify。不要把Mac .tools或worktree元数据复制过去。M0未实际重跑Windows，历史PASS仅保留历史含义。
- CI继续ubuntu-24.04、官方SHA固定动作、只读权限和锁定restore；本轮不启用macOS付费Runner。手工重新运行CI以GitHub实际run为准，空status不是PASS。

## Master 恢复

任务合同冻结Single Writer与路径所有权，独立树使用明确分支和规范化绝对路径。自定义explorer/platform_worker/quality_reviewer已按实际工具派发；只读角色是指令约束，OS权限仍由宿主决定。未集成果保留树；只有独立审查、Mac真实验收和Linux CI门禁通过才进入main。恢复资料见 [Master交接](../handoffs/2026-10-25-mac-master.md)。
