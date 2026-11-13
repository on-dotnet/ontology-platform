# G4-M2-ORACLE-01｜A–F 一次性准入申请

2026-11-13；Master单写。[唯一任务卡](../../tasks/G4-M2-ORACLE-01.md)。用户明确批准附件P0，附件中后续实施申请不是本轮许可。Base=`5113d0b9b233e307664c964ae9bf3c1d6b10adfb`，fetch后远端相符；最终完整Head和普通push回执随交付给出。下文“申请/拟议”均未实施。

推荐唯一组合：**Oracle AI Database 26ai Free，23.26.3.0，Linux ARM64，单FREEPDB1；Oracle.ManagedDataAccess.Core 23.26.400；仓库net10.0**。官方完整容器为`container-registry.oracle.com/database/free:23.26.3.0-arm64`，冻结digest见A。存在官方原生ARM64发行，不需要预设购买Enterprise。匿名公开Bearer握手已取得tags/index/manifest，不需要用户提供账号。当前 **P0_BLOCKED_WITH_WITNESS**：用户已直接批准精确config读取，正常权限审批已放行；已有manifest/config descriptor复核通过，但一次有界读取返回非200并停止。错误处理未保存具体状态码/响应头/实际正文长度，不能判定跳转或账号要求。未保存config原件，字节/散列/JSON仍NOT_VERIFIED；未重试或换通道。产品未准入，载荷/服务/实现均未执行。已存在本机原生制品身份，不另铺替代版本、amd64仿真或第三方镜像路线。

## A｜精确版本、来源、许可和制品

| 对象 | 已核实 | 未核实/准入后检查 |
|---|---|---|
| 驱动 | 官方NuGet `Oracle.ManagedDataAccess.Core 23.26.400`，2026-10-20发布，5,661,004 bytes；catalog实际DLL位于lib/net8.0和lib/netstandard2.1。nuspec另有net6.0依赖组，不是net6 DLL | nupkg原件/签名链/内容扫描/真实运行NOT_VERIFIED；不引入Oracle EF Provider |
| 驱动平台 | 官方支持macOS ARM64≥14.7，23.26.0起支持.NET10，目标库19c及以后；仓库Directory.Build.props=net10.0，静态选net8资产 | 本机macOS27.0.1/ARM64已观测，运行NOT_RUN；未来客户19c/21c/23ai/26ai按各自精确RU/edition另验，不承诺兼容验收 |
| 数据库发行身份锚点 | 官方页列`oracle-ai-database-free-26ai-23.26.3-1.el8.aarch64.rpm`，1,355,290,892 bytes，SHA256=`e1951c4a56eb8ef8cf5d325c90525be8ddb286486f6a318e8b4c4942e10eadbb` | RPM未获取/验签；此SHA不替代容器digest，也不授权RPM安装 |
| ARM64部署 | 官方安装要求OL8.6+/UEK7、Neoverse N1能力（推荐Ampere）；Oracle容器README明确26ai Free ARM64支持。拟在现Linux ARM64 Docker VM运行 | Apple Silicon/Docker内核不是生产认证等价物；CPU指令/容器运行仍NOT_RUN，禁止自动amd64仿真 |
| 官方容器 | `database/free:23.26.3.0-arm64`，index明确linux/arm64；29层压缩合计3,527,716,613 bytes≈3.285GiB | 唯一config请求非200，正文未核验；容器实际内核/环境/组件及运行版本NOT_VERIFIED；镜像层请求为0 |

容器取得前身份：多架构index SHA256=`f988b0c04c4c386cd306a2a914c0d7a9702d83acc31b064a28ad8eb6278a8fba`，其linux/arm64描述符引用的manifest SHA256=`844b2cdb95c4cc120f549ff3b2aa36c191c8c9244bf90e6082971aaa6355f6d8`（4,962 bytes），与实际保存正文SHA一致。config descriptor的mediaType=`application/vnd.docker.container.image.v1+json`、size=29,943、digest=`sha256:dbd385a383e229ba349c103d779932a9fb24c7f92c762b5fe0420e59a1be347b`；它和29个layer descriptor严格区分。config未取得，不能称config中的architecture/labels已验证；ARM64结论来自官方index。下载时必须按arm64 manifest digest而非浮动标签；当前只申请后续取得，不执行。

