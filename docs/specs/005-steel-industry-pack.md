# 005 钢铁全流程案例包：分层、命名与编码

- 级别：L0（样例与文档，不改平台代码）
- 关联：议题 #41（总计划）；[001 M1 规格](001-m1-ai-ingestion.md)；[samples/README.md](../../samples/README.md) 的案例包规则
- 状态：设计已由用户确认（2026-11-25，第 13 节）

名词：**通用层**指本规格设计、随仓库开源的钢铁行业本体与案例包 `samples/steel-industry/`；**企业层**指某个钢厂在通用层之上的私有扩展，不入库。**实物件**指有自己编号、能被称重和搬运的一件物料（板坯、钢卷、包装件）。**代码**指代码表里的一项（机组类型、处置类型等），**编码**指实物件、单据的编号。

## 1 目标与范围

现有的 `samples/steel/` 只有炉次、浇次、板坯、轧制事件、钢卷 5 个类，资料是 4 份 Markdown，评测分数已接近饱和。本规格新建一个覆盖钢铁全流程的案例包，不改 `samples/steel/`。

目标：

1. **一套设计好的通用本体**：从转炉到发运，命名、编码、单位、时间、代码表都有统一规则，复用 W3C 等公开标准词汇，能回答第 9 节的能力问题。
2. **一份真实格式的评测资料**：原创的 PDF、Word、Excel 规程和台账，覆盖第 8 节的七类难点，作为识别评测的开发集。
3. **企业层能接上来**：企业的私有概念按第 11 节的规则挂在通用层下面，其中能泛化的经审核提升进通用层。

范围外：平台代码改动；炼铁、焦化、烧结、长材（棒线材、型钢）；能源介质、设备点检维修（另有 `maintenance` 案例包）；工艺窗口和配方参数。

## 2 分层

| 层 | 内容 | 命名空间 | 入库 |
|---|---|---|---|
| 外部词汇 | PROV-O、OWL-Time、SOSA、QUDT、SKOS、Dublin Core、SHACL | 各自官方 IRI | 只引用 IRI，不复制文件，不 `owl:imports` |
| 通用层 | 制造骨架 + 钢铁领域概念 + 代码表 + 约束 + 标准书目 | `stl:`（第 4.1 节） | 是 |
| 企业层·产品适配 | 某 MES 产品的建模方式与接口字段到通用层的映射 | 私有 | 否，放 `.verification/private-docs/` |
| 企业层·现场 | 某厂的机组、编码、工艺与客户规则 | 私有 | 否 |

规则：

1. **依赖只向下**。企业层可以引用、细分通用层；通用层不引用企业层的任何 IRI。通用层只依赖外部词汇里第 3 节列出的项。
2. **通用层只用公开来源和原创表述**。概念的定义用自己的话写，出处只写标准编号与名称、公开文献。厂商文档的原文、字段名、电文结构不进通用层。
3. **一个命名空间，多个模块文件**。通用层所有术语共用 `stl:`，按模块分文件（第 10 节）。术语换模块不改 IRI。

## 3 复用的外部词汇

依据：调研结论（标准 79 条、可复用本体 18 项，均附官方链接，核实日期 2026-11-25）。只引用下表的项；其他候选的处理见表后。

| 词汇 | 版本 | 用在哪 | 对齐方式 |
|---|---|---|---|
| PROV-O | W3C 2013 | 工序执行、实物来源 | `stl:Operation ⊑ prov:Activity`；`stl:MaterialPiece ⊑ prov:Entity`；`stl:derivedFrom ⊑ prov:wasDerivedFrom`；`stl:producedBy ⊑ prov:wasGeneratedBy` |
| OWL-Time | W3C 2017 Recommendation | 只作注释参照 | 时间点一律用 `xsd:dateTime` 属性（第 6 节），不建 `time:Instant` 节点 |
| SOSA | W3C 2017 Recommendation | 取样、测量、检验结果 | `stl:Sample ⊑ sosa:Sample`；`stl:Observation ⊑ sosa:Observation`；`stl:sampledAt`、`stl:resultAt` 在映射表里分别对应 `sosa:phenomenonTime`、`sosa:resultTime`（值域不同，不声明子属性） |
| QUDT | 3.5.4 | 单位与量纲 | 每个数值属性用 `stl:unit` 注一个 QUDT 单位 IRI、用 `stl:quantityKind` 注一个 QUDT 量纲 IRI（第 7 节） |
| SKOS | W3C 2009 | 代码表、同义词、定义 | 代码表是 `skos:ConceptScheme`；名称用 `skos:prefLabel`/`skos:altLabel`，定义用 `skos:definition` |
| Dublin Core Terms | 2020-01-20 | 标准书目、来源 | `dcterms:identifier`、`dcterms:title`、`dcterms:issued`、`dcterms:source` |
| SHACL | W3C 2017 | 编码格式、必填、基数、单位与时区 | 约束只写在 `shapes.ttl` |

