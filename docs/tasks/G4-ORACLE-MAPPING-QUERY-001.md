# G4-ORACLE-MAPPING-QUERY-001｜Oracle Mapping/Query

唯一任务状态 **S2_PARTIAL_ABA_SESSION_BLOCKED_CHATGPT_REVIEW**。指定旧租约已清，原失败保留。四角色认证与双表 access 已获资格，唯一在途 Mapping ABA 在会话前置处失败，S3 未运行。AC03-B 和 Oracle S0 仍 BLOCKED，G4 PARTIAL。详细原件与资源后态见[当前报告](../evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/s2-s3-01/report.md)。

## 执行身份与所有权

当前项目会话、本机 Code/Agent，Master 集成，P0 非作者为 `/root/pg_coupling_facts`，S0 独立只读审查者为 `/root/spec_review`。P0 Base 为 `5168f2c93ca226caa521a6dc4ac85439335274c4`，分支 `codex/g4-oracle-mapping-query-001`，托管工作树 `/Users/chasen/.codex/worktrees/g4-oracle-mapping-query-001/ontology-platform`，operationId `bf751e90-6c75-4102-a34a-7184c735a5c3`。本机 macOS ARM64，Docker VM Linux ARM64。本次使用现行会话配置。实施起点 `8ddaabb90878d5ab72a92908a030b7397c6f2d4d`。本轮为 implementation-01。

P0 的文档归属为本任务卡、[唯一 A–F](../evidence/G4-ORACLE-MAPPING-QUERY-001/contract-admission-request.md)、[事实索引](../evidence/G4-ORACLE-MAPPING-QUERY-001/facts.md)、[非作者 Review](../evidence/G4-ORACLE-MAPPING-QUERY-001/p0-review.md)、[当前授权](current-authorization.md)、[G4 规划](../planning/g4-implementation-plan.md)与 [Doris 卡末尾的集成追加记录](G4-DORIS-MAPPING-QUERY-001.md)。回执为 ignored。read_only_dependencies 为本轮 owned_paths 以外的产品、合同与门禁，以及锁、迁移、旧证据、既有资源和冻结架构。本轮实施 owned_paths 由唯一合同 C 的精确改动图、现有 preflight/prepare/verify/证据消费者、任务专用夹具与受影响测试确定。Master 单写共享路径；历史证据、旧资源/密钥、锁、迁移只读。

本轮最小正式根采用附件批准的独立托管写者。Connections 源绑定及其专用测试归 `codex/omq-source-bindings`，SemanticQuery、G4 HTTP/MCP 原期限与占位及其专用测试归 `codex/omq-deadline-store`。Master 独占共享 Contracts、组合根、工程入口、设施与当前任务分支集成。非作者审查者只读。两写者均不操作 Docker。

## 行为、最早验证与切片

| SDD 切片 | 关联 AC 与正式入口 | 当期资格 |
|---|---|---|
| S0 源能力及取消 | AC01–03、11。先验证 Oracle 类型、事务、受控固定 SQL、正式取消与独立源终态；不可观察即停。 | BLOCKED。固定 SQL 在正式取消提交前已读完；两表事务、直取消和 PG 占位子项已测。 |
| S1 单表 | AC04、05、08、10。沿正式发布、当前 grant、HTTP、真实平台持久化及新会话恢复 | PASS：auth-handoff-01第四实际窗口，准确父命令及六阶段原件见本批报告 |
| S2 双表 | AC03、05–08。等值与半开关系、ABA、撤权、超量、原期限内清理和零成功副作用 | PARTIAL。五槽已有资格，本次健康双表和四项拒绝通过单项复核；源 ACL 清理阻断完整 access，ABA 等后续槽未运行。 |
| S3 消费者及兼容 | AC09–11。UI/HTTP/MCP 同源字节，PG/Doris 与 Oracle M2 的原身份对照 | UI/MCP NOT_RUN。PG 及 Oracle M2 的既有兼容原件按输入复用；Doris 现行类型序列化尚未资格。 |

每个 AC 的正反 Given/When/Then、真实 DI、独立预期、原件、输入变化及最小重验在唯一规格 E。实施先补当前 TaskId 实际分发，旧 M2 的通过记录仅归原输入。源实例已有原生事务并发对照、固定游标自然完成及 ODP 定向取消原件。首次源冷备已在替代容器通过驱动重开。资源余量按当次准入记录，完整平台恢复仍待验证。

