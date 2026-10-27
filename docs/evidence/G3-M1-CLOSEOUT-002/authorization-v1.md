# OntologyPlatform · G3-M1-CLOSEOUT-002
## 正式审查包、Docker 生命周期与研发效率治理纠偏 V1.0

> **模型建议：**Master：GPT-6.1 Sol / **High** / 普通执行模式；独立 Reviewer：GPT-6 Astra / High；只读盘点 Agent：Sol / Medium。若不能单独配置子 Agent，Master 使用 Sol / High。
>
> **交付标记：**`G3_M1_CLOSEOUT_READY_FOR_REVIEW`。仅表示提交复审；完成后停止，不启动 M2。

## 0. 授权范围与已知事实

仓库 `on-dotnet/ontology-platform`，Mac 路径 `/Users/chasen/Developer/repos/ontology-platform`。G3-M1 Head 为 `47935fb2eda3d708e628a1b23ccd897e2250ff33`；该 Head 的 GitHub CI Run `40462137827` 的 `engineering`、`governance-integration` 成功。开工必须重新 fetch，使用最新 origin/main，不假设 SHA 未变。

原 Review ZIP 为 35,269,794 bytes，SHA256 `68db63d0396a534a14b1452659f6fef53f141ced0a51875da124f988c7aec370`。临时 Delivery Slim 为约 10.8 MB，SHA256 `df6c534ce6f5261f966b4335637d99d8d364d9aa2935db72f88165ce06da066f`。Slim 只是传阅包，**不是正式构包器的永久修复**。

调查确认：53 张不同字节 PNG 压缩后约 30 MB（约占原包 85.2%）；manifest 展开 55,256 条 ignored 路径，压缩后约 1.89 MB。侧会话因 Docker socket `permission denied` 未执行删除，也未确认实时状态。AppHost `AddDockerfile` 与 `scripts/acceptance/g2-integration.ps1` 各自构建 Fuseki，导致镜像引用和 BuildKit history 增长。24 个 G2 卷属于三套环境，每套 8 个；不能全删，也不能无理由永久保护。M1 墙钟跨度约 3:45，完整入口约 10:22；额外成本来自 preflight 不足、整栈阶段才发现兼容/导入竞态/资源前缀问题、重复完整验收、证据过量和串行收尾。

原包 `git/diff-check.txt` 是 FAIL：`docs/evidence/G3-M1-001/SEM/g3-sem-selftest.txt:5: new blank line at EOF.` 必须纠正并重新验证，不能将该失败继续带入新 Head 的最终 diff-check。

本轮只修复工程治理、正式构包器、Docker 构建路径/资源生命周期和交付质量；不重做 M1 业务，不启动 M2，不改变 OWL/SHACL 合同。禁止改写历史 Git、强推、重置 Docker Desktop、清理其他项目、删除凭证或操作生产资源。

## 1. H1：先取得真实状态

读取 `AGENTS.md`、`PLANS.md`、当前授权、G3-M1 任务卡/交付报告、`docs/development/review-package-spec.md`、`docs/development/resource-lifecycle.md`、`scripts/create-review-package.ps1`、清理器及测试、`backend/src/AppHost/G2Infrastructure.cs`、`scripts/acceptance/g2-integration.ps1`。

在 Mac **本地执行环境**实际检查 Git、Worktree、Docker CLI/Engine/socket、Docker Desktop/Buildx/BuildKit 版本及 builder generation。若 Docker socket 不可用，记录准确错误并停止 Docker 删除；不能在无 socket 的侧会话中声称已清理。

生成 Docker before 清单：容器、镜像 ID/RepoTags/digests、镜像引用、builder、build history 精确 Ref、卷名/labels/mount 引用/创建时间/所属环境、网络、日志卷归属。不得读取卷内业务内容或输出秘密。分类 `KEEP_PRIMARY_DEV`、`KEEP_UNIQUE_RECOVERY`、`SAFE_CANDIDATE`、`AMBIGUOUS`、`UNREFERENCED_IMAGE`、`EXPIRED_BUILD_HISTORY`。删除按准确 ID/Ref 和引用证据进行，不能凭显示名、`<none>` 或 UI 容量推断。

若发现非预期工作树更改、活跃任务或未提交数据，先保护，不覆盖；继续无依赖的其他工作。

## 2. H2：正式修复 Review ZIP，而不是临时 Slim

修改正式 `scripts/create-review-package.ps1`、验证器、`scripts/tests/ReviewPackage.Tests.ps1`、`docs/development/review-package-spec.md`。为避免静默改变历史合同，引入 **schemaVersion=3 compact review package**，默认创建 V3；`VerifyOnly` 继续验证历史 V1/V2，旧包与历史 SHA 不原地修改。

V3 必须包含：`REVIEW_SUMMARY.md`、`manifest.json`、`SHA256SUMS.txt`、完整文本 `git/diff-text.patch`、`git/changed-files.json`、`git/commits.txt`、`git/diff-check.txt`、`git/ci.json`、`source/`、`review-evidence/`、`evidence-index.json`。

