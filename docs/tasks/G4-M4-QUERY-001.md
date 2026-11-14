# G4-M4-QUERY-001｜规格驱动任务

## 当前执行与授权

- 唯一状态：**IMPLEMENTING_S2**。用户已批准A–F实施及D的合成环境IdP限制；按S1→S2→S3推进，最终停产品审查关口。
- 会话：本M4会话，后续同会话继续；Code/Agent，Local Mac ARM64。实际模型/推理设置未读取，不采用附件建议冒充实际设置。
- Base：`f0afb730ce92ecbd3a5947d9c6f58faedc8b2138`，2026-11-14普通fetch后origin/main一致；初次fetch沙箱拒绝写FETCH_HEAD，获工具批准重试exit0；没有基线漂移。
- 分支：`codex/g4-m4-query-001`；Worktree：`/Users/chasen/.codex/worktrees/g4-m4-query-001/ontology-platform`。RunId=`p0-contract-20261114`，托管operationId=`ddb793db-9e28-4040-977d-73af96443916`。首次分支创建因.git锁写权限失败，获工具批准后成功；未回退main写文档。
- Owner：Master单作者；Reviewer：一位非作者只读审查，`/root/m4_p0_review`，结论见Verify；无产品Worker。
- 当前授权：本轮用户明确批准A–F实施、范围内修复及最终V3交付；[授权追加](current-authorization.md)。P0不默认ZIP；后续产品实施完成默认最终唯一ZIP、包外回执及非作者独立重开，不再申请打包。
- P0 owned_paths仅本任务卡、[唯一A–F](../evidence/G4-M4-QUERY-001/contract-admission-request.md)及current-authorization.md追加；合同修订P0.1；当前实施owned_paths扩至A–F F1准确清单、资源预算F2。read_only_dependencies为A–F A1固定Base源码/历史合同、SDD模板与现行规则。
- 当前非目标：未批依赖/版本/下载、生产、M3重跑、旧KEEP清理/移交、main、TDengine、M5。原树六个未跟踪.DS_Store受保护。

## Specify：可观察要求

以下场景已获批实施，尚未执行项仍不是运行证据。路径别名Q/C/N/G/H/A精确展开见唯一A–F F1，测试目录为`backend/tests/`；不另复制规格。

