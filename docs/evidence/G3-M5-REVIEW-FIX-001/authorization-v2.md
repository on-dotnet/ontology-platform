# Codex Master 执行手册 V2：模型、职责、配置与完整任务提示词

> 对应唯一任务：**G3-M5-REVIEW-FIX-001**。此 V2 仅补齐**使用说明、模型强度与职责边界**，下面保留原授权任务全文。不是第二次业务授权；不是 G4/G5/G6 启动许可。出现冲突以用户最新明确授权、仓库当前规则、冻结合同及原任务的更严格限制为准。

## 0. ChatGPT 与 Codex 的固定职责（不可委托变更）

| 角色 | 做什么 | 不做什么 |
|---|---|---|
| 用户 / 产品负责人 | 最终批准任务范围、额外依赖/权限/费用和关口切换 | 不被要求代替自动测试做大量基础手工操作 |
| ChatGPT（方案与独立审查） | 负责产品/技术方案裁决、明确边界与验收、审查 Codex 的真实证据并给出 PASS / FIX_REQUIRED / BLOCKED | 不把 Codex 的自报成功当独立验收，不因未证实的猜测强令大幅更改已冻结合同 |
| Codex Master（执行统筹） | 核对仓库/合同/授权，制定受控实施顺序，管理独立任务 Worktree，组织必要 Worker 和非作者 Reviewer，集成、回归、封包、止步交付 | 不擅自修改方案/原冻结合同，不越过审批扩权限/依赖/收费服务，不自动启动后续阶段 |
| Worker（按需） | 仅在自己的 owned_paths 和独立 Worktree 里做最小代码改动、测试并提交任务分支 | 不直接集成 main，不改公共合同/迁移/设计令牌，不审自己写的代码 |
| 独立 Reviewer | **非作者、只读**复核冻结合同、diff、测试、权限、安全与证据，给出可定位问题和 PASS / FAIL / NOT_VERIFIED | 不写产品代码、不与作者合并同一角色，不把“已看过”代替客观验证 |

## 1. 本次建议的模型与推理强度（在 Codex 界面/会话中设置）

| 工作角色 | 首选模型 | 推理强度 | 选择依据 |
|---|---|---|---|
| Master | **GPT-6 Astra (`gpt-6-astra`)** | **High (`high`)** | 任务核心是跨合同的语义裁决及受控集成；重要性高但不是全平台重构，不必默认 xhigh / max |
| Reviewer | **GPT-6.1 Sol (`gpt-6.1-sol`)** | **High (`high`)** | 非作者从不同模型配置独立评估代码语义、回归和证据 |
| Worker（只有实际需要时） | **GPT-6.1 Sol** | **Medium (`medium`)** | 范围已明确的最小 UI 改动与定向测试即可，减少用量 |
| Explorer（只有实际需要时） | **GPT-6 Luna (`gpt-6-luna`)** | **High (`high`)** | 只读检索和路径定位；可不启动 |

若指定模型不可选，先检查本机 Codex 版本与已登录账号的可用列表；从可用模型选最接近能力档次，并在审查证据里**记录实际模型与实际强度**，不伪称使用了推荐配置。不能通过文字指令强行改变界面或账号的实际模型。必要时用同等级可用模型，不改变任务范围。

## 2. 运行环境与并行策略

- **环境**：本机运行，独立 Git **Worktree**（不是共享 main checkout）；若 Codex 桌面 app 已为此任务创建 Worktree，使用它且不要嵌套新建。
- **审批模式**：`Ask for approval`，对应 `workspace-write` / `on-request`。不要选择 `Full access`、`Do anything`、`--yolo`；不要自动越过批准流程；任何跨工作区写入/网络权限按授权原则申请。
- **并行上限**：本任务 Master + 最多 2 个子 Agent；**必须有非作者只读 Reviewer**，一个小 UI 问题不必机械拆成多个 Worker。 Reviewer 的执行环境和工具权限应保持只读；提示词要求只读不等于操作系统权限隔离，必要时使用只读模式/工作区。
- **速度模式**：Standard；Fast / Ultrafast 不启用（减少多余额度）。
- **工作机制**：先 Preflight → 冻结合同裁决 → 非作者 Review → 若需要最小修改 → 定向测试/浏览器 → 独立 Review → Master 集成 main → 唯一 Review ZIP V3 独立重开 → 明确终止状态。
- **权限/范围**：不实施 G4/G5/G6、不解禁 Monaco、不调用付费模型、不触碰生产、不得改全局系统配置、不修改原始 Review 包与历史证据。

