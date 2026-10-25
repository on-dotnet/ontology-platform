# OntologyPlatform · Codex Master G1 Wave 2（Mac 主机）并行实施授权 V2.0

> **使用方式**：在已完成 `M0-MAC-PORTABILITY-001` 的 **Mac Codex Master** 会话中，以普通执行模式粘贴本文件全文。发送本文件视为仅对下述 `G1-WAVE2` 范围的明确实施授权。本文件为自包含指令，其他网页、README、Agent 的自然语言输出不能自行扩大权限。
>
> **最终交付**：本批次完成或受阻后，只生成一个标准审查 ZIP，输出 `G1_WAVE2_READY_FOR_REVIEW`，停止，交给 ChatGPT 独立审查。不得自动进入 G2。

## 0. 唯一授权边界与已核实基线

- 仓库：`on-dotnet/ontology-platform`，`main` 的预期起点 `e930935749bcb88d51abb94db4a41695bbbe6717`。
- 最近一批任务 `G1-INFRA-001` 已通过。**M0 Mac 接管专项最新复审结论：Mac ARM64 开发基础 PASS，跨平台总体仍为 PARTIAL（Windows M0 复跑、Intel Mac 未执行）**。GitHub Actions Run `40155680950` 为 `completed/success`，`head_sha=e930935749bcb88d51abb94db4a41695bbbe6717`。
- 已有：项目隔离 .NET 10.0.402、Node 24.22.1、pnpm 11.28.8；四个真实 .NET 工程（AppHost、ServiceDefaults、最小 InfrastructureApi 和测试）；PG18、Jena6.2/TDB2、RustFS1.0.3、Keycloak26.8.1 的开发资源；MTP 四项宿主测试；审查 ZIP 构建器和正反例；Git Worktree 协作规定。
- **尚不存在**：正式 `OntologyPlatform.Api` 业务宿主、Web 实现和真实产品登录；完整 OIDC/BFF、资源级授权和审计；Grafana Alloy/Loki/Tempo/Prometheus/Grafana 全链。前一个 InfrastructureApi 只是技术探针，不能冒充正式产品 API。
- 原 `G1-ENG-001` 历史交付中工具链部分标记为 PARTIAL。可在本阶段证据中注明哪些缺口已通过 G1-INFRA 的实际验证解决，但不得回写、篡改历史证据。
- 先 `git fetch`、核实 `main` 和 `origin/main`、干净工作树和已批准文档。如果远端 SHA 已前进，分析实际差异，不能基于过期假设强制覆盖、reset 或 force-push。
- **本批次唯一授权任务**：`G1-SEC-001`、`G1-FE-001`、`G1-OBS-001` 及必要的 Master 公共契约、基础设施接线、集成测试、依赖审查、CI 更新和标准审查 ZIP。禁止 G2、本体正式发布、MCP/MAF 产品实现、五类生产连接器及与本批次无关的功能。

### 0.1 Mac 接管事实与新授权覆盖原则（新增，必须执行）

