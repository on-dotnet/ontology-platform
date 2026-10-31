# OntologyPlatform · G3-M5-001
## 高阶本体表达式保真与 G3 验收 + AI Coding 运行可靠性专项（实施授权 V1.0）

> **任务类型：**正式实施。只授权 G3-M5，以及本文件规定的 E0 工程运行可靠性整改；不授权 G4、G5 或扩大 OWL 推理引擎范围。
>
> **推荐 Codex：**Master 使用当前可用的高能力 Codex 编码模型（界面如提供 GPT-6.1 Sol，优先）+ **High** + 普通执行模式。语义/安全 Reviewer 用可用高能力模型 + High；前端与只读调查任务可用 Medium–High。不可分别选子 Agent 模型时，Master 全程 High。
>
> **完成标记：**`G3_M5_READY_FOR_REVIEW`。完成后只交付一个正式 V3 Review ZIP、实际状态及停止。不可据此自动进入 G4。
>
> **优先级：**用户明确要求 Mac 锁屏、显示器熄灭但 Codex 持续运行；E0 的宿主持续运行保护是 **P0**，不是仅写到文档中的建议。

## 0. 事实与权限边界

- 仓库：`on-dotnet/ontology-platform`，工作机为 Mac mini（Apple Silicon）；实际工程目录、芯片、显示器、权限及时间通过宿主环境检查，不得在源码写死 `/Users/chasen`、`/private/tmp` 或 Windows 盘符。
- 上次已核实 `origin/main` / M4 交付 Head：`e5b7e99715ee7ebfe419717f7cacf0c02dfcb78a`。正式开工先 `git fetch origin`，确认最新主线、任务授权、未提交用户修改、活跃 Worktree 和当前执行环境；若主线前进，按最新实际 SHA 作为本任务 Base，不回退或强推。
- M4 实际本地验收：Web 225、Semantic 239、Publishing 78 项的修复后组合结果、Query 49、Agent 33、七项真实整栈、浏览器 600；正式 V3 ZIP 完整且 `git diff --check` 为 0。云 CI、Windows/Intel、真实 LLM、完整 OWL 推理和生产 HA/SLO 均非已通过项。
- 来自用户提交的侧聊调查：M4 完整会话约 12:05，报告 `pmset` 同窗口累计睡眠约 8:13，扣睡眠后跨度约 3:52；M3 及 M1 收口也有睡眠。**本任务必须重新读取真实 macOS 电源记录验证，不能把侧聊数字直接写成独立本次实测**。两次 `CLOCK_DRIFT` 不能自动等价于 CPU 耗时或产品测试失败。
- 仓库现有本地优先、按需 GitHub CI 政策继续有效。不得为了文档/证据小改动反复要求整套远程 CI；需要跨平台/CI 专项行为证据时才运行对应真实远程门禁。未运行如实 NOT_RUN。
- 先读取 `AGENTS.md`、`PLANS.md`、`docs/tasks/current-authorization.md`、G3 总计划、M1–M4 handoff/历史失败、`docs/development/ai-development-efficiency.md`、`docs/development/local-validation-policy.md`、`docs/development/review-package-spec.md`、`docs/development/resource-lifecycle.md`，以及当前 `scripts/maintenance/task_run_timeline.py`、自测/验收/构包脚本。

## 1. E0-P0：Mac 睡眠与 Codex 长任务可靠性（先完成）

### 1.1 用户希望的行为

**允许 Mac 锁屏及外接显示器熄屏，但主机不因空闲进入系统睡眠；Codex、子 Agent、Docker 和验收可以继续运行。**

优先采用 Apple 官方的台式 Mac 能源设置：**系统设置 → 能源 → 打开“显示器关闭时防止自动睡眠”**，并由“锁定屏幕”控制显示器关闭时间。此设置应由用户自行确认，不允许 Codex 擅自写 `pmset` 持久系统配置、重置电源计划或开启不必要的 `caffeinate -d/-u`（会阻止或唤醒显示器）。

