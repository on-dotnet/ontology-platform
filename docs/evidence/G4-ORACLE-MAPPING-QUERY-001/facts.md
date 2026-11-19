# Oracle P0 事实与恢复索引

基线 `5168f2c93ca226caa521a6dc4ac85439335274c4`。本文件区分当前源码、历史原件、厂商语义与本机观测。所有实施选择集中在[唯一 A–F](contract-admission-request.md)。

## 可以复用的事实

- Oracle M2 的实测提交为 `f6955e272c412c5528e5698b8ce94a99a44985e1`，已合并历史任务 Head `e07eab20feb3fdef9e24a20dec12d11b15bd7d46`。当时本机 ARM64 Free 23.26.3.0.0、Oracle.ManagedDataAccess.Core 23.26.400、TCPS 与原生只读证据，46 共享单元、19 合同、122 UI 组件、5 真实 adapter、11 组 OIDC/UI、8 作业/5 探测，只覆盖旧元数据与生命周期。用户已接受冻结镜像用于本机开发的既有风险以及当时 13 GiB 镜像/40 GiB 总盘预算；旧 24 小时提案没有成为当前限制。其他 RU/edition、生产、整库灾备资格未建立。[任务卡](../../tasks/G4-M2-ORACLE-01.md) · [带最新覆盖裁决的原申请](../G4-M2-ORACLE-01/admission-request.md) · [部署与恢复](../../deployment/oracle.md) · [原门禁](../G4-M2-ORACLE-01/final-review-validation.json)
- M2 证据索引 Git blob `beb4703760fc54973ccf80994cc05b1896f4231b`，文件 SHA-256 `f420b29a84f3c804511be5274eeb4dc789c97d251e9134e50fd36d6864c2ec27`。本次从主库索引内存解封并核长度及 SHA 的三份原件为 current-lifecycle-02.json（8020 字节，`d665e9d9fc49c810ef5e836a1504bdddbba951bf2bba3d422e557006222d753d`）、resource-observation.json（1071 字节，`52fa48b9e34b20bf0eb7a9deed7fe5e2e9e140cb7c7ae861002d4234a0289e0f`）、final-cleanup.json（34613 字节，`d6b7920fdcd3093d29df7c462619cb476e15f1e5f6c53e7b26051e15521bd577`）。旧 M2 定向 SID/SERIAL 夹具、平台 PG 11 表与 Keycloak realm 的恢复归原 Run。原私有 runtime/PFX/KeyRing/wallet 和平台备份留原树，内容未读取；当期解密、端口、凭据、TTL 与新业务读取 NOT_VERIFIED。[原索引](../G4-M2-ORACLE-01/metadata/index.json)
- Doris 已接受 Head 与本基线相同。产品构建输入 `9780c8f91cd084c1df11c604186d22d7f08f3023`，E1 实测 `f2673f2c62537b5422f308b99cfb25da464eee35`，工程实测 `698ca0e2e4c5b50659e02637c77473e32bc1a343`。复用原 V3（7,553,879 bytes，SHA-256 `a3bc91f2017fefd7b41c28aed3fdc9c7ef947eb8f890b3372879bc6b8563adce`）及同包 VerifyOnly exit 0/1819 成员。原固定 HEAP 取消限其实际计划。E1 审计重试可确认同 argv/源输入；完整环境身份未证相同。平台 PG 干净关库引自既有资源回执，本批没有独立读取完整关库日志。历史 -9/TIMEOUT 与 134 唯一用例并集、C# 格式 exit 2/271 条继承诊断、首次 MAF 超时根因 UNKNOWN 继续保留。[Doris 合同](../G4-DORIS-MAPPING-QUERY-001/contract-admission-request.md) · [RF-01](../G4-DORIS-MAPPING-QUERY-001/review-fix-01/review-fix-report.md) · [RF-02](../G4-DORIS-MAPPING-QUERY-001/review-fix-02/report.md) · [历史字节映射](../G4-DORIS-MAPPING-QUERY-001/implementation-01/historical-byte-mapping.json)

## 代码事实与当期缺口

