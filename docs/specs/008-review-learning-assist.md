# 008 从审核中学习与 AI 协助审核

级别：L2。批次 1 含数据库迁移；批次 2、3 改 AI 识别的写入路径和审核流程；批次 6 在审核流程中加入 AI 预审；批次 4、8 改 `dev.ps1`。批次 5、7 是 L1，各批级别见第 12 节。
关联：[路线图](../roadmap.md)"从审核中学习与 AI 协助审核"一行、[架构](../architecture.md)、[004 AI 对齐规格](004-ai-alignment.md)、[接口附录](008-review-learning-api-shapes.md)、议题 #41。

本文只是规格，不含实现。执行者写"Codex"的批次，按本文和附录就能独立实现。写"Codex 实现 + Claude 审"的批次涉及红线或跨模块的权衡：设计已在本文定下，实现交给 Codex，Claude 逐行审 diff 后才提交。实现中遇到本文没定的取舍，停下来交回 Claude。

**红线（所有批次）**：AI 不直接改本体，一切写入只经变更集，人审核后才生效。不得有自动接受、自动合并或绕过审核的路径。AI 的预审结果只是附在变更项上的参考信息，不改变更项本身（`decision`、`edited`、`note`、`match_decision` 都不动）。提示词里不出现中文（`test_the_prompts_give_examples_in_generic_words_only` 及本规格新增的同类测试）。发给模型的内容不含连接信息与凭据。

## 1 用户能做什么与验收路线

本里程碑结束时，用一个已有本体走一遍：

1. **拒绝时说明原因（可选）。** 审核人拒绝一项时，可以选一个理由："不属于本体范围""不正确""与已有元素重复""暂不决定"，也可以不选。
   - 验收：单项和批量拒绝都能带理由；改回待定或接受后理由清空；不选理由的拒绝和现在完全一样。
2. **AI 记住审核决定。** 合并一个 AI 识别的变更集后，平台把其中的审核决定记进这个本体的"审核记忆"，包括三类：被拒绝的新元素（理由为"重复"或"暂不决定"的除外）、改了名才接受的新元素、审核人判定"不是同一概念"的一对类型。
   - 验收：合并后记忆里出现对应条目，带来源变更集、决定人和时间；整个变更集被拒绝时不记。
3. **下次识别不再提同样的东西。** 再上传资料时：
   - 记忆里被拒绝过的类型、关系、属性不再出现在变更集里，审核页提示"按审核记忆，有 N 项没有再提出"，可以展开查看；
   - 改过名的类型用审核人定的名字或直接引用已有元素；
   - 判过"不是同一概念"的一对不再标疑似重复。
   - 验收：第 10.4 节的不花钱用例全部通过；第 10.2 节付费评测达到目标。
4. **查看和管理审核记忆。** 审核列表页进入"审核记忆"，按类别查看全部条目、命中次数、来源。审核人可以删除单条（可撤销）或清空（需确认）。删除后 AI 不再参考这条。
   - 验收：viewer 只能看；reviewer、admin 能删除、撤销、清空；每次删除、撤销、清空都记审计。
5. **AI 预审。** 编辑以上角色在审核页点"✦ AI 预审"。几十秒后页面顶部出现摘要卡片，内容是一段简短摘要和按主题分的组。每项卡片上显示风险标记（证据弱、与已有元素冲突——包括父类、不相交声明、域与值域——疑似重复、命名不一致、与拒绝过的相似）和"✦ 建议接受 / 拒绝 / 修改 / 拿不准"及理由。"按建议修改"只把建议的名称预填到编辑框，由审核人保存。
   - 验收：预审前后 `change_items` 逐字段不变；不提供"接受全部建议"；"接受全部高置信度项"跳过有风险的项；改过的项标"预审之后已修改"；AI 未配置时只给规则检查的结果。

## 2 范围

**做：**

- `change_items` 新增可选的拒绝理由。
- 新表 `ontology.review_memory`，在合并 `ai_extraction` 变更集时采集。
- 识别流水线读取审核记忆：代码护栏 M1–M3 加上提示词。
- 变更集记下被记忆挡掉的提议（`suppressed`）。
- 审核记忆页：查看、删除、撤销、清空。
- AI 预审：规则检查加模型检查，结果存在 `ai.review_assists`，审核页展示。
- 评测：按期望审核的场景，比较记忆开、关；预审建议的准确率与召回率。
- 文档更新。

**不做（写明原因，避免实现时扩大范围）：**

- 来源为 `ai_assistant`、`ai_qa`、`mcp`、`ai_binding`、`manual`、`import` 的变更集不采集记忆，这些来源的提议也不使用记忆。助手和问答是用户主动要求的，挡掉会让用户困惑；绑定有自己的流程。合并任何来源的变更集都会触发第 5.5 节的"覆盖"规则。
- 只从新建项（`op = create`）学习，不从 `update` 项（例如补同义词、补定义）学习。不学除改名以外的编辑（定义、父类、值域改写）。
- 不建审核统计页或审核人画像。
- 不用能力问题检验合并的影响（`cq → ai` 已有依赖，反过来会形成循环）。
- 不加 MCP 工具，外部智能体不能读写审核记忆或预审。
- 预审只看类型、关系、属性三种变更项；公理、约束、绑定、指标等其他种类的项既不做规则检查也不做模型检查，界面上照常显示、没有预审标记。公理表达式的冲突判断留到以后。
- 其他来源的变更项也能带拒绝理由，理由会保存和显示，但不进记忆。
- 不在识别完成后自动预审。

## 3 决定与理由

| 编号 | 决定 | 理由 |
|---|---|---|
| D1 | 审核信号沿用 `ontology.change_items` 现有字段（`decision`、`edited`、`note`、`match_decision`、`decided_by`、`decided_at`、`applied_element_id`），不建审核事件表；只新增一列 `reject_reason` | 现有字段已能还原每项的最终决定；拒绝理由是唯一缺的结构化信号，`note` 是自由文本，不可靠 |
| D2 | 审核记忆是派生数据，单独存一张表 `ontology.review_memory`，不每次从历史变更项现算 | 需要上限、软删除、命中次数；现算要扫全部历史，用户的删除也无处保存 |
| D3 | 只在 `ai_extraction` 变更集**合并**时采集；整个变更集被拒绝（`POST …/reject`）时不采集 | 整体拒绝通常是"这次识别不要了"（资料选错、模型故障），不是对每一项的判断 |
| D4 | 采集三类：`rejected`、`renamed`、`kept_apart`。`match_decision = same` 的"已并入"不采集 | 并入后名称已成为已有元素的同义词，G1（004 §4.3 名称精确命中）下次就能命中，再记一遍是重复 |
| D5 | 拒绝理由可选，取值 `out_of_scope`、`incorrect`、`duplicate`、`keep_open`。理由为 `duplicate`、`keep_open` 的拒绝不进记忆；不选理由的照常进记忆 | 必选会拖慢审核；"重复"由对齐负责，"暂不决定"不是否定 |
| D6 | 精确命中由代码挡（第 6.2 节 M1–M3），相近变体靠提示词提醒；记忆为空时提示词逐字节不变 | 代码挡得可靠、可测；记忆为空时，现有录制照常回放，评测基线不受影响 |
| D7 | 消解阶段的提示词不放记忆；`kept_apart` 的一对由代码直接判为不同 | 用代码判断比让模型读记忆更可靠，也省 token |
| D8 | 每个本体最多 `review_memory_max = 500` 条有效条目，超出时淘汰最久未命中的；每次模型调用最多带 `review_memory_prompt_max = 40` 行 | 有上限才能控制提示词长度和花费；500 条足够覆盖一个本体几十份资料的审核 |
| D9 | 后面的接受覆盖前面的拒绝：任何来源的变更集合并后，若新建或改名得到的元素命中 `rejected` 条目，就软删除该条目（`superseded`） | 审核人后来改主意，记忆不能继续挡 |
| D10 | 审核记忆归 `ontology` 模块；AI 只经 `ontology.review_memory_for` 读冻结副本，经 `record_memory_hits` 记命中 | 模块之间只调用服务；变更集、合并和记忆在同一模块，采集能在合并事务和本体锁内完成 |
| D11 | 预审结果存在 `ai.review_assists`，不写 `change_items`。用每项的指纹判断结果是否过期 | 红线：预审只是参考；审核人改过某项后，旧建议不能冒充对新内容的判断 |
| D12 | 预审由编辑以上角色手动发起，同一变更集同时只跑一次，每人每小时最多 `review_assists_per_hour = 20` 次 | 模型调用要花钱；审核人自己决定哪些变更集值得预审 |
| D13 | AI 未配置或模型调用全部失败时，照样给出规则检查的结果（`aiUsed = false`） | 规则检查不花钱，对审核也有用；e2e 不接模型也能覆盖这条路径 |
| D14 | 发给预审模型的只有：资料证据的引文（每项最多 2 条，每条截到 200 字）、变更项的名称、定义和结构，工作版本的元素摘要（最多 400 个），以及 `rejected` 记忆（最多 60 条）。不发数据源（catalog）证据、审核人备注、绑定的物理名称和连接信息 | 引文在识别时已经发给过模型，不新增暴露面；数据源的表名、列名和连接信息不该出平台 |
| D15 | 不提供"接受全部建议"。有效预审存在时，"接受全部高置信度项"跳过有风险、建议拒绝或建议修改的项 | 防止审核人对 AI 结论照单全收；批量操作只会更保守 |
| D16 | 新提示词放在新文件 `ai/memory_prompts.py`、`ai/review_prompts.py`，不改 `ai/prompts.py` | 批次之间文件范围不重叠；`prompts.py` 的评测基线不受影响 |
| D17 | 本里程碑只加一个迁移，放在批次 1；编号在转 ready 前按当时 main 的迁移头确定。当前头为 `v0012_m4_qa_metrics`（revision `0012`），新迁移为 v0013 | 与 M3、M4 一致：迁移只在第一批，后续批次互不冲突 |
| D18 | 评测新增"按期望审核"场景，用 `expected.toml` 模拟一个一致的审核人，比较记忆开、关两种情况 | 能重复、能比较，不需要真人审核 |