| AC-ID | 行为/不变量 | Given/When/Then正例和关键反例 | 实现/测试位置 | 最早验证层/依赖 | 结果/原件 |
|---|---|---|---|---|---|
| AC-01 | RQ-02判别与精确值，见B | 给定P1–P3；读出并PG往返→decimal/Int64/微秒逐字一致；N1–N6/N10/N12拒绝，不补猜 | C/G4QueryModels.cs、G4QueryRules.cs；OntologyPlatform.G2ContractTests/G4QueryWireTests.cs；OntologyPlatform.QueryTests/G4QueryPersistenceTests.cs | S1正式序列化+真实PG新DbContext；无float中转 | PARTIAL：wire/精确值、真实PG及HTTP/UI刷新通过；当前修复后UI/进程恢复复验中 |
| AC-02 | 唯一Gateway真实PG链，见A | 给定正式本体和active；HTTP query→实际源值/receipt；只有M3评估可用或未知capability→拒绝 | Q/SemanticGateway.cs、N/Adapters/PgQueryReader.cs；OntologyPlatform.QueryTests/G4QueryHttpTests.cs | S1正式DI/OIDC/TLS只读PG | PARTIAL：正式HTTP首查询43检查通过，当前生命周期修复复验中 |
| AC-03 | 六态区别，见C1 | 完整零行→EMPTY，有行→FOUND；断源/超时零行→UNAVAILABLE；截断有可信前缀→PARTIAL；可见snapshot全分支拒绝→UNAUTHORIZED；两可见候选→AMBIGUOUS | Q/G4QueryExecution.cs；OntologyPlatform.QueryTests/G4QueryTests.cs；OntologyPlatform.ConnectionsTests/G4QuerySourceTests.cs | S1 FOUND；S2其他状态及真实故障 | PARTIAL：真实HTTP FOUND/UNAUTHORIZED已通过；其他六态与S2真实故障待验；S-50不在范围 |
| AC-04 | 当前授权/迟到响应，见C/D | 有grant执行与恢复成功；撤权/注销/连接禁用/secret轮换→无成功披露，UI清屏且迟到响应失效；根无权401/403无snapshot；外部IdP直接禁用即时传播按D待裁决限制，不冒充已覆盖 | G/QueryAuthorizationParticipant.cs、H/G4/QueryEndpoints.cs；OntologyPlatform.SecurityTests/G4QueryAuthorizationTests.cs；apps/web/src/features/semantic/g4-query.test.ts | S2真实票据/PG grant+浏览器 | PARTIAL：真实票据/epoch撤权阻止结果与成功审计；浏览器及完整API待验 |
| AC-05 | 固定发布与ABA，见C2 | active固定执行成功；A→B→A发生于运行中→409无成功结果；已提交历史A在当前有权时仍回读A | N/Application/QueryBindingReader.cs、Q/G4QueryResultStore.cs；OntologyPlatform.QueryTests/G4QueryRaceTests.cs | S2两API独立连接/真实激活 | PARTIAL：存储幂等恢复不重验Active，提交核实际请求原件；真实激活/双API待验 |
| AC-06 | RQ-01消歧，见C1 | 同scope两候选→选择合法IRI成功；撤权/版本漂移/未知IRI→403/409/422且无候选泄露，不取第一条 | Q/G4QueryExecution.cs；OntologyPlatform.QueryTests/G4QueryTests.cs；apps/web/src/features/semantic/g4-query.test.ts | S2源真实同号及权限变化 | NOT_RUN |
| AC-07 | 来源闭合与精度，见C2 | 行→evidence→receipt→原发布/原目录/当前目录/连接版本可核；无源键→DATASET/PARTIAL；悬空ID→503，UNKNOWN不当确定事实 | Q/G4SourceEvidenceService.cs、N/Adapters/PgQueryReader.cs；OntologyPlatform.QueryTests/G4QueryPersistenceTests.cs | S1首receipt即验证；S2降级反例 | PARTIAL：正式源→API证据链已核，S2精度降级反例待验 |
| AC-08 | 结果恢复与保留，见C3/C4 | 新DI回读hash一致、刷新不增加源read计数；24h到期410、错主体404、历史撤权403；不自动重执行 | Q/G4QueryResultStore.cs、G4QueryWorker.cs；OntologyPlatform.QueryTests/G4QueryPersistenceTests.cs；UI g4-query.test.ts | S1存储→新上下文→浏览器；S2可控时钟过期 | PARTIAL：HTTP原字节/幂等与UI刷新无源重放通过；合成key ring临时卷导致进程重启恢复失败，已修复待真实复验 |
| AC-09 | 预算/取消/原子审计，见D | 两实例租约容量/fence生效；取消先提交或审计故障→无COMPLETED；大值物化前拒绝；SQL/URL不能进入计划 | Q/G4QueryWorker.cs、N/Adapters/PgQueryReader.cs；OntologyPlatform.QueryTests/G4QueryRaceTests.cs；OntologyPlatform.ConnectionsTests/G4QuerySourceTests.cs | S2真实PG事务/两API | NOT_RUN |
| AC-10 | 关系/观测及共同UI/MCP，见A/B/E | 发布关系两端有权、精确观测按同Gateway返回；无权端点/未开放ontology拒绝；MCP不用LLM | A/SemanticMcpTools.cs、Q/G4QueryExecution.cs；OntologyPlatform.AgentTests/G4QueryMcpTests.cs；UI g4-query.test.ts | S3真实受控MCP/浏览器/源PG | NOT_RUN |
| AC-11 | G2冻结兼容，见B1 | 旧查询和旧Run按原DTO读取；当前撤权拒绝；G4不转换假图 | A/ExecutionRunService.cs；OntologyPlatform.QueryTests/QueryHttpTests.cs；OntologyPlatform.AgentTests/RunFlowTests.cs；OntologyPlatform.G2ContractTests/WireContractTests.cs | S3影响范围内真实回归，其他证据按输入复用 | NOT_RUN |
| AC-12 | 当前任务准入/证据/资源，见E/F | 当前TaskId正式消费者有效才执行；未知Task/空流/ANSI/禁入路径/错误报告不得PASS；总占用未知即不启栈 | scripts/maintenance/workflow_m4_query.py；scripts/tests/WorkflowQuery.Tests.py；verification-gates.json | 实施准入及S1第一原件→公开资格→小样预检 | PARTIAL：准入5测试及本任务runtime已运行；公开原件扫描通过，最终当前输入绑定/包门禁未完成 |

