# OntologyPlatform · Codex Master G2 首个 AI Native 本体纵向闭环实施授权 V1.0

> **授权类型：G2-THIN-SLICE-001，执行模式（非 Plan-only）。** 本文件需要用户在 Codex 会话中明确发送“正式授权执行本文件全部 G2-THIN-SLICE-001 任务”。它不是项目功能已经通过验收的声明。
>
> **研发主机：** macOS ARM64；**项目：** `/Users/chasen/Developer/repos/ontology-platform`；**仓库：** `on-dotnet/ontology-platform`。
>
> **已独立核对的基线提交：** `6154ebb3703031a49cf0c555c9f0c3596e3b7726`；**对应 GitHub CI：** `40221202302`（两个 Job 成功）。正式开工前重新 `git fetch` 并核对 `origin/main`，如远端已经前进，先保护现场并对账，不回退、不强推。
>
 **推荐 Codex 运行配置：** Master 使用 **GPT-6.1 Sol / High / 普通执行模式**；复杂 OWL/SHACL、发布一致性与安全独立 Reviewer 推荐 **GPT-6 Astra / High**，真正疑难安全或并发问题可临时升到 Extra High；前端实施与遥测集成推荐 **GPT-6.1 Sol / Medium–High**。如果当前 Codex 无法对每个子 Agent 指定模型，保持 Master 的 Sol / High，优先通过独立 Review 和可重复测试保证质量。

## 0. 当前阶段审核与历史约束

上一关口 `G1-CLOSE-001` 的两项 P1（审计成功读取留痕、多厂区范围；安全结构化异常诊断）已经通过审查：上传 ZIP 成员校验、实际代码与负例、最终同 Head Linux CI 均已核对。

**精确状态：** G1 已交付的开发基础能力可以作为 G2 的依赖基线；历史总体状态仍是 **PARTIAL**，不得改写为“G1 全部 PASS”或“生产就绪”。Windows/Intel Mac 原生、完整镜像 CVE/SBOM/签名、生产证书轮换/HA/SLO/RPO/RTO、Faro/Product Analytics、完整中文业务运维等保持其真实的 `NOT_RUN/NOT_VERIFIED`。**发布 Outbox 必须在本次 G2 真正的发布事务中实施并验收**，不得因为历史 G1 未实施而跳过。

这是用户批准的 G2 最小纵向业务闭环。**允许在 G2 内部分阶段迭代、并行实现、集成与反复测试**；不要求每个小任务单独等待人类批准。但任何新的实质架构变更、尚未批准的第三方产品/依赖、付费模型或生产凭证、机器/管理员级修改、生产环境访问、越界操作都必须先报告并请求明确授权。完成 G2 后停在审查关口，不自动开始 G3–G8。

开始前必须完整读取：

- 根 `AGENTS.md`、`PLANS.md`、`.codex/config.toml`、适用目录的 `AGENTS.md` 和 `.codex/agents/`；
- `docs/bootstrap/ontology-platform-codex-master-plan-bootstrap-v1.0.md`；
- `docs/tasks/current-authorization.md`、G0/G1 的任务/ADR/交接及最近验收证据；
- `docs/planning/02-target-architecture.md`、`03-module-feature-matrix.md`、`04-roadmap-and-dependency-dag.md`、`06-spikes-and-acceptance.md`、`g1-closeout-acceptance.md`、`g2-readiness-readonly.md`；
- `docs/contracts/g1-platform-contracts.md` 和现有真实 API/OpenAPI、开发部署手册、审查包规范。

历史文档保留原状态，新授权单独写在 `docs/tasks/current-authorization.md` 顶部及本次任务卡中；不要重写过去的验收历史。

## 1. 绝对不可改变的产品与架构边界

