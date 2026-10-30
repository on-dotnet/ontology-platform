# G3-M4-SEM-B

状态：AUTHORIZED / CONTRACT_B_FROZEN，尚未派业务执行。Slice A已于main/origin实际推进d1345222fa0f024c99611dff97b2a957998176d1，BaseSha（B阶段基线）同值；合同Owner Master，ContractHead将在本卡同批冻结提交后用派工回执记录完整SHA。Owner /root/sem_a；Reviewer非作者只读Agent（实现时实记）。复用独立托管Worktree `/Users/chasen/.codex/worktrees/g3-m4-sem-a/ontology-platform`，新任务分支`codex/g3-m4-sem-b`；旧A分支/提交已main集成，不reset、不覆盖历史。

owned_paths：Ontology与Publishing模块的业务实现/注册（排除OntologyDbContext.cs、ImpactReportRecord.cs、全部Migrations）；Semantic/Publishing受影响真实测试和夹具（排除G3M4ImpactMigrationContractTests.cs）；samples/g3-m4/**；docs/evidence/G3-M4-001/SEM-B/**。read_only_dependencies：所有公共Contracts/Host/OpenAPI/生成TS/g2-client、公共scripts/CI/锁/Tokens/AppHost/迁移、Master storage合同与另一个worker。你不是唯一Agent，不回退别人改动，不跨树抢写；公共变更先提Master。

合同唯一依据docs/contracts/g3-m4-contract-b.md及g2-models生成类型。Master公共storage已生成唯一迁移，只向前；业务可直接使用ImpactReports DbSet，不重建M1 SourceBundle/assessment/审计/Outbox/发布系统。只M4 B，不M5/G4/G5，不新依赖/收费/系统/生产。Timeline复用现有工具，日志先ignored后逐行LF去展示空格，原失败和原始散列留证。

验收：真实PG/Jena/RustFS固定版本Diff、报告、审批/激活/旧v3-v4历史/Run相关回归；变更C#格式。负例：跨资产/scope；四源/no-op/blank同构与预算；伪造/过期/异assessment/profile/source；INITIAL/active漂移；生成幂等并发及审计一次；旧审批失效/发布CAS。先最小固定版本Diff+真实API可运行里程碑提交/push，非作者Review后Master增量联调，不等全部功能。最终真实本地门禁和唯一V3/资源收尾由Master统筹；未运行CI/Windows/Intel写NOT_RUN。已过且相应输入未变的完整门禁不重复，失败指纹先短定位。

停止：公共合同矛盾先报Master；未知依赖/权限/费用/不可逆只停对应项，不扩大范围。所有临时资源创建Task/Run/准确ID/TTL，finally实际回收及强不存在；不启动第二固定端口栈/不全局prune或restart。Root已有唯一M4 runtime，本任务对其只读直到联调授权。