不导入、只登记对照的：

- **ISA-95 / IEC 62264**：没有官方 OWL，正文收费。只把公开的对象名（Material Lot、Equipment、Process Segment、Operations Schedule / Performance 等）写进映射表作对照。
- **GS1 EPCIS 2.0.1**：分卷对照 `TransformationEvent`，打包对照 `AggregationEvent`，出入库扫描对照 `ObjectEvent`。只写进映射表（`skos:closeMatch`），不断言为其子类：本包的事件不保证满足 EPCIS 的交换语义。
- **CROS、IOF Core、BFO、EMMO**：首版不对齐。CROS 只用来核对概念粒度；IOF、BFO 等跨工厂交换确有共同上层需求时再加映射文件。
- **UCUM**：只在接口数据里保存原始单位串，不作 RDF 对象；**OM 2**：只作外部数据的映射目标。

映射表用 SSSOM（Simple Standard for Sharing Ontological Mappings）的 TSV 格式，单独一个文件、单独记版本：每行写我方 IRI、对方 IRI 或对象名、谓词（`skos:exactMatch`/`closeMatch`/`broadMatch`/`relatedMatch`）、依据、作者、日期。

## 4 命名规则

### 4.1 IRI

- 通用层基址：`https://w3id.org/ontology-platform/steel/`，前缀 `stl:`（第 13 节待确认）。用斜杠结尾，术语直接接在后面：`stl:Heat` 即 `https://w3id.org/ontology-platform/steel/Heat`。
- 代码表：`stl:code/<方案名>`；代码：`stl:code/<方案名>/<代码值>`。例：`stl:code/disposition-type/DEGRADE`。代码的 IRI 等于方案 IRI 加 `/` 加代码值，只看 IRI 就知道它属于哪张表、取值是什么。
- 标准书目条目：`stl:std/<机构>-<编号>-<年份>`，全部小写，点和斜杠换成连字符。例：GB/T 228.1-2021 → `stl:std/gbt-228-1-2021`；EN 10204:2004 → `stl:std/en-10204-2004`。每个版次一个条目，新版用 `dcterms:replaces` 指向旧版。
- 标准牌号：`stl:std/<书目条目本地名>/grade/<牌号>`，牌号里 `A–Z`、`0–9` 以外的字符换成 `-`，原写法存 `skos:notation`。例：GB/T 2518-2019 的 DX51D+Z → `stl:std/gbt-2518-2019/grade/DX51D-Z`。牌号是公开标准里的事实，放通用层 `standards.ttl`，不放合成数据。
- 模块本体 IRI：`stl:module/<模块名>`，版本 IRI 加 `/<语义化版本>`。
- 样例数据（个体）：`urn:synthetic:steel-industry:<类的本地名小写>/<编码>`，例 `urn:synthetic:steel-industry:heat/H22600123`。合成数据永远不用 `stl:` 命名空间，避免与本体术语混在一起。
- IRI 一经发布不改、不复用。改名只改标签；概念作废用 `owl:deprecated true` 加 `dcterms:isReplacedBy`。

### 4.2 本地名

| 元素 | 规则 | 例 |
|---|---|---|
| 类 | 英文单数名词，UpperCamelCase；用全称，不用缩写（缩写放 `skos:altLabel`）；不带模块或层的前缀 | `Heat`、`CastSequence`、`HotRolledCoil`、`QualityDisposition` |
| 对象属性 | lowerCamelCase，读作"主语 属性 宾语"成句；不用 `has` 开头，除非是整体对部分 | `castIn`（炉次 castIn 浇次）、`derivedFrom`、`performedOn`、`hasPart` |
| 数据属性 | lowerCamelCase 名词；单位不进名字（单位见第 7 节）；时间属性以 `At` 结尾，日期以 `On` 结尾 | `thickness`、`netMass`、`sampledAt`、`issuedOn` |
| 布尔属性 | `is` 开头，只用于本身就是二值的事实 | `isTransitionSlab` |
| 代码方案名 | 英文小写，连字符分隔 | `unit-type`、`disposition-type` |
| 代码值 | 第 5.3 节 | `BOF`、`DEGRADE` |

