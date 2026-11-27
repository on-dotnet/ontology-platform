# 007 附录：M4 接口的请求与响应结构

约定同 [001 附录](001-m1-api-shapes.md)、[002 附录](002-m2-api-shapes.md)、[003 附录](003-m3-api-shapes.md)：
- 字段一律用 camelCase；
- 时间为 ISO 8601 字符串，id 为 uuid 字符串；
- 可空字段写作 `T | null`；
- 错误统一用 problem+json，带稳定的 `code`；
- 分页为 `?limit=&cursor=`，响应 `{ items, nextCursor }`。

本文只列出新增和变化的部分。正文见 [007 规格](007-m4-qa-metrics-rules.md)。带 `M3` 前缀的名字（`M3Kind`、`M3ChangeSetSource`）指 003 附录里同名、不带前缀的类型在 M3 结束时的定义；`ReleaseRef`、`Scalar`、`FilterOp`、`Filter`、`ObjectRow`、`ObjectSource`、`Datatype` 沿用 003 附录。

新增 HTTP 路由在批次 1 建好，实现合并前返回 501 `http.not_implemented`。已有接口的指标写入限制见下文。

```ts
// ---------- 元素种类与变更集来源（批次 1 读取容忍，批次 3 开放指标写入） ----------
type Kind = M3Kind | 'metric';
type ChangeSetSource = M3ChangeSetSource | 'ai_qa';
type MetricAggregate = 'count' | 'sum' | 'avg' | 'min' | 'max' | 'ratio';
type MetricFilter = { propertyId: string; op: FilterOp; value?: Scalar | Scalar[] };   // 同 Filter
type MetricDefinition = {
  aggregate: MetricAggregate;
  propertyId: string | null;             // sum / avg / min / max 必填
  filters: MetricFilter[];               // 总体，最多 10 个
  numerator: MetricFilter[];             // 只有 ratio 用，最多 10 个
  decimals: number;                      // 0–6，默认 2
  percent: boolean;                      // ratio 显示为百分数
};
// 接口 Element 新增 metric: MetricDefinition | null；只有指标非空，旧快照缺键取 null。released_ontology 的 ElementCopy 只交付原有字段。
// 指标元素：localName、labelZh 必填；subjectId = 主体类型 id；unit 可选。
// 变更项 fields 里写法：metric 同上，但 propertyId 换成 propertyRef（元素 id 或 temp_ref "new:<localName>"）。
// 批次 1 拒绝含 metric 的变更项（422 changeset.invalid_item）；批次 3 开放指标的手工新建、修改和删除，仍走已有 edits / 变更集接口。

// ---------- 多跳查询（批次 2） ----------
type PathHop = { relationId: string; direction: 'out' | 'in'; filters?: Filter[] };   // filters 作用在这一跳到达的类型上，最多 10 个
type PathQuery = {
  typeId: string; filters?: Filter[];    // 起点类型与它的筛选
  hops: PathHop[];                       // 0–5 个，零跳只筛起点
  target?: number;                       // 答案位置：0 = 起点，i = 第 i 跳到达的类型；不写 = 终点
  limit?: number;                        // 返回的对象数，默认 50，最多 200；total 不受它限制
};
type QueryStep = {
  typeId: string; typeLabel: string;
  conditions: string[];                  // 可读描述，例如 "钢种 = Q235B"
  statements: number; rows: number; truncated: boolean;
};
type PathRow = ObjectRow & { via: string[] };   // 它所在的第一条完整链上每个位置的对象主键（编码形式，位置 0 到终点）
type PathResult = {
  release: ReleaseRef; typeId: string;   // typeId 是答案位置的类型
  items: PathRow[]; total: number; truncated: boolean;   // 答案对象：答案位置上至少有一条完整链走到终点的对象；truncated：items 少于 total
  tailTypeId: string | null; tail: PathRow[]; tailTotal: number;   // 答案位置不是终点时的终点对象，否则 null、[]、0
  steps: QueryStep[];
};
// POST /api/ontologies/{id}/objects/traverse                       → PathResult
// limit 只限制返回的行。包括零跳在内，内部按键集取完才算 total；traverse、traverse_keys、scan 超过 metric_rows_max（默认 10,000）报 query.too_many_rows。

// ---------- 指标与规则（批次 4） ----------
type KeySet = { typeId: string; keys: string[] };   // 最多 100 个主键（编码形式）；问答内部调用不受此限
type MetricValue = {
  release: ReleaseRef; metricId: string; label: string; unit: string | null;
  aggregate: MetricAggregate;
  value: string | null;                  // 小数的字符串；ratio 为 0–1 的比值，percent 只影响显示
  display: string | null;                // 按 decimals、percent 格式化，例如 "92.3%"
  population: number;                    // 总体行数
  matched: number | null;                // ratio 的分子行数
  nulls: number;                         // sum / avg / min / max 跳过的空值数
  reason: 'empty_population' | null;
  steps: QueryStep[];
};
type MetricEvaluate = { within?: KeySet };
type RuleCheck = 'minCount' | 'minInclusive' | 'maxInclusive' | 'minExclusive' | 'maxExclusive'
  | 'allowedValues' | 'minLength' | 'maxLength' | 'pattern';
type UncheckedReason = 'path_not_property' | 'path_not_bound' | 'check_not_supported' | 'value_mismatch';
type RuleResult = {
  constraintId: string; constraintLabel: string;
  propertyId: string | null; propertyLabel: string | null;
  checks: RuleCheck[];                   // 这条规则实际检查了哪些
  unchecked: { check: string; reason: UncheckedReason }[];
  message: string | null;                // 约束的 sh:message，按当前语言
  violations: number;
  samples: { object: ObjectRow; failed: { check: RuleCheck; expected: Scalar | Scalar[]; actual: Scalar | null }[] }[];   // 最多 limit 个
};
type RuleReport = {
  release: ReleaseRef; typeId: string;
  scanned: number; checkedRules: number; uncheckedRules: number;
  results: RuleResult[]; steps: QueryStep[];
};
type RuleCheckRequest = { typeId: string; within?: KeySet; limit?: number };   // limit 默认 50，最多 200
// GET  /api/ontologies/{id}/metrics                                → { release: ReleaseRef; items: MetricInfo[] }
type MetricInfo = {
  metricId: string; label: string; definition: string | null; unit: string | null;
  subjectTypeId: string; subjectTypeLabel: string; aggregate: MetricAggregate;
  bound: boolean;                        // 主体类型与所用属性在生效版本里都有绑定
};
// POST /api/ontologies/{id}/metrics/{metricId}/evaluate             → MetricValue
// POST /api/ontologies/{id}/rules/check                             → RuleReport

// ---------- 问答（批次 5a 后端、5b 界面、6 缺口回流） ----------
type QaOrigin = 'user' | 'cq';
type QaStatus = 'queued' | 'running' | 'answered' | 'unanswerable' | 'failed';
type QaStep = 'plan' | 'check' | 'query' | 'answer' | 'done';
type QaIntent = 'objects' | 'count' | 'metric' | 'rules';
type QaQuestionCreate = { question: string };   // 1–500 字
type QaPlan = {                          // 校验过的计划，引用已换成元素 id
  intent: QaIntent;
  start: { typeId: string; label: string; filters: Filter[] } | null;
  hops: (PathHop & { label: string; targetTypeId: string; targetLabel: string })[];
  target: number;                        // 答案位置（已补成具体的数）
  metricId: string | null;
  description: string;                   // 代码生成的中文描述
  assumptions: string[];                 // 模型写的
};
type QaGaps = {
  elements: { kind: 'entity_type' | 'relation_type' | 'property' | 'metric'; labelZh: string; description: string; near: { id: string; label: string }[] }[];
  bindings: { typeId: string; label: string }[];   // 需要绑定的类型（属性或关系缺绑定时给出其所属类型）
};
type QaEvidenceElement = {
  id: string; kind: Kind; label: string; iri: string | null;
  documents: { documentId: string; documentName: string; chunk: number; quote: string }[];   // 前 2 条已有证据
};
type QaEvidenceBinding = {
  schema: string; table: string;
  keyColumns: string[];                  // 主键列名；不含属性绑定列名
};
type QaEvidence = {
  release: ReleaseRef;
  elements: QaEvidenceElement[];
  bindings: QaEvidenceBinding[];
  steps: QueryStep[];
  rows: PathRow[]; truncated: boolean;   // 答案对象，最多 50 行
  tail: PathRow[];                       // 答案位置不是终点时的终点对象，最多 50 行
  metric: MetricValue | null;
  rules: RuleReport | null;
};
type QaFacts = {
  count: number | null;                  // count 意图，或 objects 意图的 total
  metric: { label: string; display: string | null } | null;
  objects: { typeId: string; key: string; label: string }[];   // 答案对象，最多 50 个
  violations: number | null;
};
type QaNote = 'cited_unknown' | 'answer_unavailable' | 'rows_not_shared' | 'rows_truncated';
type QaAnswer = {
  text: string | null;                   // 模型写的说明，短引用已换成对象编号；回答调用失败、回答引用了未分配的短引用或没有做（rows_not_shared）时为 null
  facts: QaFacts;                        // 代码生成，界面以它为准显示数字
  citedKeys: string[];                   // 模型 cited_keys 只回 K1…K50；代码将本次已分配的短引用映射回编码主键，未知引用丢弃并记 cited_unknown
  counterpoints: string[];
  notes: QaNote[];
};
type QaQuestion = {
  id: string; ontologyId: string; question: string;
  origin: QaOrigin; cqQuestionId: string | null;
  askedBy: { id: string; displayName: string };
  status: QaStatus; step: QaStep | null;
  release: ReleaseRef | null;            // 计划开始时的生效版本
  plan: QaPlan | null;
  gaps: QaGaps | null;                   // 只有 unanswerable 时非空
  answer: QaAnswer | null;               // 只有 answered 时非空
  evidence: QaEvidence | null;
  gapProposal: { status: 'queued' | 'running' | 'done' | 'empty' | 'failed'; changeSetId: string | null; dropped: number; errorCode: string | null } | null;   // empty：无可用项，changeSetId 为 null，显示 qa.gapEmpty
  errorCode: string | null;
  createdAt: string; finishedAt: string | null;
};
// POST /api/ontologies/{id}/qa/questions                           → 202 QaQuestion（queued）
// GET  /api/ontologies/{id}/qa/questions?askedBy=me|all&limit=&cursor=   → { items: QaQuestion[]; nextCursor }（all 需要 admin；列表项的 evidence 为 null）
// GET  /api/qa/questions/{id}                                      → QaQuestion
// POST /api/qa/questions/{id}/gap-proposal                         → 202 QaQuestion（gapProposal 为 queued；已发起过则返回 200 与现有结果）

// ---------- 能力问题（批次 7） ----------
type CqExpectKind = 'answerable' | 'objects' | 'number';
type CqResult = 'pending' | 'pass' | 'fail' | 'unanswerable' | 'error';
type CompetencyQuestion = {
  id: string; ontologyId: string; text: string;
  expect: { kind: CqExpectKind; typeId: string | null; keys: string[]; number: string | null; tolerance: string };
  note: string | null; position: number; revision: number;
  lastCheck: CqCheck | null;
  createdAt: string; updatedAt: string; archivedAt: string | null;
};
type CqCheck = {
  id: string; questionId: string; release: ReleaseRef;
  stale: boolean;                        // 不是当前生效版本上的结果
  qaQuestionId: string; result: CqResult;
  detail: { missing: string[]; extra: string[]; actual: string | null; errorCode: string | null } | null;
  createdAt: string; finishedAt: string | null;
};
type CompetencyQuestionCreate = {
  text: string;                          // 1–500 字
  expect: { kind: CqExpectKind; typeId?: string; keys?: string[]; number?: string; tolerance?: string };   // keys 为明文主键，最多 100 个
  note?: string;
};
type CompetencyQuestionPatch = Partial<CompetencyQuestionCreate> & { position?: number; revision: number };
type CoverageItem = {
  questionId: string;
  status: 'ok' | 'element_missing' | 'binding_missing' | 'never_checked';
  elements: { id: string; label: string; present: boolean; bound: boolean }[];
};
// GET    /api/ontologies/{id}/competency-questions?archived=false     → { items: CompetencyQuestion[] }
// POST   /api/ontologies/{id}/competency-questions                     → 201 CompetencyQuestion
// PATCH  /api/competency-questions/{id}                                → CompetencyQuestion
// POST   /api/competency-questions/{id}/archive                        → CompetencyQuestion
// POST   /api/ontologies/{id}/competency-questions/import              → { created: number; skipped: number }（请求体 text/plain 或 multipart：questions.toml，最多 64 KB、50 条）
// POST   /api/competency-questions/{id}/check                          → 202 CqCheck
// POST   /api/ontologies/{id}/competency-questions/check               → 202 { checks: CqCheck[] }（最多 50 条）
// GET    /api/ontologies/{id}/competency-questions/coverage            → { release: ReleaseRef | null; items: CoverageItem[] }
```