## Plan：最早真实风险路径

最高风险为当前授权与固定映射身份跨外源读取/平台持久化的竞态，以及精确值经PG回读、生成TS后失真。S1先跨层形成最短可恢复查询，再扩能力。正式DI/provider/DbContext工厂/迁移/序列化/OIDC均复用，只换合成端点和新合成凭据；不拿mock代真实成功。

首证据命令、输入键、缓存和资源详见A–F E/F2，不复制第二套计划。首条正式DI/OIDC/TLS PG→持久结果HTTP观察时间为2026-11-14T12:03:18.731216Z；当前已接线本任务消费者。原件见下方S1记录，未覆盖的S2/S3仍未完成，不借旧TaskId。

## Tasks：按行为纵向拆分

| 切片 | 对应AC与可验证成果 | 路径/Owner | 必要正反验证 | 当前状态 |
|---|---|---|---|---|
| S1 | AC01/02/07/08/12，真实值→持久→新上下文→刷新 | A–F F1 Master单写 | 精确值/receipt闭合/无源二次执行；首证据归档资格 | PASS：正式源/持久/新上下文/UI刷新及修复后的进程恢复已贯通；原件与失败见Verify |
| S2 | AC03–09，高风险权限/版本/取消 | 同上；非作者早期只读Review | 六态、消歧、ABA、撤权、审计失败、跨实例fence、保留期 | IMPLEMENTING：真实HTTP消歧/选择/EMPTY/注入参数/完成后取消47检查通过；其他竞态待验 |
| S3 | AC10/11及剩余覆盖、最终交付 | 同上 | 关系/观测/UI/MCP同服务、G2历史兼容、最终按影响验收 | NOT_RUN |

## Verify与恢复

- P0 FRESH：三路径、UTF-8/LF、12条新增相对链接、4个JSON封闭判别样例及嵌套精确值检查、12项AC、六态对照、授权只追加均exit0；diff-check exit0。非作者 `/root/m4_p0_review` 一轮集中Review及实际增量定向复核完成，发现项关闭，可交A–F一次裁决；详见申请F4。D的外部IdP直接禁用即时传播限制已由本轮用户明确接受（仅合成环境）。产品FRESH=无，产品REUSED=无（只读M3身份不算M4测试复用）；CI、Windows/Intel/其他源/所有产品场景NOT_RUN。
- P0未运行build/test/Schema工具安装；实施阶段允许已批准离线准备与适用测试，禁止安装新工具。完整正式Schema执行NOT_RUN；轻量JSON/字段检查只证明文档样例，不证明运行合同。
- 产品TestedCommit不存在；文档Head由本任务分支最终Git提交解析并在交付中给完整值，避免文档自引用SHA。Base不变，无ZIP。
- 失败：初次fetch与branch锁写被沙箱拒绝，分类ENVIRONMENT；改为受审工具权限后对应命令成功，没有产品重跑。未观测总耗时/等待UNKNOWN；restore=0、产品运行=0、封包=0。
- 本任务树/分支KEEP，原因是等待裁决和同树继续；解除条件为明确收尾授权且成果已安全集成/归档。旧M3KEEP没有移交/清理，资源总量只作预算申请，不伪称实时测量。
- 恢复：读本卡唯一状态→唯一A–F的裁决→确认新授权→同会话/分支/树继续；当前已批准实施S1/S2/S3。最终停在产品交付审查关口，不更新main/生产/TDengine/M5。

### 实施恢复记录（query-impl-01）

