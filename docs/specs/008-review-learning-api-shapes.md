# 008 附录：审核记忆与 AI 预审接口的请求与响应结构

约定同 [001 附录](001-m1-api-shapes.md)、[004 规格](004-ai-alignment.md)、[007 附录](007-m4-api-shapes.md)：
- 字段一律用 camelCase；
- 时间为 ISO 8601 字符串，id 为 uuid 字符串；
- 可空字段写作 `T | null`；
- 错误统一用 problem+json，带稳定的 `code`；
- 分页为 `?limit=&cursor=`，响应 `{ items, nextCursor }`。

本文只列出新增和变化的部分，正文见 [008 规格](008-review-learning-assist.md)。`ChangeItem`、`ChangeSetDetail`、`ItemDecisionPatch`、`BulkDecision` 指 M4 结束时的定义，这里只写新增字段。

新增 HTTP 路由在批次 1 建好，实现合并前返回 501 `http.not_implemented`。

```ts
// ---------- 拒绝理由（批次 1 实现） ----------
type RejectReason = 'out_of_scope' | 'incorrect' | 'duplicate' | 'keep_open';

type ItemDecisionPatch = { /* 现有字段 … */ rejectReason?: RejectReason | null };
// 只有本次的 decision 为 'rejected'，或该项已是 rejected 且本次不改 decision 时，才能带非空值，
// 否则返回 422 changeset.invalid_reason。
// decision 改为 'pending' 或 'accepted' 时，服务端清空 rejectReason。
// 传 null 表示清空理由。

type BulkDecision = { itemIds: string[]; decision: Decision; rejectReason?: RejectReason | null };
// decision 不是 'rejected' 时，rejectReason 必须省略或为 null，否则返回 422 changeset.invalid_reason。

type ChangeItem = { /* 现有字段 … */ rejectReason: RejectReason | null };

// ---------- 被审核记忆挡掉的提议（批次 1 存储，批次 3 写入） ----------
type SuppressedItem = {
  kind: 'entity_type' | 'relation_type' | 'property';
  labelZh: string | null;
  labelEn: string | null;
  cause: 'memory' | 'depends_on_suppressed';
  memoryEntryId: string | null;          // cause = 'memory' 时为命中的条目；依赖被挡时为它所依赖的那条
  dependsOn: string | null;              // cause = 'depends_on_suppressed' 时为被挡类型的名称
};
type ChangeSetDetail = { /* 现有字段 … */ suppressed: SuppressedItem[]; suppressedTotal: number };
// suppressed 最多 200 条；suppressedTotal 是实际被挡的总数。ChangeSetSummary 不变。

// ---------- 审核记忆（批次 2） ----------
type MemoryKind = 'rejected' | 'renamed' | 'kept_apart';
type MemoryElementKind = 'entity_type' | 'relation_type' | 'property';
type ReviewMemoryEntry = {
  id: string;
  ontologyId: string;
  kind: MemoryKind;
  elementKind: MemoryElementKind;        // kept_apart 只有 entity_type
  label: string;                          // 被拒绝的名称 / 改名前的名称 / 提议一方的名称
  detail:
    | { kind: 'rejected'; reason: RejectReason | null; labelEn: string | null; domain: string | null; range: string | null }
    | { kind: 'renamed'; toLabelZh: string; toLabelEn: string | null; elementId: string }
    | { kind: 'kept_apart'; otherLabel: string; otherElementId: string | null };
  sourceChangeSetId: string | null;
  sourceItemId: string | null;
  decidedBy: string | null;
  decidedByName: string | null;           // 同 ChangeSetSummary.createdByName 的取法
  createdAt: string;
  hits: number;
  lastHitAt: string | null;
};
// key（规范化匹配键）只在服务端使用，不对外返回。

// GET /api/ontologies/{id}/review-memory?kind=&q=&limit=&cursor=
//   kind：可选，MemoryKind；q：可选，在 label、toLabelZh、otherLabel 上做不区分大小写的包含匹配，最长 100 字
//   limit：1–200，默认 50；按 createdAt 倒序，同时间按 id
type ReviewMemoryPage = { items: ReviewMemoryEntry[]; nextCursor: string | null; total: number; max: number };
// total 是本体当前的有效条目数（不受 kind、q 影响），max 为 review_memory_max。

// DELETE /api/ontologies/{id}/review-memory/{entryId}            → 204
// POST   /api/ontologies/{id}/review-memory/{entryId}/restore    → 200 ReviewMemoryEntry
// POST   /api/ontologies/{id}/review-memory/clear                → 200 { cleared: number }
// 已删除的条目再次 DELETE 返回 404 review_memory.not_found（不存在、属于别的本体时也是 404）。
// restore 只接受 deletedReason = 'deleted' 的条目，其他返回 409 review_memory.not_restorable；
// 条目仍有效时 restore 原样返回 200。
// restore 把 createdAt 刷新为当前时间、lastHitAt 清空，hits 保留；有效条目超出上限时按正文第 5.6 节淘汰别的条目。

// ---------- AI 预审（批次 6） ----------
type Locale = 'zh-CN' | 'en';
type AssistStatus = 'queued' | 'running' | 'done' | 'partial' | 'failed';
type RiskCode = 'weak_evidence' | 'conflict' | 'duplicate' | 'naming' | 'memory';
type RuleDetail =
  | 'evidence_not_found' | 'no_evidence' | 'low_confidence'
  | 'possible_duplicate' | 'undecided_match'
  | 'kept_fields' | 'stale_target'
  | 'local_name_style' | 'missing_label_en'
  | 'similar_to_rejected';
type AssistRisk = {
  code: RiskCode;
  source: 'rule' | 'ai';                  // memory 只来自 rule
  detail: RuleDetail | null;              // source = 'rule' 时必有
  reason: string | null;                  // source = 'ai' 时必有，最多 300 字
  relatedItemIds: string[];               // 同变更集里相关的项，最多 5 个
  relatedElementIds: string[];            // 相关的已有元素，最多 5 个
  memoryEntryId: string | null;           // similar_to_rejected 时为相似的条目
};
type AssistSuggestion = 'accept' | 'reject' | 'edit' | 'unsure';
type AssistRename = { labelZh?: string; labelEn?: string; localName?: string };   // 至少一个字段
type AssistItem = {
  itemId: string;
  stale: boolean;                         // GET 时由服务端比较指纹得出
  risks: AssistRisk[];
  suggestion: AssistSuggestion | null;    // 只有规则检查的项为 null
  reason: string | null;                  // 最多 300 字
  rename: AssistRename | null;            // 只有 suggestion = 'edit' 时可能非空
};
type AssistGroup = { title: string; itemIds: string[] };   // 最多 12 组，标题最多 40 字；一项最多属于一组
type ReviewAssist = {
  id: string;
  changeSetId: string;
  status: AssistStatus;
  errorCode: string | null;               // partial、failed 时的第一个错误
  aiUsed: boolean;
  truncated: boolean;                     // 有项超出 review_assist_items_max，只做了规则检查
  locale: Locale;
  requestedBy: string | null;
  requestedByName: string | null;
  createdAt: string;
  finishedAt: string | null;
  summary: string | null;                 // 最多 600 字；aiUsed = false 时为 null
  groups: AssistGroup[];
  items: AssistItem[];                    // 按变更项 seq 排序，只含类型、关系、属性项；queued、running 时为空数组
  // GET 时，变更集仍为 open 的，source = 'rule' 的风险按当前状态重新计算；source = 'ai' 的取保存的结果
  counts: { total: number; aiReviewed: number; withRisks: number; suggestReject: number; suggestEdit: number; stale: number; dropped: number };
  // withRisks、suggestReject、suggestEdit 只数 stale = false 的项
};

// POST /api/change-sets/{id}/review-assist   body: { locale: Locale }   → 202 ReviewAssist（status = 'queued'）
// GET  /api/change-sets/{id}/review-assist                              → 200 ReviewAssist | null（最近一次）
```

