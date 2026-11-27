# 007 M4：能力问题、自然语言问答、指标与规则

级别：L2（批次 1 含数据库迁移，批次 3 改审核流程里的元素种类，批次 6 是 AI 写入路径）。其余批次按第 15 节各自定级。
关联：[路线图](../roadmap.md) M4 一行、[架构](../architecture.md)、[003 M3 规格](003-m3-data-binding-query.md)、[接口附录](007-m4-api-shapes.md)、议题 #41。

本文只是规格，不含实现。执行者一栏写"Codex"的批次，按本文和附录就能独立实现；写"Codex 实现 + Claude 审"的批次涉及红线或跨模块的权衡，设计已在本文定下，实现交给 Codex，Claude 逐行审 diff 后才提交，实现中遇到本文没定的取舍时停下来交回 Claude。

## 1 用户能做什么与验收路线

M4 结束时，一个已经按 M3 绑定了 `mes` 样例库的钢铁本体，可以这样用：

1. **写下能力问题。** 编辑在本体页"能力问题"一栏写下这个本体要能回答的问题，例如"哪些 Q235B 钢卷检验不合格？"。可以附期望答案：一组对象、一个数，或只要求"能答"。
2. **用自然语言提问。** 任何登录用户在探索页"问答"一栏提问。平台先让模型把问题翻成一个结构化的查询计划，再由确定性代码校验并执行，代码生成事实与证据。所有用到的数据源都允许取样本值时，模型再根据结果行写说明。回答旁边列出证据：用到的类型、属性、关系、绑定，执行过的每一步查询和结果行，以及这些元素原有的资料出处。
3. **看指标、查规则。** 指标是一种新的元素种类，和其他元素一样经变更集审核、随发布版本固化。规则就是现有的 SHACL 约束元素，M4 补上"按约束检查绑定数据"的能力。探索页"指标与规则"一栏可以算指标、列出违反约束的对象。
4. **答不了时说明缺什么，并一键回流。** 计划里引用了本体里没有的东西，或者引用的类型没有绑定，回答就是"答不了"，并列出缺的元素或绑定。用户点"生成变更提议"，平台走现有的变更集路径生成提议，等人审核；缺绑定时跳到 M3 的 AI 绑定建议。
5. **用能力问题检验本体。** 编辑在"能力问题"一栏点"全部检验"，平台对生效版本把每个问题问一遍，并和期望答案比对，结果按版本记下。

**验收路线**（第 13 节有完整脚本）：导入 `samples/steel/qa/ontology.ttl`，绑定到 `mes` 样例库，发布；新建指标"检验合格率"并发布；依次问五个演示问题，前四个答对且带证据；第五个问题"W240100501 有哪些表面缺陷？"答不了，回流生成的提议经审核、绑定、发布后，再问一次就能答对。

## 2 范围

**做：**

- 能力问题的录入、编辑、检验，以及按版本记录检验结果。
- 自然语言问答：先计划、后执行、再回答，只读，只针对当前生效的发布版本。
- 多跳查询：从一个类型出发，沿最多 5 个关系走到目标类型，每一跳都可以加筛选。`query` 模块新增这一能力，问答和指标共用。
- 指标元素：`count`、`sum`、`avg`、`min`、`max`、`ratio` 六种聚合，带筛选，可以限定在一组对象上。
- 规则检查：按生效版本里的约束元素，逐行检查绑定数据。
- 缺口回流：缺语义元素时，用新的变更集来源 `ai_qa` 生成提议；缺绑定时，转到现有的 AI 绑定建议。
- MCP 新增两个只读工具：`evaluate_metric`、`check_rules`。`search_elements` 可以搜到指标元素。

**不做（留给后续）：**

- 让模型自己调用工具、多轮推理（智能体循环）。M4 每个问题最多调用两次模型。
- 把资料正文放进问答的提示词。资料只以元素已有的证据链接出现在界面上（第 5.6 节）。
- 下推到数据库的聚合（`GROUP BY`、`COUNT`）、分组指标、时间序列、指标之间的公式。
- 新的规则语言、SHACL-SPARQL、跨关系路径的约束（`sh:path` 是关系或属性路径时只报告"未检查"）。
- 多轮对话与追问上下文。每个问题独立。
- 沿父类型继承关系、属性、绑定或约束。M4 查询、计划校验、指标和规则检查都按类型 id 精确匹配。
- MCP 的问答工具（外部智能体本身就是模型，可以用已有的查询工具）。
- 能力问题由 AI 从资料里生成；按审核学习；AI 协助审核（第 17 节只列衔接点）。
- 对 `samples/steel-industry`、`ontologies/steel` 的问答演示。

## 3 决定与理由

| # | 决定 | 理由 |
|---|---|---|
| D1 | 演示建在 `samples/steel` 和 M3 的 `mes` 样例库上，新增 `samples/steel/qa/` 放演示用本体、期望绑定、演示问题 | 只有它有可查询的关系库、Q235B 的异常数据和资料 04；`samples/steel-industry` 只有 RDF 数据，`ontologies/steel` 还没完成。不改 `samples/steel/ontology.ttl`，M3 的测试和评测依赖它 |
| D2 | 问答是"计划 → 校验 → 执行 → 回答"最多两次结构化调用，不做工具调用循环 | `ModelGateway` 只有 `structured`；模型不写 SQL，提示词只用业务标签（第 5.8 节）；执行完全由确定性代码完成，便于用替身网关做不花钱的自动化验收 |
| D3 | 计划只用本体里的短引用（`T1`、`P3`、`R2`、`M1`），由代码映射回元素 id，再经 `BoundModel` 找到表和列 | 和 AI 助手的 `context_for` 同一思路；上下文不读取绑定的物理名称或连接信息，绑定换了表问答照样能用 |
| D4 | 多跳查询放在 `query` 模块，按批走一跳：上一跳的主键用 `in` 条件分批（每批 100 个，即 `IN_VALUES_MAX`）带到下一跳；复合主键退回逐个对象走 | 不改 `connectors`（`SelectQuery` 只支持一个 `join`，只读红线代码）；复用 `planner.hop_join`，单起点用 `planner.joined_key`，批量条件另建函数 |
| D5 | 指标在平台进程里算：按主键分页取行，最多 10,000 行（`metric_rows_max`），超过就报 `metric.too_many_rows` | 连接层没有聚合，加聚合要改红线代码；演示数据很小。下推到数据库留作以后的工作 |
| D6 | 指标是新的元素种类 `metric`，像 M3 的绑定一样经变更集审核、随发布版本固化，不导出为 OWL | 指标是业务语义，必须经审核；复用变更集、审核、发布、回滚，不另开写入路径 |
| D7 | 规则就是现有的 `constraint` 元素，不新增规则种类；M4 只加"按约束检查数据" | SHACL 约束已经能导入、审核、发布、导出；Q235B 的力学性能要求（ReH ≥ 235 等）正好是 `sh:minInclusive` 之类 |
| D8 | 规则检查在 Python 里逐行判断，只支持值层面的检查：`minCount ≥ 1`（不为空）、`min/maxInclusive`、`min/maxExclusive`、`allowedValues`、`min/maxLength`、`pattern`（只支持 `i` 标志）；其余检查报告"未检查" | 逐行判断不需要新的 SQL 运算符；未检查的项列出来，避免让人以为"全部通过" |
| D9 | 能力问题存在新模块 `cq` 的表里，不是本体元素，不随版本固化；每次检验记下当时的发布版本号和结果 | 能力问题是对本体的要求，不是本体内容；编辑直接维护不必审核；但检验结果必须能说明"在哪个版本上答对了" |
| D10 | 问答记录存在 `ai.qa_questions`；证据里保存最多 50 行结果、64 KB | 刷新页面、能力问题比对都要用；行数和大小有上限，避免把业务库搬进平台库 |
| D11 | 回答里的数字和对象由代码生成，模型只写说明文字和"假设"；模型给出的短引用不在本次结果行里的，丢弃并记一条提示 | 防止模型编造；证据可复核 |
| D12 | 缺口回流复用 `ontology.assistant.propose`，来源 `ai_qa`；模型输出复用 `AssistantOut` 与 `ai/assistant.py` 的 `to_item` | 只走现有变更集路径；先按来源只保留类型、关系、属性的 create，再走助手的校验 |
| D13 | 缺绑定不生成新提议，界面转到 M3 的 AI 绑定建议（带上 `typeIds`） | M3 已有完整流程，不新增写入路径 |
| D14 | viewer 也能提问；每人每小时最多 30 个问题（`qa_questions_per_hour`），同时进行中的最多 3 个 | 提问是只读的；模型调用要花钱，需要限流 |
| D15 | 问答和缺口回流都是后台任务（`jobs`），前端轮询，照 `ai/assistant.py` 的写法 | 两次模型调用加多步查询可能超过 30 秒；任务队列已有重试与失败处理 |
| D16 | 新提示词放在新文件 `ai/qa_prompts.py`，不改 `ai/prompts.py` | 批次之间文件范围不重叠；`prompts.py` 里的评测基线不受影响 |
| D17 | MCP 只加 `evaluate_metric`、`check_rules` 两个只读工具，作用域 `objects:read` | 外部智能体最缺的是平台独有的计算；问答本身外部模型可以自己做 |
| D18 | 演示本体故意不含"表面缺陷"，用来演示缺口回流 | 回流是 M4 的完成标准之一，演示要稳定地出现一次缺口 |
| D20 | 计划带一个"答案位置"`target`：答案可以是路径中间某一跳到达的对象，条件是它至少有一条完整的链走到终点 | "哪些 Q235B 钢卷检验不合格"要的是钢卷，而"不合格"这个条件在钢卷后面的检验记录上；路径只能是一条线，没有答案位置就只能返回检验记录，数字和对象都对不上问题 |
| D21 | 回答调用只在所用数据源都允许取样本值（`allow_samples`）时才把结果行发给模型；否则不做第二次调用，界面只显示代码生成的事实与证据 | 数据源管理员关掉"允许取样本值"的意思就是业务数据不发给模型，问答不能绕开这个开关；事实与证据不经模型，照常显示 |
| D19 | M4 只加一个迁移，放在批次 1；编号在转 ready 前按当时 main 的迁移头确定（当前头为 `v0011_change_item_matches`，revision 为 `0011`，新迁移为 v0012） | 与 M3 约定一致：迁移只在第一批，后续批次互不冲突 |

