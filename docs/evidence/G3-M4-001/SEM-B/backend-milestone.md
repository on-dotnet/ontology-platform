# G3-M4-SEM-B 后端可运行里程碑

基于已推送419708c8418fa2763ad802de10afe6c291645fd4，依赖Master已审audit allowlist（本树68c77c2，对应Master cd69ee2）。本文件不自称独立Review；最终Head由包含本证据的提交及Master集成回执绑定。只修改owned Ontology/Publishing业务与相关测试；公共合同、Host、迁移、脚本、Query/Agent夹具均未改。

确认修复：内建IRI按明确受控名单识别；Class/ObjectProperty/DatatypeProperty声明按准确种类与consumer角色检查，NamedIndividual不掩盖定义删除；报告/assessment envelope统一微秒比较，业务时间七位精度保持。新发布在创建、审批、准备（含未成功预留重试）、最终提交复核持久影响；最终active锁后再核对INITIAL/准确Release基线。Catalog沿原ProposalId追溯Impact，旧manifest/Run/Outbox格式及两条旧审批hash分支不变。已成功回执可独立恢复，旧无报告待批不再取得新发布资格。

真实验证均复用已校验arm64 canonical Fuseki，无重建：

| 入口label | 结果 |
| --- | --- |
| impact-review-dependencies | 8/8 PASS，0skip，真实PG/Jena内建正反及按种类删除正反 |
| impact-review-precision | 2/2 PASS，0skip，真实同连接锁读非微秒正反 |
| impact-publishing-boundaries | 10/10 PASS，0skip，真实三依赖四点/回执/基线 |
| impact-semantic-stable-full | 239/239 PASS，0skip，完整真实PG/Jena |
| impact-publishing-stable-full | 原78总：77PASS/1FAIL/0skip；0warn/0error |
| impact-publishing-cas-regression | 唯一失败项修正测试后1/1 PASS，0skip；0warn/0error |

唯一完整Publishing失败是旧并发测试只接受activation_revision_conflict，而真实败方在CommitActivation同事务被新增INITIAL保护先拒为impact_baseline_conflict。只将相关断言限定接受这两个409，原CAS与唯一激活/Outbox断言保留；生产输入不变，不重跑已过77。新增assessment/profile自洽漂移审批负例、历史v3/v4发布回滚、故障恢复、幂等、并发、真实目录均包含在原完整运行已通过77中。不能将原78运行改写为完整PASS。

MSB4166原失败和输入指纹保留；限定读取原临时MSBuild故障目录发现已不存在，具体IPC/权限/资源原因UNKNOWN，未按源码错误处理。单节点-m:1 -nr:false探测通过；未重启系统或Docker。后续测试源码Outbox.AssetId编译错误廉价定位为使用了不存在的字段，改为实际release关联查询，原FAIL日志保留。全部失败原始散列、命令输入指纹、UTC/真实耗时见timeline与backend-milestone.json；不推断思考时间。

以上六轮准确创建16个临时容器，finally逐ID删除后再inspect得到No such container，16个全部真实回收；无卷/镜像/build history删除。分支与Worktree KEEP至Master独立Review和合并确认，解除条件为精确提交已集成且无活跃写者。ignored日志/本地SDK与工具保持，交由Master最终生命周期清单，不删除其他任务资源。

CI、Windows、Intel均NOT_RUN。Root接续独立Review、真实Report/审批API/UI联调、Query/Agent真实回归、SelfTest与唯一Review V3封包；本Agent不启动下游阶段。完整可重现命令与资源准确ID在对应JSON/TXT与timeline。当前相关C#格式化及git diff --check退出0。