## 3. Codex 中如何设置

**桌面 App**：新建 Codex 会话 → 选择现有 `ontology-platform` 项目 → 运行环境选择 `Worktree`（本地） → 模型选择 `GPT-6 Astra` → Reasoning 选 `High` → 权限选择 `Ask for approval`。把此文件**全文作为任务附件**交给 Codex，随后使用第 4 节启动提示词。

**Codex CLI**：在你的本体项目仓库中，确保 `codex --version` 是支持当前模型的版本，再启动（不修改用户级/项目级 config 文件）：

```bash
cd ~/Documents/Codex/repos/ontology-platform
codex --worktree -m gpt-6-astra \
  -c model_reasoning_effort=high \
  -c agents.max_concurrent_threads_per_session=2 \
  --sandbox workspace-write \
  --ask-for-approval on-request
```

如果本地版本不支持 `--worktree`，先查看 `codex --help` 并使用当前版本的 `/worktree` 功能；不应因此直接写共享 main。Codex CLI 交互中可用 `/model` 选择/核验模型与推理档位。

## 4. 直接粘贴到 Codex 的启动提示词

> **前提**：此文件全文已经在本次 Codex 会话中作为附件、完整粘贴内容或当前可读取的任务文件出现。不要只提供文件名而未提供内容。

```text
你现在是 on-dotnet/ontology-platform 项目的 Codex Master。正式授权任务为 G3-M5-REVIEW-FIX-001。本会话附上的《G3-M5-REVIEW-FIX-001-Codex-Master-Prompt-V2.md》是唯一完整执行依据，请先完整读取其第 0～4 节和以下《原任务全文》，再读取仓库当前授权索引、AGENTS.md、PLANS.md、冻结合同及本地验证政策。

职责严格分离：ChatGPT 负责方案、范围、验收标准与最终独立复审；你负责工程实施、合同核实、必要的最小修复、分层验证、Master 唯一 main 集成与正式交付；非作者 Reviewer 必须只读复核，不能以你自己自检代替。

本次先裁决上一轮 ChatGPT 对 OwlExpressionSnapshot/ProfileVersion 的 P1 是否成立，不允许未经合同裁决就更改 SemanticProfile.Current()、历史 Profile/Manifest/Run/SSE 或公共 API。如果是前端展示歧义，仅修正真实歧义并做定向浏览器/回归；若原实现按合同正确且显示无歧义，可零代码关闭；如果必须破坏冻结合同，标 CONTRACT_CHANGE_REQUIRED 并停止等待批准。

执行时使用本地独立 Worktree、最小授权、最多 Master + 两名子 Agent；非作者只读 Reviewer 必须参与。先 Preflight，识别现有活跃工作树并保护；不强推、不 reset --hard、不清理他人资源。保持用户的当前阶段授权和历史失败事实，不擅自启动 G4/G5/G6，不用付费模型、不触碰生产、不解禁 Monaco。

完成后提供：合同裁决、明确 diff、真实测试矩阵和失败/跳过/未运行情况、非作者审查证据、Base/Head、main 同步、唯一 Review ZIP V3 的实际路径/大小/SHA256 及独立重开回执。按原提示词定义输出 READY_FOR_REVIEW / CONTRACT_CHANGE_REQUIRED / BLOCKED 三类终止标识之一，然后停止等待 ChatGPT 复审。

不需要把已明确的条件再问我一遍；按授权在本轮完成所有能完成的工作。遇到越权、不可逆、未知付费或冻结合同需破坏的情况，只停止对应操作并给出具体阻断与所需批准，不得擅自替代方案。
```

---

# 原任务全文（原版内容不改动，作为本次唯一实施合同）

# Codex Master 执行授权：G3-M5-REVIEW-FIX-001