2026-11-14：fetch重新核实origin/main仍为预期Base，任务Head=5e0f5c2889daadec2be3a4a53f57c74ceab5908a，开工工作树干净。用户已确认本轮能源策略；公共host_continuity.inspect以准确TaskId实测POLICY_READY（AC=true、sleep=0、displaysleep=10），锁屏/熄屏NOT_VERIFIED。首次Docker socket检查为沙箱permission denied，不判Engine离线；待受控只读重核。准入适配缺失尚未运行产品。

S1进展：M4环境白名单4测试先失败（1失败/1错误）后4通过；零下载prepare完成，179后端包/391Web包，11个缺共享目录的既有公共包逐SHA复用，未复制私有runtime。初次嵌套sandbox拒绝、重试被止损拦截均保留；20秒短诊断SDK10.0.402成功后使用真实变化权限环境身份完成prepare。新增G4QueryWireTests先因缺模型编译失败，再补判别载荷/精度校验；首次全合同程序集133通过/1跳过（历史V2真实manifest场景仍缺前提），不报完整合同PASS。S1真实PG/HTTP/浏览器仍NOT_RUN，正在贯通。

S1基础增量：真实PG首次宿主连接因内部网络路由失败（c1fe2accec764f51ba03b49c69adfab5），改为同内部网络短命容器后正式迁移发现快照缺项（29c27d2275364277a7da996b1b275bf0）；补齐冻结字段和迁移目标模型后1测试/0跳过通过（22a14d7ff42d40cbb794fa9bb12548fb）。这是bytea与正式factory证据，不是结果加密/HTTP闭环PASS。容器准确ID回收，首次清理记录因Docker错误措辞误判CLEANUP_UNVERIFIED，后续准确container inspect确认不存在；历史记录不覆盖。新增查询权限单条完整grant静态正反例1通过（f9a332d873c5412ea144332e5ac883de），真实会话撤权事务待S2。非作者早审发现末尾LF词法P2，先负例失败a96f1dedb73649758730c081bcdf8e4c，改\A/\z后通过；当前判别/请求/六态及证据闭合5测试通过（924d93f6c4e14ee4b2c148d193dce3c7）。首批原始stdout/空stderr经公共workflow_evidence扫描无损存于[原件索引](../evidence/G4-M4-QUERY-001/query-impl-01/raw-index.json)，[早期证据](../evidence/G4-M4-QUERY-001/query-impl-01/early-validation.json)通过test-review-evidence（仅EVIDENCE_SCHEMA_ONLY）。当前未提交开发输入不声称TestedCommit；无中间ZIP。

早审增量修复：UNKNOWN无可信断言的UNAVAILABLE正例先失败8daacf052c8642fc9f2b1bda6a61f86f，修正后当前合同5测试/0跳过通过80bc911fe2b64a16947ba4002ba254d9；不同精度UTC排序先失败37682435ff56411bad9a97360a803b61，使用同种类精确补零比较并拒绝LOCAL/UTC混排后规范字节2测试通过abfd5c5c133245c78bf1883f985c0971。完整源执行尚未开始。

工程限制：全仓verify.ps1实际exit1，8条均为旧M3两份原始JSON末尾格式和六处历史相对链接；[基线诊断](../evidence/G4-M4-QUERY-001/query-impl-01/baseline-format-diagnostic.json)确认4个涉及文件与预期Base逐字相同，缺失目标在Base也不存在。未修改只读历史原件、未放宽门禁；此失败不能算当前交付PASS，完整package-check仍须如实报告。新任务平台PG/卷/网络KEEP，仅为进行中的S1；准确资源与临时容器删除后验保存在ignored当前Run的platform-resource-postcheck.json，不涉及旧KEEP。

源路径进展：当前已提交基础候选Head为6f834df6409feb8ffb1e0cae6b5ce5c3540af9a9（不是最终产品Head）。首次workflow plan因M4公开JSON路径未登记而BLOCKED；补精确任务路径正反例后5准入测试通过，当前plan=PLANNED/unknown=[]。早期package-check整体BLOCKED，formatExitCode=1为上述基线问题，evidenceSchemaExitCode=0、diffCheckExitCode=0、pathPolicy=PASS，估算4,359,001字节；未构包。

