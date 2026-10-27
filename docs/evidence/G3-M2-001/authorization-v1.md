# OntologyPlatform · G3-M2-001
## 基础可视本体建模器：Codex Master 实施授权 V1.0

> **推荐配置：**Master GPT-6.1 Sol / **High** / 普通执行模式。语义 Reviewer 如可单独选择，GPT-6 Astra / High；前端 Agent Sol / Medium–High。若不能单独配置子 Agent，Master 使用 Sol + High。
>
> **授权边界：**只授权 G3-M2，不授权 M3–M5。完成后输出 `G3_M2_READY_FOR_REVIEW`，生成唯一正式 Review ZIP V3 并停止。

## 0. 基线与开工预检

仓库：`on-dotnet/ontology-platform`。G3-M1-CLOSEOUT-002 已集成至 main，Head 为 `f0712e9174d1bff82b5f6959e0a61e723585be88`。开工必须 `git fetch origin`，使用实际最新 `origin/main` 为 Base；记录完整 SHA、工作树、活跃 Worktree/分支和同 Head CI。不得 reset、force push 或覆盖用户改动。

先读取 `AGENTS.md`、`PLANS.md`、当前授权、G3 计划、`docs/development/ai-development-efficiency.md`、Review ZIP V3 规范、资源生命周期规范、`apps/web/AGENTS.md`、`backend/AGENTS.md`、G3-M1 交付和未关闭风险。

先执行廉价 Preflight：`doctor.ps1`、`verify.ps1 -SelfTest`、Web lint/typecheck、后端 Release build、OpenAPI/TS 生成检查。记录实际命令、exit code、测试数。若依赖资产/环境缺失，先准确分类并修复；不要立刻反复跑整栈验收。不得把环境失败算成业务失败。

## 1. 目标和范围

实现可操作的基础本体建模工作台，形成真实闭环：

**打开资产/草稿 → 查看四源与语义支持状态 → 编辑已支持的简单子集 → 服务端评估 → 展示诊断 → 保存新修订 → 按现有审批发布 → 正式查询验证 → 回滚验证。**

M2 范围是 G3 计划能力矩阵第 1–11 项的已批准简单子集：
- IRI、prefix、BASE；
- 命名类、简单 subclass；
- 命名 ObjectProperty、DatatypeProperty；
- 简单命名 IRI domain/range；
- label/comment、语言标签；
- 命名个体及简单类型断言；
- 命名对象间受控的 `equivalentClass`、`disjointWith`、`inverseOf`；
- 已支持、仅源码编辑、只读保留、阻断发布等能力状态；
- 精确来源定位、中文诊断、四源导入/导出；
- 三栏 UI：左侧资产/类/属性树，中间图/源码，右侧属性/约束/诊断；
- 真实 API 集成、revision/CAS、assessment、发布与回滚。

保留已确认的彩色企业后台、深浅主题、键盘可访问性、响应式布局与窄屏后备。只改相关 Ontology 功能区，不重写整个 Shell 或 Design System。

### 非目标

- 不启动 M3 术语/单位治理、M4 身份/时间/ImpactReport、M5 高阶 OWL。
- Monaco 继续 `BLOCKED / PAUSED_BY_USER`；使用现有 textarea/源码后备，不绕过安全阻断。
- 不实现 OWL 完整推理，不把 SHACL conforms 说成 OWL 一致性证明。
- 不加载或联网解析 `owl:imports`；不执行用户 SPARQL、JavaScript 或自定义 SHACL target。
- 不新增直接依赖，不更新锁定版本，不调用收费 LLM。
- 不创建第二套 SourceBundle、身份、Evidence、语义服务或结果类型。
- 不重做 G3-M1 的四源保真、assessment、发布门禁和 V1/V2 兼容；只消费并回归这些能力。
- 不改 GitHub branch protection、历史 refs、G2 保护卷、其他项目资源或生产环境。

## 2. 先冻结公共合同，再并行

Master 先单写 `G3-M2-CONTRACT`，独立 Reviewer 只读审查通过后，才允许前后端并行实现。

合同必须明确：
- 精确结构化编辑命令、IRI/三元组/字段、revision/If-Match/CAS；
- 复杂/未支持公理的保护策略：可源码保留，结构编辑不能静默丢失；无法安全改写时明确阻断；
- assessment/profile 的读取和重评估规则；客户端不能伪造发布资格；
- API 错误码、诊断类别、来源绑定（sourceId + sourceHash + focusNode/path/sourceShape）；
- OpenAPI 与生成 TypeScript 的唯一来源和检查方式；
- 四源导入/导出必须保留原始内容及 hash；
- 组件、API、测试文件 owned_paths 与 Single Writer 责任。

先用廉价测试验证畸形 JSON、未知/缺失字段、过期 revision、缺失 If-Match、权限不足、未支持语义、OpenAPI/TS 漂移。共享合同冻结前禁止大规模并行编码。