## 核验与恢复

本轮按 A/F 冻结 host-entry 与两内部网、API 内定向 relay、替代式恢复；按 A/B/E 验 11 列、激活后 NULL 注入、纳秒端点与显式驱动事务；按 C/D 验 HTTP/MCP 原期限、跨实例 Oracle 未确认占位与真实证据资格。S0 准入失败执行止损，真实通过再继续。原 Doris ZIP/回执及 Main 更新可由本树 `artifacts/reviews/G4-ORACLE-MAPPING-QUERY-001/main-update-receipt.json` 恢复；准确文档 Head、检查/推送/回读见相邻 `delivery-receipt.json`。历史数据和私有材料由原 Owner 保管。本轮实施完成后交付唯一最终 V3、同包重开和包外机器回执。

2026-11-19 非作者核对集中修订。已关闭所有权表述、C 表排版与旧准入时态意见。结论为 GO 进入条件执行，运行资格仍按每阶段当前原件判定。

本次 S0 最小正式根已通过真实 OIDC 登录、G3 发布、正式目录发现、Mapping 异人核准及激活。源业务读者与四个 OIDC 主体相互独立。首批 76、57、46 个检查分别属于 provision、mapping 和当期 ready，均按各自实测提交登记。正式取消与资源恢复条件见[阻断交接](../evidence/G4-ORACLE-MAPPING-QUERY-001/implementation-01/s0-blocked/report.md)。

2026-11-20，`s0-recovery-01` 起点为 `9de3b93a0dfddb948b4d68c61ad1b54ce84e0812`。实施占位入口封闭、内部维护 CAS 及 Run 较早截止。Master 独占正式资源操作、恢复审计白名单、预算器、备份和最终交接。原任务及操作身份保留，新增维护尝试分别登记。 Oracle S0 BLOCKED，AC03 未通过，S1–S3 未准入，G4 PARTIAL。

本批真实占位已完成 TASK_LEVEL_RECOVERY，替代栈已停止保留。RC05 的 OIDC 签名/角色和对象历史版本缺证，收尾 BLOCKED，S0 BLOCKED，G4 PARTIAL。[恢复报告](../evidence/G4-ORACLE-MAPPING-QUERY-001/s0-recovery-01/report.md)

s0-recovery-02 以 454d1a2f17581673cbbf44900a5fe241d603f5ef 为 Base。OIDC 与 RustFS 写者分别拥有各自维护 Python/C# 文本，复用已计量的 omq-deadline-store 与 omq-source-bindings 托管工作树。Master 单写实际维护分发、阶段预算、资源、测试汇总和交付。正常认证使用替代 PG 与 IdP，允许会话、审计及由正式票据生命周期引发的 epoch 变化。对象读取在实际及封存参考间串行。原五服务和原业务入口保持封闭。

本批认证窗口已关闭，0/4 个原主体完成新登录，OIDC 为 WAITING_FOR_USER_AUTH。RustFS 实际及独立封存参考各遍历三页，5 个版本、0 个删除标记一致。资源停止后态已核对，RC05 仍 BLOCKED。[本批交接](../evidence/G4-ORACLE-MAPPING-QUERY-001/s0-recovery-02/report.md)

product-resume-01 从 `4924f44ec1628b156d7e722513405bc13d376d8e` 开始。Master 负责证据消费、产品阶段准入、共享文件集成和真实资源。独立写者分别负责 Oracle 生命周期及 Connections/Query 回归、SelfTest 夹具及其执行预算。非作者先复核登录原件和竞态切片，再审实际交付。


## auth-handoff-01 执行追踪

Base `33e66879a6b48e25580f1623316b88fe5a5e85cc`；Master 单写 `workflow-m4-query.mjs`、Oracle fixture/plan/platform/evidence、受影响 tests、gate登记、本卡/当前授权/唯一A–F及本批三文件。其它产品、构建、依赖锁、私有材料、旧原件只读。非作者 `/root/auth_review` 只读审查真实调用链和原件。

固定执行顺序：auth → AC03-A natural-cancel → Mapping当前正式链核验／必要补齐 → S1 → reader-auth → s1-reopen。前后处理各60秒，auth600秒，四产品槽各180秒，新reader认证180秒，父截止1620秒。没有可选尾阶段。前置失败或取消不进入后续；产品5秒／源分支1秒／清理250ms不变。每阶段前重核必要会话与授权210秒；新reader会话只替换reader。auth不读源、不续授、不发布；恢复只读平台存储。

