# G4-M4-QUERY-001｜复审修复与工程根因闭合执行指令

日期：2026-11-15。类型：同任务实施续接，不是新 P0，不是主线集成授权。

> 本文件经用户在 Codex 中明确确认后，作为本轮有限实施授权。ChatGPT 本轮只编制指令，未修改仓库、运行产品或操作用户主机。历史附件中的 PASS/MERGEABLE 是对应时点的报告，不能覆盖本轮发现；历史原件不改写。

## 1. 目标、身份与终点

**目标：修复已发现的 numeric 关系键静默漏边；把 AC-05 因果验证、测试隔离、运行构建隔离、按影响资格和构包口径落实到现有执行入口，用定向反例证明，而不是再增加一套文字制度。**

| 身份 | 固定值 |
|---|---|
| Repository | `on-dotnet/ontology-platform` |
| TaskId | `G4-M4-QUERY-001`，不得另建工程优化或恢复 TaskId |
| 主线预期基线 / 最终包 Base | `f0afb730ce92ecbd3a5947d9c6f58faedc8b2138` |
| 本轮修复起点 / 上次交付 Head | `0ab9658ae7873fe98a927a0202d6f51f391a2371` |
| 上次 TestedCommit | `127c7650194761a2c1324340c9cb45708847ff31` |
| 原分支 | `codex/g4-m4-query-001` |
| 原工作树 | `/Users/chasen/.codex/worktrees/g4-m4-query-001/ontology-platform`，启动前按 Git 实况核对 |
| 原 ZIP | `OntologyPlatform-Review-G4-M4-QUERY-001-0ab9658ae787.zip` |
| 原 ZIP SHA-256 | `129c77f14b61589be1634cd4fc7f76697ac3cad0c1c1795933b00f75185c7039` |
| 原 ZIP 大小 | `13,871,429` 字节 |
| 本轮证据批次建议 | `review-fix-01`；保留旧批次，不覆盖 |
| 本轮终点 | 修复后唯一当前最终 V3、包外回执、非作者源码及证据审查、独立 VerifyOnly；停等 ChatGPT 复审 |

本轮不允许将已知有缺陷的旧 Head 合并。完成后也不自动合并新 Head。

开始时只做一次正常 fetch/引用与工作树核对。预期 main 和任务 Head 均需核对；发现未预期提交、分叉或用户改动，保护现场并报告差异，不 reset、不覆盖、不强推。不要重新调查 M1–M3 或重读全部历史会话。

## 2. 会话、模型和执行组织

| 项目 | 设置 |
|---|---|
| 是否新建会话 | 否，继续 `G4-M4-QUERY-001-MASTER` |
| 推荐模型 | GPT-6 Astra；以客户端实际可用为准，已在用则沿用 |
| 推荐推理强度 | 常规实施 Medium；类型语义、证据依赖和独立终审可局部使用 High；不默认 Max/Ultra/Fast |
| 模式 | Code / Agent，直接实施；不是 Plan-only |
| 环境 | Local，原 Mac ARM64；不迁往 Cloud/Windows/Intel |
| Worktree | 复用原托管工作树、分支及已核验缓存，不重新创建主工作树 |
| 作者 | 一个 Master 单写产品比较逻辑、共享工程脚本和合同说明 |
| Reviewer | 一位非作者只读 Reviewer；先检查关键反例是否准确，再终审实际差异与原件；无需逐文件审批 |
| 并行 | 可以并行只读分析；不得并行改公共脚本、构建配置、测试库或同一运行实例 |

先在现有任务卡内给出一页以内的实施清单、准确 owned_paths 和受影响 gate，然后在本文件范围内继续，不等逐补丁/逐 AC 人工批准。模型/强度读不到就写“建议值，实际未读取”，不伪造客户端配置。

使用已有的 systematic-debugging、test-driven-development、receiving-code-review、verification-before-completion 工作法；无需安装 Skill。项目现行授权、零下载、按影响验收和资源规则优先于通用 Skill 中的安装、全量测试或清理示例。

## 3. 授权范围与不可变边界

### 3.1 本轮明确允许

