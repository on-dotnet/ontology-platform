# OntologyPlatform · G3-M3-001
## 术语、标准、单位量纲与研发效率治理：Codex Master 实施授权 V1.0

> **模型配置（推荐）**：Mac Codex Master **GPT-6.1 Sol · High · 普通执行模式**。语义建模和单元/量纲审查优先高强度；前端和流水线工程可用 Medium–High。独立 Reviewer 如可选择使用 GPT-6 Astra · High。子 Agent 不能单独设置模型时沿用 Master 配置。
>
> **执行边界**：只授权 G3 **M3** 及本文件列明的 M2 效率纠偏任务，**不授权 M4/M5、G4/G5**。完成后生成唯一正式 Review ZIP V3，输出 `G3_M3_READY_FOR_REVIEW`，停止待审。不得把文档、CI 绿灯或接口存在当作真实产品功能 PASS。

## 一、正式基线与必须读取的仓库合同

仓库：`on-dotnet/ontology-platform`，上次核实 `main` 为 `c8f1040829b2bfe1e9f7e36223092286975643f0`，CI 为 `https://github.com/on-dotnet/ontology-platform/actions/runs/40545746924`，两个 Job 成功。**开工时重新 fetch 并核对实际最新 origin/main 及工作树，不能盲目硬编码旧 Base。**

Master 先完整读取：`AGENTS.md`、`PLANS.md`、`docs/tasks/current-authorization.md`、G3 已批准的五里程碑计划、M2 交付与效率报告、`docs/development/ai-development-efficiency.md`、`docs/development/review-package-spec.md`、`docs/development/resource-lifecycle.md`、适用子目录 AGENTS、当前验收脚本和 `.github/workflows/ci.yml`、canonical Fuseki Dockerfile/构建器/下载脚本与测试、G2/G3 的数据合同和审计/发布/版本策略。

先核对真实源码、现有接口和脚本状态；不得从旧提示词推断尚不存在的项目文件。检查并保护未提交的用户文件、旧 Worktree、真实开发卷和历史审批/测试事实。保存新任务卡与当前授权，不重写过去的 PARTIAL/NOT_RUN/BLOCKED 事实。

### G3-M2 独立复审结果与必须解决的问题

已认可 M2 范围内的三栏 UI、受控简单结构编辑、四源语义保真、真实 PG/Jena/RustFS 发布查询回滚、Web/OIDC 与同 Head CI。总体 PARTIAL 保留明确非目标。

M3 必须实质解决这三项工程问题，不得仅创建复盘文档：

1. **跨 GitHub Actions 运行的 Fuseki 构建/下载复用缺失**。过去 3 次旧 CI 在单一 Dockerfile RUN 达 600 秒超时；修复后单次构建已通过，但 Mac 本地镜像无法供全新 Linux Runner 使用。重复 600 秒等待必须通过阶段前置验证、持久缓存或不可变制品以及失败指纹门禁减少。
2. **浏览器 UI 状态契约漂移**。旧验收脚本默认图视图始终可见，M2 默认源码视图。旧测试约 13 分钟后才报错；必须将默认状态、模式切换、窄屏和历史流程写成自动契约，在昂贵整栈测试前运行。
3. **Docker 生命周期只对卷完成收尾**。M2 已清理 8 个测试卷和 1 个 fixture，留下 11 image IDs、2 条 Build history、共享缓存（按 M2 报告约 609MB）。需逐 ID 区分固定镜像、可替代旧镜像、失败/成功构建记录、共享缓存和 Loki 数据卷，做必要的实际收尾，不删除有效开发环境。

另需解决可量化的工程效率：测试失败类型及构建阶段耗时记录不完整、证据字段 late schema reject、修复后反复生成候选并重跑昂贵 CI。必须使常见故障成为自动失败分类和早期检查。

## 二、关口 E0：先落地工具与效率修复（M3 业务大规模实施前）

### E0-A · Canonical Fuseki 的跨 CI 运行复用及根因定位

