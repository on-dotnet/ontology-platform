# 本体智能平台｜Codex Master 首次会话启动提示词（Plan Only）

> 版本：V1.0 · 2026-10-23  
> 状态：交由 Codex 执行 **G0：仓库审计 + 实施计划**；尚未授权开发、迁移或改写代码。  
> 使用方式：在实际项目仓库中打开一个新的 Codex 主会话，选择 **Plan 模式**（客户端支持时可用 `/plan`），把本文件全文作为首次任务输入。  
> 最终审批：Codex 输出计划后，**先交回 ChatGPT 审查**；审查通过后，再发送下一轮“批准实施 / Master 执行”的专用提示词。  
> 文件内容是项目负责人已确认决策的工作基线。仓库当前状态必须通过实际审计得出，不能因为本文件提到旧版源码就推断这些源码在当前分支仍然存在。

---

## 0. 你的角色、当前授权和禁止事项

你是本体智能平台研发项目的 **Codex Master / Chief Architect / Delivery Planner**，负责制定计划、组织专项审计、厘清依赖、控制风险、规划分工和集成验收；你不是可以绕过用户审批的独立项目所有者。

**本轮是 G0 / PLAN ONLY**：

1. 首先读取当前仓库根目录及相关子目录的 `AGENTS.md` / `AGENTS.override.md`、已有计划/ADR/需求文档、Git 状态以及已有脚本，再进行审计。全程优先只读分析。
2. 使用当前客户端实际可用的 Codex Subagents，将相互独立的只读审计并行委派给最多 **3–4 个**专职 Agent；若能力不可用，单 Agent 顺序完成，并在报告中说明。等待全部审计结果后，由主会话交叉验证、汇总成一份计划。
3. **不得**擅自创建代码、迁移数据库、安装/升级依赖、删文件、格式化整个仓库、重构、切换/强制重置分支、执行生产连接、改写旧本体、运行破坏性命令、部署服务或启动大规模并行实施。
4. 计划阶段可以读取源码、锁文件、测试目录和架构文档；可以运行无副作用的环境查询与静态只读检查。不能把历史文档描述视作实际测试通过。需要执行可能更改文件或外部状态的验证时，先列为“待授权的验证任务”。
5. 可以在回答中生成 Markdown 的计划全文及建议文件内容；**Plan 模式若不允许写文件，不要绕过它去修改仓库**。计划交付时提供可以保存的准确目标路径，并把重要内容呈现在当前会话中。
6. 不得把用户先前明确排除的 TMDL、Microsoft GraphRAG、AutoMapper、通用 Repository、Ant Design 或 Fluent UI v9 默认重新引入。
7. 如仓库发现与已确认方案冲突：列出证据、影响、推荐迁移策略和决策点；本轮不修改原文件。不允许以“重写更快”为理由忽略可复用成果。
8. 计划完成后停止，明确输出 `G0_PLAN_READY_FOR_REVIEW`，不得自行进入 G1。

**重要：主会话负责协调，子 Agent 负责范围受限的工作。** 不能声称存在一个官方内建的“永久 Master 权限”，也不能假定几个互不关联的 Codex 会话会自动共享所有上下文。真正的协作契约须落在任务卡、仓库文档、Git、计划与验收记录中。

---

## 1. 产品目标（已确认，不再反复征询）

建设面向企业自有机房、可商业应用、可扩展至多行业的 **AI Native 本体与知识智能平台**。

首期业务以冶金 **炼钢/精炼 → 连铸 → 轧制** 的质量异常根因分析为验证场景，平台自身不能硬编码为冶金专用。首期为生产企业只读查询，不向 MES/QMS/ERP/设备或现场生产系统写回。

**核心六类资产**：

- 本体定义：RDF/OWL 语义、公理、实体类型、属性、关系、身份、时态/事件语义，以及配套 SHACL、SKOS 等标准资产；
- 业务事实：源数据库和必要的实例图谱，不把所有源表物化成 RDF；
- 文档知识：文档、术语、规则依据、片段、图谱抽取候选及 Evidence；
- 语义映射：外部 Schema 到本体类型、属性、身份和关系的映射；
- 指标与规则：受治理的语义定义、计算或评估契约及其版本；
- 可执行语义能力：统一查询、指标、规则、知识发现及 MCP/REST/Agent 消费能力。

**产品功能覆盖 14 个模块**（规划需给出完整覆盖和依赖矩阵）：

01 本体资产中心；02 本体设计中心；03 术语与标准中心；04 AI 本体构建中心；05 文档知识中心；06 数据连接与映射中心；07 实体与知识图谱中心；08 语义验证与推理中心；09 本体发布治理中心；10 统一语义查询中心；11 指标与规则中心；12 MCP 与智能体中心；13 业务智能应用中心；14 平台治理、审计、行为分析与中文运维中心。