## 4 交付顺序

批次 1（骨架与迁移）→ 批次 2（采集与管理）和批次 3（流水线使用记忆）并行 → 批次 4（记忆评测）、批次 5（记忆界面）、批次 6（预审后端）三者并行（都在 2 之后，6 还在 3 之后）→ 批次 7（预审界面，在 5、6 之后）→ 批次 8（预审评测、e2e、文档）。详见第 12.3 节。

## 5 审核信号与审核记忆

### 5.1 现有信号

| 信号 | 位置 | 用途 |
|---|---|---|
| 项被拒绝 | `change_items.decision = 'rejected'` | `rejected` 条目 |
| 拒绝理由 | `change_items.reject_reason`（新增） | 决定是否进记忆，并显示在记忆页 |
| 改名后接受 | `decision = 'accepted'`，`edited` 里的 `labelZh` 与 `proposed` 不同，合并后 `applied_element_id` 非空 | `renamed` 条目 |
| 判为不同 | `match_decision = 'different'`，对齐记录 `match_kind = 'possible'`，另一方为 `match_element_id` 或 `match_item_id` | `kept_apart` 条目 |
| 判为同一 | `match_decision = 'same'` | 不采集（D4） |

### 5.2 拒绝理由

- `ItemDecisionPatch` 与 `BulkDecision` 新增可选字段 `rejectReason`，取值见 D5。
  - 只有 `decision` 为 `rejected`（本次请求设置的，或该项已是这个状态）时才能带；否则返回 422 `changeset.invalid_reason`。
  - 本次请求把决定改成 `pending` 或 `accepted` 时，服务层把 `reject_reason` 清空。
- `POST /api/change-sets/{id}/reject` 不带理由，整个拒绝也不进记忆（D3）。
- 不加"`reject_reason` 非空时 `decision` 必须是 `rejected`"这类跨列检查约束。上一版程序把项改回接受时不会清空这一列，加了约束会让旧程序报错。采集只看 `decision = 'rejected'` 的项，残留的理由不会产生影响。

### 5.3 数据模型：`ontology.review_memory`

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | uuid PK | |
| `ontology_id` | uuid FK → `ontology.ontologies`，`on delete cascade` | |
| `kind` | text，检查约束 `rejected` / `renamed` / `kept_apart` | |
| `element_kind` | text，检查约束 `entity_type` / `relation_type` / `property` | `kept_apart` 只有 `entity_type` |
| `key` | text not null | 匹配键，见第 5.4 节 |
| `label` | text not null | 展示用：被拒绝的名称；改名前的名称；`kept_apart` 中提议一方的名称 |
| `detail` | jsonb not null default `'{}'` | 按 `kind` 区分，见下文 |
| `source_change_set_id` | uuid FK → `ontology.change_sets`，`on delete set null` | |
| `source_item_id` | uuid FK → `ontology.change_items`，`on delete set null` | |
| `decided_by` | uuid，可空 | 引用用户的方式照 `change_items.decided_by` 的现有做法 |
| `created_at` | timestamptz not null | 首次采集或再次采集（复活）的时间 |
| `hits` | integer not null default 0 | |
| `last_hit_at` | timestamptz，可空 | |
| `deleted_at` | timestamptz，可空 | 软删除 |
| `deleted_reason` | text，可空，检查约束 `deleted` / `cleared` / `evicted` / `superseded` | |
| `deleted_by` | uuid，可空 | 用户删除或清空时有值 |

- 唯一约束：`(ontology_id, kind, element_kind, key)`，**包括已软删除的行**。同一个键再次采集时，复活这一行：清空 `deleted_*`，更新 `label`、`detail`、来源与 `created_at`，`hits` 归零，`last_hit_at` 清空。这样表的行数不超过不同键的个数。
- 索引：`(ontology_id) where deleted_at is null`。
- `detail` 的内容：
  - `rejected`：`{ reason: RejectReason | null, labelEn: string | null, domain: string | null, range: string | null }`，其中 `domain`、`range` 是关系、属性的域和值域的类型名称；
  - `renamed`：`{ toLabelZh: string, toLabelEn: string | null, elementId: uuid }`；
  - `kept_apart`：`{ otherLabel: string, otherElementId: uuid | null }`。

### 5.4 匹配键

所有键都由 `ai/candidates.py` 的 `normalize` 与 `main_name` 规则计算（NFKC、小写、去空白；主名称取中文名，没有中文名时取英文名）。函数放在 `ontology/review_memory.py`，是纯函数。`ontology` 不导入 `ai`，所以批次 1 把这两条规则复制成 `ontology/review_memory.py` 里的私有函数，并加一个测试，断言两边对同一组样例结果相同。

| 元素 | 键 |
|---|---|
| 类型 | `t:` + 主名称键 |
| 关系 | `r:` + 域主名称键 + 竖线 + 关系主名称键 + 竖线 + 值域主名称键 |
| 属性 | `p:` + 域主名称键 + 竖线 + 属性主名称键 |
| 一对类型（`kept_apart`） | `k:` + 两个类型主名称键按字典序排列，以两个竖线连接 |

"竖线"即字符 U+007C。例如 `r:炉次|产出|钢卷`、`k:钢包||钢包车`。

改名条目的键是**改名前**的类型键。

### 5.5 采集规则（合并时，批次 2）

在 `merge._apply_change_set` 结束、状态置为 `merged` 之前，于同一事务和本体锁内执行。

先覆盖、后采集；本次采集写入的键不会被本次的覆盖删掉。

**覆盖（任何来源）：** 对本次合并中按 create 或 restore 生效的元素，以及被改名的元素，计算它们的最终键。命中有效的 `rejected` 条目时，软删除该条目，`deleted_reason = 'superseded'`。

**采集（只对 `source = 'ai_extraction'`）：** 逐项计算，只看 `op = 'create'` 的项。