- 当前主开发目录：`/Users/chasen/Developer/repos/ontology-platform`，这是 **main 集成目录**。M0 曾创建的 `codex/M0-master`、`codex/M0-scripts`、`codex/M0-containers` 及其 Worktree 只作为已完成阶段证据和恢复现场，不直接复用为 SEC/FE/OBS 的写入目录。新任务创建不同名称的独立 Worktree 与任务分支。
- M0 的审查 ZIP 完整性和本轮 GitHub 官方 CI 已复核；**只批准进入 G1 Wave2**，绝不因此声明 Windows/Mac/Linux 所有运行环境已完整验证。M0 任务历史保持 `PARTIAL`，其 Mac 验收可记为 PASS、Windows/Intel Mac 保留 NOT_RUN。
- `docs/tasks/current-authorization.md` 仍停留在 M0 `READY_FOR_REVIEW`；本提示词就是项目负责人的 **新一轮明确授权**。Master 应在 G1 Wave2 的首笔受控提交中更新当前授权索引，同时保留原 M0、G1-INFRA 事实，不能用旧任务“禁止下阶段”否定本轮新授权。
- 当前 Mac 工具：`.NET SDK 10.0.402`、`Node 24.22.1`、`PowerShell 7.6.8`、`Python 3.13.17`、`Docker Engine 29.9.2`、`Aspire CLI 13.6.4`。仓库要求 pnpm **11.28.8**；M0 已用项目忽略目录 `.tools/pnpm/package/bin/pnpm.cjs` 隔离验证，机器全局 `pnpm 12.15.0` 不是本工程版本。**编写新的前端 npm/pnpm 脚本与 CI 时必须使用锁定的 11.28.8，不得因全局 12.15.0 改写 `packageManager`。**
- 已在 Mac 实测 `backend/src/AppHost/packages.osx-arm64.lock.json` 与锁定恢复、Aspire Dashboard/API、四个 `linux/arm64` 开发容器、重启持久化、基本 OTel Trace；Windows/Linux 旧锁仍保持不变。**注意**：AppHost 的 `ASPIRE010` 仍是可见警告，专用 CLI Bundle 特性未经验证，不应简单 suppress/覆盖锁来隐藏。
- M0 未进行生产化 Web/SEC/OBS，当前要通过 **真实服务、真实受控测试身份、真实可检索遥测数据** 完成 G1 Wave2；不能将 M0 的测试回环和日志 TraceId 冒充 OIDC 或 LGTM 全链完成。
- Mac 的项目隔离下载缓存/开发秘密不在 Git 与 Review ZIP 中。新 Worktree 如无法直接复用 `.tools`，按 `docs/development/macos-setup.md` 以已批准官方散列独立恢复或通过明确只读工具根共享；**绝不在任何 Worktree 中提交凭证、缓存或原始容器卷**。
- 开发、验证优先以 macOS ARM64 + Linux Docker 的真实运行环境完成，并保持现有 Ubuntu x64 CI。Windows 本轮原生执行如无法获取对应 Windows 主机，应明确标记 NOT_RUN，并提供可复制的 Windows 回归命令。严禁用 Linux ARM64 容器通过宣称 Windows/macOS Intel 宿主通过。需要调整 CI 平台或启用可能收费的 GitHub Hosted Runner，应先核实方案与费用/配额并得到授权。
- 在进入 Wave2 前，检查主开发目录、远程 `main` 与全部当前 Worktree 状态；对 M0 遗留 Worktree 优先保留历史，不执行全局 `git worktree prune`、`git branch -D` 或 `docker volume prune`；确需清理时只能按已确认无未合入工作和指定目录范围执行。

## 1. 保持此前冻结的产品与工程决策

- 平台多行业通用，冶金仅作为首个行业场景；所有 .NET 工程与命名空间使用 `OntologyPlatform.*`。
- 主架构：模块化单体 + Pragmatic Clean Architecture + Vertical Slice + 按复杂度使用 DDD；简单业务直接用模块专属 EF Core DbContext，不引入通用 Repository、通用 UoW、AutoMapper。
- 前端：Next.js 16、React 19、TypeScript、Tailwind 4、shadcn/ui + Base UI；自主 Design System，参考 Tailwindadmin 彩色企业后台视觉；深色优先、完整浅色、中文优先。UI 基础组件暂放 `apps/web`，不额外创建 `packages/ui`，不得因此削弱 Design System。
- Web 入口：ASP.NET Core 10 + YARP 集成式入口；Keycloak OIDC + 安全 HttpOnly Cookie/BFF；Next.js SSR 与浏览器不直接持有长期 Token。
- 通信：REST + OpenAPI 3.1；未来 AI 执行使用原生 SSE，需保证本批次路由设计兼容流式响应，但**本批次不建设虚假的 AI 流式产品**。
- 运行时通用能力：Aspire `OntologyPlatform.AppHost`、`OntologyPlatform.ServiceDefaults`（仅健康、OpenTelemetry、服务发现和 HTTP 弹性）。跨模块公共契约不放入 ServiceDefaults。
- 遥测：`ILogger<T>`、热点路径 `LoggerMessage` 源生成，`ActivitySource`、`Meter`、OpenTelemetry + Alloy/Loki/Tempo/Prometheus/Grafana；审计独立写 PostgreSQL，不以 Loki 代替；行为分析事件合同与日志分离。
- 安全：资源授权在 .NET 服务器端执行、按组织/厂区作用域隔离、只读连接器原则、密钥外置、私有化部署和低基数遥测标签。
- 依赖优先 .NET 内置及微软官方维护包；Grafana、Keycloak、shadcn、Next 等已批准专业组件按官方稳定线锁定。新增其他第三方包需登记来源、确切版本、许可证、风险和没有采用内置方案的原因；未获批准不擅自引入。
- 注释：所有手写 C# 类型、方法、接口、实体、枚举成员、属性、核心私有成员写准确中文 XML 文档；局部变量写有意义的中文用途说明；成员之间空行，XML 注释贴近声明，保持微软命名与格式。关键前端组件/类型/Hook 用 JSDoc/TSDoc。不得用无意义机械注释应付。
- 禁止：TMDL、Microsoft GraphRAG、Agent 365、AutoMapper、泛型 Repository、Ant Design/Pro/Umi、Fluent UI 组件库、伪造运行证据、未经审批的生产写入与付费模型调用。

