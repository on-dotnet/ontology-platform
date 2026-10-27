# G3-M2 公共合同

状态：FROZEN。独立contract_review只读Spec/Quality审查PASS；详见本任务master/contract-review.md。授权：G3-M2-001 附件 V1，Base=f0712e9174d1bff82b5f6959e0a61e723585be88。Master 单写合同/API/生成物/CI/公共验收；仅 M2，无新增直接依赖。

## 精确编辑及事务

复用 POST /api/v1/ontology-drafts/{id}/edits 与 EditDraftRequest，不新增 SourceBundle、身份或语义服务。JSON必需 edit/command；edit 必需 subjectIri、predicateIri、oldObject、newObject。oldObject=null 为新增，newObject=null 为删除，二者非null为替换，二者null拒绝。RdfTerm 必需 kind/value/datatype/language；只允许命名IRI或literal。提交旧对象来自相同revision的服务投影，不能以标签匹配、批量字符串替换或从画布重建RDF。

CommandContext原字段/幂等保持：commandId、idempotencyKey、reason、expectedRevision；If-Match必须单个强ETag且等于expectedRevision。ontology.edit、服务器actor、CSRF和完整scope先于业务；事务内锁头CAS。成功响应为完整OntologyDraft新revision；no-op字节/hash不变但仍沿既有保存规则增加revision。旧源修订完整保留。仅ontology源允许结构命令，其他三源逐字/hash不变。IRI、prefix、BASE可用原四源textarea保存；实际结构编辑的新ontology格式变化必须展示Diff。

## 支持子集与保护

支持命名Class/ObjectProperty/DatatypeProperty/NamedIndividual、简单type、subClassOf、命名domain/range、label/comment/lang及已声明简单属性断言。新增受控命名equivalentClass/disjointWith两端须显式owl:Class；inverseOf两端须显式owl:ObjectProperty。IRI必须绝对合法，不能带literal元数据。literal不得语言与任意datatype冲突；RIOT规范rdf:langString+language可接受并精确保留，客户端新对象发送language时datatype=null或规范rdf:langString；oldObject必须原样复制服务投影的language/datatype，不能清除rdf:langString使精确删除失配。对编辑前后完整ontology图检查命名公理两端类型，包括删除类/属性声明而遗留公理的情形。未知字符串/数字kind在JSON绑定阶段400；已知blank、IRI附带literal元数据、空变更、未声明/类型不符公理以422失败关闭，不更改源或revision。

完整原始图先真实RIOT解析；含blank、restriction、cardinality、chain、imports、身份公理或未知语义时继续整图structural_edit_unsupported；不尝试从简化图清洗。源码保存/原文导出仍可使用，发布由assessment决定。不得联网imports、用户SPARQL/JS/自定义SHACL target、推理或自动sameAs。domain/range不是必填约束，多domain不是任选；allValuesFrom不保证关系存在，Functional不是数据库唯一键。

## Profile与历史

保留原SemanticProfile v1全部字段顺序、Reason和hash（golden SHA-256=54e4db0fac2c7e4f89802678f3269b8a460190775b53b4fb74955f8cbadd8b86），新增LegacyM1()原样构造。Current()为同ProfileId ontology-platform/g3-m1、Version=2；09–11 Edit=BASIC，01仍SOURCE，其余发布边界不变。Matches只接受注册v1/v2的精确version/hash；历史V2 Release按对应注册profile回验，不升级或改写原Manifest/Binding。仅编辑能力变化，v1/v2 asserted-only发布语义相同，PublicationSupport可共享相同白名单；V1继续LegacySupport。新assessment绑定当前v2；旧draft assessment不能新发布，旧正式Release仍可经现有授权/异人审批/CAS回滚。需测试历史v1/hash、V1/V2 manifest、旧Run/SSE。

## 状态、诊断与错误

UI分别展示可保存（权限、有效源、dirty/请求结果）、可结构编辑（服务projection+profile+权限）、可发布（当前服务assessment绑定/未过期/eligible）、可推理（OWL_REASONING=NOT_RUN）。客户端不能伪造publishEligible。保存后清除旧assessment；重新评估使用服务器完整revision/four hashes。

复用AssessmentDiagnostic：sourceId=ontology/shapes/vocabulary/data/bundle、对应sourceHash、diagnostic.focusNode/path及可选wrapper.sourceShape；可靠唯一绑定才定位源，未知行列显示UNKNOWN不猜测。点击诊断选择focus节点/对应源码；sourceHash与当前不一致时显示过期，不跳到伪位置。命名shape仅在当前shapes hash匹配且实际节点存在时定位；blank shape标识不是原始源码稳定位置，行列仍UNKNOWN。SHACL和SUPPORT独立显示，conforms不是OWL一致性。

