# Doris 单机部署与平台接入边界

当前为 G4-M2-DORIS-01 条件实施文档；制品身份已核验，真实部署与恢复演练尚未完成。不得将本文当作生产验收结果。准入和实际运行记录见[任务卡](../tasks/G4-M2-DORIS-01.md)。

## 部署模型

单机仍包含一个 FE 和一个 BE：FE 提供 MySQL 查询入口与元数据管理，BE 提供执行与存储。测试使用单副本，不启用外部 catalog、对象存储或额外 Meta Service。测试和生产使用同一版本化 Compose 来源，通过独立覆盖层区分资源、数据、账号和证书。

批准版本为 Doris 4.0.8 linux/arm64：FE manifest `sha256:c7b4288a34affac9fe809a2895565b4d558ea3b85fbf5d29bb1ec27d398e4f02`，BE manifest `sha256:1d4ccee8d7cc5e33f1c16e0b3ce764f5f764c396ea5e938a8793f88682c982f7`。不使用浮动latest，不自动选择amd64；未测试平台保持NOT_RUN。

## 本机合成环境

FE容器4GiB、BE容器6GiB；平台PG0.5GiB、OIDC1GiB，四容器合计不超过12GiB，宿主API/Worker、Web及测试/浏览器合计另不超过4GiB。VM由操作者调整，Engine实际可见至少15GiB且无挤占预算的其它工作负载。JVM堆与BE内存参数必须给非堆/本机线程留余量，不能只限制容器而沿用更大的默认堆。

只用任务标签、私有证书与合成数据，持久卷不得与既有开发或生产卷共享。测试管理员只用于建夹具、授撤权限、观测查询；应用只有独立只读账号。应用元数据读取必须验证全部有效权限及目标范围；不以试写业务数据证明只读。

宿主API连接FE时，必须同时验证连接地址、发布端口、SAN/SNI一致。容器内服务名不能直接假定在宿主可解析。不改全局hosts，不降低VerifyFull；私有CA由本任务显式指定，不安装系统信任。只有批准的loopback端口可映射，内部RPC不发布到公网。

## 生产部署配置的边界

生产覆盖层不得带入测试管理员、fixture初始化、默认口令、合成CA私钥或测试FE4/BE6限额。生产容量由操作者按负载配置，不能使用开发测试成功作为生产容量依据；单机单副本存在单点故障，不提供高可用承诺。

凭据和服务端证书通过外部私有文件提供，不写入Compose正文、Git、构建上下文或审查ZIP。数据卷、备份目录、文件权限、备份密钥的所有者由操作者明确管理；启动前检查必需参数缺失必须失败关闭。升级前记录镜像digest、配置和数据备份身份；先做隔离恢复验证再执行正式升级，不能承诺任意版本数据格式均可原地回滚。不得以自动删卷作为失败恢复流程。

本轮生产模板仅提供Doris服务配置来源与平台接入前提。平台 `G4Composition.AddG4Module` 的非Development拒绝保持不变；禁止将Production伪装成Development。实际生产源接入、部署、容量/SLA、高可用及生产备份恢复均NOT_RUN，需独立生产准入。

## 验收顺序

制品获取与内容/风险检查 → 资源与隔离准入 → Compose静态渲染 → 有界就绪 → 原生MySQL端口TLS及坏证书/降级拒绝 → 有效只读权限与撤权 → 源端取消见证 → 平台完整凭据生命周期 → 合成备份恢复演练。首次OOM、进程退出、最终健康失败或就绪超时停昂贵链，保留证据做短定位；健康starting期间不误判失败。

## 当前源码与静态验证

`infra/doris/compose.yaml`为共同来源，必须选用`compose.test.yaml`或`compose.production.yaml`之一，不叠加两种环境覆盖层。`.env.example`只含非敏感路径和合成预算；配置示例必须复制至私有目录，替换所有REPLACE标记，证书外置，不直接挂载源码示例。生产覆盖层另要求独立容量、配置和证书参数；使用独立Compose项目和卷，不能复用合成项目名。

当前仅支持静态检查：从仓库根目录执行`docker compose --env-file <私有非敏感环境文件> -f infra/doris/compose.yaml -f infra/doris/compose.test.yaml config`；生产静态检查替换最后一个文件为`compose.production.yaml`，并显式提供所有生产参数。此命令不启动设施。未放行`up`，未验证备份/恢复操作，不把静态模板作为完整部署交付。

Compose先插值再合并覆盖层，因此生产渲染当前仍需填写base的`DORIS_FE_MEMORY/BE_MEMORY/FE_CONFIG/BE_CONFIG/TLS_DIR`，以及对应的`DORIS_PRODUCTION_*`五项。可将base五项填为相同生产值以避免重复维护；最终合并结果使用生产覆盖值。生产缺参拒绝已验证，但不据此声称插值前提完全独立。

镜像内`start_fe.sh`实际读取`JAVA_OPTS_FOR_JDK_17`；示例FE堆2GiB，BE堆512MiB及显式`mem_limit=3G`，仍待运行确认线程/非堆与最终峰值。脚本自动补充必要JDK17 opens参数，Compose直接调用已核验启动脚本，保留BE环境检查。健康检查只提示端口存活；总就绪窗口拟为240秒，真实准入还须管理员经直接TLS认证、FE存活与BE注册/Alive、fixture单副本成功。首次OOM/退出/最终超时停止昂贵链，不能无限重启。

2026-11-13只读诊断发现VM的`vm.max_map_count=262144`和约1GiB swap不满足BE启动要求（至少2000000、禁用swap）；nofile65536符合。操作者完成支持的VM配置调整后再复核，不修改全局设置或设置`SKIP_CHECK_ULIMIT`绕过。宿主合成客户端目标计划为`localhost:19030`，服务证书须包含DNS SAN localhost，客户端使用显式私有CA+VerifyFull；该路径和证书验证仍NOT_RUN。实例首次启动前必须在私有FE配置中设置随机管理员口令对应的两阶段SHA1；应用不得持有它。

准确启动/恢复命令将在执行准入和真实验证后补齐。当前[资源差异与剩余项](../evidence/G4-M2-DORIS-01/post-download-status.md)未闭合。
