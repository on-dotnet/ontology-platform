# OntologyPlatform · G3-M4-001
## 身份、时间、版本差异与影响治理：Codex Master 实施授权 V1.0

> **推荐配置：**Master GPT-6.1 Sol / **High** / 普通执行模式；语义/安全独立 Reviewer 如可单独选择，GPT-6 Astra / High；后端/前端 Agent GPT-6.1 Sol / Medium–High。
>
> **授权边界：**正式授权 G3-M4，不授权 M5 或 G4/G5。完成后输出 `G3_M4_READY_FOR_REVIEW`，生成唯一正式 Review ZIP V3 并停止。未验证项保持 PARTIAL/NOT_RUN。

## 0. Master 职责、基线与预检

仓库：`on-dotnet/ontology-platform`。M3 交付 Head 为 `3992582e03df1a103fac36e7e82b8c81f85f622e`。开工必须重新 `git fetch origin`，使用实际最新 `origin/main` 为 Base；记录完整 SHA、工作树、活跃 Worktree/分支、授权与本地工具链。不得 reset、force push 或覆盖用户改动。

读取 `AGENTS.md`、`PLANS.md`、当前授权、G3 计划、`docs/development/ai-development-efficiency.md`、`docs/development/local-validation-policy.md`、Review ZIP V3 规范、资源生命周期规范、G3-M1/M2/M3 交付及未关闭风险。新会话/新机器不得依赖聊天记忆；仓库文件是规范来源。

先做廉价 Preflight：doctor、SelfTest、Web lint/typecheck、后端 build、OpenAPI/TS 生成检查。先核实实际命令存在；记录命令、exit code、测试数和输入指纹。若工具/依赖/环境前提失败，先分类与短复现，不立即盲跑整栈。

本项目当前采用本地优先、按需 CI 政策。**不要机械触发每次 push 的完整云 CI。** M4 必须完成本地真实 PostgreSQL/Jena/RustFS、权限、审批、查询、回滚和相关浏览器验收；只有改动跨 runner 缓存/CI 专属行为时才要求相应远程证据。云 CI 未运行如实记 `NOT_RUN`，不得冒充 PASS；产品输入变化时不可复用旧测试为当前代码背书。

## 1. 本轮目标与边界

实现 G3-M4 的身份、时间、版本比较与影响治理闭环：

**身份声明/有效期 → 事件时间校验 → 任意两个固定版本的四源 Diff → 可追溯 ImpactReport → 审批绑定报告与目标版本 → 发布门禁重新验证 → 正式查询读取 active Release → 历史 Run 固定原 snapshot → 安全回滚。**

允许实现：
- 显式组织/厂区/来源命名空间下的外部标识、身份声明、有效期和冲突诊断；
- OWL-Time 受控点/区间模板与事件时间检查；
- 同一资产/范围内任意两个固定版本的四源源码 Diff 和 RDF 图 Diff；
- 可解释的变更影响分析、ImpactReport hash、引用与未知范围；
- 将 impact hash、source hashes、profile/assessment、版本引用绑定到审批/发布资格；
- 输入变化使旧审批失效、并发更新 CAS、正式查询和历史 Run 隔离；
- 中文 UI、真实 API、测试和阶段资源收尾。

### 非目标

- 不启动 M5 高阶 OWL 源码/表达式树深化。
- 不实现 G4 的五类真实数据连接器、通用实体解析或跨源自动匹配；只实现合成数据和本体资产内显式身份治理。
- 不实现 G5 指标计算、规则引擎或通用单位换算。
- 不自动推断 `owl:sameAs`，不因标签/编号相同而合并身份。
- 不加载/联网解析 `owl:imports`，不执行用户 SPARQL、JavaScript 或自定义 SHACL target。
- 不接入 Monaco（继续 BLOCKED/PAUSED_BY_USER），不调用收费 LLM，不自动发布。
- 不引入未经批准的直接依赖，不下载 QUDT 正式词汇资产；使用明确标记的 Synthetic fixtures。
- 不修改 GitHub branch protection、历史 refs、G2 保护卷、其他项目资源或生产环境。
- 不重建 M1 的 SourceBundle、SemanticSupportProfile、SemanticAssessment、Evidence、Outbox、CAS、审批或发布系统；复用并扩展现有服务。

## 2. 身份、时间与版本合同

### 2.1 身份模型

