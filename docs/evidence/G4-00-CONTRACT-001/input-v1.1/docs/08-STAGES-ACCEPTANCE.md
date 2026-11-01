# 08 · G4 开发里程碑、验收矩阵、实测门槛与资源治理

> 本文同时定义 **G4-00 合同的出关条件** 与 **未来 G4-M1~M5 产品实施的验收依据**。二者必须分开报告：本次文档设计完成不代表任何 G4 产品测试已通过。所有真实运行值/耗时/数量/TLS/许可/跨平台都标 `NOT_RUN`，直到获得准确实验授权。

## 1. 关口与所有权矩阵
| Gate | 最小闭环 | 受权 Owner | 测试/交付 | 进入下游条件 |
|---|---|---|---|---|
| G4-00-CONTRACT-001 | PRD + 五源适配能力 + UI + 公共 DTO/API + 安全 + 映射发布 + Query + 反例 + ADR | ChatGPT设计；后续Codex Master仅写合同文档（需另授权） | 独立Reviewer；合同 JSON/示例/状态/权限一致性；V3（只有Codex真执行时） | 产品需求、错误码/分层/数据边界裁决冻结 |
| G4-M1-CONNECTION-001 | PG真实配置→测试→保存/编辑/禁用→审计；五类型UI动态Schema | Master单写共享Host/Contracts+Adapter Worker+UI Worker（独立树） | 真实PG/docker/OIDC/REST/浏览器、拒绝/负例 | 配置端到端及权限可复用 |
| G4-M2-CONNECTORS-001 | Oracle、Doris、TDengine、WebAPI 真实只读连接+Schema | 各适配器非重叠所有权，Master统合契约 | 每源真实隔离环境、功能和安全对照、版本/许可清单 | 五源各源可查、权限正确；欠缺源真实验收→PARTIAL |
| G4-M3-MAPPING-001 | schema快照→候选/审核→验证→MapRelease→激活/回滚 | Domain/SEM + UI独立写者 | 版本CAS、身份/时间/单位、回滚故障注入 | MappingRelease不污染G3，可供query固定 |
| G4-M4-QUERY-001 | 计划→五源→身份合并→六态/证据→MCP受控工具 | SemanticQuery/Adapter + Web写者 | 分布式失败/大结果/ACL/取消/旧Run/兼容 | 可验证真实业务数据、正确返回/拒绝 |
| G4-M5-INTEGRATION-001 | 五源“转炉/精炼→连铸→轧制”全纵向及资源 | 集成Master、独立Reviewer | 5源矩阵、浏览器E2E、Linux双架构、故障恢复、安全/并发 | 才准说G4完整通过，推进G5 |

路径：**合同先冻结、最小 PG 真实切片、其余源按稳定契约补齐、Mapping与查询分层集成、G4产品完整验收。** G6实验分支独立推进，不抢共有Contracts/Host/锁/迁移的 Single Writer。

## 2. 标准验收状态和分层要求
`PASS`：实际命令/输入/结果/退出码/环境/版本/审查可核对，且无阻断问题；`FAIL`：实际结果不符合；`PARTIAL`：部分必需能力可用但未完成；`NOT_RUN`：有能力但本阶段未执行；`NOT_VERIFIED`：证据不足；`BLOCKED`：可定位阻断且有下一项精确需求。零测试不是 PASS。设计可 `DESIGN_REVIEW_PASS_RUNTIME_NOT_RUN`，不能标产品 `PASS`。

每条真实产品路径执行：单元/契约负例→模块真实连接→HTTP/OIDC→前端交互→发布/查询/回滚→故障/资源；昂贵的完整验证对稳定的产品输入只做必要一次。源/二进制/证书没有授权时测例保持NOT_RUN，不能被合成Fixture替代。