注意最后编号仅代表本轮统一的模块清单，具体页面 IA 可以按业务任务合并导航，不允许按14个模块机械生成14个大菜单。需有功能清单、角色、页面、交互、接口、状态和验收逐级对应。

**必须有三个端到端业务闭环**：

- **A 本体治理**：设计/导入 → 验证 → 数据绑定 → 影响分析 → 审核 → 发布 → 查询生效 → 版本/审计/回滚。
- **B 文档知识建模**：上传 → 解析/OCR → 抽取候选实体关系/规则 → 消歧/证据 → 专家审核 → 进入草稿或知识资产 → 发布/可检索。
- **C AI 业务分析**：提问 → 语义发现 → 工具规划 → 授权与跨源查询 → 指标/规则/文档证据 → 假设验证/反证 → 解释性结论 → 反馈优化。

**可落地的首个演示问答**：用户问某 Q235B 钢卷出现异常的可能原因，Agent 应经由正式本体发现 `Heat`、`CastingSequence`、`Slab`、`RollingEvent`、`Coil`、`InspectionResult`、`QualityIssue` 等语义关联；使用授权的源数据、指标、规则和规程给出带证据及不确定性标识的结果。禁止将相关性直接当因果性。

---

## 2. 冻结技术决策（任何调整必须提出 ADR 和理由，等待审批）

### 2.1 本体、查询、数据

| 领域 | 方案与边界 |
|---|---|
| 正式语义 | W3C RDF / RDFS / OWL 2；Turtle 为主要源码格式；不以自定义 JSON/TypeScript 或 TMDL 充当本体权威定义 |
| 数据约束 | SHACL 1.0 为稳定基准；OWL 逻辑推理与 SHACL 数据验证职责分离 |
| 词汇与证据 | SKOS、PROV-O；OWL-Time 按需要引用；保持标准语义可导入导出 |
| RDF 引擎 | **Apache Jena + Fuseki / TDB2** 已获准重新进入项目，作为首选；必须做语义、性能、部署、备份/恢复 PoC；RDF4J 仅作回退备选 |
| 虚拟映射 | Ontop 可插拔，适合的数据源才用；并非所有数据库必须经 Ontop |
| 查询网关 | 自研 Semantic Query Gateway 负责逻辑计划、授权、预算、路由、跨源合并、证据/来源、时效、状态区分 |
| 原始数据 | 首批：PostgreSQL、Oracle、Doris、TDengine、Web API；只读、真实配置、连接测试、Schema 探查、映射/分页/超时/限流闭环 |
| 数据分层 | PostgreSQL 保存平台元数据与审计；Jena 保存已发布语义图与必要物化事实；RustFS 保存正式发布包/文档/证据原件；原始业务事实可保留在外部源 |
| 数据身份 | 全局 IRI、跨厂编码、同名异物、历史编号、关联有效期、冲突消歧必须设计 |
| 指标和规则 | 独立版本化语义资产，与正式本体关联；指标计算与规则执行由确定性服务实现，不直接塞入 OWL；不能用 LLM 解析替代合规判定 |
| MCP | REST 与 MCP 复用统一语义能力注册和执行网关；工具有版本、入参/出参 Schema、授权/预算和证据契约 |

### 2.2 前端、UI、交互

- Next.js 16 App Router、React 19、TypeScript、Tailwind CSS 4、shadcn/ui（Base UI 新代码首选）、可维护的自研 Design Tokens 和组件体系。
- 参考 Tailwindadmin Next.js Dark 演示的**彩色企业后台视觉设计体系**，自主开发、可商用；不得复制商业模板源码。保留优秀的微软式信息密度/交互思想，但 **Fluent UI v9 和 Ant Design / Ant Design Pro / Umi 不作为组件依赖**。
- UI 必须有统一 Enterprise Shell、模型三栏工作区、查询/分析工作区、AI 工作区，支持深浅主题、中文、可访问性、错误/空数据/加载状态。
- Cytoscape.js：本体结构图/实例图；Monaco：Turtle、SHACL、Diff 源码；ECharts：统计/运维图表；TanStack Query、Zustand、React Hook Form + Zod、TanStack Table；pnpm + Turborepo；Playwright / Vitest。
- 用户要求全部重要交互闭环，不接受展示性的假按钮；Mock 仅限获准原型阶段，生产功能与 Mock 必须明确区分。
- AI 交互默认 **SSE 流式**：结构化事件 `run.started/message.delta/tool.started/tool.completed/evidence.added/proposal.created/approval.required/run.completed/run.failed`；长任务须保存事件/运行状态，并提供断线重连与必要的游标恢复机制。人工审批采用独立 Command API。

### 2.3 后端、架构与实现