1. 平台通用，首个可信合成样例采用冶金炉次 → 浇次 → 板坯 → 轧制事件 → 钢卷，但工程基建与核心模块名称不绑定冶金行业。
2. 正式本体使用 RDF/RDFS/OWL 2、Turtle；约束用 SHACL 1.0，词汇 SKOS，来源语义 PROV-O。**不使用 TMDL，不以 JSON/TypeScript/EF 实体替代 OWL 权威表达**；不引入 Microsoft GraphRAG、Agent 365 或未经批准的第二图数据库。
3. .NET 10 / ASP.NET Core 10 / EF Core 10，模块化单体、Pragmatic Clean Architecture、Vertical Slice；Domain 纯净，模块独立 DbContext 和写入边界，直接使用 DbContext 和显式映射，不引入 AutoMapper 或通用 Repository/UoW。
4. Jena/Fuseki/TDB2 是批准的 RDF 语义查询运行时；RustFS 存不可变发布制品；PostgreSQL 存草稿/治理/版本/审计/Outbox；Ontology Query Gateway 受控执行，不允许 Agent 生成任意生产 SQL/SPARQL 并自由执行。
5. Next.js + React + TypeScript + Tailwind + shadcn/ui/Base UI + 自研彩色 Design System；不引入 Ant Design/Fluent UI 组件体系，不复制 Tailwindadmin 商业源码。Cytoscape/Monaco 的精确引入方式和许可/版本必须先按已批准技术方向登记、验证；不得为演示偷偷换一套无法维护的编辑器模型。
6. 复用当前 Keycloak/OIDC/YARP BFF/CSRF/授权会话；SSE 采用 .NET 原生机制和持久化执行事件，人工审批必须走独立受控 Command API；MAF 和 MCP C# SDK 必须通过已确认真实版本兼容性检查，不假设框架特性已经运行。
7. 保留 `ILogger`/`LoggerMessage`、OpenTelemetry/Alloy/Loki/Tempo/Prometheus/Grafana、独立 PG 审计；所有新增核心能力必须可记录 Trace、版本、Evidence 和健康状态。
8. 所有手写 C# 类型、方法、属性、字段、枚举和成员必须有**准确中文 XML 文档注释**；关键局部变量有说明；成员之间留空行，XML 注释紧邻 Attribute/声明。TypeScript 复杂逻辑有中文 JSDoc/TSDoc；遵守 EditorConfig、分析器与既有 CI。
9. 官方或微软推荐包优先，第三方必须提前列名称、维护者、版本、许可证、安全/商用及用途，获准后才能引入；不靠隐式框架和魔法约定替代显式代码。
10. 原始企业五类数据源保持只读；G2 可以使用经确认的 **Local/Synthetic** RDF 实例和数据集，不引入真实生产凭证，不假称完成 G4 的五源访问。

## 2. 目标：一个真实、可测试、可回滚的 G2 纵向业务闭环

在同一已发布语义模型、同一安全身份上下文、同一共享执行与证据体系下完成：

**可信示例本体导入/创建 → 类/属性/关系编辑 → Turtle 与画布/表单真实对应 → 草稿保存与 revision 冲突 → SHACL 正反例验证 → 变更 Diff → 提交独立人工审核 → 生成哈希校验的不可变本体包 → Jena 版本图部署与回读验证 → PostgreSQL CAS 激活 + 同事务审计和 Outbox → 通过 BFF/REST 和 MCP 查询正式本体及有来源的实例/谱系 → Agent 通过受控工具做最小真实问答 → 浏览器 SSE 接收流式事件/证据 → 回滚旧版本并重新查询；运行中已固定版本不混用**。

采用至少五类合成类：`Heat`、`CastingSequence`、`Slab`、`RollingEvent`、`Coil`，具备属性与对象关系；材料谱系不能暗中硬编码 Slab→Coil 一对一。至少构造一对多的轧制关系、缺失关系或非法值负例，以及两个厂区可能出现相同外部编号的身份歧义样本。所有实体记录标记 Synthetic，属性/关系/证据含 `sourceId`、`sourceRecordId`、有效时间、观察时间及模型/映射版本的明确适用边界。

不能用纯网页 Mock、预先硬编码的 Agent 回答、只写 RustFS 文件却未 Jena 部署、只将画布 JSON 存 PG 等手段冒充端到端闭环。对真实 LLM 的调用须经过模型 Provider 安全策略；若没有已批准可用模型，保证确定性工具路径可以验收，但 **真实 AI 模型调用标记 BLOCKED / NOT_VERIFIED，不能把 G2 完成度写为完全 PASS**。

## 3. 首先由 Master 完成共享合同冻结（单写者）

