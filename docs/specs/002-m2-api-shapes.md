# 002 附录：M2 接口的请求与响应结构

约定同 [001 附录](001-m1-api-shapes.md)：
- 字段一律用 camelCase；
- 时间为 ISO 8601 字符串，id 为 uuid 字符串；
- 可空字段写作 `T | null`；
- 错误统一用 problem+json。

本文只列出新增和变化的部分。

```ts
type Kind = 'entity_type' | 'relation_type' | 'property' | 'constraint' | 'axiom';
type ElementFlag = 'non_standard';

// RDF 取值，保留原写法：iri 与 lexical 二选一；datatype 为 xsd 局部名（如 'integer'）或完整 IRI
type RdfValue = { iri: string | null; lexical: string | null; datatype: string | null; lang: string | null };
type LangText = { lang: string | null; text: string };
type NodeKind = 'IRI' | 'Literal' | 'BlankNode' | 'BlankNodeOrIRI' | 'BlankNodeOrLiteral' | 'IRIOrLiteral';

type ConstraintRule = {
  pathId: string;                       // 属性或关系元素
  classId: string | null;               // sh:class，对象类型元素
  minCount: number | null; maxCount: number | null;
  datatype: string | null; nodeKind: NodeKind | null;
  allowedValues: RdfValue[] | null;     // sh:in
  allowedValuesLost: boolean;           // sh:in 指向空节点：Protégé 丢掉了列表
  minInclusive: RdfValue | null; maxInclusive: RdfValue | null;
  minExclusive: RdfValue | null; maxExclusive: RdfValue | null;
  minLength: number | null; maxLength: number | null; pattern: string | null; flags: string | null;
  message: LangText[];
};

// ---------- 元素（在 M1 的基础上变化） ----------
type Element = {
  id: string; ontologyId: string; kind: Kind;
  localName: string | null;             // 公理为 null
  iri: string | null;                   // 公理为 null；其余为显式 IRI 或 baseIri + localName
  explicitIri: boolean;                 // true：导入时带来的 IRI
  labelZh: string | null; labelEn: string | null;
  definitionZh: string | null; definitionEn: string | null; synonyms: Synonym[];
  parentId: string | null; domainId: string | null; rangeId: string | null; inverseId: string | null;
  datatype: Datatype | null; unit: string | null; required: boolean; multiple: boolean;
  autoShape: boolean;                   // 必填、允许多个是否写进平台的自动形状
  rules: ConstraintRule[] | null;       // 仅约束
  turtle: string | null;                // 仅公理
  subjectId: string | null;             // 仅公理
  flags: ElementFlag[];
  status: 'active' | 'deprecated'; origin: 'ai' | 'manual' | 'import'; revision: number;
  createdAt: string; updatedAt: string;
};
// GET /api/ontologies/{id}/elements?kind=&q=&status=active|deprecated|all（默认 active）

type OntologySummary = M1OntologySummary & {
  ontologyIri: string; constraintCount: number; axiomCount: number;
};

// ---------- 变更集 ----------
type ConstraintRuleFields = Omit<ConstraintRule, 'pathId' | 'classId'> & { pathRef: string; classRef?: string | null };
type ElementFields = M1ElementFields & {
  iri?: string | null; inverseRef?: string | null; autoShape?: boolean | null;
  rules?: ConstraintRuleFields[] | null; turtle?: string | null;
};
type ChangeOp = 'create' | 'update' | 'delete' | 'restore';
type ChangeItem = M1ChangeItem & { op: ChangeOp; kind: Kind; flags: ('evidence_not_found' | 'possible_duplicate' | 'non_standard')[] };
type ChangeSetSource = 'ai_extraction' | 'ai_assistant' | 'manual' | 'import';
// ChangeSetSummary 新增 createdBy: string | null（提交人；AI 变更集为上传资料或提问的人）。
// 异人审核模式下，提交人可以撤回（整体拒绝）自己的变更集，但不能逐项决定或合并（PR B）。
type MergeSkipCode = 'changeset.stale_target' | 'changeset.dependency_skipped' | 'changeset.invalid_item' | 'changeset.has_dependents';

// ---------- 导入（PR A） ----------
// POST /api/ontologies/import          multipart：file，name?，key?       → 201 ImportResult
// POST /api/ontologies/{id}/import     multipart：file                   → 200 ImportResult
// POST /api/ontologies/{id}/turtle     { turtle: string }                → 200 ImportResult（PR B）
type ImportResult = {
  ontology: OntologySummary;
  changeSetId: string | null;           // 没有差异时为 null
  counts: { create: number; update: number; delete: number; restore: number };
  warnings: { code: 'non_standard' | 'multiple_parents' | 'unsupported_shape' | 'lost_list' | 'kind_changed'; count: number }[];
};
// 导入到已有本体时，warnings 只针对本次变更集：没有差异时为空；lost_list 只计平台里沿用不了的列表；
// kind_changed 是文件里换了种类的已有元素个数，这些元素保持原样，指向它们的引用不进变更集。
// 语法错误：422 import.parse_error，附加字段 line: number | null、column: number | null

// ---------- 手工编辑与影响（PR B） ----------
type EditItem = {
  op: ChangeOp; kind: Kind;
  targetElementId?: string; targetRevision?: number;   // update / delete / restore 必填
  tempRef?: string; fields: ElementFields;
};
type EditRequest = { items: EditItem[]; apply: boolean };
type EditResult = { changeSetId: string; merged: boolean; merge: MergeResult | null };

type ElementRef = { id: string; kind: Kind; label: string; iri: string | null };
type Impact = {
  elementId: string;
  // 直接引用它的在用元素（侧栏"被引用"）
  subtypes: ElementRef[]; relations: ElementRef[]; properties: ElementRef[];
  constraints: ElementRef[]; axioms: ElementRef[]; inverse: ElementRef | null;
  // 删除它时手工保存会一并提出的全部变更（传递闭包，删除确认框用）
  cascade: { op: 'delete' | 'update'; element: ElementRef }[];
};
// 手工保存的补充规则：
// - create 不能带 iri（显式 IRI 只来自导入），否则 422 changeset.invalid_edit；
// - 同一次保存里两项指向同一元素，或某项引用、修改的元素会被本次删除（含级联）一并删除，422 changeset.invalid_edit；
// - 级联按本次修改之后的引用计算：用户在同一次保存里把引用改走的，不再清空或删除；
// - 约束的规则被级联移除光后保留约束（空规则列表合法），不删除；
// - 公理的 create、update、restore 都做三项校验；同一次保存里重复的公理按 422 axiom.invalid。

type PlatformSettings = { reviewMode: 'single' | 'separate' };   // GET /api/settings/platform

// ---------- 版本对比（PR C） ----------
// GET /api/ontologies/{id}/compare?from=<releaseId>&to=<releaseId|working>
// field 是 Element 的字段名（camelCase）；引用字段（parentId、domainId、rangeId、inverseId）的取值是
// { id, label } 或 null，label 取对应那一边版本里的名称；rules、synonyms、turtle 给原值
type FieldChange = { field: string; before: unknown; after: unknown };
type ElementChange = {
  elementId: string; kind: Kind; label: string; iri: string | null;
  change: 'added' | 'removed' | 'changed' | 'restored';
  level: 'breaking' | 'review' | 'compatible';
  fields: FieldChange[];                // 仅 changed；restored 为空，起点版本里没有它的前值
};
type Comparison = {
  from: { releaseId: string; version: number };
  to: { releaseId: string | null; version: number | null };   // 工作版本为 null
  changes: ElementChange[];
  counts: { breaking: number; review: number; compatible: number };
};

// ---------- AI 助手（PR C） ----------
type AssistantRequestCreate = { message: string; context: { page: string; elementId?: string | null } };
type AssistantRequest = {
  id: string; ontologyId: string; message: string;
  context: { page: string; elementId: string | null };
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  step: 'context' | 'model' | 'changeset' | null;
  reply: string | null; changeSetId: string | null; errorCode: string | null;
  dropped: number;                       // 模型提出、但没通过校验而被忽略的操作数
  createdAt: string; finishedAt: string | null;
};
```

