# G4-00-CONTRACT-001 · Codex 输入包 V1.1

**项目**：`on-dotnet/ontology-platform` · 本体智能平台。**修订日期**：2026-11-01；**本包用于纠正用户 REQUEST_CHANGES 的四项合同缺陷**，V1.0 不可再用于工程冻结。
**当前授权**：用户仅授权 ChatGPT 形成、核查、交付设计与 Codex 输入包；**未授权 Codex 自动执行、修改仓库、网络连接、付费 API、Docker 资源及合并 main**。

## 使用顺序
1. 先阅读 `docs/01-BASELINE-AND-ROADMAP.md`，核实 G3 主线、G6 支线、下一 G4 关口。
2. 读取 `docs/02-G4-PRODUCT-PRD.md` 和 `docs/03-G4-UX-STATE-MATRIX.md`，这是用户使用与交互的主要设计依据。
3. 读取 `docs/04-CONNECTOR-MATRIX.md`、`docs/05-DATA-API-CONTRACT.md`、`docs/06-SECURITY-AND-QUERY.md`、`docs/07-AI-NATIVE-ALIGNMENT.md`，这是 G4 领域与接口裁决。
4. 必须先核对 `docs/14-REVIEW-CLOSURE.md` 的四项请求修改及严格 JSON Schema 回归。然后读取 `docs/08-STAGES-ACCEPTANCE.md` 和 `docs/11-PITFALL-QUALITY-GATES.md`，评估计划与避免返工。
5. 只有用户**另行正式批准** Codex 执行 `G4-00-CONTRACT-001` 后，才使用 `docs/10-CODEX-START-COPY.md` 在新的 Codex 会话中启动；该任务也只准做方案/合同验证与任务分解，禁止直接进入 G4-M1 产品实施。
6. `docs/09-CODEX-EXECUTION-CONTRACT.md` 是后续给 Codex 的唯一执行任务合同；`docs/12-DESIGN-REVIEW.md` 是本次 ChatGPT 自审结果；`docs/13-SOURCES-AND-DECISIONS.md` 为来源与已决/未决说明。

## 状态说明
- `FROZEN_UPSTREAM`：G3 已审定语义、发布、身份、权限和工具合同；本包不能替代或修改这些合同。
- `APPROVED_PRODUCT_DIRECTION`：用户批准 G4 为下一产品主线；本次方案细节属于 ChatGPT 设计建议，需 Codex 独立合同审查后再批准实施。
- `PROPOSED_G4_CONTRACT`：G4 此次新提出的 DTO、API、交互、错误码、状态机和数值预算，**不是仓库已存在能力**。
- `NOT_RUN`：所有 G4 五源真实连接、.NET、Docker Compose、Web 浏览器、外部模型的运行验收均未执行。
- `BLOCKED_DEPENDENCY`：G6 的 Docling 依赖问题保持独立，不作为 G4 阻断。

## 仓库读取策略
ZIP 刻意不复制数 MB 的历史源码或过时 `AGENTS.md`。Codex 使用已绑定真实仓库读取最新：`AGENTS.md`、`PLANS.md`、`docs/tasks/current-authorization.md`、`docs/contracts/g2-thin-slice-contracts.md`、G3-M1~M5 适用合同、`docs/development/{local-validation-policy,ai-development-efficiency,resource-lifecycle,review-package-spec}.md`。G6 分支不可自动合入 G3 `main`。

## 交付校验
顶层 `MANIFEST.json`、`SHA256SUMS.txt` 覆盖其他全部有效载荷，包下载后可使用 Python 标准库 `zipfile.testzip()` 与 `hashlib.sha256` 验证。清单不能证明实际产品功能已验收。

## V1.1 的四项合同修复（优先阅读）

1. 查询输出采用 `G4QueryResultV1`，六态 + 完整候选/证据/时间/诊断；G2 `SemanticQueryResult` 及端点不变。
2. `ConnectionCreateRequest` 只有 `config:{type,profile}`、`secretRef`、`command`，创建 expectedRevision=0；旧扁平字段拒绝。
3. SecretRef 唯一顶层引用，TDengine profile 没有 credentialRef；匿名Web API 使用null。
4. Mapping GET 读接口和 UX 保存、审核、版本恢复全部补齐。

校验命令：`python verify_input.py`（标准库完成结构和跨文档检查；系统具备 `jsonschema` 时进一步执行 `python verify_schema.py`，否则明确其 NOT_RUN，不允许未安装自动下载安装）。
