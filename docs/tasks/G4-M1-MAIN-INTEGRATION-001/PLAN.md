G4_M1_MAIN_INTEGRATION_PLAN_READY_FOR_CHATGPT_REVIEW

```text
PlanOnly: true
Observed origin/main: NOT_VERIFIED（当前远端查询失败）
Local origin/main: d1a61daffe844475b07705797e3ad325cc3f2945
CandidateSourceHead: 99753df6f03b184e40b431a5b5aba89d8fa67087
VR11: VERIFIED（仅历史包外交付）
CurrentRemoteRefBinding: NOT_VERIFIED
P0: BLOCKED_WITH_WITNESS
Actual merge/push main: NOT_AUTHORIZED_NOT_EXECUTED
Actual M2: NOT_AUTHORIZED_NOT_EXECUTED
```

# G4-M1-MAIN-INTEGRATION-001 主线集成计划

本回答为 `PLAN.md` 正文；本轮未写入文件。阶段 B 获批后，保存到专用工作树的 `docs/tasks/G4-M1-MAIN-INTEGRATION-001/PLAN.md`。

目标是保留已审 G4-00、M1 和工程恢复提交链，在新任务身份下完成候选适配、真实回归和独立交付，然后另行申请 main 更新。用户已选定：**任务专用适配；Mac ARM64 本地完整验收为合并硬门禁。**

## 1. P0：已核实输入、提交资格与当前阻断

### Git 与交付事实

| 项目 | 本轮只读核实结果 |
|---|---|
| 本地 main / origin/main | `d1a61daffe844475b07705797e3ad325cc3f2945` |
| 候选源 Head | `99753df6f03b184e40b431a5b5aba89d8fa67087`，候选工作树干净 |
| 当前远端 | 普通查询 DNS 失败；扩大沙箱权限后的只读查询 TLS 失败，均 exit 128；`REMOTE_NOT_VERIFIED` |
| 提交数量 | 实测 47；线性单父链，分组为 3＋12＋22＋8＋2 |
| 本地祖先关系 | main→候选、`d40e6ab…`→候选均 exit 0 |
| POSTREVIEW 侧枝 | `7f526e10e9b4044f85dcb7fdb332b9103c148508` 不是候选祖先；共同祖先为 `d40e6ab…` |
| 对象检查 | `git fsck --connectivity-only --no-dangling <候选>` exit 0；这项仅证明连接完整性 |
| 两层格式检查 | main→候选、`d40e6ab…`→候选的 `git diff --check` 均 exit 0 |
| main→候选差异 | 628 个文件，569,010 行增加、19 行删除；包含大量历史证据 |
| 工程恢复增量 | 40 个路径；仅两个验证脚本及任务文档/证据，未新增业务、合同、锁文件或迁移变化 |
| 主工作树 | 六个未跟踪 `.DS_Store` 保持原状，不清理 |

当前远端不可核实，因此只能确认**本地拓扑允许快进**，不能确认当前远端 main 仍符合快进前提。阶段 B 启动前必须恢复远端核验；若 main 前进、候选分支变化或来源不符，提交差异见证并重新审批，不自动调整基线。

### VR-11 历史包外交付复核

已读取并核验原任务的 `/Users/chasen/.codex/worktrees/g4-m1-verify-recovery-001/ontology-platform/artifacts/g4-m1-verify-recovery-001/final-receipt.json`、独立重开记录及原 ZIP：

- 回执 SHA-256：`0cf01e22a457a69834a323d76e2660f7fafb3908c0552d2e8160f0842fdc7e35`，与旁置校验文件一致。
- ZIP SHA-256：`faf807f07550b949136e80c41d0012e556a081dce99adbf845212649c8b51c93`；2,852,778 字节、830 成员、CRC 完整。
- 本轮重新计算 829 项成员散列，逐项核对 827 项归档内容与候选 Git blob，全部一致。
- 回执引用的 49 份包外产物，字节数和 SHA-256 全部一致。
- 原非作者 Reviewer 的 `VerifyOnly` 原始记录为 exit 0，重开前后 ZIP SHA 相同；原始 stdout 确认完整成员集、源 blob、Head 和完整差异检查通过。
- 历史最终远端回读记录绑定 main=`d1a61da…`、任务分支=`99753df…`，证明该记录时点的远端可见性；**不证明当前远端未变化**。
- ZIP 内原来的 11 PASS／1 NOT_RUN 保持原字节，包外回执后置闭合 VR-11 至 12 PASS。本轮未改写任何旧矩阵或 ZIP。

