# 001 附录：M1 接口的请求与响应结构

字段一律 camelCase；时间为 ISO 8601 字符串；id 为 uuid 字符串；可空字段写作 `T | null`。错误统一为 problem+json。

列表：资料列表 `GET /api/documents` 按架构约定分页（`?limit=&cursor=`，响应 `{ items, nextCursor }`）；本体、元素、变更集、版本的列表在 M1 数据量小，直接返回数组。

```ts
type Kind = 'entity_type' | 'relation_type' | 'property';
type Datatype = 'string' | 'integer' | 'decimal' | 'boolean' | 'date' | 'dateTime';
type Synonym = { lang: 'zh' | 'en'; text: string };

// ---------- ontology ----------
type OntologySummary = {
  id: string; key: string; name: string; description: string | null; baseIri: string;
  entityTypeCount: number; relationTypeCount: number; propertyCount: number;
  openChangeSetCount: number; activeReleaseId: string | null; activeReleaseVersion: number | null;
  createdAt: string; updatedAt: string;
};
type OntologyCreate = { name: string; key?: string; description?: string };

type Element = {
  id: string; ontologyId: string; kind: Kind; localName: string; iri: string;
  labelZh: string; labelEn: string | null; definitionZh: string | null; definitionEn: string | null;
  synonyms: Synonym[];
  parentId: string | null; domainId: string | null; rangeId: string | null;   // 按 kind 使用
  datatype: Datatype | null; unit: string | null; required: boolean; multiple: boolean;
  status: 'active' | 'deprecated'; origin: 'ai' | 'manual'; revision: number;
  createdAt: string; updatedAt: string;
};
type ElementDetail = Element & {
  provenance: {                       // 由哪些已合并的变更项产生或修改
    changeSetId: string; changeSetTitle: string; itemId: string; op: 'create' | 'update';
    mergedAt: string; evidence: Evidence[];
  }[];
};

type GraphNode = { id: string; label: string; localName: string; parentId: string | null; propertyCount: number };
type GraphEdge = { id: string; source: string; target: string; kind: 'relation' | 'subclass'; label: string | null };
type Graph = { nodes: GraphNode[]; edges: GraphEdge[] };

// ---------- change sets ----------
type ElementFields = {                 // proposed / edited 的字段（都可选，按 kind 校验）
  localName?: string; labelZh?: string; labelEn?: string | null;
  definitionZh?: string | null; definitionEn?: string | null; synonyms?: Synonym[];
  parentRef?: string | null; domainRef?: string | null; rangeRef?: string | null;  // 元素 id 或 temp_ref
  datatype?: Datatype | null; unit?: string | null; required?: boolean; multiple?: boolean;
};
type Evidence = {
  id: string; documentId: string; chunkId: string; quote: string;
  charStart: number | null; charEnd: number | null;   // 在分块文本中的位置，未找到为 null
};
type ChangeItem = {
  id: string; seq: number; op: 'create' | 'update'; kind: Kind;
  targetElementId: string | null; tempRef: string | null;
  proposed: ElementFields; edited: ElementFields | null;
  before: ElementFields | null;          // update 时目标元素当前值，便于对比
  decision: 'pending' | 'accepted' | 'rejected';
  confidence: number | null; rationale: string | null;
  flags: ('evidence_not_found' | 'possible_duplicate')[];
  note: string | null; decidedBy: string | null; decidedAt: string | null;
  appliedElementId: string | null;
  evidence: Evidence[];
  resolution: ItemResolution | null;   // 规格 004 第 5.4 节：AI 识别的变更集里，合并时会怎样（合并后为实际结果）
};
type ItemResolution = {
  mode: 'create' | 'into' | 'rename' | 'update';
  elementId: string | null; elementLabel: string | null;   // into、update：并入或追加到的元素
  localName: string | null;                                // rename：合并时使用的局部名
  keptFields: string[];                                    // 目标已有值、合并时保持不变的字段
};
type ChangeSetSummary = {
  id: string; ontologyId: string; title: string;
  source: 'ai_extraction' | 'ai_assistant' | 'manual';
  documentId: string | null; status: 'open' | 'merged' | 'rejected';
  counts: { total: number; pending: number; accepted: number; rejected: number };
  createdAt: string; mergedAt: string | null;
};
type ChangeSetDetail = ChangeSetSummary & { items: ChangeItem[]; resolutionToken: string };
type MergeRequest = { resolutionToken?: string | null };   // 合并时带上详情里的 resolutionToken
type ItemDecisionPatch = { decision?: 'pending' | 'accepted' | 'rejected'; edited?: ElementFields | null; note?: string | null };
type BulkDecision = { itemIds: string[]; decision: 'pending' | 'accepted' | 'rejected' };
type MergeResult = { applied: number; skipped: { itemId: string; code: 'changeset.stale_target' | 'changeset.dependency_skipped' | 'changeset.invalid_item' }[] };

// ---------- releases ----------
type ReleaseSummary = {
  id: string; ontologyId: string; version: number; title: string; notes: string | null;
  elementCount: number; isActive: boolean; createdBy: string | null; createdAt: string;
};
type ReleaseCreate = { title: string; notes?: string };
type ReleaseProblem = { code: string; elementId: string | null; message: string };
// 发布校验失败：422 problem+json，code = 'release.invalid'，附加字段 problems: ReleaseProblem[]

// ---------- documents ----------
type DocumentStatus = 'queued' | 'parsing' | 'extracting' | 'ready' | 'failed';
type DocumentInfo = {
  id: string; ontologyId: string; filename: string; mediaType: string; sizeBytes: number;
  status: DocumentStatus;
  sha256: string;
  progress: { step: string; done: number; total: number };   // step: parse | terms | types | relations | changeset
  errorCode: string | null; pageCount: number | null; charCount: number | null;
  changeSetId: string | null; uploadedBy: string; createdAt: string; updatedAt: string;
};
type DocumentList = { items: DocumentInfo[]; nextCursor: string | null };
type Chunk = { id: string; documentId: string; seq: number; text: string; page: number | null; heading: string | null; charCount: number };

// ---------- ai / workbench ----------
type AiStatus = { configured: boolean; reachable: boolean | null; model: string | null };
type WorkbenchSummary = {
  pendingChangeSets: number; entityTypes: number; processingDocuments: number;
  recentActivity: { id: string; action: string; occurredAt: string; actorName: string | null; targetType: string | null; targetId: string | null }[];
};
```