驱动catalog公开SHA512(Base64)=`IBORVSidVfAxoWbeiD38CgRTNEHaAHT7GEfecUvDBdt8+PE0ZXlpspIK2tbZUp/NysPbbT638qpF2PAID/2cJg==`，仅为获取前锚点。目录含`.signature.p7s`不是验签通过；获取后才检签名链、原件散列、许可/组件和漏洞，未知不得写PASS。

现Connections锁未含下列新增闭包。拟将Microsoft候选对齐现.NET10补丁线；这不是已经restore的锁：

| System.包后缀 | 驱动net8最低版本 | 拟批准精确版本及net10下一层 |
|---|---|---|
| Collections.Immutable | 10.0.3 | 10.0.13，无下一层 |
| Diagnostics.PerformanceCounter | 8.0.0 | 10.0.13 → Configuration.ConfigurationManager 10.0.13 |
| DirectoryServices.Protocols | 8.0.2 | 10.0.13，无下一层 |
| Formats.Asn1 | 8.0.1 | 10.0.13，无下一层 |
| Security.Cryptography.Pkcs | 8.0.1 | 10.0.13，无下一层 |
| Text.Json | 10.0.9 | 10.0.13，无下一层 |
| Memory | 4.6.3 | 4.6.3，netcoreapp2.1/netstandard2.1空依赖组 |
| Configuration.ConfigurationManager | 间接 | 10.0.13 → Diagnostics.EventLog、Security.Cryptography.ProtectedData，各10.0.13 |
| Diagnostics.EventLog / Security.Cryptography.ProtectedData | 间接 | 各10.0.13，net10依赖组为空；批准后restore最终选择核验 |

Microsoft nuspec声明MIT；Windows计数器/EventLog/DPAPI和LDAP不启用为功能，不把依赖存在当Mac可调用。Shared framework可能消解部分资产；当前中央版本/锁均未改，最终恢复结果和下载量须批准后验证，额外包不得自动扩张范围。