1. 修复本轮识别出的 P1-01；新增内部类型化比较 helper 和对应单元、真实 PG 及必要 UI/MCP 定向回归。
2. 加强 AC-05 原件资格器、测试证据输出与反例；不修改五秒产品预算和正式授权/事务参与者。
3. 在当前 M4 适配器及已有公共机制中拆分资格输入职责，复用既有 gate 注册、执行、计时、证据与失败止损，不新造框架。
4. 固化现有独立测试库准入，完成运行构建与测试构建的目录隔离；继承已修复的持久密钥方案，不重新生成或销毁旧密钥。
5. 对现有构包器做最小职责提取，让预检与正式 V3 复用成员选择；允许必要的内部工程报告/诊断字段变更，不改变 V3 制品格式和安全规则。
6. 必要的当前 M4 合成资源启停、离线构建和定向测试；仅在已核身份和既有资源预算内操作。本轮新建的隔离测试库/临时容器按准确 ID 回收。
7. 更新现行任务卡、授权索引和本轮修复证据；将少量“不可绕过的执行要求”合并到现行效率规则/SDD模板，不再追加第二套制度。
8. 普通提交及普通 push 当前任务分支，默认生成修复后的最终 V3、SHA、包外回执和非作者独立重开，无需另申请打包。

### 3.2 本轮不允许

- 更新 main、强推、改分支保护、部署生产、进入 M5、恢复 TDengine、扩展其他连接器。
- 新下载、新依赖、新镜像、新 Skill、升级 SDK/驱动/Node/pnpm、收费模型或云服务。
- 改 G2 冻结 DTO、M3 历史 Manifest/canonical、G4 对外六态/字段/精度合同、数据库业务迁移、权限默认授予、IdP 已接受风险边界。
- 用缩窄已批准 numeric 支持范围、去掉 precision/scale、修改历史规范字节、放宽状态判定或秘密扫描来使测试变绿。
- 修改旧 ZIP、旧原件、旧 FAIL/事故记录或抹去当前 23 份历史 PASS 恢复索引、5 份 FAIL 快照。回执有旧结论也按原样保留，在新记录说明被哪个发现推翻。
- 清理、改挂载或复制其他任务 KEEP 资源及私有凭据；清空 M4 运行库、恢复空库覆盖现有查询、全局 prune/restart/改 Docker 配额或宿主信任。

需要超出以上边界时，仅停止受影响项并集中报告准确差异；其余独立项可以继续。不为范围内的 helper、测试、格式、路径适配重复请求授权。

## 4. 已定位问题与复现入口

以下行号对应修复起点 `0ab9658…`，不是要求按固定行号打补丁；先核对源码与调用路径。

| ID | 位置 | 事实与本轮目标 |
|---|---|---|
| P1-01 | `backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/G4QueryExecution.cs:465–469` | Relationship 用完整 G4QueryValue canonical/hash 判断连接键相等；numeric 等值但 precision/scale 表示不同会被丢边。以真实失败测试复现并修正 |
| P1 上游 | `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/PgQueryReader.cs:228–256,438–455` | 源查询按精确数值匹配，输出保留声明精度；不能破坏输出表示来修连接语义 |
| P1 语义对照 | 同 Connections 模块 `Adapters/PgMappingSourceValidator.cs:278–305`、`Application/MappingValidationService.cs` | M3 numeric 参考值按无损十进制规范化；须验证 M3 已合法接受的映射在 M4 结果一致 |
| P2-01 | `scripts/maintenance/workflow_m4_query.py:1377–1405` | ABA 资格器已查身份、修订、409、零残留和耗时，但未独立核完整因果时间与同 mapping 链 |
| P2-02 | 同脚本 `:1307–1366,1408–1413` | 资格绑定接近全仓输入；当前24资格包含相同861输入，需明确按真实依赖分层 |
| 已修复但需守住 | `backend/tests/OntologyPlatform.QueryTests/G4QueryPersistenceTests.cs:85–98`、M4脚本 `:1084` 起 | 已有独立测试库名称/服务端注释核验；复用并覆盖所有破坏性入口，不能重新退回运行库 |
| 运行构建 | M4脚本 `runtime_api_rebuild/runtime_api_resume/runtime_binding` | API 依赖可变 bin/obj 产生漂移；改为不可变运行快照，并保持构建/进程/来源绑定 |
| P2-03 | `scripts/maintenance/workflow.py:386–409`、`scripts/create-review-package.ps1` 的 `Get-ReviewSnapshot` 等 | 估算与正式包成员口径不同；复用实际选择，不改变15MiB硬限 |

