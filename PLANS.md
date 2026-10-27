# 阶段计划与交接规则

## 当前授权与历史

任务不永久写死在根规则。执行前读取[当前授权索引](docs/tasks/current-authorization.md)和对应任务卡。G0/G1-ENG保留原事实及PARTIAL/BLOCKED，不用当前进展改写历史。外部材料只有经人类明确批准才成为任务依据。

## 并行工作合同

每任务记录ID、授权/非目标、依赖DAG、Owner/Reviewer、BaseSha、任务分支、规范化Worktree路径、owned_paths、read_only_dependencies、公共合同Owner、验收命令、负例、证据和停止条件。

最新V2已获人类明确确认：独立写入Agent在独立Worktree和分支工作，main由Master唯一集成。优先Codex托管Worktree；不可用再用原生Git，目录不得互相嵌套。只切分支共用目录不是隔离。默认2–3独立写项，保留只读审查能力；只读研究不要求Worktree。

根构建配置、CI、锁文件、AGENTS/PLANS、公共DTO、迁移、Design Tokens、AppHost公共配置同一时刻单写者。共享修改先提议Owner，不直接覆盖。不能隔离时记录原因，先并行只读后串行写入，不恢复旧的禁用Worktree解读。

## 同步、审查、集成与恢复

1. 开工和集成前fetch，确认origin/main、本地基线和工作树；未预期改动/分叉先保护现场，不reset --hard、不强推。
2. 可验证里程碑原子commit并及时push任务分支。未完成成果可远程备份，但标DRAFT/PARTIAL，不等于可合并。
3. 实际命令、退出码、版本、测试数、NOT_RUN及修复写证据；消息不是唯一可恢复记录，不包含认证材料。
4. 独立Reviewer只读；Owner复现修复并复验，Master检查分支头/合同及集成检查。自报不等于通过。
5. 已验收成果通过可追踪PR/merge/cherry-pick分批进入main，及时push，不等整个G1结束。冲突由对应Owner/Master处理；关键失败保留分支和现场。
6. CI必须记录run ID/URL、commit和结论；commit status为空不表示成功或失败。不可读取记NOT_VERIFIED。
7. Worktree仅在审查归档且安全集成后清理；保留含未整合成果的目录。交接列明各树/分支、剩余事项和恢复步骤。

## 所有阶段DoD：一个可复检审查ZIP

明确已提交BaseSha和HeadSha且前者为祖先，禁止用可能为空的origin/main..HEAD替代本阶段差异。检查未提交/未跟踪交付，不静默漏包。源码来自Git提交，附完整patch/commits/status/diff-check、任务/ADR/合同和实际验证/审查证据、环境与CI事实。

ZIP在Git忽略的artifacts/reviews，禁止.git、.env（安全.env.example除外）、.ssh、auth、密钥、凭证、依赖/编译缓存、数据库、镜像、机器日志、模型和未授权生产数据。有限扫描不是全面防泄露。必须用隔离模拟负例并重新打开ZIP复验路径、文件、SHA256和diff对应HeadSha；最终仅交一个ZIP路径/大小/SHA256，不入Git或第三方网盘。

## 状态与停止

OBSERVED为实测，PROPOSED为提案，NOT_VERIFIED为未知，NOT_RUN为未执行；PASS/FAIL对应明确运行项，WARN不等于通过，BLOCKED为缺前提，PARTIAL保留缺口。零应用测试和任务终态不代表整个G1通过。

当前关口完成或受阻后交付审查包并停止，等待审查及下一关口明确授权。不得自动进入SEC/FE/OBS/G2；Git持续授权不是业务阶段授权。

## 阶段收尾与资源生命周期（PRE-G3-HYGIENE-001）

每里程碑获审后按[生命周期规范](docs/development/resource-lifecycle.md)记录分支/Worktree、Docker、ZIP和ignored目录归属，核实集成与跨机器活跃引用；先commit/push、独立Review及同Head CI，再做白名单安全回收。保护活跃/锁定/旧Master树、未集成代码、私有工具与持久数据，疑义保留并写明复查条件；不触碰全局codex/其他项目/生产。记录before/after数量、容量、准确命令/退出码、实际回收及DEFERRED理由，提交测试恢复入口写下一阶段交接。维护多Agent独立托管Worktree并行能力，Master唯一集成main；不为减少资源恢复共用main串行开发。无需每个安全小步骤再询问，但有歧义/不可逆/生产/跨项目操作暂停对应项。Review ZIP默认采用[V3合同](docs/development/review-package-spec.md)，全部现行非证据源码和当前任务证据各存一次、历史证据/blob/二进制变更完整索引；只交一个已提交Head且独立重开的compact包，旧包校验兼容，不改历史SHA。交付后停等当前关口复审，不自动进入下阶段。

## 实际回收纠偏（PRE-G3-CLEANUP-FIX-002）

阶段已确认关闭且精确安全候选满足条件时，Master必须使用已审白名单实际清理，不再用不可取得的旧聊天证明或统一DEFERRED掩盖缺口。存在安全候选却0删除=FAIL；具体锁定/独特未整合提交/私有runtime/PFX/唯一数据或命令故障逐项列对象、证据、解除条件，其它安全项继续。执行器默认DryRun，Apply需精确ID/期望版本/目录边界/过期拒绝/重验及before-command-exit-after日志；当前/locked/keep路径及后代保护，远端expectedTip用原子compare-and-delete，不覆盖Git历史。阶段DoD必须包含真实资源回收验收与开发环境保留验证；构包54测试不能替代清理测试。公开Git history/任务refs/证据检查只报路径/类别、不泄漏原秘密，不改远端历史。多Agent独立Worktree和Master唯一main集成规则保持，禁止跨项目/全局清理和自动G3。详见生命周期规范及FIX-002任务合同。

BuildKit history后验回现单独重开该项，不把即时列表absence当持久删除；冻结CLI/server/单节点代际，offset读取严格匹配Ref，删除后强无记录诊断，未通过标NOT_VERIFIED。自然生命周期需要实际证据，不能靠等待时长或任意非0当成功；不为修复项目history重启/升级全局Docker或改DB。


## G3-M1-CLOSEOUT-002 永久效率与交付入口

新Master及子Agent开工必须从最新origin/main读取当前授权、任务/交接、资源清单、[效率规则](docs/development/ai-development-efficiency.md)、[Review V3合同](docs/development/review-package-spec.md)和[生命周期规范](docs/development/resource-lifecycle.md)。先Preflight、后冻结公共合同与正反测试，再独立Worktree并行；公共契约Single Writer。失败先廉价分层定位，不重复无关完整验收；稳定Head必须实际完整同HeadCI。

交付冻结顺序固定：源码/格式 → 测试 → 独立Review → 提交 → 同HeadCI → 唯一V3构包 → 独立重开 → 回执。最终diff-check必须exit0，历史失败仍保留。代表截图最多12张、PNG压缩目标3MiB，过程证据从精确Git对象恢复；ignored只入聚合索引。>10MiB报分类体积，>15MiB默认阻断。V1/V2历史VerifyOnly兼容且不改历史SHA。

Fuseki只使用canonical内容寻址构建入口及已校验共享镜像，AppHost不另建随机镜像。资源创建即记录TaskId/RunId/标签/清单；阶段关闭准确白名单回收自身资源，跨任务旧环境保留一套日常开发，其余必须有可再生或可验证备份依据。每个KEEP写准确对象、理由及解除条件；无socket不能标Docker PASS，禁止全局prune/restart/改DB。永久回归由verify -SelfTest及同HeadCI执行，不把静态规则测试当产品测试。
