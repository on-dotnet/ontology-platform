# G3-M4-CONTRACT-B 四源版本差异与影响审批

状态：FROZEN。公共Owner Master。前置Slice A实际已于2026-10-30快进/push origin/main=d1345222fa0f024c99611dff97b2a957998176d1，见slice-a-main-receipt。只M4 B，不M5/G4/G5，无新直接依赖。

## DTO与HTTP唯一来源

唯一g2-models.json→生成C#/g2-schemas→真实宿主OpenAPI→生成TS。旧SourceComparison[]、Manifest V1/V2、PublicationSemantics、AssetVersionSnapshot、Run及Outbox字节/历史hash不改。新模型SourceVersionDiff/VersionDiff/ImpactEvidenceReference/ImpactConclusion/GenerateImpactReportRequest/ImpactReport/ImpactApprovalBinding和两枚举以唯一模型字段为准。

POST /api/v1/ontology-version-diffs（semantic.read+CSRF，CompareVersionsRequest→VersionDiff）；POST /api/v1/impact-reports（ontology.edit+CSRF，GenerateImpactReportRequest→ImpactReport）；GET /api/v1/impact-reports/{id}（semantic.read→原持久报告，过期仍可审计读取）。不接受客户端actor/scope/source hash/报告正文/executor/budget/PublishEligible。请求全部required非null，唯一明确nullable也需显式null；新增提案impact两个nullable字段为了旧请求兼容optional/omitNull，但必须成对，回滚禁止夹带。

现有POST /release-proposals继续复用CreateProposalRequest，新增optional ImpactReportId/ImpactHash。所有新Publish（包括历史未激活缺Impact提案的新审核/激活）都必须从服务器持久报告取得ImpactApprovalBinding；Rollback保持旧算法且拒新impact输入，已经成功的旧命令幂等回执仍可恢复。Proposal.Impact可缺席读取历史，不等于准许新发布绕过。ReleaseSummary新增optional/omitNull Impact，从本模块ReleaseRecord.ProposalId读取原提案绑定，便于正式版本直接追溯报告；历史为空，不改Manifest/Snapshot/Run。

## 固定版本及有界Diff

复用ReadVersion授权完整scope后恢复不可变PG修订或经RustFS/Jena核验的正式四源。拒跨asset/scope、未知/不正确VersionRef。每源保完整BaseText/TargetText（原BOM/换行/语言/datatype不重写）、各hash/缺席、真实集合统计、M1 Graph状态与遥测、可确定增删。固定四源ontology/shapes/vocabulary/data，null vocabulary与空字符串不同。

新IG3VersionDiffRuntime在M1比较同一有界执行内产出完整源Diff，不重复另建解析/同构系统。仍四源共享128 bnode/100000 search/5000ms、左右各5000三元组和1MiB bundle。超预算/取消全四源Graph=INDETERMINATE；统计未实际完成为null，不能0冒充。图同构→语义delta为空/EQUIVALENT，原始源码变化仍准确。无blank的不同图→完整RdfTerm集合差/EXACT。变化图含blank而无法可靠对齐→仅确定的地面三元组差异，TripleDeltaStatus=INDETERMINATE，完整空白结构仍在两侧原文且作用域限定version+source，不按label跨源/版本配对；影响报告列实际unknown并阻断。不得让不稳定RIOT blank IDs进入canonical hash。公共ValidateSourceIdentity/ValidateEvidence在wire、canonical及发布复核统一拒绝delta/Evidence.Triple的blank和blank Focus；实际blank结论使用null Triple+bundle或命名focus证据。相同版本仍核验源/预算，稳定no-op，不用graph projection省略未支持公理。

## 报告、证据与范围

影响只覆盖本资产四源显式变化、IRI/三元组及入向引用；对删除定义而目标仍引用、未解析imports/依赖、未支持公理、来源缺失/hash不符、预算/blank不确定、assessment缺失/过期/不合格列Blockers或Blocking Unknown，审核者不可覆盖。不完整源/hash读取失败直接明确错误，不返回“无影响”报告。

每个Known/Blocker/Unknown结论至少一ImpactEvidenceReference，引用精确From或To、实际source/hash及可确认Triple/focus/path；无法唯一定位bundle/hash，行列无证据null。不伪造原EvidenceRef要求的正式图/业务有效/观察时间。最多256结论/8MiB报告；超限显式unknown blocking，保源/hash/统计，不静默截断当完整。

未知不等于无影响。M5/G4/G5/完整OWL/外部系统未覆盖是明确范围限制（Blocking=false），不能声称其无影响；实际发现变化触及未解析依赖则Blocking=true。PublishEligible仅表达本轮有界技术资格，仍受发布时active基线/CAS/异人审批复核。报告不得使用全系统“无影响”总括。

BaselineKind=VERSION_PAIR允许任意同asset固定两版本作分析，To可历史Release/草稿；用于发布必须To=准确当前draft/revision。VERSION_PAIR用于发布必须当前存在active，且From为其Release和manifest hash；无active时只接受INITIAL，target自比不能绕过真实变更。初始没有active时允许显式INITIAL且From=To当前draft，Diff仍no-op，但已知影响是首次引入整个资产/实体/引用，不是无影响；最终active锁后仍须确认无active。INITIAL与普通self-compare输入/hash不同。

