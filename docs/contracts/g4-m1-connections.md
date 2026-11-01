# G4-M1 公共合同冻结候选 1

TaskId G4-M1-CONNECTION-001；Master唯一写入；P1候选待非作者Review。唯一输入原字节存本任务input-original-bytes.json。C# G4ConnectionModels.cs是新增产品DTO权威；运行Host的OpenAPI生成TS；不得改G2模型JSON/生成代码。输入schema是设计验收，不是产品生成源。

## API与状态裁决

执行输入docs/02的16路由与六权限；新增路由只有/api/v1，真实body无schemaKind包装。所有G4 HTTP正文用G4ConnectionJson.Options显式解析，NumberHandling.Strict、RespectNullableAnnotations=true、大小写敏感；JSON未知字段、缺必填、null/布尔/字符串伪修订拒绝；五类型字段严格遵从已审G4-00。除PG外四类返回422 connector_not_enabled，不落可用连接、不建假Adapter。ResourceScope只允许可信Actor全部组织/厂区的非空子集。operator授六权限；auditor仅connection.read/schema.read且配置脱敏（PG host/database/username固定为redacted，allowedSchemas=[redacted]，port/sslMode保留；该只读投影不能提交，manage拒绝；operator可见真实非秘密配置）；viewer默认拒绝。rotate-secret同时需manage与secret.manage。

持久连接仅DRAFT/ACTIVE/DISABLED；Probe和Job独立状态。创建永远DRAFT；成功测试不启用；显式enable要求五阶段全PASS、10分钟内且配置散列/秘密版本/scope/目标策略完全相同，并重新核验源端权限。ACTIVE编辑/轮换退DRAFT。禁用使旧Probe失效、取消运行Job、拒绝任何新源调用。M1采用输入中“若policy允许”的保守分支：DISABLED终止本连接生命周期，不提供重新启用；需要新建并重新测试。

草稿Probe选择同步有界10秒实现；请求开始持久RUNNING记录，终态+审计短事务。网络中断可重发同commandId/idempotencyKey及相同请求恢复原记录，不再次调源；不存在无连接id的GET路由。失败/重启中的RUNNING到期限转TEST_FAILED，重测需要新命令。保存草稿不继承未绑定Probe，必须已保存复测后才能启用。

ETag为强引用，绑定资源revision和权威配置hash；格式"{revision}-{configHash}"。expectedRevision必须同当前正修订；创建为0无If-Match。复用G2可信Actor/授权/CSRF基础，G4在独立边界校验完整ETag，不能改变G2原纯数字ETag接受范围。缺If-Match 428，格式错误400，旧版/同key异payload409。响应GET/PATCH/创建/启停/轮换均带当前ETag。

同actor+org+operation+targetId+idempotencyKey唯一（未保存目标使用固定draft/create/intake操作域），绑定commandId和规范化请求HMAC；同键异正文409，同键同正文只返回原回执。Intake原秘密不落请求JSON/普通receipt，HMAC用服务器KEK派生用途键；唯一可返回Ref的Intake回执受actor+scope+TTL检查，绑定后拒绝再次发放。已保存test/discover/cancel也检查If-Match，完成时再次核验revision，防并发配置变化使旧结果生效。

## Secret与源安全

AES-GCM密文/nonce/tag/KeyVersion存在Connections schema；KEK只在任务私有0600文件，经Compose Secret挂载。AAD绑定org/排序sites/owner/purpose/ref/version；未绑定10分钟TTL，一次绑定、跨actor/scope/用途拒绝；绑定凭据不受Intake短TTL影响。每次调用解密当前版本；本轮禁用连接池(Pooling=false)，避免轮换后旧pool重用。秘密/Ref/密文不出现在GET；SQL/host/秘密不出现在普通日志、Trace或错误；只有具connection.manage的operator详情可见非秘密host配置，auditor使用上述脱敏投影。PG只允许固定pg-source:5432、fixture/fixture_reader/production；VerifyFull、服务端CA；拒绝Options/任意连接串、多目标及任意SQL。

PG SPI位于Connections/Abstractions/IPgSourceAdapter.cs。Adapter固定五阶段NETWORK/TLS/AUTH/READ_ONLY/METADATA；NETWORK≤3秒/完整Probe≤10秒，Discover≤20秒/100对象/2000字段/2MiB，固定白名单SQL、只读事务、取消传到Npgsql；不读取业务行，不发DML试权限。角色不能superuser/createdb/createrole/bypassrls/继承写成员/拥有对象；验证数据库CREATE/TEMP及schema/object有效写权限，权限不明fail closed。源ACL与Connection允许schema再次取交集。零对象无法证明完整可见性时PERMISSION_LIMITED，不伪EMPTY_VERIFIED。

## 存储、并发和恢复