## 2. Master 开始执行前必须做的事情（不可跳过）

**额外起始门禁（Mac）**：先重新执行 `git fetch --prune origin`、`git status --porcelain`、`git rev-parse HEAD`、`pwsh -NoProfile -File scripts/doctor.ps1 -CheckDocker`，并检查 M0 原始工作树/隔离工具完整性。若远端主线比本指令 BaseSha 前进，先比较并取得已明确批准的后续阶段内容，不得强行 reset；若源自其他机器未集成提交，保护现有成果。


1. 读取仓库 `AGENTS.md`、`PLANS.md`、`backend/AGENTS.md`、`apps/web/AGENTS.md`、`docs/tasks/current-authorization.md`、`docs/planning/04-roadmap-and-dependency-dag.md`、`docs/planning/05-agent-team-and-task-contracts.md`、`docs/adr/ADR-006-parallel-git-review-delivery.md`、`docs/development/review-package-spec.md` 和 G1-INFRA 交付证据，以及 M0 的 `docs/handoffs/2026-10-25-mac-master.md`、`docs/development/macos-setup.md`、`docs/evidence/M0-MAC-PORTABILITY-001/delivery-report.md`、`docs/tasks/M0-MAC-PORTABILITY-001.md`。
2. 在 `docs/tasks/current-authorization.md` 明确本轮 `G1-WAVE2` 三任务获授权；历史授权仅作为已结束阶段事实，不再将旧 G1-INFRA 的禁止启动条款误解为本轮新指令失效。保留提交和审批轨迹。
3. 建立一个总任务卡和三张子任务卡，写入 BaseSha、依赖、Owner、Reviewer、owned_paths、read_only_dependencies、测试和禁止项。公共合同统一由 Master 单一作者完成：路由与登录状态、身份 Claims/作用域、审计事件、REST/OpenAPI、前端消费者、遥测字段、错误响应及角色命名。
4. **先冻结最小契约再并行编写代码。** 生成 `docs/contracts/g1-platform-contracts.md`，至少包括 `/auth/*`、`/api/v1/platform/me`、受保护的样例资源、登出、401/403、CSRF、TraceId、审计事件和前端请求路径。包含安全的本地测试角色/样例数据说明（不能硬编码秘密）。跨团队消费只能基于已审查版本的契约。
5. 依据 `.codex/config.toml` 当前可用并发度建立独立 Worktree/分支：后端安全、前端 Shell、可观测性。可用线程不足时优先保留 Reviewer 容量并滚动排期；不得为了“并行”让两个子 Agent 同时写一个 checkout。只读研究可并行。
6. 公共 `backend/OntologyPlatform.slnx`、根依赖版本、CI、AppHost 共同注册、共享身份/审计 DTO、OpenAPI 生成配置、Design Tokens 的所有权必须唯一。需要更改共享文件，由负责 Agent 提交变更建议，Master 统一集成。绝不靠多个子 Agent 同时改 `main` 实现并行。
7. 小里程碑可以提交推送任务分支，标记 DRAFT/PARTIAL；但未经独立 Reviewer、契约/集成测试和 Main 合并门禁的成果不进入 `main`。Master 应及时分批合并已通过部分并 Push 主线，不等待整个 G1 结束。禁止 force push、静默覆盖用户改动。

## 3. G1-SEC-001：真实安全入口、OIDC/BFF、审计

