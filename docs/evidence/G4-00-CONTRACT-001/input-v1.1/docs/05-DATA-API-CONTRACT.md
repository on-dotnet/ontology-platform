# 05 · G4 领域、数据、版本、API 与状态一致性合同 V1.1

> **PROPOSED**。这些 DTO、API 路径、数据表、权限 action 仍是下一轮合同冻结候选；未在当前 `main` 中实现。G2/G3 现有类型和协议由仓库冻结合同决定，不能用本文件静默覆盖。所有 API 的实际权威类型仍须由后端唯一 OpenAPI 生成链 `g2-models.json → C# → 真实宿主 OpenAPI → TS` 与 G4 Master 单写者裁决，严禁另造并行 TypeScript/JSON 本体事实模型。

## 1. G4 领域对象与所有权

`SourceConnection`：G4 创建的源连接配置实体（**不等于** G3 Ontology asset），含 id、组织/允许厂区、type、displayName、configRevision/etag、类型化 `config:{type,profile}`、**唯一** `secretRef`（可为 null）及服务端受控的 `secretVersion`、allowedObjects、networkPolicyRef、state、created/updated 及审计；不保留可取回 Secret 明文。`credentialRef` 不是第二个连接配置字段，TDengine profile 禁止该字段。

`ConnectionProbe`：只读测试的不可变报告，绑定 connection draft 的 config fingerprint、secret version、actor、目标版本、时间、stageResult、status、Trace，过期不再作为最新有效测试；不因仅有 TCP 通断就标记 CONNECTED。

`SourceCatalogSnapshot`：对一个连接与授权可见对象的 schema 快照，包含 `catalogId/snapshotId/connectionId/configVersion/credentialVersion/Scope/schemaFingerprint/capabilityFingerprint/capturedAt/status/objects[]/diagnostics`，对象类型为 TABLE/VIEW/SUPERTABLE/SUBTABLE/API_OPERATION；字段名/原始类型/nullable/键/标签及厂商专有扩展不丢。

`SourceDataset`：单一已批准读对象（schema.table / owner.table / stable 或 API operation），以 source-owned 的 `objectRef` 标识；严禁把原始用户字符串拼接到 SQL/HTTP。`SourceField` 按原始字段类型、nullability、scopeSensitivity、semanticHints、nativeColumnId、precision/scale/timezone 是否明确与哈希记录；Graph 中 Class/Property 的数据不要回写这张元数据表作为权威。

`MappingDraft`：非正式草稿，绑定 `OntologyReleaseId`、`SourceCatalogSnapshotId`、Connection/Scope、revision、候选实体/属性/关系、IdentitySpec、TemporalSpec、ConversionSpec、Evidence/Issue、AIProposalRef、`mappingHash`、editor/updatedAt。

`MappingAssessment`：相对固定 revision 和被参照版本的可重复校验报告；阶段 `SCHEMA_COMPAT/IDENTITY/TIME_UNIT/SECURITY/QUERY_EXECUTABILITY/RECONCILIATION/IMPACT`，每项 `PASS/FAIL/INDETERMINATE/NOT_RUN`。**人工审查不替代确定性执行校验**。

`MappingProposal`：固定 revision 与哈希、ontology/source versions/impact hash、提交/审核主体、过期、审批决定，批准/拒绝/取消；异人审核。

`MappingRelease`：独立于 G3 OntologyRelease 的不可变关联版本，绑定 `MappingHash/SchemaFingerprint/OntologyReleaseId/ConnectionRevision/AdapterVersion/ReviewReceipt/createdAt`，不可变；只由 PG 的 `activeMappingPointer` CAS 激活，旧版本保留引用；不写 G3 的 `dataTurtle`、Release Manifest 或当前 active ontology pointer。

`SourceReadReceipt`：源数据读取水位、受控 objectRef、queryPlanHash、adapterVersion、rowCount、min/max valid time、readAt、sourceRecordRef（如源侧确实可定位）、source status、traceId、limited。不能凭不存在的源键伪造 SourceRecordRef；API 若无稳定 record key 须降级 evidence precision、显示未知。