- **.NET 10 LTS + C# + ASP.NET Core 10 + EF Core 10 + PostgreSQL** 为主技术栈，尽量使用微软维护的官方包；第三方必须登记、解释引入理由并取得审批。
- **Modular Monolith + Pragmatic Clean Architecture + Vertical Slice + 按复杂度采用 DDD + 轻量 CQRS**。不机械建立一堆层和接口；Domain 不依赖 EF、HTTP、Jena、LLM SDK。
- 每模块拥有自己的数据写入边界、DbContext/Migrations/接口契约；简单 Application 用例可直接使用本模块的 EF Core DbContext；避免共享巨型 DbContext 和跨模块直接修改表。
- **禁用 AutoMapper、通用 IRepository<T> / GenericRepository / 冗余 IUnitOfWork 包装**。普通 DTO 使用显式 C# 属性映射，数据库查询优先 LINQ Projection；数据映射引擎是不同的业务能力，不受这条限制。
- `Platform.AppHost` + `Platform.ServiceDefaults`（Aspire 用于服务启动默认配置）+ 独立 `BuildingBlocks` + 基础设施 Adapter。`ServiceDefaults` 不是通用业务 Shared Kernel。
- **YARP** 用于集成式 .NET 公共入口、BFF/OIDC；首期不需要再部署独立网关微服务。Keycloak + OIDC、服务端身份会话、HttpOnly Cookie、CSRF、服务端资源权限、多实例 Data Protection 密钥共享。
- 系统 API 使用 .NET 原生 OpenAPI/ProblemDetails/`IExceptionHandler`/`ILogger`/`System.Text.Json`，依赖注入与 `Options.ValidateOnStart`、`TimeProvider`、`IHttpClientFactory` + 分业务 Resilience、RateLimiting、`CancellationToken`、结构化错误和健康检查。
- .NET 高性能日志优先 `LoggerMessageAttribute` 源生成；源生成 JSON、显式数据映射、EF Core 只读投影；性能优化以 Benchmark / 真实性能测试为依据。
- `Microsoft.Extensions.AI` + Microsoft Agent Framework；自建模型 Provider 适配企业私有模型、千问、GLM、Kimi、DeepSeek 等；Agent 不直接持有生产数据库任意读写权限。
- MAF Agent/Workflow 负责确需 AI 的任务，确定性事务/发布/规则计算由 C# 执行；Checkpoint 与 `ExecutionRun` 的多实例可靠持久化必须专项验证；增加 AI Evaluation 与受控 Tool Guard。
- Python Worker 用 MarkItDown + PaddleOCR 做文档转换/OCR，抽取产物必须作为候选知识入审核；禁止重新引入 Microsoft GraphRAG。
- 主后端使用模块化单体，Jena/Ontop/文档 Worker 是必要专业组件；不预设微服务、Kafka、Kubernetes 或第二套 Neo4j 图数据库。

### 2.4 工程、日志、审计、运维

- Aspire `ServiceDefaults` 用于共通 OTel、健康检查、服务发现和 HTTP 弹性；`BuildingBlocks` 用于必要公共契约与设施。
- Grafana **Loki + Tempo + Prometheus + Alloy + Grafana**（LGTM）；Faro 用于 Web RUM；Pyroscope、Mimir 按业务需要/HA 门槛引入，不默认过度建设。
- 平台自建**中文运维工作台**：服务健康、语义查询执行树、Jena/Ontop、MCP/Agent 工具步骤、文档流水线、指标规则、告警事件、审计和用户行为分析。Grafana 负责专业诊断，支持中文优先显示和 SSO。
- **审计独立于日志**：PostgreSQL 持久化审计和 Outbox，核心修改/发布/安全操作不可采样丢失；记录角色、资源、前后摘要、理由、版本、Trace、时间；按规定归档与恢复。
- **用户行为分析独立于 RUM**：经同意/授权的产品事件（功能使用、完成率、漏斗、AI 建议采纳率等），不得收集未脱敏的敏感输入、AI 对话或源业务记录。
- 后台：`BackgroundService`、`Channel<T>` 适用于短暂队列；PostgreSQL Outbox 解决可靠事件；Hangfire **保留可验证候选**，需澄清是否需要持久化调度、与 Outbox/MAF 的边界；RabbitMQ 按跨服务异步需求决定。
- API SDK：优先 PoC 微软 Kiota；如果 Next.js/TanStack Query 结合不利则可以采用 Hey API，但属第三方依赖需明确登记。
- 默认后端测试优先 MSTest + Microsoft.Testing.Platform，真实基础设施测试可使用 Testcontainers（第三方须登记）；前端 Vitest/Playwright；架构测试、契约测试、性能测试、AI Eval、权限/故障注入必须规划。
- 私有化、多实例、备份恢复、RPO/RTO、供应链审计、SBOM、开源/商业许可、离线部署是生产验收条件。

### 2.5 注释及代码规范（项目加严要求）

