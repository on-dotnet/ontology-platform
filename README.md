# Ontology Platform

仓库：`on-dotnet/ontology-platform`。多行业AI Native本体与知识平台，基础工程统一`OntologyPlatform.*`。

当前任务以[授权索引](docs/tasks/current-authorization.md)为准；G1-ENG-001保持历史PARTIAL，当前正式授权M0-MAC-PORTABILITY-001 Mac接管及兼容验收（G1-INFRA为已交付历史）。G0/G1-ENG是历史归档，不把空solution或零应用测试当作产品通过。

## 检查入口

使用PowerShell7；解析器代码要求Python3.11+，当前批准的安装哈希覆盖Windows CPython3.13 x64、Ubuntu CPython3.12 x64和macOS CPython3.13 arm64。V2完整语法门禁先按精确哈希隔离恢复小型解析器，不修改全局Python；其他组合需先核验发行物并登记哈希：

```powershell
python -m pip install --index-url https://pypi.org/simple --only-binary=:all: --no-deps --require-hashes --target .tools/pythonlibs -r scripts/verification-requirements.txt
pwsh -NoProfile -File scripts/verify.ps1 -SelfTest
pwsh -NoProfile -File scripts/doctor.ps1
```

verify默认退出0仅代表工程静态检查通过，退出1表示失败；SelfTest在受控临时目录跑正反例并清理，包含审查ZIP测试。显式`-RunNative -RunTests`才执行真实.NET构建、格式和MTP测试，先按项目锁恢复；默认优先根`.tools/dotnet`，Worktree可用`-ToolRoot`指向已准备工具目录。有限机密模式扫描不是完整安全审计。doctor只读，退出0为必要工具版本满足、2为环境BLOCKED、1为异常，不安装或启动资源。CI使用同一入口；远程CI只按实际run ID/URL/commit/结论记录。

工具目标：SDK10.0.402、Node24.22.1、pnpm11.28.8，详见[本阶段工具登记](docs/evidence/G1-INFRA-001/toolchain.md)。本机不满足时保持目标并报告，不升级OS/用户全局工具。真实.NET依赖恢复后提交项目锁，前端只有清单时不创建空锁文件，Turbo配置待实际前端任务落地后接入。

## 工程边界

前端`apps/web`、`@ontology-platform/web`；后端入口`backend/OntologyPlatform.slnx`。ServiceDefaults仅宿主默认设置，BuildingBlocks仅必要技术合同，运行时MAF与研发Agent分开。最小健康API和基础设施测试不代表业务或Web已实现；没有实际Web目标时其检查均NOT_RUN。

[研发约定](AGENTS.md) · [计划与交接](PLANS.md) · [G0审查记录](docs/planning/10-g0-review-record.md) · [目录ADR](docs/adr/ADR-001-design-system-location.md)

G1-INFRA实现、真实验证和保留事项见[交付记录](docs/evidence/G1-INFRA-001/delivery-report.md)；开发资源启动见[操作手册](docs/development/local-infrastructure.md)。历史G1-ENG状态不因本次运行结果改写。

任务完成后停止；任何其他G1任务或G2必须另行明确授权。

Mac固定工具、项目隔离pnpm11.28.8、跨平台回退与Master恢复见[Mac开发手册](docs/development/macos-setup.md)。
