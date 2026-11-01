# 09 · G4-00-CONTRACT-001 Codex Master 正式任务合同 V1.1（未来执行用）

> **授权状态：AWAITING_SEPARATE_USER_EXECUTION_APPROVAL**。
> 本次 ChatGPT 只编制/交付；此文档不能单独授权 Codex 新建分支、写仓库、推送、执行有副作用命令或调取外部源。只有用户后续明确批准并主动启动新 Codex 会话，才能依照本合同执行**G4-00 工程合同归档与审查**。**绝不启动 G4-M1 产品开发**。

## 1. Task header（每轮固定上报）
| 项目 | 内容 |
|---|---|
| TaskId | `G4-00-CONTRACT-001` |
| Codex 会话标题 | `本体平台｜G4-00 五源连接与 AI Native 语义数据正式合同冻结` |
| Stage | `G3 frozen → G4 contract → G4-M1~M5 → G5/G7/G8`；G6独立支线 |
| 推荐 Master | GPT-6 Astra / High（复杂五源+G3兼容/安全裁决） |
| 非作者 Reviewer | GPT-6.1 Sol / High（若当前可选；否则等价高强度并记录实值） |
| Worker | 默认不启写者；只读 Explorer 仅在独立厂商研究确有需要时1名 |
| 运行 | 本地 Codex Worktree、Ask for approval、Standard speed，先 Plan/checklist 再执行文档化合同 |
| 源基线 | G3 `main=d1a61daffe844475b07705797e3ad325cc3f2945`（本次核对）；开工重新fetch、检查 HEAD/Worktree |
| G6 实验分支 | `codex/g6-p0-parser-prep-master` Head `851fa...`、`codex/g6-p0-dependency-lock-001` Head `72a883...`：只作历史参考，不直接合/拣选 |
| 交付形式 | 合同归档 + 独立审查 + 自测证据 + 一个 Review ZIP V3 + 独立重开；**仅在实际获得执行授权后** |
| 退出 | `G4_00_CONTRACT_READY_FOR_CHATGPT_REVIEW` 或 `G4_00_CONTRACT_BLOCKED_WITH_WITNESS`，停止等待ChatGPT |

## 2. Master 首先应该做什么
1. 安全解包本任务输入 ZIP 至 TaskId 唯一临时路径，先做 CRC、path traversal/symlink、SHA256SUMS 和 Manifest 校验；读 `README-FIRST.md`，保留只读输入Hash。
2. 在**用户另行批准后**从 `origin/main` 新建独立托管 Worktree/任务分支 `codex/g4-00-contract-001`；读实际仓库 `AGENTS.md`/适用子目录/`PLANS.md`/`current-authorization.md`、冻结 G2/G3 contracts、`docs/planning/04-roadmap-and-dependency-dag.md`、`03-module-feature-matrix.md`、最新 local-validation-policy、review-package-spec、resource-lifecycle、ai-development-efficiency。对所有输入记录 SHA/real branch。
3. 制定约束精确的 ExecPlan（目标/可观察成果/OwnedPaths/验证/回退/停机条件），先核实设计包每一重要决策与现有G3边界是否冲突；冲突分类 `EXISTING_CONTRACT_WINS/CLARIFY_IN_G4_CONTRACT/REQUIRES_USER_DECISION`，**不按 ChatGPT 文档假设修改G3**。
4. 如果合同结构可直接匹配，执行本任务下的**文档与机器可检验合同归档**，不写实现代码；在任务证据里记录所有 Proposals 与仍待实测的 ADR。

## 3. 允许写入的最小文件清单（未来获得该TaskId授权后）
- `docs/contracts/g4-00-connections.md`（五源配置/Probe/Catalog/安全/状态）
- `docs/contracts/g4-00-mapping.md`（MappingDraft/Release/Approval/Identity/Time/单位）
- `docs/contracts/g4-00-query.md`（受控Query计划、六态/来源/预算/ACL）
- `docs/contracts/g4-00-ui.md`（13界面与类型配置，loading/error/permission/冲突）
- `docs/planning/g4-implementation-plan.md`（G4-M1~M5依赖和切片）
- `docs/tasks/G4-00-CONTRACT-001.md`（本次任务卡，授权事实/路径/测试）
- `docs/evidence/G4-00-CONTRACT-001/**`（合同/独立审查/静态校验及资源证据）
- `docs/tasks/current-authorization.md` **仅允许在本TaskId另行执行授权时**增加准确的授权段落，不得覆盖G3/G6历史事实。
- 如需 JSON Schema 作为真实机器可检验合同，优先在 `docs/contracts/g4/` 独立存放（本次专属）；暂不触及 `docs/contracts/g2-models.json` 及所有生成物。

