# G4-M1 验收矩阵（真实 PASS 定义、拒绝样本与执行顺序）

此表是**将来运行要求**；当前交付的所有产品测试为 `NOT_RUN`。开发可在P1合同冻结后新增用例ID，但不得删除以下拒绝场景以凑通过。

## A. 合同 / 复用 / 负例 16项

| ID | 必须能观测的断言 |
|---|---|
| M1-C01 | `POST /connections` body唯一 `config:{type,profile}` / top-level secretRef / command，未知字段和旧`connectionProfile/secretInput`拒绝 |
| M1-C02 | `CommandContext` create expectedRevision=0，更新 expectedRevision>=1 + If-Match；null/bool/字符串伪整数拒绝 |
| M1-C03 | 五类型profile精确字段；TD无第二个credentialRef，Web NONE=null；PG本批启用的安全子集明确 |
| M1-C04 | schemaKind/payload仅设计测试包装，真实 HTTP body 无该包装 |
| M1-C05 | G2/G3全部正式接口、SourceBundle、G3 dataTurtle / MCP及已有11字段query未改变 |
| M1-C06 | NuGet版本/License/hash与平台恢复记录；未审依赖阻断而不自动新增 |
| M1-C07 | Frontend 类型来自真实 OpenAPI 生成链，非手写独立DTO漂移 |
| M1-C08 | SourceConfig修改后 configHash/probe失效，SecretVersion改变后probe失效 |
| M1-C09 | Probe/Connection/Catalog状态是不同对象，不写混用枚举 |
| M1-C10 | 六个Policy均服务器执行且resourceScope判断不靠客户端提供ActorContext |
| M1-C11 | 严格安全错误优先级和ProblemDetails，非授权场景不得返回内部host/表名 |
| M1-C12 | Probe/Connection/Job的ID、版本、hash、时间、审计与真实Trace匹配 |
| M1-C13 | G4审计 action只白名单不接受任意字符串 |
| M1-C14 | M1不产生正式MappingRelease、不注册新MCP、不连接外部模型 |
| M1-C15 | No real business rows / no customer production data / Synthetic provenance clear |
| M1-C16 | 新的G4接口OpenAPI与前端运行时调用一致，CLI及文档URL无双定义 |

## B. PostgreSQL / TLS / Secret 14项

| ID | 实际验收 |
|---|---|
| M1-P01 | 启用合成PG TLS VerifyFull，真实连接、证书/hostname verified，返回阶段报告 |
| M1-P02 | 非受信 CA 拒绝，证书身份错误不默默回退 Require/Prefer |
| M1-P03 | 错误密码认证失败，限定重试/敏感诊断脱敏 |
| M1-P04 | 仅TCP连通但没有schema访问时全Probe不是TEST_OK |
| M1-P05 | fixture_reader只允许 production指定表 SELECT，maintenance/otherplant访问拒绝 |
| M1-P06 | 文本拼接SQL、任意函数/CTE写/多语句及非法schema名均无法达到Adapter执行层 |
| M1-P07 | SecretRef跨org、跨actor、过期、重放、不同用途、撤销全部拒绝 |
| M1-P08 | 秘密不出现在GET/响应错误/普通日志/OpenAPI示例/ZIP/Trace/前端localStorage/浏览器URL |
| M1-P09 | Secret版本轮换后旧Probe无效、原pool不能用于下一次旧配置 |
| M1-P10 | 连接创建后只DRAFT，不因probe或保存自动ACTIVE |
| M1-P11 | 同IdempotencyKey异payload 409，响应/持久实体/审计无重复副作用 |
| M1-P12 | Concurrent PATCH/enable/dsiable（错ETag）409，旧状态不被覆盖 |
| M1-P13 | 关闭真实PG源/超时后显示失败或PARTIAL，不能把失败显示为EMPTY |
| M1-P14 | 禁用后新Probe/Discover不能调源；历史读取受当前scope和类型权限限制 |

## C. Catalog、Job、UI、资源 19项

