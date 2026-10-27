# G3 本体建模与语义治理计划

已审计划归档，2026-10-27。总方案PROPOSED；仅M1由[实施授权V1](../evidence/G3-M1-001/authorization-v1.md)正式批准，M2–M5仍未授权。本档保留原计划决策与未验证边界，当前执行状态见[G3-M1任务](../tasks/G3-M1-001.md)，精确实施接口见[G3-M1合同](../contracts/g3-m1-contracts.md)。

## 基线与目标

开工重新fetch：HEAD=origin/main=d6aab6b47e63c9d5deadfa480f6659c62c5ed138。G2历史6154ebb..46c7a6d仅历史范围。PRE-G3最终CI40375316071两job同Head成功，Review ZIP V2已落地，不重做构包器。原6个DS_Store保留；原6Worktree、15本地/15远端refs、24保护卷、11镜像保持。main未保护，规则变更未授权。

面向建模者、术语专家、审核发布者，建立源码/语义无损、能力支持透明、版本审批可追溯闭环。继续模块化单体、Next/shadcn/Base UI/Tailwind、自研Design System、RDF/OWL/Turtle/SHACL/SKOS；禁TMDL/GraphRAG/AutoMapper/万能Repository。四源SourceBundle权威，PG修订/审计、Jena正式图、RustFS不可变制品。Domain不依赖EF/HTTP/Jena/LLM。

## 五个纵向里程碑与DAG

BASE/合同冻结→M1→M2→M3→M4→M5。每里程碑均有真实Web/API/权限/PG/Jena/RustFS、发布查询回滚、独立Review、同Head CI、main增量集成、V2唯一包和资源真实收尾。

|里程碑|可运行闭环及接受条件|状态|
|---|---|---|
|M1 源码及语义保真|四源导入/修订/原文导出重入、20语料/profile/assessment、有界同构、有效assessment新发布、V1/V2及旧Run/SSE读回滚、授权与故障负例|AUTHORIZED，运行NOT_RUN|
|M2 三栏基础建模|基础建模和有限命名公理编辑、SHACL对象定位、源码后备、逐步整理TSX、主题键盘窄屏|PROPOSED/NOT_RUN|
|M3 术语/单位量纲|SKOS中英标签别名/对齐、单位和quantitykind适配校验、发布读取；不通用换算|PROPOSED/NOT_RUN|
|M4 身份时间/Diff/影响|同号歧义、历史有效期、事件区间、任两固定版本四源Diff、已知引用/未知影响、审批绑定impactHash、版本回滚|PROPOSED/NOT_RUN|
|M5 高阶保留/总验收|复杂OWL源码及只读树、明确限制/诊断、无损导出重入、支持对照资产真实发布查询；复杂发布继续阻断|PROPOSED/NOT_RUN|

## 二十项能力矩阵

V=可视化，S=专家源码，R=结构只读保留，B=阻断操作或发布，L=后续；能力、发布和推理分别标识。以下为G3目标，不代表M1全量图形编辑。

|项|标准表达与目标|负例/边界|
|---|---|---|
|1 IRI/namespace|IRI/prefix/BASE V/S|四文档独立、固定BASE，不字符串替换literal|
|2 Class|owl:Class V/S|删除引用需影响说明|
|3 子类|rdfs:subClassOf V/S|环不一概当OWL不一致|
|4 对象属性|owl:ObjectProperty V/S|类型不符/越权拒绝|
|5 数据属性|owl:DatatypeProperty V/S|typed lexical精确保留，部署改写阻断|
|6 domain/range|命名IRI V/S，复杂S/R/B|非必填，多domain非任选|
|7 annotation/lang|label/comment V/S，简单自定义S|语言/datatype互斥，Unicode/公理注释不丢|
|8 individual|命名个体及简单事实V/S|Synthetic，不自动合并/授权|
|9 equivalentClass|命名类对V/S；复杂S/R/B|公理声明不等于执行推理|
|10 disjointWith|命名类对V/S|不声称完整一致性证明|
|11 inverseOf|命名属性对V/S|双向遍历与推理分开|
|12 属性特征|S/R/B，推理L|Functional非唯一键|
|13 some/all|S/R/B|all不要求至少存在|
|14 hasValue|S/R/B|保留IRI/类型/语言，非默认值|
|15 cardinality|S/R/B|与SHACL min/maxCount分开|
|16 交并补|S/R/B|嵌套/列表/共享bnode不丢|
|17 propertyChain|S/R/B，执行L|保留顺序，不冒称路径推理|
|18 imports|S/R/B，加载L|不联网、不执行闭包；未锁/循环/越权诊断|
|19 身份公理|sameAs/differentFrom/hasKey S/R/B|同号不同厂不自动sameAs|
|20 事件时间|OWL-Time2017命名模板V/S|有效区间[from,to)，显式时区、未知终点|

SKOS：ConceptScheme/Concept、notation/definition、中英pref/alt/hiddenLabel、broader/narrower/related及受控mapping；每语言最多一prefLabel且标签类别冲突拒绝。单位登记IRI/quantitykind/量纲/依据版本，不执行G5计算。OWL开放世界/SHACL数据约束/身份治理/时间/业务规则分别报告。语法解析不等于完整OWL支持，不把sh:conforms当OWL一致性。