错误码补充：`ontology.not_found`、`ontology.key_taken`、`element.not_found`、`changeset.not_found`、`changeset.closed`（已合并或已拒绝的变更集不能再改）、`changeset.pending_items`、`changeset.invalid_edit`、`changeset.resolution_changed`（本体在审核人打开变更集之后有了变化，合并结果会与页面上显示的不同）、`release.not_found`、`release.invalid`、`documents.not_found`、`documents.too_large`、`documents.unsupported_type`、`documents.not_failed`、`documents.needs_ocr`、`documents.unreadable`（读不出文字：文件损坏、解析进程异常退出，或扫描件转写后仍没有文字）、`documents.parse_timeout`（解析超过 180 秒）、`documents.too_long`（分块后超过 200,000 字，`charCount` 为实际字数）、`documents.too_many_pages`（扫描件超过 100 页，`pageCount` 为实际页数）、`ai.not_configured`、`ai.unavailable`、`ai.invalid_output`（模型返回的结构不合规）、`internal.error`（资料处理时的意外错误）。资料的 `errorCode` 取上面 `documents.*`、`ai.*`、`ontology.not_found`、`changeset.invalid_item` 或 `internal.error` 之一。

补充约定：

- 上传到不存在的本体返回 404 `ontology.not_found`。
- 资料没识别出任何内容时状态为 `ready`、`changeSetId` 为 null。
- 拒绝整个变更集返回 `ChangeSetSummary`；批量决定返回 `ChangeSetDetail`；`GET /api/releases/{id}` 返回 `ReleaseSummary`。变更项不属于该变更集时返回 `changeset.not_found`。
- 变更集响应里的 `proposed` / `edited` 只包含设置过的键；OpenAPI 中这些键生成为 `T | null`。
- `ReleaseProblem.code`：`release.empty`（工作版本没有任何元素，`elementId` 为 null）、`release.cyclic_hierarchy`、`release.invalid_parent`、`release.invalid_domain`、`release.invalid_range`、`release.invalid_datatype`、`release.invalid_local_name`、`release.missing_label`。
- 工作台 `recentActivity` 最多 10 条，只含 `ontology.*`、`document.*`、`changeset.*`、`release.*`；登录类事件只留在审计日志里。
