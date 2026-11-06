# 保持15MiB的证据选择与恢复合同

当前来源9ed3b9283acc81805737fb19efd3123281010103；用户已批准减量方向，范围见REDUCTION-APPROVAL.md。Master单写，Reviewer只读。本文件是实施计划，不是测试PASS或交付回执。

## 合同

1. 新策略仅可信工具中固定Task/Base/祖先/批准SHA全部符合时生效。旧V1/V2/无批准V3兼容。批准存在但损坏必须拒绝；不提供CLI、环境变量或ZIP自授权开关。保持15MiB创建及重开硬限制。
2. 已提交review-evidence-selection.json采用闭合schema1：finalRun、validationPath、retainedPaths。finalRun必须是本任务b-continue-YYYYMMDD-NN；该Run的全部已提交非PNG证据自动随包，不能逐文件隐藏。validationPath必须在该Run内且随包；选择文件自身随包。retainedPaths是本任务内准确、存在、唯一的非PNG路径，保留关键失败/修复/审批/恢复链。代表PNG继续现有独立清单及12张/3MiB/像素门禁。独立Reviewer必须审查选择链完整性，工具不把文件名当产品PASS。
3. 工具强制保留Run32 I06失败、Run33 I07失败、无损迁移映射、体积根因报告及本实施合同；其余审批/关键失败/修复链在明确清单中补全。工具完整扫描所有Head blob及全部变更双侧blob。全部Head证据仍有commit/blob/SHA/size/path/恢复索引；删除证据仍由changed-files双侧索引恢复。
4. 仅当一个变更所有实际存在的两侧路径均在docs/evidence/内，才标为evidence-index-only；跨证据/源码重命名保留完整文本patch。二进制保持binary-index-only，其他文本为full-text。每项新增patchDisposition；原isBinary按原始blob分类，不伪装证据为二进制。两侧添加commit和准确git cat-file恢复信息。
5. 有界argv保持256项/8192字节。先准确literal目标文本集合，再根范围减精确排除集合。仅在没有需包含的证据文本时，可用整个docs/evidence目录代替该目录内排除路径。真实name-only在执行前后必须等于应交付文本集合；跨界重命名不能用目录排除偷漏，无法满足预算则拒绝。全范围diff-check仍检查全部证据。
6. manifest绑定策略ID、批准SHA、选择文件路径/SHA、finalRun、validationPath和diff范围；VerifyOnly重新从可信工具及Git推导并逐字段比较，删除/伪造策略或重算ZIP散列不能绕过。EvidencePath必须等于选定validationPath且有payload映射。摘要明确证据变更使用索引，不能声称全量文本patch或完整离线审计。

## 实施与验证顺序

1. 独立只读Review本合同；补真实临时Git/ZIP正反例并观察RED。
2. 三文件最小实现：选择与diff策略、创建/重开对称绑定、合同增量。定向GREEN覆盖无批准/错身份/篡改、缺选择/未知字段/外任务/重复/不存在路径、关键失败及finalRun完整性、删除与跨界重命名/二进制、证据被删秘密、重算hash篡改、错误EvidencePath、15MiB门禁和旧格式兼容。
3. 冻结并独立Review选择链及代码；完整SelfTest和必要工程检查。提交稳定T，创建新的正式Run35输入/资源清单，完成真实硬门禁及资源回收。不得用Run34冒充新T。
4. 按最终Run更新选择及validation等非执行证据，最终H只允许已审说明/证据增量；保留执行工具实际字节绑定。完整两层diff-check、独立Review、任务分支普通push/回读。
5. 唯一V3实际创建/分类体积/独立VerifyOnly/包外回执。若仍超过15MiB，记录实际分类原因并进一步在同一保留/索引合同内选择；不自动提限。到main审批关口停止。

## 当前验证

2026-11-06远端main=d1a61daffe844475b07705797e3ad325cc3f2945；任务分支=9ed3b9283acc81805737fb19efd3123281010103，与本地一致。新策略及新Run完整验收尚未运行。
