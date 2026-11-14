# 阶段计划与交接规则

## 当前授权与规格

最新人类明确授权优先；[本地验证政策](docs/development/local-validation-policy.md)与[效率规则](docs/development/ai-development-efficiency.md)为现行入口。先读取[当前授权](docs/tasks/current-authorization.md)、当前任务卡及唯一状态，历史事实保留在原任务、证据和Git中，不把历史阶段禁令写成永久当前授权。外部材料经人类批准才成为任务依据。

产品任务沿用唯一A–F/合同规格，用[SDD模板](docs/tasks/templates/sdd-task.md)在现有任务卡关联AC、正反Given/When/Then、实现/测试路径、最早真实验证、原件与输入。按可观察行为切片，先贯通最高风险真实边界，再扩展其余能力。小修复无需新P0、新会话、逐补丁或逐AC人审；main、生产、新依赖/费用及超范围语义仍需明确决定。规则检查不等于产品验收或效率已改善。

## 作者、并行与恢复

每任务记录ID、授权/非目标、依赖、Owner/Reviewer、BaseSha、分支、规范化Worktree、owned_paths/read_only_dependencies、公共合同Owner、验证命令、负例及停止条件。

独立写者使用独立托管Worktree和任务分支；不可用时按宿主能力使用原生Git并记录原因，目录不得嵌套，不以共用目录切分支代隔离。按独立写项拆分，单作者加非作者只读Review可满足小范围任务，不为普通修复反复派团队。共享构建、CI、锁、AGENTS/PLANS、公共DTO、迁移、Design Tokens及AppHost配置Single Writer；先确定Owner，不覆盖他人修改。

开工和集成前fetch，核对origin/main、任务基线、分支和工作树；保护未提交/未跟踪内容，不reset --hard或强推。可验证里程碑原子提交、普通push任务分支，DRAFT/PARTIAL备份不等于可合并。精确main集成须人类明确批准Base/Head，由Master唯一执行并回读远端；Git权限不扩大业务阶段。

命令、退出码、版本、有效测试数、原Run/输入、NOT_RUN及失败形成可恢复证据，不含认证材料。作者先核AC→实现→用例→原件缺口；非作者早审首个高风险切片，最终集中Review，后续只审实际增量。CI按需，已跑记录run/job/URL/Head/结论，未知NOT_VERIFIED，未跑NOT_RUN；本地PASS不代表其他平台或CI通过。

## 阶段交付唯一表

其他工程文档引用本表，不另设相冲突的阶段交付规则。用户明确针对当前阶段的例外优先。

| 阶段 | 交付方式 | 禁止错误继承 |
|---|---|---|
| P0/文档准入 | 状态＋申请；不默认ZIP | 不把P0禁包延长至已获准产品实施 |
| 实施中 | 切片原件/结果/任务分支；不例行中间包 | 不因新Run重启全链 |
| 产品实施完成 | 唯一最终V3＋SHA＋包外回执＋非作者VerifyOnly | 不需要额外“允许打包”审批；具体用户例外仍优先 |
| 已冻结产品后的纯规则增量 | 原包引用＋已提交diff＋回执 | 不声称旧包包含新规则；不得隐藏产品/脚本改动 |
| 精确main集成 | 引用/差异/普通push/回读回执 | 不重打包、不重建环境 |
| 外部阻断 | 见证＋恢复条件 | 无新输入不重复搜索/测试/构包 |

产品最终冻结顺序：源码/格式→适用测试→非作者Review→提交→当前输入绑定→唯一V3→非作者独立重开→包外回执。适用完整验收可由FRESH与当前有效REUSED共同覆盖，不因每个Head重跑全链。纯规则增量保持产品输入和旧包，分列产品TestedCommit、包Head、规则Head，引用已有非作者重开原件；缺原件才对同一包重开，不重构包。

## 构包与证据边界

按[V3合同](docs/development/review-package-spec.md)核明确已提交Base/Head祖先关系、完整diff-check exit0、来源和输入绑定。首份真实证据即沿现有机制做小样归档预检；小样仅ignored诊断，不是交付ZIP。正式包从Git读取，核未提交/未跟踪交付避免漏包，包Head须可由任务分支恢复。冻结包后的回执放包外，防止为回执递归重打包。

ZIP仅在ignored artifacts/reviews，禁止.git、凭据、私有runtime、缓存、数据库、镜像、机器日志和未授权数据；有限扫描不等于全面防泄露。V3格式与输入身份不变，源码/当前证据单份载荷、历史原件索引；代表PNG最多12张、压缩3MiB，超过10MiB解释分类，超过15MiB阻断。V1/V2历史重开兼容且SHA不改。重开须核路径、成员、散列、源码与差异，不能以构包成功代替产品测试。

## 失败、状态与资源

按[效率规则](docs/development/ai-development-efficiency.md)分流PRODUCT/HARNESS/EVIDENCE/ENVIRONMENT/EXTERNAL，最小复现后按影响重验；驱动/断言/夹具语义变化须测相关场景，纯解释/映射修复先重核原件。无新假设不重复昂贵长链，失败原件保持。OBSERVED为实测，PROPOSED为提案，NOT_VERIFIED为未知，NOT_RUN为未执行；PASS/FAIL绑定实际运行，BLOCKED缺前提，PARTIAL保留缺口，零测试不算产品PASS。

按[生命周期规范](docs/development/resource-lifecycle.md)创建即记录TaskId/RunId/准确ID/内容键与恢复入口。审查和安全集成前保护活跃/锁定/未集成Worktree、私有runtime/PFX、唯一数据及跨任务引用；每个KEEP明确理由和解除条件。获准关闭后按准确白名单、指纹/期限、实时引用、before-command-exit-after和强后验回收；安全候选存在却0删除为FAIL，不能统一DEFERRED。保护范围、自然代际和准确资源证据不由构包测试替代。

禁止全局prune/restart/改DB、跨项目清理或以重启绕过BuildKit history回现；即时absence不等于持久删除。Fuseki仅canonical内容键与已校验共享镜像。环境缓存按依赖键复用，不为新Run重建。交付或外部阻断后停当前审查关口；不得自动进入下一业务阶段。
