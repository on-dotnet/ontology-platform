# OntologyPlatform · G3-M1-001
## 本体源码与语义保真：Codex Master 实施授权 V1.0

> **模型建议：**Master 使用 **GPT-6.1 Sol / High / 普通执行模式**。独立 OWL/RDF Reviewer 如可单独选模型，使用 GPT-6 Astra / High；前端 Agent 使用 Sol / Medium–High；测试/文档分析 Agent 使用 Sol / Medium。若无法给子 Agent 单独配置，Master 使用 Sol + High。
>
> **授权边界：**正式授权 G3 **M1**，不授权 M2–M5。完成后输出 `G3_M1_READY_FOR_REVIEW`，生成唯一轻量 Review ZIP 并停止。该标记不代表 ChatGPT 已验收通过。

## 0. Master 职责与当前基线

你是 OntologyPlatform 的 G3 Codex Master / Integrator。遵循仓库 `AGENTS.md`、`PLANS.md`、`.codex/config.toml`、`.codex/agents/*.toml`、当前授权、阶段收尾规范及 Review ZIP V2 合同。不要重新设计已批准的总架构。

上次核实 `origin/main` 为 `d6aab6b47e63c9d5deadfa480f6659c62c5ed138`。开工必须重新 `git fetch origin` 并记录最新 `origin/main` 完整 SHA；若 main 已前进，使用最新主线，不得 reset、覆盖或强退回旧 SHA。

将已审查计划保存为 `docs/planning/g3-ontology-modeling-and-governance-plan.md`，保留未验证状态。建立 G3-M1 任务卡、授权记录和交接索引；不得覆盖 G2 或 PRE-G3 历史证据。

### 本次目标

完成首个可运行纵向切片：
- 四源 `SourceBundle`（ontology、shapes、vocabulary、data）的原始字节、hash、保存、导出与重入；
- 版本化语义支持 profile 和与准确 revision/四源 hash 绑定的 assessment；
- 新发布必须使用有效 assessment；保留旧 V1/V2 发布、Run、SSE 和回滚兼容；
- 有界、精确的 RDF 图比较，正确处理空白节点同构；
- 基础 Web 资产/源码/支持状态、导入导出及语义诊断；
- 真实 PostgreSQL/Jena/RustFS、授权、发布查询和回滚验收；
- 可重复的 G3-M1 验收脚本、同 Head CI、独立审查及唯一 Review ZIP。

### 不在本次授权范围

- 不启动 M2–M5；不实现 G4 连接器、G5 指标/规则业务。
- 不接入 Monaco；保持 `BLOCKED / PAUSED_BY_USER`，使用现有 textarea/源码后备。
- 不新增 Turtle parser、OWL reasoner、Java 服务或未批准运行时依赖；复用 Jena 6.2、RIOT、SHACL。
- 不加载或联网获取 `owl:imports`，不执行用户 SPARQL、JavaScript 或自定义 SHACL target。
- 不把 SHACL conforms 当作 OWL 一致性证明，不声称未实现的推理已完成。
- 不调用收费模型；deterministic Agent 测试不能冒充真实 LLM 验收。
- 不修改 GitHub 分支保护，不删除历史 refs/Worktree/G2 数据卷，不改写 Git 历史。
- 不覆盖 G2 manifest、源字节、历史发布制品、Run snapshot、SSE 事件或证据。
- 不用宽松 JSON 解析掩盖 DTO 漂移；不以空测试、Mock 代替关键真实集成。

## 1. 冻结公共合同后再并行

开工前先读当前授权、G3 计划、G2 合同/交接、真实源码、发布流程、`SourceBundle`、hash、CAS、审计、Outbox、MCP、SSE、OpenAPI/TS 生成流程、Review ZIP V2 规范及资源生命周期规范。

重新确认 `origin/main`、工作树、分支/Worktree、CI 和工具链。若存在非预期改动，先保护并报告，不覆盖。

### 1.1 SemanticSupportProfile

建立版本化 profile，明确每项能力的 `edit / preserve / publish / validation` 状态、推理模式与资源预算。Profile 有稳定版本和内容 hash。Assessment 与发布绑定明确 profile 版本，不得静默切换策略。

### 1.2 SemanticAssessment