1. `decision = 'rejected'`，且 `reject_reason` 为空、`out_of_scope` 或 `incorrect`，生成 `rejected` 条目。元素种类为类型、关系或属性时采集，其他种类不采集。项带任何对齐记录（`match_kind` 为 `same`、`possible` 或 `name`）时不采集：这种拒绝多半是因为与已有元素重复，记下名称会在 M1 里误挡这个概念。合并时因依赖被跳过的项（`changeset.dependency_skipped`）不算被拒绝。
2. `decision = 'accepted'`，最终生效为新建元素（`applied_element_id` 非空，且合并计划的动作是 create），且 `edited.labelZh` 存在并与 `proposed.labelZh` 的键不同：只对类型生成 `renamed` 条目。关系、属性的改名不采集，因为它们的键依赖域和值域，复用价值低。
3. `match_kind = 'possible'` 且 `match_decision = 'different'`：生成 `kept_apart` 条目，另一方取 `match_element_id` 对应元素的名称（合并时读取），或取 `match_item_id` 对应项的最终名称。

一次合并里，同一个键只保留最后一项。采集结果写入时按第 5.3 节复活或插入，之后执行第 5.6 节的淘汰。

审计：每次合并若有采集，记一条 `review_memory.collected`，带条目数，不逐条记。

### 5.6 上限与淘汰

- 插入或复活后，如果有效条目数超过 `review_memory_max`，按 `coalesce(last_hit_at, created_at)` 从旧到新软删除多出的条目，`deleted_reason = 'evicted'`。
- 撤销删除也走同一淘汰规则。撤销时把 `created_at` 刷新为当前时间、`last_hit_at` 清空，`hits` 保留，所以刚撤销的那条排在最新，不会立即被淘汰（测试：满额时撤销一条命中过的旧条目，它不被淘汰）。

### 5.7 用户管理

- 列表：所有能读这个本体的登录用户可看，按 `kind` 筛选，按标签模糊搜索，按 `created_at` 倒序分页。响应带有效总数和上限。
- 删除单条：reviewer、admin。软删除，`deleted_reason = 'deleted'`，审计 `review_memory.deleted`。界面给轻提示和"撤销"。
- 撤销：只能撤销 `deleted_reason = 'deleted'` 的条目。复活后审计 `review_memory.restored`；对其他原因删除的条目返回 409 `review_memory.not_restorable`。
- 清空：reviewer、admin。软删除本体的全部有效条目，`deleted_reason = 'cleared'`，审计 `review_memory.cleared`（带条数）。需要确认对话框，不可撤销（界面上）。
- 已删除的条目不在列表里显示，也不提供"回收站"。

## 6 识别流水线怎样使用记忆（批次 3）

### 6.1 读取

`make_extractor` 在取 `list_alignment_candidates` 的同一时刻调用 `ontology.review_memory_for(db, ontology_id)`，得到冻结副本 `ReviewMemory`，作为新的可选参数 `memory` 传给 `Extractor.run`。

- `run` 的返回类型不变，仍是提议列表。`suppressed` 与命中的条目经新的可选出参 `outcome: MemoryOutcome | None` 带出（可变数据类，`run` 往里填）。现有调用方和测试不用改。
- 命中在写变更集的那个事务里记（`record_memory_hits` 对已删除或已淘汰的条目 id 静默忽略，不报错也不复活）：调用 `create_change_set` 时传入 `suppressed`，紧接着调用 `record_memory_hits`。提议为空、提前返回时，在返回前单独记一次命中。重放已有变更集的路径不调用模型，也不记命中。
- 记忆和对齐候选一样，在加本体锁之前读取，锁内不复核。同一时刻另一次合并新采集的条目，下次识别才会用到。

评测里用内存中的 `ReviewMemory`，不访问数据库（第 10.1 节）。

### 6.2 代码护栏（纯函数，与 004 §4.3 的 G1–G8 并列）

| 编号 | 时机 | 规则 |
|---|---|---|
| M1 | `build_proposals` 生成提议前 | 新建类型的主名称键命中 `rejected` 条目时，不提出；引用它的关系、属性一并不提出；以它为父类的新类型只去掉父类引用，其他照常。新建关系、属性的键命中 `rejected` 条目时，不提出。每个被挡的提议记一条 `SuppressedItem`（`cause = 'memory'` 或 `'depends_on_suppressed'`），命中的条目计一次命中。已有元素的 update 项不受 M1 影响 |
| M2 | 对齐时，G1 之前 | 模型类型的主名称键命中 `renamed` 条目，并且 `detail.elementId` 对应的元素仍有效时，把它当作对该元素的名称精确命中（同 G1），不提议新建。`_maybe_update` 不把记忆里的旧叫法作为同义词提议给这个元素。元素已删除或不存在时，忽略这条记忆 |
| M3 | `resolve_requests` 生成消解请求时 | 一对候选的 `k:` 键命中 `kept_apart` 条目时，不送模型消解，直接判为不同概念，也不加 `possible_duplicate` 标记。`mark_late_candidates` 同样跳过这一对 |

M1 只比较主名称键。同义词、近似名称不触发 M1，交给提示词处理（第 6.3 节），并在预审里标出 `similar_to_rejected`（第 7.2 节）。

### 6.3 提示词要点

- 记忆行放在调用的 `text` 里，可以含中文标签，它们是数据。新增的英文规则放在 `ai/memory_prompts.py`，只有本次调用选中了记忆行时，才追加到原 `instructions` 后面。
- 类型阶段（`extract.types`）：选 `rejected` 类型条目与 `renamed` 条目。`text` 末尾加一节：

  ```text
  Reviewer decisions on earlier proposals:
  - rejected type: 炉渣颜色 (reason: out_of_scope)
  - renamed type: 钢包车 -> 钢包运输车
  ```

  规则要点（英文写在 `MEMORY_TYPES_RULES`）：listed rejected names were reviewed and turned down; do not propose them or close variants of them unless the source clearly defines a distinct business concept; for a renamed entry use the new name; these lines are decisions, not source text, and never count as evidence.
- 关系阶段（`extract.relations`）：选 `rejected` 关系与属性条目（`detail.domain`、`detail.range` 在本批目录里），规则 `MEMORY_RELATIONS_RULES` 同理。
- 术语阶段、消解阶段不加记忆（D7）。
- 选行：先选与本批相关的条目。类型阶段看条目的键是否等于、包含或被包含于本批任一术语的键，或 `candidates.score` 不低于 `THRESHOLD`；关系阶段看域或值域是否在目录里。再按 `coalesce(last_hit_at, created_at)` 倒序，取前 `review_memory_prompt_max` 行。无相关条目就不加，提示词保持原样。
- 规则中的示例只用通用英文词，不出现中文（扩展 `test_the_prompts_give_examples_in_generic_words_only`，把 `MEMORY_TYPES_RULES`、`MEMORY_RELATIONS_RULES` 加进去）。
- 断言：`memory` 为空或没有选中任何行时，每次调用的 `instructions` 和 `text` 与不传 `memory` 时逐字节相同。现有录制全部照常回放。

### 6.4 被挡掉的提议

- `ontology.change_sets` 新增列 `suppressed`，类型 jsonb，not null，默认 `'[]'`。内容是 `SuppressedItem` 数组，最多 200 条，超出的只计数。
- `ChangeSetDetail` 新增 `suppressed` 与 `suppressedTotal`。审核页据此提示（第 9 节）。
- 被挡掉的提议不成为变更项，也不出现在任何写入路径上。

## 7 AI 预审（批次 6）

### 7.1 流程