- C# 使用微软 XML Documentation Comments：`/// <summary>`、`<remarks>`、`<param>`、`<returns>`、`<exception>`；以简体中文描述业务含义，代码标识符采用微软 C# 英文命名规范。
- **所有手写类型、接口、业务实体/值对象/聚合、枚举和每个枚举成员、属性、字段、常量、方法、构造函数及重要变量均有有意义的注释**。复杂关键逻辑解释业务依据、算法假设、边界条件、单位、时间、幂等、事务和恢复。对简单局部变量也应提供简短有意义的说明；不得用只重复变量名的空注释凑数。自动生成文件豁免。
- 属性和成员之间保留一个空白行；XML 文档注释需紧贴对应的 Attribute / 声明，不能在 XML 文档块和目标成员间插入无效空行。遵循微软 `.editorconfig`、Roslyn、Allman 大括号、4 空格缩进、Nullable/分析器、`dotnet format` 和项目自定义格式规则。
- 前端重要组件、Hooks、领域类型、复杂算法使用 JSDoc/TSDoc；中文业务说明，风格统一。接口/领域名需加入术语字典，避免 `Heat/炉次/熔次` 等歧义。
- 编译器 `CS1591` 只覆盖公开成员；私有成员、局部变量和项目格式采用必要的自定义分析/人工评审，不得声称微软编译器能直接强制全部项目规则。

### 2.6 明确不采用（禁止默默复活）

**TMDL；Microsoft GraphRAG；Agent 365 依赖；自定义 JSON/TS 作为本体权威；AutoMapper；通用 Repository/UoW 模板；Ant Design / Ant Design Pro / Umi；Fluent UI v9 作为正式组件库；LLM 自动发布正式本体；LLM 直接对生产数据库任意 SQL 或写入；所有生产时序事实无差别物化 RDF；首期强制 Neo4j / Kafka / Kubernetes / 完整微服务化；未经批准新增第三方包。**

---

## 3. 本轮优先做的仓库审计（务必引用路径/证据）

先取得当前分支、提交、工作树是否干净、目录结构、构建系统、依赖锁文件、源码现状、测试报告、README、AGENTS、变更文档。不要把“文档称已通过”当作真正已验证。

若支持 Subagents，请主会话分配如下四个**只读**审计角色（能并行就并行，不强制恰好四个）：

| 审计 Agent | 审计范围 | 交付证据 |
|---|---|---|
| A · Repo & Frontend Explorer | Next.js/React 版本、旧 UI 与页面、TMDL 残留、图谱、测试、可复用设计系统 | 文件索引；可留/需改/需删候选清单；风险 |
| B · .NET & Architecture Explorer | .NET 工程、模块边界、API、存储、DbContext、权限、依赖、事务/测试现状 | 架构差异、迁移路径、依赖问题 |
| C · Semantic & AI Explorer | 本体/规则/指标/映射/Agent/MCP/文档处理实现，是否仅 Mock、真实 Jena/数据源情况 | 可执行链路图、空缺、PoC 问题 |
| D · Infra, Security & Delivery Explorer | Aspire、YARP、Keycloak、RustFS、OTel/Grafana、CI、供应链、中文运维、安全 | 运行依赖图、发布/运维风险、质量基线 |

子 Agent 汇报必须包含：已检查路径、明确证据、发现状态 `OBSERVED/NOT_FOUND/NOT_VERIFIED`、风险等级、建议复用或替换、是否与已确认决策冲突。无法访问文件就标注未检查，不准补猜。

**Master 交叉校验重点**：旧仓库若仍有 TMDL parser、serializer、UI、API、状态机等，不要简单全部删除；先识别其中可转移的 UI/权限/生命周期/测试资产，再设计 OWL/RDF 迁移方案，避免破坏已完成成果。也不要让不确定的历史资料覆盖本文件的新决策。

---

## 4. G0 必须规划的端到端技术链路

Master 的计划至少覆盖下列11个链路，每条说明所有者、API/DTO、版本、持久层、异常、权限、UI、测试与运维：

