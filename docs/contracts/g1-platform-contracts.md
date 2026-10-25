# G1 平台公共契约 V1

状态：FROZEN（实施前87eb51a独立契约审查通过，运行时语义门禁已补），2026-10-25。人类正式批准Wave2 Mac V2全范围；本契约由Master单写，独立Review通过的提交为三线实现基线，变更先提议Master。BaseSha=e930935749bcb88d51abb94db4a41695bbbe6717。M0历史PARTIAL不改写，G2未授权。

## 入口和路由

开发BFF源http://localhost:15100（第二实例15101）；Next内部http://127.0.0.1:15300；Keycloak18080；全部只回环，生产必须HTTPS、明确AllowedHosts/可信代理，不能沿用开发HTTP豁免。正式宿主OntologyPlatform.Api，与InfrastructureApi分开。YARP同源代理Web路径，/auth、/api、/health、/openapi保留给.NET，不把认证Cookie/Authorization转给外部源。Next内部SSR用配置的可信PLATFORM_API_ORIGIN访问BFF，显式转发Cookie，cache:no-store；禁止从请求Host构造任意上游或将上游地址/秘密放NEXT_PUBLIC。浏览器只调用同源相对路径。

| 路径 | 语义 |
|---|---|
| GET /auth/login?returnUrl=/ | OIDC confidential code+PKCE、state/nonce；只允许本地returnUrl，禁止//、反斜线/控制符/外部URI |
| GET /signin-oidc | 标准OIDC回调，ResponseMode=query使开发HTTP的Lax关联Cookie可用；无效回调400通用ProblemDetails，无敏感远端错误 |
| GET /signout-callback-oidc | 标准注销回调，返回/signed-out |
| GET /auth/csrf | ASP.NET Antiforgery返回{requestToken}；仅用于CSRF，不是身份token；响应no-store |
| POST /auth/logout | 认证+内置Antiforgery表单字段__RequestVerificationToken（也接受X-CSRF-TOKEN）；必须原生form POST顶层导航以接收OIDC302，不能用fetch跟随跨源注销；撤销PG服务器会话、记录审计、清Cookie并完成Keycloak注销，最后/signed-out；缺CSRF=403 |
| GET /api/v1/platform/me | 匿名/过期/坏Cookie401；已认证200，含subjectId/displayName/roles/scopes，不含JWT/认证属性/token/秘密Claim |
| GET /api/v1/platform/resources?siteId=site-a | viewer或operator；只返回自身organization/site；显式请求越界site403，空合法作用域可为空列表 |
| GET /api/v1/platform/resources/{id} | 同角色+行级组织/厂区检查；本轮已知样例跨厂403，未知id404；无角色403 |
| GET /api/v1/platform/audit?limit=20 | auditor角色且按组织/厂区过滤，limit1..100，非法400 invalid_request；支持审计ID与TraceId关联，禁止匿名读取 |
| GET /health/live、/health/ready | 正式API在Development/Production均有真实探针；仅有效X-Health-Key内部编排访问，错误key401；live不依赖PG，ready依赖真实PG，故障503且不泄露连接信息 |
| GET /openapi/v1.json | OpenAPI3.1；开发回环可读供生成/校验，生产禁匿名；实际导出由Master与冻结schema核对 |

Web根页SSR遇/me401则重定向/auth/login?returnUrl=/；/signed-out为公开注销后登录面板。已认证无资源角色仍可/me200，资源403显示真实无权状态。运行中401、403、503/网络错误必须区分，不能Mock成功。静态资源可匿名但不包含秘密；Next不重复后端授权。

## 身份、会话与安全

可信Claims来自验证通过的Keycloak issuer/audience/签名；只映射批准realm角色platform.viewer/platform.operator/platform.auditor及organization_id、site_ids。不信任角色/厂区请求头。Cookie为HttpOnly、SameSite=Lax，生产Secure=Always，开发只回环SameAsRequest；固定30分钟无滑动续期，需重新认证，不无限续期。state/nonce关联Cookie使用Lax及环境适当Secure；生产全部安全。API返回401/403 ProblemDetails而非302跳转。

