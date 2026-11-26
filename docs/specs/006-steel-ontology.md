# 006 钢铁冶金通用本体：分层、模块与验收

- 级别：L0（本体内容与文档，不改平台代码）；最后一个 PR 加后端测试夹具，属 L1
- 关联：[005 钢铁全流程案例包](005-steel-industry-pack.md)（PR #67，评测用）；[002 M2 本体工作台](002-m2-ontology-workbench.md) 第 4 节（导入与导出）
- 状态：设计已确认（2026-11-26，用户授权主会话决定，第 13 节）

名词沿用 005：**实物件**指有自己编号、能被称重和搬运的一件物料；**代码**指代码表里的一项，**编码**指实物件、单据的编号。**普钢**指以普通质量和优质非合金钢、低合金钢为主、大批量生产的钢；**特钢**指优质特殊质量钢、合金钢和特冶产品（分类依据 GB/T 13304.1-2008、GB/T 13304.2-2008）。

## 1 目标与范围

做一套**可以直接使用、行业通用、普钢特钢都适用**的钢铁冶金本体，随仓库开源，放在 `ontologies/steel/`。用户把它导入平台即可作为建模起点，企业在上面细分自己的概念。

| 范围内 | 范围外 |
|---|---|
| 长流程：焦化、烧结、球团、高炉炼铁、铁水预处理、转炉 | 工艺窗口、配方与操作参数的取值 |
| 短流程：电炉 | 能源介质、设备点检维修 |
| 炉外精炼（LF、RH、VD、VOD、AOD、CAS-OB 等）、连铸、模铸 | 成本、财务、人事 |
| 板带、长材（棒线、型钢）、管材（无缝、焊管） | 任何企业、厂商的编码规则、接口字段和电文 |
| 特冶：真空感应（VIM）、电渣重熔（ESR、PESR）、真空自耗（VAR） | 标准正文、限值表、评级图 |
| 锻造、热处理、精整；质量检验；订单计划；物流发运 | |

与 #67 的分工：#67 的 `samples/steel-industry/` 是**评测案例包**（资料、合成数据、期望识别结果），本规格做的是**权威的通用本体**。#67 设计得好的规则直接沿用（005 第 4–8 节：命名、标签、代码、时间、单位、七类难点的建模），本规格只写新增和不同之处。

## 2 分层

```
          ┌─────────────┐  ┌───────────────────┐
扩展层     │ plain 普钢   │  │ special 特钢/特冶  │     只依赖通用层，两者互不引用
          └──────┬──────┘  └─────────┬─────────┘
          ┌──────┴───────────────────┴─────────┐
通用层     │ process 通用工艺（各工序，普特共用）   │
          ├────────────────────────────────────┤
          │ core 核心（跨工序骨架）               │
          └────────────────────────────────────┘
外部词汇   PROV-O · SOSA · QUDT · SKOS · DCTerms · SHACL（只引用 IRI）
```

**下沉原则**：

1. **普钢、特钢都会用的放通用层**。特钢厂同样走高炉—转炉—精炼—连铸—轧制，电炉、精炼、模铸、热处理普钢厂也有，所以全部工序都在 `process`，不放普钢层。
2. **只有一方用的才下沉**。普钢层只放普钢特有的产品族、牌号体系与组批交货口径；特钢层放特冶与重熔链、锻造、特钢产品族、特钢专门的检验评级和更严格的追溯要求。**下沉判定**：一个概念只有在普钢或特钢之一独有时才放进扩展层，判定理由写进该术语的 `rdfs:comment`（以"下沉理由："开头），扩展层模块的本体头 `rdfs:comment` 概述本模块的下沉范围；没有理由的一律留在通用层。
3. **差异不复制概念**，按以下顺序选表达方式：
   - 扩展层的概念是通用概念的细分，且有自己的属性或约束 → **子类**（例：`ElectroslagRemelting ⊑ Remelting ⊑ Operation`；`RemeltedIngot ⊑ Ingot`）；
   - 通用概念在扩展层多出要记的事实 → **扩展属性**，定义域仍是通用类（例：特钢层给 `Ingot` 加 `ingotPosition` 头中尾；给 `Forging` 加 `forgingRatio`）；
   - 只是多出取值 → **代码**，扩展层往通用层定义的代码表里加代码（例：`equipment-type` 由各工序模块各自加机组类型；特钢层往 `defect-type` 加锻件缺陷）；
   - 扩展层要求更严 → **SHACL 形状**，只在扩展层的形状文件里收紧，不改通用层的形状（例：特钢层要求每件锻材必须追溯到重熔锭和一次冶炼炉次）。