`FederatedQueryExecution`：源子计划、预算、取消、当前 actor 权限、指定 Ontology/Mapping versions、可用子结果、六态统一执行语义。**G4 的新 HTTP 边界明确采用 `G4QueryResultV1`，不是 G2 的 `SemanticQueryResult` 同名扩字段**；仍复用现有 `ISemanticGateway`/Capability Guard 的安全和预算执行通路，新旧 REST DTO 分离，禁止复制第二套独立 Gateway。G2 `SemanticQueryResult` 的完整 `EvidenceRef`、`AssetVersionSnapshot` 和 `SemanticSubSource` 有冻结必需字段，不能将无图的真实源读取结果伪装成 G2 synthetic Evidence。详情见本文件§8。

`ConnectionJob`：连接测试、schema扫描及预览/对账的长任务记录；不共用 AgentRun 的私有表，按真实执行模型复用 PG reliable run/lease/fencing/worker，同时区分每个 job 的领域事件。复制整个 Run 框架不允许。

## 2. PostgreSQL schema 与模块边界建议
建议新增 G4 拥有的独立 `connections` schema（正式名字需审查现有模块命名后确定），仅存本模块实体 `connections / credential_bindings / probes / catalog_snapshots / catalog_objects / mapping_drafts / mapping_assessments / mapping_proposals / mapping_releases / active_mapping / source_read_receipts / jobs`；PG 仅作 G4 元数据审计与状态，不静默缓存全部生产原始数据。业务审计继续由 Governance 模块拥有，不建第二套 Audit；正式本体读服务继续由 Ontology/Publishing 拥有；实际业务访问仅经 Semantic Gateway / G4 Adapter 契约。`credential_bindings` 只存唯一 SecretRef/SecretVersion（null 表示经允许的匿名连接），不存 Key 原文；安全程序和部署密钥另 ADR。

**跨模块事务要求**：激活 `MappingRelease` 时，G4 必须在同一 PG 事务内协调 CAS、Governance 审计和 Outbox，否则保持旧 active。不在外部源查询/Schema发现时持有 PG 长锁。事件至少一次、消费者幂等；不能凭事件通知判断映射有效性，查询应从权威 active MappingRelease 固定版本。

## 3. 版本一致性输入与哈希
```text
StableMappingIdentity = (
  organizationId,
  completeSiteScope,
  ontologyReleaseId,
  connectionId,
  connectionRevision,
  sourceCatalogSnapshotId,
  sourceCatalogFingerprint,
  canonicalMappingHash,
  validationHash,
  adapterVersion
)
```

字段均由服务器完成校验；catalog snapshot 不能以文件修改时间替代内容哈希。`CanonicalMappingHash` 应按有 schema 版本的规范序列化（固定字段、排序、Unicode/IRI规范策略、null语义、量纲/时间等）再 SHA256，策略本身必须固定 executor 版本并有字节级反例测试。未知或不可确定的 schema 差异状态 `INDETERMINATE`，不能计算一个空 Hash 冒充相等。变更 Mapping 不能无声地继承旧 approval。Schema 变动影响仅确定相关字段时可限定范围重评估；无法判定影响应阻断高风险查询。

## 4. API 端点（候选路径，实际 OpenAPI 唯一权威待 G4-00 独立审查）
统一前缀 `/api/v1`，`POST/PATCH` 使用服务端已有 BFF/OIDC/CSRF/Origin/Host 防线；所有命令需 `CommandContext`（commandId/idempotencyKey/expectedRevision/reason），修改已有资源必须 `If-Match` 与 body revision 匹配；GET 无副作用。`ActorContext` 只能来自服务器，客户端发来的 org/sites 不扩大授权范围。