## 4 交付顺序

```
1 后端骨架 → 3 指标元素
1 + 1b 演示数据与界面骨架 → 2 多跳与扫描
2 + 3 → 4 指标计算与规则检查 → 5a 问答后端
1 + 1b → 5b 问答界面
5a + 5b → 6 缺口回流；5a + 1b → 7 能力问题；5b + 6 + 7 → 8 端到端验收与演示
```

批次 1b 的导入测试用现有接口，界面骨架只用本地标签参数和 i18n，不引用批次 1 的类型，可与 1 并行。批次 2 的测试用 1b 的样例；2 和 3 可并行。5b 用生成的接口类型和组件替身，可与 5a 并行。6 和 7 可并行。同时进行的 Claude 实现会话不超过 1 个（议题 #41）。

## 5 自然语言问答

### 5.1 流程

```
POST 问题 → ai.qa_questions 一行（queued）→ 任务 qa.answer
  步骤 plan    ：组装上下文（只含生效版本的语义元素和指标，不含绑定细节）→ 第一次模型调用 → QaPlanOut
  步骤 check   ：确定性校验计划 → 合法则得到 Plan，不合法则得到"缺什么"
  步骤 query   ：经 query、metrics 服务执行，得到 Evidence
  步骤 answer  ：第二次模型调用，输入问题、计划的文字描述、结果行 → QaAnswerOut（所用数据源不允许取样本值时跳过，见第 5.8 节）
  步骤 done    ：代码合成 Answer（数字、对象、证据由代码给出），写回行，状态 answered / unanswerable / failed
```

计划阶段就判定答不了时（模型输出 `intent = "unanswerable"`，或校验发现缺元素、缺绑定），跳过 query 与 answer 两步，直接以 `unanswerable` 结束，不做第二次调用。

### 5.2 计划的结构（第一次模型调用的输出）

新文件 `backend/src/ontology_platform/modules/ai/qa_prompts.py`：

```python
class PlanFilterOut(BaseModel):
    property: str                       # P 引用，例如 "P3"
    op: Literal["eq", "ne", "lt", "le", "gt", "ge", "contains", "startsWith", "in", "isNull", "notNull"]
    value: str | None                   # in 用 values
    values: list[str] | None

class PlanHopOut(BaseModel):
    relation: str                       # R 引用
    direction: Literal["out", "in"]
    filters: list[PlanFilterOut]        # 作用在这一跳到达的类型上

class MissingOut(BaseModel):
    kind: Literal["entity_type", "relation_type", "property", "metric"]
    label_zh: str
    description: str                    # 一句话：问题里的什么概念在本体里找不到
    near: list[str]                     # 相关的现有引用，例如关系的两端 "T5"

class QaPlanOut(BaseModel):
    intent: Literal["objects", "count", "metric", "rules", "unanswerable"]
    start: str | None                   # T 引用
    filters: list[PlanFilterOut]        # 作用在起点类型上
    path: list[PlanHopOut]              # 最多 5 跳（QA_HOPS_MAX）
    target: int | None                  # 答案位置：0 = 起点，i = 第 i 跳到达的类型；None = 路径终点
    metric: str | None                  # M 引用，intent = metric 时必填
    missing: list[MissingOut]           # intent = unanswerable 时至少一项
    assumptions: list[str]              # 对问题的理解，例如"把'不合格'理解为检验记录 passed = false"
```

`PlanFilterOut.value` 按属性数据类型把字符串转换为布尔、数值或日期时间值；`in` 对 `values` 逐项转换，`isNull`、`notNull` 不带值。转换失败或 `op` 不在该属性的 `ObjectProperty.ops` 中，问题以 `qa.invalid_plan` 失败。枚举、uuid 列属于 `opaque` 族，绑定到 string 属性时只允许 `eq`、`ne`、`in`、`isNull`、`notNull`。

各意图的含义：

| intent | 结果 |
|---|---|
| `objects` | 答案位置上的对象（去重），最多 50 个 |
| `count` | 答案位置上的对象个数（最多数到 `metric_rows_max`，超过报 `query.too_many_rows`） |
| `metric` | 指标的值；指标的主体类型等于答案位置的类型时，限定在答案对象上，否则路径必须为空 |
| `rules` | 对答案对象做规则检查，列出违反的约束和对象 |
| `unanswerable` | 不执行查询，只返回 `missing` |

**答案对象**：答案位置上、至少有一条完整的链从起点经过它走到路径终点的对象；每一跳的筛选都要满足。`target` 为空时答案位置就是终点。例："哪些 Q235B 钢卷检验不合格"的计划是 炉次（钢种 = Q235B）→ … → 钢卷 → 质量检验（是否合格 = false），`target = 4`（钢卷），答案是 2 个钢卷，终点上的 3 条检验记录作为依据一并返回。

### 5.3 计划的校验（确定性代码）

新文件 `ai/qa_plan.py`，入口 `check_plan(out: QaPlanOut, refs: RefTable, model: BoundModel, types: ObjectTypeList) -> Plan | Gaps`。`types` 来自 `query.list_types(db, ontology_id)`（M3 已有）：每个属性允许的运算符（`ObjectProperty.ops`）取决于物理列的类型族，`BoundModel` 里没有，`ai` 模块也不直接读 `query/planner.py` 或数据源目录。依次检查，遇到第一类问题就停：

1. **引用存在**：每个 `T/P/R/M` 引用都在本次上下文的引用表里。编造的引用按"缺元素"处理，`missing` 里补一项，`label_zh` 取模型写的说明。
2. **结构**：路径允许 0–5 跳。关系按方向用 `planner.resolve_relation` 匹配当前类型 id；属性必须直属筛选所在的类型，绑定只取该类型自己的 `BoundType.properties`。按第 5.2 节检查运算符和值，每组筛选最多 10 个。
3. **绑定**：起点类型、每一跳的关系与到达的类型、每个筛选用到的属性、指标的主体类型与属性，都在 `BoundModel` 里有绑定。缺的记为 `Gaps.bindings`（类型 id 列表）。
4. **意图**：`metric` 必须给出 `metric`；`count`、`objects`、`rules` 必须给出 `start`；`target` 给出时在 0 到路径跳数之间（越界按结构问题处理）。

结构问题（第 2 条）不算缺口，问题以 `failed`、`qa.invalid_plan` 结束；第 1 条与第 3 条算缺口，以 `unanswerable` 结束。不合法的计划不做第二次模型调用、不自动重试。

### 5.4 执行

问答只经 `query`、`metrics` 两个服务读业务行；`ai` 通过 `connectors` 的服务接口核对取样授权（第 5.8 节）。

- `query.traverse(db, ontology_id, body: PathQuery, *, limit) -> PathResult`（批次 2）：起点筛选 + 逐跳走，返回答案对象（`items`），每个对象带一条"经由"链（它所在的第一条完整链上每个位置的对象主键）；答案位置不是终点时，另返回能走到的终点对象（`tail`，同样最多 `limit` 个，带经由链）。`objects`、`count` 即使 `hops = []` 也走 `traverse`：只筛起点，按主键键集分页直到取完。`total` 取全部匹配的不同主键数，`limit` 只限制展示；超过 `metric_rows_max` 报 `query.too_many_rows`。
- `metrics.evaluate(db, ontology_id, metric_id, *, within: KeySet | None) -> MetricValue` 与 `metrics.check_rules(db, ontology_id, type_id, *, within: KeySet | None, limit) -> RuleReport`（批次 4）。

上限：

| 项 | 上限 | 超过时 |
|---|---|---|
| 起点及每一跳的不同对象数、每一跳的不同（上一跳, 这一跳）对数；`scan` 的行数 | `metric_rows_max` = 10,000 | `traverse`、`traverse_keys`、`scan` 报 `query.too_many_rows`；指标计算的行数超限对外报 `metric.too_many_rows` |
| 一题对业务库发出的 SELECT 总数（含分页、分批、指标或规则扫描，共用一个计数） | 200 | 发第 201 条前报 `qa.too_many_queries` |
| 一个问题的执行时间（query 步骤） | 60 秒 | `query.timeout` |
| 回答中展示和保存的结果行 | 50 | 证据里 `truncated = true` |

查询层的错误（`query.*`）原样作为问题的 `errorCode`，不重试；其中 `query.busy` 与 `query.source_unavailable` 照任务队列的规矩抛 `RetryableJobError`。

### 5.5 回答（第二次模型调用）

```python
class QaAnswerOut(BaseModel):
    answer: str                         # 中文，3–8 句；不写数字以外的取值时也可以只写结论
    cited_keys: list[str]               # 本次回答输入里引用过的行号，例如 K1、K3
    counterpoints: list[str]            # 结果里与结论相悖或需要留意的地方，例如"W240101201 有两次检验都不合格"
```

仅在第 5.8 节允许回答调用时组装 `text`：问题原文、代码生成的计划描述、结果行（类型标签、对象编号、按属性标签列值，每个值截到 200 字）、指标值、违反的规则与条数、截断与上限提示。答案行与作为依据的终点行合计最多 50 行，按输入顺序编号 `K1` 至 `K50`。代码保留短引用到 `ObjectRow.key` 的映射，模型在 `cited_keys` 里只写短引用，不用抄编码主键。

对象编号（`name`）是该行主键的明文值，复合主键用" / "连接，与 `facts.objects[].label` 相同，不带主键列名。理由（#128）：主键值和属性值一样是这次读到的业务行数据，只在第 5.8 节的取样开关打开时发送，口径不变；不给编号时模型只能用 `K1` 这类短引用称呼对象，或者说"未提供编号、无法列出"，与事实区矛盾。列名、表名和连接信息仍不发送。

合成回答（代码）：

- `answer.text` 用模型写的 `answer`，代码再做两步后处理（`counterpoints` 逐条同样处理）：
  - 括号里只有已分配短引用的部分（如"（K1、K2）"）删掉，其余已分配的短引用换成对象编号；在问题、计划描述、对象编号或字符串属性值里原样出现过的同形词（如牌号 `K55`）不动。`answer` 里仍有未分配的短引用时，整段回答按回答调用失败处理（`text` 为空、`counterpoints` 与 `citedKeys` 为空、记 `answer_unavailable`）；某条留意点里有时，只丢弃这一条；
  - `facts.objects` 列出了全部答案对象（条数等于 `count`）时，删掉说"无法列出""未提供编号或清单"之类的句子；删完为空时同样按回答调用失败处理。结果截断时不做这一步，模型可以说明只展示了一部分；