1. `POST /api/change-sets/{id}/review-assist`，请求体为 `{ locale }`。
   - 校验：变更集为 `open`，否则 409 `changeset.closed`；调用者为 editor 以上；同一变更集没有 `queued` 或 `running` 的预审，否则 409 `review_assist.running`；不超过限流，否则 429 `review_assist.rate_limited`，带 `Retry-After`。
   - "同时只有一次"由部分唯一索引保证（第 11 节）：并发插入撞到索引时，捕获冲突并返回 409 `review_assist.running`。
   - 失效的行：创建超过 `review_assist_timeout_seconds + 120` 秒仍是 `queued` 或 `running` 的行，在发起新预审时先改为 `failed`（`errorCode = review_assist.timeout`），再插入新行。这样 worker 崩溃后不会永远卡住。任务写结果前先核对这一行仍是 `running`，不是时放弃写入，避免把已判失效的行改回 `done`。
   - 新建 `ai.review_assists` 行（`queued`），排入任务 `review.assist`，返回 202 和这条预审。
2. 任务调用 `ontology.review_context(db, change_set_id, …)` 取冻结上下文，先跑规则检查（第 7.2 节），AI 已配置时再按批调用模型（第 7.3 节）。最后写入 `result`，状态置为 `done` 或 `partial`。
3. `GET /api/change-sets/{id}/review-assist` 返回最近一次预审，没有时返回 `null`。前端在 `queued`、`running` 时每 2 秒轮询一次。返回时，服务端：
   - 对每项比较保存的指纹和当前指纹，不同的标 `stale = true`，只影响 AI 部分；
   - **重新计算规则检查**（不花钱），返回当前的规则风险，不用保存的。`stale_target`、`kept_fields` 会随别人的合并而变化，保存的结果会过时。变更集已关闭时，返回保存的规则结果。
4. 任务全程只写 `ai.review_assists` 和 `ai.runs`，不写 `ontology` 的任何表。

### 7.2 规则检查（`source = 'rule'`，纯函数 `ai/review_rules.py`）

| 风险 | 细项 `detail` | 条件 |
|---|---|---|
| `weak_evidence` | `evidence_not_found` | 项带 `evidence_not_found` 标记 |
| | `no_evidence` | 新建项没有任何证据 |
| | `low_confidence` | `confidence < 0.5` |
| `duplicate` | `possible_duplicate` | 带 `possible_duplicate` 标记 |
| | `undecided_match` | 对齐记录为 `possible`，`match_decision` 为空 |
| `conflict` | `kept_fields` | 合并计划的 `kept_fields` 非空（更新会与他人的修改冲突） |
| | `stale_target` | 目标元素的 revision 已变（合并会报 `changeset.stale_target`） |
| `naming` | `local_name_style` | 局部名不符合 `rules.LOCAL_NAME`，或类型不是大写开头、关系与属性不是小写开头 |
| | `missing_label_en` | 新建项没有英文名 |
| `memory` | `similar_to_rejected` | 主名称与某条 `rejected` 条目不是精确命中，但 `candidates.score ≥ THRESHOLD` |

规则检查覆盖第 2 节范围内的所有项（类型、关系、属性），不限 400 项。

### 7.3 模型检查（`source = 'ai'`）

- 只查第 2 节范围内的项，按变更项 `seq` 顺序每批 `review_assist_batch = 80` 项，最多 `review_assist_items_max = 400` 项。超出的项只有规则检查，`result.truncated = true`。
- 每批一次调用，purpose `review.assist`。批数大于 1 时，最后再调一次 `review.assist.summary`，用来合并摘要和分组。整个任务最长 `review_assist_timeout_seconds = 300` 秒。
- `text` 的内容（D14）：
  - `language: zh-CN` 或 `en`（来自请求的 `locale`）；
  - 本批各项，用短引用 `i1`、`i2`…… 表示，每项包括：种类、操作、中英文名、局部名、定义、父类或域、值域、标记、置信度、资料引文（最多 2 条、每条截到 200 字）、对齐记录的另一方名称；
  - 工作版本元素摘要（最多 `400` 个，先选与本批名称相关的，再按名称排序）：种类、中英文名、局部名、父类、域与值域、不相交类型；
  - `rejected` 记忆（最多 60 条，选法同第 6.3 节）。
- 不发数据源（catalog）证据、`note`、`edited` 以外的审核人信息、绑定的物理名称、连接信息。`edited` 存在时，发送的是"审核人修改后的值"（审核人的修改本身就是要预审的内容）。
- 输出结构（`ReviewAssistOut`，见附录）：每项给 `risks[]`（code 为 `weak_evidence`、`conflict`、`duplicate`、`naming`，各带一句理由）、`suggestion`（`accept`、`reject`、`edit`、`unsure`）、`reason`、可选的 `rename`（`labelZh`、`labelEn`、`localName`）；本批的 `groups[]`（标题和成员短引用）与 `summary`。
- 校验（确定性代码）：
  - 未知短引用、未知 code 丢弃并计入 `dropped`；
  - `rename.localName` 不合 `rules.LOCAL_NAME` 时丢弃这个字段；`rename` 的字段全被丢弃时，`suggestion` 改为 `unsure`；
  - 理由截到 300 字，摘要截到 600 字；最多 12 个组，组标题截到 40 字；一项只能属于一个组，重复出现时取第一次。
- 汇总调用的输入只有各批的摘要和组（标题、成员数、批号），输出合并后的 `summary` 与组映射（新组标题 → 原组列表）。汇总失败时，摘要取第一批的，组按批拼接。
- 某批失败（`ai.unavailable`、`ai.invalid_output`）或超时（`review_assist.timeout`）：已完成批次的结果保留，状态为 `partial`，`errorCode` 记第一个错误，未完成的项只有规则结果。全部批次都失败时，状态也是 `partial`，`aiUsed = false`。规则检查不受影响。
- 每次调用都在 `ai.runs` 留记录，与现有做法一致。

### 7.4 提示词要点（`ai/review_prompts.py`，英文）

- 角色：帮审核人逐项看一个本体变更集，只给参考意见，审核人做决定。
- 风险判断依据：
  - 证据是否支持这个名称和定义；
  - 是否与已有元素重名、同义或部分重叠（duplicate）；
  - 是否与已有父类、不相交声明、域与值域矛盾（conflict）；
  - 名称、局部名是否与本体已有命名风格一致（naming）；
  - 与 rejected 记忆相似时要指出。
- 建议：证据充分且无冲突的给 `accept`；不是业务概念、与已拒绝的相同、证据不支持的给 `reject`；名称不规范的给 `edit` 并附名称；拿不准的给 `unsure`，不要硬猜。
- 理由与摘要用 `language` 行给出的语言写，简短，引用证据时不超过 30 字。
- 示例只用通用英文词；`REVIEW_INSTRUCTIONS`、`REVIEW_SUMMARY_INSTRUCTIONS` 由本批的测试检查不含 CJK。

### 7.5 过期

- 指纹由 `ontology.review_context.item_fingerprint` 计算：对项的 `kind`、`op`、`target_element_id`、`proposed`、`edited` 做规范化 JSON，再取 sha256，只取前 16 个十六进制字符。`decision`、`note`、`match_decision` 不参与计算，因为改决定是正常的审核动作，不会让建议过期。
- 指纹不同的项在响应里标 `stale = true`。界面上把这些项的建议变灰，并标"预审之后已修改"；它们的风险不再计入批量接受的排除条件。
- 变更集已关闭时，预审仍可读，只是不能再发起。

### 7.6 限流与保留

- 每人每小时最多 `review_assists_per_hour` 次，按 `requested_by` 与 `created_at` 计数。
- 预审行不删除；只有最近一次在界面上显示。

## 8 权限矩阵

| 操作 | viewer | editor | reviewer | admin |
|---|---|---|---|---|
| 查看审核记忆 | ✓ | ✓ | ✓ | ✓ |
| 删除、撤销、清空审核记忆 | | | ✓ | ✓ |
| 拒绝时带理由 | | | ✓（同审核决定） | ✓ |
| 发起 AI 预审 | | ✓ | ✓ | ✓ |
| 查看预审结果 | ✓（能读变更集即可） | ✓ | ✓ | ✓ |

API 令牌（MCP）不能访问本规格的新路由。新增的写接口（DELETE、POST）沿用现有的会话与 CSRF 保护，不另开例外。

## 9 界面

遵守[界面规范](../ui-guidelines.md)：文字全部走 i18n，只用设计令牌，页面不输出过程信息。

