# G4-M2-ORACLE-01｜A–F 一次性准入申请

> 最新覆盖裁决：用户明确接受当前冻结镜像的本机开发漏洞风险并要求继续；漏洞原件与历史阻断保留，当前状态为READY_FOR_REVIEW。生产/正式验收使用用户已授权的一体机，不在本轮操作范围。无需换版或再次风险审批；其余A–F、预算/隔离/TLS/只读与main/TDengine边界保持。

> 最新裁决（2026-11-13）：用户明确批准现有A–F条件实施，并批准镜像展开13GiB、总峰值40GiB。以下申请及P0回执保留原时点语义；其中“未批准/待裁决”不再代表当前实施授权。获取前非作者准入、原件/安全、合同Review和真实门禁仍须满足；不代接受许可、不更新main、不恢复TDengine、不制作ZIP。

2026-11-13；Master单写。[唯一任务卡](../../tasks/G4-M2-ORACLE-01.md)。用户明确批准附件P0，附件中后续实施申请不是本轮许可。Base=`5113d0b9b233e307664c964ae9bf3c1d6b10adfb`，fetch后远端相符；最终完整Head和普通push回执随交付给出。下文“申请/拟议”均未实施。

推荐唯一组合：**Oracle AI Database 26ai Free，23.26.3.0，Linux ARM64，单FREEPDB1；Oracle.ManagedDataAccess.Core 23.26.400；仓库net10.0**。官方完整容器为`container-registry.oracle.com/database/free:23.26.3.0-arm64`，冻结digest见A。存在官方原生ARM64发行，不需要预设购买Enterprise。匿名公开Bearer握手已取得tags/index/manifest，不需要用户提供账号。当前 **P0_READY_FOR_ADMISSION_REVIEW**：用户批准限定HTTPS源站跳转后，已成功取得精确config，实际29,943字节、SHA256与descriptor相符，JSON可解析并声明linux/arm64；元数据读取阻断解除。仅跟随一次已批准源站，签名地址仅内存、未转发Registry token、未继续跳转。此前失败/未知量保留，不追溯改写。产品未准入；用户已自行下载指定镜像，本轮Agent只做本地身份元数据核验，未启动服务或实施产品。已存在本机原生制品身份，不另铺替代版本、amd64仿真或第三方镜像路线。

## A｜精确版本、来源、许可和制品

| 对象 | 已核实 | 未核实/准入后检查 |
|---|---|---|
| 驱动 | 官方NuGet `Oracle.ManagedDataAccess.Core 23.26.400`，2026-10-20发布，5,661,004 bytes；catalog实际DLL位于lib/net8.0和lib/netstandard2.1。nuspec另有net6.0依赖组，不是net6 DLL | nupkg原件/签名链/内容扫描/真实运行NOT_VERIFIED；不引入Oracle EF Provider |
| 驱动平台 | 官方支持macOS ARM64≥14.7，23.26.0起支持.NET10，目标库19c及以后；仓库Directory.Build.props=net10.0，静态选net8资产 | 本机macOS27.0.1/ARM64已观测，运行NOT_RUN；未来客户19c/21c/23ai/26ai按各自精确RU/edition另验，不承诺兼容验收 |
| 数据库发行身份锚点 | 官方页列`oracle-ai-database-free-26ai-23.26.3-1.el8.aarch64.rpm`，1,355,290,892 bytes，SHA256=`e1951c4a56eb8ef8cf5d325c90525be8ddb286486f6a318e8b4c4942e10eadbb` | RPM未获取/验签；此SHA不替代容器digest，也不授权RPM安装 |
| ARM64部署 | 官方安装要求OL8.6+/UEK7、Neoverse N1能力（推荐Ampere）；Oracle容器README明确26ai Free ARM64支持。拟在现Linux ARM64 Docker VM运行 | Apple Silicon/Docker内核不是生产认证等价物；CPU指令/容器运行仍NOT_RUN，禁止自动amd64仿真 |
| 官方容器 | `database/free:23.26.3.0-arm64`，index明确linux/arm64；29层压缩合计3,527,716,613 bytes≈3.285GiB | config200/29,943字节与散列通过；用户下载后，本地manifest/Descriptor/LinuxARM64/29diff_ids匹配。实际运行/组件/补丁/签名/漏洞仍NOT_VERIFIED；Agent镜像层请求为0 |