分开表达：
- Turtle/RIOT 解析；
- 语义能力支持判定；
- SHACL Core 验证；
- 平台治理检查；
- `publishEligible`；
- 诊断、来源定位、预算状态；
- `draftId`、准确 revision、四源 hash、profile version/hash、assessment hash、时间及执行版本。

不能用单一 `valid=true` 混合表达解析成功、SHACL conforms、OWL 一致性和可发布性。`INDETERMINATE` 是独立状态，绝不能当作零差异或 PASS。

Assessment 必须由服务端基于真实源码和实际 RIOT/SHACL 运行时生成。发布端重新核验绑定与 hash，拒绝客户端伪造、跨 revision 复用、过期或 profile 不匹配的 assessment。

### 1.3 新发布门禁与历史兼容

所有新的 G3 发布必须绑定当前 revision、四源 hash、profile 和有效 assessment。源、revision 或 profile 变化会使先前批准失效。保持已有异人审批、24 小时有效期、If-Match、CAS、审计和 Outbox 事务语义。

**旧版本兼容是 M1 强制验收项：**
- G2 旧制品/报告可能没有 `profileVersion` 或 `assessmentHash`。不得伪造缺失字段，也不得自动把旧报告升级成新 profile。
- 用显式 Legacy reader/validator 读取旧发布和历史报告；历史 Run、MCP 记录、SSE 事件继续使用原 snapshot。
- Legacy 记录不能直接授权新的 G3 PUBLISH。
- 旧 Release 回滚按其原始语义边界重新验证制品与同批正式图，再执行当前权限、异人审批和 CAS；不能绑定当前草稿或强行补字段。
- 旧制品无法可靠验证时，明确阻断并返回原因。
- V2 写入前，真实验证兼容 V2 的回退二进制读取；V2 写入后不能直接把旧 G2 宿主当作安全应用回退。应用回退与业务 Release 回滚分开验收。
- 数据库迁移采用兼容增量，不得以删除数据的降级迁移恢复。

### 1.4 有界精确 RDF 图比较

实现集合去重、分区细化剪枝、空白节点双射搜索，并最终核对完整三元组集合。默认上限：
- 使用现有 triple/字节预算；
- 最多 128 个空白节点；
- 最多 100,000 个搜索节点；
- 最多 5 秒；
- 跨源比较隔离 blank node 作用域，不能按 label 字符串直接比较。

同构图即使 blank node label 不同也应正确判断；非同构图必须正确判异。超时、取消或预算耗尽返回 `INDETERMINATE`。需要确定结果的编辑/发布必须失败关闭；不能把 `INDETERMINATE` 显示为“无差异”。


## 2. 语义支持边界

M1 建立并测试 20 项语料/能力矩阵，但这**不意味着 20 项都必须在 M1 提供图形编辑或完整推理**。按计划区分 V（可视化编辑）、S（专家源码可编辑并通过 RIOT）、R（结构视图只读保留）、B（阻断相关操作/发布）、L（后续能力）。

- 简单命名类、子类、对象/数据属性、简单 domain/range、label/comment、命名个体及类型断言，以及命名对象间有限 `equivalentClass`、`disjointWith`、`inverseOf`，按 profile 明确支持范围。
- 复杂表达式、属性特征、restriction、cardinality、布尔表达式、property chain、`owl:imports`、身份公理等：保留源码；未支持时禁止结构改写和发布，给出可解释诊断。
- `rdfs:domain/range` 不解释成必填约束；多个 domain 不解释成任选其一。
- OWL `allValuesFrom` 不代表至少存在一条关系；OWL Functional 不等于数据库唯一键；SHACL 约束与 OWL 公理分开。
- 不同 IRI、相同标签/编号不自动等于同一实体；不自动生成 `sameAs` 或扩大权限。
- 不联网加载 imports，不做未经实现的逻辑推理。
- 不从简化 UI 节点/边投影重建并丢弃未知公理。

## 3. 真实实现与模块边界

复用现有模块、DTO 和服务，不创建第二套 `SourceBundle`、身份、Evidence 或 Result。Ontology 拥有源码、支持 profile、评估和比较；Publishing 拥有批准与发布；SemanticQuery 拥有正式读取；Governance 拥有审计。