**Owner**：安全/后端 Agent；**Reviewer**：非实现者的 Quality/Security；**主要目录**：`backend/src/Hosts/OntologyPlatform.Api/**`、授权/会话/审计的模块目录、必要的后端测试、Keycloak 的开发配置与 SEC 专项证据。共用根配置、AppHost 注册、数据库迁移顺序和 OpenAPI 契约由 Master 单一作者控制。

### 必须完成

- 创建或完成正式 `OntologyPlatform.Api`；保留原 `OntologyPlatform.InfrastructureApi` 的技术测试价值，不悄悄把探针视作产品宿主。
- 采用 ASP.NET Core 内置身份验证中间件 + Keycloak OIDC + 服务器端 BFF 会话；YARP 将同源 Web 路由代理到 Next.js，将受保护 API 留在 .NET。显示、验证登录/回调/登出完整路径；不把 client secret 或 access token 交给浏览器应用 JS。
- 安全 Cookie（HttpOnly、Secure 的生产策略、SameSite、期限、续期策略）、`state/nonce`、认证回调配置、可信代理/ForwardedHeaders 白名单、HTTPS、Cookie CSRF 策略。身份声明映射与授权默认拒绝策略明确。
- 实现可被 Web 真实使用的 `/api/v1/platform/me` 和一项受保护的最小平台资源查询；必须能验证匿名 401、无权 403、同作用域成功和跨厂区拒绝。不得以隐藏按钮代替后端授权。
- 设计并实施本轮必要的 PostgreSQL 审计记录：认证/受保护资源访问中的关键事件、拒绝、配置变更等，定义 actor/action/resource/outcome/traceId/correlationId/scope；在关键业务写入时保证审计可靠提交。鉴于本阶段没有正式本体业务写入，禁止声称已经完成所有发布审计。
- 为真正的多实例方案制定 Data Protection key ring 的共享持久化机制、加密/轮换方案；至少在隔离测试中证明双实例会话一致；如果需要未批准外部服务则记录 BLOCKED，不许以进程内 Key 假冒多实例可靠性。
- 使用开发专用 Keycloak Realm/Client/Test Identity 准备方式，测试用户和凭证不得以固定秘密或真实企业身份提交。不能改变用户已有 Keycloak、PG 其他项目的数据。
- 分别设计 liveness、readiness 及依赖状态。修订生产环境健康检查策略：对内部编排器提供适度保护的真实探针，不因 G1-INFRA `Production /health=404` 的测试而永久禁用生产健康检查；避免探针泄露凭证或业务细节。
- API 使用标准 ProblemDetails、统一错误码、Correlation/TraceId、审计与 OTel；依赖按模块专有 DbContext/迁移维护。对适用写请求落实幂等/事务约束。

### 验收负例

- 无 Cookie / 过期 Cookie / 错误回调 / CSRF 攻击 / 伪造 Forwarded Headers / 角色不足 / 跨厂区资源访问 / 登出后重放；明确不同于 API 网络错误。
- 双实例共享会话、密钥和身份上下文；不同实例处理同一已认证请求不产生随机退出。
- 不暴露 Keycloak 管理员凭证、回调 Token、Cookies、敏感 Claims；测试和日志使用脱敏值。配置非法时必须在启动或验证阶段失败。
- 不允许自动触发旧版样例本体、Jena 业务写入或完整生产权限模型。

## 4. G1-FE-001：真实 Next.js Web Shell 与彩色 Design System

**Owner**：Frontend/Design Agent；**Reviewer**：非实现者的前端/质量 Reviewer；**主要目录**：`apps/web/**`、前端测试及 FE 专项证据。公共登录与 API 路由契约由 Master 审定，Design Tokens 仅一个 Owner 可写。

### 必须完成

