# G2-AI-001 实施回执

状态：DRAFT / READY_FOR_INDEPENDENT_REVIEW / PARTIAL。只完成Task6实施与本分支验证，不自行Review、main集成或构ZIP。

- 分支：`codex/G2-AI-001`；独立Worktree：`/Users/chasen/.codex/worktrees/g2-ai/ontology-platform`。
- BaseSha：`233dd61ed08382bea91581aaa30dd7a0e26666e4`。
- 完整实现HeadSha：`89510fe2a34640808b55834c1ee34bfb02469b22`；后续仅Master日志规范化及本回执证据。
- 模型里程碑：`e353040f1f65f54b6a52e2a7a2f72be478b2ba87`；首个11项真实闭环：`6f52feadc34b593f1e7a8a579177bc1596c6d0e0`，均已push。
- Master唯一迁移：原`6c78632`→本树`87faaf948ca250d3cc9999dbe60d954f988c2925`；未自行生成/修改迁移。
- Master共享日志规范化：原`c95748b`→本树`bd7da5f3ab9631a70cc44cb92b09f6a9eed64ed6`；只整理本轮G2行尾空白，原始字节仍在此前Git提交，前后hash由Master记录。
- AgentTests新工程/私锁以及其Api ProjectReference由Master本轮明确批准；其他项目/锁、共同Guard、DTO、Host composition和CI未自行修改。

## 实际行为

Agents独立schema保存Run、完整Prompt/可信actor/固定plan/snapshot、幂等回执、事件、工具次数、首次执行deadline与租约/fence。创建从真实ReleaseCatalog固定版本并重新授权完整scope；只有owner且完整scope可读/列出/重放/取消。幂等绑定正式资源scope与完整payload，授权超集变化不产生重复Run；完整payload重试先恢复已提交事实并重新授权，不重查active或重跑工具。

所有业务事件与Governance审计共用物理连接/事务，先提交后发流；PG行锁分配单调seq/eventId，失效fence无法提交。取消使用当前lastSeq CAS，终态唯一，心跳将持久取消传入Gateway/HTTP。最多3工具、首次执行起30秒、512事件、每事件UTF8序列化128KiB和message.delta 4096字符；超限持久安全失败。租约接管允许重新执行只读工具且累计预算，不声称外部副作用exactly-once。

MAF1.26.0/Extensions.AI10.11.0实际ChatClientAgent函数循环只调用同一Gateway；文本和证据来自实际结果。harness要求Development宿主且`Agents:EnableDeterministicHarness=true`，默认关闭；worker在恢复旧任务时也检查当前开关。`approved_model`始终拒绝；disabled形成provider_not_configured持久失败。

MCP2.3.0真实SDK仅显式describe_ontology/resolve_entity/traverse_relationships，服务器Claims注入，三项均实际call并得到`text/event-stream`协议响应。MCP和Run SSE为不同传输。MCP POST/DELETE原生防伪与Origin检查，JSONRPC不伪造Command。Run SSE为.NET10原生ServerSentEvents/SseItem；16条PG分页、准确游标400/409、终态关闭、25秒底层连接上限、断流不cancel。每轮由原生CookieManager/TicketDataFormat恢复随机引用并调用同一PostgresTicketStore真实查PG，复验撤销、绝对过期、当前完整scope。

