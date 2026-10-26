# G2-QRY-001 实施记录

状态：READY_FOR_INDEPENDENT_REVIEW / PARTIAL。Task5实现与本卡模块验收完成；独立Reviewer由Master另派，S3全入口组合尚未在本树验收。只交付本卡，不进入AI或制作最终ZIP。

BaseSha：`b1d2a51feea5b27bf91e2470fe87f3aea697fcb3`。公共资源Master提交8223101在任务树cherry-pick为`6652f25`；其余交付仅QRY owned_paths。首个可消费DRAFT为`cfcfa12a43d3be33fb3c98af33fbec8fa5a6813a`，已推送。最终实现与真实验证SourceHead：`96fc92b4c6edbedaefe4219e17795f6969693ff2`，已推送且分支当时干净。本文后续仅补该固定SHA回执，不改变已测试源码。后续源文件精确SHA256见query-frozen-source.json的13项sourceHashes；实际重开重算13项全部相符。

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

## 第一轮独立审查修复（2026-10-26）

原审查固定Head为`2e0174560f3c34bb70a62580ec67f5e6f9d97edd`，结论C0/I5/M2；以上原实施记录保留历史事实，本节覆盖修复后的最终行为。按receiving-code-review与SDD fix-loop先复现再改动；没有自行派Reviewer、改main或制作最终ZIP。

共享依赖由Master明确授权：`cee8a7b`是Master233dd61的精确TransportAsync Guard；`f7159b9`是Master0e970f9同批读取合同；SEM源`21ed0172fc207db55164985f3c97fd2a640f1519`已cherry-pick为`8d81740`。QRY未手改这些共享/SEM源。Master另明确批准只在全新QueryTests工程加入Api ProjectReference及该新锁的现有批准闭包；没有新增PackageReference。父消息明确修正卡中旧时间下界为冻结合同100..5000ms，实际Registry、Validate、整体计时入口已统一，executor为`/4`，版本从新输入/唯一输出Schema/executor重新计算，不复用旧发布版本。

修复内容：

- I1/I2/I3：标准POST为`/api/v1/semantic/queries`，通过TransportAsync复用真实身份、Origin和原生CSRF；全部四个入口在JSON绑定前RequireAuthorization("semantic.read")，声明实际DTO及400/401/403/404/409/422/503适用Problem元数据。未构造假CommandContext。
- I4：新增VerifiedReleaseSources，从Catalog已授权清单恢复原始三/四源。独立校验清单版本、release/图/快照四源hash、bundleHash、固定对象槽位与键、大小与媒体类型，真实GET后再算SHA256并严格UTF8解码。Gateway与Evidence仅调用SEM ReadVerifiedPublishedAsync(manifest,sources,ct)，消费其已与权威源精确对账的同一数组，之后不再ReadPublished。真实Catalog后PUT无关triple窗口均拒绝，查询UNAVAILABLE、证据503。
- I5：同一linked deadline覆盖目录、源、图、业务投影、真实成功或失败审计。审计提交并且预算仍有效才公开结果；错误审计仅用剩余预算，不新增第二时间窗。预算已耗尽或审计无法完成时503失败关闭，不补无界审计，不声称已成功审计。成功审计放在处理catch外，真实失败不被第二次审计隐藏。PG驱动将取消包装为DbException时先检查真实token，保留调用者OCE。证据读取使用同样五秒有界策略。
- M1：全部实际返回六态统一经过Complete计数一次，catch返回UNAVAILABLE也有低基数capability/status指标。
- M2：修复原self-test-draft.txt EOF空行与RegistryTests相邻成员空行；执行完整Base差异检查，不能只靠工作区为空。

真实执行记录（命令均为`python3 scripts/acceptance/query-plan.py --label <下列label>`，过滤参数如列出；每份同名JSON含实际命令、exit、输出、源码散列，不因label包含green就视为成功）：

| Label / filter | 实际结果 | 证明 |
| --- | --- | --- |
| review-1-service-red / FullyQualifiedName~ReviewRegressionTests | 5项全红、exit2 | 真Catalog后图变异被旧实现误报EMPTY/404；真pg_sleep超时仍成功；UNAVAILABLE计数0 |
| review-1-error-budget-red / FullyQualifiedName~FailureAuditIsBoundedAndNotHidden | 1红、exit2 | 修正为明确1000ms查询预算后，错误审计仍越界 |
| review-1-http-red / FullyQualifiedName~QueryHttpTests | 10项，9红1绿、exit2 | 真Kestrel生产路由、防伪、Origin、授权先绑定与metadata缺陷 |
| review-1-http-green / FullyQualifiedName~QueryHttpTests | 10/10、exit0 | 生产薄适配HTTP修复 |
| review-1-service-green / FullyQualifiedName~ReviewRegressionTests | 5/5、exit0 | 同批读取、审计预算和metrics修复 |
| review-1-minimum-isolated-red / FullyQualifiedName~TimeoutMinimumMatchesFrozenContract\|FullyQualifiedName~SchemaUsesCompleteGeneratedClosure | 3项，2红1绿、exit2 | minimum实际1；99ms错误进入真实目录404；100ms合法控制404 |
| review-1-full-green | 49项，48绿1红、exit2 | 新增真实审计中外部取消，捕获DbException包装误转503 |
| review-1-full-fixed | 49/49、0跳过、exit0 | 全量旧24项、新HTTP10、审查服务8、真实源7，所有回归通过 |

