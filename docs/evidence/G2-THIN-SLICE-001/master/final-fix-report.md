# G2 final combined fix wave

状态：**DRAFT / PARTIAL，待Master实际OIDC浏览器、cold one-key、同Head CI与独立限定复审**。本波不自行批准、集成main、构造审查ZIP或进入G3。

Base：`96db23bb17627cfa37efbba113c1641906b931d1`；任务分支：`codex/G2-FINAL-FIX`；独立树：`/Users/chasen/.codex/worktrees/g2-final-fix/ontology-platform`。开工工作树干净，已fetch。四项完整审查发现由一个统一修复波处理，没有派子Agent。

## 修复与覆盖

1. **名称丢失**：`OntologyService.SaveAsync`按create相同规则拒绝空白或超过200字符名称；`SaveCoreAsync`在已有CAS、源修订、命令回执、Governance审计的同一事务更新草稿头。结构编辑没有名称参数时保留当前名称。没有改变源字节/hash、历史、资产scope、锁顺序或幂等载荷范围。
   - 真实PG/Jena新增`RenamePersistsThroughReopenListReplayAndStructuralEdit`：响应、独立读回、目录、同命令重放不增修订、源/hash、原始历史、结构编辑保留名称。
   - 新增`RenameFailureAndNameBoundsLeaveCommittedNameUnchanged`：旧修订409、真实Governance写后注入503、空白/201字符422均不改已提交名称，修订/命令/审计均只保留基线；200字符上界成功。
   - 保留原67项，最终实际**69/69，0跳过**。原先省略必填Name的本文件旧夹具补真实名称。Master另外明确转交PUB三文件/QRY一文件，实际共**6处**补`Name=对应draft.Name`（PUB5、QRY1），没有改变原断言或故障/CAS路径；先前调度消息“7处”是计数错误，以本diff为准。PUB真实50/50、QRY真实49/49。
2. **发布预绑定授权**：六条生产路由增加实际具名策略：三个读取`semantic.read`、提案和激活`release.activate`、审批`release.approve`。保留原guard、CSRF、完整scope和应用检查，复用既有授权结果处理器与真实Governance拒绝审计。
   - 新`G2PublishingAuthorizationTests`通过生产`MapPublishingEndpoints`与真实Kestrel调用三个POST：匿名畸形JSON401、viewer畸形JSON403且真实PG已提交三条完整双厂拒绝审计；PG触发器拒绝审计时三个入口均安全500、零审计；合法角色畸形JSON400、合法唯一DTO缺CSRF403。
   - 业务哨兵所有方法只抛异常，不能返回模拟发布成功。固定主体fixture只证明服务器管道顺序，不等同真实OIDC。
3. **运行OpenAPI**：五个实际CAS入口声明必需强`If-Match`（`"<revision>"`，与`Command.expectedRevision`相同，缺失428/冲突409）；发布明确实际安全/业务Problem错误，G2发现路由的错误响应关联唯一`PlatformProblem`结构。没有增加运行端点或修改CAS行为。
   - `ProductionHostDocumentsStrongRevisionAndPublishingProblems`通过`SecurityHostFixture`启动正式`PlatformApiHost`全部生产映射，自建临时证书/密钥，实际HTTP GET文档，逐项检查五个头与发布错误。两次导出字节相同。
   - `g2-platform.openapi.json`直接来自该实际导出，只做JSON空白/LF规范化；全对象相等与原始/规范化SHA256在验证证据。实际**28个路径、96个组件**，不是手造路由表。
4. **TS生成漂移**：用规范运行快照经现有生成器重新生成全部组件，产物实际**97个type（96组件+JsonValue辅助）**，无`unknown`、无手写业务DTO。新增`--check`只比较实际生成字节并在漂移时非零退出。Vitest断言签入产物与规范快照完整生成结果逐字节相等，并重复check不改文件；另实际运行生成器两次，全部绑定源码散列均不变。
5. **Master同波增补的路径边界**：`g2-trace-browser.mjs`移除硬编码POSIX分隔符；两脚本都拒绝空relative、`..`、上级前缀及跨drive绝对relative。26项实际提取guard的POSIX/Win32纯字符串检查全过，不读取任何runtime文件；Windows运行仍NOT_RUN。

## 红绿与实际命令

原始安全输出保留于[raw outputs](final-fix-raw-outputs.json)，包括临时编排源代码；原生脚本自身脱敏后的完整结果分别见以下JSON。初始错误的shell solution路径与wildcard过滤器零测试exit8属于setup失败，未作为RED或PASS。

