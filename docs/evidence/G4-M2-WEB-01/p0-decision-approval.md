# G4-M2-WEB-01｜P0 最小合同裁决与原任务继续执行指令

**任务身份**：`G4-M2-WEB-01`  
**审查状态**：`APPROVED_WITH_CONDITIONS_FOR_SCOPE_EXTENSION`（仅新增 Web API Key 凭据用途，不代表 P0、产品或主线验收通过）  
**已审 Base**：`b3b68500d76ab5965fcc540afb883ca605cb15dd`  
**当前任务 Head**：`38a889a8004663120291c8bac34f7b30dc0b45c5`（开始写入前重新核实）  
**已有 P0 BLOCKED ZIP**：SHA-256 `fb42f650b5e51f8dad15b2c3a1f65b0239a79a86c90074beb9e734d3139fc73a`（保持原样；仅作为历史阻断证据）。  
**本文件用途**：附加到**原 Codex Master 会话**，在现有 Worktree/分支继续。不新建 M2 会话或 Worktree，不重写 M1 或 G4-ENG 历史，不合并 main。

## 1. 技术裁决——只批准以下公共行为增量

1. 在现有 `ConnectionSecretIntakeRequest.Purpose` **字符串值域**中新增准确用途 `WEB_API_KEY`；原 `POSTGRESQL_READONLY` 完全保持。仅此用途扩展是本次批准的公共合同变化。**不变更 DTO 字段、类型判别、16 个路由、权限集合、已有错误码语义和数据库模式。**
2. 当前 Web API 产品运行切片**仅启用 `Authentication=API_KEY_REF` 且 `Method=GET`、固定服务端预登记 Operation、固定 HTTPS Origin / 路径以及 `Pagination=NONE`**。现有 `NONE`、`OAUTH_CLIENT_CREDENTIALS_REF`、其他分页模式仍可按既有公开 DTO 解析供预览，但在运行/绑定凭据/网络请求前拒绝进入未实现流程；不能错误变成 `ACTIVE`、`TEST_OK` 或假空目录。
3. **明确暂缓 `NONE` 无凭据持久语义**：不引入虚构 SecretRef、PG 占位凭据、sentinel SecretId、nullable 数据库字段或新迁移；不要为了本切片修改 `ConnectionDraftProbeRequest.SecretRef`。未来需要 NONE 时另行设计 `SecretId/Version`、Probe、Enable、Worker、Rotate、状态与迁移兼容合同。
4. API Key 的 Header **名称和注入格式**只能由**服务器可信 Operation 注册**提供，客户端不能配置任意 Header、URL、query、HostPolicy 或认证格式。`HostPolicyRef` 只是索引；服务端需核对该引用对应的精确 origin、路径、operation、可连接 IP 与当前授权范围，绝不能仅信客户端提交的相同字符串。
5. 首切片仅允许单一已登记合成来源与操作（或与同等严格、可审查的精确批准清单一一对应）；**禁止复用该 Key 发往另一个来源/操作**。如果配置的 Origin/Operation/HostPolicyRef 发生变化，必须在发出新的源请求前强制重新绑定相应授权与新凭据；无法证明则拒绝相关操作，不能拿旧密钥探测新目标。

## 2. 必须覆盖的凭据闭环（不是仅在校验中增加一个字符串）

Master 先准确冻结 owned_paths；本次允许在已有窄任务范围以外，**追加** `backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionRules.cs` 的准确用途校验变更（公共合同行为），以及相关 Connections 应用逻辑、当前 Connections UI intake 和针对性合同/权限测试。**不授予其他 Contracts 文件、数据库迁移、共享依赖/锁、权限或生产安全策略改写权。**

- Intake：只允许 `POSTGRESQL_READONLY` 或 `WEB_API_KEY`；未知用途拒绝；入站 secret 继续固定长度和严格范围校验，密文与明文不得进入普通日志/回执。
- 绑定：`UnboundSecretAsync` 等统一按**服务端从类型化配置确定的预期用途**，核验 Owner、Organization/Sites、未使用、未过期、连接类型、配置目标、事务锁与一次性消费；Web key 不能用作 PG，PG 密钥不能用作 Web，其他连接类型不能借用 Web key。
- 幂等重放：当前 `ReplayAsync` 针对 Secret Intake receipt 再次调用 `UnboundSecretAsync`，必须同步适配到正确的凭据用途和原始请求身份。验证相同命令重复不重新签发、不扩大可读范围，payload/用途变化触发原有冲突/拒绝，不将已消费/过期引用重新激活。
- Draft Test、Create、已保存 Test、Enable、Discover Worker、Rotate、Edit、Disable、取消及审计均须校验用途。每条路径应有实测正例与跨用途/跨scope/过期/重复消费/旧版本反例；失效旧 Probe 和 CAS/Fence 语义保持。
- Web key 只允许注入**实际服务器批准且 TLS 校验通过**的请求；不把 key 出现在重定向、代理、取消/故障日志、审计、HTTP 回执、配置视图或目录快照中。既有 PG 的有效回归不受影响。
- `NONE/OAuth` 等未实现模式在 API 及 UI 表现为明确不可执行，不隐藏地使用 API_KEY_REF 代替，不破坏原公开配置的反序列化兼容。
- 如果仅靠现有字段无法安全实现目标/key 绑定，**停止该点并提交具体差异**，不要自行扩数据库、DTO 或认证能力。

## 3. 独立闭合 P0 的环境和消费者阻断

本次公共合同裁决**不等于 P0 已经通过**。继续原批准的工程适配范围，须先完成：