- `answer.facts` 由代码生成：`count`、指标值（带单位与小数位）、对象列表、违规条数；界面以 `facts` 为准显示数字；
- `cited_keys` 中已分配的短引用映射回编码主键，存入 `answer.citedKeys`；丢弃未知短引用，`answer.notes` 记 `cited_unknown`；
- 第二次调用失败（`ai.invalid_output`、不可重试的 `AiError`）时，问题仍以 `answered` 结束，`answer.text` 为空、`answer.notes` 记 `answer_unavailable`，界面只显示事实与证据；
- 所用数据源不允许取样本值时不做第二次调用（第 5.8 节），问题以 `answered` 结束，`answer.text` 为空、`answer.notes` 记 `rows_not_shared`。

### 5.6 证据

证据完全由代码生成，存为 `ai.qa_questions.evidence`（结构见附录 `QaEvidence`）：

- **release**：生效版本的 id 与版本号；
- **elements**：计划用到的每个类型、属性、关系、指标、约束：id、种类、标签、IRI；以及每个元素在本体里已有的资料证据（文档名、片段号、引文，取前 2 条）。引文来自本体模块已存的 `Evidence`，**不发给模型**；
- **bindings**：每项列出绑定所用对象表的 `schema`、`table`、`keyColumns`（主键列名）。物理列名的可见范围与 M3 `ObjectSource` 一致，不列属性对应的列；
- **steps**：每一步执行：类型 id 与标签（`typeId`、`typeLabel`）、条件的可读描述（属性标签 + 运算符 + 值）、语句数、行数、是否截断；
- **rows**：答案对象（最多 50 行，`ObjectRow` 结构加 `via` 经由链）；**tail**：答案位置不是终点时的终点对象（最多 50 行）；
- **metric**、**rules**：指标值与违规明细（如有）。

### 5.7 模型调用的输入、失败与超时

| 项 | 计划调用 | 回答调用 |
|---|---|---|
| `purpose` | `qa.plan` | `qa.answer` |
| `instructions` | `QA_PLAN_INSTRUCTIONS` | `QA_ANSWER_INSTRUCTIONS` |
| `text` | 问题 + 上下文（第 5.8 节） | 第 5.5 节的输入 |
| `schema` | `QaPlanOut` | `QaAnswerOut` |
| `files`、`document_id` | 不传 | 不传 |
| `effort` | `None`（用网关默认） | `None` |

- 网关已有的重试（`RETRY_DELAYS`）之外不再重试。可重试的 `AiError` 抛 `RetryableJobError`，由任务队列按它的规矩重排；不可重试的写 `failed` 与对应的 `ai.*` 码。
- `ai.not_configured`：创建问题时就检查，直接返回 409 `ai.not_configured`，不建行。
- 任务总时长 180 秒（含两次调用与查询），超时写 `failed`、`qa.timeout`。

### 5.8 不把资料正文和凭据带进提示词

计划调用的上下文由新函数 `ontology.qa_context(db, ontology_id) -> QaContext` 生成（批次 1 定签名、批次 5a 实现，放在新文件 `ontology/qa_context.py`），只读生效版本（语义元素用 `released_ontology`，指标用 `released_metrics`）：

- 每个对象类型：引用、中文与英文标签、定义（截到 200 字）、父类型引用、是否有绑定；
- 每个属性：引用、所属类型、标签、数据类型、单位、是否有绑定。可选取值只来自该类型直接约束此属性的 `sh:in`（`allowedValues`），最多 20 个；不读绑定列的枚举或业务行；
- 每个关系：引用、标签、两端类型引用、是否有绑定；
- 每个指标：引用、标签、定义、主体类型、聚合；
- 上限 400 个元素，超过时先保留有绑定的。

提示词使用业务标签，不拼入绑定、资料正文或引文、数据源和连接信息。批次 5a 用替身记录计划与回答的 `text`、`instructions`，只断言其中没有带模式限定的表名（含 `mes.heat`、`"mes"."heat"` 等写法，模式 `mes` 按单词边界 `\bmes\b` 匹配）、与属性英文标签不同的绑定列名、数据源名、连接参数（主机、端口、库名、用户名）及资料 04 原文。`Heat`、`Slab`、`Coil` 可作为英文标签，`message` 可作为普通单词。

**行数据与"允许取样本值"开关。** 计划调用不含任何行数据（只有问题原文和上面的元素清单）。回答调用会带上结果行，所以它受数据源的 `allow_samples` 开关约束：这次执行读过的每个数据源都必须是启用状态且 `allow_samples = true`，才做回答调用；只要有一个不满足，就跳过回答调用，`answer.notes` 记 `rows_not_shared`，界面照常显示代码生成的事实与证据（这些不经模型），并提示"这个数据源没有允许把数据发给模型，所以没有文字说明"（i18n 键 `qa.rowsNotShared`）。判断用 `connectors` 服务已有的数据源信息（同 `ai/binding_suggest.py` 判断能否取样的口径），`ai` 模块不读 `connectors` 的表。问答一栏另有一句固定说明（`qa.dataNotice`）：开关打开时，回答涉及的结果行（最多 50 行）会发给配置的模型。批次 5a 要有测试：开关关着时替身网关只收到计划调用，且计划调用的 `text` 里没有任何行数据；开关打开时回答调用的 `text` 只含第 5.5 节列出的内容。

## 6 能力问题

### 6.1 是什么

能力问题（competency question）是用户先写下的、这个本体必须能回答的问题。它是本体的验收标准，不是本体内容。

### 6.2 存在哪里

新模块 `backend/src/ontology_platform/modules/cq/`，模式 `cq`：

- `cq.questions`：`id`、`ontology_id`、`text`（最多 500 字）、`expect_kind`（`answerable` | `objects` | `number`）、`expect_objects`（jsonb：`{ typeId, keys: string[] }`，最多 100 个）、`expect_number`（numeric）、`tolerance`（numeric，默认 0）、`note`（最多 1000 字）、`position`、`created_by`、`created_at`、`updated_at`、`revision`、`archived_at`；
- `cq.checks`：`id`、`question_id`、`release_id`、`version`、`qa_question_id`（对应 `ai.qa_questions` 的行，只按 id 引用）、`result`（`pending` | `pass` | `fail` | `unanswerable` | `error`）、`detail`（jsonb：比对差异，如多出与缺少的主键、实际数值）、`created_by`、`created_at`、`finished_at`。

### 6.3 怎么录入

本体页"能力问题"一栏：列表 + 新建与编辑对话框。editor 以上可以增改、归档、排序；viewer 只读。期望答案的写法：

- **只要求能答**：答案状态为 `answered` 即通过；
- **一组对象**：选择类型，粘贴主键（每行一个，按 `ObjectRow.key` 的明文形式，平台转换成编码形式）；通过条件是答案位置的类型等于期望类型，且全部答案主键的集合与期望相等（顺序无关，按第 13.2 节读取全集）；
- **一个数**：通过条件是 `|实际 − 期望| ≤ tolerance`。实际值取 `count` 或指标值。

批次 7 另提供从 TOML 导入的入口（`POST …/competency-questions/import`，格式同 `samples/steel/qa/questions.toml`），供演示与测试使用。

### 6.4 怎么检验本体和问答

- **检验一条 / 全部检验**：为每条问题建一个 `ai.qa_questions` 行（`origin = "cq"`，`cq_question_id` 指回），复用问答任务；任务结束时调用 `cq.record_result(db, question)`，`question` 是 `QaQuestion` 冻结副本（`cq` 模块注册的回调，见第 15 节批次 1 的跨模块接口），写入 `cq.checks.result` 与 `detail`。
- **全部检验**不受每人每小时 30 个问题的限制，但受同一本体同时最多 1 次"全部检验"的限制（`cq.check_running` 409），一次最多 50 条。
- **不用模型的覆盖检查**：每条能力问题最近一次检验的计划（`Plan`）会存下来；本体变更集合并或发布后，界面上用 `cq.coverage(db, ontology_id) -> list[CoverageItem]` 显示"最近一次计划引用的元素现在是否还在、是否还有绑定"，不调用模型。

### 6.5 是否随版本固化

不固化。能力问题本身随时可改；每次检验记下当时的发布版本号，列表显示"在第 N 版上通过 / 未通过"。发布新版本后，已有的检验结果标为"旧版本"，不自动重新检验（会花钱），由用户点"全部检验"。

## 7 指标

### 7.1 数据模型

新的元素种类 `metric`。元素已有的字段照常用：`local_name`（必填）、`label_zh`（必填）、`label_en`、`definition_zh`、`definition_en`、`unit`、`subject_id`（= 主体类型 id，用于级联删除与依赖检查）。指标的定义放在新的 jsonb 列 `ontology.elements.metric`（变更项的 `fields` 里同名字段 `metric`）：

```python
class MetricFilter(CamelModel):          # 同 query.schemas.Filter 的形状，引用改为元素 id 或 temp_ref
    property_ref: Ref
    op: FilterOp
    value: Scalar | list[Scalar] | None = None

class MetricDefinition(CamelModel):
    aggregate: Literal["count", "sum", "avg", "min", "max", "ratio"]
    property_ref: Ref | None = None      # sum / avg / min / max 必填，必须是主体类型自己的属性，允许的数据类型见第 7.2 节
    filters: list[MetricFilter] = []     # 总体，最多 10 个
    numerator: list[MetricFilter] = []   # 只有 ratio 用：总体里满足这些条件的占比，最多 10 个
    decimals: int = Field(default=2, ge=0, le=6)
    percent: bool = False                # ratio 显示为百分数
```

存储时引用解析为元素 id（`propertyId`），与约束规则 `ConstraintRuleFields.path_ref` → `ConstraintRule.path_id` 的做法相同。

### 7.2 是否走审核