- 身份必须显式限定 `organizationId`、`siteId`、`sourceNamespace`、外部编号、目标 IRI、有效时间及声明来源。
- 相同编号在不同厂区/命名空间不等于同一对象；同名/同标签不自动合并。
- 身份冲突返回可解释的 `AMBIGUOUS` 或阻断诊断，不挑选第一个值。
- 身份声明/时间范围使用真实 CAS/If-Match，审计、权限与异人审批沿用现有契约。
- 时间范围采用半开区间 `[from,to)`；未知终点为空，不伪造无限期确定性。
- 输入时间必须有明确时区；不能用本地机器时区推测无时区输入。业务有效时间、事件/观察时间、资产版本时间必须分开。
- 不覆盖同一外部编号的历史身份记录；历史身份可追溯。

### 2.2 事件时间

- 仅允许 G3 计划定义的 OWL-Time 受控模板；不开放任意复杂表达式。
- 校验起止顺序、时区、未知端点、区间重叠和历史编号冲突。
- 不确定的时间关系返回 `INDETERMINATE`，不能当作无冲突。
- 诊断必须定位真实来源；无法准确定位时给 bundle-level 证据，不伪造行列号。
- OWL-Time 模板校验不等于通用时间推理引擎。

### 2.3 四源版本 Diff

- 只比较同一 asset/scope 的两个明确固定 `VersionRef`；拒绝跨资产、跨范围或未知版本组合。
- 每个源分别输出源码 Diff、hash、图比较状态和统计；保留语言标签、datatype 与空白节点作用域。
- 复用 M1 有界 RDF 图比较器；预算超限/取消返回 `INDETERMINATE`。
- 不把图比较说成完整 OWL 推理。复杂未支持公理可保留源码，不能因图形投影而省略。
- 同一版本比较应产生稳定 no-op 结果；任何源 hash 变化必须反映在报告中。

### 2.4 ImpactReport 与审批绑定

ImpactReport 至少包含固定 source/target VersionRef、四源 Base/Target hashes、变化的 IRI/三元组/资产引用、已知影响、阻断项、未知覆盖范围、profile/assessment 版本、生成时间、执行器版本、稳定 canonical hash，以及每个结论对应的 EvidenceReference。

**未知不等于无影响。** 未覆盖模块、未解析依赖、比较超预算、来源缺失或 hash 不匹配必须列为 unknown/blocked，不能生成“无影响”结论。

新发布审批必须绑定准确的 impact hash、source/target versions、四源 hashes、assessment/profile 与目标 draft revision。任一输入变化使审批失效。审核者不能覆盖技术阻断项。

保持异人审批、24 小时有效期、If-Match、CAS、审计和 Outbox 原子性。ImpactReport 生成必须有明确幂等键；相同输入重试返回相同报告，不重复创建业务副作用。


## 3. 先冻结公共合同，再并行实现

Master 单写 `G3-M4-CONTRACT`，独立 Reviewer 只读审查通过后才允许后端/前端并行编码。

合同至少明确：
- identity claim/validity 的 Request/Response、错误码和权限边界；
- time point/interval 的标准化 DTO 与诊断；
- `VersionRef`、四源 Diff、`ImpactReport`、canonical hash；
- 审批/发布绑定与旧版本兼容；
- OpenAPI/TypeScript 唯一生成源和逐字节一致性检查；
- owned_paths 与 Single Writer 责任。

先运行廉价合同测试：未知/缺失字段、非法时区、倒序/重叠区间、跨厂区身份、重复编号、跨资产 VersionRef、伪造/过期 impact hash、陈旧审批、权限不足、比较 `INDETERMINATE`。合同未冻结前不启动大规模并行。

## 4. 里程碑与并行任务

将 M4 拆成两个可运行纵向切片，避免首次真实集成拖到最后。

### Slice A：身份与时间

1. `G3-M4-BASE`：Master 记录当前 Base SHA、授权、风险、任务卡、真实环境状态。
2. `G3-M4-CONTRACT-A`：冻结 identity/time DTO、错误码、权限和存储合同；独立 Reviewer 通过后冻结。
3. `G3-M4-SEM-A`：后端实现身份声明、有效期、时间点/区间和冲突诊断，真实 PG/Jena 测试。
4. `G3-M4-WEB-A`：前端在独立 Worktree 实现身份/时间编辑与诊断，连接真实 API。
5. `G3-M4-GATE-A`：真实用户路径：创建/编辑身份与时间→保存→冲突诊断→发布→正式查询→回滚。