证据策略：
- 当前可审查源码/配置/测试只存一份，禁止 `source/docs/evidence` 与顶层 evidence 重复复制。
- 默认仅保留最终稳定验收的代表截图，每个关键页面/主题/视口最多一张，默认最多 12 张、PNG 压缩总量目标 ≤3 MiB。早期过程截图只保留 Git 恢复索引（准确 commit/blob OID/SHA256/size/path），不删除 Git 中原始证据。
- ignored 文件不得无限枚举。manifest 保存按目录/类别聚合数量、总字节估算、清单 SHA256、扫描时间和少量必要示例。逐文件列表仅作本地 artifact，不随 ZIP 传阅。
- 任一 payload 只存一次；文本差异完整，二进制差异列 Base/Head blob OID、SHA256、size、mode、状态。不能为缩包丢失源码、关键失败证据或无法从 Git 恢复的唯一材料。
- 省略内容必须可从精确 Git 对象恢复并验证 hash/size；摘要明确 Slim 不等于独立离线审计包。
- manifest 包含 Base/Head 完整 SHA、TaskId、真实同 Head CI run/job、状态、证据索引与 schema 版本。Master 必须从 GitHub 实际查询 run 和两个 job；不能只信任手工传入 `success`。
- 软目标 ≤10 MiB；>10 MiB 输出分类体积报告；>15 MiB 阻断默认交付，除非任务合同记录经审查的具体例外。
- 从已提交 Head 构包；Base 必须为 Head 祖先、工作树干净；拒绝路径穿越、大小写冲突、符号链接、敏感文件、伪造 CI/索引/散列。独立重开后重算成员 hash、Git blob、文本 diff 和证据索引。
- `.partial` 原子发布；失败不能覆盖最后有效 ZIP，也不能为构包成功而删除测试失败证据或伪改 CI 状态。

V3 测试必须真实覆盖：V1/V2 VerifyOnly 不回归；53 张合成截图与 55,256 条 ignored 路径的 fixture 能显著瘦身；无双份 payload；文本 diff、二进制索引完整；索引可恢复；CI 与 Head 对齐；非祖先 Base、脏树、未跟踪文件、伪造 CI、篡改 hash、缺失索引、重复/大小写冲突、路径穿越、符号链接、秘密扫描命中、超体积门禁均拒绝。

## 3. H3：统一 Docker 构建来源并实际清理

### 3.1 消除重复 Fuseki 构建

检查 `G2Infrastructure.cs` 的 `AddDockerfile` 与 `g2-integration.ps1` 的 `docker build`。设计并实现单一 canonical Fuseki image build source，让 AppHost 和集成验收复用同一镜像定义/标签或明确共享构建结果，避免两条独立路径不断产生不同标签和 build history。若 Aspire 必须生成独立 image ref，须有固定映射和清理元数据，不能只凭标签名清理。加入测试证明连续运行不会无界新增镜像引用/history。

### 3.2 实际 Docker 清理

必须在有 Docker socket 权限的 Mac 本地 Master 环境执行，不得只提交盘点报告。保留一套选定的日常开发环境、必要固定镜像/网络/持久卷，以及有唯一恢复价值的数据。对另外两套旧 G2 测试环境逐卷核对活跃挂载、恢复需求和私有运行状态；若无唯一价值且已验证可再生/有可验证备份，允许按准确白名单删除。不能把所有旧卷永久保留，也不能直接删除全部 24 个卷。

- 清理本任务产生且无容器/manifest 引用的重复 Fuseki 镜像标签/镜像 ID；核对共享层，报告实际可回收量，不把每行显示容量相加。
- 清理本任务已结束的准确 Buildx history Ref。Build history、镜像标签、共享 layer、build cache、Loki 日志卷是不同资源，分别记录和验证。
- Build history 删除后不能仅凭 `rm` exit 0 或列表缺席判成功；核对客户端/服务端版本、builder/VM generation，使用该版本支持的精确无记录诊断。若后端不支持持久删除，标记 BLOCKED 并报告具体证据；不重启/重置全局 Docker、不改内部数据库、不全局 prune。
- 容器日志与 Loki/Tempo 持久日志分开。只清理已确认过期测试日志/卷，保留一套可复用日常观测数据。
- 禁止 `docker system prune -a --volumes`、全局 volume/cache prune、Docker Desktop 重置或清理其他项目资源。
- 删除前后记录准确 ID、引用、命令、退出码、后验状态、逻辑容量和物理容量可验证性。APFS/共享层无法验证物理回收时写 `NOT_VERIFIED`。

### 3.3 永久资源治理

更新 `docs/development/resource-lifecycle.md`、`AGENTS.md`、`PLANS.md`，以及必要的 `scripts/maintenance/inspect-resources.ps1`、`cleanup-resources.ps1` 和测试。资源在创建时就记录 TaskId/RunId/标签/清单；阶段关闭时清理自身资源；跨任务旧资源做归属盘点，保留一套日常环境，其余经可再生/备份验证后清理。每个 KEEP 必须写具体理由和解除条件，不能笼统标 KEEP/DEFERRED。