结论：`HistoricalDelivery=VERIFIED`；`CurrentRemoteRefBinding=NOT_VERIFIED`。P0 总体仍阻断。

### 47 项提交清单与资格映射

以下顺序已经核对真实 SHA、父关系及变更清单。**每行的唯一父提交是上一行；第 01 行父提交为上述本地 main。**

| 编号 | 完整 SHA | 任务组 |
|---|---|---|
| 01 | `7132c51203939d9b47de047d5c187f339910ba26` | A |
| 02 | `a919d624ef85fdc5c1ff75c404052ec427296295` | A |
| 03 | `8afc5d4dfd32e7adb48262cce6587057c0e68715` | A |
| 04 | `ceadd5393a377e537539c29d144ddd59ce51d103` | B |
| 05 | `719aaca36ca6988f28e7daf71725f92684ae7e87` | B |
| 06 | `18cd1f7b89286af354f844c8f4b253fcc659f517` | B |
| 07 | `1dbf66ae1114c83fe4894f51c46496f4654a1f2d` | B |
| 08 | `de9bbe5f2b273eb3c404cdce445c5e225032f2d4` | B |
| 09 | `79610f79c0b4e710e8c6e25097e94b4b7504f654` | B |
| 10 | `607b7d1ae780ba52ba74be4940f012497e6211f4` | B |
| 11 | `2c2b2804d3c39e5973d7151a0c305d9c60c90d0f` | B |
| 12 | `f31767117a9b99879c973a1f6be31ed6697396ae` | B |
| 13 | `ee6fb15942ed849845c8a9e8d8524d22fb64086c` | B |
| 14 | `958dc6c4eb121958ae889213d1a523a7e7914ce8` | B |
| 15 | `59edb405dfb4acf4d4a259cffdc3551bafa90d2c` | B |
| 16 | `840155b9ca707ecb8208c6ee57dead14b014a03d` | C |
| 17 | `cb40815090bce36ce982b6365f50c4346776a568` | C |
| 18 | `7527ae6bccb6f6869f4a85ac867d1feb26ec117f` | C |
| 19 | `605acc98d98b9cbddae0d0ffd9227f764deea0ac` | C |
| 20 | `37a65f9aad5247373b86c9f842d4c61fe38bc734` | C |
| 21 | `6ceb0de58aea9630c82c86afdd75022e6629adaf` | C |
| 22 | `cdf9e0ce63c5a784f1473b7de0117ae07f4d912b` | C |
| 23 | `3e3d5bf6d2aff80f8ec6dddfcca088ff659baf62` | C |
| 24 | `ee10927ff27a714733d3059a9f449c0703098daf` | C |
| 25 | `1fb6982ecbad4822062d0a9e56725c249dcd6ac4` | C |
| 26 | `1c9779ec8cadc71c931a89c9c5deb1369b5dc180` | C |
| 27 | `f34a5597c6857090662288bf8711a9ef95085987` | C |
| 28 | `188e2b51adcdc161be7687788e7e86019d248c7e` | C |
| 29 | `35631fef44a936cd31709a5974966f876d611bb3` | C |
| 30 | `5703f4600b8047411d41ec758636cd546b0d811e` | C |
| 31 | `b70b142c5b002c1033e47af1580b4802ba1a3845` | C |
| 32 | `d0cf54ed6d42aef6cedb266a55fcaa31f55268f5` | C |
| 33 | `9b9b39e58c2cbd968935c137e412bc2ec2ffa9f0` | C |
| 34 | `47663df81f7b59c97a5dc2ae022b31f36cd237ad` | C |
| 35 | `d7f3208893edc05a336d5d6ca3d5d9df9192be51` | C |
| 36 | `4efbeca1cbf33d52c2bd950e1968db20abe322d5` | C |
| 37 | `1399364ad1367f3d1bfdee4d9901fdb33b48c15d` | C |
| 38 | `fbe822f2a43170fb34a4542880673ac7c2d2cc54` | D |
| 39 | `e9c51d75b19e75276a7517a721e1e45cc30fb8be` | D |
| 40 | `48d53eee02eb3c545593b35dfca673b222c42eda` | D |
| 41 | `954a2b8e8eab6bc709139eda4921633e5931958c` | D |
| 42 | `48be53e807cab22622ea31c6b39d6cb8805e9771` | D |
| 43 | `53c34a28ba3c6b0a2050219038412a42e59ddc9b` | D |
| 44 | `7da6363d1a891cba11318f9c9bd883033e65f1cb` | D |
| 45 | `d40e6ab67360cc46aadd7ec013bd514b3f61a6ea` | D |
| 46 | `279f9230225ddcea7baf9840b66fb3b6875c4a28` | E |
| 47 | `99753df6f03b184e40b431a5b5aba89d8fa67087` | E |

