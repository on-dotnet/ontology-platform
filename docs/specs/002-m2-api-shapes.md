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

// RDF 取值，保留原写法；datatype 为 xsd 局部名（如 'integer'）或完整 IRI
type RdfValue = { iri: string } | { lexical: string; datatype: string | null; lang: string | null };
type LangText = { lang: string | null; text: string };
type NodeKind = 'IRI' | 'Literal' | 'BlankNode' | 'BlankNodeOrIRI' | 'BlankNodeOrLiteral' | 'IRIOrLiteral';

type ConstraintRule = {
  pathId: string;                       // 属性或关系元素
  minCount?: number; maxCount?: number;
  datatype?: string; classId?: string; nodeKind?: NodeKind;
  in?: RdfValue[];
  minInclusive?: RdfValue; maxInclusive?: RdfValue; minExclusive?: RdfValue; maxExclusive?: RdfValue;
  minLength?: number; maxLength?: number; pattern?: string; flags?: string;
  message?: LangText[];
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
type ConstraintRuleFields = Omit<ConstraintRule, 'pathId' | 'classId'> & { pathRef: string; classRef?: string };
type ElementFields = M1ElementFields & {
  iri?: string | null; inverseRef?: string | null;
  rules?: ConstraintRuleFields[] | null; turtle?: string | null; subjectRef?: string | null;
};
type ChangeOp = 'create' | 'update' | 'delete' | 'restore';
type ChangeItem = M1ChangeItem & { op: ChangeOp; kind: Kind; flags: ('evidence_not_found' | 'possible_duplicate' | 'non_standard')[] };
type ChangeSetSource = 'ai_extraction' | 'ai_assistant' | 'manual' | 'import';
type MergeSkipCode = 'changeset.stale_target' | 'changeset.dependency_skipped' | 'changeset.invalid_item' | 'changeset.has_dependents';

// ---------- 导入（PR A） ----------
// POST /api/ontologies/import          multipart：file，name?，key?       → 201 ImportResult
// POST /api/ontologies/{id}/import     multipart：file                   → 200 ImportResult
// POST /api/ontologies/{id}/turtle     { turtle: string }                → 200 ImportResult（PR B）
type ImportResult = {
  ontology: OntologySummary;
  changeSetId: string | null;           // 没有差异时为 null
  counts: { create: number; update: number; delete: number; restore: number };
  warnings: { code: 'non_standard' | 'multiple_parents' | 'unsupported_shape'; count: number }[];
};
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
  subtypes: ElementRef[]; relations: ElementRef[]; properties: ElementRef[];
  constraints: ElementRef[]; axioms: ElementRef[]; inverse: ElementRef | null;
};

type PlatformSettings = { reviewMode: 'single' | 'separate' };   // GET /api/settings/platform

// ---------- 版本对比（PR C） ----------
// GET /api/ontologies/{id}/compare?from=<releaseId>&to=<releaseId|working>
type FieldChange = { field: string; before: unknown; after: unknown };
type ElementChange = {
  elementId: string; kind: Kind; label: string; iri: string | null;
  change: 'added' | 'removed' | 'changed' | 'restored';
  level: 'breaking' | 'review' | 'compatible';
  fields: FieldChange[];                // 仅 changed / restored
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
  createdAt: string; finishedAt: string | null;
};
```

## 接口与角色

| 方法与路径 | 角色 | PR |
|---|---|---|
| `POST /api/ontologies/import` | editor | A |
| `POST /api/ontologies/{id}/import` | editor | A |
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
| `element.stale` | 409 | 元素在读取之后被修改过 |
| `element.name_taken` | 409 | 局部名或 IRI 已被占用（包括已删除的元素） |
| `element.not_found` | 404 | 沿用 M1 |
| `axiom.invalid` | 422 | 公理片段无法解析，或不是恰好一条公理 |
| `axiom.maps_to_element` | 422 | 片段的内容可以用表单表达 |
| `changeset.self_review` | 403 | 异人审核模式下，审核自己创建的变更集 |
| `assistant.not_found` | 404 | 请求不存在，或不属于当前用户 |

补充约定：

- **来源**：导入生成的元素 `origin = 'import'`；`origin` 的约束随迁移 v0005 一起放宽。
- **已删除元素**：元素详情接口对已删除的元素照常返回，`status = 'deprecated'`。
- **审核模式**：`apply: true` 但当前用户不能自审时（editor，或 separate 模式），不报错，变更集保持 open，`merged = false`。