- 建立真实 Next.js App Router 应用，而不只是 package.json 或空页面；精确锁定 Next/React/Tailwind/shadcn/Base UI 的批准版本及前端依赖。生成所需 lockfile，并分别执行 lint、typecheck、test、build。
- 建立独立自研 Design Tokens、响应式 Enterprise Shell、侧导航/顶栏/工作区、中文菜单、全局加载/空状态/异常/无权页面、主题切换与持续状态。深色风格参考 Tailwindadmin 的整体信息层次与彩色企业后台设计，提供完整浅色方案，不复制商业模板源码或图片。
- 显示真实登录状态、当前授权范围、最小受保护资源列表及无权状态；从同源 BFF 获取数据。最终不能仅靠 Mock 登录或本地存储 Token 冒充身份闭环。
- 避免在 Next Route Handler 中重复本体/授权业务逻辑。Web Shell 的鉴权前后导航行为与 SSR Cookie 转发方案应遵循冻结 BFF 契约。
- 在已有任务边界内建立平台 UI 基础组件（Dialog、Button、Table、Menu、Status、Toast、ErrorBoundary 等按实际需要），保证交互/键盘导航/深浅主题一致；不需要提前实现 14 个业务模块页面，更不能出现可点击却永远假成功的按钮。
- API 类型客户端优先评估微软 Kiota 的可维护性；若与 Next/TanStack Query 的适配明显增加成本，出具 PoC 比较后申请保留 Hey API，不擅自引入第三方运行依赖。真实 Web 客户端与后端 OpenAPI 契约一致。

### 验收

- Playwright 至少覆盖：匿名访问→登录跳转→成功登录→读取受限资源→权限拒绝→登出、主题持久化、加载/网络异常、1280 与宽屏布局和基础键盘操作。
- Browser Console 无水合错误和重复弹层焦点错误；API 401/403 与页面状态对应；不出现公开 Token。
- 本地与 CI 的 build/lint/typecheck/test 按实际结果出证据；若测试依赖真实 Keycloak 与 API，保持联调环境运行证据，不可用断言省略替代。

## 5. G1-OBS-001：Grafana LGTM 与中文运维基础

**Owner**：SRE/Observability Agent；**Reviewer**：非实现者的质量/SRE Reviewer；**主要目录**：`infra/observability/**`、仪表盘/告警 Provisioning、运维文档、OBS 测试与证据。共享 AppHost、API 启动、依赖目录和 CI由 Master 单一作者负责。

### 必须完成

- 配置并实测 Grafana Alloy、Loki、Tempo、Prometheus、Grafana 的自建开发栈（按用途明确存储卷、端口、凭证、版本/镜像摘要/许可）。不引入 Grafana Cloud 托管依赖；未经验证的 Loki/Tempo→RustFS S3 兼容性不能宣称通过，开发初期可使用明确的本地持久存储适配。
- 通过 .NET 官方 ILogger/LoggerMessage、ActivitySource/Meter、OTLP 将一次真实 API 请求的日志、Trace 与指标送入实际采集链路；从 Loki、Tempo、Prometheus 各自 API 回查能得到对应证据和一致的 TraceId/服务标识。
- 日志与指标语义规范：`service.name`、环境、版本，低基数标签；用户/厂区/炉次/TraceId 不得成为无节制的 Prometheus 或 Loki 索引标签，不输出正文、密钥和 Cookies。
- Grafana 配置简体中文（可用范围内）、中文仪表盘与导航说明，至少具备系统总览、API 性能、依赖健康、错误与 Trace 关联；仪表盘和告警规则全部配置即代码。页面数据必须是真实采集结果，示例图明确标注不是生产事实。
- 最少实现一个可通过安全的故障注入触发、恢复的告警路径（本地通知或可验证记录即可，无需真实向外部发送邮件/IM）。保留告警发生、恢复、状态转移与证据。
- 架构上为用户行为分析、Faro RUM 与中文平台业务运维中心定义接口和事件标准，但本任务不必完成完整 Product Analytics；用户行为事件不得写入普通运行日志来冒充可靠产品分析。
- PostgreSQL 审计日志是业务事实，不得借助 Loki 替代；运维页面需能从已授权的操作关联到 TraceId、审计 ID，权限由 .NET 而非前端控制。
- 监控系统本身提供健康状态和故障排查说明；Grafana 和采集端口仅本地或隔离网络开放，生产入口方案不能让匿名用户访问运维数据。

### 验收

- 服务启动/重启与持久化检查；API→Alloy→Loki/Tempo/Prometheus→Grafana 数据实际到达且可检索，而不是只验证进程 `Running` 或 Dashboard 能打开。
- 中文面板截图/查询证据、告警触发/恢复证据、低基数检查、重要失败注入；不能将 Console 日志具备 TraceId 视为 OTLP 端到端通过。
- 已批准之外的容器、新包或公共配置变更须登记并由 Master 审核。

## 6. 三任务并行依赖与集成 DAG