i18n 文件：
- 拒绝理由与被挡提议的提示：加在根文件 `web/src/i18n/locales/{zh-CN,en}.json` 的 `review` 键下（批次 5）；
- 记忆页：新命名空间文件 `locales/{zh-CN,en}/reviewMemory.json`（批次 5）；
- 预审：新命名空间文件 `locales/{zh-CN,en}/reviewAssist.json`（批次 7）。

不要新建 `locales/<locale>/review.json`：`review` 已是根文件里的键，同名命名空间文件会让 i18n 初始化抛错。

**拒绝理由（批次 5）**

- 卡片上的"拒绝"改为分体按钮。主按钮直接拒绝，不带理由；下拉菜单列出四个理由。批量操作栏的"拒绝"同样处理。
- 已拒绝且带理由的项显示理由徽标（中性色）。

**被记忆挡掉的提示（批次 5）**

- `suppressed` 非空的变更集，在审核详情页顶部显示一条信息提示条（info 色，不用黄色：它不需要审核人处理）："按审核记忆，有 N 项没有再提出"，可以展开。
- 展开后列出名称、种类和原因（被拒绝过 / 依赖被挡的类型）。每行链接到审核记忆页，并定位到对应条目。

**审核记忆页（批次 5）**

- 路由 `/review/memory?ontology=<id>`。入口在审核列表页右上角的"审核记忆"链接。页内有本体选择器，默认选当前本体。
- 顶部一行说明："AI 识别新资料时会参考这些审核决定。"计数写作"123 / 500 条"。
- 表格列：类别（拒绝、改名、保持分开）、元素种类、内容（拒绝显示名称；改名显示"旧名 → 新名"；保持分开显示"A ↔ B"）、拒绝理由、来源变更集（链接）、决定人、时间、命中次数。可按类别筛选，可搜索。
- reviewer、admin 每行有"删除"。删除后给轻提示和"撤销"。页头有"清空"按钮（危险样式），点击后弹确认对话框，写明条数和"清空后 AI 不再参考这些决定"。
- 空状态："还没有审核记忆。合并 AI 识别的变更集后，这里会记下被拒绝、改名和判定为不同的决定。"主按钮"去审核"，链接到审核列表。
- 加载失败用通用错误状态，带重试。viewer 看不到删除和清空按钮。列表接口返回 403 时，表格区域显示界面规范的"无权限"状态；删除等操作返回 403 时用轻提示。

**AI 预审（批次 7）**

- 审核详情页头部有"✦ AI 预审"按钮：editor 以上、变更集为 open 时可用；viewer 和变更集已关闭时不显示按钮。预审进行中时，按钮禁用并显示加载状态；超过 10 秒后在按钮旁显示"仍在处理"。预审不能取消：已经发出的模型调用照样计费，取消也省不了钱。已有预审时，按钮文字为"重新预审"。
- 摘要卡片放在页面顶部，带 `✦ AI 建议` 标识（`--info`），内容：
  - 摘要；
  - 计数"有风险 n · 建议拒绝 n · 建议修改 n"；
  - 有过期项时写"预审之后有 n 项已修改"；
  - `aiUsed = false` 时写"只做了规则检查"（AI 未配置或调用失败时）；
  - `truncated` 时写"AI 只看了前 400 项，其余只做了规则检查"；
  - `partial` 时写"部分项没有完成 AI 检查"。
- 列表上方有筛选标签"有风险""建议拒绝""建议修改"和分组选择（列出组标题和项数）。这些筛选与现有筛选是"且"的关系。
- 卡片上：
  - 风险徽标：规则检查的用中性或警告色，AI 的带 ✦；悬停显示理由或细项说明；
  - 建议行："✦ 建议拒绝：理由……"；
  - 建议修改的项有"按建议修改"按钮，打开现有编辑对话框，预填建议的名称，审核人保存后才生效；
  - 过期项的建议行变灰，标"预审之后已修改"。
- "接受全部高置信度项"：有有效预审时，排除有未过期风险、建议拒绝或建议修改的项。按钮旁的说明写明"已排除 AI 预审标出风险的 n 项"。前端 `web/src/features/review/api.ts` 的 `highConfidencePending` 接受可选的预审参数。
- 不提供"接受全部建议""拒绝全部建议"。
- 预审失败（`failed`）：卡片显示错误状态和"重试"。读取预审返回 403 时，卡片区域显示"无权限"状态。限流时，轻提示写明多久后可以再试。

## 10 评测与验收

### 10.1 按期望审核的场景（批次 4）

`ai/eval.py` 新增 `OracleReviewer`，按 `expected.toml` 模拟一个一致的审核人：

- 新建类型：主名称和别名都不在任何期望组里的，拒绝（理由 `incorrect`）；在某组里但主名称不是该组 `names[0]` 的，改名为 `names[0]` 后接受；其余接受。
- 新建关系：不在期望关系里的拒绝（`incorrect`），其余接受。期望里没有属性清单的案例，属性一律接受。
- 对齐记录的处理沿用 `FlagReviewer`：期望在同一组的判为同一，不在同一组的判为不同。
- 决定交给 `ontology.review_memory` 的纯函数 `collect`（第 12.2 节），得到内存中的 `ReviewMemory`；`WorkingVersion` 照旧在内存里合并。
- 场景 `sequential` 加 `reviewed`：按资料顺序逐份识别，每份的变更集交给 `OracleReviewer` 处理后合并，并更新记忆，再识别下一份。`-NoMemory` 时照样审核，但记忆始终为空。
- `dev.ps1 eval` 新增 `-Reviewed`、`-NoMemory` 开关（批次 4，Claude 改），原样传给 eval 模块。

### 10.2 指标与目标

记忆开、关各跑一次 `-Sequential -Reviewed`，报告：

| 指标 | 含义 | 目标（记忆开，相对记忆关） |
|---|---|---|
| 再提比例（模型层面） | 被拒绝的键，在后续资料的**模型输出**里再次出现的次数 ÷ 后续资料中有机会再提的次数（被挡掉的也算） | steel-industry 相对下降至少 30% |
| 再提比例（审核人面前） | 同上，但只数进了变更集的 | 0 |
| 变体再提比例 | 后续新建项与被拒绝的键 `score ≥ THRESHOLD`、但不是精确命中的比例 | 报告，不设目标 |
| 改名沿用率 | `renamed` 条目对应的概念在后续资料中再次出现时，用了审核人的名称或引用已有元素的比例 | ≥ 0.9 |
| 保持分开的违背率 | `kept_apart` 的一对在后续资料中又被标疑似重复或判为同一的比例 | 0 |
| 类型准确率、类型召回、关系召回 | 沿用现有评测 | 类型准确率不降；类型召回下降不超过 0.02；关系召回单次波动大（0.73–0.838），下降时要逐条核对漏掉的核心关系后再判断 |

### 10.3 预审评测（批次 8）

- `-Assist`：对每个案例的非顺序（全量）变更集先跑预审，再用 `OracleReviewer` 的决定作为标准答案。
- 报告：建议拒绝的准确率和召回率、建议修改的命中率（建议名称与 `names[0]` 一致的比例）、`duplicate` 风险与期望同组的准确率。
- 目标：steel-industry 建议拒绝的准确率 ≥ 0.6，只报告，不卡门禁。

### 10.4 不花钱的自动化验收