本任务新源PG已按F2实际预算创建（仅复用公开baseline fixture和本地镜像，新凭据/TLS），准确资源原件为ignored source-resources.json；没有重跑M3或访问其私有runtime。第一条真实TLS业务读取79afec60712749f5ac0a70f065661db7通过1/0skip，验证site-a准确行、真实微秒、主键及SQL样式外部号参数化零行，[原件索引](../evidence/G4-M4-QUERY-001/query-impl-01/source-first-raw-index.json)。非作者发现未知时间端点可能被WHERE静默丢弃的P1，增加本任务独占query_assets_unknown单行fixture并以Indeterminate与Limited分开；9ed7bd49f90548dc9543266ca929ccb3真实源回归1/0skip通过。上述是适配层，不是正式发布/HTTP/S1闭环PASS；当前正在实现共享源端口、当前会话及完整字段授权、结果与回执原子存储。

存储与当前授权增量：加密用途绑定queryId，密文篡改/跨行重放/hash不符3测试通过e4507aa26e2d45518a6be67ebc141bf0；真实PG与独立文件keyring provider恢复通过807515ef93824d45869e539a8b97dab4。正式PostgresTicketStore/MappingSessionAuthority/治理epoch与事务审计参与者实测撤权先提交后无成功结果，初次2测试通过b30c9f3078264962be07815d8c229830。非作者发现幂等旧查询不应重验当前Active、提交必须比对实际query原件；反例69302effe507488b9841021b1dcb96f3失败，修复后55caa5831cb646668e8e419db7abfea7通过。最终本增量dbcc72ab17344826a0cf20f3ee775b01为2/0skip通过，补齐结果密文/分支回执/成功审计同事务可见以及已完成历史幂等恢复。事务测试仅Connections绑定使用明确替身，不能作为正式发布、外部IdP或S1端到端证明。历史失败保留于[存储和源原件索引](../evidence/G4-M4-QUERY-001/query-impl-01/storage-source-raw-index.json)；一次故意失败遗留查询行按准确ID回收，before=1/after=0，ignored red-test-row-cleanup.json记录强后验。

回执/取消早审增量：非作者指出未读分支允许null回执以及UNKNOWN不能升级ROW_KEY，负例8a304c9520e4413eb297e95ec0a348dd真实失败，修复后f06541509fec44da813be2076272bcd3为4/0skip通过。当前真实PG事务69618c36024645a5896dac9f1e867078为2/0skip通过，覆盖取消先提交拒绝迟到成功/旧fence心跳，成功先提交则取消409且原结果保留。[原件索引](../evidence/G4-M4-QUERY-001/query-impl-01/receipt-cancel-raw-index.json)。当前仍IMPLEMENTING_S1，存储服务尚未正式Gateway/HTTP/UI接线，不能按接口存在报可用；完整runtime准入继续BLOCKED，产品交付未完成，未构ZIP。

非作者定向复核：幂等恢复/提交原件两项和回执空引用/精度两项均关闭；独立恢复各索引9个成员的字节、大小及SHA一致。未扩审、未重跑测试，不表示S1完整通过。当前53路径范围/UTF-8/LF/无尾空白/JSON检查通过，diff-check exit0；源适配器两处空行尾空格已清除，无业务变化。

网关/恢复增量：新增执行、历史恢复、取消、源证据通过同一SemanticGateway和G2EndpointGuard，实际路由导出G4 OpenAPI及TS，QueryEnabled显式DI与本任务专用key ring/后台保留期维护已接线。当前真实PG恢复授权/保留期2项通过（6e9570f1ba4f46d2a497c362a3bc2687），Connections当前版本参与者仍为明确测试替身；不能替代完整源ACL纵向验证。非作者发现首次无数据响应经基础View泄露结果hash的P2，693f79cc92744a94b2d557d6e823a099负例失败；基础View默认隐藏hash，仅当前result.read与审计事务通过后填充，e3388d80c9ba489e8d6591d339fded5c为6/0skip通过，非作者核原件关闭。原生多态Schema转换过早造成子类处理缺失，b146e57083f340d9a9b9651c650e3225失败；改为文档生成完成后转换，cf825cf73fad437f8bd286072c4fc443为7/0skip通过，含旧G2能力字节不变及真实生成闭包。[原件索引](../evidence/G4-M4-QUERY-001/query-impl-01/gateway-recovery-raw-index.json)24成员经公开扫描及无损恢复核验。仍无最终TestedCommit声明。