## 3. G4-00 设计合同验收（必须在交付包形成时检查）
| ID | 要求 | 验收方式 |
|---|---|---|
| C-01 | 读取冻结G3本体/Scope/Identity/Manifest/Query合同，不暗改 | 来源路径与不变量检查 |
| C-02 | 五种 Source 类型有差异字段、校验、试连状态 | 02/03/04各自五项对照 |
| C-03 | SourceScope与ActorScope不由前端扩大 | 数据/安全边界正反推演 |
| C-04 | 只读由源权限+计划+执行三重防线 | SQL/HTTP攻击向量清单 |
| C-05 | Schema本体Mapping/Release版本Hash关系清楚 | DTO与状态机一致 |
| C-06 | mapping发布异人审批/CAS/恢复 | 05/06签署与失败分支 |
| C-07 | 业务六态与source read evidence字段一致 | 03/05/06枚举对照 |
| C-08 | 无模型的完整人工路径可用 | 07 OFF模式与02 J3 |
| C-09 | 无未经批准的数据外联/真实模型调用 | 权限与流程审阅 |
| C-10 | Compose双架构、资源归属与禁止prune | 06/10规范检查 |
| C-11 | G4按M1~M5和G5/G7/G8依赖有正确主线 | 01/08交叉核对 |
| C-12 | ZIP只有一个权威任务合同，未提前批准Codex | README/09/10/Manifest/SHA核对 |
| C-13 | API被标为PROPOSED且当前API能力区分 | 05所有候选路径标注 |
| C-14 | G4不会继承G6的Docling阻断 | 01路线依赖校验 |
| C-15 | 公共DTO+OpenAPI+TS生成路径只一条 | G2/G3现有合同引用、无自创本体元模型 |
| C-16 | 连接/映射/查询任一页没有假交互 | UX动作状态与API/失败闭环逐项检查 |

### G4-00 V1.1 新增四项合同一致性门禁
| ID | 要求 | 验收方式 |
|---|---|---|
| C-17 | G4QueryResultV1 完整11字段、AMBIGUOUS候选与证据、G2不变 | 正反 JSON Schema + G2严格 DTO 对照 + 两候选可回源交叉引用设计检查 |
| C-18 | 创建请求唯一结构 config/secretRef/command，初始 revision=0 | Schema样例+旧扁平格式/缺命令/null修订负例 |
| C-19 | 唯一凭据引用规则，TD profile 无二次Ref，匿名API null | 五源正例+匿名API正例+双凭据/匿名非空/认证空Ref负例 |
| C-20 | Mapping List/Draft/Revision/Assessment/Proposal/Release/Active GET齐备 | U07/U09/U10/U11刷新/跨用户审核/历史恢复/API映射逐项核对 |

以上 C-17..C-20 属 **新增设计验收**，不替代原 C-01..C-16；本次真实 G4 接口和浏览器 E2E 仍 `NOT_RUN`。

## 4. 产品真实验收矩阵（按功能划分，共 64 条，均待后续阶段实测）

### 连接与管理 S-01..S-13
| ID | 真实操作与期望 |
|---|---|
| S-01 | PG TLS成功/证书不可信失败，错误码不同且不泄证书私钥 |
| S-02 | Oracle serviceName配置与错误alias分开报错，未授权owner不列出 |
| S-03 | Doris FE MySQL wire协议连接成功，非Doris MySQL实例不可冒充Doris功能 |
| S-04 | TDengine WS成功，Native协议默认拒绝；精度和tag有真实检查 |
| S-05 | Web API允许列表GET成功，不允许无副作用合同的POST |
| S-06 | 5源不同输入表单字段/校验、tab/回退保持正确 |
| S-07 | 凭证保存在SecretRef、GET列表和详情无明文，也不进入日志/ZIP |
| S-08 | 连接测试分阶段状态，TCP通但元数据权限不足只返回PARTIAL |
| S-09 | 连接保存/编辑ETag/If-Match、重复幂等键不同载荷返回409 |
| S-10 | 配置或secretVersion改变使原Probe过期，不能凭旧Pass启用 |
| S-11 | 连接停用后新查询不能使用，未完成任务有正确取消/审计 |
| S-12 | 用户只能见自身组织/厂区数据源，越权403且不泄元数据 |
| S-13 | 所有5源安装/驱动/TLS与许可证矩阵实际可核对，缺环境NOT_RUN |

### 元数据和Schema S-14..S-23
| ID | 真实操作与期望 |
|---|---|
| S-14 | PG允许 schema/列完整且不暴露无权表/系统元数据 |
| S-15 | Oracle GetSchema/ALL_* 大小写/空owner/类型正确 |
| S-16 | Doris catalog/database/FE类型差异、DECIMAL与JSON映射正确 |
| S-17 | TDengine stable/subtable/tags/timePrecision/分区枚举正确 |
| S-18 | Web API OpenAPI schema/operation/响应路径安全、无网络remote ref |
| S-19 | Schema hash同输入稳定；字段新增和删除差异可追溯 |
| S-20 | 同名表跨 schema、字段类型变更、缺nullable或主键时未知准确 |
| S-21 | Schema 发现超时/权限不足保留旧快照但标stale，不假成功 |
| S-22 | 大Schema分页、限额、取消和任务关闭后恢复 |
| S-23 | Schema漂移后的活跃Mapping受影响范围精确定位，未知阻断 |

