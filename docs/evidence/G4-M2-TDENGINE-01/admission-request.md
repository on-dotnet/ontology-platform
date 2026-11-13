# G4-M2-TDENGINE-01｜一次性 A–F 准入申请

日期：2026-11-13；Base `5113d0b9b233e307664c964ae9bf3c1d6b10adfb`。唯一状态见[任务卡](../../tasks/G4-M2-TDENGINE-01.md)。本文件全部实施项均为 **PROPOSED**，未获得产品执行准入。

**决定建议：先解决合法Enterprise验证源，不批准当前产品实施或制品下载。** 官方原生WSS与权限文档已否决社区直连方案；网关只可能改变传输，不能补出社区版源端权限。旧3.4.1.8线索还有已知风险，不能沿用。一个条件性候选已列A，尚不是可获取组合。现有硬门槛不能用用户接受一般风险替代。

## A｜版本、供应链与合法取得

唯一推荐调查组合：`TDengine.Connector 3.2.1`（托管WebSocket）＋ **TDengine TSDB Enterprise 3.4.2.13 发行套件 / Linux ARM64**，含 taosd 与该发行配套 taosAdapter。服务发行号是官方安全公告的修复版本；**配套taosAdapter独立版本、ARM64二进制存在性和合法可获取性均NOT_VERIFIED**，不能把发行号当成已验证Adapter版本。先请用户提供已有合法来源/允许用途证明及官方精确制品元数据；不注册试用、不采购、不假定已有许可。若该套件不可取得，停在本申请，不自动换版本。

| 项目 | 本轮证据与未决条件 |
|---|---|
| Connector精确身份 | NuGet index最高3.2.1，文档3.2.2不能当已发布包。3.2.1 nuspec仓库指向taosdata/taos-connector-dotnet，短commit 70cd1c0；官方v3.2.1 annotated tag解析为完整 `70cd1c0142c69b220077e042e39508014c35fc31` |
| 依赖闭包提案 | nuspec net9.0组仅Newtonsoft.Json最低13.0.3；本仓Connections锁已有13.0.4，拟保持13.0.4，Newtonsoft.Json 13.0.4自身的net6.0组没有额外包依赖（Connector的net6.0/net9.0组均依赖Newtonsoft.Json≥13.0.3）。新增包候选仅Connector；.NET10实际资产选择/闭包仍待批准后的restore核实，不写零依赖 |
| 客户端许可 | Connector源码MIT、nuspec MIT；Newtonsoft.Json 13.0.3/13.0.4 nuspec MIT。二进制内NOTICE/第三方组成待取得原件核验；客户端MIT不证明服务合法使用 |
| 服务许可 | 旧线索ver-3.4.1.8源码LICENSE为AGPLv3文本，只证明该源码许可。Enterprise 3.4.2.13合同、评估/内部合成使用期限、再分发限制、组件NOTICE尚未提供；不继承DORIS-LOCAL-01或AMBER-A1 |
| 制品锁定 | 官方发布者/仓库、index digest、ARM64平台manifest digest、config descriptor/mediaType/size/digest、layers清单均NOT_VERIFIED。能力门未通过，未遍历Docker Hub、未读取config或任何layer |
| 容量/共享 | 压缩总量、解压量、共享命中、包大小/校验值均NOT_VERIFIED；本机索引未见TDengine命名镜像不等于共享层命中0。不得把未知写为零下载预算 |
| 签名 | v3.2.1 tag官方API为`verified=false, reason=unsigned`；NuGet包签名和企业镜像签名/证明可得性NOT_VERIFIED，未验签 |
| 已知风险 | 官方公告的GHSA-67g2-ffwr-7x9h覆盖Enterprise 3.4.1.8，GHSA-5r9p-3j4f-gmgp等也覆盖旧线索。更晚GHSA-8c53-8w6m-w28r列≤3.4.2.12未认证RCE、3.4.2.13修复；因此不选择3.4.1.8或3.4.1.15。公告修复声明不是精确企业二进制修复证明，也不是“无漏洞”结论；完整组件SBOM/依赖风险仍待核 |