| 模块 | 方法与路径 | 权限意图 | 结果与 side effects |
|---|---|---|---|
| 连接 | `GET /connections` | source visibility | 分页/权限过滤/无凭据 |
| 连接凭据 | `POST /connection-secrets` | connection.secret.manage | 专用受保护一次性 Secret 通道；只返回本 Scope 临时 secretRef，不经普通 JSON 连接请求传密钥；不得落入常规日志；具体 OS/Secret Store 实现后续审批 |
| 连接 | `POST /connections` | connection.manage | **唯一 `ConnectionCreateRequest` payload**；创建 `command.expectedRevision=0`，无需 If-Match；只保存关闭态，返回 etag/audit |
| 连接 | `GET /connections/{id}` | connection.read | 脱敏详情/版本/引用 |
| 连接 | `PATCH /connections/{id}` | connection.manage | `CommandContext.expectedRevision>0` + `If-Match` 相等；CAS修改、重测标记、审计；不得使用创建请求格式重放 |
| 连接 | `POST /connections/{id}/rotate-secret` | connection.manage+secret policy | 只返回 secretRef/version；不输出敏感值 |
| 连接 | `POST /connections/tests` | connection.test | 输入受控草稿，返回独立 probeId 或异步 job |
| 连接 | `POST /connections/{id}/test` | connection.test | 重新测试已有配置；只读阶段报告 |
| 连接 | `POST /connections/{id}/enable` | connection.manage | 只有有效探测与授权范围才启用 |
| 连接 | `POST /connections/{id}/disable` | connection.manage | 及时停止新访问并影响依赖评估 |
| Catalog | `POST /connections/{id}/discoveries` | schema.discover | 异步任务、需 scope 与预算 |
| Catalog | `GET /connections/{id}/catalogs` | schema.read | 已固定 snapshot、变化状态 |
| Catalog | `GET /catalog-snapshots/{id}/objects` | schema.read | 授权可见字段与权限裁剪 |
| Catalog | `GET /catalog-snapshots/{id}/diff?from=...` | schema.read | 固定版本精确差异 |
| Mapping | `GET /mappings?connectionId=&status=&cursor=` | mapping.read | 权限裁剪的 MappingListPage，含最新草稿修订和当前 active 版本；无密钥 |
| Mapping | `POST /mappings` | mapping.edit | 创建绑定本体/source snapshot 的 Draft，返回 id/revision/ETag |
| Mapping | `GET /mappings/{id}` | mapping.read | 当前最新 Draft 固定读视图 `MappingDraft`，`ETag` 与 `revision`，权限、Scope 重验 |
| Mapping | `GET /mappings/{id}/revisions/{revision}` | mapping.read | 历史不可变草稿修订的精确内容，不能读成最新版本 |
| Mapping | `GET /mappings/{id}/diff?fromRevision=&toRevision=` | mapping.read | 两个固定修订的有界 MappingRevisionDiffView（增删改/哈希/证据），禁止对实时可变草稿读两次冒充固定比较 |
| Mapping | `GET /mappings/{id}/assessments?revision=` | mapping.read | 绑定修订/本体/Schema 的评估列表，按冻结 assessment id 读取；新修订使旧评估不可直接用于提交 |
| Mapping | `GET /mapping-assessments/{id}` | mapping.read | MappingAssessmentView 固定校验报告与问题定位，依当前权限裁剪 |
| Mapping | `POST /mappings/{id}/suggestions` | mapping.edit | AI/rule 候选；需数据外联批准 |
| Mapping | `PATCH /mappings/{id}` | mapping.edit | CAS更新已授权字段、审计 |
| Mapping | `POST /mappings/{id}/validate` | mapping.edit | 有界校验任务、不可自行激活 |
| Mapping | `POST /mappings/{id}/proposals` | mapping.submit | 固定 revisions/hashes/impact 与提交者，审计 |
| Mapping | `GET /mapping-proposals?status=&cursor=` | mapping.review | 跨用户待审列表；只显示合法 Scope 下的固定 proposal/版本摘要 |
| Mapping | `GET /mapping-proposals/{id}` | mapping.review | MappingProposalView；固定 DraftRevision、connectionVersion、SchemaFingerprint、OntologyRelease、validation/impact hash、提交者、过期与已存在的审核决定 |
| Mapping | `GET /mapping-releases?mappingId=&cursor=` | mapping.read | 历史不可变 MappingRelease 的授权版本目录 |
| Mapping | `GET /mapping-releases/{id}` | mapping.read | MappingReleaseView 固定版本及实时计算的 active 状态；不覆写发布原始内容 |
| Mapping | `GET /mappings/{id}/active` | mapping.read | PG 权威 activeMappingPointer、activationRevision；不存在时明确 EMPTY/404 |
| Mapping | `POST /mapping-proposals/{id}/decisions` | mapping.approve | 非作者审查、明确accept/reject、审计 |
| Mapping | `POST /mapping-proposals/{id}/activate` | mapping.activate | 重新验证再CAS/Outbox，返回MappingReleaseId |
| Mapping | `POST /mapping-proposals/{id}/rollback-proposal` | mapping.submit | 只提出回滚，不直接改active |
| 语义查询 | `POST /data/semantic-queries` | semantic.read | **独立 G4 版本化 HTTP 读模型 `G4QueryResultV1`**（六态+真实源证据）；内部复用现有 Gateway/Guard，不改变 `/api/v1/semantic/queries` 的 G2 DTO |
| 语义查询 | `GET /data/semantic-query-runs/{id}` | semantic.read+Run owner | 读持久运行状态/完成结果；回放需按当前权限和固定版本重授权 |
| 证据 | `GET /data/source-evidence/{id}` | semantic.read/source evidence | 按当前组织/厂区/字段/源访问权限重新授权，G4SourceEvidenceRef 受控回源，不调用 G3 synthetic EvidenceService 冒充真源 |
| 运维 | `GET /connector-jobs/{id}` | authorized owner/operator | 已持久状态、trace、无原始秘密 |
| 运维 | `POST /connector-jobs/{id}/cancel` | appropriate owner | 传播取消、幂等终止 |