- 拒绝理由：带理由的单项与批量拒绝；理由与非拒绝决定同时出现时返回 422；改回待定后清空。
- 采集：每条规则（第 5.5 节第 1–3 条和覆盖）各有一个用例；带对齐记录的拒绝不采集；整体拒绝不采集；非 `ai_extraction` 来源不采集但会覆盖；依赖被跳过的项不采集；复活、淘汰。
- 管理：角色矩阵；软删除后 `review_memory_for` 不再返回；不能撤销的情况返回 409；每个动作都有审计。
- 护栏：用构造的 `ReviewMemory` 和假模型输出跑 `build_proposals`。M1 挡住类型和依赖它的关系、属性，子类型只去掉父类；M2 引用已有元素且不提议旧名为同义词，元素已删除时忽略；M3 不送消解、不加标记。`suppressed` 写进变更集，命中计数增加。
- 提示词：记忆为空时，三个阶段的 `instructions` 与 `text` 逐字节不变（用现有录制回放，结果完全一致）；有记忆时 `text` 含记忆行、`instructions` 末尾带记忆规则；中文测试覆盖新常量。
- 预审：
  - 规则检查表中每个细项各一个用例；
  - 用假网关覆盖多批、汇总、校验丢弃、部分失败、超时、AI 未配置；
  - **预审前后对全部 `change_items` 行逐列比较，完全相同**；
  - 指纹过期；
  - 发给模型的 `text` 不含 catalog 证据的表名和列名、`note`、连接信息（构造带这些值的夹具后，断言它们不在 `text` 里）；
  - 限流、重复发起、变更集已关闭。
- 界面：组件测试覆盖分体拒绝按钮、提示条、记忆页（空状态、只读、删除与撤销、清空确认）、预审卡片、筛选、"按建议修改"只预填、批量接受的排除。
- e2e（批次 8）：冒烟流程中，在审核一步点"AI 预审"（e2e 环境不配 AI，走规则检查），看到摘要卡片和至少一个规则风险；带理由拒绝一项。

### 10.5 付费评测预算（不进门禁，只在主检出目录由主会话运行）

- 每轮最多 5 次全量：steel、steel-industry 各跑 `-Sequential -Reviewed` 与 `-Sequential -Reviewed -NoMemory`，再加 steel-industry 的 `-Assist` 一次。
- 本里程碑最多 2 轮（批次 4 合并后一轮，批次 8 合并后一轮）。超出预算或未达目标时，主会话在 #41 记下结论，再决定是否调整提示词，不靠重跑碰运气。
- 录制沿用 eval 现有的位置和做法；记忆开启的运行会产生新的输入哈希，第一次运行要付费。

## 11 迁移清单（v0013，批次 1）

只加不删，上一版程序可以照常运行：

1. `ontology.change_items` 加 `reject_reason text null`，检查约束 `reject_reason is null or reject_reason in ('out_of_scope','incorrect','duplicate','keep_open')`。
2. `ontology.change_sets` 加 `suppressed jsonb not null default '[]'::jsonb`（服务端默认值，旧程序插入时不需要知道这一列）。
3. 新表 `ontology.review_memory`（第 5.3 节），带唯一约束与部分索引。
4. 新表 `ai.review_assists`：
   - `id uuid PK`；
   - `change_set_id uuid not null`（不加外键，见下文）；
   - `ontology_id uuid not null`；
   - `requested_by uuid`；
   - `locale text not null`；
   - `status text`，检查约束 `queued` / `running` / `done` / `partial` / `failed`；
   - `error_code text null`、`ai_used boolean not null default false`、`truncated boolean not null default false`；
   - `result jsonb not null default '{}'`；
   - `items_total`、`items_ai`、`dropped`：`integer not null default 0`；
   - `created_at timestamptz not null`、`finished_at timestamptz null`；
   - 索引 `(change_set_id, created_at desc)`、`(requested_by, created_at)`；
   - 部分唯一索引 `(change_set_id) where status in ('queued','running')`，保证同一变更集同时只有一次预审。

   `change_set_id` 不加外键：现有 `ai` 表都不建跨 schema 外键，这里沿用。服务层在发起时校验变更集存在。变更集目前没有删除入口；以后要加删除入口时，由那次改动一并清理预审行。

降级按相反顺序删除。`test_migrations.py` 覆盖升级、降级、再升级；另用旧版 ORM 写入 `change_sets` 与 `change_items` 的用例，证明上一版程序在新表结构上仍能运行。

## 12 批次切分

### 12.1 约定

- 后端共享文件归批次 1：迁移、`main.py`、根 `models.py`、`worker.py`、`settings.py`、`.env.example`、`backend/tests/conftest.py`、`test_openapi.py`。`web/src/api/schema.d.ts` 由批次 1 运行 `gen-api` 生成；之后只有接口形状确需变化时才重新生成，由改形状的那一批负责，并同时跑 `test-web`。
- HTTP 路由在批次 1 按最终签名建好，服务函数先抛 501 `http.not_implemented`。跨模块入口在批次 1 定好签名与冻结数据类，函数体抛 `NotImplementedError`。**例外**：`review_memory_for` 的桩返回空的 `ReviewMemory`，`record_memory_hits` 的桩什么也不做。批次 3 可能先于批次 2 合并，识别流程不能因为桩而出错。
- 迁移编号：批次 1 开 PR 时如果 main 已有更新的迁移，由批次 1 的执行者改文件名和 `down_revision`，再跑 `test_migrations.py`。
- 批次 1 的 `test_review_learning_skeleton.py` 为后续每个后端批次留 `xfail(strict=True)` 用例，各批实现时启用对应断言。
- 新设置项（批次 1 加到 `settings.py` 与 `.env.example`）：`review_memory_max = 500`、`review_memory_prompt_max = 40`、`review_assists_per_hour = 20`、`review_assist_items_max = 400`、`review_assist_batch = 80`、`review_assist_timeout_seconds = 300`。
- 所有批次都要做到：不改 `ai/prompts.py`、`connectors/**`；ruff format 与 lint、mypy strict、eslint、tsc 通过；新功能有测试；改接口行为的批次把附录列进范围。

### 12.2 跨模块接口（批次 1 定型）