任务级额外保障可使用 macOS 自带 `caffeinate -i`、接交流电时 `-s`。必须实际区分 CLI 和桌面 App：
- **CLI：**可采用 `caffeinate -is codex`，使 assertion 与 Codex CLI 进程生命周期绑定；命令结束释放。运行时实际检查 `pmset -g assertions`。
- **Codex 桌面 App：**临时终端命令的子进程不一定能跨越多个模型轮次存活；**不得仅凭一次工具调用启动 caffeinate 就声称覆盖整个会话**。优先依赖用户已开启的 macOS 系统选项；如实现额外受控 task-owned assertion，必须有能覆盖会话全寿命的外部管理器、准确 owner/PID、启动/确认/退出释放机制，并经真实长会话验证。若做不到，显示 `BLOCKED_HOST_SLEEP_ASSURANCE` 并提示用户完成上述系统设置，而非虚假 PASS。
- **不得使用** `sudo pmset -a sleep 0`、永久修改机器能源计划、修改系统登录项、保活屏幕、无期限后台常驻进程或与本任务无关的全局 `killall caffeinate`。
- Windows/Linux：检测当前运行宿主和 CI 环境，采用只读适用性判断；Windows 不执行 macOS 命令，Linux 容器/CI 不需要 macOS caffeinate；不得因平台不同而破坏测试。

### 1.2 必须实现的仓库入口

在现有脚本/规范中增加一个**简洁、受控**的跨平台预检入口（例：`scripts/maintenance/host-continuity`，名称可根据实际仓库规范确定），并提供可选的“伴随 CLI 会话”的任务级 wrapper；禁止扩展成常驻通用守护平台。

预检至少检查并记录：
1. 当前 OS、芯片架构、是否交流供电（可以可靠取得时），不读取秘密；
2. macOS `pmset -g custom` 对显示器关闭后自动睡眠的配置，`pmset -g assertions` 中活动的 idle/system sleep assertion；
3. 启用预期策略后是否确实存在所需 assertion；使用标准 `caffeinate`，**不包含 `-d`**；
4. 对短生命周期 fixture 的启动、可验证存在、用户要求终止/正常完成后清理，防止 assertion 泄漏；
5. 检查用户锁屏/显示器熄屏下仍然有运行日志/测试心跳；若无法在沙箱中进行真实屏幕/整会话演练，明确 NOT_VERIFIED，不宣称已经保证整夜运行；
6. 记录前后 `pmset -g log` 中 Idle Sleep/Wake 事件的摘要和时间窗（无权访问则 NOT_VERIFIED），不得收集无关系统隐私日志。

**必须主动检验实际运行模式：**在用户确认 Mac“显示器关闭时不自动睡眠”选项已开启之后，验证锁屏、外接显示器熄灭情况下，Codex 的任务仍继续，日志时间线无 Idle Sleep。不能将显示器熄灭本身判为主机睡眠。停电、主动 Sleep、重启、系统更新、外设驱动异常不在 idle sleep assertion 保证范围内。

> E0 失败时不得开始会跨夜的长时间 M5 全栈验收；可以先开展不依赖宿主持续运行的短任务、合同设计和静态测试。

## 2. E0-P1：把既有返工问题变成前置机械门禁

**不允许重复建设新的通用任务框架。** 复用现有 `verify.ps1`、`task_run_timeline.py`、`g3-governance.ps1`、Review V3、审计/授权/生成器规范和日志工具，仅补足验证缺口。

### 2.1 计时与睡眠诊断分离