每项通过任务组关联授权、审查及本轮修复影响：

| 组 | 任务来源与已有审查 | 资格及当前影响 |
|---|---|---|
| A | G4-00-CONTRACT-001；`review-receipt.json` | 合同/设计审查；不代表产品运行通过 |
| B | G4-M1-CONNECTION-001；`p1-review.md`、`independent-component-review.md` | 原合同、PG、UI、应用服务批量审查；当时真实环境缺口保留 |
| C | G4-M1-RECOVERY-001；`r5-independent-review.md` | 真实恢复与安全验收；该任务终态原有 C08/R04 阻断 |
| D | G4-M1-FINAL-GATES-001；F0、C08、R04及最终独立审查 | 后续按范围闭合上述产品阻断；旧 49 项仍为历史验收 |
| E | G4-M1-VERIFY-RECOVERY-001；负例及最终独立审查 | 46 仅修精确历史 JSONL 验证及测试；47 绑定证据。旧 R09 工程阻断已解除 |

前 45 项与侧枝旧清单逐项一致；本轮不继承旧清单中已经过时的 R09 阻断结论。历史审查是任务终态的批量审查，不能表述为 47 个中间提交分别获得产品 PASS。

POSTREVIEW 仅引用研究材料，不 merge/cherry-pick。其他 UI、PG、恢复分支也不追加导入；候选祖先链是唯一产品来源。

## 2. 阶段 B：候选实现边界、所有权和输入绑定

**建议有条件批准 B；不建议在当前 P0 阻断下立即启动。** 批准对象须同时覆盖专用适配工具、必要测试白名单、新任务资源及镜像风险接受，不包含 main 更新。

### 工作树与责任

- 从精确 `99753df6f03b184e40b431a5b5aba89d8fa67087` 创建独立托管工作树，分支固定为 `codex/g4-m1-main-integration-001`；托管系统返回的绝对路径记为 `W`，创建后立即冻结。
- Master 是本轮唯一作者和公共输入所有者；Reviewer 为非作者，只读。
- 本轮没有产品功能写入项，不另派产品 Worker。若后续另批产品修复，再冻结独立 owned_paths 和独立工作树。
- 原主树、旧 G3/G4/G6 树、旧 ZIP、原始证据及私有恢复材料全部保护。

### 精确候选 owned_paths

以下均以 `W` 为根，不授权目录外修改：

| 类别 | 允许路径 |
|---|---|
| 任务与交付说明 | `docs/tasks/G4-M1-MAIN-INTEGRATION-001.md`、`docs/tasks/G4-M1-MAIN-INTEGRATION-001/PLAN.md`、`docs/evidence/G4-M1-MAIN-INTEGRATION-001/**` |
| 专用测试入口 | `experiments/g4-m1-main-integration/` 下的 `run.py`、`consumer_check.py`、`host_continuity.py`、`runtime.py`、`pg_fixture.py`、`module-tests.py`、`startup-boundary.py`、`migration-boundary.py`、`contract-check.mjs`、`http.mjs`、`browser.mjs`、`fault.mjs`、`g3-compatibility.mjs`、`readback.py`、`closeout.py`、`tests.py` |
| 精确设施配置 | 同目录 `compose.m1.yaml`、`compose.g3.yaml` |
| main 防竞态工具 | 同目录 `hooks/pre-push`；测试归入 `tests.py` |
| 唯一既有测试改动 | `backend/tests/OntologyPlatform.ConnectionsTests/PgFixtureSecurityTests.cs`：仅增加本任务精确 fixture 身份，保留原两任务及未知身份拒绝 |
| ignored 输出 | 本树 `artifacts/g4-m1-main-integration-001/**`、`artifacts/reviews/**`、本任务私有 runtime/证书目录及登记后的工具副本 |