复审发现不是强迫作者同意的代码指令。先用最小失败用例验证 P1；若实际调用链反证了该问题，提交准确反证与原件，停止该项盲改。不得为制造“红灯”篡改正式数据或断言。

## 5. 按行为实施，不按文件层分批完成

### S0：轻量恢复与安全基线

- 读取当前授权、任务卡、唯一 A–F、现行效率规则和 SDD 模板；只加载本轮相关代码。
- 将唯一当前状态改为修复中，列明旧 PASS 的适用范围已被 P1 发现限制；不反向编辑历史 PASS 原件。
- 明确区分 **资源归属 Run** 和 **本轮证据批次**。当前脚本资源标签/数据库注释可能仍绑定 `query-impl-01`；不得全局改成 `review-fix-01` 后冒认旧资源归属。新证据写新批次，旧资源保留原 Owner，并有明确使用引用；需要最小参数化时在本轮脚本范围内实施。
- 当前已有可用隔离保护则直接使用；缺保护先补廉价拒绝测试，再运行破坏性用例。只核一次必要环境资格，不无理由 restore 或整栈重建。
- 为本轮首份原件立即验证写入→解析→归档路径。它是 ignored 诊断，不是中间交付 ZIP。

### S1：先关闭 P1，形成最短真实语义路径

#### 行为要求

1. 在已批准的有限 numeric 范围内，连接键按**精确数值**比较；例如 `numeric(10,2)=1.00` 和 `numeric(12,2)=1.00` 必须匹配。合法不同 scale 的等值也应按既有语义处理。
2. 显示/传输/恢复仍保留各自 lexical、precision、scale；不修改 `G4QueryCanonical` 或历史结果的 hash。
3. 不使用 double、float、容差、隐式舍入、文化相关解析或仅取 `.ToString()`；只采用现有类型范围可无损表达的方式。
4. 支持的其他同类型关系键保持既有语义；复合键逐项、按原顺序比较，不通过简单拼接制造碰撞。不同 org/site、无有效时间重叠不得产生边。
5. null 不等于零或空字符串，也不能让两个 null 自动成边；未知、不兼容或无损转换无法证明时沿既有明确错误边界拒绝，不静默包装为完整 EMPTY/FOUND。
6. 不顺便发明数字字符串与数字、跨时区、大小写/排序规则或新数据库类型的等价关系。发现原合同对此含糊，记录准确冲突；本轮首先解决 numeric 对 numeric 的确定性缺陷。

#### RED → GREEN

- 先添加以独立预期关系集合为判据的失败用例，对当前旧实现运行并保存真实失败。测试预期不能调用待修 comparator/canonical/hash 自己计算“正确答案”。
- 最小修复优先放在 SemanticQuery 内部 helper，仅在已有模块引用允许时复用已经存在的无损比较能力；不新增项目依赖来追求形式上的共享。
- 建立两个真实合成表，用正式 M3 发布/评估/异人审核/激活取得映射，再通过正式 G4 Gateway 查询。确认源端确有匹配、关系端点及 evidence/receipt 完整、结果状态没有把遗漏包装成成功。
- 原映射、历史结果和旧 canonical 字节保留。新执行按新源码/构建输入绑定；若现有注册执行器版本策略要求更新，只按该策略处理，不改旧 Release/旧结果来适应新代码。
- 第一次真实正反例闭合后让 Reviewer 核对语义，不等整个工程修改结束才发现本缺陷仍未修复。

### S2：把验收及工程边界改成现有入口的确定性检查

#### S2a：AC-05 因果资格

使用当前 `G4QueryAbaRuntimeTests.cs` 及 `demand_aba_original`，不新建第二套 ABA 实现。验证以下关联：

- 同一 Task、queryId、mappingId、捕获 binding 和当前运行；实际只读 PG 完成后，查询尚未提交。
- 捕获 A → 正式 B 激活 → 正式 A 回滚激活，前后 Release 链连续、mapping 相同，ActivationId 不同、revision 单调递增。取实际回执，不硬编码3/4/5或1。
- 两次激活完成在原查询 deadline 内；实际源读取、激活、提交拒绝的先后顺序可验证。UTC用于关联，单调时钟用于同进程耗时；数据库时间分辨率导致相等时，必须以已记录事件顺序证明，不能加宽预算或猜顺序。
- 原五秒预算不变；正式 DI/源读取/Mapping服务/Worker/授权/审计/结果存储保持。不能换 fake binding、直接写activation表、查询结束后才ABA或把连接版本变化冒充映射ABA。
- 两次激活完成之后，准确以409/query_binding_stale拒绝；同queryId无COMPLETED、密文/hash/size成功结果、已提交读取回执及成功审计。