- 单个子进程执行结果 `exitCode` 与计时有效性 `timingStatus` **分开**：子进程确实 exit0 但时间发现 CLOCK_DRIFT 时，不能假冒整个时间正常，也不得反向改写真实产品结果。
- 记录 UTC wall time、单调 elapsed、有效区间、运行依赖、sleep/wake 时间窗、输入 fingerprint、任务 ID、并行重叠和可观察关键路径；检测到墙钟/单调明显差异时诊断是否因 macOS Sleep，不能以 `CLOCK_DRIFT=睡眠` 直接推定因果。
- 依据有界合成日志/假时间源做正反测试：进程成功+时钟漂移、真实进程失败+有效时钟、无 sleep 但漂移、睡眠/唤醒区间、时钟回拨、Windows/Linux 无 pmset。日志不含用户、密码、token、运行命令正文中的敏感参数。
- 报告分离：会话墙钟、确定睡眠（需 pmset 证据）、有效非睡眠墙钟、可计量命令执行、Agent 活跃/思考 `UNKNOWN`、人工等待 `UNKNOWN`；绝不把未计量间隔填成“浪费”。

### 2.2 修复历史重复坑位

开工先构造 **“既有失败 → 最早可发现入口 → 正反自动测试”** 矩阵，并在真实入口加入判定：

1. **日志自扫描**：SelfTest/输出写入已明确排除的 ignored 临时目录；扫描器验证边界，避免刚生成的失败输出再次被自己当作源码扫描；为并发日志写入/完整退出加正反例。
2. **路径/工具参数幻觉**：任务派发前核实文件/目录、项目、解释器、CLI 支持参数和真实可运行的验收入口。错误路径/错误参数必须在启动容器或长任务之前快速失败并给中文诊断；不得硬编码 `/private/tmp`、Mac 用户路径或 Windows 盘符。
3. **阶段合同漂移**：为本阶段新增/修改的 API、DTO、审计 action、DI、授权、Migrations、阶段 guard、fixture、OpenAPI/TS 生成物自动生成消费者检查清单。**不存在的 audit action、遗漏 DI 注册、旧阶段硬编码期待值必须在第一条短真实请求之前失败**；M4 `ontology.impact.generate` 及 9 项事务回滚作为回归样例。
4. **高风险语义错误**：新的删除、关系编辑、时态、IRI、复杂公理路径必须有至少一个“合法且保留语义”的正例和对应越权/未支持/词法错误负例；所有类别先短真实服务测试，不能留到整栈最后发现。
5. **Evidence/ZIP Schema 返工**：原始 evidence 文件创建及每次修改后执行现有 Schema 预检；截图/尺寸/路径/输入 hash 一并验证。稳定候选先使用真实 fixture 做一次非最终 V3 `VerifyOnly`，发现无效字段立刻失败，不等最终 CI 或封包时才暴露。不能将 `VerifyOnly` 单独当成真实产品验收。
6. **测试失败去重**：为失败建立 `fingerprint=(输入Hash、测试/构建版本、平台、错误类别)`，相同指纹短复现仍失败时先定位/变更输入，不重复跑原昂贵 full suite；真正输入变化才按风险补跑。
7. **审查批次**：公共合同冻结后以可运行切片为单位批量独立审查；不为每一条非阻断注释/证据小改动反复暂停 Agent/生成全量证据。

每一个新增规则必须有自动正/反例，所有新增代码和说明采用本项目 C# 中文 XML 文档/TS 注释、跨平台路径及清晰格式。**写入 `AGENTS.md`、`PLANS.md`、`docs/development/ai-development-efficiency.md`、当前验证工具与对应测试**，精简重复文字，避免新增无用抽象或无限增长的提示词。

## 3. G3-M5 核心业务：高阶 OWL 源码与结构只读保真

在 E0-P0 宿主持续运行最低门禁通过后启动正式 M5 纵向业务实现。新 Master 应先复核 G3 计划 20 项能力矩阵以及 M1–M4 已交付范围，**不因 M5 开始而修改已批准的“高阶公理只读/保留/阻断发布”边界**。

### 3.1 正式目标