| 准确消费者 | 本基线可见行为 | 需要的当期证明 |
|---|---|---|
| [目录规范编码](../../../backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Catalog.cs) / [QueryBindingReader](../../../backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/QueryBindingReader.cs) | CanonicalCatalog 对对象 schema/name/kind 及列 ordinal/name 排序。Oracle 使用 oracle-m2-v1；Web 用 web-m2-v1；PG 与当前 Doris 落 pg-m1-v1。DemandCatalog 最终重算固定 pg-m1-v1，原与当前快照都经过它。DescribeProjection 对 Doris 单列专路，其余走 PG 字段。 | 从精确原绑定而非客户端/最新配置选择；旧身份重算、错源拒绝、所有实际投影字段授权 |
| [源分发](../../../backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionSourceDispatcher.cs) / [Oracle 端口](../../../backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Abstractions/IOracleSourceAdapter.cs) / [驱动](../../../backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/OracleSourceAdapter.cs) / [Oracle SQL](../../../backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/OracleSourceAdapter.Sql.cs) | 注册了 M2 探测 10 s/发现 20 s；连接/传输 5 s、重试 0、Pooling=false，Dispose 有独立 5 s WaitAsync。Create 禁用 Pipelining，ExecuteAsync 写旧 M2 ModuleName 与唯一 ClientId。启用 pipelining 的异步取消不受官方支持。ALTER SESSION READ_ONLY 及目录 SQL 存在。元数据含 Precision/Scale/字符长度单位/时间精度；它不完成逐行身份或关系评估。 | 原 1 s 分支内新业务命令/清理，窄实表与权限、字符集/列 collation、事务顺序和源终态 |
| [Mapping 验证](../../../backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/MappingValidationService.cs) / [发布](../../../backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/MappingApplicationService.cs) / [版本规则](../../../backend/src/Contracts/OntologyPlatform.Contracts/G4MappingRules.cs) | 当前以 SourceSemanticsHash 非空选择 Doris entity/relation/executor hash，UNKNOWN 选择 evidence 形状；MappingVersionBinding 和配置 switch 只闭合 PG/Doris。 | 三级显式分发、原字节 golden、NULL/数值/时间、发布与恢复均重验版本 |
| [执行器](../../../backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/G4QueryExecution.cs) / [收据](../../../backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/G4SourceEvidenceService.cs) / [发布槽](../../../backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/VerifiedReleaseSources.cs) | Doris 专属提交余量与观察，现存查询证据只接受 PG/Doris 两组版本/水位。根发布按固定槽位核权威字节、散列、图引用、严格 UTF-8，再经正式 SHACL。 | 当前权限优先的 Oracle 同对象因果、真实发布/恢复及原期限 |
| [组合根](../../../backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs) / [Mapping 编辑器](../../../apps/web/src/features/mappings/editor.tsx) | G4 Development 注册 IOracleSourceAdapter；业务读经 QueryBindingReader 与 PG reader、Doris 专路。编辑器合并 PG/Doris 列表。 | 实际 DI 经 HTTP、MCP 和浏览器；测试替身不构成执行资格 |
| [工作流](../../../scripts/maintenance/workflow.py) / [前检](../../../scripts/maintenance/execution_preflight.py) / [原平台控制器](../../../scripts/maintenance/workflow_oracle_platform.py) / [旧夹具](../../../scripts/maintenance/workflow_oracle_fixture.py) | 旧工程脚本检查固定 M2 TaskId、RunId、源容器标签、网络及 runtime 根；新 TaskId 尚无业务适配。既有 prepare 以锁、存档 SHA、缓存内容键及构建绑定作为使用条件。 | 新任务真正经过 prepare、准入、生产资格、publish/restore 和 MemberPlan/MeasureOnly。本批均未以业务身份执行 |

## 官方语义依据

访问日期 2026-11-19，Oracle AI Database 26ai 与同代 ODP.NET 开发文档。文档描述系列语义；23.26.3.0.0 / 23.26.400 的实际耗时、驱动映射与证明可用性等待 S0。