**已采用独立版本化 HTTP 读模型，而非未决的条件方案**：现有 G2 `POST /api/v1/semantic/queries` 仍使用冻结 `SemanticQueryPlan`→`SemanticQueryResult`，G4 采用 `POST /api/v1/data/semantic-queries` 的 `SemanticQuery`→`G4QueryResultV1`。`/api/v1` 前缀不属于表中的相对路径。只有后续实测可以 **逐字段无损** 映射完整 G2 `EvidenceRef/AssetVersionSnapshot/SemanticSubSource/SemanticDatum` 时才允许投影到 G2；否则返回 G4 类型，不造假 `graphIri`、`sourceRecordId`、`dataHash` 或 synthetic 标识。请求 `CapabilityId/Version/Depth/MaxRows/TimeoutMs` 必须在共享 Gateway 实际能力表和预算内。

## 5. 参考 JSON 合同（严格传输模型，而非 RDF 权威模型）

### 5.1 连接创建唯一请求（REST body = Schema 中 `ConnectionCreateRequest.payload`）

`contracts/g4-proposed-wire-contract.schema.json` 外层的 `schemaKind/payload` 是**设计测试样例判别包装**，不是 REST 要求多提交一层。`POST /api/v1/connections` 只接收下面的严格 body：

```json
{
  "displayName": "炼钢 QMS 只读数据（合成）",
  "scopeSelection": {"organizationId":"ORG_SYN","siteIds":["SITE_A"]},
  "config": {"type":"POSTGRESQL","profile": {
    "host":"db.example.invalid", "port":5432, "database":"qms",
    "username":"qms_reader", "sslMode":"VerifyFull", "allowedSchemas":["production"]
  }},
  "secretRef": "secret-synthetic-only",
  "command": {"commandId":"cmd-syn-create-01","idempotencyKey":"idem-syn-create-01","expectedRevision":0,"reason":"创建只读连接"}
}
```

