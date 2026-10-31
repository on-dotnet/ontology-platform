# G3 二十项能力与 M5 只读支持矩阵（最终矩阵）

源码依据：最终已审源码 `80adf4756f3c6da9a5e1be4a0e348ebdd72e2f69`（后续仅任务/证据/研发说明增量）。文件名保留原draft恢复入口，内容已更新为最终矩阵。真实结果和输入复用见[最终验收矩阵](../master/final/test-matrix.md)及[输入绑定](../master/final/input-binding.json)。未启动G4/G5。

## 读法与当前验证事实

V=可视化/导航；S=专家源码；R=有界结构只读；B=阻断对应结构改写或发布；L=后续能力。SP=source-preserved；RO=read-only-structured。表中 `T` 仅指合法、预算内且经权威hash/真实RIOT解析的源；不是任意输入均成功。损坏列表/匿名环/错误基数/未知OWL/预算耗尽为 `INDETERMINATE`，RO=false；语法错误可能直接拒绝，不能声称已保真入库。

所有行的 `editable` 均分“新树”与“既有编辑器”：新树固定false；普通BASIC编辑与专家源码保存仍沿已有权限/CAS/审计，不因新增只读树被撤销。所有行 `inferred=false`，OWL_REASONING=NOT_RUN，无reasoner、无imports联网加载。RO完整也不证明OWL逻辑一致性，SHACL Core不是OWL一致性证明。

Master本轮已实际取得：独立RIOT新高阶读取6/0失败/0跳过，真实PG+RIOT的M5过滤全57/0/0；原始记录为 `docs/evidence/G3-M5-001/master/b1-riot/b1-riot.json` 和 `master/b1-pg/b1-pg.json`（均exit0）。其中57包括廉价守卫/投影和真实服务用例，不能称57项全部独立外部服务用例。Master另报告Web268/0、DI2/0及工程SelfTest通过；本作者未重新执行这些命令。最终M1–M4真实600检查与最新M5的38项专属检查组成638项PASS；最新真实UI50/0、普通发布/Run/SSE/MCP/回滚均有该原链实际证据。原整链失败未覆盖，不宣称一次七门禁命令exit0。其余六门禁分别通过，细目见最终矩阵。M1–M4既有交付事实按各原handoff保留，本次是否复验另列。

## 二十项精确边界

“发布”列是新只读DTO的publishEligible及现行profile边界：`N`=NOT_ASSESSED，普通子集的profile为SUPPORTED，但仍须有效assessment/impact/异人审批及全部发布门禁；`B`=BLOCKED，不能用审批覆盖。同图出现任何不安全复杂结构时整图失败关闭，不能静默删复杂三元组后仅发布普通部分。源槽位shapes读取本身不执行ShapePolicy，其资格仍由独立assessment决定。

语料根目录 `samples/g3-m1/` 的01–20文件是原矩阵正式语料；M5综合语料为 `samples/g3/m5/advanced.owl.ttl`。下列测试缩写对应下一节的精确现有符号，未添加不存在的测试名。