本轮runtime：实际Engine为12CPU/16787419136bytes；计入旧M3 KEEP、新两PG、KC/Fuseki/RustFS/API及短命第二API预留，共11.5CPU/11.75GiB，低于实际引擎及批准上限。独立证书、realm、卷、key ring均新建；只复用已校验镜像和公开夹具源。首次compose因YAML 1.1将501:20解释为整数而在创建前失败（ca519b00ea0f47ada22eaf70d4440ae9），before/after准确集合无新增/移除；修正明确字符串后启动通过。独立edge网络承载批准loopback端口，源PG保留原内部网络；API连接两网，未改旧资源。三依赖健康端点200，API匿名me为401。OIDC正式本体/源目录前提62项检查通过、单实体映射发布前提46项检查通过，均仅本任务新栈，不是重跑M3回归；S1首条真实查询/恢复/证据HTTP正在验证，UI/MCP及S2/S3尚未完成，不构包。

S1纵向原件：首正式HTTP查询43检查通过，观察时间2026-11-14T12:03:18.731216Z；原规范响应SHA256=2ea9b9e33907d1d42b5d47cebf593b2c0d05e6bdc8bf858c7b0a14cd1acfdd1b，恢复及同键重放相同。首脚本结果文件追加了一个LF，文件原件保持；其HTTP原字节为移除这一个脚本追加LF后的字节，不能把文件hash混作响应hash。浏览器刷新21检查通过，四次源统计均seqScan=2/idxScan=10，未增加业务SELECT，localStorage/sessionStorage/IndexedDB均无结果。手机原截图仅自动无溢出通过，尚未作视觉PASS。[纵向原件索引](../evidence/G4-M4-QUERY-001/query-impl-01/s1-http-raw-index.json)含6个公开扫描/无损恢复成员。

生命周期增量：新API进程读取旧查询返回503 query_result_invalid（e29e7440f6cc408f879bebad9e771dea），定位合成runtime将专用key ring置于tmpfs，停止后旧结果无法解密；保留原查询与失败，不声称新上下文测试覆盖进程重启。修复为本任务0700私有持久目录，旧卷KEEP，准确旧API容器替换后其余准确资源集合不变（bbf498549c5c435e893e2d1923a6fef4）。新查询43检查通过，原响应文件现保留精确字节，不追加LF；跨进程复验正在运行。

UI/合同早审：非作者发现主体变化旧结果未清屏、同厂区候选同名、OpenAPI路径/请求头参数缺失。修复后10/0skip回归通过14a9f698149047498f187a2560c281ec，类型检查821d1209409945ec8f771e91f5581086、lint91584a59e88c4900b1b6a81f0dd1802a及Web构建8dcd431f1cd54c3e9e889c7f5caea9b2通过；两次RED2bd5d967f83b42c4ab99df99d9cd1b9b/4a817d97a8d84a69ad07eed4c2f9ce3d保留。非作者静态复核无剩余代码缺口，但真实两标签主体切换/晚到响应与移动视觉尚待当前输入验证。

S1复验完成：browser-s1-reopen-1794659754883为18检查PASS，准确同容器新启动时间及原结果hash一致；browser-ui-s1-1794659802258为30检查PASS，含无源重放刷新、同浏览器两标签真实注销换主体、延迟旧响应不渲染与恢复404。非作者复核关闭三项UI/参数问题、独立看移动截图，查询区域完整无侧栏覆盖；不扩大为全M4通过。S2首增量browser-s2-basic-1794659895929为47检查PASS，验证跨site同号AMBIGUOUS、合法选择、缺/错上下文和改参数拒绝、完整零行EMPTY、SQL样式参数无注入、完成后取消409且结果原字节保留。

