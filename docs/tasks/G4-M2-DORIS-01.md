# G4-M2-DORIS-01｜条件执行清单

唯一状态：**WAITING_USER_IMAGE_DOWNLOAD / RUNTIME_NOT_ADMITTED**（2026-11-12）。[A–F已授权](../evidence/G4-M2-DORIS-01/conditional-authorization.md)；P0历史结论见提交6f985b6a，未改写历史申请。

- Base/origin/main：`11595ecb6560f7ed6ceca54666d32b7afcae7f35`，本轮fetch核实一致；P0 Head `6f985b6a3c9558213a63a428ddec5eca3e05057b`，申请SHA256与批准附件一致。
- 分支：`codex/g4-m2-doris-01`；托管树：`/Users/chasen/.codex/worktrees/g4-m2-doris-01/ontology-platform`；Master单写，原非作者Reviewer继续；RunId=`admission-20261112-01`。
- 边界：仅单机1FE+1BE/internal/fixture元数据；DORIS-LOCAL-01风险接受不等于安全PASS；G4生产Guard保留，禁止生产访问、更新main、未批制品/架构/预算；无中间ZIP。
- 资源：FE4GiB+BE6GiB，4容器总12GiB、宿主额外4GiB；用户已确认VM调整并保持能源策略；读回15.63GiB、0运行容器。载荷后置与执行准入前设施不启动。载荷≤5GiB/NuGet≤10MiB、解包≤100MiB、磁盘新增≤25GiB、过程≤1GiB。

## 顺序与验收

- [x] 有界元数据：逐字节校验index→ARM64 manifest→config、层清单/HEAD域名、net10依赖闭包、精确缓存/保守预算；非作者获取准入。
- [ ] 条件获取：缺失载荷、hash/签名/许可/组成/CVE检查、下载/磁盘累计；未知保留，非作者执行准入。
- [ ] 用户VM通知及资源/能源前提→有界ARM64启动、直接TLS/只读/源端取消最短见证；失败短定位不盲跑。
- [ ] 本任务TaskId/门禁/Vitest路径→凭据合同定向测试与Review→Adapter/UI/Compose；总deadline10秒，取消清理有界。
- [ ] 影响测试、真实生命周期/合成恢复、适用PG/Web兼容、稳定输入Review/提交→唯一V3独立重开及回执。

## 冻结路径与保留

[准确路径清单](../evidence/G4-M2-DORIS-01/owned-paths.md)已冻结。Master owned_paths采用[申请第6节](../evidence/G4-M2-DORIS-01/admission-request.md#6-后续源码交付和执行路径本轮不修改)逐项路径，现均在条件授权内，补充 `apps/web/vitest.config.ts`；本任务文档证据为 `docs/tasks/G4-M2-DORIS-01.md`、`docs/tasks/current-authorization.md`（追加）、`docs/evidence/G4-M2-DORIS-01/**`。新增部署/适配器/测试路径按申请，未列出源码只读；公共合同、锁、部署配置、执行器Single Writer。依赖/锁新增变化超出批准名单即停止对应获取，不为凑名单降级。

read_only_dependencies：AGENTS/PLANS、架构合同、现行政策、既有PG/Web实现/历史证据；必要消费链修改限申请路径。KEEP当前树/分支与后续有效内容缓存，解除条件为任务最终审查及明确回收；不清历史资源。保护当前两项未跟踪 `.DS_Store`。

获取准入独立PASS；首层27,383,877 bytes已校验，随后匿名token到期HTTP401停止。2026-11-12用户明确改为自行下载两项Doris镜像，Agent停止获取与依赖实施，待用户通知后同树继续；服务NOT_RUN；静态合同17+5项及缓存回归20项PASS且独立Review通过，Doris分发仍关闭。当前离线prepare一次成功、下载0；原失败保留。600秒能源观察策略持续符合、锁屏熄屏未见证，非整会话连续性PASS。