```mermaid
flowchart TD
    B["G1-INFRA 与 M0 Mac 基础已验收"] --> C["Master 冻结契约与安全边界"]
    C --> S["G1-SEC-001 登录与授权"]
    C --> F["G1-FE-001 Shell 与组件"]
    C --> O["G1-OBS-001 LGTM"]
    S --> SF["SEC + FE 真实 OIDC/BFF 联调"]
    F --> SF
    S --> SO["审计与可观测性联合验证"]
    O --> SO
    SF --> G["G1 Wave2 集成与关口验收"]
    SO --> G
    G --> P["唯一标准 Review ZIP，提交 ChatGPT"]
```

- SEC 与 FE 可以独立开发，但必须共享冻结的 URL、身份与错误合同，最终强制进行真实登录联调。
- OBS 与 SEC 可以同步进行，OBS 不得修改 SEC 的业务端点，SEC 不得自建第二套遥测管道。
- Master 负责公共基础设施修改、顺序解决依赖，必要时进行短时间的串行集成。所有并行修改使用不同 Worktree，契约/迁移/CI/根配置实行 Single Writer。
- 若运行时允许 3 个写入 Agent 同时工作且文件所有权没有冲突，可让 SEC/FE/OBS 三线并行；Reviewer 在可用槽位或各任务达到审查点时滚动介入，不必固定占用一个槽位。若实际并发受限，按关键路径优先排期。最优先保证正确性与持续集成，而非盲目提高线程数。

## 7. 必须执行的真实验证、修复和质量门禁

### 通用

- 每次合并前检查独立分支基线、文件白名单、受保护文件、依赖差异、Git 状态、代码格式、中文注释、锁图与测试证据。
- 新 .NET 端点统一 ASP.NET Core 标准错误、认证/授权、输入验证、取消令牌、结构化日志和 OpenAPI。不得使用任意生产数据库写权限。
- 所有重大错误和阻断都要立即记录，不得通过绕过依赖、删测试、静默 Mock 或声称 NOT_RUN=PASS 解决。
- G1-INFRA/M0 已通过的 4 项基础宿主测试必须保留并运行，防止后续跨模块回归；原 ASPIRE010 与不完整 Dashboard/OTLP 的事实保留到真实解决为止。
- GitHub Actions 的最终代码版本、测试与结果必须相符：校验 workflow `head_sha`，不能拿旧的成功 Run 或空 status 作为当前关口的 PASS。
- 更改仪表盘、审计、认证时建立可复现的失败场景，独立 Reviewer 核查负例和安全边界。

### G1 Wave2 纵向验收

必须在隔离开发环境完成以下演示，记录截图/响应/Trace、运行环境、命令和退出码：

1. 访问中文 Web Shell，未登录则按照 BFF 流程跳转 Keycloak。
2. 用经批准的本地测试身份成功登录，Cookie/Token 不暴露给浏览器 JavaScript；访问受保护 API 返回有权资源。
3. 用无权限或跨厂测试身份请求同一资源返回准确的 401/403（按是否认证），无敏感信息泄露。
4. 对关键允许/拒绝事件，审计在 PostgreSQL 中可查询，字段准确，不能只在 Loki 查到一条日志。
5. 发起一次真实受控 HTTP 请求，跨 .NET/代理产生正确关联标识，Grafana 能检索到对应 Loki 日志、Tempo Trace 和 Prometheus 指标。
6. 中文运维总览可看到真实 API 指标与服务健康，受控故障演练触发告警，恢复后状态可查。
7. 正式退出登录，再请求受保护资源被拒；负面 CSRF、Cookie、转发头和双实例会话测试通过。
8. 重启至少一次相关开发资源，验证合法持久状态与身份、审计记录未意外丢失；不破坏其他项目资源和用户凭证。

**不得**拿自测试程序硬编码的成功响应冒充真实端到端。允许合成的测试数据，但每个服务与状态必须真实运行并明确来源。任何阻断核心流程的失败，将 Wave2 总状态标记为 PARTIAL/BLOCKED，不能自宣称 PASS。

## 8. CI/安全/依赖与生产边界

