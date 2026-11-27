# 003 附录：M3 接口的请求与响应结构

约定同 [001 附录](001-m1-api-shapes.md)、[002 附录](002-m2-api-shapes.md)：
- 字段一律用 camelCase；
- 时间为 ISO 8601 字符串，id 为 uuid 字符串；
- 可空字段写作 `T | null`；
- 错误统一用 problem+json；
- 分页为 `?limit=&cursor=`，响应 `{ items, nextCursor }`。

本文只列出新增和变化的部分。正文见 [003 规格](003-m3-data-binding-query.md)。带 `M2` 前缀的名字（`M2Kind`、`M2ChangeSetSource`、`M2ItemFlag`、`M2ReleaseSummary`）指 002 附录里同名、不带前缀的类型在 M2 结束时的定义。

```ts
// ---------- 访问令牌（批次 2） ----------
type TokenScope = 'ontology:read' | 'objects:read' | 'changes:propose';
type AccessToken = {
  id: string; name: string;
  prefix: string;                        // "op_pat_" 加 8 位，只用于辨认
  scopes: TokenScope[];
  owner: { id: string; displayName: string };
  createdAt: string; expiresAt: string;
  lastUsedAt: string | null; revokedAt: string | null;
};
type AccessTokenCreate = { name: string; scopes: TokenScope[]; expiresInDays: number };   // 1–365，默认 90
type AccessTokenCreated = { token: string; info: AccessToken };   // token 只在这一次响应里出现
// GET    /api/auth/tokens?owner=me|all        → AccessToken[]（all 需要 admin）
// POST   /api/auth/tokens                     → 201 AccessTokenCreated，响应带 Cache-Control: no-store
// DELETE /api/auth/tokens/{id}                → 204（自己的，或 admin 撤销任何人的）

// ---------- 数据源（批次 3） ----------
type DataSourceKind = 'postgresql';
type SslMode = 'disable' | 'prefer' | 'require' | 'verify-full';
type TestWarning = 'account_can_write';
type CatalogStatus = 'never' | 'refreshing' | 'ready' | 'failed';
type DataSource = {
  id: string; name: string; kind: DataSourceKind; status: 'active' | 'archived';
  // viewer 得到 null：主机、库、用户名只给 editor 以上
  connection: { host: string; port: number; database: string; username: string; sslMode: SslMode; schemas: string[] } | null;
  hasCredential: boolean; credentialUpdatedAt: string | null;   // 口令本身在任何响应里都不出现
  allowSamples: boolean;
  lastTest: { at: string; ok: boolean; code: string | null; warnings: TestWarning[] } | null;
  catalog: { status: CatalogStatus; refreshedAt: string | null; errorCode: string | null; tableCount: number } | null;   // viewer 为 null
  boundTypeCount: number | null;         // 工作版本里绑定到它的对象类型数；无法确定时为 null
  revision: number; createdAt: string; updatedAt: string;
};
type DataSourceCreate = {
  name: string; kind: DataSourceKind; host: string; port: number; database: string; username: string;
  password: string; sslMode?: SslMode; schemas?: string[]; allowSamples?: boolean;
};
// 修改：只带要改的字段。连接目标（host、port、username、sslMode）不变时，不带 password 表示不改口令；
// 目标变了必须带新口令，否则 422 datasource.password_required
type DataSourcePatch = Partial<Omit<DataSourceCreate, 'kind'>> & { revision: number };
// 用未保存的参数测试。编辑时不带 password 而带 dataSourceId，只在连接目标不变时沿用已保存的口令
// （host 比较忽略大小写和首尾空白）；目标变了返回 422 datasource.password_required，不会去连接
type ConnectionTestRequest = Omit<DataSourceCreate, 'name' | 'password' | 'allowSamples'> & { password?: string; dataSourceId?: string };
type ConnectionTest = {
  ok: boolean; code: string | null;
  reason: 'unreachable' | 'auth_failed' | 'database_missing' | 'ssl' | 'timeout' | null;   // code 为 datasource.connect_failed 时
  warnings: TestWarning[]; serverVersion: string | null;
};

type ColumnFamily = 'string' | 'opaque' | 'integer' | 'decimal' | 'boolean' | 'date' | 'dateTime' | 'other';   // opaque：uuid、枚举
type CatalogColumn = { name: string; type: string; family: ColumnFamily; nullable: boolean; comment: string | null; position: number };
type CatalogForeignKey = { name: string | null; columns: string[]; refSchema: string; refTable: string; refColumns: string[] };
type CatalogTableBrief = {
  schema: string; name: string; kind: 'table' | 'view' | 'materialized_view' | 'foreign_table';
  comment: string | null; columnCount: number;
  boundType: { id: string; label: string } | null;   // 工作版本里绑定到这张表的对象类型
};
type CatalogTable = CatalogTableBrief & {
  columns: CatalogColumn[]; primaryKey: string[] | null; foreignKeys: CatalogForeignKey[]; refreshedAt: string;
};
// GET   /api/data-sources                                          → DataSource[]
// POST  /api/data-sources                                          → 201 DataSource
// GET   /api/data-sources/{id}                                     → DataSource
// PATCH /api/data-sources/{id}                                     → DataSource
// POST  /api/data-sources/{id}/archive                             → DataSource
// POST  /api/data-sources/test                                     → ConnectionTest（未保存的参数）
// POST  /api/data-sources/{id}/test                                → ConnectionTest
// POST  /api/data-sources/{id}/catalog/refresh                     → 202 DataSource（任务 connectors.refresh_catalog）
// GET   /api/data-sources/{id}/catalog/schemas                     → { name: string; tableCount: number }[]
// GET   /api/data-sources/{id}/catalog/tables?schema=&q=&limit=&cursor=   → { items: CatalogTableBrief[]; nextCursor }
// GET   /api/data-sources/{id}/catalog/tables/{schema}/{table}     → CatalogTable

// ---------- 绑定（批次 4a；在 002 的基础上变化） ----------
type BindingKind = 'type_binding' | 'property_binding' | 'relation_binding';
type Kind = M2Kind | BindingKind;
type Join =
  | { kind: 'foreign_key'; side: 'source' | 'target'; columns: string[]; references: string[] }
  | { kind: 'link_table'; schema: string; table: string; sourceColumns: string[]; targetColumns: string[] };
type Binding =
  | { target: 'table'; dataSourceId: string; schema: string; table: string; keyColumns: string[] }   // type_binding
  | { target: 'column'; column: string }                                                              // property_binding
  | { target: 'join'; join: Join };                                                                   // relation_binding

// Element 新增 binding: Binding | null。绑定元素的 localName、iri、名称都是 null；
// subjectId 是所绑的元素；property_binding 的 parentId、relation_binding 的 domainId / rangeId 指向类型绑定。
// GET /api/ontologies/{id}/elements 默认不返回绑定；kind 明确写绑定种类时才返回。

// ElementFields 新增 subjectRef?: string; binding?: Binding。
// 绑定种类的 parentRef / domainRef / rangeRef 指向类型绑定（元素 id 或同一变更集里的 temp_ref）。
type ChangeSetSource = M2ChangeSetSource | 'ai_binding' | 'mcp';
type ItemFlag = M2ItemFlag | 'key_unverified';

// 证据：原来只有资料证据，现在增加目录证据
type CatalogFact = 'table' | 'column' | 'primary_key' | 'foreign_key' | 'sample';
type Evidence = {
  id: string; kind: 'document' | 'catalog'; quote: string;
  documentId: string | null; chunkId: string | null; charStart: number | null; charEnd: number | null;   // 仅 document
  source: { dataSourceId: string; schema: string; table: string; column: string | null; fact: CatalogFact } | null;   // 仅 catalog
};

// 按对象类型组织的绑定视图（工作版本），供类型详情使用
type CatalogCheck = 'ok' | 'missing_table' | 'missing_column' | 'type_mismatch' | 'catalog_unavailable';
type TypeBindingView = {
  typeId: string;
  table: {
    elementId: string; revision: number;
    dataSource: { id: string; name: string; status: 'active' | 'archived' };
    schema: string; table: string; keyColumns: string[]; check: CatalogCheck;
  } | null;
  properties: {
    propertyId: string; label: string; datatype: Datatype | null; inherited: boolean;
    column: { elementId: string; revision: number; column: string; columnType: string | null; check: CatalogCheck } | null;
  }[];
  relations: {
    relationId: string; label: string; direction: 'out' | 'in'; otherTypeId: string; otherTypeLabel: string;
    join: { elementId: string; revision: number; join: Join; check: CatalogCheck } | null;
  }[];
  openChangeSetIds: string[];            // 含这个类型的绑定项的未决变更集
};
// GET /api/ontologies/{id}/bindings?typeId=        → TypeBindingView[]（不带 typeId 时返回所有已绑定的类型）
// 手工编辑绑定沿用 POST /api/ontologies/{id}/edits（002 第 6 节），items 的 kind 用绑定种类。

// 影响分析（002 的 Impact）新增 bindings: ElementRef[]：直接引用该元素的在用绑定；
// 绑定的 ElementRef.label 是生成的说明，如 "炉次 → mes.heat"。cascade 里照常包含绑定的删除项。

type ReleaseSummary = M2ReleaseSummary & { bindingCount: number };   // elementCount 只数语义元素
// ReleaseProblem.code 新增 'release.invalid_binding'
// GET /api/releases/{id}/r2rml                     → text/turtle（批次 6c）

// ---------- AI 绑定建议（批次 4b） ----------
type TableRef = { schema: string; name: string };
type BindingSuggestionCreate = {
  dataSourceId: string;
  tables?: TableRef[];                   // 与 schemas 二选一；合计不超过 200 张表、4,000 列
  schemas?: string[];
  typeIds?: string[];                    // 只为这些对象类型建议；缺省为全部未绑定的
};
type BindingSuggestion = {
  id: string; ontologyId: string; dataSourceId: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  step: 'catalog' | 'match' | 'columns' | 'changeset' | null;
  changeSetId: string | null;            // 没有可采用的建议时为 null
  proposed: number; dropped: number;     // 采用与丢弃的条数
  samplesSent: boolean; errorCode: string | null;
  createdAt: string; finishedAt: string | null;
};
// POST /api/ontologies/{id}/binding-suggestions          → 202 BindingSuggestion
// GET  /api/binding-suggestions/{id}                     → BindingSuggestion
// GET  /api/ontologies/{id}/binding-suggestions?limit=20 → BindingSuggestion[]（当前用户发起的）

// ---------- 对象查询（批次 5） ----------
type ReleaseRef = { id: string; version: number };
type Scalar = string | number | boolean;   // 结果里的取值：decimal 一律是字符串
type FilterOp = 'eq' | 'ne' | 'lt' | 'le' | 'gt' | 'ge' | 'contains' | 'startsWith' | 'in' | 'isNull' | 'notNull';
type Filter = { propertyId: string; op: FilterOp; value?: Scalar | Scalar[] };   // 筛选值的小数可以写成数字或字符串
// 运算符与数据类型：string 可用全部；数值、日期、时间不可用 contains / startsWith；boolean 只有 eq / ne / isNull / notNull；
// 绑到 opaque 族的列（uuid、枚举）的 string 属性只有 eq / ne / in / isNull / notNull。每个属性实际能用的见 ObjectTypeInfo 的 ops。
type ObjectTypeInfo = {
  typeId: string; label: string; localName: string | null; iri: string | null;
  keyColumns: string[];
  problem: 'source_mismatch' | 'source_disabled' | null;   // 非空时这个类型暂时不能查询，其余类型不受影响
  properties: { propertyId: string; label: string; datatype: Datatype; unit: string | null; ops: FilterOp[] }[];   // 只列绑定过的属性，都可以排序
  relations: { relationId: string; label: string; direction: 'out' | 'in'; otherTypeId: string; otherTypeLabel: string }[];
};
type ObjectSearch = {
  typeId: string; filters?: Filter[];    // 最多 10 个，条件之间是"并且"
  sort?: { propertyId: string; direction: 'asc' | 'desc' }[];   // 最多 2 个
  limit?: number;                        // 默认 50，最多 200
  cursor?: string;
};
type ObjectSource = {
  dataSourceId: string; dataSourceName: string; schema: string; table: string;
  key: { column: string; value: string }[];
};
type ObjectRow = {
  typeId: string;
  key: string;                           // 主键值的 URL 安全编码，用在路径里
  values: Record<string, Scalar | null>; // 属性 id → 值；decimal 为字符串
  truncated: string[];                   // 文本被截断的属性 id
  source: ObjectSource;
};
type ObjectPage = { release: ReleaseRef; typeId: string; items: ObjectRow[]; nextCursor: string | null };
type ObjectDetail = ObjectRow & { release: ReleaseRef; relations: ObjectTypeInfo['relations'] };
// GET  /api/ontologies/{id}/objects/types                                     → { release: ReleaseRef; items: ObjectTypeInfo[] }
// POST /api/ontologies/{id}/objects/search                                    → ObjectPage
// GET  /api/ontologies/{id}/objects/{typeId}/{key}                            → ObjectDetail
// GET  /api/ontologies/{id}/objects/{typeId}/{key}/related?relationId=&direction=out|in&limit=&cursor=
//                                                                             → ObjectPage（typeId 是相关对象的类型）
```

