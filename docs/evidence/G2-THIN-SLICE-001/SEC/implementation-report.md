# G2-SEC-SUPPORT 实施与验证证据

状态：**DRAFT / PARTIAL，等待Master宿主集成与独立Review**。本子项工程检查与38项真实测试PASS；不能据此宣称产品G2完整安全验收通过。2026-10-26，Owner `g2_security_support`。

## 授权与不可变基线

- 当前授权：[G2授权索引](../../../tasks/current-authorization.md)、[SEC子卡](../../../tasks/G2-SEC-SUPPORT.md)、[冻结合同](../../../contracts/g2-thin-slice-contracts.md)。Master在任务消息明确转移本次五个手写C#文件的唯一写入权。
- 实施BaseSha：`5525f71cec05aa8814dbf367d0c2c87d5b12d276`。
- 源码里程碑SourceSha：`4eeaa56c3a6c3e10ccc54b84cf779f5cbd7570d5`，已推送 `origin/codex/G2-SEC-SUPPORT`。本报告与日志属于随后docs-only证据提交，避免自引用SHA。
- Worktree：`/Users/chasen/.codex/worktrees/g2-security/ontology-platform`，任务分支 `codex/G2-SEC-SUPPORT`；开工fetch成功，未修改main。
- 只改五个卡内C#文件和本SEC证据目录。未修改Contracts、项目文件、锁文件、Host/AppHost、迁移、CI或既有安全测试。工具验证额外在Git忽略的 `.tools/pythonlibs` 复用主工作树已批准隔离PyYAML目录的符号链接；未新增依赖、修改机器配置或读取凭证。

## 实际实现

`TransactionalAuditWriter`同时实现唯一 `ITransactionalAuditWriter` 和 `IAuditTrail`，构造依赖 `IDbContextFactory<GovernanceDbContext>`。共享模式先核对打开连接与 `transaction.Connection` 是同一对象，再通过独立Governance上下文 `SetDbConnection(..., contextOwnsConnection:false)` 和 `UseTransactionAsync` 写自己模块表；成功不提交外层事务，不销毁调用方连接。审计失败显式整笔Rollback，防止EF只回滚Savepoint后业务方误提交。独立模式自己开启短事务并在commit之后返回ID。Action采用Master登记的有限白名单，Outcome只允许allowed/denied/failure；Resource只能传服务器受控ID/固定路由，不存用户源、Prompt或异常原文。标识的字符校验不能代替调用方对来源及资源范围的授权。ScopeSiteIds保存完整规范集合，多厂及空集合SiteId=null，单厂保留唯一厂。

`G2Authorization.AddG2Authorization(IServiceCollection)`返回原服务集合，注册semantic.read、ontology.edit、release.approve、release.activate。角色保留 `platform.*` 原名；CreateActor仅读取G1服务器验证后的Claims及安全关联上下文，不读取身份请求头或Body。角色策略不声称已经完成资源范围授权，应用服务必须再次检查真实资源完整scope。

`G2EndpointGuard`使用冻结的static ReadAsync/WriteAsync签名，均返回Task<IResult>。身份401；角色/应用层403与CSRF/Origin拒绝均先调用持久审计。写入必须通过原生IAntiforgery和现有X-CSRF-TOKEN头；提供Origin时必须精确等于Security.PublicOrigin且无路径/凭据/多值。命令ID及幂等key1..64、reason1..500、revision非负。需要修订时只接受单个规范强ETag；缺428、格式错400、body不一致409。等待业务委托完整返回后才创建200，草稿DTO提供正确ETag时发送；不生成虚假X-Audit-Id。响应no-store。受控SemanticOperationException采用有限status、安全机器码与既有通用Problem正文；未预料异常与取消继续传播给原Host安全诊断。

## 真实测试与红绿证据

测试使用SDK 10.0.402、macOS ARM64、既有MSTest/Microsoft.Testing.Platform。HTTP测试是真实Kestrel加原生Antiforgery；固定可信身份只存在于测试宿主，没有产品登录头或测试路由。32项HTTP测试覆盖四策略九种角色组合、401/403、拒绝发生于业务委托之前、5类Origin、缺失/无效CSRF、8类ETag、4类非法Command、身份头伪造、固定业务错误和未知异常/取消传播。

6项PG测试使用批准固定镜像 `postgres:18.6-trixie@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6`，随机回环端口与tmpfs。每个用例在本轮容器新建随机数据库，执行真实Governance迁移；业务探针只映射 `g2_probe.business_probe`。故障用例仅在自己随机库给Governance表挂接测试schema触发器，产生真实PG审计写失败。结束删除随机库与容器，不读取/清空历史runtime、realm或持久卷。包括：双上下文commit全有且提交前其他连接不可见；rollback全无；审计失败后捕获异常仍不能commit业务；相同连接串不同物理连接拒绝；独立审计提交及空/单/多厂范围；真实HTTP403之前PG拒绝审计已持久。

