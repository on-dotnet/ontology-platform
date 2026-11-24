# 001 M1：AI 识别资料 → 本体

- 级别：L2（AI 写入路径与审核流程、数据库迁移、compose）
- 关联：[架构](../architecture.md)、[界面规范](../ui-guidelines.md)、[路线图](../roadmap.md)

## 1 用户能做什么

1. 在工作台或"资料"页上传资料（docx、xlsx、pdf、md、txt）。没有本体时，先起一个名字建本体。
2. 平台在后台解析资料，再由 AI 分阶段识别：术语 → 对象类型与层级 → 关系与属性。页面只显示步骤级进度，不显示日志。
3. 识别完成后生成一个**变更集**，在"审核"页逐项接受、修改或拒绝。每一项都附 ✦AI 建议标识、置信度和证据，点击证据会打开原文并高亮对应片段。
4. 审核后把变更集**合并**进本体的工作版本，在"本体"页用图谱和列表查看。
5. 在"版本"页**发布**版本（不可变快照），可以导出 Turtle（OWL 2 + SHACL + SKOS），也可以把旧版本重新设为当前版本（回滚）。

验收：用 `samples/steel/docs` 的钢铁冶金样例资料，从零生成一版本体并发布；`./dev.ps1 eval` 给出对象类型与关系的准确率、召回率基线。

## 2 范围外（后续里程碑）

手工新建、删除元素（M2；M1 只能在审核时修改 AI 的建议）；高级公理与 Protégé 往返（M2）；数据源绑定（M3）；问答（M4）；向量检索与跨资料去重（M2 起）；多人协同编辑冲突处理（M2）。

## 3 数据模型

全部表放在 PostgreSQL，各模块用自己的 schema。主键 uuid，时间带时区，存 UTC。

### 3.1 `ontology` 模块

**`ontology.ontologies`**：`id`、`key`（唯一，小写字母、数字、短横线，用于 IRI）、`name`、`description`、`base_iri`（默认 `https://example.org/ontology/{key}#`）、`created_by`、`created_at`、`updated_at`、`active_release_id`（可空）。

**`ontology.elements`**：本体的工作版本，一行一个元素。

| 列 | 说明 |
|---|---|
| `id`、`ontology_id` | |
| `kind` | `entity_type` / `relation_type` / `property` |
| `local_name` | IRI 局部名，创建后不变。对象类型用 PascalCase，关系与属性用 camelCase，同一本体内唯一 |
| `label_zh`、`label_en` | 显示名；`label_zh` 必填 |
| `definition_zh`、`definition_en` | 可空 |
| `synonyms` | jsonb 数组：`[{ "lang": "zh", "text": "钢包" }]` |
| `parent_id` | 仅对象类型：父类型（`rdfs:subClassOf`），可空 |
| `domain_id` | 关系与属性：所属对象类型 |
| `range_id` | 仅关系：目标对象类型 |
| `datatype` | 仅属性：`string` / `integer` / `decimal` / `boolean` / `date` / `dateTime` |
| `unit` | 仅属性：单位符号，例如 `mm`、`℃`、`%`，可空 |
| `required`、`multiple` | 属性与关系的基数：是否必填、是否允许多个 |
| `status` | `active` / `deprecated` |
| `origin` | `ai` / `manual` |
| `revision` | 乐观锁版本号，每次修改加一 |
| `created_at`、`updated_at` | |

约束：按 `kind` 检查各列是否允许为空；`(ontology_id, local_name)` 唯一；`parent_id`、`domain_id`、`range_id` 指向同一本体的 `entity_type`（由服务层校验，并禁止父子关系成环）。

**`ontology.change_sets`**：`id`、`ontology_id`、`title`、`source`（`ai_extraction` / `ai_assistant` / `manual`）、`document_id`（可空）、`status`（`open` / `merged` / `rejected`）、`created_by`（可空；AI 生成时为发起上传的用户）、`created_at`、`merged_by`、`merged_at`。

**`ontology.change_items`**：

| 列 | 说明 |
|---|---|
| `id`、`change_set_id`、`seq` | `seq` 在变更集内递增，决定展示顺序 |
| `op` | `create` / `update` |
| `kind` | 与元素相同 |
| `target_element_id` | `update` 时指向已有元素 |
| `temp_ref` | `create` 时的临时引用（如 `new:Slab`），供同一变更集内其他项引用 |
| `proposed` | jsonb：建议的字段（camelCase，字段同元素；引用其他元素时写元素 id 或 `temp_ref`，键为 `parentRef`、`domainRef`、`rangeRef`） |
| `edited` | jsonb，可空：审核人修改后的字段，合并时以它为准 |
| `decision` | `pending` / `accepted` / `rejected` |
| `confidence` | 0–1，可空 |
| `rationale` | AI 给出的一句话理由 |
| `flags` | jsonb 数组，如 `["evidence_not_found", "possible_duplicate"]` |
| `decided_by`、`decided_at`、`note` | |
| `applied_element_id` | 合并后对应的元素 |

