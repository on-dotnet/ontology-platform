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

每里程碑获审后按[生命周期规范](docs/development/resource-lifecycle.md)记录分支/Worktree、Docker、ZIP和ignored目录归属，核实集成与跨机器活跃引用；先commit/push、独立Review及同Head CI，再做白名单安全回收。保护活跃/锁定/旧Master树、未集成代码、私有工具与持久数据，疑义保留并写明复查条件；不触碰全局codex/其他项目/生产。记录before/after数量、容量、准确命令/退出码、实际回收及DEFERRED理由，提交测试恢复入口写下一阶段交接。维护多Agent独立托管Worktree并行能力，Master唯一集成main；不为减少资源恢复共用main串行开发。无需每个安全小步骤再询问，但有歧义/不可逆/生产/跨项目操作暂停对应项。Review ZIP默认采用[V2合同](docs/development/review-package-spec.md)，全部现行非证据源码和当前任务证据各存一次、历史证据/blob/二进制变更完整索引；只交一个已提交Head且独立重开的compact包，旧包校验兼容，不改历史SHA。交付后停等当前关口复审，不自动进入下阶段。