错误复用：400 malformed/unknown/missing JSON、invalid_revision；401未登录；403角色/CSRF/scope；404草稿；409 revision_conflict/draft_revision_conflict/edit_source_conflict/assessment_binding_conflict；422 rdf_edit_invalid/predicate_edit_unsupported/structural_edit_unsupported/assessment_not_eligible；428 revision_required；413/429/503沿原预算。新增受控类型错误统一rdf_edit_invalid。不得放宽预算来让测试PASS。

## 唯一生成来源与所有权

Master：docs/contracts/g2-models.json、scripts/generate-g2-contracts.py、Contracts/**、生成OpenAPI/TS、Host/**、CI、迁移、AppHost、Design Tokens、scripts公共验收/资源、任务与master证据。本轮仅AssessmentDiagnostic增可选RdfTerm? SourceShape，required=false/omitNull=true；旧缺席诊断字节/hash保持，Manifest/Run/SSE不变。SEM WrapDiagnostic直接保留issue.SourceShape。生成链g2-models→生成C#/schema→真实宿主OpenAPI→generate-types.mjs；只运行--check验证TS，不假定Python生成器有--check。

SEM唯一写：Ontology模块（含SemanticProfile注册策略）、backend/tests/OntologyPlatform.SemanticTests/**、必要PublishingTests/**、samples/g3-m2/**、本任务SEM证据。SemanticProfile为已冻结共享策略，SEM为本轮唯一实现写者，变更先报Master。只读Contracts/Host/脚本/Web，禁止迁移/DTO/锁变更。

WEB唯一写：apps/web/src/features/ontology/**、本任务WEB证据；复用g2-client，无需修改共享client/生成TS/Tokens/Shell。只读SEM/Contracts/公共脚本。三栏左资产/类/属性树，中间图/源码，右属性/诊断/评估；保留深浅主题、窄屏tab后备和键盘节点选择。手写TSX多行且单行默认≤200。

Master新增契约测试：G2ContractTests/G3M2EditContractTests.cs与SecurityTests/G3M2EndpointTests.cs。双方不越界，不还原他人变更；合同修订需Master记录并再审。

## 测试与集成点

先畸形/未知/缺失JSON、If-Match、权限、revision、未支持语义/生成漂移廉价测试，再独立Reviewer只读通过。SEM先提交最小命名编辑+PG/Jena/assessment纵向切片，独立Review/同HeadCI后Master尽早main集成（点1）；WEB真实UI→API编辑/保存/重读后同样集成（点2）。每点记录Head及实际CI。最终发布/查询/回滚、旧兼容、主题键盘窄屏完整门禁。canonical Fuseki只经现有内容寻址入口并复核cache hit；V3早期fixture及稳定候选非最终包，再唯一最终包/独立重开。资源精确归属只清本任务，旧树/8保护卷等实际before对象全部保留，不全局prune。

## Canonical 下载修订（M2 环境关口，FROZEN / 独立限定审查PASS）

9bac/SEM/point1三个实际CI检查点在canonical RUN阶段超时600s，业务未启动，旧失败保留。Master新增owned_paths=infra/development/fuseki/Dockerfile、.dockerignore、fetch-fuseki.sh、scripts/tests/CanonicalFuseki.Tests.py、g2-integration与CI；其余Owner不写这些路径。版本6.2.0、SHA512、基础镜像摘要、许可证不变，无新直接依赖。官网https://jena.apache.org/download/与官方.sha512核对匹配原锁。唯一Dockerfile调用有界下载helper：固定dlcdn primary/archive fallback，每次connect15/max180/无retry/HTTPS/最多3重定向，下载成功后的坏SHA立即失败，不fallback；校验在tar前。canonical外层600不变，context hash自然变化，旧镜像不重标。CI冷构建前置于应用restore，集成处必须cache hit并输出实际image/context/reused receipt。真实Linux冷构建/同HeadCI仍待验证，不把本机HEAD/Range或shell fixture当Linux成功。

后置实际核验：3d57255同Head CI40529681102与dfce2df同Head CI40537316476双job均success；实际Linux冷构建与后续cache hit已验，旧600s失败仍保留。完整Mac真实模块121/113/56/49/33均零失败/跳过；浏览器显式图/源码切换的旧验收假设已修，7runtime gates通过，未改变产品合同或超时预算。