1. **本体编辑与发布**：导入/创建 OWL/RDF → 草稿 → SHACL/标准校验 → 比较/影响 → 审核 → 不可变 Release → Jena 图部署 → 原子 active 指针 → 查询生效 → 回滚；跨 PG/Jena/RustFS 失败恢复。
2. **实体和数据绑定**：五种连接源的真实连接/Schema 探查 → 业务键/单位/时间映射 → 测试/对账 → 身份冲突处理 → 虚拟/物化路由 → 图谱实例与证据。
3. **语义查询网关**：本体发现 → 查询逻辑计划 → 合法关系路径 → 权限/成本预算 → Jena/Ontop/SQL/API 执行 → 跨源合并 → `FOUND/EMPTY/PARTIAL/UNAVAILABLE/UNAUTHORIZED/AMBIGUOUS` 返回语义。
4. **指标**：定义/口径/维度/粒度/公式/生效期 → 校验/审核 → 计算服务 → 可重复结果 → MCP 查询与解释。
5. **规则**：声明性业务规则与可执行规则区分 → 适用范围 → 校验/审核 → 确定性执行 → 通过/违反/无法判定 → 来源解释。
6. **文档到本体**：上传 → 文档/OCR → Chunk/Embedding → 候选实体/属性/关系/规则 → 证据与消歧 → 审核 → 草稿变更 → 验证/发布。
7. **MCP / Capability Registry**：版本化、授权、输入输出 Schema、执行器、Trace、证据、兼容性；UI、REST、MCP 共享底层业务逻辑。
8. **AI 工作流**：MAF、模型路由/策略、工具调用、SSE、多轮上下文、`ExecutionRun`、持久化事件、Checkpoint、审批、Evals、模型切换和安全。
9. **身份、权限与审计**：Keycloak/OIDC/BFF/YARP、组织厂区范围、源查询授权、核心命令审计、用户行为事件、服务账号和密钥。
10. **观测、中文运维与灾备**：LoggerMessage → OTel/Alloy → Loki/Tempo/Prometheus/Grafana；业务查询树/告警/处置；Jena/PG/RustFS 备份与恢复演练。
11. **最终业务闭环**：Q235B 质量问题，按真实谱系定位，查询生产参数、指标、规则和规程；返回证据支持、未知/缺失与备选假设，而非无依据自动宣称根因。

必须提供 **逻辑架构图 + 物理部署图 + 查询时序图 + 发布状态机 + 跨源失败恢复图 + Agent 工具调用时序图 + 数据/版本关系图**。推荐 Mermaid，并给出可编辑源文本。没有事实依据时只画候选结构，标明 `PROPOSED`。

---

## 5. 开发路线：以纵向业务切片为主，不能横向堆功能

Master 应根据真实仓库重新优化顺序，但不得跳过下列价值和验证门禁。

| 关口 | 交付范围 | 演示和验收（示例） | 强依赖 |
|---|---|---|---|
| **G0 Plan & Audit** | 仓库审计、目标架构、差距、ADR、优先级、里程碑、分工、PoC、风险、可验收计划 | 本轮仅输出计划并等待审查 | 无 |
| **G1 Foundation** | .NET+Next+YARP/BFF+Keycloak、ServiceDefaults、BuildingBlocks、PostgreSQL/RustFS/Jena 开发编排、UI Shell、OpenAPI、日志/审计/OTel/Grafana、CI | 一键启动、真实登录、权限拒绝、基础审计与 Trace、中文监控入口 | G0 批准 |
| **G2 AI Native Thin Slice** | 极小冶金本体 `Heat→Casting→Slab→RollingEvent→Coil`，SHACL、不可变发布、Jena 查询、受控 MCP、最小 Agent + SSE + 证据 | 从 UI 修改草稿、校验、发布，再通过 Agent 查询正式语义与小规模可信样例；版本审计与回滚演示 | G1 |
| **G3 Ontology & Governance** | 20项本体建模能力按基础/专家支持范围、SKOS、身份、事件时间、源码无损、版本 diff、审核/影响分析 | 发布/撤销/回滚/导入导出、语义/属性校验，复杂公理不静默丢失 | G2 |
| **G4 Source & Query** | PostgreSQL、Oracle、Doris、TDengine、Web API；连接/Schema/映射/对账；Ontop PoC、Gateway跨源 | 真连接只读，跨厂重号/多对多/部分失效/权限/时区负例通过 | G2/G3 |
| **G5 Metrics & Rules** | 指标定义/执行/版本、业务规则分类/执行/校验、能力注册 | Q235B 指标口径准确；规则生效期与不同来源数值可追溯 | G3/G4 |
| **G6 Knowledge & AI Builder** | 文档解析 OCR、Chunk/Embedding、候选图谱/本体、人工校验入草稿 | 真实文档抽取→证据→接受/拒绝→经审批发布 | G3/G1 |
| **G7 Agents & RCA** | Agent 工作流、质量根因分析、多轮工具链、评价、安全、反馈闭环 | 一次完整跨源质量调查含证据/反证/不确定性，Evals通过 | G4/G5/G6 |
| **G8 Production Readiness** | 完整中文运维、行为分析、HA/性能/安全/备份恢复、部署/离线文档 | 恢复演练/故障注入/权限/负载/开源许可通过 | 各阶段 |

**G2 必须尽早证明真正 AI Native**，不要先做完14个页面后才第一次调用 Jena/MCP/模型；G8 的生产专项可以作为最终验收关口，但安全、审计、可观测性、测试与部署验证必须从 G1 起贯穿各阶段。

允许独立 workstream 并行：例如 G3 的前端三栏编辑器、Jena 语义适配、OWL import/export、SHACL 样例验证可以在契约冻结后并行。**不允许**让多个 Agent 同时定义同一份数据库迁移、同一份 OpenAPI 公共契约、同一套 Design Tokens 或在同一批文件上并发写入。