### AI建议和Mapping S-24..S-37
| ID | 真实操作与期望 |
|---|---|
| S-24 | G3 OntologyRelease固定哈希、SKOS语义匹配无越权 |
| S-25 | AI OFF/没有Token仍可手动和规则建议完成映射 |
| S-26 | AI ON只访问组织允许的Schema元数据、预算内且不得发送未批准生产行 |
| S-27 | 字段注释携带prompt injection不能篡改Mapping/Policy |
| S-28 | 同号跨厂返回独立实体或AMBIGUOUS，不误合并 |
| S-29 | 历史别名同厂时间重叠/未知端点遵循G3半开身份规则 |
| S-30 | 温度未声明单位时必须审核，不自动摄氏度化 |
| S-31 | 无时区本地时间与纳秒precision不能默默UTC/毫秒化 |
| S-32 | 一对多/多对多关系映射、预算与结果计数正确 |
| S-33 | 源字段JSON/NULL/MISSING/0值区分、转换失败诊断正确 |
| S-34 | SourceMap修订/SchemaFingerprint/MappingHash绑定真实输入 |
| S-35 | 低风险映射批量接受，高风险待决定清单，有具体来源 |
| S-36 | 不能凭建议自动创建 G3 class/property、不能写G3 dataTurtle |
| S-37 | 未经授权的AI、模型费用超限和Provider故障不让映射流程直接失败或外传 |

### 发布治理与回滚 S-38..S-46
| ID | 真实操作与期望 |
|---|---|
| S-38 | 影响/验证/元数据Hash不同不允许沿用旧评估 |
| S-39 | 提案绑定固定revision/schema/ontology/secretVersion，修改后审批过期 |
| S-40 | 同主体提交/审批被服务端403拒绝，不仅UI灰按钮 |
| S-41 | 批准后源失联/Schema变化时激活失败但旧active不变 |
| S-42 | PG CAS与审计/Outbox同事务，注入故障回滚准确 |
| S-43 | 发布前构建并验证不可变MappingRelease，不覆盖旧包 |
| S-44 | 并发激活仅一成功，另一409，幂等重试不会双写审计 |
| S-45 | 回滚只重新激活固定旧版本、重新授权、来源不兼容时阻断 |
| S-46 | G3 OntologyRelease/Manifests 原字节及旧Run读取兼容 |

### 语义查询/安全/证据 S-47..S-59
| ID | 真实操作与期望 |
|---|---|
| S-47 | 只允许注册的Typed QueryPlan；SQL输入/多语句/越权字段被拒 |
| S-48 | 源端只读账号及执行计划防DML/DDL/函数/管理接口 |
| S-49 | 查询FOUND/EMPTY/PARTIAL/UNAVAILABLE/UNAUTHORIZED/AMBIGUOUS六态真实正反例 |
| S-50 | 3源中一成功一超时一权限拒绝不假EMPTY、不泄无权子结果 |
| S-51 | 同一炉次号跨厂，返回AMBIGUOUS候选且仅展示有权工厂 |
| S-52 | 时间窗口/多对多/源水位/回源Evidence/当前ACL全部正确 |
| S-53 | 来源缺主键时降级证据精度，不伪造SourceRecordRef |
| S-54 | 可取消/超时/重试计入预算，不产生无界继续运行 |
| S-55 | 结果行/字节/内存/join fanout 超限能安全停止或PARTIAL |
| S-56 | 游标过期/源记录变更能识别，不能重复或跳过称精确 |
| S-57 | 历史Run重查证据按当前权限撤权，缓存不泄漏 |
| S-58 | WebAPI SSRF含127.0.0.1、IMDS、DNS rebinding、redirect、IPv6和remote `$ref` 全拒 |
| S-59 | Doris/Oracle/TDengine各自方言不被普通MySQL/PG逻辑错判 |