现有产品 Host、Connections 应用服务、DTO、迁移、生成器、生成产物、共享脚本、CI、锁文件和依赖版本全部只读。发现需要修改时，单独提交位置、影响、负例和授权差异；对应门禁停止。

**公开接口变化：无。** 本计划不增加 REST、DTO、数据库迁移或运行时 SPI；新增接口仅是任务验收 CLI。

### 专用入口合同

统一候选入口如下，**目前不存在，须在 B 中实现并先审查**：

```text
python3 experiments/g4-m1-main-integration/run.py \
  --gate <PREFLIGHT|I01|I02|I03|I04|I05|I06|I07|I08> \
  --run-id <本任务唯一RunId> \
  --expected-head <完整TestedCommit> \
  --resource-manifest <已审批清单绝对路径>
```

TaskId 固定为 `G4-M1-MAIN-INTEGRATION-001`。入口检查实际 cwd、HEAD、构建散列、资源清单和全部消费者；不接受旧任务身份或任意 TaskId。

正反测试覆盖底层实际生成的 Compose project、labels、卷、私有目录、证据路径、HTTP/browser/fault 身份，不能只改包装器参数。旧工具仅作为可追溯实现参考，不调用其带旧身份或隐式下载的 `main()`。

### 提交与测试绑定

1. 完成适配、格式检查和廉价正反测试，独立 Review 后提交，形成稳定 `TestedCommit=T`。
2. 在 T 上运行完整 SelfTest、原生检查及全部真实门禁；记录源码、驱动、配置、工具和构建输出散列。
3. 任何源码、测试驱动、运行配置或锁输入变化，产生新的 T，重新完成适用增量检查及稳定输入完整验收。
4. 最终 `IntegrationHead=H` 只允许在 T 后增加 V3 合同允许的说明/证据；脚本即使放在证据目录，也必须额外绑定其实际执行字节，不能借目录豁免复用结果。
5. 任务分支可按获批 B 范围提交、普通 push；当前候选 CI 仅 `workflow_dispatch`，发布前仍复查触发条件，不自动触发 Actions。

## 3. I01–I08：实际执行顺序与验收设计

所有下列产品实测在本轮均为 **NOT_RUN**。

执行顺序固定为：

**P0及资源准入 → 专用适配正反测试/Review → 冻结 T → I01 → I05 → I03 拒绝路径 → I02 → I04及I03正例 → I06 → I07 → I08。**

各运行组串行切换。启动新组前完成上一组精确资源回收检查，避免叠加超预算。

