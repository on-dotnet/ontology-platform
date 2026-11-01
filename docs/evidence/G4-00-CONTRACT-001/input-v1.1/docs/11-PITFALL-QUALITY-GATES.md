# 11 · 历史问题防复发台账：G4 强制预防项（版本1.0）

## A. 延续 G3/G6 的真实问题（不重新改写旧任务事实）
| ID | 已发生/已审风险 | G4-00及后续任务必须做到 |
|---|---|---|
| LL-001 合同误判 | G3-M5 曾误把“当前支持Profile”当历史Release Profile | 先检查字段字义/冻结合同/DTO/测试；有语义争议先判 `AS_DESIGNED/UI_CLARIFICATION/CONTRACT_CHANGE_REQUIRED`，**不先修后端** |
| LL-002 阶段偏航 | G6预检和依赖锁占用多轮，但G4还没启动 | 本任务必须显式显示G3→G8主线；G4是当前产品建设主线、G6是独立支线 |
| LL-003/004 依赖解析与原生库 | Docling/PaddleX extras、numpy固定pin导致源闭包未完成 | 五源驱动也必须真实锁定许可+版本+目标平台；不把官方“可用”冒充当前可安装；不为求解失败连续创建无效新观察任务 |
| LL-005 商用许可 | MinerU附加署名；top-level许可不覆盖全部依赖与权重 | Oracle/TDengine/MySqlConnector/Npgsql/镜像许可证单独记录，若商业限制UNKNOWN则不能声称可商用发布 |
| LL-006 metadata≠runtime | G6枚举metadata却未真正求解/安装 | G4必须把 Schema发现、Adapter Probe、真实查询、端到端浏览器分别标阶段；纯JSON合同不冒充真实源 |
| LL-007 平台混淆 | Mac ARM64和Windows WSL2 AMD64不等于同一种wheel/driver | G4 Compose测试必须分别有Linux ARM64/AMD64原生/仿真标签；CI/Windows未做就NOT_RUN |
| LL-008 秘钥/费用 | G6六Provider合同真实密钥/模型未运行 | G4默认不调用LLM；任何真实Secret/外联另授权，安全输入且不入Git、日志、ZIP |
| LL-009 昂贵重复检查 | G3/G6多次长SelfTest/宿主连续监测造成时间与SSD浪费 | 精确输入版本→先短失败→改动层测试→稳定输入完整一次；无关证据提交不机械触发所有重测 |
| LL-010 Reviewer找出负例缺陷 | G6-PREP曾出现Decimal四舍五入、bool/int混淆、userinfo/profile注入等 | G4时间/单位/Decimal/URL/SQL/Secret/权限的负例为首要测试，Reviewer不得只查 happy-path |
| LL-011 Docker资源 | 旧8卷等被保护、bridge漂移原因未知 | 不全局 prune/down -v，TaskId/RunId/ID和实际Docker backend前后清单，KEEP有解除条件 |
| LL-012 分支隔离 | G6-PREP/LOCK Head均未合main | G4从G3 main为权威；引用G6只读研究，避免自动cherry-pick/合并实验代码 |
| LL-013 ZIP下载/失效 | 曾发生链接不可用、HTML空图谱、外部Mac绝对路径无效 | 必须由容器真实生成、校验精确路径、解包CRC/sha/Manifest/成员总数；一个ZIP且内部可复制Prompt |
| LL-014 Prompt过厚 | 历史任务堆积重复AGENTS/提示词，前置阅读费时 | `README-FIRST`+唯一执行合同+短启动词；仅按需读取冻结源及本任务相邻文件；避免复制整个旧ReviewZIP |
| LL-015 先跑工具后检查 | G6-PREP的SelfTest/脚本接口不匹配造成假失败 | 先检验脚本确实支持TaskId/参数；未覆盖G4时标NOT_RUN/提出升级申请，不偷改全局脚本 |
| LL-016 权威数据边界 | G3 RustFS Release只适合小SourceBundle，G6知识/文档不能替代 G3 Evidence | G4 SourceEvidence和MappingRelease独立；不写G3 SourceBundle/dataTurtle或持久化生产全量数据 |
| LL-017 AI 不是自动发布 | G6-00要求AI主动工作、用户做决策 | G4 Schema/Mapping由AI建议、人处理风险、异人正式审批；不靠高置信度自动发布 |
| LL-018 过度并行 | 每任务强启Master+2写者浪费分支/上下文 | G4-00仅Master+非作者Reviewer；G4产品阶段合同单写、非交叠Worker按需启动 |