缺证字段允许只扩充**测试/工程原件报告**，不扩公共产品DTO。资格器负例包括：事后ABA、错mapping、错query、倒序、缺阶段、放宽deadline、只切一次、同修订、非409/错误code、成功残留、重复矛盾报告。合成反例标明测试用途，不能替换正式原件。

本轮会修改共享 `G4QueryExecution`，因此最终新候选的真实AC-05应进入受影响定向验证；这不是因新Head自动重跑。仅补资格器而执行输入完全未变的后续改动，应重新解析原件，不再重复真实ABA。

#### S2b：隔离保护覆盖，继承已有修复

- 复用已有独立测试库机制，检查迁移、时间推进、Sweep、清空/删除与清理各入口在破坏操作前均核对客户端目标、真实数据库身份、Task/ResourceRun/nonce所有权。
- 不能只凭名字或客户端注释认定独占；当前实际服务端标记需匹配。允许精确随机测试库的创建/迁移/销毁，不允许针对运行库执行Sweep来“测试能否拦住”。
- 反例应在守卫处被拒绝：运行库名、缺标记、其他Run标记、伪造同名、错误容器归属；可以读取受控元数据，但任何破坏性SQL均不得已发送。
- 对准确的非空运行query记录建立只读保全见证；隔离测试前后原ID/hash仍可恢复。禁止用空库代替保全证明。
- 持久keyring已修复则保留；验证其挂载/生命周期覆盖结果保留期，准确API重启后可恢复同一原字节，不重查业务源。不得复制秘密入证据或重新生成key覆盖旧key。

#### S2c：不可变运行构建

- 运行API不再直接挂载测试build可能覆盖的工作区bin/obj；在当前ignored任务目录形成带内容清单的运行构建快照，并只读挂载。
- 清单包含实际依赖DLL、deps/runtimeconfig和所需内容文件，关联源码/项目/构建配置、生成合同、工具平台、build命令及进程身份；不能只验证一个主DLL。
- 新build写新目录。切换仅针对本任务准确API容器，执行有界停启/就绪与前后输入绑定；其他服务、用户网络和私有keyring不改变。
- 见证：运行快照启用后，执行一次确会构建相关项目的定向测试；运行文件散列保持不变、查询可用，未发生因为覆盖bin而被迫的无理由重启。临时构建缓存按内容复用。
- 不复制新工具链，不制作新Docker镜像，不对所有项目做构建系统改造；只解决当前M4真实调用路径。

#### S2d：按实际依赖分层资格

以已有gate登记和内容身份机制为唯一入口，保守但不全仓绑定。允许先做到程序集/模块级闭包，不建设方法级依赖推导框架。

| 层 | 包含 | 变化后的正确动作 |
|---|---|---|
| 产品执行 | 实际执行源码、传递项目/共享合同、生成资源、编译配置、相关锁/工具平台、正式配置/源语义 | 构建/执行受影响产品场景 |
| 测试与驱动 | 对应断言、fixture、编排/调度、请求参数、正式参与者与预算 | 执行该用例及受影响场景 |
| 资格解释 | 原件解析、证据资格、输入范围策略及其自身测试 | 用当前解释器重核不可变原件；矛盾/不足才定向补测 |
| 归档展示 | 无损封套、路径映射、显示、副本/成员选择 | 验保真恢复、散列、扫描、包与索引；不因这一层重新执行产品 |

- 兼有执行与解析的文件先拆清职责再区分身份，不能简单把整个 `workflow_m4_query.py` 排除。
- 未分类的实质改动、遗漏新增源文件、工具/配置未知漂移应拒绝相关覆盖声明，不全局默许。
- 必须保留原执行输入和原构建二进制身份；不能拿当前新build给旧执行换标签。解析器的新测试绑定当前版本；旧PASS不是解析器通过的理由。
- 861项旧输入原件保持；从旧输入投影到相关闭包，只有能证明原件覆盖全部相关文件、参数、环境且无已知缺陷推翻时才可复用。缺任何必要字段就定向新测，不能手补历史数据。
- P1反例没有被旧测试覆盖：不能靠重新分组资格把缺陷报告改成通过。
- 增加小型失效反例：只改显示不触发产品；只改解析触发重核；改变比较器/真实驱动/断言/fixture/相关合同必须失效；无关连接器说明不使PG查询测试失效。