**`ontology.evidence`**：`id`、`change_item_id`、`document_id`、`chunk_id`、`quote`（不超过 500 字）、`char_start`、`char_end`（在分块文本中的位置；未找到时为空）。

**`ontology.releases`**：`id`、`ontology_id`、`version`（本体内从 1 递增）、`title`、`notes`、`snapshot`（jsonb：发布时全部 active 元素）、`turtle`（文本）、`turtle_sha256`、`element_count`、`created_by`、`created_at`。发布后不可修改。

### 3.2 `documents` 模块

**`documents.documents`**：`id`、`ontology_id`、`filename`、`media_type`、`size_bytes`、`sha256`、`storage_key`、`status`（`queued` / `parsing` / `extracting` / `ready` / `failed`）、`progress`（jsonb：`{ "step": "terms", "done": 3, "total": 5 }`）、`error_code`（可空，稳定错误码）、`page_count`、`char_count`、`change_set_id`（识别完成后）、`uploaded_by`、`created_at`、`updated_at`。

**`documents.chunks`**：`id`、`document_id`、`seq`、`text`、`page`（可空）、`heading`（所在标题路径，可空）、`char_count`。分块约 2,000 字，在段落边界切分，相邻块不重叠。

原件保存在数据卷 `/data/documents/{sha256 前 2 位}/{sha256}`，读写只经过 `documents.storage` 接口（以后可换成 S3）。由原件派生、可复用的结果（如扫描件分段转写）存放在同一卷的 `derived/{资料 id}/` 下，也只经过该接口读写。同一本体内 sha256 相同的资料视为重复，直接返回已有记录。

上传限制：单个文件不超过 20 MB；类型以扩展名加内容检测为准；不支持的类型返回 415 `documents.unsupported_type`。

### 3.3 `jobs` 模块（后台任务）

**`jobs.jobs`**：`id`、`kind`（`document.process`）、`payload`（jsonb）、`status`（`queued` / `running` / `succeeded` / `failed`）、`attempts`、`max_attempts`（默认 3）、`run_after`、`locked_by`、`locked_at`、`heartbeat_at`、`error_code`、`error_detail`（只记日志与库，不返回给界面）、`created_at`、`finished_at`。

worker 用 `SELECT … FOR UPDATE SKIP LOCKED` 领取任务，运行期间每 15 秒更新心跳；心跳超过 2 分钟的 `running` 任务视为中断，重新排队。失败后按 30 秒、2 分钟的间隔退避重试。worker 与 api 用同一个镜像，在 compose 中以单独的 `worker` 服务运行。

### 3.4 `ai` 模块

**`ai.runs`**：`id`、`purpose`（`extract.terms` / `extract.types` / `extract.relations` / `transcribe` / `status.check`）、`model`、`document_id`（可空）、`status`、`input_tokens`、`output_tokens`、`latency_ms`、`error_code`、`created_at`。用于统计用量与排查问题，不保存提示词，也不保存资料原文。

## 4 AI 识别流水线

一份资料对应一个 `document.process` 任务，步骤如下（`progress.step` 依次取值）：

1. `parse`：解析成纯文本并分块。docx 用 python-docx，xlsx 用 openpyxl（每个工作表转成 Markdown 表格），pdf 用 pypdf 逐页提取，md/txt 直接读取。如果 PDF 平均每页少于 50 个字（扫描件），把原件按每 5 页拆成小 PDF，逐批交给多模态模型转写成文本，页码换算成原文页码后再分块。每段的转写结果保存在资料存储里（`derived/{资料 id}/transcript-{起始页}-{页数}.json`，与原件同一个数据卷），任务重试时已转写的段直接读回，不再调用模型。没有文字的段不保存，用户在“读不出文字”后重试时会重新转写；保存的结果读不出或格式不对时也重新转写；保存失败只记日志，不影响本次处理。保存的结果不随模型更换而失效（只在重试时复用）；以后增加删除资料的功能时，要一并删除 `derived/{资料 id}/`。
   - 规模上限：扫描件超过 100 页时不转写，记为 `documents.too_many_pages`；分块后的总字数超过 200,000 时不进入识别，记为 `documents.too_long`。两者都在调用模型前判断，并保存实际页数或字数，界面据此提示超出多少；重试无济于事，界面不提供重试。上传前浏览器先数 md、txt 的字数，超限的不上传。