禁止：本地名里出现中文、空格、版本号、厂名、MES 产品名或接口字段名；同一个英文词在不同模块表示不同概念；用代码值当类名（`BOF` 是代码，不是类）。

**类与代码怎么选**：有自己的属性或约束、会被单独引用的，建类（板坯、热轧卷、质量处置）；只是给事物分类、取值有限、没有自己属性的，进代码表（机组类型、缺陷类型、处置类型、样品类型）。实物件的类表示**产品状态**，一件实物从生到灭不换类：一卷热轧卷经酸轧后变成的是一卷新的冷硬卷（新实物、新编码），不是同一个对象换了类。

### 4.3 标签、定义与注释

每个类、属性、代码都必须有：

- `rdfs:label` 中文和英文各一个（`@zh`、`@en`），`skos:prefLabel` 与 `rdfs:label` 相同；行业通行的别称、缩写放 `skos:altLabel`（例：浇次的 `altLabel` 有"连浇炉数组""cast sequence"；转炉有"BOF""LD 转炉"）。
- `skos:definition` 中文一句话，写"是什么、和谁区分"。例：炉次——"一座炼钢炉一次冶炼出钢得到的一批钢水及其全部产出的身份；同一炉次的钢水化学成分视为一致。"
- 引自标准的术语加 `dcterms:source` 指向书目条目（第 4.1 节），定义仍用自己的话写。
- 需要说明边界的写 `skos:scopeNote`（例：板坯编码里的炉次段只说明"按哪个炉次编号"，不说明来源炉次）。

## 5 编码规则

编码是实物件和单据的身份。本节规定通用层合成数据使用的编码，也是给企业层做映射的参照：企业的真实编码规则放企业层，映射到同一组属性。

### 5.1 原则

1. **一物一码，终身不变**。实物件和单据只有一个主编码，存在 `dcterms:identifier`（字符串），同一类内唯一。
2. **新实物新编码**。切割、分卷、合卷、酸轧出口等产生新实物的工序，产出件一律取新编码，并用 `stl:derivedFrom` 记下直接来源件（第 8.2、8.3 节）。改判、让步、封闭、移库、重新分配订单不产生新实物，**不改编码**。
3. **编码只用来识别，事实另有属性**。编码可以带有可读的分段（类型、机组、年份），但每一段承载的事实都必须另有一个显式属性（炉座、年份、流号）。查询和推理只看属性，不解析编码；SHACL 检查编码与属性是否一致。
4. **类型字母开头**。所有实物件和单据的编码第一位是类型字母（第 5.2 节），只看编码就知道是什么东西；各类型字母互不相同，不用 `I`、`O`（易与 `1`、`0` 混淆）。
5. **定长、大写、无空格**。只用 `A–Z` 和 `0–9`；表示从属关系的复合编码用一个 `-` 连接父编码和子序号（订单行、库位）。
6. **年份与流水号**。`YY` 是该实物或单据**创建事件**发生时的公历年后两位，按北京时间（`+08:00`）计；流水号每年从 1 起、左补零、不复用。
7. **不设校验位**（合成数据规模不需要）。企业层若有校验位，作为企业层规则记录。

### 5.2 编码表