批次 1 能读取指标；各入口提交 `metric` 变更项时统一返回 422 `changeset.invalid_item`，合并既有变更集时也不得应用指标项。批次 3 才开放手工新建、修改、删除指标，经 `POST /api/ontologies/{id}/edits` 生成 `manual` 变更项，按已有流程审核合并。M4 的缺口回流与 MCP 都不提议指标。合并时按 `ontology/metric_rules.py` 校验：

- 主体类型存在且为对象类型；全部引用的属性存在、有效且 `domain_id` 等于主体类型；聚合与数据类型相容（`sum`、`avg` 只能用 `integer`、`decimal`；`min`、`max` 还可以用 `date`、`dateTime`）；筛选的运算符与数据类型相容；
- 删除主体类型时，`editing._Cascade` 已把 `subject_id` 计入依赖，指标随主体级联删除。对属性，批次 3 让 `editing._View.refs()`、`merge._rule_references` 和 `releases.release_problems` 都读取 `metric.filters`、`metric.numerator` 和聚合 `propertyId`。
- 属性删除沿用约束引用的两道检查，但级联的做法不同：约束是移除受影响的规则、保留约束；**指标只要有一处（总体筛选、分子条件、聚合属性）引用了被删的属性，级联项就是删除整个指标**，不做部分改写——悄悄去掉一个筛选条件，指标的名字不变而算出来的数变了，比指标没了更糟。编辑时的影响预览列出将被删除的指标；合并时若仍有活动指标引用该属性，属性删除项按 `changeset.has_dependents` 跳过；
- 不检查绑定：指标可以先于绑定存在，算的时候没有绑定报 `query.type_not_bound`。

发布时，`release_problems` 在批次 1 的指标分支只检查 `subject_id` 指向有效对象类型。批次 3 再检查三处引用的都是有效属性且直属主体，`sum`、`avg` 只用 `integer`、`decimal`，`min`、`max` 还允许 `date`、`dateTime`。

发布快照保存完整指标，接口 `Element` 增加 `metric`（旧快照缺键时默认为 `null`）。`released_ontology().elements` 仍只含 `SEMANTIC_KINDS`，`ElementCopy` 的字段不增加。`metrics` 与 `ontology/qa_context.py` 通过 `released_metrics` 读生效快照（第 15.2 节）。发布记录不加列；详情要显示指标数时，现数该快照里 `kind = metric` 的行。

### 7.3 怎样计算

`metrics.evaluate`（批次 4）：

1. 从 `ontology.released_metrics` 取生效版本的指标定义；主体类型必须有绑定。
2. 经 `query.scan(db, ontology_id, type_id, filters, *, property_ids, within, max_rows) -> ScanResult`（批次 2）按主键分页取行，`filters` 为总体条件，`within` 为限定的主键集合。
3. 在 Python 里用 `Decimal` 聚合：`count` 计行数；`sum`、`avg` 跳过空值；`min`、`max` 跳过空值；`ratio` 再扫一次"总体 + numerator"，值为两个计数之比，分母为 0 时值为 `null`、`reason = "empty_population"`。
4. 指标计算超出 `metric_rows_max` 报 422 `metric.too_many_rows`；`scan` 自身的 `query.too_many_rows` 在指标边界转为此码，不返回部分结果。

结果带：值（字符串形式的小数）、计数、空值个数、扫描行数、生效版本、执行过的步骤（同问答证据的 `steps`）。

### 7.4 与 SHACL 的关系

指标不是 SHACL，导出 Turtle、RDF/XML 时跳过 `metric` 元素（与绑定种类一样，`SemanticKind` 不含它）。为了与 M3 的分类一致，`ontology/models.py` 新增 `AnalyticKind = Literal["metric"]`，`Kind` 加上 `"metric"`。

## 8 规则

### 8.1 数据模型与审核

规则就是现有的 `constraint` 元素（`domain_id` = 目标类型，`rules: list[ConstraintRule]`，每条规则以 `path_id` 指向一个属性）。新建、修改、删除照 M2 的规矩走变更集。M4 不改约束元素的结构。现有约束表单能填写 `minInclusive`、`maxInclusive`；M4 演示从 Turtle 导入。

### 8.2 检查数据

`metrics.check_rules(db, ontology_id, type_id, *, within, limit=50) -> RuleReport`（批次 4）：

1. 只取生效版本中 `domain_id` 等于 `type_id` 的有效约束元素，不沿父类型继承。
2. 每条规则：`path_id` 是有绑定的属性时参与检查；否则记为 `unchecked`，原因 `path_not_property`、`path_not_bound`。
3. 经 `query.scan` 取出所需列（最多 `metric_rows_max` 行），逐行判断第 3 节 D8 列出的检查；`datatype`、`nodeKind`、`maxCount`、`class` 等记为 `unchecked`，原因 `check_not_supported`。
4. 结果：每条规则的违反行数、最多 `limit` 个违反对象（`ObjectRow` + 违反的检查与实际值），以及约束的 `message`（按当前语言取）。

比较前用同一解析函数读取约束的 `RdfValue`：识别 XSD 局部名或完整 datatype IRI，按 `datatype` 解析 `lexical`。`integer` 按整数词法、`decimal` 和 `double` 按数值词法转为 `Decimal`；`date` 转 `date`，`dateTime` 转 `datetime`。文本取 `lexical`，语言标记 `lang` 不当作值。连接层已返回 `date` / `datetime` 对象；从 `ObjectRow.values` 取到序列化日期时，按属性类型还原后比较。两端的 `datetime` 一律转 UTC，无时区按 UTC。解析失败或类型不相容时，该检查记 `unchecked`、`value_mismatch`。

### 8.3 与 SHACL 的关系

检查的语义与 SHACL Core 对应的约束分量一致，但只是"对绑定数据的近似检查"：数据不转成 RDF，不跑 SHACL 引擎，`sh:path` 只支持直接属性。界面与 MCP 的结果都写明"已检查 N 条，未检查 M 条"。

## 9 缺口回流

### 9.1 缺语义元素

问题以 `unanswerable` 结束且 `gaps.elements` 非空时，界面显示"生成变更提议"按钮（editor 以上可见）。点击后：

1. `POST /api/qa/questions/{id}/gap-proposal` 为该问题创建一个 `qa.gap` 任务。重复发起返回已有结果。若问题的提议状态仍为 `queued` 或 `running`，但该问题最近的 `qa.gap` 任务已结束，则允许重新入队一次。问题状态非 `unanswerable` 或没有语义元素缺口时返回 409 `qa.not_unanswerable`；
2. 任务调用 `ontology.assistant.context_for(db, ontology_id, message=…, page="explore", element_id=None)` 取工作版本上下文，`message` 为问题原文加 `gaps.elements` 的中文描述。提问来自探索页，`context_for` 只把 `page` 写进上下文说明；不按页面分支，`element_id=None` 不附选中元素；
3. 以 `purpose = "qa.gap"`、`instructions = QA_GAP_INSTRUCTIONS`、`schema = AssistantOut` 调用模型；
4. 来源为 `ai_qa` 时，先只保留 `op = create` 且 `kind` 为 `entity_type`、`relation_type`、`property` 的操作，按原顺序取其中前 `OPERATIONS_MAX` 条。再用 `ai/assistant.py` 的 `to_item` 转为 `ProposedItem`，交给 `ontology.assistant.propose(db, ontology_id, message=…, created_by=user_id, items=…, source="ai_qa", title="问答缺口：<问题前 40 字>")`；
5. `gapProposal.dropped` 等于模型返回的操作数减去传给 `propose` 的项数，再加上 `propose` 丢弃的项数。返回了 `change_set_id` 时记 `done` 和该 id；返回 `None` 时记 `empty`、`changeSetId = null`，界面用 `qa.gapEmpty` 提示没有可提议的变更。

通过硬过滤的项仍走 `propose` 已有的校验。`QA_GAP_INSTRUCTIONS` 额外要求：只为 `gaps.elements` 里的概念提议。`AssistantOperationOut.kind` 不含 `metric`，所以 M4 的回流只提议类型、关系、属性；缺指标时缺口卡片只给出说明和"新建指标"入口（editor 以上），提议指标留到第 17 节的后续工作。

问题询问一个对象有哪些 X 时，如果每个 X 都有多个字段，就提议新建 X 的对象类型、描述 X 的属性，以及从已有类型指向 X 的多值关系。已有类型只缺一个单值字段时，只提议该属性，主键已绑定的类型不再重复提议编号属性。

### 9.2 缺绑定

`gaps.bindings` 非空时，界面显示"让 AI 建议绑定"，跳到数据页的 AI 绑定建议对话框并带上 `typeIds`（M3 的 `BindingSuggestionCreate.type_ids`）。不新增接口。

### 9.3 回流之后

提议在审核页出现，来源显示"问答缺口"（i18n 键 `review.source.ai_qa`）。合并、绑定、发布之后，问题详情上的"再问一次"按钮用同一问题文字新建一个问题。

## 10 权限矩阵

| 操作 | viewer | editor | reviewer | admin | 访问令牌 |
|---|---|---|---|---|---|
| 提问、看自己的问题 | ✓ | ✓ | ✓ | ✓ | 不接受 |
| 看别人的问题 | | | | ✓ | 不接受 |
| 生成缺口提议 | | ✓ | ✓ | ✓ | 不接受 |
| 看能力问题与检验结果 | ✓ | ✓ | ✓ | ✓ | 不接受 |
| 增改、归档、导入能力问题；发起检验 | | ✓ | ✓ | ✓ | 不接受 |
| 算指标、查规则 | ✓ | ✓ | ✓ | ✓ | `objects:read`（经 `/api` 与 MCP） |
| 新建、修改、删除指标（变更集） | | ✓ | 合并需 reviewer | ✓ | 不接受 |

问题行属于提问人：`GET /api/qa/questions/{id}` 对别人的问题返回 404 `qa.not_found`（admin 除外），与 `assistant.not_found` 一致。

普通提问在同一事务内按用户 id 取得 PostgreSQL 事务级咨询锁（`pg_advisory_xact_lock`），统计过去一小时的问题数与当前 `queued`、`running` 数。小时计数达到 `qa_questions_per_hour`，或进行中计数达到 `qa_running_max`，就返回 429 `qa.rate_limited` 并带 `Retry-After`；通过才建问题行、入队并提交。并发提交按同一把锁顺序检查。能力问题全部检验的例外见第 6.4 节。

