# M0 平台依赖与恢复

2026-10-25。沿用已批准版本，不引入产品框架。pnpm11.28.8（MIT）从官方 npm registry tarball 获取并逐字节 SHA512 匹配 integrity；通过 node .tools/pnpm/package/bin/pnpm.cjs --version 实测11.28.8，不修改全局pnpm12.15.0。PyYAML6.0.3（MIT）新增官方 CPython3.13 macOS arm64 wheel SHA256，并用 --only-binary=:all: --no-deps --require-hashes --target .tools/pythonlibs 实际恢复。精确来源和 hash 见 official-dependencies.json。哈希匹配不是完整签名或漏洞审计。

AppHost 新 packages.osx-arm64.lock.json 由 dotnet restore backend/OntologyPlatform.slnx --use-lock-file 实际生成（exit0），随后 --locked-mode 成功；非手写依赖图。NuGet 生成文件缺末尾换行，静态验收首次 exit1；仅添加 LF，解析 JSON 前后一致。Windows/Linux 和其他三工程锁文件 Git diff 均为空。

全部三平台锁图共112个唯一包版本，当前Mac恢复108个，公开nuspec许可记录见 lock-license-inventory.json；四个非Mac平台工具包未在本机恢复，许可沿用历史G1清单，不声称重新恢复。Mac新工具 Aspire.Dashboard.Sdk.osx-arm64 / Aspire.Hosting.Orchestration.osx-arm64 13.6.3 为MIT，与既有Aspire家族一致。官方源为 https://api.nuget.org/v3/index.json 。漏洞查询使用 dotnet list backend/OntologyPlatform.slnx package --vulnerable --include-transitive --format json；当前输出未列已知漏洞包，详见 vulnerability-query.json；不代表镜像OS层SBOM或完整供应链审计。

官方资料：

- [pnpm 安装](https://pnpm.io/installation)：当前latest为12，故显式保留11.28.8，不跟随latest。
- [PyYAML精确发行物](https://pypi.org/pypi/PyYAML/6.0.3/json)：MIT和Mac wheel哈希来源。
- [.NET10 官方支持矩阵](https://github.com/dotnet/core/blob/main/release-notes/10.0/supported-os.md)：2026-09-28版本列出macOS27/26/15 Arm64/x64。Microsoft Learn安装页仍只列到26，两者存在更新差异；本机macOS27.0.1遵循更明确的版本矩阵，真实运行单列证据。
- [Docker Desktop Mac条件](https://docs.docker.com/desktop/setup/install/mac-install/)：支持当前及前两个macOS主版本；使用用户已运行daemon，不安装/变更许可订阅。
- [官方Codex子Agent](https://learn.chatgpt.com/docs/agent-configuration/subagents)：角色/TOML不代表独立OS权限，本会话以实际派发和Git隔离证据为准。