必须使用真正ITicketStore服务器会话：PG保存加密AuthenticationTicket/过期/撤销状态，Cookie只承载受保护的随机会话引用；OIDC SaveTokens即使用于标准注销也只保存在加密服务器ticket，不让JS/SSR HTML/localStorage获得JWT。注销后旧Cookie重放必须401，过期行不再读取。认证/协议日志、Hosting.Diagnostics默认请求query日志必须抑制或净化，不能输出code/state/id_token/cookie/密码/敏感Claims。测试输出/截图/失败日志同样脱敏，不提交Playwright含登录网络信息的trace/HAR。

DataProtection必须相同ApplicationName、共享显式持久keyring、X509证书加密，缺路径/证书/密码启动失败，不静默回落进程内Key或未加密文件。开发证书由本轮隔离工具新建，不安装系统信任；文件0700/0600、Git忽略；生产用外置证书/权限边界，文档说明轮换及保留旧证书解密。双实例从同一PG会话和共享加密keyring实测，不靠内存缓存模拟。

默认不处理ForwardedHeaders；只有显式非通配可信代理列表才启用且ForwardLimit=1、校验对称和主机；回调外部origin来自验证配置，不由不可信Host/Forwarded头派生。默认拒绝，非法issuer/client/public origin/keyring/连接配置启动或验证失败。CSRF用内置Antiforgery，POST logout验证内置表单字段或header（浏览器采用原生form，避免fetch跨源重定向）；写操作不得使用GET。允许本轮认证/会话变更，不创建本体业务写入口。

## 最小合成资源及审计

模块OntologyPlatform.Modules.Governance拥有专属GovernanceDbContext和governance schema；不跨模块写表，不建Repository/UoW。服务器会话、审计和平台开发资源分别建表；迁移及顺序由Master写入/生成，SEC提供模型/DesignTimeFactory，不能自行抢写Migrations。ApplyMigrations/SeedDevelopmentResources必须显式开发配置，生产禁止自动seed。两个PG样例platform-site-a、platform-site-b，org-demo的site-a/site-b，中文名称与status=SyntheticDevelopment；真实数据库查询/授权/审计，合成数据明确标记而非硬编码成功响应。

安全测试realm与client每次使用独立前缀，复用同一测试卷重启时保持秘密配置；不改已有realm/用户/卷。身份名wave2-viewer-a、wave2-viewer-b、wave2-no-role-a、wave2-operator-a、wave2-auditor-a，密码全部运行时随机，不提交真实企业身份。viewer-a只读a、viewer-b只读b、no-role有身份无资源角色、operator-a可读a，auditor-a可查a审计；组合角色由开发mapper明确配置。

审计字段id/occurredAtUtc/actor/action/resource/outcome/traceId/correlationId/organizationId/siteId；事件authentication.login、authentication.logout、platform.resource.read、authorization.denied、csrf.denied、configuration.changed（仅有真实配置变更时使用，不捏造）。关键允许/拒绝写入PG后才能声明审计成功；会话增删与对应审计尽量同DbContext事务，失败关闭且ready失败，不能只写Loki代替。没有本体发布写入，不宣称发布审计完整。

所有API返回X-Trace-Id；资源读取/拒绝有已提交审计时返回X-Audit-Id，关联ID输入仅接受1..64位字母数字点横线，否则服务端新建；响应X-Correlation-Id。ProblemDetails包含status/title/type及code/traceId/correlationId，detail通用，不含异常栈、秘密和数据；code包括unauthenticated/forbidden/csrf_failed/resource_not_found/invalid_request/dependency_unavailable/oidc_callback_invalid。JSONcamelCase，UTC时间RFC3339，ID为字符串，scopes数组结构{organizationId,siteId}。

## 公共DTO/客户端

Master单写API的Contracts目录以及docs/contracts/g1-platform.openapi.json；SEC只消费并通过Results等返回。类型为PlatformIdentity、PlatformScope、PlatformResource、PlatformResourceList、PlatformAuditEntry、CsrfResponse；原生ProblemDetails扩展，不做万能共享库。真实OpenAPI导出要与契约的路径/状态/DTO语义核对。FE先执行Kiota1.36.1的真实PoC；当前微软TS运行包官方latest为preview，不将预览运行依赖直接引入产品。可采用内置fetch+从冻结/导出的OpenAPI生成的类型适配，记录生成/取消/401/403/空值维护证据；不擅引Hey API或其他SDK。

## 遥测、运维及行为事件