4. **依赖只向下**：扩展层可以引用通用层；通用层不引用扩展层任何 IRI；`plain` 与 `special` 互不引用。同时适用两层的概念，提升到通用层。
5. 企业层照 005 第 11 节，挂在本本体之下，不入库。

## 3 命名空间与 IRI

**沿用 `stl:` = `https://w3id.org/ontology-platform/steel/`**，全部层共用一个命名空间，层与模块只是归属（`rdfs:isDefinedBy`）。理由：概念在层间提升或下沉时 IRI 不变；用户只记一个前缀。

| 对象 | IRI | 例 |
|---|---|---|
| 术语（类、属性） | `stl:<本地名>` | `stl:Heat`、`stl:derivedFrom` |
| 代码表 / 代码 | `stl:code/<方案名>` / `stl:code/<方案名>/<代码值>` | `stl:code/refining-method/RH` |
| 标准书目 / 标准牌号 | 同 005 第 4.1 节 | `stl:std/gbt-10561-2023` |
| 来源"行业通用" | `stl:source/industry-practice` | 无标准出处时的 `dcterms:source` |
| 模块本体 | `stl:ontology/<层>/<模块>`，版本 IRI 加 `/<语义化版本>` | `stl:ontology/core/quality/0.1.0` |
| 层汇总 / 全量汇总 | `stl:ontology/<层>` / `stl:ontology/steel` | |
| 示例数据 | `urn:synthetic:steel:<类本地名小写>/<编号>` | `urn:synthetic:steel:heat/H22600123` |

本地名、标签、定义、代码值规则同 005 第 4.2、4.3、5.3 节。IRI 发布后不改、不复用；作废用 `owl:deprecated` 加 `dcterms:isReplacedBy`。

**与 #67 共存**：

1. 两者共用 `stl:` 命名空间，本本体是 #67 通用层的权威演进。#67 已有的本地名，本本体收录时**语义保持兼容**：可以改写定义、增加上位类和属性，不改术语种类（类、对象属性、数据属性），不收窄外延。要表达不同的意思就另起本地名。
2. 本体头不冲突：#67 用 `stl:module/<名>`，本本体用 `stl:ontology/<层>/<模块>`。代码与书目 IRI 相同时含义相同（本本体是超集）。
3. 自检脚本比对本本体与 main 上 `samples/steel-industry/ontology/` 的同名术语：种类不同、上位类矛盾或代码 IRI 归属不同的报错。
4. 另开 backlog 议题：案例包是否改为引用本本体。本规格的 PR 不改 `samples/steel-industry/`。

## 4 上位对齐

只引用下表词汇的 IRI，不 `owl:imports`、不复制文件（版本与许可已在 005 的调研中核实）。

| 词汇 | 对齐 |
|---|---|
| PROV-O（W3C 2013） | `Operation ⊑ prov:Activity`；`MaterialLot`、`MaterialPiece ⊑ prov:Entity`；`derivedFrom ⊑ prov:wasDerivedFrom`；`producedBy ⊑ prov:wasGeneratedBy`；`inputPiece`、`consumedLot ⊑ prov:used` |
| SOSA（W3C 2017） | `Sampling ⊑ sosa:Sampling`；`Sample ⊑ sosa:Sample`；`Observation ⊑ sosa:Observation`；`MeasuringInstrument ⊑ sosa:Sensor` |
| QUDT 3.5.4 | 数值属性上用 `stl:unit`、`stl:quantityKind` 两个注解属性注单位与量纲（同 005 第 7 节）；自检只认登记过的 QUDT IRI 清单 |
| SKOS（W3C 2009） | 代码表、同义词、定义；`skos:broader` 表示代码上下位 |
| DCTerms | 书目条目与术语来源 `dcterms:source` |
| SHACL（W3C 2017） | 约束只写在各模块的 `*-shapes.ttl`；SHACL-SPARQL 只用于核心约束无法表达的跨属性检查 |
| IEC 62264（ISA-95） | 不导入（无官方 OWL，正文收费）。核心层的类按其对象模型设计，用 SSSOM 映射登记 `skos:closeMatch` 到对象名：Material Class / Definition / Lot / Sublot、Equipment 层级（Enterprise、Site、Area、Work Center、Work Unit）、Process Segment、Operations Definition / Schedule / Performance、Personnel |
| GS1 EPCIS 2.0 | 只在映射表里对照转换、聚合、对象事件 |