| 对象 | 类 | 结构 | 长度 | 例 | 各段含义（对应属性） |
|---|---|---|---|---|---|
| 炉次 | `stl:Heat` | `H` + 炉座号 1 + `YY` + 流水 5 | 9 | `H22600123` | 炉座号 → `stl:producedOnFurnace`（2 号转炉）；26 → 开始冶炼年份 |
| 浇次 | `stl:CastSequence` | `Q` + 铸机号 1 + `YY` + 流水 4 | 8 | `Q1260045` | 铸机号 → `stl:castOn` |
| 板坯 | `stl:Slab` | `S` + 编号炉次的后 8 位 + 流号 1 + 流内序号 2 | 12 | `S22600123203` | 编号炉次 → `stl:numberingHeat`；流号 → `stl:strandNumber`；序号 → `stl:sequenceInStrand` |
| 热轧卷 | `stl:HotRolledCoil` | `R` + 机组号 1 + `YY` + 流水 6 | 10 | `R126000456` | 机组号 → `stl:producedBy` 的执行机组 |
| 冷轧段钢卷 | `stl:FullHardCoil` 等 4 类 | `C` + 机组段码 2 + 机组序号 1 + `YY` + 流水 6 | 12 | `CPL126000789` | 机组段码 `PL` 酸轧、`CA` 连退、`CG` 镀锌、`RC` 重卷，加序号即产出机组（`PL1` = `PLTCM1`） |
| 包装件 | `stl:Package` | `P` + `YY` + 流水 7 | 10 | `P260001234` | |
| 样品 | `stl:Sample` | `T` + `YY` + 流水 7 | 10 | `T260004567` | 取自谁看 `stl:sampleOf`，不进编码 |
| 检验批 | `stl:InspectionLot` | `L` + `YY` + 流水 6 | 9 | `L26000321` | |
| 质量处置单 | `stl:QualityDisposition` | `N` + `YY` + 流水 6 | 9 | `N26000088` | |
| 质量证明书 | `stl:MillCertificate` | `Z` + `YY` + 流水 6 | 9 | `Z26000210` | |
| 销售订单 | `stl:SalesOrder` | `D` + `YY` + 流水 6 | 9 | `D26001234` | |
| 订单行 | `stl:SalesOrderLine` | 订单号 + `-` + 行号 3 | 13 | `D26001234-010` | 行号按 10 递增，留插行余地 |
| 生产订单 | `stl:ProductionOrder` | `W` + `YY` + 流水 6 | 9 | `W26004321` | |
| 发运单 | `stl:Shipment` | `F` + `YY` + 流水 6 | 9 | `F26000777` | |
| 设备 | `stl:Equipment` | 机组类型代码 + 序号 1 | 3–6 | `BOF2`、`CC1`、`PLTCM1` | 类型 → `stl:unitType` |
| 天车 | `stl:Crane` | `CR` + 库区代码 + 序号 1 | 6 | `CRCY12` | 所属库区 → `stl:locatedIn` |
| 库位 | `stl:StorageLocation` | 库区代码 3 + `-` + 行 2 + 列 2 + 层 1 | 9 | `CY1-03121` | 行、列、层 → `stl:row`、`stl:column`、`stl:tier`；库区 → `stl:locatedIn` |
| 内部钢种 | `stl:SteelGrade` | `G` + 流水 4 | 5 | `G1023` | **不带成分含义**，成分范围见钢种规范 |

**板坯编码里的炉次段**是最容易误读的一处：它只表示"这块坯按哪个炉次编号"（`stl:numberingHeat`，恰好一个），不表示"钢水来自哪个炉次"（`stl:sourceHeat`，一到两个）。换炉过渡坯的两个来源炉次见第 8.1 节。板坯编码的序号段（`stl:sequenceInStrand`）是编号用的号，和实物在炉内的出坯次序（`stl:positionInHeat`，第 8.1 节）分开存：普通坯两者相等；二次切割产出的新坯取同炉同流下一个未用的序号，出坯次序不变。

**标准牌号不是编码**。Q235B、DC04、DX51D+Z 这类名称由产品标准规定，建模为 `stl:StandardGrade`，名称存 `skos:notation`、所属标准用 `stl:definedIn` 指向书目条目（同一名称在不同标准、不同版次里是不同条目）。一个内部钢种可以满足多个标准牌号（`stl:satisfies`），订单行要求的是标准牌号加标准版次。

### 5.3 代码表

规则：

- 代码值只用大写字母和数字，1–10 位；可读的英文缩写或单词，有通行符号的用符号（化学元素用元素符号的大写：`C`、`SI`、`MN`、`P`、`S`，酸溶铝 `ALS`），不用无意义的流水号；在本方案内唯一，发布后不改、不复用。
- 每个代码有 `skos:notation`（数据类型 `stl:<方案名驼峰>Code`，例 `stl:DispositionTypeCode`）、中英文 `skos:prefLabel`、`skos:definition`，用 `skos:inScheme` 指向方案。
- 代码之间有上下位时用 `skos:broader`；需要互斥说明时在 `skos:scopeNote` 里写明和谁的区别。
- 数据里引用代码用对象属性指向代码 IRI（如 `stl:dispositionType stl:code/disposition-type/DEGRADE`），不存代码字符串。
- 一个代码需要第二种写法时，另加一个不同数据类型的 `skos:notation`，不另建代码。例：`unit-type` 的 `PLTCM` 另有段码 `PL`（数据类型 `stl:LineSegmentCode`），供冷轧段钢卷编码使用。

首批代码方案（取值在 `codes.ttl` 里给全；下面列出语义最关键的几张）：

