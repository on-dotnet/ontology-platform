# OntologyPlatform · Codex Master G1-CLOSE-001 收口修复与阶段验收授权 V1.0

> **请在 Mac Codex 原 Master 会话的普通执行模式使用。** 本文档是本轮明确实施授权，不是仅供总结的参考材料。起始仓库：`/Users/chasen/Developer/repos/ontology-platform`，远程：`on-dotnet/ontology-platform`。

## 0. 推荐的 Codex 模型与强度

| 岗位 | 模型 | 推理强度 | 选择依据 |
|---|---|---|---|
| Master / Integrator | GPT-6.1 Sol (`gpt-6.1-sol`) | High | 多模块协调、契约把关、工作树合并、CI 证据 |
| SEC 修复 Owner | GPT-6 Astra（如可用） | Medium / High | 认证与敏感审计边界；无 Astra 则 Sol High |
| OBS 修复 Owner | GPT-6.1 Sol | Medium | 原生日志、OTel 与 Grafana 契约 |
| Independent Security Reviewer | GPT-6 Astra | High | 审查权限/审计/脱敏/越权负例 |
| 低风险脚本与文档 | GPT-6 Luna | Medium | 成本较低，但必须经过可复现门禁 |

若 Codex 当前客户端无法分别指定子 Agent 模型，由 Master 使用 **GPT-6.1 Sol + High**，通过独立 Reviewer 和真实测试保障质量。此任务不必整体使用 Extra High、Max 或 Ultra；只有出现复杂未解安全/并发问题再升级。

## 1. 当前基线与审查事实

- G1 Wave 2 主线起点：`e930935749bcb88d51abb94db4a41695bbbe6717`。
- 本轮收口 **BaseSha**：`d181f66e569e190a66b0f48b179f2fd9390b9467`。
- 已经确认 GitHub Action `40199269314` 对应 BaseSha，`engineering`、`governance-integration` 两个 Job 均 success。
- G1 Wave 2 的 Mac 开发/纵向 SEC、FE、OBS 测试有真实证据；`PARTIAL` 总状态包含 Windows/Intel、镜像完整 CVE/SBOM/签名、生产证书轮换及运行目标未验证，**不得将它们改成 PASS**。
- ChatGPT 复审上传 Review ZIP（大小 6,530,531 B，SHA-256 `00ce77ab05c32c97824194456ccaedf1eb4f52318258627a4969918c978ca9a4`），验证 1,090 ZIP 成员及逐项散列；复核实际代码发现下面两项需要收口。

开始前必须阅读仓库 `AGENTS.md`、`PLANS.md`、`docs/tasks/current-authorization.md`、`docs/tasks/G1-WAVE2.md`、G1 Wave 2 Master 交付记录、架构与注释规范、当前代码、真实 CI 证据。先 `git fetch`，验证 main 对应预期 BaseSha、工作树和所有保留 Worktree 状态。若远程前进、发现未预期用户改动或其他正在进行的写入，保护现场、先分析再继续，**不得 reset --hard、force push 或丢弃他人代码**。

## 2. 本轮明确授权范围

批准创建并执行 **G1-CLOSE-001**（G1 Wave 2 收口修复及阶段验收）：

1. 修复审计读取行为未记录成功审计的问题；
2. 修复运行时异常过度统一为 503、缺少足够安全诊断的可观测性缺口；
3. 对两个改动新增真实负例与回归测试，保持 SEC/BFF/审计/FE/OBS 已通过链路不退化；
4. 对照 G1 退出标准产出 **G1 验收矩阵**、未完项分期跟踪，以及 G2 的只读准备事项；
5. 按原来的独立 Worktree、任务分支、及时 Commit/Push、Single Writer、独立审查、CI 验证、主线集成与单一 Review ZIP 交付。

**不授权** G2 本体建模、Jena 正式发布逻辑、MCP、Agent、SSE；不引入新业务模块、新数据库或额外外部模型；不修改生产凭证、管理员权限、真实业务数据、外部系统。不要为了修复两个缺口重写整个认证系统、查询服务或 UI。

## 3. Issue A：审计查询成功也必须留下审计事实（P1）

实际代码位置：

- `backend/src/Hosts/OntologyPlatform.Api/PlatformEndpoints.cs` 的 `ReadAuditAsync`：无权访问时已调用 `AuditService.WriteAsync`，但成功返回 `PlatformAuditEntry[]` 时，当前没有同等的成功审计写入。
- `backend/src/Hosts/OntologyPlatform.Api/Security/AuditService.cs` 与 Governance DbContext / AuditRecord 是现有统一持久化通道。