2. `terms`：逐块（或多块合批，每次约 8,000 字）抽取领域术语，记录名称、英文名、一句话定义、类别（对象 / 属性 / 关系 / 取值 / 其他）、原文引语。按规范化后的名称合并去重。
3. `types`：把汇总的术语（每批至多 150 个，超出时分批，后面的批次附上前面已提出的类型并要求复用其 ref，同一 ref 的同义词、定义、父类型和引语合并），连同本体中已有的对象类型摘要，交给推理模型，提出对象类型及层级：中英文名、局部名、定义、同义词、父类型（已有 id 或新的 temp_ref）、引语。
4. `relations`：把对象类型（已有的加上本次新提出的）和相关分块交给模型，提出关系（定义域、值域、基数）与属性（数据类型、单位、是否必填）及引语。
5. `changeset`：由确定性代码生成变更集：
   - **对齐**：与已有元素按规范化名称或同义词匹配。完全相同的跳过；只有同义词或定义有新增的，生成 `update`；其余生成 `create`。
   - **证据核验**：引语在空白规范化后必须出现在对应分块中，找到则记录位置；找不到的项加 `evidence_not_found` 标记，置信度乘 0.5。
   - **引用检查**：关系或属性引用的对象类型既不存在、也不在本变更集中时，丢弃该项。
   - 变更集标题为"识别：{资料名}"。

所有模型调用都要求**结构化输出**（JSON Schema 由 Pydantic 模型生成），提示词里写明：只依据给定原文，引语必须逐字摘自原文，不确定时降低置信度。模型名取自配置：`terms` 与 `relations` 用 `OP_AI_MODEL`，`types` 用 `OP_AI_REASONING_MODEL`。

模型调用一律走流式（Responses 流）：常见的代理会切断约 60 秒没有数据的连接，而一次识别常要一到两分钟。`OP_AI_TIMEOUT_SECONDS` 因此限制的是两次数据之间的等待，不是整次调用。

推理模型的静默推理（2026-11-24 实测）：推理阶段会不会让流整段没有事件、被代理切断，取决于服务端。对 `gpt-6.2-astra` 经本机代理的实测结果是不会：它在推理过程中每隔约 6–14 秒发一个推理条目事件（`response.output_item.added/done`），所以不请求推理摘要时，流也不会静默到 60 秒。三次高强度推理调用（`reasoning.effort=high`，一次纯文本、一次结构化输出、一次请求推理摘要）分别用时 175、251、341 秒，都经代理完整完成，事件间隔最长 13.7、14.1、16.4 秒，没有断连。因此网关**不请求推理摘要**（多出的事件没有用处，摘要内容也要另行处理才能保证不进日志与调用记录）。如果以后换用的推理模型或兼容服务在推理阶段整段无事件、调用被切断（`ai.runs` 里出现 `extract.types` 的 `ai.unavailable` 失败行，耗时接近代理的空闲上限），再对推理模型请求 `reasoning={"summary": "auto"}`，忽略摘要事件，不记录其内容。

失败处理：
- 模型未配置时返回 `ai.not_configured`，不重试。
- 暂时性失败在网关内重试，间隔 2 秒、8 秒，最多 3 次。暂时性失败包括：连接断开、流没有结束事件就关闭、限流、5xx、服务端 `server_error`、输出不合结构。每次尝试都记一行调用记录。
- 不会因重试而改变的失败不重试，包括：401/400、额度耗尽（`insufficient_quota`）、输出被截断或被过滤（`response.incomplete`，记为 `ai.invalid_output`）。
- 网关重试后仍失败的，再按任务重试整份资料。三次都失败后资料状态为 `failed`，`error_code` 为 `ai.unavailable` 或 `ai.invalid_output`。界面上提示"AI 识别暂不可用，资料已保存，可稍后重试"。
- 解析在独立的子进程中运行，超过 180 秒即终止子进程，资料状态为 `failed`，`error_code` 为 `documents.parse_timeout`，不自动重试（畸形文件再解析多半还会卡住），用户可手动重试。解析进程异常退出记为 `documents.unreadable`。
- 写变更集的事务先锁定并核对任务租约：已被新一次执行接管的旧执行不写变更集，以免证据指向已被重建的分块。识别过程中每次写进度也先核对租约，旧执行在下一次写进度时就停下，不再覆盖新执行的进度，也不再继续调用模型。

## 5 接口