这是不包含明文密钥的合成样例。实际 API Key / 密码只允许先经专用 `POST /api/v1/connection-secrets` 安全通道输入，签发**服务器绑定组织、请求者、用途、有效期**的 `secretRef`；创建请求仅引用它，服务端核实归属与有效期。真实密钥不得进入普通请求、日志、审查包或可回读响应。

**唯一凭据规则**：PostgreSQL/Oracle/Doris/TDengine 需要非空 `secretRef`，**TDengine profile 不存在 `credentialRef`**；`WEB_API` 且 `authentication=NONE` 时 `secretRef=null`，需 `API_KEY_REF/OAUTH_CLIENT_CREDENTIALS_REF` 时 `secretRef` 非空。禁止同时提交两个凭据引用或通过字符串 `"NONE"` 绕过 null 分支。密钥轮换使用独立命令，令已有测试状态过期，不能绕过重测启用。`CommandContext` 采用 G2 冻结合同：创建时 `expectedRevision=0`（不是 null），修改时必须和 `If-Match` 一致。

### 5.2 MappingRelease 只读样例

```json
{
  "mappingReleaseId":"maprel-syn-001", "mappingHash":"sha256:synthetic-mapping",
  "ontologyReleaseId":"ont-syn-001", "sourceConnectionId":"conn-syn-001",
  "connectionRevision":1, "sourceCatalogSnapshotId":"catalog-syn-001",
  "sourceCatalogFingerprint":"sha256:synthetic-schema", "reviewProposalId":"proposal-syn-001",
  "createdAtUtc":"2026-11-01T00:00:00Z",
  "readOnly":true, "active":true, "activationRevision":1
}
```

`active` 与 `activationRevision` 属**读取时从 PG 权威指针投影**的状态，不是不可变 MappingRelease 制品被修改。`sha256:synthetic-*` 均为明确合成设计占位符，正式 API/哈希验证必须拒绝其作为真实发布哈希。

## 6. Mapping 规则类型（强限定）
```
EntityBinding = { entityClassIri, sourceDatasetRef, identitySpecId,
                  scopeFields, temporalPolicy, baseFilterId }
PropertyBinding = { entityBindingId, propertyIri, sourceFieldRef,
                    conversionSpec, nullPolicy, evidencePolicy }
RelationBinding = { fromBinding, toBinding, predicateIri,
                    registeredJoinKeySet, joinCardinality, temporalJoinPolicy }
IdentitySpec = { organizationIdSource, siteIdSource, sourceNamespace,
                 externalIdFields[], validityFrom?, validityTo? }
TemporalSpec = { eventTimeField?, observedAtField?, timezonePolicy,
                 precision, validFrom?, validTo?, sourceWatermarkKind }
```
标识符必须从发现对象中引用；转换仅受控明确定义的整数/Decimal/字符串/布尔/日期/单位换算，非法转换拒绝。严禁自由字符串 expression/动态程序执行/SQL片段。`sourceNamespace` 必须参与身份键；`owl:sameAs` 不自动产生。G3 的半开有效区间 `[from,to)`、未知端点与歧义约束继续适用。

## 7. Endpoint 错误码及语义（建议）
| HTTP/业务 code | 用例 | 前端动作 |
|---|---|---|
| 400/422 `connection_profile_invalid` | 参数类型/URL/端口无效 | 聚焦出错字段 |
| 401 `login_required` | 会话不可用 | 引导登录，不缓存源结果 |
| 403 `connection_scope_forbidden` | 用户无该 org/sites/源对象访问 | 不透露对象是否存在及秘密信息 |
| 409 `connection_revision_conflict` | CAS或 secretVersion 冲突 | 展示新版并重测 |
| 422 `read_only_policy_unverified` | 源无法保证只读 | 阻断启用，说明预检阶段 |
| 409 `schema_fingerprint_changed` | Mapping 对应旧 Schema | 重新发现/重评估/新 revision |
| 409 `mapping_approval_stale` | 输入版本变化/审批过期 | 重新提案/审批 |
| 422 `mapping_identity_ambiguous` | 同号/未知有效期 | 修正 IdentitySpec，不猜 |
| 422 `mapping_unit_unknown` | 缺单位或不可逆转换 | 源单位验证/人工裁决 |
| 422 `query_plan_invalid` | 未登记能力/未授权字段/任意SQL注入 | 缩减计划条件 |
| 429 `query_budget_exceeded` | 行/时长/并发/分页超额 | 提示时间窗收缩，保留 Trace |
| 503 `source_unavailable` | 全必需源不可用 | UNAVAILABLE，不返回 EMPTY |
| 409 `source_cursor_expired` | 源数据变化导致分页不稳定 | 从第一页重建一致快照 |
| 422 `webapi_ssrf_blocked` | 请求目标不在审批范围 | 管理员核对网络策略 |

