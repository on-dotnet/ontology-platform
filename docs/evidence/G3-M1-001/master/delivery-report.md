# G3-M1-001 交付报告

状态：IMPLEMENTED / CLOSURE_IN_PROGRESS，整体PARTIAL；最终main同HeadCI、实际资源回收和唯一包以后置回执为准。本报告不代表ChatGPT已验收M1。只M1，M2–M5未启动。

Base=d6aab6b47e63c9d5deadfa480f6659c62c5ed138；开工及首次集成前均重新fetch，未退回旧main。核心源码59c7875430c92443ffd8ab7463d11012e4461f68经非作者独立审查及同Head双job成功后，已首次快进main/push；main重跑CI40455145345当前待实际结论。原主树六个.DS_Store保持。最终文档Head、CI和ZIP由最终manifest精确绑定，不自引用未来SHA。

## 完成的M1切片

- 四源SourceBundle原始UTF8/BOM/CRLF/注释/非BMP及hash为唯一权威，no-op与旧revision保留；精确结构命令只改请求三元组，非法Turtle不产生新revision。未知复杂公理不从UI投影重建或静默丢弃。
- 固定20项profile及稳定version/hash，ASSERTED_ONLY；真实RIOT/SHACL产生分阶段assessment，准确revision/四源hash/profile/自身hash/24h/执行版本、报告/回执/审计同事务。服务端重新核验发布创建、审批、准备和激活；新PUBLISH不能用旧报告或客户端伪造资格绕过。
- 新发布V2严格Semantics/source-hash绑定；V1显式原G2策略与原Binding字段/顺序，历史Run/SSE形状保留。业务回滚重新验证原制品/同批图、当前权限/异人批准/CAS，不锁当前草稿或补字段。增量迁移拒绝破坏性Down。冻结兼容reader真实读取V2不等于旧G2宿主可安全应用降级。
- 有界精确RDF集合比较：分区细化、blank双射搜索、完整全集核对；每侧bundle总5000条、每源256KiB/总1MiB、每图128 blank，四源总100000搜索节点/5s。预算/取消撤回全部部分结论为INDETERMINATE，绝不作零差异或发布PASS。
- Web真实四源导入导出、dirty/缺席语义、20项矩阵、评估诊断、固定版本比较、键盘及主题/窄屏。延迟导入绑定草稿/修订和工作区/逐源代次，functional合并，期间名称/另源/后发输入不被旧闭包覆盖。
- 原/api/v1与生成流水线复用，实际Kestrel导出32 paths/110 schemas，生成TS逐字节校验；无新增直接依赖、万能Repository或第二套SourceBundle/身份模型。

## 实际验收与Head映射

|检查点|命令/结果|证据|
|---|---|---|
|24f6379完整入口|g3-governance.ps1 -Milestone M1 -StartRuntime，exit0，父13阶段/子7门禁PASS|full-gate-attempt4.txt及provenance；runtime/pipeline-48725802e8314611ad4e2692af0a8de2|
|同轮工程/真实模块|SelfTest（清理42/构包54等）；Web122；真实Security116、SEM96、Publishing55、Query49、Agent33，均0失败/真实模块0skip|同一pipeline输出与ci-*.json；不是把原生缺配置skip当通过|
|59c7875元数据增量|真实进程启动异常RED1→GREEN5、copy observer真实HTTP RED2→GREEN6；实际七门禁exit0，M1浏览器54、完整链169、观测25/故障8/trace4/性能27|process-start-*、copied-observer-*；runtime/g3-m1-ff712e0c29b1/a913360d2588432396887d598de249ce|
|dc5a5c3仅截图时序|实际七门禁exit0，M1浏览器56；390两主题侧栏结束态、稳定图像抽查|stable-visual-runtime*；runtime/g3-m1-bb5e3661b605/e2a597356fa846319cd8a368263a91d7；visual-qa.md|
|写前/写后兼容reader|5df0765构建冻结126文件、清单hash固定；写前1/1及实际API导出V2回读1/1，0skip，整个依赖集不变|各run prewrite/compatibility证据；最终V2原字节base64封套及SHA；不作为旧应用降级认证|
|独立审查|whole review初C0/I4/M1；唯一统一fix wave后全部ADDRESSED，Spec/Quality PASS、C0/I0/M0|whole-branch-review-initial/final.md及FIX目录；不是第二GitHub用户批准|
|核心CI/首次集成|分支40453901949，59c7875，engineering与governance-integration实际success；Master FF main/push，main同Head新run后置|core-ci-59.json，实际mainCI回执后续归档|

24..dc的backend/apps差异为空；后续仅验收记录/异常路径和截图选项，不把增量说成在新Head重复全部原生测试。所有最终代码仍须最终Head实际CI。每条能力的精确测试方法与未独立变异组合见backend-coverage.md；未导入私有真实G2备份或升级前Run/Event库，历史协议夹具不能外推为生产迁移演练。

原缺assets/未恢复pnpm、迁移Down先删表、诊断来源猜测、validTo兼容、空skip假reader成功、manifest缺LF、旧AppHost前缀、429、异步导入和跨轮证据混合等FAIL均保留并有纠正，不重写历史。初次新browser直接读取认证材料曾被自动审批拒绝，已改为既有受控验收器注入认证上下文，未绕过拒绝或新增credential reader。

## 资源、限制与恢复

具体清理候选：40个本任务g3-m1合成命名卷、3个本任务worker托管树；每个执行会话已停止且原证据归档。只读pre-apply为10树/38refs、64卷（24保护+40候选）；3worker ignored普通文件逻辑字节约2.235GB（未硬链接去重），无未解决私有候选，唯一公开CC0 22字节资产按既有精确例外验证。actual Apply/native archive及after尚待门禁，不预填回收成功；见closed-resource-ownership.md及worker-ignored-prearchive.json。

原6历史树/24G2卷/历史refs、Master活跃树、私有runtime/PFX和共享镜像/cache/history保护；不全局prune、不改DB内部/引擎/默认工具、不删历史。物理APFS/SSD回收NOT_VERIFIED。回收后保留集、doctor与恢复入口逐项后验，不把已停止的旧G2数据集称为再次健康启动。恢复一律动态fetch，再用fresh g3-governance -M1 -StartRuntime；已删除合成卷的旧private runtime不可当作仍有效的恢复入口。

Monaco保持BLOCKED/PAUSED_BY_USER；真实LLM未配置且未调用收费模型；完整OWL推理、五真实源、Windows/Intel、生产HA/证书轮换/SLO-RPO-RTO、完整供应链与语义隐私认证均未完成。SHACL合并图诊断使用bundle/hash及null行列，不声称OWL一致性或精确SHACL源行列。详细风险见retention-risk-matrix.md。

## Master执行裁定（按发生顺序）

1. 用户已明确授权，合同冻结后SEM/WEB独立树并行。若错误，会造成跨树写冲突；以owned_paths、共享Single Writer及独立审查约束。
2. baseline缺assets/pnpm是清理后的恢复前提，按原锁恢复且不加依赖。若错误，会掩盖产品回归；保留原失败并完成真实构建/模块/E2E及CI复验。
3. 四个历史cherry+采用当前main覆盖，不重复合并。若错误，会遗漏历史功能；覆盖映射保留在已审计划，旧refs/树/数据继续保留。

阶段只有M1；完成唯一Review V2 ZIP与外部CI/重开回执后输出G3_M1_READY_FOR_REVIEW，停止等待ChatGPT独立复审。
