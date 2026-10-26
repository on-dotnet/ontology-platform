# PRE-G3-HYGIENE-001 实施合同与计划

> 执行方式：Master按 writing-plans / executing-plans 执行，独立只读 Reviewer 检查；用户已明确批准附件全部执行及Git集成，无需重复设计审批。

## 目标与合同

- 授权：[原文](../evidence/PRE-G3-HYGIENE-001/authorization-v1.md)，只做G2后资源治理与Review ZIP V2；不启动G3 Plan/功能，不改业务源、依赖、锁与生产。
- BaseSha：`46c7a6de70b1b97c032b12a19bc27c1c54e70f4c`；开工fetch后HEAD=origin/main=Base；G2 CI40283523824双job已实际读取success。
- Owner/公共文件Single Writer：本轮Master；Reviewer：独立只读Agent；调查Agent均只读，不共享索引写入。
- 分支：`codex/PRE-G3-HYGIENE-001`；托管Worktree：`pre-g3-hygiene/ontology-platform`。主checkout六个既存DS_Store不改。
- owned_paths：`scripts/create-review-package.ps1`、`scripts/tests/ReviewPackage.Tests.ps1`、`scripts/maintenance/**`、`docs/development/review-package-spec.md`、`docs/development/resource-lifecycle.md`、`docs/tasks/PRE-G3-HYGIENE-001.md`、`docs/tasks/current-authorization.md`、`docs/evidence/PRE-G3-HYGIENE-001/**`、`docs/handoffs/2026-10-26-pre-g3-hygiene.md`、根`AGENTS.md`/`PLANS.md`。若需共享CI/verify，只由Master单写且记录理由。
- read_only_dependencies：全部业务源、其他任务证据、历史ADR/合同、CI/依赖锁、所有旧Worktree、ignored私有运行资料。独立Reviewer对全部路径只读。
- 环境：PowerShell7/Git/.NET内置ZIP与散列，无新增第三方直接依赖；macOS/Windows路径用相对仓库路径。

## 设计取舍

采用schemaVersion=2作为默认紧凑格式，显式schemaVersion=1兼容原构包和VerifyOnly。原格式原字节不改。完整非证据Head源只存一次，本任务证据只存一次；其余历史证据以完整blob/SHA256/size/commit/恢复命令索引。全部文本diff保留，二进制逐文件列Base/Head OID/hash/bytes和恢复入口。未采用全量重复副本或仅变更源码包，避免历史重复同时保留现行实现。正常ZIP写partial、校验成功后原子发布。未确认清理项一律保留。

## 审查重点

凭证及被删秘密仍拒绝；历史索引不能篡改或隐瞒文件；文本补丁不能被Git配置污染；CI成功必须同Head；失败不能替换最后有效包；ignored私有资料及活跃/跨机器资源不因年龄删除。

## 执行关口

- [ ] H1：只读Git/Worktree/Docker/ZIP/缓存盘点，逐项风险/归属/体积/保护依据，保存删除前清单；实际main/CI与原G2状态。
- [ ] H2：先扩展真实Git fixture（默认V2、V1兼容、二进制/rename/大量历史证据、无重复、完整索引与篡改拒绝、同HeadCI）；观察RED，再实现V2及只读资源脚本，跑GREEN/SelfTest，独立Review；commit/push、同HeadCI后集成main。
- [ ] H3：只处理H1中可证明安全候选；旧ZIP先归档生成metadata、manifest、回执，保存SHA与恢复入口；新有效包独立重开后才删除准确旧ZIP；分支/树/卷疑义保留。日志记录命令/退出码/前后/回收量。
- [ ] H4：生命周期规范/根DoD/交接/风险矩阵/validation固化，独立Review、本地SelfTest、Mac真实fixture及Linux同HeadCI；main集成push；从最终提交生成唯一紧凑包并独立重开，交付READY_FOR_REVIEW后停止。

## 验证命令

`pwsh -NoProfile -File scripts/tests/ReviewPackage.Tests.ps1`；`pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`；`pwsh -NoProfile -File scripts/maintenance/inspect-resources.ps1`；`pwsh -NoProfile -File scripts/doctor.ps1`。真实Linux全工程与G2模块由现有CI两job执行，记录同Head run；Windows/Intel原生无环境保持NOT_RUN。构包与VerifyOnly按新规范使用显式Base/Head、已提交validation和实际CI参数。

## 停止与恢复

不使用force/reset-hard/prune全局操作，不读取凭证，不清理全局codex/其他项目；独立Review重要缺陷先修复。恢复以已提交Git对象、保留持久卷与旧会话树、包内索引为准。只输出PRE_G3_HYGIENE_READY_FOR_REVIEW，不代表G3获准或ChatGPT验收。
