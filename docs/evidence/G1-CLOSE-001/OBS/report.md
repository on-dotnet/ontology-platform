# G1-CLOSE-OBS 真实验证与交接

状态：DRAFT / PARTIAL，等待独立Review及Master集成。Owner=OBS；分支`codex/G1-CLOSE-OBS`；独立工作树`/Users/chasen/.codex/worktrees/g1-close-obs/ontology-platform`。授权阶段Base=`d181f66e569e190a66b0f48b179f2fd9390b9467`，开工冻结提交=`1cbfcf3b3807a49003c0054fa618108a4c1a63a0`。2026-10-25已fetch，origin/main仍为阶段Base；未修改只读路径，未合main，未新增依赖。当前提交头由Git提交事实和Master审查包记录，避免自引用。

## 实现及安全边界

- LoggerMessage事件1003/EventName=`PlatformRequestFault`，业务字段仅`Route/ExceptionCategory/Outcome/Status/TraceId`，不接受Exception；1001增加完成Outcome。标准日志另有固定OriginalFormat元数据，不记录任意类型名或原异常。
- BadHttpRequestException固定400；DbUpdateException为database_write/503；Npgsql已知网络包装为database_connection/503，其余Npgsql为database_failure/503；HttpRequestException为upstream_unavailable/503；普通InvalidOperation、Argument、Format、UnauthorizedAccess和非请求取消OCE均500/internal_error。EF实际连接故障会以InvalidOperationException包装NpgsqlException，只对这一明确结构解包；Npgsql链最多检查8层，不分析Message或类型名称字符串。
- RequestAborted OCE不写Problem，未开始的取消用499作为内部诊断状态并Abort；已开始取消保持实际200。普通故障遇到已取消请求也Abort；已开始保持原状态、不追加JSON。Problem写回再失败受控Abort，不重复故障事件、不把原异常抛给框架。响应清理后恢复安全关联头与no-store。
- 真实Development Kestrel OnStarting失败会在返回中间件前通过`Microsoft.AspNetCore.Server.Kestrel`事件13记录原Exception；红例已观察。Host源头关闭该类别出口，继续用本平台固定诊断及指标。此过滤覆盖该类别的框架技术日志，故障可观测性由受控事件补足。
- Activity只新增固定category/outcome/status三个标签，设Error且不附原异常状态描述，不创建异常事件。Alloy额外清除OTLP status.message（即status description）、span级exception/error属性，归一化事件名并仅保留三个安全平台事件属性。
- 旧Alloy只过滤attributes，body可保留异常原文；现在body固定为PlatformTelemetry，故障事件为PlatformRequestFault，诊断字段走精确大小写白名单。保留Route/ExceptionCategory/Outcome/Status/TraceId及原有字段和PAR布尔。三个Loki索引配置及低基数指标合同未改变。此配置不宣称能够判别白名单字段内任意恶意值，上游固定来源仍是合同前提。

## 命令与实际结果