## MCP（批次 4）

在 003 附录的工具清单上新增两个，作用域 `objects:read`：

```ts
// evaluate_metric   { ontology, metric, within?: { type, keys } }      → MetricValue
// check_rules       { ontology, type, keys?, limit? }                  → RuleReport
// metric、type 可以用元素 id、IRI 或局部名；keys 最多 100 个。
// ElementBrief.kind 增加 'metric'；get_element 对指标返回 ElementInfo & { metric: MetricDefinition }。
// search_elements 的 kinds 可以写 'metric'。propose_changes 不变（kind 仍不含 metric）。
```

## 接口与角色

| 方法与路径 | 角色 | 令牌作用域 | 批次 |
|---|---|---|---|
| `POST /api/ontologies/{id}/objects/traverse` | viewer | `objects:read` | 2 |
| `GET /api/ontologies/{id}/metrics`、`POST …/metrics/{metricId}/evaluate`、`POST …/rules/check` | viewer | `objects:read` | 4 |
| `POST /api/ontologies/{id}/qa/questions`、`GET /api/qa/questions/{id}`、`GET …/qa/questions?askedBy=me` | viewer（只看自己的；admin 可看全部，`askedBy=all`） | 不接受令牌 | 5a |
| `POST /api/qa/questions/{id}/gap-proposal` | editor（且必须是提问人，或 admin） | 不接受令牌 | 6 |
| `GET …/competency-questions`、`GET …/competency-questions/coverage` | viewer | 不接受令牌 | 7 |
| `POST/PATCH …/competency-questions`、`archive`、`import`、`check` | editor | 不接受令牌 | 7 |
| `POST /api/ontologies/{id}/edits`（指标项） | 同 002：editor；`apply` 需要 reviewer 且为单人模式 | 不接受令牌 | 3 |
| `POST /mcp` 的 `evaluate_metric`、`check_rules` | 令牌主人的角色为 viewer 以上 | `objects:read` | 4 |