BFO、IOF Core、EMMO、CROS 首版不对齐，确有需要再加映射文件。

## 5 模块与文件

```
ontologies/steel/
  README.md                 中文说明（含英文段落）：分层、怎么导入平台、怎么扩展
  steel.ttl                 全量汇总本体，owl:imports 四个层汇总
  core/      core.ttl  manufacturing.ttl  material.ttl  specification.ttl  quality.ttl
             logistics.ttl  codes.ttl  shapes.ttl  standards.ttl
  process/   process.ttl  ironmaking.ttl  steelmaking.ttl  casting.ttl  rolling.ttl
             tubemaking.ttl  heattreatment.ttl  finishing.ttl
             以及每个模块的 <模块>-codes.ttl、<模块>-shapes.ttl
  plain/     plain.ttl  products.ttl  quality.ttl  及 -codes、-shapes
  special/   special.ttl  remelting.ttl  forging.ttl  products.ttl  inspection.ttl  及 -codes、-shapes
  mappings/  external.sssom.tsv  IEC 62264 对象名、PROV-O、SOSA、EPCIS 的映射
  examples/  <层>.ttl 合成示例数据；<层>-invalid.ttl 每条形状至少一个违例
  cq/<层>/   cqNN.rq 与 cqNN.csv（期望结果）
  check/     check.py、check.ps1：在 op-tmp- 临时容器里自检
  dist/      steel.ttl：全部模块合并成的单个文件（自检生成并核对），供平台导入
```

- 一个模块文件只写本模块的类和属性；代码表单独放 `-codes.ttl`，形状单独放 `-shapes.ttl`，便于不同任务并行写不同文件。
- **跨模块共享的代码表**（`equipment-type`、`process-type`、`product-form`、`defect-type`、`chemical-element` 等）在核心层 `codes.ttl` 定义方案；各模块在自己的 `-codes.ttl` 里加代码（`skos:inScheme` 指向核心的方案）。
- **标准书目**全部放 `core/standards.ttl`，由一个任务一次写全（第 8 节）；后续 PR 需要新条目时在本 PR 里追加，同一时间只有一个写入者。
- **平台导入**：平台单次导入不超过 5 MB、5 万个三元组，且不加载 `owl:imports`（002 第 4.1 节）。所以另提供 `dist/steel.ttl` 单文件。它**只由 `check/check.py build` 生成，不手改**；自检核对它与各模块合并后的三元组完全一致（空白节点按同构比对），并检查三元组数不超过 50,000、文件不超过 5 MB。

## 6 各层骨架

下表是骨架，完整清单由各 PR 的任务在骨架内补齐（调研草稿见 `.verification/codex/steel-ontology-research/concepts.csv`，审定后才写入）。每个类都要有中英 `rdfs:label`、中英 `skos:definition`、`dcterms:source`（书目条目或 `stl:source/industry-practice`）、`rdfs:isDefinedBy`。

### 6.1 core 核心

