# Codex Master 执行指令｜G4-M2-WEB-01 单 Adapter 薄切片

> 版本：2026-11-07 · 状态：**候选授权文本**。仅当用户在 Codex 会话中明确批准本文件及其范围后执行。此文件本身不证明已获授权。
>
> 唯一目标：在已合并的 G4-M1 上，交付 **Web API 受控 HTTPS GET 连接器**的最小真实闭环，并用新落地的按影响验收流程完成一次可审查交付。不同时开发其余三类 Adapter。

## 0. 基线、仓库规则与不可变边界

- 仓库：`on-dotnet/ontology-platform`；批准的起始 `origin/main`：`b3b68500d76ab5965fcc540afb883ca605cb15dd`。首次先真实 `fetch/ls-remote` 并核对；漂移则记录差异并停止源码写入，禁止自动重基、强推或猜测新版合同。
- 新任务：`G4-M2-WEB-01`。新建 **一个**独立托管 Worktree 和任务分支 `codex/g4-m2-web-01`；不从遗留 M1、G4-ENG 或 G6 工作树继续写；不更改 `main`。保护旧树、现有活跃引用、冻结 ZIP/日志、用户未跟踪文件。
- 优先遵守 `AGENTS.md`、`docs/development/ai-development-efficiency.md`、`docs/development/local-validation-policy.md`、`docs/development/verification-gates.json`、`docs/development/resource-lifecycle.md`、`docs/development/review-package-spec.md` 和 `docs/tasks/current-authorization.md`。本任务获用户明确授权后，把新的授权追加为现行任务段，历史授权只归历史，不改旧证据。
- G4-M1 的 PostgreSQL Create/Probe/Enable/Discover/Disable、G2/G3、权限/审计、数据库迁移与 UI 已冻结行为不可回归。其他三类 Oracle、Doris、TDengine 仍返回 `connector_not_enabled`。不进入 G4-M3/M4/M5 或 G5/G6，不实现新的 MCP、Mapping、远程 OpenAPI 文档抓取或真实业务数据查询。

## 1. 启动方式：一页清单，然后在批准范围内持续实施

在执行模式一次性输出**一页以内**的 P0/实现/验收清单，立即开展 **只读 P0**。P0 核验当前 main、Worktree、当前项目真实 DTO/SPI/16 路由、可用测试/工具、资源/许可、Mac ARM64 与现有依赖闭包；所有要求报告为 `READY`、`BLOCKED` 或 `NOT_APPLICABLE`，无推定通过。核对官方 .NET 10 HTTP/TLS API 文档与本地锁定运行时。

P0 闭合后在本文件已授权边界内**继续实施，无需反复申请每个格式补丁**。如果需要改变公开 wire DTO/枚举、EF 模式/迁移、权限语义、认证形式、依赖或共享环境，**仅停止该越界变更**并提交一个明确决策点；不自行设计和批准。任何真实远端漂移或安全前提缺失也停止相应工作，不靠降低测试要求绕过。

先落实任务入口与最小真实烟测（OIDC→API→源 HTTPS GET→UI 管理操作／拒绝场景），证明测试消费者、DNS/TLS/构建链接可用，再启动长验收。尚未完成的产品适配器不允许让烟测假 PASS。

## 2. 实现范围（先公共分发，后 WEB；不新建大框架）

### 2.1 公共 Adapter 分发（M2-C，最小增量）

- 读现有 `ConnectionApplicationService`、`IPgSourceAdapter`、`G4Composition`、`G4ConnectionModels/Rules` 和前端五类型配置。**保留现行 16 个 REST 路由、已公开类型化 wire DTO、权限、SecretRef、ETag/CAS、幂等、审计和状态机。**
- 当前真实执行仅支持 `IPgSourceAdapter`。采用最小的 typed dispatcher／能力接口支持 PostgreSQL 与 Web API；不得将 Web 伪装成 Pg 配置，不得引入泛型 Repository 或大型插件框架。
- 先写公共分发的正/负合同测试并请非作者 Reviewer 核对；完成共享合同冻结后再实施 Web Adapter。PG 的现有路径及明确拒绝的类型不变。
- 如果现有 wire 无法表达安全的 Web GET 配置，应提出最小 DTO/ADR 差异及需要的人类决定，**不得暗中增字段或修改生成的 TS 客户端**。

### 2.2 Web API 首切片（M2-WEB-01）

