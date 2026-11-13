# G4-M2-DORIS-01｜条件执行清单

唯一状态：**READY_FOR_REVIEW / LOCAL_VALIDATION_PASS**（2026-11-13）。用户已通知两镜像下载完成，同树继续[A–F已授权](../evidence/G4-M2-DORIS-01/conditional-authorization.md)范围；本轮[一页状态与差异](../evidence/G4-M2-DORIS-01/post-download-status.md)。P0历史结论见提交6f985b6a，未改写历史申请。

- Base/origin/main：`11595ecb6560f7ed6ceca54666d32b7afcae7f35`，本轮fetch核实一致；P0 Head `6f985b6a3c9558213a63a428ddec5eca3e05057b`，申请SHA256与批准附件一致。
- 分支：`codex/g4-m2-doris-01`；托管树：`/Users/chasen/.codex/worktrees/g4-m2-doris-01/ontology-platform`；Master单写，原非作者Reviewer继续；RunId=`admission-20261112-01`。
- 边界：仅单机1FE+1BE/internal/fixture元数据；DORIS-LOCAL-01风险接受不等于安全PASS；G4生产Guard保留，禁止生产访问、更新main、未批制品/架构/预算；无中间ZIP。
- 资源：FE4GiB+BE6GiB，4容器总12GiB、宿主额外4GiB；用户已确认VM调整并保持能源策略；读回15.63GiB、0运行容器。载荷后置与执行准入前设施不启动。载荷≤5GiB/NuGet≤10MiB、解包≤100MiB、磁盘新增≤25GiB、过程≤1GiB。

## 顺序与验收

- [x] 有界元数据：逐字节校验index→ARM64 manifest→config、层清单/HEAD域名、net10依赖闭包、精确缓存/保守预算；非作者获取准入。
- [x] 条件获取：缺失载荷、hash/签名/许可/组成/CVE检查、下载/磁盘累计；未知保留，非作者执行准入。
- [x] 用户VM通知及资源/能源前提→有界ARM64启动、直接TLS/只读/源端取消最短见证；失败短定位不盲跑。
- [x] 本任务TaskId/门禁/Vitest路径→凭据合同定向测试与Review→Adapter/UI/Compose；总deadline10秒，取消清理有界。
- [x] 影响测试、真实生命周期/合成恢复、适用PG/Web兼容、稳定输入Review和提交；12项门禁通过。最终V3与独立重开回执随交付。

## 冻结路径与保留

