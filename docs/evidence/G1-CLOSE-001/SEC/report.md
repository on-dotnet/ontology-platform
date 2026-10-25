# G1-CLOSE-SEC 验证与交接报告

状态：DRAFT / READY_FOR_INDEPENDENT_REVIEW。仅本任务实现与本机验证完成，未合并main；独立审查、集成CI与唯一审查ZIP由Master完成。

- 授权：[G1-CLOSE-001任务合同](../../../tasks/G1-CLOSE-001.md)、[V1授权](../authorization-v1.md)。
- 分支：`codex/G1-CLOSE-SEC`；独立Worktree：`/Users/chasen/.codex/worktrees/g1-close-sec/ontology-platform`。
- 实施BaseSha：`1cbfcf3b3807a49003c0054fa618108a4c1a63a0`（Master已冻结模型、DTO、迁移及错误合同）。
- 已验证源码HeadSha：`b9a568a0c63f21edee9a0ef6220ddd1db24d40ca`。随后报告提交只增加本文件与最终静态核验证据，不修改源码。
- 本次仅编辑PlatformEndpoints、Security/AuditService、新AuditReadTests及本SEC证据目录；无新依赖、无公共配置/迁移/DTO/Host/CI修改。

## 最终行为

统一AuditService.Create将可信厂区去除空白、Ordinal去重排序后存为ScopeSiteIds；只有单厂兼容SiteId非null。登录、注销、拒绝和资源读取复用同一构造通道；已授权显式厂区使用单元素数组。

审计API要求非空白可信组织相等、历史ScopeSiteIds非null且非空、全部厂区属于当前可信范围。真实PG执行过滤、排序和Take后物化；随后唯一提交`platform.audit.read / platform.audit / allowed`，才设置X-Audit-Id并返回200。空结果、缺组织和无厂区也记录实际读取事实；legacy null不据SiteId推断。当前结果不含自身，后续可见；并发允许看到别次先提交事件，不声明全局串行快照。

所有十个冻结路由新增500 PlatformProblem metadata，并保留原状态。错误运行时分类仍由OBS负责，本分支不修改Host。

## 实测结果

| 命令/验证 | 结果与证据 |
|---|---|
| `python3 scripts/acceptance/test-governance.py`，生产修复前 | RED：27项，13失败、14通过、0跳过；dotnet test退出2、脚本退出1。[原始脱敏记录](red-governance.json) |
| 同脚本，最小修复后 | GREEN：27/27、0跳过，脚本退出0。[首次绿例](green-governance.json) |
| 同脚本，最终源码复验 | GREEN：27/27、0跳过，脚本退出0。[最终绿例](green-final-governance.json) |
| `dotnet restore backend/OntologyPlatform.slnx --locked-mode` | PASS，退出0 |
| `dotnet build backend/OntologyPlatform.slnx --no-restore`及`-c Release` | PASS，退出0；保留已有ASPIRE010，不修改共享AppHost配置 |
| `dotnet format backend/OntologyPlatform.slnx --no-restore --verify-no-changes` | 最终PASS，退出0；保留工具workspace警告，初次新测试初始化换行失败见原记录 |
| `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest` | 最终PASS，退出0；包含8个检查器、4个结构解析正反例、35个审查包用例等，并保留其产品NOT_RUN边界 |
| `dotnet test --project backend/tests/OntologyPlatform.InfrastructureTests --no-build --no-restore` | PASS，4/4、0跳过，退出0 |

构建、格式、SelfTest、基础设施的完整命令/退出码/输出见[验证记录](verification.json)。首次误用根目录`OntologyPlatform.slnx`得到MSB1009/退出1，随后按真实`backend/OntologyPlatform.slnx`恢复构建。首次SelfTest退出1已查明该新树未恢复PyYAML（ModuleNotFoundError）；按既有`scripts/verification-requirements.txt`用`python3 -m pip install --require-hashes --target .tools/pythonlibs -r scripts/verification-requirements.txt`隔离恢复6.0.3，退出0，无全局修改。初次format退出2后只格式化新测试文件，最终复验通过。

每次脚本新建随机专用PG和Keycloak容器、内存随机认证材料，应用Master两份迁移；未使用fullstack、旧私有运行时或生产资源。PG空库迁移首次探测不存在的历史表会打印`Failed executing DbCommand`，随后迁移正常完成/退出0；该日志保留，不伪报迁移失败。脚本结束删除本轮容器。原14项安全测试全部继续执行，其中真实Keycloak PAR使用本轮临时签发者。

新增13项参数化/独立用例覆盖：

- 正常200已提交唯一事实、重复及4个并发请求总计6条、当前不含自身/下次可见、Trace32位格式/响应关联一致/合成令牌不泄漏。
- A/B/AB/异组织/null组织/空组织/legacy null/空数组；ScopeSiteIds是权限依据，旧SiteId不可泄漏跨厂记录。
- 乱序重复空白claims归一；空结果、无厂区、缺失/空/空白组织仍记事实；空集合不得变成全局权限。
- 无审计角色403及denied、真实PG会话过期401、非法limit无成功事实、过滤先于排序Take。
- 专用PG触发器只拒绝本测试Actor的审计读取INSERT；故障期间会话认证和SELECT正常，读取503且无X-Audit-Id/无新成功行；移除触发器后恢复200。
- 资源查询全范围与已授权显式厂区的审计范围，以及未授权厂区仍403。

## 专项自审及交接边界

类型、字段、属性、方法均有准确中文XML，成员间空行；新增局部变量逐一核对中文用途注释；不把CS1591或SelfTest宣称为注释语义审查。测试DDL仅使用固定前缀加GUID十六进制，并先以锚定白名单检查标识符/Actor；两处EF1002仅在该DDL调用局部抑制。所有测试清理仅按本测试唯一主体/票据和专用触发器，初始化失败也进入释放路径。真实PG使用服务器端SQL范围过滤，无内存数据库替代。

独立Reviewer：NOT_VERIFIED，等待Master固定提交审查；本报告为Owner自审。CI：NOT_VERIFIED，未宣称任务分支或最终main已通过；最终回归/OBS集成/真实LGTM/Web端到端/迁移Down恢复由对应Owner和Master执行，本SEC未重做，不把本地27项扩大成整体G1 PASS。Windows/Intel：NOT_RUN。本分支不另构造ZIP，避免违反本轮唯一Review ZIP合同；Master统一封包本报告、源码和原始脱敏证据。