- 利用**已存在**的 `WebApiConnectionProfile`：`BaseOrigin`、`OperationId`、`Method`、`ApprovedPath`、`Authentication`、`Pagination`、`HostPolicyRef`。仅启用**服务端预登记且准确匹配**的合成 HTTPS origin、固定 GET operation、固定相对路径/参数和返回数据合同。客户端不能任意提供 URL、Header 模板或远端 schema 引用。`HostPolicyRef` 必须由服务端可信策略解析，不能因客户端填写同名字符串就获得权限。
- 首切片认证只允许 `NONE` 或利用顶层 `SecretRef` 的 `API_KEY_REF`，密钥头名/格式来自服务端 operation 注册且不回显；已有 `OAUTH_CLIENT_CREDENTIALS_REF` 虽可解析，但本切片**显式不支持执行**。禁止任意 Bearer/OAuth、系统代理、Cookie、自动重定向、非 GET 和用户提供自由查询串。没有额外批准不做跨来源授权/真实客户外联。
- SSRF 是**硬门禁**：严格校验 hostname/origin、所有 DNS 解析 IP、IPv4-mapped IPv6、回环/私网/link-local/metadata；连接到经过核验的准确地址且保留原 hostname 的 TLS SNI、证书链及 SAN 校验；连接池/再解析/重连须保证策略仍成立，禁止 DNS rebinding 和代理绕过。测试专用回环/私网例外只能在**精确合成 fixture + 隔离网络 + 明确 TaskId/RunId**中启用，不可成为通用白名单。重定向首跳即拒绝；绝不能依赖默认自动跳转。使用 `.NET 10` 既有 `SocketsHttpHandler.ConnectCallback` 等能力前需验证实际平台行为。
- 执行现有生命周期：Create(DRAFT)→Probe（真实网络/TLS/认证）→明确 Enable→受预算 Discover（真实 HTTPS 响应且明确目录保真）→Disable；配置或 Secret 变化使 Probe 失效，取消应传至 socket/HTTP body/worker；源站在禁用后不再被访问。响应正文/密钥不得进入日志、审计或目录快照；目录只保存经定义的元数据，不臆造字段/精度。
- 预算继承：Probe 10s（network 3s）；Discover 20s、最多 100 对象/2,000 字段/2MiB。对超大/深 JSON、missing/null、精确数字、分页游标循环等使用有界解析。无法安全支持的分页策略本切片明确拒绝，不因现有枚举有 `PAGE/OFFSET/CURSOR/LINK` 就假装全支持。不能将截断、隐藏或取消伪装成 `EMPTY_VERIFIED`。
- 前端优先复用现有 Web API 类型配置和 Connections 页面，仅在实际端到端缺口时做窄改，不重做菜单、Design System、Layout 或其他连接器表单。

### 2.3 允许写入的范围

- `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/{Abstractions,Adapters,Application}/**` 中与 typed dispatcher / Web API 相关的准确文件；相应 `backend/tests/*Connections*` 及必要现有 G4 合同回归测试。
- `backend/src/Hosts/OntologyPlatform.Api/G4/` 内的必要 DI 注册（仅需的准确文件）；`apps/web/` 内 Connection 页面/表单/对应测试的窄变动（确有缺口才写）。
- `docs/tasks/G4-M2-WEB-01*`、`docs/tasks/current-authorization.md`（追加新的现行任务段）、`docs/evidence/G4-M2-WEB-01/**`；若不可避免，`experiments/g4-m2-web-01/**` 中少量任务专属合成 fixtures／测试，优先复用已批准设施。
- 新工作流适配仅限新 TaskId 接入 `scripts/maintenance/workflow*`、`docs/development/verification-gates.json` 和对应定向测试；避免为 M2 又复制整个 M1 验收引擎。
- 以上为上限，不表示每个目录都要修改。Master 对共享配置单写；独立 Reviewer 只读。只有确实可独立写入的适配器与 UI 才考虑并行，不为凑团队人数新开分支。

**禁止未经追加批准写入：** `backend/src/Contracts/**` 的公开 wire 结构或行为、新 EF migrations/数据库 schema、共享锁文件/依赖版本、原 G2/G3/M1 冻结证据、公开 API 路由与权限集合、全局 Git/Docker/OS 配置、其他项目目录。需要调整则提供简短具体差异、兼容/风险、影响门禁，等待明确授权。

## 3. 运行与安全资源预算

- Mac ARM64 本地合成隔离开发环境；既有通过准入的镜像/CLI/包优先复用。零新增 NuGet/NPM/Node/Python/浏览器安装、零镜像下载、零费用、零 GPU；不调用生产地址、模型、Oracle、Doris、TDengine。确需新依赖/镜像/付费资源时停止并申请。
- 单次最多 **6 个任务进程/容器、容器内存上限合计 6 GiB**；源 HTTPS/DNS fixture 最多两个，源内存 <=512 MiB；新增任务数据停止阈值 3 GiB、过程产物 1 GiB（精确清点，非宣称硬配额）。必须先核实宿主内存、磁盘和已有活跃资源占用；不能伤害或清理别的任务。
- 本地证书由任务隔离创建并登记，绝不修改系统信任根或关闭产品 TLS 校验。网络限制为精确许可的合成地址与回环入口。M1、G3、G6 数据卷/网络/Worktree、活跃引用及 Secret 保持保护。
- 原 `G4:Enabled` 的 Development 环境门禁不可放宽，生产、Staging 不自动打开 Web API。敏感地址/代理/证书失败记录安全诊断，不输出秘密原文。