对旧3.4.1.8 tag API的一次请求发生URLError、正文0字节；同tag LICENSE成功。3.4.1.15两个raw文件均404，各14字节；保留失败而不推断该企业版本不存在。停止追查这些旧候选。当前网页为滚动文档，只能佐证edition/版本范围，不能替代指定企业原件。

**A申请：批准以上唯一方向的合法来源核实；在精确ARM64套件/Adapter版本、许可、digest/层清单/容量/NOTICE与风险重审补齐前，下载准入保持BLOCKED。不得把同意方向解释为允许pull、nupkg或安装包。**

## B｜TLS、源端只读与取消

证据：`adapter-config.html`把`[ssl]`原生HTTPS/WSS标为Enterprise；`privileges.html`明确权限能力仅Enterprise，社区≤3.3语法不生效，社区≥3.4.0.0直接拒绝。不能用root、SHOW结果或SQL语法成功证明只读。

单一候选endpoint为 **`wss://tdengine-adapter:6041/ws`**（未来隔离网络内部别名，尚未创建）。Profile必须完整匹配scheme/规范化host/port/path；拒绝userinfo、query、fragment、多地址、重定向和Native/REST fallback。源码WSClient固定`/ws`，不能接受任意WsUrl再静默丢弃路径。

| 跳/能力 | 拟议边界与硬门槛 |
|---|---|
| 平台→taosAdapter | Enterprise原生WSS；链、有效期、SAN/主机名均验证。Connector 3.2.1 `BaseConnection`内部构造ClientWebSocket，`useSSL`只改变scheme；已读builder/连接入口未公开自定义CA/验证回调。实际资产及平台TLS行为NOT_RUN |
| CA来源 | 不改宿主全局信任库。不以跳过验证补齐。优先要求合法服务证书被隔离运行环境信任；私有CA需要证实可用的进程/容器信任方案并单独审批准确配置与证书指纹。当前自定义CA能力BLOCKED，不假造SDK参数 |
| taosAdapter→taosd | 经taosc原生连接，不能由前一跳WSS推断加密。候选同机内部网络仅Adapter可达taosd:6030；该跳加密可配置性、凭据保护和精确版本证据NOT_VERIFIED。如保留内部明文必须明确单独接受风险；本轮未接受 |
| 权限 | 独立合成reader账号，只允许指定database的必要目录读取；无写入、DDL、用户/角色管理、授权、UDF、跨库、订阅等权限。3.4.2.13准确RBAC/系统元数据最小授权列表待原件核实，不直接套早期GRANT READ语法；不授予管理员权限方便自证 |
| 真实只读/撤权 | 后续由隔离fixture管理员准备结构并从独立见证通道证明授权；reader执行必要元数据正例和写/DDL/跨库负例。撤权后旧/新连接、Enable/Discover/Worker/Catalog必须失败关闭，检查真实源状态未变 |
| 取消 | 已读3.2.1 `WSClient.Query(string[,long])`为同步接口，无调用方CancellationToken；Dispose会关闭连接，BaseConnection的内部token不等于源端取消API。调用方停止等待、传输已关闭、源操作已结束须三项独立证据。源端通过独立管理员观察特定请求/会话结束且无遗留操作；应用账号不获取该管理权限。当前后三层闭环未证实，不用Task.Run/WaitAsync冒充取消 |
| 重连 | 首切片要求自动重连/HA关闭、单endpoint、无隐式查询重试，但尚未证明可配置达成：WSClient.Query第303–319行异常后仍进入第二次DoQuery，Reconnect关闭时也不能据此推出零重试。此项作为源码见证的额外准入缺口，须核对实际分支/异常并确定可行的有界策略，不能只设置AutoReconnect=false就称满足；应用新建连接必须重验目标、scope、secret版本与授权。既有Worker最多2次尝试不得变成无条件驱动重试，需明确可恢复错误与取消不重试 |