[准确路径清单](../evidence/G4-M2-DORIS-01/owned-paths.md)已冻结。Master owned_paths采用[申请第6节](../evidence/G4-M2-DORIS-01/admission-request.md#6-后续源码交付和执行路径本轮不修改)逐项路径，现均在条件授权内，补充 `apps/web/vitest.config.ts`；本任务文档证据为 `docs/tasks/G4-M2-DORIS-01.md`、`docs/tasks/current-authorization.md`（追加）、`docs/evidence/G4-M2-DORIS-01/**`。新增部署/适配器/测试路径按申请，未列出源码只读；公共合同、锁、部署配置、执行器Single Writer。依赖/锁新增变化超出批准名单即停止对应获取，不为凑名单降级。

read_only_dependencies：AGENTS/PLANS、架构合同、现行政策、既有PG/Web实现/历史证据；必要消费链修改限申请路径。KEEP当前树/分支与后续有效内容缓存，解除条件为任务最终审查及明确回收；不清历史资源。保护当前两项未跟踪 `.DS_Store`。

获取准入独立PASS；首层27,383,877 bytes已校验，随后匿名token到期HTTP401停止。2026-11-12用户明确改为自行下载两项Doris镜像，Agent停止获取与依赖实施，待用户通知后同树继续；服务NOT_RUN；静态合同17+5项及缓存回归20项PASS且独立Review通过，Doris分发仍关闭。当前离线prepare一次成功、下载0；原失败保留。600秒能源观察策略持续符合、锁屏熄屏未见证，非整会话连续性PASS。

2026-11-13续行：两镜像本地ARM64 manifest/config rootfs引用匹配；只用未启动容器读取OS/JDK/dpkg/config/NOTICE/启动脚本，全部临时容器精确回收并确认不存在。实际Ubuntu22.04.5、BiSheng17.0.11，FE默认8GiB堆须覆盖；BE启动要求max_map_count≥2000000、无swap、nofile≥60000，不能静默跳过。MySqlConnector2.6.2已获取并核验官方SHA512，ZIP安全成员/包内身份/net10资产/MIT元数据检查通过，解包总额10,927,508 bytes，未执行包内容；签名存在但验证NOT_VERIFIED。用户自行拉取的实际网络流量NOT_VERIFIED。非作者已复核16份镜像内容原件，服务执行准入待配置、风险、资源和隔离方案闭合；不启动服务、不重复下载镜像。

随后经非作者窄准入启动一次无网络/只读128MiB诊断容器：max_map_count实测262144，存在1048572KiB swap，nofile65536；前两项不符合BE启动脚本，已汇总请用户调整。诊断容器已精确删除及确认不存在，Doris服务启动仍0。Compose/config源码草案已静态渲染通过，实际参数生效、TLS/只读/取消、适配器与完整生命周期仍NOT_RUN；等待期间不绕过检查、不修改VM全局设置。

用户通知“已调整”后，`resource-20261113-02`复核max_map_count已为2000000、nofile65536；VM的`/proc/swaps`仍列`/var/lib/swap`1048572KiB、used0，故当前外部资源缺口缩减为禁用VM swap。此次只读诊断容器准确ID清理及后验通过，Doris仍未启动；不重做已通过的镜像获取或静态检查。

最新`resource-20261113-05`：用户将Swap设为0并应用后，max_map_count2000000、swap列表为空、nofile65536全部符合；之前03/04变化保留原件。累计5个只读诊断容器均按准确ID删除并确认不存在。VM调整缺口关闭，继续内容/风险/最终配置与非作者服务执行准入，不再要求用户重复设置。

最新阶段：用户澄清本机仅开发测试、验收/生产已有独立Doris集群；非作者放行最短固定合成探针，完整产品链尚未准入。实际FE内部健康但internal-only未发布宿主端口，短复现保留；用户已明确批准仅FE增加任务bridge入口。实际loopback映射与VerifyFull连接随后成功，版本SQL在BE前执行导致1105已短定位为就绪顺序问题，修正FE为握手就绪后继续。首次/短复现失败容器均停止，当前网络03有界探针进行中。

2026-11-13当前进展：用户批准的临时VM单项sysctl已执行并核验，network07的FE/BE启动成功；本机127.0.0.1:19030、VerifyFull与合成元数据通过，坏CA/错误SAN拒绝通过。同一reader显式KILL QUERY后24ms源查询消失；原驱动取消1105失败保留，不能声称驱动原生取消可用。非作者明确放行已批准Adapter/UI实施。产品Doris适配器、DORIS_READONLY分发/DI、scope变更拒绝、UI用途/TLS已落源码；12项后端定向测试与120项连接UI测试通过。产品取消、完整凭据生命周期、权限负例、目录预算、UI真实链路、最终Review/提交/V3仍待完成。当前FE/BE及私有CA/合成凭据KEEP用于同任务验证；main未变，未生成中间ZIP。

当前后续边界：API/Web离线构建通过，新增写权限/撤SELECT真实拒绝并恢复通过，取消复审无剩余P1。平台PG/OIDC网络差异已落`compose.platform.yaml`并静态验证（4容器11.5GiB），非作者确认原申请禁止DB宿主端口且FE例外不覆盖PG/OIDC，因此已一次请求用户批准，仅该依赖链等待；未启动PG/OIDC。


2026-11-13后续实测：PG/OIDC网络差异已获用户明确批准。`doris-abff4dfedbf3`完成真实OIDC、UI Intake/建草稿/探针/启用/发现、轮换/单次绑定/旧探针失效、禁用拒绝五组；新增容器和宿主进程精确回收。当前API/Connections构建绑定源码后18项Doris定向测试通过。扩展取消入口曾因夹具CLI缺少control子命令失败，未执行BE暂停；短修复后入口通过。空合成表备份恢复首次因Doris原生类型int(11)断言不符而在删除前拒绝；校正后METADATA_MATCHED。原始失败保留，未声称完整生命周期收口。当前继续运行中取消/撤权/审计与部署证据，main不变、无中间ZIP。


最新关口：[TLS最小机制差异](../evidence/G4-M2-DORIS-01/tls-validation-delta.md)。8组真实生命周期、22项Doris定向测试及PG/Web短兼容已有通过；真实过期叶证书被原生VerifyFull接受，原证书/健康/正常读取已恢复。停止TLS依赖的产品验收，准备并独立审查严格实际握手验证草案，不将适用缺口写成PASS；仍无中间ZIP、main未变。

2026-11-13当前收口：用户已批准严格TLS机制差异，实际过期叶证书被拒绝，原证书恢复后读取通过。稳定源码38项单元、17项wire、24项Doris定向、120项UI、8组真实生命周期及PG1/HTTPS13项短兼容通过；两次warm prepare零下载/零restore。五类产品证据资格已重新核验通过（计数跨gate重叠，不相加）；正在完成历史共享原件资格、工程门禁、最终独立Review、提交和唯一V3。没有待批TLS事项；在线撤销、全量供应链安全结论仍NOT_VERIFIED，CI/其他宿主架构/生产NOT_RUN。以上覆盖当前状态，下方及前文早期运行描述为历史事实。

最终格式构建：38单元、17wire、24Doris定向、120UI、8组真实生命周期、PG1/HTTPS13及TLS过期拒绝/恢复各1通过；生命周期`doris-210dd06860f3`。当前任务容器/宿主进程/闲置网络均已准确回收，四个唯一合成数据/日志卷及私有证据KEEP至审查结束；无需新审批。磁盘保守合计约17.44GiB，过程约69MiB，未将用户拉取流量未知写成通过。

最终唯一状态：READY_FOR_REVIEW / LOCAL_VALIDATION_PASS。最新原件以[正式本地验证](../evidence/G4-M2-DORIS-01/validation.json)和[一页交付状态](../evidence/G4-M2-DORIS-01/delivery-status.md)为准。12项受影响门禁全部通过，最终FE/BE及平台临时容器、宿主进程和闲置网络已精确回收；四个合成数据/日志卷及私有原件KEEP至审查结束。无新增待批事项，停在当前审查关口，不更新main或进入生产。前文各阶段等待/失败/进行中为历史记录。