### 用户界面、部署和资源 S-60..S-64
| ID | 真实操作与期望 |
|---|---|
| S-60 | 13界面单元每项至少一个成功、失败、恢复交互；点击导航有真实作用 |
| S-61 | Next/shadcn设计一致，亮/暗主题、窄屏、键盘及加载/空/错误/拒绝完整 |
| S-62 | Mac ARM64、Windows WSL2 AMD64、Linux AMD64 Compose依实际授权真实启动/健康检查或NOT_RUN |
| S-63 | task-specific Docker前后回执，OWN/KEEP/DELETE分类，旧G2/G3卷无误删 |
| S-64 | 五源纵向用户操作“配置→发现→映射→发布→查询→故障恢复”真实完成且可追溯 |

## 5. 典型合成覆盖数据准备
建议合成工程基线覆盖：厂 A、B 均有 `heat_no=001`；一炉多测点及临时换设备；单位为摄氏/开尔文及未知；TDengine序列ns/ms；API重复页/循环页/429/跳转；Oracle NUMERIC precision；Doris重复和JSON；删列及类型变化；源TLS失败/凭据失败；跨scope/回滚/过期。**任何 Synthetic 测例不得冒充真实业务 Gold**。业务人员未来至少审核数十个典型映射与复杂反例后确定质量门槛。

## 6. E0 效率与资源节奏
- Preflight：核对真实 main 与受权 TaskId/上一Head/现有Worktree/工具链/后端环境/资源，再冻结 owned_paths，公共Contracts/Host/DTO/锁/CI/OIDC/迁移 Master单写。
- 每个里程碑按影响面运行廉价单测/契约负例；真实服务/浏览器/多源 E2E 在稳定输入上按预算执行一轮，第一次失败缩小复现，禁止每次证据提交重新跑长流程。
- Docker资源先盘点和唯一 project，测试结束分类回收；旧包保持immutable/有回执，不能无差别 `docker system prune -a --volumes`。
- 独立 Reviewer 不能修改自己审查的代码；发现P1必须有可复现最短负例，不做只靠措辞的伪缺陷。
- `base/head/testedCommit` 明确，V3只是源码/证据保真，不代表业务 E2E PASS；原始失败/CI NOT_RUN保留。

## 7. 阶段完成标志（预案）
- `G4_00_CONTRACT_READY_FOR_CHATGPT_REVIEW`：后续 Codex 经**单独用户批准**实施 G4-00 文档化和独立审查时使用，不代表 G4 产品已运行。
- `G4_M1_CONNECTION_READY_FOR_REVIEW` 等 M1~M5 需各关的真实出关矩阵；不得自动进入下一步。
- `G4_RUNTIME_PARTIAL`：有真实源/平台缺失或某安全负例未达标；不得自称 G4 结束。

## 8. 面向用户的下一步授权顺序（此处不是执行授权）
1. ChatGPT 本次提交 G4-00 设计包并自审。
2. 用户若同意，另行批准 Codex `G4-00-CONTRACT-001` **仅工程合同冻结与独立review**。Codex 只产任务卡/冻结合同/测试计划与V3，不写产品代码。
3. ChatGPT 审查其文件/证据/ADR、裁决未决项。
4. 用户再授权 `G4-M1-CONNECTION-001`，届时按授权试验 PG、Docker、Secret 与最小端到端，扩源另分阶段。

## 9. G4-00 V1.1 未来产品验收增量（S-65..S-70）

| ID | 真实操作与期望 |
|---|---|
| S-65 | G4 AMBIGUOUS 在实际同号场景返回至少两个有权且可区分的 candidate，并各有可定位 evidence；无权候选不泄漏 |
| S-66 | G2 原 `SemanticQueryResult` 对旧调用方 byte/schema 兼容；G4 新 URL 使用版本化 DTO，不能错误 cast 或丢证据/诊断 |
| S-67 | 连接创建 body、JSON Schema、五源动态表单和错误提示一致；旧扁平结构及 `command.expectedRevision=null` 被拒 |
| S-68 | TDengine profile 出现 credentialRef/重复凭据被拒；Web API NONE→null/认证时→非空；SecretRef 不回显且异Scope引用拒绝 |
| S-69 | 编辑者保存 Mapping 后跨设备刷新恢复当前与历史修订，409 冲突显示真实差异；GET 不写状态 |
| S-70 | 审核者从 PENDING 列表获取固定 Proposal，独立审核、审批过期及激活/CAS失败可恢复；历史 MappingRelease/active 读取严格一致 |

未来验收总计为 **S-01..S-70 共70条**；G4-00 的设计 C-01..C-20 共20条。不得将新设计样例校验冒充这些未来真实产品测试。