Slice A 必须先集成到 main 并通过适用的本地真实门禁，才允许 Slice B 共享新合同和资产。

### Slice B：四源版本 Diff 与 ImpactReport

1. `G3-M4-CONTRACT-B`：冻结 VersionRef、四源 Diff、ImpactReport 和审批绑定合同。
2. `G3-M4-DIFF`：后端实现固定版本比较、来源 hash、RDF 图比较、预算/INDETERMINATE 与稳定报告 hash。
3. `G3-M4-IMPACT`：影响引用、未知范围、阻断项、幂等与发布/审批失效。
4. `G3-M4-WEB-B`：版本选择、四源 Diff、影响报告、审批状态和诊断 UI。
5. `G3-M4-GATE-B`：真实纵向路径：两个版本→四源 Diff→ImpactReport→审批→发布资格→active 查询→旧 Run snapshot→回滚。

每个可运行切片先提交/推送、独立审查、执行相关真实测试，再增量集成。禁止等所有 SEM/WEB 任务结束后才首次联调。

## 5. Codex 多 Agent 与 Git 规则

并行上限 Master + 两个独立写入 Agent；需要独立 Reviewer 时暂停一个写入槽位。Master 是 `main` 唯一集成责任人。写入 Agent 使用独立托管 Worktree/任务分支，及时 Commit/Push，不共用 main。

每张任务卡必须包含 Task ID、Base SHA、Owner/Reviewer、实际 Worktree 路径、owned_paths、read_only_dependencies、合同 Owner、验收命令、负例、证据与停止条件。

Master 单写公共 DTO、迁移、OpenAPI/TS 生成产物、CI、锁文件、AppHost 公共配置和 Design Tokens。SEM/PUB/FE 只能修改已分配路径。不得把独立 Agent 报告伪装成另一个 GitHub 用户批准。不得修改 GitHub branch protection/rulesets，除非另有明确授权。

## 6. 必须落实的效率机制（以现有工具为主）

执行仓库 `docs/development/ai-development-efficiency.md`、`docs/development/local-validation-policy.md`、Review ZIP V3 合同和资源生命周期规范。**不新增一层泛化工具系统；复用已有脚本并只补齐缺口。**

1. **Preflight-first：**先核实锁定依赖、测试入口、Docker socket、canonical Fuseki、OpenAPI/TS、迁移和证据目录。基础前提失败先分类与短复现，不进入完整整栈。
2. **合同先行：**共享 DTO/错误/事务/证据契约先冻结并做正反测试；之后才并行写。共享文件 Single Writer。
3. **分层验证：**静态/单测→模块真实集成→纵向 E2E→稳定候选完整门禁。增量变更只重跑受影响层；只有输入变化、失败或疑点才重跑完整入口。禁止同一输入/环境下盲目重复昂贵测试。
4. **失败指纹与止损：**Fuseki/cache/镜像输入按 context hash、平台、锁定源、工具版本形成 fingerprint。相同 fingerprint 已有同终态失败时，先运行不超过 20 秒的固定短探测；重现相同错误即 BLOCKED，不再无条件等待 600 秒。输入或环境变化才允许重新完整尝试。保留真实失败，不改写成 PASS。
5. **Fuseki 复用：**只用 `scripts/maintenance/canonical_fuseki.py` 与已验证跨-run cache；不从 AppHost 和集成脚本重复 `docker build`。缓存 key 必须精确，命中要验证 producer/source/input/platform/image identity。Mac 缓存不代表 Linux Runner 缓存；如果 M4 未改变 canonical 输入，复用已有跨-run 证据，不为普通业务改动重新证明。
6. **浏览器契约：**复用 `scripts/acceptance/workspace-smoke.mjs`。涉及默认视图、图/源码切换、窄屏、权限或保存流程时，先跑短 Smoke；隐藏 canvas 的故障注入必须快速失败并恢复。不能用延长 timeout、默认切换视图或吞异常迁就旧测试。
7. **本地优先 CI：**本地真实测试为默认；Actions 按需。若 M4 改动跨 runner 缓存/CI专属逻辑，必须实际运行对应远程证据。业务代码/锁/构建输入未变化时，可复用绑定到精确输入的已通过测试；文档提交不自动触发全量云 CI。
8. **证据预检前置：**开发早期就运行 `new-review-evidence.ps1`、`test-review-evidence.ps1` 和 Review V3 VerifyOnly；不能到最后才发现字段/schema不匹配。过程截图/全量遥测留本地归档，正式包只保留代表证据与准确 Git 恢复索引。
9. **Docker 资源生命周期：**每个新容器、卷、镜像、Build history 在创建时登记 TaskId、RunId、准确 ID、输入 fingerprint、用途和 TTL。结束时对本任务资源做 before/after；仅删除准确白名单内且无引用、可恢复的对象。保护 G2 卷、其他项目资源和共享 cache；禁止全局 prune。新 Fuseki 构建不得无归属堆积镜像/history。
10. **自动计时：**复用 `scripts/maintenance/task_run_timeline.py`，记录 UTC/monotonic 时间、任务类别、输入 fingerprint、exit code、错误类别、依赖和 retry attempt。分别报告墙钟跨度、区间并集、累计执行、并行重叠、可观察关键路径与失败重验。未采集的 Agent 思考/活跃时间记 UNKNOWN，不推测。
11. **代码可维护性：**C# 中文 XML 注释、显式映射、清晰多行 TSX；变更 TSX 单行默认不超过 200 字符。只对变更文件做可读性治理，不全仓重写。
12. **跨平台：**macOS ARM64 开发、Windows 开发宿主、Linux 容器/CI分开验证。使用标准临时目录和路径 API，不写死 `/private/tmp`、盘符或用户路径；记录未实测平台为 NOT_RUN，不用 Linux 容器成功冒充 Windows 原生通过。
13. **资源收尾：**阶段结束时清理本任务明确归属的临时 Worktree、分支、Review ZIP、容器/卷/镜像/history；每项清理有真实 before→command→exit→after。歧义项保留准确 ID 和解除条件。
14. **交付冻结：**本地测试→独立 Review→提交/Push→适用本地完整门禁→唯一 Review ZIP V3→独立重开→资源收尾。`git diff --check` 必须 exit 0。Actions 未运行记 NOT_RUN；不伪造同 Head CI。

