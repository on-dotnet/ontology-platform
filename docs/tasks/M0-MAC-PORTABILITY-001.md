# M0-MAC-PORTABILITY-001 · Mac Master 接管与兼容验收

状态：READY_FOR_REVIEW / PARTIAL（Mac最低工程验收及独立审查通过，其他平台覆盖边界保留；最终CI/ZIP以manifest为准）。日期：2026-10-25（Asia/Shanghai）。BaseSha：25eab6f5bfd944dc44c8c77b1a3cbd22ec9468e1。

## 授权与停止

人类在本会话明确批准 M0，采用 Master、多 Agent、独立托管 Worktree、任务分支及独立审查后集成。依据 Downloads 中 OntologyPlatform-Mac-CodexMaster-Handoff-and-Portability-V1.md 第二节至文末，已完整读取。只做跨平台工程兼容与开发基础设施验收；SEC/FE/OBS/G2 不授权。历史 G1-INFRA 事实不改写。系统安装、管理员操作、收费服务和不明凭证停止对应项。

## 冻结任务合同

| 项 | Owner / Reviewer | 分支 / Worktree | owned_paths | read_only_dependencies |
|---|---|---|---|---|
| Master | Master / quality_reviewer | codex/M0-master；/Users/chasen/.codex/worktrees/m0-master/ontology-platform | 根配置、全部锁文件、CI、AppHost、scripts/verification-requirements.txt、README、当前授权、本任务、docs/development/macos-setup.md、docs/handoffs/**、docs/evidence/M0-MAC-PORTABILITY-001/master/**、总证据 | 专项源码只读至集成 |
| A 脚本 | platform_worker / quality_reviewer | codex/M0-scripts；/Users/chasen/.codex/worktrees/m0-scripts/ontology-platform | scripts/doctor.ps1、scripts/verify.ps1、scripts/create-review-package.ps1、scripts/tests/**、docs/evidence/M0-MAC-PORTABILITY-001/A/** | requirements/CI/锁/合同只提议 Master |
| B 容器 | platform_worker / quality_reviewer | codex/M0-containers；/Users/chasen/.codex/worktrees/m0-containers/ontology-platform | infra/development/**、docs/development/local-infrastructure.md、docs/evidence/M0-MAC-PORTABILITY-001/B/** | AppHost/锁/根配置由 Master 唯一写入 |
| 独立审查 | quality_reviewer | 只读共享或隔离树 | 无 | 全部已提交差异、真实证据及最终 ZIP |

Agent 不是唯一写者，Master 是 main 唯一集成者。其他人同时工作，不回退他人修改；跨路径需求报 Master。每项有效里程碑 commit/push（未验收标 PARTIAL），未经独立审查和真实 Mac 验收以及 Linux CI 不退化不得进入 main。未集成树保留。

## DAG 与计划

1. 读取合同/架构/历史与 Git fetch，核对基线，发现并派发只读自定义角色。
2. 本任务卡和授权增量提交；A/B 独立 Worktree 并行调查，Master 官方来源核实并恢复 pnpm/PyYAML/真实 osx-arm64 NuGet 锁。
3. A 修复 doctor/脚本平台假设并运行正反例；B 检查锁定镜像原生平台，运行 AppHost、探针、网络、重启持久化与基本 Trace。B 启动依赖 Master 可用构建和锁图。
4. 独立 Reviewer 审查各分支，Owner 修复；Master 集成任务分支并执行完整 verify/真实 build/test/format。
5. 更新 Mac/Windows/Linux 矩阵、交接和证据；读取实际 Linux CI；只有满足门禁才合并 main/push，否则保留 PARTIAL/BLOCKED。
6. 完整已提交 Base/Head 构建唯一标准 ZIP，独立重开校验路径/文件/散列/diff 后停止。

## 最低验收矩阵（开工时均 NOT_RUN）

| 项 | Mac 当前运行 | Windows | Linux |
|---|---|---|---|
| 精确工具、doctor/Docker | NOT_RUN | 历史 G1 证据，M0 NOT_RUN | CI 按实际 run |
| 脚本静态、正反例、Review ZIP | NOT_RUN | M0 NOT_RUN | CI 按实际 run |
| locked restore/build/MSTest/format | NOT_RUN | 保留 win-x64 锁，M0 NOT_RUN | 保留 linux-x64 锁，CI 按实际 run |
| 四资源原生平台/健康/持久化 | NOT_RUN | 历史 G1 证据，M0 NOT_RUN | M0 NOT_RUN |
| Aspire/Dashboard/Trace 查询 | NOT_RUN | M0 NOT_RUN | M0 NOT_RUN |

记录命令、退出码、真实版本/架构/测试数、提交及 CI run ID/URL/head/conclusion。缺条件 BLOCKED；未做 NOT_RUN；静态配置不替代运行。负例必须运行。验收入口为 pwsh -NoProfile -File scripts/verify.ps1 -SelfTest、受锁 restore、-RunNative -RunTests、Docker manifest 与实际资源探针/重启脚本，以及 create-review-package -VerifyOnly。

## 修复阶段写权调整（2026-10-25）

组合入口实际失败后，A已定位null恢复为空字符串；为完成当前关口，Master暂停A worker的后续写入，收回A脚本修复写权，在同一独立m0-scripts树/codex/M0-scripts分支串行完成最小环境恢复修复和回归。A原里程碑仍由worker独立提交。Reviewer保持只读并复核修复固定头。没有并发抢写，不改变其他owned_paths。

B已完成真实容器/持久化/Trace验收，两个AppHost会话exit0。后续归档工具等待审批随会话中断，未取得结果。Master暂停B所有工具/写入并接收完整只读回报，收回B树最终证据/手册写权，在原独立m0-containers分支串行归档并核实收尾状态；报告明确区分B实测与Master归档/复核，不伪称B已commit或未执行命令PASS。Reviewer仍独立审查固定B提交。

独立B审查指出Owner转录不足以独立解除运行门禁。Master在master证据owned_paths内使用新增唯一开发卷前缀重跑原AppHost/持久化脚本，直接归档脱敏原始进程输出、实际HTTP JSON、退出码及资源快照；不改AppHost/infra实现、不读取凭证、不删除已有卷。B转录保留其来源，Reviewer据新固定头复核。

## 收尾门禁

A两固定里程碑、Master锁/完整组合入口、B来源文案及Master直接原始运行证据均已独立审查，无剩余Critical/Important/Minor。最终任务集成头先读取实际Linux CI成功，再由Master快进main并push；构包显式绑定同Head main CI实际run。Windows本轮NOT_RUN、未授权产品能力NOT_RUN；不将整体覆盖标为PASS。仅交付唯一标准ZIP并独立重开，随后停止等待人类复审。