| ID | 实际验收 |
|---|---|
| M1-E01 | schema发现只返回当前源角色和Connection.allowedSchemas下的对象/字段 |
| M1-E02 | 对 numeric(8,2), timestamptz, timestamp, jsonb, array, nullable的native类型保持可辨 |
| M1-E03 | 首次发现生成不可变SchemaSnapshot/fingerprint，重复同内容hash稳定；变更可比较 |
| M1-E04 | 无权schema/字段不列出；零对象权限受限不表示“没有表” |
| M1-E05 | Discovery 先有持久jobId，刷新/跨窗口GET可恢复，不靠单个HTTP会话 |
| M1-E06 | Cancel真正持久、传播到底层Npgsql，超时/失败/租约恢复准确终态 |
| M1-E07 | Probe审计+状态同事务；审计失败不留下成功/启用记录 |
| M1-E08 | Schema目标删除/变更后新版Snapshot/STALE状态准确，旧快照可审计但禁用于新探测 |
| M1-U01 | UI-E2E-01完整PG配置→测试→保存→启用→发现→编辑→重测→禁用，真实HTTP/OIDC |
| M1-U02 | 用户无权403/未登录401，CSS/隐藏按钮不能代替HTTP拒绝 |
| M1-U03 | 五类型表单字段实测；非PG四类不伪联通 |
| M1-U04 | 409冲突展示新版、保留非敏草稿；敏感输入不持久 |
| M1-U05 | Probe分阶段、空/加载/错误/取消/超时/Partial以及刷新恢复均有动作 |
| M1-U06 | 浅/深主题与窄屏检查，代表截图≤12张，不在页面展示研发提示 |
| M1-R01 | 独立Compose project before/after真实ID/labels/volume/fingerprint与KEEP/销毁回执 |
| M1-R02 | 任务临时容器/网络/临时卷在精确条件满足时真实清理，其他G3/G6资源无触碰 |
| M1-R03 | Mac ARM64原生容器与实际测试结果实证；Windows AMD64不可用时NOT_RUN单列 |
| M1-R04 | G3回归（认证、CSRF、发布/查询）在受影响范围无破坏，真实主要服务启动 |
| M1-R05 | 末次稳定完整本地验收 + 独立Review + 单一V3+Git重开输入绑定；CI按需NOT_RUN |

**合计 49 项**（A16+B14+C19）。适用性由测试矩阵逐项记录PASS/FAIL/NOT_RUN/NOT_VERIFIED/BLOCKED及原始证据；M1-U06等真实浏览器检查不能靠源码截图替代。

## D. 低成本运行顺序及故障注入

0. Preflight：校验实际版本、`-Help`参数、证书工具、OCI平台、Docker socket、NuGet缓存、EF模型变更/当前G3资源；先运行本包设计 Schema/负例。
1. 合同级：DTO/route/权限/严格JSON/If-Match/SecretRef 模型单测＋负例（不启动DB）。
2. PG Adapter级：启动独立合成 source PG，测试 TLS、权限、发现、固定预算；单个失败立即最小复现。
3. HTTP：独立平台 PG/Keycloak/API，真实OIDC/CSRF/审计/CAS，固定测试身份，权限不以假header代替。
4. Browser：Playwright真实端到端，将 Browser测试先拆最短路径，再组合全部路径；稳定输入完整运行一次。
5. Fail/Recovery：模拟TLS untrusted, auth revoked, metadata ACL, source down, audit db unavailable, concurrent change, stuck catalog job, cancel/lease, role revoked, secret replay。
6. Resource：独立Reviewer检查before/after准确IDs和回收候选；无匹配不得全局删除。
7. 基线 regression + V3独立重开。

任何高成本测试失败后保留原失败，先短复现/定向修复后在对应层再验，不盲延长timeout或启动完整SelfTest多次。每个用户可见流程至少成功、失败、刷新恢复/新任务取消三条状态链；没有可测试环境时按实列BLOCKED/NOT_RUN，不降格为Mock PASS。