> 任务定位：G3-M5 交付后的**复审纠偏与最小范围收口**，不是新的 G3 里程碑，不是 G4/G5/G6 的启动授权。
>
> 当前已知基线（2026-10-31）：`on-dotnet/ontology-platform` 的 `main` 位于 `580d73e7c0fb38b94dbbed1136ee0b1d24fadc9d`。原 G3-M5 Base 为 `e5b7e99715ee7ebfe419717f7cacf0c02dfcb78a`，唯一 Review ZIP V3 的 SHA256 为 `7a0149056514933491856fe80b93b1e26149b1295e3746fdfeb4cd7fe9208a63`。**原 Review ZIP、历史结论和哈希不可覆盖或改写。**

## 一、此次正式授权的目标和边界

我批准 Codex Master **仅执行 `G3-M5-REVIEW-FIX-001`**：对上一轮 ChatGPT 独立复审提出的“历史 Release 显示 Profile v4”进行基于冻结合同的二次裁决，完成必要的最小缺陷修复、增量验证、独立 Review、提交/推送及标准唯一 Review ZIP V3 交付，并停在本次任务复审关口。

特别注意：上一轮审查报告把 `OntologyExpressions.cs` 返回 `SemanticProfile.Current()` 视为 P1，但进一步核查 G3-M5 冻结合同后，**这一判断不能直接成立**。现有合同明确约定 `OwlExpressionSnapshot.profileId/profileVersion/profileHash` 是“现行支持策略”，与 `projectionVersion=1` 分开；`G2Models.g.cs` 的 XML 文档也写明“现行支持策略”，既有 `G3M5ServiceTests.cs` 对当前 v4 有断言。因此，**严禁在没有合同裁决的情况下直接把后端 ProfileVersion/ProfileHash 改成历史 Manifest 的 Profile**，也不能删除/改写历史 Profile、Manifest、Run 或 SSE 的已有语义。

本次工作以**复审裁决为首要成果**，有证据才修改。更可能的最小问题是前端 `ExpressionReadView` 在“固定正式 Release”区域里只显示 `profile ... v4`，没有明确标注这是**当前平台支持策略**，可能被误解为 Release 发布时使用的历史 Profile。这属于需验证的展示语义歧义，并非已经证实的后端数据错误。

不授权：G4/G5/G6 业务实施、全新系统/技术栈、模型调用或费用、生产数据、TMDL、GraphRAG、Monaco 解禁、正式推理/imports 加载、后台服务大重构、已有版本的迁移/重写、跨项目或全局资源清理、新的外部依赖。

## 二、开工前 Preflight（只读优先）

1. 读取仓库当前的 `AGENTS.md`、`PLANS.md`、`docs/tasks/current-authorization.md`、`docs/development/local-validation-policy.md`、`docs/development/review-package-spec.md`、`docs/development/resource-lifecycle.md`、`docs/contracts/g3-m5-contracts.md`、`docs/tasks/G3-M5-001.md`，以及与本次修复相关的真实证据。
2. 在已有仓库中 `git fetch`，确认 `origin/main` 当前实际 SHA、现有所有未提交/未跟踪变化、worktree/branch 活跃状态。保护他人工作及原始主树，不 `reset --hard`、不 force push、不覆盖已有 Review ZIP。如果 `main` 已超过上述 `580d...`，先做差异/冲突评估；无法安全继续则给出 BLOCKED，禁止自行回退或覆盖。
3. 新建本任务的独立 Worktree 与任务分支（如 `codex/G3-M5-REVIEW-FIX-001`）；由 Master 唯一集成 `main`。单项前端修复不必机械启动多个写入 Agent，但审查必须是**非作者的独立只读 Reviewer**。
4. 仅使用项目锁定工具链和已批准依赖；验证开工状态、源码指纹和资源归属，不修改 Mac 全局电源、Docker 全局配置或其它项目。实际命令、退出码及结果留证据。

## 三、复审裁决（必须先于写代码）

对照下面文件，形成 **`docs/evidence/G3-M5-REVIEW-FIX-001/contract-adjudication.md`**：