S2竞态夹具诊断：第一次后台请求断言未及时接管（ef3ebfae8d29441ba7a6f7f3e808b248）导致未形成浏览器最终报告；原stderr保留于[修复与S2原件索引](../evidence/G4-M4-QUERY-001/query-impl-01/s1-review-s2-raw-index.json)。数据库探针返回时查询已COMPLETED，不能算取消先提交。第二次已正常记录browser-s2-runtime-1794660341228失败：当前execute/result/evidence分开撤权与源ACL撤销/恢复均通过，双API同键观察到202 RUNNING，但取消到达时已完成而返回合同规定409；不把该时序计为取消PASS。随后改为提前建立只读准入观察连接，未改产品预算；只定向复验竞态和源失败。一次SHORT_REPRO_REQUIRED止损保留，定位浏览器命令输入键遗漏mjs，已将实际API/驱动/Web绑定纳入输入键，不绕过失败守卫。

资源KEEP补充：本任务私有持久query key ring目录0700、UID当前用户，未读取密钥内容；为24h结果跨进程/实例恢复保留，解除条件为最终审查完成且加密结果到期或获准安全归档。旧tmpfs卷因失败追溯暂KEEP，解除须核无活跃挂载/跨任务引用并执行准确收尾。第二API15448/768MiB/.75CPU实测共同预算通过，准确ID和启动时刻在当前Run runtime-secondary-api.json；只供S2，两者均不进入交付ZIP。

S2双API定向复验：browser-s2-race-1794660672737为34检查PASS，持锁连接实际READY后执行，第二API取消200/CANCELLED，第一API迟到提交409 query_execution_stale，真实PG状态仍CANCELLED且恢复409；源锁故障返回UNAVAILABLE而非EMPTY，两个持锁事务均明确RELEASED。前一次browser-s2-race-1794660544379取消路径通过但后续故障夹具就绪超时，整份仍FAIL；[S2竞态原件索引](../evidence/G4-M4-QUERY-001/query-impl-01/s2-race-raw-index.json)保留失败与成功，不重写原件。当前S2尚欠真实ABA/连接变化、完整容量及审计故障覆盖，S3关系/观测/MCP仍未完成，无最终ZIP。

S2版本/容量增量：[版本与容量原件索引](../evidence/G4-M4-QUERY-001/query-impl-01/s2-version-capacity-raw-index.json)含真实ABA94检查、双API主体容量26检查、真实PG事务3/0skip（ed10b0cde88d49779cb9ebb65fd2daf3）。连接2槽、任务4槽及失联FAILED/fence递增通过；审计实际INSERT后注入固定故障，独立上下文确认状态/密文/回执/审计均回滚，再成功路径通过。此存储测试仍只对Connections使用明确替身；真实ABA和HTTP取消证据独立记录。

构建绑定诊断：提交32fd05e482e25bd251f6d00b43949d84d4d2a860后测试项目引用构建重新生成API依赖程序集，检测到磁盘与运行进程绑定漂移；期间没有继续HTTP验收。已按准确进程身份停止两个API，记录原绑定/漂移文件，重建绑定9e54d2c502e4450e8e0b4e1a01a62b22；contract_build现在拒绝任何已运行API的引用构建，停止入口只核准确进程而不会因磁盘漂移阻止安全停止。旧运行证据不改、不冒充新进程。短命测试复用第二API预算槽位，实际回收后才恢复第二API。


测试隔离P1与证据影响：browser-s2-connection-1794661671287整体FAIL；旧查询404不是预期连接禁用403，随后test返回409 connection_disabled，既有DISABLED为终态，禁止为夹具修改产品状态机。根因是G4QueryRaceTests未来+25h/+8d维护使用运行库query，Sweep全库语义清除了既有查询；+6s同样必须隔离。只读审计3c3d5d20da8b424d9e4782f51c4a0e81显示当前queryCount=0及13:03:20对应准确queryId两阶段expire记录。历史HTTP/ABA/新进程恢复原件保留当时观察，但原query不再可作后续恢复基线，不能复造原ID或声称旧结果仍可恢复。未涉及M3库或资源。