需要增量定义/完善：
- profile 与 assessment 的 DTO、存储和版本绑定；
- 新发布资格校验与旧版本显式兼容；
- `VersionRef` 与四源 Diff 的最小契约；
- 影响报告只冻结未来扩展所需的最小接口，M1 不实现 M4 完整 ImpactReport；
- 错误码、诊断来源、OpenAPI 与 TypeScript 生成契约；
- G3 专用验收入口与隔离证据输出。

所有 API 继续使用现有 `/api/v1`。导入导出继续使用原始 SourceBundle；G3 正式交换格式先冻结为 Turtle，不在本轮扩展多格式。结构编辑使用精确变更命令和 revision/CAS，不能把用户输入拼成任意查询。

## 4. 任务拆分、并行和集成

本仓库并行上限为 3：Master + 两个独立写入 Agent。需要独立 Reviewer 时暂停一个写入槽位。公共合同、迁移、OpenAPI/TS 生成产物、CI、根配置和 Design Tokens 由 Master 单写；语义与 Web 在合同冻结后并行。

按以下顺序执行，不要同时启动全部 G3 里程碑：

1. **`G3-M1-BASE`（Master）**：记录授权、最新 Base SHA、计划、任务卡、风险、四个历史补丁“采用当前 main 替代”的覆盖映射。不要删除历史分支或重复 cherry-pick。
2. **`G3-M1-CONTRACT`（Master + 只读 Reviewer）**：冻结 profile/assessment、错误码、发布资格、Legacy 兼容、V1/V2 DTO、OpenAPI 和 TS 正反例。合同未通过独立审查前，禁止 SEM/FE 对共享契约编码。
3. **`G3-M1-SEM`（独立语义后端 Worktree）**：四源字节保真、20 项语料支持矩阵、assessment、精确图比较、发布门禁及真实 PG/Jena 测试。
4. **`G3-M1-WEB`（独立前端 Worktree，与 SEM 并行）**：基础资产/源码/支持状态、导入导出、诊断与源码后备，连接真实 API。只修改分配的 ontology feature 目录与测试；不修改生成客户端和公共 Design Tokens。
5. **`G3-M1-GATE`（Master）**：真实组合发布→正式查询→回滚 E2E、故障/安全负例、G3 验收脚本、证据输出隔离与 TSX 可读性检查。
6. **`G3-M1-REVIEW`（非作者 Reviewer）**：独立检查源码/契约/语义标准/测试/安全；集成到 main 后重跑同 Head CI，生成唯一轻量 Review ZIP，完成本任务获授权范围内的资源收尾，然后停止。

每张任务卡必须明确 Task ID、Base SHA、Owner/Reviewer、独立 Worktree 路径（使用工具实际返回路径，不猜路径）、owned paths、只读依赖、验收命令、负例、证据及停止条件。每个可验证任务及时 Commit/Push；DRAFT 不等于可合并。Reviewer 通过且真实 CI 通过后，Master 尽早集成，不要等到整个 G3 完成才首次集成。

不得将独立 Agent 报告伪装成另一个 GitHub 用户的批准。不要修改 GitHub branch protection/rulesets；相关配置需要单独授权。

## 5. 测试与验收

开工先记录以下检查结果：
- `pwsh -NoProfile -File scripts/doctor.ps1 -CheckDocker`
- `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`
- `dotnet build backend/OntologyPlatform.slnx --no-restore`
- `pwsh -NoProfile -File scripts/verify-web.ps1`
- `node apps/web/scripts/generate-types.mjs --check`

先核实测试入口真实存在；不得假设上述所有命令在当前版本都已实现。拟新增的 `scripts/acceptance/g3-governance.ps1 -Milestone M1 -StartRuntime` 必须真正实现、运行并有正反例，不能只创建空壳。

M1 必须覆盖：
- no-op/未修改：四源原始 UTF-8 字节、BOM、换行、注释及 hash 不变；
- 实际结构修改：只修改明确三元组，保留其余 RDF 语义；旧 revision 原始字节保留；
- Turtle 非法时不创建 revision；
- 20 项语料逐项显示能力状态；未知/复杂公理源码可保留，不能静默删除；
- blank node 重命名同构正例、近似非同构负例、对称图/环/共享节点、预算耗尽与取消；
- 伪造/过期/跨 revision/profile assessment、源 hash 改变、错误角色、跨厂区越权、自批/过期审批、If-Match 冲突全部失败关闭；
- 真实 PostgreSQL/Jena/RustFS 的发布→查询→回滚；故障发生时 active Release 不被半更新；
- G2 历史 V1/V2 manifest、Release、Run 和 SSE 兼容读取及回滚负例；
- OpenAPI 与生成 TS 逐字节一致；错误状态/多余字段/缺字段的契约负例；
- UI 深浅主题、键盘操作、窄屏后备和真实 API 集成；
- 未经批准依赖不存在；Monaco 未接入；
- CI 与最终 Head SHA 一致。