在发放写入任务之前，**Master 必须产出并独立复审**最小且可执行的 G2 契约/ADR，包含以下内容。沿用 G1 已冻结公共合同，不能重复造 `Result`, `EvidenceRef`, `ExecutionRun` 等第二套互不兼容的模型。

- `OntologyDraft`：草稿 ID、所属组织/厂区、Base Release、revision/ETag、Turtle 与 Shapes 内容哈希、owner/审计；源码存储方式要明确；
- `SemanticValidationReport`：校验类型、严重度、focus node/path、模型 hash、来源及阻断规则；区分 OWL 逻辑、公理支持边界和 SHACL 约束，不宣称“Fuseki 自动 SHACL 验证”；
- `ReleaseManifest`、`AssetVersionSnapshot`：ontology/shapes/vocabulary hash，import locks、graph IRI、映射/指标/规则/能力关联版本（G2 未实现的资产应诚实标明 absent，不填假版本）；
- 审批状态机与修订绑定：提交者与批准者分离，审批绑定草稿 revision、完整内容 hash、scope 与有效期；修改草稿后原审批失效；
- 发布状态机：PREPARE → VERIFY artifacts → DEPLOY isolated named graph → VERIFY graph and SHACL/query → PG CAS 激活 + audit + Outbox → POST-ACTIVATION 调和；失败保持旧 active，有重试/幂等；
- `SemanticQueryPlan/Result`：许可概念/关系、查询深度/超时/行数预算、来源/版本/时间、`FOUND/EMPTY/PARTIAL/UNAVAILABLE/UNAUTHORIZED/AMBIGUOUS` 适用状态；
- `SemanticCapability`：用于受控 REST/MCP 工具的输入/输出 Schema、业务意义、权限、执行器和版本，Agent 不直连 Jena 管理端点；
- `ExecutionRun` 与 SSE Event：runId、固定 snapshot、单调 seq、eventId、eventType、schemaVersion、持久状态、Last-Event-ID 重放、终止/取消/断线恢复及审计；
- Web/BFF/REST/MCP：同一 AuthorizationPolicy、输出和证据引用类型；新增所有 API 的 OpenAPI 3.1 生成与 TS SDK/显式映射检查；
- 本体/Shape 编辑边界：G2 允许编辑的 OWL 子集、源码 round-trip 的未知公理如何完整保留或阻断；未支持的表达式不得默默丢失；
- Jena SHACL 工程方案：使用有证据的 Jena 官方 API、CLI 或受控适配方式，说明实际执行路径、输入边界和测试；新增 Java 验证进程/依赖如果需要架构扩展，先给 ADR 和 PoC，不自行添加重量级组件。

新增依赖和系统边界先登记/核实，冻结版本与许可证。接口路径优先复用 `docs/planning/g2-readiness-readonly.md` 已建议路径；准确版本与契约最终以本轮代码真实 OpenAPI 为准。**不允许多个 Agent 各自创造 DTO、迁移、release manifest、版本规则或 Design Tokens**。

## 4. 多 Agent 并行实施方案（任务依赖与写入所有权）

Master 先建立 `docs/tasks/G2-THIN-SLICE-001.md` 和实际任务卡、owned_paths、read_only_dependencies、依赖 DAG、Reviewer、验收/停止标准；小步持续提交、推送并集成已验证成果。逻辑岗位不等于同时并发数，使用 Codex 可用并发 2–3 个写入任务加独立只读审查；共享文件必须 Single Writer。

