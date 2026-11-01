# 14 · G4-00-CONTRACT-001 V1.1 四项 REQUEST_CHANGES 关闭报告

**状态**：`PROPOSED_G4_DESIGN_V1_1 / REQUEST_CHANGES_RESOLVED_LOCALLY / AWAITING_USER_REVIEW`。

**审查输入**：V1.0 ZIP（82,878 bytes；原始 SHA256 `0e397b907b81aa4e41854eac395dd4a02fb9145a358208f5bdf2328ae2c6a281`）、用户四项审查缺陷、G3 main `d1a61daffe844475b07705797e3ad325cc3f2945` 的 `G2Models.g.cs` 与 `SemanticEndpoints.cs` 冻结源码。既有 G6 `PARTIAL/BLOCKED_WITH_WITNESS` 事实不变。本轮仅 ChatGPT 编制/审查设计输入，不修改 GitHub 仓库，不授权 Codex，五源 runtime / Docker / 模型 API / 浏览器均 NOT_RUN。

## 1. 缺陷逐项裁决

| ID | 严重度 | V1.0 可复现问题 | V1.1 修订 | 机器及文档验收证据 |
|---|---|---|---|---|
| CR-01 | P1 | QueryResult strict additionalProperties=false 却缺 candidates/evidence/validTime/observedAtUtc/diagnostics；AMBIGUOUS 返回空候选；且 G2 的严格嵌套 DTO 不可直接承载 G4 源数据 | `G4QueryResultV1` 明确版本化，保留六态及11个 G2 同名语义字段，另有 schemaVersion。candidates 与 G2 EntityCandidate 字段同义；证据改用独立 `G4SourceEvidenceRef`，绑定当前授权/SourceReadReceipt/MappingRelease；G2 DTO 和旧 `/api/v1/semantic/queries` 不变，新增 `/api/v1/data/semantic-queries` | JSON Schema `G4QueryResultV1`；21正例中六态各有设计样例；AMBIGUOUS 两名不同 IRI 候选且 evidenceIds 可回链，FOUND/PARTIAL 有证据；R01..R05/R15/R16 缺失、非法、额外字段被拒；05§8、06 附录 |
| CR-02 | P2 | `05` 的创建正文 `type/connectionProfile/secretInput/command` 与 schema `config/secretRef` 冲突；create 的 G2 expectedRevision 误写 null | 唯一 `ConnectionCreateRequest.payload` 定义 displayName/scopeSelection/config:{type,profile}/secretRef/command；创建 expectedRevision=0，真实 Secret 走独立受保护通道；README/05/Schema/样例保持一致 | 5类类型正例+匿名Web API正例，05§5.1 内联 JSON 用 Schema 校验通过；R06..R08 旧字段/缺命令/null revision 拒绝 |
| CR-03 | P2 | schema 所有连接必须非空 secretRef，却又支持 WebAPI authentication=NONE；TDengine profile 的 credentialRef 与顶层 secretRef 可以不同 | 唯一顶层 secretRef（null 仅 WebAPI NONE）；TDengine profile 删除 credentialRef；Web API API_KEY_REF/OAUTH_* 必须非空；PG/Oracle/Doris/TD 必须非空。SecretRef 由服务器校验组织、主体、用途和有效期 | Schema if/then 双分支，R09..R12 拒绝重复Ref及错误认证组合；positive WebAPI NONE=null；05§5.1、03五源表、06§末 |
| CR-04 | P2 | 仅定义 Mapping 写接口；页面跨用户审核与刷新后无法找回固定 revision/proposal；U07 的 `/edits` 与 API 的 PATCH 冲突 | `GET /mappings`、draft详情、固定revision、diff、assessment、pending proposal列表/固定详情、mapping release历史与active指针补齐；U07/U09/U10/U11 读写轨迹一致，统一 PATCH+CAS | Schema新增 MappingListPage/ProposalView/ReleaseView/RevisionDiffView/AssessmentView；21正例含这五类；R13 缺冻结SchemaFingerprint拒绝；05§10、03§8、C20、S69/S70 |

## 2. 冻结 G2 对照的具体影响