| 方案 | 代码 |
|---|---|
| `unit-type` 机组类型 | `BOF` 转炉、`EAF` 电弧炉（通用层留口，样例数据不用）、`LF` 钢包精炼炉、`RH` 真空循环脱气、`CC` 板坯连铸机、`HSM` 热连轧机、`PLTCM` 酸洗冷连轧、`CAL` 连续退火、`CGL` 连续热镀锌、`RCL` 重卷、`PCK` 包装 |
| `disposition-type` 质量处置类型 | `RELEASE` 放行；`HOLD` 封闭待处理；`DEGRADE` 降级：同一实物改为较低一档的质量规格，原订单是否保留另行决定；`REASSIGN` 改判：把实物重新指定为另一物料规格或另一订单，原规格作废；`CONCESSION` 让步接收：规格不变，经批准在限定订单、数量和期限内接收偏差；`REWORK` 返修；`SCRAP` 报废 |
| `judgement-result` 判定结果 | `CONFORM` 合格、`NONCONFORM` 不合格、`PENDING` 待判 |
| `analysis-type` 化学分析类型 | `HEAT` 熔炼分析（代表整炉、用于判定的那一次，一个炉次只有一条，通常取精炼结束后的钢水样）、`PROCESS` 过程分析（转炉终点样、精炼过程样等，只用于工艺控制，不用于判定）、`PRODUCT` 成品分析（取自成品，按成品化学成分允许偏差判定） |
| `sample-type` 样品类型 | `ENDPOINT` 转炉终点样、`REFINING` 精炼工位取的钢水样（含精炼过程中和精炼结束时取的样）、`TUNDISH` 中间包样、`PRODUCT` 成品样、`MECHANICAL` 力学性能样、`COATING` 镀层试样。样品类型说"在哪里、取的什么"，分析类型说"做什么用"：精炼结束样是 `REFINING` 样品，它的分析可以是 `HEAT` |
| `share-basis` 份额基准 | `LENGTH` 按长度、`MASS` 按质量 |
| `measurement-method` 采集方式 | `MANUAL` 手工、`AUTOMATIC` 自动 |
| `contribution-evidence` 来源证据等级 | `MEASURED` 有测量依据的份额、`ESTIMATED` 按规则估算、`UNKNOWN` 知道来源但份额未知 |
| `inspection-document-type` 检验文件类型 | `T21`、`T22`、`T31`、`T32`，对应 EN 10204:2004 的 2.1、2.2、3.1、3.2（标准原写法放 `skos:altLabel`） |
| `coating-type` 镀层类型 | `GI` 纯锌镀层、`GA` 锌铁合金镀层（镀锌卷是一个类，镀层种类是代码，不各建一类） |
| `movement-event-type` 移动事件 | `LIFT` 吊起、`RELEASE` 释放落位、`LOAD` 装车、`DISPATCH` 出厂 |

## 6 时间

1. 所有时间点用 `xsd:dateTime`，**必须带时区**（SHACL 检查）；日期用 `xsd:date`。
2. 一个时间属性只表示一种含义，名字说清楚是哪种：

| 含义 | 属性 | 只用在 |
|---|---|---|
| 计划 | `plannedStartAt`、`plannedEndAt` | 计划类（生产订单、切割计划、移库指令） |
| 实际发生 | `actualStartAt`、`actualEndAt`、`occurredAt` | 执行与事件 |
| 取样 | `sampledAt` | 样品、测量 |
| 出结果 | `resultAt` | 分析与试验结果 |
| 创建 | `createdAt` | 实物件与单据；编码的 `YY` 取它的年份。实物件的 `createdAt` 等于产出它的工序的 `actualEndAt`（SHACL 检查） |
| 系统登记 | `recordedAt` | 任何记录，可选 |

3. 计划时间和实际时间不出现在同一个对象上（第 8.4 节）。时长不存，由开始、结束算出；资料里两个时间口径不一致时，按资料原样分别保留，不合并。

## 7 单位与数值

1. 每个数值属性只有一个单位，用 `stl:unit` 注在属性定义上（QUDT 单位 IRI），数据里只存数字（`xsd:decimal`）。不同单位的同一量（mm 与 m）是两个属性，或统一到一个单位，不混用。
   - **序号不是数值属性**：设备序号、流号、流内序号、订单行号、库位的行列层、炉内顺序等是位置或编号的一部分，用 `xsd:positiveInteger`，不带 `stl:unit`、`stl:quantityKind`。
   - **件数**（让步接收的卷数、铸机流数）是计数：用 `xsd:nonNegativeInteger`，带 `stl:unit unit:NUM`、`stl:quantityKind quantitykind:Count`。
