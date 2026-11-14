# G4-M4-QUERY-001｜规格驱动任务

## 当前执行与授权

- 唯一状态：**P0_DESIGN_READY_FOR_REVIEW**。本轮是P0文档准入，不是产品实施授权；最终停一次性规格与实施裁决关口。
- 会话：本M4会话，后续同会话继续；Code/Agent，Local Mac ARM64。实际模型/推理设置未读取，不采用附件建议冒充实际设置。
- Base：`f0afb730ce92ecbd3a5947d9c6f58faedc8b2138`，2026-11-14普通fetch后origin/main一致；初次fetch沙箱拒绝写FETCH_HEAD，获工具批准重试exit0；没有基线漂移。
- 分支：`codex/g4-m4-query-001`；Worktree：`/Users/chasen/.codex/worktrees/g4-m4-query-001/ontology-platform`。RunId=`p0-contract-20261114`，托管operationId=`ddb793db-9e28-4040-977d-73af96443916`。首次分支创建因.git锁写权限失败，获工具批准后成功；未回退main写文档。
- Owner：Master单作者；Reviewer：一位非作者只读审查，`/root/m4_p0_review`，结论见Verify；无产品Worker。
- 当前授权：本轮用户明确批准附件P0及文档提交/push；[授权追加](current-authorization.md)。P0不默认ZIP；后续产品实施完成默认最终唯一ZIP、包外回执及非作者独立重开，不再申请打包。
- owned_paths仅本任务卡、[唯一A–F](../evidence/G4-M4-QUERY-001/contract-admission-request.md)及current-authorization.md追加；合同修订P0.1。read_only_dependencies为A–F A1固定Base源码/历史合同、SDD模板与现行规则。
- 非目标：产品/DTO/DB/脚本修改、prepare/restore/build/test、下载/安装、服务启停、M3重跑、KEEP清理/移交、main、TDengine、M5。原树六个未跟踪.DS_Store受保护。

## Specify：可观察要求

以下场景均为后续实施规格，不是当前运行证据。路径别名Q/C/N/G/H/A精确展开见唯一A–F F1，测试目录为`backend/tests/`；不另复制规格。

| AC-ID | 行为/不变量 | Given/When/Then正例和关键反例 | 实现/测试位置 | 最早验证层/依赖 | 结果/原件 |
|---|---|---|---|---|---|
| AC-01 | RQ-02判别与精确值，见B | 给定P1–P3；读出并PG往返→decimal/Int64/微秒逐字一致；N1–N6/N10/N12拒绝，不补猜 | C/G4QueryModels.cs、G4QueryRules.cs；OntologyPlatform.G2ContractTests/G4QueryWireTests.cs；OntologyPlatform.QueryTests/G4QueryPersistenceTests.cs | S1正式序列化+真实PG新DbContext；无float中转 | NOT_RUN；原件待S1当前Run |
| AC-02 | 唯一Gateway真实PG链，见A | 给定正式本体和active；HTTP query→实际源值/receipt；只有M3评估可用或未知capability→拒绝 | Q/SemanticGateway.cs、N/Adapters/PgQueryReader.cs；OntologyPlatform.QueryTests/G4QueryHttpTests.cs | S1正式DI/OIDC/TLS只读PG | NOT_RUN |
| AC-03 | 六态区别，见C1 | 完整零行→EMPTY，有行→FOUND；断源/超时零行→UNAVAILABLE；截断有可信前缀→PARTIAL；可见snapshot全分支拒绝→UNAUTHORIZED；两可见候选→AMBIGUOUS | Q/G4QueryExecution.cs；OntologyPlatform.QueryTests/G4QueryTests.cs；OntologyPlatform.ConnectionsTests/G4QuerySourceTests.cs | S1 FOUND；S2其他状态及真实故障 | NOT_RUN；S-50跨源不在范围 |
| AC-04 | 当前授权/迟到响应，见C/D | 有grant执行与恢复成功；撤权/注销/连接禁用/secret轮换→无成功披露，UI清屏且迟到响应失效；根无权401/403无snapshot；外部IdP直接禁用即时传播按D待裁决限制，不冒充已覆盖 | G/QueryAuthorizationParticipant.cs、H/G4/QueryEndpoints.cs；OntologyPlatform.SecurityTests/G4QueryAuthorizationTests.cs；apps/web/src/features/semantic/g4-query.test.ts | S2真实票据/PG grant+浏览器 | NOT_RUN |
| AC-05 | 固定发布与ABA，见C2 | active固定执行成功；A→B→A发生于运行中→409无成功结果；已提交历史A在当前有权时仍回读A | N/Application/QueryBindingReader.cs、Q/G4QueryResultStore.cs；OntologyPlatform.QueryTests/G4QueryRaceTests.cs | S2两API独立连接/真实激活 | NOT_RUN |
| AC-06 | RQ-01消歧，见C1 | 同scope两候选→选择合法IRI成功；撤权/版本漂移/未知IRI→403/409/422且无候选泄露，不取第一条 | Q/G4QueryExecution.cs；OntologyPlatform.QueryTests/G4QueryTests.cs；apps/web/src/features/semantic/g4-query.test.ts | S2源真实同号及权限变化 | NOT_RUN |
| AC-07 | 来源闭合与精度，见C2 | 行→evidence→receipt→原发布/原目录/当前目录/连接版本可核；无源键→DATASET/PARTIAL；悬空ID→503，UNKNOWN不当确定事实 | Q/G4SourceEvidenceService.cs、N/Adapters/PgQueryReader.cs；OntologyPlatform.QueryTests/G4QueryPersistenceTests.cs | S1首receipt即验证；S2降级反例 | NOT_RUN |
| AC-08 | 结果恢复与保留，见C3/C4 | 新DI回读hash一致、刷新不增加源read计数；24h到期410、错主体404、历史撤权403；不自动重执行 | Q/G4QueryResultStore.cs、G4QueryWorker.cs；OntologyPlatform.QueryTests/G4QueryPersistenceTests.cs；UI g4-query.test.ts | S1存储→新上下文→浏览器；S2可控时钟过期 | NOT_RUN |
| AC-09 | 预算/取消/原子审计，见D | 两实例租约容量/fence生效；取消先提交或审计故障→无COMPLETED；大值物化前拒绝；SQL/URL不能进入计划 | Q/G4QueryWorker.cs、N/Adapters/PgQueryReader.cs；OntologyPlatform.QueryTests/G4QueryRaceTests.cs；OntologyPlatform.ConnectionsTests/G4QuerySourceTests.cs | S2真实PG事务/两API | NOT_RUN |
| AC-10 | 关系/观测及共同UI/MCP，见A/B/E | 发布关系两端有权、精确观测按同Gateway返回；无权端点/未开放ontology拒绝；MCP不用LLM | A/SemanticMcpTools.cs、Q/G4QueryExecution.cs；OntologyPlatform.AgentTests/G4QueryMcpTests.cs；UI g4-query.test.ts | S3真实受控MCP/浏览器/源PG | NOT_RUN |
| AC-11 | G2冻结兼容，见B1 | 旧查询和旧Run按原DTO读取；当前撤权拒绝；G4不转换假图 | A/ExecutionRunService.cs；OntologyPlatform.QueryTests/QueryHttpTests.cs；OntologyPlatform.AgentTests/RunFlowTests.cs；OntologyPlatform.G2ContractTests/WireContractTests.cs | S3影响范围内真实回归，其他证据按输入复用 | NOT_RUN |
| AC-12 | 当前任务准入/证据/资源，见E/F | 当前TaskId正式消费者有效才执行；未知Task/空流/ANSI/禁入路径/错误报告不得PASS；总占用未知即不启栈 | scripts/maintenance/workflow_m4_query.py；scripts/tests/WorkflowQuery.Tests.py；verification-gates.json | 实施准入及S1第一原件→公开资格→小样预检 | NOT_RUN；当前适配器缺失BLOCKED |