## 错误码补充

| code | HTTP | 含义 |
|---|---|---|
| `http.not_implemented` | 501 | 接口已定义、实现尚未合并（只在 M4 开发期间出现） |
| `changeset.invalid_item` | 422 | 批次 1 至开放写入前，拒绝种类为 `metric` 的变更项 |
| `metric.not_found` | 404 | 生效版本里没有这个指标 |
| `metric.invalid` | 422 | 指标定义不合法（手工编辑时；合并时为跳过码 `changeset.invalid_item`） |
| `query.too_many_rows` | 422 | `traverse`、`traverse_keys` 的起点、任一跳对象或键对、`scan` 的行数超过 `metric_rows_max` |
| `metric.too_many_rows` | 422 | 指标计算超出 `metric_rows_max`（默认 10,000 行），请加筛选 |
| `qa.not_found` | 404 | 问题不存在，或不属于当前用户 |
| `qa.rate_limited` | 429 | 超过每小时 30 个问题，或同时进行中的问题超过 3 个；带 `Retry-After` |
| `qa.invalid_plan` | 无（问题的 `errorCode`） | 模型给出的计划结构不合法，包括筛选值无法转换或运算符不在属性的 `ops` 中 |
| `qa.too_many_queries` | 无（问题的 `errorCode`）/ 422（`traverse`） | 一次问答或多跳查询需要的语句超过 200 条 |
| `qa.timeout` | 无（问题的 `errorCode`） | 问答任务超过 180 秒 |
| `qa.not_unanswerable` | 409 | 只有答不了且缺语义元素的问题能生成缺口提议 |
| `cq.not_found` | 404 | 能力问题不存在 |
| `cq.stale` | 409 | 能力问题在读取之后被修改过 |
| `cq.check_running` | 409 | 这个本体已有一次"全部检验"在进行 |
| `cq.invalid_import` | 422 | 导入文件不是合法的 TOML，或超过 64 KB、50 条 |
| `ai.not_configured` | 409 | 沿用：创建问题、发起检验或缺口提议时 AI 未配置 |

补充约定：

- 问题的 `errorCode` 还可能是 `query.*`（沿用 003 附录）与 `ai.unavailable`、`ai.invalid_output`（沿用 002）。
- 问答与能力问题检验不受 `query.release_changed` 以外的版本变化影响：计划开始时记下生效版本，执行途中版本变了就以 `query.release_changed` 失败，用户重问即可。
- 计划调用只收问题与语义上下文。全部用过的数据源都启用且 `allowSamples = true` 时才做回答调用；否则 `answer.text = null`，`answer.notes` 含 `rows_not_shared`，仍返回代码生成的事实与证据（正文第 5.8 节）。
- `QaEvidenceBinding` 只公开 `schema`、`table`、`keyColumns`；列名限于 M3 `ObjectSource.key` 已展示的主键列名。
- 跳过码：指标变更项在合并时被跳过用现有的四个码，不新增。