2. 首批单位：长度 `unit:MilliM`（厚、宽）与 `unit:M`（长）、质量 `unit:TONNE`、温度 `unit:DEG_C`、化学成分 `unit:PERCENT`（质量分数，N、H、O 也用它，与产品标准的写法一致）、在线测氧 `unit:PPM`（只用于测量，不用于成分分析）、强度 `unit:MegaPA`、冲击功 `unit:J`、拉速 `unit:M-PER-MIN`、镀层质量 `unit:GM-PER-M2`。写本体时逐个对 QUDT 3.5.4 核对 IRI 确实存在。
3. 化学成分不为每个元素各建一个属性：一次分析（`stl:ChemicalAnalysis`）下挂多条元素结果（`stl:ElementResult`），每条有元素代码（`stl:code/chemical-element/MN`）和质量分数；成分限值同样用质量分数，比较时不换算单位。
4. 质量要分清**毛重、净重、理论重量**（三个属性），不用一个"重量"。

## 8 难点的建模

这七类是评测资料要覆盖、本体必须表达清楚的情形。

### 8.1 换炉过渡坯与混浇坯

- 板坯有 `numberingHeat`（恰好 1 个，编码用）和 `sourceHeat`（1–2 个，钢水来源）。
- 两个来源时，用 `stl:HeatContribution` 记每个来源：炉次、证据等级（`contribution-evidence`）、份额（可选，必须同时给份额的基准：长度或质量）。
- `isTransitionSlab` 表示资料或系统明确标为过渡坯。只凭"是一炉的头坯或尾坯"不能推出是过渡坯。
- 位置分开存：在炉次内的顺序 `positionInHeat`（同一炉次、同一流内的出坯次序，多流铸机每流各自从 1 起）、在浇次内的顺序 `positionInSequence`（同一浇次、同一流内的出坯次序，只用于板坯）；炉次在浇次中的炉序另用 `heatPositionInSequence`，不与板坯共用属性；换钢种的过渡坯另记前后两个钢种（各一个属性，不写进说明文字）。

### 8.2 切割与重新赋号

- 切割计划（`stl:CuttingPlan`，计划长度、切序）与切割执行（`stl:Cutting`，实际长度、时间）是两个对象。
- 每块板坯由一次切割产出（`producedBy`）；二次切割产出新板坯、新编码，`derivedFrom` 指向原坯。

### 8.3 分卷与合卷

- 一次工序执行可以有多个投入（`inputPiece`）、多个产出（`outputPiece`）。
- **每个产出件**都用 `derivedFrom` 记直接来源件；一件投入出现在多个产出的来源里不算重复投料。合卷（焊接）的产出有多个来源。
- 可选记录产出件在来源件上的区段（起止长度），用来传递缺陷位置。

### 8.4 计划与实绩

- 计划类：`ProductionOrder`、`CuttingPlan`、`MovementOrder`；执行类：各 `Operation` 子类与事件。执行用 `fulfills` 指向它完成的计划。
- 计划属性只出现在计划类上，实际属性只出现在执行类上（SHACL 检查）。

### 8.5 质量判定与处置

- 判定（`stl:QualityDecision`）针对一件实物或一个检验批，记结果代码、依据的规格及其标准版次、判定时间。
- 处置（`stl:QualityDisposition`）记处置类型（第 5.3 节）、原因、缺陷、处置前后的规格与订单行、批准人角色；`CONCESSION` 另记适用订单、数量与期限。
- 处置不改实物的编码和类；`REASSIGN` 不是 `DEGRADE`，`CONCESSION` 也不是永久降级。

### 8.6 测量的测点与时点

- 每次测量（`stl:Observation`）有：被测对象（炉次或实物件）、测量项（代码）、测点（`stl:MeasurementPoint`，属于某机组）、`sampledAt`、`resultAt`、数值、单位、方法（手工或自动）。
- 同一炉次的多次测量靠测点、测量项和取样时间区分；消息到达时间不能代替取样时间。
- 测量项代码与存值的属性一一对应（如 `TEMP` 只配 `stl:temperature`），SHACL 检查两者一致。

### 8.7 库区位置与移动

- 计划目的地在移库指令上；实际移动由事件组成：`LIFT`（吊起，实物进入天车）、`RELEASE`（落位，到达库位）。
- 实物的当前位置由最后一个已确认的事件得出：吊起之后、落位之前，位置是天车。本体不存"当前位置"字段作为事实来源。