| 模块 | 类（骨架） | 关键属性 |
|---|---|---|
| manufacturing | `ManufacturingRecord`、`Event`、`Operation`（工序执行）、`Plan`、`ProcessSegment`（工序段）、`ProcessRoute`（工艺路线）、`Equipment` 及层级 `Site`、`Area`、`WorkCenter`、`WorkUnit`、`MeasuringInstrument`、`SalesOrder`、`SalesOrderLine`、`ProductionOrder`、`ProductionSchedule`、`PersonnelRole` | `executesSegment`、`performedOn`、`partOfEquipment`、`equipmentType`、`processType`、`inputPiece`、`outputPiece`、`consumedLot`、`consumedQuantity`、`fulfills`、`forOrderLine`、`allocatedTo`、计划与实际时间（005 第 6 节） |
| material | `MaterialClass`（物料类别）、`MaterialSpecification`（物料规格，对应 ISA-95 Material Definition）、`MaterialLot`（批次：一批成分、状态一致的物料，如一炉钢水、一批焦炭）、`MaterialPiece`（实物件）、`Heat`（炉次，`⊑ MaterialLot`）、`SemiFinishedProduct`、`FinishedProduct`、`Package`、`SourceContribution`（来源份额；`HeatContribution ⊑ SourceContribution`） | `derivedFrom`、`producedBy`、`hasPart`/`partOf`、`productForm`、`steelGrade`、`sourceHeat`、尺寸与毛重/净重/理论重量 |
| specification | `StandardEdition`、`StandardGrade`、`SteelGrade`（内部钢种）、`CompositionLimit`、`PropertyRequirement`（性能要求：性能项、上下限、试验方法标准、试验条件）、`DimensionRequirement`、`DeliveryCondition` | `definedIn`、`satisfies`、`numericDesignation`（统一数字代号）、`steelClassByComposition`、`steelQualityClass`、`steelUseClass`（三根分类轴，代码表） |
| quality | `Sampling`、`Sample`、`TestPiece`、`Observation`、`MeasurementPoint`、`ChemicalAnalysis`、`ElementResult`、`MechanicalTest` 及 `TensileTest`、`ImpactTest`、`HardnessTest`、`BendTest`、`NondestructiveTest`、`MetallographicExamination`、`InspectionLot`、`QualityDecision`、`QualityDisposition`、`Defect`、`MillCertificate` | `sampleOf`、`sampleType`、`analysisType`、`testType`、`ndtMethod`、`methodStandard`、`element`、`massFraction`、`judgementResult`、`dispositionType`，以及 005 第 8.5、8.6 节的属性 |
| logistics | `Location`、`StorageArea`、`StorageLocation`、`Crane`、`MovementOrder`、`MovementEvent`、`Shipment`、`TransportUnit` | 同 005 第 8.7 节 |
| codes | 共享代码表：`equipment-type`、`process-type`、`product-form`、`material-category`、`chemical-element`、`sample-type`、`analysis-type`、`test-type`、`ndt-method`、`defect-type`、`judgement-result`、`disposition-type`、`inspection-document-type`、`delivery-condition`、`surface-condition`、`steel-class-composition`、`steel-class-quality`、`steel-class-use`、`measurement-item`、`measurement-method`、`contribution-evidence`、`share-basis`、`movement-event-type`、`personnel-role` | |

设备类型用 `stl:equipmentType` 与 `stl:code/equipment-type`（覆盖全流程）。#67 的 `stl:unitType`、`stl:code/unit-type` 本本体不收录，也不复用这两个本地名；#67 改为引用本本体时再一一对照。

### 6.2 process 通用工艺

| 模块 | 工序（`⊑ Operation`） | 物料与实物件 | 设备类型代码与专用代码表 |
|---|---|---|---|
| ironmaking | `Coking`、`Sintering`、`Pelletizing`、`BlastFurnaceOperation`、`BlastFurnaceTapping`（出铁，一个铁次）、`HotMetalPretreatment` | `Coal`/`CoalBlend`、`Coke`、`IronOre`、`Sinter`、`Pellet`、`Flux`、`HotMetal`（铁水批，按铁次）、`PigIron`、`BlastFurnaceSlag` | 焦炉、烧结机、球团设备、高炉、铁水罐、脱硫站；`pretreatment-method` |
| steelmaking | `Steelmaking` 及 `ConverterSteelmaking`、`ElectricArcFurnaceSteelmaking`；`Charging`、`Tapping`、`Refining`（方法用代码）、`AlloyAddition` | `Heat`、`Scrap`、`Ferroalloy`、`DirectReducedIron`、`LiquidSteel`、`SteelmakingSlag`、`ChargeComponent` | 转炉、电炉、LF、RH、VD、VOD、AOD、CAS-OB、钢包；`refining-method` |
| casting | `ContinuousCasting`、`Cutting`、`CuttingPlan`、`IngotCasting`（模铸） | `CastSequence`、`Slab`、`Bloom`、`Billet`、`RoundBillet`、`BeamBlank`、`Ingot` | 连铸机、中间包、锭模；`teeming-method`（上注、下注） |
| rolling | `Reheating`、`HotRolling`、`ColdRolling`、`Annealing`、`Coating`、`Recoiling`、`CoilSplitting`、`CoilJoining`、`Packing` | `Coil`（`HotRolledCoil`、`ColdRolledCoil`、`CoatedCoil`）、`Plate`、`Sheet`、`Bar`、`WireRod`、`Section` | 热连轧、中厚板轧机、冷轧、连退、镀锌、棒材、线材、型钢轧机；`coating-type` |
| tubemaking | `Piercing`、`TubeRolling`、`TubeWelding`、`SizingAndReducing` | `HollowShell`、`SeamlessTube`、`WeldedPipe` | 穿孔机、连轧管机、焊管机组；`weld-method` |
| heattreatment | `HeatTreatment`（工艺用代码） | `HeatTreatmentLoad`（一个装炉批，`⊑ MaterialLot`） | 热处理炉；`heat-treatment-process` |
| finishing | `Straightening`、`Shearing`、`SurfaceConditioning`（修磨、扒皮）、`InlineInspection`、`Marking` | | 精整线设备 |