任何跨现有 `Contracts/Host/AppHost/迁移/依赖锁/CI/DesignTokens/UI源码/后端模块/共享开发脚本` 的修改，均**不在本任务授权范围**，应形成下一关 G4-M1 前精确审批清单后停止，不能借“修一点小问题”越界。

## 3A. 合同冻结前必须完成的 REQUEST_CHANGES 回归门禁（V1.1）

**不得恢复使用 V1.0 的陈旧Schema和样例**。先检查 `docs/14-REVIEW-CLOSURE.md`，再用明确的 JSON Schema Draft 2020-12 验证全部21个合成正例、16个Schema负例和3个Schema合法但业务约束错误的语义反例；对本体平台当前正式 G2 `SemanticQueryResult/CommandContext` 核对完整字段、`expectedRevision=0`、证据语义与旧路由。无验证器时保留 `NOT_RUN/BLOCKED`，不得声称校验通过。

必须审阅 `GET /mappings...` 列表/版本/草稿/评估/审核/正式版本/active 与 U07/U09/U10/U11 的一一对应，独立测试 P1 缺候选、P2 旧请求、凭据不一致、跨用户审核刷新失败。发现 P1/P2 再次回现时先做最短可复现负例，不直接将其发布为 FROZEN。

## 4. 主要合同产出内容
- 五源类型差异完整定义（配置/认证/TLS/Schema/查询/时间/类型/错误/证据/驱动许可/平台）。
- 动态UI schema → backend validator → probe state → Draft/Active/Disabled 真实状态机，逐个动作可追至拟议API及权限要求。
- G3 OntologyRelease 与独立 MappingRelease 的权威/版本/归属关系。PG active映射 CAS/Outbox/异人审批，绝不将生产数据写 G3 synthetic dataTurtle。
- 从 SourceScope/ActorScope 到字段 ACL、源端只读、SQL Query AST/HTTP防SSRF、Query Gateway六态、证据/水位/SourceRef 的守卫。
- 映射建议的 OFF/LOCAL/APPROVED_EXTERNAL 三模式、Schema/本体上下文、可验证建议、人工审核/冲突/漂移及审计；不允许 AI 自动写正式本体或 MappingRelease。
- 历史 G3 合同兼容：G2 OIDC、CommandContext、Semantics、统一Gateway/MCP、G3-M4 Identity/Time和影响分析边界；旧 DTO/Run hash不可更改。
- 首期 PG/M1 小纵向切片、Oracle/Doris/TDengine/WebAPI 后续真实适配、Ontop 受控对比（非强制实现）、G4-M3/M4/M5集成、G5/G7依赖。
- G4-ADR-01~08 记录 `PROPOSED/APPROVED_FOR_DESIGN/BLOCKED_FOR_IMPLEMENTATION`，真实驱动/镜像/模型/生产源许可必须另批。

## 5. 源证据等级与冲突裁决
- `REPOSITORY_FROZEN`: 当前main冻结合同及实际已测试代码，优先于本次新的设计建议。
- `OFFICIAL_DOC_VERIFIED`: 厂商/OWASP/OpenAI官方文档提供的能力/版本/风险（必须记录URL、访问日和适用版本），不等于本机真正运行。
- `PROJECT_DESIGN_PROPOSAL`: 本包的新DTO/API/数值预算/UI/验收与分工，由人类与 Reviewer 继续裁决。
- `EXPERIMENT_NOT_RUN`: 驱动/数据库/Compose/LLM/五源/真实浏览器/多架构，仍为NOT_RUN。