| 命令/证据 | Exit | 事实 |
|---|---:|---|
| `git fetch origin` | 0 | 冻结基线及origin/main已核对 |
| `dotnet restore backend/OntologyPlatform.slnx --locked-mode` / restore.txt | 0 | 全后端受锁恢复；首次误用根solution路径MSB1009，已更正，没有依赖变更 |
| 新OBS14红例 / red.txt | 2 | 14 FAIL；普通异常实际503而预期500，缺少受控事件及完成结果 |
| 旧边界再红 / red-boundary.txt | 2 | 3 FAIL；取消项在AssertFault中因缺少1003而失败，不能据此宣称该项marker泄漏；已开始和二次写回失败两项明确由AssertNoSensitiveData观察到marker进入日志边界 |
| 首实现 / green-first.txt | 2 | 2 PASS/12 FAIL；发现清理响应丢Trace头、EF包装及Kestrel事件13出口 |
| 第二实现 / green-second.txt | 2 | 13 PASS/1 FAIL；唯一剩余是Kestrel事件13泄漏，后已源头修复 |
| 新OBS完整测试 / green.txt | 0 | 17 PASS/0 FAIL/0 skip，真实Kestrel包括开始后取消及已取消普通异常 |
| 原生OTLP出口 / otlp-export.txt | 0 | 1 PASS；正式ServiceDefaults exporter实际HTTP/protobuf日志及Span，无marker（也包含于17项） |
| Release全后端build / build-release.txt | 0 | 0 error；既有ASPIRE010 warning保留 |
| `dotnet format ... --verify-no-changes` / format-final.txt | 0 | 全后端；首次仅新文件导入顺序失败，已仅格式化owned C#修正 |
| Infrastructure完整测试 / infrastructure.txt | 0 | 4 PASS |
| `python3 scripts/acceptance/test-governance.py` / governance-integration.txt | 1（test子进程2） | 独立真实PG+Keycloak，31项中30 PASS/1 FAIL/0 skip；唯一FAIL是既有RuntimeOpenApiDeclaresRedirectsAndCompleteErrors：`get /auth/login`缺500 metadata。该路径由SEC负责，本分支不改/不掩盖 |
| `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest` / selftest-final.txt | 0 | 标准SelfTest；ReviewPackage35/35。首次因新日志行结束和未复用隔离PyYAML失败，修正LF并复用已批准隔离依赖后通过；工程SelfTest不代表产品全PASS |
| 固定镜像`alloy validate` / alloy-validate.txt | 0 | 真实官方镜像语法验证；无stdout |
| `python3 docs/evidence/G1-CLOSE-001/OBS/verify-alloy-boundary.py` / alloy-runtime.json、alloy-runtime.txt | 0 | 真实Alloy容器接收OTLP并实际导出到内存回环sink，10项PASS：body/状态/事件marker删除，精确字段及安全Span类别保留，错误大小写字段移除；该原始运行的Loki检查仅对比工作区，不证明相对冻结基线的配置不变。原始输出保留，冻结基线配置复验见下一行；此sink不验证实际Loki索引 |
| 限定复审后同helper复跑 / alloy-runtime-baseline.json、alloy-runtime-baseline.txt | 0 | 固定Alloy真实运行10项PASS；Loki索引配置以完整冻结提交`1cbfcf3b3807a49003c0054fa618108a4c1a63a0`执行`git diff --exit-code`比较未变，仅证明配置与冻结基线相同；实际索引由Master另查Loki `/series`。原alloy-runtime.json/txt未覆盖 |
| 限定证据修复后SelfTest / review-minor-selftest.txt | 0 | 标准SelfTest通过；ReviewPackage35项0失败。原17份stdout的SHA256均与rename-map.json一致，backend/infra源码无变更 |

测试捕获器同时检查实际formatter正文、全部state、外部scopes、Exception对象、真实Activity标签/事件/status description；原生OTLP出口额外检查真实protobuf日志及Span字节。所有marker均固定无效合成值，原始异常和OTLP字节仅在测试内存，不落盘。测试注入路由仅在测试程序集MapGet注册；产品无故障路由。PG/Keycloak脚本使用本轮隔离容器及随机生成运行时配置，未读取历史凭据。

## Master真实LGTM接续建议

PROPOSED：用统一完整LGTM栈和本轮专用PG，先用真实登录Cookie调用`/api/v1/platform/me`确认200，保留该Cookie在受控内存，然后临时停止专用PG，再请求同一正式API。PostgresTicketStore真实查询会抛出驱动故障，正式Host应返回503/dependency_unavailable及TraceId、产生1003/database_connection/problem_returned；恢复PG后同会话应恢复200。或使用已有PG故障脚本的受保护`/health/ready`：其真实三表查询也会抛驱动故障，但健康Probe依原设计可不导出业务Span，因此要同Trace关联优先使用正式API。

在Loki按`{service_name="ontology-platform-api"}`配合body=`PlatformRequestFault`及对应TraceId结构化元数据查询；确认1003精确字段、固定route、category/outcome/status，无合成marker。按同TraceId查Tempo，确认Error与三个平台标签且无exception原文/status description/事件敏感值；查询series确认索引仍只有service_name/deployment_environment_name/service_version。保留故障前200、故障503、恢复200的响应及查询脱敏证据。不添加产品调试端点。该停止PG方案验证依赖连接失败遥测，不能冒充“SELECT成功但审计INSERT失败”的SEC测试，后者应使用已认证请求和仅限制审计INSERT的隔离机制。

## 尚未完成与停止边界

- 真正完整LGTM中的Loki/Tempo同Trace查询：本子任务NOT_RUN，由Master统一栈验收；本地Alloy实际出口已测但不冒充完整LGTM PASS。
- 独立Reviewer、同Head CI、Master集成、唯一审查ZIP：NOT_VERIFIED，由Master执行；本分支仅DRAFT/PARTIAL备份。
- Windows/Intel、生产拓扑/证书轮换、供应链完整CVE/SBOM/签名：NOT_RUN/NOT_VERIFIED，未扩大本轮授权。
- 新增C#类型/成员/主构造参数已人工核查中文XML；局部变量与异常分类/取消边界有中文用途说明；成员空行、源生成日志方式保留。正式端点、AuditService、既有测试、DTO/PlatformProblem、ServiceDefaults、迁移、锁、CI均未编辑。