### 6.3 plain 普钢

| 模块 | 内容 |
|---|---|
| products | 普钢产品族代码（碳素结构钢、低合金高强度结构钢、钢筋、冷轧低碳、热镀层板带、型钢、焊管）；普钢常用标准牌号条目（只写牌号与所属标准，不写成分限值）；`Rebar ⊑ Bar`、`CoatedSheet` 等需要独立属性的子类；交货口径（定尺、捆、卷） |
| quality | `LotFormationRule`（组批规则：按炉号、规格、交货状态组批的维度，不写数量限值）、普钢的组批检验与按批判定口径 |

### 6.4 special 特钢/特冶

| 模块 | 内容 |
|---|---|
| remelting | `VacuumInductionMelting ⊑ Steelmaking`；`Remelting ⊑ Operation` 及 `ElectroslagRemelting`、`ProtectiveAtmosphereElectroslagRemelting`、`VacuumArcRemelting`；`Electrode ⊑ MaterialPiece`、`RemeltedIngot ⊑ Ingot`；`remeltNumber`、`remeltSequence`（第几次重熔）；`melting-route` 代码（如 VIM+ESR、VIM+VAR、VIM+ESR+VAR）。**重熔链**：每次重熔产出新实物件，`derivedFrom` 指向电极，电极 `derivedFrom` 指向上一步的锭；一次冶炼炉次沿链可查，不在锭上重复存 |
| forging | `Forging`（方法代码：自由锻、快锻、径锻、精锻、模锻）、`Cogging`（开坯）、`ForgedProduct`；`forgingRatio`（记录值）与 `initialCrossSectionArea`、`finalCrossSectionArea`（可选，用于核算） |
| products | 特钢产品族代码（优质碳素结构钢、合金结构钢、齿轮钢、弹簧钢、轴承钢、工模具钢、不锈钢、耐热钢、高温合金）与常用标准牌号条目 |
| inspection | `InclusionRating`（按夹杂物类别和粗细系列评级）、`MacroExamination`（低倍）与低倍缺陷评级、`MicroExamination`（高倍）下的 `GrainSizeDetermination`、`DecarburizationMeasurement`、`BandedStructureRating`、`HardenabilityTest`（末端淬透性）、`GasContentAnalysis`；`CleanlinessAssessment`（纯净度）；`ndt-acceptance-class`；严格追溯：`ingotPosition`（头、中、尾）、每件材必须追溯到炉次与重熔锭（SHACL） |

## 7 代码表与 SHACL

**代码表**：规则同 005 第 5.3 节。另加：

- 每张方案有 `dcterms:source` 与 `rdfs:isDefinedBy`（定义它的模块）；扩展层加进通用方案的代码，`rdfs:isDefinedBy` 写扩展层模块。
- 分组用 `skos:broader`（例：`defect-type` 先分铸坯、板带、长材、管、锻件五组）。顶层代码用 `skos:topConceptOf`。
- 代码是标准里的类别名时（夹杂物 A、B、C、D、DS 类，检验文件 3.1 等）只写类别名和自己的定义，不写评级图、限值。

**SHACL 原则**：

1. 只写**行业通用**的约束：必填、基数、取值类、代码属于哪张方案、数据类型、非负、上下限不倒挂、时间带时区、计划属性不出现在执行对象上、测量项与存值属性一致。
2. **不写**企业编码格式、工艺窗口、标准限值。
3. 扩展层只收紧不放宽，写在自己的 `-shapes.ttl` 里（如特钢层对锻材要求 `derivedFrom` 链可达炉次）。
4. 违反结构的用 `sh:Violation`，建议性的用 `sh:Warning`。每个形状都有 `rdfs:comment` 中文说明，且在 `examples/<层>-invalid.ttl` 里至少有一个违例。

## 8 依据与来源