不重写 G2 原有 ProblemDetails status/code 优先级；新增 code 是否需要 namespace/版本须审阅 G3 合同后冻结。

## 8. G4 查询结果版本化合同与 G2 无损边界（CR-01）

**G2 冻结事实**：`SemanticQueryResult` 的 11 个顶层字段依次为 `status/data/candidates/evidence/snapshot/subSources/validTime/observedAtUtc/traceId/limited/diagnostics`，`JsonUnmappedMemberHandling.Disallow`；其中 G2 `EvidenceRef` 必须关联已发布 G3 命名图及源对象哈希，不能直接表示尚未物化的 G4 真实跨源数据行。`AssetVersionSnapshot` 和 `SemanticSubSource` 也有完整必需字段。**既有 G2 DTO、OpenAPI、REST/MCP/Run 字节契约不得改。**

**G4 新协议**：`POST /api/v1/data/semantic-queries` 返回 `G4QueryResultV1`，`schemaVersion=g4.query-result.v1`。该协议保留上述 11 个字段名称和六态语义，但 `snapshot/subSources/evidence/data` 明确是新 G4 类型，不能声称是 G2 DTO 的子类或直接 JSON 反序列化兼容：

| 字段 | G4 最低要求 | 不能虚构的内容 |
|---|---|---|
| `status` / `data` | 六态；FOUND 有真实已授权数据，EMPTY/UNAVAILABLE/UNAUTHORIZED 无行 | 失败当空、NULL当0、PARTIAL当FOUND |
| `candidates[]` | 与 G2 EntityCandidate 相同的实体IRI/类型/外部号/组织/厂区/label/evidenceIds；AMBIGUOUS 至少2个有权候选 | 把同外部号自动 sameAs；泄露越权厂区 |
| `evidence[]` | G4SourceEvidenceRef：evidenceId、connectionId、mappingReleaseId、sourceCatalogSnapshotId、datasetRef、sourceReadReceiptId、scope、precision、可空recordRef、可空validTime、observedAtUtc | 无主键时假 recordRef；无图时假 G3 graphIri/sourceObjectKey |
| `snapshot` | ontologyReleaseId、mappingReleaseIds、sourceCatalogSnapshotIds、capabilityId/version，必须同一执行固定并重新授权 | 动态读后替换历史版本 |
| `subSources[]` | connectionId、SUCCESS/EMPTY/TIMEOUT/FORBIDDEN/UNAVAILABLE/INDETERMINATE、observedAtUtc、watermarkKind、可空readReceiptId、limited | 无测得水位填精确值 |
| `validTime` | null 或明确 RFC3339 `[fromUtc,toUtc)`，结束可未知 | 用查询时间推断业务时间 |
| `observedAtUtc` | 实际读取时间、RFC3339，不与有效时间混淆 | 未采集精确时间却假填 |
| `diagnostics[]` | code、severity、脱敏message、可空focusNode/path | 异常栈、SQL、密钥或查询内部URL |
| `traceId/limited` | 实际运行 Trace、精确限额标记 | 静默截断 |