全部需要登录；写接口需要 CSRF。角色：`viewer` 只读；`editor` 可上传资料；`reviewer` 可审核、合并、发布、回滚；`admin` 拥有全部权限。字段一律 camelCase，错误用 problem+json。

| 方法与路径 | 说明 | 角色 |
|---|---|---|
| `GET /api/ontologies` | 列表，含元素数、待审核变更集数 | viewer |
| `POST /api/ontologies` | `{ name, key?, description? }`；不传 key 时由名称生成（中文名转为 `ontology-` 加 6 位随机串） | editor |
| `GET /api/ontologies/{id}` | 详情与统计 | viewer |
| `GET /api/ontologies/{id}/elements?kind=&q=` | 元素列表，`q` 搜索名称与同义词 | viewer |
| `GET /api/ontologies/{id}/elements/{elementId}` | 详情，含来源：哪些变更集、哪些证据 | viewer |
| `GET /api/ontologies/{id}/graph` | `{ nodes, edges }`：节点是对象类型；边是关系与父子关系 | viewer |
| `GET /api/ontologies/{id}/export?format=turtle` | 导出工作版本的 Turtle（`text/turtle`） | viewer |
| `GET /api/change-sets?ontologyId=&status=` | 列表，含各决定的计数 | viewer |
| `GET /api/change-sets/{id}` | 详情：全部项及其证据 | viewer |
| `PATCH /api/change-sets/{id}/items/{itemId}` | `{ decision?, edited?, note? }`；`edited` 按 kind 校验 | reviewer |
| `POST /api/change-sets/{id}/decisions` | 批量：`{ itemIds, decision }` | reviewer |
| `POST /api/change-sets/{id}/merge` | 在一个事务里应用已接受的项，返回 `{ applied, skipped: [{ itemId, code }] }`；仍有 `pending` 项时返回 409 `changeset.pending_items` | reviewer |
| `POST /api/change-sets/{id}/reject` | 整体拒绝 | reviewer |
| `GET /api/ontologies/{id}/releases` | 版本列表 | viewer |
| `POST /api/ontologies/{id}/releases` | `{ title, notes? }`；先做校验（见第 6 节），不通过返回 422 `release.invalid` 并附问题列表 | reviewer |
| `GET /api/releases/{id}`、`GET /api/releases/{id}/export?format=turtle` | 版本详情与导出 | viewer |
| `POST /api/releases/{id}/activate` | 设为当前版本（回滚也走这个接口），写审计 | reviewer |
| `POST /api/documents` | multipart：`file`、`ontologyId`；创建记录并排队处理 | editor |
| `GET /api/documents?ontologyId=` | 列表 | viewer |
| `GET /api/documents/{id}` | 状态、进度、错误码、变更集 id | viewer |
| `GET /api/documents/{id}/chunks/{chunkId}` | 分块文本，用于证据高亮 | viewer |
| `GET /api/documents/{id}/file` | 下载原件 | viewer |
| `POST /api/documents/{id}/retry` | 仅 `failed` 状态可用 | editor |
| `GET /api/ai/status` | `{ configured, reachable, model }`；`reachable` 缓存 60 秒；不返回地址与 Key。可达性先调免费的 `models.retrieve`；服务不支持（404、405、501）时改用一次极小的结构化调用（`status.check`，计费、记一行调用记录），成功后 10 分钟内不再重复调用，失败不缓存 | viewer |
| `GET /api/workbench/summary` | 待审核变更集数、对象类型数、处理中的资料数、最近 10 条动态 | viewer |

合并规则：
- `create` 生成新元素（`origin=ai`）；`temp_ref` 先解析为本次新建元素的 id。
- `update` 按目标元素的 `revision` 做乐观锁：元素在变更集生成后被改过的项跳过，`code` 为 `changeset.stale_target`。
- 引用指向被拒绝或被跳过的项时，该项同样跳过，`code` 为 `changeset.dependency_skipped`。
- 合并后变更集状态为 `merged`，写审计。

审计动作：`ontology.created`、`document.uploaded`、`changeset.merged`、`changeset.rejected`、`release.published`、`release.activated`。

## 6 发布与导出

发布前校验：对象类型的父子关系无环；每个关系、属性的定义域和值域都存在且为 active；`local_name` 符合命名规则；`label_zh` 不为空。