要求：

- 授权的审计查询成功时，在响应返回前提交 `platform.audit.read`（名称可纳入事件目录规范）的不可否认审计记录；持久化失败不得返回假成功。
- 不把完整审计行、请求参数、JWT、Cookie、用户 PII 或 SQL 原文写入运行日志。
- 只记录经过授权的 Actor、操作、审计资源、结果、真实 Scope、Trace/Correlation、UTC 时间；如需要记录查询范围/返回数，采用受控字段和隐私界限。
- 明确多厂区审计读取的 Scope 语义，**不能默默把一次跨多个授权厂区的审计查询归属到任意第一个厂区**。在保留已有资源范围检查的前提下给出最小正确的数据表示和权限方案；确需修改 schema 时由唯一 Migration Owner 实施并增加迁移与恢复测试，不使用字符串堆叠冒充标准结构。
- 如果新审计事件能被当前查询读到，明确其时序（一次请求是否显示自己的审计事件），确保重复请求与并发下行为可解释、无递归写入。

验证（至少）：审计角色允许读取且新增一条成功审计；无审计角色返回 403 并记录拒绝；会话失效 401；空集合也记录实际敏感查询；跨厂和多厂区作用域不泄露其他厂区；PG 审计写入失败时不返回 200；审计事件包含有效 TraceId；响应不暴露秘密；真实 PostgreSQL 集成测试通过。

## 4. Issue B：安全、结构化的异常诊断（P1）

实际代码位置：

- `backend/src/Hosts/OntologyPlatform.Api/PlatformApiHost.cs` 请求中间件 `catch (Exception) ...` 当前对多种故障一律返回 503；`finally` 只记录 `route/status/traceId/auditId`，缺乏受控的内部故障分类。
- `PlatformTelemetry.cs` 已使用官方高性能 `LoggerMessage` Source Generator，应继续采用。

要求：

- 保留对浏览器的简洁 `ProblemDetails` 与 Trace ID，避免泄露异常堆栈、数据库连接串、用户输入、OIDC 参数和安全凭证。
- 增加一个带稳定 EventId/EventName 的**受控诊断事件**：记录固定路由模板、异常类别（白名单枚举/稳定错误码）、TraceId、结果；禁止将任意原始 `Exception.Message`、`Exception.ToString()` 或可能含敏感数据的异常对象无过滤地导出 Loki。
- 明确区分可判定的业务/认证/输入类错误和基础设施故障；**不要粗暴将所有异常改成 500 或 503**，保持当前已验收的 OIDC/CSRF/权限/数据库故障结果。
- 测试请求取消、响应已开始、数据库连接失败、正常异常、健康检查等负例；验证日志与 Tempo Span 能关联，Alloy 的低基数/脱敏合同不被破坏。
- 使用 .NET 原生 `ILogger`、`LoggerMessageAttribute`、`Activity`/OpenTelemetry，第三方日志封装/AutoMapper/通用 Repository 不引入。

## 5. 阶段验收与剩余风险，不篡改历史

创建 G1 阶段收口验收记录：

- `G1-ENG-001`、`G1-INFRA-001`、`M0-MAC-PORTABILITY-001`、`G1-SEC-001`、`G1-FE-001`、`G1-OBS-001` 的历史状态独立保留；新增“截至本次收口已满足的基础能力”与相应真实证据，不能把历史 `PARTIAL` 直接改写成全部 PASS。
- 按 14 个产品模块，明示 G1 只交付基础设施、安全、基础前端及可观测性，不宣称已经实现 OWL/SHACL 本体设计器、指标规则中心、知识处理、数据连接器、智能体或 G2+ 业务。
- “用户行为分析 / Faro”当前仅有事件 Schema、治理设计，未见完整事件接收与产品分析端到端实现；作为以后业务阶段的显式计划，不宣称已交付。完整中文业务运维中心也区别于已完成的 Grafana 中文基础仪表盘。
- FE 目前确认有 `@base-ui/react`、Tailwind CSS 和自研视觉组件，但不能因为风格类似就宣称 shadcn/ui 生成组件或设计系统分包已经完整采用；保持已批准的 Next.js + shadcn/ui/Base UI 目标，明确 G2 编辑器组件引入、tokens 和全局样式拆分的实际边界及验收。
- 当前 BFF `Web:Origin` 仅接受回环 HTTP，适用于当前同机开发，但跨主机/容器 Next SSR 的未来生产拓扑需在部署 ADR 中明确解决，不能把 G1 开发配置当作 HA 生产方案。
- Windows、Intel Mac 原生、镜像完整 CVE/SBOM/签名、生产证书轮换/SLO/RPO/RTO 均保留 NOT_RUN/NOT_VERIFIED，在阶段门禁中列明负责阶段与前置条件。Linux CI 不代替 Windows 真实运行。
- 评估但不要擅自修改 GitHub 分支保护设置（目前 GitHub 读取 `main.protected=false`）。提出适合单人仓库的受保护 main、必经 CI、审批/PR 配置方案及可能产生的成本/权限影响，不擅自启用。
- 本轮仅允许**只读地**准备 G2 首条纵向切片的接口、数据示例和依赖 DAG，不得编写 G2 功能源码或启动 G2 进程。

