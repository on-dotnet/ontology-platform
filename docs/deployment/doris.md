# Doris 单机部署与平台接入边界

当前为 G4-M2-DORIS-01 条件实施文档；制品身份、开发FE/BE启动、TLS和合成元数据已核验；OIDC/UI/API生命周期、撤权、运行中取消与空合成表元数据恢复已通过。不得将本文当作生产验收结果。准入和实际运行记录见[任务卡](../tasks/G4-M2-DORIS-01.md)。

## 部署模型

单机仍包含一个 FE 和一个 BE：FE 提供 MySQL 查询入口与元数据管理，BE 提供执行与存储。测试使用单副本，不启用外部 catalog、对象存储或额外 Meta Service。测试和生产使用同一版本化 Compose 来源，通过独立覆盖层区分资源、数据、账号和证书。

批准版本为 Doris 4.0.8 linux/arm64：FE manifest `sha256:c7b4288a34affac9fe809a2895565b4d558ea3b85fbf5d29bb1ec27d398e4f02`，BE manifest `sha256:1d4ccee8d7cc5e33f1c16e0b3ce764f5f764c396ea5e938a8793f88682c982f7`。不使用浮动latest，不自动选择amd64；未测试平台保持NOT_RUN。

## 本机合成环境

FE容器4GiB、BE容器6GiB；平台PG0.5GiB、OIDC1GiB，四容器合计不超过12GiB，宿主API/Worker、Web及测试/浏览器合计另不超过4GiB。VM由操作者调整，Engine实际可见至少15GiB且无挤占预算的其它工作负载。JVM堆与BE内存参数必须给非堆/本机线程留余量，不能只限制容器而沿用更大的默认堆。

只用任务标签、私有证书与合成数据，持久卷不得与既有开发或生产卷共享。测试管理员只用于建夹具、授撤权限、观测查询；应用只有独立只读账号。应用元数据读取必须验证全部有效权限及目标范围；不以试写业务数据证明只读。

宿主API连接FE时，必须同时验证连接地址、发布端口、SAN/SNI一致。容器内服务名不能直接假定在宿主可解析。不改全局hosts，不降低证书链、名称、有效期及用途验证；私有CA由本任务显式指定，不安装系统信任。只有批准的loopback端口可映射，内部RPC不发布到公网。

## 生产部署配置的边界

生产覆盖层不得带入测试管理员、fixture初始化、默认口令、合成CA私钥或测试FE4/BE6限额。生产容量由操作者按负载配置，不能使用开发测试成功作为生产容量依据；单机单副本存在单点故障，不提供高可用承诺。

凭据和服务端证书通过外部私有文件提供，不写入Compose正文、Git、构建上下文或审查ZIP。数据卷、备份目录、文件权限、备份密钥的所有者由操作者明确管理；启动前检查必需参数缺失必须失败关闭。升级前记录镜像digest、配置和数据备份身份；先做隔离恢复验证再执行正式升级，不能承诺任意版本数据格式均可原地回滚。不得以自动删卷作为失败恢复流程。

本轮生产模板仅提供Doris服务配置来源与平台接入前提。平台 `G4Composition.AddG4Module` 的非Development拒绝保持不变；禁止将Production伪装成Development。实际生产源接入、部署、容量/SLA、高可用及生产备份恢复均NOT_RUN，需独立生产准入。

## 验收顺序

制品获取与内容/风险检查 → 资源与隔离准入 → Compose静态渲染 → 有界就绪 → 原生MySQL端口TLS及严格证书验证/降级拒绝 → 有效只读权限与撤权 → 源端取消见证 → 平台完整凭据生命周期 → 合成备份恢复演练。首次OOM、进程退出、最终健康失败或就绪超时停昂贵链，保留证据做短定位；健康starting期间不误判失败。

## 当前源码与静态验证