## 9 能力问题

通用层发布前，样例数据上必须能用 SPARQL 回答下列问题（每题一个 `.rq` 和期望结果）。两条验收主线：**A** 一块跨炉换钢种的过渡坯一直追到发运；**B** 一卷热轧卷酸轧后分成两卷，分别检验、一卷让步接收、两卷分别发运。

| 编号 | 问题 | 主线 |
|---|---|---|
| CQ1 | 某发运钢卷追溯到哪些炉次，每个炉次的证据等级是什么 | A |
| CQ2 | 某板坯是否过渡坯；两个来源炉次、各自钢种、在浇次中的位置 | A |
| CQ3 | 某浇次按顺序包含哪些炉次，换钢种发生在哪两炉之间 | A |
| CQ4 | 某冷轧段钢卷的母卷、热轧卷、板坯分别是什么 | A、B |
| CQ5 | 某热轧卷分出了哪些卷，各自的判定结果和发运单 | B |
| CQ6 | 某卷经过哪些处置，处置前后的规格、订单行，让步的适用范围 | B |
| CQ7 | 某炉次的熔炼分析是否满足订单行物料规格的成分范围（规格注明所依据的牌号与标准版次；样例数据里的限值是合成示例值，不抄标准正文） | A |
| CQ8 | 某炉次精炼期间各测点的温度，按取样时间排序 | A |
| CQ9 | 某卷的力学性能结果、取样位置、试验方法标准 | B |
| CQ10 | 某质量证明书覆盖哪些卷、依据哪些标准版次、检验文件类型 | B |
| CQ11 | 某卷当前在哪个库位；最近一次吊起、落位的时间和天车 | B |
| CQ12 | 某切割计划的计划长度与实际长度之差 | A |
| CQ13 | 某订单行要求的牌号、标准版次、尺寸，已分配哪些卷 | B |
| CQ14 | 编码与属性不一致的实物件（例：板坯编码的炉次段不等于 `numberingHeat`） | — |

## 10 案例包内容

```
samples/steel-industry/
  ontology/
    core.ttl           制造骨架：实物件、设备、位置、工序执行、计划、订单、单据、事件
    steelmaking.ttl    炼钢、精炼、连铸
    rolling.ttl        热轧、冷轧（酸轧、连退、镀锌、重卷、包装）
    quality.ttl        取样、测量、分析、试验、判定、处置、证明书
    logistics.ttl      库区、天车、移动、发运
    codes.ttl          代码表（第 5.3 节）
    standards.ttl      标准书目：编号、年份、名称、状态、官方链接，不含正文
    shapes.ttl         SHACL：编码格式与一致性、必填、基数、单位、时区、计划与实绩分离
    steel-industry.ttl 汇总本体，owl:imports 以上模块
    mappings.sssom.tsv 外部词汇与 ISA-95 对象名的映射
  data/
    data.ttl           合成数据：主线 A、B 加一条普通路径
    invalid-data.ttl   每条 SHACL 规则至少一个违例
  cq/                  CQ1–CQ14 的 .rq 与期望结果
  check/               自检脚本：SHACL（data 合规、invalid-data 每条规则都报）、CQ 结果比对、编码一致性；在临时容器里运行，不进项目依赖
  build/               资料生成脚本与源文件（同 maintenance 的做法）
  docs/                生成的资料
  eval/expected.toml   期望识别结果
```

首批规模（不追求更多）：约 60 个类、110 个属性、14 张代码表。属性超出时先查有没有可合并的，不为凑数合并语义不同的属性。模块之间只经 `stl:` 术语引用，不互相复制定义。

### 10.1 评测资料

一家虚构的"示例钢铁公司"的规程与台账，全部原创，不含任何企业的真实信息和厂商文档的文字：

| 序号 | 资料 | 格式 | 主要覆盖 |
|---|---|---|---|
| 01 | 转炉炼钢作业规程 | PDF | 炉次、终点样、测温测氧 |
| 02 | 炉外精炼作业规程（LF、RH） | Word | 精炼处理、过程样、测点 |
| 03 | 板坯连铸与切割管理规程 | PDF | 浇次、换钢种、过渡坯、切割计划与实绩、板坯编号 |
| 04 | 热轧作业与热轧卷管理规程 | PDF | 热轧、热轧卷编号 |
| 05 | 冷轧作业规程（酸轧、连退、镀锌、重卷、包装） | Word | 分卷、合卷、新卷号、包装件 |
| 06 | 取样与检验规程 | PDF | 样品、熔炼与成品分析、力学试验、检验批 |
| 07 | 质量判定与不合格品处置规程 | Word | 判定、降级、改判、让步、封闭、返修、报废 |
| 08 | 库区管理与发运规程 | PDF | 库位编码、天车吊起与落位、移库指令、发运单 |
| 09 | 订单与生产计划管理规程 | Word | 订单、订单行、标准牌号、生产订单 |
| 10 | 生产与质量记录台账 | Excel | 炉次、浇次、板坯、钢卷、样品、结果、处置、发运的样表（含主线 A、B） |
| 11 | 编码与代码规则手册 | Excel | 第 5 节的编码表与代码表 |

