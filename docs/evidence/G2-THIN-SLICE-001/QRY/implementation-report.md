# G2-QRY-001 实施记录

状态：READY_FOR_INDEPENDENT_REVIEW / PARTIAL。Task5实现与本卡模块验收完成；独立Reviewer由Master另派，S3全入口组合尚未在本树验收。只交付本卡，不进入AI或制作最终ZIP。

BaseSha：`b1d2a51feea5b27bf91e2470fe87f3aea697fcb3`。公共资源Master提交8223101在任务树cherry-pick为`6652f25`；其余交付仅QRY owned_paths。首个可消费DRAFT为`cfcfa12a43d3be33fb3c98af33fbec8fa5a6813a`，已推送。后续源文件精确SHA256见query-frozen-source.json的13项sourceHashes；实际重开重算13项全部相符。

实现：Scoped唯一ISemanticGateway/IEvidenceService，AddSemanticQueryModule注册；三能力describe_ontology/resolve_entity/traverse_relationships。完整输出Schema仅从嵌入机器生成组件的SemanticQueryResult可达闭包派生，保留oneOf/null/enum/未知字段约束且重写本地refs为defs。版本由精确input/output/executor SHA256派生，最终executor语义标识为/3。正式快照必须包含实际能力版本；PUB已有optional Gateway绑定支持，无硬编码v1。

Schema Catalog由正式OWL声明派生；标准rdf:Statement/PROV-O解析真实源记录/有效时间/观察时间，模型版本以正式manifest ReleaseId绑定，不把g2-synthetic-1当发布版。Evidence ID为releaseId加完整标准断言及来源内容散列，不依赖进程缓存或空白节点导出标签。打开时真实Catalog重新授权、同版graph重定位、S3 GET/hash回验；不信任客户端对象键/hash。

完整对象scope先经Catalog授权，实体和关系两端再次按组织/厂区/计划过滤。IRI仅用于内存标准项等值匹配，不拼接SPARQL，不请求客户端URL。遍历双向邻接，输出保持RDF原关系方向；深度1..5、行1..100、时间1..5000ms，真实取消传播。深度或行预算截断明确PARTIAL，缺来源明确诊断；无可信snapshot前403/404/503，已固定snapshot后业务六态，不伪造空发布。

查询/证据通过Governance独立持久审计，PG失败安全503。OTel ActivitySource/Meter均OntologyPlatform.SemanticQuery；指标仅固定三能力/六态，无源正文、主体、厂区、Trace标签；结果Trace来自可信ActorContext。

## 红绿与真实执行

- 注册红例：`dotnet test --project backend/tests/OntologyPlatform.QueryTests --no-restore`，1项失败/0成功，exit2；registry-red.txt。真实模块入口缺失。
- 初始runner：`python3 scripts/acceptance/query-plan.py --label query-initial`，exit1、产品测试未运行；误将Publishing迁移模块改名Query，已修复并保留记录。
- 首轮业务：`... --label query-first-real`，11项/10绿/1红，exit2。record内数组引用相等断言错误；改为完整序列化字段比较，没有弱化来源字段。
- DRAFT：`... --label query-draft-green`，12/12、0跳过，exit0。
- 故障红例：`... --label query-fault-red`，20项/19绿/1红，exit2；反向谱系未实现，修正为双向受控邻接。
- 预算/审计红例：`... --label query-budget-audit-red --filter 'FullyQualifiedName~DepthBudget|FullyQualifiedName~AuditFailure'`，2/2失败、exit2。深度截断错误标FOUND和原始PG审计异常未转安全503；均已修复。
- 最终冻结源码：`python3 scripts/acceptance/query-plan.py --label query-frozen-source`，**24/24成功、0跳过、exit0**。其中2项纯真实Registry/Schema测试、22项真实PG/Jena/RustFS服务集成（含参数化删图/篡图两例）。query-frozen-source.json记录命令、退出、输出、源码散列；不以静态检查或替身作为产品PASS。

真实环境：每轮随机新容器名、新PG库/迁移、新RustFS临时数据、新Jena配置与TDB；不读取历史private runtime/卷。PG18.6与RustFS1.0.3沿已批准digest。最终Jena为Master按仓库固定JRE/Jena6.2.0/SHA512 Dockerfile构建的`ontology-platform-g2-fuseki:6.2.0`，实际image ID `sha256:6cd40ff063db802d36a082fda07849fef3289d974b48d5c44fc9a82c41a1e826`。runner支持G2_TEST_JENA_IMAGE，并使用Mac/Linux存在的临时根目录；旧镜像运行证据保留。全部本轮容器已清理。

故障边界：成功路径全为真实PG/Jena/RustFS。小范围故障注入为真实Catalog完成后阻断HTTP发送、真实S3响应到达后破坏字节、真实PG触发器拒绝审计，以及真实Jena删除/覆盖发布图；均验证恢复。没有返回假成功snapshot或模拟数据源。新服务实例重定位已实际执行；真正OS进程重启未单列测试，不能将新DI scope称为进程重启。

覆盖：六态、五类正式schema、双厂同号与预算下仍保留歧义、多对多/反向谱系/缺关系、跨厂关系两端过滤、声明组织/厂区/角色授权先于外部读取、未知关系/危险IRI/错误能力版本/超预算、来源缺失、错hash、删篡图与恢复、证据二次授权、依赖超时/用户取消、实际R2激活期间R1快照保持、显式历史R1读取、真实查询/证据审计事实及审计故障恢复。

## 工程验证和剩余边界

final-verification.json逐命令保存真实exit0：backend cwd分别format模块/新测试/唯一SemanticEndpoints相对路径并verify-no-changes；QueryTests Release与实际Api Release构建（0警告/0错误）；`pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`；git diff --check。受锁restore在最终runner真实exit0。SelfTest首次失败因本树缺已锁PyYAML6.0.3、原始日志尾空白和新lock末换行；保留首次失败，按已批准requirements仅项目隔离恢复后通过，没有弱化门禁。

NOT_RUN / NOT_VERIFIED：本树正式Host服务组合与实际runtime OpenAPI导出比对、REST/MCP/MAF/SSE/浏览器全链、Linux同Head CI、Windows/Intel/生产/付费模型、独立Review。API编译成功不等同HTTP验收；机器Schema组件不是运行OpenAPI导出。Master需注册模块及OTel source/meter、组合真实S3发布与AI入口，并使用最终registry版本重新发布演示R1/R2。未实现其他模块或额外直接依赖。