模型输出结构（服务端内部，`ai/schemas.py` 的 `ReviewAssistOut`，不对外暴露）：

```ts
type ReviewAssistOut = {
  summary: string;
  groups: { title: string; items: string[] }[];          // items 为短引用 i1、i2……
  items: {
    ref: string;
    risks: { code: 'weak_evidence' | 'conflict' | 'duplicate' | 'naming'; reason: string; related?: string[] }[];
    // related 为短引用（i…）或元素局部名
    suggestion: AssistSuggestion;
    reason: string;
    rename?: AssistRename;
  }[];
};
type ReviewAssistSummaryOut = {
  summary: string;
  groups: { title: string; from: { batch: number; group: number }[] }[];
};
```

## 接口与角色

| 方法与路径 | 角色 | 令牌作用域 | 批次 |
|---|---|---|---|
| `PATCH /api/change-sets/{id}/items/{itemId}`、`POST …/decisions` 的 `rejectReason` | 同现有：reviewer | 不接受令牌 | 1 |
| `GET /api/change-sets/{id}` 的 `suppressed`、`suppressedTotal`、项的 `rejectReason` | 同现有：登录用户 | 不接受令牌 | 1（存储）、3（写入） |
| `GET /api/ontologies/{id}/review-memory` | viewer | 不接受令牌 | 2 |
| `DELETE /api/ontologies/{id}/review-memory/{entryId}`、`POST …/{entryId}/restore`、`POST …/review-memory/clear` | reviewer | 不接受令牌 | 2 |
| `POST /api/change-sets/{id}/review-assist` | editor | 不接受令牌 | 6 |
| `GET /api/change-sets/{id}/review-assist` | viewer | 不接受令牌 | 6 |

