# G4-M1-MAIN-INTEGRATION-001 待审批申请

状态PROPOSED / NOT_AUTHORIZED / NOT_EXECUTED。本申请不由POSTREVIEW自动启动；不请求生产发布或M2。审批对象必须同时包括完整45项提交清单、精确源Head、目标parent、运行资源准入和本地回归。

## Git对象与最小序列

当前目标parent为d1a61daffe844475b07705797e3ad325cc3f2945；源Head为d40e6ab67360cc46aadd7ec013bd514b3f61a6ea；main为祖先，0/45。完整逐项资格见git-ancestry-and-topology.md及commit-inventory.json。G4-00 3、M1初始12、恢复22、最终8；实现范围有原授权与批量独立Review，仍没有任何main集成批准。UI/PG/恢复HTTP侧枝均patch等价，不重复cherry-pick。

建议批准后从源Head创建独立integration任务树。先补新任务专属验收身份和回归，不直接运行旧任务runtime：现有g4-m1-runtime.py及HTTP/browser入口硬编码RECOVERY TaskId/路径；final-gates实验也硬编码旧身份。未来任务须单列允许修改的任务适配入口及正反身份测试，不能借旧ID运行或使用旧私有输入。它们是待申请工具变更，不在本次修改。

最小后续提交序列：①新任务计划/准确消费者适配与测试（Master公共单写，独立Review）；②新任务完整验收与资源/绑定证据（说明增量）。没有已证实需改产品的P0/P1；若发现须另批最小修复，保持原45提交顺序，禁止静默挑选或丢弃。最终候选IntegrationHead=源Head+以上明确新增提交；必须逐项独立Review后向人类呈报准确SHA再纳入main。POSTREVIEW分支文档不自动包含在产品集成序列中。

执行main前再次窄fetch并核实parent。若仍祖先且所有资格通过，由唯一Master执行已批准的快进并普通push；任何分叉、并发main变化或未知提交都停止，重新提交模拟/冲突申请。不能用旧45结论套新Head；不force、不rebase、不真实cherry-pick试错。

## 验证矩阵（全部未来NOT_RUN）

|组|真实验证与失败条件|输入/责任|
|---|---|---|
|I01 工程|独立树执行pwsh -NoProfile -File scripts/verify.ps1 -SelfTest；随后 -RunNative -RunTests（精确现有SDK/缓存齐全才运行），零测试FAIL；不隐式安装|SDK10.0.402/global.json；Master|
|I02 G4关闭兼容|G4禁用时原G2/G3身份、权限、SourceBundle字节、发布v1→v2→回滚v1、Agent/MCP只读查询/预算/审计全部真实通过|复用原已审G3场景但使用新TaskId隔离资源；Master|
|I03 Host环境|隔离进程Production/Staging+Enabled=true必须拒启动；Enabled=false不注册G4；Development+Enabled=true才可注册；AllowEmptyPublicSchema默认false；ApplyMigrations同样环境矩阵|真实进程，不启动生产；独立Reviewer核拒绝原因|
|I04 迁移|同平台PG、connections独立schema和__EFMigrationsHistory；初次迁移、重复迁移、已有G3数据与审计同事务回滚；不对source数据库执行迁移|Master独占迁移与DB owner|
|I05 生成链|实际导出--export-g4-openapi到ignored临时路径，与冻结JSON结构比较；使用既有declarationsFor内存生成并比较g4-generated.ts；旧G1/G2产物字节不变|生成器/DTO/OpenAPI单写，不以手改TS闭合|
|I06 G4生命周期|Create/Probe/Enable/Discover/Disable、CAS/ETag/幂等、64KiB无长度短读、TLS坏CA/SAN、权限继承/owner/public非空拒绝、SecretRef用途/组织/轮换/自然过期、审计故障回滚|原49矩阵是覆盖来源，未来按新输入运行适用完整集，不复用旧私有Ref|
|I07 恢复和UI|取消、禁用/撤权竞态、lease接手旧fence拒绝、历史目录STALE；真实OIDC/浏览器reload/父子互锁/窄屏；四非PG422不伪成功|数据/日志不得泄密，人工目视与自动断言分列|
|I08 交付|两层diff-check exit0、实际输入绑定、非作者Review、准确自身资源收尾、唯一LOCAL V3及独立重开|CI按需；Windows原生AMD64未运行保持NOT_RUN|

CI当前NOT_RUN；没有在允许Git引用查询之外调用GitHub Actions API，因此既有同Head双job存在性NOT_VERIFIED，不能推定不存在。若后续批准查询/运行，记录真实run/URL/SHA/engineering和governance-integration两个job，不用本地通过替代。

## 公共文件、资源与恢复

Master独占Host/Contracts/迁移/生成器/锁/CI与main，产品Worker仅在另批具体owned_paths后派发；本次申请默认Master+只读Reviewer。所有未来运行资源前缀/TaskId=G4-M1-MAIN-INTEGRATION-001，独立合成PG/Keycloak/源PG/G3查询服务，旧G3/G6网络/卷/私有材料不挂载。

建议最大同时6容器、6GiB容器内存、3GiB新增卷、3GiB下载、GPU0、无公网监听、仅准确回环端口；这是待批上限，现无新运行许可。旧AMBER-A1镜像许可只属旧任务；若未来仍需这些镜像，必须按准确digest/平台/许可缺口取得新的限定准入，不能由源码合main继承。镜像不足不临时拉取或换源。

源Head纳入main前失败：保持任务分支和资源见证，main不变。纳入后出现问题：先关G4开关/停调度，保留审计与connections数据；禁止reset/强推或直接Down迁移。由Master提交经过Review的前向revert/修复，恢复原G3行为；数据回退必须基于任务内已验证备份另批，不自动删除schema。精确清理本任务创建对象，旧资源保护。

## 申请批准的边界

仅批准可审的源码集成及隔离验证，不批准生产、商业分发、M2、G6、付费模型、额外依赖。R01主线许可与R05运行供应链准入是独立决策。未获明确决定前，全部实施命令保持NOT_EXECUTED。
