# 本任务路径所有权

Master唯一写者；此清单冻结批准申请第6节可确定的源码路径，不扩大业务/依赖边界。需要新增不同路径时先核对是否属于已批准必要消费者修复；越界不自动扩大。其余源码与历史证据只读。

- `Directory.Packages.props`（现有）
- `apps/web/src/features/connections/connections.test.ts`（现有）
- `apps/web/src/features/connections/create.tsx`（现有）
- `apps/web/src/features/connections/detail.tsx`（现有）
- `apps/web/src/features/connections/form-model.ts`（现有）
- `apps/web/src/features/connections/form.tsx`（现有）
- `apps/web/vitest.config.ts`（现有）
- `backend/src/AppHost/packages.linux-x64.lock.json`（现有）
- `backend/src/AppHost/packages.osx-arm64.lock.json`（现有）
- `backend/src/AppHost/packages.win-x64.lock.json`（现有）
- `backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionModels.cs`（现有）
- `backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionRules.cs`（现有）
- `backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs`（现有）
- `backend/src/Hosts/OntologyPlatform.Api/packages.lock.json`（现有）
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Abstractions/DorisAdapterOptions.cs`（拟新增）
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Abstractions/IDorisSourceAdapter.cs`（拟新增）
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/DorisSourceAdapter.cs`（拟新增）
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Catalog.cs`（现有）
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Commands.cs`（现有）
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Enable.cs`（现有）
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Probes.cs`（现有）
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Worker.cs`（现有）
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.cs`（现有）
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionSourceDispatcher.cs`（现有）
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/OntologyPlatform.Modules.Connections.csproj`（现有）
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/packages.lock.json`（现有）
- `backend/tests/OntologyPlatform.AgentTests/packages.lock.json`（现有）
- `backend/tests/OntologyPlatform.ConnectionsTests/DorisAdapterTests.cs`（拟新增）
- `backend/tests/OntologyPlatform.ConnectionsTests/DorisFixtureSecurityTests.cs`（拟新增）
- `backend/tests/OntologyPlatform.ConnectionsTests/SourceDispatcherTests.cs`（现有）
- `backend/tests/OntologyPlatform.ConnectionsTests/packages.lock.json`（现有）
- `backend/tests/OntologyPlatform.G2ContractTests/G4WireContractTests.cs`（现有）
- `backend/tests/OntologyPlatform.QueryTests/packages.lock.json`（现有）
- `backend/tests/OntologyPlatform.SecurityTests/packages.lock.json`（现有）
- `docs/deployment/doris.md`（拟新增）
- `docs/development/verification-gates.json`（现有）
- `infra/doris/.env.example`（拟新增）
- `infra/doris/compose.production.yaml`（拟新增）
- `infra/doris/compose.test.yaml`（拟新增）
- `infra/doris/compose.yaml`（拟新增）
- `infra/doris/config/be.conf.example`（拟新增）
- `infra/doris/config/fe.conf.example`（拟新增）
- `scripts/maintenance/execution_preflight.py`（现有）
- `scripts/maintenance/workflow.py`（现有）
- `scripts/maintenance/workflow_doris_fixture.py`（拟新增）
- `scripts/maintenance/workflow_environment.py`（现有）
- `scripts/maintenance/workflow_m2_doris.py`（拟新增）

本任务证据与任务卡依当前授权归Master；非作者Reviewer仅只读。共享workflow_execution/workflow_evidence复用不复制，未经必要性审查不改；host_continuity CLI缺TaskId先使用原模块inspect(task_id=本任务)，不冒用旧TaskId。新增测试仅覆盖本任务变化，历史完整链不重复。

必要消费者路径补充（同一已批准TaskId准入范围）：`scripts/maintenance/workflow_web_cache.py` 与 `scripts/tests/WorkflowM2Web.Tests.py`，仅Doris缓存TaskId白名单及对应拒绝测试；不新增缓存源或下载能力。

必要消费者路径补充（已授权Doris真实门禁接入）：`scripts/maintenance/workflow_m2_build.py`仅登记Doris执行输入与TaskId；`scripts/tests/WorkflowDoris.Tests.py`仅新准入、任务边界和依赖闭包回归。不扩大其它产品门禁或生产限制。

完整生命周期配套草案：`infra/doris/compose.platform.yaml`承载已批准4容器预算内的PG/OIDC精确配置；普通bridge及PG loopback差异待单独明确授权，当前仅静态渲染，不启动。

真实生命周期测试必要消费者：`scripts/maintenance/workflow-doris.mjs`仅Doris真实OIDC/API/UI断言，复用公共执行器和既有Playwright，无新增依赖。

`scripts/maintenance/doris-fixture-control.cs.txt`为同一生命周期夹具的固定SQL源模板；仅临时授权变化、旁路观察和空合成表元数据恢复，不进入产品、不执行文件提供的SQL。

必要兼容/证据消费者补充：`scripts/maintenance/workflow_m2_fixture.py`与`workflow_smoke.py`仅允许本任务复用已有PG/Web短夹具，冻结已批准镜像、隔离/清理与预算；不授权旧产品完整烟测或relay。`scripts/maintenance/workflow_m2_evidence.py`复用原始解析/资格框架，增加Doris准确审计关联与门禁资格。

严格TLS明确批准后的必要实现：`backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/DorisCertificatePolicy.cs`，仅本任务私有CA实际握手验证。