若发现 G4 与 G3 `SourceBundle/SourceHashes/IdentityClaim/Run/Gateway` 不兼容，**不能改G3或自行发明新的RDF事实模型**，要先写精确冲突/推荐版本化扩展策略，交ChatGPT/用户再裁决。

## 6. Codex 工程效率优先规则（LL必查）
- **一次性预检**：只取本轮涉及的 G2/G3 文件，不扫描所有源代码或把3MB历史Review包放上下文；只检查五源与Gateway/Publishing/Governance的边界。
- **先合同审查后测试**：优先写可机读错误码/状态/字段的相互关系检查，再形成静态正反样例；不重复运行毫无变化的 .NET、browser、docker全量测试。
- **只读官方验证**：确有引用需要，允许默认公开文档的只读官方核查；不复制大量官网正文到仓库，引用落档到Sources。用户未授权新的账号/收费/下载/内网，不得触达。
- **避免复杂并行**：Master负责领域与合同一个写者；Reviewer仅只读；独立 Explorer 可收集 Oracle/TDengine/OWASP事实但不得改文件。若子代理受限，Master顺序执行不伪造多代理证据。
- **停止证据优先**：任何未批准驱动/镜像/网络权限/数据源/模型需要另批准，立即标 `BLOCKED`，仍完成无关文档；不能循环创建多份同类“准备”报告。
- **资源清理**：本次只做文档，预期 Docker 资源=0；实际 Before/After 只读盘点允许则保留原始来源/准确ID。临时解包专属资源用 nofollow/归属证明精准回收，旧G3/G6树和卷一律KEEP。

## 7. 验证门禁与非作者 Review
符合合同任务的验证：`README/Manifest/SHA + source-pointer check + 模型/字段枚举/状态/权限/API表一致性 + 示例 JSON Schema Draft2020-12 语法+21正向/16 Schema负向/3语义负向验证 + URL/跨厂/SQL/审计/过期回滚威胁推演 + git diff --check + 适用SelfTest`。**不要求跑 .NET/浏览器/真实五源**，也绝不能写成那些运行能力PASS。

Reviewer应提出最少 15 个攻击型反例：包括选错厂区、SQL越权、API跳内部服务、来源字段缺时间单位、终止/反复取消、旧映射审批重放、Schema漂移、Secret泄漏、同号不同厂、Doris错误类型、TDengine精度、Oracle别名、G3兼容、自批、自主合并。需要 CODE REVIEW+产品 UX审查同时 PASS；同一问题上次已裁决不能重复开伪P1。必要的合同问题只做最小文档修订，不修改源码。

**交付后**：Master提交任务分支（若未来TaskId授权含创建/推送），新V3 `-ValidationSource LOCAL -Status PARTIAL` 以当前真实测试矩阵记录设计阶段；VerifyOnly独立重开PASS，回执Base/Head/TestedCommit/Hash，停止等ChatGPT。V3 status=PARTIAL 是因为 G4 产品 Runtime NOT_RUN，即使合同设计关口通过。

## 8. 最短成功检查清单
- 五源均有独立配置表单、测试结果分级、API/字段/错误和数据/SSL/时区风险。
- 13个UI单元有关键按钮和完整状态/权限/恢复，入口/跳转与API正确闭环。
- SourceConnection/SchemaSnapshot/MappingDraft/Assessment/Proposal/Release/FederatedQuery 状态可机械核对；旧G3权益不变。
- 六态/SourceReadReceipt 来源与效时/观测时间有准确字段，缺失/错版本不能作为FOUND。
- source read-only 三层、SSRF/SQL注入、异人审批和CAS均有正反 test plan。
- 五源真实驱动/Windows/ARM64/CI/模型 API NOT_RUN 如实保留，G4-M1下一批精确授权。
- 独立Reviewer 和V3只有**实际未来执行时**才能宣称完成。

## 9. 禁止事项
本TaskId没有实施 G4-M1 的许可；不得修改本体/正式schema，创建数据库表/迁移、安装驱动、开启Docker/端口/数据卷、连接真实生产或隔离源、上传元数据至模型服务、调用付费API、移动G6提交到main、修改G3/E0工具、自动CI、大量包下载、全局资源清理。不能把 `API schema example` 当作可用 REST 端点，不能把“Document design PASS”当作 `G4 DONE`。
