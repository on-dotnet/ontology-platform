# G1-CLOSE-001 收口执行计划

> 实施采用已获人类授权的独立Worktree SEC/OBS并行与只读独立Review；本卡兼执行计划与恢复账本，不另要求执行方式确认。

**Goal:** 审计查询先提交真实范围审计再返回，故障按安全类别诊断；阶段事实可复检。
**Architecture:** 保持Governance专属PG/原生ILogger+Activity；审计同表结构化text[]，异常仅固定分类；无新依赖或业务模块。
**Tech Stack:** 当前锁定.NET10/EF/Npgsql、Next/Base UI、OTel/LGTM，不改选型。
**Spec:** [明确授权V1](../evidence/G1-CLOSE-001/authorization-v1.md)。
**BaseSha:** d181f66e569e190a66b0f48b179f2fd9390b9467。

## Global Constraints

只G1-CLOSE-001，不进入G2，不修改生产/系统权限/全局工具/收费服务/GitHub保护设置。C#全部手写成员中文XML、局部变量中文用途注释；不记录秘密/原始异常/SQL/PII。main唯一集成人Master；其他人在工作，不回退他人改动。所有证据区分PASS/FAIL/BLOCKED/NOT_RUN/NOT_VERIFIED；历史不追改。

## 冻结所有权