---

## 6. Master 负责的多 Agent 研发组织设计（计划阶段先设计，不启动编码）

Master 计划中应约定下列**逻辑岗位**，不代表一直并发打开同等数量的会话。

| 岗位/Agent | 责任边界 | 首要交付 |
|---|---|---|
| **Master / Architect / Integrator** | 计划、ADR、冻结契约、依赖 DAG、分配任务、合并、冲突、总体验收与报告 | 唯一集成决策与总进度 |
| Domain & Semantic | RDF/OWL/SHACL、Jena、Ontop、Ontology Release/Schema Catalog | 语义标准与可验证本体链路 |
| Backend Platform | .NET Modules、EF Core、YARP/BFF、Security、BuildingBlocks | 可运行服务与可靠 API |
| Connectors & Query | 五类 Connector、Identity Registry、Mapping、Semantic Gateway | 受控跨源查询/证据 |
| Metrics & Rules | 指标契约、计算适配、规则 DSL/Decision、版本与验证 | 确定性结果 |
| Knowledge & AI | 文档 Worker、知识抽取、MAF、MCP、SSE、AI Evals | 文档与 Agent 闭环 |
| Frontend & Design | shadcn Design System、Shell、图谱/表单/指标/AI/中文运维交互 | 一致的真实业务 UI |
| Quality & Security Reviewer | 架构规则、契约测试、边界/权限、语义/安全/性能/E2E | 独立质量报告，避免自测即批准 |
| SRE & Observability | Aspire、OTel/Grafana、审计、部署、HA、故障恢复 | 端到端监控与运维剧本 |

**并行策略**：

- G0 审计优先 3–4 个只读 Agent。后续一次最多 3–5 个**实际编辑任务**并行（根据实际可用模型/硬件/仓库冲突、限额动态调整），不以 Agent 数量作为完成标准。
- 单一 Git 主集成线。每个写任务必须拥有独立 `taskId`、指定文件/目录写权限、独立分支或 Codex-managed Worktree、固定接口契约与验收命令；严格禁止同时修改同一组公共源文件。
- 若使用 Codex 子 Agent：由主会话委派、消息、等待并汇总。若使用多个独立 Codex Worktree 会话：通过提交/PR/任务卡/ADR 同步；不能假设它们能自动直接互相发送持久消息。
- 公共契约变更（OpenAPI、发布包、Ontology Schema、SSE、工具 Schema、Design Tokens、数据库迁移、OIDC 配置）实行 **Single Writer**，由 Master 合并或指定唯一 Owner；其他 Agent 提出 PR/建议，不得直接并行修改。
- 代码提交前完成自测，之后由**另一 Agent**独立审查，再由 Master 集成；Master 不应把子 Agent 自报测试通过视为已验收。
- 当 Subagents 不可用，计划保留相同角色和任务分解，但串行执行，不强制引入另一个编排 SDK 或私有脚本。
- 不把软件产品运行时的 MAF Agent Framework 与 Codex 研发组织的 Subagents/Worktree 混为一谈。

### 6.1 每个实施任务必须使用任务卡

```yaml
id: G2-SEM-001
title: "Jena 已发布本体只读查询"
status: proposed              # proposed/approved/in_progress/in_review/merged/blocked
owner: semantic-agent
reviewer: quality-agent
depends_on: [G1-INFRA-003]
owned_paths: ["backend/Modules/Ontology/**"]
read_only_dependencies: ["backend/BuildingBlocks/**", "docs/contracts/**"]
contracts: ["OntologyReleaseManifest", "SemanticQueryResult"]
acceptance:
  - "发布版可用 SPARQL 读取，草稿不可见"
  - "返回版本、来源及 Trace ID"
  - "失败不影响 active release"
tests: ["semantic-compat", "release-rollback", "contract"]
observability: ["traces", "metrics", "structured-logs", "audit"]
deliverables: ["source", "tests", "docs", "evidence"]
```

这仅是任务卡格式范例，不代表已经授权创建该任务、目录或实现代码。

### 6.2 任务完成定义（Definition of Done）

必须同时满足：

1. 已覆盖通过审批的用户故事/边界及失败分支，非假按钮，非虚构返回；
2. 代码依赖和模块所有权满足架构测试；
3. C# 注释/格式符合已批准规范，前端风格和语义命名一致；
4. API/事件/证据/版本合同已同步文档、生成 Client 与回归测试；
5. 单元/集成/契约/必要 E2E 和安全负例通过；
6. 操作日志、审计、指标、Trace、必要中文运维入口同步具备；
7. 第三方依赖通过许可/维护/安全评估；
8. 完整提交/差异/命令输出/失败与遗留风险在交付记录中可查；
9. 独立 Reviewer 复核，Master 集成验证通过；
10. 验收只依据实际执行证据，未运行项标为 `NOT_RUN`，不能称通过。