**B申请：批准上述原生WSS路线与硬门槛；不批准降级ws/忽略证书。网关方案未推荐、未申请具体依赖；如改走网关须另列精确制品/资源/TLS终止位置，且仍需真正源端权限。取消或CA无法满足时停止产品准入。**

## C｜凭据与公共合同

源码事实：`G4ConnectionModels.cs`的TDengine profile仅WsUrl/Database/TimePrecision/TimeZone；Rules当前只允许PG/Web/Doris凭据用途；Dispatcher的SecretPurpose/Validate/Probe/Discover都不执行TDengine。`G4Composition.cs`没有TDengine DI。Web `form-model.ts:runnablePurpose`返回null。

提案：新增用途字符串 **`TDENGINE_READONLY`**；首切片服务器策略固定username=`tdengine_reader`，SecretRef仅存password，禁止URL内秘密与任意连接串。**不新增公开Username**；需要多账号时重新做最小DTO审批。本轮不实施。

规范化target/scope指纹至少包含：唯一WSS endpoint、database、服务器username、time precision/timezone、服务器策略版本、信任锚指纹、organization、排序去重site集合。变更目标/账号/范围/信任策略需新Intake及重签，不复绑旧密文。现有Secret intake没有target字段、Dispatcher的SameTarget/SameCredentialScope只为部分类型设限：拟用固定服务器策略在Intake绑定唯一目标及策略版本；持久化是否需新增字段/迁移须先冻结，不能声称现在已绑定，也不能偷偷改表。

| 消费链 | 必须承接的约束 |
|---|---|
| Intake/Create | 用途、Actor owner、组织厂区、目标策略、TTL=10分钟、一次性使用；Create为DRAFT，不继承草稿Probe资格；PG/Web/Doris与TD双向拒绝借用 |
| Draft/Saved Probe | 每次IO前核实当前target/scope/secret版本，秘密只在内存解密；保存后Probe必须绑定config revision/hash，10分钟过期；网络/TLS/认证/只读/schema各阶段真实验证 |
| Enable | 复用两阶段预约、CAS、幂等去重、最新Probe、重新物理连接权限复查；不得仅因历史Probe而ACTIVE |
| Discover/Worker | 当前会话票据与授权、revision/hash/secretVersion/scope、20秒期限、30秒租约/fence；取消/撤权/轮换/禁用即时阻断结果提交；task资源不借旧任务实例 |
| Catalog | 读取时重新授权/范围过滤、TTL/stale、元数据指纹含TD独立adapter版本；现有CanonicalCatalog非Web统一pg-m1-v1，必须最小分支修复并保留旧快照规则 |
| 轮换/禁用 | 新ref正确用途/target/owner/scope并单用；secretVersion递增、旧Probe/Job/Snapshot失效；禁用中断在途任务；已绑定secret不能因intake TTL过期被错误再激活 |
| 审计/幂等 | 原connection与catalog事件使用脱敏目标、结果分类及Trace；不记录密码/连接串；同键同体重放、异体冲突、ETag/CAS与事务审计保持 |
| UI/生成链 | 新用途联动intake/probe/save/enable/discover/cancel/stale/error；后端Models/Rules→G4 OpenAPI→现有合同生成器→g4-generated.ts→UI和契约测试，当前预览不提前开放 |

**C申请：同意固定服务器账号＋独立用途/目标绑定的最小方向；Profile保持四字段。任何持久化变更先提供准确合同差异再批；不以普通授权覆盖公共DTO/数据库变更。**

## D｜单机资源与取得门

OBSERVED只读：Darwin arm64、12 CPU、物理内存34,359,738,368 bytes（32GiB）；Docker context=`desktop-linux`，Engine=29.9.2/aarch64、12 CPU、VM MemTotal=16,787,419,136 bytes；`df -k .`首次可用281,600,000 KiB、下方独立复核281,585,516 KiB。初次sandbox的sysctl/socket拒绝已保留，正常提权后只读核实成功；首次空字段/0不当资源值。本机命名镜像索引未见TDengine。未检查卷内容、未变更Doris资源，缓存正文未核验，不能宣称可复用。