正反例由现有Node/Python框架定向回归：超过40秒人工等待后成功、提交后40秒与未提交区分、CSRF/me共用剩余期限、快速提交、取消/失败止步、实际驱动连续A/S1与新reader、真实外层/资格固定计划、替换阶段/父命令及越期拒绝。真实服务只在回归和非作者阻断闭合后开一次窗口。历史三次失败、旧1/1、S0/B阻断与cleanup NOT_QUALIFIED保持。

2026-11-20 auth-handoff-01 收尾：最终代码 `fdadc58f8be175090961c9fcee8af192cf6b790c`，62项定向及非作者21项通过。两次实际窗口各1/4，auditor原件提交后timeout，后续非秘密服务端记录invalid_user_credentials，过期未核实。用户明确授权再次有界登录及仅恢复原3持卷实例；原3已恢复且保护20项匹配，第三窗最终被归档device身份漂移阻断，未启动浏览器。任务5副本停止、2API已移除。唯一状态AUTH_HANDOFF_REVIEW_BLOCKED，历史失败及未资格不变。三份完整公开脱敏文件见 `docs/evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/auth-handoff-01/`；普通push回读后停ChatGPT复审。

最新用户要求先解决当前资源前检，再完成全部已授权业务后交付。Master追加owned_paths为 `scripts/maintenance/workflow_oracle_archive_requalification.py` 与现有platform/Recovery.Tests；只追加产品批归档设备号资格旁证及真实消费者，不改旧账本、不解析归档秘密、不重做数据恢复。先定向正反回归和非作者审查，再一次已获准真实窗口。af810b3b文档保留为当时过程状态，不代表最终交付。

2026-11-20 第三实际窗口四角色正常认证34项通过；同浏览器AC03-A执行200 FOUND、取消409 query_already_finished。该分支为唯一合同第76行明示允许，但驱动遗漏导致原父命令265cdf991f8d4725880728767d465711 exit1，历史FAIL保留。现补严格成功先赢原件谓词（同acquisition/query/owner/fence、实际源执行时序、事务/后验/物理释放、稳定终态唯一成功副作用、原最早清理期限），取消先赢及B资格不变。定向正反例和独立审查后，以新代码输入再执行固定1620秒计划；当前七任务实例沿用startup-03d，不重建数据栈。

A触发补充：仅natural-cancel观察者在本次唯一query/execution/acquisition的READ_RETURNED后通知浏览器发正式取消；收到响应后以本进程私有管道确认，独立终态命令必须在该确认之后。所有等待受原观察者和阶段截止约束，不给产品加延时。成功及取消先赢分别严格验收；定向回归88项（内含23项Node）已通过。

2026-11-20 当前批完成：第四窗口六阶段34/52/35/70/9/43项通过，固定业务SELECT各0/1/0/1/0/0，父窗2，均无clientId过滤。新reader主体相同、会话不同、结果字节一致。定向88/88，独立23输入重开、15项Python/23项Node及7类真实反例通过。历史三旧0/4、两窗1/4、第三窗A旧脚本FAIL及所有前检/测试失败保留。关闭操作9850bf57242a4fe88d043240b878b37f双轮排空全0，准确ID后态及最终资源准入PASS。此完成仅覆盖用户本批A/S1目标，不授予B、Oracle总体、S2/S3或main放行。


## s2-s3-01 执行追踪

Master `/root` 单写现有证据消费者、共享驱动/fixture/platform、当前准入与门禁登记、受影响测试及本卡/当前授权/唯一A–F/本批三文件。仅确有入口缺口时修改 Oracle UI 支持及其定向测试。只读分析 `/root/s2_s3_readonly`；EC-01/最终非作者独立 Review 后记录准确候选。其余产品、依赖锁、迁移、旧计划/证据、保护资源与秘密为 read_only_dependencies。独立只读角色无需创建写者工作树；Master继续用户指定原工作树，保护四个Finder未跟踪文件。