| Gate | 实际入口与设施 | 正反验收及停止条件 |
|---|---|---|
| **I01 工程与原生** | 既有 `verify.ps1 -SelfTest`、`verify.ps1 -RunNative -RunTests`；Mac ARM64 精确工具和锁定本地缓存 | 完整原 27 套及新增任务测试；.NET build/test、format verify-no-changes；Web lint/typecheck/test/build。零测试、缺工具、隐式下载、未解释 skip/inconclusive 阻断。需要 fixture 的测试由后续真实组逐项补闭，不能单凭 exit 0 提前标 I01 PASS |
| **I02 G4关闭兼容** | 新 `module-tests.py`、`g3-compatibility.mjs`；先三服务模块组，再六容器 G3 整栈 | G4 disabled；真实 OIDC/CSRF、SourceBundle 字节、发布 V1→V2→回滚、语义查询、Agent/MCP 权限与预算拒绝、审计重读。模型 OFF。必须真实 workspace smoke 和故障注入。任一旧行为回归停止 |
| **I03 启动边界** | 新 `startup-boundary.py` 调用 I01 绑定的真实 API；每例隔离进程 | Production/Staging＋Enabled 必须因准确 G4 环境拒绝而失败；Disabled 不注册服务、worker/routes，不迁移；Development＋Enabled 才注册。验证配置覆盖优先级、ApplyMigrations、AllowEmptyPublicSchema 缺省/false/true。无关配置失败不能代替预期拒绝 |
| **I04 迁移与隔离** | 新 `migration-boundary.py`；合成平台 PG，真实 Host 初始化 | `connections` schema、专属 EF History；初装、重复、CREATE 权限故障及恢复重试；既有 G3 行/发布/审计重读不变。仅操作平台合成库；源 PG schema/history 不变。禁止 Down。失败保存数据库见证并停止后续产品门禁 |
| **I05 生成链** | 真实 API DLL `--export-g4-openapi`；现有生成器 `--check`；新 `contract-check.mjs` | 实际 OpenAPI→schema/DTO→TS；隔离临时副本实际再生并比较。G1/G2/G3 正式协议、错误和权限语义无漂移。篡改 DTO、required、枚举及客户端的负例必须被拒绝。任何漂移停止，不手改生成结果闭合 |
| **I06 生命周期与安全** | 新 `http.mjs`、`fault.mjs`、`readback.py`；真实 TLS 源 PG、平台 PG、OIDC/API | VerifyFull 正例、坏 CA/SAN、错密码、owner/superuser/继承写角色/跨 schema/跨组织拒绝；SecretRef 用途/轮换/吊销/自然过期；Probe→显式Enable、CAS、幂等、64KiB流式边界；超时、真实取消、lease/fence；审计失败回滚、Catalog一致性及STALE。HTTP状态之外须有源IO/DB重读见证 |
| **I07 UI与恢复** | 新 `browser.mjs`，真实 HTTP/OIDC 浏览器，绑定同一构建 | Create→Probe→Enable→Discover→Edit→Retest→Disable；刷新重入、409、权限拒绝、失败/部分状态、父子操作互锁及窄屏。其他四类保持 `422 connector_not_enabled`。超时暂停须 guard/finally 恢复；取消须真实查询取消证据 |
| **I08 交付与资源** | 两层 diff-check、非作者 Review、专用 closeout、既有 V3/VerifyOnly | 全部硬门禁闭合、输入绑定一致、无开放 P0/P1；精确回收自身安全资源并验证保留集；唯一 V3、独立重开、包外回执。任一缺失不得进入 main 审批状态 |

### 已核实的既有命令与关键限制

以下命令在 B 工作树根执行，由任务入口设置经过核验的进程级工具环境：

```text
python3 scripts/maintenance/execution_preflight.py check --milestone G4-M1 --phase contract
pwsh -NoProfile -File scripts/verify.ps1 -SelfTest
pwsh -NoProfile -File scripts/verify.ps1 -RunNative -RunTests
node apps/web/scripts/generate-types.mjs --check
```

旧 `execution_preflight` 只证明原合同可发现性；必须叠加本任务 consumer check，不能将它解释为新任务完整准入。

现有 `verify-web.ps1` 会调用 bootstrap，缺 Node/pnpm 时可能下载。**先核实工具齐备，再运行；禁止隐式联网补齐。** 不使用 `-SkipWeb` 等参数缩减硬门禁。

I01 固定 Debug 构建；I05 直接使用该构建清单中的 API：

```text
<已核验dotnet绝对路径> \
  backend/src/Hosts/OntologyPlatform.Api/bin/Debug/net10.0/OntologyPlatform.Api.dll \
  --export-g4-openapi <本任务ignored输出绝对路径>
```

DLL、deps、runtimeconfig 和依赖集须与 I01 散列一致。既有 `verify-openapi.py` 只核对 G1，不能冒充 G2/G3/G4 协议覆盖。