候选单机布局（PROPOSED，非实测需求）：taosd与taosAdapter各1组件/各1容器，同一Docker VM；平台PG 1、OIDC 1、API 1、Web 1，共6组件/容器；不启动taosKeeper/Explorer/TDGpt/TMQ及额外源。Enterprise原件若要求额外组件，停止并修订准入。

| 预算/资源 | 拟议停止上限与未知 |
|---|---|
| CPU/内存 | source 2容器合计4 vCPU、4GiB；平台4组件合计4 vCPU、6GiB；总8 vCPU、10GiB。不是测得峰值，须先最短启动验收，无足够余量即停、不调整VM |
| 磁盘 | source合成数据≤1GiB、日志≤256MiB；平台任务数据≤2GiB、过程证据≤1GiB。制品压缩/展开另算，目前未知；下载上限未准入，不能凭这些数据上限放行pull |
| 端口/网络 | Adapter仅内部6041；taosd仅内部6030及原件证明必要的内部端口（未证前不扩开）；源网络仅API↔Adapter、Adapter↔taosd，默认无宿主发布；平台Web/API/OIDC回环端口在后续Run注册并查冲突 |
| 证书/卷 | 新任务server cert/key与CA外置只读挂载，真实私钥不提交；source数据与日志、平台PG/OIDC数据按TaskId/RunId唯一卷登记。不得挂载Doris保留卷或跨任务runtime/PFX |
| 下载/解压 | ARM64 manifest/config/layers/共享命中和包闭包补齐后单列压缩总量、最大展开量、可用盘余量与独立审核；未知峰值和保守cap分列，不用Doris预算 |

host_continuity.py当前`--task-id G4-M2-TDENGINE-01`实测exit2（invalid choice）；没有借旧TaskId伪装通过。只读pmset显示AC sleep=0/displaysleep=10；用户本任务能源确认、锁屏/熄屏有界monitor与整窗连续性仍NOT_VERIFIED。P0仅短命令；长产品准入之前需适配入口、用户确认及有界实测，不改全局电源设置。

**D申请：以上仅资源规划上限；在服务原件/合法性/精确尺寸、实际组件和CA方案核实前，不申请或准许服务启动。**

## E｜最小实施边界与合同缺口

仅连接生命周期和元数据发现；不提供业务时序查询、订阅、写入，不扩大M4时序读取。固定合成数据库/服务策略，禁止用户SQL、自动发现、多地址、HA、Native/REST fallback。

| 元数据 | 现有表达及最小缺口 |
|---|---|
| database | CatalogObject.Schema可按明确TD命名空间规则承载database；必须在生成合同/呈现中说明，不能伪称关系型schema |
| stable/subtable/普通表 | Kind当前注释TABLE/VIEW；缺TD类别及子表→stable父标识。拟新增类型化TD对象扩展，保留旧源序列化/指纹；字段名及schema差异先冻结 |
| tag/列 | CatalogField有Name/NativeType/Nullable/Ordinal/Precision/Scale，无TAG/COLUMN角色。需可选TD字段角色；不读取实际tag业务值，不将tag混成普通列后称保真 |
| 原始类型 | NativeType可存原生类型，Precision/Scale可存decimal参数；长度/unsigned等必须完整保留在原生声明或经批准扩展，不推断不可得Nullable；未知可空性当前bool不能表达，需显式可用性设计 |
| 时间精度/时区 | profile有ms/us/ns/UNKNOWN与TimeZone，但snapshot没有源观测精度/时区；不能把用户输入当源事实。拟TD对象元数据保存原始precision与时区来源/unknown，必要时用字符串/int64纳秒，不转DateTime/double丢精度 |

以上是**公共合同缺口申请**，不是本轮已批准字段变更。后续冻结最小DTO、OpenAPI、生成TS、规范化指纹和存量兼容策略，经非作者审查后才实现；不接受丢失语义的“保真”交付。