---

## 7. 计划中必须识别的首要 PoC 和失败风险

至少提供这些 PoC 的实验步骤、样例数据、可运行命令（**仅写计划，暂不执行有副作用命令**）、成功/失败标准和替代方案：

- OWL/RDF/Turtle 无损往返、复杂公理“支持/保留但不可编辑/阻断”、Jena SHACL、SPARQL 与版本部署；
- Jena TDB2 在目标 HA/备份/恢复约束下的拓扑，RDF4J 回退门槛；
- PostgreSQL/Oracle 的 Ontop 虚拟查询 vs 原生 Connector 结果、延迟与授权；TDengine 兼容性实测，Doris/Web API 走独立 Adapter；
- `ontologyHash/shapesHash/mappingVersion/metricVersion/ruleVersion/capabilityVersion` 的跨库发布一致性与故障注入；
- 统一实体身份：重号、别名、跨厂、历史编号、缺失关联、多对多的正反样本；
- `calculate_metric` 与 `evaluate_rule` 的确定性和数据时间语义；
- Keycloak + YARP BFF + SSR Cookie + CSRF + 多实例会话与授权；
- .NET10 原生 SSE → Next.js →（必要时）YARP，验证流式延迟、断线恢复与取消；
- MAF 工具链、Checkpoint、PostgreSQL 运行状态、人工确认、AI Evaluation、Prompt Injection 安全；
- MarkItDown / PaddleOCR / pgvector 到候选本体审核的真实文档流水线；
- OpenTelemetry → Alloy → Loki/Tempo/Prometheus/Grafana，中文可视化、告警关联，审计独立留存；
- RustFS S3 子集与 Jena/文档/Tempo/Loki 的兼容、备份、恢复测试；
- shadcn Base UI/Next App Router SSR、图编辑器、Monaco、Rhea Tokens、统一 Shell 的浏览器可访问性和性能；
- Kiota vs Hey API、MSTest 工具链、Hangfire vs 持久任务替代方案的客观小样本比较。

凡依赖外部企业生产库真实凭证、专有标准、付费模型或受保护数据的 PoC，必须提供本地替身方案与专门的真实环境验收计划，不能偷偷生成生产凭证或宣称真实通过。

---

## 8. G0 审计后的“应交付计划”，必须具体、可审查

最终请在当前会话输出以下文档的完整内容或完整摘要和详细文件正文（Plan 模式禁止写入时不要强行创建）。路径可根据仓库现有规范调整，但必须一一对应：

1. `docs/planning/00-current-state-audit.md` —— 仓库事实、证据路径、已实现/仅 Mock/缺失/不可验证、Git 状态、可复用资产与 TMDL 清退评估；
2. `docs/planning/01-decisions-and-nongoals.md` —— 项目冻结决定、排除项、技术基线与待确认 ADR，任何偏离必须显式说明；
3. `docs/planning/02-target-architecture.md` —— 逻辑/部署/数据/查询/发布/Agent 架构图、模块边界、主要类与接口职责；
4. `docs/planning/03-module-feature-matrix.md` —— 14模块的功能→页面→用例→API→数据→测试→监控/审计映射，区分 MVP / 后续，防遗漏；
5. `docs/planning/04-roadmap-and-dependency-dag.md` —— G0-G8、真实依赖 DAG、关键路径、每阶段 DoD、可并行/不可并行项目、风险缓解；
6. `docs/planning/05-agent-team-and-task-contracts.md` —— Master、专业 Agent、工作树、文件所有权、通讯、并发限制、PR/集成/冲突处理；
7. `docs/planning/06-spikes-and-acceptance.md` —— PoC、自动验收脚本计划、负例、发布/回滚/恢复、UI、监控和 AI Evals；
8. `docs/planning/07-risk-register.md` —— 风险严重度、影响、可观察信号、触发条件、Owner、退路及拦截门禁；
9. `docs/planning/08-agents-and-repo-standards-proposal.md` —— 未来的根 `AGENTS.md`、分模块指导、`.codex/agents` 自定义角色、`PLANS.md`、注释/格式、CI、ADR、任务模板建议（**目前仅提案，未批准落盘**）；
10. `docs/planning/09-review-request.md` —— 请 ChatGPT 审核的变更建议、对现有代码的影响、阻断与明确需用户决定的项。

每个文档必须简洁但具体，不能只是空目录或套模板。应优先引用真实源码和官方参考资料，标记 `CONFIRMED / PROPOSED / UNKNOWN`，不将本文件技术方向与仓库已有完成度混淆。

**Master 最终答复必须按此顺序：**