| 子任务 | 具体责任 | 可并行前置 |
|---|---|---|
| **G2-SEM-001** | 标准 OWL/RDF/Turtle 本体草稿模型，真正 Jena/SHACL 校验 PoC、实体类/关系及样例验证、语义保真测试；Domain 独立，适配器受控 | 首批，在共用契约冻结后 |
| **G2-FE-001** | 复用 G1 Shell、权限、主题，最小本体目录/三栏编辑或真实可编辑工作区、检验报告、发布审核/查询/Agent 流式工作区；不得以静态 HTML 代替 API | 与 SEM 并行，先冻结 UI DTO、状态、Design Tokens 的 Owner |
| **G2-PUB-001** | 独立发布提案、审查、RustFS 不可变对象、Jena Named Graph、PG CAS、Outbox、版本固定/回滚；迁移及公共 release schema 独占 | SEM 最小验证 + 版本合同后 |
| **G2-QRY-001** | 受控 Gateway、能力注册、身份/范围/关系查询、预算、六态结果与 EvidenceRef，正式发布源校验 | SEM + PUB 的正式图与版本可用后 |
| **G2-AI-001** | MCP C# SDK、MAF 最小工具编排、Provider 策略、PG ExecutionRun/事件、原生 SSE 流与恢复、工具安全、中文过程/证据展示；不代替确定性 Gateway | 冻结能力合同及 QRY 可用；部分 UI SSE 组件可先并行 |
| **G2-QA-001** | 独立语义、授权、安全、性能、故障恢复与真实端到端审查；基于固定提交而非实现者自报 | 每个关键关口以及最终集成 |

建议内部至少三次可验证集成里程碑：

- **S1 Semantic Working:** 创建/修改持久草稿 → Turtle round-trip → 真实 SHACL 正/负例，源/图/表单对齐，无未批准推断。
- **S2 Safe Release:** 严格审批 → RustFS/Jena 版本部署与 PG CAS + 同事务 audit/Outbox → 故障注入 → 回滚及历史查询快照无混版。
- **S3 AI Native:** REST/MCP 从正式版本执行受控业务能力 → Provider/Agent → 持久执行记录/SSE/证据 → 浏览器及独立验收。

S1/S2/S3 是本次 G2 授权内部集成门禁；其间 Master 可根据合同稳定情况滚动分派多个 Worktree，但 S2 不得绕过 S1 正确性，S3 不得绕过 S2 的正式发布语义。若阶段发现根本性设计或安全阻断，停止受影响链路，不用 Mock 伪造 PASS。

### Git 与上下文协作

- `main` 的集成与推送只由 Master 负责；子 Agent 各自独立 Git Worktree 和 `codex/G2-...` 分支，不共用正在写入的工作目录。
- 可验证小里程碑及时 Commit/Push 远程任务分支；未完成的提交标 DRAFT/PARTIAL，不把推送当通过。
- 根 `AGENTS.md`、`PLANS.md`、CI、锁文件、公共契约、Migration、AppHost 与 Design Tokens 的编辑权限在任何时刻只属于一个明确 Owner。
- 每次集成前 fetch、确认远端状态；独立 Reviewer 检查本次实际 Commit+Diff+测试/安全证据；Master 才集成并 push `main`，不强推、不 reset --hard、不删除含未合并成果的 Worktree。
- 分阶段将已验证源码、任务卡、接口、测试与监控一起提交，绝不在最终验收前才第一次合并前后端。

## 5. 必须完成的功能与失败分支

### A. 可信本体与草稿

- 中文优先资产页可创建/导入可信最小本体；G2 默认支持 Class、subClassOf、datatype/object properties、domain/range、label、注释及简单个体断言等已声明基础编辑子集；复杂 OWL/本体导入公理的保留/只读/阻断范围必须公开说明并测试。
- UI 编辑对应真正标准 RDF/OWL 资产与 revision，不将图拖动位置视作语义变更；取消、Undo/Redo（若暴露）、保存/刷新/重进可复现。
- 草稿修改前后 Diff、作用范围和版本可见；并发旧 revision 保存返回 409，不得静默覆盖。
- SHACL 真正执行：合法样本通过，缺业务键/非法关联/非法值能够定位 focus node、path 和 message；OWL 开放世界与 Shape 闭世界规则在 UI/代码中不能混淆。

### B. 发布、审核、恢复

- 草稿通过约束和查询用例后可提交审核；未经审核/角色不符/批准后发生修改均禁止发布；不同主体审批的正负例必须真实执行。
- 发布制品字节与 manifest SHA256 对账，RustFS 对象提交、Jena 隔离图加载及只读查询回验全部就绪后，PG CAS 同事务切换 `activeRelease`、记录审计和 Outbox。
- 发布失败：RustFS 不可用、Jena 写入或回验失败、审计/Outbox/PG 提交失败、并发发布、客户端重试或提交响应丢失，**不得指向缺失或错版制品**；需明确补偿或幂等恢复。
- 旧版本激活及历史图不能被回滚逻辑删除；新请求读取最新活动发布，已存在 `ExecutionRun` 固定旧 snapshot。