- `docs/contracts/g3-m5-contracts.md`，尤其“新 snapshot 的 projectionVersion=1 与现行支持策略 v4 分开”；
- `backend/src/Contracts/OntologyPlatform.Contracts/G2Models.g.cs` 中 `OwlExpressionSnapshot` 的字段注释（生成物只读）；
- `backend/src/Modules/Ontology/OntologyPlatform.Modules.Ontology/OntologyExpressions.cs` 中 `ReadVersionAsync` 后调用 `SemanticProfile.Current()` 的逻辑；
- `backend/src/Modules/Ontology/OntologyPlatform.Modules.Ontology/OntologyAssessment.cs` 中历史 Draft / Release 读取和 `Semantics`；
- `backend/src/Modules/Ontology/OntologyPlatform.Modules.Ontology/OntologyVocabulary.cs` 中历史发布 Profile 的使用方式；
- `apps/web/src/features/ontology/expression-tree.tsx` 中 `ExpressionReadView` 的 Profile 文案；
- `apps/web/src/features/ontology/expression-model.test.ts` 与 `backend/tests/OntologyPlatform.SemanticTests/G3M5ServiceTests.cs` 的当前断言。

裁决文件最少回答：

A. 现有 `profileVersion=4` 是“当前支持策略”，还是“该 Release 历史发布时策略”？要以冻结合同和已有消费者为准，不能凭单个字段名称猜测。

B. 对于 v1/v2/v3 Release，现有后端是否错误返回其历史发布 Profile，还是正确返回当前支持策略但前端未解释清楚？明确“后端合同缺陷”与“前端展示歧义”的证据边界。

C. 对于无 `Semantics` 的旧 Manifest，当前表达式快照是否承诺输出历史 Profile？如未承诺，禁止凭空生成 UNKNOWN 历史元数据，也不能把当前 v4 当历史事实。

D. 选择 `AS_DESIGNED`、`UI_CLARIFICATION` 或 `CONTRACT_CHANGE_REQUIRED` 之一，写明 P1 判定是否撤销/降级、涉及文件、为什么最小改动充分以及潜在兼容影响。**不要修改原 ChatGPT 审查文件或历史证据**；本轮以独立纠偏记录叠加审查历史。

E. 独立 Reviewer 在动源码前审阅裁决，确认不会违背 frozen contract。

## 四、允许的最小实施方案

默认预期为 `UI_CLARIFICATION`：

1. **只改前端明确命名**：在 `ExpressionReadView` 中将笼统的 `profile ... v4` 标记为“当前平台支持策略 Profile”（或等效准确中文），并明确说明**不是当前选中历史 Release 发布时的策略快照**。`projectionVersion=1` 应单独标注为“只读投影协议版本”，避免与策略 v4 混为一谈。
2. 对固定历史 Release、固定历史草稿两种视图使用正确文字；不改变 `OwlExpressionSnapshot` 的已冻结字段、数据、授权方式、查询边界或路径。没有已有权威数据时，不展示/捏造“历史发布时 Profile”。如未来产品需要同时显示两个版本，另行提出“历史 Profile 单独字段”非破坏性设计提案，不在本轮擅自改公共 DTO。
3. 在 `apps/web/src/features/ontology/expression-model.test.ts` 增加真实组件渲染的正反断言：`RELEASE` 历史版本携带当前策略 v4 时，明确呈现“当前平台支持策略”、只读投影版本，且不会出现“v4 是该历史 Release 发布时版本”的错误措辞；`DRAFT` 场景语义同样准确；保留 HTML 转义、权限、历史版本 ID、hash、source 和预算行为。
4. 如需要补充原合同的**说明性文档**，先确认仅解释已经冻结的原语义，不改变合同语义或现有 OpenAPI/生成物。文档变更由 Master 单写并留审查证据。
5. 允许添加少量纯证据或 UI 测试，不允许顺手重构其它页面/React 组件、升级 Next/React/.NET/依赖、修改令牌或设计体系。

**条件停止**：若证据明确表明需要修改后端字段语义、公共 DTO/OpenAPI/生成 TypeScript、现有 Profile/Release 兼容规则，则不得静默实施。这属于 `CONTRACT_CHANGE_REQUIRED`：提交影响分析、兼容方案、最小变更路径和测试计划后停止，等待我另行明确批准。不得借本任务把原 P1 判断强行实现。

若裁决为 `AS_DESIGNED` 且前端已能无歧义准确解释，也可**零代码关闭**，但必须有截图/真实测试及独立审查证据支持；不得为交付而制造无意义的代码变更。

## 五、必须执行的验证及拒绝路径

1. 先运行最廉价的定向静态检查和真实组件测试；验证具体命令与项目工具链后执行，例如：

   ```powershell
   pnpm --dir apps/web exec vitest run src/features/ontology/expression-model.test.ts
   pnpm --dir apps/web run typecheck
   pnpm --dir apps/web run lint
   ```

   如命令形态与实际项目不符，应先查看 `apps/web/package.json` 和现有脚本，使用仓库正式入口而非假装执行成功。