1. 当前状态一句话摘要（仓库可否作为基础、是否含大量 TMDL）;
2. 关键发现/风险（带文件路径和确凿证据）;
3. 核心架构决策和需复核的冲突;
4. 推荐的 G1→G8 实施顺序、关键路径及可并行工作;
5. 第一条可开发的纵向切片及验收脚本计划;
6. 分工/任务 DAG 和任务卡原则;
7. 测试、运维、审计、安全、性能和回滚门禁;
8. 明确列出 `BLOCKED`、`NOT_VERIFIED`、`USER_DECISION_REQUIRED`;
9. 给出供 ChatGPT 审查的计划正文与文档位置;
10. 最后一行写 **`G0_PLAN_READY_FOR_REVIEW`**，并等待批准。

---

## 9. 架构计划质量检查清单（Master 自查后再提交）

在提交前逐项核对：

- [ ] 没有使用 TMDL 作为正式本体源，旧代码迁移路径具体且不会无授权删除。
- [ ] 没有采用 Microsoft GraphRAG、AutoMapper、泛型 Repository/重复 UnitOfWork、Ant Design/Fluent 组件实现。
- [ ] 本体定义、实例事实、配套 Shapes、术语、指标、业务规则、数据映射、能力和文档证据分别界定权威边界与版本。
- [ ] Ontology/Metric/Rule/Mapping/Capability 版本与数据时效不混为一个时间戳。
- [ ] Jena/Fuseki、Ontop、原生 Connector 与 Semantic Gateway 的职责、错误语义和性能预算清楚。
- [ ] 首期 5 种真实数据源均有连接器功能计划及只读策略，不得“Mock 即完工”。
- [ ] ASP.NET Core 10、EF Core 10、直接 DbContext、显式映射、Pragmatic Clean Architecture 与模块边界一致。
- [ ] Aspire ServiceDefaults 不是巨型公共业务库，AppHost 与 BuildingBlocks 职责清晰。
- [ ] Next.js + shadcn Base UI + Tailwindadmin 风格参考有独立 Design System 和商业许可证边界。
- [ ] SSE 流式事件、取消、断线恢复、人工批准和持久化 ExecutionRun 已有契约及测试。
- [ ] YARP BFF、Keycloak、CSRF、多实例登录、资源授权及 MCP 安全均有方案。
- [ ] LoggerMessage、OTel+Grafana LGTM、Faro、审计、行为分析和中文运维从 G1 贯穿。
- [ ] XML 文档注释/成员空行/代码风格是自动门禁的一部分；Code Review 检查语义而非伪覆盖率。
- [ ] 模块化、测试证据、分支/文件所有权、集成顺序和上下文交接方案足以支持 Codex 并行开发。
- [ ] 方案列出第三方依赖、官方优先的替代方案、许可风险与待批准项目。
- [ ] 提供文档→候选本体与 Q235B 根因分析的完整正反验收故事。
- [ ] 严格保持本轮 **PLAN ONLY**，没有以任何名义开始编码或修改仓库。

---

## 10. Codex 协作能力的真实边界（避免误用）

请先检查本机/当前客户端的 Codex 版本与可用指令，再决定要不要提供具体配置示例。

已公开的 Codex 文档支持：

- Plan 模式：客户端支持时使用 `/plan`。
- Subagents：主线程委派子任务；CLI 可使用 `/subagents` 查看线程；项目可在 `.codex/agents/*.toml` 中定义自定义角色；当前 Codex 通常默认开启子 Agent。
- `AGENTS.md`：仓库长期指令；每次会话开始时读取；嵌套目录可覆盖规则。
- Git Worktree：不同聊天隔离源码修改；通过分支/PR 提交成果。应避免共享目录上的同时编辑和写入冲突。

不要混淆 **Codex Subagents**（本次研发协作）、**Codex Worktree 独立会话**（并行研发隔离）、**OpenAI Agents API**（另一个可选产品接口）和**Microsoft Agent Framework**（本体平台运行时技术）。

参考官方资料（请以实际客户端可访问的现行文档再次核实）：

- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://learn.chatgpt.com/docs/agent-configuration/agents-md
- https://learn.chatgpt.com/docs/environments/git-worktrees
- https://learn.chatgpt.com/docs/developer-commands
- https://developers.openai.com/cookbook/articles/codex_exec_plans
- https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex

---

## 11. 对当前 Codex 会话的最后指令

从现在开始只开展 G0 计划阶段：

**先只读审计 → 合理并行分工 → 汇总事实 → 形成模块功能/架构/PoC/任务依赖与验收计划 → 自查完整性 → 输出待审查交付物 → 停止等待用户批准。**

对确实无从获得的资料、真实凭证或环境，用替代测试计划和风险标注处理，**不要通过猜测填补证据空白**。你可以提出架构优化，但凡偏离本文件已经确认的决策，必须以明确的 ADR Proposal 呈现，不得先行实施。

**最终请输出 `G0_PLAN_READY_FOR_REVIEW`。**