| 范围 | 实际命令/入口 | 结果 |
|---|---|---|
| Rename RED | `semantic-roundtrip.py`导入后`main(postgres=True,test_filter='FullyQualifiedName~Rename')` | 2项真实断言失败，test exit2；旧名称/非法名称被接受 |
| Auth/OpenAPI RED | `python3 scripts/acceptance/test-governance.py --filter 'FullyQualifiedName~G2PublishingAuthorizationTests\|FullyQualifiedName~ProductionHostDocumentsStrongRevisionAndPublishingProblems'` | 4项中3失败：预绑定400、审计故障400、缺If-Match；test exit2，runner exit1 |
| Generator RED | 精确pnpm `--dir apps/web test src/lib/api/openapi-types.test.ts` | 4项中1失败：完整产物不等，exit1 |
| SEM GREEN | `semantic-roundtrip.py main(postgres=True)`，证据位置由临时wrapper定向到master | 69/69、0跳过，exit0 |
| SEC GREEN | `python3 scripts/acceptance/test-governance.py`，独立临时PG/Keycloak | 114/114、0跳过，exit0 |
| 最终SEC限定复验 | `dotnet test --project backend/tests/OntologyPlatform.SecurityTests --no-build --no-restore --filter 'FullyQualifiedName~G2PublishingAuthorizationTests\|FullyQualifiedName~G2OpenApiSchemaTests\|FullyQualifiedName~G2ExecutionEndpointTests'`，自建临时PG | 6/6、0跳过，exit0 |
| PUB/QRY | `release-faults.py` / `query-plan.py`，独立临时PG/RustFS/Jena | 50/50、49/49、0跳过，exit0 |
| 全solution | `dotnet build backend/OntologyPlatform.slnx --configuration Release --no-restore` | 1条既有ASPIRE010警告（CLI bundle禁用）、0错误，exit0 |
| 线协议 | `dotnet test --project backend/tests/OntologyPlatform.G2ContractTests --no-restore` | 19/19、0跳过，exit0 |
| 定向格式 | `dotnet format whitespace backend/OntologyPlatform.slnx --include <本波C#路径> --verify-no-changes --no-restore` | exit0；工作区加载警告原样保留，非编译错误 |
| 精确Web | Node24.22.1 + 项目pnpm11.28.8，`--dir apps/web lint/typecheck/test/build` | 全exit0，Vitest77/77 |
| 生成/脚本 | `node apps/web/scripts/generate-types.mjs [--check]`；两脚本`node --check` | 两次实际generation+重复check零变化，全exit0 |
| 仓库 | `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`、`git diff --check` | exit0；35个ReviewPackage自检0失败，静态检查不冒充产品PASS |

工具使用既有锁定SDK10.0.402、EF10.0.13、批准的Node/pnpm及NuGet缓存；本树独立frozen install、独立pnpm store。`.tools/pythonlibs`仅指向批准只读缓存。无新依赖/锁/迁移/CI/全局PATH变更，所有容器只用本波随机名称，均已移除。

## 精确绑定、证据与待办

- [最终验证与16个源码SHA256](final-fix-verification.json)：每条命令真实退出码/完整输出；Release/线协议/格式/Web/生成/语法/SelfTest；实际运行导出与规范快照JSON完全相等；所有绑定文件在重复生成前后散列不变。
- [SEM RED](final-fix-sem-red.json)、[SEM GREEN](final-fix-sem-green.json)、[SEC RED](final-fix-security-red.json)、[SEC full GREEN](final-fix-security-green.json)、[最终SEC真实PG限定复验及源散列](final-fix-security-focused-green.json)、[PUB GREEN](final-fix-pub-green.json)、[QRY GREEN及源散列](final-fix-query-green.json)、[路径26项](final-fix-path-boundaries.json)。原生脚本记录的`sourceSha=96db...`表示测试时尚未提交、`workingTreeChanges=true`，不是声称旧提交已含修复；最终源码散列另精确绑定。
- `g2-live-browser.mjs`原102项不降低/不跳过，新增11项：三个匿名发布POST401、三个viewer发布POST403、拒绝审计可读，以及UI真实名称PUT200/新名称与revision/相同源hash/持久GET。名称保存后`remote`更新为真实响应，使SHACL、Diff、export和后续提案绑定新revision。
- 本Agent不访问Master私有runtime、不运行该实际浏览器/OIDC链：**NOT_RUN，Master执行**。完整SEC中的真实Keycloak PAR不替代这些新浏览器断言。cold one-key、同Head LinuxCI、限定独立复审、main集成/唯一ZIP均由Master负责；本波不自批准。模型未调用，Monaco保持用户暂停；Windows/Intel/生产未验证。
- Ruling：无。Root明确授权的输入补齐与路径修正均列明，未自行扩展业务范围。
