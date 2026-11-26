# 钢铁冶金通用本体

这套行业通用本体以公开标准编号为骨架，适用于普钢和特钢，对齐 IEC 62264、PROV-O、SOSA/SSN、QUDT、SKOS、DCTerms 和 SHACL，采用 Apache-2.0 许可证。

## 分层

核心层 → 通用工艺层 → 普钢扩展层、特钢扩展层。

| 层 | 目录 | 模块 | 内容 |
|---|---|---|---|
| 核心 | `core/` | `manufacturing`、`material`、`specification`、`quality`、`logistics`、`codes`、`shapes`、`standards` | 描述跨工序的订单、设备、物料、规格、质量与物流，并提供共享代码、约束和书目。 |
| 通用工艺 | `process/` | `ironmaking`、`steelmaking`、`casting`、`rolling`、`tubemaking`、`heattreatment`、`finishing` | 描述从炼铁到成材、热处理和精整的工序、产出与逐件来源。 |
| 普钢扩展 | `plain/` | `products`、`quality` | 描述普钢订货产品族、版次牌号、钢筋特征和按批交验。 |
| 特钢扩展 | `special/` | `remelting`、`forging`、`products`、`inspection` | 描述重熔链、锻造、特钢产品族、专门检验与逐件追溯。 |

两种钢都用的概念放在通用层。两个扩展层都可引用核心和通用工艺，彼此独立。
只有普钢独有或特钢独有的概念才下沉。
扩展层的类、属性和新建的代码方案都在中文 `rdfs:comment` 中以“下沉理由：”开头说明依据。
给共享方案增加的代码沿用所在扩展模块的理由。

例如，定尺交货捆 `stl:Bundle` 在 `process/finishing.ttl` 中定义，是核心包装件 `stl:Package` 的子类。
钢筋捆和特钢棒材捆都在捆上记录单支交货长度和计重方式，也可记录实交支数。

## 目录结构

以下路径均相对于本目录。

| 目录 | 从哪里读起 |
|---|---|
| `core/` | `core.ttl` 汇总核心模块。共享代码方案见 `codes.ttl`，基础书目见 `standards.ttl`。 |
| `process/` | `process.ttl` 汇总各工序模块。按业务工序查找类、属性和代码。 |
| `plain/` | `plain.ttl` 汇总普钢的产品与质量模块。 |
| `special/` | `special.ttl` 汇总特钢模块。`products-standards.ttl` 补充产品模块引用的版次。 |
| `examples/` | `<层>.ttl` 是合成正例，`<层>-invalid.ttl` 是带预期违例的反例。 |
| `cq/` | 每层的能力问题由一对文件组成，`cqNN.rq` 是查询，`cqNN.csv` 是期望结果。 |
| `mappings/` | 两份 SSSOM 表分别记录外部模型对齐和钢铁案例包中术语的去向。 |
| `check/` | PowerShell 入口、校验脚本与允许引用的 QUDT 单位和量纲清单。 |
| `dist/` | `steel.ttl` 是供平台导入的完整本体。 |

工艺和扩展模块按内容分文件。

- `<模块>.ttl` 定义类和属性。
- `<模块>-codes.ttl` 定义代码方案和代码，也可向共享方案添加代码。
- `<模块>-shapes.ttl` 定义 SHACL 约束。
- `<模块>-standards.ttl` 在需要补充书目时收录标准版次。

## IRI 规则

`stl:` 对应 `https://w3id.org/ontology-platform/steel/`。
四层共用这一个命名空间。在下表中，相对路径都接在该基址之后。
术语归属由 `rdfs:isDefinedBy` 指明，换模块时保留术语 IRI。

| 对象 | 形式 | 示例 |
|---|---|---|
| 类、属性 | `stl:<本地名>` | `stl:Bundle`、`stl:bundleCutLength` |
| 模块本体 | `ontology/<层>/<模块>` | `ontology/process/finishing` |
| 模块版本 | `ontology/<层>/<模块>/<语义化版本>` | `ontology/process/finishing/0.1.0` |
| 层汇总、全量本体 | `ontology/<层>`、`ontology/steel` | `ontology/process`、`ontology/steel` |
| 代码方案 | `code/<方案>` | `code/bundle-mass-basis` |
| 代码 | `code/<方案>/<代码>` | `code/bundle-mass-basis/THEORY` |
| 标准书目 | `std/<机构>-<编号>-<年份>` | `std/gbt-228-1-2021` |
| 标准牌号 | `std/<版次>/grade/<牌号>` | `std/gbt-2518-2019/grade/DX51D-Z` |

标准编号在路径中规范化。例如，GB/T 228.1-2021 写作 `gbt-228-1-2021`。
牌号按版次区分，同名牌号可以有不同 IRI。牌号原写法保存在 `skos:notation`，如 `DX51D+Z`。
合成示例使用独立的绝对 IRI，形式为 `urn:synthetic:steel:<类本地名小写>/<编号>`，如 `urn:synthetic:steel:bundle/P73`。

## 导入平台

全部模块合并在一个导入文件中，文件只有一个本体头。[下载 dist/steel.ttl](dist/steel.ttl)
平台可直接读取完整内容。文件只由 `check.ps1 -Build` 生成，请勿手改。

1. 在平台的本体页导入 `dist/steel.ttl`。
2. 在审核页接受导入变更集并合并。
3. 发布合并后的本体版本。

导入会提示“多个上位类”和“表单不支持的约束”。相应的上位类声明和约束按公理原样保留。
导入后再导出，原文件中的三元组都会保留。