容器取得前身份：多架构index SHA256=`f988b0c04c4c386cd306a2a914c0d7a9702d83acc31b064a28ad8eb6278a8fba`，其linux/arm64描述符引用的manifest SHA256=`844b2cdb95c4cc120f549ff3b2aa36c191c8c9244bf90e6082971aaa6355f6d8`（4,962 bytes），与实际保存正文SHA一致。config descriptor的mediaType=`application/vnd.docker.container.image.v1+json`、size=29,943、digest=`sha256:dbd385a383e229ba349c103d779932a9fb24c7f92c762b5fe0420e59a1be347b`；它和29个layer descriptor严格区分。config已取得且正文长度/SHA256/JSON通过，architecture=arm64、os=linux、created=2026-07-08T22:01:39.411680312Z，rootfs.diff_ids数量29。labels为Oracle AI Database 26ai Free / release=Free / provider=Oracle，但version标签为23.26.0，与Registry tag23.26.3.0不同；同时config的INSTALL_FILE_1明确为`oracle-ai-database-free-26ai-23.26.3-1.el8.aarch64.rpm`，支持tag与声明构建输入的对应；标签可能表示基础版本，不能以此断言运行RU正确或错误。冻结制品以manifest/config digest为准，实际安装版本和RU须获批后检查，仍NOT_VERIFIED。用户已按arm64 manifest digest取得本地镜像，Agent未下载镜像层；驱动依赖仍未取得，后续取得/运行须按准入裁决。

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

**申请A**：批准精确驱动/候选闭包及Free目标，仅本机隔离合成非分发。config元数据身份核对现已通过；仍须另行确认许可，核上述身份/总量与D预算并独立确认获取准入，再取得载荷；原件/安全检查通过才启动。没有无上限pull授权，也不授权基于RPM另行构建/安装。数据库镜像签名、SBOM、漏洞状态NOT_VERIFIED。

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

分别预算：驱动5.66MB，Microsoft闭包压缩总量UNKNOWN（拟包下载合计≤128MiB）；Oracle29层压缩量3,527,716,613 bytes≈3.285GiB（manifest声明；用户已下载，Agent未下载；与驱动包合计下载缓存≤4GiB）；镜像展开由Docker报告13,076,125,534 bytes≈12.178GiB（非APFS独占物理增量），超过原拟12GiB；申请镜像上限改为13GiB，未获批前不启动；初始化仍UNKNOWN、源卷拟≤16GiB（官方安装至少10GB），合成用户数据≤256MiB包含在源卷内；平台卷≤2GiB、日志/证据≤1GiB、私有依赖/构建缓存增量≤4GiB。保守磁盘峰值≤40GiB含载荷保留和展开，未知不填0。共享缓存命中UNKNOWN，未验内容键不扣下载量；超过限额停申请，不掩盖超量。

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

请一次裁决：**A**精确依赖/官方来源/许可与条件取得；**B**TCPS文件wallet、最小READ、取消和独立见证；**C**ORACLE_READONLY及固定目标/账号/owners/scope与生命周期；**D**单机预算/网络；**E**DTO/JSON语义、源码候选及Compose/部署；**F**以下门禁与同树继续。config元数据读取阻断已关闭；本次并未批准A–F实施或接受许可，仍不启动实现或载荷下载。

2026-11-13用户已直接明确批准下列唯一config JSON元数据（29,943 bytes），包括此精确/blobs/路径，不含任何镜像层：

`https://container-registry.oracle.com/v2/database/free/blobs/sha256:dbd385a383e229ba349c103d779932a9fb24c7f92c762b5fe0420e59a1be347b`

历史两次自动审批拒绝保留于原提交及索引；本次正常审批已放行，不能继续写成审批缺失。执行前重新解码已有manifest，SHA256、config digest/size/mediaType与非layer身份均通过；沿用官方匿名认证，临时token不打印/保存；TLS正常，禁止自动重定向，正文上限29,943字节（最多额外读取1字节用于超限检测，超限即停）。唯一config请求返回非200，程序exit1并立即停止，没有跟随跳转、重试或换通道，没有保存config。

前次取证缺口：P0-CONFIG-20261113-02断言在保存失败诊断前退出，具体HTTP状态、响应头、正文长度/散列未留存，保持UNKNOWN；用户后来明确批准一次有界诊断，不是无授权重复请求。