**来源链**：`G4SemanticDatum.evidenceIds → G4SourceEvidenceRef → SourceReadReceipt → MappingRelease → SourceCatalogSnapshot → SourceConnection`，每次回源重新执行当前 ACL/Scope/字段级策略。`UNKNOWN` precision 允许返回受限摘要但不能作为 Agent 的确定事实证据；没有源记录键时 `sourceRecordRef=null` 且 `precision` 降级。所有候选的 evidenceIds 必须能匹配当前响应中已授权 evidenceId，数据项同理；机器 Schema 验证基本字段，交叉引用、真正来源/有效期和权限必须由服务器运行时校验。

**版本化转换**：G4 内部 Query Gateway 继续为唯一执行协调器。只有完全满足 G2 `SemanticQueryResult` 及其所有嵌套 DTO 字段（含真实固定 G3 证据图来源）时，才允许显式转换成 G2 read model，否则只使用 G4 版本化响应并返回确定性错误/能力信息，**绝不抛弃候选、证据或诊断以迎合旧协议**。G2 用户仍走 `/api/v1/semantic/queries` 不受影响。两种结果共享授权、身份消歧和六态判别规则，而不是共享同名可变 DTO。正式实现须在 OpenAPI/TS 生成链里另行冻结并做 G2 V1–V4 兼容回归。

**正向样例**：`samples/g4-design-positive-synthetic.json` 包含 `AMBIGUOUS` 两名本 Scope 候选与两项匹配证据，及 `FOUND` 回源证据；`samples/g4-wire-contract-v11-negative-mutations.json` 包含缺候选/缺证据/额外字段等负例。均为合成设计数据，无真实数据读取或正式 API 测试。

## 9. 查询版本变化优先级
- 对既有 Run：Run 的结构化 snapshot/version不可被修改，但用户再次查看详细证据时必须按**当前**权限校验；不保留隐性可见性。
- 新 Run：固定当前 active OntologyRelease 与 MappingRelease 集合，在源访问前重新校验 ActorScope 和源授权，若 source schema watermark 不兼容则 fail closed。
- 回滚：重新激活原来已存的不可变 MappingRelease，不更改历史自带哈希；当前源 schema 或权限不再兼容时不能强行回滚成功。
- Outbox 提交后失败：事实保留，重派通知，缓存只按固定 ReleaseId 命中；不能用通知顺序决定真实 active。

## 10. Mapping 页面恢复与跨用户审核读取闭环（CR-04）

- U07 进入 `/data/mappings/new`：选择 Connection 与 CatalogSnapshot、已发布本体，`POST /api/v1/mappings`；获得 `draftId/revision/ETag` 后跳到 `/data/mappings/{id}`；`GET /api/v1/mappings/{id}` 恢复草稿；字段决定统一 `PATCH /api/v1/mappings/{id}` + CommandContext + If-Match，**不存在** `POST /mappings/{id}/edits`。
- 刷新或换设备：GET 最新草稿、`GET /revisions/{revision}` 查看固定历史、`GET /diff?fromRevision&toRevision` 查看差异、`GET /assessments?revision` 查看评估，均按当前 Actor/Scope 重授权，ETag 过期先比对再重新编辑，不静默覆盖。
- U10 异人审核从 `GET /api/v1/mapping-proposals?status=PENDING` 发现待审队列；打开 `GET /api/v1/mapping-proposals/{id}` 获得**一次固定**已提交 revision/hash/关联版本/提交者/过期时间及审查决定；继续 `GET /api/v1/mappings/{id}/revisions/{revision}` 和固定 diff/assessment。审核时不再依赖当前可变草稿状态；权限或输入变化导致审批/激活失败关闭，提交者不能自批。
- U11 历史目录 `GET /api/v1/mappings` 与 `GET /api/v1/mapping-releases?mappingId=...`；查看 `GET /api/v1/mapping-releases/{id}` 的不可变版本及指针激活状态，`GET /api/v1/mappings/{id}/active` 读取 PG 权威指针，回滚仍需固定目标版本/审批/CAS，不能靠 GET 修改状态。
- 列表/提案/版本的 cursor、组织厂区过滤、403/404/409/过期与已失效显示都由服务端校验；前端页面刷新、直链、审核人更换和历史访问要可恢复。
