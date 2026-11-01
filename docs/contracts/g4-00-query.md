状态：PROPOSED_G4_CONTRACT / NOT_IMPLEMENTED。TaskId：G4-00-CONTRACT-001；Master 单写。基线 d1a61daffe844475b07705797e3ad325cc3f2945。

本文件为 V1.1 输入的仓库合同入口。下列引用章节按原字节归档，属于本合同的详细定义；当前裁决优先于输入中的建议，G2/G3 冻结合同优先于 G4。输入包历史“未授权”描述保留，2026-11-01 用户明确批准本任务仅合同归档、验证、独立 Review；不是产品实施许可。

## G2 兼容与 G4 新边界

纳入[查询 API §8–9](../evidence/G4-00-CONTRACT-001/input-v1.1/docs/05-DATA-API-CONTRACT.md)及[安全与查询完整合同](../evidence/G4-00-CONTRACT-001/input-v1.1/docs/06-SECURITY-AND-QUERY.md)。既有 POST /api/v1/semantic/queries 仍 SemanticQueryPlan→SemanticQueryResult；拟议 POST /api/v1/data/semantic-queries 为 SemanticQuery→G4QueryResultV1。复用唯一 Gateway/Guard/Registry，不新增第二查询引擎。

G2 result 的 status/data/candidates/evidence/snapshot/subSources/validTime/observedAtUtc/traceId/limited/diagnostics 全部保留；G4 加 schemaVersion=g4.query-result.v1，嵌套证据/快照/数据/子源均是新版本类型。同名字段不构成 JSON 或继承兼容。不得补假 graphIri/dataHash/sourceObjectKey 通过 G2 严格解码。没有逐字段无损证明即拒绝旧类型转换；本轮无 DTO/生成物修改。

## 确定性状态顺序

先身份与请求授权：未登录401，无权403/UNAUTHORIZED并且无数据/候选/敏感来源。其后仅在获准候选集合消歧，两个以上不同IRI返回AMBIGUOUS及可回链证据，不自动取第一条。无可信结果且必需源不可用→UNAVAILABLE；有可信子结果但缺必需源/受限/截断→PARTIAL。必需源均成功，未截断且有行→FOUND；全部成功且明确无行→EMPTY。取消/运行中属于执行状态，不增加第七业务态。可选子源的必要性在 capability 固定版本中确定，不能运行后改为可选以隐藏故障。

行/候选 evidenceIds 必须在当前已授权响应 evidence 中可解引用；Evidence→ReadReceipt→MappingRelease→CatalogSnapshot→Connection 精确版本关联。SourceRecordRef未知为null，precision降级；UNKNOWN不得作为Agent确定事实。读取和历史Run回放均按当前字段/厂区/组织ACL重验，缓存不得成为撤权绕过。

## 执行预算与威胁

G2 depth≤5、maxRows≤100、timeoutMs≤5000、Run≤30s/最多3工具调用维持。连接/发现后台预算独立，不扩大交互查询。registered typed plan仅受控对象/字段/参数/排序/游标/时间窗；禁止客户端SQL/SPARQL/任意URL。Join必须已发布RelationBinding，先估fanout，不能无限拉行后截断。

各源水位独立，TRANSACTION_SNAPSHOT/EVENT_TIME/OBSERVED_AT/OPAQUE/UNKNOWN不得暗示跨源同一快照。缺字段/null/0/空字符串独立；decimal精度、TD ns、Oracle timezone不默默降级。当前 Schema/Mapping 失配必须重验，游标过期409。错误仍原生ProblemDetails+code/traceId/correlationId，G4新增码均PROPOSED；沿既有401/403/404安全优先级，禁止泄露SQL/秘密/内部URL。

六态Schema约束仅局部形状；授权、交叉ID、真实时间/来源与运行完整性由未来服务执行验证。21正例/16Schema负例/3语义负例不是五源产品验收，实际结果记录在任务证据。

## 独立 Review 裁决 RQ-01/02/03

RQ-01：原 V1.1 SemanticQuery.filters 缺 entityIri，两个同厂同外部号候选无法按 UI 选项继续。采用本任务[审查补充设计 Schema](../evidence/G4-00-CONTRACT-001/g4-reviewed-design.schema.json)，仅增 filters.entityIri（绝对http/https/urn IRI，且siteId非空）。无该字段仍按原查询消歧；有该字段必须确定性核验：当前actor可见候选中恰一个同IRI且site相同、externalId如提供也匹配、固定ontology/mapping/catalog版本未漂移；再次读取仍重新鉴权。客户端IRI不授予权限，缓存候选不构成授权。撤权403；版本漂移409；未知/不匹配选择422，均不返回候选或源细节。上游原始文件不改；本补充是PROPOSED设计输入，不生成产品DTO。

RQ-02：原 G4SemanticDatum 仅kind/entityIri/evidenceIds，是来源链设计子集，不能承载属性值、单位、时间序列、关系两端的完整U12。此缺口明确 BLOCKED_FOR_IMPLEMENTATION 于 G4-M4：必须先冻结 entity/relationship/observation/ontology 判别载荷、精确值/单位/时间及来源Schema与正反字节测试，再批准实现；不宣称当前Schema是完整正式查询传输合同。当前G4-00归档的是已审边界与缺口；ChatGPT须裁决M4该项，不能实现时自行增加字段。G4QueryResultV1顶层/证据/六态V1.1修正仍保持。

RQ-03：未登录或完全无资产/scope权限时只返回401/403原生ProblemDetails，不构造/查找任何 G4QueryResultV1.snapshot。业务UNAUTHORIZED仅适用于用户已获准读取该非敏感snapshot且子源数据请求被拒的受控场景；不能泄露无权mapping/catalog/connection ID。原UNAUTHORIZED合成例仅形状样例，不是对越权用户的HTTP响应。若无法证明snapshot本身可见，必须ProblemDetails而非填假ID或泄露ID迎合Schema。

RQ-01校验器补充：首期选定IRI使用已登记IRI的ASCII URI传输表示（不对用户输入静默规范化）；HTTP/HTTPS必须非空authority，URN必须非空namespace和NSS，空白与非法URI拒绝。它是实体标识，不是可回源URL。严格format:uri校验器必须实际注册，否则校验任务失败；不能把未知format默认忽略当通过。非ASCII IRI传输策略需后续明确版本化，不能误解为已支持全部IRI词法。
