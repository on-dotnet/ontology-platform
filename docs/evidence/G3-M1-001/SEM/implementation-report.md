# G3-M1-SEM 实现报告

状态：BACKEND_IMPLEMENTED / REVIEW_PENDING。仅当前M1；未合并main、未进入M2，最终整阶段判定/同Head CI/唯一Review ZIP由Master负责。分支codex/g3-m1-sem，独立Worktree=/Users/chasen/.codex/worktrees/g3-m1-sem/ontology-platform，Base=a4e677a12ee6ddf0f17add548f64c049136bd2fa。开工fetch成功且工作树干净；开始/结束总耗时无法可靠还原，UNKNOWN。

## 实现

- 固定20行profile、四维精确状态、ASSERTED_ONLY、按声明顺序JSON且自身hash置空的SHA256。BASIC只指既有精确编辑；命名equivalent/disjoint/inverse只有SOURCE，不运行OWL推理。未知OWL/RDFS、复杂表达式、身份、imports、OWL-Time等保留原文并阻断发布；普通annotation须明确声明/登记，未声明literal关系不能猜作注释。独立审查补核G2既有可选validToUtc来源元数据后仅补该词，真实V1原策略接受、新V2可发布且未知validUntilUtc仍阻断；不扩OWL-Time/M4。Shapes继续独立合法property/list blank策略。
- 新IG3OntologyService与IG3SemanticRuntime；真实RIOT/SHACL生成assessment，报告/assessment/幂等回执/审计同PG物理事务，Validate保持原响应并生成关联评估。同命令重放不刷新时间。新发布创建、审核、准备、最终激活再次锁读并核验准确revision/四源hash/当前profile/24h有效期/自身散列/eligible。
- auditor在IDraftPublicationReader只有完整scope的只读核验权，写操作仍需operator。审核与激活统一draft→proposal锁顺序；旧Release回滚不锁当前草稿。
- 四源原字节/hash与旧修订保留；比较采用真实RIOT、集合去重、分区细化、空白双射搜索及最终全集核验。左右bundle各总5000条、每源256KiB/合计1MiB、每源两图各128 blank、四源共享5s与100000搜索节点。任何总预算/取消撤回四个结果为INDETERMINATE，非法Turtle仍422。G2生产预算未放宽。
- 新发布V2具有Semantics；原V1无Semantics仍按独立原G2支持算法回验。旧批准Binding缺席Semantics时保持原匿名字段和顺序，未增加null字段。真实V1原始manifest对象hash与字节回读、同批正式图、回滚及新V2共存均已实测。Query明确接受V1/V2并保持同批对账；原Run/SSE形状未修改。

## 真实验证

|项目|实际结果|证据|
|---|---|---|
|最终已提交诊断修复Head的SemanticTests|96/96 PASS，0跳过；暂存图0残留|g3-sem-final-head-run.txt|
|PublishingTests真实PG/Jena/RustFS|55/55 PASS，0跳过；含既有validToUtc兼容正反|g3-sem-metadata-green.txt|
|QueryTests真实发布/授权/查询/同批读取|49/49 PASS，0跳过|g3-sem-query-final-run.txt|
|AgentTests原Run/SSE/deterministic兼容|33/33 PASS，0跳过；不代表真实LLM|g3-sem-query-agent-run.txt|
|verify.ps1 -SelfTest|前轮完整exit0，含构包54/54及维护正反例；后续metadata轮因原manifest缺LF而exit1，封套纠正后静态exit0；最后完整同Head门禁由Master执行|g3-sem-selftest-final-head.txt、manifest-text-format-fail.txt、manifest-envelope-static-verification.txt|
|全部owned改动C#按所属项目dotnet format|6项目全部exit0|format-final-head.json|

以上为233项模块用例的最新真实覆盖；Publishing55已在validToUtc精确兼容修复后完整运行，Query/Agent成功早于随后诊断映射、validToUtc兼容与import格式修复；未冒充最终整合Head的全栈CI。SEM96在已提交fad4387修复上运行；4ef97f2只有Publishing测试import顺序。原始执行脚本已按实际运行内容存executed-harnesses，均输出到本任务/private/tmp，从未执行硬编码旧G2证据目录runner。Master仍须对最终整合Head执行组合验收和CI。

红绿证据保留：新增生产边界/profile初始失败、20语料09初始失败、Binding遗漏assessment初始失败、未声明annotation初始失败。真实迁移Down曾先删assessment表后被旧保护拒绝；Master改为forward-only后重新fresh库通过，旧Initial-only独立库仍精确验证55P03/P0001。ontology.assess审计登记缺失、签名时钟夹具误偏移、旧未声明注释fixture等真实失败和修正均保留，不重写为成功。

## 独立审查诊断修复与限制

SHACL验证使用ontology/vocabulary/data合并图，旧report的synthetic-data不是data来源证明。实际ontology-only/vocabulary-only/data-only/同focus跨源歧义四例统一使用新assessment SourceId=bundle和BundleHash，Line/Column=null。不能宣称已有精确SHACL源行列。原report.SourceId保持synthetic-data，wire不改。支持策略诊断可由实际解析唯一定位的ontology/vocabulary/data三例仍保留各自准确单源hash。真实红2/2→绿2/2、扩展7/7见diagnostic-review-fix.md及日志。

OWL_REASONING永远NOT_RUN；SHACL conforms不等于完整OWL一致性。图预算耗尽不能解释成零差异或可发布。Monaco、真实收费模型、Windows/Intel、生产HA/SLO和M2–M5均不在本SEM通过声明内。

## 模型与Master迁移要求

模型只有Ontology新增AssessmentRecord/DbSet：ontology.Assessments，主键AssessmentId，ValidationReportId唯一索引与Validations一对一Restrict外键，DraftId+Revision到Revisions的Restrict外键；列为AssessmentId、ValidationReportId、DraftId、Revision(long)、AssessmentJson。Publishing只在既有JSON内增加可缺席Semantics，没有新增表列。

Master已生成f1cd505并以b48a68a修复forward-only Down；新表和原报告在拒绝downgrade后保持，均真实验证。Governance固定ontology.assess事件由Master31b5ff5登记。SEM只cherry-pick这些Master提交用于测试，没有手改迁移/公共合同/Host/锁/CI。不再需要额外模型迁移。

## 资源与未决项

精确回收本SEM创建的33个临时容器，逐一container inspect确认无记录；未删镜像、卷、历史refs/旧树或私有runtime。唯一保留Jena匹配本任务fixture挂载后按不可变ID删除；公开fixture目录与各轮SelfTest退出后的/tmp隔离PyYAML/toolbin已真实删除。命令、退出码、容量与after见resource-lifecycle.json。分支、Worktree及构建缓存为活跃待审成果保留，避免清理未整合代码；实际V1/V2公开合成manifest以compatibility-fixtures内带LF的base64封套无损归档；恢复器按原大小/hash核验并拒绝覆盖，供独立reader读取恢复后的原始字节。直接原始JSON缺末尾LF曾使文本门禁FAIL，记录manifest-text-format-fail.txt；此次只纠正证据容器，不修改原字节/hash或重跑业务。

独立Astra最终结论、Master HTTP/OpenAPI/Web组合验收、最终同Head CI与唯一V2 Review ZIP仍由Master记录；本报告不代替其PASS。最终提交/推送本证据后等待当前关口复审，不自动进入下阶段。
