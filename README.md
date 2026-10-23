# Ontology Platform

仓库：`on-dotnet/ontology-platform`。多行业AI Native本体与知识平台，基础工程统一`OntologyPlatform.*`。

当前仅实施[G1-ENG-001](docs/tasks/G1-ENG-001.md)工程基线，没有API、Web页面或可运行业务服务。G0计划是历史归档，后续专项授权见任务卡和ADR；不把空solution或零应用测试当作产品通过。

## 检查入口

使用PowerShell7，无需安装项目依赖即可运行：

```powershell
pwsh -NoProfile -File scripts/verify.ps1 -SelfTest
pwsh -NoProfile -File scripts/doctor.ps1
```

verify退出0仅代表工程静态检查通过，退出1表示失败；SelfTest在受控临时目录跑正反例并清理。有限机密模式扫描不是完整安全审计。doctor只读，退出0为必要工具版本满足、2为环境BLOCKED、1为异常，不安装或启动资源。CI使用同一个verify入口；远程CI在实际运行前保持NOT_RUN。

工具目标：SDK10.0.402、Node24.22.1、pnpm11.28.8，详见[工具登记](docs/evidence/G1-ENG-001/dependencies.md)。本机不满足时保持目标并报告，不升级OS/用户全局工具。无真实包依赖所以不创建空锁文件，Turbo配置待实际前端任务落地后接入。

## 工程边界

前端`apps/web`、`@ontology-platform/web`；后端入口`backend/OntologyPlatform.slnx`。ServiceDefaults仅宿主默认设置，BuildingBlocks仅必要技术合同，运行时MAF与研发Agent分开。没有业务源码时原生lint/typecheck/build/test/format均NOT_RUN。

[研发约定](AGENTS.md) · [计划与交接](PLANS.md) · [G0审查记录](docs/planning/10-g0-review-record.md) · [目录ADR](docs/adr/ADR-001-design-system-location.md)

任务完成后停止；任何其他G1任务或G2必须另行明确授权。