候选交付路径：`infra/tdengine/`基础Compose、隔离测试覆盖层、生产参考覆盖层与无秘密配置样例；`docs/deployment/tdengine.md`。生产覆盖层只作单机参考，单点/最小权限/证书外置/持久化/备份恢复边界需写清；只验空库元数据恢复不能宣称业务整库恢复。G4非Development Guard和生产自动迁移禁止保持。

工程只读结论：workflow.py、workflow_environment.py、workflow_m2_build.py/fixture.py/web_cache.py/evidence.py、execution_preflight.py与verification-gates.json有PG/Web/Doris准入，**没有本TaskId adapter**。后续需最小TD任务准入模块，接入上述任务白名单、准确audit/DI/消费者与受影响gate；host_continuity也需支持本TaskId。继续公共workflow_execution双流/结构化结果、workflow_evidence有限扫描、task_run_timeline schema2，exitCode与timingStatus分列；首证据复用test-review-evidence.ps1。不为本任务重造执行框架、不沿用旧任务Web cache/report目录。

**E申请：只同意上述最小切片方向与缺口清单；详细DTO/持久化/工程owned_paths须在本树补齐并明确批准，P0不先改代码或共享脚本。**

## F｜硬门槛、风险接受与验收

1. 硬门槛：合法精确Enterprise ARM64套件与Adapter版本；WSS信任链/主机名；源端有效最小只读与撤权；三层取消；DTO保真；TaskId工程适配与宿主连续性。缺任一项保持BLOCKED，不用Mock/历史PASS/风险签字抹除。
2. 原件取得后才能验证：包/层hash与签名、组件NOTICE/SBOM、实际TLS/CA接口、native内跳保护、RBAC生效、ARM64运行/内存/磁盘峰值；本轮均NOT_VERIFIED或NOT_RUN。取得本身也需先补A/D准入。
3. 可单独裁决风险：单机单点、如选择内部明文的准确网络边界、特定签名不可得及许可证用途限制。尚未接受；未知合法性、证书绕过、无只读能力不列可接受风险。
4. 后续真实短场景：可信TLS正例与错CA/过期/SAN负例；读元数据正例与写/DDL/跨库拒绝；旧会话撤权和新连接失败；调用方/传输/源端取消各有原件；scope/账号/secret用途双向隔离；轮换/禁用/TTL/幂等/CAS/Worker fence；stable-subtable-tag/native type/ms-us-ns/unknown保真与UI全流程。
5. 影响验证：公共合同与生成链、Connections/API持久化和审计、受影响Web/交互，以及PG/Web/Doris兼容负例；按gate输入键复用合格旧证据，不能用历史成功覆盖TD。源权限、CA、取消新场景必须FRESH；不从I01重跑全链、不重复无变化restore或自然TTL等待。
6. 本轮真实产品测试、prepare/restore、build、服务、SelfTest、CI全部 **NOT_RUN**；不创建任何Review ZIP、不更新main。普通push只交文档，不解锁实施。

**一次回复需裁决的项目**：A合法Enterprise来源/用途与候选版本；B原生TLS信任方案、内跳风险及取消硬门槛；C固定username/独立用途和目标绑定；D单机预算方向；E元数据DTO缺口及最小实施边界；F验收与明确未接受风险。可一次同意方向，但A/B缺证和E准确合同仍阻断获取/实施；在本会话本树补证，不另建恢复任务。

## 来源与恢复索引

所有公开原件、HTTP状态、UTC、精确来源URL、实收字节、SHA256见[metadata/index.json](metadata/index.json)。抓取不跟随重定向、请求identity编码、每响应最多8MiB，累计最多64MiB；没有触达layer/nupkg/安装包/源码压缩包，也未访问非白名单跳转。此次总实收 **1249459 bytes**（包括失败正文，0字节网络错误单列）；不是压缩制品容量。HTTP原件保持原字节；其中5份含CRLF或上游尾空格的原件用base64封装（index标明encoding/originalFile/storedBytes），解码后核对receivedBytes与SHA256，避免Git换行转换。本任务Markdown用UTF-8/LF。