Master唯一DbContext/Migrations，schema connections；SourceConnection/Secret/Probe/DiscoveryJob/CatalogSnapshot/CommandReceipt各独立持久记录；受控metadata与Governance ITransactionalAuditWriter同物理PG连接事务。源数据库绝不进入EF迁移。索引包含org/id、幂等actor/org/operation/targetId/key；回执另存scopeBeforeHash/scopeAfterHash（排序去重sites和org的规范化SHA256）、job状态/lease；Connection revision CAS，Secret usedAt原子绑定。探测/发现外部IO不持有平台事务；完成写入前短事务重验所有版本及授权，失败不启用。

Catalog任务先事务持久QUEUED，再BackgroundService消费；数据库claim含leaseUntil/fence/attempt，旧fence不能提交；进程重启过期任务最多重派一次或明确FAILED。取消写cancelRequested事实（不是额外wire枚举），传播到活动Npgsql并最终CANCELLED；禁用或授权/版本失效同样拒绝发布新snapshot。持久任务使用可信请求actor/session引用，在源调用及提交前检查当前会话仍存在、未过期且scope/role未撤销；不能仅信客户端或捕获的旧角色。

Fingerprint仅规范化排序的Schema/对象/字段内容+adapter版本，不含捕获时间；重复内容hash不变。快照不可变，STALE作为当前权限/配置状态投影。历史查询仍先当前scope及源访问控制，不用旧快照绕过撤权；只返回固定允许对象，不保留业务样本。

审计白名单：connection.secret.intake/create/update/secret.rotate/probe.start/probe.complete/enable/disable/catalog.start/catalog.finish/catalog.cancel（均带connection.前缀，明确为connection.create等11项），复用authorization.denied/csrf.denied。所有成功响应在事务提交后；审计故障回滚。错误code沿输入02，401/403/409/422/503及400/428/429按真实边界冻结，通用5xx无SQL/地址/秘密。

## Compose/E0/资源

唯一项目ontology-g4-m1-connection-001；source网络internal，只允许API与source同网，source不公开端口。API/Web可共享任务网络命名空间保持既有回环BFF约束，不扩大G3 Host信任。独立平台PG/Keycloak持久卷，旧G3/G6资源不挂载。必要G3兼容服务分批运行保证同时≤6容器/6GiB内存，任务卷≤3GiB、下载≤3GiB、仅127.0.0.1精确调试端口、GPU=0。registry许可/digest/平台/体积核实后才pull；Fuseki仅共享canonical镜像。

E0按G4-M1准确taskId登记路径/全部阶段消费者/审计/DI；host monitor输出真实当前taskId；cleanup扩展只接受本任务白名单/TTL/backend指纹/前后强不存在诊断，拒绝旧任务资源。先小回归/最短PG与HTTP，再49项稳定完整验收；输入不变失败先短复现。源码/格式→测试→独立Review→提交绑定→获审自身资源精确清理及回执提交→唯一V3独立重开。说明/证据提交不重跑无关产品。包外最后重开回执避免自引用。

## 独立审查必须覆盖的负例

旧创建结构/额外actor/secretInput、五类profile错字段、bool/null修订、跨scope/ref重放、TLS坏CA/SAN、CTE/函数写/SQL注入、角色继承/对象Owner、旧Probe/错ETag/异body同key、审计失败、禁用与发现竞态、lease过期旧fence、取消与刷新、撤权历史、source失败不伪EMPTY、非PG不伪成功、G2/G3原协议不变、资源身份不借G3绕过。

## P1复审修订1

PG共享安全错误仅PgSourceException.Code；network_forbidden→403；tls_untrusted/auth_failed/readonly_unverified→422；catalog_access_forbidden→403；source_unavailable→503。发现catalog_permission_limited/catalog_budget_exceeded→PARTIAL且snapshotId=null（无完整可信快照）；connection_cancelled→CANCELLED。Probe对未知阶段明确NOT_VERIFIED，不能仅因异常被包装而标PASS。Host只映射白名单，原异常不跨边界。

实测首次DTO9例：8通过1失败，Web默认允许字符串修订“0”；修正为G4专用严格选项，保持G2原始语义不变。初次两次 --filter-class 命令均零测试exit5，随后从实际MTP帮助确定 --filter FullyQualifiedName~G4WireContractTests，零测试不记PASS。

所有G4请求严格反序列化后必须调用唯一G4ConnectionRules.Validate；包括字符串长度、端口范围、五profile枚举/URI、Schema合法集合、命令零/正修订、空PATCH及Secret用途/长度。HTTP不得直接跳过规则调用应用服务。非PG配置规则通过仍返回connector_not_enabled；PG VerifyCA/Require可识别但运行Policy明确拒绝。

幂等执行顺序：当前身份/具名权限→按actor/org/operation/targetId/key查询回执→重新授权回执原scope及结果scope→比较完整请求HMAC→同请求重放原结果；只有没有回执的新命令才做当前ETag/CAS。成功编辑后的旧ETag重试可以恢复原回执，后续另一个编辑不改变该事实；重放不输出当前新版本为原回执，不再执行源IO/轮换。scope变更前后散列存在回执而不用于变化后重算查找键；丧失任一绑定scope即403，无跨scope查找旁路。
