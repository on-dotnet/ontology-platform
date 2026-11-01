状态：PROPOSED_G4_CONTRACT / NOT_IMPLEMENTED。TaskId：G4-00-CONTRACT-001；Master 单写。基线 d1a61daffe844475b07705797e3ad325cc3f2945。

本文件为 V1.1 输入的仓库合同入口。下列引用章节按原字节归档，属于本合同的详细定义；当前裁决优先于输入中的建议，G2/G3 冻结合同优先于 G4。输入包历史“未授权”描述保留，2026-11-01 用户明确批准本任务仅合同归档、验证、独立 Review；不是产品实施许可。

## 权威、身份与事务

详细字段及全部读取/命令端点纳入[API 合同 §1–7、9–10](../evidence/G4-00-CONTRACT-001/input-v1.1/docs/05-DATA-API-CONTRACT.md)；AI建议纳入[AI Native 合同](../evidence/G4-00-CONTRACT-001/input-v1.1/docs/07-AI-NATIVE-ALIGNMENT.md)。G4 只绑定现存 G3 OntologyRelease，不写 SourceBundle/dataTurtle/正式图/Manifest/Run。connections schema 名称及持久表仍 PROPOSED，不创建迁移或跨模块写表。

StableMappingIdentity 固定完整 org/sites、ontologyReleaseId、connectionId/revision、catalogSnapshotId/fingerprint、mappingHash、validationHash、adapterVersion；审批另固定 secretVersion、impactHash、提交者与期限。原始输入或权限变化后旧审批不得激活。Canonical 序列化须冻结 executor/version、字段排序、IRI/Unicode/null/decimal/time策略及字节反例后方可实施，当前 synthetic hash 不是生产 SHA256。

身份沿 G3-M4 org+site+sourceNamespace+externalId+有效区间；同号不自动 sameAs。半开 [from,to)、未知端点不当永久有效，业务时间不等于 observed time。未知单位/时区、不可逆转换与无法确定的身份重叠阻断。G4 转换仅登记的纯类型/单位转换，不承担 G5 指标业务口径。

## 状态守卫

| 转移 | 必要条件 | 拒绝与恢复 |
|---|---|---|
| DRAFT→VALIDATING | 固定 revision+源目录+本体版本 | 无固定版本拒绝 |
| VALIDATING→PROPOSAL_READY | Schema/Identity/TimeUnit/Security/Executability/Reconciliation/Impact 必需项真实 PASS | FAIL/INDETERMINATE/NOT_RUN→NEEDS_DECISION；新修订再验 |
| PROPOSAL_READY→REVIEWING | 固定全部身份/hash/assessment/impact/提交者/期限 | 漂移409，不提交可变引用 |
| REVIEWING→APPROVED/REJECTED | 当前权限、非提交主体、未过期、未决定 | 自批403，重复不同决定409 |
| APPROVED→ACTIVE_RELEASE | 再验全部输入/授权；PG active CAS+Governance审计+Outbox同物理事务 | 任一失败旧active不变，固定幂等回执 |
| ACTIVE_RELEASE→REVALIDATION_REQUIRED | 相关字段/类型/权限/源变化 | 不猜列；旧制品只供审计，不绕过当前ACL |
| 回滚提案→审批→激活 | 同mapping/scope固定旧release+manifest hash，当前源兼容 | 未知兼容、陈旧批准、跨scope均拒绝 |

外源查询与昂贵评估不持有 PG 长锁；先固定不可变输入，短事务锁与 CAS 复核。查询从 PG 权威 active 固定版本，不以 Outbox 通知顺序为事实。MappingRelease 原文不可变；active/activationRevision 是读时指针投影。回滚不改历史 G3 或 Mapping hash。

## 读取与恢复

U07 创建后 GET /mappings/{id} 恢复最新；GET /revisions/{revision} 恢复固定历史；PATCH+If-Match 保存。U09 GET /assessments?revision 与 /mapping-assessments/{id} 固定评估。U10 从 /mapping-proposals?status=PENDING 到 /mapping-proposals/{id}，按绑定修订、diff与assessment审核，不能读取当前可变草稿替代。U11 GET /mapping-releases?mappingId、/mapping-releases/{id}、/mappings/{id}/active；无active统一404（不再同时规定EMPTY/404）。所有GET无副作用、当前scope授权；分页游标绑定筛选与权限版本。

OFF 默认可完成手动+确定性规则路径；LOCAL/APPROVED_EXTERNAL 另批。模型只产生有来源的候选，未知概念进入单独 G3 提案，不能创建正式 Class。注释/Schema描述按不可信数据处理；接受建议不等于批准发布。新增权限、审计 action 与存储/secret实现维持未实施，详见实施计划 ADR。

## 独立 Review 裁决 RM-01/02

RM-01：上表是跨对象工作流，不是 MappingDraft.status wire枚举。Draft唯一枚举为DRAFT/NEEDS_REVIEW/VALIDATING/READY_FOR_PROPOSAL/BLOCKED：NEEDS_DECISION→NEEDS_REVIEW，PROPOSAL_READY→READY_FOR_PROPOSAL；安全/版本无法恢复→BLOCKED。REVIEWING/APPROVED/REJECTED属于Proposal生命周期，ACTIVE_RELEASE属于Release/active指针，绝不写入Draft.status。表内MAPPING_DRAFT表示Draft对象而非新增枚举。

RM-02：原 MappingProposalView strict Schema仅PUBLISH设计子集，不能承载ROLLBACK目标。回滚仍是必须的人审/CAS业务路径，但 G4-M3 实施前必须另冻kind=PUBLISH|ROLLBACK判别、目标releaseId+manifestHash、作用域/当前兼容/期限/审计读取的正反例；ROLLBACK不得要求当前Draft等于旧版本，也不得用当前Draft字段假充回滚目标。此机器读模型缺口为 BLOCKED_FOR_IMPLEMENTATION，需ChatGPT裁决后另行冻结，不能因现有正例PASS宣称完整回滚DTO已冻。