## B. 新增 G4 预防项
| ID | 风险 | 必测的防止复发证据 |
|---|---|---|
| G4-LL-019 表单不闭环 | 曾有数据源只登记系统名称而无类型参数/连通测试 | 五种类型的表单/Probe/错误/保存/启停/Secret轮换状态必须全部形成可走通UI与API |
| G4-LL-020 假只读 | `SELECT`字符串过滤、WebAPI POST等被当安全 | 源端最小只读账户+受控QueryPlan+Adapter只读执行，SQL语法、函数、SSRF负例 |
| G4-LL-021 同号误合并 | 相同炉号跨厂区、同厂历史多编码 | G3 IdentityClaim完整 org/site/ns/有效期复用；多个候选返回AMBIGUOUS，不自动sameAs |
| G4-LL-022 单位/时间偷猜 | TD ns、Oracle DATE/无时区、温度无单位 | `UNKNOWN`保留并阻断高风险映射；来源/时间精度进入证据 |
| G4-LL-023 六态误用 | 连接失败时显示“0条”或部分数据为FOUND | 统一六态正反用例；全部必需源可用才EMPTY，权限/partial不泄漏 |
| G4-LL-024 源Schema变化破坏查询 | 映射绑定字段改名/类型变化后继续执行旧计划 | Snapshot hash/CAS影响与重新验证；缺少证据标INDETERMINATE而非0差异 |
| G4-LL-025 自动生成SQL泄漏 | AI工具可直接执行LLM SQL/指定目标URL | 仅已有Capability、TypedPlan、有限字段、源端ACL；禁止任意SQL/URL端点 |
| G4-LL-026 发布混版 | Mapping审批绑定source/schema/ontology不完整 | 独立MappingRelease、固定hash、异人审批、PG CAS+审计/Outbox、错误保持旧active |
| G4-LL-027 特殊源错误当兼容 | Doris按MySQL、TD按普通SQL、Oracle权限视图 | 每源协议/类型/分页/时间/认证/许可证独立真实E2E，不用Fake全源PASS |
| G4-LL-028 静态安全假通过 | HTTP IP检测与实际连接之间存在DNS rebinding | 用真实测试服务验证连接时 IP绑定/redirect/proxy/IPv6/SSRF；静态正则检查不够 |
| G4-LL-029 查询把生产数据物化 | 为Graph方便全量搬运时序事实 | 只读虚拟/按需查询、SourceReadReceipt独立，缓存另批，G3图不污染 |
| G4-LL-030 忽视受权可见性 | 历史Run/缓存持有旧数据，用户权限撤销后仍可查看 | 每次再次授权Evidence与敏感数据读取，结果不跨组织缓存 |

## C. 任务重复阻断处理
发生同一问题两次且输入未变化：停止无意义重复执行，返回 `BLOCKED_WITH_WITNESS`，列最小可行方案及需用户单独批准的准确权限。不可因同类失败连跑昂贵全量测试。每个真正实施任务结束将新问题写任务自身证据，**不能倒改历史闭关审查包**。ChatGPT 下轮引用适用条目即可，避免大规模重复提示词。

## G4 V1.0 → V1.1 本轮复审新增防重犯规则

| 编号 | 已经发生的根因 | 后续固定防线 |
|---|---|---|
| G4-LL-028 查询 DTO 只核对六态 | 设计 Schema 禁额外字段却少候选、证据、时效、诊断 | 查询 DTO 以 G2 已生成类型清单为起点逐字段核对；真实源不能伪装 Synthetic Evidence；另建显式版本化读模型并测失真拒绝 |
| G4-LL-029 参考样例绕过 Schema | Markdown 中的 type/connectionProfile/secretInput 与 Schema 的 config/secretRef 冲突 | REST body 只允许一个请求封装；文档样例从测试样例来源同步，正负自动校验 |
| G4-LL-030 命名重复与匿名来源 | TD profile 与顶层 secretRef 两处互斥；匿名API被一律要求密钥 | secretRef 只在连接顶层；JSON Schema if/then 按 AuthMethod 条件验证；真实轮换独立 |
| G4-LL-031 映射只列写接口 | 保存后编辑者、审核者、历史版本无法重开 | 所有工作流必须有列表/详情/固定版本/评估/提案/历史/active 的 GET 对应和错误恢复 |
| G4-LL-032 冻结命令约束漂移 | G2 CommandContext create expectedRevision 为0，示例写null | 从仓库已生成 DTO 核对数值语义；创建和 CAS 修改用不同检查路径 |
| G4-LL-033 设计自审过早 PASS | V1 仅校验8个正例，遗漏跨文件/反例矛盾 | 设计出包前加机器校验、反例、正式 DTO 对照和完整页面操作追踪；不把自审当非作者审查 |