1. 保持 Fuseki `6.2.0`、JRE 及 SHA-512/镜像摘要锁定，不放宽 HTTPS、散列、安全或预算；沿用单一 `canonical_fuseki.py`，AppHost 与集成测试禁止重复独立构建同一 Dockerfile。
2. 审查当前 GitHub Actions ephemeral runner：**缓存命中必须来自与本次运行不同的全新 Workflow Run**；同一 Run 内第二次 `reused:true` 不等于跨运行缓存。提出并实现适配当前 CI 的可靠且可审计的复用方式：优先比较 GitHub 官方缓存/BuildKit `gha` 远程缓存与受控 GHCR 不可变镜像。**不得未经用户明确批准新增付费服务、启用新的包发布权限或推送公共镜像**。如果 GHCR 发布或新增第三方 Action 是最优方案，先提交精确许可、仓库权限、镜像签名、费用/配额和替代方案审批；不影响无依赖的 M3 工作。
3. 缓存键必须依赖 Jena 版本、JRE/基础镜像摘要、Dockerfile、fetch helper、构建上下文及锁定散列；不同架构（macOS arm64 开发容器 / Linux amd64 CI）必须区分镜像平台、不可混用错误架构制品；缓存损坏必须拒绝/失效并安全回退，不能跳过 SHA-512 验证。
4. 使用**至少两次独立 GitHub Actions 运行**验证：首次强制缺缓存/冷构建成功；第二次在相同输入的新 runner 恢复已验证缓存或拉取固定 digest，实际跳过重复外网源下载；修改任一构建输入则缓存失效并重建。记录两次 `runId`、runner、cache key、image ID/digest、命中率、步骤耗时、最终 SHA 与成功结果。如果 GitHub 的权限/缓存限制导致无法达到，标记 `BLOCKED` 并提交精确替代路径，不能宣称已解决。
5. 在 CI 冷构建的网络/下载、SHA 校验、解压/COPY、镜像准备阶段分别输出脱敏 `stage`, `durationMs`, `outcome`, `errorCategory`, `inputFingerprint`。遇 checksum/权限/配置错误立即失败；网络错误只做有界重试。若同一构建输入和环境连续出现完全相同失败，后续候选先复用失败指纹与短复现确认，**不要再次无条件等待 600 秒**。但不得以旧失败缓存跳过应当实际执行的最终门禁或将其判 PASS。
6. 生成单独的安全模拟负例：网络超时、两端不可达、checksum 错、Dockerfile COPY 缺失、损坏缓存、平台不匹配、缓存 miss/hit、CI 恢复失败。要有真实冷构建与跨 Run 缓存命中证据，不能以模拟缓存代替全部验证。

### E0-B · 浏览器状态与验收前置合同

1. 在 `apps/web` 为三栏建模工作区定义**明确的默认视图、源码/图切换、选中实体、编辑状态、错误/权限、窄屏切换**的可测试合同。其变更必须同步调整 E2E，旧 G1/G2/G3 脚本如有界面期望须显式进入目标视图。
2. 增加独立的快速浏览器 Smoke，包含 `默认视图`→`切换图`→`canvas 可见`→`切回源码`→`保存/取消` 以及一个历史工作流，不依赖等待超时猜测视图；用角色/语义选择器，保留真实断言。
3. 每次相关 UI 变更时在完整 263 项浏览器门禁前运行 Smoke；通过代码检查或 CI 判定需要运行的范围，不以跳过旧流程、吞异常、延长等待或仅 Mock 通过解决冲突。
4. 必须有故障注入：将默认视图改变或隐藏目标面板时，Smoke 在短时内 FAIL，修复合同后 PASS。保存实测步骤/耗时。

### E0-C · 构包证据预检、自动计时与资源创建即登记

1. 正式 V3 构包器必须**在编码早期**使用历史证据格式及小型当前任务 fixture 验证字段兼容；新增标准证据 Schema 的生成器/校验器，自动检测缺/多字段、CI Head 不匹配、无效 Status、错误末尾换行、忽略路径膨胀、截图超限。正式 Head 冻结之后不能因为可预见的证据字段漂移再次提交/重跑同 Head CI。
2. 创建轻量 `TaskRunTimeline` / JSONL，所有步骤直接记录 UTC 开始/结束、任务类型、运行 ID、输入摘要、实际耗时、结果、失败类别、依赖/并发关联；可自动计算墙钟、累计任务运行时长、可观察的关键路径与复验次数。无法获知的 Agent 活跃/思考时间标记 `UNKNOWN`；不要把并发的运行时间相加冒充墙钟。对个人聊天/密钥不得抓取。
3. 任务创建 Docker 容器、卷、镜像/构建 history 时即记录任务归属、运行 ID、构建输入 hash、image ID、复用/新增、到期及清理候选；一切删除按准确资源 ID、任务白名单、对照当前运行引用、恢复价值、DryRun/Apply、真实 before/after 及后验，保留至少一套可用开发环境。
4. 在本任务末尾对新产生且不再需要的构建记录和镜像引用进行实际受控清理。**共享 build cache 不明确属于本项目时不得全局 prune**；旧 G2 保护卷未经新授权不得删除。Build history 删除需验证真实 Engine/Builder 代际稳定，不能只看 `rm` 退出 0。
5. 把 E0-A/B/C 的最终规范、实际可运行命令、CI 约束和常见误报/失败模式持久化 `docs/development/ai-development-efficiency.md`、资源生命周期和适用 AGENTS/PLANS（短规则+规范链接），增加正反自动化回归。不能只存在 ChatGPT 提示词、交接记录或临时侧聊。