| 切片 | 正例与关键反例 | 实现与最早验证 | 本批状态 |
|---|---|---|---|
| EC-01 | 无过滤阶段/父全窗完整事件闭包；同步重登记过滤A、缺父原件、错源/窗、同计数不同内容、间隙读、重复事件及边界歧义拒绝 | 正式 reopen_browser/reopen_runtime_case；离线原件重开，不启动服务 | PASS：52项定向、原六阶段递归重开及非作者170件原件复核 |
| S2 | 六条单grant各自覆盖双表；先健康正式Mapping/查询，再独立整数/时间/关系、NULL、授权、同Q源后正式Mapping ABA、独立连接版本／旧selection、六态与新reader恢复 | fixture/m4/platform/evidence实际分发；先冻结新计划和独立预期 | PARTIAL：前五槽按原输入复用；四角色认证和 access 已获新资格。唯一 Mapping ABA 前置失败，连接版本、旧 selection 等后续项目 NOT_RUN |
| S3 | Oracle正式UI及四MCP工具、同query原字节/恢复零源读/撤权清屏与身份迟到响应；旧源兼容按输入复用 | 正式产品组件和真实消费者；S2前提成立自动推进 | NOT_RUN |

原旧auth-handoff-01计划不改。资源串行使用，不启动未准备的长链；不重试AC03-B抢竞态，不使用慢SQL/压力/新依赖。trust/secret只有可恢复的已登记合成版本才运行，否则准确记录缺项并继续独立范围。集中交付目录 `docs/evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/s2-s3-01/`；三文件绑定准确Head，公开字段白名单，私有原件仅本机重开。

EC-01 已关闭：作者回归命令 `0220692f44a143c3867d36a650b228f8` 52/52，离线资格 `7795d4266f3945c3ba338644aa7d7d81` exit0。非作者 `/root/ec01_review` 对准确消费者 SHA718bce2d400afbb31437df66204434364b52e2b054f1a82b88c474d4ead6925c独立重开170件原件与七类真实原件篡改拒绝，限定GO。父全窗两条完整事件=六阶段无重复并集，间隙0；旧TestedCommit与原字节保持。首次包装器丢失环境选系统Python3.9造成纳秒时间解析失败 `4a88fe75c0be47e586c9d9ac3765790b` 原件保留；以原环境Python3.13重开成功，无产品重跑。现在自动继续S2/S3实际入口与独立预期准备。

S2/S3实现owned_paths细化：Master新增任务专用 `scripts/maintenance/workflow_oracle_mapping_s2.py`（六条组合授权和可逆源夹具）与 `workflow-oracle-s2.mjs`（实际双表场景），由现有platform/fixture/m4真实分发调用并登记传递输入；不是通用框架。Web仅 `apps/web/src/features/mappings/editor.tsx` 与 `mappings.test.ts` 的Oracle来源准入。正式实现与负例完成前不启动产品窗口。

S2定向产品缺口：Oracle每分支旧投影只有单表，改QueryBindingReader的双表Oracle分支一次返回22字段闭包；PG/Doris分发不改。Query根过滤丢失完整父集与目标观测路径跳过重复身份，需在OracleQueryReader保留同次有界授权全集、检查交叠身份/多父/扇出。Master独占相应Contracts/G4QueryServices内部JsonIgnore载体及定向ConnectionsTests；不扩公开wire、持久schema或源读取范围。实际资格仍待新回归与真实场景。

本批新增准入路径：`scripts/maintenance/workflow-oracle-s2-plan.json`、`workflow_oracle_mapping_s2_contract.py`、`scripts/tests/WorkflowOracleS2.Tests.py`、`scripts/tests/WorkflowOracleS2.Tests.mjs`；Master 单写并复用现有正式消费者。后端定向测试 owned_paths 追加 `backend/tests/OntologyPlatform.ConnectionsTests/OracleMappingBindingTests.cs`、`backend/tests/OntologyPlatform.SecurityTests/G4MappingAuthorizationTests.cs`。新增契约载体仅进程内 JsonIgnore，不增加 wire 字段。

本批在途验证 owned_paths 追加 `backend/tests/OntologyPlatform.AgentTests/OracleQueryS2RuntimeTests.cs` 和 `G4QueryAbaRuntimeTests.cs`；复用正式五秒Gateway、四角色当前票据与现有单query因果消费者。2026-11-20用户ABA澄清已撤销未定义第二类；不再等待。唯一必验为同Q真实源返回后正式B→原A激活、activationId变化/revision递增、原期限内409及独立零成功副作用。连接版本、历史结果／旧selection按AC05各自验收，不能混计。