## 11 对 MCP 的影响

`modules/mcp/tools.py` 新增两个工具（批次 4）：

- `evaluate_metric { ontology, metric, within? }` → `MetricValue`。`metric` 可以用元素 id、IRI 或局部名（同 `_element` 的查找规则），`within` 为 `{ type, keys: string[] }`（最多 100 个）。
- `check_rules { ontology, type, keys?, limit? }` → `RuleReport`。

作用域 `objects:read`。批次 1 的 `ELEMENT_KINDS` 与 `ElementKind` 加 `"metric"`，批次 3 实现 `released_metrics` 后，`search_elements` 与 `get_element` 从同一生效版本合入指标结果（`ElementBrief.kind` 加 `metric`，`ElementInfo` 多一个 `metric` 字段）。结果大小仍受 `RESULT_LIMIT_BYTES` 限制。`propose_changes` 不变。

## 12 界面

遵守界面规范：页面上不输出过程信息（任务步骤只用一个状态指示和"计划 / 查询 / 回答"三段进度，不打印日志），所有文字走 i18n，只用设计令牌。

| 位置 | 内容 |
|---|---|
| 探索页（`/explore`）新增两个标签：对象（现有）、问答、指标与规则；路由搜索参数 `tab = objects | ask | metrics` | 去掉 `explore.qaComingSoon` |
| 问答标签 | 左侧：输入框（最多 500 字）、我的最近问题；右侧：回答卡片（结论、事实、假设、留意点），证据折叠区（元素、绑定、步骤、结果行表格、资料出处），答不了时的缺口卡片（缺的元素与绑定、两个回流按钮） |
| 指标与规则标签 | 指标列表（名称、主体类型、聚合），点开算值；规则检查：选类型 → 列出约束、违反条数、违反对象表格、未检查项 |
| 本体页（`/ontology`）新增"能力问题"一栏 | 列表（问题、期望、最近一次结果与版本）、新建编辑对话框、"全部检验"、覆盖检查提示 |
| 本体页元素列表 | 种类筛选多一个"指标"；指标详情与编辑表单（批次 3） |
| 审核页 | 指标变更项的渲染（字段对比）；来源"问答缺口" |

空状态与错误状态（每个都要有 i18n 键与组件测试）：

| 场景 | 显示 |
|---|---|
| 本体没有生效版本 | 问答与指标标签显示"本体还没有发布"，链接到发布页（`query.no_release`） |
| AI 未配置 | 问答输入框禁用，提示去设置页（`ai.not_configured`） |
| 没有问过问题 | "试试问：……"，列出能力问题里的前 3 条（没有能力问题时列固定示例） |
| 问题进行中 | 三段进度；离开页面再回来继续轮询 |
| 答不了 | 缺口卡片；viewer 只看到说明，不显示回流按钮 |
| 失败 | 按 `errorCode` 显示本地化文案和"重试"（新建同文字问题） |
| 超过频率 | `qa.rate_limited`：显示下次可提问的时间 |
| 没有指标 / 没有约束 | 空状态说明，editor 以上显示"新建指标"入口 |
| 指标行数超限 | `metric.too_many_rows`：提示加筛选 |
| 没有能力问题 | 空状态，说明能力问题的作用，editor 以上显示"新建"和"从文件导入" |

前端代码放在 `web/src/features/qa/`、`web/src/features/metrics/`、`web/src/features/cq/`。批次 1b 新建 `web/src/i18n/locales/{zh-CN,en}/{qa,metrics,cq}.json`。现有加载器用 `import.meta.glob('./locales/*/*.json')` 按语言把文件名并成翻译的顶层键。接口类型一律来自 `schema.d.ts`。

## 13 评测与验收

### 13.1 演示数据（批次 1b 交付）

- `samples/steel/qa/ontology.ttl`：在 `samples/steel/ontology.ttl` 的基础上增加：
  - 炉次的"钢种"（`ex:steelGrade`，string）；钢卷的"状态"（`ex:coilStatus`，string）与"厚度"（`ex:thickness`，decimal，单位 mm）； 炉次的钢种用 `sh:in ("Q235B" "Q275B")` 声明可选值。Q2–Q4 按检验的布尔属性“是否合格”或力学性能检查，均不用钢卷状态作筛选。
  - 对象类型"质量检验"（`ex:QualityInspection`）及属性：屈服强度、抗拉强度、断后伸长率、冲击功、是否合格、检验日期；
  - 关系"检验对象"（`ex:inspects`，质量检验 → 钢卷）；
  - 质量检验的四个 SHACL 约束：ReH ≥ 235、370 ≤ Rm ≤ 500、A ≥ 26、KV2 ≥ 27。各用一个有 IRI 的 `sh:NodeShape`，写 `rdf:type`、`sh:targetClass`、`sh:property` 和可选的 `rdfs:label`（`@zh` / `@en`）。在属性节点上写 `sh:path`、`sh:minInclusive` / `sh:maxInclusive` 和带 `@zh` 的 `sh:message`，消息内写资料 04 的条款编号。NodeShape 和属性节点均不写 `rdfs:comment`，否则整个 shape 导入为 `unsupported_shape`；
  - D18 只在演示本体里留出“表面缺陷”的语义缺口，样例库已有 `mes.surface_defect` 表和数据。
- 五跳路径以浇次和轧制事件连接对象。样例中没有一个浇次或轧制事件混有两种钢种，所以从 Q235B 炉次出发，去重后恰好得到 39 条检验记录；混钢种的数据不能沿用这个期望数。
- `samples/steel/qa/expected-bindings.toml`：上面这些类型、属性、关系对 `mes` 库的期望绑定，写法同 `samples/steel/relational/expected-bindings.toml`。
- `samples/steel/qa/questions.toml`：五个演示问题与期望答案（第 13.2 节），既是能力问题的导入文件，也是自动化验收的输入。
- `samples/steel/qa/metrics.toml`：演示指标"检验合格率"的定义（变更项 JSON 的 TOML 写法），供测试与演示脚本建指标。
- 测试副本：`backend/tests/fixtures/qa/steel/`（同 M3 的 `fixtures/connectors/steel/` 做法）。

### 13.2 演示脚本

前置：开发栈已有 `mes` 样例库（M3 的 `seed-steel`）与数据源；AI 已配置。为演示回答文字，所用数据源须启用并允许取样本值；关闭时仍能验收事实与证据（D21）。

| 步 | 操作 | 预期看到 |
|---|---|---|
| 0 | 新建本体"钢铁质量演示"，导入 `samples/steel/qa/ontology.ttl`；导入得到的是一个来源为 `import` 的变更集，先审核合并它；再让 AI 建议绑定，审核合并；发布 v1 | 导入结果的每条演示约束均为 `constraint`，没有 `unsupported_shape`；发布页有 v1；探索页能查到质量检验 43 行 |
| 1 | 本体页手工新建指标"检验合格率"：主体"质量检验"，`ratio`，`numerator` = 是否合格 eq true，百分数 1 位；审核合并；发布 v2 | 指标出现在元素列表与"指标与规则"标签 |
| 2 | 本体页"能力问题"→ 从 `questions.toml` 导入 | 五条能力问题 |
| Q1 | 问"Q235B 一共有哪些炉次？" | 答 18 个炉次。证据：类型"炉次"、属性"钢种"、绑定来源 `mes.heat`、主键列 `heat_no`；零跳只筛起点，条件"钢种 = Q235B"，18 行；"钢种"的资料出处（如有） |
| Q2 | 问"哪些 Q235B 钢卷检验不合格？" | 答 W240101201、W240101503 两个钢卷，留意点提到 W240101201 有两次检验都不合格。证据：路径 炉次（钢种 = Q235B）→ 浇注于 → 产出板坯 → 轧制于 → 产出钢卷 → 检验对象（反向，是否合格 = false），共 5 跳，答案位置在第 4 跳（钢卷）；`items` 是 2 个钢卷，`tail` 是 3 条检验记录 |
| Q3 | 问"Q235B 钢卷的检验合格率是多少？" | 92.3%（36 / 39）。证据：指标"检验合格率"、限定在 Q235B 钢卷的 39 条检验记录上；步骤里有两次扫描（总体 39、合格 36） |
| Q4 | 问"Q235B 的检验记录有没有违反力学性能要求的？" | 3 条违反"ReH ≥ 235"（229、230、229 MPa），其余三条约束 0 条违反；证据是违反的约束元素及其 `sh:message`（含条款编号）；导入流程不生成资料出处 |
| Q5 | 问"W240100501 有哪些表面缺陷？" | 答不了：缺对象类型"表面缺陷"及其与钢卷的关系。点"生成变更提议" → 审核页出现来源为"问答缺口"的变更集，含类型"表面缺陷"、属性（缺陷类型、位置、严重程度）、关系 |
| 3 | 审核合并；对"表面缺陷"让 AI 建议绑定并合并；发布 v3；在 Q5 上点"再问一次" | 答 2 处：边裂（严重）、结疤（一般） |
| 4 | "能力问题"→ 全部检验 | 五条都在 v3 上通过 |

跳数上限取 5（`QA_HOPS_MAX = 5`），正是因为 Q2 的链"炉次 → 浇次 → 板坯 → 轧制事件 → 钢卷 → 质量检验"有 5 个关系。

**比对规则只有一条**：能力问题的期望是"一组对象"时，比对的是答案对象的全集（不是截断后的 50 行）的类型与主键集合；类型不等于期望的 `typeId` 直接判 `fail`，`detail` 写明实际类型。不看经由链，不看计划怎么写。Q2 的期望是 `typeId` = 钢卷、`keys` = W240101201、W240101503：

- 计划 炉次（Q235B）→ … → 钢卷 → 质量检验（不合格），`target = 4`：答案对象是这 2 个钢卷，`pass`；
- 计划 质量检验（不合格）→ 钢卷 → … → 炉次（Q235B），`target = 1`：答案对象同样是这 2 个钢卷，`pass`；
- 上面任一计划漏写 `target`：答案对象是 3 条检验记录或若干炉次，类型不符，`fail`。