## 自检

在仓库根目录用 PowerShell 7 检查当前模块、示例和分发文件。

```powershell
pwsh -NoProfile -File ontologies/steel/check/check.ps1
```

需要根据模块重新生成 `dist/steel.ttl` 时，加上 `-Build`。

```powershell
pwsh -NoProfile -File ontologies/steel/check/check.ps1 -Build
```

自检在临时容器中运行，逐项核对以下内容。

- Turtle 语法、本体头、版本和许可证。
- 类、属性与代码的标签、定义、来源及模块归属。
- 扩展层的下沉理由、各层的引用方向和代码方案归属。
- 每层的 SHACL 正例与反例，包括预期违例的节点、形状、组件和次数。
- 能力问题的查询结果与期望 CSV，包括特钢追溯查询预期的空结果。
- 分发图与模块并集的一致性。去掉本体头后两图须同构，单文件须在 5 MB、50,000 个三元组以内。

## 怎么扩展

**选择模块。** 跨工序共享的概念放在 `core/`，两类钢共用的工序和实物放在 `process/`。
只有一类钢使用的概念放在对应扩展层，写明“下沉理由：”。
按上面的文件约定命名，在该层的汇总文件中为每个新增的模块文件添加 `owl:imports`。

**定义术语。** 为类、属性和代码方案给出中英标签和定义，并让 `skos:prefLabel` 与 `rdfs:label` 对应。
用 `rdfs:isDefinedBy` 指向所属模块，用 `dcterms:source` 指向已有标准版次。
没有贴切书目时，来源写作 `<source/industry-practice>`。需要新增书目时，先核实版次，再写入模块的书目文件。

**增加取值。** 新取值作为 `skos:Concept` 加入代码方案，无需新建类。
`skos:inScheme` 指向方案，`skos:notation` 用该方案的字面量类型记录主代码。
例如，交货捆采用实际计重时，`stl:bundleMassBasis` 指向 `<code/bundle-mass-basis/ACTUAL>`。

**约束与反例。** 在形状文件中给约束一个稳定 IRI，并用中文说明它检查什么。
将合规数据写入本层正例文件，将每个形状的违例写入本层反例文件。
每条 `# EXPECT` 依次写焦点节点的完整 IRI、报告中来源形状的完整 IRI 和约束组件本地名。
例如，下面的捆给出了计重方式，缺少必填的单支定尺。

```turtle
# EXPECT <urn:synthetic:steel:bundle/B93> <https://w3id.org/ontology-platform/steel/BundleLengthShape> MinCountConstraintComponent
<urn:synthetic:steel:bundle/B93> a stl:Bundle ;
    stl:bundleMassBasis <code/bundle-mass-basis/THEORY> .
```

**能力问题。** 在 `cq/<层>/` 增加同名的 `.rq` 和 `.csv`。
查询使用本层正例，并固定结果顺序。CSV 首行按 `SELECT` 顺序写变量名，其余各行写期望值。
改完模块后，先运行带 `-Build` 的命令生成分发文件，再运行不带参数的自检。

## 引用标准的原则

只引用标准编号和名称。书目中的编号均已核实，引用的版次以书目条目为准。
可沿条目中的官方目录链接核对版次及替代关系。
术语定义用自己的话写。标准正文、限值表和评级图谱均不收录。

## English

This Apache-2.0 ontology covers both commodity and specialty steel manufacturing.
Public standard identifiers anchor its vocabulary. The manufacturing model maps to IEC 62264.
It uses PROV-O for provenance, SOSA terms from SOSA/SSN for observations and sampling,
QUDT for units and quantity kinds, SKOS for codes, DCTerms for sources and SHACL for constraints.

Start with `core/` for orders, materials, specifications, quality and logistics.
The `process/` modules cover shared operations from ironmaking through finishing.
The independent `plain/` and `special/` extensions cover concepts specific to one sector.
Each extension explains why its classes, properties and new code schemes belong there.
A fixed-length delivery bundle belongs to finishing. A bundle of reinforcing bars and a bundle
of specialty bars can therefore use the same cut length, piece count and mass basis properties.

All terms share the `stl:` namespace. Moving a term between modules preserves its IRI.
Module IRIs identify the layer and module, and version IRIs append a semantic version.
A code IRI extends its scheme IRI. Bibliographic IRIs identify a particular edition,
and grade IRIs include that edition. Synthetic records use the separate `urn:synthetic:steel:` namespace.

Import `dist/steel.ttl` on the platform’s ontology page. Accept and merge the import change set
on the review page, then publish the merged version. The importer flags multiple superclasses
and constraints beyond the form editor’s capabilities. It preserves these as axioms,
so a subsequent export retains the original triples.

To extend the vocabulary, choose the layer that owns the concept. Keep terms, codes,
shapes and additional bibliography in their respective files and register each file in the layer aggregate.
Use a concept in a code scheme for a new value. Link each term to its defining module
and cite a verified edition or industry practice. The bibliography identifies standards by number
and title. Standard text, limit tables and rating charts remain outside the ontology.

Put valid records and intended violations in the layer’s files under `examples/`.
For each violation, name its focus node, source shape and constraint component in an `# EXPECT` line.
Pair each competency query in `cq/` with its expected CSV. Consult `mappings/` for vocabulary alignments.
From the repository root, run the PowerShell command above with `-Build` to regenerate the distribution,
then run it without arguments. The temporary container checks syntax, metadata, dependencies,
shape coverage, query results and equivalence between the distribution and the module graphs.