I02 不直接运行旧 `semantic-roundtrip.py`、`release-faults.py`、`query-plan.py`、`mcp-agent.py` 或 `g2-integration.ps1`：它们存在旧镜像引用、restore、隐式 pull 或 canonical 构建入口。新 `module-tests.py` 复用其断言设计，使用受控设施运行现有 SemanticTests、PublishingTests、QueryTests、AgentTests 程序集；保留 MCP schema 正负检查，使用已有锁内 Ajv，不安装。

### 证据与失败处理

每项记录 TaskId、RunId、T、实际命令/退出码、工具身份、构建与驱动 hash、实际测试数/skip、设施身份、UTC起止、输入指纹及原始输出散列。沿用 timeline schema2，真实 `exitCode` 与 `timingStatus` 分开。

同输入、构建、平台和错误类别的昂贵失败先短复现；未改变失败条件不得重跑整栈。保留首次失败记录。`NOT_RUN`、`INCONCLUSIVE`、环境阻断不提升为 PASS。

源码已确认存在 Development 限制；本计划验证其真实调用、配置覆盖和运行效果，不将“没有限制”列为缺陷。目前定向调查未确认新的 P0/P1 产品缺陷；这不代表全量安全审查通过。

## 4. 运行资源、依赖与准入清单

### 精确镜像候选

以下仅为本轮只读观察和待批候选，均为 `linux/arm64`。本地存在不代表许可、安全或运行准入通过。

| 镜像 | 精确身份 | 本轮本地观察 |
|---|---|---|
| PostgreSQL 18.6-trixie | `sha256:9a74990a5c776ff210361b67616b347750c66c36ea0dfbb4f575d19fcc3d8437` | inspect 成功；RepoDigests 为空，需补内容映射验证 |
| Keycloak 26.8.1 | `sha256:e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4` | 精确引用 inspect 成功 |
| ASP.NET 10.0.13 | `sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55` | 精确引用 inspect 成功 |
| Node 24.22.1-trixie-slim | `sha256:a52166d89cfcc66ea62d10535ca712d161cece5d77ff4cfa758866b6b75ccb3f` | inspect 成功；RepoDigests 为空，需补内容映射验证 |
| RustFS 1.0.3 | 本地 OCI index：`sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b` | index 引用 inspect 成功；历史 ARM64 子 manifest 为 `sha256:a3951370f879374cb89cca3b495e05badab38807cc4cd609c54a35f93f6ccd64`，该子引用单独 inspect 未找到 |
| canonical Fuseki | `sha256:715703f0cdb98680f3b71ebbfcdea126ec1ddc3f483f4341afde2cc63b1a817c` | canonical tag及摘要 inspect 成功；仍须复核完整构建输入身份 |

RustFS 必须核验 index→ARM64 manifest→config 链；PG/Node 不得仅凭 tag 或 ImageID 宣称官方 manifest 绑定完成。

许可依据为历史 RECOVERY 的 `r3-review.md`、FINAL-GATES 的 `g3-license-review.md` 及对应原始 SBOM/许可证散列。六类历史结论均有 **AMBER-A1／LICENSE_PARTIAL** 限制；完整许可证、CVE、签名等仍 `NOT_VERIFIED`。B 必须重新获得本任务限定的内部合成、非分发风险接受，不继承旧任务准入。

### 待批资源方案

- 最大同时 **6 个任务容器、容器内存上限合计 6GiB、新卷观测停止阈值 3GiB、下载 0、GPU 0、费用 0**。均为提案，当前未获运行许可。
- 模块组：PG＋Fuseki＋RustFS，三容器串行运行各模块测试。
- G3 兼容组：平台 PG、Keycloak、API、Web、Fuseki、RustFS。
- G4 组：平台 PG、源 PG、Keycloak、API、Web；不同时启动 Fuseki/RustFS。
- 浏览器、构建和宿主监测另登记进程、输出目录及占用，不把它们隐藏在“六容器”统计之外。
- 3GiB 是容量观测和停止阈值，不宣称是 Docker 卷硬配额。工具副本、构建和证据占用在复制/构建前盘点；空间未知或不足停止。
- Docker 使用已冻结 context/Engine、`--pull=never`、Compose `pull_policy: never` 和 `--no-build`；不 pull/load、不新建随机 Fuseki 镜像。
- 仅本任务隔离网络、登记的合成地址及 loopback 端口；不挂载旧持久卷、旧私有 runtime 或客户源库。
- 注册项目、TaskId、RunId、准确容器/卷/网络 ID、镜像身份及恢复入口。停机和清理使用精确白名单，不全局 prune/restart。