为了让比对拿到全集，`ai.qa_questions` 另存一列 `answer_keys`（jsonb：答案类型 id 与全部答案主键，最多 `metric_rows_max` 个），不随接口返回，只给 `cq` 的比对用。完成回调拿到的内部 `QaQuestion` 冻结副本携带这个全集，HTTP 序列化时排除 `answer_keys`。

### 13.3 不花钱的自动化验收（批次 8）

`backend/tests/test_m4_end_to_end.py`，在测试库里（同 `test_m3_end_to_end.py` 的做法）：

1. 用 `fixtures/qa/steel` 导入本体并合并导入变更集、按 `expected-bindings.toml` 直接写绑定变更集并合并、发布；按 `metrics.toml` 建指标并发布；
2. 用**脚本化替身网关**（照 `tests/test_ai_extraction.py` 的 `ScriptedGateway`）：按 `purpose` 与问题文字返回预先写好的 `QaPlanOut` 与 `QaAnswerOut`（放在 `fixtures/qa/steel/plans.toml`）；
3. 依次提问 Q1–Q5，断言状态、`facts`、答案对象类型与全部主键的集合、证据元素 id、Q4 的约束及带条款编号的消息、Q5 的 `gaps`。`evidence.bindings` 每项只有模式、表和主键列名，断言 Q1 没有属性列 `steel_grade`；
4. Q5 发起缺口提议（替身返回固定的 `AssistantOut`），断言生成的变更集来源为 `ai_qa`、只含类型、属性、关系；
5. 合并提议、写"表面缺陷"的绑定、发布，再问 Q5，断言答案；
6. 导入能力问题并全部检验，断言五条 `pass`；
7. 按第 5.8 节检查替身的计划与回答 `text`、`instructions`：无模式限定表名（含引号形式，`mes` 按单词边界匹配）、与属性英文标签不同的绑定列名、数据源名、主机、端口、库名、用户名和资料 04 原文。

另外每个批次有自己的单元测试（第 15 节）。前端：问答、指标、能力问题各有组件测试，覆盖第 12 节的空状态与错误状态。`./dev.ps1 e2e` 的冒烟测试本里程碑不扩展（L2 文件）。

### 13.4 真模型评测（不进门禁）

计划质量取决于模型，替身测不出来。批次 8 提供 `backend/tests/test_qa_eval.py` 的评分函数（纯函数，可单测）：对每个问题比对计划的答案位置及其类型、路径、筛选与期望计划是否等价（筛选顺序无关、关系方向可互换）。真模型的运行由主会话在主检出目录手工执行演示脚本完成，结果记在议题 #41；把它接进 `./dev.ps1 eval` 需要改 `dev.ps1`（L2），留到 M4 之后。

## 14 迁移清单

只新增一个迁移 `v0012_m4_qa_metrics.py`（编号在转 ready 前按当时 main 的迁移头确定；`down_revision` 为当时的头），只加不删：

| # | 改动 | 说明 |
|---|---|---|
| 1 | `ontology.elements`：`ck_elements_kind` 加 `'metric'` | 照 v0009 的 `_replace_check` 写法 |
| 2 | `ck_elements_kind_columns` 新增 `metric` 分支：`parent_id`、`domain_id`、`range_id`、`inverse_id`、`datatype`、`rules`、`turtle`、`binding` 全为 NULL，`subject_id IS NOT NULL AND metric IS NOT NULL`，允许 `unit` | v0009 `NEW_KIND_COLUMNS` 的每个原有分支都补 `AND metric IS NULL`。同步 `ontology/models.py` 的 `_KIND_COLUMNS`、`ELEMENT_KIND_COLUMNS`；`ck_elements_naming` 沿用 |
| 3 | `ontology.elements`：新增列 `metric jsonb NULL` | 旧程序不读它，先加后用 |
| 4 | `ontology.change_items`：`ck_change_items_kind` 加 `'metric'` | |
| 5 | `ontology.change_sets`：`ck_change_sets_source` 加 `'ai_qa'` | |
| 6 | 新表 `ai.qa_questions` | 字段见附录 `QaQuestion` 对应的列，另含 `answer_keys`（jsonb，见第 13.2 节）；`ontology_id`、`release_id`、`asked_by`、`cq_question_id`、`gap_change_set_id` 只按 id 引用、不建外键（同 `ai.assistant_requests`）；索引 `(asked_by, created_at)`、`(ontology_id, created_at)` |
| 7 | 新模式 `cq`，新表 `cq.questions`、`cq.checks` | `cq.checks.question_id` 外键到 `cq.questions`（同模块内）；`release_id`、`qa_question_id` 只按 id 引用 |

`ontology/rules.py` 的 `KIND_REFS`、`REQUIRED_REFS` 都为 `metric` 登记 `subject_ref`，`REF_TARGETS` 允许它指向 `entity_type`；绑定的 `subject_ref` 仍按绑定种类解析。`unit` 允许用于属性和指标，指标的 `localName` 与属性一样用 camelCase。

`downgrade` 先清理 `ai_qa` 变更集、指标变更项，再将其余 `change_items.applied_element_id` 指向 `metric` 元素的值置空，然后删除指标元素，还原检查约束并删去新列、表和模式。顺序同 v0009，避免外键阻止删除。

发布快照（`ontology.releases.snapshot`，jsonb 数组，每项是一个元素的完整内容，`releases.py` 发布时写入）也要在 `downgrade` 里清理：删掉 `kind = 'metric'` 的项；批次 1 之后发布的快照里每个元素都带 `metric` 键，其余项去掉这个键。否则旧程序对比两个历史版本时会用旧的种类清单校验快照而失败（`compare.py`、`schemas.py` 里读快照的模型）。发布记录本来不可变，降级是唯一改它的地方，改完的版本里不再有指标，这一点同样写进批次 1、3 的 PR 描述。批次 1 的降级测试要包含一条带指标项的发布快照。

**读取容忍与回退。** 旧程序的 `service._elements` 默认只查 `SEMANTIC_KINDS`（`ontology/service.py:175`），`released_ontology` 也只读取这些种类（`ontology/bindings.py:724`）。默认元素列表、已有对象查询与 MCP 只读工具可照常工作。凡取 `all_kinds=True` 的调用，遇到工作库中的指标都会在 `service.py:176` 排序时由 `_kind_order` 的 `KINDS.index(element.kind)`（`service.py:111`）抛 `ValueError`。主检出中的调用点如下（路径相对于 `modules/ontology/`）：

- 合并 `merge.py:700`、发布 `releases.py:172`、工作版本对比 `compare.py:165`、删除影响与保存 `editing.py:286,474`、导入 `importing.py:467`；
- 变更集创建与校验 `service.py:350,1593`、AI 助手提议 `assistant.py:332`（含走这里的 MCP 提议）、绑定工作视图 `bindings.py:287`、绑定提议 `binding_proposals.py:86`。按绑定种类列元素时，`service.py:831` 也会打开 `all_kinds`。

批次 1 及之后的程序遇到指标都能运行；批次 1 之前的程序在新库上能运行的前提是库里没有指标，而指标只有批次 3 之后的程序能建；所以把程序回退到批次 1 之前的版本，要先降级迁移（降级会删掉指标、相关变更项，以及历史版本快照里的指标）。批次 1、3 的 PR 描述都须写入这段兼容结论和上述调用点清单。

`test_migrations.py` 的升降级往返覆盖新迁移；批次 1 用数据库夹具插入指标、`ai_qa` 变更集及其他来源、其 `applied_element_id` 指向该指标的变更项，验证降级能清理指标、置空外键并恢复旧约束；同批经应用提交指标变更项仍须被拒。

## 15 批次切分

### 15.1 约定

- 后端共享文件归批次 1：迁移、`main.py`、根 `models.py`、`worker.py`、`settings.py`、`.env.example`、`backend/tests/conftest.py`、`test_openapi.py`，以及需要变动的 `pyproject.toml`、`uv.lock`。`web/src/api/schema.d.ts` 由批次 1 运行 `gen-api` 生成；以后只有接口形状确需变化时才重新生成。前端共享路由、`web/src/app/navigation.ts` 与三个翻译命名空间归批次 1b，两批文件范围不重叠。
- HTTP 路由在批次 1 按最终签名建好，服务函数先抛 501 `http.not_implemented`。跨模块的入口函数在批次 1 定好签名与冻结数据类，函数体抛 `NotImplementedError`。
- 批次 1 的 `test_m4_skeleton.py` 为各后续后端批次留 `xfail(strict=True)` 用例；各批实现时启用对应断言。1b 的导入测试、5b 的组件测试各自在本批交付，无需改后端骨架测试。
- 新设置项（批次 1 加到 `settings.py` 与 `.env.example`）：`qa_questions_per_hour = 30`、`qa_running_max = 3`、`metric_rows_max = 10000`、`qa_job_timeout_seconds = 180`。
- 所有批次：不改 `connectors` 模块；不改 `ai/prompts.py`；ruff、mypy strict、eslint、tsc 通过；新功能有测试。

### 15.2 跨模块接口（批次 1 定型）

