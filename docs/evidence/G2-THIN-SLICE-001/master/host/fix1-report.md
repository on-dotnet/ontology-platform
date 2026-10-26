# G2 宿主独立审查修复 round 1

状态：**PARTIAL / READY_FOR_INDEPENDENT_REVIEW**。只修 I1/I2/M1；等待独立复审、Master集成与真实PG/Jena故障恢复验收，不代表G2全链PASS。

BaseSha：`c1e4dd0af6af4258f39c3c8a360c60e0709b8915`；独立分支`codex/G2-HOST-FIX`，独立托管树`g2-host-fix/ontology-platform`。修改前fetch成功并确认基线；未访问Master私有runtime，未启动其进程。精确源码及测试SHA256见[绑定清单](fix1-source-bindings.json)，Git提交头以本报告提交及Master集成回执为准。

## 修复与可复检边界

- **I1**：实际`MapExecutionEndpoints`五个操作声明唯一`ExecutionRun[]/ExecutionRun/ExecutionEvent`响应；SSE仅声明原生`text/event-stream`中每条data的事件封套。逐操作补真实400/401/403/404/409/422/428/503及宿主500的`PlatformProblem`，发送SSE头之后仍沿用原生流/关闭规则，无第二套事件编码器。Kestrel测试直接挂载生产Run和Ontology映射函数，测试不加Produces；逐路由核成功引用、标准错误、session、POST防伪头和九种事件联合。[实际导出](fix1-runtime-openapi.json)只含公开协议，不是静态bootstrap冒充实际路由。
- **I2**：G2路径将Governance三次常量投影查询移入`G2Readiness`，与Ontology/Publishing/Agents五次查询及Jena/RustFS两个HTTP请求共用一次linked token、一次两秒CancelAfter。调用方取消继续传播。禁用G2保持原Governance三表读取及RequestAborted语义。真实健康路由测试在EF连接入口阻塞首个Governance查询；另用EF命令/HTTP可控等待验证累计预算，不声称测试空读取器证明真实PG健康。
- **M1**：运行时敏感值枚举加入accesskey，字段形式覆盖`rustfsAccessKey/RUSTFS_ACCESS_KEY`及连字符形式。测试覆盖实际运行时枚举值、未在枚举中的字段值、普通公开诊断原样保留。

只修改被派所有权内的三个宿主文件、两个Python文件及三个新增G2宿主测试；无新依赖、公共项目/锁/合同/迁移/AppHost改动。新手写C#类型/成员均中文XML，局部变量声明处中文用途注释；人工逐项复核不以CS1591或SelfTest替代语义审查。

## 实际命令与结果

以下命令在独立树执行；`.txt`保留安全stdout/stderr及exitCode，仅规范尾随空白以满足仓库格式规则。

| 命令/验证 | 实际结果 | 原始证据 |
|---|---|---|
| `python3 scripts/tests/Wave2Runtime.Tests.py`（修复前） | exit1；新access key断言真实失败 | [Python RED](fix1-python-red.txt) |
| `dotnet test --project backend/tests/OntologyPlatform.SecurityTests/OntologyPlatform.SecurityTests.csproj --no-restore --filter 'FullyQualifiedName~G2ExecutionEndpointTests\|FullyQualifiedName~G2ReadinessTests'`（修复前） | exit2；4项中2失败/2通过。真实Run响应Schema缺失；Governance连接等待超过客户端5秒保险期限 | [有效 RED](fix1-dotnet-red-valid.txt) |
| 上述筛选（修复后） | exit0；4/4、0跳过 | [首次 GREEN](fix1-dotnet-green.txt) |
| 增加`FullyQualifiedName~G2ReadinessBudgetTests`、`--output Detailed` | exit0；5/5。治理首连接2007ms返回503；跨8查询/2HTTP2033ms在RustFS阶段取消返回503 | [预算 GREEN](fix1-budget-green.txt) |
| 临时在HTTP阶段再次`CancelAfter(2s)`，仅运行`G2ReadinessBudgetTests`，finally恢复原源码 | exit2；1/1失败，实际200而期望503，证明检测逐阶段重置预算 | [预算重置变异 RED](fix1-budget-reset-mutation-red.txt) |
| `dotnet test --project ...SecurityTests.csproj --no-restore --filter 'FullyQualifiedName~G2&FullyQualifiedName!~G2AuditTransactionTests' --output Detailed` | exit0；52发现、50通过、2 Inconclusive：两个原有真实PG中间件测试未注入本轮临时PG | [初次广筛](fix1-focused-security-green.txt) |
| `dotnet test --project backend/tests/OntologyPlatform.SecurityTests/OntologyPlatform.SecurityTests.csproj --configuration Release --no-build --no-restore --filter 'FullyQualifiedName~G2&FullyQualifiedName!~G2AuditTransactionTests&FullyQualifiedName!~MiddlewarePersistsForbiddenAuditBeforeMalformedBodyBinding&FullyQualifiedName!~MiddlewareAuditFailurePropagatesWithoutFalse403' --minimum-expected-tests 50 --output Detailed` | exit0；50/50、0跳过。明确排除需要真实外部PG前提项，未弱化断言 | [Release安全回归](fix1-security-release.txt) |
| `python3 scripts/tests/Wave2Runtime.Tests.py`（修复后） | exit0；原8种协议负例+运行时路径限制；新增5种access key负例+3种公开文本保留 | [Python GREEN](fix1-python-green.txt) |
| `dotnet restore backend/OntologyPlatform.slnx --locked-mode` | exit0；所有公共锁未改 | [受锁恢复](fix1-locked-restore.txt) |
| `dotnet build backend/OntologyPlatform.slnx -c Release --no-restore` | exit0；0错误，1个已有ASPIRE010（CLI bundle关闭）警告 | [真实构建](fix1-locked-build.txt) |
| `dotnet format backend/tests/OntologyPlatform.SecurityTests/OntologyPlatform.SecurityTests.csproj --no-restore --include` 本轮六个C#路径，随后同命令追加`--verify-no-changes` | 均exit0；未格式化所有权外源码 | [格式化](fix1-format.txt)、[格式验证](fix1-format-verify.txt) |
| `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest` | 首轮exit1，独立树缺隔离PyYAML；只读链接已批准主仓库`.tools/pythonlibs`后重跑exit0（含ReviewPackage35项/0失败）。无全局安装 | [首轮前提失败](fix1-selftest.txt)、[恢复后SelfTest](fix1-selftest-restored.txt) |

首次尝试误用`--filter-class`导致exit5/零测试，见[筛选器前提失败](fix1-dotnet-red.txt)，不计为RED。随后健康路由夹具初漏原生Antiforgery注册，产生500/等待超时，见[夹具诊断](fix1-dotnet-regression-red.txt)，同样不计为有效缺陷RED；补齐原生服务后才取得上述有效RED。生产未为测试增加任何旁路。

## 保留边界

真实PG阻塞/断开、Jena故障与恢复由Master在自己的私有运行时执行；本Worker全部NOT_RUN。真实OIDC、浏览器全链、正式SSE重放/MAF/MCP和G1运行回归未由本Worker重跑；真实付费模型、生产、Windows/Intel同样NOT_RUN。当前CI为NOT_VERIFIED，由Master负责最终同Head CI及唯一Review ZIP。本分支不集成main、不自动进入下一关口。
