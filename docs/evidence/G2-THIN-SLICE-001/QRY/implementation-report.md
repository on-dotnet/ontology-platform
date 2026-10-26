# G2-QRY-001 实施记录

状态：DRAFT / PARTIAL。当前已可由Master组合唯一Gateway；故障/取消/完整入口验收及独立Review未完成。

BaseSha：`b1d2a51feea5b27bf91e2470fe87f3aea697fcb3`。共享资源Master提交8223101已在任务树cherry-pick为6652f25；所有其余交付仅任务卡owned_paths。

真实红例：`dotnet test --project backend/tests/OntologyPlatform.QueryTests --no-restore`，1项失败/0成功，exit2，registry-red.txt。注册不存在导致失败，未用测试替身。

真实首轮：`python3 scripts/acceptance/query-plan.py --label query-first-real`，11项/10成功/1失败，exit2。失败为record内数组引用相等断言；改为完整序列化字段比较，没有弱化业务断言。此前query-initial为runner误将Publishing迁移模块名替换成Query，真实exit1、未运行测试；保留原始记录。

当前绿：`python3 scripts/acceptance/query-plan.py --label query-draft-green`，12/12成功、0跳过、exit0。随机新PG18.6、RustFS1.0.3、Jena6.2.0真实资源，新数据库迁移/新合成组织/独立发布；已清理本轮容器。不读取历史private runtime或卷，不以Mock证明产品通过。

覆盖：唯一三能力、机器Schema可达闭包/oneOf/未知字段、真实发布绑定版本、五类schema、FOUND/EMPTY/PARTIAL/UNAUTHORIZED/AMBIGUOUS、双厂同号、实体scope、多对多关系两端、行预算、缺来源、非法路径/IRI/能力/预算、证据新实例重定位/二次授权/真实源hash。

格式：backend目录`dotnet format src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery --no-restore`及`dotnet format tests/OntologyPlatform.QueryTests --no-restore`均exit0。SelfTest首轮环境缺已锁PyYAML、日志尾空白、新lock缺末换行，保留失败；仅恢复批准PyYAML6.0.3到本树.tools/pythonlibs并规范本任务日志，复验见self-test-draft-green.txt。

NOT_RUN：正式Host组合/实际runtime OpenAPI导出、REST/MCP/MAF/SSE/浏览器总链、Linux同Head CI、Windows/Intel/生产/付费模型、独立审查。DRAFT不代表S3或G2通过；最终唯一Review ZIP由Master制作。
