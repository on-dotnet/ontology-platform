# G2-SEC-SUPPORT 公共安全与事务审计支持

G2-THIN-SLICE-001 Task1内部实施子项；只交付既有授权内安全基础，无新业务/产品/依赖。Owner=g2_security_support，独立Reviewer由Master派。Master明确将以下手写文件在本子项期间转给此唯一Owner，不与Master同时写；公共DTO/接口/项目/锁/迁移/Host/CI继续Master唯一写入。

owned_paths：`backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/TransactionalAuditWriter.cs`；`backend/src/Hosts/OntologyPlatform.Api/G2/G2Authorization.cs`；`.../G2EndpointGuard.cs`；`backend/tests/OntologyPlatform.SecurityTests/G2SecurityTests.cs`；`.../G2AuditTransactionTests.cs`；`docs/evidence/G2-THIN-SLICE-001/SEC/**`。必要helper只在这些目录并报Master登记，不能改旧安全测试或公共Host。只读Contracts/G2Services.cs/G2Models.g.cs、冻结合同和G1安全实现。

实现Governance-owned ITransactionalAuditWriter+IAuditTrail；同物理DbConnection/DbTransaction显式UseTransaction，不提交外层txn/不跨模块直写表；原子失败关闭，完整scope保真、多厂SiteId=null。Standalone审计自己事务提交后返回ID。使用现有AuditRecord、GovernanceDbContext与IDbContextFactory，不造第二套审计。仅固定事件/资源/结果，不记录原始源码/Prompt/异常。

API G2Authorization.AddG2Authorization(IServiceCollection)只注册共同具名semantic.read（viewer/operator/auditor）、ontology.edit（operator）、release.approve（auditor）、release.activate（operator），并有CreateActor(HttpContext)从G1已验证Claims投影到唯一ActorContext，不信任请求头/Body。scope最终由模块资源应用服务检查，不能把role-only说成完整资源授权。

G2EndpointGuard的冻结调用签名：ReadAsync<T>(HttpContext,string policy,Func<ActorContext,CancellationToken,Task<T>>)；WriteAsync<T>(HttpContext,string policy,CommandContext,Func<ActorContext,CancellationToken,Task<T>>,bool requiresRevision=false)，均Task<IResult>。认证401；授权403+真实拒绝审计；CSRF用原生IAntiforgery及原header，Origin若提供必须等于Security.PublicOrigin，拒绝外部/畸形Origin。写入Command ID/幂等key1..64、reason1..500、expectedRevision>=0；requiresRevision核对If-Match格式`"<revision>"`和body，两者冲突409、缺428。成功结果可由DTO提供ETag（草稿），不捏造X-Audit-Id；业务用例同事务提交后才能给AuditId。SemanticOperationException固定status/code映射原Problem；未预料依赖/内部异常留原Host安全诊断，不能吞成成功。响应no-store。取消不吞成正常结果。不能在guard里提前发200再写业务。

真实测试：同一PG外层业务探针+Governance audit双context共享txn，commit二者全有、rollback二者全无、audit失败整个业务不commit、multi-site完整数组。探针仅测试自己临时schema，不能改生产业务；G1_SEC_PG_CONNECTION由既有test-governance.py临时PG提供，缺配置明确Inconclusive/NOT_RUN。真实Kestrel/原生Antiforgery/固定可信fixture身份做401/403/Origin/CSRF/If-Match/409/428边界，错误不含秘密；受控测试身份只在测试宿主，不加产品测试登录头或端点。

按TDD保留真实红绿、命令/退出码/测试数；中文XML全部手写成员、局部用途注释/Allman。及时commit/push独立任务分支，不main/不派子Agent。提交前自测和报告；Master另审后集成。代码没有注册到产品Host前不能声称产品G2安全验收通过。