## Plan：最早真实风险路径

最高风险为当前授权与固定映射身份跨外源读取/平台持久化的竞态，以及精确值经PG回读、生成TS后失真。S1先跨层形成最短可恢复查询，再扩能力。正式DI/provider/DbContext工厂/迁移/序列化/OIDC均复用，只换合成端点和新合成凭据；不拿mock代真实成功。

首证据命令、输入键、缓存和资源详见A–F E/F2，不复制第二套计划。首真实路径时间UNKNOWN；本轮零产品执行。当前M4消费者缺失明确BLOCKED，后续批准F1最小适配后才可能准入，不借旧TaskId。

## Tasks：按行为纵向拆分

| 切片 | 对应AC与可验证成果 | 路径/Owner | 必要正反验证 | 当前状态 |
|---|---|---|---|---|
| S1 | AC01/02/07/08/12，真实值→持久→新上下文→刷新 | A–F F1 Master单写 | 精确值/receipt闭合/无源二次执行；首证据归档资格 | NOT_RUN，待统一实施批准 |
| S2 | AC03–09，高风险权限/版本/取消 | 同上；非作者早期只读Review | 六态、消歧、ABA、撤权、审计失败、跨实例fence、保留期 | NOT_RUN |
| S3 | AC10/11及剩余覆盖、最终交付 | 同上 | 关系/观测/UI/MCP同服务、G2历史兼容、最终按影响验收 | NOT_RUN |

## Verify与恢复

- P0 FRESH：三路径、UTF-8/LF、12条新增相对链接、4个JSON封闭判别样例及嵌套精确值检查、12项AC、六态对照、授权只追加均exit0；diff-check exit0。非作者 `/root/m4_p0_review` 一轮集中Review及实际增量定向复核完成，发现项关闭，可交A–F一次裁决；详见申请F4。D的外部IdP直接禁用即时传播限制仍待人类接受。产品FRESH=无，产品REUSED=无（只读M3身份不算M4测试复用）；CI、Windows/Intel/其他源/所有产品场景NOT_RUN。
- 本轮不运行build/test/Schema工具安装。完整正式Schema执行NOT_RUN；轻量JSON/字段检查只证明文档样例，不证明运行合同。
- 产品TestedCommit不存在；文档Head由本任务分支最终Git提交解析并在交付中给完整值，避免文档自引用SHA。Base不变，无ZIP。
- 失败：初次fetch与branch锁写被沙箱拒绝，分类ENVIRONMENT；改为受审工具权限后对应命令成功，没有产品重跑。未观测总耗时/等待UNKNOWN；restore=0、产品运行=0、封包=0。
- 本任务树/分支KEEP，原因是等待裁决和同树继续；解除条件为明确收尾授权且成果已安全集成/归档。旧M3KEEP没有移交/清理，资源总量只作预算申请，不伪称实时测量。
- 恢复：读本卡唯一状态→唯一A–F的裁决→确认新授权→同会话/分支/树继续；批准前不执行S1。最终停在规格与实施裁决关口，不更新main/生产/TDengine/M5。
