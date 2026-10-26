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


## 独立审查M1限定修复（2026-10-26）

Master转述独立审查C0/I0/M1，原Spec/Quality核心通过；唯一M1为AgentRunExecutor原固定4096 UTF16 Substring切断代理对，JSON序列化成FFFD而仍COMPLETED。本轮已读指定SDD fix-loop；虽然该通用skill默认延期Minor，Master明确要求修复，因此按当前明确授权实施并交原Reviewer限定复核，不自行认定审查通过。

Fix Base=`3533251eaf844a2357daccb6cd9901e391b2ae14`；源码/测试小提交=`cedee6bc7a7c59b3bf1f563e319905b3a0a3afd5`，已push。只改`AgentRunExecutor.cs`和新增`MessageChunkTests.cs`；共享合同、SEM/QRY、迁移、依赖均未改。分片迭代器仍以`String.Length ≤ 4096`为界，切点处若为完整代理对，则本段缩短一个UTF16单元，偏移按实际长度推进；既有原子append、128KiB/512events/lease/fence预算保持原路径。空文本零分片。

覆盖文件`backend/tests/OntologyPlatform.AgentTests/MessageChunkTests.cs`：emoji😀与扩展汉字𠀀各覆盖连续两次代理对边界，真实MAF标准function loop、PG存储后读取、逐字符标签一致、无FFFD、seq/eventId连续、每段长度、事件字节预算、二次分页重放一致；空/ASCII 0、4096、4097、8193长度四个控制通过私有生产迭代器反射调用及JSON往返，不新增公共测试接口。两个集成边界用例明确仅在真实Gateway完成后以测试装饰器替换实体标签；真实正式版本/scope/查询/证据执行、MAF及PG仍实际运行，不能把注入标签称作完整发布Unicode标签验收。

| 真实命令与证据 | exit / 数量 | 结论 |
|---|---|---|
| `python3 scripts/acceptance/mcp-agent.py --label unicode-boundary-red --filter FullyQualifiedName~MessageChunkTests` | 2；2失败/0通过 | 首次真实长Unicode标签在上游SEM Load失败，未触达分片，**不是有效M1红例**；[完整记录](unicode-boundary-red.json) |
| `python3 scripts/acceptance/mcp-agent.py --label unicode-message-red --filter FullyQualifiedName~MessageChunkTests` | 2；2失败/0通过/0跳过；4.432秒 | 装饰器仅注入标签后，真实MAF/PG均Completed但持久消息损坏；emoji/扩展汉字均在字符保真断言失败；[有效红例](unicode-message-red.json) |
| `G2_AI_AJV=/Users/chasen/.codex/worktrees/g2-master/ontology-platform/node_modules/.pnpm/ajv@6.15.0/node_modules/ajv python3 scripts/acceptance/mcp-agent.py --label unicode-message-green` | 0；31通过/0失败/0跳过；40.134秒 | 原25项加新增6项全部通过；真实MCP Ajv子集3正例/6负例通过；[完整绿例](unicode-message-green.json) |
| backend目录 `dotnet format OntologyPlatform.slnx --no-restore --verify-no-changes --include src/Modules/Agents/OntologyPlatform.Modules.Agents/AgentRunExecutor.cs --verbosity diagnostic` | 0 | [限定源格式](unicode-format-source.json)，实际Agents分析器执行 |
| AgentTests目录 `dotnet format OntologyPlatform.AgentTests.csproj --no-restore --verify-no-changes --include MessageChunkTests.cs --verbosity diagnostic` | 0 | [限定测试格式](unicode-format-tests.json) |
| `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest` | 0；ReviewPackage35/0失败 | [真实SelfTest](unicode-selftest.json) |
| `git diff --check` | 0 | 本轮变更无空白错误 |

全套绿色执行时源码未提交；[源绑定](unicode-source-binding.json)逐项核验21个被测源码hash与固定源码提交相同，mismatches为空。锁定恢复、真实build、四模块迁移均0；仍有本AI旧基线共享Guard原CS1573警告，由Master已有修复处理，未越权手改。所有容器均本脚本随机新建并finally清理，无付费模型/新依赖。

应Master进一步请求，将首次SEM失败缩减为原Synthetic `data.ttl`中业务标签及来源断言的`炉次heat-1`替换为**单个😀**，其余不改。临时探针执行命令 `python3 scripts/acceptance/mcp-agent.py --label unicode-sem-minimal-diagnostic --filter FullyQualifiedName~UnicodeSemanticProbe`，exit2、1项失败、0跳过、2.255秒；仅安全输出`OBSERVED_SEM_UNICODE status=422; code=rdf_parse_invalid; type=SemanticOperationException`，未记录Jena响应正文。真实调用路径PublishAsync→ValidateAsync→LoadAsync→SendAsync。源码见[探针](unicode-sem-probe.cs.txt)，[原始诊断记录](unicode-sem-minimal-diagnostic.json)。探针临时复制到owned测试目录运行后删除，不混入31项固定回归或声称绿色；证据保存复现步骤。旧基线JenaRdfCodec.Term以JsonSerializer.Serialize生成字面量是待原SEM Owner核验的疑点；本轮未改SEM，未证明最终SEM修订仍有该缺陷。已准确交Master协调。

本次只交原Reviewer限定复核M1。Master最终SEM/QRY整合及同Head重跑仍待执行；真实模型、浏览器E2E、CI与唯一ZIP的既有NOT_RUN/NOT_VERIFIED保持不变。完成后停止写入并释放slot。