## MCP（批次 6）

端点 `POST /mcp`，JSON-RPC，协议版本 `2026-07-28`，认证为 `Authorization: Bearer <访问令牌>`。字段名与错误码以规范的 schema 原文为准，下面只列工具的输入与结构化输出。

```ts
// ontology：本体的 id 或 key。所有结果都带 release: { version }。
// list_ontologies        {}                                                    → { ontologies: { id, key, name, description, releaseId, version, publishedAt }[] }
// search_elements        { ontology, query?, kinds?, limit?, cursor? }         → { items: ElementBrief[]; nextCursor }
// get_element            { ontology, id? , iri? }                              → ElementInfo
// search_objects         { ontology, type, filters?, sort?, limit?, cursor? }  → ObjectPage
// get_object             { ontology, type, key }                               → ObjectDetail
// get_related_objects    { ontology, type, key, relation, direction?, limit?, cursor? } → ObjectPage
// propose_changes        { ontology, title, operations }                       → { changeSetId: string | null; proposed: number; dropped: number }
type ElementBrief = {
  id: string; kind: 'entity_type' | 'property' | 'relation_type' | 'constraint'; iri: string | null;
  labelZh: string | null; labelEn: string | null; definitionZh: string | null; definitionEn: string | null;
  synonyms: { lang: string; text: string }[];
  parent: string | null; domain: string | null; range: string | null;   // 名称
  datatype: Datatype | null; unit: string | null;
};
type ElementInfo = ElementBrief & {
  required: boolean; multiple: boolean;
  // 以下只有对象类型有
  properties?: ElementBrief[];           // 含继承的
  relationsOut?: ElementBrief[]; relationsIn?: ElementBrief[];
  children?: { id: string; label: string }[];
  constraints?: { id: string; label: string; ruleCount: number }[];
  hasData?: boolean;                     // 生效版本里是否绑定了数据
};
// type、relation 参数可以用元素 id、IRI 或局部名；筛选与排序里的 propertyId 同样。
// propose_changes 的 operations 结构同 AI 助手的操作（002 第 10 节），最多 50 个，其中新建或修改公理的操作最多 10 个，kind 只能是
// entity_type、relation_type、property、axiom。
// 工具执行失败时结果的 isError 为 true，结构化内容为 { code, message }，code 用下面的错误码。
```