此前P0-CONFIG-DIAG-20261113-03已先修正错误处理再执行一次：再次核manifest/descriptor非layer，匿名认证token仅内存；正常TLS、禁自动重定向、正文有界。实际HTTP **307**；保留的脱敏头为Content-Type=`application/octet-stream`、Content-Length=`0`、Date=`Fri, 13 Nov 2026 07:28:13 GMT`；完整实际正文 **0 bytes**。Location仅保留源站`https://id55cllpgrte.compat.objectstorage.us-sanjose-1.oraclecloud.com`，完整路径、query、fragment、userinfo不保存，签名参数不输出/持久化。该跨域跳转未跟随，没有换通道或第二次config请求；程序exit1表示没有取得预期config，不表示已验其散列。没有保存config原件，无镜像层请求。

用户随后明确“允许”此前提出的限定跳转读取。本次P0-CONFIG-REDIRECT-20261113-04再次核验manifest，使用正常TLS及临时匿名token向Registry请求同一精确对象；Registry跳转只允许HTTPS、精确源站`id55cllpgrte.compat.objectstorage.us-sanjose-1.oraclecloud.com`、无userinfo/fragment、默认443，不自动继续跳转。跨域请求不携Registry Authorization；签名路径/query仅内存，不保存/输出。最终HTTP200，正文29,943字节，SHA256=`dbd385a383e229ba349c103d779932a9fb24c7f92c762b5fe0420e59a1be347b`，JSON对象解析成功，原字节保存在metadata同SHA名称的.json（保留上游无末尾LF，不格式化）。此成功仅证明精确公开config身份，不是镜像层下载、供应链/漏洞/运行验证或许可接受。

仍需裁决：Oracle适用许可、已下载Oracle镜像的后续供应链/实际RU检查及尚未取得的驱动依赖，以及A–F全部实施项；本次元数据授权不扩展这些范围。标签23.26.0与tag23.26.3.0差异列为后续实际补丁核验事项，不用标签猜测已安装版本，也不另开恢复任务。

本次授权不接受Oracle许可、不批准A–F实施项。仍需集中裁决许可/载荷取得、精确依赖、TLS/权限/取消、ORACLE_READONLY、DTO/生命周期、资源和部署范围；产品实施继续未授权。

后续顺序：A身份/许可/预算→非作者获取准入→精确载荷及原件/安全核验→合同/ownership冻结Review→Oracle工程消费者与批准后prepare/restore/锁→最短真ARM64/TLS/权限/撤权/取消/类型→真OIDC与完整生命周期/UI→按影响PG/Web/Doris共享回归→最终独立Review/提交绑定/资源后验/规定交付。本轮禁止的后续动作不会提前执行。

真实验证覆盖坏CA/过期/SAN/错误service/PDB、直接/继承/PUBLIC权限和撤权、源端取消见证、大小写/NUMBER负scale/日期TZ/LOB、跨actor/scope/用途/旧Ref/旧版本/旧Probe、并发CAS/同key异body、审计失败回滚、注销/fence/重启与取消竞态、auditor脱敏。合法来源/原件门禁在服务前，不用mock顶替。input不变旧证明须核原件资格后才REUSED，不重跑无关全链/无变化自然TTL。失败先短定位，无新假设不重复扩大搜索。

CI按需NOT_RUN；Mac宿主/LinuxARM64容器分列，Windows/x64/生产NOT_RUN。供应链未核项NOT_VERIFIED；没有产品PASS。本P0仅两份材料、无ZIP、不更新main；后续同会话同树继续，不进M3/M4、不恢复TDengine。

## 来源、轻量检查和独立审查回执

[metadata/index.json](metadata/index.json)为唯一恢复索引；旧32份原件按base64保存且未改，本次新增精确config原始JSON一份（共33份公开原件）。当前43条已记录响应正文866,022 bytes，另有前次1条失败长度UNKNOWN，精确总量仍UNKNOWN，保守上限895,965 bytes，低于64MiB。匿名认证正文不保存；Registry和对象存储重定向的Location只留源站，路径/query/签名/userinfo不保存。已批准对象存储请求URL也只存脱敏占位，原件由manifest/config SHA恢复定位。不用新成功回填历史未知量，不包含HTTP头/TLS/搜索服务开销；仅取config，没有镜像层请求，返回内容未执行。