**E0 独立门禁**：E0-A/B/C 的必要静态/负例和真实 CI 验证、独立 Reviewer 完成前，不启动整栈 M3 正式验收；M3 的 SEM/Web 代码工作可以在公共合同冻结后于独立 Worktree 并行推进，不能反复因 E0 网络阻塞而停止无关开发。

## 三、G3-M3：术语、标准、单位和量纲建模业务闭环

M3 必须复用已发布本体、四源 SourceBundle、发布治理、CAS、审核、SSE/证据、RDF/SHACL 与历史 V1/V2 兼容，不建立第二套本体权威、指标引擎或通用规则平台。

### M3 业务范围

- SKOS `ConceptScheme`、`Concept`、`notation`、`definition`、`prefLabel`、`altLabel`、`hiddenLabel`；中英语言标签、`broader/narrower/related` 和受控概念对齐；基于正式 RDF/OWL 语义。
- 术语管理 UI：目录、创建/编辑/废弃与版本、别名/多语言、标准来源、引用位置、搜索、差异及审核发布；与三栏本体编辑器状态一致，语义异常准确定位，保留来源证据。
- SKOS 完整性和冲突验证：每概念每语言最多一个 `prefLabel`、同一语言标签不可同时处于互相冲突的 SKOS 标签关系；概念环、未登记引用、重复 notation、跨 Scheme 标识冲突按明确的域治理政策判定，不把全部 SKOS 关系当作 OWL 逻辑推理。未知或不确定情况单独呈现。
- 单位、量纲、quantity kind 和符号的**版本化语义引用**：单位 IRI、量纲、适用属性、标称单位、原始标准、精度/版本和来源；验证属性量纲匹配与未登记单位，避免将 ℃、K、MPa、t 等字符串当唯一标识。**M3 不实现通用单位换算和 G5 指标计算**。
- 人工/AI 的职责分界：术语标准的候选变更必须经过正常审核才能进入正式版本；当前 M3 不使用真实收费 LLM，不允许 LLM 自动批准正式语义资产。
- 对应的真实端到端闭环：**建术语与单位引用 → 验证冲突 → 审核批准 → 生成不可变 Release → Jena 正式查询与应用显示 → 历史版本回滚与证据追踪**。
- 事件/时间、跨系统身份、影响分析、完整 Owl 推理、复杂 imports 和指标规则仍按 M4/M5/G4/G5 边界，不得自行扩展本任务。

### QUDT 精确外部资产审批边界

既有 G3 计划建议 QUDT `v3.5.3` 最小词汇资产，但此版本标准资产**尚未得到独立许可引入批准**。不得因为计划提及就自动下载/嵌入全部 QUDT/UCUM 派生内容。请先列明所需**准确文件、tag/commit、SHA256、CC BY 4.0 与可能涉及的 UCUM 限制、署名/改动要求及最小集许可证信息**；需要引入该第三方资产时提交独立审批。在批准前，使用明确标记为 Synthetic 的合法 RDF 单位 fixture 验证结构和服务，不向用户宣传完整 QUDT 兼容性。未获批不阻断不依赖外部词表的 SKOS 与前端业务任务。

### 任务拆分与并行

1. `G3-M3-BASE`（Master）：最新 main/Base、当前授权、任务卡、现有瓶颈及环境资源快照。
2. `G3-M3-EFFICIENCY-E0`（Master+专业工程 Agent）：完成 E0-A/B/C，公共 CI/缓存/状态合同单写，独立 Reviewer 审查。
3. `G3-M3-CONTRACT`（Master）：冻结 SKOS/单位语义、术语身份、错误码、发布/版本、OpenAPI/TS；先跑受影响的合法与非法合同测试。
4. `G3-M3-SEM`（独立 SEM Worktree）：SKOS/单位/引用/验证/术语版本与真实 PG/Jena；不改共享合同和迁移。
5. `G3-M3-WEB`（独立 FE Worktree）：术语与单位语义 UI、三栏集成、中文校验、真实 API 与浏览器用例；不修改公共 Tokens/生成 TS。
6. `G3-M3-INTEGRATION-1`：最早可运行的 PG/RIOT/SHACL/术语 API 子闭环；独立 Review 后增量集成与 CI。
7. `G3-M3-INTEGRATION-2`：UI→真实服务→验证→发布→Jena 查询闭环，历史版本读回及回滚。
8. `G3-M3-REVIEW`：最终真实验收、安全/性能/License 检查、同 Head CI、Review ZIP V3、Docker/Worktree 生命周期收尾。