测试状态严格区分 `PASS / FAIL / PARTIAL / BLOCKED / NOT_RUN / NOT_VERIFIED`。零测试、全 Skip、静态配置存在、Mock 成功都不能替代真实验收。不得为通过测试放宽生产查询预算或语义限制。

## 6. 工程质量与可维护性

- 继续 C# 中文 XML 文档注释、显式映射、清晰多行排版和 `.editorconfig`/Roslyn 门禁。
- TSX 必须可读；避免超长单行 JSX。本轮修改的手写 TSX 单行默认不超过 200 字符；必要时用多行 JSX、子组件或具名辅助函数拆分，不能为满足行长规则制造过度碎片化组件。
- 核心算法说明语义、预算、失败关闭条件和复杂度边界。
- 新增/修改的公开 DTO、枚举、方法、属性均补准确中文文档注释；属性之间留空行，XML 注释紧贴所修饰声明。
- 不新增通用 Repository、AutoMapper、MediatR 或新的泛型抽象。
- 不新增直接依赖。若发现无法完成 M1 的必要新增依赖，先登记准确包名/版本/许可/来源/用途并停止该依赖引入，继续不依赖它的任务，等待审批。

## 7. Git、CI、证据与资源收尾

- 每任务记录开始/结束、实现/集成/修复/环境/CI/封包耗时；无法可靠取得的记录 `UNKNOWN`，不得估算或编造。
- 先在独立 Worktree/分支开发；共享合同和迁移由 Master 单写。及时 commit/push；禁止强推。
- 每个纵向任务通过独立审查与必要测试后尽早集成，至少在 M1 完成组合端到端验收；不要把首次真实集成拖到最后。
- 每次集成后的 main SHA 必须有同 Head 的 GitHub CI 成功记录，核验实际 run 和两个 required jobs；不得把旧 CI 复用为本轮通过。
- 复用 `scripts/create-review-package.ps1` 的 Review ZIP V2，不重写已验收构包器。明确 Base/Head/TaskId/Status/真实 CI run；从已提交 Head 构包并独立重开验证。最终只交付一个 compact ZIP，附大小、SHA-256、CI URL、测试矩阵、未解决事项。
- 按 `docs/development/resource-lifecycle.md` 与 `scripts/maintenance/inspect-resources.ps1` / `cleanup-resources.ps1` 执行本任务资源收尾。仅清理本任务创建且已确认可再生的容器/临时数据；不清理受保护 G2 卷、历史 refs、旧 Master Worktree 或其他项目资源。清理记录 before→command→exit→after。
- 代码和证据归档后，保持主工作树干净，Review ZIP 不入 Git。

## 8. 停止条件与交付

出现以下情况应暂停对应子任务并报告，继续无依赖的其他工作：
- 发现语义数据可能静默丢失、旧 Release/Run 无法安全读取、发布资格可能绕过；
- 必须新增未经批准的直接依赖；
- 真实 PostgreSQL/Jena/RustFS 语义测试不可用，或关键测试仅有 Mock；
- OpenAPI/TS 漂移、同 Head CI 失败、证据 ZIP 不可独立验证；
- 发现不在授权范围的系统级/生产/付费操作。

最终 Review ZIP 至少包含：中文总结、manifest 与 SHA256、完整 Base/Head、文本 diff/二进制索引、变更源码和测试、M1 证据、真实 CI、独立 Reviewer 结论、风险矩阵、资源收尾回执及 G3 交接。保留历史事实，明确列出 Monaco、真实 LLM、Windows/Intel、生产 HA/SLO、供应链扫描等未完成项。

**本次仅完成 G3-M1。完成后输出 `G3_M1_READY_FOR_REVIEW`，提供唯一 Review ZIP 的路径、大小和 SHA-256，然后停止。不得自动启动 M2、M3 或整个 G3 后续阶段。**