## 2026-10-26 真实集成事件身份缺口补修

Master真实LGTM在审计INSERT故障时得到503，Loki保留database_write/problem_returned/Route/Status/TraceId，却把故障正文降为PlatformTelemetry且没有EventName/EventId。原始安全证据位于Master的`closeout-loki-investigation.json`；本目录event-identity-investigation.json保存对应故障行与原文件SHA256，不覆盖初次失败。

准确契约已按锁定[OTel 1.20.1官方序列化源码](https://github.com/open-telemetry/opentelemetry-dotnet/blob/core-1.20.1/src/OpenTelemetry.Exporter.OpenTelemetryProtocol/Implementation/Serializer/ProtobufOtlpLogSerializer.cs)及[官方logs.proto](https://github.com/open-telemetry/opentelemetry-proto/blob/v1.9.0/opentelemetry/proto/logs/v1/logs.proto)核对：EventId.Name写入顶层event_name（字段12），数字Id默认不导出，只有实验选项启用时成为logrecord.event.id。当前实际原生protobuf经字段级解析也确认：顶层eventName=PlatformRequestFault，attributes中无EventName/EventId/logrecord.event.id。旧回归只检查原生字节里存在名称，再用手工Legacy属性喂Alloy，未验证这两层之间的真实契约，故漏测本缺口。

修复仅在Alloy将标准`log.event_name`精确等于PlatformRequestFault的记录映射成固定EventName=PlatformRequestFault及EventId=1003，再由既有条件输出固定安全正文；白名单已有这两个字段。数字1003来自这一已冻结名称的唯一平台事件合同映射，未启用实验开关、不把任意名称映成1003、不新增日志事件或原Exception。应用Host/Telemetry业务源码未改，指标及Loki配置索引白名单未改。

增强现有原生OTLP测试和Alloy边界helper：正式Kestrel的普通异常与OnStarting二次写失败产生原生OTLP，测试内存中继把原始protobuf逐字节送入独立随机端口Alloy，再按官方wire schema解析实际出口。中继仅本机回环、只处理本测试日志、抑制中继自身递归遥测；未连接Master活跃完整栈。原始protobuf仍仅在内存，落盘仅受控字段摘要；历史17份stdout及此前Alloy红绿输出全部保留。

| 真实命令/新证据 | Exit | 事实 |
|---|---:|---|
| 增强helper、修复前 / alloy-event-identity-red.json、alloy-event-identity-red.txt | 1 | 15项中14 PASS/1 FAIL；实际原生测试1/1 PASS，但两个实际故障穿过旧Alloy后body均PlatformTelemetry、EventName/EventId均null |
| 同helper、最小Alloy修复后 / alloy-event-identity-green.json、alloy-event-identity-green.txt | 0 | 15/15 PASS；两个故障均保留固定body、EventName和数字1003，关联分类/状态及脱敏保持；原10项检查继续通过 |
| 本次Release全后端构建 / event-identity-build.txt | 0 | 0 error，既有ASPIRE010 warning保留 |
| 本次全后端format verify / event-identity-format.txt | 0 | 格式通过 |
| 本次真实独立PG+Keycloak全Security / event-identity-governance.txt | 1（test子进程2） | 31项30 PASS/1 FAIL/0 skip；仍仅原分支SEC尚未补齐的OpenAPI500 metadata失败，不改只读端点或掩盖 |
| 本次Infrastructure完整测试 / event-identity-infrastructure.txt | 0 | 4 PASS |
| 本次标准SelfTest / event-identity-selftest.txt | 0 | ReviewPackage35项0失败；此前17份stdout SHA256均保持 |
| 本次固定镜像Alloy validate / event-identity-alloy-validate.txt | 0 | 无stdout，最终配置真实语法通过 |

此处证明原生exporter到实际Alloy出口，不冒充修复后真正Loki/Tempo查询。修复后完整LGTM由Master重载本次Alloy配置并复跑同一审计INSERT故障及恢复、Loki固定事件/同Trace/真实series和Tempo检查；当前此集成复验仍NOT_RUN。CI/独立复审仍由Master接续，分支保持DRAFT/PARTIAL。