1. 新运行前重新核实远端 main（必须仍是获批 Base）与当前任务远端/本地 Head、旧阻断 ZIP 身份、干净工作树以及所有已核验缓存的归属。
2. 原 `prepare` 失败是旧 Web 缓存路径 `/Users/chasen/.codex/worktrees/g3-m5-review-fix/ontology-platform/package.json` 不存在；不要继续依赖、补造该路径或仅字符串替换来宣称通过。先枚举本机已有合法候选来源（如前任务 `g4-eng-workflow-001`、`g4-eng-workflow-env`），按当前平台锁、工具身份、完整内容 hash、pnpm workspace/shim 和绝对路径核验，建立任务私有且受控的绑定。**零新下载、零隐式安装、零全局设置修改**。
3. 执行两次同条件 `workflow.py prepare --task G4-M2-WEB-01`；首次仅必要的离线准备，第二次下载、物化和无理由 restore 必须为 0；前后依赖身份一致。缺源继续 `ENVIRONMENT_BLOCKED`，不变更零下载限制。
4. 在现行 TaskId 专用 workflow 适配器中验证真正的 M2 消费者、短烟测入口及失败返回。不得把历史 G3 的 M2、M1 入口或未实现的产品消费者称作 PASS。`host_continuity.py`/`execution_preflight.py` 已有公共 CLI 不得未经授权扩大通用行为；如新 TaskId 必需精确旧 CLI 修改，先提供最小差异审批，而不是偷偷调整。
5. 只有上述条件满足，才允许启动合成 TLS/DNS/socket 设施。保持现有资源上限、任务专属 CA、固定白名单、无系统信任根变更。源 fixture 必须证明真实 HTTP、TLS SNI/证书、所有 DNS 地址和实际 socket 绑定；此处不因为 API Key 合同通过而豁免 SSRF 门禁。

## 4. 后续实施与验收——遵循刚落地的效率政策

- 先冻结最小公共 PG/Web dispatcher + 精确合同正反测试，请非作者 Reviewer 先审公共边界，再实现 Web Adapter；不要另外实现 Oracle、Doris、TDengine，也不建设通用插件框架。
- 真实网络必须按既有任务合同执行：HTTPS GET only，禁自动重定向、禁代理/Cookie、固定注册 Operation，DNS 全地址筛查、IP 地址绑定、IPv4-mapped IPv6、回环/私网/metadata 拒绝。测试中的精确 synthetic 网络例外不转入产品通用策略；证书/SNI 必须与原 hostname 一致。HTTP 3xx 首跳即拒绝，不跟随。参考 .NET `SocketsHttpHandler.ConnectCallback` 和 `AllowAutoRedirect` 官方文档。
- 完成实际 Create(DRAFT)→Test/Probe→显式 Enable→Discover→Disable，以及 Secret rotate/scope/edit、真实取消与后续源 IO 停止、OIDC/CSRF、当前 Web UI 真实端到端。不存在的能力仍明确拒绝。
- 使用 `workflow.py plan/verify` **按影响验收**。本次触及 Secret 公共合同，必须新执行相关 PG 交叉用途、授权/审计、Web 认证与安全测试；其他输入未变、有效来源能重核的项目允许标 `REUSED`，注明旧 T/Run/证据 SHA，不伪称 FRESH。对未映射输入一律不默许 PASS。
- 环境准备/测试失败首先短复现；无新假设不得整链重跑。活跃任务复用经过 hash 验证的缓存，结束时准确回收自身资源。保留历史 BLOCKED ZIP 原字节，不为每次普通修复新建 PARTIAL ZIP；真正完成后生成最终 Head 的唯一新 V3，独立重开及包外回执。
- 新范围内普通代码/格式/任务测试迭代可连续完成，不再每一修复单独审批。超出已批准的公开 DTO/数据库语义、依赖/费用、非合成网络、权限、新源或其他产品阶段才暂停申请。
- 交付前非作者独立 Review；所有适用硬门禁通过且资源证据闭合才可标 `G4_M2_WEB_01_READY_FOR_CHATGPT_REVIEW`；否则准确 `BLOCKED_WITH_WITNESS` 并报告未运行项。

## 5. 不变的权限边界

- **不更新 main**、不开发其他三类 Adapter、不进入 M3/G6；不触碰 G4-M1 冻结 ZIP 与历史记录。
- 既有 .NET/Node/pnpm 已锁身份与 Mac ARM64 准入不自动推广至其他平台/新 SDK。
- CI、Windows、Intel 若未运行，始终报告 `NOT_RUN`；供应链未实测不得报告 PASS。
- `AGENTS.md`、现行授权、生命周期和安全约束继续生效，本补充文件仅覆盖上面清晰列明的 Web 凭据用途扩展及切片缩小。

## 6. 给 Master 的最终指示

在**现有 Codex Master 会话、原 Worktree**执行。先读本审批，准确更新任务卡与任务当前授权；如果远端、文件身份或批准范围不一致，停止并保留见证。完成 P0 闭合后继续实施，不需要再为普通修复申请许可。**该指令不授权向任何真实外部 Web API 发送请求**。

交付时附一个简短的“新范围与旧范围对照”，标明 `WEB_API_KEY`、`API_KEY_REF-only`、`NONE deferred`、`OAuth deferred`、`pagination deferred` 以及所有相关负例的证据指针。

---

参考官方 API：
- https://learn.microsoft.com/en-us/dotnet/api/system.net.http.socketshttphandler.connectcallback?view=net-10.0
- https://learn.microsoft.com/en-us/dotnet/api/system.net.http.httpclienthandler.allowautoredirect?view=net-10.0
- https://learn.microsoft.com/en-us/dotnet/api/system.net.http.socketshttphandler.useproxy?view=net-10.0