Cookie引用claim及TLS绑定路径核对了[ASP.NET Core v10官方CookieAuthenticationHandler源码](https://raw.githubusercontent.com/dotnet/aspnetcore/v10.0.0/src/Security/Authentication/Cookies/src/CookieAuthenticationHandler.cs)，没有把同请求缓存AuthenticateAsync当重新查库。认证材料不输出或保存到证据。

ActivitySource/Meter均为OntologyPlatform.Agents；指标仅固定结果/能力。后台span是实际新span，通过`execution.creation_trace_id`关联创建Trace；合同只保存TraceId，未伪造不存在的父span。

## 验证事实

| 实际命令/记录 | exit / 数量 | 判定 |
|---|---|---|
| `python3 scripts/acceptance/mcp-agent.py --label idempotency-recovery-green`，本进程G2_AI_AJV指向已批准repo锁定Ajv6.15.0 | 0；25通过/0失败/0跳过；38.655秒 | [完整运行证据](idempotency-recovery-green.json) |
| 上述脚本内locked restore、真实Api/AgentTests build、四模块EF真实migration update | 0 | 已运行；最终构建有基线Guard缺param文档的1个warning，由Master单写处理 |
| 上述实际MCP OutputSchema与Registry精确比对、Ajv共同关键字子集 | 0；真实正例3/篡改负例6 | 不是完整2020-12方言一致性认证；未支持元schema校验关闭，仅对已扫描共同validation关键字作断言；未知新关键字失败 |
| `python3 scripts/acceptance/sse-replay.py`（同现有Ajv路径） | 0；6通过/0失败/0跳过；32.029秒 | [独立SSE入口](sse-replay.json)，含真实约12MiB不消费响应体，服务器24–28秒窗口退出 |
| backend工作目录`dotnet format OntologyPlatform.slnx --no-restore --verify-no-changes --include ...` | 0 | [源码实际命中](final-format-0.json) |
| 私测试工程目录同format命令 | 0 | [测试实际命中](final-format-1.json)；首轮cwd错导致0命中已标无效，后续修复实际命中2源码/1测试后复验 |
| `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest` | 0；工程检查8、结构化正负4、环境3组、ReviewPackage35/0失败 | [最终SelfTest](selftest-green.json)；这些不是业务测试数 |
| `git diff --check` | 0 | 无空白错误 |

25项覆盖真实正式发布/MAF/Gateway、MCP initialize/list/三call及身份注入拒绝、原生Cookie/CSRF/Origin、PG原子audit失败回滚、并发幂等、lease接管/fence、取消CAS及真实HTTP令牌传播、工具/时间/字符/字节/事件预算、R1/R2真实发布与回滚后旧Run固定版本及离线重放、SSE游标/注销/厂区撤销/绝对过期/慢客户端、空库Down/非空事实保护/并发NOWAIT。

[源绑定](source-binding.json)核验最终25项执行记录的20个源码hash与实现提交一致；执行时尚未commit的源码由此明确关联。初始可构建模型的真实迁移缺失红例见[记录](initial-migration-red.json)。其他红例保留：工厂未采纳隔离连接、故障测试表名/请求scope问题、第四次工具预算已持久失败却错误返回可继续、非Development harness、授权超集变化重复Run。文件标签含red/green不代表结果，实际exit/count才是判据。

所有运行由脚本新建随机回环PG/Jena/RustFS容器、tmpfs和随机Synthetic组织，finally删除本次资源；不读取/复用历史运行凭证或卷。脚本只接受既有批准镜像；Jena默认ontology-platform-g2-fuseki:6.2.0，不安装新依赖。PyYAML通过Master明确批准的忽略.tools/pythonlibs符号链接复用，未入Git或ZIP。

## 真实/替身界限与剩余门禁

- 测试Kestrel用服务器固定Synthetic身份替代OIDC登录跳转；后续Cookie、Data Protection、PG票据、Antiforgery、授权、SDK、MAF、数据库和发布HTTP均真实。没有把本测试称为真实Keycloak/浏览器完整E2E。
- TimeProvider仅用于明确的lease/绝对期限负例；SSE慢客户端25秒是实际墙钟。HTTP故障门只延迟/失败实际发送，不生成假成功图或结果。
- 真实LLM、付费/云模型调用：NOT_RUN / BLOCKED（无批准模型）；Windows/Intel、生产负载/恢复/SLO：NOT_RUN。
- Master最新QRY/SEM独立审查修复尚未进入本AI基线；本记录证明复用基线唯一Gateway，不代表最终查询模块审查通过。Master集成后需在最终依赖版本重跑。
- YARP真实代理与浏览器延迟/完整Keycloak E2E：NOT_RUN，归Master全链验收；独立Review：待Master派发；同Head CI：NOT_VERIFIED，无run ID/URL；唯一标准ZIP由Master构建，本Owner不自行打包。
- Master接入：AddAgentsModule、AddSemanticMcpEndpoints；MapExecutionEndpoints、MapMcpEndpoints；开发迁移AgentsDbContext；订阅Agents的OTel source/meter；仅Development验收显式打开harness。

本轮没有修改main、公共合同、AppHost、共享锁或CI，没有调用外部模型。提交推送后停止实施，等待独立审查反馈。