## 接口与角色

| 方法与路径 | 角色 | PR |
|---|---|---|
| `POST /api/ontologies/import` | editor（及 reviewer、admin） | A |
| `POST /api/ontologies/{id}/import` | editor（及 reviewer、admin） | A |
| `POST /api/ontologies/{id}/turtle` | editor | B |
| `POST /api/ontologies/{id}/edits` | editor（`apply` 需要 reviewer 且为单人模式） | B |
| `GET /api/ontologies/{id}/elements/{elementId}/impact` | viewer | B |
| `GET /api/settings/platform` | viewer | B |
| `GET /api/ontologies/{id}/compare` | viewer | C |
| `POST /api/ontologies/{id}/assistant/requests` | editor | C |
| `GET /api/assistant/requests/{id}`、`GET /api/ontologies/{id}/assistant/requests` | viewer（只能看自己的请求） | C |

## 错误码补充

| code | HTTP | 含义 |
|---|---|---|
| `import.unsupported_format` | 415 | 不是 Turtle 或 RDF/XML |
| `import.too_large` | 413 | 文件超过 5 MB |
| `import.too_many_triples` | 422 | 三元组超过 50,000 个 |
| `import.parse_error` | 422 | 语法错误，附 `line`、`column` |
| `import.empty` | 422 | 文件里没有任何三元组 |
| `import.axiom_too_large` | 422 | 某条公理超过平台能存的长度（200 万字符） |
| `element.stale` | 409 | 元素在读取之后被修改过 |
| `element.name_taken` | 409 | 局部名或 IRI 已被占用（包括已删除的元素） |
| `element.not_found` | 404 | 沿用 M1 |
| `axiom.invalid` | 422 | 公理片段无法解析、不是恰好一条公理，或本体（或同一次保存）里已有这条公理 |
| `axiom.maps_to_element` | 422 | 片段的内容可以用表单表达 |
| `changeset.self_review` | 403 | 异人审核模式下，审核自己创建的变更集 |
| `assistant.not_found` | 404 | 请求不存在，或不属于当前用户 |

补充约定：

- **来源**：导入生成的元素 `origin = 'import'`；`origin` 的约束随迁移 v0005 一起放宽。
- **已删除元素**：元素详情接口对已删除的元素照常返回，`status = 'deprecated'`。
- **审核模式**：`apply: true` 但当前用户不能自审时（editor，或 separate 模式），不报错，变更集保持 open，`merged = false`。
- **发布校验**：`ReleaseProblem.code` 新增两个码：`release.invalid_inverse`（互逆关系缺失或已删除）、`release.invalid_constraint`（约束的规则指向缺失或已删除的元素）。导入的元素（`explicitIri = true`）不检查中文名和局部名的大小写约定；它们可以没有定义域、值域或数据类型，但如果写了，就必须指向在用的元素。公理不参加发布校验，合并时已经校验过。