新父命令尚未启动。冻结前补入独立 `s2-oracle-versions` 槽（180秒），当前目录单变量变化拒绝后重评发布并恢复正常查询；按最新澄清另设连接版本在途槽180秒；冻结前新计划父预算3240秒，各产品请求5秒、源1秒、清理250ms均不变。旧auth-handoff计划不变。

2026-11-21（原批持续）：ABA澄清已同步唯一AC05及本矩阵，单一在途Mapping ABA与独立连接版本／历史selection均有真实入口与独立消费者。新计划冻结前加入连接版本180秒槽，总3240秒，原auth计划及5s/1s/250ms不变。六组合grant与源/权限反例具备前态计划、全值CAS、真实命令双流及恢复后态；自然到期使用新grant未来5秒及独立PG时钟观察，短TTL仍只签发阶段前检拒绝。trust/secret登记核查仅见本任务version1，无本任务可恢复替代版本，具体轮换链保留NOT_QUALIFIED。产品窗口尚NOT_RUN。

2026-11-21入口候选：67项Python定向（内含原23项Node执行，不重复累计）、新增2项Node、结构前检通过；Connections8、Security4、PG黄金2、OracleM2目录1、Web12及类型/lint和零下载构建通过。非作者关闭SQL时间等价、源记录闭包及属性误引三处消费者问题，六文件冻结，限定GO进入有界窗口，不代表S2/S3已验收。Vitest首次实际12通过，但包装器错误解析默认文件报告且在当前Oracle树写入旧默认任务名目录；保留HARNESS_REPORT_PATH偏差，按现有隔离配置重验12通过。

2026-11-21本批真实窗：代码6d77931685a3d5c8a5a9ac68e9b1cf63df872d4b，父eebde047943f4a7e8e405510131308ea exit1。四角色600秒窗口首角色未提交、0/4，S2/S3及六条新组合grant未执行。最终绑定因阶段期限耗尽未取得，inputsUnchanged=false保留。父/认证阶段无过滤业务读均0。收尾9112c22911f54b27bfacfbd70414c9f4双轮排空全0、五副本进程停止（Fuseki干净关闭未资格）、两API移除、Web退出；旧资源/main不变。唯一状态S2_S3_WAITING_FOR_NORMAL_AUTH，当前交接三文件保留NOT_RUN/NOT_QUALIFIED，不生成中间PARTIAL ZIP。

2026-11-21用户明确正常登录已就绪，从a40753d33e19c70dbf6e3c43c15e895d2d71bce8继续同批。新父e4cf6ad7a0f64bce86ea698f57fdd56f中四角色认证4/4、词汇及8查询内容检查通过；Mapping源读预期漏算激活重评（真实应为4），内层先写PASS被外层异常遗漏撤回；relations在null-parent快照省NULL后恢复校验失败，父exit1。旧报告/失败保持；现消费者拒绝假PASS，不能把已观察内容称完整CASE资格。

本次受影响短修复仍由Master独占原owned_paths：browserRun异常强制FAIL并阻断后续；Mapping全新验证+激活独立预期4，完整既有链0，中断态拒绝；独立快照显式NULL ON NULL及11列，消费者按明确v1/v2 SQL兼容完整旧原件；Agent构建消费者额外接受准确product-resume-01，其他身份/双流/快照绑定保留。原null-parent token03018836c8e54863a439c2838c07cbfa已以4df9527db7584a87b847141596bcbde3按全值CAS恢复双表原散列。14 Node/16 S2 Python/7认证原件回归通过，原构建键及服务复用。原15槽计划及预算不变；已发布词汇与Mapping只回读，实际快照输入受修复影响的查询短阶段重验，随后继续未执行场景；不重跑旧EC/A/S1、不导出关闭的旧会话。

非作者对当前增量限定GO：真实认证构建/票据32原件短链重开通过；旧父仍拒，源恢复27原件精确闭合。继续原15槽无派生计划，当前词汇/Mapping已发布状态只回读且验0源读；受影响查询阶段及余槽新测。

2026-11-21后缀继续：父命令edd1379b83c246329579075d16ccda58前五槽经a495b4d475404f95b726b8b46d6a3663正式离线资格及非作者重开，546件原件、父窗50次源读、间隙0。权限撤销已按原token恢复，失败仅为JSON对象键顺序比较；改用既有微秒精确same_grant。Master owned_paths追加新workflow-oracle-s2-access-plan.json、workflow_oracle_mapping_continuation.py及既有S2测试/门禁登记。新planId s2-s3-01-access-01保持同批：四角色新认证后从access接余下十槽，总11槽2520秒，各槽预算不变。原15槽计划及其失败原件保留；已资格前五槽以原父命令独立引用，不进入新父时间窗或源审计事件。当前绑定、源基线、未执行代码差异及真实消费者逐项核验后启动，禁止重跑已资格前缀。后缀由任务专用run_access_suffix实际入口执行，原platform与审计依赖保持2a原字节和严格校验。