2. 如果 UI 实际发生变更，至少跑一次**真实浏览器的定向验收**，覆盖固定 Release 与草稿的 Profile 文案及已有读取链路；无需因一行标签改动重跑原 638 项全部浏览器组合，除非影响范围经证据证明扩大。
3. 根据改动影响运行现有 `scripts/verify.ps1 -SelfTest`、Web 相关验证；检查未改动 API/DTO、发布 Manifest、历史 profile hash、Query/Agent 契约。已通过且输入完全一致的 G3-M5 后端测试允许按最新 `local-validation-policy.md` 复用，必须列出复用测试提交、固定输入 SHA 与原因。
4. 如果意外需要写入后端（只有获得新增批准后才可），则补跑有真实 PG/Jena 的历史 Release v1–v4、旧 Manifest、权限、篡改和发布查询回滚定向测试。不得用 Mock、零测试、静态 grep 替代真实产品验收。
5. 验证不产生写审计新动作、不改变老 Release/Run/SSE、不误改历史 profile 语义、不改变复杂 OWL 源码和图保真；真实出现错误立即短复现并修复，再按影响范围复验。
6. 提供正反例、测试数、失败数、跳过数、实际 exit code、时长、日志、精确测试 SHA 与环境。新旧失败记录保留；CI 未运行按 `NOT_RUN`，Windows/Intel/付费模型/Monaco/生产继续维持原未验证边界。无须重新运行 G3-M5 的 93 分钟宿主长监测，除非本次实际变更触及 E0/宿主连续性能力；已存在的原始 E0 结果按证据可复用。

## 六、Review、Git 集成、正式交付

- 独立非作者 Reviewer 只读审查：先核对合同裁决，再核对 diff、测试及无意越界；Reviewer 提出问题后由实现者修复与复验，Reviewer 不能自报代替证据。
- Master 核对 worktree、公共文件 Single Writer、资源范围、原始 G3-M5 历史未被覆盖；合规后提交并 push 任务分支，分批或一次最小增量进入 `main`。原 `580d...` 历史不得改写；提交前后校验远端已知 head，不强推。
- 使用新任务名 `G3-M5-REVIEW-FIX-001`、**此次任务真实 Base 和冻结 Head**，执行项目现有 Review ZIP V3 `LOCAL` 构包及 VerifyOnly 独立重开。按仓库规范创建 `docs/evidence/G3-M5-REVIEW-FIX-001/validation.json`（schema2、真实 `testedCommit`、输入绑定、检查、CI 状态），不得伪造云 CI。必须 `git diff --check` exit0；审查包从提交源码重建。
- 原始 `OntologyPlatform-Review-G3-M5-001-580d73e7c0fb.zip` 原封保留，新任务的唯一 ZIP 使用新任务编号，不与原包同名。若本轮无源码差异，需要按 V3 规则说明仅证据/文档差异，不杜撰软件验证。
- 精确资源清理仅限**本任务创建**并经白名单复核的对象。不得触碰旧 G2/G3、现有用户资源和未整合 worktree；若未新建持久资源，就如实记为“无需新增资源回收”。
- 最终交付以下内容：
  1. `contract-adjudication.md`：审查问题成立与否、优先级裁决、冻结合同依据和结论。
  2. 简明 diff 摘要与正反测试证据、受影响回归/复用输入绑定、真实测试矩阵。
  3. 非作者独立 Review 结论，失败及遗留限制表。
  4. 新 Base/Head、已推送 `main` SHA、唯一 V3 ZIP 实际路径/字节数/SHA256、独立重开回执。
  5. 给 ChatGPT 的下一步复审要点。

**终止标记**：

- 证据+必要修复+本地验收+独立审查+V3 重开均通过：`G3_M5_REVIEW_FIX_READY_FOR_REVIEW`；
- 合同需变更而未获授权：`G3_M5_REVIEW_FIX_CONTRACT_CHANGE_REQUIRED`；
- 存在未解决真实缺陷、环境或测试阻断：`G3_M5_REVIEW_FIX_BLOCKED`。

交付后停止，等待我/ChatGPT 复审。**不得自动开启 G4、G5、G6。**