### C. 查询、MCP、Agent 与 SSE

- REST 的 `describe_ontology`、`resolve_entity`、`traverse_relationships/trace_material` 首个受控执行器必须从发布版本图及有来源样例读取，禁止把未知事实编造为存在；身份歧义返回 AMBIGUOUS，源不可用与 EMPTY 严格不同。
- Gateway 强制鉴权、组织/厂区数据范围、版本、查询路径、深度、行数、时间、资源限额；不能向公共 Agent 工具暴露任意 SQL、SPARQL Update 或 Fuseki 管理 API。
- 证据返回可指向标准图/源对象/数据版本，业务查询/API/MCP/Agent 采用同一个可信 EvidenceRef，证据打开时再次授权，不能因为在 Agent 答案中引用就允许绕过权限。
- Agent 使用正式工具 Schema，模型只负责解释与选择；不得绕过审批写入已发布资产。若无真实模型凭证，用安全的可替换 Provider 或明确标记的 deterministic harness 测工具管道，**模型真实调用另列未完成**。
- SSE 至少支持 `run.started`、`tool.started`、`tool.completed`、`evidence.added`、`message.delta`、`approval.required`（确有人工动作时）、`run.completed/failed`；关键事件先持久化再发送，序号单调、断线重连去重/游标/快照、明确取消行为；YARP/BFF 不缓存事件流。批准/拒绝独立 REST Command，不能通过 SSE 改变业务状态。

### D. 监控、审计、安全和前端体验

- 每次关键命令留独立 PG 审计；登录/资源旧链路回归不退化。本体发布、审批、回滚、查询工具、Agent Run、SSE 的结构化日志/OTel/Trace 与中文运维入口可关联。
- 不把用户正文、Prompt、工艺文档、令牌、连接串放入 Loki/Tempo/Prometheus 标签或普通日志；高基数标签和泄露负例纳入测试。
- Web 页面真实加载、空数据、无权、404、409、源不可用、部分失败、延迟/取消、模型未配置等状态正确；深浅主题、1440/1280/390布局、键盘焦点/ARIA、SSR 水合及跳转闭环通过。前端编辑器的新第三方依赖必须先登记授权/许可。
- 本体相关业务运维页至少可从发布/查询/Run 记录进入对应诊断和 Trace；完整运维产品不在 G2 必须一次完成的范围。

## 6. 自动化测试与不可绕过的门禁

至少建立以下真实且可复现的测试与脚本入口（如脚本名尚不存在则在本轮建立并标注真实范围）：

1. `semantic-roundtrip`：Turtle/OWL 公理合法性、RDF 图同构或明确支持子集、语言标签/空白节点/import 边界、未知公理零静默丢失。
2. `shacl-validate`：合法、缺字段、非法类型/关系/范围及校验报告定位；Jena 真实执行，不以假 JSON report 代替。
3. `draft-revision`：保存、并发修订冲突、跨厂区/角色授权、修改后审批失效。
4. `release-faults`：RustFS、Jena、PG/CAS、审计和 Outbox 逐点故障注入；旧活动版本保持有效、重试幂等、回滚查询一致。
5. `query-plan`：合法关系与来源路径、歧义、空结果、无权、不可用、限额、证据二次授权。
6. `mcp-agent`：真实运行的 MCP Server、受控工具发现与调用、Agent 错误/超额/注入防护；无真实模型时明示未验收的部分。
7. `sse-replay`：首事件、连续 Delta、终态、断线恢复、`Last-Event-ID`、慢客户端、取消/超时、YARP 代理不缓冲。
8. `full-g2-e2e`：从 Web/身份登录到草稿、验证、异人审核、发布、REST/MCP 查询、Agent/SSE 回答、证据、回滚、重新查询，至少一条全链与必要负例。
9. `g1-regression`：受锁 .NET/Web 构建、MSTest/安全回归、OpenAPI、身份/OIDC/CSRF、PG 审计、LGTM 关键关联、Mac 本地运行及 Linux CI。
10. `performance-baseline`：API、SPARQL/SHACL、发布及 SSE 的可重复实际样本/延迟记录；在尚无正式 SLO 前不编造生产性能阈值。