- 高阶 RDF/OWL Turtle 源码输入、保存、版本读取与导出重入，无静默语义损失；
- 只读表达式树/公理视图，按标准准确展示 restriction、`someValuesFrom`、`allValuesFrom`、`hasValue`、普通和 qualified cardinality、intersection/union/complement、`owl:propertyChainAxiom`、`owl:imports`、属性特征、身份公理等；
- 对匿名表达式、RDF List 与空白节点结构采用有界、有证据的遍历；损坏列表、环、共享空白节点、未知词汇、未锁 imports、超预算明确诊断；
- 语义支持状态单独表示 source-preserved、read-only-structured、editable、publishEligible 和 inferred（是否实际有推理器），不把“解析成功”当作“可发布”；
- 保留前几里程碑已经支持的简单命名公理发布能力，不因复杂公理出现而破坏普通资产；对整图中无法保证安全发布的高阶公理仍按 profile 失败关闭；
- 前端三栏工作台增加高阶结构只读展示与限制说明、来源定位、版本 Diff 与高级源码后备；继续使用 textarea，**Monaco 保持 BLOCKED**；
- 已发布 G2/M1–M4 的 Release、Assessment、ImpactReport、Run/SSE、MCP、Evidence、审批、CAS、Outbox、正式查询与回滚全部回归。

### 3.2 技术与语义边界

- 本体权威仍为 RDF/RDFS/OWL2/Turtle；SHACL Core 验证不是 OWL 逻辑一致性证明。
- 不新增自研 Turtle parser、额外 Java 微服务或未批准 reasoner；使用已引入的 Jena RIOT/现有解析及版本化 profile 作为标准基础。
- `owl:imports` 仅解析/显示引用，不联网抓取、动态加载或执行未锁定内容；不让模型自由调用 SPARQL、SHACL-JS、自定义 target。
- `owl:allValuesFrom` 不等于至少存在值，OWL Functional 不等于数据库唯一约束；属性链保留准确顺序，不把导航遍历当推理；`owl:sameAs` 不靠名称自动推断；复杂匿名类与空白节点不能被简单图编辑器悄悄覆盖。
- 只读结构树应引用标准 term、sourceId/sourceHash、真实语法和范围；无法准确取得源码行/列时不得伪造定位。未支持复杂结构的结构编辑和新发布继续阻断，不借审批绕过。
- 性能预算继承现有 triple/byte/时间/递归深度/搜索节点上限；遇到 `INDETERMINATE` 必须失败关闭，不允许无限递归或全部物化入内存。
- 不引入 M5 以外的 G4 五源、G5 指标规则、真实收费 LLM、通用单位换算或生产外联。

### 3.3 M5 最小纵向切片

- `B1`：导入复杂 OWL 源码 → RIOT 解析 → PostgreSQL 保存原字节 → 高阶表达式只读投影 → 再导出同字节与语义同构 → 明确不支持发布诊断；
- `B2`：相同用户/资源加入合法简单公理 → 已支持资产新修订 → 真实审批发布 → Jena 正式查询 → 旧 Run 和完整影响报告读取 → 回滚；
- `B3`：完整 G3 20 项能力状态矩阵逐项验收，G2/M1–M4 的真实兼容与安全回归，中文 UI 与键盘/移动端测试。

Master 先冻结共享 DTO、能力矩阵与错误/证据契约；独立 Reviewer 先审查合同，再让语义后端和 Web 在独立 Worktree 并行实现。公共契约、Migrations、OpenAPI/TS 生成物、CI、Design Tokens 仍 Single Writer。每个 B1/B2 切片运行最小真实链路并尽早集成，不等 B3 整体验收才首次联调。

## 4. 开发节奏与跨平台验证

