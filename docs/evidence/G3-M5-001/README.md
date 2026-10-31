# G3-M5-001 正式复审入口

用户授权附件全部M5/E0已在批准边界内执行；适用本地验收完成，交付PARTIAL，等待ChatGPT复审，不进入G4/G5。正式唯一V3、交付Head与ZIP SHA256取包外delivery-receipt；本目录不回填自引用SHA。

- [最终产品/工具验收矩阵](master/final/test-matrix.md)：Semantic302、Publishing78、Query49、Agent33、Web268、真实UI50及G3组合638；原失败和增量复用均保留。
- [二十能力及五维语义分级](WEB/capability-matrix-draft.md)：v4/23保持，源码保留、有界只读、不可编辑、复杂阻断发布、未推理；原15裸integer明确INDETERMINATE。
- [输入绑定](master/final/input-binding.json)及[规范化验收证据](master/final/validation.json)：testedCommit80adf475，后续仅任务/证据说明，实际CI NOT_RUN。
- [E0失败前置防线](E0/failure-prevention-matrix.md)：路径/参数、audit/DI/阶段、日志、证据/PNG尺寸、失败缓存、计时与真实退出分离；声明工具边界及本轮真实入口失误。
- [Mac提交时会话快照](master/final/host-snapshot.json)及[真实锁屏外接熄屏](master/host/locked-display-off-trial.summary.json)：ACsleep0/display10、锁屏熄屏13心跳、任务连续328心跳/82分钟/0Sleep；之后监测直到构包独立重开，最终精确PID关闭结果取包外host-closure.json。
- [时间分解](master/final/time-breakdown.json)：已记录20步命令的跨度3919009ms、union458013ms、inclusive cumulative458014ms、已声明DAG关键路径219701ms；1ms overlap为计时舍入，不推定agent并行工时。E0/M5实施活跃、模型思考、人工等待与未覆盖命令时间UNKNOWN。
- [真实资源回收](master/final/resources.md)及[准确数量](master/final/resource-counts.json)：8任务卷真实删除/强不存在，旧G2八卷未变，21→20树，1原生归档/2原生活跃guard KEEP。实际物理回收字节UNKNOWN。
- [独立审查](master/independent-slice-reviews.md)与[G3-M5交接](../../tasks/G3-M5-001-handoff.md)：公开源码/元数据审查结果及恢复边界。

完整浏览器原尝试exit1保留；最终638为原600+最新38M5明确组合，另六门禁各自exit0，不宣称一次七门禁exit0。Windows/Intel原生、实际CI、付费LLM及生产NOT_RUN；Monaco BLOCKED；OWL推理/imports闭包加载在本次范围外。PNG仅选择3张最终稳定代表，过程截图/blob由V3精确Git对象索引恢复。凭证/缓存/私有runtime/PFX不进入包。