Target draft AssessmentId显式指持久assessment，必须匹配To修订/四源/profile并通过原CheckAssessment完整hash/期限/阶段；缺席分析可生成blocked报告。目标为Release时AssessmentId必须null，绑定仅从manifest已有Semantics恢复，缺席保持unknown。新发布锁读的选定assessment/profile与报告TargetSemantics必须逐字段相同；不能拿其它assessment/旧profile的报告批准当前目标。

## Canonical与幂等

冻结ImpactContractRules.ExecutorVersion=ontology-platform/g3-m4-impact/1，BudgetIdentity=graph128-search100000-ms5000-triples5000-report256-bytes8388608/1。计算或查询InputFingerprint之前必须先ValidateDiffIdentity：逐槽UTF8 hash、Base/TargetHashes固定对应、bundle重算、SourceChanged与原文/缺席一致，不能把声称hash当真实性。Canonical/持久读取/发布复核共用ValidateReportIdentity核对每项证据版本与source hash；它不代替RIOT实际三元组真实性。InputFingerprint包含schema/executor/budget、同资产排序scope、From/To、四源hash/manifest hash、BaselineKind、profile及准确assessment引用，不包含命令key/reason、ID、生成时间或图遥测。

CanonicalHash包含上述输入身份及完整Diff原文/hash、可信统计/delta、ChangedIris/AssetReferences、已知/阻断/unknown证据与资格；scope/来源/IRI/完整三元组/结论/证据按ordinal排序去重。Graph.ElapsedMilliseconds/VisitedNodes规范为0（不参与内容身份），不稳定blank delta不纳入。ReportId/CanonicalHash自身/GeneratedAt/ExpiresAt排除，均是持久envelope；绑定审批时精确时间进入BindingHash。唯一输入行冻结首次ID/生成/到期，相同输入不同幂等key也返回同一报告且不重复创建/刷新；同key异payload409。

生成昂贵比较在短PG事务外。复用原Commands/WriteAsync审计事务和输入advisory锁；并发相同输入只有一个ImpactReports业务行和生成审计，重放不新增生成业务副作用（可有独立幂等回执）。报告ExpiresAt=min(首次生成+24h,真实assessment期限)；过期不自动重算，源/assessment/执行器实际输入变更才新报告，不伪造新时刻。

## 存储与跨模块锁

Ontology独有ImpactReports：ReportId PK、InputFingerprint唯一、AssetId/OrganizationId/SiteIds、TargetDraftId?/TargetRevision?、AssessmentId?、ReportHash/ReportJson、GeneratedAtUtc/ExpiresAtUtc；可空目标FK到自身Revisions、Assessment FK只自身表。From为Release无跨模块FK，不写Publishing表。Master唯一迁移/DbContext初始storage合同写者，迁移只向前升级；Down拒删报告。无新通用Repository。

IImpactPublicationReader.LockForPublicationAsync使用Publishing传入同物理DbConnection/DbTransaction，仅由Ontology读取自身记录并核验persisted hash/input/profile/assessment/To/四源/期限/技术资格，返回服务器ImpactApprovalBinding；锁内不跑Jena。PublicationService创建/决定/准备/最终提交四点核验，最终active锁后再核验baseline。沿draft→proposal→release→active锁序，不反向交叉锁。持久报告immutable可共享读，不新增审计或改表。

PublishingRules.Binding保留无Semantics/有Semantics无Impact两个旧匿名对象算法原字节，新增Impact非null第三分支包括整个ImpactBinding。Report/profile/source/target/assessment/时间或审批内容变化都使BindingHash/锁读核验不匹配。没有profile v5，没有Manifest升级：Release.ProposalId→Proposal.Impact→ImpactReports可追溯；旧A已发布v4/V1/V2/历史Run/回滚原样可读。

## 错误、验证与所有权

404 impact_report_not_found；409 impact_binding_conflict/impact_expired/impact_baseline_conflict/impact_target_conflict/idempotency_conflict；422 impact_required/impact_not_eligible/impact_reference_invalid；413报告/源预算；403完整scope/角色；429/503真实引擎边界。伪造hash不能被审核者覆盖。

Master单写本合同、模型/生成物、Contracts纯canonical/interface、Host/client、ImpactReportRecord与DbContext初始存储合同、Migrations、公共验收/锁/CI/Tokens及合同/Security测试；SEM-B独立树写Ontology/Pub实现（排除上述storage/Migrations）、真实Semantic/Publishing相关测试及samples；WEB-B独立树写ontology与publishing相关UI，读公共client，不改生成物/Tokens/Shell。实际任务卡在冻结后派工前写完整SHA/path/owned_paths/负例/命令。

合同先廉价正反例：缺/extra/null/未知枚举/VersionRef、成对impact字段、rollback夹带、canonical重复/顺序/遥测稳定而hash/source/sem变化不同。独立Review后才并行。真实层必须验证任意两固定版本/四源hash/no-op/bnode同构/预算、报告生成幂等并发/未知阻断、伪造过期跨版本/source/profile/assessment陈旧审批/active CAS/权限、真实发布→active查询→旧Run→回滚及浏览器深浅主题/窄屏/键盘。旧通过项只在精确输入一致时复用，不能把纯合同测试当产品。

冻结独立Reviewer：/root/preflight_review。原Down删除、原文/hash及证据不一致、blank不稳定、INITIAL基线及Graph/Delta矛盾均已复核关闭；最终命名IRI/ground窄验18/18、Graph状态14/14、迁移1、Host1通过。合同层完整兼容101PASS/1SKIP/0FAIL（实际V2 artifact reader待最终后写真实门禁），未误标零skip或B产品PASS。详细原FAIL与窄复验见本任务master证据。