## 7. M4 验收门禁

### Slice A 必须通过
- 同编号跨组织/厂区/命名空间不会自动合并；
- 同一身份在重叠有效期内冲突可被检测，非重叠历史记录保留；
- 非法/无时区/倒序/未知端点按合同处理；
- 并发编辑、陈旧 If-Match、越权和跨厂区访问失败关闭；
- 审计、Outbox、幂等、审批、正式查询和回滚正常；
- 真实 PG/Jena/RustFS 与浏览器 Smoke/E2E 通过。

### Slice B 必须通过
- 两个版本的四源 Diff 与源 hash 准确；
- blank node 同构复用 M1 逻辑；预算耗尽为 INDETERMINATE；
- ImpactReport 稳定 hash、同输入幂等、未知范围显式列出；
- 伪造/过期/跨版本 impact、陈旧审批、源变化、profile变化、并发激活、权限不足均失败关闭；
- 新审批绑定 ImpactReport 与四源/assessment/profile；历史 Run 保持原 snapshot；
- 真实发布→查询→回滚、错误注入与恢复通过；
- OpenAPI 与生成 TypeScript 一致；Web 深浅主题、键盘、窄屏与真实 API 通过。

零测试、全 Skip、Mock 成功、静态配置存在都不能判 PASS。不得为通过测试放宽语义、权限、预算或失败关闭策略。

## 8. 最终交付与停止

使用正式 Review ZIP V3。包从已提交 Head 生成，包含 Base/Head、完整文本 diff、变更源码/测试、真实验收、效率摘要、独立 Reviewer、资源收尾回执和风险矩阵；不重复打包整个历史证据树。目标 ≤10 MiB；>10 MiB 给分类体积报告，>15 MiB 默认阻断，除非关键证据有书面理由。

报告中分别标记 PASS、PARTIAL、BLOCKED、NOT_RUN、NOT_VERIFIED。明确保留 Monaco BLOCKED、真实 LLM NOT_RUN、完整 OWL 推理未实现、G4/G5未实现、Windows/Intel未测、生产 HA/SLO/供应链专项未完成。不要将本地 PASS 冒充云 CI PASS。

完成 M4 后输出 `G3_M4_READY_FOR_REVIEW`，提供唯一 ZIP 路径/大小/SHA-256、Base/Head、适用本地门禁结果、CI（如运行）、实测耗时分解、失败/重验次数、Docker/Worktree 资源前后状态和未关闭风险，然后停止。**不得自动启动 M5。**