## 4. 按影响验收的真正完成标准

使用新 `workflow.py prepare/plan/verify/package-check/closeout` 做当前任务的准确前置和输入影响规划（不默认将 M1 TaskId 硬编码复用）；登记 FRESH/REUSED/NOT_RUN 和源 T、Run、SHA、环境键。**不因新 commit 或 RunId 强迫重跑所有 G2/G3/M1**；但被共享 SPI、权限、合同、迁移、TLS 或 Adapter 生命周期影响的范围必须新测。

- **最低新测**：共享 PG/Web 分发正反测试；WEB DNS/IP/SSRF/代理/重定向/TLS/认证/预算/取消的定向正反测试；真实合成 HTTPS GET Probe 与 Discover；管理权限与 SecretRef；PG 路径仍正常；另外三类型仍 422；当前 UI 真正 Create→Test→Enable→Discover→Disable 及刷新/拒绝恢复。至少一个真实取消到 socket/worker 的可观察见证。
- **重复准备证明**：同一个环境输入连续两次 prepare，第二次下载/物化/无理由 restore 为 0；换 Worktree 要检查 pnpm 状态路径、MSBuild SDK/平台锁与 Docker 网络命名空间；API 重新构建后 Web 的服务地址/网络实例同步验证。
- **失败止损**：相同输入与失败类型只做短复现，不得反复启动整链；后续若改变局部驱动/测试，只使依赖其的门禁失效。每个产品门禁必须有真实消费者，不能用 Mock/启动容器成功代真实测试。旧产品验收可按精确可重算输入资格复用，不能伪称本轮执行。
- **真实闭环**：必须有实际 OIDC、CSRF、平台 PG（配置/作业/审计）与合成源 HTTPS、真实浏览器操作及安全负例。成功报告给出命令、计数、skip、退出码、证据 SHA 和未验证项。非作者 Reviewer 必须独立确认高风险 HTTP 安全、PG 回归与当前输入绑定；最终候选无开放 P0/P1。
- **证据精简**：任务活跃期间只保存一次原始日志，以 SHA/Git blob 引用，不重复生成多份完整内容或中间 PARTIAL ZIP。单个任务卡、简洁矩阵、唯一 V3、VerifyOnly、包外回执。默认上限 10 MiB（超限分类解释），硬上限 15 MiB（先去重，禁止自行提限）。未运行 CI/Windows/Intel 和供应链缺口诚实记 `NOT_RUN`/`NOT_VERIFIED`。
- 准确资源回收：同任务白名单、实际 before/after、保护活动引用，不全局 prune、不主动重启 Docker；保留需要后续审批的对象并说明原因。最终停在 `G4_M2_WEB_01_READY_FOR_CHATGPT_REVIEW`，不自动合入 main。

## 5. 停止条件与最终交付

- 发现 `main` 漂移、生产网络依赖、公开 DTO/权限/数据库语义变更需求、需要新下载/许可或增加预算、SSRF 漏洞无法证明防护、真实取消失败、测试设施不完整时，**停止受影响的子任务并留最小见证**；不要为了凑 PASS 放宽安全、伪造结果或重复长验收。
- 在允许范围内的普通代码、格式、路径和定向测试修复由 Master 持续完成，不再逐补丁 SHA 申请；仅真正扩大安全/业务/资源边界时另行请求人类决定。
- 交付：①任务卡／当前授权与一页计划；②新源码 `TestedCommit`/`Head`、真实门禁矩阵和 FRESH/REUSED 资格；③Web API 受控 GET 实际闭环和安全拒绝证据；④独立 Reviewer；⑤唯一 Review V3 与 VerifyOnly；⑥包外最终回执和资源收尾。不会更新 main，M2 其余三类继续未启用。

## 6. 参考资料（研究来源，不构成运行授权）

- 已审研究：`docs/evidence/G4-M1-POSTREVIEW-001/g4-m2-authorization-request.md`（历史 POSTREVIEW 分支，只读检索，不 cherry-pick 其 37 项资料）及 `docs/planning/g4-implementation-plan.md`。
- Microsoft .NET 10：
  - https://learn.microsoft.com/en-us/dotnet/api/system.net.http.socketshttphandler.connectcallback?view=net-10.0
  - https://learn.microsoft.com/en-us/dotnet/api/system.net.http.socketshttphandler.allowautoredirect?view=net-10.0
- Codex 官方实践：https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra ——精简常驻规则和提示词；本项目按影响验收以现行仓库规则为准。

**用户操作**：新建 Codex Master 会话，选择本项目；在执行模式附加本文并明确写“批准只执行 G4-M2-WEB-01 单 Web API GET 切片及本文限定资源，遵守所有停止边界；不合 main、不进入其它 Adapter”。这条用户消息才构成任务授权。