|项/标准表达|V/S/R/B/L|SP|RO|editable（新树；既有）|发布|inferred|正负语料与实际入口|
|---|---|---|---|---|---|---|---|
|01 IRI、prefix、BASE|V/S/R；IRI重命名B|T|T|false；SOURCE，不提供IRI批量改名|N|false|`01-iri.ttl`；正相对IRI/固定BASE，负非法IRI/非法源；T20、IRI、BOUND|
|02 `owl:Class`|V/S/R|T|T|false；BASIC命名类|N|false|`02-class.ttl`；正命名类声明，负未授权范围/错误修订不入库；T20、BASIC、AUTH|
|03 `rdfs:subClassOf`|V/S/R；匿名结构写B|T|T|false；BASIC命名子类，复杂源SOURCE|命名N；复杂B|false|`03-subclass.ttl`与M5匿名restriction；命名类环不直接等价逻辑不一致，匿名环明确诊断；T20、CYCLE|
|04 `owl:ObjectProperty`|V/S/R|T|T|false；BASIC显式属性/IRI事实|N|false|`04-object-property.ttl`；正声明/IRI对象，负literal类型或越权；T20、BASIC、AUTH|
|05 `owl:DatatypeProperty`|V/S/R|T|T|false；BASIC声明/literal事实|N|false|`05-datatype-property.ttl`；正typed lexical原样保存，负元数据冲突/发布回读词法改写；T20、META、LEX|
|06 `rdfs:domain/range`|命名V/S/R；复杂S/R/B|T|T|false；BASIC命名IRI，复杂结构写B|命名N；复杂B|false|`06-domain-range.ttl`多domain不是任选/必填；M5匿名交并补只读，坏列表/循环为RO=false；T20、LIST、CYCLE|
|07 annotation/lang|V/S/R；普通自定义S|T|T|false；BASIC受控注释，声明自定义注释SOURCE|受控N；未声明B|false|`07-annotation.ttl`中文/非BMP/lang；负未声明自定义事实、language/datatype冲突；T20、ANNOT、META|
|08 named individual/简单事实|V/S/R|T|T|false；BASIC命名个体/受控事实|N|false|`08-individual.ttl`；正Synthetic命名个体，负跨组织/缺一厂区/无角色；T20、BASIC、AUTH|
|09 `owl:equivalentClass`|命名V/S/R；复杂S/R/B|T|T|false；BASIC显式Class对，复杂SOURCE|命名N；复杂B|false|`09-equivalent.ttl`与M5匿名restriction；正类型匹配命名对，负声明缺失/类型错误/复杂覆盖；T20、NAMED、HISTORY|
|10 `owl:disjointWith`|命名V/S/R；复杂S/R/B|T|T|false；BASIC显式Class对|命名N；复杂B|false|`10-disjoint.ttl`；正原始公理声明，负两端类型不匹配；不提供完整一致性证明；T20、NAMED|
|11 `owl:inverseOf`|命名V/S/R；复杂S/R/B|T|T|false；BASIC显式ObjectProperty对|命名N；复杂B|false|`11-inverse.ttl`；正精确逆属性声明，负Class/缺声明；导航不执行逆属性推理；T20、NAMED|
|12 属性特征|S/R/B；推理L|T|T|false；SOURCE，结构写B|B|false|`12-features.ttl`及M5七种OWL属性特征（ObjectProperty声明另计）；正完整保留/展示，同时作为发布阻断负例；Functional不是数据库唯一键；T20、ADV|
|13 some/all restriction|S/R/B；推理L|T|T|false；SOURCE，结构写B|B|false|`13-some-all.ttl`、M5 some/all；正合法属性/类目标，负literal或悬空blank、缺属性/多构造；all不保证存在；QUANT、MALFORMED、ADV|
|14 `owl:hasValue`|S/R/B；推理L|T|T|false；SOURCE，结构写B|B|false|`14-has-value.ttl`、M5 `"001"^^xsd:integer`；正IRI/typed/lang项保留，负匿名个体暂不确认完整支持；VALUE、ADV|
|15 普通/qualified cardinality|S/R/B；推理L|T|合法typed为T；原15裸整数为false/INDETERMINATE|false；SOURCE，结构写B|B|false|原`15-cardinality.ttl`裸1为xsd:integer，保留但cardinality_invalid；合法正例来自M5显式xsd:nonNegativeInteger的六种基数/两种限定；正`+0002`/`-0`/超机器整数保词法，负负数/小数/错误type/lang/缺或双qualifier；CARD、QUAL、ADV|
|16 intersection/union/complement|S/R/B；推理L|T|T|false；SOURCE，结构写B|B|false|`16-boolean.ttl`及M5 And/Or/Not；正嵌套/共享节点/长列表，负断链/分叉/匿名环/预算；LIST、CYCLE、BUDGET、ADV|
|17 `owl:propertyChainAxiom`|S/R/B；执行L|T|T|false；SOURCE，结构写B|B|false|`17-chain.ttl`及M5 `(ex:p ex:q)`；正严格原链顺序与合法33项列表，负损坏/环；不把路径导航当推理；LIST、ADV|
|18 `owl:imports`|S/R/B；加载L|T|本地引用T；闭包未加载|false；SOURCE，结构写B|B|false|`18-imports.ttl`及M5 `https://example.invalid/never-load`；正保留IRI并`imports_not_loaded`，负发布阻断；未知OWL词汇另为RO=false；IMPORT、ADV|
|19 sameAs/differentFrom/hasKey|S/R/B；推理L|T|T|false；SOURCE，OWL结构写B|B|false|`19-identity.ttl`及M5 sameAs/differentFrom/有序hasKey；正准确声明与列表保留，负复杂发布；不按同号/标签自动合并。M4平台显式身份治理独立于OWL身份推理；T20、ADV、TIME|
|20 OWL-Time受控命名模板|V/S/R；非模板S/R/B|T|T|false；BASIC当前v4受控模板|v4模板N；不支持B|false|`20-time.ttl`及M4内联valid/adjacent；负no-zone/reverse/missing-point/unknown/unsupported；旧v3仍拒绝同语料，不伪造未知时间；TIME、TIMELEGACY|

## 精确测试符号与恢复入口

以下类均位于 `backend/tests/OntologyPlatform.SemanticTests/`，同类名 `.cs` 可从上述候选Git对象恢复。`ADV` 与 `MALFORMED` 已包含在实际6个RIOT过滤结果，M5其余符号包含在实际57个过滤结果；T20、IRI等历史入口不在57中独立计数，已由本轮完整Semantic296覆盖；新增真实RIOT负例6另计，合计302个不同测试用例，无失败/跳过。原20文件RO列由逐文件源码核对和综合真实样例验证，不宣称20份均单独调用新投影端点实测。