官方入口：[精确驱动](https://www.nuget.org/packages/Oracle.ManagedDataAccess.Core/23.26.400)、[运行要求](https://docs.oracle.com/en/database/oracle/oracle-database/26/odpnt/InstallSystemRequirements.html)、[数据库发行](https://www.oracle.com/database/free/get-started/)、[原生部署要求](https://docs.oracle.com/en/database/oracle/oracle-database/26/xeinl/requirements.html)、[容器说明](https://github.com/oracle/docker-images/blob/main/OracleDatabase/SingleInstance/README.md)、[权限指南](https://docs.oracle.com/en/database/oracle/oracle-database/26/dbseg/guidelines-securing-user-accounts-and-privileges.html)。滚动页面只证明本次快照，恢复按原件索引。

非作者只读Reviewer=`/root/oracle_p0_review`完成同一轮审查，初次发现1项P1：401/302不足以证明需要用户登录/外部资料。Master据新假设检查WWW-Authenticate、完成匿名握手，取得tags/index/manifest，已撤销该错误推断；没有重复无条件搜索。当时最小阻断为自动审批config读取边界（历史P0-CONFIG-20261113-02已放行但非200失败；本次04已成功），原401/302与两次审批拒绝均保留。同一Reviewer完成修正复核：原P1关闭，无新增阻断级文档问题；确认精确平台/大小/descriptor与原件，未认证config正文或产品。Reviewer首次误把base64文本当原字节校验失败，按encoding解码复验exit0，保留该检查纠正而不称原件损坏。

轻量检查：原件base64解码/长度/SHA256、官方index→arm64 manifest→config descriptor绑定、文档相对链接/EOF、授权纯追加与写路径白名单、最终git diff --check；原P0检查exit0：37响应/829,177 bytes（认证正文不保留6,906 bytes），32份去重原件、4相对链接、所有原件散列/manifest绑定/授权纯追加/owned_paths通过；可恢复检查源码及SHA在索引metadata.localCheckSource。`pwsh -NoProfile -File scripts/test-review-evidence.ps1 -EvidenceFile docs/evidence/G4-M2-ORACLE-01/metadata/index.json`已实测exit0（仅EVIDENCE_SCHEMA_ONLY，产品NOT_RUN）。新证据完成后重复同一廉价检查，不跑历史全量。产品/CI/跨平台/生产NOT_RUN，不用历史结果充本轮通过。

开工保护：项目.codex仅agents配置，未发现项目setup入口；原生create_worktree只创建/注册checkout，未调用安装/restore/服务。fetch首次受FETCH_HEAD权限限制，获范围权限后exit0并核main；任务分支创建和文档写入首次受沙箱限制，获范围权限后完成，未退回main写。只读宿主/Docker首次权限失败保留于本摘要，不把空格式输出当0资源。当前无本任务容器/卷，唯一持久新资源为任务分支/托管树与公开证据，KEEP供同会话后续，禁止借收尾清理旧资源。

历史P0-CONFIG-20261113-02增量保护：fetch正常审批后exit0，origin/main仍为预期Base；当前树新出现的`docs/.DS_Store`与`docs/evidence/.DS_Store`未跟踪文件保留，不纳入提交。只更新本卡/申请/索引及追加本次授权，不动产品、锁、脚本、main或TDengine。增量原件/manifest/链接/EOF/写范围检查、证据schema及diff-check均exit0；同一非作者Reviewer复核通过（仅文档/证据），记录在索引configIncrementReview；读取失败仍为FAIL，config内容未验。

历史P0-CONFIG-DIAG-20261113-03一次性诊断授权及真实307结果已记录于索引configDiagnostic20261113，修正后的临时诊断源码和SHA用于复核错误处理，不是工程脚本变更。所有历史失败与未知项保留。只做受影响文档/证据检查，不恢复服务或A–F实施。

历史P0-CONFIG-DIAG-20261113-03增量经同一非作者Reviewer只读复核通过；40条记录/833,779字节与863,722上限、历史UNKNOWN/32原件不变、Location脱敏/单次调用/不跟跳转及4路径边界均已核对。受影响原件/链接/EOF/schema/diff-check均exit0；config取得仍FAIL，产品/CI仍NOT_RUN。

本次限定跳转读取的完整结果见索引configRedirectVerification20261113；当前状态以页首和唯一任务卡为准，以上历史失败/诊断回执保持其原时点语义。后续仍停准入，不实施A–F、不更新main、不恢复TDengine。

本次04精确config成功增量已获同一非作者Reviewer只读复核通过；长度/散列/JSON/ARM64/manifest绑定、原件不变、跳转与token边界、流量核算、链接/EOF/schema/diff-check通过。config声明INSTALL_FILE_1与23.26.3 ARM64 RPM对应，仍不替代实际RU/产品验收。

## 用户下载镜像后的只读准入增量（P0-LOCAL-IMAGE-20261113-05）

用户报告“下载完成了，同意，继续任务”。按上一轮约定先核验本地镜像，不将此笼统表述自动扩大成全部A–F/许可批准；已集中确认是否包括条件实施及下列预算调整。用户未答复前仍停准入。

本轮正常权限只读`docker --context desktop-linux image inspect`：RepoDigests与Descriptor均为冻结ARM64 manifest `sha256:844b2cdb95c4cc120f549ff3b2aa36c191c8c9244bf90e6082971aaa6355f6d8`，descriptor size=4962，platform=linux/arm64；29个RootFS diff_ids与已验证config逐项同序一致。当前Docker store的Id也返回manifest digest，不能把它误当config digest或据此声称config身份错误；本地独立config digest未暴露，映射依据已有验证manifest/config原件。此为Engine公开元数据核验，不是逐层载荷重算、签名验证、漏洞扫描、数据库运行或实际RU证明。`docker ps`为空，Agent未启动容器。

展开大小13,076,125,534 bytes（12.178GiB）超过原申请12GiB，现提出**镜像上限13GiB**；总磁盘峰值≤40GiB暂不变（13镜像+4下载缓存（包含Oracle压缩层及≤128MiB驱动依赖，不另加）+16源卷+2平台卷+1证据+4私有构建缓存=40GiB），实际启动前还需重新确认剩余空间/共享缓存，不能将共享层/名义Size当独占磁盘。此调整待用户明确批准，不倒写已批准。

用户取得的唯一镜像作为任务资源KEEP，准确引用与公开身份/时间见索引`localImageInspection20261113`；供本任务后续准入/实施，不清理用户镜像、不碰旧资源。保留条件解除需任务关闭、引用/数据归属复核及明确回收范围。本轮无下载流量；用户下载的实际网络字节未知，不能用manifest压缩总量冒充实际网络计费。

本次本地镜像增量经非作者只读复核，身份/层标识/大小及33原件历史不变核对通过。已修正旧“未下载”措辞，并明确4GiB下载缓存包含驱动包；身份元数据核验、文档链接/EOF/范围、证据schema和diff-check通过，运行/安全验证及实施授权仍未通过或未执行。

## 条件实施执行记录（2026-11-13）

设计依据为本文A–F，已获用户明确批准。Master单写，采用executing-plans及先失败测试后实现；不另建任务/工作树或中间交付物。路径以E表为准，宿主入口增补`host_continuity.py`与`scripts/tests/HostContinuity.Tests.py`，用于真实TaskId预检与监测；这是现有工程入口的必要适配，不扩展产品。

1. 获取与资源前置：非作者复核精确载荷清单；冻结来源/散列/体积与许可条件后才能取依赖。宿主CLI先证明Oracle TaskId被拒，再最小接入，执行HostContinuity.Tests.py及本任务preflight。供下一步消费的身份是已验证原件和taskId，不是其他任务PASS。
2. 合同冻结：E表OracleMetadata的null/省略/排序、ORACLE_READONLY及固定目标变化拒绝规则；G4WireContractTests先加负例，生成合同旧分支字节不变；非作者Review后消费合同。
3. 工程消费者与依赖：Oracle专属结构入口/锁闭包/prepare/构建绑定；负例覆盖缺Oracle注册、错误TaskId、错散列与未知包，复用公共执行器而非复制。prepare零下载；restore仅已批私有feed；准确依赖差异超出A表则停。
4. 真实Adapter：TCPS文件wallet、CREATE SESSION与直接READ、最小目录SQL；先OracleAdapterTests和FixtureSecurityTests，再实现接口/Adapter/dispatcher/DI。真实坏CA/SAN/过期/service/PDB、写权限继承/撤权、取消源端见证和类型负例通过才开放能力。
5. 完整应用/UI：消费固定目标与OracleMetadata合同，贯通凭据/Probe/Enable/Discover/Worker/Catalog/轮换/禁用；先安全/并发/审计回滚测试再修改应用/UI，真实OIDC/UI检验，旧连接器按输入影响回归。
6. 收口：每步实际命令/exit与输入绑定，非作者Review后普通提交/push；资源精确归属与KEEP/回收后验。CI/其它平台未运行分列，不更新main、不恢复TDengine、不制作ZIP。

重点拒绝：无旧secret跨目标/scope复用；未知类型不能完整可信；管理员不能进入产品；取消仅调用方结束不得PASS；旧fingerprint不可因Oracle增量变化。既有公共字段/规则由Master单写，旧快照仍允许OracleMetadata缺省。

实施初始时点（历史）：获取准入Review进行中；宿主只读实测AC供电、sleep=0、displaysleep=10，POLICY_READY；锁屏/整会话持续性NOT_VERIFIED。未启动服务、未取得新载荷、未运行prepare/restore。

### 本次执行结果与安全门禁（IMPLEMENTATION-20261113-01）

最新A–F授权已记录；Mirror/驱动下载故障已解除。本次补齐10个Microsoft包的20份官方registration/catalog原件并获非作者准入。11新包实际13,499,230bytes（其中Microsoft7,838,226），逐包长度/SHA512通过；全部保留于任务私有artifact-cache，不入Git。System.Memory的requireLicenseAcceptance=true/MIT事实保留，未执行交互接受操作。Oracle包13条目/展开11,843,773bytes/CRC通过，附带两份性能计数器脚本不执行，无自动build targets。专用`dotnet nuget verify --all`对11包exit0；offline revocation，在线撤销NOT_VERIFIED，不把通用OpenSSL用途不匹配的旧失败改写成成功。

已接入Oracle TaskId的宿主/继承基线包/Web缓存入口。补充owned_paths：`scripts/maintenance/host_continuity.py`、`workflow_web_cache.py`及`scripts/tests/HostContinuity.Tests.py`、`WorkflowEnvironment.Tests.py`、`WorkflowM2Web.Tests.py`；仅为本任务最小工程适配。基线prepare完成DEPENDENCIES_READY，首次离线锁定restore成功、后续复用，网络下载0；其中MySqlConnector原件从已有Doris公开artifact-cache经固定SHA256核对后复制，未读取/复制任何旧runtime/凭据。新Oracle/Microsoft包未入锁或用于产品。宿主13+环境7+Web缓存14+Doris结构6+交付13=53定向测试通过。初次sandbox_apply失败71→正常权限短诊断exit0，失败止损记录保留；Web TaskId拒绝→先失败测试→最小修复，未重跑历史产品全链。

已保存[Oracle十月CPU](https://www.oracle.com/security-alerts/cpuoct2026.html)及[风险详表](https://www.oracle.com/security-alerts/cpuoct2026verbose.html)原件。数据库表内与23.26.3范围交叠的条目包括75803、91563、91499、93569、91503、91568、101512、91479、91615、59889、101510、54399（均CVE-2026前缀；75803有不同组件条目）。组件/选件/暴露适用性尚未完整排除，不是全部已实证可利用。主要直接触达风险：

| 公告 | 与方案的关系 | 当前结论 |
|---|---|---|
| CVE-2026-75803，RDBMS/OpenSSL，CVSS9.8 | 官方受影响范围23.4.0–23.26.3；TLS网络未认证条件。计划开放TCPS，不能以TLS加密本身排除 | 当前digest未证明修复或不适用 |
| CVE-2026-91568，RDBMS，CVSS7.7 | 同范围；CREATE SESSION与Oracle Net条件与reader/连接方案交叠 | READ最小权限不能排除此漏洞 |

为尽量先解决补丁证据缺口，非作者批准了不执行镜像的静态取证：冻结digest、--pull=never、network none、read-only、cap-drop ALL、no-new-privileges、128MiB/0.5CPU；无挂载、始终created/Running=false。唯一comps.xml正文388,458bytes，SHA256=`afda74fa2343a430bca615ac0de5db120805bb22eebfabc43d0a98df377ba903`；只见oracle.server/rdbms/network基础版本23.0.0.0.0和20260708构建时间，不能替代实际RU/补丁证明。临时容器`e650a11419e8d54701c8a6ede73788ed2a04c98b685ead8debcb289863ceb8ed`已rm exit0，原后验文字预期错误exit1保留，随后准确“No such container”与Engine身份一致通过；没有start/run/exec或服务/卷创建。

非作者确认**BLOCKED_SECURITY_ADMISSION**：原A–F要求原件/安全核验通过才启动，这次批准不包含对这些新披露风险的接受。当前不启动数据库，不编写假PASS；原镜像与所有证据KEEP。推荐取得绑定digest的官方修复/不适用证据；若需更换版本，先重新冻结精确官方ARM64制品并裁决，绝不自行拉取另一版本。若用户仍要求当前镜像试验，须明确接受以上披露及未排除适用性，仅同TaskId/同树、冻结digest、本机合成数据、无生产凭据、无宿主敏感目录/socket、仅任务控制的网络参与者和固定SQL、禁止外部客户端；期限限定自授权起24小时，期满/异常即停止任务服务，精确回收临时资源，保护用户镜像及唯一证据。风险例外不等于安全PASS，也不豁免剩余工程/资源/TLS/权限/取消门禁。

当前65条HTTP元数据记录正文合计2,998,020bytes，历史未知响应上限29,943保留，保守总上限3,027,963<64MiB；11包载荷和本地XML另列，不能混充元数据额度。新增22份HTTP原件+1份本地XML；原33份字节不变。索引implementationAdmission20261113保存获取/验签/宿主/prepare摘要、诊断源码和静态清理后验。CI/Oracle运行/产品测试仍NOT_RUN；未改main、未制作ZIP、未恢复TDengine。

### 实施进度 IMPLEMENTATION-20261113-02

用户最新明确本机开发接受现有镜像风险，按原A–F继续；历史24小时提案未获采纳，不作为新增限制。实际锁闭包新增10包，候选EventLog10.0.13被.NET裁剪；既有包版本未升级。7份锁文件为真实传递闭包，非作者已核对。离线prepare当前contentKey为`6c8f4a758218eefe50dc8efa1a3793854725ec6ac759603f6f008ffbf30dd7ee`，零下载。

已实现ORACLE_READONLY/TLS合同、严格OracleMetadata、Oracle真实驱动及目录解析、目标/owner/scope绑定、独立指纹、信任材料变更栅栏与DI。当前14项Adapter/Dispatcher测试、19项wire合同测试及4项Oracle结构入口测试通过；仅单元/结构证据，不代表真实源、取消、UI通过。新增执行入口与测试为原E表消费者范围的具体冻结：`workflow_m2_oracle.py`、`scripts/tests/WorkflowOracle.Tests.py`；阶段先仅提供结构preflight，未实现生命周期命令不会假报通过。

独立Review指出信任文件IO异常及列级授权遗漏；前者已用读取边界RED→GREEN修复，后者补reader列级检查，PUBLIC/列级/角色/EXECUTE完整证明仍待真实fixture完成。控制视图不能凭过程名猜测安全，未知EXECUTE须拒绝。源实例先仅内部网络、无端口、4GiB/2CPU、精确digest；服务就绪不等于只读验收。临时公开脚本取证容器从未启动，已删除，原缺席匹配错误与纠正后验均保留。


实施02后续实测增量：Oracle实际版本23.26.3.0.0；5项真实Adapter测试通过（正常五阶段/元数据/错误密码/错误CA/错误ODP wallet）。首次错误CA加载及阶段分类失败均保留，修复后重新运行。API与Web当前构建通过，122项Web组件测试通过。实际UI/OIDC创建、探测、启用和目录已运行；完整终态仍在验收，不将局部结果写成总PASS。

只读证明采用Oracle原生用户READ ONLY + 每连接session READ_ONLY，reader仅CREATE SESSION及合成对象直接READ。原生限制已实际拒绝被额外授INSERT后的DML、可写definer调用和授权；用户自行ALTER USER READ WRITE也被拒绝。ALTER SESSION READ_ONLY=false本身可调用，但不能解除用户级限制，不误写为该语句被拒绝。四组解除只读/列级写/角色/撤销READ均被产品拒绝。PUBLIC基线与同一冻结镜像PDB$SEED原件集合核对：38826→38830，仅四个新用户默认INHERIT PRIVILEGES差异；这不证明所有外部副作用或漏洞安全。原批量REVOKE因依赖错误停止，未使用FORCE，准确恢复后才继续，失败原件保留。

取消旧十秒单段sleep未能在5秒内终止，原失败保留；改为总十秒、50毫秒分段的有界fixture后，真实驱动取消及独立源端见证通过（active到会话不存在1.467秒）。该结果只覆盖本fixture，不能承诺所有Oracle长操作瞬时取消。UI cancel/disable另做精确SID/SERIAL和自然完成前提前终止检查，不能借Adapter证据代替。

实施E具体路径补充：workflow_oracle_fixture.py、workflow-oracle.mjs、oracle-fixture-relay.cs.txt及apps/web/vitest.config.ts。固定relay仅API容器回环15180→任务Keycloak、15300→宿主Web，不修改产品loopback guard、全局DNS/信任或主机配置；API仅挂载公开CA/wallet，不挂载源reader口令或管理员材料。Web测试报告按G4_TEST_TASK白名单写Oracle目录，避免复用旧Doris报告路径。全部资源准确ID/限制由implementation-02下回执恢复。


实施02最终验证增量：当前正式消费者记录11组真实OIDC/UI生命周期通过，包含凭据用途/作用域、创建/Probe/Enable/Discover、auditor脱敏、撤权历史访问、轮换/旧Probe/旧修订、进行中权限变化无快照、租约/fence接管、审计故障回滚与预约重放拒绝、注销/取消/禁用。取消计时自排队前起，准确SID/SERIAL消失均早于10秒自然延迟；注销同样无快照。8个真实作业、5个探测与原始脱敏SQL审计投影逐项关联，绑定本次lifecycle SHA与API构建，私有dump只在内存扫描。原故障/断言/启动就绪失败保留，未改写为成功。

当前API、Web及Connections/wire构建均通过；46共享单元、19 wire、122 Web组件、5真实Oracle Adapter，零跳过。TypeScript类型检查和受影响文件lint通过。五类本机产品资格由workflow.py→workflow_m2_evidence的Oracle分支消费原日志/真实exit/input绑定；不以manifest自报测试数代替解析。warm prepare零下载、零restore、零materialization。坏CA/wallet/密码及真实Oracle错SAN拒绝；过期证书被Oracle orapki拒绝导入，另在同源容器已有OpenSSL监听器上完成真实TLS拒绝测试后恢复Oracle监听器，不能将它说成Oracle成功装载过期证书。

E最小工程收口补充：workflow_oracle_platform.py负责本任务固定审计故障/fence控制；故障创建DDL事务化，finally清理并核准确对象缺席。workflow.py/workflow_m2_evidence.py接Oracle真实证据资格。scripts/verify.ps1和OracleFrozenMetadata.Tests.ps1仅为已批准的29,943字节config原件加入精确路径/长度/SHA格式例外，JSON/秘密检查保留；RED→GREEN，原件没有补LF或改写。部署文档已补，生产G4和迁移显式关闭。

本轮属于本机开发切片，CI/Windows/x64/生产一体机未执行；整会话锁屏/睡眠及宿主RSS峰值未做连续测量，当前容器上限6GiB/4CPU，源卷实测约4.13GiB、任务artifact约3.09GiB。完整卷灾备恢复、另一Oracle精确RU/edition、生产容量和漏洞修复证明不在本轮通过声明中。既有风险按用户最新开发授权处理，不重复阻断。最终只交付本申请与一页任务状态，源码及证据在同一任务分支，不制作ZIP、不更新main、不恢复TDengine。


最终收尾审查发现平台PG/Keycloak卷实际为tmpfs；原“只KEEP卷名”计划已撤回，未据此删除唯一状态。已持久化PG备份232,592bytes/0600和Keycloak完整私有snapshot约185MiB，私有父目录0700。正常关闭Keycloak前用准确卷保持器维持挂载，H2原件与副本SHA一致；隔离无网络PG恢复通过，11表源/恢复行数和内容摘要一致；隔离Keycloak副本准确realm OIDC HTTP200。此前卷读取用户和PG初始化就绪竞态失败保留；改用卷拥有者只读核验和TCP就绪后恢复。实际脚本原字节、成功exit0/tool会话74743链接及精确清理断言已保存，非作者复核关闭P1；逐查询双侧字符串及完整HTTP正文未单独保存，证据限制明确，不伪造补原件。不把这些局部恢复扩展为Oracle整库灾备或生产验收。

最终资源收尾已完成：准确删除4容器、2网络和2个已持久化并恢复验证的tmpfs卷，共8项，全部真实exit0及缺席后验已记录；宿主Web正常结束其有界运行后已停止。Oracle普通数据卷、私有持久备份/必要密钥与用户镜像KEEP，不触碰其他任务。最终状态READY_FOR_REVIEW；Head/普通push与受影响工程检查回执随最终交付给出。

最终独立只读Review无未关闭阻断项，允许同任务分支普通提交/push；八项清理实际exit/原始后验和29份新增证据散列已复核。工程仅运行本轮受影响检查及冻结原件正反例；遵照用户禁止ZIP/历史全量验收，不运行含ZIP夹具的历史全SelfTest，也不宣称整份registry verify全部PASS。