```python
# modules/query/service.py（新增，批次 2 实现）
async def traverse(db: AsyncSession, ontology_id: UUID, body: PathQuery, *, limit: int = 50) -> PathResult: ...
async def scan(
    db: AsyncSession, ontology_id: UUID, type_id: UUID, filters: Sequence[Filter], *,
    property_ids: Sequence[UUID], within: KeySet | None = None, max_rows: int,
) -> ScanResult: ...

# modules/query/schemas.py（新增）
QA_HOPS_MAX = 5
class PathHop(CamelModel): relation_id: UUID; direction: Direction; filters: list[Filter] = Field(default_factory=list, max_length=FILTERS_MAX)
class PathQuery(CamelModel): type_id: UUID; filters: list[Filter]; hops: list[PathHop] = Field(min_length=0, max_length=QA_HOPS_MAX); target: int | None = None; limit: int = Field(default=50, ge=1, le=200)   # target 为 None 时取终点
@dataclass(frozen=True) class KeySet: type_id: UUID; keys: tuple[str, ...]           # ObjectRow.key 的编码形式
@dataclass(frozen=True) class Step: type_id: UUID; type_label: str; conditions: tuple[str, ...]; statements: int; rows: int; truncated: bool   # QueryStep 对外为 typeId、typeLabel
class PathRow(ObjectRow): via: list[str]                                              # 第一条完整链上每个位置的对象主键（位置 0 到终点）
class PathResult(CamelModel): release: ReleaseRef; type_id: UUID; items: list[PathRow]; total: int; truncated: bool; tail_type_id: UUID | None; tail: list[PathRow]; tail_total: int; steps: list[StepOut]   # type_id、items、total 说的是答案位置；tail* 只在答案位置不是终点时有值
async def traverse_keys(db: AsyncSession, ontology_id: UUID, body: PathQuery) -> KeySet: ...   # 全部答案主键，供指标、规则的 within 与能力问题比对用；超过 metric_rows_max 报 query.too_many_rows
@dataclass(frozen=True) class ScanResult: release: ReleaseRef; rows: tuple[ObjectRow, ...]; steps: tuple[Step, ...]

# modules/ontology/bindings.py（批次 1 建类型和桩，批次 3 实现）
@dataclass(frozen=True) class MetricCopy: id: UUID; local_name: str; label_zh: str; label_en: str | None; definition_zh: str | None; definition_en: str | None; subject_id: UUID; unit: str | None; metric: MetricDefinition   # 生效快照中的指标定义，属性引用已解析为 id
@dataclass(frozen=True) class ReleasedMetrics: release: ReleaseRef; metrics: tuple[MetricCopy, ...]
async def released_metrics(db: AsyncSession, ontology_id: UUID) -> ReleasedMetrics: ...

# modules/metrics/service.py（新模块，批次 4 实现）
async def evaluate(db: AsyncSession, ontology_id: UUID, metric_id: UUID, *, within: KeySet | None = None) -> MetricValue: ...
async def check_rules(db: AsyncSession, ontology_id: UUID, type_id: UUID, *, within: KeySet | None = None, limit: int = 50) -> RuleReport: ...

# modules/ontology/qa_context.py（新文件，批次 5a 实现）
async def qa_context(db: AsyncSession, ontology_id: UUID) -> QaContext: ...   # QaContext：text 与 refs（短引用 → 元素 id）

# modules/ai/qa.py（批次 5a 实现）
# ai.models.QaQuestionRow 是 ORM 行；ai.schemas.QaQuestion 是冻结的 Pydantic 副本。
JOB_KIND = "qa.answer"
async def create_question(db, ontology_id, body: QaQuestionCreate, *, user_id: UUID, origin: QaOrigin = "user", cq_question_id: UUID | None = None) -> QaQuestion: ...
def make_answerer(session_factory, gateway: ModelGateway, model: str) -> Handler: ...
def register_listener(listener: Callable[[AsyncSession, QaQuestion], Awaitable[None]]) -> None: ...   # cq 用它接收结束的问题副本（含内部 answer_keys）

# modules/ai/qa_gap.py（批次 6 实现）
JOB_KIND = "qa.gap"
async def enqueue_gap_proposal(db: AsyncSession, question_id: UUID, *, user_id: UUID, settings: Settings) -> tuple[QaQuestion, bool]: ...
def make_gap_proposer(session_factory, gateway: ModelGateway, model: str) -> Handler: ...

# modules/cq/service.py（新模块，批次 7 实现）
async def record_result(db: AsyncSession, question: QaQuestion) -> None: ...  # 经 ai.qa.register_listener 注册
async def coverage(db: AsyncSession, ontology_id: UUID) -> list[CoverageItem]: ...
```

`traverse` 路由将 `body.limit` 传给服务的 `limit`，取值 1–200，默认 50；计数与 `traverse_keys` 始终覆盖答案全集。`QueryStep.typeLabel` 取生效版本里的类型标签。

模块依赖方向：`ai → ontology, query, metrics, connectors`（`connectors` 用于核对取样授权）；`metrics → ontology, query`；`cq → ai`（只经 `create_question` 与监听）；`query → ontology, connectors`（不变）。`test_module_boundaries.py` 自动发现模块（`ROOT.rglob`），新模块 `metrics`、`cq` 不用登记；批次 1 确认它对上面的依赖方向通过，不改这个测试文件。`worker.py` 在批次 1 登记 `qa.answer`、`qa.gap` 两种任务（处理函数先写为抛出不可重试错误的桩）。

### 15.3 批次表

#### 批次 1：后端骨架（L2，Codex 实现 + Claude 审，强度高，约 1,400 行）

| 项 | 内容 |
|---|---|
| 依赖 | 无 |
| 负责的路径 | 第 14 节迁移与字段规则；`ontology/models.py`、`schemas.py`（`Element.metric`，保持 `ElementCopy` 字段契约）、`rules.py`、`service.py`、`editing.py`、`merge.py`（指标写入校验）、`releases.py`、`compare.py`、`mcp/tools.py`（读取容忍）。`ontology/bindings.py` 的 `released_metrics` 类型与桩、`ontology/qa_context.py` 桩；`query/{schemas,service,api}.py`、`modules/metrics/**`、`modules/cq/**` 的模型、类型、服务桩与路由；`ai/{models,schemas,qa,qa_gap,api}.py` 的 `QaQuestionRow`、冻结 `QaQuestion`、任务桩与路由。第 15.1 节后端共享文件、生成的 `schema.d.ts`、`backend/tests/test_migrations.py`、`backend/tests/test_m4_skeleton.py` |
| 不许碰 | `connectors/**`、`ai/prompts.py`、`ontology/assistant.py` |
| 入口 | 第 15.2 节签名。`Kind` / `KINDS` 及各种类枚举识别 `metric`；发布检查指标时只校验主体是有效对象类型。发布记录及审计的 `binding_count` 只数 `BINDING_KINDS`。变更项校验拒绝 `metric`（含手工编辑、服务提议、合并入口）；应用没有入口能建指标 |
| 验收 | 迁移和外键用例见第 14 节；数据库夹具预置指标后，逐项覆盖该节全种类读取路径，无未知种类错误，含指标的快照、对比、绑定计数均正确，`Element` 可返回指标定义，`ElementCopy.model_fields` 不含 `metric`；主体缺失或种类不对不能发布。应用提交指标返回 422 `changeset.invalid_item`，不能合并出指标。OpenAPI 覆盖附录全部新路由，桩返回 501，运行 `gen-api` 核对生成类型，骨架测试见第 15.1 节。PR 描述附第 14 节兼容结论与完整调用点清单；`./dev.ps1 ci -Report` 通过 |
| 执行者 | Codex（强度高）；Claude 逐行审 diff，重点看迁移（升降级与第 14 节回退前提）、权限与路由的角色限定 |

本批接近 1,500 行，预算含生成的接口类型。手写部分限于读取容忍、写入校验和最小可调用骨架；业务实现及对应测试放在后续批次。

#### 批次 1b：演示数据与界面骨架（L1，Codex，强度中，约 550 行）

| 项 | 内容 |
|---|---|
| 依赖 | 无；导入走 M3 接口，导航、`tab` 和翻译不依赖批次 1 生成的类型 |
| 负责的路径 | `samples/steel/qa/**`、`backend/tests/fixtures/qa/steel/**`（`plans.toml` 归 8）、`backend/tests/test_qa_demo_import.py`；`web/src/i18n/locales/{zh-CN,en}/{qa,metrics,cq}.json`、`web/src/routes/_app/explore.tsx` 的 `tab` 参数和标签入口、导航 `web/src/app/navigation.ts` 及所需页面入口 |
| 验收 | 用导入接口读取演示 `ontology.ttl`，逐条按 IRI 核对第 13.1 节的约束均为 `constraint`，无 `unsupported_shape`；四条力学约束都能读出带条款编号的中文消息。样例与测试副本一致；两种语言的命名空间键一致；三个 `tab` 可导航 |
| 执行者 | Codex（强度中） |

#### 批次 2：多跳与扫描（L1，Codex，强度高，约 1,000 行）

| 项 | 内容 |
|---|---|
| 依赖 | 批次 1、1b（测试用演示数据） |
| 负责的路径 | `backend/src/ontology_platform/modules/query/traverse.py`（新）、`query/scan.py`（新）、`query/planner.py` 的批量条件函数、`query/service.py` 里 `traverse`、`traverse_keys` 与 `scan` 的函数体、`query/api.py` 里 `POST /api/ontologies/{id}/objects/traverse` 的实现；`backend/tests/test_query_traverse.py`、`test_query_scan.py` |
| 不许碰 | `query/planner.py` 的已有函数签名（可以新增函数）、`connectors/**`、其他模块 |
| 入口 | `traverse(db, ontology_id, body, *, limit)`、`traverse_keys(db, ontology_id, body)`、`scan(db, ontology_id, type_id, filters, *, property_ids, within, max_rows)` |
| 分批与分页 | 起点、每一跳的每个批次和 `scan` 都按主键键集分页到 `has_more` 为假，每条 SELECT 最多 `query_max_rows` 行（默认 1,000）。批量连接按目标主键和来源主键共同排序、续页，保留跨页的所有来源—目标对。单列主键每 100 个一批；新增 `in` 条件函数，沿用 `planner.hop_join`。`planner.joined_key` 只生成单起点 `eq`，保留签名供复合主键逐个走；新函数对连接表的每个输入值同样检查类型转换及无损往返。结果按 `(side, 列名)` 建索引，分别读主表和连接表，现有 `rows.objects` 的单列名索引不适用于这里 |
| 答案与上限 | 自终点回筛完整链，在 `target` 上按主键去重，`via` 保留第一条完整链；零跳时直接取全部匹配起点。`scan` 的 `within` 每 100 个一批。起点、任一跳累计的不同对象或不同键对、扫描行数超过 `metric_rows_max` 报 `query.too_many_rows`。整题所有业务 SELECT 合计最多 200 条，每条单独连接，沿用 `query_timeout_seconds`（默认 15 秒）；整题查询阶段最多 60 秒（`query.timeout`），含模型调用的问答任务最多 180 秒（`qa.timeout`）。语句超限报 `qa.too_many_queries`，途中换版报 `query.release_changed` |
| 验收 | 用 `fixtures/qa/steel` 的绑定：Q1 的 `count` 与 `objects` 都走零跳，`limit` 小于 18 时仍得 `total = 18`、答案全集 18 个炉次；炉次（钢种 = Q235B）走 5 跳到质量检验，得到 39 条、其中 `passed = false` 的 3 条；同一路径最后一跳加"是否合格 = false"、`target = 4` 时 `items` 是 2 个钢卷、`tail` 是 3 条检验记录，反方向的写法（从质量检验出发、`target = 1`）结果相同；某个钢卷没有检验记录时不出现在 `target = 4` 的结果里；连接表关系 `rolledIn` 两个方向都对；小页跨越每一跳的页边界，主表与连接表同名列能各取正确的键；复合主键、连接表值无法无损转换的用例；超限与版本变化用例；去掉 `test_m4_skeleton.py` 里批次 2 的 `xfail` |
| 执行者 | Codex（强度高：多跳分批与上限的边界多） |