### 工具和 PyYAML 可复现性

锁定 .NET SDK `10.0.402`、Node `24.22.1`、pnpm `11.28.8`、PyYAML `6.0.3`；EF、浏览器、Ajv 等按现有已锁定制品核验实际身份。

原任务 `.tools/pythonlibs` 已清理。本轮确认共享 PyYAML 源目录仍存在，44 个历史登记文件散列一致。B 采用原先已验证的 **26 文件独立只读副本**流程：核对 RECORD/许可证/逐文件散列，复制到新任务树，禁止链接共享源、禁止修改共享源，使用 `python3 -B` 验证版本与导入位置；结束只清理自身副本。

零下载包括隐式 dotnet restore、pnpm install、Python安装和浏览器下载。仅允许从已核验本地缓存进行锁定恢复；缺失则 `ENVIRONMENT_BLOCKED`，单列下载申请，不自动换源或安装。

Mac 长任务使用本任务 host-continuity 薄适配，复用现有监测实现，准确记录新身份；启动前确认能源策略，有界监测，阶段结束精确释放自身进程。未观测锁屏/熄屏连续性仍如实 `NOT_VERIFIED`。

## 5. I08交付、阶段 C 二次审批与后续边界

### 唯一候选交付

B 的包基线采用重新核实并获批的目标 main SHA，覆盖完整历史链和本任务增量；另保存 `99753df…→H` 增量差异。两层 `diff --check` 均须 exit 0。

按固定顺序完成：源码/格式 → 测试 → 独立 Review → 提交 → 本地输入绑定 → 唯一 V3 → 独立重开 → 包外回执。

使用现有入口：

```text
pwsh -NoProfile -File scripts/new-review-evidence.ps1 \
  -OutputPath <新validation.json> \
  -TaskId G4-M1-MAIN-INTEGRATION-001 -TestedCommit <T>

pwsh -NoProfile -File scripts/test-review-evidence.ps1 \
  -EvidenceFile <validation.json> -ExpectedHead <H>

pwsh -NoProfile -File scripts/create-review-package.ps1 \
  -BaseSha <ApprovedMain> -HeadSha <H> \
  -TaskId G4-M1-MAIN-INTEGRATION-001 \
  -Status PARTIAL -EvidencePath <已提交validation.json> \
  -ValidationSource LOCAL

pwsh -NoProfile -File scripts/create-review-package.ps1 \
  -Root <W> -VerifyOnly -PackagePath <唯一ZIP绝对路径>
```

`PARTIAL` 保留 CI、Windows、Intel及供应链限制，不掩盖任何适用硬门禁失败。截图最多12张、压缩目标3MiB；ZIP超10MiB分类报告，超15MiB阻断。

本任务安全可再生运行资源在审查后实际回收，记录 before-command-exit-after、准确不存在诊断及保留开发环境验证。候选分支、工作树、唯一 ZIP 和审批恢复材料保持 KEEP，解除条件是后续明确集成与生命周期批准。旧 G3/G4/G6 对象不清理。

最终包外回执绑定 T、H、ApprovedMain、ZIP SHA/成员数、独立 VerifyOnly 退出码、资源结论和真实远端任务分支回读。

B 完成后必须停在：

```text
READY_FOR_CHATGPT_MAIN_MERGE_APPROVAL
```

### 阶段 C：精确 main 更新审批

只有 ChatGPT 对新包复审完成，且用户明确批准 **完整 H＋完整 ApprovedMain＋平台/供应链限制**，Master 才能执行 C。Plan 批准、B 批准和 Reviewer PASS 都不代替此审批。

C 前复核顺序：

```text
git ls-remote origin refs/heads/main refs/heads/codex/g4-m1-main-integration-001
git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main
git rev-parse main origin/main
git merge-base --is-ancestor <ApprovedMain> <H>
git diff --check <ApprovedMain> <H>
git diff --check 99753df6f03b184e40b431a5b5aba89d8fa67087 <H>
```

