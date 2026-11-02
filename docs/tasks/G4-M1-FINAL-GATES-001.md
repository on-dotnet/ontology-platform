# G4-M1-FINAL-GATES-001

状态 IN_PROGRESS / C08_REVIEWED_R04_PENDING。Base=1399364ad1367f3d1bfdee4d9901fdb33b48c15d；protected origin/main=d1a61daffe844475b07705797e3ad325cc3f2945。分支 codex/g4-m1-final-gates-001，托管树 /Users/chasen/.codex/worktrees/g4-m1-final-gates-001/ontology-platform。授权见 ../evidence/G4-M1-FINAL-GATES-001/authorization.md，完整附件以 input-original-bytes.json 可恢复。

Master 唯一写者；非作者 /root/final_gates_reviewer 只读。owned_paths：本任务 docs/tasks 与 docs/evidence、experiments/g4-m1-final-gates/**、Connections/Application 的精确目标策略、Connections/Adapters 的精确 schema 交集、ConnectionsTests、必要 E0 TaskId 消费者、Hosts/OntologyPlatform.Api/G4/G4Composition.cs 的默认关闭精确开关。公共合同、Host、生成文件、锁、迁移只能 Master 修改，默认不需变更。G2/G3/G6、旧证据、旧资源只读；不合 main。

DAG：F0 授权/合同/来源/预算/Review → F1 真PG C08 → F2 C08精确回收 → F3 已准入隔离G3 R04 → F4 49条受影响输入绑定 → F5 Review/提交/LOCAL/唯一V3/独立重开。新G3 A1需人类另批，不阻塞独立已批准 C08。

历史失败→最早入口→回归：完整TaskId不是 execution_preflight milestone → --help 固定 G4-M1 → contract/runtime；Docker sandbox拒绝 → 只读提升权限 → Engine明确身份；B被旧production-only拒绝 → 精确A/B合同Review → 适配器正反/HTTP/CAS/审计；原镜像已清理 → 校验旧OCI每层后本地恢复 → inspect平台digest，不重复网络；旧脚本硬编码TaskId → 新任务独立运行器 → config/labels/路径/资源预算拒绝负例。

前置命令 python3 scripts/maintenance/execution_preflight.py check --milestone G4-M1 --phase contract 已PASS，仅旧阶段路径检查；新消费者必须另核实，不能冒充产品。宿主AC sleep=0/displaysleep=10已观测，锁屏/整会话NOT_VERIFIED。新 TaskId CLI 尚不支持，需精确新增，不借旧TaskId标记。真实长入口先完成这些门禁。

C08已获独立PASS，真实证据及受测源码/二进制映射已固定；R04未运行。新增两个精确G3镜像AMBER-A1已获人类明确受限批准。