Turtle 生成用 rdflib，包含：
- `owl:Ontology`：`rdfs:label`、`owl:versionInfo`（版本号）、`dcterms:created`。
- 对象类型：`owl:Class`，带 `rdfs:label "…"@zh`、`"…"@en`，`skos:definition`，`skos:altLabel`（同义词），`rdfs:subClassOf`。
- 关系：`owl:ObjectProperty`，带 `rdfs:domain`、`rdfs:range`。
- 属性：`owl:DatatypeProperty`，带 `rdfs:domain`，`rdfs:range` 为对应的 xsd 类型；单位写成注解 `op:unit "mm"`（`op:` 为平台命名空间 `https://w3id.org/ontology-platform/vocab#`）。
- SHACL：每个对象类型生成一个 `sh:NodeShape`；必填生成 `sh:minCount 1`，不允许多个生成 `sh:maxCount 1`；属性生成 `sh:datatype`，关系生成 `sh:class`。
- 同一快照两次导出，结果逐字节一致：按 IRI 排序，前缀固定。

## 7 界面

遵守界面规范。新增和改造的页面：

- **工作台**：AI 识别资料卡片变为可用，支持拖拽上传，没有本体时先弹窗起名建本体；四张卡片接入真实数据（待审核数、对象类型数、处理中的资料数、最近动态）；顶栏旁显示 AI 状态。
- **资料**：表格列出名称、状态（步骤进度条）、上传时间、结果（链接到变更集）；失败项显示原因与"重试"按钮；上传按钮是页面主操作。
- **审核**：变更集列表，显示来源资料、待定 / 接受 / 拒绝计数。详情页左右分栏：
  - 左栏按"对象类型 / 关系 / 属性"分组列出各项，每项带 ✦AI 建议、置信度、标记提示（`evidence_not_found` 用 ! 图标）、"接受 / 拒绝"按钮和编辑入口（表单字段同元素）。
  - 右栏显示证据：所在分块的原文，高亮引语，并标出页码或章节。
  - 支持"接受全部高置信度项"（置信度 ≥ 0.8 且无标记）；全部决定后，主按钮"合并到本体"才可用。合并结果中被跳过的项要列出原因。
- **本体**：选择本体；"图谱 / 列表"两个视图。图谱用 `@xyflow/react` 配 dagre 自动布局：节点是对象类型，边是关系，父子关系用虚线。列表按 kind 筛选，可搜索。点击元素打开详情侧栏：定义、同义词、属性与关系、来源证据。右上角提供"导出 Turtle"。
- **版本**：版本列表（版本号、标题、元素数、发布人、时间、是否当前）。主按钮"发布新版本"，弹窗里先显示校验结果；每个版本可以导出 Turtle、设为当前版本（需确认）。
- **设置**：新增"AI 服务"卡片，显示可用状态和模型名，不显示地址和 Key。

## 8 样例与评测

- `samples/steel/docs/`：合成的钢铁冶金资料，至少 4 份：转炉炼钢与精炼工艺规程、板坯连铸工艺规程、热轧带钢工艺规程、Q235B 钢卷质量检验与缺陷判定规范（含表格）。内容由人工编写，不含任何企业真实信息。
- `samples/steel/eval/expected.toml`：期望的对象类型（名称与可接受的同义词）和关系（定义域、名称、值域）。
- `./dev.ps1 eval`：用真实模型处理样例资料，按名称或同义词匹配，统计对象类型与关系的准确率和召回率，结果写到 `.verification/eval/`。它会调用模型并产生费用，所以不纳入 `ci`。

## 9 测试

- 单元与接口测试中，模型调用一律由假网关替代（按输入返回固定的结构化结果），不访问网络。
- 必须覆盖：解析器（各格式、空文件、扫描 PDF 判定）；分块边界；任务领取、心跳、超时重排与重试；流水线对齐与证据核验（引语找不到时打标记、引用缺失时丢弃）；变更集审核、编辑校验、合并的各种跳过原因；发布校验、版本递增、快照不可变、Turtle 逐字节稳定（黄金文件）；回滚；全部接口的角色检查；上传大小与类型限制、重复上传。
- 前端：上传、进度、审核（接受、拒绝、编辑、批量、合并结果）、图谱与列表、发布与回滚的主要交互都有测试。

## 10 分工

| 部分 | 执行者 | 理由 |
|---|---|---|
| 规格、共享骨架（各模块的表、迁移、接口模型、路由注册、配置、compose 中的 worker） | Claude | 共享契约，需要统一设计 |
| AI 网关、识别流水线、提示词、证据核验、样例资料与评测 | Claude | 核心设计，需要反复权衡 |
| `documents` 与 `jobs` 模块（解析、存储、任务队列、worker）及测试 | Codex（high） | 规则清楚，可按文件切开 |
| `ontology` 模块（变更集、合并、发布、导出、图谱）及测试 | Claude 子代理 | 业务规则多，需要自己跑测试反复验证 |
| 前端页面 | Claude 子代理 | 界面质量要求高，需要自己跑测试 |