```python
# modules/ontology/review_memory.py（批次 1：类型与键函数实现；批次 2：collect 实现）
MemoryKind = Literal["rejected", "renamed", "kept_apart"]
MemoryElementKind = Literal["entity_type", "relation_type", "property"]
RejectReason = Literal["out_of_scope", "incorrect", "duplicate", "keep_open"]
def type_key(label_zh: str | None, label_en: str | None) -> str: ...
def relation_key(domain: str, name: str, range_: str) -> str: ...      # 三个参数都是主名称键
def property_key(domain: str, name: str) -> str: ...
def pair_key(a: str, b: str) -> str: ...
@dataclass(frozen=True) class MemoryEntry:
    id: UUID; kind: MemoryKind; element_kind: MemoryElementKind; key: str; label: str
    reason: RejectReason | None          # rejected
    label_en: str | None                 # rejected
    domain: str | None; range: str | None    # rejected 的关系、属性
    to_label_zh: str | None; to_label_en: str | None; element_id: UUID | None   # renamed；kept_apart 的 element_id 为 otherElementId
    other_label: str | None              # kept_apart
    created_at: datetime; last_hit_at: datetime | None
@dataclass(frozen=True) class ReviewMemory:
    ontology_id: UUID; entries: tuple[MemoryEntry, ...]
    def find(self, kind: MemoryKind, key: str) -> MemoryEntry | None: ...
@dataclass(frozen=True) class DecidedItem:   # 由合并（或评测）从一项构造
    item_id: UUID; kind: str; op: str; decision: Decision; reject_reason: RejectReason | None
    proposed_label_zh: str | None; proposed_label_en: str | None
    final_label_zh: str | None; final_label_en: str | None          # 应用 edited 之后
    domain_label: str | None; range_label: str | None                # 最终值，关系、属性用
    created_element_id: UUID | None                                  # 合并按 create/restore 生效时
    renamed_element_id: UUID | None                                  # 合并改了已有元素的名称时
    match_kind: MatchKind | None; match_decision: MatchDecision | None
    match_other_label: str | None; match_other_element_id: UUID | None
@dataclass(frozen=True) class NewEntry: kind: MemoryKind; element_kind: MemoryElementKind; key: str; label: str; detail: Mapping[str, object]; source_item_id: UUID | None; decided_by: UUID | None
@dataclass(frozen=True) class MemoryDelta: upserts: tuple[NewEntry, ...]; superseded_keys: tuple[tuple[MemoryElementKind, str], ...]
def collect(source: ChangeSetSource, items: Sequence[DecidedItem]) -> MemoryDelta: ...   # 纯函数；非 ai_extraction 只产出 superseded_keys
def apply_delta(memory: ReviewMemory, delta: MemoryDelta, *, now: datetime, max_entries: int) -> ReviewMemory: ...   # 纯函数，评测用；淘汰规则同第 5.6 节

# modules/ontology/service.py
async def review_memory_for(db: AsyncSession, ontology_id: UUID) -> ReviewMemory: ...      # 批次 2
async def record_memory_hits(db: AsyncSession, ontology_id: UUID, entry_ids: Sequence[UUID]) -> None: ...   # 批次 2
async def create_change_set(..., suppressed: Sequence[schemas.SuppressedItem] = (), suppressed_total: int | None = None) -> UUID: ...   # 批次 1 实现存储

# modules/ontology/review_context.py（批次 1 类型与桩，批次 6 实现）
@dataclass(frozen=True) class ReviewItem:
    id: UUID; seq: int; fingerprint: str; kind: str; op: str; decision: Decision
    label_zh: str | None; label_en: str | None; local_name: str | None; definition: str | None
    parent: str | None; domain: str | None; range: str | None
    flags: tuple[ItemFlag, ...]; confidence: float | None; has_evidence: bool
    quotes: tuple[str, ...]              # 只含资料证据，≤2 条，每条 ≤200 字
    match_kind: MatchKind | None; match_decision: MatchDecision | None; match_other_label: str | None
    kept_fields: tuple[str, ...]; target_stale: bool
@dataclass(frozen=True) class ElementBrief: id: UUID; kind: str; label_zh: str | None; label_en: str | None; local_name: str; parent: str | None; domain: str | None; range: str | None; disjoint: tuple[str, ...]
@dataclass(frozen=True) class ReviewContext:
    change_set_id: UUID; ontology_id: UUID; status: str; source: ChangeSetSource
    items: tuple[ReviewItem, ...]        # 只含 entity_type、relation_type、property 种类的项
    elements: tuple[ElementBrief, ...]   # 工作版本，最多 elements_max
    rejected: tuple[MemoryEntry, ...]    # 最多 memory_max
def item_fingerprint(kind: str, op: str, target_element_id: UUID | None, proposed: Mapping[str, object], edited: Mapping[str, object] | None) -> str: ...
async def review_context(db: AsyncSession, change_set_id: UUID, *, elements_max: int = 400, memory_max: int = 60) -> ReviewContext: ...
async def item_fingerprints(db: AsyncSession, change_set_id: UUID) -> dict[UUID, str]: ...

# modules/ai/review_assist.py（批次 1 桩，批次 6 实现）
JOB_KIND = "review.assist"
async def request_assist(db: AsyncSession, change_set_id: UUID, *, user: CurrentUser, locale: Locale, settings: Settings) -> schemas.ReviewAssist: ...
async def latest_assist(db: AsyncSession, change_set_id: UUID) -> schemas.ReviewAssist | None: ...
def make_review_assistant(session_factory, gateway: ModelGateway | None, model: str | None, settings: Settings) -> Handler: ...

# modules/ai/review_rules.py（批次 6）
def rule_risks(ctx: ReviewContext, *, threshold: float = THRESHOLD) -> dict[UUID, tuple[schemas.AssistRisk, ...]]: ...

# modules/ai/extraction.py（批次 3）
@dataclass class MemoryOutcome:            # 可变，由 run 填写
    suppressed: list[SuppressedItem] = field(default_factory=list); suppressed_total: int = 0
    memory_hits: set[UUID] = field(default_factory=set)
# Extractor.run(..., memory: ReviewMemory | None = None, outcome: MemoryOutcome | None = None) -> list[Proposal]   # 返回类型不变
# build_proposals(..., memory: ReviewMemory | None = None, outcome: MemoryOutcome | None = None)                 # 返回类型不变
```

模块依赖方向不变：`ai → ontology`。`ontology` 不导入 `ai`；第 5.4 节的规范化规则在 `ontology` 里复制一份，用测试保证两边一致。`worker.py` 在批次 1 登记 `review.assist`（处理函数先写为抛出不可重试错误的桩）。

### 12.3 批次表

| 批次 | 内容 | 依赖 | 负责的路径 | 不许碰 | 级别 | 执行者 | 行数 |
|---|---|---|---|---|---|---|---|
| 1 | 骨架与迁移：迁移 v0013、ORM、schemas、路由桩（501）、第 12.2 节签名与冻结类、键函数（含与 `candidates` 一致的测试）、设置项、`worker` 登记、`gen-api`；拒绝理由完整实现（存、清、返回、422）；`create_change_set` 存 `suppressed`；骨架测试 | 无 | 第 12.1 节共享文件；`ontology/{models,schemas,service,api,review_memory,review_context}.py`（`review_memory`、`review_context` 只放类型、键函数和桩）；`ai/{models,schemas,review_assist,api}.py`（只放类型、桩和路由）；`schema.d.ts`；`tests/test_migrations.py`、`tests/test_review_learning_skeleton.py`、`tests/test_reject_reason.py` | `ai/{extraction,pipeline,prompts,eval}.py`、`ontology/merge.py`、`web/src/features/**` | L2 | Codex 实现（强度高）+ Claude 审：迁移的兼容性、角色、路由 | 约 1,200（含生成的类型） |
| 2 | 记忆采集与管理：`collect`、`apply_delta`；合并时采集和覆盖、淘汰、`review_memory.collected` 审计；`review_memory_for`、`record_memory_hits`；列表、删除、撤销、清空接口和审计 | 1 | `ontology/review_memory.py`（实现）、`ontology/merge.py`、`ontology/service.py`（记忆相关函数）、`ontology/api.py`（记忆路由实现）；`tests/test_review_memory_collect.py`、`tests/test_review_memory_api.py` | `ai/**`、`mergeplan.py` 的现有签名、`web/**` | L2 | Codex 实现（强度高）+ Claude 审：合并事务与锁、覆盖规则 | 约 900 |
| 3 | 流水线使用记忆：M1–M3、`suppressed`、命中、提示词规则与选行、记忆为空时逐字节不变；`run` 与 `build_proposals` 只加可选参数，返回类型不变 | 1（用构造的 `ReviewMemory` 测试；与 2 并行，桩返回空记忆） | `ai/extraction.py`、`ai/pipeline.py`、`ai/memory_prompts.py`（新）；`tests/test_ai_memory_guards.py`（新）；`tests/test_ai_extraction.py` 只改中文测试的常量清单 | `ai/prompts.py`、`ai/candidates.py` 的现有函数、`ontology/**` | L2 | Codex 实现（强度高）+ Claude 审：护栏不越界、提示词不含中文、回放不变 | 约 900 |
| 4 | 记忆评测：`OracleReviewer`、`reviewed` 场景、第 10.2 节指标；`dev.ps1` 的 `-Reviewed`、`-NoMemory` | 2、3 | `ai/eval.py`、`tests/test_ai_eval_reviewed.py`（新，回放夹具）、`dev.ps1`、`docs/development.md` 评测一节 | `ai/extraction.py`、`ontology/**` | L2 | Codex 写 `eval.py` 和测试（强度中）；Claude 改 `dev.ps1` 和文档；主会话跑第一轮付费评测 | 约 600 |
| 5 | 记忆界面：审核记忆页、入口、分体拒绝按钮（单项和批量）、理由徽标、被挡提议提示条 | 1、2 | `web/src/routes/_app/review/memory.tsx`（新）、`web/src/features/review/review-list-page.tsx`（入口链接）、`web/src/features/review-memory/**`（新）、`web/src/features/review/{change-item-card,review-detail-page,suppressed-notice}.tsx`、`web/src/features/review/api.ts`（拒绝理由参数）、根 `web/src/i18n/locales/{zh-CN,en}.json` 的 `review` 键、`locales/{zh-CN,en}/reviewMemory.json`（新）、对应组件测试；路由树文件由路由生成器更新 | 后端、`schema.d.ts` | L1 | Codex（强度中） | 约 800 |
| 6 | AI 预审后端：`review_context`、规则检查、模型检查、汇总、校验、部分失败、限流、过期判断 | 1、2（`review_memory_for`）、3（选行做法相同，不共用文件） | `ontology/review_context.py`（实现）、`ai/review_assist.py`、`ai/review_rules.py`（新）、`ai/review_prompts.py`（新）、`ai/api.py`（预审路由实现）；`tests/test_review_assist.py`、`tests/test_review_rules.py`（新） | `ai/{extraction,pipeline,prompts,eval}.py`、`ontology/{merge,service}.py`、`web/**` | L2 | Codex 实现（强度高）+ Claude 审：不写 `ontology`、发给模型的内容、限流 | 约 1,300 |
| 7 | 预审界面：按钮与轮询、摘要卡片、筛选与分组、风险徽标、建议行、"按建议修改"、过期、批量接受排除 | 5、6 | `web/src/features/review/{assist-*.tsx（新）,change-item-card,review-detail-page,api}.tsx/ts`、`locales/{zh-CN,en}/reviewAssist.json`（新）、对应组件测试 | 后端、`review-memory/**`、根 `locales/{zh-CN,en}.json` | L1 | Codex（强度中） | 约 900 |
| 8 | 收尾：`-Assist` 评测（`eval.py`）与 `dev.ps1` 开关；e2e 冒烟步骤；`docs/architecture.md` 审核记忆与预审一节；路线图状态 | 4、7 | `ai/eval.py`、`dev.ps1`、`web/e2e/smoke.e2e.ts`、`docs/architecture.md`、`docs/development.md`、`docs/roadmap.md` | 其余全部 | L2（`dev.ps1`） | Codex 写 `eval.py` 与 e2e（强度中）；Claude 改 `dev.ps1` 和文档；主会话跑第二轮付费评测 | 约 500 |