#### S2e：一致的V3成员选择与大小预检

- 以生产构包器现有 `Get-ReviewSnapshot` 等实际选择为权威，最小提取可复用的只读成员计划/输出模式，让Python预检消费同一结果；不在两处复制截图、去重或diff选择逻辑。
- 允许新增一个必要内部helper或PowerShell模块，但不引入新语言/工具依赖或第二构包器。供预检的模式不得生成正式交付ZIP或修改历史源码。
- 区分 ESTIMATE、正式候选成员选择及实际 ZIP 大小。估算有保守余量应明示；不能宣称与实际逐字相等。估算-only超量可以提示需精确计算，其他安全/路径/Schema/身份失败仍然阻断。
- 15MiB=15,728,640字节为最终实际硬限，10MiB软目标仍须解释构成。不得提限、跳过扫描/VerifyOnly、删除必要当前原件或FAIL来过关。
- 在合成小夹具中验证：重复内容、多PNG选择、二进制变更索引、文本diff、metadata/ZIP开销、路径/秘密负例、真实超限。旧V3可重开及V1/V2必要兼容保持；修改共同构包代码需跑现有相关定向回归。
- 原BLOCKED估算及原ZIP大小/解释保留。新结果来自新算法，不倒改旧状态。

### S3：稳定输入后按影响验收与交付

各切片分别形成可核验结果，不额外增加人工审批关口。S1产品和S2工程变更分提交或可分离差异；整体仍在同一任务分支，避免无法区分修改来源。

先冻结实际源码/测试/驱动/工具输入，再集中跑受影响验证。公共执行/构包机制若改变，安排一次有依据的完整工程SelfTest；稳定后纯证据修订只跑相关定向检查。新的实质变化可以增加有理由的验证，不设置“只能跑一次”来压制真实失败，也不能每个Head自动全跑。

## 6. 本轮验收矩阵：在原任务卡关联，不新增审批表

| ID | 必须可观察的结果 | 最小验证方式 |
|---|---|---|
| RF-01 | 旧实现对不同precision等值numeric漏边的真实RED，修复后GREEN | 确定性单元反例＋实际PG最短链；独立预期集合 |
| RF-02 | scale/零/负值/接近已支持精度上限/不等值/复合键/null/不兼容类型不误匹配或静默成功 | 批量定向测试；按已批准语义，无float或舍入 |
| RF-03 | 正式M3接受/发布的映射，经M4返回正确关系、端点、六态和可解引用证据；回读原规范字节 | 真实PG＋正式Gateway；UI/MCP受影响消费者最短兼容 |
| RF-04 | 当前真实执行中ABA保持正式参与者和五秒预算，409且同query无成功残留 | 最终受影响真实用例；新上下文检查准确ID |
| RF-05 | ABA资格器拒绝事后切换、错身份、倒序、放宽deadline、成功残留等 | 从已保存原件派生的标识化合成负例，不冒充真实执行 |
| RF-06 | 所有相关破坏性测试入口在SQL前拒绝运行库/错归属；隔离运行后非空运行结果保全 | 守卫负例＋一次真实独立测试库保全检查 |
| RF-07 | 测试build不改运行快照；受控API重启后同queryId/hash恢复、业务源查询不重跑 | 前后文件/进程身份＋现有read计数和规范字节 |
| RF-08 | 资格四层变更只使真实依赖失效；未知实质变更拒绝，旧失败不洗白 | 小型变更矩阵，当前策略自检 |
| RF-09 | 预检/正式V3选择同一成员集合；实际15MiB、扫描、历史兼容未放宽 | 合成小包定向测试＋最终实际包 |
| RF-10 | 已有授权/取消/六态/恢复/G2兼容没有被本轮变更破坏 | 按依赖选择，FRESH/REUSED及理由逐项区分 |
| RF-11 | 原23历史PASS索引、5份FAIL、事故及旧ZIP不变；外部未取回原件仍NOT_VERIFIED | 当前/历史索引和散列；不强行抓取全历史 |
| RF-12 | 当前源码/执行/资格/Head绑定与资源/实际耗时可复核，非作者Review无未关闭阻断 | 唯一新最终V3＋非作者VerifyOnly＋包外回执 |