- 以公开标准为骨架，只引用编号和名称，不抄正文；定义一律自己写。
- 书目条目**只写编号、中英文名称、版次（发布年份）、现行状态、官方链接、代替关系**（字段同 #67 的 `standards.ttl`），不写正文、范围、限值或摘要。
- **每条书目在写入前核实**：由 Codex 联网核对官方目录（std.samr.gov.cn、hbba.sacinfo.org.cn、iso.org、astm.org、webstore.iec.ch 等）并附访问过的链接，Claude 抽查不少于 10%，抽查条数、比例与结果写进 PR 描述；抽查有错则整表返工。查不到的不入库，对应概念的来源写"行业通用"。
- 覆盖方向：术语与分类、牌号与统一数字代号、原燃料、各类产品、取样与化学分析、力学试验、金相与低倍、无损检测、热处理、锻造、质量证明与交货、制造运营（IEC 62264 及对应国标）、计量单位。

## 9 能力问题（CQ）

每层的 CQ 在该层的示例数据上必须有结果，并与 `cq/<层>/cqNN.csv` 一致。下面是首批，各 PR 可以增加，不能减少。

| 层 | 编号 | 问题 |
|---|---|---|
| core | C1 | 某实物件经过哪些工序执行（按时间排序），每步的设备、投入与产出 |
| | C2 | 某实物件追溯到哪些批次与炉次，各自的来源份额与证据等级 |
| | C3 | 某订单行要求的标准牌号、标准版次、物料规格，已分配哪些实物件 |
| | C4 | 某实物件的样品、试验与结果，判定结论和依据的规格 |
| | C5 | 某实物件经过哪些质量处置，处置前后的规格与订单行 |
| | C6 | 某质量证明书覆盖哪些实物件、依据哪些标准版次、检验文件类型 |
| | C7 | 某实物件当前在哪个库位，最近的移动事件 |
| | C8 | 某生产订单的计划时间与实际执行时间之差 |
| process | P1 | 某炉次的铁水来自哪几个铁次、哪座高炉，装入的废钢与铁合金批次 |
| | P2 | 某炉次的精炼路线（方法与先后、起止时间）及各测点温度 |
| | P3 | 某浇次按顺序包含哪些炉次；某钢锭的浇注方式与锭模 |
| | P4 | 某钢卷、钢板或棒材来自哪块坯，坯来自哪个炉次 |
| | P5 | 某高炉某日使用的焦炭、烧结矿、球团矿批次及其检验结果 |
| | P6 | 某无缝钢管来自哪支圆坯；某热处理装炉批包含哪些实物件、用什么工艺 |
| plain | N1 | 某普钢订单行的牌号所属产品族与标准；对应检验批按哪些维度组批 |
| | N2 | 某镀层钢卷的镀层类型与镀层质量结果是否满足规格要求 |
| special | S1 | 某锻材的完整熔炼链：材 → 锻件 → 重熔锭 → 电极 → 一次冶炼炉次，以及冶炼路线 |
| | S2 | 某锻件的锻造方法与锻造比 |
| | S3 | 某炉次的夹杂物评级、低倍与高倍结果，是否满足规格要求 |
| | S4 | 某批棒材的探伤方法、验收等级与结果；不合格件的锭位置（头、中、尾） |
| | S5 | 缺少到炉次或重熔锭追溯链的特钢实物件（应为空） |

示例数据全部合成，不含任何企业信息；限值是示例值，注明不是标准值。

## 10 自检与验收

`check/check.ps1` 把文件打包送进 `op-tmp-` 临时容器（`python:3.13-slim-trixie`，锁定 `rdflib==7.6.0`、`pyshacl==0.40.2`，做法同 #67），运行 `check.py`，退出码 0 为通过。检查项：