必须满足远端 main、本地 main、origin/main 均等于 ApprovedMain；任务远端等于 H；本地主树只有已登记的六个 `.DS_Store`，无其他变动。任何漂移停止，不自动重放或重审批。

主线采用 `git merge --ff-only <H>` 和普通 push。专用 `pre-push`：

- 只接受一条准确 main 更新，local OID=H、remote OID=ApprovedMain。
- 核对 origin、目标仓库和 `refs/heads/main`；拒绝空输入、零OID、删除、额外 refs。
- 用本地隔离 bare fixture 验证通告前和通告后的并发更新拒绝。
- C 前重查既有 hooks，不静默覆盖或绕过。

拟推送形式：

```text
git -c core.hooksPath=<已审任务hooks绝对路径> \
  push origin <H>:refs/heads/main
```

不使用 force、force-with-lease、`+refspec` 或 `--no-verify`。服务器对通告旧OID进行原子更新；拒绝后停止，不自动重试不同基线。

推送后重新查询远端 main=H，核对本地 main、候选、差异和包回执。若本地已快进而远端拒绝，明确记录两端状态，保留现场，不 reset。

### 故障恢复和未运行平台

- 入 main 前失败：main 保持不变，保留分支与见证，仅回收本任务可安全回收资源。
- 入 main 后发现问题：保持 G4 默认关闭；启用环境中先停 G4 调度并保留 Connections 数据/审计。前向 revert、修复或数据恢复须另行审查批准，不强推、不重写历史、不直接 Down。
- Mac ARM64 原生构建与适用真实整栈为硬门禁。CI、Windows、Intel 未运行保持 `NOT_RUN`，最终 C 审批明确接受限制；本地成功不替代这些平台结果。

### 当前决定与 M2 边界

当前建议：**提交本计划供 ChatGPT 审查，暂不启动 B。** 可继续只读工作；B 前须闭合当前远端、工具可复现性、镜像身份映射，并批准本任务资源和 AMBER-A1 限定准入。

M2 仅保留依赖顺序：

**M1 main资格与明确集成决定 → M2-P0版本/许可/资源准入 → M2-C公共SPI及正反合同审查 → 单独批准的M2-WEB-01受控GET。**

本次不实施 Oracle、Doris、TDengine、Web Adapter，不安装驱动，不新增 MappingRelease/MCP，不调用付费模型，不进入 G6，不冻结候选 ADR、DTO 或镜像。非 PG 四类型继续保持 `connector_not_enabled`。

下一审查入口为本计划、上列精确候选源、VR-11历史复核及当前阻断见证；实际阶段 B 的授权与最终阶段 C 的授权分别作出。


## 2026-11-02 执行审批增量（保留上文历史原文）

P0_AUTHORIZED / B_CONDITIONAL / C_NOT_AUTHORIZED / M2_NOT_AUTHORIZED。最新审批原文为本目录approval-original.md，约束见approval-constraints.json。

本轮真实远端refs已匹配，默认TLS验证成功；当前结果取remote-and-tls.json。镜像及工具完整P0仍待逐项闭合，B未启动。Mac ARM64本地完整验收为硬门禁，CI/Windows/Intel保持NOT_RUN。镜像准入须列本地ID、归档官方来源或构建来源、架构manifest链及许可风险处置；任何剩余未知不提升为PASS。阶段B仅限任务候选，C的ff/main push均未授权。

## B 执行状态补记（2026-11-03 Asia/Shanghai）

P0 已真实核验通过限定准入，历史阻断描述保留。本计划归档将唯一绝对 Markdown 链接改为代码路径；完整原始字节与审批文档保存在本任务 p0/original-documents.json 的 base64 字段，原始 SHA 不变。

B 在廉价原生格式检查发现继承输入的 275 项错误（274 WHITESPACE / 1 CHARSET，15 个文件）后停止。I01 BLOCKED，I02–I07 NOT_RUN，I08 仅进行阻断部分交付；不进入主线审批就绪。精确补丁仅在 ignored 独立副本生成供审阅，未应用到产品。
