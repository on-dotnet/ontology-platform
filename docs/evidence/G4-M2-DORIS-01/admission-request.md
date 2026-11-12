# G4-M2-DORIS-01｜一次性准入申请

日期：2026-11-12（Asia/Shanghai）；Base `11595ecb6560f7ed6ceca54666d32b7afcae7f35`；RunId `p0-20261112-01`。状态以[唯一任务卡](../../tasks/G4-M2-DORIS-01.md)为准。以下均为待批准提案；本轮只核对，无服务/依赖载荷下载、安装、运行或产品代码变化。

## 1. 建议一次裁决的 A–F

| 项 | 申请内容及约束 |
|---|---|
| A 精确组合 | Doris **4.0.8** 官方 FE+BE ARM64 镜像（下列 digest），MySqlConnector **2.6.2**；依赖下限候选 Logging.Abstractions **8.0.2** / DependencyInjection.Abstractions **8.0.2**。不升级SDK/Node/pnpm；未知闭包不允许自动加包 |
| B 元数据与供应链 | 明确允许只读 Registry index/manifest/config、逐层列表及公开校验/许可元数据，并保存小型摘要（不取镜像层）。这是解除本次自动审批拒绝所需的具体确认。完整闭包、地址和大小核实之前，A不能直接解锁下载；签名/许可证/CVE不明不能套用历史AMBER-A1 |
| C 合成运行预算 | 单机1FE+1BE、单副本。申请容器总上限12GiB（FE4、BE6、PG0.5、OIDC1、余量0.5），Docker VM由用户自行确认16GiB可用；本机API/Web/测试临时进程额外≤4GiB。该缩减实验低于官方开发建议，不保证成功；首次OOM/健康失败即停，不自动扩容或切仿真。最多4容器+3宿主工作负载进程，内部子进程另监测；磁盘新增≤25GiB，载荷下载≤5GiB，过程产物≤1GiB，任何阈值先到即停 |
| D 凭据及行为 | 新用途DORIS_READONLY、双向拒绝PG/Web混用；完整生命周期和目标绑定规则见第4节。只固定FE/internal/fixture数据库元数据，不读生产业务数据、不开放用户SQL、外部catalog或M4查询 |
| E 实施范围 | typed adapter、现有生命周期/UI与错误映射、依赖/锁、Doris TaskId准入与受影响测试；同时将Docker Compose、配置模板、部署/备份恢复/升级说明及验证脚本纳入源码，供测试/生产配置使用。详见第6节；不另建工程任务 |
| F 使用与停止 | 新制品仅先用于本机隔离合成验证；完整二进制许可证/签名/CVE审计未完成，**生产使用与分发风险未接受**。生产模板可以交付，但不授权访问/部署/写入生产。待制品准入闭合且用户批准A–F后才进入实施；批准不能把未知事实改为PASS |

推荐唯一组合为分离FE/BE两个容器、同一台Mac上运行；不增备选版本或All-in-one制品。用户要求单机测试：两个组件仍必要，不需要多节点集群。生产单机存在单点故障，不宣称高可用；生产资源应按负载另行验收，不套用合成预算。

## 2. 制品、依赖、下载与许可

### Doris 4.0.8