1. 所有 `.ttl` 能用 rdflib 解析；每个模块有本体头、版本 IRI、许可证。
2. **标签与定义齐全**：每个 `stl:` 类、属性、代码方案、代码都有中英 `rdfs:label`（与 `skos:prefLabel` 相同）、中英 `skos:definition`、`dcterms:source`、`rdfs:isDefinedBy`；同一术语只在一个模块定义。
3. **无悬空引用**：用到的每个 `stl:` IRI 都有定义；外部 IRI 只来自第 4 节的词汇，QUDT 单位只来自登记清单；`dcterms:source` 都指向书目条目或"行业通用"。
4. **分层依赖**：通用层不引用扩展层 IRI，`plain` 与 `special` 互不引用；扩展层没有改通用层术语的定义（只能加子类、属性、代码、形状）。
5. 代码规则：代码值格式、IRI 等于方案加代码值、方案内唯一、`skos:inScheme` 正确。
6. SHACL：`examples/<层>.ttl` 合规；`examples/<层>-invalid.ttl` 中每个形状都报出预期的违例，没有意外违例。
7. CQ：每个查询有结果，与期望 CSV 一致（S5 期望为空）。
8. `dist/steel.ttl` 与重新生成的结果逐字节一致，且与各模块合并后的三元组完全一致；三元组数不超过 50,000、文件不超过 5 MB。
9. 与 `samples/steel-industry/ontology/` 的同名术语比对（第 3 节），目录缺失时报错。

**每个 PR 的验收**：自检通过；`reviewer` 复审没有必须修的项；`./dev.ps1 ci -Report` 通过；Claude 抽查定义与来源不少于 10%（看定义是否原创、来源编号是否在核实过的书目里）。

**整体验收**（最后一个 PR）：`dist/steel.ttl` 导入平台再导出，原文件每个三元组都在导出里、再导入差异为空（002 第 4 节的往返规则）；在开发栈实际导入、发布后 `./dev.ps1 owl-check` 通过。

## 11 PR 拆分

| PR | 内容 | 依赖 | 估计规模 |
|---|---|---|---|
| 1 | 本规格 | — | 约 300 行 |
| 2 | 核心层 5 个模块、共享代码表、全部标准书目、映射表、自检脚本、核心示例与 C1–C8 | 1 | 约 3000 行，其中书目约 1200 行为逐条核实后的机械条目 |
| 3 | 通用工艺·炼铁炼钢铸造：ironmaking、steelmaking、casting 及示例、P1–P3、P5 | 2 | 约 2000 行 |
| 4 | 通用工艺·成材：rolling、tubemaking、heattreatment、finishing 及示例、P4、P6 | 2 | 约 2000 行 |
| 5 | 普钢扩展层及 N1–N2 | 3、4 | 约 800 行 |
| 6 | 特钢扩展层及 S1–S5 | 3、4 | 约 2200 行 |
| 7 | `dist/steel.ttl`、README、平台导入往返（后端测试夹具，L1）、开发栈导入发布后 owl-check | 5、6 | 约 500 行 |

PR 1 先单独合并，再派 PR 2。3 和 4、5 和 6 文件互不重叠，可以同时派给两个 Codex。超过约 2500 行的 PR 按模块再拆；每个 PR 的描述写明行数，超过 1500 行的写明原因。本体文件是声明式内容，靠自检保证结构正确，复审集中在概念边界、定义与来源。

## 12 分工

| 工作 | 谁做 | 理由 |
|---|---|---|
| 规格、分层与概念边界、每 PR 的骨架审定、抽查、复审意见处理、合并 | Claude | 设计权衡 |
| 标准清单核实、概念清单草稿 | Codex（high） | 联网核对、量大 |
| 各模块 Turtle、代码表、形状、示例数据、CQ 与期望结果 | Codex（high），每个 PR 一到两个任务，文件互不重叠 | 规则清楚、量大 |
| 自检脚本 | Codex（high），PR 2 | 照 #67 的思路改写 |
| 自检运行 | Codex 在任务内经提权运行 `check.ps1`；结果对不上时 Claude 重跑 | 省 Claude 额度 |
| 复审 | `reviewer` 子代理 + Claude 抽查 | |

## 13 已确认的取舍

2026-11-26 用户授权主会话决定，主会话确认全部按以下建议执行：

1. **分层**：通用层分"核心"与"通用工艺"两部分，全部工序放通用工艺（特钢也走这些工序）；普钢层只放普钢特有的产品族、牌号和组批口径，因此较薄；特钢层放特冶、锻造、特钢产品与检验评级、严格追溯。
2. **命名空间**沿用 `stl:`，与 #67 按第 3 节共存：同名术语语义兼容，本体头 IRI 分开，自检比对冲突。
3. **规模**：约 300 个类、250 个属性、50 张代码表（约 800 个代码）、150 条书目、全量约 2.5–3 万个三元组。
4. **PR 拆分**按第 11 节 7 个 PR；PR 2、3、4、6 超过约定的 1500 行，因为大部分是声明式条目。