|缩写|精确现有类/方法|
|---|---|
|T20|`G3BoundaryTests.TwentyCorpusRowsUseAssertedOnlySupportAndShapesBlankException`（真实20文件逐项支持/拒绝）|
|IRI / BOUND|`RoundtripTests.RelativeIriAndExactEditPreserveRemainingGraph`；`G3BoundaryTests.ComparisonPreservesAbsentBytesAndRejectsInvalidOrOversizedBundles`|
|BASIC / AUTH|`DraftRevisionTests.M2BasicModelingSequencePersistsEachRevisionAndKeepsOtherSourcesExact`；`G3M5ServiceTests.RealScopeAuthorizationPrecedesProjectionRequests`|
|NAMED|`G3M2EditingTests.NamedAxiomEditPreservesOtherSourcesAndRequiresBothDeclarations`，DataRow为equivalentClass/Class、disjointWith/Class、inverseOf/ObjectProperty|
|META / LEX|`G3M2EditingTests.InvalidMetadataFailsBeforeAnyNoOpOrSerialization`；`RoundtripTests.PublishedGraphsAreIsolatedAndLexicalMismatchIsRejected`|
|ANNOT|`G3BoundaryTests.UndeclaredCustomFactsRequireAnExplicitPropertyOrAnnotation`；`G3M2EditingTests.RiotLanguageTermCanBeCopiedAndDeletedPrecisely`|
|ADV|`G3M5ExpressionTests.RealRiotReadsAdvancedFixtureWithoutLosingSourceOrEnablingPublish`、`RealRiotSeparatesFourSourceBlankScopesAndPreservesLiteralMetadata`|
|MALFORMED|`G3M5ExpressionTests.RealRiotMalformedOwlHasExplicitProjectionDiagnostics`，broken/cycle/cardinality/unknown四个真实RIOT场景|
|QUANT / VALUE|`G3M5ExpressionTests.ProjectionRestrictionQuantifierHasLegalTarget`；`ProjectionRestrictionHasValuePreservesSupportedValueKinds`；`ProjectionRestrictionRejectsAmbiguousOrMalformedShape`|
|CARD / QUAL|`G3M5ExpressionTests.ProjectionCardinalityPreservesLexicalAndDiagnosesInvalid`、`ProjectionCardinalityRejectsWrongTypeAndLanguage`；`ProjectionQualifiedCardinalityRequiresUniqueQualifier`|
|LIST|`G3M5ExpressionTests.ProjectionListOrderAndLongListDoNotUseExpressionDepth`、`ProjectionMalformedListsNeverBecomeComplete`、`ProjectionSharedListTailDoesNotBecomeCycle`|
|CYCLE / BUDGET|`G3M5ExpressionTests.ProjectionAnonymousCycleAndNamedSubclassCycleAreDistinct`；`ProjectionNodeAndDepthBudgetFailClosed`、`ProjectionCancellationPropagates`|
|IMPORT|`G3M5ExpressionTests.ProjectionUnknownTermsAndImportsHaveSeparateSupport`|
|HISTORY|`G3M5ServiceTests.RealHistoricalSnapshotAndReimportRetainExactSourceAndBlankGraph`、`RealReadOnlySnapshotPreservesRawBytesAndDoesNotWrite`、`RealTamperedRevisionHashCannotProducePreservedSnapshot`|
|TIME / TIMELEGACY|`G3M4IdentityTimeTests.ControlledTemplatesAndIdentityRelations`；`LegacyVersionThreeStillRejectsTheSameControlledTimeCorpus`、`CurrentProfileRetainsExactHistoricalFactories`|

Master已运行的准确子命令（由b1原始records读取；调用前必须使用本轮临时服务环境，不能读取历史runtime/凭证）：

```text
dotnet test --project backend/tests/OntologyPlatform.SemanticTests --no-restore -- --filter FullyQualifiedName~G3M5ExpressionTests.Real
dotnet test --project backend/tests/OntologyPlatform.SemanticTests --no-restore -- --filter FullyQualifiedName~G3M5
```

可再生宿主入口是 `python3 scripts/acceptance/semantic-roundtrip.py --postgres --filter FullyQualifiedName~G3M5 --label <受控标签>`，由Master先设置本任务 `PLATFORM_TASK_ID`、`PLATFORM_EVIDENCE_DIR` 及 canonical 校验镜像，经过宿主/路径/参数/审计/DI/阶段/Evidence前置检查再启动。此文档任务没有执行该入口。

当前profile仍v4/23项（01–20加M3两项与M4平台身份一项），不升级v5，不修改旧profile/hash或Release/Run序列化。新快照projectionVersion=1只表达有界只读投影。最终输入绑定、真实浏览器/普通资产发布查询/Impact/旧Run/SSE/MCP/回滚矩阵与独立Review已另附master/final；唯一V3与重开结果取封包后置回执。