- 开工 preflight（目录/入口/依赖/host awake/Docker/真实服务/合同/审计白名单），先通过廉价门禁，再派并行写任务；编译/静态失败先修，不跑整栈。
- 默认本地真实测试 + 风险选择性回归；M5 的新高阶公理用真实 Jena/PG，发布兼容/Impact/SSE 走真实阶段入口，UI 与浏览器用短 Smoke 和完整目标 E2E。Mock 只可补充单测。
- **跨平台**：在 Mac ARM64 实测宿主持续运行；Linux 容器和 CI 只在代码确实涉及 runner/CI 或用户明确授权时执行；Windows native 无实际执行时标记 NOT_RUN，必须做路径/大小写/换行/编码检查，不以 macOS 结果替代。
- 在固定输入上记录失败指纹、可复验的日志窗口、退出码。廉价负例和 UI 状态合同测试先于昂贵 full suite；同输入同失败不能盲跑第二次 600 秒。
- M5 功能和 E0 可靠性修复分别记合同和耗时，避免“为改进效率修工具”无限占据业务关键路径。E0-P0 的生效验证是正式长任务的硬前提；E0-P1 应在相应代码路径首次使用前完成，有非阻断改进则登记后续而不无限扩 scope。

## 5. 验收：本轮必须真实通过的正反例

**E0：**
1. 用户手动能源设置打开或任务级 assertion 真实覆盖整段 M5 会话；`pmset -g assertions`/设置状态可核对，显示器可熄屏；任务结束后临时 assertion 已释放；若不能核对整段只标 PARTIAL/NOT_VERIFIED；
2. 模拟 sleep/wake、CLOCK_DRIFT、子进程 exit0/exit非0及 Windows/Linux，证明计时与业务结果不混淆；
3. 自扫描日志、错误路径/非法参数、旧审计 action、失效 Schema/截图元数据、阶段 guard 漂移由廉价前置检查拒绝；
4. 断言相同失败 fingerprint 的第二次昂贵执行被阻断或缩小范围，输入改变后可以重新尝试。

**M5：**
1. 二十项能力全部有明确 V/S/R/B/L 和保存/编辑/发布/推理状态、正反语料与证据；
2. 同源复杂 Turtle 导入→保存→导出 no-op 字节一致，RDF 图比较能处理 blank node 重命名；
3. RDF List 断裂、循环、不合法 cardinality、未知类型、属性链顺序、imports 引用、超出预算、无权限和跨厂区正反例；
4. 只读表达式树不引发 RDF 源内容变化；尝试未经支持的结构改写或发布被阻断；
5. 简单受控公理仍可完整发布，Jena 查询、ImpactReport、审计、CAS/Outbox、历史 Run/SSE/MCP 和回滚通过；
6. Web 深浅主题、键盘、窄屏、来源证据、中文状态/诊断和真实 API 浏览器 E2E；
7. `git diff --check` exit0、正式 Review ZIP V3 创建和 VerifyOnly 通过；实际 CI 事实如实，未运行记 NOT_RUN；
8. 真实安全 Owner/Reviewer 审查，进程终态、资源 before/after、任务级临时 assert 释放与风险矩阵均有证据。

完整验收不以“只创建脚本/测试”冒充成功；关键测试 0 个执行、全 skipped、Mock 代替关键服务均不能 PASS。

## 6. 工程质量、测试和交付纪律

- C# 所有手写类型、方法、属性、枚举等采用准确中文 XML 文档注释，变量/关键逻辑注释遵循冻结规范；成员间保留空行，XML 注释紧贴声明。
- 前端 TSX 清晰多行排版，变更的手写行默认不超过 200 字符；不为减少行数引入无用框架或泛型 Repository/AutoMapper。
- 日志/审计/Trace 三类数据分开；关键审计 action/权限检查失败时 fail closed，不把错误作为没有记录的成功。
- Review ZIP V3 默认提供全现行代码、变更差异、任务必要证据和历史 Git 恢复索引。过程截图/全量遥测归档，包内最终代表样本 ≤12 张、目标 ≤10 MiB，>15 MiB 需要明确特许，不为缩小包丢失关键证据。
- Source/Tests/Contracts/Docs 稳定后冻结 Head，独立审查→提交/Push→真实适用本地测试/CI 按需→Review ZIP→独立重开→资源收尾及外部回执。避免只因回填 receipt SHA 再次提交引发循环。
- 切片级成果及时 Commit/Push，Master 负责主线集成，写入 Agent 使用独立托管 Worktree；Reviewer 不批准自己写的代码。旧 G2/M4 受保护 Worktree 或数据卷不属于本次清理白名单。
- 每个新增容器/卷/镜像/history 有准确 TaskId、RunId、ID、用途与 TTL；阶段结束按精确白名单实际清理；共享镜像与缓存按引用保留，不做全局 prune。
- 时间线报告分列 wall span、pmset 可确认 sleep、non-sleep span、命令 union/cumulative、测试重验、关键路径与 UNKNOWN，不承诺绝对工期或不可观测的模型活跃工时。
- 安全、性能、语义、发布、跨源和恢复优先级高于人为制造速度指标；E0 不得引入全局电源修改、付费云工具或未经批准第三方依赖。