| Owner | 分支/独立托管Worktree | owned_paths | read_only_dependencies |
|---|---|---|---|
| Master | codex/G1-CLOSE-001-master; /Users/chasen/.codex/worktrees/g1-close-master/ontology-platform | 公共Contracts/OpenAPI/生成TS、apps/web/tests/{ui,oidc}仅截图证据路径、PlatformProblem.cs运行错误工厂、Governance AuditRecord/DbContext/Migrations、既有HttpSecurityTests合同断言、新AuditScopeMigrationTests、scripts/acceptance/**、CI、docs总卡/授权/阶段/证据 | 专项源码只审查集成 |
| SEC | codex/G1-CLOSE-SEC; /Users/chasen/.codex/worktrees/g1-close-sec/ontology-platform | PlatformEndpoints.cs、Security/AuditService.cs、新AuditReadTests.cs及专属helper、docs/evidence/G1-CLOSE-001/SEC/** | Host/Telemetry/公共DTO/模块模型/迁移/锁/CI只读 |
| OBS | codex/G1-CLOSE-OBS; /Users/chasen/.codex/worktrees/g1-close-obs/ontology-platform | PlatformApiHost.cs、PlatformTelemetry.cs、新PlatformFailure*.cs、新ObservabilityFailureTests.cs及专属helper、infra/observability/alloy/config.alloy、docs/evidence/G1-CLOSE-001/OBS/** | Endpoints/AuditService/现有测试/ServiceDefaults/公共合同/迁移/锁/CI只读 |
| Independent Reviewer | 只读固定提交/差异/实际证据 | 无 | 全部范围 |

## 冻结接口与安全语义

### 审计

- AuditRecord与PlatformAuditEntry增加nullable `ScopeSiteIds` / JSON `scopeSiteIds` (`string[]?`, PG text[])。null仅历史未知；[]明确无厂；新事件数组取可信claims或已授权显式厂区，非空字符串、Distinct、Ordinal排序。兼容SiteId仅单厂填值，多厂/无厂null。
- API查询必须非空组织相等、数组非空且所有元素都在当前可信sites；legacy null和[]不在普通API暴露。旧SiteId不可推断/回填真实范围，原事实保留。审计员缺组织/厂区返回空且依然记录敏感读取。
- 鉴权/limit校验→SQL过滤排序Take物化→唯一 `platform.audit.read/platform.audit/allowed` SaveChanges→X-Audit-Id→200。SELECT snapshot不含本请求事件，后续可见；并发可能看到先提交的别次事件，不声称全局串行快照/递归查询。
- INSERT失败不得200/成功AuditId。拒绝仍403+denied，会话无效401，原资源行级检查保留。
- nullable迁移不篡改历史。Down只允许没有新结构化范围事实时；否则明确拒绝防丢审计。迁移/恢复由Master实测。

### 诊断

- `LoggerMessage` EventId=1003、EventName=`PlatformRequestFault`；仅 `Route/ExceptionCategory/Outcome/Status/TraceId`，不接受Exception，不原文类型名/Message/ToString/连接串/用户值。
- 类别固定：request_cancelled/invalid_request/database_connection/database_write/database_failure/upstream_unavailable/unexpected_failure；结果problem_returned/request_cancelled/response_aborted。
- RequestAborted的OCE不写Problem，响应已开始不追加JSON/不伪改状态，Abort且不再向框架抛原异常。错误响应写出若再次失败也受控Abort。成功/失败完成日志有明确结果。
- BadHttpRequestException固定输入400；DbUpdate/Npgsql/明确HttpRequest依赖故障503；普通异常及非请求取消OCE500 internal_error。Argument/Format/UnauthorizedAccess不武断当客户端错。现有OIDC400/401/CSRF与权限403/404由原管道保留。
- 源头不发原异常，Activity只fixed category/outcome/status；不得添加原始exception事件；Alloy删除status.description和event异常属性，保留准确大小写字段、三个Loki索引和原低基数指标。健康Probe依原设计不要求Tempo业务Span。
- Master添加500公共标题/错误码/文档，SEC按此给实际路由追加500文档；原现有状态不能去掉。故障注入仅测试注册/真实依赖，不加产品测试路由。

## Review Focus

1. A权限不可见AB事件，旧首厂误归不能继续泄漏；org缺失/[]不能vacuous truth。
2. SELECT成功但INSERT失败仍失败关闭；不靠停库混淆认证失败。
3. 并发每请求唯一写事件、响应不含自身；清理只触及本测试主体。
4. RequestAborted/HasStarted/错误写回再失败不逃逸框架原文；观察state/scopes/exception而非只body。
5. 真正Loki与Tempo同Trace无marker；Alloy字段大小写/低基数不得只静态宣称。

## DAG与任务

- [x] 0: 完读授权、fetch确认Base、全树状态和工具诊断；原checkout六个.DS_Store保留，各历史树干净，未清理。新建三个独立托管树/任务分支。
- [x] 1a: 冻结契约8fdf242经独立Reviewer通过（0 P0/P1，一项路径P3已补全）；
- [x] 1b: 模块模型/DTO/迁移、受锁restore/build及真实PG迁移拒绝丢失/前向恢复验证。
- [x] 2: SEC写真实PG红例，再修复成功审计/数组权限/一次事件，含允许拒绝/过期/空/跨厂/多厂/失败写入/Trace/并发与脱敏；commit/push DRAFT。
- [x] 3a: OBS写真实Kestrel红例，再改固定分类/取消/已开始/脱敏，官方Alloy语法和实际导出测试；commit/push DRAFT。
- [ ] 4: 固定提交独立Review两线、Owner修复；Master集成，全部后端/format/SelfTest/Web/浏览器/OIDC/OpenAPI/真实LGTM正反回归。
- [ ] 5: G1退出标准/14模块/未完项分期/只读G2接口样例DAG/生产拓扑ADR与只读保护规则评估，保留历史状态。
- [ ] 6: 通过独立最终Review+任务分支同HeadCI后Master集成main/push；最终main同HeadCI；标准唯一ZIP+独立VerifyOnly/逐成员回验，输出G1_CLOSE_READY_FOR_REVIEW停止。

验收入口沿用doctor、verify -SelfTest、Release restore/build/format、全部Infra/Security test-governance、verify-web -Restore、UI5/OIDC2、verify-openapi、五身份协议、proxy/PGfault/persistence、真实LGTM查询；增加本次故障/迁移测试。每次记录命令/退出码/计数，环境缺失明确标识。

## 恢复账本

2026-10-25：本轮Base与origin/main一致，独立调查确认两根因；历史只读，六个.DS_Store用户现场保留。环境doctor观察pnpm11.28.8（不同于前次观察12，不执行全局修改）、Docker29.9.2。实现未开始，契约待独立Review。

2026-10-25：新增结构化范围迁移1cbfcf3、真实PG migration红绿证据；新运行时wave2-a19529d4edb4专用卷/Realm仅忽略私有目录，core引导后受控停止。SelfTest首次缺PyYAML/console CR明确FAIL，原锁哈希隔离恢复与展示空白规范化后完整PASS35构包负例；未更改检查器。当前main仍Base。

集成账本：SEC 5d92109经独立0/0/0审查在357345f合入Master；OBS240929c经0Critical/0Important/2Minor审查在Master合入，737c38d两个证据Minor限定复审已闭环，待同步。集成Release安全45/45无跳过、实际OpenAPI PASS。真正LGTM验收先9项事实/失败关闭/恢复PASS，但EventId/EventName出口缺失FAIL（trace22e6a80c6fc2a7c67630be18a37612e2）；已交OBS调查修复，不放宽断言。main仍Base，完整LGTM/CI/最终审查未完成。