[官方发行页](https://doris.apache.org/download/)本次列4.0.8 Stable、4.1.5 Latest。选择稳定分支4.0.8，不追随最新升级。官方仓库公开标签API本轮成功返回以下值（元数据声明，不是本机镜像/签名验证）：

| 制品 | index digest | linux/arm64 子manifest | 压缩体积（标签API size） |
|---|---|---|---:|
| `apache/doris:fe-4.0.8` | `sha256:390413325a93d9121768bda153ccaa3c7a8da4aa0fd2a466406cddc14a6399b2` | `sha256:c7b4288a34affac9fe809a2895565b4d558ea3b85fbf5d29bb1ec27d398e4f02` | 1,463,024,822 bytes |
| `apache/doris:be-4.0.8` | `sha256:d911ae3826491598be4e383cba83011a266091b8fdc6c34c036280220cc4fea9` | `sha256:1d4ccee8d7cc5e33f1c16e0b3ce764f5f764c396ea5e938a8793f88682c982f7` | 2,753,722,990 bytes |

来源：[FE标签元数据](https://hub.docker.com/v2/repositories/apache/doris/tags/fe-4.0.8)、[BE标签元数据](https://hub.docker.com/v2/repositories/apache/doris/tags/be-4.0.8)。两项合计4,216,747,812 bytes（约3.93GiB），**不是逐层去重后的精确新增下载量**。本地16条镜像列表无Doris；共享层是否已有未知，不以镜像缺失断言每层缺失。config digest、层digest/size、压缩去重值、解压占用均 NOT_VERIFIED。

读取Registry manifest/config并保存摘要的命令在执行前被自动审批拒绝，理由为“属于下载并新增证据文件；用户明确要求本轮不下载”。未重试或绕过，未生成该元数据文件。附件允许小型元数据，但执行层未接受该解释，故申请B明确确认。标签元数据已先前读取，不充当manifest内容校验。

未来地址：`registry-1.docker.io/v2/apache/doris/manifests/<digest>`、`.../blobs/<digest>`，匿名公开元数据可能经过 `auth.docker.io`；镜像层实际CDN转向域名本轮未取得，**不得预批任意CDN**。确认准确地址/转向白名单及层清单后再下载。源码/发行校验参考 [4.0.8 release](https://github.com/apache/doris/releases/tag/4.0.8)，本轮不选发行tarball，因此不额外申请JDK/Linux基底或自行构建。

### .NET 闭包

[MySqlConnector 2.6.2](https://www.nuget.org/packages/MySqlConnector/2.6.2)作者Bradley Grainger，NuGet所有者bgrainger/MySqlConnector，MIT。本轮直接读取[2.6.2 nuspec](https://api.nuget.org/v3-flatcontainer/mysqlconnector/2.6.2/mysqlconnector.nuspec)，repo commit=`775689bb3e1ab55d16171e0795264fa746e364c4`，含net10.0；与本仓库net10.0/SDK10.0.402元数据兼容，实际编译NOT_RUN。

net10.0组依赖Logging.Abstractions≥8.0.2、DependencyInjection.Abstractions≥8.0.2；不应带入其它TFM的DiagnosticSource/Tasks.Extensions。候选精确闭包：直接MySqlConnector2.6.2，传递两项8.0.2（Microsoft/MIT）。[DI8.0.2](https://www.nuget.org/packages/Microsoft.Extensions.DependencyInjection.Abstractions/8.0.2)的net8.0组无依赖；Logging8.0.2官方页面两次超时，其最终依赖闭包/CVE尚未核实。现有Connections/API锁未含这两个显式包，FrameworkReference并不等于NuGet缓存已取得；不能写“零传递变化”。最终解析如不是这三项，停止扩张而非自动批准新版本。

MySqlConnector页面包大小3.66MB；两传递包大小未取得，NuGet总载荷暂按≤10MiB预算、解压/缓存≤100MiB，**不是实测合计**。全局缓存无MySqlConnector及两项8.0.2；主树`.tools/nuget`和`artifacts/workflow`不存在；未依赖或读取已删除历史Worktree缓存。其它缓存未全面验证，命中统一待内容hash核实。

批准后仅从 `https://api.nuget.org/v3-flatcontainer/<lower-id>/<version>/<lower-id>.<version>.nupkg` 取上述闭包；API/镜像层载荷本轮均为零。实际转向域名、最终contentHash/签名须下载前元数据核对及下载后原件校验，未取得不伪造。跨平台同net10包不引入RID native依赖；预期锁影响Connections、Api、ConnectionsTests、QueryTests、SecurityTests、AgentTests，以及AppHost `packages.osx-arm64.lock.json` / `packages.linux-x64.lock.json` / `packages.win-x64.lock.json`（经Api项目引用）。最终锁差异受审，不运行异平台冒充通过；pnpm锁不应改变。

| 审查维度 | 当前状态与后续门槛 |
|---|---|
| 来源/内容校验 | 官方tag/nuspec已读；digest仅来自标签声明；manifest/config内容hash及载荷hash待核验 |
| 许可证 | Doris项目Apache-2.0，MySqlConnector与Microsoft包MIT；镜像OS/JDK/第三方完整LICENSE/NOTICE/SBOM未取得，不以README代替二进制组成 |
| CVE | [上游GHSA-473q-m89c-ghf8](https://github.com/mysql-net/MySqlConnector/security/advisories/GHSA-473q-m89c-ghf8)修复于2.6.1，2.6.2高于修复版本；不据此宣布无CVE。Doris安全页读取失败，镜像OS/JDK和Logging完整漏洞审查未完成 |
| 签名 | NuGet签名、OCI签名/attestation可信发布者均NOT_VERIFIED；index存在unknown平台条目不等于已验签。无原件不得写PASS |
| 接受范围 | 历史AMBER-A1不继承；本任务供应链缺口先保持阻断，不授权商业/生产分发 |

## 3. 宿主资源与单机拓扑

只读实测：Mac物理内存34,359,738,368 bytes（32GiB），12核；磁盘可用283GiB。`vm_stat`页大小16KiB，free64,826页约0.99GiB、inactive867,169页约13.23GiB，不能把全部inactive视为可立即承诺内存。Docker context=`desktop-linux`，Engine29.9.2、aarch64、12 CPU、MemTotal8,319,238,144 bytes（7.75GiB）。沙箱首次sysctl/socket拒绝，经已授权只读提权成功；不等于Engine离线。当前没有启动/停止任何容器。

[官方开发建议](https://doris.apache.org/docs/4.x/install/preparation/env-checking/)允许同机1FE+1BE，列FE8GB/10GB磁盘、BE16GB/50GB磁盘，明确ARM64支持。现有VM连24GB组件建议都不满足。因此申请C仅为极小单副本合成试验，资源限额属于待验证假设，失败保留见证，不借All-in-one降低账面需求。若不接受缩减实验，本机维持BLOCKED，不申请云主机/amd64仿真/源码全构建。

拓扑：平台PG、OIDC、Doris FE、Doris BE四个容器；API（含Worker）、Web、一个串行测试驱动为宿主工作负载。PG兼容源fixture与Doris阶段串行，不同时增加第5个容器；不启动Fuseki/观测全栈。API/Web必要消费者依赖必须在准入中证实，无法裁剪则重新计算预算，不能先启动。

隔离网络仅任务内部；FE MySQL9030，FE/BE内部8030/9010/9020/8040/9050/9060/8060按精确镜像配置核对，不向公网发布。仅API/Web/OIDC及开发所需FE端口映射到127.0.0.1，冲突检查不试探公网；DB和内部RPC不对宿主开放。生产Compose内部DNS直连FE，不使用代理TLS。服务器策略分别冻结环境目标，用户字段不能任意指定新host。

后续新增临时证书申请：任务私有CA一套，FE服务证书一张（SAN覆盖批准DNS），错误CA/SAN/过期证书负例，API/Web若现有私有证书不可复用则本任务一套；不装全局信任、不归档私钥、不用发行默认证书。前述为数量范围，不是本轮创建事实。Docker VM调整须用户通过系统设置确认，Agent不修改全局配置；长运行前host_continuity preflight及能源确认仍须执行。

## 4. DORIS_READONLY 与最小公共行为

已读 `G4ConnectionModels.cs`：Doris公开字段FeHost/QueryPort/Catalog/Database/Username/Tls均已存在。`G4ConnectionRules.cs` Intake只允许PG/Web用途；Dispatcher只分发PG/Web，Doris返回connector_not_enabled。新增用途需要显式批准D；无需新wire字段、路由或权限。

无迁移的源码依据：`Persistence/ConnectionSecretRecord.cs` Purpose为string，`Migrations/20261101115947_InitialConnections.cs` 为非空text，`ConnectionsDbContext.cs`无用途check constraint。用途字符串本身可直接承载，不能顺带修改持久语义。

Doris首次仅服务器固定FE `doris-fe`（实际宿主映射需在运行准入冻结）、9030、`internal`、`fixture`、`fixture_reader`、Tls=true及固定组织/厂区白名单；生产通过服务器配置冻结相应目标，不继承合成目标/账号。Tls=false在绑定/解密/网络前拒绝，客户端强制VerifyFull+显式私有CA。PG/Web与Doris secret双向拒绝，沿用既有脱敏错误码。

Doris目标比较为完整Profile值比较（FeHost/QueryPort/Catalog/Database/Username/Tls）；范围以规范化组织和厂区集合比较。任何变化均拒绝沿用旧secret，要求新建目标/重新Intake；同目标轮换走既有rotate。不能沿用当前仅Web目标比较，也不能沿用Commands.cs scope patch对Doris旧secret的自动重绑。展示名编辑仍可走现有流程。

完整消费链：Intake、Create、draft/saved Probe、Enable、Discover队列/Worker、Catalog历史快照读取时实时ACL求交、轮换/禁用/吊销/未绑定TTL、并发CAS/fence、幂等重放、session/组织撤权、审计、UI Intake。绑定后TTL语义沿用既有合同，不把未绑定10分钟TTL误改为所有已绑定秘密过期。

## 5. TLS、只读、类型与取消见证（实际均NOT_RUN）

[4.0.8 MysqlSslContext源码](https://github.com/apache/doris/blob/4.0.8/fe/fe-core/src/main/java/org/apache/doris/mysql/MysqlSslContext.java)含服务端SSLEngine/密钥库加载/握手；[MySQL证书文档](https://doris.apache.org/docs/4.x/admin-manual/auth/certificate/)说明enable_ssl。此为版本源码能力依据，**不是所选OCI二进制的TLS实测**。[4.1 TLS framework](https://doris.apache.org/docs/4.x/admin-manual/auth/tls-framework/)是另一框架，不据此声称所有协议可TLS。未来直接9030做私有CA、正确SAN成功，坏CA/SAN/过期/明文降级失败；[MySqlConnector选项](https://mysqlconnector.net/connection-options/)必须VerifyFull，禁止Preferred/Disabled/不验主机名/代理TLS冒充源TLS。

权限：固定SHOW GRANTS读取当前账号有效权限；[Doris说明](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/account-management/SHOW-GRANTS/)包含角色合并结果。仅准入固定database内必要SELECT与系统元数据最小例外，拒绝全局/跨catalog/跨database/管理员/写/GRANT权限和未知权限形态。应用账号不授GRANT_PRIV用于自证。合成管理员仅供隔离fixture创建、授/撤直接与继承角色、源端见证，不进入产品连接。应用不尝试业务写SQL证明只读。正反例覆盖继承写权限、隐表/隐列、跨库、撤权后Probe/Enable/Worker及历史目录读取拒绝。

目录固定查询白名单、参数绑定/标识符白名单：建议最多128对象、每对象256列、总4096列、结果1MiB、单次10秒；超限明确拒绝，不把截断当完整。仅元数据，不执行用户SQL。保留原始类型、precision/scale和时间精度；大decimal以类型描述/精确字符串表达，不经double；无时区类型不编造UTC。空库、无权导致隐藏、未知类型、列缺失要分开表达与测试，必要时用既有错误码拒绝，不悄加wire字段。

[客户端取消说明](https://mysqlconnector.net/overview/command-cancellation/)软取消需要另一连接向同一源发送KILL QUERY。不能把CancellationToken抛异常或断连当源端已终止。申请固定合成慢查询场景，记录连接ID/queryId，独立管理员见证PROCESSLIST/运行查询终止及FE审计结果，验证超时、显式取消、撤权取消、连接清理与后续新连接。建议CommandTimeout10s、CancellationTimeout2s、Pooling=false用于首切片，取消辅助连接最多一个；源端兼容/权限不足则阻断，不给应用管理员权限兜底。无源端见证不写PASS。

## 6. 后续源码交付和执行路径（本轮不修改）

下列为待批准最小范围，实施前将准确owned_paths冻结入同一任务卡；公共合同、依赖/锁、Compose/执行器均Master Single Writer。

| 范围 | 准确现有路径 / 拟新增路径 |
|---|---|
| 合同 | `backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionRules.cs`；Models仅必要中文说明，不增加字段 |
| 适配与消费 | `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/` 下拟增 `Abstractions/IDorisSourceAdapter.cs`、`Abstractions/DorisAdapterOptions.cs`、`Adapters/DorisSourceAdapter.cs`；修改 `Application/ConnectionSourceDispatcher.cs`、`Application/ConnectionApplicationService.Commands.cs`，检查并最小修订 `Application/ConnectionApplicationService.{Probes,Enable,Worker,Catalog}.cs` 及主partial的错误映射（目前消费PgSourceException，不能泄漏MySqlException） |
| DI/依赖 | `backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs`；`Directory.Packages.props`、Connections csproj与第2节锁文件；不把Doris SDK放Domain/ServiceDefaults，不新增EF Provider |
| UI | `apps/web/src/features/connections/{form-model.ts,form.tsx,create.tsx,detail.tsx,connections.test.ts}` 按影响修改；支持用途、TLS固定及状态，不创建第二套生命周期 |
| 部署源码（用户补充要求） | 拟增 `infra/doris/compose.yaml`、`compose.test.yaml`、`compose.production.yaml`、`config/fe.conf.example`、`config/be.conf.example`、`.env.example`；`docs/deployment/doris.md`；`scripts/maintenance/workflow_doris_fixture.py` 与部署验证入口（复用公共执行器）。不得把真实.env、密码、私钥、数据库入Git |
| 工程准入 | `scripts/maintenance/workflow.py`、`workflow_environment.py`、`execution_preflight.py`、`docs/development/verification-gates.json`，拟增 `workflow_m2_doris.py`；复用 `workflow_execution.py`/`workflow_evidence.py`/现有构建资格与归档，不复制旁路subprocess或日志解析器 |
| 测试 | `backend/tests/OntologyPlatform.ConnectionsTests/`、受影响G4契约/安全测试及Web tests；新增本任务真实TLS/权限/取消/生命周期驱动，不复制M1全链 |

部署交付要求：开发单机1FE+1BE/单副本；生产模板仍明确单机单点风险，参数化服务器目标与独立reader账号、证书外置、持久卷与目录权限、healthcheck、启动依赖、资源限制、digest锁定、网络隔离、备份恢复/升级与回滚操作说明。测试初始化管理员及合成数据只在test override，生产配置不能自动初始化测试账号。Compose config静态检查与合成恢复演练作为后续门禁；生产真实部署、生产备份恢复演练及容量/SLA验收保持NOT_RUN。不把“模板可用”宣称“生产已验收”。

现有缺口一次登记：workflow.py约317行只认Web/DELIVERY的产品gate；environment约437/451行同样旧TaskId；execution_preflight只支持历史M1–M5/G4-M1，裸M2是G3历史消费者，不能代Doris；verification-gates没有Doris真实映射。Vitest cache/report仍指向G4-ENG-DELIVERY-002，第一次UI执行前必须绑定本任务TaskId/RunId/工作树。P0不改、不运行这些入口。

实施顺序：补齐供应链/资源准入→冻结合同并非作者审查→本任务执行器/Compose准入→精确依赖一次准备与首次证据生成-解析-归档样例→typed adapter与UI→静态/单元/契约→最短真实TLS/只读/取消→生命周期与受影响PG/Web兼容→稳定输入完整适用覆盖→独立Review/提交/输入绑定/最终唯一V3独立重开。失败同输入先短定位，natural TTL仅资格核验后复用，不盲跑完整链；环境内容键命中不重复restore。所有证据JSON生成后走既有test-review-evidence；本P0只Markdown，未伪造schema2运行证据。

## 7. 本轮检查与停止

FRESH：fetch基线、独立树/分支、源码/政策检查、官方公开页面与标签/nuspec、宿主/Docker只读元数据。REUSED产品测试：无。历史M1/Web成功不重跑，也不宣称覆盖新增Doris。产品服务/测试、prepare/restore、完整SelfTest、CI及异平台均NOT_RUN。下载载荷0、服务启动0、证书创建0、ZIP0、main更新0。

关键缺项保留为BLOCKED_WITH_WITNESS：Registry读取保存被拒；Logging元数据超时及闭包/大小/完整CVE缺证；镜像完整组成/签名/逐层列表/下载转向缺证；当前VM资源不足且缩减方案未经实测。A–F可一次裁决，但不能跳过这些事实门槛直接实施。完成文档轻量检查与一次非作者审查后普通提交/push，保留同树同会话等待决定。

非作者审查回执：`/root/p0_reviewer`于2026-11-12只读核对源码与最终两文档，结论P0文档PASS、运行准入仍BLOCKED；3文件diff-check（含新文件no-index）、两文档本地链接/EOF检查exit0。作者采纳Application路径明确化建议。无产品测试执行或产品通过声明。
