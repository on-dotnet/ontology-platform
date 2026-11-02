# G4-M2-001 四Adapter实施授权申请（候选，未获批准）

本次仅研究，不编码、不安装、不启动服务。资料查询截至2026-11-02 UTC，逐次URL/结果/缺证见external-access-ledger.json。原G4-00与ADR02/03/04/05/06等仍PROPOSED，不借本申请冻结。M1只有PostgreSQL真实启用，另外四类继续422 connector_not_enabled。

## 依赖、平台、许可与费用研究

|Adapter|精确候选与官方证据|许可证/平台/缺证|
|---|---|---|
|Oracle|Oracle.ManagedDataAccess.Core **23.26.400**，Oracle发布者[NuGet元数据](https://www.nuget.org/packages/Oracle.ManagedDataAccess.Core/23.26.400)；官方[系统要求](https://docs.oracle.com/en/database/oracle/oracle-database/26/odpnt/InstallSystemRequirements.html)|[该版本许可](https://www.nuget.org/packages/Oracle.ManagedDataAccess.Core/23.26.400/License)为Oracle Free Distribution, Hosting, and Use Terms；不是MIT。官方支持.NET10及macOS ARM64 14.7+、所列64位Linux/Windows；本机与Windows实测NOT_RUN。元数据有System.Text.Json等传递最低版本，不能直接替换本仓库锁。数据库19c+仅兼容范围，准确服务版本/RU、许可、Wallet和镜像digest待证；支持/数据库可能收费，未批准任何费用|
|Doris|MySqlConnector **2.6.2**，官方发布者[元数据](https://www.nuget.org/packages/MySqlConnector)，MIT；Doris服务候选 **4.0.8**，来自官方[版本页](https://doris.apache.org/download/)|Doris官方[MySQL协议说明](https://doris.apache.org/docs/4.x/connection-integration/mysql-proto/)确认FE默认9030；不证明方言/元数据完全等同MySQL。服务Apache-2.0，官方页面列x64/ARM64；镜像完整组件/签名/CVE、.NET客户端与4.0.8互操作NOT_VERIFIED。开源许可不等于托管/支持免费；费用预算0，收费选项另批|
|TDengine|TDengine.Connector **3.2.1**，[官方发布者NuGet](https://www.nuget.org/packages/TDengine.Connector)与[官方项目](https://github.com/taosdata/taos-connector-dotnet)；候选服务 **3.4.1.8**，由[官方C#兼容表](https://docs.tdengine.com/developer-guide/connectors-reference/csharp/)对应3.2.1|客户端MIT，传递Newtonsoft.Json>=13.0.3；[服务主分支许可](https://github.com/taosdata/TDengine/blob/main/LICENSE)显示AGPLv3，不能替代3.4.1.8具体制品完整许可。WS官方称支持.NET运行平台；旧汇总表与具体WS页范围不同，原生/WS不得混算。文档出现3.2.2但NuGet查询为3.2.1，保留差异；服务发行制品、ARM64镜像和许可准入待证，商业版/云收费未批|
|Web API|复用仓库global.json SDK **10.0.402** 和既有.NET10 shared framework，不增第三方包；[ConnectCallback](https://learn.microsoft.com/en-us/dotnet/api/system.net.http.socketshttphandler.connectcallback?view=net-10.0)、[AllowAutoRedirect](https://learn.microsoft.com/en-us/dotnet/api/system.net.http.httpclienthandler.allowautoredirect?view=net-10.0)|官方支持自定义连接回调；自动重定向默认开启，因此候选必须显式关闭并受控处理。准确部署runtime patch以未来既有工具身份记录，不安装升级。既有.NET许可范围沿用登记，服务端API条款/配额须逐operation批准；首切片只用自有合成HTTPS，费用0|

上述为元数据事实与工程候选，不是依赖准入、法律结论或安全通过。本轮未下载任何驱动/镜像；CVE、签名、完整传递依赖、第三方文件系统清单均NOT_VERIFIED。较早错误TDengine.Driver路径和失效文档404保留；不拿网页打不开当包不存在。

## 公共边界与最小API变化（候选）

沿用16个连接/目录路由、五类判别config、顶层SecretRef、六权限、ETag/CAS/幂等、DRAFT/ACTIVE/DISABLED。管理权限不自动获得源数据读权；配置/秘密/scope变化使Probe失效，Disable取消任务且不再调源。每类实现均需真实Create→Probe→显式Enable→Discover→Disable；测试成功不能直接ACTIVE。

现有应用服务和SPI为PgConnectionProfile/IPgSourceAdapter专用，不能直接注入四个假PG实现。候选由Master先独占提出typed IConnectionSourceAdapter/dispatcher、Probe/Discover结果和能力声明，PG保留兼容路径及原正反测试；尚未冻结签名或新增wire枚举。C# Contracts→原生OpenAPI→TS生成单写，禁止手改生成产物。未来需新增精度或分页字段必须单独批准DTO候选，不暗增actor/credentialRef或自由连接串。

首期预算候选沿用Probe10秒（network3秒）、Discover20秒/100对象/2000字段/2MiB，取消必须到实际传输。错误沿用connection_network_forbidden、connection_tls_untrusted、connection_auth_failed、connection_readonly_unverified、catalog_permission_limited、catalog_budget_exceeded、connection_cancelled等已存在语义；缺失/新能力码先列ADR候选，不把未知变成EMPTY_VERIFIED。

## 四类独立切片与真实负例

**Oracle：** 仅host/port/serviceName/username/tls/allowedOwners，不接受SID/任意描述符/alias，Wallet首切片关闭待另批。TLS验证CA/SAN；固定目录查询按实际账号权限与allowedOwners交集，不盲目大写quoted owner。NUMBER保留precision/scale，不经double截断；DATE无时区、TIMESTAMP及带时区类型分列，CLOB只取元数据不读业务正文。真实隔离Oracle验证认证/TLS、owner大小写、继承写权限/对象owner/跨owner拒绝、38位及负scale、时间精度、限量/取消；管理员只用于外部夹具建模，应用账号只读。service patch/license/Wallet/可信CA不明不得Probe假成功。预计3–5工程日（规划估计，不是实际工时）。

**Doris：** FE身份/9030受控端口、catalog/database强绑定；禁止把MySQL wire等同MySQL权限/事务/分页语义。独立Doris目录SQL，不复用PG只读事务假设；SELECT前缀不构成只读证明，检验账户角色/权限及固定查询集合。DECIMAL超过CLR decimal用精确字符表示的候选，datetime精度/时区明确，分页有稳定排序及总预算。真实FE+BE验证跨catalog/库拒绝、写角色继承、元数据隐藏、DECIMAL边界、分页重复/遗漏和超时；TLS能力不能确认则拒绝，不照抄官网useSSL=false示例。预计3–5工程日。

**TDengine：** 只受控单WS endpoint，明确WebSocket协议/TLS，禁止Native/REST fallback、地址列表/自动发现扩网。database/timezone/timePrecision与服务精度交叉核验，stable/subtable/tags分类保真。ns不得只靠DateTime tick或浮点；拟保留整数epoch+unit并进行字节往返，现有Catalog仅元数据，不解锁M4数据查询。官方显示TIMESTAMP映射DateTime及DECIMAL溢出路径，所以无损读取能力必须真实证明。真实WS验证ms/us/ns、负epoch/时区、标签与子表ACL、权限撤销、取消/超时/断线、SecretRef轮换后旧连接失效。服务许可及精确制品不明则BLOCKED，不能用客户端MIT代替。预计3–5工程日。

**Web API：** 首切片仅自有合成HTTPS固定origin与已登记GET operation，固定服务端参数/分页模板，不允许用户输入任意URL/OpenAPI远端ref。候选首切片仅使用现有wire枚举NONE与API_KEY_REF；API_KEY_REF凭据仍由顶层SecretRef绑定，header名称和载荷格式由服务器operation注册限定，不新增BEARER枚举。若需要Bearer格式，须先在operation准入中明确该固定传输格式；OAuth/代理未批准时显式拒绝，未来需单列认证端点和每跳政策。禁自动redirect、系统代理、cookie及非GET；只准明确同origin分页，拒绝跨origin next。DNS解析全地址校验、实际socket连接已验证地址并保持TLS/SNI；连接池/重连重验，防DNS rebinding、IPv4-mapped IPv6、私网/loopback/link-local/metadata目标。测试夹具仅精确测试网络例外，不放宽通用私网。双重重定向在首跳拒绝即有明确负例，不能声称已支持安全跟随。真实隔离HTTP/TLS检验坏CA/SAN、DNS换址、代理环境变量、OAuth目标、超大/深JSON、missing/null/精确number、游标循环、跨origin分页、取消/响应泄密。预计3–4工程日。

接口/类型/合成用例只能证明候选设计；四类产品准入均须真实隔离服务、真实权限及拒绝路径，缺环境NOT_RUN，不用mock晋级。

## DAG、推荐顺序与所有权

推荐先只批准 **M2-WEB-01受控GET闭环**：无需新增第三方驱动或商业数据库，能在已有.NET与自有TLS夹具证明真实生命周期。它不是SSRF低复杂度功能；socket/DNS/redirect负例为硬门禁，失败停止。其余三类继续维持未启用。

DAG：main集成决策→M2-P0精确授权/版本许可/资源准入→M2-C公共SPI及正反合同/独立Review→M2-WEB-01→真实完整验收/独立Review/交付；Doris/TDengine/Oracle各自准入通过后才进入独立后续切片。M2-C完成后不同Adapter可独立树并行编码，但内存上限内真实服务验收串行，不能同时启动四套源。

|责任|owned_paths候选|并行条件|
|---|---|---|
|Master|Connections公共Abstractions/Application分发、Host/Contracts/迁移/生成链/锁、任务工具和main|公共内容先审后冻结；所有共享修改串行|
|单Adapter Worker|Connections/Adapters/<本Adapter>及专属测试|仅独立Worktree；无跨模块写表、无共享锁写入|
|UI Worker（后续必要才派）|connections特定表单/状态测试|DTO冻结后；现有五表单优先复用，不为研究改UI|
|非作者Reviewer|只读，无owned_paths|检查SPI/负例/许可/实际源/资源及交付；不以作者自审替代|

## 待批资源与网络上限

以下均是建议的拒绝上限，不是实测需求或当前获批预算；镜像/压缩字节未知时不得下载或保存。每切片新TaskId/RunId，精确资源清单、非作者Review和生命周期强后验必须先就绪。

|切片|额外源服务/平台合计上限|新增镜像下载/磁盘上限|准入缺口|
|---|---|---|---|
|Web首切片|最多6进程/容器，合计6GiB；源HTTPS+DNS夹具最多2个，源内存512MiB|新驱动0、新源镜像0；任务数据≤3GiB，过程产物≤1GiB|复用平台镜像仍需本任务精确许可准入；精确loopback端口/fixture IP/CA需登记|
|Doris|源FE+BE≤2个且≤8GiB；含平台总计≤6容器/12GiB|新下载≤4GiB、总任务磁盘≤8GiB|超原6GiB预算，必须单独批准；精确镜像digest/大小/架构/组件许可待证|
|TDengine|源taosd+adapter≤2个且≤2GiB；含平台≤6容器/6GiB|新下载≤2GiB、总任务磁盘≤5GiB|AGPL服务制品及ARM64/WS TLS准入待证|
|Oracle|源≤1个/4GiB；含平台≤6容器/8GiB|新下载≤4GiB、总任务磁盘≤12GiB|服务准确版本/RU、镜像许可/平台/体积；超原内存预算须另批|

本轮已访问域名仅www.nuget.org、docs.oracle.com、doris.apache.org、docs.tdengine.com、github.com（准确官方项目文档/许可）、learn.microsoft.com；未来包/镜像下载域名均未批准。运行网络仅未来批准的隔离平台服务与准确source endpoint；不开放公网，不访问任意厂商示例IP，不用生产数据，GPU0/费用0。新依赖、包下载、镜像、许可证、私有CA/Secret输入、端口、存储及任何费用须逐切片明确批准。

## 请求批准的最小集合

仅候选：①M1 main准确集成决定；②M2-C SPI/权限/事务/DTO候选与owned_paths；③M2-WEB-01单切片及真实SSRF负例；④准确平台镜像与6GiB上限、fixture白名单及零费用；⑤单切片验收/资源/独立Review/V3后停止。Oracle/Doris/TDengine实现、商业部署、MappingRelease、新MCP和后续阶段不包含其中。