`infra/doris/compose.yaml`为共同来源，必须选用`compose.test.yaml`或`compose.production.yaml`之一，不叠加两种环境覆盖层。`.env.example`只含非敏感路径和合成预算；配置示例必须复制至私有目录，替换所有REPLACE标记，证书外置，不直接挂载源码示例。生产覆盖层另要求独立容量、配置和证书参数；使用独立Compose项目和卷，不能复用合成项目名。

静态检查：从仓库根目录执行`docker compose --env-file <私有非敏感环境文件> -f infra/doris/compose.yaml -f infra/doris/compose.test.yaml config`；生产静态检查替换最后一个文件为`compose.production.yaml`，并显式提供所有生产参数。此命令不启动设施。本机FE/BE已按明确授权运行并验证；平台配套网络差异已按下文获批，基础生命周期已实测；空表元数据恢复通过不代表业务备份恢复。

Compose先插值再合并覆盖层，因此生产渲染当前仍需填写base的`DORIS_FE_MEMORY/BE_MEMORY/FE_CONFIG/BE_CONFIG/TLS_DIR`，以及对应的`DORIS_PRODUCTION_*`五项。可将base五项填为相同生产值以避免重复维护；最终合并结果使用生产覆盖值。生产缺参拒绝已验证，但不据此声称插值前提完全独立。

镜像内`start_fe.sh`实际读取`JAVA_OPTS_FOR_JDK_17`；示例FE堆2GiB，BE堆512MiB及显式`mem_limit=3G`，已验证缩减线程配置可启动，最终峰值覆盖仍须结合验收原件。脚本自动补充必要JDK17 opens参数，Compose直接调用已核验启动脚本，保留BE环境检查。健康检查只提示端口存活；总就绪窗口为240秒，真实准入还须管理员经直接TLS认证、FE存活与BE注册/Alive、fixture单副本成功。首次OOM/退出/最终超时停止昂贵链，不能无限重启。

VM实际前提为 `vm.max_map_count>=2000000`、swap关闭、nofile>=60000。用户已完成内存/swap调整，并明确批准本任务仅当map_count不足时临时设为2000000；禁止跳过BE检查。已运行的宿主合成客户端使用 `localhost:19030`、DNS SAN localhost、私有CA及已批准的严格握手回调。首次启动必须在私有FE配置中设置随机管理员口令对应的两阶段SHA1；应用只使用独立reader。

已有私有配置/证书/合成凭据时，可用相同三参数前缀执行 `create --pull never fe be`，按FE→BE顺序 `start`，必须在240秒内验证原生TLS、BE注册/Alive和fixture元数据；Docker的TCP健康检查不能代替这些断言。停止仅使用本任务Compose项目的准确服务名，保留数据卷；不使用全局prune或`down -v`。首次初始化须由操作者按私有配置建立BE及固定只读夹具；固定空表恢复自动化在测试入口中提供，不能把上述启动命令当作完整部署验收。

## 当前用户部署范围

2026-11-13用户明确：本机仅用于开发合成测试，验收和生产使用用户已有独立Doris集群。因此本任务继续交付连接适配、配置与本机Compose源码，不扩展新生产集群部署或生产备份恢复演练。既有生产覆盖层仅静态参考，不能视为既有集群已验收；平台G4生产限制仍不解除。

用户已批准测试FE增加本任务专用普通bridge入口网络以恢复Docker宿主端口发布；BE仍仅接内部网络，发布仍为127.0.0.1:19030。FE具备出站能力，不能宣称为internal-only或出站防火墙隔离。禁止外部catalog/生产数据源，固定合成探针及应用目标白名单保持。

本任务源码接入使用 `G4:Doris:RootCertificatePath` 指向宿主可读的私有CA公证书。Doris凭据用途为 `DORIS_READONLY`，当前产品运行范围固定为 localhost:19030 / internal.fixture / fixture_reader、org-demo/site-a；G4非Development限制仍有效。编辑Doris目标或规范化scope不能转移旧凭据，应重新Intake/新建连接；同目标轮换沿用现有轮换入口。验收与生产使用用户既有独立Doris集群，本轮不连接或部署这些集群，也不声称当前阶段固定目标已解除。