2026-11-21当前收尾：后缀实测Head2f7b4f5476280c3f8e93d69fc94dbc5d6c55f9f0，父36a4b8abb9de4c46a901778b74fdceb2仅运行认证槽600002.686042ms，operator-ab未提交、0/4，ORACLE_LOGIN_WAITING_FOR_INPUT。结束绑定因期限耗尽未取得；保留inputsUnchanged=false，不声称实际漂移。后十槽NOT_RUN，既有前五槽资格与六组合grant事实保留。收尾operation25241e1baf8c40828442bd29488c9642两次七项排空全0、准确两API移除、五副本进程停止、受保护资源hash不变；Fuseki干净关闭仍未资格。磁盘上限前检曾超9MiB，仅按非作者审查回收本任务SecurityTests/bin 39284736分配字节，绑定与原件保留，未放宽40GiB。

收尾更新当前formal-resources.json后，旧冻结路径失效；既有formal-resources-d0f2f50e09679c3092fe4d23a259e0acc22e618e3c41f386cd4c6f4a22484124.json仍保留准确1384字节。仅对此固定资源清单支持内容键原件定位，重新核原SHA/长度并记录别名；不改旧资格索引、当前资源清单或任何原件。其他文件变更仍拒绝。普通推送与三文件交付后停ChatGPT复审，产品尚未完成，不生成中间PARTIAL ZIP。

2026-11-21用户明确刚不在电脑旁，授权从70c94502a2bfbb0a306ccf599403a75fceeb61b1再次600秒正常认证。同批/原后缀计划继续，既有原件复用。上次收尾后同五数据实例启动，按同构建/配方创建两API；前缀衔接只允许真实登记的进程代次及无状态API ID变化，固定数据容器/镜像/卷/网络/端口/快照/构建/relay/compose仍逐项一致。当前宿主继续完整真实检查，观察与新父身份仍严格相等；旧前缀和源审计原件不改。

本次最终认证窗短链 owned_paths 追加 workflow_oracle_mapping_continuity.py、recovery.require_current_fuseki 单个新代次分支及现有 evidence/门禁登记。独立预期验证旧全集和正式发布词汇四声明；冻结检查点与失败启动原件不变。正常停止/新启动、API准确删除/创建及完整Oracle挂载均消费实际命令；不重建数据或放宽源审计。

2026-11-21 10:02用户因仍未在屏幕前，再授权一次600秒正常认证。同批原后缀继续，上一父654eaf461bec4c00b9cf618bf0a93211认证0/4、产品未资格原件保留；关闭补证348c1f...保留原磁盘后验失败与Fuseki clean未知。Master owned_paths追加workflow_oracle_mapping_repeat.py，固定第二段宿主代次边；第一段常量和证据原样保留。只新读本代完整图库、Published源码与真实停启链，不恢复数据。两个同任务公共feed副本已按非作者审查回收，运行四构建/快照不变；完整prepare不再声称当前READY，下次须从现存同hash原件零下载物化。

2026-11-21最新明确授权：用户要求Codex自行填写现有密码完成正常登录，不再要求本人操作。仅后缀s2-s3-01-access-01使用系统钥匙串四个准确账号条目，operator-ab为独立operator-reset-01-20261120，其余为isolated-login-20261120T040700Z；口令只在本机进程内直填已核验本机OIDC表单，不显示、写日志、落盘、导出会话或重置密码。原600秒/新reader180秒/提交40秒与产品预算不变。最新父04f23ea8cfe34868a8500b80164d86fb认证4/4及34checks通过；access因源清理未确认503失败，后9槽NOT_RUN，权限/源ACL准确恢复。继续短链修复和自动S2→S3，当前状态S2_S3_IMPLEMENTING。

本次确证源ACL短链修复owned_paths追加Connections的Adapters/OracleQueryReader.cs、OracleSourceAdapter.Mapping.cs及OracleQueryLifetimeTests.cs；仅区分完整前置拒绝与未知打开/取消/释放，保留原1秒/250ms、旧AC03-B未资格。相应API/Agent/Query/Connections按影响重建，持卷实例保持，原件与旧快照不覆盖。

