# 03 · 十四模块功能与依赖矩阵

本矩阵为 **PROPOSED**，验收均 **NOT_RUN**。导航按资产、建模、数据、查询分析、AI、治理运维组织，不机械建立十四个顶级菜单。

所有页面必须覆盖加载、空数据、错误、拒绝、冲突及长任务状态；命令写审计，查询和任务带Trace，运维可定位对应记录。公共接口见 [02](02-target-architecture.md)，阶段见 [04](04-roadmap-and-dependency-dag.md)。

| 模块／角色 | 页面与真实用例 | API／权威数据 | 验收与监控 | 阶段／依赖 |
|---|---|---|---|---|
| 01 资产中心／建模者 | 资产目录、导入导出、版本与引用 | Draft/Release；PG、正式包 | 搜索与权限过滤、版本溯源、导入任务 | G2→G3；发布 |
| 02 设计中心／建模者 | 三栏编辑、源码、图、Diff、冲突处理 | Draft、Validation；Turtle权威 | 无损保存、并发修订、编辑错误 | G2→G3；01/08 |
| 03 术语标准／专家 | SKOS、别名、单位、标准依据 | Terminology；PG及语义资产 | 多义词、版本、生效范围、引用 | G3；01 |
| 04 AI构建／专家 | 抽取候选、消歧、接受/拒绝进入草稿 | ExtractionProposal/Decision | 证据定位、拒绝可追溯、不能自动发布 | G6；02/05/12 |
| 05 文档知识／知识管理员 | 上传、OCR、片段、检索、任务重试 | Document/Job/Evidence；RustFS/PG | 原件可追溯、解析失败、恶意文档 | G6；14 |
| 06 连接映射／数据管理员 | 五源连接、Schema、映射、对账 | Connection/Mapping/Identity；PG | 真连接、分页、超时、只读、凭证脱敏 | G4；03/14 |
| 07 实体图谱／分析者 | 谱系、实例图、身份冲突 | EntityGraph/Identity；源/Jena/PG | 跨厂重号、历史编码、多对多 | G2样例→G4；06 |
| 08 验证推理／专家 | SHACL报告、推理范围与问题定位 | ValidationReport；Shapes/Jena | 约束正反例、公理保真、耗时 | G2→G3；02 |
| 09 发布治理／审核发布者 | 影响分析、审批、发布、回滚 | Proposal/Release/Activation | 不混版、审批修订一致、故障恢复 | G2→G3；08/14 |
| 10 语义查询／分析者 | 发现、查询、执行树、证据 | SemanticQueryResult；网关 | 六态、预算、取消、源故障 | G2→G4；06/09 |
| 11 指标规则／业务专家 | 口径、模拟、版本、确定性执行 | Metric/Rule/Evaluation；PG/源 | 精度、时间、缺失、规则三态 | G5；03及G4数据查询能力 |
| 12 MCP智能体／用户及管理员 | 能力目录、运行、审批、模型策略 | Capability/Run/Event；PG | Schema、越权、重连、接管、费用 | G2→G7；10/14 |
| 13 业务应用／质量分析者 | Q235B调查、假设、反证、反馈 | Run/Evidence/Feedback | 正确谱系、未知及备选解释、Evals | G2样例→G7；10/11/05 |
| 14 平台治理运维／管理员审计员 | 权限、审计、行为、中文运维、告警 | Governance/Operations；PG/LGTM | 登录拒绝、审计完整、恢复和隐私 | G1贯穿G8 |

11指标规则的完整数据依赖为G4 Connections/SemanticQuery，不将04 AI构建中心作为指标计算前置；此处明确原计划表格与其下方澄清的一致含义。

## 本体建模能力支持分级

规划覆盖二十项：①IRI/命名空间；②Class；③子类；④对象属性；⑤数据属性；⑥domain/range；⑦annotation/语言标签；⑧individual/类型断言；⑨等价类；⑩互斥类；⑪逆属性；⑫属性特征；⑬some/all限制；⑭hasValue；⑮基数；⑯交并补表达式；⑰属性链；⑱import及依赖；⑲身份公理；⑳事件/时态建模。

G2编辑①—⑧及最小SHACL；G3为其余能力建立“支持编辑／源码保留只读／阻断”清单。OWL-Time与身份策略按标准建模，不伪称都是OWL内建构造。复杂公理即使不能图形编辑，也不得静默丢失。SHACL、SKOS及推理能力分别验收。