使用当前仓库真实 PowerShell/Python 验证入口和 MSTest/Microsoft.Testing.Platform，必要时补强脚本，但绝不删减既有门禁来获得绿灯。同步提交真实测试输入、实际命令、退出码、日志、Trace/状态、测试环境、失败和修复证据。无测试、无模型、无生产凭证时必须标 `NOT_RUN/NOT_VERIFIED/BLOCKED`。

## 7. 必须提前报告的风险

- **SHACL 如何由 Jena 正式执行**：Fuseki 的普通 SPARQL endpoint 不等于自动具备 SHACL 校验；先 PoC 并以实际 Jena API/CLI 方案和兼容性证据决定适配。
- **强保证的发布一致性**：PG 与对象存储/Jena 没有跨服务 ACID，必须采用隔离制品、就绪检查、CAS 和幂等调和，禁止“成功返回但图尚未生效”。
- **身份语义**：`owl:sameAs` 等形式语义不等于业务键一一对应；两个厂区重复编号不能被简单字符串 Join 自动合并。
- **模型使用和费用**：不自动调用外部收费模型或更改组织策略；提供离线可复检工具级用例，并将真实模型端到端验收单列。
- **Cytoscape/Monaco 与下一版 shadcn 组件**：已在产品层面确定使用方向，具体新增包、许可证/商用、版本、SSR 边界和性能要求先登记与验证。
- **发布性能与历史版本保留**：图、对象和证据在回滚/长期运行时不可过早 GC；先定测试与引用策略，生产保留周期待实际批准。
- **Windows 原生、Intel Mac、生产镜像、HA**：沿用原 `NOT_RUN/NOT_VERIFIED`，不要冒充 G2 当轮已通过；不得因没有这些环境阻止可独立完成的 Mac/Linux G2 工程研发。

## 8. 必须交付的工程结果

- 实际 .NET 源码、Web 页面、最小 RDF/OWL/SHACL 标准资源，必要的 Java/Jena 适配器（如通过 ADR）、PG/RustFS/Jena 配置、正式的最小 Schema Catalog/Capability Registry、REST/MCP/SSE 契约；
- 不可变发布与回滚的 PG/CAS/Outbox 工程和迁移、真实权限/审计/证据引用实现；
- 可通过验证脚本一键复现的 Docker/Aspire 开发链路和完整 G2 E2E；
- ADR、架构/时序图、开发/中文运维指南、失败恢复方案、依赖许可/供应链清单、必要的中文注释；
- `docs/tasks/G2-THIN-SLICE-001.md`、分工与 Task DAG、`docs/evidence/G2-THIN-SLICE-001/` 的原始证据、独立 Reviewer 审查与缺陷关闭记录；
- 更新 `docs/tasks/current-authorization.md` 的 G2 授权索引和 `docs/handoffs/` Master 当前进展；保留历史不覆盖；
- Git 分支/Worktree 清单、BaseSha、HeadSha、远程推送和同 Head CI 真实记录。`main` 当前未保护则记录风险，不未经批准修改仓库设置；
- **按现有 `docs/development/review-package-spec.md` 自动生成唯一标准 Review ZIP**，从已提交 Head 全量源树+Base..Head 完整 diff+真实测试/运行证据构包，排除 `.git`、私有凭证、数据库/容器卷、模型权重、缓存与生产数据。重开逐成员 SHA256/安全路径及 diff 对账。ZIP 放于忽略的 `artifacts/reviews/`，不要 Push ZIP。

**统一终态：** `G2_THIN_SLICE_READY_FOR_REVIEW`。

最终以中文汇报：阶段状态 PASS/PARTIAL/BLOCKED（按真实事实）、实际完成闭环、未完成原因、每项测试命令/退出码、独立审查结论、Base/Head/main 的完整 SHA、CI Run ID/结论、Worktree/任务分支和 Review ZIP 的绝对路径、字节数与 SHA-256。完成后必须停止，不自动开展 G3–G8。