API ActivitySource/Meter=OntologyPlatform.Api，OTEL_SERVICE_NAME=ontology-platform-api，service.version来自提交/显式配置，deployment.environment.name=Development；生产配置显式。SEC负责API内Activity/LoggerMessage/Meter挂钩；OBS不编辑SEC端点，不建立第二条管道。API OTLP→Alloy→Loki/Tempo/Prometheus，Master配置API OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:14328，protocol=http/protobuf；Alloy容器端4318。AppHost Dashboard保持已有Infra遥测价值，不用它冒充LGTM。

只允许service_name/environment/version及有限method/route/status_class等索引标签；actor/site/trace/auditId不能做无界Prometheus/Loki索引标签。traceId/auditId作结构化元数据和关联字段，不输出请求体/查询字符串/cookie/token。logger只记录固定path/状态/eventcode。自定义计数platform.requests与耗时直方图有真实HTTP请求数据；注册Meter必须由API或宿主技术配置明确完成。

OBS资源建议固定开发端口：Grafana15330、Loki13100、Tempo13200、Prometheus19095、Alloy管理12345、OTLP14327/14328。资源镜像精确版本+index SHA且ARM64真实核验，配置/卷/用户权限/低基数规则登记；本地文件存储明确，不声称RustFS S3兼容。共享AppHost注册由Master写，OBS提供infra/observability资源清单/配置，保持唯一编排模型。真实告警可用受控API进程停启或内部只读health失败模拟触发，不新增公开故障写入端点；只写本地通知/可检索状态，不向外部消息服务发送。

中文仪表盘系统总览/API性能/依赖健康/错误及Trace关联；实际数据与截图来自真实查询。/api/v1/platform/audit按服务端权限可关联合成资源的TraceId/审计ID。Faro/行为分析仅定义独立结构{eventId,eventType,schemaVersion,occurredAtUtc,consent,scope,traceId}，先授权/同意、排除敏感正文；不将普通日志冒充可靠分析存储，本轮不建设完整ProductAnalytics。

## 验收与变更

真实Keycloak登录/回调/退出、Cookie坏例/过期/重放、CSRF、错误回调、伪造Forwarded、角色/跨厂区、双实例共享加密keyring/PG会话；PG审计、重启持久化。真实Web lint/typecheck/test/build+Playwright1280/宽屏/键盘/主题持久化/加载/网络错误和完整OIDC闭环；Console无水合/焦点错误。真实Loki/Tempo/Prometheus查询、中文Grafana、告警触发/恢复及持久化。原4项Infra测试保留。Windows本轮无主机则NOT_RUN并给复现命令，Linux现有CI必须不退化。任何核心失败总PARTIAL/BLOCKED，未跑不算PASS。

独立契约审查修订：浏览器退出采用原生form POST及隐藏__RequestVerificationToken，允许内置header用于其他客户端但不能用fetch跟随OIDC跨源注销。错误媒体类型统一application/problem+json，type字段必须存在（默认about:blank）；audit limit非法明确400 invalid_request。本修订在任何产品并行写入前完成。

遥测实施增量：API同一Meter增加platform.heartbeat ObservableGauge，值为当前UTC Unix秒，无单位/无用户厂区标签；导出周期5秒。OBS用time()-heartbeat/absent判断真实API停启，避免缓存旧计数冒充存活；Prometheus归一化名以实际查询为准。本地告警时间阈值明确不是生产SLO。

## G1-CLOSE-001 收口增量（当前授权）

成功审计读取在响应前提交platform.audit.read/platform.audit/allowed；空集合也记录。先物化再写入，本次不包含自身、后续查询可见；并发按PG实际快照可见性，不递归写。新增scopeSiteIds结构化厂区数组，可信claims去重排序，显式单厂来自已授权资源；单厂SiteId兼容，多厂/空范围SiteId=null。普通审计API仅允许同非空组织且完整非空数组是调用者厂区子集；legacy null/空数组隐藏，旧首厂无法恢复真实范围，保留原事实不自动补写。新增500 internal_error通用错误，原401/403/OIDC400/PG503保留。原始异常/SQL/输入/秘密不能进Problem或日志/Span。诊断事件1003 PlatformRequestFault固定Route/ExceptionCategory/Outcome/Status/TraceId，不接受Exception；字段仅结构化元数据，不增加索引或指标维度。完整时序、分类及迁移恢复门禁见本轮总卡。