角色：**开发集**，可以看模型输出、调规则；`pharma` 仍是唯一的留出集。案例包规则照 `samples/README.md`：答案在任何一次模型运行之前写好并单独提交。11 份资料一次评测约 35 分钟（按规格 004 的基线每份约 188 秒估算），只在需要时手动运行。

## 11 企业层与提升规则

### 11.1 企业层放什么

- 位置：`.verification/private-docs/<企业代号>/`，结构同案例包（`docs/`、`eval/expected.toml`），另加 `ontology/enterprise.ttl` 与 `mappings.sssom.tsv`。
- 命名空间：`urn:enterprise:<企业代号>:`，私有，不出 `.verification/`。
- 内容：企业的机组、真实编码规则（映射到第 5.2 节的同一组属性）、MES 产品的对象与接口字段到 `stl:` 的映射、企业特有的概念（用 `rdfs:subClassOf` 挂到通用层的类下）。
- 资料按保密要求处理：评测前确认资料可以发给所配置的模型服务。

### 11.2 提升进通用层的判据

企业层的概念同时满足以下四条，才提议提升：

1. **不止一家**：至少两个独立来源出现——两家企业，或一家企业加一份公开标准、教材、论文。
2. **去掉身份仍成立**：去掉厂商名、产品名、字段名、机组号、厂内编码后，定义仍然成立。
3. **能原创表述**：能用自己的话写出定义和边界，出处只需公开来源；写不出来不提升。
4. **不重复**：不是已有通用概念的同义词；若是细分，要有通用层没有的属性或约束。

不提升：接口字段和电文结构、企业编码规则本身、工艺窗口和参数、客户验收条件、MES 产品的状态机。

### 11.3 提升的流程

1. 在平台里对通用层本体提交一个变更集（新建类或属性），证据引用公开来源或原创资料，不引用私有资料原文。
2. 人审核通过后发布；新术语用 `stl:` IRI。
3. 企业层原来的术语保留，加 `owl:equivalentClass`（或 `rdfs:subClassOf`，若企业的更窄）指向新术语，企业数据不用迁移。
4. 通用层资料（第 10.1 节）若需体现新概念，改资料与答案按案例包规则 2 另开 PR。

## 12 分工与步骤

| 步骤 | 内容 | 谁做 |
|---|---|---|
| 1 | 本规格；确认第 13 节 | Claude 写，用户确认 |
| 2a | `ontology/`、`data/`、`cq/`：按第 4–9 节写本体、代码表、约束、书目、映射、合成数据、能力问题与期望结果，写 `check/` 自检脚本 | Codex 写（与 2b 同时，文件范围不重叠）；自检由 Claude 在临时容器里运行 |
| 2b | `build/`、`docs/`：按第 10.1 节写 11 份资料的源文件与生成脚本，生成资料 | Codex |
| 3 | 复审 2a、2b：概念、编码、单位、时间是否合规则；资料是否覆盖七类难点、是否有厂商文字 | Claude |
| 4 | 只读资料写 `eval/expected.toml`，在任何模型运行之前单独提交 | Claude |
| 5 | 跑评测基线，结果写进 PR 描述 | Claude |
| 6 | 企业层：选资料、写期望答案、写扩展本体与映射，提出首批提升候选 | Claude 设计与答案，Codex 写扩展与映射 |

## 13 已确认的取舍

2026-11-25 用户确认，全部按建议：

1. **IRI 基址** `https://w3id.org/ontology-platform/steel/`，前缀 `stl:`。向 w3id 登记重定向是对外提交，由用户决定是否、何时做；不登记不影响这些 IRI 作为标识使用。
2. **编码方案**按第 5.2 节（类型字母开头、定长、分段另有属性）。
3. **案例包角色**：开发集；`pharma` 仍是唯一的留出集。
4. **规模**：11 份资料、约 60 个类。
