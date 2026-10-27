# M1 风险与后续边界

本表不重写 G2/PRE-G3 历史结论。M1 的执行证据以 validation.json、统一门禁日志、独立审查和最终包 manifest 为准；本表不能替代实际验收。

|事项|M1 控制和退路|保留状态/复查条件|
|---|---|---|
|四源有损及未知公理|SourceBundle 原始 UTF-8 为唯一权威，精确编辑保留未触及三元组；未知能力保留源码并阻断发布|不能从 UI 投影重建全图；M2–M5 另行授权|
|支持或推理被夸大|固定 20 项 profile；ASSERTED_ONLY；OWL_REASONING=NOT_RUN；SHACL 与 OWL 分开|完整 OWL 推理 NOT_IMPLEMENTED；SHACL 行列未知保持 null，歧义来源使用 bundle/hash|
|比较超界误判|每侧 bundle 5000 triples，每图 128 blank，四源总 100000 搜索节点/5s，最终全集核对|超限/取消 INDETERMINATE，不当作 EQUIVALENT 或发布依据|
|assessment 绕过或发布混版|真实 RIOT/SHACL；准确 revision/四源 hash/profile/有效期/自身 hash 复核；异人批准、CAS、同批图回验|客户端不能伪造资格；active 不得半更新；真实故障证据单列|
|历史读取/回滚与应用降级混淆|V1 显式 Legacy 策略、V2 严格 Semantics；原 Binding/Run/SSE 保留；增量迁移拒绝 Down|冻结 reader 的读取证明不认证旧 G2 宿主的安全应用回退；不可验证旧制品阻断回滚|
|工具链/许可/供应链|既有精确 SDK/Node/pnpm/锁/镜像；无新直接依赖|镜像完整供应链、离线交付及全面许可认证 NOT_VERIFIED|
|Monaco|现有 textarea 源码后备|BLOCKED / PAUSED_BY_USER，未接入|
|真实 LLM、五真实业务源|deterministic Agent 仅验证原 Run/SSE 协议|真实 LLM BLOCKED，未调用收费模型；业务源 NOT_RUN|
|平台/生产承诺|本机 macOS arm64 与 GitHub Linux 各按实际证据|Windows/Intel、生产 HA、证书轮换、SLO/RPO/RTO NOT_RUN/NOT_VERIFIED|
|Git 保护与独立性|Master 唯一 main 集成，非作者 Agent 审查、同 Head 两 job|未修改 GitHub 保护；Agent 审查不冒充第二 GitHub 用户批准|
|隐私和公开历史|有限静态模式和只报路径/类别的 history 扫描|语义隐私、任意混淆、不可达远端对象 NOT_VERIFIED；不改写历史|
|资源回收|只处理 M1 精确合成/可再生候选，保留旧 6 树/历史 refs/G2 24 卷|共享 cache/镜像不全局 prune；物理 APFS/SSD 回收 NOT_VERIFIED；私有 runtime 依准确路径保留|

QUDT/UCUM 等词汇候选保留为后续审批，不在 M1 引入。身份、时间、影响报告、完整图形建模、连接器与指标业务均不由本任务启动。