## 6. 并行与代码所有权

由 Master 创建独立任务卡/工作树/分支：

- `G1-CLOSE-SEC`：仅修改 Audit 的必需模块、`PlatformEndpoints.cs` 及对应 SEC Tests；如有迁移，契约/迁移仍单一 Owner；
- `G1-CLOSE-OBS`：仅修改 `PlatformTelemetry.cs` 和受控异常诊断相关的宿主代码及观测负例；
- `Independent Reviewer`：只读复核两组变更及全部集成差异，不进行修复实现；
- `Master`：独占公共契约、迁移、Git 主线、CI、审查打包、任务/阶段记录与集成验收。

同一文件不得由两个写 Agent 并行编辑。对于安全代码中间件与端点相互依赖的修改，先冻结接口与测试契约。多个 Agent 的时间收益不能以破坏授权逻辑、诊断脱敏或数据一致性为代价。

各任务分支及时提交并推送；仅经过独立 Reviewer + 真正测试后的成果由 Master 集成 `main` 并及时 Push。未验证代码可远程备份为 DRAFT，不可冒充 main PASS。不强推、不覆盖未授权本地状态、不删除保留历史 Worktree。

## 7. 强制测试和质量门禁

- Mac Apple Silicon：受锁依赖恢复、.NET Release build、`dotnet format`、全部 Infrastructure/Security Tests、测试数据隔离 PG+Keycloak、必要的 Web lint/typecheck/Vitest/build/Playwright、OpenAPI 契约。
- SEC/OBS 两项新增真实测试，至少证明审计成功事件、范围与回滚/失败关闭，及固定异常诊断、Trace 关联、日志脱敏；原 Wave 2 本地端到端正反例不得退化。
- LGTM 能接收到真实**受控**异常诊断事件，确认 Loki 低基数及 Tempo Trace 关联；不存在完整 LGTM 启动前提时保留 BLOCKED/NOT_RUN，不改造一个内存假对象冒充验收。
- GitHub Linux CI 与最终 **HeadSha** 对齐，记录真实运行链接和所有 Job 结论。Windows/Intel 未执行时仍为 NOT_RUN。
- 继续遵守中文 C# XML 注释（类型、实体、属性、枚举、成员、方法、变量）及属性之间空行规范，保持显式 DTO 映射、模块边界和官方包优先。
- 为所有新增回归提供负例、失败结果及通过结果；不得只运行新增的两项测试后跳过原有集成门禁。

## 8. 最终交付方式

自动生成**唯一**审查 ZIP（不含 `.git`、密码、令牌、PFX、密钥、测试私有配置、缓存、真实用户数据），使用现有 `scripts/create-review-package.ps1` 及独立 VerifyOnly。内容必须包含：

- 全量 HEAD 已提交源代码、Base..Head 完整 diff、Git 状态与提交清单；
- G1 收口任务卡、ADR/依赖变更（如有）、独立 Reviewer 报告、测试原始脱敏输出、故障注入证据、CI 结果和阶段验收矩阵；
- `manifest.json`、全部成员散列、最终 ZIP SHA-256，以及被排除文件类别；
- 真正运行项 PASS、受阻项 BLOCKED、未运行 NOT_RUN、未知 NOT_VERIFIED，不能伪造 CI 或跨平台结论。

本轮完成后，输出：

`G1_CLOSE_READY_FOR_REVIEW`

然后**停止并等待 ChatGPT 审查**；未经后续用户明确授权，不执行 G2，不自动改变 G1 以外的阶段计划，也不启动任何生产环境操作。
