# G4-M2-WEB-01｜一页实施清单与唯一状态

状态：**VERIFIED_PENDING_PACKAGE / 产品真实验收完成，按影响工程门禁及最终包复核进行中**。
授权：2026-11-07 用户明确批准附件单 Web HTTPS GET；[附件](../evidence/G4-M2-WEB-01/authorization.md)。
Base：`b3b68500d76ab5965fcc540afb883ca605cb15dd`，真实 fetch 一致；分支 `codex/g4-m2-web-01`。
Worktree：`/Users/chasen/.codex/worktrees/g4-m2-web-01/ontology-platform`；Master 单写，p0_review 非作者只读。

## 清单

- [x] P0：核实基线/独立树、DTO/SPI/16路由、宿主资源、既有环境入口、官方 .NET HTTP API；详情见[P0](../evidence/G4-M2-WEB-01/p0.md)。
- [x] P0闭合：Web认证合同裁决；离线Web缓存来源核验与两次幂等prepare；TaskId消费者准入；TLS/socket平台见证。
- [x] 公共分发：准确文件冻结后编写PG/Web正反合同测试→非作者Review→最小typed dispatcher；PG不变，其他三类型继续拒绝。
- [x] Web：可信精确operation/HostPolicy注册→DNS全地址与socket绑定→正常TLS→固定GET/认证→有界目录/取消/生命周期。
- [ ] 验收：先真实OIDC/API/HTTPS/UI烟测；再workflow plan/verify按影响执行安全负例、权限/SecretRef、PG回归、取消见证及浏览器闭环。
- [ ] 产品交付：独立Review→提交/输入绑定→唯一V3→独立重开→回执；不更新main。

## 所有权与依赖

当前实际 owned_paths：本任务卡、`docs/tasks/current-authorization.md`追加段、`docs/evidence/G4-M2-WEB-01/**`。产品准确文件清单以下方恢复阶段冻结清单为准。
只读依赖：Contracts/G4ConnectionModels.cs（Rules仅下方精确授权变更）；Connections 的 Abstractions/Application/Persistence/Adapters；Api/G4；现有Web Connections；workflow*、门禁登记、冻结架构和当前工程政策。
后续准确产品owned_paths必须在合同裁决后冻结于本卡；共享配置由Master单写。无新增依赖/下载/费用、无新DB语义/公开wire/权限；Oracle/Doris/TDengine及M3/G6不在范围。

## 恢复与停止

[P0增量已获批准](../evidence/G4-M2-WEB-01/p0-decision-approval.md)，先环境及消费者准入再产品实现；普通修复无需逐补丁审批。现有prepare失败不重复整链。保留当前离线缓存和原始运行日志，任务未关闭；不清旧任务资源。
历史P0阻断见证保持不变；当前真实产品验收已完成；历史失败原件保留，最终产品 ZIP 待门禁与独立重开后另行形成。

## 恢复阶段冻结路径（Master单写）

环境：scripts/maintenance/workflow_environment.py、scripts/maintenance/workflow_web_cache.py、scripts/maintenance/workflow_m2_web.py、scripts/maintenance/workflow.py；scripts/tests/WorkflowEnvironment.Tests.py、scripts/tests/WorkflowM2Web.Tests.py；docs/development/verification-gates.json。先完成此阶段；产品准确文件清单在分发合同Review前追加。只读缓存候选限同仓库现存g4-eng-workflow-001与g4-eng-workflow-env；全内容/锁/shim验证后复制本任务，禁止旧runtime/凭证复制。

## 产品阶段准确owned_paths（Master单写，合同测试先审）

- Contracts：仅 `backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionRules.cs` 的Purpose值域。
- Connections模块下 `Abstractions/IWebSourceAdapter.cs`、`Abstractions/WebOperationPolicy.cs`、`Application/ConnectionSourceDispatcher.cs`、`Application/ConnectionApplicationService.cs` 及现有 `.Commands.cs`、`.Probes.cs`、`.Enable.cs`、`.Catalog.cs`、`.Worker.cs`；`Adapters/WebSourceAdapter.cs`、`Adapters/WebJsonCatalog.cs`。
- `backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs`；ConnectionsTests下 `SourceDispatcherTests.cs`、`WebAdapterTests.cs`；G2ContractTests下现有 `G4WireContractTests.cs`。
- UI仅 `apps/web/src/features/connections/{create,detail}.tsx`、`form-model.ts`、`connections.test.ts`；`apps/web/AGENTS.md`只读。
- 任务consumer/fixture：`scripts/maintenance/workflow_m2_web.py`、`workflow_m2_fixture.py`、`workflow_m2_smoke.py`、`workflow_m2_build.py`、`workflow_m2_evidence.py`、`workflow-m2-web.mjs`、`workflow_smoke.py`的明确任务扩展；`experiments/g4-m2-web-01/`任务HTTPS fixture和测试驱动。所有历史M1/G4-ENG证据、其他Contracts、Persistence/迁移/锁/权限继续只读。

分发方案：保留IPgSourceAdapter及原PG实现，新typed IWebSourceAdapter由最小dispatcher分派；服务器固定唯一Web operation/组织厂区/目标。凭据用途由类型化配置确定，所有绑定/读取/重放路径核验；已有Web连接禁止切换目标或类型，需新建并新签发凭据。无公开字段或数据库变更。