| 命令/证据 | 退出码 | 实测结果 |
|---|---:|---|
| `dotnet build backend/tests/OntologyPlatform.SecurityTests --no-restore`，首次测试先行 | 1 | G2命名空间尚未实现，1编译错误；0测试运行。见red-missing-implementation.txt；外层shell尾部打印成功不能当构建通过。 |
| `dotnet test --project backend/tests/OntologyPlatform.SecurityTests --no-restore --filter 'FullyQualifiedName~G2SecurityTests\|FullyQualifiedName~G2AuditTransactionTests'`，无PG配置 | 0 | 38发现、32通过、6 Inconclusive/NOT_RUN。见http-and-no-pg.txt，不把6项跳过当产品PASS。 |
| `python3 docs/evidence/G2-THIN-SLICE-001/SEC/run-isolated-pg.py`，首次真实PG | 0 | 38/38通过，0跳过。见real-pg-first-run.txt。 |
| 相同runner，临时移除writer整笔Rollback的可逆变异 | 2 | 38发现、37通过、1失败；PG审计失败后外层Commit竟成功，测试明确捕获。见red-savepoint-mutation.txt。 |
| 相同runner，恢复正式Rollback实现 | 0 | 38/38通过、0跳过；见green-real-pg.txt。变异已恢复，未进入源码提交。 |
| `dotnet build backend/tests/OntologyPlatform.SecurityTests --no-restore`，最终 | 0 | 0警告/0错误；见build.txt。 |
| `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`，首次 | 1 | 本树缺隔离PyYAML、证据尾随空白/进行中空文件、runner变量名命中有限凭证模式假阳性。见verify-selftest-first-failure.txt。 |
| 同SelfTest，根因修复后 | 0 | 仓库静态检查和真实检查器负例通过，包括ReviewPackage35测试；见verify-selftest.txt。原生命令不由SelfTest隐式执行。 |
| `dotnet format whitespace backend/OntologyPlatform.slnx --no-restore --verify-no-changes --include <五个owned C#路径>` | 0 | 无格式错误，但solution加载有警告；不据此声称全部工程载入。见format.txt。 |
| 对Api、Governance、SecurityTests各csproj分别执行同format命令，仅include其owned文件 | 0、0、0 | 三个实际项目均无警告/格式错误；见format-api.txt、format-governance.txt、format-tests.txt。 |
| `git diff --cached --check`，源码提交前 | 0 | 无补丁空白错误；源码提交只含五个owned文件。 |

HTTP先写测试后实现；PG事务回归另做真实可逆变异红绿证明，不把初始缺实现编译错误包装成业务断言失败。格式检查首次识别PG测试多行initializer的6处空白诊断，已只格式化owned测试文件，后续三个项目检查全绿。最终代码与green-real-pg逻辑一致，后续仅测试代码格式与证据整理。

日志保留真实命令输出、状态和计数；为符合仓库文本规则统一LF并去除尾随空白，不改变断言、结果或异常类型。临时随机数据库密码及连接只留进程环境/内存，runner在持久化输出前脱敏；本目录不包含认证材料。

## 集成、审查与未运行边界

- **Host注册：待Master完成。** 需注册Governance上下文工厂、同一 `TransactionalAuditWriter` 的两接口以及 `AddG2Authorization()`；API使用冻结static guard签名。不修改本子项的共享文件所有权。
- **模块职责：** 资源完整范围、payload幂等hash/CAS、业务审计与外层commit由模块负责。guard不能证明每个产品端点已经调用它。
- **错误码目录：** 当前guard只校验有限安全字符与状态；Master已明确模块使用预登记固定常量，并在集成阶段统一检查目录，不能把正则当成任意原文可公开的许可。
- **独立Review：NOT_VERIFIED**，由Master针对固定SourceSha派只读Reviewer。本子项未自行派子Agent。
- **同Head CI：NOT_VERIFIED**；无CI run ID或URL证据，不从push成功推断CI通过。
- **产品Host完整G2/API、真实OIDC/Web/MCP/发布/Run：NOT_RUN**，属于Master和其他模块分工；本轮测试身份不能冒充OIDC验收。
- **Windows/Intel/生产/付费模型：NOT_RUN**；未执行系统管理员或模型调用。
- **唯一标准Review ZIP：由Master统一构建并复验**，本子项不另制竞争ZIP。源码/完整diff/本报告及红绿证据供最终唯一包纳入。

完成本子项后停止，保留独立Worktree供固定SHA审查，不自行合并main或开始后续关口。
