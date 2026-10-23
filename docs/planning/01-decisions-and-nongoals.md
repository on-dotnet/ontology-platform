# 01 · 决策、非目标与官方实践基线

审查状态：G0总体通过，仅获准文档固化。CONFIRMED指方向确认，PROPOSED指待实施或待决策提案；运行验收均NOT_RUN。状态定义见 [00](00-current-state-audit.md)，审批边界见 [10](10-g0-review-record.md)。

## 已确认决策

| 领域 | CONFIRMED |
|---|---|
| 命名 | 仓库 `on-dotnet/ontology-platform`；工程前缀 `OntologyPlatform`；前端 `apps/web`、包名 `@ontology-platform/web`；后端 `backend/OntologyPlatform.slnx` |
| 平台定位 | 多行业平台；冶金仅作为首期业务验证和行业资产，不进入平台基础工程命名 |
| 正式语义 | RDF/RDFS/OWL2、Turtle、SHACL1.0、SKOS、PROV-O；OWL 推理与数据验证分工 |
| 数据与查询 | PG 元数据及审计、Jena 正式图、RustFS 原件和发布包；Ontop 可插拔；自研 Semantic Query Gateway |
| 前端 | Next16 App Router、React19、TypeScript、Tailwind4、shadcn/ui + Base UI、自研 Tokens，pnpm/Turbo；Tailwindadmin风格的彩色企业后台 |
| 后端 | .NET10、ASP.NET Core10、EF Core10；模块化单体、Vertical Slice、务实 Clean Architecture、按复杂度采用 DDD |
| 身份与入口 | Keycloak/OIDC、集成式 YARP/BFF、服务端会话、HttpOnly Cookie、CSRF、多实例密钥共享 |
| AI | Microsoft.Extensions.AI、MAF、受控工具、持久 ExecutionRun、SSE、独立审批 Command API |
| 工程 | 原合同中文注释、格式、显式映射、模块数据所有权、独立审查和证据要求全部保留 |

合同旧称 `Platform.AppHost`、`Platform.ServiceDefaults` 由补充约束明确为 `OntologyPlatform.AppHost`、`OntologyPlatform.ServiceDefaults`。这是命名澄清，不改变职责。

## 截至2026-10-23核实的官方实践

以下是G0实际访问正文的观察；归档未重新执行框架兼容测试，也不将观察值作为未来自动升级指令。

| 官方证据 | 对本项目的建议 |
|---|---|
| Codex 支持分层 AGENTS，目录内 override 优先；指令有加载范围和大小限制。[官方说明](https://learn.chatgpt.com/docs/agent-configuration/agents-md) | 根 AGENTS 保持精简，详细规范链接到文档；前端、后端、Worker 分域指导 |
| 仓库技能通过 `.agents/skills` 发现。[官方说明](https://learn.chatgpt.com/docs/build-skills) | 技能保存可重复研发流程，采用渐进加载 |
| 项目自定义 Agent 使用 `.codex/agents/*.toml`；项目配置受信任状态及上层策略约束。[子Agent](https://learn.chatgpt.com/docs/agent-configuration/subagents)、[配置](https://learn.chatgpt.com/docs/config-file/config-basic) | 配置研发角色，不赋予越权能力；不存凭证或固定付费模型 |
| ExecPlan 是可采用的工程协作约定。[官方示例](https://developers.openai.com/cookbook/articles/codex_exec_plans) | 使用 `PLANS.md` 定义本项目计划和交接规则，不照搬所有示例目录 |
| .NET10 当时官方 SDK 为 `10.0.402`、运行时 `10.0.13`，发布于2026-10-13。[下载页](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) | G1工具链提案固定SDK10.0.402，不升级到.NET11预览 |
| .NET10 新solution默认支持`.slnx`。[官方说明](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-sln) | 使用指定solution路径 |
| Aspire当时稳定版为`13.6.0`；ServiceDefaults不应承载其他共享模型。[官方说明](https://aspire.dev/get-started/csharp-service-defaults/) | 作为编排研究基线，保持启动默认配置边界 |
| `AddNextJsApp`仍标Experimental。[官方说明](https://aspire.dev/integrations/frameworks/javascript/) | 默认通用JavaScript/pnpm开发编排；专用helper单列PoC |
| Next官方文档当时显示`16.4.2`。[安装说明](https://nextjs.org/docs/app/getting-started/installation) | G1锁版候选16.4.2，锁定前复核安全公告和兼容性 |
| Next16.2+包含版本匹配文档；16.3+默认管理AGENTS指定区块。[官方说明](https://nextjs.org/docs/app/guides/ai-agents) | 前端指导放`apps/web/AGENTS.md`，保留框架管理区块和项目规则 |
| Next16构建不再执行lint。[升级说明](https://nextjs.org/docs/app/guides/upgrading/version-16) | build、lint、typecheck分别验收，使用ESLint CLI |

以上不代表已安装或通过兼容测试。其他依赖精确版本由获授权后的G1工具链任务生成锁定清单；候选新增第三方依赖须单独登记审批。

## 非目标与ADR

原合同全部排除项继续有效：TMDL、Microsoft GraphRAG、Agent365、AutoMapper、通用Repository/UoW、Ant Design/Pro/Umi、Fluent UI v9、LLM自动发布、生产库任意SQL/写入，以及首期强制微服务/Kafka/Kubernetes/Neo4j均不引入；不使用JSON/TS替代正式本体，不无差别物化全部时序事实，不默认引入未批准第三方包。

| ADR提案 | 推荐方案 | 备选与触发条件 |
|---|---|---|
| 001 工程结构 | 下文Monorepo；暂不建立根`packages/`或`packages/ui` | 必须解释与既有Design System决策的关系、复用边界和提取成本；第二真实前端消费者出现后评估共享包；仍待明确批准 |
| 002 发布一致性 | PG active指针、不可变制品、Outbox | 不采用未经验证的跨存储分布式事务 |
| 003 Next编排 | 通用JavaScript开发资源、独立standalone生产镜像 | 专用helper经实验接口评估后再采用 |
| 004 后台持久任务 | PG Outbox/Run为可靠事实，短队列用Channel | Hangfire仅在持久调度需求及PoC成立后审批 |
| 005 SDK与工具 | Kiota、MSTest/MTP优先验证 | Hey API、Testcontainers等按理由和许可审批 |

## 本次审查补充

“暂不建立packages/ui”是需要ADR解释的优化提议，不能以归档或G0总体通过默认为单项架构批准。已确认Design System（Tokens、可复用组件、统一Shell和交互规范）完整保留，存放位置暂提议在应用内；实施前须明确ADR决定。

UI继续采用Next.js + shadcn/ui + Base UI、Tailwindadmin风格彩色企业后台，自主开发并守住商业源码许可边界。Rhea仅作为待核实的组件风格参考（NOT_VERIFIED），不作为未经验证的新依赖。