## 语义及兼容决定

无修改和no-op原始UTF8/BOM/换行/注释/hash不变；实际结构修改仅明确变更，全部其他RDF保留，旧revision原文保留，新排版Diff明示。未知/复杂/bnode图默认锁结构，原文仍可保存导出。

复用RIOT，不新增parser/reasoner/Java服务。精确比较以集合、分区细化、bnode双射、完整triple最终核验；128 bnodes/100000搜索/5s，保留原triple/字节上限。取消/预算返回INDETERMINATE，不能零差异或PASS；跨源blank scope隔离。

SemanticAssessment分PARSE/SUPPORT/SHACL/GOVERNANCE/OWL_REASONING，绑定revision/四hash/profile/version/executor/time及自身hash。新PUBLISH需有效assessment，M4起需impact；源/profile/修订改变旧批准失效。ManifestV2固定profile/assessment，兼容V1不补伪字段、不重写hash。旧正式版本按原语义重验、当前权限和异人审批CAS回滚，Run/SSE原snapshot不变。V2写入前实际验证兼容回退binary，之后不直接退G2宿主。

VersionRef比较同asset/scope任两draft revision或release，四源分别源码/图状态。Impact覆盖本体/shapes/vocab/imports声明、已登记capability/release/run引用；未知不是无影响，G4/G5不存在明确NOT_IMPLEMENTED。不实现imports部署。

UI左资产树/中图与源码/右属性诊断，继续textarea；准确sourceId/hash/focus/path/shape定位，未知行列为空。Monaco BLOCKED/PAUSED_BY_USER，真实LLM未验收，不收费调用。

## 协作/历史补丁/工程整改

Master唯一main集成及Contracts/迁移/锁/CI/Host/Tokens写者；独立托管Worktree和codex任务枝，最多Master+2写者；评审释放一槽，由非作者独立Review。合同先冻结再SEM/FE并行，PUB/QRY按独立路径卡串接。每任务记完整Base/owned_paths/只读依赖/验收/负例/停止，及时commit/push，DRAFT不等可合并。

G2四个cherry+已覆盖：cee8a7b单Guard patch与main233dd61同；b8dc13c的29/30路径patch与6920168同，剩余EOF最终blob同，7产品文件当前同；SEC42c95db三合同文件与main同blob，原报告记Master同步；SEM098418c接口patch与0e970f9同。建议均采用main替代，不重复cherry-pick；另外9非祖先refs全部cherry+=0。此判断不是删除授权。

G2实查92commit、08:04:05–15:04:06提交跨度（不是活跃工时），587证据/20530556bytes。必要跨存储/授权复杂度保留；名称/绑定前授权/If-Match/生成漂移前置测试；冷JIT夹具预热不放宽生产预算；OTel可见性有界等待；checks/ci Schema持续正反检查；每里程碑main真实集成。超长TSX随改动整理，手写变更单行默认<=200，不加formatter依赖。计时分实现/等待/环境/集成/CI/封包，缺数据UNKNOWN，不编造收益。

## 测试/交付/资源/风险

doctor -CheckDocker、verify -SelfTest、受锁restore/build/format/test、verify-web、generate-types --check、真实PG/Jena/RustFS/HTTP/OIDC/Web/发布/查询/回滚、旧Run/SSE、故障及性能；新G3统一入口确实实现再声明PASS。MacARM开发/LinuxCI，Windows/Intel原生NOT_RUN，不改系统PATH/SDK/Docker。

先完成源码/测试/Review/文档提交固定Head→实际同Head双job CI→main集成及同HeadCI→现有V2构包/独立重开；CI/ZIP回执后置，不自引用提交。持续证据Schema与输出隔离，不覆盖G2历史。源码/当前必要证据各一次，原始大产物可取得Artifact+hash索引；不能只有不可取得hash。

生命周期复用inspect/cleanup，默认DryRun、精确fresh白名单、before-command-exit-after；仅本任务可再生资源，实际安全候选0删除FAIL。保护原G2 24卷/6树/历史refs/私有runtime。G3资源按g3-m1-runId隔离。共享cache不prune；history固定后端/代际/准确ID强absence，不凭list缺席。物理SSD回收NOT_VERIFIED。

风险继续：Monaco/真实LLM/五真实源/高阶推理/生产HA/证书轮换/SLO-RPO-RTO/WindowsIntel/镜像完整供应链/隐私语义/共享cache归属/main保护；有限扫描非认证。G2历史失败和外部网络漂移原样保留。

QUDT3.5.3最小词汇资产为M3候选，CC BY4且UCUM另许可；需精确版本/commit/hash/抽取/署名审批，M1不引入。无新runtime直接依赖。主线保护沿ADR007建议PR、同Head两check、禁force/delete，单人独立Agent不冒充另GitHub用户；本轮不改规则。

M1完成后仅交G3_M1_READY_FOR_REVIEW及唯一ZIP并停止，M2–M5不自动启动。