- 在现有工程 CI 基础上增加真实 Web lint/typecheck/build/test、.NET 后端单元/集成与契约检查、关键安全负例及可重复环境验证。Windows/Linux 相关性明确；容器测试可单独 Job 与 runner 资源保障，不得永久标为可选而同时宣称生产基础通过。
- 第三方依赖与容器必须经过批准、版本/摘要固定、安全与许可证登记；对全部新依赖做漏洞/供应链检查，完整镜像 CVE/SBOM 扫描若无法完成必须在报告标 `NOT_VERIFIED`，不能偷换概念。
- `main` 此前核实 `main` 未受 GitHub Branch Protection 保护；Wave2 开始时应重新核实状态。Master 提交 ADR/建议分支规则（要求主线 CI、PR 审查、禁止非快进与强推），**不得未经许可自行改 GitHub 仓库规则**。在保护启用前继续通过任务分支的远程 CI、独立 Reviewer 与 Master 合并控制确保质量。
- 不自动向公网暴露数据库、Keycloak Admin、Grafana、RustFS Console 或其他开发服务。需要管理员权限、系统级 Docker/WSL 变更、额外付费、生产凭证、真实企业数据接入时仅阻止对应操作并报告，不擅自执行。
- 第三阶段/生产前目标 SLO、RPO/RTO、保留期、Jena HA 和真实生产审计合规仍待专项评审；此波只做基础服务，不冒充全部生产运维验收。

## 9. 交付标准：只允许一个自动审查 ZIP

每个 Owner 完成独立分支任务后提交：任务卡、文件 diff、实际命令/退出码、构建测试、失败/修复、运行截图/日志/Trace 证据、许可证变更、已知风险和提交 SHA。Reviewer 独立审查并做必要负例。

Master 完成已批准范围内的合并/分批 Push，核对主线最终 CI 实际 `run_id`、`head_sha`、`completed/success` 或准确失败状态，整合证据并固定 `BaseSha=e930935749bcb88d51abb94db4a41695bbbe6717`、阶段实际最终 `HeadSha`。

使用仓库已有 `scripts/create-review-package.ps1`，依照 `docs/development/review-package-spec.md` 生成一个完整的：

`artifacts/reviews/OntologyPlatform-Review-G1-WAVE2-<head12>.zip`

必须包含已提交的源码、配置、完整差异、Git commit/文件信息、三张任务卡、Master 集成报告、独立审查结论、CI 记录、测试证据、状态矩阵、风险、未运行项和 `manifest.json`。按已有标准独立重开验证 ZIP 的文件清单、SHA256、禁止路径、秘密扫描与成员哈希；报告 ZIP 字节数与整个 ZIP SHA256。

不得包含 `.git/`、真实凭证、Keycloak Token、Cookie、开发本地 secret、用户个人数据、Docker 卷、模型缓存、node_modules、NuGet 缓存、构建产物或其他机密。审查包不提交 Git、不上传其他无关平台。

如果任务未全部通过，仍应按实际 Head 生成一份标 `PARTIAL/BLOCKED` 的审查包并停止，不得伪造缺失的截图、运行结果、测试日志或已成功的远程 CI。

## 10. 最终报告与停止条件

最终只回复（**报告与证据先写入仓库，审查 ZIP 仍仅一份**）：

- G1 Wave2 任务总状态 `PASS/PARTIAL/BLOCKED`，SEC/FE/OBS 分项状态；
- BaseSha、HeadSha、main/三个分支对应 SHA，是否 Push，Worktree 是否干净；
- 各任务实际完成的功能，真实环境与测试结果、CI run URL/head_sha；
- 独立 Reviewer 的 Critical/Important/Minor 遗留项及修复结果；
- 审查 ZIP 的本地绝对路径、大小、SHA256、重开验证结果；
- 未验证事项和 G1 Wave2 能否通过纵向验收的判断。

最后输出独立一行：

`G1_WAVE2_READY_FOR_REVIEW`

**本轮 Git 策略：**三个 Agent 分别使用独立托管 Worktree/任务分支，达到可验证里程碑便及时 Commit + Push。Master 在契约和真实集成门禁通过后及时分批合并与 Push `main`；单写者约束适用于共享配置及迁移；不得因为 M0 已通过而将历史 Worktree 重用为本阶段工作区。交付 ZIP 只含本阶段批准源码、测试/报告证据与基于 BaseSha 的完整差异。不得只附本机 `C:/...` 或 `/Users/...` 绝对路径作为用户可检索文档链接。

**到此必须停止，等待 ChatGPT 审查。不得自动启动 G2、本体业务开发或其他关口。**
