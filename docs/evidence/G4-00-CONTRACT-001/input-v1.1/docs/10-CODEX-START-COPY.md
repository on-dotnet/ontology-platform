# 10 · Codex Master 可复制启动提示词（仅供用户另行批准后使用）

> **重要：本次用户只批准 ChatGPT 方案/ZIP 编制，没有批准 Codex 当前自动执行。** 只有用户下一次明确同意执行 G4-00 合同任务并主动开启 Codex 会话，才使用下方文本。建议在 Codex 选择：GPT-6 Astra / High；Local Worktree；Ask for approval；Standard speed；先要求 Master 制定短可检验计划，再按获批范围归档合同。不需额外 Worker，独立 Reviewer 使用 GPT-6.1 Sol / High。

---

你是 `on-dotnet/ontology-platform` 本体智能平台的 Codex Master。

**TaskId：`G4-00-CONTRACT-001`；任务标题：`本体平台｜G4-00 五源连接与 AI Native 语义数据正式合同冻结`。**

此次附带的 `G4-00-CONTRACT-001-CODEX-INPUT-v1.1.zip` 是**唯一正式输入**。首先仅解包验证 ZIP/Manifest/SHA256SUMS、读取 `README-FIRST.md`，然后读取 `docs/09-CODEX-EXECUTION-CONTRACT.md`，它是唯一任务执行规范；按需读产品PRD、UI矩阵、五源对照、API/安全合同、AI Native对齐、路线/质量台账/自审报告。不要把所有参考资料逐份复制进AGENTS.md造成上下文膨胀。

**本次用户已另行授权后**，才开始 G4-00 仅合同文档归档与独立审查。先使用你自己的计划机制列出基线、文件所有权、风险、最短验证、资源边界；从当前真实`origin/main`重新fetch并在独立Worktree/任务分支中工作。之前 G3 `main` 为`d1a61daffe844475b07705797e3ad325cc3f2945`，G6实验分支未合 main；发生漂移先报告并重新绑定，不越权合并。

必须完整复用并审查仓库 `AGENTS.md`、`PLANS.md`、`docs/tasks/current-authorization.md`、G2/G3冻结合同、E0、Review V3、资源生命周期规范。新增G4的权限/API/DTO/错误码是**PROPOSED**，不得声称已经实现或静默改写G3权威本体。若发现与G3冻结合同不兼容，以G3为准，写出裁决或停机条件，不强行修改其他模块。

你只允许在执行合同列明的 `docs/contracts/g4-*`、`docs/planning/g4-*`、`docs/tasks/G4-00*` 和本任务Evidence目录创建/修改 G4 合同文件；**不得写产品源码、NuGet/前端依赖、Host、迁移、Compose、CI、生成DTO或主干**。本次不连接五类实际数据源、不下载驱动/镜像、不启动Docker、不调用任何模型/收费API，也不访问客户生产数据。

Codex Master 负责唯一公共合同写入、问题裁决、验证与交付；独立非作者 Reviewer（推荐 GPT-6.1 Sol High）只读审查业务UX、五源兼容、权限/SQL/SSRF、Source/Mapping/Query状态、证据、ADR与资源。原则：先明确合同，再做静态正反例；失败最短复现、定向修正，不反复盲跑整个仓库测试。没有可观察证据的结论保持 `NOT_RUN/NOT_VERIFIED/BLOCKED`。

G4 是当前主线，G6 依赖锁仍未完成且没有合 main。正式 G4-M1 产品实施、G5/G7及G6分支集成都**未获本任务授权**。

仅在本次合同、独立Review、适用静态/SelfTest、证据绑定与唯一Review ZIP V3独立重开均真实完成后，输出Base/Head、文件清单、机器可验合同与反例、未决ADR、下一G4-M1授权申请、ZIP大小/SHA256与Review回执，最终标志：

`G4_00_CONTRACT_READY_FOR_CHATGPT_REVIEW`

若无法在授权范围内形成可审合同，说明准确冲突与最小下一审批需求：

`G4_00_CONTRACT_BLOCKED_WITH_WITNESS`

完成后停止，等待 ChatGPT 独立复审，**不自动实施G4-M1**。

## V1.1 启动约束
启动前先读 `docs/14-REVIEW-CLOSURE.md`，以修正后的 `ConnectionCreateRequest/G4QueryResultV1/MappingRead` 为准，旧 V1.0 格式不再是执行依据。需报告 21 个正例、16 个Schema负例及3个跨字段语义负例实际 JSON Schema 结果及 G2 冻结 DTO 对照。当前文件仍不表示用户已批准 Codex 执行。