批次 2 与 3 文件不重叠，可以并行；批次 4、5、6 文件互不重叠，也可以并行。批次 8 的 e2e 依赖 e2e 栈里的 worker 能执行 `review.assist` 任务；如果不能，停下来交回 Claude，不要绕开。批次 5、7 都改审核页的文件，所以 7 必须排在 5 之后。每批完成后都要能独立通过门禁：后续功能未合并时，接口返回 501，界面隐藏入口。

## 13 风险

| 风险 | 应对 |
|---|---|
| 一次拒绝就再也不出现，可是后来的资料确实需要这个概念 | `keep_open`、`duplicate` 不进记忆；被挡的提议在审核页可见，并能链接到记忆条目一键删除；后面的接受会覆盖（D9）；M1 只看精确主名称 |
| 同名不同义：不同领域的资料用同一个词 | 本体内名称本就要求唯一，同一本体里冲突很少；记忆按本体隔离 |
| 记忆行让提示词变长，召回下降 | 每次最多 40 行，只选相关条目；第 10.2 节召回容忍 0.02；记忆为空时逐字节不变 |
| 录制失效，评测基线漂移 | 记忆为空时逐字节不变，并有测试断言；新场景单独录制 |
| 审核人照搬 AI 建议（自动化偏差） | 不提供一键接受建议；建议带理由并标 ✦；允许 `unsure`；第 10.3 节报告准确率 |
| 预审花费失控 | 手动发起、限流、400 项上限、每批 80 项、300 秒超时 |
| 预审结果过期误导审核人 | 按项指纹判断，过期项变灰；改变更项后不会把旧建议当作新的 |
| 发给模型的内容越界 | `review_context` 只装允许的字段，并有夹具测试断言 catalog 证据、备注和连接信息不在 `text` 里 |
| 模型引用不存在的项或乱给枚举 | 确定性校验后丢弃并计数 |
| 合并与采集并发 | 采集在合并事务和本体锁内；复活或插入用 upsert |
| 上一版程序在新表结构上运行 | 只加列，服务端带默认值；不加跨列约束（第 5.2 节） |

## 14 主会话已定的取舍

以下取舍按推荐方案写进了本文。主会话审 PR 时逐条确认，改动其中任何一条都要同步改相应章节。

| 编号 | 取舍 | 推荐（本文采用） | 备选 | 理由 |
|---|---|---|---|---|
| T1 | 记忆怎样存 | 单独一张表 `ontology.review_memory` | 每次从历史 `change_items` 现算 | 上限、删除、命中次数都需要持久状态；现算的成本随历史增长 |
| T2 | 从哪些来源采集 | 只采 `ai_extraction` | 所有 AI 来源（助手、问答、MCP） | 其他来源是用户主动要求的提议，挡掉会让人困惑；先用识别验证效果 |
| T3 | 整个变更集被拒绝时 | 不采集 | 当作逐项拒绝采集 | 整体拒绝多半是"这次识别不要了"，不是对每一项的判断 |
| T4 | 改名之后旧叫法怎样处理 | 映射到审核人的元素，不提议为同义词（M2）；元素已删除则忽略这条记忆 | 把旧叫法提议为同义词 | 审核人改名，往往是因为旧叫法不规范；要保留同义词的，审核人可以手工加 |
| T5 | "判为同一"要不要采集 | 不采集 | 采集为 `merged`，下次直接判同一 | 并入后已是同义词，G1 会命中；再加一类只会增加复杂度 |
| T6 | 拒绝理由 | 可选，四个值，`duplicate`、`keep_open` 不进记忆 | 必填；或不加理由 | 必填拖慢审核；不加理由就分不出"暂不决定" |
| T7 | 上限 | 每本体 500 条，每次调用 40 行，按最久未命中淘汰 | 不设上限；或按条目的类别分别设上限 | 控制提示词长度和花费；单一上限简单可解释 |
| T8 | 删除与清空 | 单条软删除并可撤销；清空要确认，界面上不可撤销 | 硬删除；或提供回收站 | 符合界面规范（可撤销的用轻提示，危险的用确认）；回收站超出本里程碑 |
| T9 | 谁能管理记忆 | reviewer、admin | editor 也能删 | 记忆来自审核决定，应由有审核权的人改 |
| T10 | 记忆页的入口 | 审核列表页，新路由 `/review/memory` | 本体页加一个视图标签 | 本体页的 `view` 参数只有 graph、list、turtle，加标签要改共享路由；记忆属于审核 |
| T11 | 消解阶段用不用记忆 | 不放进提示词，`kept_apart` 由代码跳过（M3） | 提示词里也列出记忆 | 用代码判断更可靠、更省 token |
| T12 | 预审怎样触发 | 手动，editor 以上，限流 20 次/小时 | 识别完成后自动预审；或提供设置开关 | 控制花费；先观察使用情况再考虑自动 |
| T13 | 预审结果怎样存 | `ai.review_assists`，按项指纹判断过期 | 写进 `change_items` 的新列 | 红线：不改变更项；独立表也便于保留历史 |
| T14 | 批量接受 | 有有效预审时，"接受全部高置信度项"排除风险项；不提供"接受全部建议" | 保持现状；或提供"接受全部建议" | 只让批量操作更保守，不新增 AI 驱动的批量写入 |
| T15 | 分组 | 模型给出，多批时由汇总调用合并 | 按域类型、父类确定性分组 | 模型分组更贴近主题；汇总失败时退回按批拼接 |
| T16 | 预审的语言 | 按请求的 `locale` 写理由和摘要 | 一律中文 | 界面支持中英文 |
| T17 | 被挡提议的提示样式 | info 色提示条，可展开 | 黄色警告提示条 | 不需要审核人处理；黄色留给会改变合并结果的提示 |
| T18 | `reject_reason` 的约束 | 只约束取值，不加跨列约束，由服务层清空 | 加"非拒绝时必须为空"的约束 | 上一版程序改回接受时不会清空，加约束会让旧程序报错 |
| T19 | 付费评测预算 | 每轮最多 5 次全量，最多 2 轮，只在主检出目录 | 每批都跑 | 额度紧；关系召回单次波动大，多跑也不能替代逐条核对 |