## 接口与角色

| 方法与路径 | 角色 | 令牌作用域 | 批次 |
|---|---|---|---|
| `GET /api/auth/tokens`、`POST /api/auth/tokens`、`DELETE /api/auth/tokens/{id}` | 任何角色（`owner=all`、撤销别人的需要 admin） | 不接受令牌 | 2 |
| `GET /api/auth/me` | 任何角色 | 任何有效令牌 | 2 |
| `GET /api/releases/{id}`、`GET /api/releases/{id}/export` | viewer | `ontology:read` | 2 |
| `GET /api/data-sources`、`GET /api/data-sources/{id}` | viewer（`connection`、`catalog` 为 null） | 不接受令牌 | 3 |
| `POST /api/data-sources`、`PATCH`、`archive`、`POST /api/data-sources/test` | admin | 不接受令牌 | 3 |
| `POST /api/data-sources/{id}/test`、`catalog/refresh`、`GET …/catalog/**` | editor（及 reviewer、admin） | 不接受令牌 | 3 |
| `GET /api/ontologies/{id}/bindings` | viewer | 不接受令牌 | 4a |
| `POST /api/ontologies/{id}/edits`（绑定项） | 同 002：editor；`apply` 需要 reviewer 且为单人模式 | 不接受令牌 | 4a |
| `POST /api/ontologies/{id}/binding-suggestions` | editor | 不接受令牌 | 4b |
| `GET /api/binding-suggestions/{id}`、`GET /api/ontologies/{id}/binding-suggestions` | editor（只能看自己发起的） | 不接受令牌 | 4b |
| `GET /api/ontologies/{id}/objects/types`、`POST …/objects/search`、`GET …/objects/{typeId}/{key}`、`GET …/related` | viewer | `objects:read` | 5 |
| `POST /mcp` | 取决于工具 | 取决于工具（规格第 9 节） | 6 |
| `GET /api/releases/{id}/r2rml` | editor | 不接受令牌 | 6c |