预算下界调试尝试全部保留：review-1-minimum-red因误用过滤语法为零测试/exit8，不能计产品验证；review-1-minimum-real-red的两个例因冷启动超100ms得到503；review-1-minimum-warm-red发现计划遗漏Depth/MaxRows使100ms控制误报422。最终有效红例补齐其他合法参数并先真实完成EF/连接冷启动，测试只比较99拒绝和100合法进入目录；未以替身让100ms发布查询假成功。

新增真实源测试含合法四源、词汇缺席三源、槽位交换、快照错hash、bundle错hash、对象键错绑、真实S3 hash一致但非法UTF8。负面清单只传入源恢复组件，不写PG或激活不合法发布。真实HTTP夹具复用生产端点、Kestrel、原生Antiforgery和真实PG审计/Gateway，固定服务器principal明确不是OIDC登录验证。真实PG `pg_sleep(3)`审计在TimeoutMs1000下：成功路径1024ms、错误路径1011ms均503，详见review-1-full-fixed.json timings；成功审计取消后无allowed行，调用者中断仍OCE。

原CancellationAndBudgetReachDependency测试的内部deadline断言由UNAVAILABLE改为503，是Master明确批准的失败关闭边界：原deadline耗尽时无法提交成功的失败审计，不能返回假装已完成审计的业务结果；仍断言实际依赖收到取消，并保留外部取消测试。其余既有测试断言未弱化。

工程检查回执见review-1-verification.json；源码验证17项SHA256在格式化后重算全部相符。测试使用本轮随机新PG/Jena/RustFS、随机回环端口及内存临时认证，未读历史private runtime或保留卷，所有本轮容器已清理。新增锁只包含Api引用所需的既有批准传递闭包。

NOT_RUN / NOT_VERIFIED：完整正式Host组合的runtime OpenAPI安全声明/单一Schema比对由Master最终固定Head执行，本树仍旧共享Host依赖（PlatformOpenApi旧转换仅platform路径），未另造QRY转换器。原生真实HTTP已通过，但真实OIDC、REST/MCP/MAF/SSE浏览器全链、同Head Linux CI、Windows/Intel、真正进程重启仍不宣称通过。SEM独立50/50同批验证证据由SEM/Master提供，本QRY回执只申报自己实际49项。shared Guard旧版CS1573警告保留准确边界，Master已有f0a54ed修复，本树未越权改共享文件。当前状态为READY_FOR_LIMITED_REREVIEW / PARTIAL，交同一独立Reviewer限定复审本轮修复及关联回归。

本轮工程命令实际全部exit0：三范围format及verify-no-changes、QueryTests Release、Api Release、pwsh SelfTest、git diff --check b1d2a51feea5b27bf91e2470fe87f3aea697fcb3。完成固定源码提交后追加精确SHA回执。

固定业务源码及首轮证据提交：`b8dc13cf7956ce4abbfa0c072ce81a91c202b45d`，已push。其完整`git diff --check b1d2a51feea5b27bf91e2470fe87f3aea697fcb3 HEAD`真实exit0。后续仅按Master批准调整owned runner跨Linux权限：随机0700父目录下新建只含公开Jena config/logging的0755 fixture子目录，两个文件显式0644并真实stat校验，容器只读bind该子目录，不用root、不扩大凭证目录。`python3 scripts/acceptance/query-plan.py --label review-1-portable-final`实际49/49、0skip、exit0；JSON首项记录0755/0644/0644，17个最终源码散列重开全部相符。本次真实审计耗时1011ms和1006ms仍均503；当前Mac实跑不能代替Linux CI结论。Release QueryTests构建1项已知共享Guard CS1573，Api增量构建0警告，未将增量结果冒称全树零警告。

最后权限与文档改动后的`pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`实际exit0，回执review-1-final-self-test.json；工程SelfTest中的合成checker/ZIP负例不计入49项真实产品测试。