#### 批次 3：指标元素（L2，Codex 实现 + Claude 审，强度高，约 1,200 行）

| 项 | 内容 |
|---|---|
| 依赖 | 批次 1 |
| 负责的路径 | `ontology/metric_rules.py`（新）、`rules.py`、`editing.py`、`merge.py`、`mergeplan.py`、`service.py`（开放指标变更项与元素列表）、`releases.py`（补全发布校验）、`bindings.py`（实现 `released_metrics`）；`mcp/tools.py` 读生效版本指标，`ontology/rdf/**` 导出跳过指标；`web/src/features/ontology/metric-*.tsx`、审核的 `metric-item.tsx` 与种类分派；`test_ontology_metrics.py`、相应组件测试 |
| 不许碰 | `ontology/assistant.py`、`ontology/bindings.py` 的公开签名、`query/**`、`ai/**` |
| 验收 | 手工新建、修改、删除指标经审核合并；不合法定义（非主体属性、`sum` 用 string、`ratio` 无分子条件）报 `metric.invalid`。分别让总体筛选、分子条件、聚合属性引用被删属性，验证影响预览列出该指标、级联项是删除整个指标（没有"更新指标"的级联项），仍有活动引用则合并跳过属性删除（`changeset.has_dependents`）；删除主体级联删除指标。发布时检查缺失、停用、归属与聚合类型错误。`released_metrics` 从生效快照读版本号及完整指标，切换版本时随之切换；`released_ontology` 仍只含语义种类，MCP 可按种类检索、读取发布的指标；导出 Turtle 无指标；绑定计数不计指标。审核页显示指标对比。PR 描述附第 14 节兼容结论与完整调用点清单 |
| 执行者 | Codex（强度高）；Claude 审 diff，重点看合并与级联 |

#### 批次 4：指标计算、规则检查与 MCP 工具（L1，Codex，强度中，约 900 行）

| 项 | 内容 |
|---|---|
| 依赖 | 批次 2、批次 3 |
| 负责的路径 | `modules/metrics/**`（`service.py`、`aggregate.py`、`rule_check.py`、`api.py` 实现）；`modules/mcp/tools.py`（两个新工具，指标从 `released_metrics` 读取）；`web/src/features/metrics/**`（探索页"指标与规则"标签）；`backend/tests/test_metrics_evaluate.py`、`test_metrics_rules.py`、`test_mcp_metrics.py` |
| 不许碰 | `query/**`、`ontology/**`、`ai/**`、`mcp/transport.py` |
| 验收 | 检验合格率总体 43 条、Q275B 之外 39 条时为 36/39；`within` 限定生效；分母为 0 返回 `null` 与 `empty_population`；超过上限报 `metric.too_many_rows`；规则检查对质量检验报告 ReH 违反 3 条、其余 0 条；不继承父类型约束；数值与日期边界、带与不带时区的时间、词法错误 `value_mismatch` 各有用例；`datatype` 等记 `unchecked`；MCP 两个工具的作用域与错误码；探索页标签的组件测试覆盖空状态 |
| 执行者 | Codex（强度中） |

#### 批次 5a：问答后端（L1，Codex，强度高，约 1,100 行）

| 项 | 内容 |
|---|---|
| 依赖 | 批次 2、3、4 |
| 负责的路径 | `ai/qa.py`、`ai/qa_plan.py`（新）、`ai/qa_prompts.py`（新）、`ai/qa_answer.py`（新：合成回答与证据）、`ai/api.py` 里问答路由的实现；`ontology/qa_context.py` 的函数体；`backend/tests/test_ai_qa.py`、`test_ai_qa_plan.py`、`test_ai_qa_prompt_safety.py` |
| 不许碰 | `ai/prompts.py`、`ai/assistant.py`、`ontology/assistant.py`、`query/**`、`metrics/**`、`connectors/**` |
| 验收 | 第 5 节全部行为；替身网关驱动 Q1–Q4 得到期望的 `facts` 与证据；编造引用 → `unanswerable`；筛选值转换失败、`opaque` 列使用 `contains` 等结构错误 → `qa.invalid_plan`；回答调用失败 → `answer_unavailable`；`K1` 等映射回主键，未知引用丢弃并记 `cited_unknown`；数据源不允许取样本值时不做回答调用、记 `rows_not_shared`；按用户并发提交仍受小时与进行中两个上限约束；他人问题 404；提示词安全测试（第 5.8 节） |
| 执行者 | Codex（强度高：提示词与校验） |

#### 批次 5b：问答界面（L1，Codex，强度中，约 500 行）

| 项 | 内容 |
|---|---|
| 依赖 | 批次 1 的 `schema.d.ts` 和 1b 的标签入口、翻译；用接口替身做组件测试，可与 5a 并行 |
| 负责的路径 | `web/src/features/qa/**` 的问答标签与组件测试；缺口提议交互 `gap-*.tsx` 归 6 |
| 验收 | 提问、轮询、最近问题、事实与证据、答案行与终点依据分别展示；覆盖第 12 节问答的空状态、错误状态、答不了及 viewer 权限。`rows_not_shared` 时显示事实、证据与 `qa.rowsNotShared` |
| 执行者 | Codex（强度中） |

#### 批次 6：缺口回流（L2，Codex 实现 + Claude 审，强度高，约 450 行）

| 项 | 内容 |
|---|---|
| 依赖 | 批次 5a、5b |
| 负责的路径 | `ai/qa_gap.py`、`ai/qa_prompts.py` 里新增 `QA_GAP_INSTRUCTIONS`（只追加，不改批次 5a 的内容）、`ai/api.py` 里 `gap-proposal` 路由的实现；`web/src/features/qa/gap-*.tsx`（新）；`web/src/features/review/` 里来源标签只加 `ai_qa` 的 i18n 键使用处；`backend/tests/test_ai_qa_gap.py` |
| 不许碰 | `ontology/assistant.py`（只调用）、`ontology/binding_proposals.py` |
| 验收 | Q5 生成 `ai_qa` 变更集。替身混入 `update`、`delete`、新建约束和合法 `create` 时，变更集只含新建类型、属性、关系，丢弃数准确；另测种类硬过滤。全部丢弃时 `empty`、`changeSetId = null`，界面显示 `qa.gapEmpty`；不满足发起条件返回 `qa.not_unanswerable`。同题重复返回已有结果；viewer 403；缺绑定时界面跳转并带 `typeIds` |
| 执行者 | Codex（强度高）；Claude 逐行审 diff（AI 写入路径，红线：只能经 `ontology.assistant.propose` 生成变更集，不得有别的写入口） |

#### 批次 7：能力问题（L1，Codex，强度中，约 900 行）

| 项 | 内容 |
|---|---|
| 依赖 | 批次 5a、1b（与批次 6 可并行） |
| 负责的路径 | `modules/cq/**` 的实现（`service.py`、`compare.py`、`importing.py`、`api.py`）；`web/src/features/cq/**`；`backend/tests/test_cq.py` |
| 不许碰 | `ai/**`（只调用 `create_question` 与 `register_listener`）、`ontology/**` |
| 验收 | 增改、归档、排序、乐观锁（`revision`，冲突 `cq.stale`）；TOML 导入；单条与全部检验；三种期望的比对；同一本体同时只有一次全部检验；新版本发布后旧结果标为旧版本；覆盖检查不调用模型；组件测试 |
| 执行者 | Codex（强度中） |

#### 批次 8：端到端验收与演示（L1，Codex 实现 + Claude 审，强度中，约 600 行）

| 项 | 内容 |
|---|---|
| 依赖 | 批次 1、1b、2、3、4、5a、5b、6、7 已集成 |
| 负责的路径 | `backend/tests/test_m4_end_to_end.py`、`backend/tests/test_qa_eval.py`、`backend/tests/fixtures/qa/steel/plans.toml`、`docs/development.md` 的 M4 演示一节、`docs/roadmap.md` 的 M4 状态 |
| 验收 | 第 13.3 节七步全部通过；去掉骨架里最后一条 `xfail`；主会话按第 13.2 节在开发栈上手工演示一遍，结果记入议题 #41 |
| 执行者 | Codex（强度中）；Claude 审 diff 并亲自跑一遍演示脚本与真模型评测（付费评测只在主检出目录，最多 1 次） |

## 16 已定的事项

- 问答只针对生效版本，不能问工作版本（与 M3 查询一致）。
- 问题文字最多 500 字；答案文字最多 4,000 字（超出截断）。
- 问答记录永久保留，M4 不做清理；admin 可以在设置页按本体看全部问题（列表接口带 `askedBy=all`）。
- 演示问题的期望值（18、2 个钢卷、36/39、3 条违规、2 处缺陷）来自 `samples/steel/relational/02-data.sql`，样例数据变化时 `questions.toml` 同步修改。

## 17 与"从审核中学习、AI 协助审核"的衔接点

只列接口位置，不展开设计：

- `ai.qa_questions` 的 `plan`、`gaps`、`gap_change_set_id`：可以与变更集的审核结果关联，统计"问答缺口提议的接受率"。
- `ai_qa` 来源的变更集与其他 AI 来源同样经审核，审核决定可以作为提示词改进的样本。
- 能力问题的检验结果（`cq.checks`）：AI 协助审核时，可以对待合并的变更集预跑能力问题，提示"合并后哪些能力问题会答不了"（`cq.coverage` 是不调用模型的一半）。
- `AssistantOperationOut.kind` 加入 `metric` 以后，缺口回流可以提议指标。
- 计划评分函数（`test_qa_eval.py`）可以用于在审核样本上比较提示词版本。