本次source-acl失败留下准确FAILED占位query-4b9f97e1bbdd45f7a39111c907447f65、owner oracle-execution-8db5f162e634422abf8b94caf509d2c9/fence2。只对本次替代实例执行相关任务收尾，owned_paths追加SemanticQuery/G4OracleAccessMaintenance.cs、Api/G4/OracleAccessMaintenance.cs与Program.cs、QueryTests/G4OracleAccessRecoveryTests.cs及本任务精确执行器。原S0维护常量/入口不变；必须两API封闭、新鲜零源会话、全行和失败审计CAS后同事务只清租约两列。保留原FAILED与250ms未资格，不重启五持卷、不触及旧资源。

2026-11-21 当前源ACL失败短链修复：21项Connections生命周期测试通过；新固定FAILED租约恢复在随机隔离PG实测1/1、0skip且库/helper已删除。两原API 31fc0ef3…/7dac6ce7…正常退出并移除；固定query-4b9f97…经非作者新鲜证明重开后，真实命令56a20ab08e69402e8469f7c8c8362f4c完成仅两租约列TASK_LEVEL_RECOVERY，FAILED/fence2/失败审计保持。新连接37d113…/ba8667…已独立核对，仅新增一次准确维护审计；原250ms仍NOT_QUALIFIED。新API 26e72f80…/c45bfd75…采用新API/Query/Agent快照，五持卷容器与进程代次保持。

当前owned_paths再明确：`workflow_oracle_mapping_access_refresh.py`、`workflow_oracle_access_maintenance.py/.cs.txt`、现有continuation/continuity/repeat/evidence/query准入与verification-gates登记、受影响S2/正常登录测试。历史前五槽仅按原2a2ea74提交的414文件input53bddbec…及原build/log/config字节重开；当前backend inpute8b537ed…不同，必须由新增双表healthy-relations真实短链补证。旧计划/索引不改，正式窗口仍使用原s2-s3-01-access-01后缀，旧latestQuery保持原绑定。回收仅本批公共feed重复副本和已结束构建中间件；原源码/原件/快照/私有材料及受保护资源保持，完整prepare状态不冒称当前READY。


2026-11-21 当前容量短链：Oracle替代卷真实增长203277824B，原40GiB检查如实阻断在认证前。Master owned_paths追加 `workflow_oracle_mapping_capacity.py` 及当前resume/continuation/evidence/query消费者、S2测试与门禁登记。原resources/platform/window/execution审计依赖保持原字节；产品专用入口逐AST节点及全局绑定核对原算法，只从原host_start核销63个已删除公共feed副本254558208B，重现逐项撤销信用。当前host实测与总量不再重复扣除；40GiB/.75GiB/64MiB保留额不变。额外回收7个已独立复核有全局同hash原档的本树压缩副本160780288B，只影响实际du，展开内容/快照/私有材料保持；完整prepare仍NOT_CURRENT。原失败与资源增长事实保留，正常登录沿用户既有自动填写授权。

2026-11-21 451d26a9窗口自动正常登录4/4、34检查PASS；父7e3085f4533143fb84b49adc83159998在首条healthy-relations的源前置阶段超时，503 query_source_cleanup_unconfirmed，后九槽NOT_RUN，无权限/ACL变更。保留该冷启动失败，不推断JIT原因。owned_paths追加workflow_oracle_mapping_readiness.py、workflow_oracle_preparation_runner.py、workflow_oracle_preparation_maintenance.py/.cs.txt及对应S2测试/消费者/门禁：仅准确query-c2195dd80e21477c9f75f44cf29e8ad0的FAILED占用采用冻结451d源码三文件白名单替换的一次性维护程序集；真实PG隔离测试1/1通过，产品e8构建/三快照保持。只移除重建本任务两API，五持卷代次保持；正式Connection test先核当前API的Oracle就绪及零业务读，再执行原Query预算。准备失败及晚恢复不提升任何产品/250ms资格；main与受保护资源保持。

本次第四边消费者workflow_oracle_mapping_preparation_refresh.py纳入owned_paths；原access_refresh保持冻结，原三边先完整重开，再核同e8构建/快照、准确两API退出重建及本次query-c2195晚恢复。实际CAS7e9289f17c0740a68a18058360f6a1c4只两字段并保留失败；MTP生成0e68命令argv未完整重开，保留限定状态，409编译输入/真实csc/新准确测试1/1已独立闭合。

