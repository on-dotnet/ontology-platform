# G3-M5 只读高阶表达式合同

状态：FROZEN（独立合同审查及修正见本任务证据）。Base=e5b7e99715ee7ebfe419717f7cacf0c02dfcb78a。Master 独占公共 DTO/生成物/接口/路由/DI/验收入口；SEM/WEB 独立托管树依本合同实现。无新依赖/迁移/reasoner；Monaco BLOCKED，imports 不联网。

## 读取与持久兼容

新增 IG3ExpressionService.ReadExpressionsAsync(actor, VersionRef, cancellationToken)；OntologyService partial 先校验 VersionRef，再复用 ReadVersionAsync 权威四源恢复和完整 scope 授权。草稿必须精确 revision；release 必须 revision=null。新 GET /api/v1/ontology-drafts/{id}/expressions?revision=<long> 和 GET /api/v1/releases/{id}/expressions，均 G2EndpointGuard.ReadAsync + semantic.read，无写操作/新写审计 action。404/403/422/503 既有 fail closed 边界。

IG3ExpressionRuntime.ProjectExpressionsAsync(SourceBundle, CancellationToken) 返回 OwlExpressionSource[]。JenaSemanticRuntime partial 实现，复用 Execute / ParseSourcesAsync(checkShapes:false) / RIOT；只读解析不执行SHACL安全策略，正式验证仍原样失败关闭；四源分别投影，空缺 vocabulary 不伪造源。成功读取不写 PG 源、投影、revision、assessment、新业务写审计或正式图；安全拒绝仍保留 G2EndpointGuard 既有拒绝审计。既有 v1–v4 profile/hash/持久 ProjectionJson/Release/Run 协议保持原字节；新 snapshot 的 projectionVersion=1 与现行支持策略 v4 分开。未知 profile 前端仍 UNKNOWN；准确登记 v4/23 项。

## DTO（g2-models.json 为唯一生成来源）

派WEB前由现有generate-types从g2-schemas规范Schema补充生成缺席的OwlExpression类型；引用已有RdfTerm/VersionRef等生成类型。此规范补充有显式注释，不能当真实路由证据。真实宿主OpenAPI导出后优先使用运行时Schema，不重复类型。

OwlExpressionSnapshot：projectionVersion string、version VersionRef、scope ResourceScope、hashes SourceHashes、profileId/profileVersion/profileHash string、sources OwlExpressionSource[]。

OwlExpressionSource：sourceId/sourceHash/status string、sourcePreserved/readOnlyStructured/editable/inferred bool、publishEligible string、roots RdfTerm[]、nodes OwlExpressionNode[]、diagnostics OwlExpressionDiagnostic[]。

status=COMPLETE|INDETERMINATE；sourcePreserved=true 仅源经权威hash核验与RIOT成功；readOnlyStructured=true 仅有界遍历完整；editable=false 表示此视图无结构写能力，不否定普通编辑器已有能力；inferred=false；publishEligible=BLOCKED（现行profile拒绝复杂结构）或 NOT_ASSESSED（其余，读取不能代替assessment/impact/审批）。不从parse/tree成功推 ELIGIBLE。

OwlExpressionNode：term RdfTerm、kind string、properties OwlExpressionProperty[]、orderedItems RdfTerm[]。OwlExpressionProperty：predicateIri string、values RdfTerm[]。OwlExpressionDiagnostic：code/message string、focusNode RdfTerm?、predicateIri string?、line/column int?。行列未知必须 null；sourceId/hash 在父 source 绑定，不伪造精确字符范围。

新快照内所有 blank term 的 Value 统一为带 `_:` 的本源标识（RIOT适配历史codec对subject/object前缀不一致只在新投影修正；不得修改旧codec/序列化/profile）。覆盖subject/object前缀异形、共享节点、跨源同名隔离正反例。flat nodes 为每个实际 RDF 主体一个记录（同源 RdfTerm kind/value 精确唯一）；roots 是需展示的命名公理主体和匿名表达式根。属性值是准确 RDF term；空白节点以 term 引用同源 node，不递归复制共享节点。orderedItems 严格按 rdf:first/rest 顺序，不能排序替代链顺序；properties 的集合值可确定排序。来源坐标为 sourceId/hash + RDF主体/谓词，blank ID 只在本source/version/hash内有效，不能跨版本当稳定标识。

kind 使用 restriction/intersection/union/complement/list/axiom/term 等固定展示标签；保留所有标准谓词原 IRI 和 typed/language literal 词法。准确展示 some/all/hasValue/普通及qualified cardinality/onClass/onDataRange/propertyChain/imports/属性特征/sameAs/differentFrom/hasKey。all不蕴含存在，Functional非唯一键，导航非推理。

## 有界诊断与失败关闭

继承每bundle 5000 triples、源字节/既有5秒总 Execute 限制；新增表达式嵌套深度32（不把rdf:rest链长度当表达式深度）、结构nodes512、列表items512；即使roots为空，也遍历检查纯环等独立分量，检查 CancellationToken。超限 status=INDETERMINATE、readOnlyStructured=false，保留source，诊断 expression_budget_exceeded；绝不默默截断后 COMPLETE。循环 expression_cycle、断裂/分叉 list_invalid、未知OWL词汇 owl_term_unknown、未锁imports imports_not_loaded、非法cardinality cardinality_invalid（xsd:nonNegativeInteger准确词法含非负+前导零，拒绝语言/错误datatype/负数/小数）、共享blank引用可明示 shared_blank_reference。损坏list、循环、不合法cardinality、未知OWL结构均 status=INDETERMINATE/readOnlyStructured=false；未锁imports为明确引用节点且诊断，不加载闭包，本地准确引用结构可COMPLETE。shared_blank_reference本身不是损坏。未知/损坏不修复源、不放开结构编辑或复杂发布。

RDF List校验恰好1 first/1 rest、rest blank或rdf:nil；循环必须诊断。列表成员顺序保留；非列表共享blank用引用，不能误判丢失或无限遍历。反例包括所有四源复杂结构、越权/跨厂、超预算、取消、unknown/imports、不合法qualified restriction及词法。合法复杂源仍保存导出no-op字节一致和图同构。

## 所有权与最短验收

SEM：新增 JenaExpressions.cs、OwlExpressionProjection.cs、OntologyExpressions.cs；新增 G3M5ExpressionTests.cs/G3M5ServiceTests.cs；samples/g3/m5/**。不改公共接口/DI/DTO/路由/profile/既有Jena文件；需要额外路径先报告。WEB：新增 expression-tree.tsx/expression-model.ts 与对应测试；workspace.tsx/support-profile.tsx及对应局部测试/样式（具体卡冻结）；不改生成物/tokens。Master 连接服务组合/路由并扩验收入口和M5精准资源前缀。

先短实际编译/合同/DI及audit消费者检查，再真实 RIOT+PG B1；B2普通命名公理审批发布→正式查询→历史Run/Impact读取→回滚；B3稳定产品输入全阶段兼容/UI目标E2E。正反自动测试不得只检查文字存在。Schema/截图/VerifyOnly在正式构包前试验，原失败保留。相同输入昂贵失败先短复现，禁止盲二跑。
