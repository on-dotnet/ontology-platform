# M0 专项 A 脚本兼容证据

状态：PARTIAL，等待独立 Reviewer、Master 集成及整体 Mac/Linux 验收。日期：2026-10-25。
基线：e3f0b9694412f7a91b6075be9d7e8d4fac4b890b；分支：codex/M0-scripts；独立 Worktree：m0-scripts/ontology-platform。

## 变更与根因

doctor 原先把全部非 Windows 隔离 Node 路径硬编码为 linux-x64，导致 macOS ARM64 的 darwin-arm64/bin/node 不被发现。现在按 OS 与 OSArchitecture 选择 Node 官方发行目录，继续优先项目隔离工具并保留 PATH 回退。

新增回归在含空格临时目录创建真实本机 Node 的符号链接，隐藏 PATH 回退，断言 doctor 真正执行隔离 Node 并报告目标版本。已有缺 Node、仅有 pnpm 的负例保留。未修改 verify 或构包脚本：真实既有正反例未发现需修复问题。

## 实际验证

- 初始新增回归先失败；随后修复。为排除夹具早期多入口问题，使用修正后夹具再次对基线 doctor 重放，退出 1，原因 Native macOS ARM64 Node in isolated path was not discovered，见 doctor-red.txt。基线脚本由 git show 导出至临时目录，只读重放。
- `pwsh -NoProfile -File scripts/tests/Doctor.Tests.ps1`：退出 0，2 项通过，见 doctor-green.txt。
- `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`：最终复验退出 0，checker 8 + doctor 2 + structured 4 + ReviewPackage 35 = 49 项，见 self-test.txt。结构化输出的两个 FAIL 是预期解析负例，断言已验证退出 1。ReviewPackage 35 项含实际生成与 VerifyOnly 重开、路径/散列/源码/full diff 和负例拒绝。
- `pwsh -NoProfile -File scripts/doctor.ps1 -CheckDocker`：沙箱内退出 2（Docker daemon 不可访问，见 doctor-sandbox.txt）；按权限升级后同命令退出 0（doctor.txt）。SDK 10.0.402、Node 24.22.1、pnpm 11.28.8、Docker 29.9.2。
- `git diff --check`：退出 0。

## 环境与限制

Master 恢复的 .tools/pythonlibs 与 .tools/pnpm 在本树忽略目录中只读引用；未安装全局依赖或修改机器配置。第一次把正在写入的日志放进被扫描目录，静态检查按设计拒绝未完成文本（退出 1）；后续全部运行输出先写临时目录，完成后归档。

macOS ARM64 原生回归在其他 OS 明确 NOT_RUN；原有缺工具负例仍跨平台执行。Windows/Linux 本专项实际运行 NOT_RUN，远程 CI NOT_VERIFIED。应用测试、真实构建、资源探针、Trace 与最终唯一标准 ZIP 由 Master/对应 Owner 验收；不以 49 个脚本测试代替产品通过。未合并 main，未自行进入下游关口。
