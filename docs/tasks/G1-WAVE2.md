# G1-WAVE2 · Mac SEC/FE/OBS并行总任务

状态：EXECUTING / PARTIAL。日期2026-10-25。BaseSha=e930935749bcb88d51abb94db4a41695bbbe6717。人类正式批准附件V2全部Wave2范围，原文见[授权](../evidence/G1-WAVE2/authorization-v2.md)，不进入G2。当前新授权覆盖历史任务停止条款，不篡改M0/G1历史。

## 冻结分工

| Owner | 分支 / 独立托管树 | owned_paths | read_only_dependencies |
|---|---|---|---|
| Master/Integrator | codex/G1-WAVE2-master；/Users/chasen/.codex/worktrees/g1-wave2-master/ontology-platform | 公共合同/API Contracts、所有锁、根版本/solution/CI、AppHost/ServiceDefaults共享配置、全部迁移、scripts/acceptance/**、根工程规则/文档/授权/总证据 | 专项源码合入前只读 |
| SEC platform_worker | codex/G1-SEC-001；/Users/chasen/.codex/worktrees/g1-wave2-sec/ontology-platform | backend/src/Hosts/OntologyPlatform.Api/**（除Contracts）、backend/src/Modules/Governance/**（除Migrations）、backend/tests/OntologyPlatform.SecurityTests/**、infra/security/**、docs/evidence/G1-WAVE2/SEC/**、docs/development/security.md | 合同/DTO/根CPM/锁/迁移/solution/CI/AppHost只提议Master |
| FE platform_worker | codex/G1-FE-001；/Users/chasen/.codex/worktrees/g1-wave2-fe/ontology-platform | apps/web/**（Design Tokens唯一Owner FE）、docs/evidence/G1-WAVE2/FE/**、docs/development/web.md | 合同/OpenAPI/根版本/根pnpm-lock/CI只读 |
| OBS platform_worker | codex/G1-OBS-001；/Users/chasen/.codex/worktrees/g1-wave2-obs/ontology-platform | infra/observability/**、docs/evidence/G1-WAVE2/OBS/**、docs/development/observability.md | 合同/API/ServiceDefaults/AppHost/根CI/锁只提议Master |
| quality_reviewer | 只读共享；不负责实现 | 无源码写入 | 固定提交、实际命令/原始脱敏证据和最终ZIP |

最多三专项并行，达到审查点滚动释放Reviewer槽位。单写者同时成立，独立目录不嵌套；M0树只保留历史，不作本轮写入树。源路径按此冻结，其他人在工作，不回退他人修改。每次命令显式workdir；写权限被沙箱拒绝走正常审批，保持小命令，等待时报告具体session，不能静默以计划代替执行。

## DAG及里程碑

1. fetch/main/全树/doctor门禁、依赖官方来源/许可登记，更新授权；Master冻结最小契约并独立Review。
2. SEC/FE/OBS从已审合同提交并行。Master唯一处理公共根版本/锁/DTO/迁移/AppHost接线。FE解析锁先输出忽略.tools/fe-lock，Master生成正式根锁；SEC直接项目restore可关闭生成锁，正式锁Master产生。
3. 各专项真实可验证里程碑commit/push，PARTIAL/DRAFT明确；独立只读Review，修复交回Owner，不抢写。通过独立Review+适用契约/集成测试+同Head Linux CI后分批进入main并push。
4. 正式API+Next+专用KeycloakRealm/PG会话/审计/共享证书keyring+LGTM9资源，真实纵向验收与负例、双实例、重启；原4测试保留。
5. 更新合同/ADR/运行手册、完整原始脱敏证据/截图/CI/风险矩阵，独立总审查，一个标准Review ZIP并重开，停止输出G1_WAVE2_READY_FOR_REVIEW。

## 禁止与门禁

只Wave2，不做本体发布/MCP/MAF/G2/生产连接器，不调用付费模型或修改GitHub保护规则，不改全局工具/管理员/机器PATH。必要批准技术栈依赖先登记官方精确版本/许可/用途；非内置同等替代选型按合同Review；不擅自引入额外第三方框架。只本地隔离开发资源/随机身份，不读取旧凭证/卷或改已有Keycloak。密钥/密码/Cookie/token不提交、不记录、截图和Playwright输出脱敏，不打包node_modules/.tools/bin/obj/卷。

验收命令：doctor -CheckDocker、verify -SelfTest -RunNative -RunTests、受锁restore/format、真实Web lint/typecheck/test/build/Playwright、PG审计查询、双实例OIDC/CSRF/重放/转发头负例、Alloy→Loki/Tempo/Prometheus原始查询、Grafana截图/告警触发恢复/重启。每项命令/退出码/版本/测试数写证据，缺前提BLOCKED/未执行NOT_RUN，核心流程不通过总PARTIAL/BLOCKED；单纯Running或旧CI不能PASS。