## 7. Codex Agent 任务合同和 Stop 条件

建议任务分配：
1. `G3-M5-BASE`：Master 读授权、G3 计划、M4 交接、当前仓库与 worktree，冻结 Base/owned_paths/证据路径和后续挂钩。
2. `G3-M5-E0-P0`：Master/工程 Agent 在 Mac 实现宿主唤醒 Preflight、CLI wrapper/可验证 App 策略、真实 task lifetime 检测；独立 Reviewer 通过后才能启动跨夜完整验收。
3. `G3-M5-CONTRACT`：Master 单写高阶表达式状态/只读结构/错误码/API 和权限合同，先审查后冻结。
4. `G3-M5-SEM`：独立 Worktree 实现语义高阶结构保留/只读投影与正反语料；不改公共合同。
5. `G3-M5-WEB`：独立 Worktree 实现 UI 表达式只读树、支持状态、定位和源码后备；不改生成 DTO/Design Tokens。
6. `G3-M5-E0-P1`：工程 Agent 限于验证脚本/CI/时间线/证据路径修复，必须和业务 SEM/WEB 文件所有权隔离；持续在关键切片前提供廉价门禁。
7. `G3-M5-B1/B2`：Master 至少两次纵向真实集成，Reviewer 按切片批量审查；每次冻结输入与 Test/Contract Matrix。
8. `G3-M5-GATE`：真实整栈、兼容、权限、浏览器和高阶语义矩阵；受影响测试先跑，稳定候选完整验收。
9. `G3-M5-REVIEW`：非作者审查、main 集成、适用 CI、唯一 V3 Review ZIP、精确资源收尾与简明 G3 完成度报告。

并行上限和角色以仓库 `.codex` 当前实际配置为准；默认 Master + 2 个可隔离写入 Agent，Review 占用槽位时暂停 writer。无 Worktree 时不假装有并行隔离。共享文件/迁移/合同/锁/生成产物/CI/AGENTS/PLANS/Design Tokens 为 Single Writer。

出现下列情形时仅阻断相关高风险子任务，继续无依赖工作：
- Mac 真实长任务无法避免 Idle Sleep 或 assertion 无法持续（需用户完成系统设置）；
- 高阶源码可能有语义损失、导出不保真、未知结构被静默删除、错误地允许复杂公理发布；
- 旧 Release/Run/SSE 兼容失效、审计与权限可能绕过；
- 新增未经审批的依赖、收费调用、越权清理、试图修改系统能源设置或未知敏感数据处理；
- Review ZIP 损坏、稳定 Head 变更却复用旧验收、真实测试失败且无隔离修复证据。

最终输出：唯一 `OntologyPlatform-Review-G3-M5-001-<Head12>.zip` 路径、大小、SHA256、Base/Head、真实测试矩阵、E0-P0 宿主持续运行证据与睡眠统计、E0-P1 前置防线统计、主线 Git/CI 状态、本任务资源清理 before/after、未关闭风险和 `G3_M5_READY_FOR_REVIEW`。**到此停止，等待 ChatGPT 复审，不直接启动 G4。**
