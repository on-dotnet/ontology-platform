# G4-M2-DORIS-01｜一页当前任务状态

**IMPLEMENTATION_VALIDATED / FINAL_REVIEW_IN_PROGRESS**（2026-11-13）。同会话、`codex/g4-m2-doris-01`及原托管工作树；基线/main仍为`11595ecb6560f7ed6ceca54666d32b7afcae7f35`。

| 项目 | 当前结论 |
|---|---|
| 源码 | DORIS_READONLY Adapter、UI、凭据生命周期、严格TLS、Compose及部署说明已实现；G4生产Guard保留 |
| 定向验证 | 38单元、17接口合同、24Doris定向、120UI；8组真实生命周期；PG1、HTTPS13；实际过期证书拒绝及恢复读取各1项 |
| 证据资格 | environment/contract/backend/web/interaction五类原件、散列、构建与实际执行输入重新核验通过；各gate计数重叠 |
| 安全界限 | 仅本机合成数据；Required＋实际握手严格回调已获批并实测；原生VerifyFull接受过期证书的历史失败保留 |
| 资源 | FE4GiB＋BE6GiB；平台PG/OIDC合计1.5GiB；最终生命周期宿主峰值约1.34GiB。平台容器/宿主进程已回收，FE/BE暂留用于同任务收尾 |
| 待完成 | 共享历史证据窄资格、工程门禁、最终独立Review、提交、唯一V3与独立重开 |
| 未覆盖 | CI、Windows/Intel、生产NOT_RUN；在线撤销、完整SBOM/全量CVE及用户拉取网络字节NOT_VERIFIED |

**当前准入申请：无新增待批事项。** A–F及后续明确差异授权已足够完成本机范围内收尾；不更新main、不部署生产、不生成中间ZIP。详见[唯一任务卡](../../tasks/G4-M2-DORIS-01.md)、[TLS差异与实测](tls-validation-delta.md)。

## 以下为历史阶段记录（不代表当前阻断）

> 最新关口（2026-11-13）：**TLS_DIFFERENCE_AWAITING_APPROVAL**。原生VerifyFull＋私有CA实测接受过期叶证书；独立OpenSSL已核实际leaf并拒绝，原服务证书/健康/正常读取已恢复。严格替代草案和唯一待批事项见[tls-validation-delta](tls-validation-delta.md)。当前22项Doris定向、8组真实生命周期、PG/Web短兼容已有通过，均不能覆盖此新增TLS失败。已回收9项本任务闲置平台卷/网络；FE/BE及私有证据KEEP。main未变，无中间ZIP。

> 当前状态（2026-11-13）：**IMPLEMENTATION_IN_PROGRESS**。下文早期资源阻断均保留为历史记录；现FE/BE已启动，最短TLS/目录/证书负例/同reader取消见证通过，非作者准入通过，正在实现与验证产品链。新依赖2.6.2已禁网锁定并完成环境准备，下载0；签名验证exit0但实时撤销未知。产品12项后端与120项UI定向测试通过，完整生命周期和最终交付尚未完成。

# G4-M2-DORIS-01｜下载后核验与资源差异（2026-11-13）

唯一任务状态见[任务卡](../../tasks/G4-M2-DORIS-01.md)。同一分支/托管树，基线仍为`11595ecb6560f7ed6ceca54666d32b7afcae7f35`；本页是条件执行阶段记录，不是最终验收或新的工程任务。

| 核验项 | 本轮事实 |
|---|---|
| FE/BE身份 | 本地linux/arm64 manifest与获批digest一致，rootfs diffIDs逐项匹配批准config；未重复下载镜像 |
| 内容 | 读取OS/JDK/dpkg/config/NOTICE及启动脚本；Ubuntu22.04.5、BiSheng17.0.11；16份成功内容原件经非作者复算size/SHA一致。镜像LICENSE候选路径未取得，官方4.0.8源码LICENSE及dist许可另有原件，不能混称镜像内已取得 |
| NuGet | MySqlConnector2.6.2官方SHA512匹配；安全ZIP成员、包内ID/version/net10/MIT元数据核对通过，展开总额10,927,508 bytes，未执行包脚本；签名存在，验签NOT_VERIFIED |
| 资源诊断 | Engine可见16,787,419,136 bytes、ARM64、运行容器0；max_map_count=262144；VM swap=1048572KiB、used0；nofile65536。读取时容器禁用swap，仍不能消除VM级swap前提 |
| 源码 | base/test/production Compose与配置示例已落库；测试4/6GiB、loopback19030、内部网络、digest锁定；生产独立必填容量/配置/证书，不继承测试发布端口。静态渲染及生产缺参拒绝通过，真实运行NOT_RUN |
| 清理 | 内容检查容器从未启动；另有1个经独立窄准入的只读资源诊断容器启动，全部按准确ID删除并确认不存在。Doris服务启动0；既有镜像/卷/构建缓存保留 |