隔离修正：每次持久测试使用随机m4_query_test_十二位hex独立数据库，创建标记为TaskId/RunId/suffix；测试迁移前同时核连接串、current_database与服务端所有权注释，运行库拒绝进入。容量测试独立应用正式迁移，不依赖测试顺序。Python名称正反例先缺实现失败后6测试通过；真实隔离库1963cdfc919046b78fb47b8865dc738a为3/0skip通过，准确容器及临时库创建/回收强后验保存。见[隔离缺陷与修正原件](../evidence/G4-M4-QUERY-001/query-impl-01/test-database-isolation-raw-index.json)。尚需建立新正式连接/映射/查询并证明后续测试前后运行查询不变；不能把空库不变当作存在结果保护证据。唯一任务状态仍IMPLEMENTING_S2，无最终ZIP。


隔离缺陷纵向复验：新连接正式TLS/目录48检查、正式映射独立审批激活40检查、新查询43检查通过。第二次隔离库测试6e5dec5b0d3b411bbac89b25b3b2c573为3/0skip，m4_query_test_98fb7274da21-runtime-preservation原件显示运行库两条实际COMPLETED查询的ID/status/hash/size/fence前后逐项一致；随后browser-s1-reopen-1794662558981为18PASS、原结果字节相同。临时库和准确容器均真实回收。此证据覆盖非空运行查询保护，不声称恢复已经删除的旧query。

连接状态机真实验证：browser-s2-connection-1794662583894为49PASS，从当前可恢复查询起，ACTIVE连接轮换secret版本/configRevision后读取403；正式TLS Probe与enable后历史原字节恢复；旧Active绑定的新执行409；最后终态disable后历史读取403。旧失败脚本原件保留，不再尝试启用DISABLED连接；后续通过新建合成连接继续，已禁用连接准确KEEP。公开原件见[隔离与当前连接索引](../evidence/G4-M4-QUERY-001/query-impl-01/isolation-current-connection-raw-index.json)。S2仍欠执行中当前授权/绑定变化证据，S3观测/关系/MCP未实施，不能声称本轮完成。


非作者隔离复核：准确核两次真实测试原件与非空运行库前后保护/恢复证据，关闭测试串库清除P1；仅关闭此项，不作全M4通过。另指出临时测试库创建在try外的异常收尾缺口，已移入try；创建即写准确状态，命令或后验失败明确KEEP_UNVERIFIED及解除条件；容器确定未创建时NOT_CREATED也回收已创建测试库，存在性不明不删库。注入创建失败用例确认准确KEEP记录，当前Python7测试通过。

继续执行基线：第二个已验证禁用连接终态KEEP后，第三条新合成连接正式TLS/目录45检查、映射46检查、新查询43检查通过（browser-replace-disabled-connection-1794662657060、browser-mapping-1794662667167、browser-s1-1794662679191）。两轮旧状态完整保存在ignored runtime-fixture.retiredFixtures；当前映射/query取runtime-fixture顶层，不恢复已删除原ID、不改旧Active/禁用状态。后续同一会话/树/分支继续S2执行中撤权和绑定变化，再S3；最终完整验收/V3/独立重开/包外回执尚未完成。


异常清理增量：非作者继续指出inspect超时/owner校验/stop失败可能跳过KEEP记录，已为整个容器清理增加finally；无法确认容器消失时始终写准确容器及已创建库KEEP_UNVERIFIED与解除条件，并传播原异常，临时env确保移除。新增persistence_test注入inspect TimeoutExpired的用例，确认准确库/容器KEEP及env移除；当前Python8测试通过。该短故障注入不声称重新运行整条真实链路。


非作者定向复核关闭隔离P1及异常清理P2；静态复核不冒充重跑。当前8项短测试的真实命令e71b7aa565ce4ea4a4c412f1db386936 exit0及stdout/stderr已通过公开扫描保存于[生命周期短测试原件](../evidence/G4-M4-QUERY-001/query-impl-01/isolation-lifecycle-tests-raw-index.json)。最后diff-check exit0。此提交为S2过程检查点，非最终交付Head。