没有列出的 `/api` 路由都不接受令牌（403 `auth.token_not_allowed`），包括读工作版本的接口（本体列表、元素、变更集）。上表"令牌作用域"一列就是令牌的白名单，测试按它枚举。`POST …/objects/search` 是读操作，但方法是 POST：Cookie 会话照常要带 CSRF 头，令牌请求不需要。

## 错误码补充

| code | HTTP | 含义 |
|---|---|---|
| `auth.invalid_token` | 401 | 令牌不存在、已过期、已撤销，或主人已停用（不区分，防止探测） |
| `auth.token_not_allowed` | 403 | 这个接口不接受访问令牌 |
| `auth.insufficient_scope` | 403 | 令牌缺少所需的作用域 |
| `token.limit_reached` | 409 | 有效令牌已达 10 个 |
| `token.scope_not_allowed` | 403 | 当前角色不能申请这个作用域 |
| `token.not_found` | 404 | 令牌不存在，或不属于当前用户 |
| `http.not_implemented` | 501 | 接口已定义、实现尚未合并（只在 M3 开发期间出现） |
| `datasource.not_found` | 404 | 数据源不存在 |
| `datasource.name_taken` | 409 | 名称已被占用 |
| `datasource.stale` | 409 | 数据源在读取之后被修改过 |
| `datasource.in_use` | 409 | 工作版本或生效版本的绑定还在引用它，不能归档 |
| `datasource.archived` | 409 | 对已归档的数据源做修改、测试、读取目录或发起 AI 绑定建议 |
| `datasource.platform_database` | 422 | 不能把平台自己的数据库作为数据源 |
| `datasource.credential_unreadable` | 409 | 保存的口令无法解密，需要重新填写 |
| `datasource.password_required` | 422 | 修改或测试时改了连接目标（主机、端口、用户名、SSL 模式），却没有带新口令 |
| `datasource.connect_failed` | 200（`ConnectionTest.code`）/ 502 | 连不上：附 `reason`，取值 `unreachable`、`auth_failed`、`database_missing`、`ssl`、`timeout` |
| `catalog.not_ready` | 409 | 还没有读取过目录 |
| `catalog.too_large` | 无（目录任务的失败码，出现在 `DataSource.catalog.errorCode`） | 表或列超过上限，请填写模式范围 |
| `catalog.table_not_found` | 404 | 目录缓存里没有这张表 |
| `binding.invalid` | 422 | 绑定的结构或引用不合法（手工编辑时；合并时为跳过码 `changeset.invalid_item`） |
| `binding.duplicate` | 409 | 这个元素已经有在用的绑定 |
| `binding.type_mismatch` | 422 | 列的类型与属性的数据类型不相容 |
| `binding.cross_source` | 422 | 关系两端的表不在同一个数据源 |
| `binding_suggestion.scope_too_large` | 422 | 范围超过 200 张表或 4,000 列 |
| `binding_suggestion.scope_empty` | 422 | 所选的模式或表在目录缓存里一张表都没有 |
| `binding_suggestion.not_found` | 404 | 请求不存在，或不属于当前用户 |
| `query.no_release` | 409 | 本体没有生效的发布版本 |
| `query.type_not_bound` | 409 | 这个类型在生效版本里没有绑定 |
| `query.object_not_found` | 404 | 没有这个主键的对象 |
| `query.invalid_filter` | 422 | 属性没有绑定；运算符不适用于它的数据类型或所绑列的类型族；取值的写法不合法（含数据库报的枚举取值不合法） |
| `query.invalid_cursor` | 422 | 游标与当前请求不符 |
| `query.release_changed` | 409 | 翻页途中生效版本变了，需要从头查询 |
| `query.timeout` | 504 | 查询超时 |
| `query.busy` | 503 | 这个数据源上排队的查询太多 |
| `query.source_unavailable` | 502 | 数据源连不上 |
| `query.source_mismatch` | 409 | 绑定的表或列在目录缓存或数据源里已不存在，或所绑视图在数据库里执行出错 |
| `query.source_disabled` | 409 | 数据源已归档，或口令不可用 |
| `mcp.rate_limited` | 429 | 超过 nginx 对 `/mcp` 的限流（HTTP 429）；或超过提议变更的频率限制（工具错误，HTTP 仍是 200） |

补充约定：

- **错误里没有驱动原文**：`datasource.*`、`query.*` 的 `detail` 是固定的英文句子，最多附异常类名和 SQLSTATE；主机、用户名、连接串、语句文本都不出现。
- **跳过码**：合并时绑定项被跳过用现有的四个码（`changeset.stale_target`、`dependency_skipped`、`invalid_item`、`has_dependents`），不新增。
- **MCP 的认证失败**：401 带 `WWW-Authenticate: Bearer`；作用域不足的协议层请求 403 带 `WWW-Authenticate: Bearer error="insufficient_scope"`。