当前短链验证：实际四边重开9135b452e9f74756adcc9ab3598b8fdd、S2 Python34项3417ac22c72c48e1b31257d80f11bf1b、JS入口4项2633e9edd64b48fea25fb82a008d6f6a、runtime前检f1c554cae17d4b5498c3ef7f12681256与格式80700ca1e27d4f28b9d5ced9fb0d36d8通过。此前维护MTP启动/发现失败、消费者路径边界失败及检查包装器漏product环境失败保留，不冒充测试通过。新准确API为4d4b403d37e11d19e5082e0a2ead5235d66f135e52a3f46f22022ec9c333d89e/d6a458aed358e28de1eb254d504ec1a0b24e14282a7f3ae823c92f3c0f84533c；Oracle/PG/IdP/RustFS/Fuseki代次保持。

6c5c6503 实测父60a80687b58546afbd5abb19af3741c1正常认证4/4，当前连接探测五阶段通过。首个双表查询在目录校验阶段超时、503，未执行业务SELECT。04:19源统计显示一次物理主键/NLS目录语句耗时308183微秒。AC03-B仍BLOCKED。追加owned_paths workflow_oracle_mapping_postprobe.py与现行access/就绪消费者，仅对应query-515cf74c1f53415785ff35c89ecd2fbb。原件7053bb4a503847d38997368b92e2bbd7为新准确维护隔离测试1/1。就绪入口用本人历史结果的正式GET在原5秒内核5056字节及零业务读，然后执行原预算新Query。

2026-11-21 本批准确实测父命令 `685e33e9abd749168f6152789677859a`，产品 Head `ee802b487f386417e312d40e84978ab49e78c182`。四角色登录与本人历史结果恢复合格。新关系查询 FOUND，父全窗 2 次业务读，间隙 0。四项 UNAUTHORIZED 已核；撤回目标表 READ 后 HTTP 503，查询 `query-3e6bb50bdffe43feaa09736718b1dcb0` 保留 FAILED、fence 2 及原租约。实际物理释放及事后源会话零已观察。六条组合 grant、变更 grant 与撤回的 READ 后态均已回读。权限恢复原件不替代失败查询资格。

本次 owned_paths 包括既有 OracleSourceAdapter.Sql.cs、OracleSourceAdapter.Mapping.cs、OracleAdapterTests.cs、产品原生停止入口及前缀消费者。只读证明的完整单行阻断结果现能到达明确拒绝路径。修正编译及 35 项 Oracle 定向测试通过，含非整数计数拒绝；该修正尚无新产品窗实测。两个 API 已移除，五个持久副本进程已停，旧受保护资源及最后失败行 KEEP。原单行维护程序准确绑定到此前查询。另行处置本次失败行及重新实机验收由 ChatGPT 集中复审。三份公开文件见[本批报告](../evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/s2-s3-01/report.md)。

本次维护目标仅为最后失败窗口的 `query-3e6bb50bdffe43feaa09736718b1dcb0`。沿现有 SemanticQuery 准确行两列 CAS 和治理同事务审计、原生启动/停机、有界平台访问及真实消费者。维护从已核关闭状态起步。原失败与 AC03-B 不得提升。Master 单写此目标的执行入口、原窗口驱动、消费者和三份交付。

源撤权查询在候选 319e7cfe 上实测为 UNAVAILABLE，物理释放得到确认、租约两列为空。原父 c9a0458559de4934a530dcbcc9ca74a4 的旧结果恢复返回 HTTP 500。当前原路径补 QueryBindingReader.cs 对 Oracle 只读证明拒绝的正式错误映射，沿原范围复核随后短链。

2026-11-21 续行收尾。按用户授权仅维护 query-3e6bb50bdffe43feaa09736718b1dcb0 的两列租约，原 FAILED 与失败审计保留。最新 access 实测 78 项，源 READ 撤回下的清理确认 1.5729 ms，旧结果 503，目标 READ 已恢复。原 A 的激活 revision 仍为 1，批准的 B 提案未激活。S3 未准入。门禁登记包括三个新增 ACL 消费模块，生命周期单测改用实际产品资源入口，129/129 通过。两 API 和五副本已收口。当前停点为 ChatGPT 复审。