RF不是新业务阶段或逐项审批。确有已修复机制无需改代码，可提交当前机制及定向证明，不能为凑修改文件数重复重构。

## 7. 精确代码与工程修改边界

Master在一页开工清单列实际触碰路径及理由，范围如下：

**产品最小范围**
- `backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/G4QueryExecution.cs`。
- 必要新增的同模块内部关系键比较helper，例如 `G4QueryKeyEquality.cs`；不新增对外DTO/API。
- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/PgQueryReader.cs` 仅允许为已批准关系比较链的必要修正；未需改动就不改。
- `G4QueryCanonical.cs`、`G4QueryModels.cs`、G4对外Schema及M3历史canonical只读；不能用规范表示变更代替语义修复。
- M3 `PgMappingSourceValidator`/`MappingValidationService`作为对照默认只读。不为复现方便改映射审批或手写成功Release。

**定向测试**
- `backend/tests/OntologyPlatform.QueryTests/G4QueryTests.cs`、`G4QueryRaceTests.cs`、`G4QueryPersistenceTests.cs`及同目录必要的关系键/隔离测试helper。
- `backend/tests/OntologyPlatform.ConnectionsTests/G4QuerySourceTests.cs`。
- `backend/tests/OntologyPlatform.AgentTests/G4QueryAbaRuntimeTests.cs`、`G4QueryMcpTests.cs`。
- `backend/tests/OntologyPlatform.SecurityTests/G4QueryAuthorizationTests.cs`及`OntologyPlatform.G2ContractTests/G4QueryWireTests.cs`仅相关兼容测试。
- Web查询相关测试和本任务浏览器驱动按影响适配；不改页面视觉/交互业务范围。

**工程最小范围**
- `scripts/maintenance/workflow_m4_query.py`、`workflow-m4-query.mjs`，允许将职责拆到同目录最少数量的 `workflow_m4_query_*` helper；所有执行仍走已有公共执行/双流/计时机制。
- `scripts/maintenance/workflow.py` 中相关资格接入、package-check，`scripts/create-review-package.ps1` 中只读成员计划提取；必要新增共用selection/helper，不改变V3格式。
- `scripts/tests/WorkflowQuery.Tests.py`、`Workflow.Tests.py`、`WorkflowDelivery.Tests.py`、`ReviewPackage.Tests.ps1`及这些机制的必要回归；`docs/development/verification-gates.json` 做准确依赖登记。
- 原M4任务的Compose/运行覆盖层只允许运行快照挂载与现有keyring保留所必需的配置；先从当前任务入口查到准确路径再列入清单，不猜旧任务路径。
- `docs/tasks/G4-M4-QUERY-001.md`、`docs/tasks/current-authorization.md`、本任务A–F的修复说明、本任务新证据目录。现行效率规则/SDD模板只合并必要约束，避免大段重复。

未列但确属上述机制直接同目录helper/测试，先在清单说明依赖并由非作者查范围，范围内不逐文件人审；跨模块业务语义、公共DTO、数据库迁移、新依赖则停对应项申请。

## 8. 运行授权、资源预算和安全恢复

本轮为同一M4任务续接，允许为定向验证使用已批准的本任务合成设施，保留既有供应链与IdP限制。旧回执“KEEP/不操作”不应被误读成永远不能为已批准修复启动本任务服务；也不能被解释为允许删除持久资源。

按原A–F F2核当前资源：M4基础六组件5.75GiB/7CPU；含短命第二API的M4峰值6.5GiB/8CPU、最多7个并发容器、每容器PIDs≤256；与其他任务共同容器上限14GiB/16CPU，宿主Web/浏览器预算4GiB。16CPU是配置预算，不宣称宿主有16个物理核，实际压力仍需核验。

M4数据≤3GiB、过程证据≤1GiB、缓存/构建≤6GiB、总增量≤10GiB；与M3历史磁盘预算合并上限20GiB。并发测试容器算进预算，必要时与第二API串行；不通过漏算KEEP消耗释放账面配额。可用量不明或超限停受影响运行，不擅改VM或清旧卷。

只用已验证的本地依赖、镜像和工具；新增下载为0。必要恢复仅利用离线已核内容，准备键相同直接复用；缺失内容集中报告，不偷偷联机。M4已登记回环端口15441–15448按当前占用复核，冲突仅选择未占用回环端口并记录，不停止别的服务。

数据库/运行输出/证据批次身份明确分离。只回收本轮新建、独占、已停止且无引用的准确临时对象，保留before-command-exit-after。M4既有运行库、持久keyring、原查询、历史原件、ZIP、用户文件及其他任务KEEP保留。不把短期测试nonce、取证用副本与需长期保留的解密材料用同一清理规则。

同一失败无新假设不重启长链；先分类PRODUCT/HARNESS/EVIDENCE/ENVIRONMENT/EXTERNAL再定向诊断。升级权限使用正常审批，不绕过平台拒绝。

## 9. 原件、独立审查与最终交付

- 首先保留RED、历史事故和缺陷定位；绿色结果不覆盖红色原件。当前资格不能仅相信上游自报PASS或测试个数。
- 新增工程/测试报告可以增加必要因果字段及分层输入身份；旧原件保持旧Schema，不凭空补出历史时间或mappingId。
- 原23历史PASS恢复索引、5份FAIL快照和322当前原件作为上一交付基线。新包可以继续按V3去重/封套/历史索引机制组织，但本轮关键反例、因果报告、命令输出和资格必须可直接恢复；不为体积把全部关键证据变成外链。
- 精确区分：本轮FRESH执行、原执行REUSED/本轮资格FRESH、未执行NOT_RUN、外部未取回原件NOT_VERIFIED。未证明的来源不作为当前PASS必要依据。
- Reviewer独立核P1的反例和期望、真实链、ABA负例、按影响复用与资源保护，不只读作者结论；随后对最终同一ZIP做VerifyOnly。Reviewer不能同时是所审实现作者。
- 只提交一个修复后的“当前最终”ZIP；原ZIP及其旧回执转为历史但字节不变。稳定候选前使用ignored小样，不重复正式构包。若最终构包真实失败，保留失败、修最小问题，不用“只能构包一次”阻止必要修复。
- 最终新ZIP Base仍为主线基线 `f0afb730…`，另附 `0ab9658…→修复Head` 的准确增量；不能把repair起点替代整个M4最终差异。完整源码/执行脚本/测试、Base/Head/TestedCommit、输入版本、git差异、当前证据、历史索引、安全扫描、体积和独立重开都按V3记录。
- 最终Head普通push后回读，包Head须可恢复。包外回执不递归要求重打ZIP；Tested→Head若仅证据文档需证明，无实质输入变化时不重跑产品。

**交付给用户只报三项：** 唯一当前最终V3、包外最终回执、同一修复报告/验收矩阵入口。详细原件都由索引恢复，不另交多套相同报告。

回执至少有：Base、repairBase、TestedCommit、Head、远端引用、ZIP大小/SHA；P1/P2/RF逐项结果与准确原件；fresh/reused/未验证边界；实际build/restore/产品与ABA执行/完整SelfTest/构包次数；准备/执行/证据处理的实际时间和未知时段；资源保全/回收；原ZIP散列未变。不要以测试数增加、脚本行数或主观感受宣称提速。

全部约定闭合后状态为 `G4_M4_QUERY_001_REVIEW_FIX_READY_FOR_CHATGPT_REVIEW`；若尚有阻断，写准确BLOCKED与已完成项，不预报MERGEABLE。停在ChatGPT独立复审关口，不进入main或M5。

## 10. 参考方法与本轮实施边界

本轮按“规格→可证伪反例→最短真实路径→最小修复→按影响复验”执行。SDD模板用于追踪，不代替机器断言；改善已有脚本，不新增重复流程Skill或回填不存在的早期验证。

方法参考（2026-11-15核对，非额外执行许可）：
- OpenAI《Iterating Development Workflows with Codex》：可机械判断的条件用确定性代码；可复现失败进入回归；规则结构通过不等于工作流改善。
  `https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex`
- OpenAI 模型/用量说明：Astra可用于复杂调试，Medium为速度与推理的平衡；实际选择以账户权限为准，局部复杂审查再提升。
  `https://help.openai.com/en/articles/20001516-managing-usage-with-gpt-6-astra-in-work-and-codex`

本文件不承诺“以后绝无缺陷”；要求把已经识别且可复现的失败模式变成会阻止重犯的代码、断言和可审查结果。不能只更新文档就宣告根因闭合。