实测4.0.8需要限制BE后台线程池；当前测试配置为FE4GiB、BE6GiB、BE pids1024。临时VM `vm.max_map_count` 修改仅在本任务明确授权下执行，阈值2000000；普通Compose不应自动修改宿主或全局VM设置。swap必须关闭，不跳过BE启动检查。测试实际使用直接TLS及严格握手回调，错误SAN、CA和过期证书均拒绝。原生VerifyFull私有CA路径曾接受过期证书，历史失败保留。

## 平台生命周期配套网络差异（2026-11-13已批准）

`infra/doris/compose.platform.yaml` 用于本机平台PG/OIDC生命周期验证：PG512MiB、OIDC1GiB，与FE/BE合计四容器11.5GiB。普通bridge `platform-entry` 使PG/OIDC具有出站能力；仅发布127.0.0.1:15432和127.0.0.1:15180。原申请禁止DB对宿主开放，FE专用bridge例外不自动覆盖此处，用户已明确批准这项差异，允许通过资源前提后继续本机生命周期验证。FE/BE网络保持独立，不发布其余内部端口；API/Worker与Web继续在宿主运行。


## 测试入口与数据保留

`python3 -B scripts/maintenance/workflow_m2_doris.py preflight --task G4-M2-DORIS-01`检查实际DI/消费者/审计与生产Guard。已有本任务FE/BE私有运行目录和已核验依赖回执时，以`adapter --task G4-M2-DORIS-01 --runtime <任务运行目录> --prepared <依赖回执>`执行定向验证；`lifecycle`使用相同参数，另要求当前API/Web构建绑定有效。入口不下载镜像或依赖，镜像/资源/端口不符即停止。

生命周期入口仅创建本轮PG/OIDC，API/Worker和Web在宿主运行；退出时精确回收本轮容器和宿主进程，保留既有FE/BE。PG/OIDC卷为tmpfs，容器删除后不能把卷句柄存在解释为数据保留；成功路径在删除前将审计/数据库原件写入本任务私有证据目录。原件含受保护会话和加密凭据，不可提交或打包。

固定恢复夹具只对`fixture.metadata_sample`执行：备份两个字段的类型/空值/序号，确认备份完整、当前结构一致且表为空，删除并按固定DDL重建，再逐字节核对元数据。存在业务行或结构漂移时拒绝删除。它不是业务行、FE元数据目录或整个集群的备份方案。恢复中断保留备份，重试允许表已不存在；不得通过删卷恢复。


## 已批准的严格TLS验证实现

2026-11-13用户批准机制差异：MySqlConnector2.6.2使用Required启用公开证书回调，所有主连接及取消辅助连接均由同一工厂强制挂接验证器。Required不代表省略验证：实际握手叶证书以显式私有CA建立CustomRootTrust完整链，校验固定TargetHost、有效期、ServerAuth及全部链错误；未知SslPolicyErrors拒绝，不使用明文回退。当前没有SslCa驱动选项，也不安装系统信任。

自建链禁用证书下载；本机生命周期运行器对API/Worker和Web施加OS级仅loopback出站约束，覆盖驱动回调之前的潜在系统链构建行为。合成CA没有CRL/OCSP，在线撤销NOT_VERIFIED，不能据此承诺生产证书撤销策略。真实过期叶证书拒绝与原证书恢复后目录读取已在`tls-expired-f39164d081c7`通过；此前原生VerifyFull失败没有删除或改写。

最终源码复核同时补齐Doris的auditor脱敏投影：列表和详情隐藏FE主机、catalog、数据库和账号；operator保留经批准的非秘密配置。真实OIDC角色读取和旧revision修改409已在`doris-210dd06860f3`验证。
