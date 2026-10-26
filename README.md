# Ontology Platform

仓库：`on-dotnet/ontology-platform`。多行业AI Native本体与知识平台，基础工程统一`OntologyPlatform.*`。

当前任务以[授权索引](docs/tasks/current-authorization.md)为准；本轮G2-THIN-SLICE-001源码、Mac完整cold工具链和Linux验证已进入复审交付，整体PARTIAL（Monaco按人类暂停，真实模型/Windows/Intel/生产未验）。新[开发运维手册](docs/development/g2-local-development-and-operations.md)与[验收报告](docs/evidence/G2-THIN-SLICE-001/master/delivery-report.md)区分实际范围；最终Head/CI/唯一ZIP以实际manifest回执为准。G0、M0、G1各阶段保持原历史，不把空solution、零测试或配置存在当产品通过。

## 检查入口

使用PowerShell7；解析器代码要求Python3.11+，当前批准的安装哈希覆盖Windows CPython3.13 x64、Ubuntu CPython3.12 x64和macOS CPython3.13 arm64。V2完整语法门禁先按精确哈希隔离恢复小型解析器，不修改全局Python；其他组合需先核验发行物并登记哈希：

```powershell
python -m pip install --index-url https://pypi.org/simple --only-binary=:all: --no-deps --require-hashes --target .tools/pythonlibs -r scripts/verification-requirements.txt
pwsh -NoProfile -File scripts/verify.ps1 -SelfTest
pwsh -NoProfile -File scripts/doctor.ps1
```

verify默认退出0仅代表工程静态检查通过，退出1表示失败；SelfTest在受控临时目录跑正反例并清理，包含审查ZIP测试。显式`-RunNative -RunTests`才执行真实.NET构建、格式和MTP测试，先按项目锁恢复；默认优先根`.tools/dotnet`，Worktree可用`-ToolRoot`指向已准备工具目录。有限机密模式扫描不是完整安全审计。doctor只读，退出0为必要工具版本满足、2为环境BLOCKED、1为异常，不安装或启动资源。CI使用同一入口；远程CI只按实际run ID/URL/commit/结论记录。

工具目标：SDK10.0.402、Node24.22.1、pnpm11.28.8，详见[本阶段工具登记](docs/evidence/G1-INFRA-001/toolchain.md)。本机不满足时保持目标并报告，不升级OS/用户全局工具。真实.NET依赖恢复后提交项目锁，真实Web与pnpm锁已建立，固定工具/冻结恢复和四项独立检查见[Wave2操作手册](docs/development/wave2-local-development.md)。

## 工程边界

前端`apps/web`、`@ontology-platform/web`；后端入口`backend/OntologyPlatform.slnx`。ServiceDefaults仅宿主默认设置，BuildingBlocks仅必要技术合同，运行时MAF与研发Agent分开。原InfrastructureApi仍为技术探针；正式Api、Next Shell、PG会话/审计和LGTM真实验收见[Wave2交付报告](docs/evidence/G1-WAVE2/master/delivery-report.md)。

[研发约定](AGENTS.md) · [计划与交接](PLANS.md) · [G0审查记录](docs/planning/10-g0-review-record.md) · [目录ADR](docs/adr/ADR-001-design-system-location.md)

G1-INFRA实现、真实验证和保留事项见[交付记录](docs/evidence/G1-INFRA-001/delivery-report.md)；开发资源启动见[操作手册](docs/development/local-infrastructure.md)。历史G1-ENG状态不因本次运行结果改写。

本轮只按已批准G2执行，交付后停止等待复审；G3–G8及任何新的业务范围必须另行明确授权。

Mac固定工具、项目隔离pnpm11.28.8、跨平台回退与Master恢复见[Mac开发手册](docs/development/macos-setup.md)。