角色按现有层级包含：admin ⊇ reviewer ⊇ editor ⊇ viewer。当前的审核人分工设置（`review_mode = separate`）不影响记忆管理和预审：预审不是审核决定，记忆管理也不在变更集内。

## 错误码补充

| code | HTTP | 含义 |
|---|---|---|
| `http.not_implemented` | 501 | 接口已定义、实现尚未合并（只在本里程碑开发期间出现） |
| `changeset.invalid_reason` | 422 | `rejectReason` 与决定不一致（非拒绝时带了理由） |
| `changeset.closed` | 409 | 沿用：变更集已合并或已拒绝，不能发起预审 |
| `changeset.not_found` | 404 | 沿用 |
| `review_memory.not_found` | 404 | 条目不存在、已删除，或不属于这个本体 |
| `review_memory.not_restorable` | 409 | 只有被用户删除的条目能撤销；被清空、淘汰或覆盖的不能 |
| `review_assist.running` | 409 | 这个变更集已有一次排队中或进行中的预审（含并发插入撞到部分唯一索引的情况） |
| `review_assist.rate_limited` | 429 | 超过每人每小时 `review_assists_per_hour` 次；带 `Retry-After` |
| `review_assist.timeout` | 无（预审的 `errorCode`） | 预审任务超过 `review_assist_timeout_seconds`；已完成批次的结果保留，状态为 `partial` |
| `ai.unavailable`、`ai.invalid_output` | 无（预审的 `errorCode`） | 沿用 002：某批模型调用失败，状态为 `partial` |

补充约定：

- AI 未配置时，`POST …/review-assist` 照常返回 202，结果只有规则检查，`aiUsed = false`，`errorCode = null`，状态为 `done`。不返回 `ai.not_configured`。
- `status = 'failed'` 只在任务本身出错（例如读上下文失败）时出现。这时 `items` 为空，界面显示错误状态和"重试"。
- 审计事件：`review_memory.collected`（合并时，带条目数）、`review_memory.deleted`、`review_memory.restored`、`review_memory.cleared`（带条数）。预审不记审计，模型调用照常记在 `ai.runs`，purpose 为 `review.assist`、`review.assist.summary`。
- 跳过码：本规格不新增合并跳过码。
