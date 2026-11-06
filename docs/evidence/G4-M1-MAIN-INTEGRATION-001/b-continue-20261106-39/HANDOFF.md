# G4-M1-MAIN-INTEGRATION-001 — 最终本地验收交接

当前已完成获批影响范围内产品验收、非作者Review及实际资源收尾；唯一V3和独立VerifyOnly必须在本说明提交后执行，由包外final-receipt.json闭合交付。此处不预造ZIP或重开结果。

TestedCommit：0f7b74e1f832d079cf68e762e7688277917ffc90。
ApprovedMain：d1a61daffe844475b07705797e3ad325cc3f2945。
CandidateSourceHead：99753df6f03b184e40b431a5b5aba89d8fa67087。
IntegrationHead：以随后唯一V3 manifest与包外回执的完整HeadSha为准；T后仅允许本任务说明/证据提交，实际执行辅助脚本字节另行绑定。

## 验收

- 用户已批准按影响验收。15份T37原证据以H37固定Git blob为权威，19驱动及1426后端构建文件核对一致；I01后端/SelfTest、I02完整G3/模块、I03/I04/I05/I06复用且标记NOT_REEXECUTED。不是本轮重新执行，也不是以静态检查替代原真实测试。
- T39新执行Web lint/typecheck/test/build，23文件388测试通过；HTTP baseline59检查135请求、provision21/52及DB lineage24项通过。
- 初读403确定调度回归通过，真实原字节403→重验→202→jobURL/PARTIAL；权限恢复。完整原样I07六场景齐备，UI六验收项闭合；超时约10秒且故障/恢复证据完整；真实取消POST后源worker471在锁仍持有时消失、持久CANCELLED/无快照，刷新与操作入口恢复。
- 非作者argv_review复核源码/实际构建/日志、四张最新截图与源IO/DB证据，未发现开放P0/P1。单场景原exit2和NOT_RUN投影保留，由明确聚合闭合U05；旧Run37/38失败不改写。

## 资源与限制

5容器2网络4卷、4工具目录共27021文件515448006逻辑字节已按准确白名单实际回收；host/ingress进程与4端口已释放，非作者实时后验通过。3默认网络和8旧卷保持当前冻结基线；默认bridge曾在只读Docker状态观察时替换，原因NOT_VERIFIED，不声称全过程旧ID不变。VM未操作，物理空间/FD回收NOT_VERIFIED。

工作树/分支、唯一待生成ZIP、原始证据、私有恢复材料、incident dotnet-home及已绑定构建/离线缓存KEEP，准确理由和解除条件见resource-final-ledger.json。所有已知合成秘密扫描47模式17582项无发现，但不扩大为完整供应链审计。

CI、Windows、Intel为NOT_RUN；供应链AMBER-A1/LICENSE_PARTIAL与锁屏/熄屏连续性NOT_VERIFIED保持。V3必须PARTIAL且<=15MiB；超过10MiB分类说明，不提高上限。唯一ZIP重开和任务远端回读成功后，包外回执才可写READY_FOR_CHATGPT_MAIN_MERGE_APPROVAL。

## 恢复与下一关口

原始证据按public-artifact-index.json及public-raw-envelopes.json恢复；UTF8字段编码后核字节数/SHA。旧证据由V3完整Git恢复索引定位，历史失败/ZIP均不修改。不要覆写已有RunId；如后续确需复验，先核T39源码、实际驱动/构建及现有锁内本地缓存，登记新Run及私有资源，再执行已审按影响入口。缺失缓存仍环境阻断，不隐式下载。

本任务不更新main、不进入M2/G6。C仍须用户明确批准完整IntegrationHead、完整ApprovedMain及上述平台/供应链限制，届时再执行原计划的远端防竞态/快进门禁；本次没有merge/push main。