遵守 Master 统一 main 集成、公共文件 Single Writer、两个独立写 Agent 使用不同 Worktree 和任务分支、及时 Commit/Push、Reviewer 只读。原并发上限为 3；不能把整个团队放在共享 `main` 上抢写。

## 四、强制验收（不得只用静态配置/文档 PASS）

- `doctor -CheckDocker`、锁恢复、C# build/format/全部影响测试、Web lint/typecheck/test/build、OpenAPI 与生成 TS 一致，所有实际运行命令/退出码记录；新增直接依赖或许可争议需单独审批。
- 真实 PostgreSQL + Jena/Fuseki + RustFS + Keycloak/Governance 集成；SKOS、词汇、单位引用、冲突、中文 UI、审计、来源证据、异人审批、发布、查询和回滚。G2/M1/M2 真实服务与权限回归不可因 M3 通过而失效。
- 成功和负例：非法语言标签、跨语言冲突、重复 notation、歧义/跨 Scheme 错配、错误量纲、丢失引用、旧发布、源 hash 变更、过期 revision、越权、空数据、无法确定等均准确反馈，绝不静默丢 RDF 语义。
- 正式 M3 端到端测试前：E0 完成至少一次新 runner CI 冷构建和第二次跨 runner CI 缓存复用证明；若最优方案需未批准外部制品/权限，则报告 `BLOCKED`，不能暗中跳过该门禁。
- 真实 UI Smoke（默认视图/图源码切换/编辑）必须在完整浏览器场景之前运行，故障注入确认测试能够快速 FAIL；不靠延长等待规避断言。
- 对重复失败的 Fuseki 构建输入：失败指纹阻断昂贵的无意义重试，短期故障先复核是否可独立重现；最终绿色 CI 仍须真实执行。
- 首个组合切片结束至少一次真实集成和同 Head CI，最终完整验收前至少两次可验证的增量集成，不集中到最后一轮。
- 任务级阶段计时机读报告及摘要表：总墙钟、可确定的构建/测试/CI/收尾耗时、并行叠加、返工原因/重复次数，未知列 `UNKNOWN`，不推算用户花费或模型成本。
- 正式 Review ZIP V3 预检应在开发早期用真实当前 Schema 执行；最终 Head 冻结前完成文档和证据；最终 CI/ZIP/独立重新打开/回执必须同一个 Head。ZIP 目标 ≤10MiB；大于门槛需说明必要 payload，不为了缩包丢关键证据。
- Docker 资源必须产生 before/after（容器、卷、镜像、Build history、共享 cache），本轮新增**失败/无引用构建记录**应在确认不需要后清理，而非全部永久 `KEEP`；保留一套有效开发镜像与数据。历史 G2 保护卷或不明镜像不得为追求数量删除。
- 旧 V1/V2/V3 Review ZIP 兼容、旧 Release/Run/SSE 的读回与回滚仍需通过；`git diff --check` 最终 exit0，全部已批准 CI required jobs 在最终 Head 成功。
- 留存旧失败事实，不能把原失败报告改写为 PASS，修复后追加对应绿色证据。

## 五、停止与交付

本轮仅获批 G3-M3 + E0 工程效率改进；不自动启动 M4/M5/G4/G5，不采购付费云资源、不使用生产数据、不调用收费模型、不修改 GitHub 分支保护或删除其他项目资源。

如遇需要新增直接依赖、公开/私有镜像推送、镜像缓存额外权限或第三方词表许可，必须先登记具体方案/变更范围并等待人类审批；其他无关任务可继续。不能以 CI/环境阻断绕过真实业务验收或放宽安全限制。

最终报告：TaskId、Base/Head 完整 SHA、同 Head GitHub CI run 和两个 Job、真实测试结果、资源回收 before/after、工程效率改进前后、遗留风险矩阵、V3 Review ZIP 路径/字节数/SHA256、独立复验及审查状态。

最终仅交付一个 Review ZIP，输出 `G3_M3_READY_FOR_REVIEW`，停止等待 ChatGPT 独立复审。