- NUMBER 的声明精度/scale、DATE 含时间、TIMESTAMP 小数精度以及本地/带时区变体不同；字符长度语义区分 BYTE/CHAR。应用的 18 位整数、28 位定点与六位时间是本任务建议子集。[Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Data-Types.html)
- Oracle 当前把零长字符串当 NULL；字符比较同时受排序规则与空格填充规则影响。即使源等值，应用仍须验证固定比较与独立预期。带引号标识符保留精确拼写。[Nulls](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Nulls.html) · [Comparison Rules](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Data-Type-Comparison-Rules.html) · [Object Names](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Database-Object-Names-and-Qualifiers.html)
- SET TRANSACTION READ ONLY 要求事务首条语句；同事务各查询读一致，提交/回滚结束该边界。系列文档不能给本次会话生成可披露水位。[Transaction Processing and Control](https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/transaction-processing-and-control.html)
- OracleCommand.Cancel 是取消尝试，命令可能已自然结束。V$SESSION 的 SID/SERIAL# 表示会话，需另绑定实际 SQL 执行；UNIFIED_AUDIT_TRAIL 的可用字段和 return code 提供终态候选，实际策略、可见窗口、字段粒度与迟延须测。只使用 Free 允许的现有能力，任何需要额外许可的诊断设施均须另议。[ODP.NET Cancel](https://docs.oracle.com/en/database/oracle/oracle-database/26/odpnt/CommandCancel.html) · [Pipelining 与取消限制](https://docs.oracle.com/en/database/oracle/oracle-database/26/odpnt/featAsyncPipelining.html) · [V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/V-SESSION.html) · [UNIFIED_AUDIT_TRAIL](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/UNIFIED_AUDIT_TRAIL.html)

## 本机资源与恢复入口

2026-11-19 12:44:32 UTC 只读采样，原件在本树 ignored `artifacts/workflow/G4-ORACLE-MAPPING-QUERY-001/resource-inventory.json`。该文件记录真实命令/退出、20 个相关容器完整 ID、资源限制、挂载和端口，摘要同时进入包外回执。Docker 29.9.2 aarch64 报 20,964,958,208 bytes（19.525 GiB）/12 CPU。宿主 32 GiB/12 logical CPU，memory_pressure -Q 为 48%，swap 已用 1404.69 MiB；数据分区可用 216.53 GiB。Docker system df 报镜像 32.27 GB、卷 6.305 GB、build cache 2.925 GB，未给 Linux VM 文件系统剩余空间。端口探测与资源余量须在实施当刻重取。

| 已持有对象 | 当前身份和状态 | 恢复条件 |
|---|---|---|
| Keycloak | `3f1502f453da342d8cd57ab6514852d1fa06007baad709156abb7da0e5e2647f`，运行，1 GiB/1 CPU，回环 15643 | 原卷身份、realm/主体/签名与隔离恢复 |
| Fuseki | `d3f2a4b9dd9d06bf3141e35c80b4c96246b47cc81092762f88171bf57dff5e04`，运行，2 GiB/2 CPU，15645 | 原 TDB2 全库、真实发布图与 SHACL |
| RustFS | `57ef8d99c6eb37eb4681f9ae707537de93b556218394ad54c8703b2f2b2f5ce9`，运行，0.5 GiB/1 CPU，15646 | 原版本、对象字节/长度、PG 槽位与解密身份 |
| Doris FE、BE、平台 PG | 分别 `8b25045bed1fac7df9fa945d636216f2a92c8efb7fce35f0a0edf96a6df888a5`、`292a8c9e30a5465a9cac32127a65d8db760d366ab45fcf75cf34be4af3fe35f2`、`34a947835a8949be5fb34bdc813e87ff812dca1d3381ccea7ce610754448367f`，均 exited/STOPPED_KEEP | 各自原 Owner；新 Oracle 栈无依赖 |
| 原 M4/M5 14 个 ID | 按两个准确项目各七个，全部 exited/STOPPED_KEEP | 原保全/恢复决定与证据继续有效 |
| Oracle M2 | 用户本地 linux/arm64 manifest `844b2cdb95c4cc120f549ff3b2aa36c191c8c9244bf90e6082971aaa6355f6d8`，Docker 显示 13,076,125,534 bytes。普通卷 `g4-oracle-impl-02_oracle-data` 为 local，当前可见持有容器数 0。保留旧工作树私有材料 | 复用镜像与复用数据是两项不同决定。首选新卷。若要求读旧数据须单独核只读冷复制、版本、私有密钥与隔离恢复 |

宿主 lsof 在建议段 15741–15747 未见监听。旧 Oracle 文档的 API/OIDC/Web/PG 回环为 15100/15180/15300/15432，本次也未见监听；只是采样时点。现有三项持有服务实占约 2 GiB，本任务按限制合计 3.5 GiB/4 CPU 计峰值。资源方案、恢复判据与停止点见合同 F。[原保全卡](../G4-DORIS-MAPPING-QUERY-001/review-fix-01/resource-retention.md) · [新任务卡](../../tasks/G4-ORACLE-MAPPING-QUERY-001.md)