清理器默认 DryRun；Apply 要求准确白名单、过期时间、资源指纹和逐项后验。真实 Docker 测试可用隔离 fixture 测试安全边界，但不能用 mock 代替本机真实 before/after。无 socket 权限不得把 Docker 项标 PASS。

## 4. 修复 diff-check 并重验 M1 交付

修复 `docs/evidence/G3-M1-001/SEM/g3-sem-selftest.txt` 的 EOF 多余空行，检查本次所有新增/修改文本文件。保留历史失败记录的事实，但不要把已修复的格式错误继续带进新 Head。重新执行必要工程/前端/后端/真实集成门禁；仅对相关变更执行增量测试，最终稳定 Head 必须有完整同 Head CI。最终 `git diff --check` 必须 exit 0。

## 5. 把效率规则持久化进仓库

更新 `AGENTS.md`、`PLANS.md`、`docs/development/review-package-spec.md`、`docs/development/resource-lifecycle.md`，新增 `docs/development/ai-development-efficiency.md`。规则必须由新 Master、子 Agent 和换机器后的 Codex 从 Git 读取，而非只存在聊天记录。

永久流程：
1. **Preflight-first：**编码前验证锁定工具链、依赖恢复、真实测试入口、容器健康、迁移兼容、OpenAPI/TS 生成和基线测试；基础失败先分类，不与业务开发混做。
2. **先合同后并行：**公共 DTO、错误码、发布事务、资源命名、证据 Schema 先由 Master 冻结并做正反契约测试，再派独立 Worktree。
3. **分层测试：**静态/单测 → 模块真实集成 → 纵向 E2E → 完整验收。廉价门禁失败时不运行昂贵整栈；增量变更只运行受影响门禁，最终稳定 Head 才跑完整门禁。
4. **持续集成：**每个可运行纵向切片审查后尽早集成；不能把首次真实集成拖到最后。共享契约 Single Writer。
5. **证据分层：**每次失败保留短摘要、命令、exit、关键日志窗口和复现入口；过程截图/全量遥测进入本地归档，不自动复制进正式 ZIP。最终只留稳定代表截图和索引。
6. **交付冻结顺序：**修源码/格式 → 测试 → 独立 Review → 提交 → 同 Head CI → 构包 → 独立重开校验 → 交付回执。包验证失败不能触发无关业务重做或伪造 PASS。
7. **真实效率数据：**记录开始/结束、实现/等待/环境/测试/CI/返工/封包时间；无法取得写 `UNKNOWN`。区分墙钟跨度与活跃工时。
8. **阶段资源收尾：**每任务结束核对分支、Worktree、Docker 容器/卷/镜像/history、ignored 临时文件和 ZIP；本任务资源优先清理，历史资源分类处理。每个保留对象有具体理由与解除条件。
9. **防跨会话丢规则：**新 Master 开始必须读授权、交接、资源清单、构包合同和效率规则，并从最新 `origin/main` 恢复基线。规则写在根 `AGENTS.md`、`PLANS.md`、正式合同、工具和 CI，不只写聊天。
10. **不以速度换安全：**不跳过真实数据库/权限/回滚测试，不把 Mock 当真实集成，不用强推、全局 prune 或未知数据删除。

## 6. 验收、交付与停止

必须满足：
- 默认 Review ZIP 已切换为 V3 compact；V1/V2 仍可验证，历史包原字节不变。
- 53 PNG / 55,256 ignored paths 的合成 fixture 验证体积与聚合策略，索引准确可恢复。
- `git diff --check` exit 0。
- Docker 真实 before/after 证明重复 Fuseki 构建来源已统一，过期 build history 与无引用镜像已按准确 ID 处理；旧卷逐项给出删除/保留依据。若某项不可安全删除，给出具体阻断事实与解除条件，不能全类 DEFERRED。
- 若 Build history 无法证明持久删除，明确 PARTIAL/BLOCKED，不得声称清理成功；继续执行其他安全清理。
- 永久规则已入 Git，并有自动化测试/CI 防止复发。
- 同 Head GitHub CI 的 `engineering`、`governance-integration` 成功；唯一 Review ZIP 独立重开，散列、Base/Head/diff/CI 校验通过。
- Review ZIP 目标 ≤10 MiB；超出时按类别给出精确体积和例外，不得静默放宽。
- 交付报告分别列 `PASS / PARTIAL / BLOCKED / NOT_RUN / NOT_VERIFIED`，区分逻辑容量和物理容量。

最终只交付一个 Review ZIP，附大小、SHA-256、Base/Head、CI URL、实际 Docker before/after、回归结果和未解决事项。输出 `G3_M1_CLOSEOUT_READY_FOR_REVIEW` 后停止；不得启动 M2。