| 依据 | 索引文件 / 官方来源 |
|---|---|
| WSS/edition | [adapter-config](metadata/adapter-config.html) · [官方配置](https://docs.tdengine.com/operations-and-tooling/components/taosadapter/configuration/) |
| 源端授权 | [privileges](metadata/privileges.html)、[users](metadata/users.html)、[security](metadata/security.html) · [官方权限](https://docs.tdengine.com/tdengine-sql/user-and-privilege/grant/) |
| C#兼容/TLS说明 | [csharp](metadata/csharp.html)、[client-security](metadata/client-security.html) · [官方C#](https://docs.tdengine.com/developer-guide/connectors-reference/csharp/) |
| 发行/依赖 | connector-index/registration、connector-3.2.1.nuspec、newtonsoft-13.0.3/13.0.4.nuspec · [NuGet](https://www.nuget.org/packages/TDengine.Connector/3.2.1) |
| 源码接口/签名 | connector-tag/tag-object/tree、connector-baseconnection/wsclient/builder、connector-license · [固定官方提交](https://github.com/taosdata/taos-connector-dotnet/tree/70cd1c0142c69b220077e042e39508014c35fc31) |
| 风险 | [advisories](metadata/advisories.html) · [官方公告](https://docs.tdengine.com/security-guide/security-advisories/) |

本地源码证据均以Base恢复：`backend/src/Contracts/OntologyPlatform.Contracts/G4Connection{Models,Rules}.cs`；`backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/Connection{SourceDispatcher,ApplicationService*}.cs`；`backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs`；`apps/web/src/features/connections/form-model.ts`；`apps/web/src/lib/api/g4-generated.ts`；`scripts/maintenance/`上述消费者及`docs/development/verification-gates.json`。无需重载全部历史会话。

## 非作者审查与轻量检查

非作者Reviewer `/root/tdengine_p0_review` 最终复核通过：前述P2资源见证可恢复性及P3依赖措辞、隐式重试、来源拼写均已关闭，P0文档交付无阻断项。Reviewer独立执行完整暂存diff-check exit0，核实暂存23条记录/22份正文（含5份base64解码）size/SHA256与累计1,249,459 bytes一致、无未暂存差异、仅授权路径。产品准入仍BLOCKED；审查不授予下载、实施或main权限。

轻量检查：`python3 /tmp/tdengine-p0-check.py` exit0，23条HTTP记录合计1,249,459 bytes；每个保存正文（base64先解码）的size/SHA256、8MiB/64MiB预算、本地Markdown链接/UTF-8/LF核验通过。临时检查器不作为交付依赖：复核只需按index读取file、按encoding解码，核对receivedBytes与sha256并累加，再检查本卡和申请的相对链接。

`pwsh -NoProfile -File scripts/test-review-evidence.ps1 -EvidenceFile /tmp/tdengine-p0-evidence.json` exit0，输出`scope=EVIDENCE_SCHEMA_ONLY, checks=3, product=NOT_RUN`。临时schema1输入为本轮文档检查PASS/exit0、host-task-preflight FAIL/exit2、product NOT_RUN/null；CI NOT_RUN。仅复用既有schema检查，不伪造产品证据或新增工程框架；正式消费者的actualCi输出NOT_VERIFIED不改变本轮CI未执行事实。

首次完整暂存diff-check发现上游`connector-builder.cs.txt:367`尾空格（FAIL），并有4份CRLF原件转换提示；未裁剪原件，改为base64保留，恢复索引已登记。第二次暂存检查因申请末尾新增空行exit2，已去除；随后Master及Reviewer分别执行`git diff --cached --check`均exit0。

宿主资源复核（工作目录为任务树，2026-11-13 UTC；逐命令stderr均为空）：

| UTC | 精确命令 | exitCode | stdout必要原文 |
|---|---|---|---|
| 05:25:30.032621 | `sysctl -n hw.memsize hw.ncpu` | 0 | `34359738368` / `12` |
| 05:25:30.035321 | `docker --context desktop-linux info --format '{{json .ServerVersion}} {{json .Architecture}} {{json .NCPU}} {{json .MemTotal}}'` | 0 | `"29.9.2" "aarch64" 12 16787419136` |
| 05:25:30.119751 | `df -k .` | 0 | `/dev/disk3s5 482746452 174710088 281585516 39% 2676491 2815855160 0% /System/Volumes/Data`（KiB） |
| 05:25:30.124244 | `pmset -g custom` | 0 | `AC Power: ... displaysleep 10 ... sleep 0 ...`（只保留相关原字段） |

失败见证（早先调用UTC未采集，记UNKNOWN而不回填）：首次默认sandbox资源组合命令最终exit1；stderr含`sysctl: sysctl fmt -1 1024 1: Operation not permitted`及`permission denied while trying to connect to the docker API`，后来正常提权的只读查询如上。分支创建初次`git switch -c codex/g4-m2-tdengine-01`被`.git/...lock: Operation not permitted`拒绝，随后同命令正常提权exit0；没有自动审批拒绝或绕过。只读`python3 -B scripts/maintenance/host_continuity.py preflight --task-id G4-M2-TDENGINE-01`单独exit2，stderr为`argument --task-id: invalid choice: 'G4-M2-TDENGINE-01'`；该入口缺口未修复、不借旧TaskId跑。

资源索引通过`docker --context desktop-linux image ls --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}'`只读取得（组合命令exit0）：可见Doris历史image短ID `1d4ccee8d7cc` / `c7b4288a34af`，未出现TDengine命名仓库；该观察仅命名索引，不作为层复用或删除依据，不读取容器env、卷或私有runtime。没有资源删除候选被本任务授权。

## 2026-11-13 用户接受复审裁决与恢复条件

用户明确接受附件 `Codex-G4-M2-TDENGINE-01-P0-Review-Decision-20261113.md`，仅授权本申请与任务卡追加、轻量文档检查及一次增量Review、原任务分支普通提交/push。对应已审P0 Head：`df6c316878f81e634d316f32e0afcba495a8441b`。本段为当前有效裁决；此前申请、元数据原件、历史失败及 `P0_BLOCKED_WITH_WITNESS` 保留原样。P0文档接受，不是产品准入通过；唯一当前状态仍由[任务卡](../../tasks/G4-M2-TDENGINE-01.md)记录。

**P0DocumentReview=ACCEPTED；ProductAdmission=BLOCKED；PrimaryBlocker=LEGALLY_AVAILABLE_ENTERPRISE_TEST_SOURCE_NOT_PROVIDED；NextAction=WAIT_FOR_EXTERNAL_INPUT。** 当前材料未提供足以准入的合法Enterprise验证来源，不推断用户没有许可，也不要求为完成P0立即采购。一般继续研究许可不替代厂商使用权或精确能力证据。

| 项 | 已接受的方向及仍有效的限定 |
|---|---|
| A | Connector 3.2.1＋Enterprise 3.4.2.13 Linux ARM64仅保留为调查候选。公告修复号不等于唯一安全版本，也不证明企业ARM64/Adapter制品或许可存在。供应方提供其他受支持版本时只登记待审候选及一次差异，不自动换版/拉取/安装。先核合法来源、用途期限、发布者、版本/架构、交付形式、地址、校验资料和容量；OCI核index/平台manifest/config/layers，安装包核平台/大小/官方校验和/签名资料，不强求OCI字段。改安装包/自建镜像仍须另行准入。二进制内部NOTICE/SBOM/组成与运行行为留待获批取得后检查，不形成下载前必须检查内部原件的循环。旧元数据预算不重置，无新输入不重复抓取。 |
| B | 原生WSS、链/主机名/有效期、源端最小只读与真实撤权、三层取消门槛保持。外部TLS终止或仅限制平台SELECT不能替代源权限。源码存在Reconnect后再次DoQuery路径，但是否实际重发待有界实验，不断言每次重发或零重试。合法来源明确后先另申请小范围WSS/证书负例、权限、取消/重试探针，再考虑完整Adapter/UI。取消分别见证调用方、传输、源操作终止；自然完成不冒充取消，产品账号无管理权，探针不扩大业务时序查询。优先隔离进程/容器信任；不改宿主全局信任、不假造CA接口。内跳保护未知，本轮不接受内部明文风险。 |
| C | 同意TDENGINE_READONLY、服务器固定tdengine_reader、SecretRef仅密码及四字段Profile方向，不授权用途校验或存储实现。后续一份准确差异说明Intake/target策略版本/信任锚/scope绑定存储、失效重签、跨用途隔离、历史密文与绑定后TTL。既不推定无需迁移，也不预设新表；多账号/公开Username另批。 |
| D | 接受规划上限6组件/容器、8 vCPU/10GiB（源4GiB、平台6GiB），源数据1GiB/日志256MiB、平台数据2GiB/过程证据1GiB；制品与解压另计、未知不写零。未准入实际资源、启动、卷/证书或VM调整，不挂载/清理Doris保留资源或复制旧秘密。 |
| E | 认可对象类别/父stable、TAG/COLUMN、可空性unknown、源观测precision/timezone缺口；false不能代未知、用户配置不能代源事实。合法源及短能力探针可行后，才冻结C/E的DTO/OpenAPI/TS/规范化/快照兼容及必要持久化差异，先独立Review再申请实施。新TD版本规则不重算PG/Web/Doris历史指纹。Compose/部署文档仍为后续目标，G4 Guard保持。TaskId/消费者/gate/计时/缓存适配将来在本任务内常规完成，不另建工程优化任务、不逐小补丁审批；本轮不改脚本。 |
| F | 产品、服务、prepare/restore/build、SelfTest及CI保持NOT_RUN；无新增验收或风险接受，不继承DORIS-LOCAL-01/AMBER-A1。签名可得性与完整SBOM按取得前后分阶段核验，未证有签名不是验签失败；非法来源、无源权限、TLS绕过不能由一般风险签字替代。无ZIP/main集成/其他Adapter开发。 |

外部输入仅需脱敏资料：①可核查的合法研发/合成测试用途、期限、分发限制；②精确发行版本、ARM64支持、配套taosAdapter/taosc与WSS/权限范围；③官方制品标识/交付形式、校验资料及取得渠道；④证书信任、Adapter→taosd保护、Connector兼容、重试/查询取消资料。不要把密码、license key、下载令牌或生产数据放入聊天/Git。已有隔离测试实例可作为替代验证源提案，但需另核版本、数据、网络、账号、负例/取消测试授权及本机ARM64差异，不能自动访问或使用生产实例。

严格恢复顺序：**合法来源及取得条件 → 精确获取授权 → 原件检查和获批有界能力探针 → 一次性冻结C/E准确合同并非作者审查 → 产品实施授权 → 按影响真实验收**。来源缺失即等待，不循环重试P0；新材料不自动解锁任何后续步骤。本轮不再联网研究、Registry遍历、资源探测、prepare/restore/测试、下载、服务、产品/DTO/数据库/工程脚本修改；不采购、试用、不新建恢复任务、不启动Oracle/M3/G6或改变总体计划。

本轮保留原会话/树/分支、全部既有证据和历史状态；仅在外部输入到达并满足各步授权后原地恢复。原P0复审方未逐件重算全部22份正文、未测产品或证实企业原件，本轮亦不重复这些检查。

本次增量检查与非作者Review回执：Master轻量检查exit0，确认仅两份获准Markdown变化、原Head正文逐字节保留为前缀、UTF-8/LF及本地链接/锚点有效；`git diff --check` exit0。原非作者Reviewer `/root/tdengine_p0_review` 一次增量审查通过、无阻断发现，并独立执行diff-check exit0；仅审附件与本次增量，未联网、探测资源、运行测试或重验元数据。fetch确认origin/main仍为指定Base；本轮结束普通提交/push后停在WAIT_FOR_EXTERNAL_INPUT。