## 3. 语义和 UI 强制规则

- “可保存、可编辑、可发布、可推理”是四个不同状态，必须分别展示。
- 简单命名公理按 M1 的 SemanticSupportProfile 执行；复杂表达式、restriction、cardinality、property chain、imports、身份公理等保留源码并给只读/阻断诊断。
- `rdfs:domain/range` 不是必填约束；多个 domain 不是任选其一。
- `allValuesFrom` 不代表至少有一条关系；OWL Functional 不等于数据库唯一键。
- 同标签/同编号/同文本不自动合并实体，不自动生成 `sameAs` 或扩大权限。
- UI 节点/边是读模型，不得从简化投影重建 RDF 并丢失未知公理。
- 编辑必须应用精确变更命令到原始图；未修改四源保持字节/hash 不变；修改后仅允许预期语义变化，保留其他三元组、语言和 typed literal。
- 诊断必须可解释并中文显示；定位不可靠时不伪造行列号。
- TSX 采用清晰多行排版，单行默认不超过 200 字符；职责明确，避免超长 JSX 和过度碎片化组件。

## 4. Agent 拆分与增量集成

并行上限 Master + 两名独立写入 Agent；需要独立 Reviewer 时暂停一个写入槽位。Master 是 `main` 唯一集成责任人。所有写入 Agent 使用独立托管 Worktree 和任务分支，及时 Commit/Push，不共用 main。

建议顺序：
1. `G3-M2-BASE`：Master 记录授权、最新 Base SHA、风险、资源快照与验收入口。
2. `G3-M2-CONTRACT`：Master 冻结编辑/评估/API/错误/权限/生成类型合同；独立只读 Reviewer 通过后冻结。
3. `G3-M2-SEM`：语义后端 Owner 实现精确编辑命令、支持状态/诊断与真实 PG/Jena 测试。
4. `G3-M2-WEB`：前端 Owner 独立实现三栏工作台、源码后备、结构编辑和诊断 UI，连接真实 API。
5. `G3-M2-INTEGRATION`：Master 尽早集成一个最小纵向切片，先跑真实 API/PG/Jena，再补完整 UI；不得等 SEM/WEB 全部完成才首次集成。
6. `G3-M2-GATE`：真实导入/编辑/评估/保存/发布/查询/回滚 E2E、权限负例、主题/键盘/窄屏回归。
7. `G3-M2-REVIEW`：非作者独立审查、同 Head CI、唯一 Review ZIP V3、M2 自身资源收尾，完成后停止。

每张任务卡必须记录 Task ID、Base SHA、Owner/Reviewer、实际 Worktree 路径、owned_paths、read_only_dependencies、合同 Owner、验收命令、负例、证据与停止条件。公共 DTO、迁移、OpenAPI/TS 生成物、CI、锁文件、AppHost 公共配置、Design Tokens 由 Master 单写。DRAFT 不可合并；独立 Review 和必要 CI 通过后分批集成，不等待整个 M2 结束。

## 5. 强制效率规则（必须执行，不只是写报告）

本节要求与 `docs/development/ai-development-efficiency.md` 一致；若发现合同缺口，应在本任务中更新仓库文件并添加自动回归，不得只依赖聊天记忆。