**本次一次性外部差异：**请操作者通过受支持方式使Docker VM的`vm.max_map_count≥2000000`且禁用swap，确认未中断其他任务后通知。现有16GiB内存设置已满足，不要求再次调整。`used=0`不等于无swap，容器memswap限制不等于VM已禁用swap；不设置`SKIP_CHECK_ULIMIT`，Agent不执行全局sysctl/swap/daemon修改。非作者已确认这两项真实阻断，没有证据支持第三项已确认资源故障。

**调整后的最新复核：**用户通知“已调整”后，`resource-20261113-02/resource-probe.json`显示max_map_count=2000000已满足；`/proc/swaps`仍列`/var/lib/swap`1048572KiB、used0。因此只剩禁用VM swap这一已确认外部资源缺口，前述两项记录保留为历史事实。诊断容器`4a31b635d7febd301ae4eb4d6a4cf787d26a955f844b8f62bd278d4c5f5a972c`退出0、删除0、后验不存在；Doris启动0。资源诊断累计启动2个容器，均已回收。

**内部后续工作：**用户通知后窄复核Engine/内存/并发负载及上述值；继续完成组件风险适用性、可得签名、累计磁盘和最终配置/私有CA/SAN/管理员初始化隔离准入，再独立审查最短真实探针。Compose草案不代表运行已批准；Adapter/UI/TLS/有效只读/源端取消/完整凭据生命周期与合成恢复尚未完成。DORIS-LOCAL-01下SBOM/签名可得性/全量CVE未知保留NOT_VERIFIED，未将其写成PASS。G4生产限制保持，CI/Windows/Intel/生产NOT_RUN；main未更新，无中间ZIP。

预算：Agent已知载荷31,226,265 bytes（先前首层27,383,877＋本轮包3,842,388）；用户自行拉取的实际网络字节NOT_VERIFIED。两镜像完整展开大小之和12,068,903,555 bytes，去重压缩描述符3,660,429,743 bytes，二者合计保守约14.65GiB，仍需计入环境/过程产物和实际存储增量，不能据此宣称25GiB磁盘门槛最终PASS。当前宿主可用285,078,092KiB；Docker全部历史images19.18GB、volumes619.3MB、build cache2.925GB不全归本任务，未清理。

原始证据在ignored `artifacts/workflow/G4-M2-DORIS-01/`：`content-20261113-01`保留符号链接拒绝；`content-20261113-02/03`内容/包检查；`resource-20261113-01/resource-probe.json`资源与清理；`compose-20261113-02/validation.json`静态检查。Compose首次断言把JSON内存字符串当整数导致失败，短定位转换后通过，`compose-20261113-01`原件保留。未重跑历史全量测试。

非作者阶段审查：镜像16份原件散列、两项资源阻断及精确清理确认；部署增量草案未发现明显P1，仅通过静态草案审查。生产插值仍要求base和production两套变量，说明已明确，不能以缺参拒绝测试夸大独立性。运行准入未通过，最终增量Review/唯一V3及重开尚未执行。

**最终VM复核更新：**`resource-20261113-05`读回max_map_count2000000、swap列表为空、nofile65536，用户资源设置缺口已关闭。03/04过程中swap缩小但仍启用的历史原件保留；累计5个只读诊断容器均精确回收。当前转入内部执行准入核对，仍未启动Doris。

最终格式构建：38单元、17wire、24Doris定向、120UI、8组真实生命周期、PG1/HTTPS13及TLS过期拒绝/恢复各1通过；生命周期`doris-210dd06860f3`。当前任务容器/宿主进程/闲置网络均已准确回收，四个唯一合成数据/日志卷及私有证据KEEP至审查结束；无需新审批。磁盘保守合计约17.44GiB，过程约69MiB，未将用户拉取流量未知写成通过。