数据库：[Oracle Free Use Terms and Conditions](https://www.oracle.com/downloads/licenses/oracle-free-license.html)允许有条件内部开发/测试；[官方Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/26/dblic/Licensing-Information.html)将Free关联此许可，Free限制2 CPU、2GB数据库RAM、12GB用户数据。驱动精确包为[Oracle Free Distribution, Hosting, and Use Terms and Conditions](https://www.nuget.org/packages/Oracle.ManagedDataAccess.Core/23.26.400/License)，不是数据库许可。requireLicenseAcceptance=false不等于没有条款。用户需确认代表使用主体有权按条款取得/使用；既有协议优先适用及出口/分发义务待裁决。公开Registry元数据匿名可读，无账号登录/条款接受操作；未来载荷取得若出现条款或账号要求即停止由用户走系统流程。本轮不代签、不注册试用，不继承DORIS-LOCAL-01/AMBER-A1。

**申请A**：批准精确驱动/候选闭包及Free目标，仅本机隔离合成非分发。先闭合失败的config元数据核对并验证digest/size、另行确认许可，核上述身份/总量与D预算并独立确认获取准入，再取得载荷；原件/安全检查通过才启动。没有无上限pull授权，也不授权基于RPM另行构建/安装。数据库镜像签名、SBOM、漏洞状态NOT_VERIFIED。

## B｜TLS、最小权限、取消和类型边界

TLS拟固定`oracle-source:2484/FREEPDB1`、`Tls=true`、TCPS；服务器目标表绑定host/port/service/PDB/username/owners/scope/信任配置及实际解析地址，拒任意描述符、TNS alias、地址列表、LDAP/proxy、wallet URL、隐式fallback或未知重试。连接后核PDB身份，证书host通过不证明目标PDB正确。

[官方连接文档](https://docs.oracle.com/en/database/oracle/oracle-database/26/odpnt/featConnecting.html)支持TLS1.2/1.3、SSL_SERVER_DN_MATCH=true和可选SSL_SERVER_CERT_DN；不设DN时hostname匹配。要求链/有效期/SAN或host全部通过，不关闭验证。免wallet模式依赖系统信任，自定义合成CA不能因此改Mac全局信任：拟每连接指定任务只读文件wallet存CA，服务wallet存服务证书/私钥，不启用客户端证书认证/SEPS。驱动为托管DLL无需Oracle客户端运行库；建wallet可能用数据库镜像内已有orapki，官方说明它仅建wallet需要、不必部署到客户端，其实际存在仍待原件核验，不额外安装Instant Client。私钥/KEK仅外置0600/只读挂载，不进Git。本轮证书、坏CA/过期/错SAN/错服务/PDB实测均NOT_RUN。

最小只读：PDB本地`FIXTURE_READER`，无自有业务对象/配额/写/DDL/授权能力，仅CREATE SESSION及两合成owner对象直接READ，无WITH GRANT OPTION。优先READ而非SELECT，避免FOR UPDATE/锁权限扩大。ALL_TABLES/ALL_VIEWS/ALL_TAB_COLUMNS与allowedOwners精确交集，不用DBA_*，不授DBA、SELECT_CATALOG_ROLE、SELECT ANY DICTIONARY或ANY TABLE。禁止业务值、统计LOW_VALUE/HIGH_VALUE、默认表达式内容和用户SQL。

只读证明涵盖SESSION_PRIVS、USER_SYS_PRIVS、USER_TAB_PRIVS、启用/嵌套角色、PUBLIC、所有权及可写definer-rights过程；仅SELECT授权不足。fixture管理员导出合成授权清单与运行账号目录交叉核对，不能完整排除继承写能力时READ_ONLY=NOT_VERIFIED并拒Enable；不为自证给reader广域字典权。测试控制面管理员仅创建/撤销合成授权，产品不持管理凭据、不发DML探权；控制器验证DML/DDL/GRANT/锁表拒绝、角色/直接权限差异、跨owner拒绝和撤权后Probe/Enable/Discover/Catalog历史访问关闭。空目录不直接判完整可见，沿用permission_limited/无可信快照。

取消：[Cancel](https://docs.oracle.com/en/database/oracle/oracle-database/26/odpnt/CommandCancel.html)发送取消请求但非成功保证；[pipelining文档](https://docs.oracle.com/en/database/oracle/oracle-database/26/odpnt/featAsyncPipelining.html)明确启用时不支持Cancel/超时/token取消。因此固定关闭pipelining、Pooling/自动重试/HA恢复，一物理连接一在途命令；OpenAsync/ExecuteReaderAsync/ReadAsync传真实token、有界超时并Dispose，不用Task.Run冒充。

拟沿用Probe10秒、Discover20秒/100对象/2000列/2MiB。独立fixture见证账号只获按reader/任务标记过滤的会话状态窄视图，管理者建视图，不给产品V_$SESSION；记录SID/SERIAL#/SQL_ID或执行标记、操作开始/取消/不再执行/连接结束。真实有界延迟fixture目录场景分别证明调用方停止等待、驱动取消、源端操作结束；只有Task取消无源端见证不PASS，区分源端完成竞态与取消。会话IDLE不等于操作继续。

[ALL_TAB_COLUMNS](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/ALL_TAB_COLUMNS.html)可表达原名、类型、ordinal、nullable、precision/scale。NUMBER未声明保留null、负scale不改0，不能默认(38,0)；DATE保留Oracle含时分秒语义；TIMESTAMP(p)/WITH TIME ZONE/WITH LOCAL TIME ZONE区分，保留小数秒精度不推断时区。CLOB/NCLOB/BLOB/BFILE只读类型，不读值；未知类型不改VARCHAR。owner/列按字典原字节与Ordinal比较，不Uppercase quoted名字；现规则≤63 ASCII子集可覆盖`PRODUCTION`与`CaseOwner`，明确拒绝特殊字符/Unicode/超长quoted输入，不宣称支持全部128字节标识符。

**申请B**：批准TCPS文件wallet、单目标/单PDB、最小READ、独立控制面见证与取消/类型边界；真实证据不足停止对应能力，不能借其他连接器PASS。

## C｜ORACLE_READONLY与完整生命周期

源码核对：`backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionModels.cs`、`G4ConnectionRules.cs`；Connections模块`Application/ConnectionSourceDispatcher.cs`、`ConnectionApplicationService{,.Commands,.Probes,.Enable,.Catalog,.Worker}.cs`、`ConnectionSecretCipher.cs`；API/G4与Web connections。

已有Oracle profile含host/port/serviceName/username/tls/allowedOwners；Purpose为string，Secret记录/AAD已有purpose/owner/org/sites/ref/version。无需重复新增Username。现public校验仅PG/Web/Doris用途，Oracle Tls=false仍可解析预览；dispatcher拒Oracle，UI runnablePurpose=null。申请独立**ORACLE_READONLY**及强制TLS、OracleOptions/SPI/adapter/DI/固定目标规则，复用OpenAPI→TS链；不复用PG/Doris凭据语义，不改现有路由/角色集合。

| 链路 | 现有机制及Oracle增量 |
|---|---|
| Intake | 10分钟TTL/一次绑定，actor owner/org/精确scope/purpose、AES-GCM/HMAC；加新Purpose。Intake无target字段，首期仅单一服务器固定Oracle目标/账号以阻止跨目标复用；未来多目标须另批持久绑定，不能假称已有 |
| Create/draft Probe | Source先核目标，UnboundSecret核owner用途scope/TTL；Create原子消费Ref为DRAFT，不继承draft probe。Oracle消费/解密前核固定host/service/user/owners，跨actor/scope/用途拒绝 |
| saved Probe/Enable | configHash/secretVersion/期限和当前session；Enable重新真Probe并CAS。Oracle需五阶段含真实TLS/只读，安全异常映射兼容既有捕获链 |
| Discover/Worker | ACTIVE/fresh→事务排队，捕获actor/session/revision/hash/version/scope；lease/fence、250ms观察、提交重验。Oracle真实token贯通，不准旧fence/旧版本发布 |
| Catalog/历史 | 当前scope/BoundSecret/真实Discover求可见交集/STALE；Oracle精度元数据参与比较/fingerprint。现CanonicalCatalog非Web用pg-m1-v1，新增oracle-m2-v1且保持旧分支字节 |
| rotate/disable | 新Ref核当前命令owner/scope/purpose，版本递增、旧密文清除、退DRAFT、失效Probe、取消job；禁用终止且不新触源，旧池关闭 |
| patch/幂等/CAS/审计 | 复用ETag+revision、HMAC同键异body拒绝、重放授权、审计同事务；新增Oracle DemandSameTarget及DemandSameCredentialScope。target所有字段/username/owners/scope变更必须新建+新Ref；只显示名可编辑，不能旧secret静默换目标 |
| UI/脱敏 | 复用创建/详情/轮换/probe/catalog；开放Oracle用途/执行，TLS不可关闭，TDengine仍预览；补auditor Oracle脱敏（目前只有PG/Web/Doris），秘密/SQL/host不进普通日志 |

固定单目标政策下用途字符串无需加数据库列；不代表任意目标密钥绑定已存在。BoundSecret不要求当前operator等于原Intake owner：沿用资源operator权限，owner是来源/AAD，未绑定Ref跨actor仍拒绝；不擅改为原owner独占管理。申请C为上述用途/目标/完整生命周期变更，均未实现。

## D｜单机预算、网络和资源

本轮2026-11-13约14:04–14:05 CST观测：Mac18,5/ARM64、12逻辑CPU、32GiB；Docker desktop-linux/Engine29.9.2/aarch64、12 CPU和16,787,419,136 bytes（约15.63GiB）VM内存。ps空，0容器、20镜像19.19GB、12卷635MB、build cache2.925GB；未清理。df可用280,800,000 KiB≈267.79GiB；vm_stat free597022×16384≈9.11GiB，不是持续可分配保证。首次sandbox sysctl/socket拒绝不记0容量，升级只读权限后获得观测。Docker VM包含在宿主物理内存内，不重复加算。

| 未来项 | CPU/RAM上限提案 | 说明 |
|---|---|---|
| Oracle源容器 | 2 CPU/4GiB | 数据库仍受Free2GB限制，额外为OS/工具开销 |
| 平台PG、OIDC容器 | 各1 CPU/各1GiB | 独立合成卷 |
| 宿主API/Web/测试浏览器与runner | 合计4 CPU/4GiB | build/浏览器错峰，不重复计入VM |
| PG/Web源及Doris回归 | 串行按原预算 | 停Oracle后再跑Doris，不授权二者同时启动 |

Oracle场景容器合计4 CPU/6GiB；宿主4GiB+VM上限15.63GiB+宿主保留10GiB≈29.63GiB≤32GiB（规划非实测峰值），总活跃预算8 CPU。出现旧任务并发/内存压力即错峰/停止，不改VM。启动前重新核可用量。

分别预算：驱动5.66MB，Microsoft闭包压缩总量UNKNOWN（拟包下载合计≤128MiB）；Oracle29层压缩量3,527,716,613 bytes≈3.285GiB（manifest声明，未下载，拟≤4GiB）；展开/初始化UNKNOWN（拟镜像≤12GiB、源卷≤16GiB；官方安装至少10GB），合成用户数据≤256MiB包含在源卷内；平台卷≤2GiB、日志/证据≤1GiB、私有依赖/构建缓存增量≤4GiB。保守磁盘峰值≤40GiB含载荷保留和展开，未知不填0。共享缓存命中UNKNOWN，未验内容键不扣下载量；超过限额停申请，不掩盖超量。

内部仅TCPS2484、PG5432、OIDC8080；Oracle1521只容器内管理，不给adapter/host发布，禁5500/ORDS。source网internal，仅API/runner可达；必要调试仅127.0.0.1，API/Web候选5100/3000沿既有BFF回环规则，启用前核端口。证书/私钥/KEK/密码外置，不写明文Compose环境变量。前缀`ontology-g4-m2-oracle-01`，准确TaskId/RunId、卷ID/镜像digest/context/时间创建即记录；仅本任务关闭且无引用的合成资源按白名单before-command-exit-after及强后验回收，旧树/Doris卷/TDengine保护。

申请D为预算与网络原则；长验收前host_continuity preflight、用户能源策略确认和有界实测，不继承其他会话长期保证。本轮没有长产品任务、服务或下载载荷。

## E｜后续源码范围、元数据和部署

CatalogField只有Name/NativeType/Nullable/Ordinal/Precision/Scale，能保留NUMBER null/负scale和基础LOB类型，不能结构化保存字符字节语义、类型owner、时间小数秒精度及支持状态；不能滥用Scale或NativeType塞私有JSON。

申请可选`CatalogField.OracleMetadata`，仅Oracle输出，旧类型省略且不改旧fingerprint字节。字段：`dataTypeOwner:string?`、`byteLength:int?`、`charLength:int?`、`charSemantics:BYTE|CHAR|null`、`fractionalSecondsPrecision:int?`、`timeZoneKind:NONE|WITH_TIME_ZONE|WITH_LOCAL_TIME_ZONE|UNKNOWN`、`supportStatus:SUPPORTED|METADATA_ONLY|UNSUPPORTED`。NativeType保持原生，NUMBER precision/scale null表示未声明；LOB为METADATA_ONLY，未知类型UNSUPPORTED且不发布完整可信目录，缺失不能默认SUPPORTED。旧快照保持缺省语义；实施前固定null/省略/排序、历史投影与生成合同并非作者Review。现JSON快照/Config存储预计无需新列，但确有JSON语义变化；若需迁移，另列精确裁决。quoted owner先保留ASCII子集大小写，不顺带放宽所有连接器规则。

后续owned_paths候选（本轮全部只读，共享文件Master唯一写）：

| 模块 | 路径及范围 |
|---|---|
| Oracle实现 | `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Abstractions/IOracleSourceAdapter.cs`、`OracleAdapterOptions.cs`；同模块`Adapters/OracleSourceAdapter.cs`与`.Sql.cs`新增；`Application/ConnectionSourceDispatcher.cs` |
| 生命周期 | 同模块`Application/ConnectionApplicationService.cs`、`.Commands.cs`、`.Probes.cs`、`.Enable.cs`、`.Catalog.cs`、`.Worker.cs`按C差距最小变更；保持PG/Web/Doris既有策略 |
| 公共合同/API | `backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionModels.cs`、`G4ConnectionRules.cs`；`backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs`、`G4OpenApi.cs`、`G4ContractExport.cs`；`docs/contracts/g4-m1-connections.md`、`g4-connections.openapi.json` |
| Web/生成 | `apps/web/src/features/connections/form-model.ts`、`form.tsx`、`create.tsx`、`detail.tsx`、`catalog.tsx`、`connections.test.ts`；生成`apps/web/src/lib/api/g4-generated.ts`，沿现export链 |
| 包/测试 | `Directory.Packages.props`、Connections模块csproj/锁；受传递影响API/ConnectionsTests/SecurityTests/G2ContractTests锁，restore差异后冻结不预批全仓升级；ConnectionsTests新增OracleAdapterTests/OracleFixtureSecurityTests并改SourceDispatcherTests，G2ContractTests/G4WireContractTests及SecurityTests既有G4用例 |
| 工程消费者 | `scripts/maintenance/workflow.py`、`workflow_environment.py`、`workflow_m2_build.py`、`execution_preflight.py`、`docs/development/verification-gates.json`；拟新增任务薄适配`workflow_m2_oracle.py`、`workflow_oracle_fixture.py`、`workflow-oracle.mjs`，准确文件清单实施前冻结；复用workflow_execution/evidence/结果解析器，不复制公共执行器 |
| 部署源码 | 新增`infra/oracle/compose.yaml`、`compose.test.yaml`、`compose.platform.yaml`、`compose.production.yaml`、`.env.example`与`config/`模板、`docs/deployment/oracle.md`；不带第三方二进制/私有wallet或擅自再分发许可载荷 |

工程实况：execution_preflight支持G4-M1/Doris但无Oracle；workflow_environment无Oracle缓存/restore消费者。Oracle产品入口**BLOCKED：任务适配器缺失**；不能借Doris TaskId或旧M1全链启动。作为本任务最小适配，不另开优化/恢复任务。

部署文档包含单机源库/平台拓扑、隔离测试覆盖、账号/信任分离、轮换/撤权、卷和wallet备份及隔离恢复、精确版本升级/回滚、日志预算/回收。保留G4Composition非Development拒绝及生产自动迁移Guard；生产参考模板G4显式禁用/待授权，不能伪装Development，不等于生产部署/容量验收。

## F｜集中裁决和门禁

请一次裁决：**A**精确依赖/官方来源/许可与条件取得；**B**TCPS文件wallet、最小READ、取消和独立见证；**C**ORACLE_READONLY及固定目标/账号/owners/scope与生命周期；**D**单机预算/网络；**E**DTO/JSON语义、源码候选及Compose/部署；**F**以下门禁与同树继续。config元数据阻断关闭前，批准仅是条件性设计裁决，不启动实现或载荷下载。

2026-11-13用户已直接明确批准下列唯一config JSON元数据（29,943 bytes），包括此精确/blobs/路径，不含任何镜像层：

`https://container-registry.oracle.com/v2/database/free/blobs/sha256:dbd385a383e229ba349c103d779932a9fb24c7f92c762b5fe0420e59a1be347b`

历史两次自动审批拒绝保留于原提交及索引；本次正常审批已放行，不能继续写成审批缺失。执行前重新解码已有manifest，SHA256、config digest/size/mediaType与非layer身份均通过；沿用官方匿名认证，临时token不打印/保存；TLS正常，禁止自动重定向，正文上限29,943字节（最多额外读取1字节用于超限检测，超限即停）。唯一config请求返回非200，程序exit1并立即停止，没有跟随跳转、重试或换通道，没有保存config。

本次取证缺口：断言在保存失败诊断前退出，具体HTTP状态、响应头、正文长度/散列未留存，不能说是跨域跳转、账号问题或内容不匹配；config大小/散列/JSON解析均NOT_VERIFIED。最小后续事项为对这一精确对象的非200响应作保留状态/长度的有界诊断，再裁决是否允许后续请求；本轮按停止要求不再发请求。用户无需再次批准已经明确的config范围，不请求密码/token。

本次授权不接受Oracle许可、不批准A–F实施项。仍需集中裁决许可/载荷取得、精确依赖、TLS/权限/取消、ORACLE_READONLY、DTO/生命周期、资源和部署范围；产品实施继续未授权。

后续顺序：A身份/许可/预算→非作者获取准入→精确载荷及原件/安全核验→合同/ownership冻结Review→Oracle工程消费者与批准后prepare/restore/锁→最短真ARM64/TLS/权限/撤权/取消/类型→真OIDC与完整生命周期/UI→按影响PG/Web/Doris共享回归→最终独立Review/提交绑定/资源后验/规定交付。本轮禁止的后续动作不会提前执行。

真实验证覆盖坏CA/过期/SAN/错误service/PDB、直接/继承/PUBLIC权限和撤权、源端取消见证、大小写/NUMBER负scale/日期TZ/LOB、跨actor/scope/用途/旧Ref/旧版本/旧Probe、并发CAS/同key异body、审计失败回滚、注销/fence/重启与取消竞态、auditor脱敏。合法来源/原件门禁在服务前，不用mock顶替。input不变旧证明须核原件资格后才REUSED，不重跑无关全链/无变化自然TTL。失败先短定位，无新假设不重复扩大搜索。

CI按需NOT_RUN；Mac宿主/LinuxARM64容器分列，Windows/x64/生产NOT_RUN。供应链未核项NOT_VERIFIED；没有产品PASS。本P0仅两份材料、无ZIP、不更新main；后续同会话同树继续，不进M3/M4、不恢复TDengine。

## 来源、轻量检查和独立审查回执

[metadata/index.json](metadata/index.json)为唯一恢复索引；旧32份公开原件按内容hash/base64保存，解码后核长度/SHA，原字节不改。本次匿名认证200响应2,300字节只留URL/时间/状态/长度/hash，不留token正文；记录合计38响应/831,477 bytes，另有1次非200 config响应缺长度记录，实际总量UNKNOWN，保守上限861,420 bytes（失败正文上限29,943计入），仍低于64MiB。不得将失败正文算0或把已记录量写成完整网络流量；HTTP头/TLS/搜索服务开销不在正文计数中。唯一config对象未保存，未请求任何镜像层，返回内容未执行。

官方入口：[精确驱动](https://www.nuget.org/packages/Oracle.ManagedDataAccess.Core/23.26.400)、[运行要求](https://docs.oracle.com/en/database/oracle/oracle-database/26/odpnt/InstallSystemRequirements.html)、[数据库发行](https://www.oracle.com/database/free/get-started/)、[原生部署要求](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinl/requirements.html)、[容器说明](https://github.com/oracle/docker-images/blob/main/OracleDatabase/SingleInstance/README.md)、[权限指南](https://docs.oracle.com/en/database/oracle/oracle-database/26/dbseg/guidelines-securing-user-accounts-and-privileges.html)。滚动页面只证明本次快照，恢复按原件索引。

非作者只读Reviewer=`/root/oracle_p0_review`完成同一轮审查，初次发现1项P1：401/302不足以证明需要用户登录/外部资料。Master据新假设检查WWW-Authenticate、完成匿名握手，取得tags/index/manifest，已撤销该错误推断；没有重复无条件搜索。当时最小阻断为自动审批config读取边界（本次已放行，转为非200读取失败），原401/302与两次审批拒绝均保留。同一Reviewer完成修正复核：原P1关闭，无新增阻断级文档问题；确认精确平台/大小/descriptor与原件，未认证config正文或产品。Reviewer首次误把base64文本当原字节校验失败，按encoding解码复验exit0，保留该检查纠正而不称原件损坏。

轻量检查：原件base64解码/长度/SHA256、官方index→arm64 manifest→config descriptor绑定、文档相对链接/EOF、授权纯追加与写路径白名单、最终git diff --check；原P0检查exit0：37响应/829,177 bytes（认证正文不保留6,906 bytes），32份去重原件、4相对链接、所有原件散列/manifest绑定/授权纯追加/owned_paths通过；可恢复检查源码及SHA在索引metadata.localCheckSource。`pwsh -NoProfile -File scripts/test-review-evidence.ps1 -EvidenceFile docs/evidence/G4-M2-ORACLE-01/metadata/index.json`已实测exit0（仅EVIDENCE_SCHEMA_ONLY，产品NOT_RUN）。新证据完成后重复同一廉价检查，不跑历史全量。产品/CI/跨平台/生产NOT_RUN，不用历史结果充本轮通过。

开工保护：项目.codex仅agents配置，未发现项目setup入口；原生create_worktree只创建/注册checkout，未调用安装/restore/服务。fetch首次受FETCH_HEAD权限限制，获范围权限后exit0并核main；任务分支创建和文档写入首次受沙箱限制，获范围权限后完成，未退回main写。只读宿主/Docker首次权限失败保留于本摘要，不把空格式输出当0资源。当前无本任务容器/卷，唯一持久新资源为任务分支/托管树与公开证据，KEEP供同会话后续，禁止借收尾清理旧资源。

本次增量保护：fetch正常审批后exit0，origin/main仍为预期Base；当前树新出现的`docs/.DS_Store`与`docs/evidence/.DS_Store`未跟踪文件保留，不纳入提交。只更新本卡/申请/索引及追加本次授权，不动产品、锁、脚本、main或TDengine。增量原件/manifest/链接/EOF/写范围检查、证据schema及diff-check均exit0；同一非作者Reviewer复核通过（仅文档/证据），记录在索引configIncrementReview；读取失败仍为FAIL，config内容未验。