1. **Preflight-first：**先确认锁定工具链、依赖恢复、真实测试入口、Docker socket、AppHost/Fuseki canonical 镜像、OpenAPI/TS 生成、迁移与证据输出目录。缺前提先修或 BLOCKED，不盲跑整栈。
2. **合同先行：**共享 DTO/错误/事务/证据合同先冻结并测试，之后并行；共享文件 Single Writer。
3. **分层测试：**静态/单测 → 模块集成 → 纵向 E2E → 最终完整门禁。廉价失败先修；按变更范围跑受影响测试；只有稳定候选跑完整入口。禁止无诊断重复整栈重试。
4. **早集成：**至少在 M2 期间完成两次可运行纵向集成点：第一点证明真实 API + PG/Jena 的简单编辑与评估；第二点证明 UI 到真实 API 的完整编辑/保存闭环。每个点独立记录 Head/CI，不等最后才第一次联调。
5. **失败诊断：**每次失败保留准确命令、exit code、固定错误类别、关键日志窗口和复现入口。若失败只发生在构建/启动阶段，不得声称业务测试已运行。
6. **Fuseki 不增量堆积：**只使用仓库 `scripts/maintenance/canonical_fuseki.py` 的内容寻址入口。AppHost/测试脚本禁止自行 `docker build` 同一 Dockerfile；先验证镜像 context hash 命中。每次验收结束核查 image/history 数量变化。
7. **证据分层：**过程截图/全量遥测进入本地归档；正式 V3 包只带最终稳定代表截图（每页面/主题/视口最多一张，默认最多 12 张、PNG 压缩目标 3 MiB），其他证据用准确 Git blob/hash/commit/path 索引。ignored 清单只聚合，不逐文件膨胀 manifest。所有当前源码和当前任务关键文本证据各存一份。
8. **交付前预检：**开发早期就跑正式 V3 构包器/VerifyOnly 的小型真实 fixture；在最终业务验收前至少用当前稳定候选生成一次非最终预检包，检查 Schema/证据字段兼容。最终 Head 冻结后再生成正式包。
9. **交付顺序固定：**源码/格式 → 受影响测试 → 独立 Review → commit/push → 同 Head CI → 唯一 V3 包 → 独立重开验证 → 资源收尾回执。最终 `git diff --check` 必须 exit 0。CI 事实必须查询 GitHub 实际 run 与 `engineering`/`governance-integration` 两个 Job，不能由调用者传入 `success` 伪造。
10. **时间记录：**记录 UTC 开始/结束及实现、等待、环境、测试、CI、返工、封包分类；无法观测记 `UNKNOWN`。墙钟与活跃工时分开，不从聊天时间推断工时。
11. **资源收尾：**开始/结束记录容器、卷、镜像、Build history、Worktree、分支、Review ZIP 与缓存。清理仅限本任务明确创建且有精确白名单的资源；保留 G2 保护卷和其他项目数据。Build cache 共享时只报告，不全局 prune。不得为了减少计数删除未知资源。
12. **防跨会话丢规则：**所有重要合同、任务状态、恢复命令和效率规则写入 Git。新会话/新机器必须读取当前授权、handoff、效率规范、V3 包规范、资源生命周期规范并 fetch 最新 main。聊天不是唯一状态来源。

## 6. 必须通过的测试

先核实仓库中真实存在的命令；不得创建空壳验收入口。M2 至少包括：
- 四源导入/导出 hash 与未修改字节保真；
- 简单类、属性、subclass、label/lang、individual 等结构化编辑真实保存；
- 复杂/未知公理在 UI 编辑/保存后仍完整保留，不能静默丢失；
- 非法 Turtle、伪造/过期 assessment、过期 revision、缺 If-Match、并发修改、越权和跨厂区请求失败关闭；
- SHACL 诊断和语义支持状态分别呈现，不冒称 OWL 推理；
- 真实 PostgreSQL/Jena/RustFS 发布、正式查询和回滚；
- G2 历史 V1/V2 Release/Run/SSE 兼容回归；
- OpenAPI 与生成 TS 一致，未知字段/缺字段负例；
- 深浅主题、键盘操作、窄屏布局、浏览器 E2E 和真实 API 集成；
- Fuseki canonical cache hit 不新增镜像 ID/Build history；
- V3 Review ZIP 默认创建、VerifyOnly、hash、证据索引、体积限制和旧 V1/V2 验证兼容；
- `git diff --check` exit 0；最终 GitHub CI 与提交 Head 一致。

零测试、全 Skip、Mock 成功、静态配置存在都不能判 PASS。真实模型未运行仍记 `NOT_RUN`。不得为让测试通过放宽语义或生产预算。

## 7. Git、交付和停止条件

- 任务分支采用 `codex/g3-m2-<task>`，具体命名与实际 Worktree 由 Master 记录；不猜测路径。
- 每个可验证切片及时 Commit/Push；Master 审查后尽早集成 main。禁止强推。
- 最终只交一个正式 V3 Review ZIP，≤10 MiB 为目标，>10 MiB 给分类体积报告，>15 MiB 默认阻断；不得为缩包省略关键源码/测试。
- ZIP 必须从已提交 Head 生成，Base/Head 为完整 SHA；独立重开并校验成员散列、diff、源码 blob、证据索引和真实 CI。
- M2 任务资源只清理明确归属、可再生的临时资源；不删除 G2 保护卷、历史 refs 或其他项目资源。
- 若语义可能静默丢失、旧版本兼容失败、未经批准依赖必需、真实 PG/Jena 不可用、同 Head CI 失败或 Review ZIP 无法独立验证，停止相关任务并报告；可并行的无依赖任务继续。

交付包必须包含源码/diff、任务卡、合同、测试矩阵、实际 CI、独立 Reviewer、资源收尾前后记录、效率数据和未关闭风险。明确保留 Monaco `BLOCKED`、真实 LLM `NOT_RUN`、完整 OWL 推理及生产 HA/SLO、Windows/Intel 原生测试等状态。

**只完成 G3-M2。最终输出 `G3_M2_READY_FOR_REVIEW`、唯一 Review ZIP 路径/大小/SHA-256、Head SHA、同 Head CI 链接和 PASS/PARTIAL/NOT_RUN 摘要，然后停止。不得自动启动 M3。**