- 当前 G2 `SemanticQueryResult` 字段为 `status,data,candidates,evidence,snapshot,subSources,validTime,observedAtUtc,traceId,limited,diagnostics`，对所有未知 JSON 字段为 Disallow。G4 **不应**给它直接追加 `mappingReleaseIds` 或把真实源 `EvidenceRef` 硬转换成需要 Jena 图 IRI 的 G2 EvidenceRef。
- G2 `CommandContext` 四字段都为必需；**create `expectedRevision=0`**。普通 `PATCH` 必须与 `If-Match` 对齐，不允许从 JSON 客户端传授予组织外 Scope。
- G2 实际 `POST /api/v1/semantic/queries` 保持不变；拟新增 G4 查询 `POST /api/v1/data/semantic-queries`，内部复用同一授权与网关链路，不建立第二个并行的基础查询引擎。
- V1.1 Schema 仅是**未来 G4 的设计合同样例**。正式 REST 模型与 OpenAPI 必须经后续 G4 Master 单写者审查与授权；不能把本 JSON 文件当作已实施的 C#/TypeScript/RDF 权威模型。

## 3. 固定可运行的交付包校验

运行环境拥有 Python 标准库时：

```bash
python verify_input.py
```

已有 `jsonschema` Draft 2020-12 Python 库时**进一步**运行：

```bash
python verify_schema.py
```

这两个脚本均只读自身 ZIP 解包文件，不安装新依赖、不联网、不访问数据库或 Docker。`verify_schema.py` 没有 jsonschema 库时退出码3并明确 `NOT_RUN`，不自动下载安装。必须保留此局限，不能将 `verify_input.py` 的标准库结构检查写为完整 JSON Schema PASS。标准库检查核对 13 个页面、C01..20、S01..70、5源、6态、接口关键路径、Manifest/SHA；Schema 检查独立验证 21 正/16 Schema负 + 3语义反例/2内联JSON/证据交叉引用。

本次 ChatGPT 环境中**实际**运行 Draft202012Validator.check_schema + 21正例通过 + 16 Schema负例均被拒 + 3语义负例拒绝 + 2 Markdown 内联 REST body 通过。输出详情见 `docs/12-DESIGN-REVIEW.md`；设计结构/语义检查不能替代未来真实 API、跨厂 ACL、SQL 与正式发布测试。

## 4. 留待 G4-00 Codex 合同复审及 G4-M1 实施的边界

- 当前 8 个 G4 ADR 仍为 proposed，不能将新增的安全凭据上传接口误写成已部署能力。
- 新 G4QueryResultV1 是**版本化提议**；未来后端须为所有六态和子源实际状态确定唯一转换、Schema/生成接口，执行跨调用方兼容性测试，尤其不能使 G2 Snapshot/Run/旧 Evidence 发生字节变化。
- 密钥签发只从属源凭证安全模块，不要求业务人员每次重复输入；WebAPI 真正匿名可由网络策略批准，匿名≠不受 Scope/SSRF 管理。
- Mapping 审核读取允许跨用户但不越 Scope；固定提案的核心版本/哈希不能在审批期间重读可变草稿来代替。
- G4-M1 真 PostgreSQL 垂直闭环、Oracle/Doris/TDengine/Web API、Docker、LLM 和浏览器测试 `NOT_RUN`；用户此次仅要求方案修订/自审，没有授权 Codex 直接执行。

## 5. 复审建议

`REQUEST_CHANGES` 的四项内部合同冲突已在 V1.1 修复并以机器样例验证。**建议用户复审 V1.1，再决定是否授权 Codex `G4-00-CONTRACT-001` 仅做仓库中的工程合同冻结与非作者独立审查。** 不允许跳至 G4-M1 或把 G6 分支合并 main。

**审查标记**：`G4_00_V1_1_REQUEST_CHANGES_RESOLVED_AWAITING_USER_REVIEW`。

### 附加的防误判校验

另加入 `samples/g4-wire-contract-v11-semantic-negative-cases.json` 的 X01..X03：**它们故意满足 JSON Schema，但分别违反证据ID关联、可见厂区和非作者审核规则**。`verify_schema.py` 须先证明这些负例在 Schema 层通过，再在纯合成的语义交叉检查中明确拒绝。避免把字段校验当成授权、完整证据或审批验证。
